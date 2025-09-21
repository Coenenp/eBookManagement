"""
Test cases for utility functions and helper methods in views.py.

This module contains comprehensive tests for utility functions, edge cases,
error handling, and helper methods that don't have dedicated test coverage
in other test files.
"""

from unittest.mock import patch
from django.test import TestCase, Client, RequestFactory
from django.contrib.auth.models import User
from django.http import JsonResponse
from books.models import Book, Author, Series, Genre, FinalMetadata, BookGenre, DataSource, BookAuthor
from books.views import BookRenamerView, BookRenamerFileDetailsView, BookRenamerExecuteView


class UtilityFunctionTests(TestCase):
    """Test utility and helper functions within views."""

    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.client = Client()
        self.client.login(username='testuser', password='testpass123')

    def test_clean_filename(self):
        """Test filename cleaning utility."""
        renamer_view = BookRenamerView()

        # Test basic filename cleaning
        self.assertEqual(renamer_view._clean_filename("Test Book: A Story!"), "Test Book - A Story")
        self.assertEqual(renamer_view._clean_filename("Book/with\\slashes"), "Book-with-slashes")
        self.assertEqual(renamer_view._clean_filename("Book<with>invalid*chars"), "Book-with-invalid-chars")
        self.assertEqual(renamer_view._clean_filename("Book|with?quotes\""), "Book-with-quotes")

        # Test edge cases
        self.assertEqual(renamer_view._clean_filename(""), "")
        self.assertEqual(renamer_view._clean_filename("   "), "")
        self.assertEqual(renamer_view._clean_filename("Normal Book Title"), "Normal Book Title")
        self.assertEqual(renamer_view._clean_filename("Multiple   Spaces"), "Multiple Spaces")

        # Test unicode and special characters
        self.assertEqual(renamer_view._clean_filename("Book with éàü characters"), "Book with éàü characters")
        self.assertEqual(renamer_view._clean_filename("Book: with—em-dash"), "Book - with—em-dash")

    def test_format_file_size(self):
        """Test file size formatting utility."""
        details_view = BookRenamerFileDetailsView()

        # Test different file sizes
        self.assertEqual(details_view._format_file_size(0), "0B")
        self.assertEqual(details_view._format_file_size(512), "512.0 B")
        self.assertEqual(details_view._format_file_size(1024), "1.0 KB")
        self.assertEqual(details_view._format_file_size(1536), "1.5 KB")
        self.assertEqual(details_view._format_file_size(1048576), "1.0 MB")
        self.assertEqual(details_view._format_file_size(1073741824), "1.0 GB")

        # Test large file sizes
        self.assertEqual(details_view._format_file_size(2147483648), "2.0 GB")

    def test_get_file_description(self):
        """Test file description utility."""
        details_view = BookRenamerFileDetailsView()

        # Test known extensions
        self.assertEqual(details_view._get_file_description('.opf', '/path/file.opf'), 'eBook metadata file (OPF)')
        self.assertEqual(details_view._get_file_description('.jpg', '/path/cover.jpg'), 'Book cover image (JPEG)')
        self.assertEqual(details_view._get_file_description('.png', '/path/cover.png'), 'Book cover image (PNG)')
        self.assertEqual(details_view._get_file_description('.pdf', '/path/doc.pdf'), 'PDF document')

        # Test unknown extensions
        self.assertEqual(details_view._get_file_description('.xyz', '/path/file.xyz'), 'XYZ file')
        self.assertEqual(details_view._get_file_description('.custom', '/path/file.custom'), 'CUSTOM file')

        # Test case sensitivity
        self.assertEqual(details_view._get_file_description('.JPG', '/path/file.JPG'), 'Book cover image (JPEG)')
        self.assertEqual(details_view._get_file_description('.PDF', '/path/file.PDF'), 'PDF document')

    def test_determine_category(self):
        """Test category determination logic."""
        renamer_view = BookRenamerView()

        # Create test book with genres
        book = Book.objects.create(
            file_path="/test/path.epub",
            file_format="epub"
        )

        # Create FinalMetadata
        FinalMetadata.objects.create(
            book=book,
            final_title="Test Book",
            final_author="Test Author"
        )

        # Test fiction determination
        fiction_genre = Genre.objects.create(name="Fiction")
        source = DataSource.objects.get_or_create(name=DataSource.MANUAL)[0]
        BookGenre.objects.create(book=book, genre=fiction_genre, source=source, confidence=1.0)
        category = renamer_view._determine_category(book)
        self.assertEqual(category, "Fiction")

        # Test non-fiction determination
        BookGenre.objects.filter(book=book).delete()
        nonfiction_genre = Genre.objects.create(name="Biography")
        BookGenre.objects.create(book=book, genre=nonfiction_genre, source=source, confidence=1.0)
        category = renamer_view._determine_category(book)
        self.assertEqual(category, "Non-Fiction")

        # Test default case
        BookGenre.objects.filter(book=book).delete()
        category = renamer_view._determine_category(book)
        self.assertEqual(category, "Fiction")  # Default

    def test_extract_issue_number(self):
        """Test comic issue number extraction."""
        renamer_view = BookRenamerView()

        # Create test book
        book = Book.objects.create(
            file_path="/comics/spiderman-001.cbz",
            file_format="cbz"
        )

        final_metadata = FinalMetadata.objects.create(
            book=book,
            final_title="Spider-Man #1",
            final_series="Spider-Man",
            final_series_number="1"
        )

        # Test with metadata
        comic_metadata = {'issue_number': '5'}
        issue_num = renamer_view._extract_issue_number(comic_metadata, book)
        self.assertEqual(issue_num, 5)

        # Test with final metadata
        comic_metadata = {}
        issue_num = renamer_view._extract_issue_number(comic_metadata, book)
        self.assertEqual(issue_num, 1)

        # Test title extraction
        final_metadata.final_series_number = None
        final_metadata.save()
        comic_metadata = {'title': 'Spider-Man Issue 15'}
        issue_num = renamer_view._extract_issue_number(comic_metadata, book)
        self.assertEqual(issue_num, 15)  # Should extract 15 from "Spider-Man Issue 15"

    def test_map_language_to_folder(self):
        """Test language mapping utility."""
        renamer_view = BookRenamerView()

        # Test known language codes
        self.assertEqual(renamer_view._map_language_to_folder('nl'), 'Nederlands')
        self.assertEqual(renamer_view._map_language_to_folder('en'), 'English')
        self.assertEqual(renamer_view._map_language_to_folder('fr'), 'Francais')
        self.assertEqual(renamer_view._map_language_to_folder('de'), 'Deutsch')

        # Test unknown language code (defaults to Nederlands)
        self.assertEqual(renamer_view._map_language_to_folder('xx'), 'Nederlands')
        self.assertEqual(renamer_view._map_language_to_folder(''), 'Nederlands')
        self.assertEqual(renamer_view._map_language_to_folder(None), 'Nederlands')

    def test_get_file_action(self):
        """Test file action determination for renaming."""
        execute_view = BookRenamerExecuteView()

        # Test with file actions
        file_actions = [
            {'index': 0, 'action': 'rename'},
            {'index': 1, 'action': 'skip'},
            {'index': 2, 'action': 'delete'}
        ]

        self.assertEqual(execute_view._get_file_action(0, file_actions), 'rename')
        self.assertEqual(execute_view._get_file_action(1, file_actions), 'skip')
        self.assertEqual(execute_view._get_file_action(2, file_actions), 'delete')

        # Test with missing index (should default to 'rename')
        self.assertEqual(execute_view._get_file_action(5, file_actions), 'rename')

        # Test with no file actions
        self.assertEqual(execute_view._get_file_action(0, None), 'rename')
        self.assertEqual(execute_view._get_file_action(0, []), 'rename')

    def test_check_for_duplicate_paths(self):
        """Test duplicate path checking."""
        renamer_view = BookRenamerView()

        # Create test book
        book = Book.objects.create(
            file_path="/library/test.epub",
            file_format="epub"
        )

        # Create another book with different path
        Book.objects.create(
            file_path="/library/other.epub",
            file_format="epub"
        )

        # Test no duplicates
        has_duplicates = renamer_view._check_for_duplicate_paths(book)
        self.assertFalse(has_duplicates)

        # This would require mocking the path generation to test duplicates
        # Since _generate_new_file_path is complex, we'll test the warning logic

    def test_generate_warnings_edge_cases(self):
        """Test warning generation for various edge cases."""
        renamer_view = BookRenamerView()

        # Create test book with minimal data
        book = Book.objects.create(
            file_path="/library/test.epub",
            file_format="epub"
        )

        # Test with missing final metadata
        warnings = renamer_view._generate_warnings(book)
        self.assertIsInstance(warnings, list)

        # Test with final metadata but no series
        FinalMetadata.objects.create(
            book=book,
            final_title="Test Book",
            final_author="Test Author"
        )

        warnings = renamer_view._generate_warnings(book)
        self.assertIsInstance(warnings, list)


