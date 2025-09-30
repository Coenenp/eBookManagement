"""
Test cases for ISBN utilities
"""
from unittest.mock import patch, Mock
from django.test import TestCase, RequestFactory, Client
from django.contrib.auth.models import User
from django.urls import reverse
from books.utils.isbn import (
    normalize_isbn, is_valid_isbn13, is_valid_isbn10, convert_to_isbn13
)
from books.views import isbn_lookup


class ISBNUtilsTests(TestCase):
    """Test cases for ISBN utility functions"""

    def test_normalize_isbn_valid_isbn13(self):
        """Test normalization of valid ISBN-13"""
        isbn = "9780134685991"
        result = normalize_isbn(isbn)
        self.assertEqual(result, "9780134685991")

    def test_normalize_isbn_valid_isbn10(self):
        """Test normalization and conversion of valid ISBN-10"""
        isbn = "0134685997"
        result = normalize_isbn(isbn)
        # Should convert to ISBN-13
        self.assertEqual(result, "9780134685991")

    def test_normalize_isbn_with_hyphens(self):
        """Test normalization of ISBN with hyphens"""
        isbn = "978-0-13-468599-1"
        result = normalize_isbn(isbn)
        self.assertEqual(result, "9780134685991")

    def test_normalize_isbn_with_prefix(self):
        """Test normalization of ISBN with prefix"""
        isbn = "isbn:9780134685991"
        result = normalize_isbn(isbn)
        self.assertEqual(result, "9780134685991")

    def test_normalize_isbn_with_urn_prefix(self):
        """Test normalization of ISBN with URN prefix"""
        isbn = "urn:isbn:9780134685991"
        result = normalize_isbn(isbn)
        self.assertEqual(result, "9780134685991")

    def test_normalize_isbn_invalid_length(self):
        """Test normalization of ISBN with invalid length"""
        isbn = "978013468599"  # 12 digits
        result = normalize_isbn(isbn)
        self.assertIsNone(result)

    def test_normalize_isbn_invalid_checksum(self):
        """Test normalization of ISBN with invalid checksum"""
        isbn = "9780134685990"  # Wrong checksum
        result = normalize_isbn(isbn)
        self.assertIsNone(result)

    def test_normalize_isbn_empty_input(self):
        """Test normalization of empty input"""
        result = normalize_isbn("")
        self.assertIsNone(result)

        result = normalize_isbn(None)
        self.assertIsNone(result)

    def test_normalize_isbn_with_x_check_digit(self):
        """Test normalization of ISBN-10 with X check digit"""
        isbn = "043942089X"
        result = normalize_isbn(isbn)
        self.assertEqual(result, "9780439420891")

    def test_is_valid_isbn13_valid(self):
        """Test valid ISBN-13 validation"""
        self.assertTrue(is_valid_isbn13("9780134685991"))
        self.assertTrue(is_valid_isbn13("9781234567897"))

    def test_is_valid_isbn13_invalid(self):
        """Test invalid ISBN-13 validation"""
        self.assertFalse(is_valid_isbn13("9780134685990"))  # Wrong checksum
        self.assertFalse(is_valid_isbn13("978013468599"))   # Wrong length
        self.assertFalse(is_valid_isbn13("abc0134685991"))  # Non-numeric

    def test_is_valid_isbn10_valid(self):
        """Test valid ISBN-10 validation"""
        self.assertTrue(is_valid_isbn10("0134685997"))
        self.assertTrue(is_valid_isbn10("043942089X"))

    def test_is_valid_isbn10_invalid(self):
        """Test invalid ISBN-10 validation"""
        self.assertFalse(is_valid_isbn10("0134685996"))  # Wrong checksum
        self.assertFalse(is_valid_isbn10("013468599"))   # Wrong length
        self.assertFalse(is_valid_isbn10("abc4685997"))  # Non-numeric

    def test_convert_to_isbn13(self):
        """Test conversion from ISBN-10 to ISBN-13"""
        isbn10 = "0134685997"
        result = convert_to_isbn13(isbn10)
        self.assertEqual(result, "9780134685991")

    def test_convert_to_isbn13_with_x(self):
        """Test conversion from ISBN-10 with X to ISBN-13"""
        isbn10 = "043942089X"
        result = convert_to_isbn13(isbn10)
        self.assertEqual(result, "9780439420891")

    def test_normalize_isbn_case_insensitive(self):
        """Test normalization is case insensitive"""
        isbn_upper = "ISBN:9780134685991"
        isbn_lower = "isbn:9780134685991"

        result_upper = normalize_isbn(isbn_upper)
        result_lower = normalize_isbn(isbn_lower)

        self.assertEqual(result_upper, result_lower)
        self.assertEqual(result_upper, "9780134685991")

    def test_normalize_isbn_with_spaces(self):
        """Test normalization removes spaces"""
        isbn = "978 0 13 468599 1"
        result = normalize_isbn(isbn)
        self.assertEqual(result, "9780134685991")

    def test_normalize_isbn_mixed_formatting(self):
        """Test normalization with mixed formatting"""
        isbn = "  URN:ISBN: 978-0-13-468599-1  "
        result = normalize_isbn(isbn)
        self.assertEqual(result, "9780134685991")


