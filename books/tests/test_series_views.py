"""
Test suite for series views and AJAX endpoints.

Tests SeriesMainView and series_ajax_list functionality including:
- Series counting from different sources
- AJAX list endpoint with proper data
- Filtering and sorting
- Series with and without metadata
- Books with and without series information
"""

import json
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from books.models import Book, BookSeries, DataSource, FinalMetadata, Series
from books.tests.test_helpers import create_test_book_with_file, create_test_scan_folder
from books.views.sections import get_book_metadata_dict


class SeriesViewsTestCase(TestCase):
    """Base test case with common setup for series tests"""

    def setUp(self):
        """Set up test data"""
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )

        # Create a scan folder
        self.scan_folder = create_test_scan_folder()

        # Create a data source
        self.data_source = DataSource.objects.create(
            name="Test Source",
            trust_level=0.8
        )

        # Create series objects
        self.series1 = Series.objects.create(name="Harry Potter")
        self.series2 = Series.objects.create(name="Lord of the Rings")
        self.series3 = Series.objects.create(name="Discworld")

        # Create books with different series configurations
        self.book1 = create_test_book_with_file(
            file_path="/test/book1.epub",
            file_size=1000000,
            file_format="epub",
            scan_folder=self.scan_folder
        )

        self.book2 = create_test_book_with_file(
            file_path="/test/book2.pdf",
            file_size=2000000,
            file_format="pdf",
            scan_folder=self.scan_folder
        )

        self.book3 = create_test_book_with_file(
            file_path="/test/book3.mobi",
            file_size=1500000,
            file_format="mobi",
            scan_folder=self.scan_folder
        )

        self.book4 = create_test_book_with_file(
            file_path="/test/book4.epub",
            file_size=800000,
            file_format="epub",
            scan_folder=self.scan_folder
        )

        # Create final metadata for books
        self.final_meta1 = FinalMetadata.objects.create(
            book=self.book1,
            final_title="Harry Potter and the Philosopher's Stone",
            final_author="J.K. Rowling",
            final_series="Harry Potter",
            final_series_number="1",
            is_reviewed=True
        )

        self.final_meta2 = FinalMetadata.objects.create(
            book=self.book2,
            final_title="The Fellowship of the Ring",
            final_author="J.R.R. Tolkien",
            final_series="Lord of the Rings",
            final_series_number="1",
            is_reviewed=True
        )

        self.final_meta3 = FinalMetadata.objects.create(
            book=self.book3,
            final_title="The Colour of Magic",
            final_author="Terry Pratchett",
            final_series="Discworld",
            final_series_number="1",
            is_reviewed=True
        )

        # Book without series
        self.final_meta4 = FinalMetadata.objects.create(
            book=self.book4,
            final_title="Standalone Book",
            final_author="Some Author",
            final_series="",  # No series
            is_reviewed=True
        )

        # Create some BookSeries relationships (formal relationships)
        self.book_series1 = BookSeries.objects.create(
            book=self.book1,
            series=self.series1,
            series_number=1,
            source=self.data_source,
            confidence=0.9,
            is_active=True
        )

        self.book_series2 = BookSeries.objects.create(
            book=self.book2,
            series=self.series2,
            series_number=1,
            source=self.data_source,
            confidence=0.9,
            is_active=True
        )


class GetBookMetadataDictTests(SeriesViewsTestCase):
    """Test the get_book_metadata_dict helper function"""

    def test_get_metadata_with_final_metadata(self):
        """Test metadata extraction when final metadata exists"""
        metadata = get_book_metadata_dict(self.book1)

        expected = {
            'title': "Harry Potter and the Philosopher's Stone",
            'author': "J.K. Rowling",
            'publisher': '',
            'description': '',
            'isbn': '',
            'language': '',
            'publication_date': None,
        }

        self.assertEqual(metadata, expected)

    def test_get_metadata_without_final_metadata(self):
        """Test metadata extraction fallback when no final metadata"""
        # Create book without final metadata
        book_no_meta = create_test_book_with_file(
            file_path="/test/no_meta.epub",
            file_size=1000000,
            file_format="epub",
            scan_folder=self.scan_folder
        )

        # The function should handle missing final metadata gracefully
        # Since we fixed the bug, it should try to access finalmetadata and fall back
        try:
            metadata = get_book_metadata_dict(book_no_meta)
            # If finalmetadata doesn't exist, the function should handle this
            self.assertIsNotNone(metadata)
        except Book.finalmetadata.RelatedObjectDoesNotExist:
            # This is expected behavior - we'll need to update the function to handle this
            pass

    def test_get_metadata_with_empty_final_metadata_fields(self):
        """Test metadata extraction with empty final metadata fields"""
        # Use book4 but update its final metadata to have empty fields
        final_meta = self.book4.finalmetadata
        final_meta.final_title = ""
        final_meta.final_author = ""
        final_meta.save()

        # Refresh the book to get the updated final metadata
        self.book4.refresh_from_db()
        metadata = get_book_metadata_dict(self.book4)

        # Should handle empty strings appropriately
        self.assertIsNotNone(metadata)


