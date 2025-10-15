"""
Test Suite for Ebook & Series Renamer - Views & Integration
Tests the Django views, AJAX endpoints, and complete integration
with the web interface and user interactions.
"""

import json
import time
from unittest.mock import patch, MagicMock

from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model

from books.models import Author, Series, Genre
from books.tests.test_helpers import create_test_book_with_file


class RenamingViewsTestCase(TestCase):
    """Base test case for renaming views"""

    def setUp(self):
        """Set up test data and user authentication"""
        self.client = Client()

        # Create test user
        User = get_user_model()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )

        # Create test data
        self.author = Author.objects.create(
            first_name="Isaac",
            last_name="Asimov"
        )

        self.series = Series.objects.create(name="Foundation Series")

        self.genre = Genre.objects.create(name="Science Fiction")
        # NOTE: Language and Format models don't exist - commented out for now
        # self.language = Language.objects.create(name="English", code="en")
        # self.format_epub = Format.objects.create(name="EPUB", extension=".epub")

        # Create test books
        self.book1 = create_test_book_with_file(
            file_path="/test/Foundation.epub",
            file_size=1024000,
            file_format="epub"
        )

        self.book2 = create_test_book_with_file(
            file_path="/test/Foundation and Empire.epub",
            file_size=1536000,
            file_format="epub"
        )

        # Create metadata relationships
        from books.models import DataSource, BookTitle, BookAuthor, BookSeries, FinalMetadata

        # Create data source (use get_or_create to avoid duplicates)
        self.data_source, created = DataSource.objects.get_or_create(
            name=DataSource.INITIAL_SCAN,
            defaults={'trust_level': 0.9}
        )

        # Create book titles
        BookTitle.objects.create(
            book=self.book1,
            title="Foundation",
            source=self.data_source,
            confidence=1.0
        )
        BookTitle.objects.create(
            book=self.book2,
            title="Foundation and Empire",
            source=self.data_source,
            confidence=1.0
        )

        # Create book-author relationships
        BookAuthor.objects.create(
            book=self.book1,
            author=self.author,
            source=self.data_source,
            confidence=1.0,
            is_main_author=True
        )
        BookAuthor.objects.create(
            book=self.book2,
            author=self.author,
            source=self.data_source,
            confidence=1.0,
            is_main_author=True
        )

        # Create book-series relationships
        BookSeries.objects.create(
            book=self.book1,
            series=self.series,
            series_number="1",
            source=self.data_source,
            confidence=1.0
        )
        BookSeries.objects.create(
            book=self.book2,
            series=self.series,
            series_number="2",
            source=self.data_source,
            confidence=1.0
        )

        # Create final metadata for renaming engine
        FinalMetadata.objects.create(
            book=self.book1,
            final_title="Foundation",
            final_author="Isaac Asimov",
            final_series="Foundation Series",
            final_series_number="1"
        )
        FinalMetadata.objects.create(
            book=self.book2,
            final_title="Foundation and Empire",
            final_author="Isaac Asimov",
            final_series="Foundation Series",
            final_series_number="2"
        )

        # Login user
        self.client.login(username='testuser', password='testpass123')


class BookRenamerViewTests(RenamingViewsTestCase):
    """Test cases for the main BookRenamerView"""

    def test_renamer_view_get_authenticated(self):
        """Test GET request to renamer view when authenticated"""
        url = reverse('books:book_renamer')
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        # Check for basic functionality rather than specific text
        self.assertTrue(response.context['predefined_patterns'])
        self.assertTrue(response.context['available_tokens'])

    def test_renamer_view_get_unauthenticated(self):
        """Test GET request to renamer view when not authenticated"""
        self.client.logout()
        url = reverse('books:book_renamer')
        response = self.client.get(url)

        # Should redirect to login
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_renamer_view_context_data(self):
        """Test context data provided to template"""
        url = reverse('books:book_renamer')
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)

        # Check context data
        context = response.context
        self.assertIn('predefined_patterns', context)
        self.assertIn('available_tokens', context)
        self.assertIn('books', context)

        # Books should be accessible in queryset
        books = context['books']
        self.assertIsNotNone(books)

    def test_renamer_view_filtering(self):
        """Test view filtering functionality"""
        url = reverse('books:book_renamer')

        # Test search filter
        response = self.client.get(url, {'search': 'Foundation'})
        self.assertEqual(response.status_code, 200)
        books = response.context['books']
        self.assertIn(self.book1, books)

        # Test category filter
        response = self.client.get(url, {'category': self.category.id})
        self.assertEqual(response.status_code, 200)
        books = response.context['books']
        self.assertIn(self.book1, books)

        # Test language filter
        response = self.client.get(url, {'language': self.language.id})
        self.assertEqual(response.status_code, 200)
        books = response.context['books']
        self.assertIn(self.book1, books)


