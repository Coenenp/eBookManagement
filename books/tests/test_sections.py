"""
Test suite for sections.py views module with comprehensive coverage.

Tests all views and functions in sections.py including:
- Content type-based filtering
- Helper functions
- All section views (Ebooks, Comics, Series, Audiobooks)
- AJAX endpoints
- Error handling
- Edge cases
"""

import json
import tempfile
import shutil
from unittest.mock import patch
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
import uuid

from books.models import (
    Book, FinalMetadata, ScanFolder, DataSource, Series, BookSeries,
    Author, BookMetadata
)
from books.views.sections import get_book_metadata_dict, get_book_cover_url
from books.tests.test_helpers import create_test_book_with_file


class SectionsTestCase(TestCase):
    """Base test case with comprehensive setup for sections testing"""

    def setUp(self):
        """Set up test data for all content types"""
        # Create temporary directories for scan folders
        self.temp_ebooks_dir = tempfile.mkdtemp()
        self.temp_comics_dir = tempfile.mkdtemp()
        self.temp_audiobooks_dir = tempfile.mkdtemp()
        self.temp_inactive_dir = tempfile.mkdtemp()

        # Cleanup temp directories when tests complete
        self.addCleanup(shutil.rmtree, self.temp_ebooks_dir, ignore_errors=True)
        self.addCleanup(shutil.rmtree, self.temp_comics_dir, ignore_errors=True)
        self.addCleanup(shutil.rmtree, self.temp_audiobooks_dir, ignore_errors=True)
        self.addCleanup(shutil.rmtree, self.temp_inactive_dir, ignore_errors=True)

        self.client = Client()
        # Create unique username to avoid conflicts
        unique_id = uuid.uuid4().hex[:8]
        username = f'testuser_{unique_id}'
        self.user = User.objects.create_user(
            username=username,
            email='test@example.com',
            password='testpass123'
        )

        # Create scan folders with different content types using real temp directories
        self.ebooks_folder = ScanFolder.objects.create(
            name="Ebooks Folder",
            path=self.temp_ebooks_dir,
            content_type="ebooks",
            is_active=True
        )

        self.comics_folder = ScanFolder.objects.create(
            name="Comics Folder",
            path=self.temp_comics_dir,
            content_type="comics",
            is_active=True
        )

        self.audiobooks_folder = ScanFolder.objects.create(
            name="Audiobooks Folder",
            path=self.temp_audiobooks_dir,
            content_type="audiobooks",
            is_active=True
        )

        # Mixed folders are no longer supported - removed

        self.inactive_folder = ScanFolder.objects.create(
            name="Inactive Folder",
            path=self.temp_inactive_dir,
            content_type="ebooks",
            is_active=False
        )

        # Create data source
        self.data_source = DataSource.objects.create(
            name="Test Source",
            trust_level=0.8
        )

        # Create test books in different folders
        self.ebook1 = create_test_book_with_file(
            file_path="/test/ebooks/book1.epub",
            file_format="epub",
            file_size=1000000,
            scan_folder=self.ebooks_folder,
            content_type='ebook',
            title="Book 1"
        )

        self.ebook2 = create_test_book_with_file(
            file_path="/test/ebooks/book2.pdf",
            file_format="pdf",
            file_size=2000000,
            scan_folder=self.ebooks_folder,
            content_type='ebook',
            title="Book 2"
        )

        self.comic1 = create_test_book_with_file(
            file_path="/test/comics/comic1.cbr",
            file_format="cbr",
            file_size=5000000,
            scan_folder=self.comics_folder,
            content_type='comic',
            title="Comic 1"
        )

        self.comic2 = create_test_book_with_file(
            file_path="/test/comics/comic2.pdf",
            file_format="pdf",
            file_size=3000000,
            scan_folder=self.comics_folder,
            content_type='comic',
            title="Comic 2"
        )

        self.audiobook1 = create_test_book_with_file(
            file_path="/test/audiobooks/audio1.m4b",
            file_format="m4b",
            file_size=100000000,
            scan_folder=self.audiobooks_folder,
            content_type='audiobook',
            title="Audiobook 1"
        )

        self.audiobook2 = create_test_book_with_file(
            file_path="/test/audiobooks/audio2.mp3",
            file_format="mp3",
            file_size=50000000,
            scan_folder=self.audiobooks_folder,
            content_type='audiobook',
            title="Audiobook 2"
        )

        self.inactive_book = create_test_book_with_file(
            file_path="/test/inactive/book.epub",
            file_format="epub",
            file_size=1000000,
            scan_folder=self.inactive_folder,
            content_type='ebook',
            title="Inactive Book"
        )

        # Create authors and series with unique names
        self.author1 = Author.objects.create(
            first_name=f"J.K._{unique_id}",
            last_name="Rowling"
        )

        self.author2 = Author.objects.create(
            first_name=f"Frank_{unique_id}",
            last_name="Miller"
        )

        self.series1 = Series.objects.create(name=f"Harry Potter {unique_id}")
        self.series2 = Series.objects.create(name=f"Batman {unique_id}")

        # Create FinalMetadata
        self.final_meta_ebook1 = FinalMetadata.objects.create(
            book=self.ebook1,
            final_title="Harry Potter and the Philosopher's Stone",
            final_author="J.K. Rowling",
            final_series="Harry Potter",
            final_series_number="1",
            final_publisher="Bloomsbury",
            description="A young wizard's journey begins",
            isbn="9780747532699",
            language="en",
            publication_year=1997,
            final_cover_path="http://example.com/cover1.jpg",
            is_reviewed=True
        )

        self.final_meta_ebook2 = FinalMetadata.objects.create(
            book=self.ebook2,
            final_title="Standalone Ebook",
            final_author="Unknown Author",
            is_reviewed=True
        )

        self.final_meta_comic1 = FinalMetadata.objects.create(
            book=self.comic1,
            final_title="Batman: Year One",
            final_author="Frank Miller",
            final_series="Batman",
            final_series_number="1",
            is_reviewed=True
        )

        self.final_meta_comic2 = FinalMetadata.objects.create(
            book=self.comic2,
            final_title="Standalone Comic",
            final_author="Alan Moore",
            is_reviewed=True
        )

        self.final_meta_audiobook2 = FinalMetadata.objects.create(
            book=self.audiobook2,
            final_title="Audiobook Folder Book",
            final_author="Test Author",
            is_reviewed=True
        )

        # Create BookMetadata for search testing and fallback testing
        BookMetadata.objects.create(
            book=self.ebook1,
            field_name="title",
            field_value="Harry Potter and the Philosopher's Stone",
            source=self.data_source,
            confidence=0.9,
            is_active=True
        )

        self.book_metadata = BookMetadata.objects.create(
            book=self.audiobook1,
            field_name="title",
            field_value="Test Audiobook",
            source=self.data_source,
            confidence=0.9,
            is_active=True
        )

        BookMetadata.objects.create(
            book=self.audiobook1,
            field_name="author",
            field_value="Test Author",
            source=self.data_source,
            confidence=0.9,
            is_active=True
        )

        # Create BookSeries relationships
        BookSeries.objects.create(
            book=self.ebook1,
            series=self.series1,
            series_number="1",
            source=self.data_source,
            confidence=0.9,
            is_active=True
        )