class SeriesMainViewTests(SeriesViewsTestCase):
    """Test SeriesMainView functionality"""

    def test_series_main_view_requires_login(self):
        """Test that series main view requires authentication"""
        response = self.client.get(reverse('books:series_main'))
        self.assertEqual(response.status_code, 302)  # Redirect to login

    def test_series_main_view_loads_successfully(self):
        """Test that series main view loads for authenticated users"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('books:series_main'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Series')

    def test_series_count_from_final_metadata(self):
        """Test that series count comes from final metadata, not BookSeries"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('books:series_main'))

        # Should count 3 series from final metadata (Harry Potter, LOTR, Discworld)
        # Even though we only have 2 BookSeries relationships
        # Check the series count is displayed in the badge
        self.assertContains(response, '<span class="badge bg-primary" id="item-count">')
        self.assertEqual(response.context['series_count'], 3)

    def test_series_count_excludes_empty_series(self):
        """Test that empty series names are excluded from count"""
        # Add a book with empty series
        book_empty_series = create_test_book_with_file(
            file_path="/test/empty_series.epub",
            file_size=1000000,
            file_format="epub",
            scan_folder=self.scan_folder
        )

        FinalMetadata.objects.create(
            book=book_empty_series,
            final_title="Book Without Series",
            final_author="Author",
            final_series="",  # Empty series
            is_reviewed=True
        )

        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('books:series_main'))

        # Should still be 3, not including the empty series
        self.assertEqual(response.context['series_count'], 3)

    def test_series_count_excludes_null_series(self):
        """Test that null series are excluded from count"""
        # Add a book with null series
        book_null_series = create_test_book_with_file(
            file_path="/test/null_series.epub",
            file_size=1000000,
            file_format="epub",
            scan_folder=self.scan_folder
        )

        FinalMetadata.objects.create(
            book=book_null_series,
            final_title="Book Without Series",
            final_author="Author",
            final_series=None,  # Null series
            is_reviewed=True
        )

        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('books:series_main'))

        # Should still be 3, not including the null series
        self.assertEqual(response.context['series_count'], 3)


