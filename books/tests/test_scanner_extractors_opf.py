"""
Test cases for OPF Scanner Extractor
"""

import os
import shutil
import tempfile
from unittest.mock import MagicMock, mock_open, patch

from django.test import TestCase

from books.models import BookAuthor, BookMetadata, BookPublisher, BookSeries, BookTitle, DataSource, Publisher, Series
from books.scanner.extractors.opf import extract
from books.tests.test_helpers import create_test_book_with_file, create_test_scan_folder


class OPFExtractorTests(TestCase):
    """Test cases for OPF extractor functions"""

    def setUp(self):
        """Set up test data"""
        # Create temporary directory for testing
        self.temp_dir = tempfile.mkdtemp()

        self.scan_folder = create_test_scan_folder()

        self.book = create_test_book_with_file(
            file_path=os.path.join(self.temp_dir, "test.epub"),
            file_format="epub",
            file_size=1024000,
            scan_folder=self.scan_folder,
            opf_path=os.path.join(self.temp_dir, "content.opf"),
            title=None,  # Don't auto-create title, let extractor create it
        )

        # Ensure OPF_FILE data source exists
        self.opf_source, created = DataSource.objects.get_or_create(name=DataSource.OPF_FILE, defaults={"trust_level": 0.9})

    def tearDown(self):
        """Clean up temporary directories"""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_extract_no_opf_path(self):
        """Test extraction when book has no OPF path"""
        # Set empty OPF path
        self.book.files.first().opf_path = ""
        self.book.save()

        extract(self.book)

        # Should not create any metadata
        self.assertEqual(BookTitle.objects.filter(book=self.book).count(), 0)

    @patch("builtins.open", new_callable=mock_open)
    @patch("books.scanner.extractors.opf.ET.parse")
    def test_extract_complete_metadata(self, mock_parse, mock_file):
        """Test successful extraction of complete metadata from OPF"""
        # Mock XML structure
        mock_root = MagicMock()
        mock_tree = MagicMock()
        mock_tree.getroot.return_value = mock_root
        mock_parse.return_value = mock_tree

        # Mock title element
        mock_title = MagicMock()
        mock_title.text = "Test OPF Book"

        # Mock author elements
        mock_author1 = MagicMock()
        mock_author1.text = "John Doe"
        mock_author2 = MagicMock()
        mock_author2.text = "Jane Smith"

        # Mock publisher element
        mock_publisher = MagicMock()
        mock_publisher.text = "Test Publisher"

        # Mock series elements
        mock_series_name = MagicMock()
        mock_series_name.get.return_value = "Test Series"
        mock_series_index = MagicMock()
        mock_series_index.get.return_value = "1"

        # Mock metadata elements
        mock_language = MagicMock()
        mock_language.text = "en-US"
        mock_isbn = MagicMock()
        mock_isbn.text = "978-0-13-468599-1"
        mock_description = MagicMock()
        mock_description.text = "Test description"
        mock_date = MagicMock()
        mock_date.text = "2023-01-01"

        # Configure find/findall methods
        def mock_find(xpath, ns=None):
            if "dc:title" in xpath:
                return mock_title
            elif "dc:publisher" in xpath:
                return mock_publisher
            elif 'calibre:series"]' in xpath:
                return mock_series_name
            elif 'calibre:series_index"]' in xpath:
                return mock_series_index
            elif "dc:language" in xpath:
                return mock_language
            elif "dc:identifier" in xpath:
                return mock_isbn
            elif "dc:description" in xpath:
                return mock_description
            elif "dc:date" in xpath:
                return mock_date
            return None

        def mock_findall(xpath, ns=None):
            if "dc:creator" in xpath:
                return [mock_author1, mock_author2]
            return []

        mock_root.find = mock_find
        mock_root.findall = mock_findall

        extract(self.book)

        # Verify title was created
        book_title = BookTitle.objects.get(book=self.book)
        self.assertEqual(book_title.title, "Test OPF Book")
        self.assertEqual(book_title.source, self.opf_source)

        # Verify authors were created
        book_authors = BookAuthor.objects.filter(book=self.book)
        self.assertEqual(book_authors.count(), 2)
        author_names = [ba.author.name for ba in book_authors]
        self.assertIn("John Doe", author_names)
        self.assertIn("Jane Smith", author_names)

        # Verify publisher was created
        book_publisher = BookPublisher.objects.get(book=self.book)
        self.assertEqual(book_publisher.publisher.name, "Test Publisher")

        # Verify series was created
        book_series = BookSeries.objects.get(book=self.book)
        self.assertEqual(book_series.series.name, "Test Series")
        self.assertEqual(book_series.series_number, "1")

        # Verify metadata was created
        language_meta = BookMetadata.objects.get(book=self.book, field_name="language")
        self.assertEqual(language_meta.field_value, "en")  # Normalized

        isbn_meta = BookMetadata.objects.get(book=self.book, field_name="isbn")
        self.assertEqual(isbn_meta.field_value, "9780134685991")  # Normalized

        desc_meta = BookMetadata.objects.get(book=self.book, field_name="description")
        self.assertEqual(desc_meta.field_value, "Test description")

        year_meta = BookMetadata.objects.get(book=self.book, field_name="publication_year")
        self.assertEqual(year_meta.field_value, "2023")

    @patch("builtins.open", new_callable=mock_open)
    @patch("books.scanner.extractors.opf.ET.parse")
    def test_extract_title_only(self, mock_parse, mock_file):
        """Test extraction with only title metadata"""
        # Mock XML structure with only title
        mock_root = MagicMock()
        mock_tree = MagicMock()
        mock_tree.getroot.return_value = mock_root
        mock_parse.return_value = mock_tree

        mock_title = MagicMock()
        mock_title.text = "Title Only Book"

        def mock_find(xpath, ns=None):
            if "dc:title" in xpath:
                return mock_title
            return None

        def mock_findall(xpath, ns=None):
            return []

        mock_root.find = mock_find
        mock_root.findall = mock_findall

        extract(self.book)

        # Verify only title was created
        self.assertEqual(BookTitle.objects.filter(book=self.book).count(), 1)
        self.assertEqual(BookAuthor.objects.filter(book=self.book).count(), 0)
        self.assertEqual(BookPublisher.objects.filter(book=self.book).count(), 0)
        self.assertEqual(BookSeries.objects.filter(book=self.book).count(), 0)
        self.assertEqual(BookMetadata.objects.filter(book=self.book).count(), 0)

    @patch("builtins.open", new_callable=mock_open)
    @patch("books.scanner.extractors.opf.ET.parse")
    def test_extract_existing_publisher_reuse(self, mock_parse, mock_file):
        """Test that existing publishers are reused"""
        # Create existing publisher
        existing_publisher = Publisher.objects.create(name="Test Publisher")

        # Mock XML structure
        mock_root = MagicMock()
        mock_tree = MagicMock()
        mock_tree.getroot.return_value = mock_root
        mock_parse.return_value = mock_tree

        mock_publisher = MagicMock()
        mock_publisher.text = "test publisher"  # Different case

        def mock_find(xpath, ns=None):
            if "dc:publisher" in xpath:
                return mock_publisher
            return None

        mock_root.find = mock_find
        mock_root.findall = lambda *args: []

        extract(self.book)

        # Verify existing publisher was reused
        book_publisher = BookPublisher.objects.get(book=self.book)
        self.assertEqual(book_publisher.publisher.id, existing_publisher.id)

        # Should only have one publisher in database
        self.assertEqual(Publisher.objects.count(), 1)

    @patch("builtins.open", new_callable=mock_open)
    @patch("books.scanner.extractors.opf.ET.parse")
    def test_extract_existing_series_reuse(self, mock_parse, mock_file):
        """Test that existing series are reused"""
        # Create existing series
        existing_series = Series.objects.create(name="Test Series")

        # Mock XML structure
        mock_root = MagicMock()
        mock_tree = MagicMock()
        mock_tree.getroot.return_value = mock_root
        mock_parse.return_value = mock_tree

        mock_series_name = MagicMock()
        mock_series_name.get.return_value = "Test Series"
        mock_series_index = MagicMock()
        mock_series_index.get.return_value = "2"

        def mock_find(xpath, ns=None):
            if 'calibre:series"]' in xpath:
                return mock_series_name
            elif 'calibre:series_index"]' in xpath:
                return mock_series_index
            return None

        mock_root.find = mock_find
        mock_root.findall = lambda *args: []

        extract(self.book)

        # Verify existing series was reused
        book_series = BookSeries.objects.get(book=self.book)
        self.assertEqual(book_series.series.id, existing_series.id)
        self.assertEqual(book_series.series_number, "2")

        # Should only have one series in database
        self.assertEqual(Series.objects.count(), 1)

    @patch("builtins.open", new_callable=mock_open)
    @patch("books.scanner.extractors.opf.ET.parse")
    def test_extract_publication_year_extraction(self, mock_parse, mock_file):
        """Test publication year extraction from date field"""
        # Mock XML structure
        mock_root = MagicMock()
        mock_tree = MagicMock()
        mock_tree.getroot.return_value = mock_root
        mock_parse.return_value = mock_tree

        # Test various date formats
        test_dates = [("2023-01-01", "2023"), ("Published in 2022", "2022"), ("Copyright 2021 by Publisher", "2021"), ("No year here", None), ("", None)]

        for date_text, expected_year in test_dates:
            with self.subTest(date=date_text):
                # Clear existing metadata
                BookMetadata.objects.filter(book=self.book).delete()

                mock_date = MagicMock()
                mock_date.text = date_text

                def mock_find(xpath, ns=None):
                    if "dc:date" in xpath:
                        return mock_date if date_text else None
                    return None

                mock_root.find = mock_find
                mock_root.findall = lambda *args: []

                extract(self.book)

                year_metadata = BookMetadata.objects.filter(book=self.book, field_name="publication_year")

                if expected_year:
                    self.assertEqual(year_metadata.count(), 1)
                    self.assertEqual(year_metadata.first().field_value, expected_year)
                else:
                    self.assertEqual(year_metadata.count(), 0)

    @patch("builtins.open", new_callable=mock_open)
    @patch("books.scanner.extractors.opf.ET.parse")
    def test_extract_empty_values_skipped(self, mock_parse, mock_file):
        """Test that empty metadata values are skipped"""
        # Mock XML structure with empty values
        mock_root = MagicMock()
        mock_tree = MagicMock()
        mock_tree.getroot.return_value = mock_root
        mock_parse.return_value = mock_tree

        # Mock elements with empty text
        mock_title = MagicMock()
        mock_title.text = "   "  # Whitespace only
        mock_publisher = MagicMock()
        mock_publisher.text = ""  # Empty string
        mock_language = MagicMock()
        mock_language.text = None  # None value

        def mock_find(xpath, ns=None):
            if "dc:title" in xpath:
                return mock_title
            elif "dc:publisher" in xpath:
                return mock_publisher
            elif "dc:language" in xpath:
                return mock_language
            return None

        mock_root.find = mock_find
        mock_root.findall = lambda *args: []

        extract(self.book)

        # Should not create any metadata for empty values
        self.assertEqual(BookTitle.objects.filter(book=self.book).count(), 0)
        self.assertEqual(BookPublisher.objects.filter(book=self.book).count(), 0)
        self.assertEqual(BookMetadata.objects.filter(book=self.book).count(), 0)

    @patch("builtins.open", new_callable=mock_open)
    @patch("books.scanner.extractors.opf.ET.parse")
    def test_extract_invalid_language_skipped(self, mock_parse, mock_file):
        """Test that invalid language codes are skipped"""
        # Mock XML structure
        mock_root = MagicMock()
        mock_tree = MagicMock()
        mock_tree.getroot.return_value = mock_root
        mock_parse.return_value = mock_tree

        mock_language = MagicMock()
        mock_language.text = "invalid-lang"

        def mock_find(xpath, ns=None):
            if "dc:language" in xpath:
                return mock_language
            return None

        mock_root.find = mock_find
        mock_root.findall = lambda *args: []

        extract(self.book)

        # Should not create language metadata for invalid language
        language_metadata = BookMetadata.objects.filter(book=self.book, field_name="language")
        self.assertEqual(language_metadata.count(), 0)

    @patch("builtins.open", new_callable=mock_open)
    @patch("books.scanner.extractors.opf.ET.parse")
    def test_extract_invalid_isbn_skipped(self, mock_parse, mock_file):
        """Test that invalid ISBNs are skipped"""
        # Mock XML structure
        mock_root = MagicMock()
        mock_tree = MagicMock()
        mock_tree.getroot.return_value = mock_root
        mock_parse.return_value = mock_tree

        mock_isbn = MagicMock()
        mock_isbn.text = "invalid-isbn"

        def mock_find(xpath, ns=None):
            if "dc:identifier" in xpath:
                return mock_isbn
            return None

        mock_root.find = mock_find
        mock_root.findall = lambda *args: []

        extract(self.book)

        # Should not create ISBN metadata for invalid ISBN
        isbn_metadata = BookMetadata.objects.filter(book=self.book, field_name="isbn")
        self.assertEqual(isbn_metadata.count(), 0)

    @patch("builtins.open", new_callable=mock_open)
    @patch("books.scanner.extractors.opf.ET.parse")
    def test_extract_file_read_error(self, mock_parse, mock_file):
        """Test extraction with file read error"""
        # Mock file read error
        mock_file.side_effect = IOError("File not found")

        # Should not raise exception, just log warning
        extract(self.book)

        # Should not create any metadata
        self.assertEqual(BookTitle.objects.filter(book=self.book).count(), 0)

    @patch("builtins.open", new_callable=mock_open)
    def test_extract_xml_parse_error(self, mock_file):
        """Test extraction with XML parsing error"""
        # Mock invalid XML content
        mock_file.return_value.read.return_value = "invalid xml content"

        # Should not raise exception, just log warning
        extract(self.book)

        # Should not create any metadata
        self.assertEqual(BookTitle.objects.filter(book=self.book).count(), 0)

    @patch("builtins.open", new_callable=mock_open)
    @patch("books.scanner.extractors.opf.ET.parse")
    def test_extract_series_without_index(self, mock_parse, mock_file):
        """Test series extraction when only name is provided (no index)"""
        # Mock XML structure
        mock_root = MagicMock()
        mock_tree = MagicMock()
        mock_tree.getroot.return_value = mock_root
        mock_parse.return_value = mock_tree

        mock_series_name = MagicMock()
        mock_series_name.get.return_value = "Test Series"

        def mock_find(xpath, ns=None):
            if 'calibre:series"]' in xpath:
                return mock_series_name
            elif 'calibre:series_index"]' in xpath:
                return None  # No index
            return None

        mock_root.find = mock_find
        mock_root.findall = lambda *args: []

        extract(self.book)

        # Verify series was created without volume number
        book_series = BookSeries.objects.get(book=self.book)
        self.assertEqual(book_series.series.name, "Test Series")
        self.assertIsNone(book_series.series_number)