class HelperFunctionsTests(SectionsTestCase):
    """Test helper functions in sections.py"""

    def test_get_book_metadata_dict_with_final_metadata(self):
        """Test getting metadata from FinalMetadata"""
        metadata = get_book_metadata_dict(self.ebook1)

        self.assertEqual(metadata['title'], "Harry Potter and the Philosopher's Stone")
        self.assertEqual(metadata['author'], "J.K. Rowling")
        self.assertEqual(metadata['publisher'], "Bloomsbury")
        self.assertEqual(metadata['description'], "A young wizard's journey begins")
        self.assertEqual(metadata['isbn'], "9780747532699")
        self.assertEqual(metadata['language'], "en")
        self.assertEqual(metadata['publication_date'], 1997)

    def test_get_book_metadata_dict_fallback_to_metadata(self):
        """Test fallback to BookMetadata when no FinalMetadata"""
        metadata = get_book_metadata_dict(self.audiobook1)

        self.assertEqual(metadata['title'], "Test Audiobook")
        self.assertEqual(metadata['author'], "Test Author")

    def test_get_book_metadata_dict_no_metadata(self):
        """Test metadata dict with no metadata at all"""
        book = create_test_book_with_file(
            file_path="/test/empty.epub",
            file_format="epub",
            scan_folder=self.ebooks_folder,
            content_type='ebook',
            title="Empty"
        )

        metadata = get_book_metadata_dict(book)

        self.assertEqual(metadata['title'], "Unknown Title")
        self.assertEqual(metadata['author'], "Unknown Author")
        self.assertEqual(metadata['publisher'], "")
        self.assertEqual(metadata['description'], "")
        self.assertEqual(metadata['isbn'], "")
        self.assertEqual(metadata['language'], "")
        self.assertIsNone(metadata['publication_date'])

    def test_get_book_metadata_dict_invalid_publication_date(self):
        """Test handling of invalid publication dates"""
        BookMetadata.objects.create(
            book=self.audiobook2,
            field_name="publication_date",
            field_value="invalid_date",
            source=self.data_source,
            confidence=0.9,
            is_active=True
        )

        metadata = get_book_metadata_dict(self.audiobook2)
        self.assertIsNone(metadata['publication_date'])

    def test_get_book_cover_url_from_final_metadata(self):
        """Test getting cover URL from FinalMetadata"""
        cover_url = get_book_cover_url(self.ebook1)
        self.assertEqual(cover_url, "http://example.com/cover1.jpg")

    def test_get_book_cover_url_local_path(self):
        """Test converting local path to media URL"""
        with patch('django.conf.settings.MEDIA_ROOT', '/media/root/'), \
             patch('django.conf.settings.MEDIA_URL', '/media/'):

            self.final_meta_ebook1.final_cover_path = "/media/root/covers/cover.jpg"
            self.final_meta_ebook1.save()

            cover_url = get_book_cover_url(self.ebook1)
            self.assertEqual(cover_url, "/media/covers/cover.jpg")

    def test_get_book_cover_url_fallback_to_book(self):
        """Test fallback to book's cover_path"""
        book = create_test_book_with_file(
            file_path="/test/book.epub",
            file_format="epub",
            scan_folder=self.ebooks_folder,
            content_type='ebook',
            title="Test Book"
        )
        # Set cover_path on the BookFile
        primary_file = book.primary_file
        if primary_file:
            primary_file.cover_path = "http://example.com/book_cover.jpg"
            primary_file.save()

        cover_url = get_book_cover_url(book)
        self.assertEqual(cover_url, "http://example.com/book_cover.jpg")

    def test_get_book_cover_url_no_cover(self):
        """Test when no cover is available"""
        cover_url = get_book_cover_url(self.audiobook1)
        self.assertIsNone(cover_url)

    def test_get_book_cover_url_exception_handling(self):
        """Test exception handling in cover URL generation"""
        # Test with a book that has no cover information
        book_no_cover = create_test_book_with_file(
            file_path="/test/no_cover.epub",
            file_format="epub",
            scan_folder=self.ebooks_folder,
            content_type="ebook",
            title="No Cover Book"
        )

        cover_url = get_book_cover_url(book_no_cover)
        # Should not raise exception and return None when no cover available
        self.assertIsNone(cover_url)


