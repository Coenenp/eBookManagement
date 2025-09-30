"""
Comprehensive tests for AJAX endpoints in views.py.

This module contains tests for all AJAX endpoints including metadata rescanning,
AI feedback, ISBN lookup, trust level updates, theme previews, and other
asynchronous operations.
"""

import json
from unittest.mock import patch, MagicMock
from django.test import TestCase, Client, RequestFactory, override_settings
from django.contrib.auth.models import User
from django.urls import reverse
from django.http import JsonResponse
from django.core.cache import cache
from books.models import Book, FinalMetadata, DataSource, AIFeedback, UserProfile, ScanFolder


class AJAXMetadataEndpointTests(TestCase):
    """Tests for AJAX metadata-related endpoints."""

    def setUp(self):
        self.client = Client()
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.client.login(username='testuser', password='testpass123')

        # Create a ScanFolder for all books in this test class
        self.scan_folder = ScanFolder.objects.create(
            path="/test/scan/folder",
            name="Test Scan Folder"
        )

        # Create test book
        self.book = Book.objects.create(
            file_path="/library/test.epub",
            file_format="epub",
            scan_folder=self.scan_folder
        )

        FinalMetadata.objects.create(
            book=self.book,
            final_title="Test Book",
            final_author="Test Author"
        )

        # Create data sources
        self.google_source, _ = DataSource.objects.get_or_create(
            name=DataSource.GOOGLE_BOOKS, defaults={'trust_level': 0.8}
        )

    def test_ajax_rescan_external_metadata_success(self):
        """Test successful AJAX metadata rescan."""
        url = reverse('books:ajax_rescan_external_metadata', kwargs={'book_id': self.book.id})

        data = {
            'sources': ['google', 'openlibrary'],
            'options': {
                'clearExisting': False,
                'forceRefresh': True
            },
            'searchTerms': {
                'title': 'Test Book',
                'author': 'Test Author'
            }
        }

        with patch('books.views.rescan_external_metadata') as mock_rescan:
            mock_rescan.return_value = JsonResponse({
                'success': True,
                'message': 'Metadata rescanned successfully',
                'before_counts': {'total': 1},
                'after_counts': {'total': 2},
                'added_counts': {'google': 1}
            })

            response = self.client.post(
                url,
                data=json.dumps(data),
                content_type='application/json'
            )

            self.assertEqual(response.status_code, 200)
            response_data = json.loads(response.content)
            self.assertTrue(response_data.get('success'))

    def test_ajax_rescan_external_metadata_invalid_book(self):
        """Test AJAX metadata rescan with invalid book ID."""
        url = reverse('books:ajax_rescan_external_metadata', kwargs={'book_id': 99999})

        data = {
            'sources': ['google'],
            'options': {'forceRefresh': True},
            'searchTerms': {}
        }

        response = self.client.post(
            url,
            data=json.dumps(data),
            content_type='application/json'
        )

        # Should return 404 or error
        self.assertEqual(response.status_code, 404)

    def test_ajax_rescan_external_metadata_malformed_data(self):
        """Test AJAX metadata rescan with malformed JSON data."""
        url = reverse('books:ajax_rescan_external_metadata', kwargs={'book_id': self.book.id})

        response = self.client.post(
            url,
            data="invalid json",
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 400)  # Malformed JSON should be a 400 Bad Request
        response_data = json.loads(response.content)
        self.assertFalse(response_data['success'])
        self.assertIn('error', response_data)

    def test_update_trust_endpoint(self):
        """Test trust level update endpoint."""
        url = reverse('books:update_trust', kwargs={'pk': self.google_source.pk})

        response = self.client.post(url, {
            'trust_level': '0.9'
        })

        self.assertEqual(response.status_code, 200)
        response_data = response.json()
        self.assertTrue(response_data['success'])
        self.assertEqual(response_data['new_trust_level'], 0.9)

        # Verify database update
        self.google_source.refresh_from_db()
        self.assertEqual(self.google_source.trust_level, 0.9)

    def test_update_trust_invalid_values(self):
        """Test trust level update with invalid values."""
        url = reverse('books:update_trust', kwargs={'pk': self.google_source.pk})

        # Test invalid trust level (> 1.0)
        response = self.client.post(url, {'trust_level': '1.5'})
        self.assertEqual(response.status_code, 400)
        response_data = response.json()
        self.assertFalse(response_data['success'])
        self.assertIn('error', response_data)

        # Test invalid trust level (< 0.0)
        response = self.client.post(url, {'trust_level': '-0.1'})
        self.assertEqual(response.status_code, 400)
        response_data = response.json()
        self.assertFalse(response_data['success'])

        # Test non-numeric value
        response = self.client.post(url, {'trust_level': 'invalid'})
        self.assertEqual(response.status_code, 400)
        response_data = response.json()
        self.assertFalse(response_data['success'])

    def test_update_trust_missing_parameter(self):
        """Test trust level update with missing trust_level parameter."""
        url = reverse('books:update_trust', kwargs={'pk': self.google_source.pk})

        response = self.client.post(url, {})
        self.assertEqual(response.status_code, 400)
        response_data = response.json()
        self.assertFalse(response_data['success'])
        self.assertIn('Missing trust_level', response_data['error'])

    def test_update_trust_invalid_source(self):
        """Test trust level update with invalid data source ID."""
        url = reverse('books:update_trust', kwargs={'pk': 99999})

        response = self.client.post(url, {'trust_level': '0.8'})
        self.assertEqual(response.status_code, 404)