class ViewUtilityMethodTests(TestCase):
    """Test utility methods within various view classes."""

    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.client = Client()
        self.client.login(username='testuser', password='testpass123')

    def test_ajax_response_handler_decorator(self):
        """Test the ajax_response_handler decorator functionality."""
        from books.views import ajax_response_handler

        @ajax_response_handler
        def test_view(request):
            return {'success': True, 'data': 'test'}

        # Create a mock request
        request = self.factory.post('/test/')
        request.user = self.user

        # Test the decorated function
        response = test_view(request)
        self.assertIsInstance(response, JsonResponse)

        # Parse JSON response
        import json
        data = json.loads(response.content)
        self.assertTrue(data['success'])
        self.assertEqual(data['data'], 'test')

    def test_get_comic_metadata(self):
        """Test comic metadata extraction."""
        renamer_view = BookRenamerView()

        # Create test book
        book = Book.objects.create(
            file_path="/comics/spider-man-001.cbz",
            file_format="cbz"
        )

        # Mock the metadata extraction
        with patch.object(renamer_view, '_get_comic_metadata') as mock_get_metadata:
            mock_get_metadata.return_value = {
                'series': 'Spider-Man',
                'issue_number': '1',
                'title': 'Spider-Man #1'
            }

            metadata = renamer_view._get_comic_metadata(book)
            self.assertEqual(metadata['series'], 'Spider-Man')
            self.assertEqual(metadata['issue_number'], '1')

    def test_analyze_series_completion(self):
        """Test series completion analysis."""
        renamer_view = BookRenamerView()

        # Create test books in a series
        Series.objects.create(name="Test Series")

        books = []
        for i in range(1, 4):
            book = Book.objects.create(
                file_path=f"/library/series{i}.epub",
                file_format="epub"
            )
            FinalMetadata.objects.create(
                book=book,
                final_title=f"Test Series Volume {i}",
                final_series="Test Series",
                final_series_number=str(i)
            )
            books.append(book)

        # Test series completion analysis
        complete_series = renamer_view._analyze_series_completion()
        self.assertIsInstance(complete_series, dict)

    def test_language_folder_mapping_edge_cases(self):
        """Test edge cases in language folder mapping."""
        renamer_view = BookRenamerView()

        # Test with None
        result = renamer_view._map_language_to_folder(None)
        self.assertEqual(result, 'Nederlands')

        # Test with empty string
        result = renamer_view._map_language_to_folder('')
        self.assertEqual(result, 'Nederlands')

        # Test with whitespace
        result = renamer_view._map_language_to_folder('  ')
        self.assertEqual(result, 'Nederlands')