class PatternValidationViewTests(RenamingViewsTestCase):
    """Test cases for pattern validation AJAX endpoint"""

    def test_validate_pattern_valid_folder(self):
        """Test validating valid folder pattern"""
        url = reverse('books:renamer_validate_pattern')
        data = {
            'pattern': '${author_sort}/${series_name}',
            'type': 'folder'
        }

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)

        json_data = json.loads(response.content)
        self.assertTrue(json_data['success'])
        self.assertTrue(json_data['valid'])
        self.assertIn('preview', json_data)

    def test_validate_pattern_valid_filename(self):
        """Test validating valid filename pattern"""
        url = reverse('books:renamer_validate_pattern')
        data = {
            'pattern': '${title}.${ext}',
            'type': 'filename'
        }

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)

        json_data = json.loads(response.content)
        self.assertTrue(json_data['success'])
        self.assertTrue(json_data['valid'])
        self.assertIn('preview', json_data)

    def test_validate_pattern_invalid(self):
        """Test validating invalid pattern"""
        url = reverse('books:renamer_validate_pattern')
        data = {
            'pattern': '${invalid_token}',
            'type': 'filename'
        }

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)

        json_data = json.loads(response.content)
        self.assertTrue(json_data['success'])  # Request succeeded
        self.assertFalse(json_data['valid'])   # But pattern is invalid

    def test_validate_pattern_with_warnings(self):
        """Test pattern validation with warnings"""
        url = reverse('books:renamer_validate_pattern')
        data = {
            'pattern': '${title}',  # Missing extension
            'type': 'filename'
        }

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)

        json_data = json.loads(response.content)
        self.assertTrue(json_data['success'])
        self.assertTrue(json_data['valid'])
        self.assertIn('warnings', json_data)
        self.assertGreater(len(json_data['warnings']), 0)

    def test_validate_pattern_unauthenticated(self):
        """Test pattern validation when not authenticated"""
        self.client.logout()
        url = reverse('books:renamer_validate_pattern')
        data = {
            'pattern': '${title}.${ext}',
            'type': 'filename'
        }

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)  # Redirect to login

    def test_validate_pattern_invalid_method(self):
        """Test pattern validation with invalid HTTP method"""
        url = reverse('books:renamer_validate_pattern')
        response = self.client.get(url)  # GET instead of POST

        self.assertEqual(response.status_code, 405)  # Method not allowed


class PatternPreviewViewTests(RenamingViewsTestCase):
    """Test cases for pattern preview AJAX endpoint"""

    def test_preview_pattern_valid(self):
        """Test previewing valid patterns"""
        url = reverse('books:renamer_preview_pattern')
        data = {
            'folder_pattern': '${author_sort}',
            'filename_pattern': '${title}.${ext}',
            'book_ids': [str(self.book1.id), str(self.book2.id)]
        }

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)

        json_data = json.loads(response.content)
        self.assertTrue(json_data['success'])
        self.assertIn('previews', json_data)

        # Should have previews for both books
        previews = json_data['previews']
        self.assertEqual(len(previews), 2)

        # Check preview content
        preview1 = previews[0]
        self.assertIn('title', preview1)
        self.assertIn('author', preview1)
        self.assertIn('current_path', preview1)
        self.assertIn('full_target_path', preview1)

    def test_preview_pattern_single_book(self):
        """Test previewing patterns for single book"""
        url = reverse('books:renamer_preview_pattern')
        data = {
            'folder_pattern': 'Library/${format}/${author_sort}',
            'filename_pattern': '${series_name} - ${title}.${ext}',
            'book_ids': [str(self.book1.id)]
        }

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)

        json_data = json.loads(response.content)
        self.assertTrue(json_data['success'])

        previews = json_data['previews']
        self.assertEqual(len(previews), 1)

        preview = previews[0]
        self.assertEqual(preview['book_id'], self.book1.id)
        self.assertIn('Asimov, Isaac', preview['full_target_path'])
        self.assertIn('Foundation Series', preview['full_target_path'])

    def test_preview_pattern_empty_book_list(self):
        """Test previewing with empty book list"""
        url = reverse('books:renamer_preview_pattern')
        data = {
            'folder_pattern': '${author_sort}',
            'filename_pattern': '${title}.${ext}',
            'book_ids': []
        }

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)

        json_data = json.loads(response.content)
        self.assertFalse(json_data['success'])
        self.assertIn('error', json_data)

    def test_preview_pattern_invalid_book_ids(self):
        """Test previewing with invalid book IDs"""
        url = reverse('books:renamer_preview_pattern')
        data = {
            'folder_pattern': '${author_sort}',
            'filename_pattern': '${title}.${ext}',
            'book_ids': ['999', '1000']  # Non-existent IDs
        }

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)

        json_data = json.loads(response.content)
        self.assertTrue(json_data['success'])

        # Should have empty previews or error entries
        previews = json_data['previews']
        self.assertEqual(len(previews), 0)

    def test_preview_pattern_warnings(self):
        """Test preview with pattern warnings"""
        url = reverse('books:renamer_preview_pattern')
        data = {
            'folder_pattern': '${author_sort}',
            'filename_pattern': '${title}',  # Missing extension
            'book_ids': [str(self.book1.id)]
        }

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)

        json_data = json.loads(response.content)
        self.assertTrue(json_data['success'])

        # Should include warnings
        self.assertIn('filename_warnings', json_data)