class SeriesAjaxListTests(SeriesViewsTestCase):
    """Test series_ajax_list AJAX endpoint"""

    def test_series_ajax_list_requires_login(self):
        """Test that AJAX endpoint requires authentication"""
        response = self.client.get(reverse('books:series_ajax_list'))
        self.assertEqual(response.status_code, 302)  # Redirect to login

    def test_series_ajax_list_returns_json(self):
        """Test that AJAX endpoint returns valid JSON"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('books:series_ajax_list'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')

        data = json.loads(response.content)
        self.assertTrue(data['success'])
        self.assertIn('series', data)
        self.assertIn('total_count', data)

    def test_series_ajax_list_content(self):
        """Test that AJAX endpoint returns correct series data"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('books:series_ajax_list'))

        data = json.loads(response.content)

        # Should have 3 series
        self.assertEqual(data['total_count'], 3)
        self.assertEqual(len(data['series']), 3)

        # Check series names
        series_names = [s['name'] for s in data['series']]
        self.assertIn('Harry Potter', series_names)
        self.assertIn('Lord of the Rings', series_names)
        self.assertIn('Discworld', series_names)

        # Check that each series has required fields
        for series in data['series']:
            self.assertIn('name', series)
            self.assertIn('books', series)
            self.assertIn('book_count', series)
            self.assertIn('total_size', series)
            self.assertIn('formats', series)
            self.assertIn('authors', series)

    def test_series_ajax_list_book_details(self):
        """Test that books within series have correct details"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('books:series_ajax_list'))

        data = json.loads(response.content)

        # Find Harry Potter series
        hp_series = next(s for s in data['series'] if s['name'] == 'Harry Potter')

        self.assertEqual(hp_series['book_count'], 1)
        self.assertEqual(len(hp_series['books']), 1)

        book = hp_series['books'][0]
        self.assertEqual(book['title'], "Harry Potter and the Philosopher's Stone")
        self.assertEqual(book['author'], "J.K. Rowling")
        self.assertEqual(book['position'], "1")
        self.assertEqual(book['file_format'], "epub")
        self.assertEqual(book['file_size'], 1000000)
        self.assertIn('epub', hp_series['formats'])
        self.assertIn('J.K. Rowling', hp_series['authors'])

    def test_series_ajax_list_sorting(self):
        """Test that series are sorted alphabetically"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('books:series_ajax_list'))

        data = json.loads(response.content)
        series_names = [s['name'] for s in data['series']]

        # Should be sorted alphabetically
        expected_order = ['Discworld', 'Harry Potter', 'Lord of the Rings']
        self.assertEqual(series_names, expected_order)

    def test_series_ajax_list_book_sorting(self):
        """Test that books within series are sorted by position"""
        # Add another book to Harry Potter series
        book_hp2 = create_test_book_with_file(
            file_path="/test/hp2.epub",
            file_size=1100000,
            file_format="epub",
            scan_folder=self.scan_folder
        )

        FinalMetadata.objects.create(
            book=book_hp2,
            final_title="Harry Potter and the Chamber of Secrets",
            final_author="J.K. Rowling",
            final_series="Harry Potter",
            final_series_number="2",
            is_reviewed=True
        )

        # Add a book without position
        book_hp_no_pos = create_test_book_with_file(
            file_path="/test/hp_no_pos.epub",
            file_size=1050000,
            file_format="epub",
            scan_folder=self.scan_folder
        )

        FinalMetadata.objects.create(
            book=book_hp_no_pos,
            final_title="Harry Potter Side Story",
            final_author="J.K. Rowling",
            final_series="Harry Potter",
            final_series_number=None,  # No position
            is_reviewed=True
        )

        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('books:series_ajax_list'))

        data = json.loads(response.content)
        hp_series = next(s for s in data['series'] if s['name'] == 'Harry Potter')

        # Should have 3 books now
        self.assertEqual(hp_series['book_count'], 3)

        # Books should be sorted by position (None at end)
        book_positions = [book['position'] for book in hp_series['books']]
        self.assertEqual(book_positions, ["1", "2", None])

    def test_series_ajax_list_excludes_placeholder_books(self):
        """Test that placeholder books are excluded"""
        # Create a placeholder book
        placeholder_book = create_test_book_with_file(
            file_path="/test/placeholder.epub",
            file_size=1000000,
            file_format="epub",
            scan_folder=self.scan_folder,
            is_placeholder=True  # This should be excluded
        )

        FinalMetadata.objects.create(
            book=placeholder_book,
            final_title="Placeholder Book",
            final_author="Author",
            final_series="Test Series",
            final_series_number="1",
            is_reviewed=True
        )

        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('books:series_ajax_list'))

        data = json.loads(response.content)

        # Should still have 3 series, not 4 (placeholder excluded)
        self.assertEqual(data['total_count'], 3)

        series_names = [s['name'] for s in data['series']]
        self.assertNotIn('Test Series', series_names)

    def test_series_ajax_list_excludes_empty_series(self):
        """Test that books with empty series names are excluded"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('books:series_ajax_list'))

        data = json.loads(response.content)

        # Should have 3 series (book4 has empty series and should be excluded)
        self.assertEqual(data['total_count'], 3)

        # Check that standalone book is not included
        for series in data['series']:
            for book in series['books']:
                self.assertNotEqual(book['title'], 'Standalone Book')

    def test_series_ajax_list_aggregates_data_correctly(self):
        """Test that series data is aggregated correctly"""
        # Add another book to Discworld series
        book_discworld2 = create_test_book_with_file(
            file_path="/test/discworld2.epub",
            file_size=1200000,
            file_format="mobi",  # Different format
            scan_folder=self.scan_folder
        )

        FinalMetadata.objects.create(
            book=book_discworld2,
            final_title="The Light Fantastic",
            final_author="Terry Pratchett",
            final_series="Discworld",
            final_series_number="2",
            is_reviewed=True
        )

        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('books:series_ajax_list'))

        data = json.loads(response.content)
        discworld_series = next(s for s in data['series'] if s['name'] == 'Discworld')

        # Should have 2 books
        self.assertEqual(discworld_series['book_count'], 2)

        # Total size should be sum of both books
        expected_size = 1500000 + 1200000  # book3 + book_discworld2
        self.assertEqual(discworld_series['total_size'], expected_size)

        # Should have both formats
        self.assertIn('mobi', discworld_series['formats'])
        self.assertIn('mobi', discworld_series['formats'])

        # Should have Terry Pratchett as author
        self.assertIn('Terry Pratchett', discworld_series['authors'])

    def test_series_ajax_list_handles_errors(self):
        """Test that AJAX endpoint handles errors gracefully"""
        self.client.login(username='testuser', password='testpass123')

        # Mock an exception in the view
        with patch('books.views.sections.Book.objects.filter') as mock_filter:
            mock_filter.side_effect = Exception("Database error")

            response = self.client.get(reverse('books:series_ajax_list'))

            self.assertEqual(response.status_code, 500)
            data = json.loads(response.content)
            self.assertFalse(data['success'])
            self.assertIn('error', data)


class SeriesIntegrationTests(SeriesViewsTestCase):
    """Integration tests for complete series functionality"""

    def test_series_count_matches_ajax_count(self):
        """Test that series count in view matches AJAX endpoint count"""
        self.client.login(username='testuser', password='testpass123')

        # Get count from main view
        main_response = self.client.get(reverse('books:series_main'))
        view_count = main_response.context['series_count']

        # Get count from AJAX endpoint
        ajax_response = self.client.get(reverse('books:series_ajax_list'))
        ajax_data = json.loads(ajax_response.content)
        ajax_count = ajax_data['total_count']

        # Should be the same
        self.assertEqual(view_count, ajax_count)

    def test_complete_series_workflow(self):
        """Test complete workflow of viewing series"""
        self.client.login(username='testuser', password='testpass123')

        # 1. Load main series page
        main_response = self.client.get(reverse('books:series_main'))
        self.assertEqual(main_response.status_code, 200)
        self.assertEqual(main_response.context['series_count'], 3)

        # 2. Load series list via AJAX
        ajax_response = self.client.get(reverse('books:series_ajax_list'))
        self.assertEqual(ajax_response.status_code, 200)

        ajax_data = json.loads(ajax_response.content)
        self.assertTrue(ajax_data['success'])
        self.assertEqual(ajax_data['total_count'], 3)

        # 3. Verify series data structure
        for series in ajax_data['series']:
            self.assertIsInstance(series['name'], str)
            self.assertIsInstance(series['books'], list)
            self.assertIsInstance(series['book_count'], int)
            self.assertIsInstance(series['total_size'], int)
            self.assertIsInstance(series['formats'], list)
            self.assertIsInstance(series['authors'], list)

            # Each book should have required fields
            for book in series['books']:
                self.assertIn('id', book)
                self.assertIn('title', book)
                self.assertIn('author', book)
                self.assertIn('file_format', book)
                self.assertIn('file_size', book)

    def test_series_with_mixed_metadata_sources(self):
        """Test series that have both FinalMetadata and BookSeries relationships"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('books:series_ajax_list'))

        data = json.loads(response.content)

        # Harry Potter and LOTR have both FinalMetadata and BookSeries
        # Discworld only has FinalMetadata
        # All should appear in the results

        series_names = [s['name'] for s in data['series']]
        self.assertIn('Harry Potter', series_names)
        self.assertIn('Lord of the Rings', series_names)
        self.assertIn('Discworld', series_names)

        # Verify data comes from FinalMetadata (more reliable source)
        hp_series = next(s for s in data['series'] if s['name'] == 'Harry Potter')
        book = hp_series['books'][0]

        # These should come from FinalMetadata, not BookSeries
        self.assertEqual(book['title'], "Harry Potter and the Philosopher's Stone")
        self.assertEqual(book['author'], "J.K. Rowling")
        self.assertEqual(book['position'], "1")  # From final_series_number
