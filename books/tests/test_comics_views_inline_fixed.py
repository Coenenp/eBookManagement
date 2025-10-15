"""
Test cases for comics-related views and functionality.
"""

import json
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.contrib.auth.models import User
from books.models import FinalMetadata, ScanFolder
from books.tests.test_helpers import create_test_book_with_file


@override_settings(USE_SQLITE_TEMPORARILY=True)
class ComicsMainViewTests(TestCase):
    """Test comics main view functionality."""

    def test_comics_main_view_requires_login(self):
        """Test comics view requires authentication."""
        response = Client().get(reverse('books:comics_main'))
        self.assertEqual(response.status_code, 302)

    def test_comics_main_view_loads_successfully(self):
        """Test comics view loads with authentication."""
        client = Client()
        User.objects.create_user('testuser', password='testpass123')
        client.login(username='testuser', password='testpass123')
        response = client.get(reverse('books:comics_main'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Comics')

    def test_comics_count_from_final_metadata(self):
        """Test comics count from metadata."""
        client = Client()
        User.objects.create_user('testuser', password='testpass123')
        client.login(username='testuser', password='testpass123')

        # Create test data
        scan_folder = ScanFolder.objects.create(
            name="Test", path="/test", content_type="comics")

        for i, fmt in enumerate(['cbr', 'cbz'], 1):
            book = create_test_book_with_file(
                file_path=f'/test/comic{i}.{fmt}',
                file_format=fmt,
                file_size=1000000,
                scan_folder=scan_folder
            )

            FinalMetadata.objects.create(
                book=book, final_title=f'Comic {i}', final_author='Author',
                is_reviewed=True)

        response = client.get(reverse('books:comics_main'))
        self.assertEqual(response.context['comics_count'], 2)

    def test_comics_count_excludes_non_comics(self):
        """Test non-comic formats excluded."""
        client = Client()
        User.objects.create_user('testuser', password='testpass123')
        client.login(username='testuser', password='testpass123')

        scan_folder = ScanFolder.objects.create(
            name="Test", path="/test", content_type="comics")

        # Create comic and pdf comic
        comic = create_test_book_with_file(
            file_path='/test/comic.cbr', file_format='cbr',
            file_size=1000000, scan_folder=scan_folder
        )
        pdf_comic = create_test_book_with_file(
            file_path='/test/comic.pdf', file_format='pdf',
            file_size=1000000, scan_folder=scan_folder
        )

        for book in [comic, pdf_comic]:
            FinalMetadata.objects.create(
                book=book, final_title=book.file_path, final_author='Author',
                is_reviewed=True)

        response = client.get(reverse('books:comics_main'))
        self.assertEqual(response.context['comics_count'], 2)

    def test_comics_count_excludes_empty_formats(self):
        """Test empty formats excluded."""
        client = Client()
        User.objects.create_user('testuser', password='testpass123')
        client.login(username='testuser', password='testpass123')

        scan_folder = ScanFolder.objects.create(
            name="Test", path="/test", content_type="comics")

        # Create a comic with valid format
        comic = create_test_book_with_file(
            file_path='/test/comic.cbr', file_format='cbr',
            file_size=1000000, scan_folder=scan_folder
        )
        FinalMetadata.objects.create(
            book=comic, final_title='Valid Comic', final_author='Author',
            is_reviewed=True)

        # Create a book with empty format (should be excluded)
        create_test_book_with_file(
            file_path='/test/noformat', file_format='', file_size=1000000,
            scan_folder=scan_folder
        )

        response = client.get(reverse('books:comics_main'))
        self.assertEqual(response.context['comics_count'], 1)  # Only the valid comic

    def test_comics_count_fallback_to_book_format(self):
        """Test fallback to Book.file_format when FinalMetadata missing."""
        client = Client()
        User.objects.create_user('testuser', password='testpass123')
        client.login(username='testuser', password='testpass123')

        scan_folder = ScanFolder.objects.create(
            name="Test", path="/test", content_type="comics")
        create_test_book_with_file(
            file_path='/test/comic.cbr', file_format='cbr', file_size=1000000,
            scan_folder=scan_folder
        )
        response = client.get(reverse('books:comics_main'))
        self.assertEqual(response.context['comics_count'], 1)


@override_settings(USE_SQLITE_TEMPORARILY=True)
class ComicsAjaxListTests(TestCase):
    """Test comics AJAX list functionality."""

    def test_comics_ajax_list_requires_login(self):
        """Test AJAX list requires authentication."""
        response = Client().get(reverse('books:comics_ajax_list'))
        self.assertEqual(response.status_code, 302)

    def test_comics_ajax_list_returns_json(self):
        """Test AJAX list returns JSON."""
        client = Client()
        User.objects.create_user('testuser', password='testpass123')
        client.login(username='testuser', password='testpass123')

        response = client.get(reverse('books:comics_ajax_list'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')

        data = json.loads(response.content)
        self.assertIn('series', data)
        self.assertIn('standalone', data)

    def test_comics_ajax_list_content(self):
        """Test AJAX list content structure."""
        client = Client()
        User.objects.create_user('testuser', password='testpass123')
        client.login(username='testuser', password='testpass123')

        # Create test comic
        scan_folder = ScanFolder.objects.create(
            name="Test", path="/test", content_type="comics")
        book = create_test_book_with_file(
            file_path='/test/comic.cbr', file_format='cbr',
            file_size=1000000, scan_folder=scan_folder
        )
        FinalMetadata.objects.create(
            book=book, final_title='Test Comic', final_author='Author',
            final_series='Test Series', is_reviewed=True)

        response = client.get(reverse('books:comics_ajax_list'))
        data = json.loads(response.content)

        self.assertEqual(len(data['series']), 1)
        self.assertEqual(data['series'][0]['name'], 'Test Series')

    def test_comics_ajax_list_excludes_empty_series(self):
        """Test handling of books without series."""
        client = Client()
        User.objects.create_user('testuser', password='testpass123')
        client.login(username='testuser', password='testpass123')

        # Create comic without series
        scan_folder = ScanFolder.objects.create(
            name="Test", path="/test", content_type="comics")
        book = create_test_book_with_file(
            file_path='/test/comic.cbr', file_format='cbr',
            file_size=1000000, scan_folder=scan_folder
        )
        FinalMetadata.objects.create(
            book=book, final_title='No Series Comic', final_author='Author',
            is_reviewed=True)

        response = client.get(reverse('books:comics_ajax_list'))
        data = json.loads(response.content)

        self.assertEqual(len(data['standalone']), 1)
        self.assertEqual(len(data['series']), 0)

    def test_comics_ajax_list_book_details(self):
        """Test book detail formatting."""
        client = Client()
        User.objects.create_user('testuser', password='testpass123')
        client.login(username='testuser', password='testpass123')

        scan_folder = ScanFolder.objects.create(
            name="Test", path="/test", content_type="comics")
        book = create_test_book_with_file(
            file_path='/test/spiderman.cbr', file_format='cbr',
            file_size=15000000, scan_folder=scan_folder
        )
        FinalMetadata.objects.create(
            book=book, final_title='Spider-Man #1', final_author='Stan Lee',
            is_reviewed=True)

        response = client.get(reverse('books:comics_ajax_list'))
        data = json.loads(response.content)

        book_data = data['standalone'][0]
        self.assertEqual(book_data['title'], 'Spider-Man #1')
        self.assertEqual(book_data['file_format'], 'cbr')
        self.assertEqual(book_data['author'], 'Stan Lee')

    def test_comics_ajax_list_series_sorting(self):
        """Test series data formatting and sorting."""
        client = Client()
        User.objects.create_user('testuser', password='testpass123')
        client.login(username='testuser', password='testpass123')

        scan_folder = ScanFolder.objects.create(
            name="Test", path="/test", content_type="comics")
        series_names = ['X-Men', 'Amazing Spider-Man', 'Fantastic Four']

        for series_name in series_names:
            book = create_test_book_with_file(
                file_path=f'/test/{series_name.lower()}.cbr',
                file_format='cbr',
                file_size=1000000,
                scan_folder=scan_folder
            )
            FinalMetadata.objects.create(
                book=book,
                final_title=f'{series_name} #1',
                final_author='Author',
                final_series=series_name,
                is_reviewed=True
            )

        response = client.get(reverse('books:comics_ajax_list'))
        data = json.loads(response.content)

        returned_series = [series['name'] for series in data['series']]
        self.assertEqual(set(returned_series), set(series_names))

    def test_comics_ajax_list_book_sorting(self):
        """Test book sorting."""
        client = Client()
        User.objects.create_user('testuser', password='testpass123')
        client.login(username='testuser', password='testpass123')

        scan_folder = ScanFolder.objects.create(
            name="Test", path="/test", content_type="comics")
        titles = ['Z Comic', 'A Comic', 'M Comic']

        for title in titles:
            book = create_test_book_with_file(
                file_path=f'/test/{title.lower()}.cbr',
                file_format='cbr',
                file_size=1000000,
                scan_folder=scan_folder
            )
            FinalMetadata.objects.create(
                book=book,
                final_title=title,
                final_author='Author',
                is_reviewed=True
            )

        response = client.get(reverse('books:comics_ajax_list'))
        data = json.loads(response.content)

        returned_titles = [book['title'] for book in data['standalone']]
        self.assertEqual(returned_titles, sorted(titles))

    def test_comics_ajax_list_aggregates_data_correctly(self):
        """Test data aggregation."""
        client = Client()
        User.objects.create_user('testuser', password='testpass123')
        client.login(username='testuser', password='testpass123')

        scan_folder = ScanFolder.objects.create(
            name="Test", path="/test", content_type="comics")
        book = create_test_book_with_file(
            file_path='/test/comic.cbr', file_format='cbr',
            file_size=1000000, scan_folder=scan_folder
        )
        FinalMetadata.objects.create(
            book=book, final_title='Test Comic', final_author='Author',
            final_series='Test Series', is_reviewed=True)

        response = client.get(reverse('books:comics_ajax_list'))
        data = json.loads(response.content)

        self.assertEqual(len(data['series']), 1)
        self.assertEqual(data['total_count'], 1)

        book_data = data['series'][0]['books'][0]
        self.assertIn('id', book_data)
        self.assertIn('title', book_data)
        self.assertIn('author', book_data)

    def test_comics_ajax_list_handles_errors(self):
        """Test error handling."""
        client = Client()
        User.objects.create_user('testuser', password='testpass123')
        client.login(username='testuser', password='testpass123')

        # Test with invalid parameters
        response = client.get(reverse('books:comics_ajax_list'), {'invalid_param': 'test'})
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content)
        self.assertIn('series', data)
        self.assertIn('standalone', data)


@override_settings(USE_SQLITE_TEMPORARILY=True)
class ComicsIntegrationTests(TestCase):
    """Integration tests for comics functionality."""

    def test_comics_count_matches_ajax_count(self):
        """Test main view and AJAX counts match."""
        client = Client()
        User.objects.create_user('testuser', password='testpass123')
        client.login(username='testuser', password='testpass123')

        # Create test comics
        scan_folder = ScanFolder.objects.create(
            name="Test", path="/test", content_type="comics")
        for i in range(3):
            book = create_test_book_with_file(
                file_path=f'/test/comic{i}.cbr', file_format='cbr',
                file_size=1000000, scan_folder=scan_folder
            )
            FinalMetadata.objects.create(
                book=book, final_title=f'Comic {i}', final_author='Author',
                is_reviewed=True)

        main_response = client.get(reverse('books:comics_main'))
        ajax_response = client.get(reverse('books:comics_ajax_list'))
        ajax_data = json.loads(ajax_response.content)

        self.assertEqual(main_response.context['comics_count'], ajax_data['total_count'])

    def test_comics_with_mixed_metadata_sources(self):
        """Test comics with different metadata sources."""
        client = Client()
        User.objects.create_user('testuser', password='testpass123')
        client.login(username='testuser', password='testpass123')

        scan_folder = ScanFolder.objects.create(
            name="Test", path="/test", content_type="comics")

        # Create comics
        for i, source_name in enumerate(['Source 1', 'Source 2']):
            book = create_test_book_with_file(
                file_path=f'/test/{source_name.lower()}.cbr',
                file_format='cbr',
                file_size=1000000,
                scan_folder=scan_folder
            )
            FinalMetadata.objects.create(
                book=book,
                final_title=f'{source_name} Comic',
                final_author='Author',
                is_reviewed=True
            )

        response = client.get(reverse('books:comics_ajax_list'))
        data = json.loads(response.content)
        self.assertEqual(data['total_count'], 2)

    def test_complete_comics_workflow(self):
        """Test complete comics workflow."""
        client = Client()
        User.objects.create_user('testuser', password='testpass123')
        client.login(username='testuser', password='testpass123')

        # Create test data
        scan_folder = ScanFolder.objects.create(
            name="Test", path="/test", content_type="comics")
        book = create_test_book_with_file(
            file_path='/test/comic.cbr', file_format='cbr',
            file_size=1000000, scan_folder=scan_folder
        )
        FinalMetadata.objects.create(
            book=book, final_title='Test Comic', final_author='Author',
            final_series='Test Series', is_reviewed=True)

        # Test main view
        main_response = client.get(reverse('books:comics_main'))
        self.assertEqual(main_response.status_code, 200)
        self.assertEqual(main_response.context['comics_count'], 1)

        # Test AJAX list
        ajax_response = client.get(reverse('books:comics_ajax_list'))
        self.assertEqual(ajax_response.status_code, 200)

        ajax_data = json.loads(ajax_response.content)
        self.assertEqual(len(ajax_data['series']), 1)
        self.assertEqual(ajax_data['total_count'], 1)

        # Verify consistency
        self.assertEqual(main_response.context['comics_count'], ajax_data['total_count'])
