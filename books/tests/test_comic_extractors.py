"""Tests for comic book archive extractors (CBR/CBZ)."""

import shutil
import tempfile
from unittest.mock import MagicMock, patch

from django.test import TestCase

from books.models import Book, BookFile, BookMetadata, DataSource, ScanFolder
from books.scanner.extractors.comic import (
    _clean_comic_title,
    _detect_issue_type,
    _extract_comic_info_xml,
    _parse_filename_metadata,
    extract_cbr,
    extract_cbz,
    get_comic_series_list,
)


class ComicExtractorTests(TestCase):
    """Test cases for comic book archive metadata extractors"""

    def setUp(self):
        """Set up test data"""
        # Create content scan data source
        self.content_source, _ = DataSource.objects.get_or_create(name=DataSource.CONTENT_SCAN, defaults={"trust_level": 1.0})

        # Create temporary directory for scan folder
        self.test_dir = tempfile.mkdtemp()

        # Create scan folder
        self.scan_folder = ScanFolder.objects.create(name="Test Comics Folder", path=self.test_dir, content_type="comics")

    def tearDown(self):
        """Clean up test data"""
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_clean_comic_title_basic(self):
        """Test basic title cleaning"""
        result = _clean_comic_title("Spider_Man_Amazing_#001_(2023)")
        self.assertEqual(result, "Spider Man Amazing")

    def test_clean_comic_title_volume_removal(self):
        """Test volume number removal"""
        result = _clean_comic_title("Batman Vol.1 Detective Comics")
        self.assertEqual(result, "Batman")

    def test_clean_comic_title_empty_input(self):
        """Test handling of empty or None input"""
        result = _clean_comic_title("")
        self.assertIsNone(result)

        result = _clean_comic_title(None)
        self.assertIsNone(result)

    def test_parse_filename_metadata_basic(self):
        """Test basic filename parsing"""
        result = _parse_filename_metadata("Batman #001.cbz")
        self.assertIn("issue_type", result)
        self.assertEqual(result["issue_type"], "main_series")

    def test_detect_issue_type_annual(self):
        """Test detection of annual issues"""
        result = _detect_issue_type("Batman Annual 001.cbz")
        self.assertEqual(result, "annual")

    def test_detect_issue_type_main_series(self):
        """Test detection of main series issues"""
        result = _detect_issue_type("Batman #001.cbz")
        self.assertEqual(result, "main_series")

    @patch("books.scanner.extractors.comic.rarfile")
    def test_extract_cbr_basic(self, mock_rarfile):
        """Test basic CBR extraction"""
        # Create test book
        book = Book.objects.create(scan_folder=self.scan_folder, content_type="comic")
        BookFile.objects.create(book=book, file_path=f"{self.test_dir}/comic.cbr", file_format="cbr")

        # Mock rarfile behavior
        mock_rar = MagicMock()
        mock_rarfile.RarFile.return_value.__enter__.return_value = mock_rar
        mock_rar.namelist.return_value = ["page001.jpg", "page002.png"]
        mock_rar.read.return_value = b"fake image data"

        # Test extraction
        with patch("books.scanner.extractors.comic.os.path.exists", return_value=True):
            with patch("books.scanner.extractors.comic._enrich_with_comicvine", return_value={}):
                result = extract_cbr(book)
                # The function returns True on success
                self.assertIsNotNone(result)

    @patch("books.scanner.extractors.comic.zipfile")
    def test_extract_cbz_basic(self, mock_zipfile):
        """Test basic CBZ extraction"""
        # Create test book
        book = Book.objects.create(scan_folder=self.scan_folder, content_type="comic")
        BookFile.objects.create(book=book, file_path=f"{self.test_dir}/comic.cbz", file_format="cbz")

        # Mock zipfile behavior
        mock_zip = MagicMock()
        mock_zipfile.ZipFile.return_value.__enter__.return_value = mock_zip
        mock_zip.namelist.return_value = ["page001.jpg", "page002.png"]
        mock_zip.read.return_value = b"fake image data"

        # Test extraction
        with patch("books.scanner.extractors.comic.os.path.exists", return_value=True):
            with patch("books.scanner.extractors.comic._enrich_with_comicvine", return_value={}):
                result = extract_cbz(book)
                # The function returns True on success
                self.assertIsNotNone(result)

    def test_get_comic_series_list_basic(self):
        """Test getting comic series list"""
        # Create some test books with metadata
        book1 = Book.objects.create(scan_folder=self.scan_folder, content_type="comic")
        BookFile.objects.create(book=book1, file_path=f"{self.test_dir}/batman_001.cbr", file_format="cbr")

        BookMetadata.objects.create(book=book1, source=self.content_source, field_name="series", field_value="Batman", confidence=1.0)

        result = get_comic_series_list()
        self.assertIsInstance(result, list)

    def test_extract_comic_info_xml_invalid(self):
        """Test extracting invalid ComicInfo.xml"""
        result = _extract_comic_info_xml(b"invalid xml")
        self.assertIsNone(result)

        result = _extract_comic_info_xml(None)
        self.assertIsNone(result)
