"""
Test suite for books/scanner/extractors/comicvine.py
Tests Comic Vine API integration and metadata extraction.
"""

from unittest.mock import patch, Mock
from django.test import TestCase, override_settings

from books.models import (
    DataSource, BookTitle, BookCover, BookPublisher, Publisher,
    BookMetadata, BookAuthor, Author, Series, BookSeries
)
from books.tests.test_helpers import create_test_book_with_file, create_test_scan_folder
from books.scanner.extractors.comicvine import (
    ComicVineAPI,
    query_comicvine_metadata,
    _save_volume_metadata,
    _save_issue_metadata,
    _save_creators,
    _save_cover_from_url
)


class ComicVineAPITests(TestCase):
    """Test ComicVineAPI class functionality"""

    def setUp(self):
        """Set up test data"""
        self.comicvine_source, _ = DataSource.objects.get_or_create(
            name=DataSource.COMICVINE,
            defaults={'trust_level': 0.8}
        )

    @patch('books.scanner.extractors.comicvine.get_api_client')
    @override_settings(COMICVINE_API_KEY='test_api_key')
    def test_api_initialization_with_key(self, mock_get_client):
        """Test API initialization with API key"""
        mock_client = Mock()
        mock_get_client.return_value = mock_client

        api = ComicVineAPI()

        self.assertEqual(api.api_key, 'test_api_key')
        self.assertEqual(api.client, mock_client)
        mock_get_client.assert_called_once_with('comic_vine')

    @patch('books.scanner.extractors.comicvine.get_api_client')
    def test_api_initialization_without_key(self, mock_get_client):
        """Test API initialization without API key"""
        with override_settings(COMICVINE_API_KEY=None):
            api = ComicVineAPI()
            self.assertIsNone(api.api_key)

    @patch('books.scanner.extractors.comicvine.get_api_client')
    @override_settings(COMICVINE_API_KEY='test_key')
    def test_make_request_success(self, mock_get_client):
        """Test successful API request"""
        mock_client = Mock()
        mock_response_data = {
            'status_code': 1,
            'results': [{'id': 123, 'name': 'Test Comic'}]
        }
        mock_client.make_request.return_value = mock_response_data
        mock_get_client.return_value = mock_client

        api = ComicVineAPI()
        result = api._make_request('test_endpoint', {'param': 'value'})

        self.assertEqual(result, mock_response_data)
        mock_client.make_request.assert_called_once()

        # Check that API key and format were added to params
        call_args = mock_client.make_request.call_args
        url, kwargs = call_args
        params = kwargs.get('params', {})
        self.assertEqual(params['api_key'], 'test_key')
        self.assertEqual(params['format'], 'json')

    @patch('books.scanner.extractors.comicvine.get_api_client')
    @override_settings(COMICVINE_API_KEY='test_key')
    def test_make_request_api_error(self, mock_get_client):
        """Test API request with API error response"""
        mock_client = Mock()
        mock_response_data = {
            'status_code': 100,  # Error status
            'error': 'Invalid API key'
        }
        mock_client.make_request.return_value = mock_response_data
        mock_get_client.return_value = mock_client

        api = ComicVineAPI()
        result = api._make_request('test_endpoint', {})

        self.assertIsNone(result)

    @patch('books.scanner.extractors.comicvine.get_api_client')
    def test_make_request_no_api_key(self, mock_get_client):
        """Test API request without API key"""
        with override_settings(COMICVINE_API_KEY=None):
            api = ComicVineAPI()
            result = api._make_request('test_endpoint', {})

            self.assertIsNone(result)

    @patch('books.scanner.extractors.comicvine.get_api_client')
    def test_make_request_no_client(self, mock_get_client):
        """Test API request when client is not available"""
        mock_get_client.return_value = None

        with override_settings(COMICVINE_API_KEY='test_key'):
            api = ComicVineAPI()
            result = api._make_request('test_endpoint', {})

            self.assertIsNone(result)

    @patch('books.scanner.extractors.comicvine.get_api_client')
    @override_settings(COMICVINE_API_KEY='test_key')
    def test_search_volumes(self, mock_get_client):
        """Test searching for volumes"""
        mock_client = Mock()
        mock_response = {
            'status_code': 1,
            'results': [
                {'id': 123, 'name': 'Amazing Spider-Man', 'start_year': 1963},
                {'id': 456, 'name': 'Spider-Man', 'start_year': 1990}
            ]
        }
        mock_client.make_request.return_value = mock_response
        mock_get_client.return_value = mock_client

        api = ComicVineAPI()
        results = api.search_volumes('Spider-Man')

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]['name'], 'Amazing Spider-Man')

    @patch('books.scanner.extractors.comicvine.get_api_client')
    @override_settings(COMICVINE_API_KEY='test_key')
    def test_search_issues(self, mock_get_client):
        """Test searching for issues within a volume"""
        mock_client = Mock()
        mock_response = {
            'status_code': 1,
            'results': [
                {'id': 789, 'name': 'Origin', 'issue_number': '1'},
                {'id': 790, 'name': 'First Hunt', 'issue_number': '2'}
            ]
        }
        mock_client.make_request.return_value = mock_response
        mock_get_client.return_value = mock_client

        api = ComicVineAPI()
        results = api.search_issues(123, issue_number=1)

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]['issue_number'], '1')

    @patch('books.scanner.extractors.comicvine.get_api_client')
    @override_settings(COMICVINE_API_KEY='test_key')
    def test_get_volume_details(self, mock_get_client):
        """Test getting volume details"""
        mock_client = Mock()
        mock_response = {
            'status_code': 1,
            'results': {'id': 123, 'name': 'Amazing Spider-Man', 'count_of_issues': 800}
        }
        mock_client.make_request.return_value = mock_response
        mock_get_client.return_value = mock_client

        api = ComicVineAPI()
        result = api.get_volume_details(123)

        self.assertIsNotNone(result)
        self.assertEqual(result['name'], 'Amazing Spider-Man')

    @patch('books.scanner.extractors.comicvine.get_api_client')
    @override_settings(COMICVINE_API_KEY='test_key')
    def test_get_issue_details(self, mock_get_client):
        """Test getting issue details"""
        mock_client = Mock()
        mock_response = {
            'status_code': 1,
            'results': {'id': 789, 'name': 'Origin', 'issue_number': '1'}
        }
        mock_client.make_request.return_value = mock_response
        mock_get_client.return_value = mock_client

        api = ComicVineAPI()
        result = api.get_issue_details(789)

        self.assertIsNotNone(result)
        self.assertEqual(result['name'], 'Origin')

    @patch('books.scanner.extractors.comicvine.get_api_client')
    @override_settings(COMICVINE_API_KEY='test_key')
    def test_search_issue(self, mock_get_client):
        """Test searching for specific issue"""
        mock_client = Mock()
        mock_response = {
            'status_code': 1,
            'results': [
                {'id': 789, 'name': 'Amazing Spider-Man #1', 'issue_number': '1'}
            ]
        }
        mock_client.make_request.return_value = mock_response
        mock_get_client.return_value = mock_client

        api = ComicVineAPI()
        result = api.search_issue('Amazing Spider-Man #1')

        self.assertIsNotNone(result)
        self.assertEqual(result['name'], 'Amazing Spider-Man #1')

    @patch('books.scanner.extractors.comicvine.get_api_client')
    @override_settings(COMICVINE_API_KEY='test_key')
    def test_search_issue_no_results(self, mock_get_client):
        """Test searching for issue with no results"""
        mock_client = Mock()
        mock_response = {
            'status_code': 1,
            'results': []
        }
        mock_client.make_request.return_value = mock_response
        mock_get_client.return_value = mock_client

        api = ComicVineAPI()
        result = api.search_issue('Nonexistent Comic')

        self.assertIsNone(result)


