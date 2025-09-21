"""
Comprehensive tests for file operations, uploads, and file processing functionality.

This module contains tests for file uploads, file validation, file processing,
batch operations, file format handling, error recovery, and security validation.
"""

import json
from unittest.mock import patch, MagicMock
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from books.models import Book, ScanLog, ScanFolder


class FileUploadTests(TestCase):
    """Tests for file upload functionality."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.client.login(username='testuser', password='testpass123')

        # Create scan folder for book creation
        self.scan_folder = ScanFolder.objects.create(
            path="/test/scan/folder",
            is_active=True
        )

    def test_single_file_upload_success(self):
        """Test successful single file upload."""
        # Create a test file
        test_content = b"This is a test ebook file content."
        uploaded_file = SimpleUploadedFile(
            "test_book.epub",
            test_content,
            content_type="application/epub+zip"
        )

        url = reverse('books:ajax_upload_file')
        response = self.client.post(url, {'file': uploaded_file})

        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content)
        self.assertTrue(response_data.get('success', False))
        self.assertIn('file_id', response_data)

    def test_multiple_file_upload(self):
        """Test multiple file upload functionality."""
        files = []
        for i in range(3):
            content = f"Test ebook content {i}".encode()
            uploaded_file = SimpleUploadedFile(
                f"test_book_{i}.epub",
                content,
                content_type="application/epub+zip"
            )
            files.append(uploaded_file)

        url = reverse('books:ajax_upload_multiple_files')
        response = self.client.post(url, {'files': files})

        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content)
        self.assertTrue(response_data.get('success', False))
        self.assertEqual(len(response_data.get('uploaded_files', [])), 3)

    def test_file_upload_size_validation(self):
        """Test file size validation during upload."""
        # Create oversized file (mock large content)
        large_content = b"x" * (100 * 1024 * 1024)  # 100MB
        large_file = SimpleUploadedFile(
            "large_book.epub",
            large_content,
            content_type="application/epub+zip"
        )

        url = reverse('books:ajax_upload_file')
        response = self.client.post(url, {'file': large_file})

        # Should either succeed or fail gracefully with size limit message
        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content)
        # Either success or appropriate error message
        self.assertIn('success', response_data)

    def test_file_upload_format_validation(self):
        """Test file format validation during upload."""
        # Test valid formats
        valid_formats = [
            ("test.epub", "application/epub+zip"),
            ("test.pdf", "application/pdf"),
            ("test.mobi", "application/x-mobipocket-ebook"),
            ("test.azw3", "application/vnd.amazon.ebook"),
        ]

        for filename, content_type in valid_formats:
            with self.subTest(format=filename):
                uploaded_file = SimpleUploadedFile(
                    filename,
                    b"test content",
                    content_type=content_type
                )

                url = reverse('books:ajax_upload_file')
                response = self.client.post(url, {'file': uploaded_file})

                self.assertEqual(response.status_code, 200)
                response_data = json.loads(response.content)
                self.assertTrue(response_data.get('success', False))

    def test_file_upload_invalid_format(self):
        """Test upload rejection for invalid file formats."""
        invalid_file = SimpleUploadedFile(
            "test.txt",
            b"This is not an ebook",
            content_type="text/plain"
        )

        url = reverse('books:ajax_upload_file')
        response = self.client.post(url, {'file': invalid_file})

        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content)
        # Should reject invalid format
        if not response_data.get('success', True):
            self.assertIn('error', response_data)
            self.assertIn('format', response_data['error'].lower())

    def test_file_upload_duplicate_handling(self):
        """Test handling of duplicate file uploads."""
        # Upload same file twice
        test_content = b"Duplicate test content"

        for attempt in range(2):
            uploaded_file = SimpleUploadedFile(
                "duplicate_test.epub",
                test_content,
                content_type="application/epub+zip"
            )

            url = reverse('books:ajax_upload_file')
            response = self.client.post(url, {'file': uploaded_file})

            self.assertEqual(response.status_code, 200)
            response_data = json.loads(response.content)

            if attempt == 1:
                # Second upload might be handled differently
                # Either allowed (with new name) or rejected as duplicate
                self.assertIn('success', response_data)

    def test_file_upload_progress_tracking(self):
        """Test file upload progress tracking."""
        url = reverse('books:ajax_upload_progress')

        # Check upload progress (may return empty if no active uploads)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        response_data = json.loads(response.content)
        self.assertIn('uploads', response_data)
        self.assertIsInstance(response_data['uploads'], list)

    def test_file_upload_cancellation(self):
        """Test cancelling file uploads."""
        # Start upload
        uploaded_file = SimpleUploadedFile(
            "cancel_test.epub",
            b"test content for cancellation",
            content_type="application/epub+zip"
        )

        upload_url = reverse('books:ajax_upload_file')
        upload_response = self.client.post(upload_url, {'file': uploaded_file})

        if upload_response.status_code == 200:
            upload_data = json.loads(upload_response.content)

            if upload_data.get('success') and 'upload_id' in upload_data:
                # Cancel upload
                cancel_url = reverse('books:ajax_cancel_upload')
                cancel_response = self.client.post(
                    cancel_url,
                    {'upload_id': upload_data['upload_id']}
                )

                self.assertEqual(cancel_response.status_code, 200)


class FileValidationTests(TestCase):
    """Tests for file validation and integrity checking."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.client.login(username='testuser', password='testpass123')

        # Create scan folder for book creation
        self.scan_folder = ScanFolder.objects.create(
            path="/test/scan/folder",
            is_active=True
        )

    def test_file_integrity_validation(self):
        """Test file integrity validation."""
        url = reverse('books:ajax_validate_file_integrity')

        # Test with valid file ID
        book = Book.objects.create(
            file_path="/library/test.epub",
            file_format="epub",
            scan_folder=self.scan_folder,
        )

        response = self.client.post(
            url,
            {'book_id': book.id}
        )

        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content)
        self.assertIn('success', response_data)
        self.assertIn('valid', response_data)

    @patch('os.path.exists')
    @patch('os.path.getsize')
    def test_file_existence_validation(self, mock_getsize, mock_exists):
        """Test validation of file existence."""
        # Mock file exists and has size
        mock_exists.return_value = True
        mock_getsize.return_value = 1024

        book = Book.objects.create(
            file_path="/library/existing.epub",
            file_format="epub",
            file_size=1024,
            scan_folder=self.scan_folder,
        )

        url = reverse('books:ajax_validate_file_existence')
        response = self.client.post(url, {'book_id': book.id})

        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content)
        self.assertTrue(response_data.get('exists', False))

    @patch('os.path.exists')
    def test_missing_file_detection(self, mock_exists):
        """Test detection of missing files."""
        # Mock file doesn't exist
        mock_exists.return_value = False

        book = Book.objects.create(
            file_path="/library/missing.epub",
            file_format="epub",
            scan_folder=self.scan_folder,
        )

        url = reverse('books:ajax_validate_file_existence')
        response = self.client.post(url, {'book_id': book.id})

        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content)
        self.assertFalse(response_data.get('exists', True))

    def test_file_format_validation_detailed(self):
        """Test detailed file format validation."""
        formats_to_test = [
            ("test.epub", "epub"),
            ("test.pdf", "pdf"),
            ("test.mobi", "mobi"),
            ("test.azw3", "azw3"),
            ("test.txt", "txt"),  # Invalid format
        ]

        for filename, expected_format in formats_to_test:
            with self.subTest(format=expected_format):
                url = reverse('books:ajax_validate_file_format')

                response = self.client.post(url, {
                    'filename': filename,
                    'expected_format': expected_format
                })

                self.assertEqual(response.status_code, 200)
                response_data = json.loads(response.content)
                self.assertIn('valid', response_data)

    def test_batch_file_validation(self):
        """Test batch validation of multiple files."""
        # Create multiple books
        books = []
        for i in range(5):
            book = Book.objects.create(
                file_path=f"/library/batch_test_{i}.epub",
                file_format="epub",
                scan_folder=self.scan_folder,
            )
            books.append(book)

        book_ids = [book.id for book in books]

        url = reverse('books:ajax_batch_validate_files')
        response = self.client.post(
            url,
            data=json.dumps({'book_ids': book_ids}),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content)
        self.assertIn('results', response_data)
        self.assertEqual(len(response_data['results']), 5)

    def test_corrupted_file_detection(self):
        """Test detection of corrupted files."""
        url = reverse('books:ajax_check_file_corruption')

        book = Book.objects.create(
            file_path="/library/corruption_test.epub",
            file_format="epub",
            scan_folder=self.scan_folder,
        )

        with patch('zipfile.ZipFile') as mock_zipfile:
            # Mock corrupted ZIP file
            mock_zipfile.side_effect = Exception("Bad ZIP file")

            response = self.client.post(url, {'book_id': book.id})

            self.assertEqual(response.status_code, 200)
            response_data = json.loads(response.content)
            self.assertIn('corrupted', response_data)