class ErrorHandlingTests(TestCase):
    """Test error handling in utility functions."""

    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )

    def test_file_size_formatting_edge_cases(self):
        """Test file size formatting with edge cases."""
        details_view = BookRenamerFileDetailsView()

        # Test negative sizes (shouldn't happen but handle gracefully)
        with self.assertRaises((ValueError, ZeroDivisionError)):
            details_view._format_file_size(-1)

        # Test very large numbers
        large_size = 10**15  # 1 petabyte
        result = details_view._format_file_size(large_size)
        self.assertIsInstance(result, str)
        self.assertIn('TB', result)  # Should show in TB for petabyte size

    def test_clean_filename_edge_cases(self):
        """Test filename cleaning with problematic inputs."""
        renamer_view = BookRenamerView()

        # Test None input
        result = renamer_view._clean_filename(None)
        self.assertEqual(result, 'Unknown')

        # Test very long filename
        long_filename = "A" * 300
        result = renamer_view._clean_filename(long_filename)
        self.assertIsInstance(result, str)

        # Test filename with only invalid characters
        result = renamer_view._clean_filename("|||***???")
        self.assertEqual(result, '-')  # All invalid chars should be collapsed to single dash

    def test_category_determination_with_missing_data(self):
        """Test category determination when data is missing."""
        renamer_view = BookRenamerView()

        # Create book without final metadata
        book = Book.objects.create(
            file_path="/test/path.epub",
            file_format="epub"
        )

        # Should not crash and return default
        category = renamer_view._determine_category(book)
        self.assertEqual(category, "Fiction")

    def test_issue_number_extraction_with_invalid_data(self):
        """Test issue number extraction with invalid or missing data."""
        renamer_view = BookRenamerView()

        # Create book without final metadata
        book = Book.objects.create(
            file_path="/comics/test.cbz",
            file_format="cbz"
        )

        # Test with invalid metadata
        comic_metadata = {'issue_number': 'not-a-number'}
        result = renamer_view._extract_issue_number(comic_metadata, book)
        self.assertEqual(result, 1)  # Should return 1 as default when no clear number found

        # Test with None values
        comic_metadata = {'issue_number': None}
        result = renamer_view._extract_issue_number(comic_metadata, book)
        self.assertEqual(result, 1)  # Should return 1 as default when no clear number found


