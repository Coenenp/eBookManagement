"""Comprehensive tests for books.templatetags module.

Tests for book_extras.py and custom_filters.py template tags.
Focuses on achieving higher coverage for template tag functionality.
"""
import os
import django
from django.test import TestCase, RequestFactory
from django.template import Context, Template
from unittest.mock import patch, Mock, mock_open, PropertyMock

from books.models import (
    DataSource, ScanFolder, Book, FinalMetadata, Author
)
from books.templatetags import book_extras, custom_filters

# Must set Django settings before importing Django models
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ebook_manager.settings')
django.setup()


class BookExtrasTemplateTagsTests(TestCase):
    """Test book_extras.py template tags"""

    def setUp(self):
        self.factory = RequestFactory()
        self.scan_folder = ScanFolder.objects.create(path='/test/path')
        self.book = Book.objects.create(
            file_path='/test/path/test_book.epub',
            file_size=1000,
            file_format='epub',
            scan_folder=self.scan_folder
        )
        self.data_source, _ = DataSource.objects.get_or_create(
            name=DataSource.MANUAL,
            defaults={'trust_level': 0.9}
        )
        self.final_metadata = FinalMetadata.objects.create(
            book=self.book,
            final_title='Test Title',
            final_author='Test Author',
            final_cover_path='/test/cover.jpg',
            is_reviewed=True  # Prevent auto-updating
        )

    @patch('books.templatetags.book_extras.encode_cover_to_base64')
    @patch('books.templatetags.book_extras.requests.get')
    @patch('os.path.exists')
    @patch('os.makedirs')
    def test_download_and_cache_cover_success(self, mock_makedirs, mock_exists, mock_get, mock_encode):
        """Test successful cover download and caching"""
        # Setup mocks
        mock_exists.return_value = False  # Cache doesn't exist
        mock_response = Mock()
        mock_response.content = b'fake_image_content'
        mock_get.return_value = mock_response
        mock_encode.return_value = 'base64_encoded_image'

        with patch('builtins.open', mock_open()) as mock_file:
            result = book_extras.download_and_cache_cover('http://example.com/cover.jpg', 1)

        self.assertEqual(result, 'base64_encoded_image')
        mock_get.assert_called_once_with('http://example.com/cover.jpg', timeout=10)
        mock_file.assert_called()
        mock_encode.assert_called()

    @patch('books.templatetags.book_extras.encode_cover_to_base64')
    @patch('os.path.exists')
    def test_download_and_cache_cover_cached(self, mock_exists, mock_encode):
        """Test cover download when already cached"""
        mock_exists.return_value = True  # Cache exists
        mock_encode.return_value = 'cached_base64_image'

        result = book_extras.download_and_cache_cover('http://example.com/cover.jpg', 1)

        self.assertEqual(result, 'cached_base64_image')
        mock_encode.assert_called()

    @patch('books.templatetags.book_extras.requests.get')
    def test_download_and_cache_cover_error(self, mock_get):
        """Test cover download with error"""
        mock_get.side_effect = Exception('Network error')

        result = book_extras.download_and_cache_cover('http://example.com/cover.jpg', 1)

        self.assertIsNone(result)

    def test_get_fallback_context(self):
        """Test _get_fallback_context function"""
        result = book_extras._get_fallback_context(self.book, 'large', 'New')

        expected = {
            'book': self.book,
            'cover_path': '',
            'is_url': False,
            'size': 'large',
            'badge': 'New',
            'base64_image': None,
        }
        self.assertEqual(result, expected)

    @patch('books.templatetags.book_extras.encode_cover_to_base64')
    @patch('os.path.exists')
    def test_process_cover_for_display_local_file(self, mock_exists, mock_encode):
        """Test _process_cover_for_display with local file"""
        mock_exists.return_value = True
        mock_encode.return_value = 'local_base64_image'

        cover_path, is_url, base64_image = book_extras._process_cover_for_display(
            '/local/path/cover.jpg', self.book, False
        )

        self.assertEqual(cover_path, '/local/path/cover.jpg')
        self.assertFalse(is_url)
        self.assertEqual(base64_image, 'local_base64_image')

    @patch('books.templatetags.book_extras.download_and_cache_cover')
    def test_process_cover_for_display_url(self, mock_download):
        """Test _process_cover_for_display with URL"""
        mock_download.return_value = 'url_base64_image'

        cover_path, is_url, base64_image = book_extras._process_cover_for_display(
            'http://example.com/cover.jpg', self.book, False
        )

        self.assertEqual(cover_path, 'http://example.com/cover.jpg')
        self.assertFalse(is_url)  # Should be False because we have base64
        self.assertEqual(base64_image, 'url_base64_image')

    def test_process_cover_for_display_empty_path(self):
        """Test _process_cover_for_display with empty path"""
        cover_path, is_url, base64_image = book_extras._process_cover_for_display(
            '', self.book, False
        )

        self.assertEqual(cover_path, '')
        self.assertFalse(is_url)
        self.assertIsNone(base64_image)

    @patch('books.templatetags.book_extras._process_cover_for_display')
    def test_book_cover_from_metadata_success(self, mock_process):
        """Test book_cover_from_metadata template tag success"""
        mock_process.return_value = ('/test/cover.jpg', False, 'base64_image')

        # Create a mock cover object
        cover = Mock()
        cover.cover_path = '/test/cover.jpg'

        result = book_extras.book_cover_from_metadata(cover, self.book, 'large', 'New')

        expected = {
            'book': self.book,
            'cover_path': '/test/cover.jpg',
            'is_url': False,
            'size': 'large',
            'badge': 'New',
            'base64_image': 'base64_image',
        }
        self.assertEqual(result, expected)

    def test_book_cover_from_metadata_error(self):
        """Test book_cover_from_metadata template tag with error"""
        # Create a problematic cover object that will raise an exception
        cover = Mock()
        cover.cover_path = Mock(side_effect=Exception("Test error"))

        with patch('books.templatetags.book_extras._process_cover_for_display') as mock_process:
            mock_process.side_effect = Exception("Processing error")
            result = book_extras.book_cover_from_metadata(cover, self.book)

        # Should return fallback context when exception occurs
        expected = {
            'book': self.book,
            'cover_path': '',
            'is_url': False,
            'size': 'medium',
            'badge': None,
            'base64_image': None,
        }
        self.assertEqual(result, expected)

    @patch('books.templatetags.book_extras._process_cover_for_display')
    def test_book_cover_with_cover_data(self, mock_process):
        """Test book_cover template tag with existing cover data"""
        mock_process.return_value = ('/test/cover.jpg', False, None)

        # Set up book with cover data
        self.book._cover_data = {
            'cover_path': '/test/cover.jpg',
            'cover_base64': 'existing_base64'
        }

        result = book_extras.book_cover(self.book, 'medium', 'Hot')

        expected = {
            'book': self.book,
            'cover_path': '/test/cover.jpg',
            'is_url': False,  # Should be False because we have base64
            'size': 'medium',
            'badge': 'Hot',
            'base64_image': 'existing_base64',
        }
        self.assertEqual(result, expected)

    @patch('books.templatetags.book_extras._process_cover_for_display')
    def test_book_cover_fallback_to_finalmetadata(self, mock_process):
        """Test book_cover template tag fallback to finalmetadata"""
        mock_process.return_value = ('/test/cover.jpg', False, 'processed_base64')

        result = book_extras.book_cover(self.book)

        self.assertEqual(result['cover_path'], '/test/cover.jpg')
        self.assertEqual(result['base64_image'], 'processed_base64')

    def test_book_cover_no_finalmetadata(self):
        """Test book_cover template tag with no finalmetadata"""
        # Create book without finalmetadata
        book_no_meta = Book.objects.create(
            file_path='/test/no_meta.epub',
            file_size=1000,
            file_format='epub',
            scan_folder=self.scan_folder
        )
        book_no_meta.cover_path = '/fallback/cover.jpg'

        with patch('books.templatetags.book_extras._process_cover_for_display') as mock_process:
            mock_process.return_value = ('/fallback/cover.jpg', False, None)
            result = book_extras.book_cover(book_no_meta)

        self.assertEqual(result['cover_path'], '/fallback/cover.jpg')

    def test_safe_finalmetadata_with_metadata(self):
        """Test safe_finalmetadata filter with existing metadata"""
        result = book_extras.safe_finalmetadata(self.book, 'final_title')
        self.assertEqual(result, 'Test Title')

    def test_safe_finalmetadata_no_metadata(self):
        """Test safe_finalmetadata filter without metadata"""
        book_no_meta = Book.objects.create(
            file_path='/test/no_meta.epub',
            file_size=1000,
            file_format='epub',
            scan_folder=self.scan_folder
        )

        result = book_extras.safe_finalmetadata(book_no_meta, 'final_title')
        self.assertIsNone(result)

    def test_safe_finalmetadata_nonexistent_field(self):
        """Test safe_finalmetadata filter with nonexistent field"""
        result = book_extras.safe_finalmetadata(self.book, 'nonexistent_field')
        self.assertIsNone(result)

    def test_has_finalmetadata_true(self):
        """Test has_finalmetadata filter returns True"""
        result = book_extras.has_finalmetadata(self.book)
        self.assertTrue(result)

    def test_has_finalmetadata_false(self):
        """Test has_finalmetadata filter returns False"""
        book_no_meta = Book.objects.create(
            file_path='/test/no_meta.epub',
            file_size=1000,
            file_format='epub',
            scan_folder=self.scan_folder
        )

        result = book_extras.has_finalmetadata(book_no_meta)
        self.assertFalse(result)

    def test_has_finalmetadata_exception(self):
        """Test has_finalmetadata filter with exception"""
        # Create a mock book that raises an exception when accessing finalmetadata
        mock_book = Mock()
        # Make hasattr raise an exception
        type(mock_book).finalmetadata = PropertyMock(side_effect=Exception('Error'))

        result = book_extras.has_finalmetadata(mock_book)
        self.assertFalse(result)

    def test_language_display_valid_code(self):
        """Test language_display filter with valid language code"""
        result = book_extras.language_display('en')
        self.assertEqual(result, 'English')

    def test_language_display_invalid_code(self):
        """Test language_display filter with invalid language code"""
        result = book_extras.language_display('xx')
        self.assertEqual(result, 'xx')

    def test_language_display_empty(self):
        """Test language_display filter with empty input"""
        result = book_extras.language_display('')
        self.assertEqual(result, '')

    def test_language_name_alias(self):
        """Test language_name filter (alias for language_display)"""
        result = book_extras.language_name('fr')
        self.assertEqual(result, 'French')


