"""
Working test suite for AI-driven filename pattern recognition system.
"""

import unittest

from django.contrib.auth.models import User
from django.test import TestCase

from books.models import AIFeedback
from books.scanner.ai.filename_recognizer import FilenamePatternRecognizer
from books.tests.test_helpers import create_test_book_with_file, create_test_scan_folder


class WorkingAITests(TestCase):
    """Test core AI functionality that actually works."""

    def test_ai_system_initialization(self):
        """Test that AI system can be imported and initialized."""
        recognizer = FilenamePatternRecognizer()
        self.assertIsNotNone(recognizer)
        self.assertIsNotNone(recognizer.model_dir)

    def test_feature_extraction(self):
        """Test feature extraction on a sample filename."""
        recognizer = FilenamePatternRecognizer()

        filename = "Brandon Sanderson - Mistborn 01 - The Final Empire.epub"
        features = recognizer._extract_features(filename)

        self.assertIsInstance(features, dict)
        self.assertIn('filename_length', features)
        self.assertIn('word_count', features)
        self.assertTrue(features['has_numbers'])

    def test_filename_cleaning(self):
        """Test filename cleaning functionality."""
        recognizer = FilenamePatternRecognizer()

        dirty_filename = "Test File (2023) [EPUB].epub"
        cleaned = recognizer._clean_filename(dirty_filename)

        self.assertIsInstance(cleaned, str)
        self.assertGreater(len(cleaned), 0)

    def test_confidence_evaluation(self):
        """Test prediction confidence evaluation."""
        recognizer = FilenamePatternRecognizer()

        # High confidence predictions
        high_conf = {
            'title': ('Great Title', 0.9),
            'author': ('Famous Author', 0.8),
            'series': ('Best Series', 0.85),
            'volume': ('1', 0.7)
        }
        self.assertTrue(recognizer.is_prediction_confident(high_conf))

        # Low confidence predictions
        low_conf = {
            'title': ('Maybe Title', 0.3),
            'author': ('Unknown Author', 0.2),
            'series': ('', 0.1),
            'volume': ('', 0.1)
        }
        self.assertFalse(recognizer.is_prediction_confident(low_conf))


class AIFeedbackTests(TestCase):
    """Test AI feedback model functionality."""

    def setUp(self):
        self.user = User.objects.create_user('testuser', 'test@example.com', 'password')
        scan_folder = create_test_scan_folder()
        self.book = create_test_book_with_file(
            file_path='/test/test_book.epub',
            scan_folder=scan_folder
        )

    def test_feedback_creation(self):
        """Test creating feedback entries."""
        feedback = AIFeedback.objects.create(
            book=self.book,
            user=self.user,
            original_filename='test_book.epub',
            ai_predictions='{"title": "AI Title"}',
            user_corrections='{"title": "Real Title"}',
            feedback_rating=4
        )

        self.assertEqual(feedback.feedback_rating, 4)
        self.assertTrue(feedback.needs_retraining)

    def test_feedback_accuracy_scores(self):
        """Test accuracy score calculation."""
        ratings_and_scores = [
            (1, 0.0),   # Poor
            (3, 0.5),   # Good
            (5, 1.0)    # Excellent
        ]

        # Create different users to avoid unique constraint violation
        for i, (rating, expected_score) in enumerate(ratings_and_scores):
            user = User.objects.create_user(f'testuser{i}', f'test{i}@example.com', 'password')
            feedback = AIFeedback.objects.create(
                book=self.book,
                user=user,
                original_filename='test.epub',
                ai_predictions='{}',
                user_corrections='{}',
                feedback_rating=rating
            )
            self.assertEqual(feedback.get_accuracy_score(), expected_score)


if __name__ == '__main__':
    unittest.main()
