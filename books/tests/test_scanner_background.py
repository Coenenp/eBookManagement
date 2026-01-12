"""
Tests for the background scanner implementation.
"""

import os
import shutil
import tempfile
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase

from books.models import DataSource, ScanFolder
from books.scanner.background import BackgroundScanner, ScanProgress, background_rescan_books, background_scan_folder, cancel_scan, get_all_active_scans, get_scan_progress
from books.tests.test_helpers import create_test_book_with_file


class BaseTestCaseWithTempDir(TestCase):
    """Base test case with temporary directory management for ScanFolder tests."""

    def setUp(self):
        """Set up test environment with temporary directories."""
        super().setUp()
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up temporary directories."""
        if hasattr(self, "temp_dir") and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
        super().tearDown()


class ScanProgressTests(TestCase):
    """Test cases for the ScanProgress class."""

    def setUp(self):
        self.job_id = "test_job_123"
        self.progress = ScanProgress(self.job_id)
        cache.clear()

    def test_update_progress(self):
        """Test that progress is updated and stored in cache."""
        self.progress.update(10, 100, "Processing", "file.epub")
        status = self.progress.get_status()

        self.assertEqual(status["job_id"], self.job_id)
        self.assertEqual(status["current"], 10)
        self.assertEqual(status["total"], 100)
        self.assertEqual(status["percentage"], 10)
        self.assertEqual(status["status"], "Processing")
        self.assertIn("eta_seconds", status)

    def test_completion(self):
        """Test marking a scan as complete."""
        self.progress.complete(True, "Scan finished.")
        status = self.progress.get_status()

        self.assertTrue(status["completed"])
        self.assertTrue(status["success"])
        self.assertEqual(status["message"], "Scan finished.")
        self.assertIn("total_time", status)

    def test_error_completion(self):
        """Test marking a scan as complete with an error."""
        self.progress.complete(False, error="Something went wrong.")
        status = self.progress.get_status()

        self.assertTrue(status["completed"])
        self.assertFalse(status["success"])
        self.assertEqual(status["error"], "Something went wrong.")


class BackgroundScannerTests(BaseTestCaseWithTempDir):
    """Test cases for the BackgroundScanner class."""

    @classmethod
    def setUpTestData(cls):
        DataSource.objects.get_or_create(name=DataSource.INITIAL_SCAN, defaults={"trust_level": 0.2})

    def setUp(self):
        super().setUp()
        self.job_id = "bg_scan_job_456"
        self.scanner = BackgroundScanner(self.job_id)
        self.scan_folder = ScanFolder.objects.create(path=self.temp_dir, name="Test Folder")
        cache.clear()

    @patch("books.scanner.background.folder_scanner.scan_directory")
    def test_scan_folder_success(self, mock_scan_directory):
        """Test a successful folder scan."""
        # Mock successful scanning - scan_directory doesn't return anything, just processes
        mock_scan_directory.return_value = None

        result = self.scanner.scan_folder(self.scan_folder.path)

        self.assertTrue(result["success"])
        mock_scan_directory.assert_called_once()

        # Check final progress status
        status = self.scanner.progress.get_status()
        self.assertTrue(status["completed"])
        self.assertTrue(status["success"])

    @patch("books.scanner.background.folder_scanner.scan_directory")
    def test_scan_folder_failure(self, mock_scan_directory):
        """Test a failed folder scan."""
        mock_scan_directory.side_effect = Exception("Test scan error")
        result = self.scanner.scan_folder(self.scan_folder.path)

        # The scanner still returns success=True but with errors
        self.assertTrue(result["success"])
        self.assertGreater(result["errors"], 0)
        self.assertIn("errors", result["message"])

        # Check final progress status
        status = self.scanner.progress.get_status()
        self.assertTrue(status["completed"])
        # Scanner design considers scan_directory errors as successful completion with errors
        self.assertTrue(status["success"])
        # The error details are in the error field
        self.assertEqual(status["error"], "1 errors occurred")

    @patch("books.scanner.background.folder_scanner.extract_internal_metadata")
    @patch("books.scanner.background.folder_scanner.query_external_metadata")
    def test_rescan_books_failure(self, mock_query_external, mock_extract):
        """Test a failed book rescan."""
        book1 = create_test_book_with_file(file_path="/fake/dir/book1.epub", scan_folder=self.scan_folder, content_type="ebook")
        mock_extract.side_effect = Exception("Rescan process error")

        result = self.scanner.rescan_existing_books([book1.id])

        self.assertTrue(result["success"])  # The job itself succeeds, but reports errors
        self.assertIn("1 errors", result["message"])

        status = self.scanner.progress.get_status()
        self.assertTrue(status["completed"])
        self.assertIn("1 errors", status["error"])

    @patch("books.scanner.background.folder_scanner.extract_internal_metadata")
    @patch("books.scanner.background.folder_scanner.query_external_metadata")
    def test_rescan_books(self, mock_query_external, mock_extract):
        """Test rescanning existing books."""
        book1 = create_test_book_with_file(file_path="/fake/dir/book1.epub", scan_folder=self.scan_folder, content_type="ebook")
        book2 = create_test_book_with_file(file_path="/fake/dir/book2.epub", scan_folder=self.scan_folder, content_type="ebook")

        result = self.scanner.rescan_existing_books([book1.id, book2.id])

        self.assertTrue(result["success"])
        self.assertEqual(mock_extract.call_count, 2)
        self.assertEqual(mock_query_external.call_count, 2)

        # Check final progress status
        status = self.scanner.progress.get_status()
        self.assertTrue(status["completed"])
        self.assertTrue(status["success"])
        self.assertIn("Rescanned 2 books", status["message"])


class BackgroundJobFunctionTests(BaseTestCaseWithTempDir):
    """Test cases for the standalone background job functions."""

    @classmethod
    def setUpTestData(cls):
        DataSource.objects.get_or_create(name=DataSource.INITIAL_SCAN, defaults={"trust_level": 0.2})

    def setUp(self):
        super().setUp()
        self.job_id = "job_func_789"
        self.scan_folder = ScanFolder.objects.create(path=self.temp_dir, name="Job Test Folder")
        cache.clear()

    @patch("books.scanner.background.BackgroundScanner.scan_folder")
    def test_background_scan_folder_job(self, mock_scan_folder):
        """Test the background_scan_folder job function."""
        mock_scan_folder.return_value = {"success": True, "message": "Test completed"}
        result = background_scan_folder(self.job_id, self.scan_folder.path)
        mock_scan_folder.assert_called_once()
        self.assertTrue(result["success"])

    @patch("books.scanner.background.BackgroundScanner.rescan_existing_books")
    def test_background_rescan_books_job(self, mock_rescan_books):
        """Test the background_rescan_books job function."""
        book = create_test_book_with_file(file_path="/fake/dir/jobs/book.epub", scan_folder=self.scan_folder, content_type="ebook")
        mock_rescan_books.return_value = {"success": True, "message": "Test completed"}
        result = background_rescan_books(self.job_id, [book.id])
        mock_rescan_books.assert_called_once_with([book.id], True)
        self.assertTrue(result["success"])

    def test_get_scan_progress(self):
        """Test retrieving scan progress."""
        ScanProgress(self.job_id).update(25, 100, "Testing", "details")
        progress = get_scan_progress(self.job_id)
        self.assertEqual(progress["percentage"], 25)

    def test_get_all_active_scans(self):
        """Test retrieving all active scans."""
        job1 = "active_job_1"
        job2 = "active_job_2"
        job3_completed = "completed_job_3"

        cache.set("active_scan_job_ids", [job1, job2, job3_completed], timeout=60)
        ScanProgress(job1).update(1, 10, "Running")
        ScanProgress(job2).update(2, 10, "Running")
        ScanProgress(job3_completed).complete(True, "Finished")

        active_scans = get_all_active_scans()
        self.assertEqual(len(active_scans), 2)
        active_job_ids = {scan["job_id"] for scan in active_scans}
        self.assertIn(job1, active_job_ids)
        self.assertIn(job2, active_job_ids)

    def test_cancel_scan(self):
        """Test cancelling a scan job."""
        # Set up a progress entry for the job
        progress = ScanProgress("job_to_cancel")
        progress.update(50, 100, "Running", "Test job")

        # Verify progress exists before cancellation
        initial_status = progress.get_status()
        self.assertIsNotNone(initial_status)

        # Cancel the scan
        self.assertTrue(cancel_scan("job_to_cancel"))

        # Verify progress has been cleared
        cleared_status = get_scan_progress("job_to_cancel")
        self.assertEqual(cleared_status, {})
