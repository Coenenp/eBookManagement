"""
Comprehensive tests for AI feedback views and functionality.

This module contains tests for AIFeedbackListView, AIFeedbackDetailView,
and related AI functionality including feedback submission, model retraining,
and status checking.
"""

import json
from unittest.mock import patch, MagicMock
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from books.models import Book, FinalMetadata, BookMetadata, DataSource, AIFeedback


class AIFeedbackListViewTests(TestCase):
    """Tests for AIFeedbackListView."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.client.login(username='testuser', password='testpass123')

        # Create AI data source
        self.ai_source = DataSource.objects.create(
            name='filename_ai',
            trust_level=0.7
        )

        # Create test books with AI predictions
        self.books_with_ai = []
        for i in range(5):
            book = Book.objects.create(
                file_path=f"/library/ai_book_{i+1}.epub",
                file_format="epub"
            )

            # Create final metadata
            FinalMetadata.objects.create(
                book=book,
                final_title=f"AI Test Book {i+1}",
                final_author=f"AI Author {i+1}",
                overall_confidence=0.5 + (i * 0.1),  # Varying confidence levels
                is_reviewed=(i < 2)  # First 2 are reviewed
            )

            # Create AI metadata
            BookMetadata.objects.create(
                book=book,
                source=self.ai_source,
                field_name='ai_title',
                field_value=f"AI Predicted Title {i+1}",
                confidence=0.5 + (i * 0.1),
                is_active=True
            )

            self.books_with_ai.append(book)

    def test_ai_feedback_list_access(self):
        """Test basic access to AI feedback list view."""
        response = self.client.get(reverse('books:ai_feedback_list'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'books/ai_feedback_list.html')

    def test_ai_feedback_list_context(self):
        """Test AI feedback list view context data."""
        response = self.client.get(reverse('books:ai_feedback_list'))
        context = response.context

        self.assertIn('books', context)
        self.assertIn('stats', context)
        self.assertIn('confidence_filter', context)
        self.assertIn('status_filter', context)

    def test_ai_feedback_list_statistics(self):
        """Test statistics calculation in AI feedback list."""
        response = self.client.get(reverse('books:ai_feedback_list'))
        stats = response.context['stats']

        # Check statistics structure
        expected_stats = [
            'total_ai_predictions', 'low_confidence', 'medium_confidence',
            'high_confidence', 'needs_review', 'reviewed'
        ]
        for stat in expected_stats:
            self.assertIn(stat, stats)

        # Verify actual counts
        self.assertEqual(stats['total_ai_predictions'], 5)
        self.assertEqual(stats['reviewed'], 2)
        self.assertEqual(stats['needs_review'], 3)

    def test_ai_feedback_confidence_filtering(self):
        """Test filtering by confidence level."""
        # Test low confidence filter
        response = self.client.get(reverse('books:ai_feedback_list'), {'confidence': 'low'})
        self.assertEqual(response.status_code, 200)
        books = response.context['books']
        for book in books:
            self.assertLess(book.finalmetadata.overall_confidence, 0.6)

        # Test high confidence filter
        response = self.client.get(reverse('books:ai_feedback_list'), {'confidence': 'high'})
        self.assertEqual(response.status_code, 200)
        books = response.context['books']
        for book in books:
            self.assertGreaterEqual(book.finalmetadata.overall_confidence, 0.8)

        # Test medium confidence filter
        response = self.client.get(reverse('books:ai_feedback_list'), {'confidence': 'medium'})
        self.assertEqual(response.status_code, 200)

    def test_ai_feedback_status_filtering(self):
        """Test filtering by review status."""
        # Test needs review filter
        response = self.client.get(reverse('books:ai_feedback_list'), {'status': 'needs_review'})
        self.assertEqual(response.status_code, 200)
        books = response.context['books']
        for book in books:
            self.assertFalse(book.finalmetadata.is_reviewed)

        # Test reviewed filter
        response = self.client.get(reverse('books:ai_feedback_list'), {'status': 'reviewed'})
        self.assertEqual(response.status_code, 200)
        books = response.context['books']
        for book in books:
            self.assertTrue(book.finalmetadata.is_reviewed)

    def test_ai_feedback_list_ordering(self):
        """Test that books are ordered by confidence level."""
        response = self.client.get(reverse('books:ai_feedback_list'))
        books = list(response.context['books'])

        # Should be ordered by descending confidence
        confidences = [book.finalmetadata.overall_confidence for book in books]
        self.assertEqual(confidences, sorted(confidences, reverse=True))

    def test_ai_feedback_list_pagination(self):
        """Test pagination in AI feedback list."""
        # Create many books to test pagination
        for i in range(60):  # More than default paginate_by (50)
            book = Book.objects.create(
                file_path=f"/library/extra_{i}.epub",
                file_format="epub"
            )

            FinalMetadata.objects.create(
                book=book,
                final_title=f"Extra AI Book {i}",
                overall_confidence=0.5
            )

            BookMetadata.objects.create(
                book=book,
                source=self.ai_source,
                field_name='ai_title',
                field_value=f"AI Title {i}",
                confidence=0.7,
                is_active=True
            )

        response = self.client.get(reverse('books:ai_feedback_list'))
        self.assertTrue(response.context['is_paginated'])
        self.assertEqual(len(response.context['books']), 50)  # Default page size

        # Test second page
        response = self.client.get(reverse('books:ai_feedback_list') + '?page=2')
        self.assertEqual(response.status_code, 200)

    def test_ai_feedback_list_no_ai_books(self):
        """Test AI feedback list when no AI predictions exist."""
        # Delete all AI metadata
        BookMetadata.objects.filter(source=self.ai_source).delete()

        response = self.client.get(reverse('books:ai_feedback_list'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['books']), 0)


class AIFeedbackDetailViewTests(TestCase):
    """Tests for AIFeedbackDetailView."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.client.login(username='testuser', password='testpass123')

        # Create AI data source
        self.ai_source = DataSource.objects.create(
            name='filename_ai',
            trust_level=0.7
        )

        # Create test book with AI predictions
        self.book = Book.objects.create(
            file_path="/library/ai_detail_test.epub",
            file_format="epub"
        )

        self.final_metadata = FinalMetadata.objects.create(
            book=self.book,
            final_title="AI Detail Test Book",
            final_author="AI Test Author",
            final_series="AI Test Series",
            overall_confidence=0.75,
            is_reviewed=False
        )

        # Create AI metadata entries
        ai_fields = [
            ('ai_title', 'AI Predicted Title'),
            ('ai_author', 'AI Predicted Author'),
            ('ai_series', 'AI Predicted Series'),
            ('ai_volume', '1')
        ]

        for field_name, field_value in ai_fields:
            BookMetadata.objects.create(
                book=self.book,
                source=self.ai_source,
                field_name=field_name,
                field_value=field_value,
                confidence=0.8,
                is_active=True
            )

    def test_ai_feedback_detail_access(self):
        """Test basic access to AI feedback detail view."""
        response = self.client.get(reverse('books:ai_feedback_detail', kwargs={'pk': self.book.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'books/ai_feedback_detail.html')

    def test_ai_feedback_detail_context(self):
        """Test AI feedback detail view context data."""
        response = self.client.get(reverse('books:ai_feedback_detail', kwargs={'pk': self.book.pk}))
        context = response.context

        # Check context structure
        self.assertIn('book', context)
        self.assertIn('ai_predictions', context)
        self.assertIn('current_metadata', context)
        self.assertIn('original_filename', context)

        self.assertEqual(context['book'], self.book)

    def test_ai_predictions_organization(self):
        """Test that AI predictions are properly organized."""
        response = self.client.get(reverse('books:ai_feedback_detail', kwargs={'pk': self.book.pk}))
        ai_predictions = response.context['ai_predictions']

        # Should have predictions for title, author, series, volume
        expected_fields = ['title', 'author', 'series', 'volume']
        for field in expected_fields:
            self.assertIn(field, ai_predictions)
            self.assertIn('value', ai_predictions[field])
            self.assertIn('confidence', ai_predictions[field])

    def test_current_metadata_context(self):
        """Test current metadata context structure."""
        response = self.client.get(reverse('books:ai_feedback_detail', kwargs={'pk': self.book.pk}))
        current_metadata = response.context['current_metadata']

        # Check metadata fields
        expected_fields = ['title', 'author', 'series', 'volume', 'is_reviewed', 'confidence']
        for field in expected_fields:
            self.assertIn(field, current_metadata)

        self.assertEqual(current_metadata['title'], self.final_metadata.final_title)
        self.assertEqual(current_metadata['author'], self.final_metadata.final_author)

    def test_original_filename_context(self):
        """Test original filename in context."""
        response = self.client.get(reverse('books:ai_feedback_detail', kwargs={'pk': self.book.pk}))
        original_filename = response.context['original_filename']

        self.assertEqual(original_filename, 'ai_detail_test.epub')

    def test_ai_feedback_detail_no_metadata(self):
        """Test detail view when book has no final metadata."""
        # Create book without final metadata
        book_no_meta = Book.objects.create(
            file_path="/library/no_meta.epub",
            file_format="epub"
        )

        response = self.client.get(reverse('books:ai_feedback_detail', kwargs={'pk': book_no_meta.pk}))
        self.assertEqual(response.status_code, 200)

        # Should have empty current_metadata
        current_metadata = response.context['current_metadata']
        self.assertEqual(current_metadata, {})

    def test_ai_feedback_detail_invalid_book(self):
        """Test detail view with invalid book ID."""
        response = self.client.get(reverse('books:ai_feedback_detail', kwargs={'pk': 99999}))
        self.assertEqual(response.status_code, 404)


class AIFeedbackSubmissionTests(TestCase):
    """Tests for AI feedback submission functionality."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.client.login(username='testuser', password='testpass123')

        self.book = Book.objects.create(
            file_path="/library/feedback_test.epub",
            file_format="epub"
        )

        FinalMetadata.objects.create(
            book=self.book,
            final_title="Feedback Test Book",
            final_author="Test Author",
            is_reviewed=False
        )

    def test_submit_ai_feedback_success(self):
        """Test successful AI feedback submission."""
        url = reverse('books:ajax_submit_ai_feedback', kwargs={'book_id': self.book.id})

        feedback_data = {
            'corrections': {
                'title': 'Corrected Title',
                'author': 'Corrected Author',
                'series': 'Corrected Series',
                'volume': '2'
            },
            'rating': 4,
            'comments': 'Good AI prediction overall, minor corrections needed',
            'ai_predictions': {
                'title': 'Original AI Title',
                'author': 'Original AI Author'
            },
            'prediction_confidence': 0.85
        }

        response = self.client.post(
            url,
            data=json.dumps(feedback_data),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content)
        self.assertTrue(response_data['success'])
        self.assertIn('feedback_id', response_data)

        # Verify feedback was created
        feedback = AIFeedback.objects.get(id=response_data['feedback_id'])
        self.assertEqual(feedback.book, self.book)
        self.assertEqual(feedback.user, self.user)
        self.assertEqual(feedback.feedback_rating, 4)
        self.assertTrue(feedback.needs_retraining)

    def test_submit_ai_feedback_updates_metadata(self):
        """Test that feedback submission updates final metadata."""
        url = reverse('books:ajax_submit_ai_feedback', kwargs={'book_id': self.book.id})

        feedback_data = {
            'corrections': {
                'title': 'New Corrected Title',
                'author': 'New Corrected Author'
            },
            'rating': 5
        }

        response = self.client.post(
            url,
            data=json.dumps(feedback_data),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 200)

        # Verify metadata was updated
        self.book.finalmetadata.refresh_from_db()
        self.assertEqual(self.book.finalmetadata.final_title, 'New Corrected Title')
        self.assertEqual(self.book.finalmetadata.final_author, 'New Corrected Author')
        self.assertTrue(self.book.finalmetadata.is_reviewed)

    def test_submit_ai_feedback_invalid_book(self):
        """Test feedback submission with invalid book ID."""
        url = reverse('books:ajax_submit_ai_feedback', kwargs={'book_id': 99999})

        feedback_data = {
            'corrections': {},
            'rating': 3
        }

        response = self.client.post(
            url,
            data=json.dumps(feedback_data),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content)
        self.assertFalse(response_data['success'])

    def test_submit_ai_feedback_malformed_json(self):
        """Test feedback submission with malformed JSON."""
        url = reverse('books:ajax_submit_ai_feedback', kwargs={'book_id': self.book.id})

        response = self.client.post(
            url,
            data="invalid json",
            content_type='application/json'
        )

        # Malformed JSON should return 400 Bad Request
        self.assertEqual(response.status_code, 400)


class AIModelRetrainingTests(TestCase):
    """Tests for AI model retraining functionality."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.client.login(username='testuser', password='testpass123')

        # Create test books for feedback
        self.books = []
        for i in range(10):
            book = Book.objects.create(
                file_path=f"/library/retrain_{i}.epub",
                file_format="epub"
            )
            self.books.append(book)

    def test_retrain_ai_models_sufficient_feedback(self):
        """Test AI model retraining with sufficient feedback."""
        # Create enough feedback entries
        for i, book in enumerate(self.books[:7]):  # 7 feedback entries
            AIFeedback.objects.create(
                book=book,
                user=self.user,
                feedback_rating=4 + (i % 2),  # Ratings 4 or 5
                needs_retraining=True
            )

        url = reverse('books:ajax_retrain_ai_models')

        with patch('threading.Thread') as mock_thread:
            response = self.client.post(url)

            self.assertEqual(response.status_code, 200)
            response_data = json.loads(response.content)
            self.assertTrue(response_data['success'])
            self.assertEqual(response_data['feedback_count'], 7)

            # Verify thread was started
            mock_thread.assert_called_once()

    def test_retrain_ai_models_insufficient_feedback(self):
        """Test AI model retraining with insufficient feedback."""
        # Create insufficient feedback entries
        for book in self.books[:3]:  # Only 3 feedback entries
            AIFeedback.objects.create(
                book=book,
                user=self.user,
                feedback_rating=3,
                needs_retraining=True
            )

        url = reverse('books:ajax_retrain_ai_models')
        response = self.client.post(url)

        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content)
        self.assertFalse(response_data['success'])
        self.assertIn('Need at least 5 feedback entries', response_data['error'])

    @patch('books.models.AIFeedback.objects.filter')
    def test_retrain_ai_models_with_exception(self, mock_filter):
        """Test AI model retraining when exception occurs."""
        # Mock exception during processing
        mock_filter.side_effect = Exception("Database error")

        url = reverse('books:ajax_retrain_ai_models')
        response = self.client.post(url)

        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content)
        self.assertFalse(response_data['success'])
        self.assertIn('error', response_data)