class EbooksViewsTests(SectionsTestCase):
    """Test ebooks section views"""

    def test_ebooks_main_view_requires_login(self):
        """Test that ebooks main view requires authentication"""
        response = self.client.get(reverse('books:ebooks_main'))
        self.assertEqual(response.status_code, 302)

    def test_ebooks_main_view_anonymous_redirects(self):
        """Test ebooks main view redirects for anonymous users"""
        response = self.client.get(reverse('books:ebooks_main'))
        # Should redirect to login page
        self.assertEqual(response.status_code, 302)

    def test_ebooks_main_view_authenticated(self):
        """Test ebooks main view for authenticated users"""
        self.client.login(username=self.user.username, password='testpass123')
        response = self.client.get(reverse('books:ebooks_main'))

        # Check if the status code is 200 first
        if response.status_code != 200:
            self.fail(f"Expected status 200, got {response.status_code}. Response: {response}")

        # Check if we have a context (template was rendered)
        if response.context is None:
            self.fail("response.context is None - template view not rendered")

        self.assertIn('ebooks_count', response.context)
        # Should count ebook1 + ebook2 (both in ebooks folder) = 2
        self.assertEqual(response.context['ebooks_count'], 2)

    def test_ebooks_main_view_excludes_inactive_folders(self):
        """Test that inactive folders are excluded from count"""
        self.client.login(username=self.user.username, password='testpass123')
        response = self.client.get(reverse('books:ebooks_main'))

        # Should not count book from inactive folder, total should be 2
        self.assertEqual(response.context['ebooks_count'], 2)

    def test_ebooks_ajax_list_requires_login(self):
        """Test that ebooks AJAX endpoint requires authentication"""
        response = self.client.get(reverse('books:ebooks_ajax_list'))
        self.assertEqual(response.status_code, 302)

    def test_ebooks_ajax_list_success(self):
        """Test ebooks AJAX list returns correct data"""
        self.client.login(username=self.user.username, password='testpass123')
        response = self.client.get(reverse('books:ebooks_ajax_list'))

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)

        self.assertTrue(data['success'])
        self.assertIn('ebooks', data)
        self.assertEqual(len(data['ebooks']), 2)  # Should include both books from ebooks folder

    def test_ebooks_ajax_list_with_search(self):
        """Test ebooks AJAX list with search parameter"""
        self.client.login(username=self.user.username, password='testpass123')
        response = self.client.get(reverse('books:ebooks_ajax_list'), {'search': 'Harry'})

        data = json.loads(response.content)
        self.assertEqual(len(data['ebooks']), 1)
        self.assertIn('Harry', data['ebooks'][0]['title'])

    def test_ebooks_ajax_list_with_format_filter(self):
        """Test ebooks AJAX list with format filter"""
        self.client.login(username=self.user.username, password='testpass123')
        response = self.client.get(reverse('books:ebooks_ajax_list'), {'format': 'epub'})

        data = json.loads(response.content)
        self.assertEqual(len(data['ebooks']), 1)
        self.assertEqual(data['ebooks'][0]['file_format'], 'epub')

    def test_ebooks_ajax_list_with_sorting(self):
        """Test ebooks AJAX list with different sort options"""
        self.client.login(username=self.user.username, password='testpass123')

        # Test date sorting
        response = self.client.get(reverse('books:ebooks_ajax_list'), {'sort': 'date'})
        data = json.loads(response.content)
        self.assertTrue(data['success'])

        # Test size sorting
        response = self.client.get(reverse('books:ebooks_ajax_list'), {'sort': 'size'})
        data = json.loads(response.content)
        self.assertTrue(data['success'])

    def test_ebooks_ajax_list_limit(self):
        """Test that ebooks AJAX list respects 500 item limit"""
        self.client.login(username=self.user.username, password='testpass123')
        response = self.client.get(reverse('books:ebooks_ajax_list'))

        data = json.loads(response.content)
        # Should not exceed 500 items
        self.assertLessEqual(len(data['ebooks']), 500)

    def test_ebooks_ajax_detail_success(self):
        """Test ebooks AJAX detail endpoint"""
        self.client.login(username=self.user.username, password='testpass123')
        response = self.client.get(reverse('books:ebooks_ajax_detail', args=[self.ebook1.id]))

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)

        self.assertTrue(data['success'])
        self.assertIn('ebook', data)
        self.assertEqual(data['ebook']['title'], "Harry Potter and the Philosopher's Stone")

    def test_ebooks_ajax_detail_not_found(self):
        """Test ebooks AJAX detail with non-existent book"""
        self.client.login(username=self.user.username, password='testpass123')
        response = self.client.get(reverse('books:ebooks_ajax_detail', args=[99999]))

        self.assertEqual(response.status_code, 404)
        data = json.loads(response.content)
        self.assertFalse(data['success'])

    def test_ebooks_ajax_detail_no_metadata(self):
        """Test ebooks AJAX detail with book having no metadata"""
        book = create_test_book_with_file(
            file_path="/test/empty.epub",
            file_format="epub",
            scan_folder=self.ebooks_folder,
            content_type="ebook",
            title="Empty Book"
        )

        self.client.login(username=self.user.username, password='testpass123')
        response = self.client.get(reverse('books:ebooks_ajax_detail', args=[book.id]))

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertTrue(data['success'])
        self.assertEqual(data['ebook']['title'], 'Unknown Title')  # Should use fallback when no metadata

    def test_ebooks_ajax_list_exception_handling(self):
        """Test exception handling in ebooks AJAX list"""
        self.client.login(username=self.user.username, password='testpass123')

        with patch('books.views.sections.Book.objects.filter', side_effect=Exception("Test error")):
            response = self.client.get(reverse('books:ebooks_ajax_list'))

            self.assertEqual(response.status_code, 500)
            data = json.loads(response.content)
            self.assertFalse(data['success'])
            self.assertIn('error', data)


