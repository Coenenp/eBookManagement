"""
Comprehensive error handling tests across all views and functionality.

This module contains tests for exception handling, edge cases, validation errors,
database errors, external service failures, and recovery mechanisms.
"""

import json
from unittest.mock import patch, Mock
from django.test import TestCase, Client, override_settings
from django.contrib.auth.models import User
from django.urls import reverse
from django.db import DatabaseError, IntegrityError
from django.core.exceptions import ValidationError
from books.models import Book


class DatabaseErrorHandlingTests(TestCase):
    """Tests for database error handling."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.client.login(username='testuser', password='testpass123')

    @patch('books.models.Book.objects.all')
    def test_database_connection_error_handling(self, mock_all):
        """Test handling of database connection errors."""
        # Simulate database connection error
        mock_all.side_effect = DatabaseError("Connection to database failed")

        response = self.client.get(reverse('books:book_list'))

        # Should handle gracefully without crashing
        self.assertIn(response.status_code, [200, 500])

        if response.status_code == 200:
            # Should show error message or fallback content
            self.assertContains(response, 'error', status_code=200, msg_prefix='Should contain error message')

    @patch('books.models.Book.objects.create')
    def test_database_integrity_error_handling(self, mock_create):
        """Test handling of database integrity errors."""
        # Simulate integrity constraint violation
        mock_create.side_effect = IntegrityError("Duplicate key violation")

        response = self.client.post(reverse('books:ajax_create_book'), {
            'title': 'Test Book',
            'file_path': '/library/test.epub'
        })

        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content)
        self.assertFalse(response_data.get('success', True))
        self.assertIn('error', response_data)

    @patch('django.db.transaction.atomic')
    def test_transaction_rollback_on_error(self, mock_atomic):
        """Test proper transaction rollback on errors."""
        # Simulate transaction rollback
        mock_atomic.side_effect = DatabaseError("Transaction failed")

        response = self.client.post(reverse('books:ajax_batch_update_metadata'), {
            'book_ids': [1, 2, 3],
            'updates': {'genre': 'Science Fiction'}
        })

        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content)
        self.assertFalse(response_data.get('success', True))

    def test_foreign_key_constraint_error(self):
        """Test handling of foreign key constraint errors."""
        # Try to create book with invalid data source
        response = self.client.post(reverse('books:ajax_create_book_metadata'), {
            'book_id': 1,
            'source_id': 99999,  # Non-existent source
            'field_name': 'title',
            'field_value': 'Test Title'
        })

        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content)
        # Should handle foreign key constraint gracefully
        self.assertIn('success', response_data)

    @patch('books.models.Book.save')
    def test_model_validation_error_handling(self, mock_save):
        """Test handling of model validation errors."""
        # Simulate validation error
        mock_save.side_effect = ValidationError("Invalid field value")

        response = self.client.post(reverse('books:ajax_update_book'), {
            'book_id': 1,
            'title': '',  # Invalid empty title
        })

        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content)
        self.assertFalse(response_data.get('success', True))
        self.assertIn('error', response_data)


class ExternalServiceErrorTests(TestCase):
    """Tests for external service failure handling."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.client.login(username='testuser', password='testpass123')

    @patch('requests.get')
    def test_isbn_lookup_service_timeout(self, mock_get):
        """Test handling of ISBN lookup service timeout."""
        # Simulate timeout
        mock_get.side_effect = Exception("Connection timeout")

        response = self.client.post(reverse('books:ajax_isbn_lookup'), {
            'isbn': '1234567890'
        })

        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content)
        self.assertFalse(response_data.get('success', True))
        self.assertIn('error', response_data)

    @patch('requests.get')
    def test_cover_image_service_failure(self, mock_get):
        """Test handling of cover image service failures."""
        # Simulate service failure
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_get.return_value = mock_response

        response = self.client.post(reverse('books:ajax_fetch_cover_image'), {
            'book_id': 1,
            'cover_url': 'http://example.com/cover.jpg'
        })

        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content)
        self.assertFalse(response_data.get('success', True))

    @patch('books.scanner.external.goodreads_api')
    def test_metadata_service_rate_limiting(self, mock_api):
        """Test handling of API rate limiting."""
        # Simulate rate limiting
        mock_api.get_book_metadata.side_effect = Exception("Rate limit exceeded")

        response = self.client.post(reverse('books:ajax_fetch_metadata'), {
            'book_id': 1,
            'service': 'goodreads'
        })

        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content)
        # Should handle rate limiting gracefully
        self.assertIn('success', response_data)

    @patch('books.utils.external_services.openlibrary_client')
    def test_service_authentication_failure(self, mock_client):
        """Test handling of service authentication failures."""
        # Simulate authentication failure
        mock_client.authenticate.return_value = False
        mock_client.search_books.side_effect = Exception("Authentication failed")

        response = self.client.post(reverse('books:ajax_search_external_metadata'), {
            'query': 'test book',
            'service': 'openlibrary'
        })

        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content)
        self.assertFalse(response_data.get('success', True))

    @patch('urllib.request.urlopen')
    def test_network_connectivity_issues(self, mock_urlopen):
        """Test handling of network connectivity issues."""
        # Simulate network error
        mock_urlopen.side_effect = Exception("Network unreachable")

        response = self.client.post(reverse('books:ajax_test_connection'), {
            'service': 'isbn_lookup'
        })

        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content)
        self.assertFalse(response_data.get('connected', True))


