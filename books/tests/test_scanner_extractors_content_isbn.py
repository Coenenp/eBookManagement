"""
Test cases for Content ISBN Scanner Extractor
"""
import os
import shutil
import tempfile
from unittest.mock import MagicMock, patch

from django.test import TestCase

from books.models import Book, BookMetadata, DataSource, ScanFolder
from books.scanner.extractors.content_isbn import (
    _extract_text_from_html,
    _find_isbn_patterns,
    _validate_and_dedupe_isbns,
    bulk_scan_content_isbns,
    extract_isbn_from_content,
    save_content_isbns,
)
from books.tests.test_helpers import create_test_book_with_file


class ContentISBNExtractorTests(TestCase):
    """Test cases for Content ISBN extractor functions"""

    def setUp(self):
        """Set up test data"""
        # Create temporary directory for testing
        self.temp_dir = tempfile.mkdtemp()

        self.scan_folder = ScanFolder.objects.create(
            path=self.temp_dir,
            name="Test Scan Folder"
        )

        self.epub_book = create_test_book_with_file(
            file_path=os.path.join(self.temp_dir, "test.epub"),
            file_format="epub",
            file_size=1024000,
            scan_folder=self.scan_folder
        )

        self.pdf_book = create_test_book_with_file(
            file_path=os.path.join(self.temp_dir, "test.pdf"),
            file_format="pdf",
            file_size=1024000,
            scan_folder=self.scan_folder
        )

        # Ensure CONTENT_SCAN data source exists
        self.content_source, created = DataSource.objects.get_or_create(
            name=DataSource.CONTENT_SCAN,
            defaults={'trust_level': 0.85}
        )

    def tearDown(self):
        """Clean up temporary directories"""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_find_isbn_patterns_with_isbn_prefix(self):
        """Test finding ISBN patterns with ISBN prefix"""
        text = "This book ISBN: 9780134685991 is a great read"
        isbns = _find_isbn_patterns(text)
        self.assertIn('9780134685991', isbns)

        text2 = "ISBN-13: 978-0-13-468599-1"
        isbns2 = _find_isbn_patterns(text2)
        self.assertIn('9780134685991', isbns2)  # Expect cleaned format

    def test_find_isbn_patterns_thirteen_digit(self):
        """Test finding 13-digit ISBN patterns"""
        text = "Random text 9780134685991 more text"
        isbns = _find_isbn_patterns(text)
        self.assertIn('9780134685991', isbns)

        text2 = "Another number 9790123456789 here"
        isbns2 = _find_isbn_patterns(text2)
        self.assertIn('9790123456789', isbns2)

    def test_find_isbn_patterns_ten_digit_context(self):
        """Test finding 10-digit ISBN patterns with context"""
        text = "ISBN: 0-13-468599-2"
        isbns = _find_isbn_patterns(text)
        self.assertIn('0134685992', isbns)  # Expect cleaned format

        text2 = "International Standard Book Number 0134685997"
        isbns2 = _find_isbn_patterns(text2)
        self.assertIn('0134685997', isbns2)

    def test_find_isbn_patterns_copyright_context(self):
        """Test finding ISBN patterns near copyright information"""
        text = "Copyright 2023, Published by Test Press 9780134685991"
        isbns = _find_isbn_patterns(text)
        self.assertIn('9780134685991', isbns)

    def test_find_isbn_patterns_empty_text(self):
        """Test finding ISBN patterns in empty text"""
        isbns = _find_isbn_patterns("")
        self.assertEqual(isbns, [])

        isbns2 = _find_isbn_patterns(None)
        self.assertEqual(isbns2, [])

    def test_validate_and_dedupe_isbns_valid_isbn13(self):
        """Test validation of valid ISBN-13"""
        candidates = ["9780134685991", "978-0-13-468599-1"]
        valid = _validate_and_dedupe_isbns(candidates)
        self.assertIn("9780134685991", valid)
        # Should dedupe and have only one
        self.assertEqual(len(valid), 1)

    def test_validate_and_dedupe_isbns_valid_isbn10(self):
        """Test validation and conversion of valid ISBN-10"""
        candidates = ["0134685997"]
        valid = _validate_and_dedupe_isbns(candidates)
        # Should convert to ISBN-13
        self.assertIn("9780134685991", valid)

    def test_validate_and_dedupe_isbns_invalid(self):
        """Test validation rejects invalid ISBNs"""
        candidates = ["1234567890", "invalid", "123"]
        valid = _validate_and_dedupe_isbns(candidates)
        self.assertEqual(valid, [])

    def test_validate_and_dedupe_isbns_empty(self):
        """Test validation with empty candidates"""
        valid = _validate_and_dedupe_isbns([])
        self.assertEqual(valid, [])

        valid2 = _validate_and_dedupe_isbns(["", None])
        self.assertEqual(valid2, [])

    def test_extract_text_from_html_simple(self):
        """Test extracting text from simple HTML"""
        html = "<p>This is a test paragraph with <strong>bold text</strong>.</p>"
        text = _extract_text_from_html(html)
        self.assertIn("This is a test paragraph", text)
        self.assertIn("bold text", text)
        self.assertNotIn("<p>", text)
        self.assertNotIn("<strong>", text)

    def test_extract_text_from_html_with_scripts(self):
        """Test extracting text from HTML with scripts and styles"""
        html = """
        <html>
        <head><style>body { color: red; }</style></head>
        <body>
        <script>alert('test');</script>
        <p>Visible content</p>
        </body>
        </html>
        """
        text = _extract_text_from_html(html)
        self.assertIn("Visible content", text)
        self.assertNotIn("alert", text)
        self.assertNotIn("color: red", text)

    @patch('ebooklib.epub.read_epub')
    def test_extract_isbn_from_content_epub(self, mock_read_epub):
        """Test ISBN extraction from EPUB content"""
        # Mock EPUB book structure
        mock_book = MagicMock()
        mock_item1 = MagicMock()
        mock_item1.get_type.return_value = 9  # ITEM_DOCUMENT
        mock_item1.get_content.return_value = b"<p>ISBN: 9780134685991</p>"

        mock_item2 = MagicMock()
        mock_item2.get_type.return_value = 9
        mock_item2.get_content.return_value = b"<p>More content</p>"

        mock_book.get_items.return_value = [mock_item1, mock_item2]
        mock_read_epub.return_value = mock_book

        isbns = extract_isbn_from_content(self.epub_book, page_limit=5)
        self.assertIn("9780134685991", isbns)

    @patch('PyPDF2.PdfReader')
    def test_extract_isbn_from_content_pdf(self, mock_pdf_reader):
        """Test ISBN extraction from PDF content"""
        # Mock PDF reader
        mock_reader = MagicMock()
        mock_page1 = MagicMock()
        mock_page1.extract_text.return_value = "Title page ISBN: 9780134685991"
        mock_page2 = MagicMock()
        mock_page2.extract_text.return_value = "Chapter content"

        mock_reader.pages = [mock_page1, mock_page2]
        mock_pdf_reader.return_value = mock_reader

        isbns = extract_isbn_from_content(self.pdf_book, page_limit=5)
        self.assertIn("9780134685991", isbns)

    def test_extract_isbn_from_content_unsupported_format(self):
        """Test ISBN extraction from unsupported file format"""
        unsupported_book = create_test_book_with_file(
            file_path="/test/scan/folder/test.txt",
            file_format="txt",
            file_size=1024,
            scan_folder=self.scan_folder
        )

        isbns = extract_isbn_from_content(unsupported_book)
        self.assertEqual(isbns, [])

    def test_extract_isbn_from_content_mobi_not_implemented(self):
        """Test ISBN extraction from MOBI (not implemented)"""
        mobi_book = create_test_book_with_file(
            file_path="/test/scan/folder/test.mobi",
            file_format="mobi",
            file_size=1024000,
            scan_folder=self.scan_folder
        )

        isbns = extract_isbn_from_content(mobi_book)
        self.assertEqual(isbns, [])

    @patch('books.scanner.extractors.content_isbn.extract_isbn_from_content')
    def test_save_content_isbns_success(self, mock_extract):
        """Test saving content ISBNs successfully"""
        mock_extract.return_value = ["9780134685991", "9780321356680"]

        save_content_isbns(self.epub_book)

        # Verify ISBNs were saved
        metadata = BookMetadata.objects.filter(
            book=self.epub_book,
            field_name='isbn',
            source=self.content_source
        )
        self.assertEqual(metadata.count(), 2)

        isbn_values = [m.field_value for m in metadata]
        self.assertIn("9780134685991", isbn_values)
        self.assertIn("9780321356680", isbn_values)

    @patch('books.scanner.extractors.content_isbn.extract_isbn_from_content')
    def test_save_content_isbns_no_isbns_found(self, mock_extract):
        """Test saving when no ISBNs are found"""
        mock_extract.return_value = []

        save_content_isbns(self.epub_book)

        # Verify no metadata was created
        metadata = BookMetadata.objects.filter(
            book=self.epub_book,
            field_name='isbn',
            source=self.content_source
        )
        self.assertEqual(metadata.count(), 0)

    @patch('books.scanner.extractors.content_isbn.extract_isbn_from_content')
    def test_save_content_isbns_duplicate_handling(self, mock_extract):
        """Test that duplicate ISBNs are handled properly"""
        # Create existing ISBN metadata
        BookMetadata.objects.create(
            book=self.epub_book,
            field_name='isbn',
            field_value='9780134685991',
            source=self.content_source,
            confidence=0.85
        )

        mock_extract.return_value = ["9780134685991", "9780321356680"]

        save_content_isbns(self.epub_book)

        # Should still only have 2 total (1 existing + 1 new)
        metadata = BookMetadata.objects.filter(
            book=self.epub_book,
            field_name='isbn',
            source=self.content_source
        )
        self.assertEqual(metadata.count(), 2)

    @patch('books.scanner.extractors.content_isbn.save_content_isbns')
    def test_bulk_scan_content_isbns(self, mock_save):
        """Test bulk scanning of content ISBNs"""
        # Create multiple books
        book2 = create_test_book_with_file(
            file_path="/test/scan/folder/test2.epub",
            file_format="epub",
            file_size=1024000,
            scan_folder=self.scan_folder
        )

        # Mock save_content_isbns to simulate finding ISBNs
        def mock_save_side_effect(book):
            if book == self.epub_book:
                # Simulate finding ISBNs for first book
                BookMetadata.objects.create(
                    book=book,
                    field_name='isbn',
                    field_value='9780134685991',
                    source=self.content_source,
                    confidence=0.85
                )

        mock_save.side_effect = mock_save_side_effect

        queryset = Book.objects.filter(id__in=[self.epub_book.id, book2.id])
        stats = bulk_scan_content_isbns(queryset)

        self.assertEqual(stats['total_books'], 2)
        self.assertEqual(mock_save.call_count, 2)

    @patch('books.scanner.extractors.content_isbn.save_content_isbns')
    def test_bulk_scan_content_isbns_skip_existing(self, mock_save):
        """Test bulk scanning skips books with existing content ISBNs"""
        # Create existing content ISBN
        BookMetadata.objects.create(
            book=self.epub_book,
            field_name='isbn',
            field_value='9780134685991',
            source=self.content_source,
            confidence=0.85
        )

        queryset = Book.objects.filter(id=self.epub_book.id)
        stats = bulk_scan_content_isbns(queryset)

        self.assertEqual(stats['total_books'], 1)
        # Should not call save_content_isbns for book with existing ISBNs
        mock_save.assert_not_called()

    @patch('ebooklib.epub.read_epub')
    def test_extract_isbn_from_content_epub_error_handling(self, mock_read_epub):
        """Test EPUB extraction with errors"""
        # Mock EPUB reading error
        mock_read_epub.side_effect = Exception("EPUB read failed")

        isbns = extract_isbn_from_content(self.epub_book)
        self.assertEqual(isbns, [])

    @patch('PyPDF2.PdfReader')
    def test_extract_isbn_from_content_pdf_error_handling(self, mock_pdf_reader):
        """Test PDF extraction with errors"""
        # Mock PDF reading error
        mock_pdf_reader.side_effect = Exception("PDF read failed")

        isbns = extract_isbn_from_content(self.pdf_book)
        self.assertEqual(isbns, [])

    @patch('ebooklib.epub.read_epub')
    def test_extract_isbn_from_content_epub_item_error(self, mock_read_epub):
        """Test EPUB extraction with item processing errors"""
        # Mock EPUB book with problematic item
        mock_book = MagicMock()
        mock_item = MagicMock()
        mock_item.get_type.return_value = 9
        mock_item.get_content.side_effect = Exception("Item read failed")

        mock_book.get_items.return_value = [mock_item]
        mock_read_epub.return_value = mock_book

        # Should handle item errors gracefully
        isbns = extract_isbn_from_content(self.epub_book)
        self.assertEqual(isbns, [])

    @patch('PyPDF2.PdfReader')
    def test_extract_isbn_from_content_pdf_page_error(self, mock_pdf_reader):
        """Test PDF extraction with page processing errors"""
        # Mock PDF with problematic page
        mock_reader = MagicMock()
        mock_page = MagicMock()
        mock_page.extract_text.side_effect = Exception("Page extraction failed")

        mock_reader.pages = [mock_page]
        mock_pdf_reader.return_value = mock_reader

        # Should handle page errors gracefully
        isbns = extract_isbn_from_content(self.pdf_book)
        self.assertEqual(isbns, [])
