"""
Test cases for EPUB Scanner Extractor
"""
from django.test import TestCase
from unittest.mock import patch, MagicMock
from books.models import (
    Book, ScanFolder, DataSource, BookTitle, BookAuthor,
    BookPublisher, BookMetadata, Publisher
)
from books.scanner.extractors.epub import extract


class EPUBExtractorTests(TestCase):
    """Test cases for EPUB extractor functions"""

    def setUp(self):
        """Set up test data"""
        self.scan_folder = ScanFolder.objects.create(
            path="/test/scan/folder",
            name="Test Scan Folder"
        )

        self.book = Book.objects.create(
            file_path="/test/scan/folder/test.epub",
            file_format="epub",
            file_size=1024000,
            scan_folder=self.scan_folder
        )

        # Ensure EPUB_INTERNAL data source exists
        self.epub_source, created = DataSource.objects.get_or_create(
            name=DataSource.EPUB_INTERNAL,
            defaults={'trust_level': 0.9}
        )

    @patch('books.scanner.extractors.epub.epub.read_epub')
    def test_extract_title_success(self, mock_read_epub):
        """Test successful title extraction from EPUB"""
        # Mock EPUB book
        mock_epub_book = MagicMock()
        mock_epub_book.get_metadata.return_value = [('Test Book Title', {})]
        mock_read_epub.return_value = mock_epub_book

        extract(self.book)

        # Verify title was created
        book_title = BookTitle.objects.get(book=self.book)
        self.assertEqual(book_title.title, 'Test Book Title')
        self.assertEqual(book_title.source, self.epub_source)
        self.assertEqual(book_title.confidence, self.epub_source.trust_level)

    @patch('books.scanner.extractors.epub.epub.read_epub')
    def test_extract_authors_success(self, mock_read_epub):
        """Test successful author extraction from EPUB"""
        # Mock EPUB book
        mock_epub_book = MagicMock()
        mock_epub_book.get_metadata.side_effect = lambda dc, field: {
            'title': [('Test Book', {})],
            'creator': [('John Doe', {}), ('Jane Smith', {})]
        }.get(field, [])
        mock_read_epub.return_value = mock_epub_book

        extract(self.book)

        # Verify authors were created
        book_authors = BookAuthor.objects.filter(book=self.book)
        self.assertEqual(book_authors.count(), 2)

        author_names = [ba.author.name for ba in book_authors]
        self.assertIn('John Doe', author_names)
        self.assertIn('Jane Smith', author_names)

    @patch('books.scanner.extractors.epub.epub.read_epub')
    def test_extract_publisher_success(self, mock_read_epub):
        """Test successful publisher extraction from EPUB"""
        # Mock EPUB book
        mock_epub_book = MagicMock()
        mock_epub_book.get_metadata.side_effect = lambda dc, field: {
            'title': [('Test Book', {})],
            'publisher': [('Test Publisher', {})]
        }.get(field, [])
        mock_read_epub.return_value = mock_epub_book

        extract(self.book)

        # Verify publisher was created
        book_publisher = BookPublisher.objects.get(book=self.book)
        self.assertEqual(book_publisher.publisher.name, 'Test Publisher')
        self.assertEqual(book_publisher.source, self.epub_source)

    @patch('books.scanner.extractors.epub.epub.read_epub')
    def test_extract_existing_publisher_reuse(self, mock_read_epub):
        """Test that existing publishers are reused"""
        # Create existing publisher
        existing_publisher = Publisher.objects.create(name='Test Publisher')

        # Mock EPUB book
        mock_epub_book = MagicMock()
        mock_epub_book.get_metadata.side_effect = lambda dc, field: {
            'title': [('Test Book', {})],
            'publisher': [('test publisher', {})]  # Different case
        }.get(field, [])
        mock_read_epub.return_value = mock_epub_book

        extract(self.book)

        # Verify existing publisher was reused
        book_publisher = BookPublisher.objects.get(book=self.book)
        self.assertEqual(book_publisher.publisher.id, existing_publisher.id)

        # Should only have one publisher in database
        self.assertEqual(Publisher.objects.count(), 1)

    @patch('books.scanner.extractors.epub.epub.read_epub')
    def test_extract_language_success(self, mock_read_epub):
        """Test successful language extraction from EPUB"""
        # Mock EPUB book
        mock_epub_book = MagicMock()
        mock_epub_book.get_metadata.side_effect = lambda dc, field: {
            'title': [('Test Book', {})],
            'language': [('en-US', {})]
        }.get(field, [])
        mock_read_epub.return_value = mock_epub_book

        extract(self.book)

        # Verify language metadata was created
        language_metadata = BookMetadata.objects.get(
            book=self.book,
            field_name='language'
        )
        self.assertEqual(language_metadata.field_value, 'en')  # Normalized
        self.assertEqual(language_metadata.source, self.epub_source)

    @patch('books.scanner.extractors.epub.epub.read_epub')
    def test_extract_isbn_success(self, mock_read_epub):
        """Test successful ISBN extraction from EPUB"""
        # Mock EPUB book
        mock_epub_book = MagicMock()
        mock_epub_book.get_metadata.side_effect = lambda dc, field: {
            'title': [('Test Book', {})],
            'identifier': [('978-0-13-468599-1', {})]
        }.get(field, [])
        mock_read_epub.return_value = mock_epub_book

        extract(self.book)

        # Verify ISBN metadata was created
        isbn_metadata = BookMetadata.objects.get(
            book=self.book,
            field_name='isbn'
        )
        self.assertEqual(isbn_metadata.field_value, '9780134685991')  # Normalized
        self.assertEqual(isbn_metadata.source, self.epub_source)

    @patch('books.scanner.extractors.epub.epub.read_epub')
    def test_extract_description_success(self, mock_read_epub):
        """Test successful description extraction from EPUB"""
        test_description = "This is a test book description."

        # Mock EPUB book
        mock_epub_book = MagicMock()
        mock_epub_book.get_metadata.side_effect = lambda dc, field: {
            'title': [('Test Book', {})],
            'description': [(test_description, {})]
        }.get(field, [])
        mock_read_epub.return_value = mock_epub_book

        extract(self.book)

        # Verify description metadata was created
        desc_metadata = BookMetadata.objects.get(
            book=self.book,
            field_name='description'
        )
        self.assertEqual(desc_metadata.field_value, test_description)
        self.assertEqual(desc_metadata.source, self.epub_source)

    @patch('books.scanner.extractors.epub.epub.read_epub')
    def test_extract_description_truncation(self, mock_read_epub):
        """Test description truncation for long descriptions"""
        long_description = "A" * 1500  # Longer than 1000 chars

        # Mock EPUB book
        mock_epub_book = MagicMock()
        mock_epub_book.get_metadata.side_effect = lambda dc, field: {
            'title': [('Test Book', {})],
            'description': [(long_description, {})]
        }.get(field, [])
        mock_read_epub.return_value = mock_epub_book

        extract(self.book)

        # Verify description was truncated
        desc_metadata = BookMetadata.objects.get(
            book=self.book,
            field_name='description'
        )
        self.assertEqual(len(desc_metadata.field_value), 1000)
        self.assertEqual(desc_metadata.field_value, "A" * 1000)

    @patch('books.scanner.extractors.epub.epub.read_epub')
    def test_extract_no_metadata(self, mock_read_epub):
        """Test extraction when EPUB has no metadata"""
        # Mock EPUB book with no metadata
        mock_epub_book = MagicMock()
        mock_epub_book.get_metadata.return_value = []
        mock_read_epub.return_value = mock_epub_book

        extract(self.book)

        # Should not create any metadata records
        self.assertEqual(BookTitle.objects.filter(book=self.book).count(), 0)
        self.assertEqual(BookAuthor.objects.filter(book=self.book).count(), 0)
        self.assertEqual(BookPublisher.objects.filter(book=self.book).count(), 0)
        self.assertEqual(BookMetadata.objects.filter(book=self.book).count(), 0)

    @patch('books.scanner.extractors.epub.epub.read_epub')
    def test_extract_invalid_language_skipped(self, mock_read_epub):
        """Test that invalid language codes are skipped"""
        # Mock EPUB book
        mock_epub_book = MagicMock()
        mock_epub_book.get_metadata.side_effect = lambda dc, field: {
            'title': [('Test Book', {})],
            'language': [('invalid-lang', {})]
        }.get(field, [])
        mock_read_epub.return_value = mock_epub_book

        extract(self.book)

        # Should not create language metadata for invalid language
        language_metadata = BookMetadata.objects.filter(
            book=self.book,
            field_name='language'
        )
        self.assertEqual(language_metadata.count(), 0)

    @patch('books.scanner.extractors.epub.epub.read_epub')
    def test_extract_invalid_isbn_skipped(self, mock_read_epub):
        """Test that invalid ISBNs are skipped"""
        # Mock EPUB book
        mock_epub_book = MagicMock()
        mock_epub_book.get_metadata.side_effect = lambda dc, field: {
            'title': [('Test Book', {})],
            'identifier': [('invalid-isbn', {})]
        }.get(field, [])
        mock_read_epub.return_value = mock_epub_book

        extract(self.book)

        # Should not create ISBN metadata for invalid ISBN
        isbn_metadata = BookMetadata.objects.filter(
            book=self.book,
            field_name='isbn'
        )
        self.assertEqual(isbn_metadata.count(), 0)

    @patch('books.scanner.extractors.epub.epub.read_epub')
    def test_extract_file_read_error(self, mock_read_epub):
        """Test extraction with file read error"""
        # Mock file read error
        mock_read_epub.side_effect = Exception("File not found")

        # Should not raise exception, just log warning
        extract(self.book)

        # Should not create any metadata
        self.assertEqual(BookTitle.objects.filter(book=self.book).count(), 0)

    @patch('books.scanner.extractors.epub.epub.read_epub')
    def test_extract_empty_values_skipped(self, mock_read_epub):
        """Test that empty metadata values are properly skipped"""
        # Mock EPUB book with empty values
        mock_epub_book = MagicMock()
        mock_epub_book.get_metadata.side_effect = lambda dc, field: {
            'title': [('', {})],  # Empty title
            'creator': [('', {})],  # Empty creator
            'publisher': [('   ', {})],  # Whitespace only
            'language': [('', {})],  # Empty language
        }.get(field, [])
        mock_read_epub.return_value = mock_epub_book

        extract(self.book)

        # Improved behavior: empty values should be skipped
        self.assertEqual(BookTitle.objects.filter(book=self.book).count(), 0)
        self.assertEqual(BookAuthor.objects.filter(book=self.book).count(), 0)
        self.assertEqual(BookPublisher.objects.filter(book=self.book).count(), 0)
        self.assertEqual(BookMetadata.objects.filter(book=self.book).count(), 0)
