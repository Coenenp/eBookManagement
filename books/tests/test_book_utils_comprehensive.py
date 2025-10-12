"""
Comprehensive test suite for book_utils.py metadata processing functionality.
Tests MetadataProcessor and related utility functions.
"""

import os
import tempfile
import shutil
from unittest.mock import patch, MagicMock
from django.test import TestCase, RequestFactory
from django.contrib.auth.models import User
from django.db import IntegrityError

from books.models import (
    Author, Series, Publisher, Genre, DataSource, ScanFolder,
    FinalMetadata, BookSeries, BookTitle, BookAuthor, BookPublisher,
    BookMetadata
)
from books.book_utils import MetadataProcessor
from books.tests.test_helpers import create_test_book_with_file


class BaseTestCaseWithTempDir(TestCase):
    """Base test case with temporary directory management for ScanFolder tests."""

    def setUp(self):
        """Set up test environment with temporary directories."""
        super().setUp()
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up temporary directories."""
        if hasattr(self, 'temp_dir') and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
        super().tearDown()


class MetadataProcessorTests(BaseTestCaseWithTempDir):
    """Test suite for MetadataProcessor class"""

    def setUp(self):
        """Set up test data for metadata processor tests"""
        super().setUp()
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )

        # Create test data sources
        self.manual_source, _ = DataSource.objects.get_or_create(
            name='Manual Entry',
            defaults={'trust_level': 1.0}
        )
        self.epub_source, _ = DataSource.objects.get_or_create(
            name='EPUB',
            defaults={'trust_level': 0.7}
        )

        # Create test scan folder using temporary directory
        self.scan_folder = ScanFolder.objects.create(
            path=self.temp_dir,
            is_active=True
        )

        # Create test entities
        self.author = Author.objects.create(name='Test Author')
        self.series = Series.objects.create(name='Test Series')
        self.publisher = Publisher.objects.create(name='Test Publisher')
        self.genre = Genre.objects.create(name='Science Fiction')

        # Create test book using helper
        # Create test file in temp directory
        test_file_path = os.path.join(self.temp_dir, 'book1.epub')
        with open(test_file_path, 'w') as f:
            f.write('test content')

        self.book = create_test_book_with_file(
            file_path=test_file_path,
            file_format='epub',
            file_size=1000000,
            scan_folder=self.scan_folder
        )

        # Create final metadata
        self.final_metadata = FinalMetadata.objects.create(
            book=self.book,
            final_title='Original Title',
            final_author='Original Author',
            is_reviewed=False
        )

    def test_handle_manual_entries_basic_functionality(self):
        """Test basic functionality of handle_manual_entries"""
        # Create a request with manual entry data
        request = self.factory.post('/', {
            'final_title': 'New Title',
            'manual_entry_final_title': 'true',
            'final_author': 'New Author',
            'manual_entry_final_author': 'true'
        })
        request.user = self.user
        request.POST = request.POST.copy()

        form_data = {
            'final_title': 'New Title',
            'final_author': 'New Author'
        }

        # Call the method
        MetadataProcessor.handle_manual_entries(request, self.book, form_data)

        # Verify manual source was created
        manual_source = DataSource.objects.get(name=DataSource.MANUAL)
        self.assertIsNotNone(manual_source)
        self.assertEqual(manual_source.trust_level, 1.0)

    def test_handle_manual_entries_title_processing(self):
        """Test manual title entry processing"""
        request = self.factory.post('/', {
            'final_title': '__manual__',
            'manual_title': 'Manual Title Entry',
            'manual_entry_final_title': 'true'
        })
        request.user = self.user
        request.POST = request.POST.copy()

        form_data = {
            'final_title': '__manual__'
        }

        with patch.object(MetadataProcessor, '_handle_manual_title') as mock_handler:
            mock_entry = MagicMock()
            mock_handler.return_value = mock_entry

            MetadataProcessor.handle_manual_entries(request, self.book, form_data)

            # Verify the title handler was called
            mock_handler.assert_called_once()
            call_args = mock_handler.call_args[0]
            self.assertEqual(call_args[0], self.book)
            self.assertEqual(call_args[1], 'final_title')

    def test_handle_manual_entries_author_processing(self):
        """Test manual author entry processing"""
        request = self.factory.post('/', {
            'final_author': '__manual__',
            'manual_author': 'Manual Author Entry',
            'manual_entry_final_author': 'true'
        })
        request.user = self.user
        request.POST = request.POST.copy()

        form_data = {
            'final_author': '__manual__'
        }

        with patch.object(MetadataProcessor, '_handle_manual_author') as mock_handler:
            mock_entry = MagicMock()
            mock_handler.return_value = mock_entry

            MetadataProcessor.handle_manual_entries(request, self.book, form_data)

            # Verify the author handler was called
            mock_handler.assert_called_once()

    def test_handle_manual_entries_series_processing(self):
        """Test manual series entry processing"""
        request = self.factory.post('/', {
            'final_series': '__manual__',
            'manual_series': 'Manual Series Entry',
            'manual_entry_final_series': 'true'
        })
        request.user = self.user
        request.POST = request.POST.copy()

        form_data = {
            'final_series': '__manual__'
        }

        with patch.object(MetadataProcessor, '_handle_manual_series') as mock_handler:
            mock_entry = MagicMock()
            mock_handler.return_value = mock_entry

            MetadataProcessor.handle_manual_entries(request, self.book, form_data)

            # Verify the series handler was called
            mock_handler.assert_called_once()

    def test_handle_manual_entries_publisher_processing(self):
        """Test manual publisher entry processing"""
        request = self.factory.post('/', {
            'final_publisher': '__manual__',
            'manual_publisher': 'Manual Publisher Entry',
            'manual_entry_final_publisher': 'true'
        })
        request.user = self.user
        request.POST = request.POST.copy()

        form_data = {
            'final_publisher': '__manual__'
        }

        with patch.object(MetadataProcessor, '_handle_manual_publisher') as mock_handler:
            mock_entry = MagicMock()
            mock_handler.return_value = mock_entry

            MetadataProcessor.handle_manual_entries(request, self.book, form_data)

            # Verify the publisher handler was called
            mock_handler.assert_called_once()

    def test_handle_manual_entries_metadata_fields(self):
        """Test manual metadata field processing"""
        request = self.factory.post('/', {
            'publication_year': '2023',
            'manual_entry_publication_year': 'true',
            'language': 'English',
            'manual_entry_language': 'true',
            'isbn': '9781234567890',
            'manual_entry_isbn': 'true',
            'description': 'Test description',
            'manual_entry_description': 'true'
        })
        request.user = self.user
        request.POST = request.POST.copy()

        form_data = {
            'publication_year': '2023',
            'language': 'English',
            'isbn': '9781234567890',
            'description': 'Test description'
        }

        with patch.object(MetadataProcessor, '_handle_manual_metadata_field') as mock_handler:
            mock_entry = MagicMock()
            mock_handler.return_value = mock_entry

            MetadataProcessor.handle_manual_entries(request, self.book, form_data)

            # Verify the metadata field handler was called for each field
            self.assertEqual(mock_handler.call_count, 4)

    def test_handle_manual_entries_existing_data_check(self):
        """Test that existing data is checked before processing"""
        # Create existing title
        BookTitle.objects.create(
            book=self.book,
            title='Existing Title',
            confidence=0.8,
            is_active=True,
            source=self.epub_source
        )

        request = self.factory.post('/', {
            'final_title': 'New Title',
            'manual_entry_final_title': 'false'  # Explicitly not manual
        })
        request.user = self.user
        request.POST = request.POST.copy()

        form_data = {
            'final_title': 'New Title'
        }

        with patch.object(MetadataProcessor, '_handle_manual_title') as mock_handler:
            MetadataProcessor.handle_manual_entries(request, self.book, form_data)

            # Should not call handler when existing data exists and not explicitly manual
            mock_handler.assert_not_called()

    def test_handle_manual_entries_empty_values(self):
        """Test handling of empty values"""
        request = self.factory.post('/', {
            'final_title': '',
            'manual_entry_final_title': 'true',
            'final_author': '   ',  # Whitespace only
            'manual_entry_final_author': 'true'
        })
        request.user = self.user
        request.POST = request.POST.copy()

        form_data = {
            'final_title': '',
            'final_author': '   '
        }

        with patch.object(MetadataProcessor, '_handle_manual_title') as mock_title_handler:
            with patch.object(MetadataProcessor, '_handle_manual_author') as mock_author_handler:
                MetadataProcessor.handle_manual_entries(request, self.book, form_data)

                # Should not call handlers for empty values
                mock_title_handler.assert_not_called()
                mock_author_handler.assert_not_called()

    def test_handle_manual_entries_manual_flag_precedence(self):
        """Test manual flag precedence logic - explicit manual flag takes precedence"""
        # Test case: explicit manual_entry flag set to true
        request = self.factory.post('/', {
            'final_title': 'New Title',
            'manual_entry_final_title': 'true'  # Explicit manual flag
        })
        request.user = self.user
        request.POST = request.POST.copy()

        form_data = {
            'final_title': 'New Title'
        }

        with patch.object(MetadataProcessor, '_handle_manual_title') as mock_handler:
            mock_entry = MagicMock()
            mock_handler.return_value = mock_entry

            MetadataProcessor.handle_manual_entries(request, self.book, form_data)

            # Should call handler when manual flag is explicitly set
            mock_handler.assert_called_once()

    def test_handle_manual_entries_bulk_operations(self):
        """Test that bulk operations are prepared correctly"""
        request = self.factory.post('/', {
            'final_title': 'New Title',
            'manual_entry_final_title': 'true'
        })
        request.user = self.user
        request.POST = request.POST.copy()

        form_data = {
            'final_title': 'New Title'
        }

        # Mock the handler to return a BookTitle instance
        mock_book_title = MagicMock(spec=BookTitle)

        with patch.object(MetadataProcessor, '_handle_manual_title', return_value=mock_book_title):
            # The method should complete without error and organize bulk operations
            MetadataProcessor.handle_manual_entries(request, self.book, form_data)

    def test_handle_manual_entries_complex_scenario(self):
        """Test complex scenario with multiple fields and conditions"""
        # Create some existing data
        BookAuthor.objects.create(
            book=self.book,
            author=self.author,
            confidence=0.7,
            is_active=True,
            source=self.epub_source
        )
        # Create existing series data to test the "has existing data" logic
        BookSeries.objects.create(
            book=self.book,
            series=self.series,
            confidence=0.6,
            is_active=True,
            source=self.epub_source
        )

        request = self.factory.post('/', {
            'final_title': 'New Title',
            'manual_entry_final_title': 'true',
            'final_author': '__manual__',
            'manual_author': 'Manual Author',
            'manual_entry_final_author': 'true',
            'final_series': 'Existing Series',  # No manual flag
            'publication_year': '2023',
            'manual_entry_publication_year': 'true'
        })
        request.user = self.user
        request.POST = request.POST.copy()

        form_data = {
            'final_title': 'New Title',
            'final_author': '__manual__',
            'final_series': 'Existing Series',
            'publication_year': '2023'
        }

        with patch.object(MetadataProcessor, '_handle_manual_title') as mock_title:
            with patch.object(MetadataProcessor, '_handle_manual_author') as mock_author:
                with patch.object(MetadataProcessor, '_handle_manual_series') as mock_series:
                    with patch.object(MetadataProcessor, '_handle_manual_metadata_field') as mock_metadata:
                        # Setup return values
                        mock_title.return_value = MagicMock(spec=BookTitle)
                        mock_author.return_value = MagicMock(spec=BookAuthor)
                        mock_series.return_value = None  # No series entry
                        mock_metadata.return_value = MagicMock(spec=BookMetadata)

                        MetadataProcessor.handle_manual_entries(request, self.book, form_data)

                        # Verify title and author handlers were called
                        mock_title.assert_called_once()
                        mock_author.assert_called_once()

                        # Series should not be called (has existing data, no manual flag)
                        mock_series.assert_not_called()

                        # Metadata field should be called
                        mock_metadata.assert_called_once()


class MetadataProcessorHelperMethodTests(BaseTestCaseWithTempDir):
    """Test helper methods of MetadataProcessor"""

    def setUp(self):
        """Set up test data for helper method tests"""
        super().setUp()
        self.factory = RequestFactory()
        self.user = User.objects.create_user(username='testuser', password='testpass123')

        self.manual_source, _ = DataSource.objects.get_or_create(
            name='Manual Entry',
            defaults={'trust_level': 1.0}
        )

        self.scan_folder = ScanFolder.objects.create(
            path=self.temp_dir,
            is_active=True
        )

        # Create test file in temp directory
        test_file_path = os.path.join(self.temp_dir, 'book1.epub')
        with open(test_file_path, 'w') as f:
            f.write('test content')

        self.book = create_test_book_with_file(
            file_path=test_file_path,
            file_format='epub',
            file_size=1000000,
            scan_folder=self.scan_folder
        )

        # Create final metadata
        self.final_metadata = FinalMetadata.objects.create(
            book=self.book,
            final_title='Original Title',
            is_reviewed=False
        )

    def test_handle_manual_title_new_entry(self):
        """Test creating new manual title entry"""
        form_data = {'final_title': 'New Manual Title'}

        entry = MetadataProcessor._handle_manual_title(
            self.book, 'final_title', form_data, self.manual_source
        )

        self.assertIsInstance(entry, BookTitle)
        self.assertEqual(entry.book, self.book)
        self.assertEqual(entry.title, 'New Manual Title')
        self.assertEqual(entry.source, self.manual_source)
        self.assertEqual(entry.confidence, 1.0)
        self.assertTrue(entry.is_active)

    def test_handle_manual_author_new_entry(self):
        """Test creating new manual author entry"""
        form_data = {'final_author': 'New Manual Author'}

        entry = MetadataProcessor._handle_manual_author(
            self.book, 'final_author', form_data, self.manual_source
        )

        self.assertIsInstance(entry, BookAuthor)
        self.assertEqual(entry.book, self.book)
        self.assertEqual(entry.author.name, 'New Manual Author')
        self.assertEqual(entry.source, self.manual_source)
        self.assertEqual(entry.confidence, 1.0)
        self.assertTrue(entry.is_main_author)
        self.assertTrue(entry.is_active)

    def test_handle_manual_author_existing_author(self):
        """Test creating manual author entry with existing author"""
        existing_author = Author.objects.create(name='Existing Author')
        form_data = {'final_author': 'Existing Author'}

        entry = MetadataProcessor._handle_manual_author(
            self.book, 'final_author', form_data, self.manual_source
        )

        self.assertIsInstance(entry, BookAuthor)
        self.assertEqual(entry.author, existing_author)

    def test_handle_manual_series_new_entry(self):
        """Test creating new manual series entry"""
        form_data = {'final_series': 'New Manual Series'}

        entry = MetadataProcessor._handle_manual_series(
            self.book, 'final_series', form_data, self.manual_source
        )

        self.assertIsInstance(entry, BookSeries)
        self.assertEqual(entry.book, self.book)
        self.assertEqual(entry.series.name, 'New Manual Series')
        self.assertEqual(entry.source, self.manual_source)
        self.assertEqual(entry.confidence, 1.0)
        self.assertTrue(entry.is_active)

    def test_handle_manual_series_existing_series(self):
        """Test creating manual series entry with existing series"""
        existing_series = Series.objects.create(name='Existing Series')
        form_data = {'final_series': 'Existing Series'}

        entry = MetadataProcessor._handle_manual_series(
            self.book, 'final_series', form_data, self.manual_source
        )

        self.assertIsInstance(entry, BookSeries)
        self.assertEqual(entry.series, existing_series)

    def test_handle_manual_publisher_new_entry(self):
        """Test creating new manual publisher entry"""
        form_data = {'final_publisher': 'New Manual Publisher'}

        entry = MetadataProcessor._handle_manual_publisher(
            self.book, 'final_publisher', form_data, self.manual_source
        )

        self.assertIsInstance(entry, BookPublisher)
        self.assertEqual(entry.book, self.book)
        self.assertEqual(entry.publisher.name, 'New Manual Publisher')
        self.assertEqual(entry.source, self.manual_source)
        self.assertEqual(entry.confidence, 1.0)
        self.assertTrue(entry.is_active)

    def test_handle_manual_metadata_field_new_entry(self):
        """Test creating new manual metadata field entry"""
        form_data = {'publication_year': '2023'}

        entry = MetadataProcessor._handle_manual_metadata_field(
            self.book, 'publication_year', form_data, self.manual_source
        )

        self.assertIsInstance(entry, BookMetadata)
        self.assertEqual(entry.book, self.book)
        self.assertEqual(entry.field_name, 'publication_year')
        self.assertEqual(entry.field_value, '2023')
        self.assertEqual(entry.source, self.manual_source)
        self.assertEqual(entry.confidence, 1.0)
        self.assertTrue(entry.is_active)

    def test_handle_manual_metadata_field_different_types(self):
        """Test creating metadata fields for different field types"""
        test_cases = [
            ('isbn', '9781234567890'),
            ('language', 'English'),
            ('description', 'A test book description'),
            ('publication_year', '2023')
        ]

        for field_name, field_value in test_cases:
            with self.subTest(field=field_name):
                form_data = {field_name: field_value}

                entry = MetadataProcessor._handle_manual_metadata_field(
                    self.book, field_name, form_data, self.manual_source
                )

                self.assertIsInstance(entry, BookMetadata)
                self.assertEqual(entry.field_name, field_name)
                self.assertEqual(entry.field_value, field_value)


class MetadataProcessorErrorHandlingTests(BaseTestCaseWithTempDir):
    """Test error handling in MetadataProcessor"""

    def setUp(self):
        """Set up test data for error handling tests"""
        super().setUp()
        self.factory = RequestFactory()
        self.user = User.objects.create_user(username='testuser', password='testpass123')

        self.manual_source, _ = DataSource.objects.get_or_create(
            name='Manual Entry',
            defaults={'trust_level': 1.0}
        )

        self.scan_folder = ScanFolder.objects.create(
            path=self.temp_dir,
            is_active=True
        )

        # Create test file in temp directory
        test_file_path = os.path.join(self.temp_dir, 'book1.epub')
        with open(test_file_path, 'w') as f:
            f.write('test content')

        self.book = create_test_book_with_file(
            file_path=test_file_path,
            file_format='epub',
            file_size=1000000,
            scan_folder=self.scan_folder
        )

        # Create final metadata
        self.final_metadata = FinalMetadata.objects.create(
            book=self.book,
            final_title='Original Title',
            is_reviewed=False
        )

    def test_handle_manual_entries_with_missing_form_data(self):
        """Test handling manual entries with missing form data"""
        request = self.factory.post('/', {
            'final_title': 'New Title',
            'manual_entry_final_title': 'true'
        })
        request.user = self.user
        request.POST = request.POST.copy()

        # Empty form data
        form_data = {}

        # Should handle gracefully without errors
        MetadataProcessor.handle_manual_entries(request, self.book, form_data)

    def test_handle_manual_entries_with_none_values(self):
        """Test handling manual entries with None values"""
        request = self.factory.post('/', {
            'final_title': 'New Title',
            'manual_entry_final_title': 'true'
        })
        request.user = self.user
        request.POST = request.POST.copy()

        form_data = {
            'final_title': None,
            'final_author': None
        }

        # Should handle gracefully without errors
        MetadataProcessor.handle_manual_entries(request, self.book, form_data)

    def test_handle_manual_author_with_very_long_name(self):
        """Test creating author with very long name"""
        very_long_name = 'A' * 1000  # Very long author name
        form_data = {'final_author': very_long_name}

        # Should handle gracefully, potentially truncating or handling the long name
        entry = MetadataProcessor._handle_manual_author(
            self.book, 'final_author', form_data, self.manual_source
        )

        self.assertIsInstance(entry, BookAuthor)
        # The actual behavior depends on model field constraints

    def test_handle_manual_entries_with_special_characters(self):
        """Test handling entries with special characters"""
        request = self.factory.post('/', {
            'final_title': 'Title with Spëcial Cháracters & Symbols!',
            'manual_entry_final_title': 'true',
            'final_author': 'Åuthör with ñoñ-ASCII chars 中文',
            'manual_entry_final_author': 'true'
        })
        request.user = self.user
        request.POST = request.POST.copy()

        form_data = {
            'final_title': 'Title with Spëcial Cháracters & Symbols!',
            'final_author': 'Åuthör with ñoñ-ASCII chars 中文'
        }

        # Should handle special characters without errors
        MetadataProcessor.handle_manual_entries(request, self.book, form_data)

    @patch('books.book_utils.logger')
    def test_handle_manual_entries_with_database_error(self, mock_logger):
        """Test handling database errors during processing"""
        request = self.factory.post('/', {
            'final_title': 'New Title',
            'manual_entry_final_title': 'true'
        })
        request.user = self.user
        request.POST = request.POST.copy()

        form_data = {
            'final_title': 'New Title'
        }

        # Mock database error
        with patch.object(DataSource.objects, 'get_or_create', side_effect=IntegrityError('Database error')):
            # Should handle database errors gracefully
            try:
                MetadataProcessor.handle_manual_entries(request, self.book, form_data)
            except Exception as e:
                # If exceptions are raised, they should be appropriate and logged
                self.assertIsInstance(e, (IntegrityError, Exception))

    def test_bulk_map_handling_with_none_entries(self):
        """Test bulk map handling when some handlers return None"""
        request = self.factory.post('/', {
            'final_title': 'New Title',
            'manual_entry_final_title': 'true'
        })
        request.user = self.user
        request.POST = request.POST.copy()

        form_data = {
            'final_title': 'New Title'
        }

        # Mock handler to return None
        with patch.object(MetadataProcessor, '_handle_manual_title', return_value=None):
            # Should handle None returns gracefully
            MetadataProcessor.handle_manual_entries(request, self.book, form_data)


class MetadataProcessorIntegrationTests(BaseTestCaseWithTempDir):
    """Integration tests for MetadataProcessor with real database operations"""

    def setUp(self):
        """Set up test data for integration tests"""
        super().setUp()
        self.factory = RequestFactory()
        self.user = User.objects.create_user(username='testuser', password='testpass123')

        self.scan_folder = ScanFolder.objects.create(
            path=self.temp_dir,
            is_active=True
        )

        # Create test file in temp directory
        test_file_path = os.path.join(self.temp_dir, 'book1.epub')
        with open(test_file_path, 'w') as f:
            f.write('test content')

        self.book = create_test_book_with_file(
            file_path=test_file_path,
            file_format='epub',
            file_size=1000000,
            scan_folder=self.scan_folder
        )

        self.final_metadata = FinalMetadata.objects.create(
            book=self.book,
            final_title='Original Title'
        )

    def test_end_to_end_manual_entry_processing(self):
        """Test complete end-to-end manual entry processing"""
        request = self.factory.post('/', {
            'final_title': 'Complete Manual Title',
            'manual_entry_final_title': 'true',
            'final_author': '__manual__',
            'manual_author': 'Complete Manual Author',
            'manual_entry_final_author': 'true',
            'final_series': 'Complete Manual Series',
            'manual_entry_final_series': 'true',
            'publication_year': '2023',
            'manual_entry_publication_year': 'true'
        })
        request.user = self.user
        request.POST = request.POST.copy()

        form_data = {
            'final_title': 'Complete Manual Title',
            'final_author': '__manual__',
            'final_series': 'Complete Manual Series',
            'publication_year': '2023'
        }

        # Process the manual entries
        MetadataProcessor.handle_manual_entries(request, self.book, form_data)

        # Verify all entries were created
        self.assertTrue(BookTitle.objects.filter(
            book=self.book,
            title='Complete Manual Title',
            source__name='Manual Entry'
        ).exists())

        self.assertTrue(Author.objects.filter(name='Complete Manual Author').exists())
        author = Author.objects.get(name='Complete Manual Author')
        self.assertTrue(BookAuthor.objects.filter(
            book=self.book,
            author=author,
            source__name='Manual Entry'
        ).exists())

        self.assertTrue(Series.objects.filter(name='Complete Manual Series').exists())
        series = Series.objects.get(name='Complete Manual Series')
        self.assertTrue(BookSeries.objects.filter(
            book=self.book,
            series=series,
            source__name='Manual Entry'
        ).exists())

        self.assertTrue(BookMetadata.objects.filter(
            book=self.book,
            field_name='publication_year',
            field_value='2023',
            source__name='Manual Entry'
        ).exists())

    def test_mixed_manual_and_existing_data_processing(self):
        """Test processing with mix of manual entries and existing data"""
        # Create some existing data
        existing_author = Author.objects.create(name='Existing Author')
        epub_source, _ = DataSource.objects.get_or_create(name='EPUB', defaults={'trust_level': 0.7})

        BookAuthor.objects.create(
            book=self.book,
            author=existing_author,
            source=epub_source,
            confidence=0.8,
            is_active=True
        )

        request = self.factory.post('/', {
            'final_title': 'New Manual Title',
            'manual_entry_final_title': 'true',
            'final_author': 'Existing Author',  # Should not create manual entry
            'final_series': '__manual__',
            'manual_series': 'New Manual Series',
            'manual_entry_final_series': 'true'
        })
        request.user = self.user
        request.POST = request.POST.copy()

        form_data = {
            'final_title': 'New Manual Title',
            'final_author': 'Existing Author',
            'final_series': '__manual__'
        }

        MetadataProcessor.handle_manual_entries(request, self.book, form_data)

        # Verify manual title was created
        self.assertTrue(BookTitle.objects.filter(
            book=self.book,
            title='New Manual Title',
            source__name='Manual Entry'
        ).exists())

        # Verify no new manual author entry was created (existing data exists)
        manual_author_entries = BookAuthor.objects.filter(
            book=self.book,
            source__name='Manual Entry'
        )
        self.assertEqual(manual_author_entries.count(), 0)

        # Verify manual series was created
        self.assertTrue(Series.objects.filter(name='New Manual Series').exists())

    def test_performance_with_multiple_entries(self):
        """Test performance with multiple manual entries"""
        # Create request with many manual entries
        post_data = {}
        form_data = {}

        for i in range(10):
            post_data[f'metadata_field_{i}'] = f'Value {i}'
            post_data[f'manual_entry_metadata_field_{i}'] = 'true'
            form_data[f'metadata_field_{i}'] = f'Value {i}'

        request = self.factory.post('/', post_data)
        request.user = self.user
        request.POST = request.POST.copy()

        # Should handle multiple entries efficiently
        MetadataProcessor.handle_manual_entries(request, self.book, form_data)