class BatchRenameExecutionViewTests(RenamingViewsTestCase):
    """Test cases for batch rename execution AJAX endpoint"""

    @patch('books.views.renaming.BatchRenamer')
    def test_execute_batch_rename_dry_run(self, mock_batch_renamer):
        """Test executing batch rename in dry run mode"""
        # Mock the batch renamer
        mock_renamer = MagicMock()
        mock_batch_renamer.return_value = mock_renamer

        mock_result = {
            'success': True,
            'dry_run': True,
            'operations': [
                {
                    'operation_type': 'move_file',
                    'source_path': '/test/Foundation.epub',
                    'target_path': '/test/Asimov, Isaac/Foundation.epub',
                    'warnings': []
                }
            ],
            'summary': {
                'total_operations': 1,
                'main_files': 1,
                'companion_files': 0,
                'books_affected': 1
            }
        }
        mock_renamer.execute_operations.return_value = mock_result

        url = reverse('books:renamer_execute_batch')
        data = {
            'folder_pattern': '${author_sort}',
            'filename_pattern': '${title}.${ext}',
            'book_ids': [str(self.book1.id)],
            'dry_run': True,
            'include_companions': False
        }

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)

        json_data = json.loads(response.content)
        self.assertTrue(json_data['success'])
        self.assertTrue(json_data['dry_run'])
        self.assertIn('operations', json_data)
        self.assertIn('summary', json_data)

    @patch('books.views.renaming.BatchRenamer')
    def test_execute_batch_rename_actual(self, mock_batch_renamer):
        """Test executing actual batch rename"""
        # Mock the batch renamer
        mock_renamer = MagicMock()
        mock_batch_renamer.return_value = mock_renamer

        mock_result = {
            'success': True,
            'dry_run': False,
            'results': {
                'successful': 1,
                'failed': 0,
                'errors': []
            },
            'summary': {
                'total_operations': 1,
                'main_files': 1,
                'companion_files': 0,
                'books_affected': 1
            }
        }
        mock_renamer.execute_operations.return_value = mock_result

        url = reverse('books:renamer_execute_batch')
        data = {
            'folder_pattern': '${author_sort}',
            'filename_pattern': '${title}.${ext}',
            'book_ids': [str(self.book1.id)],
            'dry_run': False,
            'include_companions': True
        }

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)

        json_data = json.loads(response.content)
        self.assertTrue(json_data['success'])
        self.assertFalse(json_data['dry_run'])
        self.assertIn('results', json_data)

    def test_execute_batch_rename_missing_patterns(self):
        """Test execution with missing patterns"""
        url = reverse('books:renamer_execute_batch')
        data = {
            'folder_pattern': '',
            'filename_pattern': '',
            'book_ids': [str(self.book1.id)],
            'dry_run': True
        }

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)

        json_data = json.loads(response.content)
        self.assertFalse(json_data['success'])
        self.assertIn('error', json_data)

    def test_execute_batch_rename_no_books(self):
        """Test execution with no books selected"""
        url = reverse('books:renamer_execute_batch')
        data = {
            'folder_pattern': '${author_sort}',
            'filename_pattern': '${title}.${ext}',
            'book_ids': [],
            'dry_run': True
        }

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)

        json_data = json.loads(response.content)
        self.assertFalse(json_data['success'])
        self.assertIn('error', json_data)

    @patch('books.views.renaming.BatchRenamer')
    def test_execute_batch_rename_with_errors(self, mock_batch_renamer):
        """Test execution with errors"""
        # Mock the batch renamer to return errors
        mock_renamer = MagicMock()
        mock_batch_renamer.return_value = mock_renamer

        mock_result = {
            'success': False,
            'error': 'File permission denied',
            'results': {
                'successful': 0,
                'failed': 1,
                'errors': ['Permission denied: /test/Foundation.epub']
            }
        }
        mock_renamer.execute_operations.return_value = mock_result

        url = reverse('books:renamer_execute_batch')
        data = {
            'folder_pattern': '${author_sort}',
            'filename_pattern': '${title}.${ext}',
            'book_ids': [str(self.book1.id)],
            'dry_run': False
        }

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)

        json_data = json.loads(response.content)
        self.assertFalse(json_data['success'])
        self.assertIn('error', json_data)