class CustomFiltersTemplateTagsTests(TestCase):
    """Test custom_filters.py template tags"""

    def setUp(self):
        self.factory = RequestFactory()
        self.data_source, _ = DataSource.objects.get_or_create(name='Test Source', defaults={'trust_level': 0.8})
        self.scan_folder = ScanFolder.objects.create(
            path='/test/path',
            is_active=True
        )
        self.book = Book.objects.create(
            file_path='/test/path/test_book.epub',
            file_size=1000,
            file_format='epub',
            scan_folder=self.scan_folder
        )

        # Create source data for auto-update to pull from
        from books.models import Author, BookTitle, BookAuthor
        author = Author.objects.create(name='Test Author')
        BookTitle.objects.create(
            book=self.book,
            title='Test Title',
            source=self.data_source,
            confidence=1.0
        )
        BookAuthor.objects.create(
            book=self.book,
            author=author,
            source=self.data_source,
            confidence=1.0,
            is_main_author=True
        )

        self.final_metadata = FinalMetadata.objects.create(
            book=self.book,
            final_title='Test Title',
            final_author='Test Author',
            is_reviewed=True  # Prevent auto-updating
        )

    def test_mul_filter_valid_numbers(self):
        """Test mul filter with valid numbers"""
        result = custom_filters.mul(5, 3)
        self.assertEqual(result, 15.0)

    def test_mul_filter_strings(self):
        """Test mul filter with string numbers"""
        result = custom_filters.mul('5.5', '2')
        self.assertEqual(result, 11.0)

    def test_mul_filter_invalid(self):
        """Test mul filter with invalid input"""
        result = custom_filters.mul('invalid', 5)
        self.assertEqual(result, 0)

    def test_field_label_filter(self):
        """Test field_label filter"""
        result = custom_filters.field_label('final_title_confidence')
        self.assertEqual(result, 'Final Title Confidence')

    def test_dict_get_filter_valid(self):
        """Test dict_get filter with valid dictionary"""
        test_dict = {'key1': 'value1', 'key2': 'value2'}
        result = custom_filters.dict_get(test_dict, 'key1')
        self.assertEqual(result, 'value1')

    def test_dict_get_filter_missing_key(self):
        """Test dict_get filter with missing key"""
        test_dict = {'key1': 'value1'}
        result = custom_filters.dict_get(test_dict, 'key2')
        self.assertEqual(result, '')

    def test_dict_get_filter_not_dict(self):
        """Test dict_get filter with non-dictionary"""
        result = custom_filters.dict_get('not_a_dict', 'key')
        self.assertEqual(result, '')

    def test_getattr_safe_filter_valid(self):
        """Test getattr_safe filter with valid attribute"""
        result = custom_filters.getattr_safe(self.book, 'filename')
        self.assertEqual(result, 'test_book.epub')

    def test_getattr_safe_filter_missing(self):
        """Test getattr_safe filter with missing attribute"""
        result = custom_filters.getattr_safe(self.book, 'nonexistent_attr')
        self.assertEqual(result, '')

    def test_get_item_filter(self):
        """Test get_item filter"""
        test_dict = {'key1': 'value1', 'key2': 'value2'}
        result = custom_filters.get_item(test_dict, 'key1')
        self.assertEqual(result, 'value1')

    def test_querystring_tag(self):
        """Test querystring simple tag"""
        request = self.factory.get('/test/?existing=value')
        result = custom_filters.querystring(request.GET, 'new_param', 'new_value')

        # Should contain both existing and new parameters
        self.assertIn('existing=value', result)
        self.assertIn('new_param=new_value', result)

    def test_prettify_field_name_filter(self):
        """Test prettify_field_name filter"""
        result = custom_filters.prettify_field_name('final_author_confidence')
        self.assertEqual(result, 'Final Author Confidence')

    def test_get_display_title_with_finalmetadata(self):
        """Test get_display_title filter with finalmetadata"""
        result = custom_filters.get_display_title(self.book)
        self.assertEqual(result, 'Test Title')

    def test_get_display_title_fallback_to_titles(self):
        """Test get_display_title filter fallback to titles"""
        # Create book without finalmetadata but with titles
        from books.models import BookTitle
        book_no_final = Book.objects.create(
            file_path='/test/no_final.epub',
            file_size=1000,
            file_format='epub',
            scan_folder=self.scan_folder
        )

        filename_source, _ = DataSource.objects.get_or_create(
            name=DataSource.INITIAL_SCAN,
            defaults={'trust_level': 0.5}
        )
        BookTitle.objects.create(
            book=book_no_final,
            title='Title from BookTitle',
            source=filename_source,
            confidence=0.8
        )

        result = custom_filters.get_display_title(book_no_final)
        self.assertEqual(result, 'Title from BookTitle')

    def test_get_display_title_fallback_to_filename(self):
        """Test get_display_title filter fallback to filename"""
        book_no_meta = Book.objects.create(
            file_path='/test/fallback_book.epub',
            file_size=1000,
            file_format='epub',
            scan_folder=self.scan_folder
        )

        result = custom_filters.get_display_title(book_no_meta)
        self.assertEqual(result, 'fallback_book')

    def test_get_display_title_error_handling(self):
        """Test get_display_title filter error handling"""
        # Create a problematic book mock
        mock_book = Mock()
        # Make accessing finalmetadata raise an exception
        type(mock_book).finalmetadata = PropertyMock(side_effect=Exception('Error'))
        mock_book.titles = Mock(side_effect=Exception('Error'))
        mock_book.filename = 'error_book.epub'

        result = custom_filters.get_display_title(mock_book)
        self.assertEqual(result, 'Unknown Title')

    def test_get_display_author_with_finalmetadata(self):
        """Test get_display_author filter with finalmetadata"""
        result = custom_filters.get_display_author(self.book)
        self.assertEqual(result, 'Test Author')

    def test_get_display_author_fallback(self):
        """Test get_display_author filter fallback to BookAuthor"""
        # Create book without final author
        book_no_final = Book.objects.create(
            file_path='/test/no_final_author.epub',
            file_size=1000,
            file_format='epub',
            scan_folder=self.scan_folder
        )

        from books.models import BookAuthor
        author = Author.objects.create(name='Fallback Author')
        epub_source, _ = DataSource.objects.get_or_create(
            name=DataSource.EPUB_INTERNAL,
            defaults={'trust_level': 0.7}
        )
        BookAuthor.objects.create(
            book=book_no_final,
            author=author,
            source=epub_source,
            confidence=0.8
        )

        result = custom_filters.get_display_author(book_no_final)
        self.assertEqual(result, 'Fallback Author')

    def test_get_display_author_no_author(self):
        """Test get_display_author filter with no author"""
        book_no_author = Book.objects.create(
            file_path='/test/no_author.epub',
            file_size=1000,
            file_format='epub',
            scan_folder=self.scan_folder
        )

        result = custom_filters.get_display_author(book_no_author)
        self.assertEqual(result, 'Unknown Author')

    def test_safe_confidence_format_valid(self):
        """Test safe_confidence_format filter with valid confidence"""
        result = custom_filters.safe_confidence_format(0.8567)
        self.assertEqual(result, '0.86')

    def test_safe_confidence_format_none(self):
        """Test safe_confidence_format filter with None"""
        result = custom_filters.safe_confidence_format(None)
        self.assertEqual(result, '0.00')

    def test_safe_confidence_format_invalid(self):
        """Test safe_confidence_format filter with invalid value"""
        result = custom_filters.safe_confidence_format('invalid')
        self.assertEqual(result, '0.00')

    def test_sanitize_html_valid(self):
        """Test sanitize_html filter with valid HTML"""
        html = '<p>This is <b>bold</b> and <i>italic</i> text.</p>'
        result = custom_filters.sanitize_html(html)
        self.assertEqual(result, '<p>This is <b>bold</b> and <i>italic</i> text.</p>')

    def test_sanitize_html_dangerous(self):
        """Test sanitize_html filter with dangerous HTML"""
        html = '<script>alert("dangerous")</script><p>Safe content</p>'
        result = custom_filters.sanitize_html(html)
        self.assertEqual(result, '<p>Safe content</p>')

    def test_sanitize_html_empty(self):
        """Test sanitize_html filter with empty content"""
        result = custom_filters.sanitize_html('')
        self.assertEqual(result, '')

    def test_sanitize_description_basic_html(self):
        """Test sanitize_description filter with basic HTML"""
        html = '<p>This is a <b>description</b> with some HTML.</p>'
        result = custom_filters.sanitize_description(html)
        self.assertEqual(result, '<p>This is a <b>description</b> with some HTML.</p>')

    def test_sanitize_description_class_removal(self):
        """Test sanitize_description filter removes class attributes"""
        html = '<p class="unwanted-class">Clean description</p>'
        result = custom_filters.sanitize_description(html)
        self.assertEqual(result, '<p>Clean description</p>')

    def test_sanitize_description_encoding_fix(self):
        """Test sanitize_description filter fixes encoding issues"""
        html = 'Text with â€œquotesâ€ and â€˜apostrophesâ€™'
        result = custom_filters.sanitize_description(html)
        self.assertIn('"quotes"', result)
        self.assertIn("'apostrophes'", result)

    def test_sanitize_description_source_citation_removal(self):
        """Test sanitize_description filter removes source citations"""
        html = 'Great book description (source: Some Website)'
        result = custom_filters.sanitize_description(html)
        self.assertEqual(result, 'Great book description')

    def test_language_name_filter(self):
        """Test language_name filter"""
        result = custom_filters.language_name('es')
        self.assertEqual(result, 'Spanish')

    def test_url_replace_tag(self):
        """Test url_replace simple tag"""
        request = self.factory.get('/test/?page=1&sort=title')
        context = {'request': request}

        result = custom_filters.url_replace(context, page=2, filter='new')

        # Should contain updated page and new filter, but keep sort
        self.assertIn('page=2', result)
        self.assertIn('filter=new', result)
        self.assertIn('sort=title', result)

    def test_is_valid_isbn_valid_isbn10(self):
        """Test is_valid_isbn filter with valid ISBN-10"""
        self.assertTrue(custom_filters.is_valid_isbn('0123456789'))
        self.assertTrue(custom_filters.is_valid_isbn('012345678X'))

    def test_is_valid_isbn_valid_isbn13(self):
        """Test is_valid_isbn filter with valid ISBN-13"""
        self.assertTrue(custom_filters.is_valid_isbn('9780123456789'))

    def test_is_valid_isbn_formatted(self):
        """Test is_valid_isbn filter with formatted ISBN"""
        self.assertTrue(custom_filters.is_valid_isbn('978-0-123-45678-9'))
        self.assertTrue(custom_filters.is_valid_isbn('0-123-45678-9'))

    def test_is_valid_isbn_invalid(self):
        """Test is_valid_isbn filter with invalid ISBN"""
        self.assertFalse(custom_filters.is_valid_isbn('123'))  # Too short
        self.assertFalse(custom_filters.is_valid_isbn('01234567890123456'))  # Too long
        self.assertFalse(custom_filters.is_valid_isbn('012345678Z'))  # Invalid character
        self.assertFalse(custom_filters.is_valid_isbn(''))  # Empty
        self.assertFalse(custom_filters.is_valid_isbn(None))  # None

    def test_isbn_type_isbn10(self):
        """Test isbn_type filter with ISBN-10"""
        self.assertEqual(custom_filters.isbn_type('0123456789'), 'ISBN-10')
        self.assertEqual(custom_filters.isbn_type('012345678X'), 'ISBN-10')

    def test_isbn_type_isbn13(self):
        """Test isbn_type filter with ISBN-13"""
        self.assertEqual(custom_filters.isbn_type('9780123456789'), 'ISBN-13')

    def test_isbn_type_invalid(self):
        """Test isbn_type filter with invalid ISBN"""
        self.assertEqual(custom_filters.isbn_type('123'), 'Invalid')
        self.assertEqual(custom_filters.isbn_type('012345678Z'), 'Invalid')

    def test_isbn_type_no_isbn(self):
        """Test isbn_type filter with no ISBN"""
        self.assertEqual(custom_filters.isbn_type(''), 'No ISBN')
        self.assertEqual(custom_filters.isbn_type(None), 'No ISBN')


