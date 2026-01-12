"""Tests for scanner engine functionality.

This module tests the core scanning engine logic, status tracking,
resumption capabilities, and metadata completion functionality.
"""

import json
import os
import tempfile
from unittest.mock import patch

from django.test import TestCase

from books.models import DataSource, FinalMetadata, ScanFolder, ScanStatus
from books.scanner.scanner_engine import EbookScanner
from books.tests.test_helpers import create_test_book_with_file


class EbookScannerTests(TestCase):
    """Test cases for the EbookScanner class."""

    def setUp(self):
        """Set up test data."""
        # Create or get data sources
        self.data_source, _ = DataSource.objects.get_or_create(name=DataSource.INITIAL_SCAN, defaults={"trust_level": 0.2})

    def test_init_default_settings(self):
        """Test scanner initialization with default settings."""
        scanner = EbookScanner()

        self.assertFalse(scanner.rescan)
        self.assertFalse(scanner.resume)
        self.assertEqual(scanner.cover_extensions, {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"})

        # Test that scanner uses centralized extensions from models
        from books.models import AUDIOBOOK_FORMATS, COMIC_FORMATS, EBOOK_FORMATS

        expected_extensions = set()
        for fmt in EBOOK_FORMATS:
            expected_extensions.add(f".{fmt}")
        for fmt in COMIC_FORMATS:
            expected_extensions.add(f".{fmt}")
        for fmt in AUDIOBOOK_FORMATS:
            expected_extensions.add(f".{fmt}")

        self.assertEqual(scanner.ebook_extensions, expected_extensions)

    def test_init_custom_settings(self):
        """Test scanner initialization with custom settings."""
        scanner = EbookScanner(rescan=True, resume=True)

        self.assertTrue(scanner.rescan)
        self.assertTrue(scanner.resume)

    @patch("books.scanner.scanner_engine.scan_directory")
    @patch("os.path.isdir")
    @patch("os.access")
    def test_run_with_valid_folder_path(self, mock_access, mock_isdir, mock_scan_dir):
        """Test running scanner with a valid folder path."""
        mock_isdir.return_value = True
        mock_access.return_value = True
        mock_scan_dir.return_value = None

        scanner = EbookScanner()

        with tempfile.TemporaryDirectory() as temp_dir:
            scanner.run(temp_dir)

        # Check that a ScanStatus was created
        status = ScanStatus.objects.first()
        self.assertIsNotNone(status)
        self.assertEqual(status.status, "Completed")
        self.assertEqual(status.progress, 100)

    @patch("books.scanner.scanner_engine.scan_directory")
    @patch("os.path.isdir")
    @patch("os.access")
    def test_run_with_invalid_folder_path(self, mock_access, mock_isdir, mock_scan_dir):
        """Test running scanner with an invalid folder path."""
        mock_isdir.return_value = False
        mock_access.return_value = False

        scanner = EbookScanner()
        scanner.run("/nonexistent/path")

        # Check that status was set to Failed
        status = ScanStatus.objects.first()
        self.assertIsNotNone(status)
        self.assertEqual(status.status, "Failed")
        self.assertIn("Can't access folder", status.message)

        # scan_directory should not have been called
        mock_scan_dir.assert_not_called()

    @patch("books.scanner.scanner_engine.scan_directory")
    def test_run_with_active_scan_folders(self, mock_scan_dir):
        """Test running scanner with active scan folders."""
        # Create test scan folders
        with tempfile.TemporaryDirectory() as temp_dir1, tempfile.TemporaryDirectory() as temp_dir2:

            ScanFolder.objects.create(path=temp_dir1, is_active=True)
            ScanFolder.objects.create(path=temp_dir2, is_active=True)
            ScanFolder.objects.create(path="/inactive", is_active=False)

            scanner = EbookScanner()
            scanner.run()

            # Check that scan_directory was called for each active folder
            self.assertEqual(mock_scan_dir.call_count, 2)

            # Verify status
            status = ScanStatus.objects.first()
            self.assertEqual(status.status, "Completed")

    @patch("books.scanner.scanner_engine.scan_directory")
    def test_run_with_scan_directory_exception(self, mock_scan_dir):
        """Test handling of exceptions during scan_directory."""
        mock_scan_dir.side_effect = Exception("Test error")

        with tempfile.TemporaryDirectory() as temp_dir:
            ScanFolder.objects.create(path=temp_dir, is_active=True)

            scanner = EbookScanner()
            scanner.run()

            # Check that status was set to Failed
            status = ScanStatus.objects.first()
            self.assertEqual(status.status, "Failed")
            self.assertIn("Test error", status.message)

    def test_run_resume_mode(self):
        """Test that resume mode calls _resume_scan."""
        scanner = EbookScanner(resume=True)

        with patch.object(scanner, "_resume_scan") as mock_resume:
            scanner.run("/test/path")
            mock_resume.assert_called_once_with("/test/path")

    def test_resume_scan_no_interrupted_scan(self):
        """Test resume behavior when no interrupted scan exists."""
        scanner = EbookScanner(resume=True)

        with patch.object(scanner, "run") as mock_run:
            scanner._resume_scan("/test/path")

            # Should call regular run with resume=False
            self.assertFalse(scanner.resume)
            mock_run.assert_called_once_with("/test/path")

    def test_resume_scan_with_interrupted_scan(self):
        """Test resume behavior with an interrupted scan."""
        # Create an interrupted scan status
        folders_to_scan = ["/test/folder1", "/test/folder2"]
        status = ScanStatus.objects.create(status="Running", scan_folders=json.dumps(folders_to_scan), last_processed_file="/test/folder1/book.epub")

        scanner = EbookScanner(resume=True)

        with (
            patch.object(scanner, "_handle_metadata_completion") as mock_metadata,
            patch("books.scanner.scanner_engine.scan_directory") as mock_scan_dir,
            patch("os.path.isdir", return_value=True),
            patch("os.access", return_value=True),
        ):

            scanner._resume_scan()

            # Check that metadata completion was called
            mock_metadata.assert_called_once()

            # Check that scan_directory was called for each folder
            self.assertEqual(mock_scan_dir.call_count, 2)

            # Check status is updated
            status.refresh_from_db()
            self.assertEqual(status.status, "Completed")
            self.assertIsNone(status.last_processed_file)

    def test_resume_scan_invalid_json(self):
        """Test resume behavior with invalid JSON in scan_folders."""
        # Create an interrupted scan with invalid JSON
        status = ScanStatus.objects.create(status="Running", scan_folders="invalid json")

        # Verify the status was created with invalid JSON
        self.assertEqual(status.status, "Running")
        self.assertEqual(status.scan_folders, "invalid json")

        scanner = EbookScanner(resume=True)

        with patch.object(scanner, "run") as mock_run:
            scanner._resume_scan("/test/path")

            # Should fall back to regular run
            self.assertFalse(scanner.resume)
            mock_run.assert_called_once_with("/test/path")

    @patch("books.scanner.folder.query_metadata_and_covers")
    @patch("books.scanner.folder.resolve_final_metadata")
    def test_handle_metadata_completion(self, mock_resolve, mock_query):
        """Test metadata completion for incomplete books."""
        # Create a scan folder and book without FinalMetadata
        with tempfile.TemporaryDirectory() as temp_dir:
            scan_folder = ScanFolder.objects.create(path=temp_dir, is_active=True)
            book = create_test_book_with_file(file_path=os.path.join(temp_dir, "test.epub"), file_format="epub", file_size=1000, scan_folder=scan_folder, content_type="ebook")

            status = ScanStatus.objects.create(status="Running")
            scanner = EbookScanner()

            scanner._handle_metadata_completion(status, [temp_dir])

            # Check that metadata functions were called
            mock_query.assert_called_once_with(book)
            mock_resolve.assert_called_once_with(book)

    def test_handle_metadata_completion_with_final_metadata(self):
        """Test that books with FinalMetadata are excluded from completion."""
        with tempfile.TemporaryDirectory() as temp_dir:
            scan_folder = ScanFolder.objects.create(path=temp_dir, is_active=True)
            book = create_test_book_with_file(file_path=os.path.join(temp_dir, "test.epub"), file_format="epub", file_size=1000, scan_folder=scan_folder, content_type="ebook")
            # Create FinalMetadata for the book
            FinalMetadata.objects.create(book=book)

            status = ScanStatus.objects.create(status="Running")
            scanner = EbookScanner()

            with patch("books.scanner.folder.query_metadata_and_covers") as mock_query:
                scanner._handle_metadata_completion(status, [temp_dir])

                # Should not call metadata functions for complete books
                mock_query.assert_not_called()

    def test_handle_metadata_completion_corrupted_books(self):
        """Test that corrupted books are excluded from completion."""
        with tempfile.TemporaryDirectory() as temp_dir:
            scan_folder = ScanFolder.objects.create(path=temp_dir, is_active=True)
            book = create_test_book_with_file(
                file_path=os.path.join(temp_dir, "test.epub"), file_format="epub", file_size=1000, scan_folder=scan_folder, content_type="ebook", is_corrupted=True
            )

            # Verify the corrupted book was created
            self.assertTrue(book.is_corrupted)

            status = ScanStatus.objects.create(status="Running")
            scanner = EbookScanner()

            with patch("books.scanner.folder.query_metadata_and_covers") as mock_query:
                scanner._handle_metadata_completion(status, [temp_dir])

                # Should not process corrupted books
                mock_query.assert_not_called()

    @patch("books.scanner.folder.query_metadata_and_covers")
    def test_handle_metadata_completion_exception_handling(self, mock_query):
        """Test exception handling during metadata completion."""
        mock_query.side_effect = Exception("Metadata error")

        with tempfile.TemporaryDirectory() as temp_dir:
            scan_folder = ScanFolder.objects.create(path=temp_dir, is_active=True)
            book = create_test_book_with_file(file_path=os.path.join(temp_dir, "test.epub"), file_format="epub", file_size=1000, scan_folder=scan_folder, content_type="ebook")

            status = ScanStatus.objects.create(status="Running")
            scanner = EbookScanner()

            # Should not raise exception, just log the error
            scanner._handle_metadata_completion(status, [temp_dir])

            mock_query.assert_called_once_with(book)

    def test_scan_status_progress_tracking(self):
        """Test that scan status is properly updated during scanning."""
        with tempfile.TemporaryDirectory() as temp_dir1, tempfile.TemporaryDirectory() as temp_dir2:

            ScanFolder.objects.create(path=temp_dir1, is_active=True)
            ScanFolder.objects.create(path=temp_dir2, is_active=True)

            scanner = EbookScanner()

            with patch("books.scanner.scanner_engine.scan_directory") as mock_scan_dir:
                scanner.run()

                # Check that scan_directory was called for each folder
                self.assertEqual(mock_scan_dir.call_count, 2)

                # Check final status
                status = ScanStatus.objects.first()
                self.assertEqual(status.status, "Completed")
                self.assertEqual(status.progress, 100)
                self.assertEqual(status.message, "Scan complete.")

    def test_existing_scan_status_reuse(self):
        """Test that existing completed scan status is reused."""
        # Create an existing completed scan
        existing_status = ScanStatus.objects.create(status="Completed", progress=100, message="Previous scan complete")

        scanner = EbookScanner()

        with patch("books.scanner.scanner_engine.scan_directory"):
            scanner.run()

            # Should create a new status since the old one was completed
            statuses = ScanStatus.objects.all()
            self.assertEqual(len(statuses), 2)

            # Latest status should be the new one
            latest_status = ScanStatus.objects.order_by("-started").first()
            self.assertNotEqual(latest_status.id, existing_status.id)

    def test_existing_running_scan_status_reuse(self):
        """Test that existing running scan status is reused."""
        # Create an existing running scan
        existing_status = ScanStatus.objects.create(status="Running", progress=50, message="Previous scan running")

        scanner = EbookScanner()

        with patch("books.scanner.scanner_engine.scan_directory"):
            scanner.run()

            # Should reuse the existing status
            statuses = ScanStatus.objects.all()
            self.assertEqual(len(statuses), 1)

            existing_status.refresh_from_db()
            self.assertEqual(existing_status.status, "Completed")

    def test_scan_folders_json_storage(self):
        """Test that scan folders are properly stored as JSON."""
        with tempfile.TemporaryDirectory() as temp_dir1, tempfile.TemporaryDirectory() as temp_dir2:

            ScanFolder.objects.create(path=temp_dir1, is_active=True)
            ScanFolder.objects.create(path=temp_dir2, is_active=True)

            scanner = EbookScanner()

            with patch("books.scanner.scanner_engine.scan_directory"):
                scanner.run()

                status = ScanStatus.objects.first()
                self.assertIsNotNone(status.scan_folders)

                # Should be valid JSON
                folders = json.loads(status.scan_folders)
                self.assertEqual(len(folders), 2)
                self.assertIn(os.path.abspath(temp_dir1), folders)
                self.assertIn(os.path.abspath(temp_dir2), folders)
