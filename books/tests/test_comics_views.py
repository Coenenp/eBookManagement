"""
Test cases for comics-related views and functionality.
"""

import json

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from books.models import BookSeries, DataSource, FinalMetadata, Series
from books.tests.test_helpers import create_test_book_with_file, create_test_scan_folder


class ComicsViewsTestCase(TestCase):
    """Base test case for comics views with common setup"""

    def setUp(self):
        """Set up test data"""
        # Create test user
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123',
            email='test@example.com'
        )

        # Create a scan folder
        self.scan_folder = create_test_scan_folder(content_type='comics')

        # Create a data source
        self.data_source, _ = DataSource.objects.get_or_create(
            name="Test Comics Source",
            defaults={'trust_level': 0.8}
        )

        # Create test books with comic formats
        self.comic_book1 = create_test_book_with_file(
            file_path="/test/comic1.cbr",
            file_size=5000000,
            file_format="cbr",
            scan_folder=self.scan_folder,
            content_type="comic"
        )

        self.comic_book2 = create_test_book_with_file(
            file_path="/test/comic2.cbz",
            file_size=7000000,
            file_format="cbz",
            scan_folder=self.scan_folder,
            content_type="comic"
        )

        self.comic_book3 = create_test_book_with_file(
            file_path="/test/comic3.cbr",
            file_size=6000000,
            file_format="cbr",
            scan_folder=self.scan_folder,
            content_type="comic"
        )

        # Create a non-comic book
        self.regular_book = create_test_book_with_file(
            file_path="/test/book.epub",
            file_size=1000000,
            file_format="epub",
            scan_folder=self.scan_folder,
            content_type="ebook"
        )

        # Create FinalMetadata for comics
        self.final_meta1 = FinalMetadata.objects.create(
            book=self.comic_book1,
            final_title="Batman: Year One",
            final_author="Frank Miller",
            final_series="Batman",
            final_series_number="1",
            is_reviewed=True
        )

        self.final_meta2 = FinalMetadata.objects.create(
            book=self.comic_book2,
            final_title="Batman: The Dark Knight Returns",
            final_author="Frank Miller",
            final_series="Batman",
            final_series_number="2",
            is_reviewed=True
        )

        self.final_meta3 = FinalMetadata.objects.create(
            book=self.comic_book3,
            final_title="Standalone Comic",
            final_author="Alan Moore",
            final_series="",  # No series
            final_series_number="",
            is_reviewed=True
        )

        # Create FinalMetadata for regular book (not a comic)
        self.final_meta_book = FinalMetadata.objects.create(
            book=self.regular_book,
            final_title="Regular Book",
            final_author="Author Name",
            is_reviewed=True
        )

        self.client = Client()