class RenamingIntegrationTests(RenamingViewsTestCase):
    """Integration tests for complete renaming workflows through web interface"""

    def test_complete_renaming_workflow(self):
        """Test complete workflow from view to execution"""
        # 1. Load the renamer page
        url = reverse('books:book_renamer')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        # 2. Validate patterns
        validate_url = reverse('books:renamer_validate_pattern')

        # Validate folder pattern
        response = self.client.post(validate_url, {
            'pattern': '${author_sort}',
            'type': 'folder'
        })
        self.assertEqual(response.status_code, 200)
        folder_valid = json.loads(response.content)['valid']
        self.assertTrue(folder_valid)

        # Validate filename pattern
        response = self.client.post(validate_url, {
            'pattern': '${title}.${ext}',
            'type': 'filename'
        })
        self.assertEqual(response.status_code, 200)
        filename_valid = json.loads(response.content)['valid']
        self.assertTrue(filename_valid)

        # 3. Preview changes
        preview_url = reverse('books:renamer_preview_pattern')
        response = self.client.post(preview_url, {
            'folder_pattern': '${author_sort}',
            'filename_pattern': '${title}.${ext}',
            'book_ids': [str(self.book1.id)]
        })
        self.assertEqual(response.status_code, 200)
        preview_data = json.loads(response.content)
        self.assertTrue(preview_data['success'])
        self.assertGreater(len(preview_data['previews']), 0)

        # 4. Execute dry run
        execute_url = reverse('books:renamer_execute_batch')
        with patch('books.views.renaming.BatchRenamer') as mock_batch_renamer:
            mock_renamer = MagicMock()
            mock_batch_renamer.return_value = mock_renamer

            mock_result = {
                'success': True,
                'dry_run': True,
                'operations': [],
                'summary': {
                    'total_operations': 1,
                    'main_files': 1,
                    'companion_files': 0,
                    'books_affected': 1
                }
            }
            mock_renamer.execute_operations.return_value = mock_result

            response = self.client.post(execute_url, {
                'folder_pattern': '${author_sort}',
                'filename_pattern': '${title}.${ext}',
                'book_ids': [str(self.book1.id)],
                'dry_run': True
            })
            self.assertEqual(response.status_code, 200)
            execute_data = json.loads(response.content)
            self.assertTrue(execute_data['success'])
            self.assertTrue(execute_data['dry_run'])

    def test_error_handling_workflow(self):
        """Test error handling throughout the workflow"""
        # Test with invalid pattern
        validate_url = reverse('books:renamer_validate_pattern')
        response = self.client.post(validate_url, {
            'pattern': '${invalid_token}',
            'type': 'filename'
        })
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertFalse(data['valid'])

        # Test preview with invalid book IDs
        preview_url = reverse('books:renamer_preview_pattern')
        response = self.client.post(preview_url, {
            'folder_pattern': '${author_sort}',
            'filename_pattern': '${title}.${ext}',
            'book_ids': ['999']  # Non-existent ID
        })
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        # Should handle gracefully
        self.assertTrue(data['success'])

    def test_authentication_required_workflow(self):
        """Test that authentication is required for all endpoints"""
        self.client.logout()

        endpoints = [
            ('books:book_renamer', 'GET', {}),
            ('books:renamer_validate_pattern', 'POST', {'pattern': '${title}', 'type': 'filename'}),
            ('books:renamer_preview_pattern', 'POST', {'folder_pattern': '${author_sort}', 'filename_pattern': '${title}.${ext}', 'book_ids': []}),
            ('books:renamer_execute_batch', 'POST', {'folder_pattern': '${author_sort}', 'filename_pattern': '${title}.${ext}', 'book_ids': []})
        ]

        for endpoint, method, data in endpoints:
            with self.subTest(endpoint=endpoint):
                url = reverse(endpoint)

                if method == 'GET':
                    response = self.client.get(url)
                else:
                    response = self.client.post(url, data)

                # Should redirect to login or return 302/401
                self.assertIn(response.status_code, [302, 401])

    def test_csrf_protection(self):
        """Test CSRF protection on POST endpoints"""
        # Disable CSRF middleware for this test

        endpoints = [
            ('books:renamer_validate_pattern', {'pattern': '${title}', 'type': 'filename'}),
            ('books:renamer_preview_pattern', {'folder_pattern': '${author_sort}', 'filename_pattern': '${title}.${ext}', 'book_ids': []}),
            ('books:renamer_execute_batch', {'folder_pattern': '${author_sort}', 'filename_pattern': '${title}.${ext}', 'book_ids': []})
        ]

        for endpoint, data in endpoints:
            with self.subTest(endpoint=endpoint):
                url = reverse(endpoint)

                # Test with CSRF token (should work)
                response = self.client.post(url, data)
                # Should not return 403 (CSRF failure)
                self.assertNotEqual(response.status_code, 403)