@override_settings(CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}})
class ISBNLookupEndpointTests(TestCase):
    """Tests for ISBN lookup endpoint."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.client.login(username='testuser', password='testpass123')

        # Clear cache before each test
        cache.clear()

    @patch('requests.get')
    @patch('django.conf.settings.GOOGLE_BOOKS_API_KEY', 'test_api_key')
    def test_isbn_lookup_success(self, mock_get):
        """Test successful ISBN lookup."""
        # Mock Google Books API response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'items': [{
                'volumeInfo': {
                    'title': 'Test Book',
                    'authors': ['Test Author'],
                    'publisher': 'Test Publisher',
                    'publishedDate': '2023',
                    'pageCount': 200,
                    'description': 'A test book description',
                    'imageLinks': {'thumbnail': 'http://example.com/cover.jpg'}
                }
            }]
        }
        mock_get.return_value = mock_response

        url = reverse('books:isbn_lookup', kwargs={'isbn': '9781234567890'})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        response_data = response.json()
        self.assertTrue(response_data['success'])
        self.assertEqual(response_data['isbn'], '9781234567890')
        self.assertIn('sources', response_data)
        self.assertIn('google_books', response_data['sources'])
        self.assertTrue(response_data['sources']['google_books']['found'])

    @patch('requests.get')
    def test_isbn_lookup_no_results(self, mock_get):
        """Test ISBN lookup with no results."""
        # Mock empty response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'items': []}
        mock_get.return_value = mock_response

        url = reverse('books:isbn_lookup', kwargs={'isbn': '9781234567890'})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        response_data = response.json()
        self.assertTrue(response_data['success'])
        self.assertFalse(response_data['sources']['google_books']['found'])

    def test_isbn_lookup_invalid_isbn(self):
        """Test ISBN lookup with invalid ISBN."""
        # Too short
        url = reverse('books:isbn_lookup', kwargs={'isbn': '123'})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        response_data = response.json()
        self.assertFalse(response_data['success'])
        self.assertIn('Invalid ISBN length', response_data['error'])

        # Too long
        url = reverse('books:isbn_lookup', kwargs={'isbn': '12345678901234567890'})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)  # The view handles it
        response_data = response.json()
        self.assertFalse(response_data['success'])

    @patch('requests.get')
    def test_isbn_lookup_caching(self, mock_get):
        """Test ISBN lookup caching functionality."""
        # Mock successful response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'items': [{
                'volumeInfo': {
                    'title': 'Cached Book',
                    'authors': ['Cache Author']
                }
            }]
        }
        mock_get.return_value = mock_response

        isbn = '9781234567890'
        url = reverse('books:isbn_lookup', kwargs={'isbn': isbn})

        # First request - should call API
        response1 = self.client.get(url)
        self.assertEqual(mock_get.call_count, 2)  # Google Books + Open Library

        # Second request - should use cache
        response2 = self.client.get(url)
        self.assertEqual(mock_get.call_count, 2)  # Should not increase

        # Responses should be identical
        data1 = response1.json()
        data2 = response2.json()
        self.assertEqual(data1, data2)

    @patch('requests.get')
    def test_isbn_lookup_api_error(self, mock_get):
        """Test ISBN lookup when API returns error."""
        # Mock API error
        mock_get.side_effect = Exception("API Error")

        url = reverse('books:isbn_lookup', kwargs={'isbn': '9781234567890'})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        response_data = response.json()
        self.assertTrue(response_data['success'])  # Should still be successful
        self.assertFalse(response_data['sources']['google_books']['found'])
        self.assertIn('error', response_data['sources']['google_books'])


class AIFeedbackEndpointTests(TestCase):
    """Tests for AI feedback-related endpoints."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.client.login(username='testuser', password='testpass123')

        self.scan_folder = ScanFolder.objects.create(
            path="/test/scan/folder",
            name="Test Scan Folder"
        )

        self.book = Book.objects.create(
            file_path="/library/test.epub",
            file_format="epub",
            scan_folder=self.scan_folder
        )

    def test_ajax_submit_ai_feedback_success(self):
        """Test successful AI feedback submission."""
        url = reverse('books:ajax_submit_ai_feedback', kwargs={'book_id': self.book.id})

        data = {
            'corrections': {
                'title': 'Corrected Title',
                'author': 'Corrected Author'
            },
            'rating': 4,
            'comments': 'Good prediction overall',
            'ai_predictions': {
                'title': 'Original AI Title',
                'author': 'Original AI Author'
            },
            'prediction_confidence': 0.85
        }

        response = self.client.post(
            url,
            data=json.dumps(data),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 200)
        response_data = response.json()
        self.assertTrue(response_data['success'])
        self.assertIn('feedback_id', response_data)

        # Verify feedback was created
        feedback = AIFeedback.objects.get(id=response_data['feedback_id'])
        self.assertEqual(feedback.book, self.book)
        self.assertEqual(feedback.user, self.user)
        self.assertEqual(feedback.feedback_rating, 4)

    def test_ajax_submit_ai_feedback_invalid_book(self):
        """Test AI feedback submission with invalid book ID."""
        url = reverse('books:ajax_submit_ai_feedback', kwargs={'book_id': 99999})

        data = {
            'corrections': {},
            'rating': 3
        }

        response = self.client.post(
            url,
            data=json.dumps(data),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 200)
        response_data = response.json()
        self.assertFalse(response_data['success'])

    @patch('books.models.AIFeedback.objects.filter')
    def test_ajax_retrain_ai_models_success(self, mock_filter):
        """Test successful AI model retraining trigger."""
        # Mock sufficient feedback count
        mock_queryset = MagicMock()
        mock_queryset.count.return_value = 10
        mock_filter.return_value = mock_queryset

        url = reverse('books:ajax_retrain_ai_models')

        with patch('threading.Thread') as mock_thread:
            response = self.client.post(url)

            self.assertEqual(response.status_code, 200)
            response_data = response.json()
            self.assertTrue(response_data['success'])
            self.assertEqual(response_data['feedback_count'], 10)

            # Verify thread was started
            mock_thread.assert_called_once()

    @patch('books.models.AIFeedback.objects.filter')
    def test_ajax_retrain_ai_models_insufficient_feedback(self, mock_filter):
        """Test AI model retraining with insufficient feedback."""
        # Mock insufficient feedback count
        mock_queryset = MagicMock()
        mock_queryset.count.return_value = 3
        mock_filter.return_value = mock_queryset

        url = reverse('books:ajax_retrain_ai_models')
        response = self.client.post(url)

        self.assertEqual(response.status_code, 200)
        response_data = response.json()
        self.assertFalse(response_data['success'])
        self.assertIn('Need at least 5 feedback entries', response_data['error'])

    @patch('books.scanner.ai.filename_recognizer.FilenamePatternRecognizer')
    def test_ajax_ai_model_status(self, mock_recognizer_class):
        """Test AI model status endpoint."""
        # Mock recognizer instance
        mock_recognizer = MagicMock()
        mock_recognizer.models_exist.return_value = True
        mock_recognizer.get_training_data_stats.return_value = {
            'total_samples': 1000,
            'accuracy': 0.85
        }
        mock_recognizer_class.return_value = mock_recognizer

        # Create some feedback for statistics
        AIFeedback.objects.create(
            book=self.book,
            user=self.user,
            feedback_rating=4,
            needs_retraining=True
        )

        url = reverse('books:ajax_ai_model_status')
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        response_data = response.json()
        self.assertTrue(response_data['success'])
        self.assertTrue(response_data['models_exist'])
        self.assertIn('training_stats', response_data)
        self.assertIn('feedback_stats', response_data)
        self.assertFalse(response_data['can_retrain'])