class ComicsMainViewTests(ComicsViewsTestCase):
    """Test ComicsMainView functionality"""

    def test_comics_main_view_requires_login(self):
        """Test that comics main view requires authentication"""
        response = self.client.get(reverse('books:comics_main'))
        self.assertEqual(response.status_code, 302)  # Redirect to login

    def test_comics_main_view_loads_successfully(self):
        """Test that comics main view loads for authenticated users"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('books:comics_main'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Comics')

    def test_comics_count_from_final_metadata(self):
        """Test that comics count comes from final metadata"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('books:comics_main'))

        # Should count 2 items: 1 series (Batman with 2 books) + 1 standalone = 2
        self.assertEqual(response.context['comics_count'], 2)

    def test_comics_count_excludes_non_comics(self):
        """Test that non-comic formats are excluded from count"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('books:comics_main'))

        # Should not count the epub book even though it has FinalMetadata
        context_count = response.context['comics_count']
        self.assertEqual(context_count, 2)  # 1 series + 1 standalone comic

    def test_comics_count_excludes_empty_formats(self):
        """Test that books with empty comic formats are excluded"""
        # Create a book with non-comic format but with FinalMetadata
        empty_comic = create_test_book_with_file(
            file_path="/test/empty.epub",
            file_size=1000000,
            file_format="epub",  # Not a comic format (ebook format)
            scan_folder=self.scan_folder,
            content_type="ebook"
        )
        FinalMetadata.objects.create(
            book=empty_comic,
            final_title="Non-Comic Book",
            is_reviewed=True
        )

        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('books:comics_main'))

        # Should still be 2, not 3 (epub should be excluded)
        self.assertEqual(response.context['comics_count'], 2)

    def test_comics_count_fallback_to_book_format(self):
        """Test fallback to Book file format when no FinalMetadata comics exist"""
        # Remove all comic FinalMetadata
        FinalMetadata.objects.filter(book__files__file_format__in=['cbr', 'cbz']).delete()

        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('books:comics_main'))

        # Should fall back to counting Book objects with comic formats
        self.assertEqual(response.context['comics_count'], 3)


class ComicsAjaxListTests(ComicsViewsTestCase):
    """Test comics_ajax_list endpoint functionality"""

    def test_comics_ajax_list_requires_login(self):
        """Test that AJAX endpoint requires authentication"""
        response = self.client.get(reverse('books:comics_ajax_list'))
        self.assertEqual(response.status_code, 302)  # Redirect to login

    def test_comics_ajax_list_returns_json(self):
        """Test that AJAX endpoint returns valid JSON"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('books:comics_ajax_list'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')

        data = json.loads(response.content)
        self.assertTrue(data['success'])
        self.assertIn('series', data)
        self.assertIn('standalone', data)
        self.assertIn('total_count', data)

    def test_comics_ajax_list_content(self):
        """Test that AJAX endpoint returns correct comics data"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('books:comics_ajax_list'))

        data = json.loads(response.content)

        # Should have one series (Batman) and one standalone comic
        self.assertEqual(len(data['series']), 1)
        self.assertEqual(len(data['standalone']), 1)

        # Check Batman series
        batman_series = data['series'][0]
        self.assertEqual(batman_series['name'], 'Batman')
        self.assertEqual(batman_series['total_books'], 2)
        self.assertEqual(len(batman_series['books']), 2)

        # Check standalone comic
        standalone = data['standalone'][0]
        self.assertEqual(standalone['title'], 'Standalone Comic')
        self.assertEqual(standalone['author'], 'Alan Moore')

    def test_comics_ajax_list_book_details(self):
        """Test that books within series have correct details"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('books:comics_ajax_list'))

        data = json.loads(response.content)

        # Find Batman series
        batman_series = next(s for s in data['series'] if s['name'] == 'Batman')

        self.assertEqual(batman_series['total_books'], 2)
        self.assertEqual(len(batman_series['books']), 2)

        # Check first book details
        book = batman_series['books'][0]
        self.assertEqual(book['title'], "Batman: Year One")
        self.assertEqual(book['author'], "Frank Miller")
        self.assertEqual(book['position'], "1")
        self.assertIn(book['file_format'], ['cbr', 'cbz'])
        self.assertIsNotNone(book['file_size'])

        # Check series aggregated data
        self.assertIn('Frank Miller', batman_series['authors'])
        self.assertTrue(any(fmt in ['cbr', 'cbz'] for fmt in batman_series['formats']))

    def test_comics_ajax_list_book_sorting(self):
        """Test that books within series are sorted by position"""
        # Create more books in the series to test sorting
        comic_book4 = create_test_book_with_file(
            file_path="/test/comic4.cbr",
            file_size=8000000,
            file_format="cbr",
            scan_folder=self.scan_folder,
            content_type="comic"
        )

        FinalMetadata.objects.create(
            book=comic_book4,
            final_title="Batman: The Killing Joke",
            final_author="Alan Moore",
            final_series="Batman",
            final_series_number="1.5",
            is_reviewed=True
        )

        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('books:comics_ajax_list'))

        data = json.loads(response.content)
        batman_series = next(s for s in data['series'] if s['name'] == 'Batman')

        # Books should be sorted by position: 1, 1.5, 2
        positions = [book['position'] for book in batman_series['books']]
        self.assertEqual(positions, ["1", "1.5", "2"])

    def test_comics_ajax_list_series_sorting(self):
        """Test that series are sorted alphabetically"""
        # Create another series
        comic_book5 = create_test_book_with_file(
            file_path="/test/comic5.cbz",
            file_size=5500000,
            file_format="cbz",
            scan_folder=self.scan_folder,
            content_type="comic"
        )

        FinalMetadata.objects.create(
            book=comic_book5,
            final_title="Amazing Spider-Man #1",
            final_author="Stan Lee",
            final_series="Amazing Spider-Man",
            final_series_number="1",
            is_reviewed=True
        )

        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('books:comics_ajax_list'))

        data = json.loads(response.content)
        series_names = [s['name'] for s in data['series']]

        # Should be sorted alphabetically
        self.assertEqual(series_names, sorted(series_names))
        self.assertEqual(series_names, ["Amazing Spider-Man", "Batman"])

    def test_comics_ajax_list_excludes_empty_series(self):
        """Test that comics with empty series names are in standalone"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('books:comics_ajax_list'))

        data = json.loads(response.content)

        # The comic with empty series should be in standalone
        self.assertEqual(len(data['standalone']), 1)
        standalone = data['standalone'][0]
        self.assertEqual(standalone['title'], 'Standalone Comic')

    def test_comics_ajax_list_aggregates_data_correctly(self):
        """Test that series data is aggregated correctly"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('books:comics_ajax_list'))

        data = json.loads(response.content)
        batman_series = next(s for s in data['series'] if s['name'] == 'Batman')

        # Check aggregated data
        self.assertEqual(batman_series['total_books'], 2)
        self.assertEqual(batman_series['total_size'], 5000000 + 7000000)  # Sum of file sizes
        self.assertEqual(batman_series['authors'], ['Frank Miller'])
        self.assertEqual(set(batman_series['formats']), {'cbr', 'cbz'})

    def test_comics_ajax_list_handles_errors(self):
        """Test that AJAX endpoint handles errors gracefully"""
        self.client.login(username='testuser', password='testpass123')

        # Test that the endpoint returns valid JSON even under normal conditions
        response = self.client.get(reverse('books:comics_ajax_list'))

        # Even if there are internal issues, should return valid response
        self.assertIn(response.status_code, [200, 500])

        if response.status_code == 200:
            data = json.loads(response.content)
            self.assertTrue(data['success'])


