"""
Tests for scanner integration with cover detection.

Tests that the scanner correctly detects and extracts covers during file processing.
"""

import os
import tempfile
import zipfile
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from django.test import TestCase
from PIL import Image

from books.models import Book, BookFile, ScanFolder
from books.scanner.folder import _detect_and_extract_cover
from books.utils.cover_cache import CoverCache


class CoverDetectionIntegrationTestCase(TestCase):
    """Test cases for cover detection during scanning."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.scan_folder = ScanFolder.objects.create(name="Test Folder", path=self.temp_dir, content_type="ebooks")

    def tearDown(self):
        """Clean up test files."""
        import shutil

        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
        CoverCache.clear_all()

    def _create_test_epub(self, filename="test.epub", with_cover=True):
        """Create a test EPUB file."""
        epub_path = os.path.join(self.temp_dir, filename)

        with zipfile.ZipFile(epub_path, "w") as zf:
            zf.writestr("mimetype", "application/epub+zip")

            if with_cover:
                img = Image.new("RGB", (100, 150), color="red")
                img_bytes = BytesIO()
                img.save(img_bytes, format="JPEG")
                zf.writestr("cover.jpg", img_bytes.getvalue())

        return epub_path

    def _create_external_cover(self, book_path):
        """Create an external companion cover file."""
        cover_path = str(Path(book_path).with_suffix(".jpg"))

        img = Image.new("RGB", (100, 150), color="green")
        img.save(cover_path)

        return cover_path

    def test_detect_external_cover_priority(self):
        """Test that external covers take priority over internal."""
        # Create EPUB with internal cover
        epub_path = self._create_test_epub(with_cover=True)

        # Create external cover
        external_cover_path = self._create_external_cover(epub_path)
        cover_files = [external_cover_path]

        # Detect cover
        cover_path, source_type, internal_path, has_internal = _detect_and_extract_cover(epub_path, "epub", cover_files)

        # Should use external cover
        self.assertEqual(cover_path, external_cover_path)
        self.assertEqual(source_type, "external")
        self.assertIsNone(internal_path)
        self.assertFalse(has_internal)

    def test_detect_epub_internal_cover(self):
        """Test detecting and extracting EPUB internal cover."""
        epub_path = self._create_test_epub(with_cover=True)
        cover_files = []  # No external cover

        # Detect cover
        cover_path, source_type, internal_path, has_internal = _detect_and_extract_cover(epub_path, "epub", cover_files)

        # Should extract internal cover
        self.assertIsNotNone(cover_path)
        self.assertTrue(cover_path.startswith("cover_cache/"))
        self.assertEqual(source_type, "epub_internal")
        self.assertEqual(internal_path, "cover.jpg")
        self.assertTrue(has_internal)

        # Verify cover was cached
        self.assertTrue(CoverCache.has_cover(epub_path, internal_path))

    def test_detect_epub_no_cover(self):
        """Test EPUB with no internal or external cover."""
        epub_path = self._create_test_epub(with_cover=False)
        cover_files = []

        # Detect cover
        cover_path, source_type, internal_path, has_internal = _detect_and_extract_cover(epub_path, "epub", cover_files)

        # Should find no cover
        self.assertIsNone(cover_path)
        self.assertIsNone(source_type)
        self.assertIsNone(internal_path)
        self.assertFalse(has_internal)

    def test_detect_cbz_internal_cover(self):
        """Test detecting and extracting CBZ internal cover."""
        cbz_path = os.path.join(self.temp_dir, "test.cbz")

        # Create CBZ with images
        img_bytes = BytesIO()
        Image.new("RGB", (100, 150), color="blue").save(img_bytes, format="JPEG")

        with zipfile.ZipFile(cbz_path, "w") as zf:
            zf.writestr("001.jpg", img_bytes.getvalue())
            zf.writestr("002.jpg", img_bytes.getvalue())

        cover_files = []

        # Detect cover
        cover_path, source_type, internal_path, has_internal = _detect_and_extract_cover(cbz_path, "cbz", cover_files)

        # Should extract first image
        self.assertIsNotNone(cover_path)
        self.assertTrue(cover_path.startswith("cover_cache/"))
        self.assertEqual(source_type, "archive_first")
        self.assertEqual(internal_path, "001.jpg")
        self.assertTrue(has_internal)

    @patch("books.utils.cover_extractor.PDFCoverExtractor.extract_cover")
    def test_detect_pdf_cover(self, mock_extract):
        """Test detecting and extracting PDF first page as cover."""
        pdf_path = os.path.join(self.temp_dir, "test.pdf")

        # Create fake PDF file
        with open(pdf_path, "wb") as f:
            f.write(b"%PDF-1.4 fake pdf")

        # Mock PDF extraction
        img_bytes = BytesIO()
        Image.new("RGB", (100, 150), color="yellow").save(img_bytes, format="JPEG")
        mock_extract.return_value = img_bytes.getvalue()

        cover_files = []

        # Detect cover
        cover_path, source_type, internal_path, has_internal = _detect_and_extract_cover(pdf_path, "pdf", cover_files)

        # Should extract PDF page
        self.assertIsNotNone(cover_path)
        self.assertTrue(cover_path.startswith("cover_cache/"))
        self.assertEqual(source_type, "pdf_page")
        self.assertEqual(internal_path, "page_1")
        self.assertTrue(has_internal)

    def test_cover_cache_reuse(self):
        """Test that cached covers are reused on subsequent scans."""
        epub_path = self._create_test_epub(with_cover=True)
        cover_files = []

        # First detection - should extract and cache
        cover_path1, _, internal_path1, _ = _detect_and_extract_cover(epub_path, "epub", cover_files)

        # Get cache path
        cache_path = CoverCache.get_cover(epub_path, "cover.jpg")
        self.assertIsNotNone(cache_path)

        # Second detection - should use cached version
        # (In reality, scanner would check cover_path first, but this tests the extractor)
        self.assertTrue(CoverCache.has_cover(epub_path, "cover.jpg"))

    def test_unsupported_format_no_extraction(self):
        """Test that unsupported formats don't attempt extraction."""
        mobi_path = os.path.join(self.temp_dir, "test.mobi")

        # Create fake MOBI file
        with open(mobi_path, "wb") as f:
            f.write(b"fake mobi content")

        cover_files = []

        # Detect cover
        cover_path, source_type, internal_path, has_internal = _detect_and_extract_cover(mobi_path, "mobi", cover_files)

        # Should find no cover (MOBI extraction not implemented)
        self.assertIsNone(cover_path)
        self.assertIsNone(source_type)