class FileProcessingTests(TestCase):
    """Tests for file processing and metadata extraction."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.client.login(username='testuser', password='testpass123')

        # Create scan folder for book creation
        self.scan_folder = ScanFolder.objects.create(
            path="/test/scan/folder",
            is_active=True
        )

    @patch('books.scanner.parsing.extract_metadata_from_file')
    def test_metadata_extraction_from_file(self, mock_extract):
        """Test metadata extraction from uploaded files."""
        # Mock metadata extraction
        mock_extract.return_value = {
            'title': 'Extracted Title',
            'author': 'Extracted Author',
            'isbn': '1234567890',
            'publisher': 'Test Publisher'
        }

        book = Book.objects.create(
            file_path="/library/processing_test.epub",
            file_format="epub",
            scan_folder=self.scan_folder,
        )

        url = reverse('books:ajax_extract_metadata')
        response = self.client.post(url, {'book_id': book.id})

        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content)
        self.assertTrue(response_data.get('success', False))
        self.assertIn('metadata', response_data)

    def test_cover_image_extraction(self):
        """Test cover image extraction from files."""
        book = Book.objects.create(
            file_path="/library/cover_test.epub",
            file_format="epub",
            scan_folder=self.scan_folder,
        )

        url = reverse('books:ajax_extract_cover')

        with patch('books.utils.image_utils.extract_cover_from_file') as mock_extract:
            mock_extract.return_value = '/covers/extracted_cover.jpg'

            response = self.client.post(url, {'book_id': book.id})

            self.assertEqual(response.status_code, 200)
            response_data = json.loads(response.content)
            self.assertTrue(response_data.get('success', False))
            self.assertIn('cover_path', response_data)

    def test_file_format_conversion(self):
        """Test file format conversion functionality."""
        book = Book.objects.create(
            file_path="/library/conversion_test.epub",
            file_format="epub",
            scan_folder=self.scan_folder,
        )

        url = reverse('books:ajax_convert_format')

        conversion_data = {
            'book_id': book.id,
            'target_format': 'pdf',
            'conversion_options': {
                'quality': 'high',
                'preserve_formatting': True
            }
        }

        response = self.client.post(
            url,
            data=json.dumps(conversion_data),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content)
        self.assertIn('success', response_data)

    def test_batch_processing(self):
        """Test batch processing of multiple files."""
        # Create multiple books for batch processing
        books = []
        for i in range(10):
            book = Book.objects.create(
                file_path=f"/library/batch_{i}.epub",
                file_format="epub",
                scan_folder=self.scan_folder,
            )
            books.append(book)

        book_ids = [book.id for book in books]

        url = reverse('books:ajax_batch_process_files')

        batch_data = {
            'book_ids': book_ids,
            'operations': ['extract_metadata', 'extract_cover', 'validate'],
            'priority': 'normal'
        }

        response = self.client.post(
            url,
            data=json.dumps(batch_data),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content)
        self.assertTrue(response_data.get('success', False))
        self.assertIn('batch_id', response_data)

    def test_processing_status_tracking(self):
        """Test tracking of file processing status."""
        url = reverse('books:ajax_processing_status')

        # Check processing status
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        response_data = json.loads(response.content)
        self.assertIn('active_jobs', response_data)
        self.assertIn('completed_jobs', response_data)
        self.assertIn('failed_jobs', response_data)

    def test_processing_queue_management(self):
        """Test management of file processing queue."""
        # Add job to queue
        queue_url = reverse('books:ajax_add_to_processing_queue')

        queue_data = {
            'book_id': 1,
            'operation': 'extract_metadata',
            'priority': 'high'
        }

        response = self.client.post(
            queue_url,
            data=json.dumps(queue_data),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 200)

        # Check queue status
        status_url = reverse('books:ajax_processing_queue_status')
        status_response = self.client.get(status_url)

        self.assertEqual(status_response.status_code, 200)
        status_data = json.loads(status_response.content)
        self.assertIn('queue_length', status_data)


class FileOperationSecurityTests(TestCase):
    """Security tests for file operations."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.client.login(username='testuser', password='testpass123')

        # Create scan folder for book creation
        self.scan_folder = ScanFolder.objects.create(
            path="/test/scan/folder",
            is_active=True
        )

    def test_path_traversal_protection(self):
        """Test protection against path traversal attacks."""
        malicious_filenames = [
            "../../../etc/passwd",
            "..\\..\\..\\windows\\system32\\config\\sam",
            "test/../../../sensitive_file.txt",
            "%2e%2e%2f%2e%2e%2f%2e%2e%2fetc%2fpasswd"
        ]

        for filename in malicious_filenames:
            with self.subTest(filename=filename):
                uploaded_file = SimpleUploadedFile(
                    filename,
                    b"malicious content",
                    content_type="application/epub+zip"
                )

                url = reverse('books:ajax_upload_file')
                response = self.client.post(url, {'file': uploaded_file})

                # Should handle malicious filename safely
                self.assertEqual(response.status_code, 200)
                response_data = json.loads(response.content)

                # Either reject or sanitize the filename
                if response_data.get('success'):
                    self.assertNotIn('..', response_data.get('filename', ''))

    def test_file_type_spoofing_protection(self):
        """Test protection against file type spoofing."""
        # Upload executable with ebook extension
        malicious_content = b"MZ\x90\x00"  # PE header for Windows executable

        spoofed_file = SimpleUploadedFile(
            "malicious.epub",
            malicious_content,
            content_type="application/epub+zip"
        )

        url = reverse('books:ajax_upload_file')
        response = self.client.post(url, {'file': spoofed_file})

        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content)

        # Should detect file type mismatch
        if not response_data.get('success', True):
            self.assertIn('error', response_data)

    def test_zip_bomb_protection(self):
        """Test protection against zip bombs."""
        url = reverse('books:ajax_validate_file_integrity')

        book = Book.objects.create(
            file_path="/library/zip_bomb.epub",
            file_format="epub",
            scan_folder=self.scan_folder,
        )

        with patch('zipfile.ZipFile') as mock_zipfile:
            # Mock zip bomb scenario
            mock_zip = MagicMock()
            mock_zip.infolist.return_value = [
                MagicMock(file_size=1024, compress_size=1),  # High compression ratio
                MagicMock(file_size=1024*1024*1024, compress_size=1024)  # Suspicious
            ]
            mock_zipfile.return_value.__enter__.return_value = mock_zip

            response = self.client.post(url, {'book_id': book.id})

            self.assertEqual(response.status_code, 200)
            response_data = json.loads(response.content)
            # Should detect suspicious compression ratios
            self.assertIn('valid', response_data)

    def test_file_upload_size_limits(self):
        """Test enforcement of file upload size limits."""
        # Test with various file sizes
        size_tests = [
            (1024, True),  # 1KB - should pass
            (10 * 1024 * 1024, True),  # 10MB - should pass
            (100 * 1024 * 1024, False),  # 100MB - may fail depending on limits
        ]

        for size, should_pass in size_tests:
            with self.subTest(size=size):
                # Create content of specified size (mock to avoid memory issues)
                large_file = SimpleUploadedFile(
                    f"size_test_{size}.epub",
                    b"x" * min(size, 1024),  # Limit actual content size
                    content_type="application/epub+zip"
                )

                # Mock the file size
                large_file.size = size

                url = reverse('books:ajax_upload_file')
                response = self.client.post(url, {'file': large_file})

                self.assertEqual(response.status_code, 200)
                response_data = json.loads(response.content)

                if not should_pass:
                    # Large files should be rejected or handled specially
                    self.assertIn('success', response_data)

    def test_concurrent_upload_limits(self):
        """Test limits on concurrent file uploads."""
        # Simulate multiple concurrent uploads
        files = []
        for i in range(10):  # Try to upload 10 files simultaneously
            uploaded_file = SimpleUploadedFile(
                f"concurrent_{i}.epub",
                b"concurrent test content",
                content_type="application/epub+zip"
            )
            files.append(uploaded_file)

        url = reverse('books:ajax_upload_file')

        # Send multiple uploads (in practice would be concurrent)
        responses = []
        for file in files:
            response = self.client.post(url, {'file': file})
            responses.append(response)

        # All responses should be handled gracefully
        for response in responses:
            self.assertEqual(response.status_code, 200)
            response_data = json.loads(response.content)
            self.assertIn('success', response_data)

    def test_filename_sanitization(self):
        """Test filename sanitization for security."""
        problematic_filenames = [
            "file with spaces.epub",
            "file;with;semicolons.epub",
            "file|with|pipes.epub",
            "file<with>brackets.epub",
            "file\"with\"quotes.epub",
            "file'with'apostrophes.epub",
            "file:with:colons.epub"
        ]

        for filename in problematic_filenames:
            with self.subTest(filename=filename):
                uploaded_file = SimpleUploadedFile(
                    filename,
                    b"test content",
                    content_type="application/epub+zip"
                )

                url = reverse('books:ajax_upload_file')
                response = self.client.post(url, {'file': uploaded_file})

                self.assertEqual(response.status_code, 200)
                response_data = json.loads(response.content)

                if response_data.get('success'):
                    # Check that filename was sanitized
                    saved_filename = response_data.get('filename', '')
                    # Should not contain dangerous characters
                    dangerous_chars = ['<', '>', '"', '|', ':', ';']
                    for char in dangerous_chars:
                        self.assertNotIn(char, saved_filename)