class ThemePreviewEndpointTests(TestCase):
    """Tests for theme preview endpoints."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.client.login(username='testuser', password='testpass123')

    def test_preview_theme_success(self):
        """Test successful theme preview."""
        url = reverse('books:preview_theme')

        response = self.client.post(url, {'theme': 'darkly'})

        self.assertEqual(response.status_code, 200)
        response_data = response.json()
        self.assertTrue(response_data['success'])
        self.assertEqual(response_data['theme'], 'darkly')

        # Verify session was updated
        self.assertEqual(self.client.session['preview_theme'], 'darkly')

    def test_preview_theme_invalid_theme(self):
        """Test theme preview with invalid theme."""
        url = reverse('books:preview_theme')

        response = self.client.post(url, {'theme': 'invalid_theme'})

        self.assertEqual(response.status_code, 200)
        response_data = response.json()
        self.assertFalse(response_data['success'])
        self.assertIn('Invalid theme', response_data['error'])

    def test_preview_theme_missing_parameter(self):
        """Test theme preview with missing theme parameter."""
        url = reverse('books:preview_theme')

        response = self.client.post(url, {})

        self.assertEqual(response.status_code, 200)
        response_data = response.json()
        self.assertFalse(response_data['success'])
        self.assertIn('Theme parameter required', response_data['error'])

    def test_clear_theme_preview(self):
        """Test clearing theme preview."""
        # Set a preview theme first
        session = self.client.session
        session['preview_theme'] = 'darkly'
        session.save()

        # Create user profile with default theme
        UserProfile.objects.create(user=self.user, theme='light')

        url = reverse('books:clear_theme_preview')
        response = self.client.post(url)

        self.assertEqual(response.status_code, 200)
        response_data = response.json()
        self.assertTrue(response_data['success'])
        self.assertEqual(response_data['theme'], 'light')

        # Verify preview was cleared from session
        self.assertNotIn('preview_theme', self.client.session)

    def test_clear_theme_preview_no_preview(self):
        """Test clearing theme preview when none exists."""
        UserProfile.objects.create(user=self.user, theme='light')

        url = reverse('books:clear_theme_preview')
        response = self.client.post(url)

        self.assertEqual(response.status_code, 200)
        response_data = response.json()
        self.assertTrue(response_data['success'])
        self.assertEqual(response_data['theme'], 'light')


class AJAXEndpointSecurityTests(TestCase):
    """Security tests for AJAX endpoints."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )

        self.scan_folder = ScanFolder.objects.create(
            path="/test/scan/folder",
            name="Test Scan Folder"
        )

        self.book = Book.objects.create(
            file_path="/library/test.epub",
            file_format="epub",
            scan_folder=self.scan_folder
        )

    def test_ajax_endpoints_require_login(self):
        """Test that AJAX endpoints require authentication."""
        # Don't log in

        urls_and_methods = [
            (reverse('books:ajax_rescan_external_metadata', kwargs={'book_id': self.book.id}), 'post'),
            (reverse('books:ajax_submit_ai_feedback', kwargs={'book_id': self.book.id}), 'post'),
            (reverse('books:ajax_retrain_ai_models'), 'post'),
            (reverse('books:preview_theme'), 'post'),
            (reverse('books:clear_theme_preview'), 'post'),
        ]

        for url, method in urls_and_methods:
            with self.subTest(url=url.replace(str(self.book.id), '<id>'), method=method):
                if method == 'post':
                    response = self.client.post(url)
                else:
                    response = self.client.get(url)

                # Should redirect to login or return 403
                self.assertIn(response.status_code, [302, 401, 403, 405])

    def test_ajax_post_endpoints_reject_get(self):
        """Test that POST-only endpoints reject GET requests."""
        self.client.login(username='testuser', password='testpass123')

        post_only_urls = [
            reverse('books:ajax_retrain_ai_models'),  # This one doesn't take args
            reverse('books:preview_theme'),
            reverse('books:clear_theme_preview'),
        ]

        for url in post_only_urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 405)  # Method Not Allowed

    def test_ajax_endpoints_csrf_protection(self):
        """Test CSRF protection on AJAX endpoints where applicable."""
        self.client.login(username='testuser', password='testpass123')

        # Some endpoints may have CSRF exemption for AJAX calls
        # This test verifies the security configuration. A 403 would indicate CSRF failure.

        url = reverse('books:preview_theme')

        # Test without CSRF token (should work for AJAX endpoints if configured)
        response = self.client.post(url, {'theme': 'darkly'})

        # The actual behavior depends on the CSRF configuration
        # A 200 means it passed, a 403 would be a failure.
        self.assertIn(response.status_code, [200, 403])