class BookFileCoverFieldsTestCase(TestCase):
    """Test that BookFile cover fields are populated correctly."""

    def setUp(self):
        """Set up test fixtures."""
        self.scan_folder = ScanFolder.objects.create(name="Test Folder", path="/test/path", content_type="ebooks")

    def test_book_file_cover_fields_external(self):
        """Test BookFile fields for external cover."""
        book = Book.objects.create(title="Test Book")
        book_file = BookFile.objects.create(
            book=book, file_path="/test/book.epub", file_format="epub", cover_path="/test/book.jpg", cover_source_type="external", cover_internal_path="", has_internal_cover=False
        )

        self.assertEqual(book_file.cover_source_type, "external")
        self.assertFalse(book_file.has_internal_cover)
        self.assertEqual(book_file.cover_internal_path, "")

    def test_book_file_cover_fields_epub_internal(self):
        """Test BookFile fields for EPUB internal cover."""
        book = Book.objects.create(title="Test Book")
        book_file = BookFile.objects.create(
            book=book,
            file_path="/test/book.epub",
            file_format="epub",
            cover_path="cover_cache/abc123.jpg",
            cover_source_type="epub_internal",
            cover_internal_path="OEBPS/cover.jpg",
            has_internal_cover=True,
        )

        self.assertEqual(book_file.cover_source_type, "epub_internal")
        self.assertTrue(book_file.has_internal_cover)
        self.assertEqual(book_file.cover_internal_path, "OEBPS/cover.jpg")

    def test_book_file_cover_source_choices(self):
        """Test that cover_source_type uses valid choices."""
        book = Book.objects.create(title="Test Book")

        # Test all valid source types
        for source_type in ["external", "epub_internal", "pdf_page", "archive_first", "mobi_internal"]:
            book_file = BookFile.objects.create(book=book, file_path=f"/test/book_{source_type}.epub", file_format="epub", cover_source_type=source_type)
            self.assertEqual(book_file.cover_source_type, source_type)

    def test_book_file_cover_fields_nullable(self):
        """Test that cover fields can be null/empty."""
        book = Book.objects.create(title="Test Book")
        book_file = BookFile.objects.create(book=book, file_path="/test/book.epub", file_format="epub")

        # Fields should be empty/null by default
        self.assertEqual(book_file.cover_path, "")
        self.assertIsNone(book_file.cover_source_type)
        self.assertEqual(book_file.cover_internal_path, "")
        self.assertFalse(book_file.has_internal_cover)
