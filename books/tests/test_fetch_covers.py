"""Tests for the fetch_covers management command."""

import csv
import hashlib
import io
import shutil
import tempfile
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase

from books.management.commands import fetch_covers as fc
from books.models import FinalMetadata
from books.tests.test_helpers import create_test_book_with_file, create_test_scan_folder

from PIL import Image


def _jpeg_bytes(width=300, height=300):
    img = Image.new("RGB", (width, height))
    px = img.load()
    for y in range(height):
        for x in range(width):
            px[x, y] = (
                (x * 37 + y * 17) % 256,
                (x * 13 + y * 29) % 256,
                (x * 7 + y * 43) % 256,
            )
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=95)
    return buf.getvalue()


class FakeResponse:
    def __init__(self, content, status_code=200):
        self._content = content
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests

            raise requests.exceptions.HTTPError(f"{self.status_code}")

    def iter_content(self, chunk_size):
        yield self._content

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FetchCoversCommandTests(TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: shutil.rmtree(self.temp_dir, ignore_errors=True))
        self.scan_folder = create_test_scan_folder(temp_dir=str(self.temp_dir))
        self.counter = 0
        # Isolate MEDIA_ROOT per test (it is shared across the test process).
        media = Path(settings.MEDIA_ROOT)
        if media.exists():
            shutil.rmtree(media, ignore_errors=True)
        media.mkdir(parents=True, exist_ok=True)
        self.log_patcher = mock.patch.object(fc, "LOG_PATH", self.temp_dir / "log.csv")
        self.log_patcher.start()
        self.addCleanup(self.log_patcher.stop)

    def _make_url_book(self, url):
        self.counter += 1
        path = self.temp_dir / f"book{self.counter}.epub"
        path.write_bytes(b"fake")
        book = create_test_book_with_file(
            file_path=str(path),
            file_format="epub",
            scan_folder=self.scan_folder,
        )
        FinalMetadata.objects.create(
            book=book,
            final_title=f"T{self.counter}",
            final_cover_path=url,
            is_reviewed=False,
            unresolved_reason="",
        )
        return book

    def _run(self, get_response=None, **opts):
        target = "books.management.commands.fetch_covers.requests.get"
        if get_response is None:
            get_response = FakeResponse(_jpeg_bytes())
        with mock.patch(target, return_value=get_response) as get:
            call_command("fetch_covers", stdout=io.StringIO(), **opts)
        return get

    def test_download_stores_file_and_updates_path(self):
        book = self._make_url_book("https://books.google.com/books?id=x&printsec=frontcover")
        self._run()
        fm = FinalMetadata.objects.get(book=book)
        self.assertTrue(fm.final_cover_path.startswith("cover_cache/"))
        stored = Path(settings.MEDIA_ROOT) / fm.final_cover_path
        self.assertTrue(stored.is_file())
        self.assertEqual(stored.read_bytes(), _jpeg_bytes())

    def test_second_run_skips(self):
        book = self._make_url_book("https://books.google.com/books?id=y")
        get = self._run()
        self.assertEqual(get.call_count, 1)
        fm = FinalMetadata.objects.get(book=book)
        rel = fm.final_cover_path
        # A second run finds no http-path rows, so nothing is downloaded again.
        self._run()
        self.assertEqual(get.call_count, 1)
        fm.refresh_from_db()
        self.assertEqual(fm.final_cover_path, rel)

    def test_non_image_response_rejected(self):
        book = self._make_url_book("https://example.com/cover")
        self._run(get_response=FakeResponse(b"<html>not an image</html>"))
        fm = FinalMetadata.objects.get(book=book)
        self.assertEqual(fm.final_cover_path, "https://example.com/cover")  # unchanged
        self.assertEqual(list(Path(settings.MEDIA_ROOT).rglob("*")), [])

    def test_too_small_image_not_stored(self):
        book = self._make_url_book("https://example.com/tiny.jpg")
        self._run(get_response=FakeResponse(_jpeg_bytes(width=50, height=50)))
        fm = FinalMetadata.objects.get(book=book)
        self.assertEqual(fm.final_cover_path, "https://example.com/tiny.jpg")  # unchanged

    def test_placeholder_not_stored_and_logged(self):
        book = self._make_url_book("https://example.com/placeholder.jpg")
        content = _jpeg_bytes()
        sha = hashlib.sha256(content).hexdigest()
        with mock.patch("books.management.commands.fetch_covers.PLACEHOLDER_HASHES", {sha}):
            self._run(get_response=FakeResponse(content))
        fm = FinalMetadata.objects.get(book=book)
        self.assertEqual(fm.final_cover_path, "https://example.com/placeholder.jpg")  # keeps URL
        self.assertEqual(list(Path(settings.MEDIA_ROOT).rglob("*")), [])  # nothing stored
        with open(self.temp_dir / "log.csv", newline="") as fh:
            rows = list(csv.DictReader(fh))
        self.assertTrue(rows)
        self.assertEqual(rows[0]["outcome"], "placeholder")

    def test_failure_leaves_path_unchanged(self):
        book = self._make_url_book("https://example.com/missing.jpg")
        with mock.patch(
            "books.management.commands.fetch_covers.requests.get",
            side_effect=RuntimeError("boom"),
        ):
            call_command("fetch_covers", stdout=io.StringIO())
        fm = FinalMetadata.objects.get(book=book)
        self.assertEqual(fm.final_cover_path, "https://example.com/missing.jpg")

    def test_dry_run_changes_nothing(self):
        book = self._make_url_book("https://example.com/dry.jpg")
        self._run(dry_run=True)
        fm = FinalMetadata.objects.get(book=book)
        self.assertEqual(fm.final_cover_path, "https://example.com/dry.jpg")  # unchanged
        self.assertEqual(list(Path(settings.MEDIA_ROOT).rglob("*")), [])

    def test_log_row_written(self):
        book = self._make_url_book("https://example.com/log.jpg")
        self._run()
        with open(self.temp_dir / "log.csv", newline="") as fh:
            rows = list(csv.DictReader(fh))
        self.assertTrue(rows)
        self.assertEqual(rows[0]["book_id"], str(book.id))
        self.assertEqual(rows[0]["original_url"], "https://example.com/log.jpg")
        self.assertEqual(rows[0]["outcome"], "downloaded")

    def test_throttle_called_per_host(self):
        self._make_url_book("https://books.google.com/books?id=a")
        self._make_url_book("https://books.google.com/books?id=b")
        with mock.patch(
            "books.management.commands.fetch_covers.requests.get",
            return_value=FakeResponse(_jpeg_bytes()),
        ), mock.patch("books.management.commands.fetch_covers._sleep") as sleeper:
            call_command("fetch_covers", stdout=io.StringIO())
        # Two requests to the same Google Books host: the second is throttled.
        self.assertTrue(sleeper.called)
        waits = [c.args[0] for c in sleeper.call_args_list]
        self.assertTrue(any(w > 0 for w in waits))

    def test_dry_run_reports_would_download_and_writes_nothing(self):
        book = self._make_url_book("https://example.com/dry2.jpg")
        out = io.StringIO()
        with mock.patch(
            "books.management.commands.fetch_covers.requests.get",
            return_value=FakeResponse(_jpeg_bytes()),
        ):
            call_command("fetch_covers", stdout=out, dry_run=True)
        self.assertIn("downloaded: 1", out.getvalue())
        self.assertIn("failed: 0", out.getvalue())
        fm = FinalMetadata.objects.get(book=book)
        self.assertEqual(fm.final_cover_path, "https://example.com/dry2.jpg")
        self.assertEqual(list(Path(settings.MEDIA_ROOT).rglob("*")), [])
        # No log row is written in dry run.
        log = self.temp_dir / "log.csv"
        if log.exists():
            with open(log, newline="") as fh:
                rows = list(csv.DictReader(fh))
            self.assertEqual(rows, [])

    def test_resumable_skips_failed_and_retry_reaches_them(self):
        b1 = self._make_url_book("https://example.com/fail1.jpg")
        b2 = self._make_url_book("https://example.com/ok2.jpg")
        # First run: only b1 is attempted (limit 1) and it fails.
        with mock.patch(
            "books.management.commands.fetch_covers.requests.get",
            side_effect=RuntimeError("boom"),
        ):
            call_command("fetch_covers", stdout=io.StringIO(), limit=1)
        fm1 = FinalMetadata.objects.get(book=b1)
        self.assertEqual(fm1.final_cover_path, "https://example.com/fail1.jpg")
        # Second run: b1 is skipped (already failed), b2 is reached.
        with mock.patch(
            "books.management.commands.fetch_covers.requests.get",
            return_value=FakeResponse(_jpeg_bytes()),
        ):
            call_command("fetch_covers", stdout=io.StringIO(), limit=1)
        fm2 = FinalMetadata.objects.get(book=b2)
        self.assertTrue(fm2.final_cover_path.startswith("cover_cache/"))
        # With --retry-failed the first row is tried again.
        with mock.patch(
            "books.management.commands.fetch_covers.requests.get",
            return_value=FakeResponse(_jpeg_bytes()),
        ):
            call_command("fetch_covers", stdout=io.StringIO(), limit=1, retry_failed=True)
        fm1.refresh_from_db()
        self.assertTrue(fm1.final_cover_path.startswith("cover_cache/"))

    def test_placeholder_resume_skips_and_retry_reaches(self):
        b1 = self._make_url_book("https://example.com/ph1.jpg")
        b2 = self._make_url_book("https://example.com/ph2.jpg")
        content = _jpeg_bytes()
        sha = hashlib.sha256(content).hexdigest()
        with mock.patch("books.management.commands.fetch_covers.PLACEHOLDER_HASHES", {sha}):
            with mock.patch(
                "books.management.commands.fetch_covers.requests.get",
                return_value=FakeResponse(content),
            ):
                call_command("fetch_covers", stdout=io.StringIO(), limit=1)
        # b1 keeps its URL (a placeholder is never stored).
        fm1 = FinalMetadata.objects.get(book=b1)
        self.assertEqual(fm1.final_cover_path, "https://example.com/ph1.jpg")

        # Second run (limit 1): the placeholder outcome is remembered, so b1 is
        # skipped and b2 is reached without a second request for b1.
        requested = []

        def _get(url, *a, **kw):
            requested.append(url)
            return FakeResponse(_jpeg_bytes())

        with mock.patch(
            "books.management.commands.fetch_covers.requests.get", side_effect=_get
        ):
            call_command("fetch_covers", stdout=io.StringIO(), limit=1)
        fm2 = FinalMetadata.objects.get(book=b2)
        self.assertTrue(fm2.final_cover_path.startswith("cover_cache/"))
        self.assertNotIn("https://example.com/ph1.jpg", requested)
        self.assertIn("https://example.com/ph2.jpg", requested)

        # With --retry-failed the placeholder book is requested again.
        with mock.patch(
            "books.management.commands.fetch_covers.requests.get",
            return_value=FakeResponse(_jpeg_bytes()),
        ):
            call_command("fetch_covers", stdout=io.StringIO(), limit=1, retry_failed=True)
        fm1.refresh_from_db()
        self.assertTrue(fm1.final_cover_path.startswith("cover_cache/"))

    def test_atomic_write_no_final_file_on_replace_failure(self):
        book = self._make_url_book("https://example.com/atomic.jpg")
        with mock.patch(
            "books.management.commands.fetch_covers.os.replace",
            side_effect=OSError("boom"),
        ):
            call_command("fetch_covers", stdout=io.StringIO())
        fm = FinalMetadata.objects.get(book=book)
        self.assertEqual(fm.final_cover_path, "https://example.com/atomic.jpg")
        files = [p for p in Path(settings.MEDIA_ROOT).rglob("*") if p.is_file()]
        self.assertEqual(files, [])

    def test_log_path_option_writes_to_custom_path(self):
        self._make_url_book("https://example.com/logpath.jpg")
        custom = self.temp_dir / "custom_log.csv"
        self._run(log_path=str(custom))
        self.assertTrue(custom.exists())
        with open(custom, newline="") as fh:
            rows = list(csv.DictReader(fh))
        self.assertTrue(rows)
        self.assertEqual(rows[0]["outcome"], "downloaded")

    def test_summary_reports_short_side_stats(self):
        self._make_url_book("https://example.com/short.jpg")
        out = io.StringIO()
        with mock.patch(
            "books.management.commands.fetch_covers.requests.get",
            return_value=FakeResponse(_jpeg_bytes(width=150, height=300)),
        ):
            call_command("fetch_covers", stdout=out)
        self.assertIn("short-side-below-200: 1", out.getvalue())
        self.assertIn("smallest-short-side: 150", out.getvalue())
        self.assertIn("largest-short-side: 150", out.getvalue())

    def test_google_content_first_candidate_is_zoom3_without_edge(self):
        url = (
            "https://books.google.com/books/content?id=abc&printsec=frontcover"
            "&img=1&zoom=1&edge=curl&source=gbs_api"
        )
        self._make_url_book(url)
        calls = []

        def _get(u, *a, **kw):
            calls.append(u)
            return FakeResponse(_jpeg_bytes())

        with mock.patch(
            "books.management.commands.fetch_covers.requests.get", side_effect=_get
        ):
            call_command("fetch_covers", stdout=io.StringIO())
        self.assertEqual(len(calls), 1)
        self.assertIn("zoom=3", calls[0])
        self.assertNotIn("edge=", calls[0])

    def test_too_small_zoom3_falls_back_to_zoom2(self):
        url = "https://books.google.com/books/content?id=abc&img=1&zoom=1&edge=curl"
        book = self._make_url_book(url)

        def _get(u, *a, **kw):
            if "zoom=3" in u:
                return FakeResponse(_jpeg_bytes(width=50, height=50))
            return FakeResponse(_jpeg_bytes())

        with mock.patch(
            "books.management.commands.fetch_covers.requests.get", side_effect=_get
        ) as get, mock.patch("books.management.commands.fetch_covers._sleep"):
            call_command("fetch_covers", stdout=io.StringIO())
        urls = [c.args[0] for c in get.call_args_list]
        self.assertIn("zoom=3", urls[0])
        self.assertIn("zoom=2", urls[1])
        fm = FinalMetadata.objects.get(book=book)
        self.assertTrue(fm.final_cover_path.startswith("cover_cache/"))

    def test_all_candidates_fail_logs_one_failed_row(self):
        url = "https://books.google.com/books/content?id=abc&img=1&zoom=1&edge=curl"
        self._make_url_book(url)
        with mock.patch(
            "books.management.commands.fetch_covers.requests.get",
            side_effect=RuntimeError("boom"),
        ) as get, mock.patch("books.management.commands.fetch_covers._sleep"):
            call_command("fetch_covers", stdout=io.StringIO())
        self.assertEqual(get.call_count, 3)
        with open(self.temp_dir / "log.csv", newline="") as fh:
            rows = list(csv.DictReader(fh))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["outcome"], "failed")

    def test_openlibrary_url_makes_exactly_one_request(self):
        url = "https://covers.openlibrary.org/b/id/12345-L.jpg"
        self._make_url_book(url)
        with mock.patch(
            "books.management.commands.fetch_covers.requests.get",
            return_value=FakeResponse(_jpeg_bytes()),
        ) as get:
            call_command("fetch_covers", stdout=io.StringIO())
        self.assertEqual(get.call_count, 1)
        self.assertEqual(get.call_args[0][0], url)

    def test_fetched_url_column_holds_used_url(self):
        url = "https://books.google.com/books/content?id=abc&img=1&zoom=1&edge=curl"
        self._make_url_book(url)

        def _get(u, *a, **kw):
            if "zoom=3" in u:
                return FakeResponse(_jpeg_bytes(width=50, height=50))
            return FakeResponse(_jpeg_bytes())

        with mock.patch(
            "books.management.commands.fetch_covers.requests.get", side_effect=_get
        ), mock.patch("books.management.commands.fetch_covers._sleep"):
            call_command("fetch_covers", stdout=io.StringIO())
        with open(self.temp_dir / "log.csv", newline="") as fh:
            rows = list(csv.DictReader(fh))
        self.assertEqual(rows[0]["outcome"], "downloaded")
        self.assertIn("zoom=2", rows[0]["fetched_url"])

    def test_http_429_stops_loop_after_current_row(self):
        self._make_url_book("https://example.com/a.jpg")
        self._make_url_book("https://example.com/b.jpg")
        calls = []

        def _get(u, *a, **kw):
            calls.append(u)
            return FakeResponse(b"", status_code=429)

        out = io.StringIO()
        with mock.patch(
            "books.management.commands.fetch_covers.requests.get", side_effect=_get
        ):
            call_command("fetch_covers", stdout=out)
        self.assertEqual(len(calls), 1)
        self.assertIn("HTTP 429", out.getvalue())
        self.assertIn("example.com", out.getvalue())

    def test_dry_run_writes_no_log_for_any_outcome(self):
        self._make_url_book("https://example.com/fail.jpg")
        self._make_url_book("https://example.com/tiny.jpg")
        self._make_url_book("https://example.com/exists.jpg")
        # Pre-create the destination for the "already exists" (skipped) case.
        content = _jpeg_bytes()
        name = hashlib.sha256(content).hexdigest() + ".jpg"
        dest = Path(settings.MEDIA_ROOT) / "cover_cache" / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(content)

        def _get(url, *a, **kw):
            if url.endswith("fail.jpg"):
                raise RuntimeError("boom")
            if url.endswith("tiny.jpg"):
                return FakeResponse(_jpeg_bytes(width=50, height=50))
            return FakeResponse(content)

        with mock.patch(
            "books.management.commands.fetch_covers.requests.get", side_effect=_get
        ):
            call_command("fetch_covers", stdout=io.StringIO(), dry_run=True)

        log = self.temp_dir / "log.csv"
        self.assertFalse(log.exists())
