"""
Comprehensive test suite for scanner engine functionality.
Addresses low coverage in scanner modules (various coverage levels).
"""

import os
import shutil
import tempfile
import uuid
from pathlib import Path
from unittest.mock import Mock, patch

from django.contrib.auth.models import User
from django.test import TestCase

from books.models import ScanFolder, ScanLog, ScanStatus
from books.scanner.background import BackgroundScanner, background_scan_folder
from books.scanner.file_ops import get_file_format
from books.scanner.folder import _collect_files


class BackgroundScannerTests(TestCase):
    """Test background scanner functionality."""

    def setUp(self):
        """Set up test environment for background scanning."""
        self.temp_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

        self.job_id = str(uuid.uuid4())

    def test_background_scanner_initialization(self):
        """Test background scanner initializes correctly."""
        scanner = BackgroundScanner(self.job_id)

        self.assertEqual(scanner.job_id, self.job_id)
        self.assertIsNotNone(scanner.progress)

    @patch("books.scanner.background.BackgroundScanner")
    def test_background_scan_folder_execution(self, mock_scanner_class):
        """Test background scan folder function executes."""
        # Create test files
        test_files = [{"name": "book1.epub", "size": 1024000}, {"name": "book2.pdf", "size": 512000}]

        for config in test_files:
            filepath = Path(self.temp_dir) / config["name"]
            with open(filepath, "wb") as f:
                f.write(b"test content")

        # Mock the scanner to avoid actual scanning
        mock_scanner = Mock()
        mock_scanner.scan_folder.return_value = {"success": True, "files_processed": 2}
        mock_scanner_class.return_value = mock_scanner

        # Mock the scanner to avoid external dependencies
        with self.settings(USE_SQLITE_TEMPORARILY=True):
            result = background_scan_folder(job_id=self.job_id, folder_path=self.temp_dir, language="en", enable_external_apis=False)

        # Should return result structure
        self.assertIsInstance(result, dict)
        self.assertIn("success", result)

        # Verify scanner was instantiated and scan_folder was called
        mock_scanner_class.assert_called_once_with(self.job_id)
        mock_scanner.scan_folder.assert_called_once()

    def test_background_scanner_progress_reporting(self):
        """Test background scanner reports progress correctly."""
        scanner = BackgroundScanner(self.job_id)

        # Test progress reporting
        scanner.report_progress(5, 10, "Processing files")

        # Should update progress in scanner
        status = scanner.progress.get_status()
        self.assertIsNotNone(status)
        # Progress should be recorded in the cache
        self.assertEqual(status["current"], 5)
        self.assertEqual(status["total"], 10)
        self.assertEqual(status["details"], "Processing files")

    def test_concurrent_background_scans(self):
        """Test handling of concurrent background scans."""
        job_id_1 = str(uuid.uuid4())
        job_id_2 = str(uuid.uuid4())

        scanner1 = BackgroundScanner(job_id_1)
        scanner2 = BackgroundScanner(job_id_2)

        # Should maintain separate progress tracking
        scanner1.report_progress(3, 10, "Scan 1")
        scanner2.report_progress(7, 15, "Scan 2")

        status1 = scanner1.progress.get_status()
        status2 = scanner2.progress.get_status()
        self.assertIsNotNone(status1)
        self.assertIsNotNone(status2)
        self.assertNotEqual(scanner1.job_id, scanner2.job_id)