class AJAXEndpointPerformanceTests(TestCase):
    """Performance tests for AJAX endpoints."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.client.login(username='testuser', password='testpass123')

        self.scan_folder = ScanFolder.objects.create(
            path="/test/scan/folder",
            name="Test Scan Folder"
        )

        self.book = Book.objects.create(
            file_path="/library/test.epub",
            file_format="epub",
            scan_folder=self.scan_folder
        )

    def test_isbn_lookup_timeout_handling(self):
        """Test ISBN lookup handles API timeouts gracefully."""
        import requests
        with patch('requests.get') as mock_get:
            # Mock timeout
            mock_get.side_effect = requests.exceptions.Timeout("Request timeout")

            url = reverse('books:isbn_lookup', kwargs={'isbn': '9781234567890'})

            import time
            start_time = time.time()
            response = self.client.get(url)
            end_time = time.time()

            # Should not hang and should complete quickly
            self.assertLess(end_time - start_time, 3.0)  # Allow a bit more time for exception handling
            self.assertEqual(response.status_code, 200)

    def test_ajax_endpoints_response_time(self):
        """Test that AJAX endpoints respond within reasonable time."""
        endpoints = [
            reverse('books:preview_theme'),
            reverse('books:clear_theme_preview')
        ]

        for url in endpoints:
            with self.subTest(url=url.replace(str(self.book.id), '<id>')):
                import time
                start_time = time.time()

                response = self.client.post(url, {'theme': 'flatly'})

                end_time = time.time()
                response_time = end_time - start_time

                # Should respond within 1 second
                self.assertLess(response_time, 1.0)
                self.assertEqual(response.status_code, 200)


class AJAXEndpointIntegrationTests(TestCase):
    """Integration tests for AJAX endpoints working together."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.client.login(username='testuser', password='testpass123')

        self.scan_folder = ScanFolder.objects.create(
            path="/test/scan/folder",
            name="Test Scan Folder"
        )

    def test_metadata_workflow(self):
        """Test complete metadata workflow through AJAX endpoints."""
        # Create book
        book = Book.objects.create(
            file_path="/library/test.epub",
            file_format="epub",
            scan_folder=self.scan_folder
        )

        # Create data source
        source, _ = DataSource.objects.get_or_create(
            name="test_source", defaults={'trust_level': 0.7}
        )

        # 1. Update trust level
        trust_url = reverse('books:update_trust', kwargs={'pk': source.id})
        response = self.client.post(trust_url, {'trust_level': '0.9'})
        self.assertEqual(response.status_code, 200)

        # 2. Trigger metadata rescan (mocked)
        rescan_url = reverse('books:rescan_external_metadata', kwargs={'book_id': book.id})

        with patch('books.views.rescan_external_metadata') as mock_rescan:
            mock_rescan.return_value = JsonResponse({'success': True})

            response = self.client.post(
                rescan_url,
                data=json.dumps({'sources': ['test_source'], 'options': {}}),
                content_type='application/json'
            )
            self.assertEqual(response.status_code, 200)

    def test_theme_workflow(self):
        """Test complete theme workflow through AJAX endpoints."""
        # Create user profile
        UserProfile.objects.create(user=self.user, theme='light')

        # 1. Preview dark theme
        preview_url = reverse('books:preview_theme')
        response = self.client.post(preview_url, {'theme': 'darkly'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.session['preview_theme'], 'darkly')

        # 2. Clear preview
        clear_url = reverse('books:clear_theme_preview')
        response = self.client.post(clear_url)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('preview_theme', self.client.session)

        # 3. Preview another theme
        response = self.client.post(preview_url, {'theme': 'cerulean'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.session['preview_theme'], 'cerulean')
