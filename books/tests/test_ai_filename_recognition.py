"""
Test suite for AI-driven filename pattern recognition system.

This module tests the complete AI functionality including:
- Filename pattern recognition and metadata extraction
- Model training and prediction
- User feedback collection and processing
- Confidence scoring and validation
- Integration with scanner system
"""

import json
import shutil
import tempfile
import unittest
from unittest.mock import Mock, patch

from django.contrib.auth.models import User
from django.http import JsonResponse
from django.test import RequestFactory, TestCase

from books.management.commands.train_ai_models import Command as TrainCommand
from books.models import AIFeedback, DataSource, FinalMetadata, ScanFolder
from books.scanner.ai.filename_recognizer import FilenamePatternRecognizer
from books.tests.test_helpers import create_test_book_with_file
from books.views import AIFeedbackListView, ajax_ai_model_status, ajax_retrain_ai_models, ajax_submit_ai_feedback


class FilenamePatternRecognizerTests(TestCase):
    """Test the core AI filename recognition functionality."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.recognizer = FilenamePatternRecognizer()
        # Override model directory for testing
        from pathlib import Path

        self.recognizer.model_dir = Path(self.temp_dir)
        # Update model paths with new directory
        self.recognizer.model_paths = {
            "title": Path(self.temp_dir) / "title_classifier.pkl",
            "author": Path(self.temp_dir) / "author_classifier.pkl",
            "series": Path(self.temp_dir) / "series_classifier.pkl",
            "volume": Path(self.temp_dir) / "volume_classifier.pkl",
            "vectorizer": Path(self.temp_dir) / "filename_vectorizer.pkl",
            "metadata": Path(self.temp_dir) / "model_metadata.json",
        }

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_feature_extraction(self):
        """Test filename feature extraction."""
        filename = "Brandon Sanderson - Mistborn 01 - The Final Empire.epub"
        features = self.recognizer._extract_features(filename)

        self.assertIsInstance(features, dict)
        self.assertIn("filename_length", features)
        self.assertIn("word_count", features)
        self.assertIn("has_numbers", features)
        self.assertIn("dash_count", features)
        self.assertEqual(features["has_numbers"], True)
        self.assertGreater(features["dash_count"], 0)

    def test_text_preprocessing(self):
        """Test text preprocessing for ML models."""
        filename = "Brandon Sanderson - Mistborn #01 - The Final Empire (2006).epub"
        processed = self.recognizer._clean_filename(filename)

        self.assertIsInstance(processed, str)
        self.assertNotIn("(", processed)  # Parentheses content should be removed
        self.assertNotIn(")", processed)
        self.assertNotIn("epub", processed.lower())  # File extensions should be removed

    def test_volume_extraction(self):
        """Test volume number detection from text."""
        test_cases = [
            ("Book 01", True),
            ("Volume 2", True),
            ("Part III", False),  # roman numerals not detected
            ("Something vol 04 Title", True),  # vol with word boundary
            ("Book 10 of 12", True),
            ("No volume here", False),
        ]

        for text, expected in test_cases:
            with self.subTest(text=text):
                features = self.recognizer._extract_features(text)
                result = features["has_volume_indicator"]
                self.assertEqual(result, expected)

    def test_training_data_collection(self):
        """Test collection of training data from reviewed books."""
        # Create test data
        User.objects.create_user("testuser", "test@example.com", "password")
        DataSource.objects.create(name="test_source")

        # Create a temporary directory for scan folder
        import tempfile

        test_dir = tempfile.mkdtemp()
        try:
            scan_folder = ScanFolder.objects.create(path=test_dir, is_active=True)

            book = create_test_book_with_file(
                file_path="/test/path/Brandon Sanderson - Mistborn 01 - The Final Empire.epub",
                title="The Final Empire",
                content_type="ebook",
                scan_folder=scan_folder,
                file_format="epub",
                file_size=1024000,
            )

            FinalMetadata.objects.create(
                book=book, final_title="The Final Empire", final_author="Brandon Sanderson", final_series="Mistborn", final_series_number="1", is_reviewed=True
            )

            # Test data collection
            training_data = self.recognizer.collect_training_data()

            self.assertEqual(len(training_data), 1)
            sample = training_data.iloc[0]  # Use iloc for DataFrame indexing
            self.assertEqual(sample["title"], "The Final Empire")
            self.assertEqual(sample["author"], "Brandon Sanderson")
            self.assertEqual(sample["series"], "Mistborn")
            self.assertEqual(sample["volume"], "1")
        finally:
            # Clean up temporary directory
            import shutil

            shutil.rmtree(test_dir, ignore_errors=True)

    def test_model_persistence(self):
        """Test model saving and loading."""
        import pickle

        # Create simple dummy objects that can be pickled
        mock_vectorizer = {"test": "vectorizer"}
        mock_model = {"test": "model"}

        # Save mock files to temp directory
        with open(self.recognizer.model_paths["vectorizer"], "wb") as f:
            pickle.dump(mock_vectorizer, f)

        for field in ["title", "author", "series", "volume"]:
            with open(self.recognizer.model_paths[field], "wb") as f:
                pickle.dump(mock_model, f)

        # Test model loading
        result = self.recognizer.load_models()
        self.assertTrue(result)

        # Verify models were loaded
        self.assertIsNotNone(self.recognizer.vectorizer)
        self.assertIsNotNone(self.recognizer.title_model)
        self.assertIsNotNone(self.recognizer.author_model)

    def test_confidence_threshold(self):
        """Test confidence-based prediction validation."""
        # Test high confidence predictions
        predictions = {"title": ("Test Title", 0.95), "author": ("Test Author", 0.90), "series": ("Test Series", 0.85), "volume": ("1", 0.80)}
        self.assertTrue(self.recognizer.is_prediction_confident(predictions))

        # Test low confidence predictions
        predictions_low = {"title": ("Test Title", 0.40), "author": ("Test Author", 0.30), "series": ("Test Series", 0.20), "volume": ("1", 0.10)}
        self.assertFalse(self.recognizer.is_prediction_confident(predictions_low))


class AIManagementCommandTests(TestCase):
    """Test the AI training management command."""

    def setUp(self):
        self.command = TrainCommand()

    def test_command_arguments(self):
        """Test that command accepts all required arguments."""
        parser = self.command.create_parser("test", "train_ai_models")

        # Test that all arguments are properly configured
        args = parser.parse_args(["--action", "status"])
        self.assertEqual(args.action, "status")

        args = parser.parse_args(["--action", "train", "--min-samples", "5"])
        self.assertEqual(args.action, "train")
        self.assertEqual(args.min_samples, 5)

    @patch("books.management.commands.train_ai_models.FilenamePatternRecognizer")
    def test_status_command(self, mock_recognizer):
        """Test the status command functionality."""
        # Mock recognizer behavior
        mock_instance = Mock()
        mock_instance.models_exist.return_value = True
        mock_instance.model_paths = {
            "title": Mock(exists=Mock(return_value=True)),
            "author": Mock(exists=Mock(return_value=True)),
            "series": Mock(exists=Mock(return_value=False)),
            "volume": Mock(exists=Mock(return_value=False)),
            "metadata": Mock(exists=Mock(return_value=False)),
        }
        mock_recognizer.return_value = mock_instance

        # Capture command output using StringIO for Django management commands
        from io import StringIO

        captured_output = StringIO()

        # Mock the command's stdout
        original_stdout = self.command.stdout
        self.command.stdout.write = captured_output.write

        try:
            # Run status command
            options = {"action": "status"}
            self.command.handle(**options)

            output = captured_output.getvalue()
            self.assertIn("AI Filename Recognition System Status", output)
        finally:
            # Restore original stdout
            self.command.stdout = original_stdout

    @patch("books.management.commands.train_ai_models.FilenamePatternRecognizer")
    def test_training_insufficient_data(self, mock_recognizer):
        """Test training with insufficient data."""
        # Mock recognizer with insufficient training data
        mock_instance = Mock()
        mock_instance.collect_training_data.return_value = []  # No training data
        mock_recognizer.return_value = mock_instance

        # Capture command output using StringIO for Django management commands
        from io import StringIO

        captured_output = StringIO()

        # Mock the command's stdout
        original_stdout = self.command.stdout
        self.command.stdout.write = captured_output.write

        try:
            options = {"action": "train", "min_samples": 10, "use_feedback": False, "min_feedback": 5}
            self.command.handle(**options)

            output = captured_output.getvalue()
            self.assertIn("Insufficient training data", output)
        finally:
            # Restore original stdout
            self.command.stdout = original_stdout


class AIFeedbackModelTests(TestCase):
    """Test the AIFeedback model functionality."""

    def setUp(self):
        self.user = User.objects.create_user("testuser", "test@example.com", "password")
        # Create a temporary directory for scan folder
        import tempfile

        self.test_dir = tempfile.mkdtemp()
        self.scan_folder = ScanFolder.objects.create(path=self.test_dir, is_active=True)
        self.book = create_test_book_with_file(file_path=f"{self.test_dir}/test_book.epub", title="Test Book", content_type="ebook", scan_folder=self.scan_folder)
        # Create a BookFile to represent the actual file
        from books.models import BookFile

        self.book_file = BookFile.objects.create(book=self.book, file_path="/test/test_book.epub", file_format="epub", file_size=1024000)

    def test_feedback_creation(self):
        """Test creating AI feedback entries."""
        feedback = AIFeedback.objects.create(
            book=self.book,
            user=self.user,
            original_filename="test_book.epub",
            ai_predictions='{"title": "Test", "author": "Author"}',
            user_corrections='{"title": "Corrected Title"}',
            feedback_rating=4,
            comments="Good prediction overall",
        )

        self.assertEqual(feedback.book, self.book)
        self.assertEqual(feedback.user, self.user)
        self.assertEqual(feedback.feedback_rating, 4)
        self.assertTrue(feedback.needs_retraining)
        self.assertFalse(feedback.processed_for_training)

    def test_feedback_json_parsing(self):
        """Test JSON parsing methods in AIFeedback model."""
        feedback = AIFeedback.objects.create(
            book=self.book,
            user=self.user,
            original_filename="test_book.epub",
            ai_predictions='{"title": "Test Title", "confidence": 0.8}',
            user_corrections='{"title": "Corrected Title", "author": "New Author"}',
            feedback_rating=3,
        )

        predictions = feedback.get_ai_predictions_dict()
        corrections = feedback.get_user_corrections_dict()

        self.assertEqual(predictions["title"], "Test Title")
        self.assertEqual(corrections["title"], "Corrected Title")
        self.assertEqual(corrections["author"], "New Author")

    def test_accuracy_score_calculation(self):
        """Test accuracy score calculation from rating."""
        test_cases = [(1, 0.0), (2, 0.25), (3, 0.5), (4, 0.75), (5, 1.0)]  # Poor  # Fair  # Good  # Very Good  # Excellent

        for rating, expected_score in test_cases:
            with self.subTest(rating=rating):
                # Create a unique book for each test case due to unique constraint
                book = create_test_book_with_file(file_path=f"{self.test_dir}/test_book_{rating}.epub", scan_folder=self.scan_folder)
                feedback = AIFeedback.objects.create(
                    book=book, user=self.user, original_filename=f"test_book_{rating}.epub", ai_predictions="{}", user_corrections="{}", feedback_rating=rating
                )
                self.assertEqual(feedback.get_accuracy_score(), expected_score)


class AIViewsTests(TestCase):
    """Test AI-related views and AJAX endpoints."""

    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user("testuser", "test@example.com", "password")
        # Create a temporary directory for scan folder
        import tempfile

        self.test_dir = tempfile.mkdtemp()
        self.scan_folder = ScanFolder.objects.create(path=self.test_dir, is_active=True)

        # Create test book with AI metadata
        self.book = create_test_book_with_file(file_path=f"{self.test_dir}/test_book.epub", title="Test Book", content_type="ebook", scan_folder=self.scan_folder)
        # Create a BookFile to represent the actual file
        from books.models import BookFile

        self.book_file = BookFile.objects.create(book=self.book, file_path="/test/test_book.epub", file_format="epub", file_size=1024000)

        self.final_meta = FinalMetadata.objects.create(book=self.book, final_title="Test Title", final_author="Test Author", overall_confidence=0.75, is_reviewed=False)

    def test_ai_feedback_list_view(self):
        """Test the AI feedback list view."""
        # Create AI source
        ai_source = DataSource.objects.create(name="filename_ai")

        # Create AI metadata for the book
        from books.models import BookMetadata

        BookMetadata.objects.create(book=self.book, source=ai_source, field_name="ai_title", field_value="Test Title", confidence=0.8, is_active=True)

        request = self.factory.get("/ai-feedback/")
        request.user = self.user

        view = AIFeedbackListView()
        view.request = request

        queryset = view.get_queryset()
        self.assertEqual(queryset.count(), 1)
        self.assertEqual(queryset.first(), self.book)

    def test_ajax_submit_ai_feedback(self):
        """Test AJAX feedback submission."""
        request_data = {
            "corrections": {"title": "Corrected Title", "author": "Corrected Author"},
            "rating": 4,
            "comments": "Good prediction",
            "ai_predictions": {"title": "Original Title", "author": "Original Author"},
            "prediction_confidence": 0.8,
        }

        request = self.factory.post(f"/ajax/book/{self.book.id}/ai-feedback/", data=json.dumps(request_data), content_type="application/json")
        request.user = self.user

        response = ajax_submit_ai_feedback(request, self.book.id)

        self.assertIsInstance(response, JsonResponse)
        response_data = json.loads(response.content)
        self.assertTrue(response_data["success"])

        # Check that feedback was created
        feedback = AIFeedback.objects.get(book=self.book, user=self.user)
        self.assertEqual(feedback.feedback_rating, 4)
        self.assertTrue(feedback.needs_retraining)

    @patch("books.scanner.ai.filename_recognizer.FilenamePatternRecognizer")
    def test_ajax_ai_model_status(self, mock_recognizer):
        """Test AJAX model status endpoint."""
        # Mock recognizer behavior
        mock_instance = Mock()
        mock_instance.models_exist.return_value = True
        mock_instance.get_training_data_stats.return_value = {"total_samples": 50, "accuracy": 0.85}
        mock_recognizer.return_value = mock_instance

        request = self.factory.get("/ajax/ai/status/")
        request.user = self.user

        response = ajax_ai_model_status(request)

        self.assertIsInstance(response, JsonResponse)
        response_data = json.loads(response.content)
        self.assertTrue(response_data["success"])
        self.assertTrue(response_data["models_exist"])

    @patch("django.core.management.call_command")
    def test_ajax_retrain_ai_models(self, mock_call_command):
        """Test AJAX model retraining endpoint."""
        # Create sufficient feedback for retraining
        for i in range(6):
            # Create a unique book for each feedback due to unique constraint
            book = create_test_book_with_file(file_path=f"{self.test_dir}/test_book_{i}.epub", scan_folder=self.scan_folder)
            AIFeedback.objects.create(
                book=book, user=self.user, original_filename=f"test_book_{i}.epub", ai_predictions="{}", user_corrections="{}", feedback_rating=4, needs_retraining=True
            )

        request = self.factory.post("/ajax/ai/retrain/")
        request.user = self.user

        response = ajax_retrain_ai_models(request)

        self.assertIsInstance(response, JsonResponse)
        response_data = json.loads(response.content)
        self.assertTrue(response_data["success"])
        self.assertEqual(response_data["feedback_count"], 6)


class AIIntegrationTests(TestCase):
    """Test AI integration with the scanner system."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch("books.scanner.ai.initialize_ai_system")
    def test_scanner_ai_integration(self, mock_init_ai):
        """Test AI system integration with scanner."""
        # Mock AI system
        mock_recognizer = Mock()
        mock_recognizer.predict_metadata.return_value = {"title": ("Test Title", 0.9), "author": ("Test Author", 0.8), "series": ("Test Series", 0.7), "volume": ("1", 0.6)}
        mock_recognizer.is_prediction_confident.return_value = True
        mock_init_ai.return_value = mock_recognizer

        from books.scanner.parsing import parse_path_metadata_with_ai

        # Test AI parsing
        filename = "Test Series - 01 - Test Title - Test Author.epub"
        result = parse_path_metadata_with_ai(filename)

        self.assertIsNotNone(result)
        self.assertEqual(result["title"], "Test Title")
        self.assertEqual(result["authors"], ["Test Author"])  # Traditional parsing returns list
        self.assertEqual(result["series"], "Test Series")
        self.assertEqual(result["series_number"], 1.0)  # Series number as float

    @patch("books.scanner.ai.initialize_ai_system")
    def test_ai_fallback_to_traditional(self, mock_init_ai):
        """Test fallback to traditional parsing when AI confidence is low."""
        # Mock AI system with low confidence
        mock_recognizer = Mock()
        mock_recognizer.predict_metadata.return_value = {"title": ("Uncertain Title", 0.3), "author": ("Uncertain Author", 0.2), "series": ("", 0.1), "volume": ("", 0.1)}
        mock_recognizer.is_prediction_confident.return_value = False
        mock_init_ai.return_value = mock_recognizer

        from books.scanner.parsing import parse_path_metadata_with_ai

        # Test fallback behavior
        filename = "Clear Author - Clear Series 01 - Clear Title.epub"
        result = parse_path_metadata_with_ai(filename)

        # Should fall back to traditional parsing
        self.assertIsNotNone(result)
        # Traditional parsing should extract metadata from the clear filename
        self.assertIn("title", result)
        self.assertIn("authors", result)  # Traditional parsing returns 'authors' (plural)
        self.assertTrue(isinstance(result["authors"], list))  # Should be a list of authors


