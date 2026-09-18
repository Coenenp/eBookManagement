"""
Tests for the cover-cache maintenance command and AJAX endpoint.
"""

from io import StringIO
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse

from books.models import Book, BookFile
from books.utils.cover_cache import CoverCache


class CleanCoverCacheCommandTest(TestCase):
    """Tests for the ``clean_cover_cache`` management command."""

    def setUp(self):
        self.test_data = b"fake cover data"
        CoverCache.clear_all()

    def tearDown(self):
        CoverCache.clear_all()

    def _create_referenced_and_orphan(self):
        """Create one referenced and one orphaned cached cover."""
        _, referenced_path = CoverCache.save_cover("/referenced/book.epub", self.test_data, "cover.jpg")
        _, orphan_path = CoverCache.save_cover("/orphan/book.epub", self.test_data, "cover.jpg")

        book = Book.objects.create()
        BookFile.objects.create(
            book=book,
            file_path="/referenced/book.epub",
            file_format="epub",
            cover_path=referenced_path,
        )

        return referenced_path, orphan_path

    def test_dry_run_reports_without_deleting(self):
        """Dry-run reports would-be deletions and leaves files untouched."""
        referenced_path, orphan_path = self._create_referenced_and_orphan()

        out = StringIO()
        call_command("clean_cover_cache", "--dry-run", stdout=out)

        output = out.getvalue()
        self.assertIn("Would delete orphaned covers: 1", output)
        self.assertTrue(CoverCache.media_exists(referenced_path))
        self.assertTrue(CoverCache.media_exists(orphan_path))

    def test_command_deletes_only_orphans(self):
        """Non-dry-run deletes orphaned covers and keeps referenced ones."""
        referenced_path, orphan_path = self._create_referenced_and_orphan()

        out = StringIO()
        call_command("clean_cover_cache", stdout=out)

        output = out.getvalue()
        self.assertIn("Deleted orphaned covers: 1", output)
        self.assertTrue(CoverCache.media_exists(referenced_path))
        self.assertFalse(CoverCache.media_exists(orphan_path))

    @patch("books.scanner.folder._detect_and_extract_cover")
    def test_rebuild_missing_updates_bookfile(self, mock_extract):
        """--rebuild-missing re-extracts missing internal covers."""
        mock_extract.return_value = ("cover_cache/rebuild.jpg", "epub_internal", "cover.jpg", True)

        book = Book.objects.create()
        book_file = BookFile.objects.create(
            book=book,
            file_path="/fake/book.epub",
            file_format="epub",
            cover_path="cover_cache/missing.jpg",
            has_internal_cover=True,
        )

        out = StringIO()
        call_command("clean_cover_cache", "--rebuild-missing", stdout=out)

        book_file.refresh_from_db()
        self.assertEqual(book_file.cover_path, "cover_cache/rebuild.jpg")
        self.assertEqual(book_file.cover_internal_path, "cover.jpg")
        self.assertTrue(book_file.has_internal_cover)
        self.assertIn("Rebuilt covers: 1", out.getvalue())


class CleanCoverCacheAjaxTest(TestCase):
    """Tests for the cover-cache cleanup AJAX endpoint."""

    def setUp(self):
        self.test_data = b"fake cover data"
        CoverCache.clear_all()

        self.client = Client()
        self.user = User.objects.create_user("testuser", "test@example.com", "password")
        self.client.login(username="testuser", password="password")

    def tearDown(self):
        CoverCache.clear_all()

    def test_clean_cover_cache_ajax_deletes_orphans(self):
        """POSTing to the endpoint deletes orphaned covers and returns stats."""
        _, referenced_path = CoverCache.save_cover("/referenced/book.epub", self.test_data, "cover.jpg")
        _, orphan_path = CoverCache.save_cover("/orphan/book.epub", self.test_data, "cover.jpg")

        book = Book.objects.create()
        BookFile.objects.create(
            book=book,
            file_path="/referenced/book.epub",
            file_format="epub",
            cover_path=referenced_path,
        )

        response = self.client.post(reverse("books:ajax_clean_cover_cache"))

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["deleted"], 1)
        self.assertEqual(data["errors"], 0)
        self.assertEqual(data["file_count"], 1)
        self.assertEqual(data["orphan_count"], 0)
        self.assertTrue(CoverCache.media_exists(referenced_path))
        self.assertFalse(CoverCache.media_exists(orphan_path))

    def test_clean_cover_cache_ajax_requires_login(self):
        """Anonymous users cannot trigger cache cleanup."""
        self.client.logout()

        response = self.client.post(reverse("books:ajax_clean_cover_cache"))

        self.assertNotEqual(response.status_code, 200)