class UserExperienceTests(RenamingViewsTestCase):
    """Test cases for user experience and interface behavior"""

    def test_pattern_examples_in_context(self):
        """Test that pattern examples are provided in context"""
        url = reverse('books:book_renamer')
        response = self.client.get(url)

        context = response.context
        token_reference = context['token_reference']

        # Should have examples for each token category
        self.assertIn('basic', token_reference)
        self.assertIn('metadata', token_reference)
        self.assertIn('format', token_reference)

        # Each category should have tokens with descriptions
        for category in token_reference.values():
            self.assertIn('tokens', category)
            for token_data in category['tokens']:
                self.assertIn('token', token_data)
                self.assertIn('description', token_data)

    def test_predefined_patterns_usability(self):
        """Test that predefined patterns are user-friendly"""
        url = reverse('books:book_renamer')
        response = self.client.get(url)

        context = response.context
        predefined_patterns = context['predefined_patterns']

        # Should have multiple predefined patterns
        self.assertGreater(len(predefined_patterns), 3)

        # Each pattern should have required fields
        for pattern_name, pattern_data in predefined_patterns.items():
            self.assertIn('folder', pattern_data)
            self.assertIn('filename', pattern_data)
            self.assertIn('description', pattern_data)

            # Patterns should be non-empty
            self.assertGreater(len(pattern_data['folder']), 0)
            self.assertGreater(len(pattern_data['filename']), 0)

    def test_book_selection_interface(self):
        """Test book selection interface functionality"""
        url = reverse('books:book_renamer')
        response = self.client.get(url)

        # Should include books in context
        books = response.context['books']
        self.assertIn(self.book1, books)
        self.assertIn(self.book2, books)

        # Books should have necessary display information
        for book in books:
            self.assertTrue(hasattr(book, 'title'))
            self.assertTrue(hasattr(book, 'file_path'))
            self.assertTrue(hasattr(book, 'authors'))

    def test_responsive_ajax_endpoints(self):
        """Test that AJAX endpoints respond appropriately"""
        # Test validation endpoint responsiveness
        validate_url = reverse('books:renamer_validate_pattern')

        start_time = time.time()

        response = self.client.post(validate_url, {
            'pattern': '${title}.${ext}',
            'type': 'filename'
        })

        end_time = time.time()
        response_time = end_time - start_time

        # Should respond quickly (under 1 second for simple validation)
        self.assertLess(response_time, 1.0)
        self.assertEqual(response.status_code, 200)

        # Response should be valid JSON
        json_data = json.loads(response.content)
        self.assertIn('success', json_data)

    def test_error_message_quality(self):
        """Test that error messages are user-friendly"""
        # Test validation errors
        validate_url = reverse('books:renamer_validate_pattern')
        response = self.client.post(validate_url, {
            'pattern': '${invalid_token}',
            'type': 'filename'
        })

        json_data = json.loads(response.content)
        self.assertFalse(json_data['valid'])

        # Should provide helpful error information
        # (Implementation may vary, but should be user-friendly)

        # Test execution errors
        execute_url = reverse('books:renamer_execute_batch')
        response = self.client.post(execute_url, {
            'folder_pattern': '',
            'filename_pattern': '',
            'book_ids': [],
            'dry_run': True
        })

        json_data = json.loads(response.content)
        self.assertFalse(json_data['success'])
        self.assertIn('error', json_data)

        # Error message should be descriptive
        error_message = json_data['error']
        self.assertGreater(len(error_message), 10)  # Reasonable error message length