class AIPerformanceTests(TestCase):
    """Test AI system performance and edge cases."""

    def test_large_dataset_handling(self):
        """Test handling of large training datasets."""
        recognizer = FilenamePatternRecognizer()

        # Create a large mock dataset
        large_dataset = []
        for i in range(1000):
            large_dataset.append({"filename": f"Author{i} - Book{i}.epub", "title": f"Book{i}", "author": f"Author{i}", "series": "", "volume": ""})

        # Test feature extraction on large dataset (should not crash)
        try:
            for sample in large_dataset[:10]:  # Test first 10 samples
                features = recognizer._extract_features(sample["filename"])
                self.assertIsInstance(features, dict)
        except Exception as e:
            self.fail(f"Feature extraction failed on large dataset: {e}")

    def test_unicode_filename_handling(self):
        """Test handling of unicode characters in filenames."""
        recognizer = FilenamePatternRecognizer()

        unicode_filenames = ["Müller - Buch über Städte.epub", "José García - El Libro Español.epub", "山田太郎 - 日本の本.epub", "Владимир Петров - Русская Книга.epub"]

        for filename in unicode_filenames:
            with self.subTest(filename=filename):
                try:
                    features = recognizer._extract_features(filename)
                    self.assertIsInstance(features, dict)
                    processed = recognizer._clean_filename(filename)
                    self.assertIsInstance(processed, str)
                except Exception as e:
                    self.fail(f"Unicode handling failed for {filename}: {e}")

    def test_edge_case_filenames(self):
        """Test handling of edge case filenames."""
        recognizer = FilenamePatternRecognizer()

        edge_cases = [
            "",  # Empty filename
            "a.epub",  # Very short filename
            "A" * 500 + ".epub",  # Very long filename
            "!@#$%^&*()_+.epub",  # Special characters only
            "123456789.epub",  # Numbers only
            "   .epub",  # Whitespace only
        ]

        for filename in edge_cases:
            with self.subTest(filename=filename):
                try:
                    features = recognizer._extract_features(filename)
                    self.assertIsInstance(features, dict)
                    # Should not crash on edge cases
                except Exception as e:
                    self.fail(f"Edge case handling failed for '{filename}': {e}")


if __name__ == "__main__":
    unittest.main()
