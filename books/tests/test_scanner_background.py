"""
Tests for the background scanner implementation.
"""
from unittest.mock import patch
from django.test import TestCase
from django.core.cache import cache

from books.scanner.background import (
    ScanProgress, BackgroundScanner, background_scan_folder, background_rescan_books, get_scan_progress, get_all_active_scans, cancel_scan
)
from books.models import Book, ScanFolder, DataSource


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

        self.assertEqual(status['job_id'], self.job_id)
        self.assertEqual(status['current'], 10)
        self.assertEqual(status['total'], 100)
        self.assertEqual(status['percentage'], 10)
        self.assertEqual(status['status'], "Processing")
        self.assertIn('eta_seconds', status)

    def test_completion(self):
        """Test marking a scan as complete."""
        self.progress.complete(True, "Scan finished.")
        status = self.progress.get_status()

        self.assertTrue(status['completed'])
        self.assertTrue(status['success'])
        self.assertEqual(status['message'], "Scan finished.")
        self.assertIn('total_time', status)

    def test_error_completion(self):
        """Test marking a scan as complete with an error."""
        self.progress.complete(False, error="Something went wrong.")
        status = self.progress.get_status()

        self.assertTrue(status['completed'])
        self.assertFalse(status['success'])
        self.assertEqual(status['error'], "Something went wrong.")


class BackgroundScannerTests(TestCase):
    """Test cases for the BackgroundScanner class."""

    @classmethod
    def setUpTestData(cls):
        DataSource.objects.get_or_create(name=DataSource.FILENAME, defaults={'trust_level': 0.2})

    def setUp(self):
        self.job_id = "bg_scan_job_456"
        self.scanner = BackgroundScanner(self.job_id)
        self.scan_folder = ScanFolder.objects.create(path="/fake/dir", name="Test Folder")
        cache.clear()

    @patch('books.scanner.background.folder_scanner.scan_directory')
    def test_scan_folder_success(self, mock_scan_directory):
        """Test a successful folder scan."""
        result = self.scanner.scan_folder(self.scan_folder.path)

        self.assertTrue(result['success'])
        mock_scan_directory.assert_called_once()

        # Check final progress status
        status = self.scanner.progress.get_status()
        self.assertTrue(status['completed'])
        self.assertTrue(status['success'])

    @patch('books.scanner.background.folder_scanner.scan_directory')
    def test_scan_folder_failure(self, mock_scan_directory):
        """Test a failed folder scan."""
        mock_scan_directory.side_effect = Exception("Test scan error")
        result = self.scanner.scan_folder(self.scan_folder.path)

        self.assertFalse(result['success'])
        self.assertEqual(result['error'], "Test scan error")

        # Check final progress status
        status = self.scanner.progress.get_status()
        self.assertTrue(status['completed'])
        self.assertFalse(status['success'])
        self.assertEqual(status['error'], "Test scan error")

    @patch('books.scanner.background.folder_scanner._process_book')
    def test_rescan_books_failure(self, mock_process_book):
        """Test a failed book rescan."""
        book1 = Book.objects.create(id=1, file_path="/fake/dir/book1.epub", scan_folder=self.scan_folder)
        mock_process_book.side_effect = Exception("Rescan process error")

        result = self.scanner.rescan_books([book1.id])

        self.assertTrue(result['success'])  # The job itself succeeds, but reports errors
        self.assertIn("1 errors", result['message'])

        status = self.scanner.progress.get_status()
        self.assertTrue(status['completed'])
        self.assertIn("1 errors", status['error'])

    @patch('books.scanner.background.folder_scanner._process_book')
    def test_rescan_books(self, mock_process_book):
        """Test rescanning existing books."""
        book1 = Book.objects.create(id=1, file_path="/fake/dir/book1.epub", scan_folder=self.scan_folder)
        book2 = Book.objects.create(id=2, file_path="/fake/dir/book2.epub", scan_folder=self.scan_folder)

        result = self.scanner.rescan_books([book1.id, book2.id])

        self.assertTrue(result['success'])
        self.assertEqual(mock_process_book.call_count, 2)

        # Check final progress status
        status = self.scanner.progress.get_status()
        self.assertTrue(status['completed'])
        self.assertTrue(status['success'])
        self.assertIn("Rescanned 2 books", status['message'])


class BackgroundJobFunctionTests(TestCase):
    """Test cases for the standalone background job functions."""

    @classmethod
    def setUpTestData(cls):
        DataSource.objects.get_or_create(name=DataSource.FILENAME, defaults={'trust_level': 0.2})

    def setUp(self):
        self.job_id = "job_func_789"
        self.scan_folder = ScanFolder.objects.create(path="/fake/dir/jobs", name="Job Test Folder")
        cache.clear()

    @patch('books.scanner.background.BackgroundScanner.scan_folder')
    def test_background_scan_folder_job(self, mock_scan_folder):
        """Test the background_scan_folder job function."""
        background_scan_folder(self.job_id, self.scan_folder.path)
        mock_scan_folder.assert_called_once()

    @patch('books.scanner.background.BackgroundScanner.rescan_books')
    def test_background_rescan_books_job(self, mock_rescan_books):
        """Test the background_rescan_books job function."""
        book = Book.objects.create(file_path="/fake/dir/jobs/book.epub", scan_folder=self.scan_folder)
        background_rescan_books(self.job_id, [book.id])
        mock_rescan_books.assert_called_once_with([book.id], True)

    def test_get_scan_progress(self):
        """Test retrieving scan progress."""
        ScanProgress(self.job_id).update(25, 100, "Testing", "details")
        progress = get_scan_progress(self.job_id)
        self.assertEqual(progress['percentage'], 25)

    def test_get_all_active_scans(self):
        """Test retrieving all active scans."""
        job1 = "active_job_1"
        job2 = "active_job_2"
        job3_completed = "completed_job_3"

        cache.set('active_scan_job_ids', [job1, job2, job3_completed], timeout=60)
        ScanProgress(job1).update(1, 10, "Running")
        ScanProgress(job2).update(2, 10, "Running")
        ScanProgress(job3_completed).complete(True, "Finished")

        active_scans = get_all_active_scans()
        self.assertEqual(len(active_scans), 2)
        active_job_ids = {scan['job_id'] for scan in active_scans}
        self.assertIn(job1, active_job_ids)
        self.assertIn(job2, active_job_ids)

    def test_cancel_scan(self):
        """Test cancelling a scan job."""
        cache.set('active_scan_job_ids', ['job_to_cancel'], timeout=60)
        self.assertTrue(cancel_scan('job_to_cancel'))
        self.assertEqual(cache.get('active_scan_job_ids'), [])