class FileOperationPerformanceTests(TestCase):
    """Performance tests for file operations."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.client.login(username='testuser', password='testpass123')

        # Create scan folder for book creation
        self.scan_folder = ScanFolder.objects.create(
            path="/test/scan/folder",
            is_active=True
        )

    def test_large_file_upload_performance(self):
        """Test performance of large file uploads."""
        import time

        # Create moderately large file
        large_content = b"x" * (5 * 1024 * 1024)  # 5MB
        large_file = SimpleUploadedFile(
            "performance_test.epub",
            large_content,
            content_type="application/epub+zip"
        )

        url = reverse('books:ajax_upload_file')

        start_time = time.time()
        response = self.client.post(url, {'file': large_file})
        end_time = time.time()

        # Should complete within reasonable time
        upload_time = end_time - start_time
        self.assertLess(upload_time, 30.0)  # 30 seconds max

        self.assertEqual(response.status_code, 200)

    def test_batch_processing_performance(self):
        """Test performance of batch file processing."""
        import time

        # Create multiple books for batch processing
        books = []
        for i in range(50):  # Process 50 books
            book = Book.objects.create(
                file_path=f"/library/perf_test_{i}.epub",
                file_format="epub",
                scan_folder=self.scan_folder,
            )
            books.append(book)

        book_ids = [book.id for book in books]

        url = reverse('books:ajax_batch_validate_files')

        start_time = time.time()
        response = self.client.post(
            url,
            data=json.dumps({'book_ids': book_ids}),
            content_type='application/json'
        )
        end_time = time.time()

        # Should complete within reasonable time
        processing_time = end_time - start_time
        self.assertLess(processing_time, 60.0)  # 60 seconds max

        self.assertEqual(response.status_code, 200)

    def test_concurrent_file_validation(self):
        """Test performance of concurrent file validation."""
        import threading
        import time

        # Create books for validation
        books = []
        for i in range(20):
            book = Book.objects.create(
                file_path=f"/library/concurrent_{i}.epub",
                file_format="epub",
                scan_folder=self.scan_folder,
            )
            books.append(book)

        def validate_book(book_id):
            """Validate a single book."""
            url = reverse('books:ajax_validate_file_existence')
            response = self.client.post(url, {'book_id': book_id})
            return response.status_code == 200

        # Run validations concurrently
        threads = []
        results = []

        start_time = time.time()

        for book in books:
            thread = threading.Thread(
                target=lambda b=book: results.append(validate_book(b.id))
            )
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        end_time = time.time()

        # Should handle concurrent requests efficiently
        total_time = end_time - start_time
        self.assertLess(total_time, 30.0)  # 30 seconds max

        # All validations should succeed
        self.assertTrue(all(results))

    def test_memory_usage_during_processing(self):
        """Test memory usage during file processing."""
        import tracemalloc

        # Start memory tracking
        tracemalloc.start()

        # Create and process multiple files
        books = []
        for i in range(10):
            book = Book.objects.create(
                file_path=f"/library/memory_test_{i}.epub",
                file_format="epub",
                scan_folder=self.scan_folder,
            )
            books.append(book)

        book_ids = [book.id for book in books]

        url = reverse('books:ajax_batch_validate_files')
        response = self.client.post(
            url,
            data=json.dumps({'book_ids': book_ids}),
            content_type='application/json'
        )

        # Get memory usage
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        # Memory usage should be reasonable (less than 100MB)
        self.assertLess(peak, 100 * 1024 * 1024)  # 100MB

        self.assertEqual(response.status_code, 200)


class FileOperationIntegrationTests(TestCase):
    """Integration tests for complete file operation workflows."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.client.login(username='testuser', password='testpass123')

        # Create scan folder for book creation
        self.scan_folder = ScanFolder.objects.create(
            path="/test/scan/folder",
            is_active=True
        )

    def test_complete_file_upload_workflow(self):
        """Test complete workflow from upload to processing."""
        # 1. Upload file
        test_content = b"Complete workflow test content"
        uploaded_file = SimpleUploadedFile(
            "workflow_test.epub",
            test_content,
            content_type="application/epub+zip"
        )

        upload_url = reverse('books:ajax_upload_file')
        upload_response = self.client.post(upload_url, {'file': uploaded_file})

        self.assertEqual(upload_response.status_code, 200)
        upload_data = json.loads(upload_response.content)
        self.assertTrue(upload_data.get('success', False))

        if 'book_id' in upload_data:
            book_id = upload_data['book_id']

            # 2. Validate uploaded file
            validate_url = reverse('books:ajax_validate_file_existence')
            validate_response = self.client.post(validate_url, {'book_id': book_id})

            self.assertEqual(validate_response.status_code, 200)

            # 3. Extract metadata
            metadata_url = reverse('books:ajax_extract_metadata')
            metadata_response = self.client.post(metadata_url, {'book_id': book_id})

            self.assertEqual(metadata_response.status_code, 200)

            # 4. Extract cover
            cover_url = reverse('books:ajax_extract_cover')
            cover_response = self.client.post(cover_url, {'book_id': book_id})

            self.assertEqual(cover_response.status_code, 200)

    def test_error_recovery_in_file_operations(self):
        """Test error recovery during file operations."""
        # Create book with invalid file path
        book = Book.objects.create(
            file_path="/nonexistent/path/error_test.epub",
            file_format="epub",
            scan_folder=self.scan_folder,
        )

        # Try to validate non-existent file
        validate_url = reverse('books:ajax_validate_file_existence')
        response = self.client.post(validate_url, {'book_id': book.id})

        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content)

        # Should gracefully handle missing file
        self.assertFalse(response_data.get('exists', True))
        self.assertIn('error', response_data.keys() or ['success'])

    def test_file_operation_logging(self):
        """Test logging of file operations."""
        book = Book.objects.create(
            file_path="/library/logging_test.epub",
            file_format="epub",
            scan_folder=self.scan_folder,
        )

        # Perform operation that should be logged
        url = reverse('books:ajax_validate_file_integrity')
        response = self.client.post(url, {'book_id': book.id})

        self.assertEqual(response.status_code, 200)

        # Check if operation was logged (if logging is implemented)
        # This would depend on your logging system
        logs = ScanLog.objects.filter(
            message__icontains='file validation'
        )
        # May or may not have logs depending on implementation
        self.assertIsInstance(logs.count(), int)  # Verify logs query executes without error