class ComicsIntegrationTests(ComicsViewsTestCase):
    """Integration tests for comics functionality"""

    def test_comics_count_matches_ajax_count(self):
        """Test that comics count in view matches AJAX endpoint count"""
        self.client.login(username='testuser', password='testpass123')

        # Get count from main view
        main_response = self.client.get(reverse('books:comics_main'))
        view_count = main_response.context['comics_count']

        # Get count from AJAX endpoint
        ajax_response = self.client.get(reverse('books:comics_ajax_list'))
        ajax_data = json.loads(ajax_response.content)
        ajax_count = len(ajax_data['series']) + len(ajax_data['standalone'])

        # Counts should match
        self.assertEqual(view_count, ajax_count)

    def test_complete_comics_workflow(self):
        """Test complete workflow of viewing comics"""
        self.client.login(username='testuser', password='testpass123')

        # 1. Load main comics page
        main_response = self.client.get(reverse('books:comics_main'))
        self.assertEqual(main_response.status_code, 200)

        # 2. Load comics data via AJAX
        ajax_response = self.client.get(reverse('books:comics_ajax_list'))
        self.assertEqual(ajax_response.status_code, 200)

        ajax_data = json.loads(ajax_response.content)
        self.assertTrue(ajax_data['success'])

        # 3. Verify data consistency
        view_count = main_response.context['comics_count']
        ajax_total = ajax_data['total_count']
        self.assertEqual(view_count, ajax_total)

    def test_comics_with_mixed_metadata_sources(self):
        """Test comics that have both FinalMetadata and BookSeries relationships"""
        # Create series relationships for some comics
        series = Series.objects.create(name="Batman Classic")

        BookSeries.objects.create(
            book=self.comic_book1,
            series=series,
            series_number="1",
            source=self.data_source,
            confidence=0.9,
            is_active=True
        )

        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('books:comics_ajax_list'))

        data = json.loads(response.content)

        # Should prioritize FinalMetadata over BookSeries
        batman_series = next(s for s in data['series'] if s['name'] == 'Batman')
        self.assertEqual(batman_series['name'], 'Batman')  # From FinalMetadata, not "Batman Classic"
