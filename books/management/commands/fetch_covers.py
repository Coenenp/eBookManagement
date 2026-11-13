"""Management command: fetch external cover images for unreviewed books.

Walks ``FinalMetadata`` rows whose ``final_cover_path`` is an ``http(s)`` URL,
whose ``unresolved_reason`` is empty and which are not yet reviewed, downloads
the image into ``MEDIA_ROOT/cover_cache`` under a name derived from the sha256
of the content, and rewrites ``final_cover_path`` to the media-relative path
(``cover_cache/<sha256><ext>``). The original URL is preserved in a CSV log
outside the repository.

Usage::

    python manage.py fetch_covers [--limit N] [--dry-run]
"""

import csv
import hashlib
import io
import time
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

import requests

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db.models import Q

from books.models import FinalMetadata
from books.utils.safe_move.book import _cover_flag

try:
    from PIL import Image
except ImportError:  # pragma: no cover - Pillow is a project dependency
    Image = None

# Log lives outside the repository so the original URL is never lost.
LOG_PATH = Path("/workspace/state/fetch_covers_log.csv")

MAX_BYTES = 10 * 1024 * 1024  # 10 MB
MIN_BYTES = 2 * 1024  # 2 KB
MIN_SHORT_SIDE = 100  # pixels
TIMEOUT = 20
USER_AGENT = "eBookManagement/1.0 (+https://github.com/Coenenp/eBookManagement)"

EXT_BY_FORMAT = {"JPEG": ".jpg", "PNG": ".png", "GIF": ".gif"}


def _host_for(url):
    """Return the netloc of a URL (the throttle key), or "" when unparseable."""
    try:
        return urlparse(url).netloc
    except ValueError:
        return ""


def _min_interval(host):
    """Minimum seconds between two requests to the same host."""
    if "google" in host:
        return 0.5
    if "openlibrary" in host:
        return 1.0
    return 0.0


def _sleep(seconds):
    time.sleep(seconds)


def _download(url):
    """Download ``url``, streaming up to MAX_BYTES; raise on any failure."""
    resp = requests.get(
        url, timeout=TIMEOUT, headers={"User-Agent": USER_AGENT}, stream=True
    )
    resp.raise_for_status()
    chunks = []
    size = 0
    for chunk in resp.iter_content(8192):
        size += len(chunk)
        if size > MAX_BYTES:
            raise ValueError("image exceeds 10 MB")
        chunks.append(chunk)
    return b"".join(chunks)


def _classify(content):
    """Return (ext, width, height) for a valid raster image, else None."""
    if Image is None:
        return None
    try:
        img = Image.open(io.BytesIO(content))
        img.load()
        fmt = img.format
        width, height = img.size
    except Exception:
        return None
    ext = EXT_BY_FORMAT.get(fmt)
    if ext is None:
        return None
    return ext, width, height


class Command(BaseCommand):
    help = "Fetch external cover images for unreviewed books with a URL cover"

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        limit = options["limit"]
        dry_run = options["dry_run"]

        qs = (
            FinalMetadata.objects.filter(
                Q(final_cover_path__startswith="http://")
                | Q(final_cover_path__startswith="https://"),
                unresolved_reason="",
                is_reviewed=False,
            )
            .order_by("id")
        )

        downloaded = 0
        too_small = 0
        skipped = 0
        failed_by_host = Counter()
        processed = 0
        last_request = {}

        for fm in qs.iterator():
            if processed >= limit:
                break
            processed += 1
            url = fm.final_cover_path
            if not url.startswith(("http://", "https://")):
                skipped += 1
                continue

            host = _host_for(url)
            _throttle(host, last_request)

            try:
                content = _download(url)
                info = _classify(content)
            except Exception:
                failed_by_host[host] += 1
                self._log(fm, url, "", 0, 0, 0, "failed")
                continue

            if info is None:
                # non-image (or unreadable) content is rejected
                failed_by_host[host] += 1
                self._log(fm, url, "", len(content), 0, 0, "failed")
                continue

            ext, width, height = info
            if len(content) < MIN_BYTES or min(width, height) < MIN_SHORT_SIDE:
                too_small += 1
                self._log(fm, url, "", len(content), width, height, "too-small")
                continue

            name = hashlib.sha256(content).hexdigest() + ext
            rel = f"cover_cache/{name}"
            dest = Path(settings.MEDIA_ROOT) / rel

            if dest.exists():
                # never overwrite an existing file: just point at it
                skipped += 1
                self._log(fm, url, rel, len(content), width, height, "skipped")
                if not dry_run and fm.final_cover_path != rel:
                    fm.final_cover_path = rel
                    fm.save(update_fields=["final_cover_path"])
                continue

            if not dry_run:
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(content)

            # validate the written file through the move-flow helper
            if _cover_flag(rel) is not None:
                failed_by_host[host] += 1
                self._log(fm, url, "", len(content), width, height, "failed")
                continue

            if not dry_run:
                fm.final_cover_path = rel
                fm.save(update_fields=["final_cover_path"])

            downloaded += 1
            self._log(fm, url, rel, len(content), width, height, "downloaded")

            if processed % 25 == 0:
                self.stdout.write(
                    f"processed {processed}: downloaded {downloaded}, "
                    f"too-small {too_small}, skipped {skipped}"
                )

        self.stdout.write(f"downloaded: {downloaded}")
        self.stdout.write(f"too-small: {too_small}")
        self.stdout.write(f"skipped: {skipped}")
        for host in sorted(failed_by_host):
            self.stdout.write(f"failed {host}: {failed_by_host[host]}")

    def _log(self, fm, url, local_path, size, width, height, outcome):
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        new = not LOG_PATH.exists()
        with open(LOG_PATH, "a", newline="") as fh:
            writer = csv.writer(fh)
            if new:
                writer.writerow(
                    ["book_id", "original_url", "local_path", "bytes", "width", "height", "outcome"]
                )
            writer.writerow([fm.book_id, url, local_path, size, width, height, outcome])


def _throttle(host, last_request):
    """Sleep until the per-host minimum interval has elapsed since the last request."""
    interval = _min_interval(host)
    if interval <= 0:
        return
    now = time.monotonic()
    prev = last_request.get(host)
    if prev is not None:
        wait = interval - (now - prev)
        if wait > 0:
            _sleep(wait)
    last_request[host] = time.monotonic()