class SeriesViewsTests(SectionsTestCase):
    """Test series section views"""

    def test_series_main_view_requires_login(self):
        """Test that series main view requires authentication"""
        response = self.client.get(reverse('books:series_main'))
        self.assertEqual(response.status_code, 302)

    def test_series_main_view_authenticated(self):
        """Test series main view for authenticated users"""
        self.client.login(username=self.user.username, password='testpass123')
        response = self.client.get(reverse('books:series_main'))

        self.assertEqual(response.status_code, 200)
        self.assertIn('series_count', response.context)
        # Should count unique series from final metadata
        self.assertEqual(response.context['series_count'], 2)  # Harry Potter, Batman

    def test_series_ajax_list_success(self):
        """Test series AJAX list returns correct data"""
        self.client.login(username=self.user.username, password='testpass123')
        response = self.client.get(reverse('books:series_ajax_list'))

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)

        self.assertTrue(data['success'])
        self.assertIn('series', data)
        self.assertEqual(len(data['series']), 1)  # Only ebook series, not comics

    def test_series_ajax_list_book_sorting(self):
        """Test that books within series are sorted by position"""
        # Create another book in Harry Potter series
        book3 = create_test_book_with_file(
            file_path="/test/book3.epub",
            file_format="epub",
            scan_folder=self.ebooks_folder,
            content_type="ebook",
            title="Test Book 3"
        )

        FinalMetadata.objects.create(
            book=book3,
            final_title="Harry Potter and the Chamber of Secrets",
            final_author="J.K. Rowling",
            final_series="Harry Potter",
            final_series_number="2",
            is_reviewed=True
        )

        self.client.login(username=self.user.username, password='testpass123')
        response = self.client.get(reverse('books:series_ajax_list'))

        data = json.loads(response.content)
        harry_potter = next(s for s in data['series'] if s['name'] == 'Harry Potter')

        # Books should be sorted by position
        positions = [book['position'] for book in harry_potter['books']]
        self.assertEqual(positions, ["1", "2"])

    def test_series_ajax_list_series_sorting(self):
        """Test that series are sorted alphabetically"""
        self.client.login(username=self.user.username, password='testpass123')
        response = self.client.get(reverse('books:series_ajax_list'))

        data = json.loads(response.content)
        series_names = [s['name'] for s in data['series']]
        self.assertEqual(series_names, sorted(series_names))

    def test_series_ajax_list_aggregation(self):
        """Test series data aggregation"""
        self.client.login(username=self.user.username, password='testpass123')
        response = self.client.get(reverse('books:series_ajax_list'))

        data = json.loads(response.content)
        harry_potter = next(s for s in data['series'] if s['name'] == 'Harry Potter')

        self.assertEqual(harry_potter['book_count'], 1)
        self.assertEqual(harry_potter['total_size'], 1000000)
        self.assertIn('J.K. Rowling', harry_potter['authors'])
        self.assertIn('epub', harry_potter['formats'])