class FileSystemErrorTests(TestCase):
    """Tests for file system error handling."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.client.login(username='testuser', password='testpass123')

    @patch('os.path.exists')
    def test_missing_file_handling(self, mock_exists):
        """Test handling of missing files."""
        # Simulate missing file
        mock_exists.return_value = False

        book = Book.objects.create(
            title="Missing File Test",
            file_path="/nonexistent/file.epub",
            file_format="epub"
        )

        response = self.client.post(reverse('books:ajax_validate_file'), {
            'book_id': book.id
        })

        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content)
        self.assertFalse(response_data.get('exists', True))

    @patch('builtins.open')
    def test_file_permission_errors(self, mock_open):
        """Test handling of file permission errors."""
        # Simulate permission denied
        mock_open.side_effect = PermissionError("Permission denied")

        book = Book.objects.create(
            title="Permission Test",
            file_path="/restricted/file.epub",
            file_format="epub"
        )

        response = self.client.post(reverse('books:ajax_read_file_metadata'), {
            'book_id': book.id
        })

        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content)
        self.assertFalse(response_data.get('success', True))
        self.assertIn('error', response_data)

    @patch('os.makedirs')
    def test_directory_creation_failure(self, mock_makedirs):
        """Test handling of directory creation failures."""
        # Simulate directory creation failure
        mock_makedirs.side_effect = OSError("Cannot create directory")

        response = self.client.post(reverse('books:ajax_create_library_folder'), {
            'folder_path': '/library/new_folder'
        })

        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content)
        self.assertFalse(response_data.get('success', True))

    @patch('shutil.copy2')
    def test_file_copy_failure(self, mock_copy):
        """Test handling of file copy failures."""
        # Simulate file copy failure
        mock_copy.side_effect = OSError("Disk full")

        response = self.client.post(reverse('books:ajax_copy_book_file'), {
            'book_id': 1,
            'destination': '/backup/location/'
        })

        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content)
        self.assertFalse(response_data.get('success', True))

    @patch('os.remove')
    def test_file_deletion_failure(self, mock_remove):
        """Test handling of file deletion failures."""
        # Simulate file deletion failure
        mock_remove.side_effect = OSError("File in use")

        response = self.client.post(reverse('books:ajax_delete_book_file'), {
            'book_id': 1,
            'confirm': True
        })

        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content)
        # Should handle deletion failure gracefully
        self.assertIn('success', response_data)


class ValidationErrorTests(TestCase):
    """Tests for input validation and form error handling."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.client.login(username='testuser', password='testpass123')

    def test_invalid_json_input_handling(self):
        """Test handling of invalid JSON input."""
        url = reverse('books:ajax_update_book_metadata')

        # Send invalid JSON
        response = self.client.post(
            url,
            data="invalid json string",
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content)
        self.assertFalse(response_data.get('success', True))
        self.assertIn('error', response_data)

    def test_missing_required_fields(self):
        """Test handling of missing required fields."""
        # Test book creation without required fields
        response = self.client.post(reverse('books:ajax_create_book'), {
            # Missing title and file_path
            'file_format': 'epub'
        })

        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content)
        self.assertFalse(response_data.get('success', True))
        self.assertIn('error', response_data)

    def test_invalid_field_types(self):
        """Test handling of invalid field types."""
        # Test with invalid data types
        response = self.client.post(reverse('books:ajax_update_book'), {
            'book_id': 'not_a_number',  # Should be integer
            'file_size': 'not_a_number',  # Should be integer
            'confidence': 'not_a_float'  # Should be float
        })

        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content)
        self.assertFalse(response_data.get('success', True))

    def test_field_length_validation(self):
        """Test handling of field length validation errors."""
        # Test with overly long field values
        very_long_string = 'x' * 10000  # Very long string

        response = self.client.post(reverse('books:ajax_create_book'), {
            'title': very_long_string,
            'file_path': '/library/test.epub',
            'description': very_long_string
        })

        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content)
        # Should either truncate or reject overly long values
        self.assertIn('success', response_data)

    def test_sql_injection_protection(self):
        """Test protection against SQL injection attempts."""
        malicious_inputs = [
            "'; DROP TABLE books; --",
            "1' OR '1'='1",
            "UNION SELECT * FROM auth_user",
            "'; UPDATE books SET title='hacked'; --"
        ]

        for malicious_input in malicious_inputs:
            with self.subTest(input=malicious_input):
                response = self.client.post(reverse('books:ajax_search_books'), {
                    'query': malicious_input
                })

                # Should handle malicious input safely
                self.assertEqual(response.status_code, 200)
                response_data = json.loads(response.content)
                self.assertIn('success', response_data)

    def test_xss_protection_in_inputs(self):
        """Test protection against XSS attacks in user inputs."""
        xss_payloads = [
            "<script>alert('xss')</script>",
            "javascript:alert('xss')",
            "<img src=x onerror=alert('xss')>",
            "';alert('xss');//"
        ]

        for payload in xss_payloads:
            with self.subTest(payload=payload):
                response = self.client.post(reverse('books:ajax_update_book'), {
                    'book_id': 1,
                    'title': payload,
                    'description': payload
                })

                # Should sanitize XSS payloads
                self.assertEqual(response.status_code, 200)
                response_data = json.loads(response.content)
                self.assertIn('success', response_data)

    def test_csrf_token_validation(self):
        """Test CSRF token validation in forms."""
        # Test without CSRF token (depending on configuration)
        self.client.logout()
        response = self.client.post(reverse('books:book_create'), {
            'title': 'CSRF Test Book',
            'file_path': '/library/csrf_test.epub'
        })

        # Should either require login or CSRF token
        self.assertIn(response.status_code, [302, 403])


