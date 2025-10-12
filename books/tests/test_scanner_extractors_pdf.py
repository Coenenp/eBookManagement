"""
Test cases for PDF Scanner Extractor
"""
import os
import tempfile
import shutil
from django.test import TestCase
from unittest.mock import patch, MagicMock
from books.models import (
    ScanFolder, DataSource, BookTitle, BookAuthor, BookMetadata
)
from books.tests.test_helpers import create_test_book_with_file
from books.scanner.extractors.pdf import extract


class PDFExtractorTests(TestCase):
    """Test cases for PDF extractor functions"""

    def setUp(self):
        """Set up test data"""
        # Create temporary directory for testing
        self.temp_dir = tempfile.mkdtemp()

        self.scan_folder = ScanFolder.objects.create(
            path=self.temp_dir,
            name="Test Scan Folder"
        )

        self.book = create_test_book_with_file(
            file_path=os.path.join(self.temp_dir, "test.pdf"),
            file_format="pdf",
            file_size=1024000,
            scan_folder=self.scan_folder,
            title=None  # Don't auto-create title
        )

        # Ensure PDF_INTERNAL data source exists
        self.pdf_source, created = DataSource.objects.get_or_create(
            name=DataSource.PDF_INTERNAL,
            defaults={'trust_level': 0.8}
        )

    def tearDown(self):
        """Clean up temporary directories"""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    @patch('books.scanner.extractors.pdf.PdfReader')
    def test_extract_complete_metadata(self, mock_pdf_reader):
        """Test successful extraction of complete metadata from PDF"""
        # Mock PDF reader and metadata
        mock_reader = MagicMock()
        mock_metadata = MagicMock()
        mock_metadata.title = "Test PDF Book"
        mock_metadata.author = "John Doe"
        mock_metadata.creator = "PDF Creator App"
        mock_reader.metadata = mock_metadata
        mock_pdf_reader.return_value = mock_reader

        extract(self.book)

        # Verify title was created
        book_title = BookTitle.objects.get(book=self.book)
        self.assertEqual(book_title.title, 'Test PDF Book')
        self.assertEqual(book_title.source, self.pdf_source)
        self.assertEqual(book_title.confidence, self.pdf_source.trust_level)

        # Verify author was created
        book_authors = BookAuthor.objects.filter(book=self.book)
        self.assertEqual(book_authors.count(), 1)
        self.assertEqual(book_authors.first().author.name, 'John Doe')

        # Verify creator metadata was created
        creator_metadata = BookMetadata.objects.get(
            book=self.book,
            field_name='creator'
        )
        self.assertEqual(creator_metadata.field_value, 'PDF Creator App')
        self.assertEqual(creator_metadata.source, self.pdf_source)

    @patch('books.scanner.extractors.pdf.PdfReader')
    def test_extract_title_only(self, mock_pdf_reader):
        """Test extraction with only title metadata"""
        # Mock PDF reader with only title
        mock_reader = MagicMock()
        mock_metadata = MagicMock()
        mock_metadata.title = "Title Only PDF"
        mock_metadata.author = None
        mock_metadata.creator = None
        mock_reader.metadata = mock_metadata
        mock_pdf_reader.return_value = mock_reader

        extract(self.book)

        # Verify only title was created
        self.assertEqual(BookTitle.objects.filter(book=self.book).count(), 1)
        self.assertEqual(BookAuthor.objects.filter(book=self.book).count(), 0)
        self.assertEqual(BookMetadata.objects.filter(book=self.book).count(), 0)

        book_title = BookTitle.objects.get(book=self.book)
        self.assertEqual(book_title.title, 'Title Only PDF')

    @patch('books.scanner.extractors.pdf.PdfReader')
    def test_extract_author_only(self, mock_pdf_reader):
        """Test extraction with only author metadata"""
        # Mock PDF reader with only author
        mock_reader = MagicMock()
        mock_metadata = MagicMock()
        mock_metadata.title = None
        mock_metadata.author = "Jane Smith"
        mock_metadata.creator = None
        mock_reader.metadata = mock_metadata
        mock_pdf_reader.return_value = mock_reader

        extract(self.book)

        # Verify only author was created
        self.assertEqual(BookTitle.objects.filter(book=self.book).count(), 0)
        self.assertEqual(BookAuthor.objects.filter(book=self.book).count(), 1)
        self.assertEqual(BookMetadata.objects.filter(book=self.book).count(), 0)

        book_author = BookAuthor.objects.get(book=self.book)
        self.assertEqual(book_author.author.name, 'Jane Smith')

    @patch('books.scanner.extractors.pdf.PdfReader')
    def test_extract_creator_only(self, mock_pdf_reader):
        """Test extraction with only creator metadata"""
        # Mock PDF reader with only creator
        mock_reader = MagicMock()
        mock_metadata = MagicMock()
        mock_metadata.title = None
        mock_metadata.author = None
        mock_metadata.creator = "LaTeX Creator"
        mock_reader.metadata = mock_metadata
        mock_pdf_reader.return_value = mock_reader

        extract(self.book)

        # Verify only creator metadata was created
        self.assertEqual(BookTitle.objects.filter(book=self.book).count(), 0)
        self.assertEqual(BookAuthor.objects.filter(book=self.book).count(), 0)
        self.assertEqual(BookMetadata.objects.filter(book=self.book).count(), 1)

        creator_metadata = BookMetadata.objects.get(
            book=self.book,
            field_name='creator'
        )
        self.assertEqual(creator_metadata.field_value, 'LaTeX Creator')

    @patch('books.scanner.extractors.pdf.PdfReader')
    def test_extract_whitespace_handling(self, mock_pdf_reader):
        """Test that whitespace is properly stripped from metadata"""
        # Mock PDF reader with whitespace in metadata
        mock_reader = MagicMock()
        mock_metadata = MagicMock()
        mock_metadata.title = "  Test PDF  "
        mock_metadata.author = "  John Doe  "
        mock_metadata.creator = "  PDF Creator  "
        mock_reader.metadata = mock_metadata
        mock_pdf_reader.return_value = mock_reader

        extract(self.book)

        # Verify whitespace was stripped
        book_title = BookTitle.objects.get(book=self.book)
        self.assertEqual(book_title.title, 'Test PDF')

        book_author = BookAuthor.objects.get(book=self.book)
        self.assertEqual(book_author.author.name, 'John Doe')

        creator_metadata = BookMetadata.objects.get(
            book=self.book,
            field_name='creator'
        )
        self.assertEqual(creator_metadata.field_value, 'PDF Creator')

    @patch('books.scanner.extractors.pdf.PdfReader')
    def test_extract_empty_values_skipped(self, mock_pdf_reader):
        """Test that empty metadata values are skipped"""
        # Mock PDF reader with empty values
        mock_reader = MagicMock()
        mock_metadata = MagicMock()
        mock_metadata.title = ""  # Empty title
        mock_metadata.author = "   "  # Whitespace only
        mock_metadata.creator = None  # None value
        mock_reader.metadata = mock_metadata
        mock_pdf_reader.return_value = mock_reader

        extract(self.book)

        # Should not create any metadata for empty values
        self.assertEqual(BookTitle.objects.filter(book=self.book).count(), 0)
        self.assertEqual(BookAuthor.objects.filter(book=self.book).count(), 0)
        self.assertEqual(BookMetadata.objects.filter(book=self.book).count(), 0)

    @patch('books.scanner.extractors.pdf.PdfReader')
    def test_extract_no_metadata(self, mock_pdf_reader):
        """Test extraction when PDF has no metadata"""
        # Mock PDF reader with no metadata
        mock_reader = MagicMock()
        mock_metadata = MagicMock()
        mock_metadata.title = None
        mock_metadata.author = None
        mock_metadata.creator = None
        mock_reader.metadata = mock_metadata
        mock_pdf_reader.return_value = mock_reader

        extract(self.book)

        # Should not create any metadata
        self.assertEqual(BookTitle.objects.filter(book=self.book).count(), 0)
        self.assertEqual(BookAuthor.objects.filter(book=self.book).count(), 0)
        self.assertEqual(BookMetadata.objects.filter(book=self.book).count(), 0)

    @patch('books.scanner.extractors.pdf.PdfReader')
    def test_extract_pdf_read_error(self, mock_pdf_reader):
        """Test extraction with PDF reading error"""
        # Mock PDF reading error
        mock_pdf_reader.side_effect = Exception("Cannot read PDF file")

        # Should not raise exception, just log warning
        extract(self.book)

        # Should not create any metadata
        self.assertEqual(BookTitle.objects.filter(book=self.book).count(), 0)
        self.assertEqual(BookAuthor.objects.filter(book=self.book).count(), 0)
        self.assertEqual(BookMetadata.objects.filter(book=self.book).count(), 0)

    @patch('books.scanner.extractors.pdf.PdfReader')
    def test_extract_metadata_access_error(self, mock_pdf_reader):
        """Test extraction when metadata access fails"""
        # Mock PDF reader but metadata access fails
        mock_reader = MagicMock()
        mock_reader.metadata = None  # No metadata available
        mock_pdf_reader.return_value = mock_reader

        # Should handle gracefully (AttributeError when accessing .title, etc.)
        extract(self.book)

        # Should not create any metadata
        self.assertEqual(BookTitle.objects.filter(book=self.book).count(), 0)
        self.assertEqual(BookAuthor.objects.filter(book=self.book).count(), 0)
        self.assertEqual(BookMetadata.objects.filter(book=self.book).count(), 0)

    @patch('books.scanner.extractors.pdf.PdfReader')
    def test_extract_duplicate_title_handling(self, mock_pdf_reader):
        """Test that duplicate titles are handled by get_or_create"""
        # Create existing title
        existing_title = BookTitle.objects.create(
            book=self.book,
            title="Existing Title",
            source=self.pdf_source,
            confidence=0.5
        )

        # Mock PDF reader with same title
        mock_reader = MagicMock()
        mock_metadata = MagicMock()
        mock_metadata.title = "Existing Title"
        mock_metadata.author = None
        mock_metadata.creator = None
        mock_reader.metadata = mock_metadata
        mock_pdf_reader.return_value = mock_reader

        extract(self.book)

        # Should still only have one title record
        titles = BookTitle.objects.filter(book=self.book)
        self.assertEqual(titles.count(), 1)
        self.assertEqual(titles.first().id, existing_title.id)

    @patch('books.scanner.extractors.pdf.PdfReader')
    def test_extract_duplicate_creator_handling(self, mock_pdf_reader):
        """Test that duplicate creator metadata is handled by get_or_create"""
        # Create existing creator metadata
        existing_creator = BookMetadata.objects.create(
            book=self.book,
            field_name='creator',
            field_value='Existing Creator',
            source=self.pdf_source,
            confidence=0.5
        )

        # Mock PDF reader with same creator
        mock_reader = MagicMock()
        mock_metadata = MagicMock()
        mock_metadata.title = None
        mock_metadata.author = None
        mock_metadata.creator = "Existing Creator"
        mock_reader.metadata = mock_metadata
        mock_pdf_reader.return_value = mock_reader

        extract(self.book)

        # Should still only have one creator record
        creators = BookMetadata.objects.filter(
            book=self.book,
            field_name='creator'
        )
        self.assertEqual(creators.count(), 1)
        self.assertEqual(creators.first().id, existing_creator.id)