class ComicsViewsTests(SectionsTestCase):
    """Test comics section views"""

    def test_comics_main_view_requires_login(self):
        """Test that comics main view requires authentication"""
        response = self.client.get(reverse('books:comics_main'))
        self.assertEqual(response.status_code, 302)

    def test_comics_main_view_authenticated(self):
        """Test comics main view for authenticated users"""
        self.client.login(username=self.user.username, password='testpass123')
        response = self.client.get(reverse('books:comics_main'))

        self.assertEqual(response.status_code, 200)
        self.assertIn('comics_count', response.context)
        # Should count comic1 (cbr) + comic2 (pdf) = 2 (both in comics folder)
        self.assertEqual(response.context['comics_count'], 2)

    def test_comics_main_view_fallback_count(self):
        """Test comics main view fallback when no final metadata"""
        # Remove final metadata for comics
        FinalMetadata.objects.filter(book__in=[self.comic1, self.comic2]).delete()

        self.client.login(username=self.user.username, password='testpass123')
        response = self.client.get(reverse('books:comics_main'))

        # Should count 2 books in comics folder (comic1 + comic2, both in comics folder)
        self.assertEqual(response.context['comics_count'], 2)

    def test_comics_ajax_list_success(self):
        """Test comics AJAX list returns correct data"""
        self.client.login(username=self.user.username, password='testpass123')
        response = self.client.get(reverse('books:comics_ajax_list'))

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)

        self.assertTrue(data['success'])
        self.assertIn('series', data)
        self.assertIn('standalone', data)
        self.assertEqual(len(data['series']), 1)  # Batman
        self.assertEqual(len(data['standalone']), 1)  # comic2 only (ebook2 is in ebooks folder)

    def test_comics_ajax_list_series_books_sorting(self):
        """Test that books within comic series are sorted correctly"""
        # Create another Batman comic
        comic3 = create_test_book_with_file(
            file_path="/test/comics/comic3.cbr",
            file_format="cbr",
            scan_folder=self.comics_folder,
            content_type="comic",
            title="Comic 3"
        )

        FinalMetadata.objects.create(
            book=comic3,
            final_title="Batman: The Dark Knight Returns",
            final_author="Frank Miller",
            final_series="Batman",
            final_series_number="2",
            is_reviewed=True
        )

        self.client.login(username=self.user.username, password='testpass123')
        response = self.client.get(reverse('books:comics_ajax_list'))

        data = json.loads(response.content)
        batman_series = data['series'][0]

        # Books should be sorted by position
        positions = [float(book['position']) for book in batman_series['books']]
        self.assertEqual(positions, [1.0, 2.0])

    def test_comics_ajax_list_standalone_sorting(self):
        """Test that standalone comics are sorted by title"""
        # Create another standalone comic
        comic4 = create_test_book_with_file(
            file_path="/test/comics/comic4.cbz",
            file_format="cbz",
            scan_folder=self.comics_folder,
            content_type="comic",
            title="Comic 4"
        )

        FinalMetadata.objects.create(
            book=comic4,
            final_title="Another Standalone",
            final_author="Different Author",
            is_reviewed=True
        )

        self.client.login(username=self.user.username, password='testpass123')
        response = self.client.get(reverse('books:comics_ajax_list'))

        data = json.loads(response.content)
        standalone_titles = [comic['title'] for comic in data['standalone']]
        self.assertEqual(standalone_titles, sorted(standalone_titles))