class ISBNLookupViewTests(TestCase):
    """Test cases for ISBN lookup view functionality"""

    def setUp(self):
        """Set up test data"""
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )

    @patch('requests.get')
    @patch('django.core.cache.cache.get')
    @patch('django.core.cache.cache.set')
    def test_isbn_lookup_success_with_google_books(self, mock_cache_set, mock_cache_get, mock_requests_get):
        """Test successful ISBN lookup with Google Books API"""
        # Mock cache miss
        mock_cache_get.return_value = None

        # Mock Google Books API response
        google_response = Mock()
        google_response.status_code = 200
        google_response.json.return_value = {
            'items': [{
                'volumeInfo': {
                    'title': 'Test Book',
                    'authors': ['Test Author'],
                    'publisher': 'Test Publisher',
                    'publishedDate': '2023',
                    'pageCount': 300,
                    'description': 'A test book description',
                    'imageLinks': {'thumbnail': 'http://example.com/thumb.jpg'}
                }
            }]
        }

        # Mock Open Library API response
        ol_response = Mock()
        ol_response.status_code = 200
        ol_response.json.return_value = {
            'docs': [{
                'title': 'Test Book OL',
                'author_name': ['Test Author OL'],
                'publisher': ['Test Publisher OL'],
                'first_publish_year': 2023,
                'cover_i': 12345
            }]
        }

        mock_requests_get.side_effect = [google_response, ol_response]

        # Create request
        request = self.factory.get('/ajax/isbn-lookup/9780134685991/')
        request.user = self.user

        # Call the view
        response = isbn_lookup(request, '9780134685991')

        # Check response
        self.assertEqual(response.status_code, 200)

        # Parse JSON response
        import json
        data = json.loads(response.content.decode('utf-8'))

        self.assertTrue(data['success'])
        self.assertEqual(data['isbn'], '9780134685991')
        self.assertIn('sources', data)
        self.assertIn('google_books', data['sources'])
        self.assertIn('open_library', data['sources'])

        # Check Google Books data
        gb_data = data['sources']['google_books']
        self.assertTrue(gb_data['found'])
        self.assertEqual(gb_data['title'], 'Test Book')
        self.assertEqual(gb_data['authors'], ['Test Author'])

    @patch('requests.get')
    @patch('django.core.cache.cache.get')
    def test_isbn_lookup_cached_result(self, mock_cache_get, mock_requests_get):
        """Test ISBN lookup returns cached result"""
        # Mock cached result
        cached_data = {
            'success': True,
            'isbn': '9780134685991',
            'sources': {
                'google_books': {
                    'title': 'Cached Book',
                    'found': True
                }
            }
        }
        mock_cache_get.return_value = cached_data

        # Create request
        request = self.factory.get('/ajax/isbn-lookup/9780134685991/')
        request.user = self.user

        # Call the view
        response = isbn_lookup(request, '9780134685991')

        # Check response
        self.assertEqual(response.status_code, 200)

        # Parse JSON response
        import json
        data = json.loads(response.content.decode('utf-8'))

        self.assertEqual(data, cached_data)

        # Ensure requests.get was not called (cached)
        mock_requests_get.assert_not_called()

    def test_isbn_lookup_invalid_isbn_length(self):
        """Test ISBN lookup with invalid ISBN length"""
        request = self.factory.get('/ajax/isbn-lookup/123/')
        request.user = self.user

        response = isbn_lookup(request, '123')

        self.assertEqual(response.status_code, 200)

        import json
        data = json.loads(response.content.decode('utf-8'))

        self.assertFalse(data['success'])
        self.assertIn('Invalid ISBN length', data['error'])

    def test_isbn_lookup_formatted_isbn(self):
        """Test ISBN lookup works with formatted ISBN (hyphens)"""
        request = self.factory.get('/ajax/isbn-lookup/978-0-13-468599-1/')
        request.user = self.user

        # We'll test that the view doesn't crash with formatted ISBN
        # The actual API calls would be mocked in a real test
        response = isbn_lookup(request, '978-0-13-468599-1')

        self.assertEqual(response.status_code, 200)

    @patch('requests.get')
    @patch('django.core.cache.cache.get')
    def test_isbn_lookup_api_error_handling(self, mock_cache_get, mock_requests_get):
        """Test ISBN lookup handles API errors gracefully"""
        # Mock cache miss to ensure we don't get cached data
        mock_cache_get.return_value = None

        # Mock API failure
        mock_requests_get.side_effect = Exception("API Error")

        request = self.factory.get('/ajax/isbn-lookup/9780134685991/')
        request.user = self.user

        response = isbn_lookup(request, '9780134685991')

        self.assertEqual(response.status_code, 200)

        import json
        data = json.loads(response.content.decode('utf-8'))

        # The overall response should be successful (no fatal errors)
        self.assertTrue(data['success'])
        # But the individual sources should show errors/not found
        self.assertIn('sources', data)
        # Check that at least one source failed
        sources_failed = False
        for source_name, source_data in data['sources'].items():
            if not source_data.get('found', False):
                sources_failed = True
                break
        self.assertTrue(sources_failed, "At least one source should have failed")

    def test_isbn_lookup_url_endpoint(self):
        """Test ISBN lookup URL endpoint works"""
        client = Client()

        # Log in the user
        client.force_login(self.user)

        # Test that the URL is accessible (will fail on API calls but shouldn't crash)
        response = client.get(reverse('books:isbn_lookup', kwargs={'isbn': '9780134685991'}))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')