class TemplateIntegrationTests(TestCase):
    """Test template tag integration with actual templates"""

    def setUp(self):
        self.data_source, _ = DataSource.objects.get_or_create(name='Test Source', defaults={'trust_level': 0.8})
        self.scan_folder = ScanFolder.objects.create(path='/test/path')
        self.book = Book.objects.create(
            file_path='/test/integration_test.epub',
            file_size=1000,
            file_format='epub',
            scan_folder=self.scan_folder
        )

        # Create source data for auto-update to pull from
        from books.models import Author, BookTitle, BookAuthor
        author = Author.objects.create(name='Test Author')
        BookTitle.objects.create(
            book=self.book,
            title='Integration Test Book',
            source=self.data_source,
            confidence=1.0
        )
        BookAuthor.objects.create(
            book=self.book,
            author=author,
            source=self.data_source,
            confidence=1.0,
            is_main_author=True
        )

        self.final_metadata = FinalMetadata.objects.create(
            book=self.book,
            final_title='Integration Test Book',
            final_author='Test Author',
            language='en',
            is_reviewed=True  # Prevent auto-updating
        )

    def test_template_with_book_cover_tag(self):
        """Test template rendering with book_cover tag"""
        template_content = """
        {% load book_extras %}
        {% book_cover book 'medium' 'New' %}
        """

        template = Template(template_content)
        context = Context({'book': self.book})

        # Should not raise an exception
        result = template.render(context)
        self.assertIsInstance(result, str)

    def test_template_with_custom_filters(self):
        """Test template rendering with custom filters"""
        template_content = """
        {% load custom_filters %}
        Title: {{ book|get_display_title }}
        Author: {{ book|get_display_author }}
        Language: {{ book.finalmetadata.language|language_name }}
        """

        template = Template(template_content)
        context = Context({'book': self.book})
        result = template.render(context)

        self.assertIn('Integration Test Book', result)
        self.assertIn('Test Author', result)
        self.assertIn('English', result)

    def test_template_error_handling(self):
        """Test template tag error handling in real templates"""
        template_content = """
        {% load book_extras custom_filters %}
        {% book_cover nonexistent_book %}
        {{ nonexistent_book|get_display_title }}
        """

        template = Template(template_content)
        context = Context({})

        # Should not crash even with missing book
        result = template.render(context)
        self.assertIsInstance(result, str)


if __name__ == '__main__':
    import unittest
    unittest.main()
