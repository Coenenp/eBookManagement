"""
Test cases for MOBI Scanner Extractor
"""
import json
import os
import shutil
import tempfile
from unittest.mock import mock_open, patch

from django.test import TestCase

from books.models import BookAuthor, BookMetadata, BookPublisher, BookTitle, DataSource, Publisher, ScanFolder
from books.scanner.extractors.mobi import extract
from books.tests.test_helpers import create_test_book_with_file


class MOBIExtractorTests(TestCase):
    """Test cases for MOBI extractor functions"""

    def setUp(self):
        """Set up test data"""
        # Create temporary directory for testing
        self.temp_dir = tempfile.mkdtemp()

        self.scan_folder = ScanFolder.objects.create(
            path=self.temp_dir,
            name="Test Scan Folder"
        )

        self.book = create_test_book_with_file(
            file_path=os.path.join(self.temp_dir, "test.mobi"),
            file_format="mobi",
            file_size=1024000,
            scan_folder=self.scan_folder,
            title=None  # Don't auto-create title
        )

        # Ensure MOBI_INTERNAL data source exists
        self.mobi_source, created = DataSource.objects.get_or_create(
            name=DataSource.MOBI_INTERNAL,
            defaults={'trust_level': 0.9}
        )

    def tearDown(self):
        """Clean up temporary directories"""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    @patch('books.scanner.extractors.mobi.mobi.extract')
    @patch('builtins.open', new_callable=mock_open)
    @patch('os.path.exists')
    def test_extract_complete_metadata(self, mock_exists, mock_file, mock_mobi_extract):
        """Test successful extraction of complete metadata from MOBI"""
        # Mock MOBI extraction
        mock_mobi_extract.return_value = ("/temp/dir", "/temp/file")
        mock_exists.return_value = True

        # Mock metadata.json content
        metadata = {
            "title": "Test MOBI Book",
            "creator": "John Doe",
            "encoding": "utf-8",
            "publisher": "Test Publisher"
        }
        mock_file.return_value.read.return_value = json.dumps(metadata)

        result = extract(self.book)

        # Verify title was created
        book_title = BookTitle.objects.get(book=self.book)
        self.assertEqual(book_title.title, 'Test MOBI Book')
        self.assertEqual(book_title.source, self.mobi_source)

        # Verify author was created
        book_authors = BookAuthor.objects.filter(book=self.book)
        self.assertEqual(book_authors.count(), 1)
        self.assertEqual(book_authors.first().author.name, 'John Doe')

        # Verify publisher was created
        book_publisher = BookPublisher.objects.get(book=self.book)
        self.assertEqual(book_publisher.publisher.name, 'Test Publisher')

        # Verify encoding metadata was created
        encoding_metadata = BookMetadata.objects.get(
            book=self.book,
            field_name='encoding'
        )
        self.assertEqual(encoding_metadata.field_value, 'utf-8')

        # Verify return value
        self.assertIsNotNone(result)
        self.assertEqual(result['title'], 'Test MOBI Book')
        self.assertEqual(result['author'], 'John Doe')
        self.assertEqual(result['publisher'], 'Test Publisher')

    @patch('books.scanner.extractors.mobi.mobi.extract')
    @patch('builtins.open', new_callable=mock_open)
    @patch('os.path.exists')
    def test_extract_minimal_metadata(self, mock_exists, mock_file, mock_mobi_extract):
        """Test extraction with minimal metadata (only title)"""
        # Mock MOBI extraction
        mock_mobi_extract.return_value = ("/temp/dir", "/temp/file")
        mock_exists.return_value = True

        # Mock metadata.json with only title
        metadata = {"title": "Minimal Book"}
        mock_file.return_value.read.return_value = json.dumps(metadata)

        extract(self.book)

        # Verify only title was created
        self.assertEqual(BookTitle.objects.filter(book=self.book).count(), 1)
        self.assertEqual(BookAuthor.objects.filter(book=self.book).count(), 0)
        self.assertEqual(BookPublisher.objects.filter(book=self.book).count(), 0)
        self.assertEqual(BookMetadata.objects.filter(book=self.book).count(), 0)

        book_title = BookTitle.objects.get(book=self.book)
        self.assertEqual(book_title.title, 'Minimal Book')

    @patch('books.scanner.extractors.mobi.mobi.extract')
    @patch('os.path.exists')
    def test_extract_no_metadata_file(self, mock_exists, mock_mobi_extract):
        """Test extraction when metadata.json doesn't exist"""
        # Mock MOBI extraction
        mock_mobi_extract.return_value = ("/temp/dir", "/temp/file")
        mock_exists.return_value = False

        result = extract(self.book)

        # Should return None gracefully
        self.assertIsNone(result)

        # Should not create any metadata
        self.assertEqual(BookTitle.objects.filter(book=self.book).count(), 0)
        self.assertEqual(BookAuthor.objects.filter(book=self.book).count(), 0)
        self.assertEqual(BookPublisher.objects.filter(book=self.book).count(), 0)
        self.assertEqual(BookMetadata.objects.filter(book=self.book).count(), 0)

    @patch('books.scanner.extractors.mobi.mobi.extract')
    @patch('builtins.open', new_callable=mock_open)
    @patch('os.path.exists')
    def test_extract_existing_publisher_reuse(self, mock_exists, mock_file, mock_mobi_extract):
        """Test that existing publishers are reused"""
        # Create existing publisher
        existing_publisher = Publisher.objects.create(name='Test Publisher')

        # Mock MOBI extraction
        mock_mobi_extract.return_value = ("/temp/dir", "/temp/file")
        mock_exists.return_value = True

        # Mock metadata with case-different publisher name
        metadata = {
            "title": "Test Book",
            "publisher": "test publisher"  # Different case
        }
        mock_file.return_value.read.return_value = json.dumps(metadata)

        extract(self.book)

        # Verify existing publisher was reused
        book_publisher = BookPublisher.objects.get(book=self.book)
        self.assertEqual(book_publisher.publisher.id, existing_publisher.id)

        # Should only have one publisher in database
        self.assertEqual(Publisher.objects.count(), 1)

    @patch('books.scanner.extractors.mobi.mobi.extract')
    @patch('builtins.open', new_callable=mock_open)
    @patch('os.path.exists')
    def test_extract_whitespace_handling(self, mock_exists, mock_file, mock_mobi_extract):
        """Test that whitespace is properly stripped from metadata"""
        # Mock MOBI extraction
        mock_mobi_extract.return_value = ("/temp/dir", "/temp/file")
        mock_exists.return_value = True

        # Mock metadata with whitespace
        metadata = {
            "title": "  Test Book  ",
            "creator": "  John Doe  ",
            "publisher": "  Test Publisher  ",
            "encoding": "  utf-8  "
        }
        mock_file.return_value.read.return_value = json.dumps(metadata)

        extract(self.book)

        # Verify whitespace was stripped
        book_title = BookTitle.objects.get(book=self.book)
        self.assertEqual(book_title.title, 'Test Book')

        book_publisher = BookPublisher.objects.get(book=self.book)
        self.assertEqual(book_publisher.publisher.name, 'Test Publisher')

        encoding_metadata = BookMetadata.objects.get(
            book=self.book,
            field_name='encoding'
        )
        self.assertEqual(encoding_metadata.field_value, 'utf-8')

    @patch('books.scanner.extractors.mobi.mobi.extract')
    @patch('builtins.open', new_callable=mock_open)
    @patch('os.path.exists')
    def test_extract_empty_values_skipped(self, mock_exists, mock_file, mock_mobi_extract):
        """Test that empty metadata values are handled (current behavior creates empty publisher)"""
        # Mock MOBI extraction
        mock_mobi_extract.return_value = ("/temp/dir", "/temp/file")
        mock_exists.return_value = True

        # Mock metadata with empty values
        metadata = {
            "title": "",  # Empty title
            "creator": None,  # None creator
            "publisher": "   ",  # Whitespace only
            "encoding": ""  # Empty encoding
        }
        mock_file.return_value.read.return_value = json.dumps(metadata)

        extract(self.book)

        # Empty title should not be created (MOBI extractor checks for title)
        self.assertEqual(BookTitle.objects.filter(book=self.book).count(), 0)

        # None/empty authors should not create any BookAuthor records
        self.assertEqual(BookAuthor.objects.filter(book=self.book).count(), 0)

        # Improved behavior: whitespace-only publisher should be skipped
        self.assertEqual(BookPublisher.objects.filter(book=self.book).count(), 0)

        # Empty encoding should not create metadata
        self.assertEqual(BookMetadata.objects.filter(book=self.book).count(), 0)

    @patch('books.scanner.extractors.mobi.mobi.extract')
    @patch('builtins.open', new_callable=mock_open)
    @patch('os.path.exists')
    def test_extract_json_parse_error(self, mock_exists, mock_file, mock_mobi_extract):
        """Test extraction with malformed JSON"""
        # Mock MOBI extraction
        mock_mobi_extract.return_value = ("/temp/dir", "/temp/file")
        mock_exists.return_value = True

        # Mock malformed JSON
        mock_file.return_value.read.return_value = "invalid json"

        result = extract(self.book)

        # Should return None due to JSON error
        self.assertIsNone(result)

        # Should not create any metadata
        self.assertEqual(BookTitle.objects.filter(book=self.book).count(), 0)

    @patch('books.scanner.extractors.mobi.mobi.extract')
    def test_extract_mobi_extraction_error(self, mock_mobi_extract):
        """Test extraction when MOBI library fails"""
        # Mock MOBI extraction error
        mock_mobi_extract.side_effect = Exception("MOBI extraction failed")

        result = extract(self.book)

        # Should return None gracefully
        self.assertIsNone(result)

        # Should not create any metadata
        self.assertEqual(BookTitle.objects.filter(book=self.book).count(), 0)

    @patch('books.scanner.extractors.mobi.mobi.extract')
    @patch('builtins.open', new_callable=mock_open)
    @patch('os.path.exists')
    def test_extract_publisher_integrity_error(self, mock_exists, mock_file, mock_mobi_extract):
        """Test handling of publisher IntegrityError"""
        # Mock MOBI extraction
        mock_mobi_extract.return_value = ("/temp/dir", "/temp/file")
        mock_exists.return_value = True

        # Mock metadata
        metadata = {
            "title": "Test Book",
            "publisher": "Test Publisher"
        }
        mock_file.return_value.read.return_value = json.dumps(metadata)

        # Create existing publisher relationship
        publisher = Publisher.objects.create(name="Test Publisher")
        BookPublisher.objects.create(
            book=self.book,
            publisher=publisher,
            source=self.mobi_source,
            confidence=0.5
        )

        # Should handle IntegrityError gracefully
        result = extract(self.book)

        # Should still return result
        self.assertIsNotNone(result)
        self.assertEqual(result['publisher'], 'Test Publisher')

    @patch('books.scanner.extractors.mobi.mobi.extract')
    @patch('builtins.open', new_callable=mock_open)
    @patch('os.path.exists')
    def test_extract_multiple_optional_fields(self, mock_exists, mock_file, mock_mobi_extract):
        """Test extraction with multiple optional metadata fields"""
        # Mock MOBI extraction
        mock_mobi_extract.return_value = ("/temp/dir", "/temp/file")
        mock_exists.return_value = True

        # Mock metadata with various fields
        metadata = {
            "title": "Test Book",
            "encoding": "utf-8",
            "language": "en",  # Not in optional_fields, should be ignored
            "description": "Test description"  # Not in optional_fields, should be ignored
        }
        mock_file.return_value.read.return_value = json.dumps(metadata)

        extract(self.book)

        # Only encoding should be stored as optional metadata
        metadata_objects = BookMetadata.objects.filter(book=self.book)
        self.assertEqual(metadata_objects.count(), 1)

        encoding_metadata = metadata_objects.first()
        self.assertEqual(encoding_metadata.field_name, 'encoding')
        self.assertEqual(encoding_metadata.field_value, 'utf-8')

    @patch('books.scanner.extractors.mobi.mobi.extract')
    @patch('builtins.open', new_callable=mock_open)
    @patch('os.path.exists')
    def test_extract_raw_metadata_in_result(self, mock_exists, mock_file, mock_mobi_extract):
        """Test that raw metadata is included in the result"""
        # Mock MOBI extraction
        mock_mobi_extract.return_value = ("/temp/dir", "/temp/file")
        mock_exists.return_value = True

        # Mock metadata
        metadata = {
            "title": "Test Book",
            "creator": "John Doe",
            "custom_field": "custom_value"
        }
        mock_file.return_value.read.return_value = json.dumps(metadata)

        result = extract(self.book)

        # Verify raw metadata is in result
        self.assertIn('raw_metadata', result)
        self.assertEqual(result['raw_metadata'], metadata)
        self.assertEqual(result['raw_metadata']['custom_field'], 'custom_value')