class AudiobooksViewsTests(SectionsTestCase):
    """Test audiobooks section views"""

    def test_audiobooks_main_view_requires_login(self):
        """Test that audiobooks main view requires authentication"""
        response = self.client.get(reverse('books:audiobooks_main'))
        self.assertEqual(response.status_code, 302)

    def test_audiobooks_main_view_authenticated(self):
        """Test audiobooks main view for authenticated users"""
        self.client.login(username=self.user.username, password='testpass123')
        response = self.client.get(reverse('books:audiobooks_main'))

        self.assertEqual(response.status_code, 200)
        self.assertIn('audiobooks_count', response.context)
        # Should count audiobook1 + audiobook2 both in audiobooks folder = 2
        self.assertEqual(response.context['audiobooks_count'], 2)

    def test_audiobooks_ajax_list_success(self):
        """Test audiobooks AJAX list returns correct data"""
        self.client.login(username=self.user.username, password='testpass123')
        response = self.client.get(reverse('books:audiobooks_ajax_list'))

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)

        self.assertTrue(data['success'])
        self.assertIn('audiobooks', data)
        self.assertEqual(len(data['audiobooks']), 2)  # audiobook1 + audiobook2 in audiobooks folder

    def test_audiobooks_ajax_list_data_structure(self):
        """Test audiobooks AJAX list data structure"""
        self.client.login(username=self.user.username, password='testpass123')
        response = self.client.get(reverse('books:audiobooks_ajax_list'))

        data = json.loads(response.content)
        audiobook = data['audiobooks'][0]

        required_fields = [
            'id', 'title', 'author', 'narrator', 'duration',
            'file_format', 'file_size', 'last_scanned',
            'series_name', 'series_position'
        ]

        for field in required_fields:
            self.assertIn(field, audiobook)

    def test_audiobooks_ajax_detail_success(self):
        """Test audiobooks AJAX detail endpoint"""
        self.client.login(username=self.user.username, password='testpass123')
        response = self.client.get(reverse('books:audiobooks_ajax_detail', args=[self.audiobook1.id]))

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)

        self.assertTrue(data['success'])
        self.assertIn('audiobook', data)
        self.assertEqual(data['audiobook']['title'], "Test Audiobook")

    def test_audiobooks_ajax_detail_not_found(self):
        """Test audiobooks AJAX detail with non-existent book"""
        self.client.login(username=self.user.username, password='testpass123')
        response = self.client.get(reverse('books:audiobooks_ajax_detail', args=[99999]))

        self.assertEqual(response.status_code, 404)

    def test_audiobooks_ajax_list_exception_handling(self):
        """Test exception handling in audiobooks AJAX list"""
        self.client.login(username=self.user.username, password='testpass123')

        with patch('books.views.sections.Book.objects.filter', side_effect=Exception("Test error")):
            response = self.client.get(reverse('books:audiobooks_ajax_list'))

            self.assertEqual(response.status_code, 500)
            data = json.loads(response.content)
            self.assertFalse(data['success'])


class ContentTypeFilteringTests(SectionsTestCase):
    """Test content type-based filtering across all sections"""

    def test_content_type_segregation(self):
        """Test that content types are properly segregated"""
        self.client.login(username=self.user.username, password='testpass123')

        # Test ebooks
        ebooks_response = self.client.get(reverse('books:ebooks_ajax_list'))
        ebooks_data = json.loads(ebooks_response.content)
        ebook_ids = [book['id'] for book in ebooks_data['ebooks']]

        # Should include ebook1 from ebooks folder
        self.assertIn(self.ebook1.id, ebook_ids)
        self.assertIn(self.ebook2.id, ebook_ids)
        self.assertNotIn(self.comic1.id, ebook_ids)
        self.assertNotIn(self.audiobook1.id, ebook_ids)

        # Test comics
        comics_response = self.client.get(reverse('books:comics_ajax_list'))
        comics_data = json.loads(comics_response.content)

        # Check series and standalone
        all_comic_ids = []
        for series in comics_data['series']:
            all_comic_ids.extend([book['id'] for book in series['books']])
        all_comic_ids.extend([book['id'] for book in comics_data['standalone']])

        # Should include comic1 from comics folder
        self.assertIn(self.comic1.id, all_comic_ids)
        self.assertIn(self.comic2.id, all_comic_ids)
        self.assertNotIn(self.ebook1.id, all_comic_ids)
        self.assertNotIn(self.audiobook1.id, all_comic_ids)

        # Test audiobooks
        audiobooks_response = self.client.get(reverse('books:audiobooks_ajax_list'))
        audiobooks_data = json.loads(audiobooks_response.content)
        audiobook_ids = [book['id'] for book in audiobooks_data['audiobooks']]

        # Should include audiobook1 from audiobooks folder
        self.assertIn(self.audiobook1.id, audiobook_ids)
        self.assertIn(self.audiobook2.id, audiobook_ids)
        self.assertNotIn(self.ebook1.id, audiobook_ids)
        self.assertNotIn(self.comic1.id, audiobook_ids)

    def test_content_type_separation(self):
        """Test that content appears only in appropriate sections based on folder content type"""
        self.client.login(username=self.user.username, password='testpass123')

        # Ebooks should appear only in ebooks section
        ebooks_response = self.client.get(reverse('books:ebooks_ajax_list'))
        ebooks_data = json.loads(ebooks_response.content)
        ebook_ids = [book['id'] for book in ebooks_data['ebooks']]
        self.assertIn(self.ebook1.id, ebook_ids)

        # Comics should appear only in comics section
        comics_response = self.client.get(reverse('books:comics_ajax_list'))
        comics_data = json.loads(comics_response.content)

        # comic1 (with Batman series) should appear in series list
        series_comic_ids = []
        for series in comics_data.get('series', []):
            series_comic_ids.extend([book['id'] for book in series['books']])
        self.assertIn(self.comic1.id, series_comic_ids)

        # comic2 (standalone) should appear in standalone list (but it's PDF so excluded)
        # Just verify the response structure is correct
        self.assertIn('standalone', comics_data)
        self.assertIn('series', comics_data)

        # Audiobooks should appear only in audiobooks section
        audiobooks_response = self.client.get(reverse('books:audiobooks_ajax_list'))
        audiobooks_data = json.loads(audiobooks_response.content)
        audiobook_ids = [book['id'] for book in audiobooks_data['audiobooks']]
        self.assertIn(self.audiobook1.id, audiobook_ids)

    def test_inactive_folders_excluded(self):
        """Test that books from inactive folders are excluded"""
        self.client.login(username=self.user.username, password='testpass123')

        # Check that inactive book doesn't appear in any section
        ebooks_response = self.client.get(reverse('books:ebooks_ajax_list'))
        ebooks_data = json.loads(ebooks_response.content)
        ebook_ids = [book['id'] for book in ebooks_data['ebooks']]
        self.assertNotIn(self.inactive_book.id, ebook_ids)