class ISBNLookupIntegrationTests(TestCase):
    """Integration tests for ISBN lookup that don't break other views"""

    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )

        from books.models import ScanFolder, Book, FinalMetadata

        self.scan_folder = ScanFolder.objects.create(
            path="/test/scan/folder",
            name="Test Scan Folder"
        )

        # Create a test book
        self.book = Book.objects.create(
            file_path="/test/path/book.epub",
            file_format="epub",
            scan_folder=self.scan_folder,
        )

        FinalMetadata.objects.create(
            book=self.book,
            final_title="Test Book",
            final_author="Test Author",
            isbn="9780134685991",
            is_reviewed=True
        )

    def test_book_list_still_works_with_isbn_lookup_enabled(self):
        """Test that book_list view still works when ISBN lookup is available"""
        client = Client()
        client.force_login(self.user)

        # Test book list view
        response = client.get(reverse('books:book_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test Book")

    def test_book_detail_still_works_with_isbn_lookup_enabled(self):
        """Test that book_detail view still works when ISBN lookup is available"""
        client = Client()
        client.force_login(self.user)

        # Test book detail view
        response = client.get(reverse('books:book_detail', kwargs={'pk': self.book.id}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test Book")

    def test_isbn_lookup_doesnt_interfere_with_book_operations(self):
        """Test that ISBN lookup doesn't interfere with normal book operations"""
        client = Client()
        client.force_login(self.user)

        # Test that we can still access book views
        response = client.get(reverse('books:book_list'))
        self.assertEqual(response.status_code, 200)

        # Test that ISBN lookup endpoint is separate and doesn't affect book views
        isbn_response = client.get(reverse('books:isbn_lookup', kwargs={'isbn': '9780134685991'}))
        self.assertEqual(isbn_response.status_code, 200)

        # Test book list again to ensure it still works
        response2 = client.get(reverse('books:book_list'))
        self.assertEqual(response2.status_code, 200)
