"""Management command: fetch external cover images for unreviewed books.

Walks ``FinalMetadata`` rows whose ``final_cover_path`` is an ``http(s)`` URL,
whose ``unresolved_reason`` is empty and which are not yet reviewed, downloads
the image into ``MEDIA_ROOT/cover_cache`` under a name derived from the sha256
of the content, and rewrites ``final_cover_path`` to the media-relative path
(``cover_cache/<sha256><ext>``). The original URL is preserved in a CSV log
outside the repository.

Usage::

    python manage.py fetch_covers [--limit N] [--dry-run] [--retry-failed]
                                  [--log-path PATH]
"""

import csv
import hashlib
import io
import os
import time
from collections import Counter
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import requests

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db.models import Q

from books.models import FinalMetadata
from books.utils.cover_quality import PLACEHOLDER_HASHES
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
BELOW_SHORT_SIDE = 200  # pixels; reported in the summary
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
    """Download ``url``, streaming up to MAX_BYTES; raise on any failure.

    The response is held in a ``with`` block so it is always closed, releasing
    the underlying connection even when ``ValueError`` is raised mid-stream.
    """
    with requests.get(
        url, timeout=TIMEOUT, headers={"User-Agent": USER_AGENT}, stream=True
    ) as resp:
        if resp.status_code == 429:
            raise _RateLimited()
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


class _RateLimited(Exception):
    """Raised when a host answers HTTP 429; stops the whole run immediately."""


def _drop_edge(url):
    """Return ``url`` without the ``edge`` query parameter."""
    parts = urlparse(url)
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k != "edge"]
    return urlunparse(parts._replace(query=urlencode(query)))


def _set_zoom(url, zoom):
    """Return ``url`` with the ``zoom`` query parameter set (added if absent)."""
    parts = urlparse(url)
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k != "zoom"]
    query.append(("zoom", zoom))
    return urlunparse(parts._replace(query=urlencode(query)))


def _candidates(url):
    """Return the ordered list of candidate URLs to try for ``url``.

    A Google Books content URL (host ``books.google.com``, path under
    ``/books/content``) is tried three ways: zoom=3, zoom=2, then unchanged,
    with ``edge`` stripped everywhere (it must never be requested). Every other
    URL has a single candidate: the stored URL unchanged.
    """
    parts = urlparse(url)
    host = (parts.hostname or "").lower()
    if host == "books.google.com" and parts.path.startswith("/books/content"):
        return [
            _drop_edge(_set_zoom(url, "3")),
            _drop_edge(_set_zoom(url, "2")),
            _drop_edge(url),
        ]
    return [url]


def _variant_label(url):
    """Return the zoom variant label (``3``, ``2``, ``1`` or ``other``) for a URL."""
    parts = urlparse(url)
    zoom = None
    for k, v in parse_qsl(parts.query, keep_blank_values=True):
        if k == "zoom":
            zoom = v
    return zoom if zoom in ("1", "2", "3") else "other"


