"""
Tests for the management commands related to scanning.
"""

from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from books.tests.test_helpers import create_test_book_with_file, create_test_scan_folder


class ScanBooksCommandTest(TestCase):
    """Tests for the scan_books management command."""

    def setUp(self):
        self.scan_folder = create_test_scan_folder(name="Test Folder")

    @patch("books.scanner.background.BackgroundScanner")
    @patch("books.management.commands.scan_books.check_api_health")
    def test_scan_folder_command(self, mock_api_health, mock_scanner_class):
        """Test the `scan` action of the command."""
        mock_api_health.return_value = {"google_books": True}
        mock_scanner = mock_scanner_class.return_value
        mock_scanner.scan_folder.return_value = {"success": True, "message": "Test completed"}

        call_command("scan_books", "scan", "/fake/dir")

        mock_scanner_class.assert_called_once()
        mock_scanner.scan_folder.assert_called_once_with("/fake/dir", "en", True)

    @patch("books.management.commands.scan_books.background_scan_folder")
    def test_scan_folder_background_wait(self, mock_scan_folder):
        """Test the `scan` action with --background and --wait flags."""
        with patch("books.management.commands.scan_books.Command.wait_for_completion") as mock_wait:
            call_command("scan_books", "scan", "/fake/dir", "--background", "--wait")
            mock_scan_folder.assert_called_once()
            mock_wait.assert_called_once()

    @patch("books.scanner.background.BackgroundScanner")
    @patch("books.management.commands.scan_books.check_api_health")
    def test_rescan_all_command(self, mock_api_health, mock_scanner_class):
        """Test the `rescan --all` action."""
        mock_api_health.return_value = {"google_books": True}
        mock_scanner = mock_scanner_class.return_value
        mock_scanner.rescan_existing_books.return_value = {"success": True, "message": "Test completed"}

        book = create_test_book_with_file(file_path="/fake/dir/book1.epub", scan_folder=self.scan_folder)
        call_command("scan_books", "rescan", "--all")

        mock_scanner_class.assert_called_once()
        mock_scanner.rescan_existing_books.assert_called_once_with([book.id], True)

    @patch("books.scanner.background.BackgroundScanner")
    @patch("books.management.commands.scan_books.check_api_health")
    def test_rescan_by_ids_command(self, mock_api_health, mock_scanner_class):
        """Test the `rescan --book-ids` action."""
        mock_api_health.return_value = {"google_books": True}
        mock_scanner = mock_scanner_class.return_value
        mock_scanner.rescan_existing_books.return_value = {"success": True, "message": "Test completed"}

        book1 = create_test_book_with_file(file_path="/fake/dir/book1.epub", scan_folder=self.scan_folder)
        book2 = create_test_book_with_file(file_path="/fake/dir/book2.epub", scan_folder=self.scan_folder)
        call_command("scan_books", "rescan", "--book-ids", str(book1.id), str(book2.id))

        mock_scanner_class.assert_called_once()
        mock_scanner.rescan_existing_books.assert_called_once_with([book1.id, book2.id], True)

    def test_rescan_no_target_error(self):
        """Test that `rescan` raises an error if no target is specified."""
        with self.assertRaises(CommandError):
            call_command("scan_books", "rescan")

    @patch("books.management.commands.scan_books.get_scan_progress")
    def test_status_command(self, mock_get_progress):
        """Test the `status` action."""
        mock_get_progress.return_value = {"percentage": 50, "status": "Running"}
        out = StringIO()
        call_command("scan_books", "status", "--job-id", "test-job", stdout=out)
        self.assertIn("Status: Running", out.getvalue())
        self.assertIn("Progress: 0/0 (50%)", out.getvalue())

    @patch("books.management.commands.scan_books.get_api_status")
    def test_status_apis_command(self, mock_get_api_status):
        """Test the `status --apis` action."""
        mock_get_api_status.return_value = {"google_books": {"api_name": "Google Books", "rate_limits": {}}}
        out = StringIO()
        call_command("scan_books", "status", "--apis", stdout=out)
        self.assertIn("API Rate Limit Status:", out.getvalue())
        self.assertIn("Google Books", out.getvalue())

    @patch("books.scanner.background.BackgroundScanner")
    @patch("books.management.commands.scan_books.check_api_health")
    def test_scan_resume_flag(self, mock_api_health, mock_scanner_class):
        """Test the `scan --resume` action dispatches to resume_scan."""
        mock_api_health.return_value = {"google_books": True}
        mock_scanner = mock_scanner_class.return_value
        mock_scanner.resume_scan.return_value = {"success": True, "message": "Resumed"}

        call_command("scan_books", "scan", "/fake/dir", "--resume")

        mock_scanner.resume_scan.assert_called_once_with("/fake/dir", "en", True)
        mock_scanner.scan_folder.assert_not_called()


class ScanContentIsbnCommandTest(TestCase):
    """Tests for the scan_content_isbn management command."""

    @patch("books.scanner.extractors.content_isbn.bulk_scan_content_isbns")
    def test_scan_content_isbn_command(self, mock_bulk_scan):
        """Test the basic execution of the command."""
        # Configure mock to return proper dictionary structure
        mock_bulk_scan.return_value = {"total_books": 1, "books_with_isbns": 0, "total_isbns_found": 0, "errors": 0}
        create_test_book_with_file(file_path="/fake/book.epub", file_format="epub")
        call_command("scan_content_isbn")
        mock_bulk_scan.assert_called_once()


class CompleteMetadataCommandTest(TestCase):
    """Tests for the complete_metadata management command."""

    @patch("books.scanner.folder.query_metadata_and_covers")
    @patch("books.scanner.folder.resolve_final_metadata")
    def test_complete_metadata_command(self, mock_resolve, mock_query):
        """Test the basic execution of the command."""
        # Create a book without final metadata
        scan_folder = create_test_scan_folder(name="Test Folder")
        create_test_book_with_file(file_path="/fake/book.epub", scan_folder=scan_folder)

        call_command("complete_metadata")

        # The functions should be called for incomplete books
        # Note: The exact number depends on the Book.objects queryset behavior in tests
        self.assertTrue(mock_query.called or mock_resolve.called)