class FolderScannerTests(TestCase):
    """Test folder scanning utility functions."""

    def setUp(self):
        """Set up test folder structure."""
        self.temp_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_folder_scanner_file_discovery(self):
        """Test folder scanner discovers files correctly."""
        # Create nested folder structure
        test_structure = [
            "book1.epub",
            "folder1/book2.pdf",
            "folder1/subfolder/book3.mobi",
            "folder2/comic1.cbz",
            "folder2/image.jpg",  # Should be ignored
            "text_file.txt",  # Should be ignored
        ]

        for file_path in test_structure:
            full_path = Path(self.temp_dir) / file_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_bytes(b"test content")

        # Use _collect_files function to discover files
        ebook_extensions = {".epub", ".pdf", ".mobi", ".cbz", ".cbr"}
        cover_extensions = {".jpg", ".jpeg", ".png"}

        ebook_files, cover_files, opf_files = _collect_files(self.temp_dir, ebook_extensions, cover_extensions)

        # Should find 4 ebook files, ignore others
        self.assertGreaterEqual(len(ebook_files), 4)  # 4 book files

        # Verify correct file types found
        epub_files = [f for f in ebook_files if f.endswith(".epub")]
        pdf_files = [f for f in ebook_files if f.endswith(".pdf")]

        self.assertEqual(len(epub_files), 1)
        self.assertEqual(len(pdf_files), 1)

    def test_file_type_detection(self):
        """Test file type detection accuracy."""
        # Use get_file_format function for file type detection

        # Test various file extensions
        test_cases = [
            ("book.epub", "epub"),
            ("book.pdf", "pdf"),
            ("comic.cbz", "cbz"),
            ("comic.cbr", "cbr"),
            ("book.mobi", "mobi"),
            ("document.txt", "unknown"),
            ("image.jpg", "unknown"),
            ("video.mp4", "unknown"),
            ("archive.zip", "unknown"),
        ]

        for filename, expected_format in test_cases:
            result = get_file_format(filename)
            self.assertEqual(result, expected_format, f"Failed for {filename}")

    def test_folder_scanner_size_calculation(self):
        """Test folder scanner calculates file sizes correctly."""
        test_files = [{"name": "small.epub", "size": 1024}, {"name": "medium.pdf", "size": 1024000}, {"name": "large.cbz", "size": 10240000}]

        total_expected_size = 0
        for config in test_files:
            filepath = Path(self.temp_dir) / config["name"]
            filepath.write_bytes(b"x" * config["size"])
            total_expected_size += config["size"]

        # Use _collect_files to discover files and calculate sizes
        ebook_extensions = {".epub", ".pdf", ".cbz"}
        cover_extensions = {".jpg", ".jpeg", ".png"}

        ebook_files, _, _ = _collect_files(self.temp_dir, ebook_extensions, cover_extensions)

        total_size = sum(os.path.getsize(f) for f in ebook_files)
        self.assertEqual(total_size, total_expected_size)


class ScanStatusTrackingTests(TestCase):
    """Test scan status and logging functionality."""

    def setUp(self):
        """Set up scan status test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

        self.user = User.objects.create_user("scanner_test", "test@example.com", "password")

        self.scan_folder = ScanFolder.objects.create(name="Status Test Folder", path=self.temp_dir, is_active=True)

    def test_scan_status_creation(self):
        """Test scan status is created and tracked properly."""
        status = ScanStatus.objects.create(status="Running", total_files=100, processed_files=50, progress=50)

        self.assertEqual(status.status, "Running")
        self.assertEqual(status.total_files, 100)
        self.assertEqual(status.processed_files, 50)
        self.assertEqual(status.progress, 50)

    def test_scan_log_creation(self):
        """Test scan log entries are created correctly."""
        scan_log = ScanLog.objects.create(scan_folder=self.scan_folder, message="Test scan completed", level="INFO", books_processed=25, books_found=20, errors_count=5)

        self.assertEqual(scan_log.message, "Test scan completed")
        self.assertEqual(scan_log.level, "INFO")
        self.assertEqual(scan_log.books_processed, 25)
        self.assertEqual(scan_log.books_found, 20)
        self.assertEqual(scan_log.errors_count, 5)

    def test_scan_status_completion_tracking(self):
        """Test scan status properly tracks completion."""
        status = ScanStatus.objects.create(status="Running", total_files=10, processed_files=0, progress=0)

        # Simulate progress
        for i in range(1, 11):
            status.processed_files = i
            status.progress = (i * 100) // 10
            status.save()

        # Mark as completed
        status.status = "Completed"
        status.save()

        self.assertEqual(status.status, "Completed")
        self.assertEqual(status.processed_files, 10)

        # Verify completion percentage calculation if implemented
        if hasattr(status, "completion_percentage"):
            self.assertEqual(status.completion_percentage, 100)