class Command(BaseCommand):
    help = "Fetch external cover images for unreviewed books with a URL cover"

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100)
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--retry-failed", action="store_true")
        parser.add_argument("--log-path", default=None)

    def handle(self, *args, **options):
        limit = options["limit"]
        dry_run = options["dry_run"]
        retry_failed = options["retry_failed"]
        self.dry_run = dry_run
        self.log_path = (
            Path(options["log_path"]) if options["log_path"] else Path(LOG_PATH)
        )
        # Read the book ids already attempted (failed / too-small) once, before
        # this run writes any row, so prior failures are skipped unless
        # --retry-failed is given.
        self.attempted = set() if retry_failed else self._read_attempted()

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
        short_sides = []
        variant_counts = Counter()

        for fm in qs.iterator():
            url = fm.final_cover_path
            if not url.startswith(("http://", "https://")):
                skipped += 1
                continue
            if fm.book_id in self.attempted:
                skipped += 1
                continue
            if processed >= limit:
                break
            processed += 1

            content = None
            info = None
            ext = width = height = 0
            fetched_url = ""
            saw_image = False
            last_size = 0
            last_width = last_height = 0

            for cand in _candidates(url):
                host = _host_for(cand)
                _throttle(host, last_request)
                try:
                    content = _download(cand)
                except _RateLimited:
                    self.stdout.write(
                        f"HTTP 429 from {host}; stopped after {processed} rows"
                    )
                    return
                except Exception:
                    continue
                info = _classify(content)
                if info is None:
                    # non-image (or unreadable) content is rejected
                    continue
                ext, width, height = info
                last_size = len(content)
                last_width, last_height = width, height
                saw_image = True
                if len(content) < MIN_BYTES or min(width, height) < MIN_SHORT_SIDE:
                    continue
                fetched_url = cand
                break

            if fetched_url == "":
                if saw_image:
                    too_small += 1
                    self._log(fm, url, "", last_size, last_width, last_height, "too-small")
                else:
                    failed_by_host[_host_for(url)] += 1
                    self._log(fm, url, "", 0, 0, 0, "failed")
                continue

            content_sha = hashlib.sha256(content).hexdigest()
            if content_sha in PLACEHOLDER_HASHES:
                # a placeholder graphic is a failed download: never stored, and
                # the book keeps its URL so it can be retried from another source.
                self._log(fm, url, "", len(content), width, height, "placeholder")
                continue

            name = content_sha + ext
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
                try:
                    self._write_atomic(dest, content)
                except Exception:
                    failed_by_host[_host_for(url)] += 1
                    self._log(fm, url, "", len(content), width, height, "failed")
                    continue
                # validate the written file through the move-flow helper
                if _cover_flag(rel) is not None:
                    failed_by_host[_host_for(url)] += 1
                    self._log(fm, url, "", len(content), width, height, "failed")
                    continue
                fm.final_cover_path = rel
                fm.save(update_fields=["final_cover_path"])

            downloaded += 1
            short_sides.append(min(width, height))
            variant_counts[_variant_label(fetched_url)] += 1
            if not dry_run:
                self._log(fm, url, rel, len(content), width, height, "downloaded", fetched_url=fetched_url)

            if processed % 25 == 0:
                self.stdout.write(
                    f"processed {processed}: downloaded {downloaded}, "
                    f"too-small {too_small}, skipped {skipped}"
                )

        self.stdout.write(f"downloaded: {downloaded}")
        self.stdout.write(f"too-small: {too_small}")
        self.stdout.write(f"skipped: {skipped}")
        self.stdout.write(f"failed: {sum(failed_by_host.values())}")
        self.stdout.write(
            f"short-side-below-{BELOW_SHORT_SIDE}: "
            f"{sum(1 for s in short_sides if s < BELOW_SHORT_SIDE)}"
        )
        self.stdout.write(
            f"smallest-short-side: {min(short_sides) if short_sides else 0}"
        )
        self.stdout.write(
            f"largest-short-side: {max(short_sides) if short_sides else 0}"
        )
        self.stdout.write(
            f"variant-used: 3={variant_counts['3']}, 2={variant_counts['2']}, "
            f"1={variant_counts['1']}, other={variant_counts['other']}"
        )
        for host in sorted(failed_by_host):
            self.stdout.write(f"failed {host}: {failed_by_host[host]}")

    def _write_atomic(self, dest, content):
        """Write ``content`` to a temp file in ``dest``'s folder, then os.replace.

        The final name only ever appears after a complete write, so a failed
        write never leaves a partial file (and the temp is removed on failure).
        """
        tmp = dest.with_name(dest.name + ".tmp")
        try:
            with open(tmp, "wb") as fh:
                fh.write(content)
            os.replace(tmp, dest)
        except Exception:
            if tmp.exists():
                try:
                    tmp.unlink()
                except OSError:
                    pass
            raise

    def _read_attempted(self):
        """Stream the log once into a set of ints (book ids) to skip.

        Only ``failed`` and ``too-small`` outcomes are remembered: a book whose
        cover could not be fetched should not be retried on every run unless
        ``--retry-failed`` is given.
        """
        attempted = set()
        if not self.log_path.exists():
            return attempted
        with open(self.log_path, newline="") as fh:
            for row in csv.DictReader(fh):
                if row.get("outcome") in ("failed", "too-small"):
                    try:
                        attempted.add(int(row["book_id"]))
                    except (ValueError, KeyError):
                        continue
        return attempted

    def _log(self, fm, url, local_path, size, width, height, outcome, fetched_url=""):
        if self.dry_run:
            return
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        new = not self.log_path.exists()
        with open(self.log_path, "a", newline="") as fh:
            writer = csv.writer(fh)
            if new:
                writer.writerow(
                    ["book_id", "original_url", "local_path", "bytes", "width", "height", "outcome", "fetched_url"]
                )
            writer.writerow([fm.book_id, url, local_path, size, width, height, outcome, fetched_url])


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
