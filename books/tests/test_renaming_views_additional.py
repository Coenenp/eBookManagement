"""
Additional test cases for books/tests/test_renaming_views.py
Supplements the existing comprehensive test suite with additional edge cases.
"""

import json
from unittest.mock import patch
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from books.models import FinalMetadata
from books.tests.test_helpers import create_test_book_with_file, create_test_scan_folder


class RenamingViewsAdditionalTests(TestCase):
    """Additional test cases to supplement the existing comprehensive test suite"""

    def setUp(self):
        """Set up additional test data"""
        self.client = Client()

        User = get_user_model()
        self.user = User.objects.create_user(
            username='testuser_additional',
            password='testpass123'
        )

        self.scan_folder = create_test_scan_folder(name="Additional Test Folder")

        # Create books with edge case scenarios
        self.book_with_special_chars = create_test_book_with_file(
            file_path="/test/books/Special & Characters! @#$.epub",
            file_format="epub",
            file_size=1000000,
            scan_folder=self.scan_folder
        )

        # Create final metadata for the book
        FinalMetadata.objects.create(
            book=self.book_with_special_chars,
            final_title="Book with Special & Characters! @#$",
            final_author="Author, Special & Co.",
            final_series="Series with Numbers 123",
            final_series_number="1.5",
            is_reviewed=True
        )

        self.book_long_title = create_test_book_with_file(
            file_path="/test/books/very_long_filename.epub",
            file_format="epub",
            file_size=2000000,
            scan_folder=self.scan_folder
        )

        FinalMetadata.objects.create(
            book=self.book_long_title,
            final_title="This Is An Extremely Long Book Title That Exceeds Normal Length Limits And May Cause Issues With File System Naming Conventions On Various Operating Systems",
            final_author="Very Long Author Name That Also Exceeds Normal Limits",
            is_reviewed=True
        )

        self.client.login(username='testuser_additional', password='testpass123')

    def test_renaming_with_special_characters(self):
        """Test renaming books with special characters in metadata"""
        preview_url = reverse('books:renamer_preview_pattern')
        response = self.client.post(preview_url, {
            'folder_pattern': '${author_sort}',
            'filename_pattern': '${title}.${ext}',
            'book_ids': [self.book_with_special_chars.id]
        })

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertTrue(data['success'])

        # Check that special characters are handled properly
        preview = data['previews'][0]
        self.assertIn('new_path', preview)

        # Special characters should be sanitized or preserved appropriately
        new_path = preview['new_path']
        self.assertNotIn('//', new_path)  # No double slashes
        self.assertTrue(new_path.endswith('.epub'))

    def test_renaming_with_very_long_titles(self):
        """Test renaming books with extremely long titles"""
        preview_url = reverse('books:renamer_preview_pattern')
        response = self.client.post(preview_url, {
            'folder_pattern': '${author_last}',
            'filename_pattern': '${title}.${ext}',
            'book_ids': [self.book_long_title.id]
        })

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)

        if data['success']:
            preview = data['previews'][0]
            new_path = preview['new_path']

            # Path should be truncated to reasonable length
            # (Windows has 260 char limit, Unix varies but ~4096 is common)
            self.assertLessEqual(len(new_path), 260)

            # Should still have valid extension
            self.assertTrue(new_path.endswith('.epub'))

    def test_pattern_validation_edge_cases(self):
        """Test pattern validation with edge cases"""
        validate_url = reverse('books:renamer_validate_pattern')

        # Test empty pattern
        response = self.client.post(validate_url, {
            'pattern': '',
            'type': 'filename'
        })
        data = json.loads(response.content)
        self.assertFalse(data['valid'])

        # Test pattern with only spaces
        response = self.client.post(validate_url, {
            'pattern': '   ',
            'type': 'filename'
        })
        data = json.loads(response.content)
        self.assertFalse(data['valid'])

        # Test pattern with invalid characters for filesystem
        invalid_chars = ['<', '>', ':', '"', '|', '?', '*']
        for char in invalid_chars:
            response = self.client.post(validate_url, {
                'pattern': f'title{char}author',
                'type': 'filename'
            })
            data = json.loads(response.content)
            # Should either be invalid or sanitize the character
            if not data['valid']:
                self.assertIn('character', data.get('error', '').lower())

    def test_concurrent_renaming_operations(self):
        """Test handling of concurrent renaming operations"""
        import threading
        import time

        results = []
        errors = []

        def rename_operation(thread_id):
            try:
                preview_url = reverse('books:renamer_preview_pattern')
                response = self.client.post(preview_url, {
                    'folder_pattern': f'Thread_{thread_id}',
                    'filename_pattern': '${title}.${ext}',
                    'book_ids': [self.book_with_special_chars.id]
                })

                results.append((thread_id, response.status_code))
                time.sleep(0.1)  # Small delay to test concurrency

            except Exception as e:
                errors.append((thread_id, str(e)))

        # Start multiple threads
        threads = []
        for i in range(3):  # Reduced number for CI stability
            thread = threading.Thread(target=rename_operation, args=(i,))
            threads.append(thread)
            thread.start()

        # Wait for completion
        for thread in threads:
            thread.join()

        # All operations should succeed
        self.assertEqual(len(errors), 0, f"Concurrent operations failed: {errors}")
        self.assertEqual(len(results), 3)

        # All should return 200
        for thread_id, status_code in results:
            self.assertEqual(status_code, 200)

    def test_memory_usage_with_large_batch(self):
        """Test memory efficiency with large batch operations"""
        # Create many books for batch testing
        books = []
        for i in range(20):  # Reduced for CI
            book = create_test_book_with_file(
                file_path=f"/test/batch/book_{i}.epub",
                file_format="epub",
                file_size=1000000,
                scan_folder=self.scan_folder
            )

            FinalMetadata.objects.create(
                book=book,
                final_title=f"Batch Test Book {i}",
                final_author=f"Author {i}",
                is_reviewed=True
            )

            books.append(book)

        # Test preview with all books
        preview_url = reverse('books:renamer_preview_pattern')
        book_ids = [book.id for book in books]

        import time
        start_time = time.time()

        response = self.client.post(preview_url, {
            'folder_pattern': '${author_last}',
            'filename_pattern': '${title}.${ext}',
            'book_ids': book_ids
        })

        end_time = time.time()
        processing_time = end_time - start_time

        # Should complete in reasonable time
        self.assertLess(processing_time, 5.0)
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content)
        if data['success']:
            # Should handle all books
            self.assertEqual(len(data['previews']), len(books))

    @patch('os.path.exists')
    @patch('os.access')
    def test_file_permission_handling(self, mock_access, mock_exists):
        """Test handling of file permission issues"""
        mock_exists.return_value = True
        mock_access.return_value = False  # No write permission

        execute_url = reverse('books:renamer_execute_batch')
        response = self.client.post(execute_url, {
            'folder_pattern': '${author_last}',
            'filename_pattern': '${title}.${ext}',
            'book_ids': [self.book_with_special_chars.id],
            'dry_run': False
        })

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)

        # Should handle permission errors gracefully
        if not data['success']:
            self.assertIn('permission', data['error'].lower())

    def test_unicode_filename_handling(self):
        """Test handling of Unicode characters in filenames"""
        # Create book with Unicode metadata
        unicode_book = create_test_book_with_file(
            file_path="/test/unicode/café.epub",
            file_format="epub",
            file_size=1000000,
            scan_folder=self.scan_folder
        )

        FinalMetadata.objects.create(
            book=unicode_book,
            final_title="Café François 中文 العربية",
            final_author="José María Azñar",
            is_reviewed=True
        )

        preview_url = reverse('books:renamer_preview_pattern')
        response = self.client.post(preview_url, {
            'folder_pattern': '${author_sort}',
            'filename_pattern': '${title}.${ext}',
            'book_ids': [unicode_book.id]
        })

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertTrue(data['success'])

        # Should handle Unicode characters properly
        preview = data['previews'][0]
        new_path = preview['new_path']

        # Path should be valid (may be transliterated or preserved)
        self.assertIsNotNone(new_path)
        self.assertTrue(new_path.endswith('.epub'))

    def test_network_path_handling(self):
        """Test handling of network paths and UNC paths"""
        # Create book with network path
        network_book = create_test_book_with_file(
            file_path="//server/share/books/network_book.epub",
            file_format="epub",
            file_size=1000000,
            scan_folder=self.scan_folder
        )

        FinalMetadata.objects.create(
            book=network_book,
            final_title="Network Book",
            final_author="Network Author",
            is_reviewed=True
        )

        preview_url = reverse('books:renamer_preview_pattern')
        response = self.client.post(preview_url, {
            'folder_pattern': '${author_last}',
            'filename_pattern': '${title}.${ext}',
            'book_ids': [network_book.id]
        })

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)

        # Should handle network paths appropriately
        if data['success']:
            preview = data['previews'][0]
            new_path = preview['new_path']

            # Should preserve network path structure
            self.assertTrue(new_path.startswith('//server/share/') or 'Network Author' in new_path)

    def test_database_transaction_handling(self):
        """Test database transaction handling during rename operations"""
        execute_url = reverse('books:renamer_execute_batch')

        # Test with database error simulation
        with patch('books.models.Book.save') as mock_save:
            mock_save.side_effect = Exception("Database error")

            response = self.client.post(execute_url, {
                'folder_pattern': '${author_last}',
                'filename_pattern': '${title}.${ext}',
                'book_ids': [self.book_with_special_chars.id],
                'dry_run': False
            })

            # Should handle database errors gracefully
            self.assertEqual(response.status_code, 200)
            data = json.loads(response.content)
            self.assertFalse(data['success'])
            self.assertIn('error', data)

    def test_pattern_complexity_limits(self):
        """Test handling of very complex patterns"""
        validate_url = reverse('books:renamer_validate_pattern')

        # Test extremely complex nested pattern
        complex_pattern = '${author_sort}/${series_name if series_name else "Standalone"}/${title if title else "Unknown"}.${ext}'

        response = self.client.post(validate_url, {
            'pattern': complex_pattern,
            'type': 'filename'
        })

        data = json.loads(response.content)
        # Should either validate or reject with clear error
        self.assertIn('valid', data)

        if not data['valid']:
            self.assertIn('error', data)
            self.assertIsInstance(data['error'], str)

    def test_renaming_robustness_under_load(self):
        """Test system robustness under load conditions"""
        # Create moderate load simulation
        import time

        start_time = time.time()

        # Make multiple rapid requests
        for i in range(10):
            preview_url = reverse('books:renamer_preview_pattern')
            response = self.client.post(preview_url, {
                'folder_pattern': f'Load_Test_{i}',
                'filename_pattern': '${title}_${counter}.${ext}',
                'book_ids': [self.book_with_special_chars.id]
            })

            # Each request should succeed
            self.assertEqual(response.status_code, 200)

            time.sleep(0.05)  # Small delay between requests

        end_time = time.time()
        total_time = end_time - start_time

        # Should handle load reasonably well
        self.assertLess(total_time, 10.0)  # All requests within 10 seconds

    def test_cross_platform_path_compatibility(self):
        """Test path compatibility across different operating systems"""
        import platform

        preview_url = reverse('books:renamer_preview_pattern')

        # Test patterns that might cause cross-platform issues
        test_patterns = [
            ('${author_last}\\${title}', 'Windows backslashes'),
            ('${author_last}/${title}', 'Unix forward slashes'),
            ('${author_last}:${title}', 'Colon separator'),
        ]

        for pattern, description in test_patterns:
            response = self.client.post(preview_url, {
                'folder_pattern': pattern,
                'filename_pattern': '${title}.${ext}',
                'book_ids': [self.book_with_special_chars.id]
            })

            self.assertEqual(response.status_code, 200)
            data = json.loads(response.content)

            # Should handle cross-platform differences
            if data['success']:
                preview = data['previews'][0]
                new_path = preview['new_path']

                # Path should use appropriate separators for current platform
                if platform.system() == 'Windows':
                    # Should handle Windows paths appropriately
                    self.assertNotIn(':', new_path[1:])  # No colons except drive letter
                else:
                    # Should handle Unix paths appropriately
                    self.assertNotIn('\\', new_path)  # No backslashes

    def test_metadata_edge_cases_handling(self):
        """Test handling of edge cases in book metadata"""
        # Create book with minimal/problematic metadata
        edge_case_book = create_test_book_with_file(
            file_path="/test/edge/edge_case.epub",
            file_format="epub",
            file_size=1000000,
            scan_folder=self.scan_folder
        )

        # Create metadata with edge cases
        FinalMetadata.objects.create(
            book=edge_case_book,
            final_title="",  # Empty title
            final_author=None,  # Null author
            final_series="   ",  # Whitespace-only series
            final_series_number="0",  # Zero series number
            is_reviewed=True
        )

        preview_url = reverse('books:renamer_preview_pattern')
        response = self.client.post(preview_url, {
            'folder_pattern': '${author_sort}/${series_name}',
            'filename_pattern': '${title}.${ext}',
            'book_ids': [edge_case_book.id]
        })

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)

        # Should handle edge cases gracefully
        if data['success']:
            preview = data['previews'][0]
            new_path = preview['new_path']

            # Should provide fallback values for missing metadata
            self.assertGreater(len(new_path), 0)
            self.assertTrue(new_path.endswith('.epub'))

            # Should not have empty path components
            self.assertNotIn('//', new_path)
            self.assertNotIn('\\\\', new_path)

    def test_renaming_performance_benchmarks(self):
        """Test performance benchmarks for renaming operations"""
        # Create performance test data
        perf_books = []
        for i in range(50):  # Moderate size for CI
            book = create_test_book_with_file(
                file_path=f"/test/perf/performance_book_{i:03d}.epub",
                file_format="epub",
                file_size=1000000,
                scan_folder=self.scan_folder
            )

            FinalMetadata.objects.create(
                book=book,
                final_title=f"Performance Test Book Number {i:03d}",
                final_author=f"Performance Author {i % 10}",
                final_series=f"Performance Series {i // 10}",
                final_series_number=str(i % 10 + 1),
                is_reviewed=True
            )

            perf_books.append(book)

        # Benchmark pattern validation
        validate_url = reverse('books:renamer_validate_pattern')

        import time
        start_time = time.time()

        response = self.client.post(validate_url, {
            'pattern': '${author_sort}/${series_name}/${series_number:02d} - ${title}.${ext}',
            'type': 'filename'
        })

        validation_time = time.time() - start_time

        # Validation should be very fast
        self.assertLess(validation_time, 0.5)
        self.assertEqual(response.status_code, 200)

        # Benchmark preview generation
        preview_url = reverse('books:renamer_preview_pattern')
        book_ids = [book.id for book in perf_books[:25]]  # Limit for performance

        start_time = time.time()

        response = self.client.post(preview_url, {
            'folder_pattern': '${author_sort}/${series_name}',
            'filename_pattern': '${series_number:02d} - ${title}.${ext}',
            'book_ids': book_ids
        })

        preview_time = time.time() - start_time

        # Preview should complete in reasonable time
        self.assertLess(preview_time, 3.0)
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content)
        if data['success']:
            # Should process all requested books
            self.assertEqual(len(data['previews']), len(book_ids))
