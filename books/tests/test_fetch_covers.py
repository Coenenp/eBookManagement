"""Tests for the fetch_covers management command."""

import csv
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