class ComicVineMetadataExtractionTests(TestCase):
    """Test metadata extraction and saving functionality"""

    def setUp(self):
        """Set up test data"""
        self.comicvine_source, _ = DataSource.objects.get_or_create(
            name=DataSource.COMICVINE,
            defaults={'trust_level': 0.8}
        )

        self.scan_folder = create_test_scan_folder(name="Test Scan Folder")
        self.book = create_test_book_with_file(
            file_path='/test/spider-man.cbz',
            file_format='cbz',
            file_size=50000000,
            scan_folder=self.scan_folder
        )

    def test_save_volume_metadata_basic(self):
        """Test saving basic volume metadata"""
        volume_data = {
            'name': 'Amazing Spider-Man',
            'start_year': 1963,
            'deck': 'The amazing adventures of your friendly neighborhood Spider-Man',
            'publisher': {
                'name': 'Marvel Comics'
            }
        }

        _save_volume_metadata(self.book, volume_data, self.comicvine_source)

        # Check that series was created
        series = Series.objects.filter(name='Amazing Spider-Man').first()
        self.assertIsNotNone(series)

        # Check BookSeries relationship
        book_series = BookSeries.objects.filter(book=self.book, series=series).first()
        self.assertIsNotNone(book_series)
        self.assertEqual(book_series.source, self.comicvine_source)

        # Check publisher was created
        publisher = Publisher.objects.filter(name='Marvel Comics').first()
        self.assertIsNotNone(publisher)

        # Check BookPublisher relationship
        book_publisher = BookPublisher.objects.filter(book=self.book, publisher=publisher).first()
        self.assertIsNotNone(book_publisher)

        # Check description metadata
        description_metadata = BookMetadata.objects.filter(
            book=self.book,
            field_name='description',
            source=self.comicvine_source
        ).first()
        self.assertIsNotNone(description_metadata)
        self.assertIn('Spider-Man', description_metadata.field_value)

        # Check publication year
        year_metadata = BookMetadata.objects.filter(
            book=self.book,
            field_name='publication_year',
            source=self.comicvine_source
        ).first()
        self.assertIsNotNone(year_metadata)
        self.assertEqual(year_metadata.field_value, '1963')

    def test_save_volume_metadata_minimal(self):
        """Test saving volume metadata with minimal data"""
        volume_data = {'name': 'Test Comic'}

        _save_volume_metadata(self.book, volume_data, self.comicvine_source)

        # Should create series even with minimal data
        series = Series.objects.filter(name='Test Comic').first()
        self.assertIsNotNone(series)

    def test_save_issue_metadata_basic(self):
        """Test saving basic issue metadata"""
        issue_data = {
            'name': 'Origin',
            'deck': 'The origin story of Spider-Man',
            'cover_date': '1962-08-01',
            'person_credits': [
                {'name': 'Stan Lee', 'role': 'writer'},
                {'name': 'Steve Ditko', 'role': 'artist'}
            ]
        }

        _save_issue_metadata(self.book, issue_data, self.comicvine_source)

        # Check title was saved
        book_title = BookTitle.objects.filter(
            book=self.book,
            source=self.comicvine_source
        ).first()
        self.assertIsNotNone(book_title)
        self.assertEqual(book_title.title, 'Origin')

        # Check description
        description = BookMetadata.objects.filter(
            book=self.book,
            field_name='description',
            source=self.comicvine_source
        ).first()
        self.assertIsNotNone(description)

        # Check publication year extracted from cover date
        year = BookMetadata.objects.filter(
            book=self.book,
            field_name='publication_year',
            source=self.comicvine_source
        ).first()
        self.assertIsNotNone(year)
        self.assertEqual(year.field_value, '1962')

        # Check creators were saved
        stan_lee = Author.objects.filter(name='Stan Lee').first()
        self.assertIsNotNone(stan_lee)

        book_author = BookAuthor.objects.filter(
            book=self.book,
            author=stan_lee,
            source=self.comicvine_source
        ).first()
        self.assertIsNotNone(book_author)

    def test_save_creators_main_author_detection(self):
        """Test creator saving with main author detection"""
        person_credits = [
            {'name': 'Stan Lee', 'role': 'writer'},
            {'name': 'Steve Ditko', 'role': 'artist'},
            {'name': 'John Doe', 'role': 'colorist'}
        ]

        _save_creators(self.book, person_credits, self.comicvine_source)

        # Check that writer is marked as main author
        stan_lee_author = BookAuthor.objects.filter(
            book=self.book,
            author__name='Stan Lee',
            source=self.comicvine_source
        ).first()
        self.assertIsNotNone(stan_lee_author)
        self.assertTrue(stan_lee_author.is_main_author)

        # Check that artist is not marked as main author
        steve_ditko_author = BookAuthor.objects.filter(
            book=self.book,
            author__name='Steve Ditko',
            source=self.comicvine_source
        ).first()
        self.assertIsNotNone(steve_ditko_author)
        self.assertFalse(steve_ditko_author.is_main_author)

    def test_save_creators_limit(self):
        """Test that creator saving respects the limit"""
        # Create more than 5 creators
        person_credits = [
            {'name': f'Creator {i}', 'role': 'contributor'}
            for i in range(10)
        ]

        _save_creators(self.book, person_credits, self.comicvine_source)

        # Should only save 5 creators
        author_count = BookAuthor.objects.filter(
            book=self.book,
            source=self.comicvine_source
        ).count()
        self.assertEqual(author_count, 5)

    @patch('requests.get')
    @patch('PIL.Image.open')
    def test_save_cover_from_url_success(self, mock_image_open, mock_requests_get):
        """Test successful cover download and save"""
        # Mock HTTP response
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.iter_content.return_value = [b'fake_image_data'] * 100
        mock_requests_get.return_value = mock_response

        # Mock PIL Image
        mock_image = Mock()
        mock_image.mode = 'RGB'
        mock_image.size = (300, 450)
        mock_image_open.return_value.__enter__ = Mock(return_value=mock_image)
        mock_image_open.return_value.__exit__ = Mock(return_value=None)

        # Mock file size
        with patch('os.path.getsize', return_value=12345):
            _save_cover_from_url(
                self.book,
                'https://comicvine.gamespot.com/image.jpg',
                self.comicvine_source
            )

        # Check that cover was saved to database
        book_cover = BookCover.objects.filter(
            book=self.book,
            source=self.comicvine_source
        ).first()
        self.assertIsNotNone(book_cover)
        self.assertEqual(book_cover.width, 300)
        self.assertEqual(book_cover.height, 450)
        self.assertEqual(book_cover.format, 'jpg')
        self.assertEqual(book_cover.file_size, 12345)

    @patch('requests.get')
    def test_save_cover_from_url_http_error(self, mock_requests_get):
        """Test cover download with HTTP error"""
        mock_requests_get.side_effect = Exception('HTTP Error')

        # Should not raise exception
        _save_cover_from_url(
            self.book,
            'https://invalid-url.com/image.jpg',
            self.comicvine_source
        )

        # No cover should be saved
        book_cover_count = BookCover.objects.filter(
            book=self.book,
            source=self.comicvine_source
        ).count()
        self.assertEqual(book_cover_count, 0)


