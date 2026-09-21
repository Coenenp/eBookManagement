"""Regression tests for the cover-image 404 fix.

Two producers built cover URLs that dropped the ``cover_cache/`` segment, and
served a broken media URL when the cached file no longer existed on disk
(48 stale ``BookFile.cover_path`` references in the test DB). These tests pin
the corrected behaviour:

* a media-relative ``cover_cache/<hash>.jpg`` path is served with its
  ``cover_cache/`` segment intact, and
* a missing cover falls back to the placeholder instead of a 404 URL, and
* the display helper clears a missing local path so the template renders the
  placeholder.

Each test only creates and removes the specific cache file it owns (keyed by
its own book path), so it is safe to run even before the test-settings
isolation lands.
"""

from pathlib import Path

from django.conf import settings
from django.test import TestCase

from books.models import FinalMetadata
from books.templatetags import book_extras
from books.tests.test_helpers import create_test_book_with_file
from books.utils.cover_cache import CoverCache
from books.utils.metadata_helpers import get_book_cover_url


class CoverCacheUrlFixTests(TestCase):
    """``get_book_cover_url`` must keep the cover_cache segment and avoid 404s."""

    def setUp(self):
        self.test_data = b"\xff\xd8\xff\xe0fake-jpeg-bytes"
        self.book_path = "/book/with_cover.epub"
        _, self.relative_path = CoverCache.save_cover(self.book_path, self.test_data, "cover.jpg")
        self.addCleanup(CoverCache.delete_cover, self.book_path, "cover.jpg")

    def _book_with_cover(self, cover_path):
        book = create_test_book_with_file(file_path="/book/x.epub", file_format="epub")
        FinalMetadata.objects.create(book=book, final_title="T", final_author="A", final_cover_path=cover_path, is_reviewed=True)
        return book

    def test_existing_cover_cache_path_keeps_segment(self):
        """A cached cover_cache/ path is served as /media/cover_cache/<hash>.jpg."""
        book = self._book_with_cover(self.relative_path)
        url = get_book_cover_url(book)

        self.assertEqual(url, f"{settings.MEDIA_URL}{self.relative_path}")
        self.assertIn("/cover_cache/", url)

    def test_missing_cover_cache_path_returns_placeholder(self):
        """A stale cover_cache/ path must not produce a broken media URL."""
        book = self._book_with_cover("cover_cache/deadbeef_missing.jpg")
        url = get_book_cover_url(book)

        self.assertEqual(url, CoverCache.placeholder_url())
        self.assertNotIn("deadbeef_missing", url)

    def test_absolute_cover_path_is_normalised(self):
        """An absolute path under MEDIA_ROOT is normalised to a media URL."""
        absolute = str(settings.MEDIA_ROOT) + "/" + self.relative_path
        book = self._book_with_cover(absolute)
        url = get_book_cover_url(book)

        self.assertEqual(url, f"{settings.MEDIA_URL}{self.relative_path}")

    def _write_cache_file(self, filename):
        """Write a file into the cover_cache dir and return its relative path."""
        cache_dir = Path(settings.MEDIA_ROOT) / "cover_cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        target = cache_dir / filename
        target.write_bytes(self.test_data)
        self.addCleanup(lambda: target.unlink(missing_ok=True))
        return f"cover_cache/{filename}"

    def test_absolute_path_from_previous_media_root_serves_media_url(self):
        """A stale absolute path whose file exists in the current cache is rebased."""
        stale_absolute = f"/old/media/root/{self.relative_path}"
        book = self._book_with_cover(stale_absolute)
        self.assertEqual(get_book_cover_url(book), f"{settings.MEDIA_URL}{self.relative_path}")

    def test_absolute_path_from_previous_media_root_missing_returns_placeholder(self):
        """A stale absolute path whose file is gone falls back to the placeholder."""
        stale_absolute = "/old/media/root/cover_cache/deadbeef_missing.jpg"
        book = self._book_with_cover(stale_absolute)
        self.assertEqual(get_book_cover_url(book), CoverCache.placeholder_url())

    def test_absolute_path_outside_any_media_root_returns_placeholder(self):
        """An absolute path with no cover_cache/ segment returns the placeholder."""
        book = self._book_with_cover("/some/random/path/cover.jpg")
        self.assertEqual(get_book_cover_url(book), CoverCache.placeholder_url())

    def test_windows_style_path_with_backslashes(self):
        """A Windows-style absolute path is normalised and rebased."""
        filename = self.relative_path.rsplit("/", 1)[-1]
        windows_path = f"C:\\media\\cover_cache\\{filename}"
        book = self._book_with_cover(windows_path)
        self.assertEqual(get_book_cover_url(book), f"{settings.MEDIA_URL}{self.relative_path}")

    def test_http_url_unchanged(self):
        """An HTTP cover URL is returned unchanged."""
        url = "https://example.com/cover.jpg"
        book = self._book_with_cover(url)
        self.assertEqual(get_book_cover_url(book), url)

    def test_book_id_cover_hash_style_name(self):
        """A book_<id>_cover_<hash>.jpg style cover_cache name resolves to a media URL."""
        relative = self._write_cache_file("book_45_cover_5d6ce040.jpg")
        book = self._book_with_cover(relative)
        self.assertEqual(get_book_cover_url(book), f"{settings.MEDIA_URL}{relative}")

    def test_book_id_cover_hash_style_absolute_path(self):
        """The same style name as a stale absolute path is rebased to a media URL."""
        self._write_cache_file("book_45_cover_5d6ce040.jpg")
        stale_absolute = "/old/media/root/cover_cache/book_45_cover_5d6ce040.jpg"
        book = self._book_with_cover(stale_absolute)
        self.assertEqual(
            get_book_cover_url(book), f"{settings.MEDIA_URL}cover_cache/book_45_cover_5d6ce040.jpg"
        )


class CoverDisplayMissingFileFixTests(TestCase):
    """``_process_cover_for_display`` clears missing local paths (no 404)."""

    def setUp(self):
        self.test_data = b"\xff\xd8\xff\xe0fake-jpeg-bytes"
        self.book = create_test_book_with_file(file_path="/book/display.epub", file_format="epub")

    def test_missing_cover_cache_path_cleared_to_empty(self):
        """A missing cover_cache/ file clears the path so the template shows a placeholder."""
        cover_path, is_url, base64 = book_extras._process_cover_for_display(
            "cover_cache/nonexistent.jpg", self.book, False
        )

        self.assertEqual(cover_path, "")
        self.assertFalse(is_url)
        self.assertIsNone(base64)

    def test_existing_cover_cache_path_encoded(self):
        """An existing cover_cache/ file is resolved and base64-encoded."""
        book_path = "/book/display_with_cover.epub"
        _, relative = CoverCache.save_cover(book_path, self.test_data, "cover.jpg")
        self.addCleanup(CoverCache.delete_cover, book_path, "cover.jpg")

        cover_path, is_url, base64 = book_extras._process_cover_for_display(relative, self.book, False)

        self.assertEqual(cover_path, relative)
        self.assertFalse(is_url)
        self.assertTrue(base64 and base64.startswith("data:image/"))