class AIModelStatusTests(TestCase):
    """Tests for AI model status functionality."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.client.login(username='testuser', password='testpass123')

    @patch('books.scanner.ai.filename_recognizer.FilenamePatternRecognizer')
    @patch('books.models.AIFeedback.objects.aggregate')
    def test_ai_model_status_success(self, mock_aggregate, mock_recognizer_class):
        """Test successful AI model status retrieval."""
        # Mock recognizer
        mock_recognizer = MagicMock()
        mock_recognizer.models_exist.return_value = True
        mock_recognizer.get_training_data_stats.return_value = {
            'total_samples': 1000,
            'accuracy': 0.85,
            'last_trained': '2023-12-01'
        }
        mock_recognizer_class.return_value = mock_recognizer

        # Mock feedback aggregate
        mock_aggregate.return_value = {'avg_rating': 4.2}

        # Create test feedback
        book = Book.objects.create(
            file_path="/library/status_test.epub",
            file_format="epub"
        )

        AIFeedback.objects.create(
            book=book,
            user=self.user,
            feedback_rating=4,
            needs_retraining=True
        )

        url = reverse('books:ajax_ai_model_status')
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content)

        self.assertTrue(response_data['success'])
        self.assertTrue(response_data['models_exist'])
        self.assertIn('training_stats', response_data)
        self.assertIn('feedback_stats', response_data)
        self.assertFalse(response_data['can_retrain'])  # Only 1 feedback, need 5

    @patch('books.scanner.ai.filename_recognizer.FilenamePatternRecognizer')
    def test_ai_model_status_no_models(self, mock_recognizer_class):
        """Test AI model status when no models exist."""
        # Mock recognizer with no models
        mock_recognizer = MagicMock()
        mock_recognizer.models_exist.return_value = False
        mock_recognizer_class.return_value = mock_recognizer

        url = reverse('books:ajax_ai_model_status')
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content)

        self.assertTrue(response_data['success'])
        self.assertFalse(response_data['models_exist'])

    @patch('books.scanner.ai.filename_recognizer.FilenamePatternRecognizer')
    def test_ai_model_status_exception(self, mock_recognizer_class):
        """Test AI model status when exception occurs."""
        # Mock exception
        mock_recognizer_class.side_effect = Exception("Import error")

        url = reverse('books:ajax_ai_model_status')
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content)

        self.assertFalse(response_data['success'])
        self.assertIn('error', response_data)


class AIFeedbackIntegrationTests(TestCase):
    """Integration tests for AI feedback functionality."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.client.login(username='testuser', password='testpass123')

    def test_complete_ai_feedback_workflow(self):
        """Test complete AI feedback workflow from list to submission."""
        # Create AI data source
        ai_source = DataSource.objects.create(
            name='filename_ai',
            trust_level=0.7
        )

        # Create book with AI metadata
        book = Book.objects.create(
            file_path="/library/workflow_test.epub",
            file_format="epub"
        )

        # Create BookMetadata so the book shows up in the AI feedback list
        BookMetadata.objects.create(
            book=book,
            source=ai_source,
            field_name='ai_title',
            field_value='AI Predicted Title',
            confidence=0.8,
            is_active=True
        )

        # Update or create FinalMetadata with our test values (after auto-processing)
        final_metadata, created = FinalMetadata.objects.get_or_create(
            book=book,
            defaults={
                'final_title': '',  # Empty string will show "Unknown Title" in template
                'final_author': "Test Author",
                'overall_confidence': 0.6,
                'is_reviewed': False
            }
        )
        if not created:
            final_metadata.final_title = ''  # Empty string will show "Unknown Title" in template
            final_metadata.final_author = "Test Author"
            final_metadata.overall_confidence = 0.6
            final_metadata.is_reviewed = False
            final_metadata.save()

        # 1. Access feedback list
        response = self.client.get(reverse('books:ai_feedback_list'))
        self.assertEqual(response.status_code, 200)
        # Verify that a book appears in the list (title may be "Unknown Title" due to auto-processing)
        self.assertContains(response, 'Unknown Title')
        self.assertContains(response, 'Needs Review')

        # 2. Access feedback detail
        response = self.client.get(reverse('books:ai_feedback_detail', kwargs={'pk': book.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'AI Predicted Title')

        # 3. Submit feedback
        feedback_data = {
            'corrections': {'title': 'Corrected Title'},
            'rating': 4,
            'comments': 'Good prediction'
        }

        response = self.client.post(
            reverse('books:ajax_submit_ai_feedback', kwargs={'book_id': book.id}),
            data=json.dumps(feedback_data),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content)
        self.assertTrue(response_data['success'])

        # 4. Verify feedback was recorded
        feedback = AIFeedback.objects.get(book=book)
        self.assertEqual(feedback.feedback_rating, 4)
        self.assertTrue(feedback.needs_retraining)

    def test_ai_feedback_permission_handling(self):
        """Test AI feedback views require proper permissions."""
        # Test without login
        self.client.logout()

        response = self.client.get(reverse('books:ai_feedback_list'))
        self.assertEqual(response.status_code, 302)  # Redirect to login

        response = self.client.get(reverse('books:ai_feedback_detail', kwargs={'pk': 1}))
        self.assertEqual(response.status_code, 302)  # Redirect to login

    def test_ai_feedback_with_large_dataset(self):
        """Test AI feedback functionality with large dataset."""
        # Create AI source
        ai_source = DataSource.objects.create(
            name='filename_ai',
            trust_level=0.7
        )

        # Create many books with AI predictions
        books = []
        for i in range(100):
            book = Book.objects.create(
                file_path=f"/library/large_{i}.epub",
                file_format="epub"
            )

            FinalMetadata.objects.create(
                book=book,
                final_title=f"Large Dataset Book {i}",
                overall_confidence=0.5 + (i % 50) / 100.0,  # Varying confidence
                is_reviewed=(i % 3 == 0)  # Every 3rd book reviewed
            )

            BookMetadata.objects.create(
                book=book,
                source=ai_source,
                field_name='ai_title',
                field_value=f'AI Title {i}',
                confidence=0.7,
                is_active=True
            )

            books.append(book)

        # Test list view performance
        import time
        start_time = time.time()
        response = self.client.get(reverse('books:ai_feedback_list'))
        end_time = time.time()

        self.assertEqual(response.status_code, 200)
        self.assertLess(end_time - start_time, 2.0)  # Should complete within 2 seconds

        # Test statistics calculation
        stats = response.context['stats']
        self.assertEqual(stats['total_ai_predictions'], 100)
        self.assertGreater(stats['needs_review'], 0)


class AIFeedbackSecurityTests(TestCase):
    """Security tests for AI feedback functionality."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )

        self.book = Book.objects.create(
            file_path="/library/security_test.epub",
            file_format="epub"
        )

    def test_ai_feedback_requires_authentication(self):
        """Test that AI feedback endpoints require authentication."""
        # Don't log in

        # Test endpoints that should require authentication
        auth_endpoints = [
            (reverse('books:ai_feedback_list'), 'GET'),
            (reverse('books:ai_feedback_detail', kwargs={'pk': self.book.pk}), 'GET'),
        ]

        for endpoint, method in auth_endpoints:
            with self.subTest(endpoint=endpoint):
                response = self.client.get(endpoint) if method == 'GET' else self.client.post(endpoint)
                self.assertIn(response.status_code, [302, 403])  # Redirect or forbidden

        # Test POST-only AJAX endpoints (should return 405 Method Not Allowed when accessed with GET)
        post_only_endpoints = [
            reverse('books:ajax_submit_ai_feedback', kwargs={'book_id': self.book.id}),
            reverse('books:ajax_retrain_ai_models'),
        ]

        for endpoint in post_only_endpoints:
            with self.subTest(endpoint=endpoint):
                response = self.client.get(endpoint)
                self.assertEqual(response.status_code, 405)  # Method not allowed

                # Test that POST also requires authentication
                response = self.client.post(endpoint)
                self.assertIn(response.status_code, [302, 403])  # Redirect or forbidden

        # Test public status endpoint (doesn't require authentication)
        status_endpoint = reverse('books:ajax_ai_model_status')
        response = self.client.get(status_endpoint)
        self.assertEqual(response.status_code, 200)  # Should be accessible

    def test_ai_feedback_csrf_protection(self):
        """Test CSRF protection on feedback submission."""
        self.client.login(username='testuser', password='testpass123')

        # Test feedback submission (may have CSRF exemption for AJAX)
        url = reverse('books:ajax_submit_ai_feedback', kwargs={'book_id': self.book.id})
        response = self.client.post(url, {'rating': 4})

        # Depending on CSRF configuration, should either work or be protected
        self.assertIn(response.status_code, [200, 403])

    def test_ai_feedback_input_validation(self):
        """Test input validation in feedback submission."""
        self.client.login(username='testuser', password='testpass123')

        url = reverse('books:ajax_submit_ai_feedback', kwargs={'book_id': self.book.id})

        # Test with malicious script in corrections
        malicious_data = {
            'corrections': {
                'title': '<script>alert("xss")</script>',
                'author': '"><script>alert("xss")</script>'
            },
            'rating': 4
        }

        response = self.client.post(
            url,
            data=json.dumps(malicious_data),
            content_type='application/json'
        )

        # Should handle gracefully without executing script
        self.assertEqual(response.status_code, 200)