class ComicVineIntegrationTests(TestCase):
    """Integration tests for Comic Vine functionality"""

    def setUp(self):
        """Set up test data"""
        self.comicvine_source, _ = DataSource.objects.get_or_create(
            name=DataSource.COMICVINE,
            defaults={'trust_level': 0.8}
        )

        self.scan_folder = create_test_scan_folder(name="Test Scan Folder")
        self.book = create_test_book_with_file(
            file_path='/test/spider-man-001.cbz',
            file_format='cbz',
            file_size=50000000,
            scan_folder=self.scan_folder
        )

    @patch('books.scanner.extractors.comicvine.ComicVineAPI')
    def test_query_comicvine_metadata_success(self, mock_api_class):
        """Test successful Comic Vine metadata query"""
        # Mock API responses
        mock_api = Mock()
        mock_api_class.return_value = mock_api

        # Mock search volumes response
        mock_api.search_volumes.return_value = [
            {
                'id': 123,
                'name': 'Amazing Spider-Man',
                'start_year': 1963,
                'publisher': {'name': 'Marvel Comics'}
            }
        ]

        # Mock search issues response
        mock_api.search_issues.return_value = [
            {
                'id': 789,
                'name': 'Origin',
                'issue_number': '1',
                'cover_date': '1962-08-01',
                'person_credits': [
                    {'name': 'Stan Lee', 'role': 'writer'}
                ]
            }
        ]

        result = query_comicvine_metadata(self.book, 'Amazing Spider-Man', issue_number=1)

        self.assertTrue(result)

        # Verify API calls
        mock_api.search_volumes.assert_called_once_with('Amazing Spider-Man')
        mock_api.search_issues.assert_called_once_with(123, 1, limit=1)

        # Verify metadata was saved
        series = Series.objects.filter(name='Amazing Spider-Man').first()
        self.assertIsNotNone(series)

    @patch('books.scanner.extractors.comicvine.ComicVineAPI')
    def test_query_comicvine_metadata_no_volumes(self, mock_api_class):
        """Test Comic Vine query when no volumes found"""
        mock_api = Mock()
        mock_api_class.return_value = mock_api
        mock_api.search_volumes.return_value = []

        result = query_comicvine_metadata(self.book, 'Nonexistent Comic')

        self.assertFalse(result)
        mock_api.search_volumes.assert_called_once_with('Nonexistent Comic')
        mock_api.search_issues.assert_not_called()

    @patch('books.scanner.extractors.comicvine.ComicVineAPI')
    def test_query_comicvine_metadata_no_specific_issue(self, mock_api_class):
        """Test Comic Vine query when specific issue not found"""
        mock_api = Mock()
        mock_api_class.return_value = mock_api

        mock_api.search_volumes.return_value = [
            {'id': 123, 'name': 'Amazing Spider-Man', 'start_year': 1963}
        ]
        mock_api.search_issues.return_value = []  # No issues found

        result = query_comicvine_metadata(self.book, 'Amazing Spider-Man', issue_number=999)

        # Should still return True for volume-level metadata
        self.assertTrue(result)

        mock_api.search_volumes.assert_called_once()
        mock_api.search_issues.assert_called_once_with(123, 999, limit=1)

    @patch('books.scanner.extractors.comicvine.ComicVineAPI')
    def test_query_comicvine_metadata_exception_handling(self, mock_api_class):
        """Test exception handling in Comic Vine query"""
        mock_api = Mock()
        mock_api_class.return_value = mock_api
        mock_api.search_volumes.side_effect = Exception('API Error')

        # Should not raise exception
        result = query_comicvine_metadata(self.book, 'Test Comic')

        # Result may vary based on implementation, but should not crash
        self.assertIsNotNone(result)