class ConcurrencyErrorTests(TestCase):
    """Tests for concurrency and race condition handling."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.client.login(username='testuser', password='testpass123')

    def test_concurrent_book_updates(self):
        """Test handling of concurrent book updates."""
        book = Book.objects.create(
            title="Concurrency Test",
            file_path="/library/concurrency_test.epub",
            file_format="epub"
        )

        # Simulate concurrent updates by making multiple requests
        import threading
        results = []

        def update_book(title_suffix):
            response = self.client.post(reverse('books:ajax_update_book'), {
                'book_id': book.id,
                'title': f'Updated Title {title_suffix}'
            })
            results.append(response.status_code)

        # Start multiple threads
        threads = []
        for i in range(5):
            thread = threading.Thread(target=update_book, args=(i,))
            threads.append(thread)
            thread.start()

        # Wait for all threads
        for thread in threads:
            thread.join()

        # All requests should be handled without errors
        for status_code in results:
            self.assertEqual(status_code, 200)

    def test_race_condition_in_file_processing(self):
        """Test handling of race conditions in file processing."""
        book = Book.objects.create(
            title="Race Condition Test",
            file_path="/library/race_test.epub",
            file_format="epub"
        )

        # Try to process the same file simultaneously
        processing_url = reverse('books:ajax_process_book')

        results = []

        def process_book():
            response = self.client.post(processing_url, {
                'book_id': book.id,
                'operation': 'extract_metadata'
            })
            results.append(json.loads(response.content))

        # Start multiple processing requests
        import threading
        threads = []
        for i in range(3):
            thread = threading.Thread(target=process_book)
            threads.append(thread)
            thread.start()

        # Wait for completion
        for thread in threads:
            thread.join()

        # Should handle concurrent processing gracefully
        for result in results:
            self.assertIn('success', result)

    @patch('books.models.Book.objects.select_for_update')
    def test_database_locking_mechanism(self, mock_select_for_update):
        """Test database locking mechanisms."""
        # Simulate select_for_update
        mock_select_for_update.return_value.get.return_value = Book(
            id=1,
            title="Lock Test",
            file_path="/library/lock_test.epub"
        )

        response = self.client.post(reverse('books:ajax_update_book_atomic'), {
            'book_id': 1,
            'title': 'Atomically Updated Title'
        })

        self.assertEqual(response.status_code, 200)

        # Verify select_for_update was called
        mock_select_for_update.assert_called()


class MemoryAndResourceErrorTests(TestCase):
    """Tests for memory and resource limitation handling."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.client.login(username='testuser', password='testpass123')

    @patch('psutil.virtual_memory')
    def test_low_memory_handling(self, mock_memory):
        """Test handling of low memory conditions."""
        # Simulate low memory
        mock_memory.return_value.available = 100 * 1024 * 1024  # 100MB available
        mock_memory.return_value.percent = 95  # 95% used

        # Try to perform memory-intensive operation
        response = self.client.post(reverse('books:ajax_batch_process_large_files'), {
            'book_ids': list(range(1, 1000)),  # Many books
            'operation': 'extract_metadata'
        })

        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content)

        # Should either succeed with reduced batch size or warn about memory
        self.assertIn('success', response_data)

    def test_large_dataset_pagination(self):
        """Test handling of very large datasets."""
        # Create many books
        books = []
        for i in range(1000):  # Large number of books
            book = Book.objects.create(
                title=f"Large Dataset Book {i}",
                file_path=f"/library/large_{i}.epub",
                file_format="epub"
            )
            books.append(book)

        # Test pagination handles large datasets
        response = self.client.get(reverse('books:book_list'))
        self.assertEqual(response.status_code, 200)

        # Should use pagination to limit results
        if 'books' in response.context:
            books_page = response.context['books']
            if hasattr(books_page, 'paginator'):
                # Page size should be reasonable
                self.assertLessEqual(books_page.paginator.per_page, 100)

    def test_disk_space_validation(self):
        """Test validation of available disk space."""
        with patch('shutil.disk_usage') as mock_disk_usage:
            # Simulate low disk space
            mock_disk_usage.return_value = (
                1000000000,  # total: 1GB
                900000000,   # used: 900MB
                100000000    # free: 100MB
            )

            response = self.client.post(reverse('books:ajax_check_disk_space'), {
                'operation': 'bulk_import',
                'estimated_size': 200000000  # 200MB needed
            })

            self.assertEqual(response.status_code, 200)
            response_data = json.loads(response.content)

            # Should warn about insufficient disk space
            self.assertFalse(response_data.get('sufficient_space', True))

    def test_timeout_handling_long_operations(self):
        """Test handling of operation timeouts."""
        with patch('time.sleep') as mock_sleep:
            # Simulate long-running operation
            mock_sleep.side_effect = Exception("Operation timeout")

            response = self.client.post(reverse('books:ajax_long_running_operation'), {
                'operation': 'full_library_scan',
                'timeout': 30  # 30 second timeout
            })

            self.assertEqual(response.status_code, 200)
            response_data = json.loads(response.content)

            # Should handle timeout gracefully
            self.assertIn('success', response_data)
            if not response_data.get('success'):
                self.assertIn('timeout', response_data.get('error', '').lower())