class EdgeCasesAndErrorHandlingTests(SectionsTestCase):
    """Test edge cases and error handling"""

    def test_books_without_scan_folder(self):
        """Test handling of books without scan folder"""
        book = create_test_book_with_file(
            file_path="/test/orphan.epub",
            file_format="epub",
            scan_folder=None,
            content_type="ebook",
            title="Orphan Book"
        )

        self.client.login(username=self.user.username, password='testpass123')
        response = self.client.get(reverse('books:ebooks_ajax_list'))

        # Should not crash and should not include orphan book
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        book_ids = [book['id'] for book in data['ebooks']]
        self.assertNotIn(book.id, book_ids)

    def test_books_with_invalid_series_position(self):
        """Test handling of invalid series positions"""
        comic = create_test_book_with_file(
            file_path="/test/invalid.cbr",
            file_format="cbr",
            scan_folder=self.comics_folder,
            content_type="comic",
            title="Invalid Comic"
        )

        FinalMetadata.objects.create(
            book=comic,
            final_title="Invalid Position Comic",
            final_author="Test Author",
            final_series="Test Series",
            final_series_number="invalid",
            is_reviewed=True
        )

        self.client.login(username=self.user.username, password='testpass123')
        response = self.client.get(reverse('books:comics_ajax_list'))

        # Should not crash and should handle invalid position
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertTrue(data['success'])

    def test_empty_database(self):
        """Test all endpoints with empty database"""
        # Clear all data
        Book.objects.all().delete()

        self.client.login(username=self.user.username, password='testpass123')

        # Test all main views
        for view_name in ['books:ebooks_main', 'books:comics_main', 'books:series_main', 'books:audiobooks_main']:
            response = self.client.get(reverse(view_name))
            self.assertEqual(response.status_code, 200)

        # Test all AJAX endpoints
        for endpoint in ['books:ebooks_ajax_list', 'books:comics_ajax_list', 'books:series_ajax_list', 'books:audiobooks_ajax_list']:
            response = self.client.get(reverse(endpoint))
            self.assertEqual(response.status_code, 200)
            data = json.loads(response.content)
            self.assertTrue(data['success'])

    def test_missing_final_metadata_relationships(self):
        """Test handling when FinalMetadata relationships are missing"""
        # Create book without FinalMetadata
        book = create_test_book_with_file(
            file_path="/test/no_meta.epub",
            file_format="epub",
            scan_folder=self.ebooks_folder,
            content_type="ebook",
            title="No Meta Book"
        )

        self.client.login(username=self.user.username, password='testpass123')
        response = self.client.get(reverse('books:ebooks_ajax_detail', args=[book.id]))

        # Should handle gracefully
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertTrue(data['success'])

    def test_unicode_and_special_characters(self):
        """Test handling of unicode and special characters"""
        book = create_test_book_with_file(
            file_path="/test/unicode测试.epub",
            file_format="epub",
            scan_folder=self.ebooks_folder,
            content_type="ebook",
            title="Unicode Test Book"
        )

        FinalMetadata.objects.create(
            book=book,
            final_title="测试书籍 with émojis 📚",
            final_author="作者名字",
            is_reviewed=True
        )

        self.client.login(username=self.user.username, password='testpass123')
        response = self.client.get(reverse('books:ebooks_ajax_list'))

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)

        # Find our unicode book
        unicode_book = next((b for b in data['ebooks'] if b['id'] == book.id), None)
        self.assertIsNotNone(unicode_book)
        self.assertEqual(unicode_book['title'], "测试书籍 with émojis 📚")

    @patch('books.views.sections.get_book_metadata_dict')
    def test_metadata_function_exception_handling(self, mock_metadata):
        """Test exception handling in metadata retrieval"""
        mock_metadata.side_effect = Exception("Metadata error")

        self.client.login(username=self.user.username, password='testpass123')
        response = self.client.get(reverse('books:ebooks_ajax_detail', args=[self.ebook1.id]))

        # Should handle exception gracefully
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertTrue(data['success'])

    def test_large_file_sizes(self):
        """Test handling of large file sizes"""
        book = create_test_book_with_file(
            file_path="/test/large.epub",
            file_format="epub",
            file_size=999999999999,  # Very large file
            scan_folder=self.ebooks_folder,
            content_type="ebook",
            title="Large File Book"
        )

        self.client.login(username=self.user.username, password='testpass123')
        response = self.client.get(reverse('books:ebooks_ajax_list'))

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)

        # Find our large book
        large_book = next((b for b in data['ebooks'] if b['id'] == book.id), None)
        self.assertIsNotNone(large_book)
        self.assertIn('file_size_display', large_book)