class ComicVineConfigurationTests(TestCase):
    """Test Comic Vine configuration and settings"""

    def test_api_without_settings(self):
        """Test API behavior without proper settings"""
        # Ensure no API key is set
        with self.settings(COMICVINE_API_KEY=None):
            api = ComicVineAPI()
            result = api._make_request('test', {})

            self.assertIsNone(result)

    @override_settings(COMICVINE_API_KEY='test_key')
    def test_api_with_settings(self):
        """Test API initialization with proper settings"""
        api = ComicVineAPI()
        self.assertEqual(api.api_key, 'test_key')

    def test_cache_key_generation(self):
        """Test that cache keys are generated consistently"""
        api = ComicVineAPI()

        # Mock the client to avoid actual requests
        with patch.object(api, 'client') as mock_client:
            mock_client.make_request.return_value = {'status_code': 1, 'results': []}

            # Make the same request twice
            params = {'query': 'test', 'limit': 5}
            api._make_request('search', params.copy())
            api._make_request('search', params.copy())

            # Should use the same cache key
            self.assertEqual(mock_client.make_request.call_count, 2)

            # Cache keys should be consistent
            call1_kwargs = mock_client.make_request.call_args_list[0][1]
            call2_kwargs = mock_client.make_request.call_args_list[1][1]
            self.assertEqual(call1_kwargs['cache_key'], call2_kwargs['cache_key'])