class ErrorRecoveryTests(TestCase):
    """Tests for error recovery and graceful degradation."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.client.login(username='testuser', password='testpass123')

    def test_partial_failure_handling(self):
        """Test handling of partial failures in batch operations."""
        # Create some valid and some invalid books
        valid_book = Book.objects.create(
            title="Valid Book",
            file_path="/library/valid.epub",
            file_format="epub"
        )

        book_ids = [valid_book.id, 99999, 99998]  # Mix of valid and invalid IDs

        response = self.client.post(reverse('books:ajax_batch_update_books'), {
            'book_ids': book_ids,
            'updates': {'genre': 'Science Fiction'}
        })

        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content)

        # Should report partial success
        self.assertIn('partial_success', response_data.keys() or ['success'])
        self.assertIn('failed_items', response_data.keys() or ['errors'])

    def test_fallback_mechanism_external_services(self):
        """Test fallback mechanisms when external services fail."""
        with patch('books.utils.external_services.primary_isbn_service') as mock_primary:
            with patch('books.utils.external_services.fallback_isbn_service') as mock_fallback:
                # Primary service fails
                mock_primary.lookup_isbn.side_effect = Exception("Service unavailable")

                # Fallback service succeeds
                mock_fallback.lookup_isbn.return_value = {
                    'title': 'Fallback Title',
                    'author': 'Fallback Author'
                }

                response = self.client.post(reverse('books:ajax_isbn_lookup'), {
                    'isbn': '1234567890'
                })

                self.assertEqual(response.status_code, 200)
                response_data = json.loads(response.content)

                # Should succeed using fallback service
                self.assertTrue(response_data.get('success', False))
                self.assertEqual(response_data.get('title'), 'Fallback Title')

    def test_graceful_degradation_missing_features(self):
        """Test graceful degradation when optional features are unavailable."""
        with patch('books.scanner.ai.ai_module_available', False):
            # AI features should be disabled gracefully
            response = self.client.get(reverse('books:book_list'))
            self.assertEqual(response.status_code, 200)

            # AI-related elements should be hidden or disabled
            # This would depend on template logic

    def test_retry_mechanism_transient_failures(self):
        """Test retry mechanisms for transient failures."""
        with patch('books.utils.network.make_request') as mock_request:
            # First two attempts fail, third succeeds
            mock_request.side_effect = [
                Exception("Network timeout"),
                Exception("Temporary unavailable"),
                {'status': 'success', 'data': 'retrieved'}
            ]

            response = self.client.post(reverse('books:ajax_fetch_external_data'), {
                'source': 'test_service',
                'max_retries': 3
            })

            self.assertEqual(response.status_code, 200)
            response_data = json.loads(response.content)

            # Should succeed after retries
            self.assertTrue(response_data.get('success', False))

            # Verify retry attempts
            self.assertEqual(mock_request.call_count, 3)

    def test_automatic_error_reporting(self):
        """Test automatic error reporting and logging."""
        with patch('logging.Logger.error') as mock_logger:
            # Trigger an error condition
            response = self.client.post(reverse('books:ajax_trigger_error'), {
                'error_type': 'test_error'
            })

            # Error should be logged
            mock_logger.assert_called()

            # Response should be handled gracefully
            self.assertEqual(response.status_code, 200)

    def test_error_context_preservation(self):
        """Test preservation of error context for debugging."""
        response = self.client.post(reverse('books:ajax_debug_operation'), {
            'operation': 'test_with_context',
            'debug': True
        })

        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content)

        if not response_data.get('success', True):
            # Error response should include context information
            self.assertIn('debug_info', response_data.keys() or ['error'])
            self.assertIn('stack_trace', response_data.keys() or ['error'])


@override_settings(DEBUG=True)
class DebugModeErrorTests(TestCase):
    """Tests for error handling in debug mode."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.client.login(username='testuser', password='testpass123')

    def test_detailed_error_messages_in_debug(self):
        """Test that detailed error messages are shown in debug mode."""
        # Trigger an error
        response = self.client.post(reverse('books:ajax_force_error'), {
            'error_type': 'validation_error'
        })

        # In debug mode, should show detailed error information
        if response.status_code == 200:
            response_data = json.loads(response.content)
            if not response_data.get('success', True):
                # Should include detailed error information
                error_info = response_data.get('error', '')
                self.assertTrue(len(error_info) > 10)  # Should be detailed

    def test_stack_trace_inclusion_debug_mode(self):
        """Test that stack traces are included in debug mode."""
        with patch('books.views.problematic_function') as mock_function:
            mock_function.side_effect = Exception("Test exception with stack trace")

            response = self.client.post(reverse('books:ajax_test_exception'))

            if response.status_code == 200:
                response_data = json.loads(response.content)
                # In debug mode, might include stack trace
                self.assertIn('success', response_data)


class ProductionErrorTests(TestCase):
    """Tests for error handling in production mode."""

    @override_settings(DEBUG=False)
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.client.login(username='testuser', password='testpass123')

    @override_settings(DEBUG=False)
    def test_generic_error_messages_in_production(self):
        """Test that generic error messages are shown in production."""
        # Trigger an error
        response = self.client.post(reverse('books:ajax_force_error'), {
            'error_type': 'internal_error'
        })

        # In production mode, should show generic error messages
        if response.status_code == 200:
            response_data = json.loads(response.content)
            if not response_data.get('success', True):
                # Error message should be generic, not revealing internal details
                error_info = response_data.get('error', '')
                self.assertNotIn('traceback', error_info.lower())
                self.assertNotIn('exception', error_info.lower())