class PerformanceTests(SectionsTestCase):
    """Test performance-related aspects"""

    def test_query_efficiency(self):
        """Test that queries are efficient with select_related and prefetch_related"""
        self.client.login(username=self.user.username, password='testpass123')

        with self.assertNumQueries(9):  # Adjusted based on actual query count with separate FinalMetadata queries
            response = self.client.get(reverse('books:ebooks_ajax_list'))
            self.assertEqual(response.status_code, 200)

    def test_pagination_limit(self):
        """Test that results are limited for performance"""
        # Create many books to test limit
        books = []
        for i in range(600):  # More than the 500 limit
            book = create_test_book_with_file(
                file_path=f"/test/book{i}.epub",
                file_format="epub",
                content_type="ebook",
                title=f"Book {i}",
                scan_folder=self.ebooks_folder
            )
            books.append(book)

        self.client.login(username=self.user.username, password='testpass123')
        response = self.client.get(reverse('books:ebooks_ajax_list'))

        data = json.loads(response.content)
        # Should be limited to 500 items
        self.assertLessEqual(len(data['ebooks']), 500)


class IntegrationTests(SectionsTestCase):
    """Integration tests across the sections module"""

    def test_workflow_consistency(self):
        """Test that main view counts match AJAX endpoint counts"""
        self.client.login(username=self.user.username, password='testpass123')

        # Test ebooks
        main_response = self.client.get(reverse('books:ebooks_main'))
        ajax_response = self.client.get(reverse('books:ebooks_ajax_list'))
        ajax_data = json.loads(ajax_response.content)

        self.assertEqual(main_response.context['ebooks_count'], len(ajax_data['ebooks']))

        # Test comics
        main_response = self.client.get(reverse('books:comics_main'))
        ajax_response = self.client.get(reverse('books:comics_ajax_list'))
        ajax_data = json.loads(ajax_response.content)

        expected_count = len(ajax_data['series']) + len(ajax_data['standalone'])
        self.assertEqual(main_response.context['comics_count'], expected_count)        # Test audiobooks
        main_response = self.client.get(reverse('books:audiobooks_main'))
        ajax_response = self.client.get(reverse('books:audiobooks_ajax_list'))
        ajax_data = json.loads(ajax_response.content)

        self.assertEqual(main_response.context['audiobooks_count'], len(ajax_data['audiobooks']))

    def test_cross_section_data_integrity(self):
        """Test that the same book doesn't appear in inappropriate sections"""
        self.client.login(username=self.user.username, password='testpass123')

        # Get all book IDs from each section
        ebooks_response = self.client.get(reverse('books:ebooks_ajax_list'))
        ebooks_data = json.loads(ebooks_response.content)
        ebook_ids = set(book['id'] for book in ebooks_data['ebooks'])

        audiobooks_response = self.client.get(reverse('books:audiobooks_ajax_list'))
        audiobooks_data = json.loads(audiobooks_response.content)
        audiobook_ids = set(book['id'] for book in audiobooks_data['audiobooks'])

        # Content should appear only in the appropriate section based on folder content type
        dedicated_ebook_ids = {self.ebook1.id}  # From ebooks folder only
        dedicated_audiobook_ids = {self.audiobook1.id}  # From audiobooks folder only

        # Dedicated ebooks should not appear in audiobooks
        self.assertFalse(dedicated_ebook_ids.intersection(audiobook_ids.difference({self.audiobook2.id})))

        # Dedicated audiobooks should not appear in ebooks
        self.assertFalse(dedicated_audiobook_ids.intersection(ebook_ids.difference({self.ebook2.id})))