class ComicVineErrorHandlingTests(TestCase):
    """Test error handling and edge cases"""

    def setUp(self):
        """Set up test data"""
        self.comicvine_source, _ = DataSource.objects.get_or_create(
            name=DataSource.COMICVINE,
            defaults={'trust_level': 0.8}
        )

        self.scan_folder = create_test_scan_folder(name="Test Scan Folder")
        self.book = create_test_book_with_file(
            file_path='/test/test.cbz',
            file_format='cbz',
            file_size=1000000,
            scan_folder=self.scan_folder,
            title=None  # Don't create a default title for ComicVine tests
        )

    def test_save_volume_metadata_with_missing_fields(self):
        """Test saving volume metadata with missing optional fields"""
        volume_data = {
            'name': 'Test Comic',
            'publisher': None,  # Missing publisher
            # Missing description, start_year, etc.
        }

        # Should not raise exception
        _save_volume_metadata(self.book, volume_data, self.comicvine_source)

        # Series should still be created
        series = Series.objects.filter(name='Test Comic').first()
        self.assertIsNotNone(series)

    def test_save_issue_metadata_invalid_date(self):
        """Test saving issue metadata with invalid cover date"""
        issue_data = {
            'name': 'Test Issue',
            'cover_date': 'invalid-date-format'
        }

        # Should not raise exception
        _save_issue_metadata(self.book, issue_data, self.comicvine_source)

        # Title should still be saved
        title = BookTitle.objects.filter(book=self.book).first()
        self.assertIsNotNone(title)
        self.assertEqual(title.title, 'Test Issue')

        # No year should be saved due to invalid date
        year = BookMetadata.objects.filter(
            book=self.book,
            field_name='publication_year'
        ).first()
        self.assertIsNone(year)

    def test_save_creators_empty_list(self):
        """Test saving creators with empty list"""
        _save_creators(self.book, [], self.comicvine_source)

        # No authors should be created
        author_count = BookAuthor.objects.filter(book=self.book).count()
        self.assertEqual(author_count, 0)

    def test_save_creators_missing_name(self):
        """Test saving creators with missing names"""
        person_credits = [
            {'role': 'writer'},  # Missing name
            {'name': 'Valid Creator', 'role': 'artist'}
        ]

        _save_creators(self.book, person_credits, self.comicvine_source)

        # Only the valid creator should be saved
        author_count = BookAuthor.objects.filter(book=self.book).count()
        self.assertEqual(author_count, 1)

        author = Author.objects.filter(name='Valid Creator').first()
        self.assertIsNotNone(author)

    @patch('requests.get')
    def test_save_cover_from_url_permission_error(self, mock_requests_get):
        """Test cover download with file permission error"""
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.iter_content.return_value = [b'data']
        mock_requests_get.return_value = mock_response

        with patch('tempfile.NamedTemporaryFile') as mock_temp:
            mock_temp.side_effect = PermissionError('Access denied')

            # Should not raise exception
            _save_cover_from_url(
                self.book,
                'https://example.com/cover.jpg',
                self.comicvine_source
            )

            # No cover should be saved
            cover_count = BookCover.objects.filter(book=self.book).count()
            self.assertEqual(cover_count, 0)