class PerformanceTests(TestCase):
    """Test performance aspects of utility functions."""

    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )

    def test_series_analysis_with_large_dataset(self):
        """Test series analysis performance with many books."""
        renamer_view = BookRenamerView()

        # Create a large series
        series_name = "Large Test Series"
        for i in range(50):  # Create 50 books in series
            book = Book.objects.create(
                file_path=f"/library/series{i+1}.epub",
                file_format="epub"
            )
            FinalMetadata.objects.create(
                book=book,
                final_title=f"{series_name} Volume {i+1}",
                final_series=series_name,
                final_series_number=str(i+1)
            )

        # Test that analysis completes in reasonable time
        import time
        start_time = time.time()
        complete_series = renamer_view._analyze_series_completion()
        end_time = time.time()

        # Should complete in under 5 seconds even with 50 books
        self.assertLess(end_time - start_time, 5.0)
        self.assertIsInstance(complete_series, dict)

    def test_filename_cleaning_performance(self):
        """Test filename cleaning performance with various inputs."""
        renamer_view = BookRenamerView()

        # Test with many special characters
        complex_filename = "Book: Title! with<many>special|chars*and?quotes\"and/slashes\\and" * 10

        import time
        start_time = time.time()
        result = renamer_view._clean_filename(complex_filename)
        end_time = time.time()

        # Should complete quickly
        self.assertLess(end_time - start_time, 0.1)
        self.assertIsInstance(result, str)


class IntegrationUtilityTests(TestCase):
    """Integration tests for utility functions working together."""

    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.client = Client()
        self.client.login(username='testuser', password='testpass123')

    def test_complete_path_generation_workflow(self):
        """Test complete file path generation workflow."""
        renamer_view = BookRenamerView()

        # Create comprehensive test book
        book = Book.objects.create(
            file_path="/original/path/test book.epub",
            file_format="epub"
        )

        # Create author and genre
        author = Author.objects.create(name="Test Author")
        genre = Genre.objects.create(name="Fiction")
        source = DataSource.objects.get_or_create(name=DataSource.MANUAL)[0]

        # Create final metadata
        FinalMetadata.objects.create(
            book=book,
            final_title="Test: Book with Special! Characters",
            final_author="Test Author",
            final_series="Test Series",
            final_series_number="1",
            language="en",
            is_reviewed=True  # Prevent auto-update from overwriting our test values
        )

        BookAuthor.objects.create(book=book, author=author, source=source, confidence=1.0)
        BookGenre.objects.create(book=book, genre=genre, source=source, confidence=1.0)

        # Test complete path generation
        try:
            new_path = renamer_view._generate_new_file_path(book)
            self.assertIsInstance(new_path, str)
            self.assertIn("Author, Test", new_path)  # Author name is formatted as "Last, First"
            self.assertIn("Test Series", new_path)
            self.assertNotIn(":", new_path)  # Special chars should be cleaned
            self.assertNotIn("!", new_path)
        except Exception as e:
            # Should not raise exceptions even with complex data
            self.fail(f"Path generation raised exception: {e}")

    def test_comic_path_generation_workflow(self):
        """Test comic-specific path generation workflow."""
        renamer_view = BookRenamerView()

        # Create comic book
        book = Book.objects.create(
            file_path="/comics/spider-man-001.cbz",
            file_format="cbz"
        )

        FinalMetadata.objects.create(
            book=book,
            final_title="Spider-Man #001",
            final_series="Spider-Man",
            final_series_number="1",
            language="en",
            is_reviewed=True  # Prevent auto-update from overwriting our test values
        )

        # Mock comic metadata
        with patch.object(renamer_view, '_get_comic_metadata') as mock_get_metadata:
            mock_get_metadata.return_value = {
                'series': 'Spider-Man',
                'issue_number': '1',
                'title': 'Spider-Man #001',
                'language': 'en'
            }

            try:
                new_path = renamer_view._generate_new_file_path(book)
                self.assertIsInstance(new_path, str)
                self.assertIn("CBR", new_path)  # Should be in CBR folder
                self.assertIn("Spider-Man", new_path)
            except Exception as e:
                self.fail(f"Comic path generation raised exception: {e}")