class ComicVinePerformanceTests(TestCase):
    """Test performance aspects of Comic Vine integration"""

    def setUp(self):
        """Set up test data"""
        self.comicvine_source, _ = DataSource.objects.get_or_create(
            name=DataSource.COMICVINE,
            defaults={'trust_level': 0.8}
        )

    def test_large_creator_list_handling(self):
        """Test handling of large creator lists"""
        scan_folder = create_test_scan_folder(name="Test Scan Folder")
        book = create_test_book_with_file(
            file_path='/test/test.cbz',
            file_format='cbz',
            file_size=1000000,
            scan_folder=scan_folder
        )

        # Create a large list of creators
        large_creator_list = [
            {'name': f'Creator {i}', 'role': 'contributor'}
            for i in range(100)
        ]

        _save_creators(book, large_creator_list, self.comicvine_source)

        # Should still respect the 5-creator limit
        author_count = BookAuthor.objects.filter(book=book).count()
        self.assertEqual(author_count, 5)

    def test_metadata_deduplication(self):
        """Test that duplicate metadata isn't created"""
        scan_folder = create_test_scan_folder(name="Test Scan Folder")
        book = create_test_book_with_file(
            file_path='/test/test.cbz',
            file_format='cbz',
            file_size=1000000,
            scan_folder=scan_folder
        )

        volume_data = {
            'name': 'Test Comic',
            'start_year': 2020,
            'publisher': {'name': 'Test Publisher'}
        }

        # Save the same metadata twice
        _save_volume_metadata(book, volume_data, self.comicvine_source)
        _save_volume_metadata(book, volume_data, self.comicvine_source)

        # Should only have one of each metadata record
        series_count = BookSeries.objects.filter(book=book).count()
        self.assertEqual(series_count, 1)

        publisher_count = BookPublisher.objects.filter(book=book).count()
        self.assertEqual(publisher_count, 1)

        year_count = BookMetadata.objects.filter(
            book=book,
            field_name='publication_year'
        ).count()
        self.assertEqual(year_count, 1)
