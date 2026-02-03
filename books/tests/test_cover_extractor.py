"""
Tests for cover extraction from various file formats.

Tests EPUB, PDF, and archive (CBZ/CBR) cover extraction.
"""

import os
import tempfile
import zipfile
from io import BytesIO
from unittest.mock import MagicMock, patch

from django.test import TestCase
from PIL import Image

from books.utils.cover_extractor import (
    ArchiveCoverExtractor,
    CoverExtractionError,
    EPUBCoverExtractor,
    PDFCoverExtractor,
)


class EPUBCoverExtractorTestCase(TestCase):
    """Test cases for EPUB cover extraction."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up test files."""
        import shutil

        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def _create_test_epub_with_cover(self, cover_path="cover.jpg", use_opf=True):
        """Create a test EPUB file with a cover image."""
        epub_path = os.path.join(self.temp_dir, "test.epub")

        # Create a fake cover image
        img = Image.new("RGB", (100, 150), color="red")
        img_bytes = BytesIO()
        img.save(img_bytes, format="JPEG")
        cover_data = img_bytes.getvalue()

        with zipfile.ZipFile(epub_path, "w") as zf:
            # Add mimetype
            zf.writestr("mimetype", "application/epub+zip")

            # Add cover image
            zf.writestr(cover_path, cover_data)

            # Add OPF file with cover reference if requested
            if use_opf:
                opf_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0">
    <metadata>
        <meta name="cover" content="cover-image"/>
    </metadata>
    <manifest>
        <item id="cover-image" href="{cover_path}" media-type="image/jpeg"/>
    </manifest>
</package>"""
                zf.writestr("content.opf", opf_content)

        return epub_path, cover_data

    def test_extract_cover_from_opf(self):
        """Test extracting cover using OPF metadata."""
        epub_path, expected_data = self._create_test_epub_with_cover(cover_path="cover.jpg", use_opf=True)

        cover_data, internal_path = EPUBCoverExtractor.extract_cover(epub_path)

        self.assertIsNotNone(cover_data)
        self.assertEqual(internal_path, "cover.jpg")
        self.assertEqual(len(cover_data), len(expected_data))

    def test_extract_cover_from_common_path(self):
        """Test extracting cover from common path when OPF not available."""
        epub_path, expected_data = self._create_test_epub_with_cover(cover_path="cover.jpg", use_opf=False)

        cover_data, internal_path = EPUBCoverExtractor.extract_cover(epub_path)

        self.assertIsNotNone(cover_data)
        self.assertEqual(internal_path, "cover.jpg")

    def test_extract_cover_first_image(self):
        """Test extracting first image as cover when no standard cover found."""
        epub_path = os.path.join(self.temp_dir, "test.epub")

        # Create EPUB with non-standard image path
        img = Image.new("RGB", (100, 150), color="blue")
        img_bytes = BytesIO()
        img.save(img_bytes, format="JPEG")

        with zipfile.ZipFile(epub_path, "w") as zf:
            zf.writestr("mimetype", "application/epub+zip")
            zf.writestr("images/page001.jpg", img_bytes.getvalue())
            zf.writestr("images/page002.jpg", img_bytes.getvalue())

        cover_data, internal_path = EPUBCoverExtractor.extract_cover(epub_path)

        self.assertIsNotNone(cover_data)
        # Should get first image (alphabetically)
        self.assertEqual(internal_path, "images/page001.jpg")

    def test_extract_cover_no_images(self):
        """Test EPUB with no images returns None."""
        epub_path = os.path.join(self.temp_dir, "test.epub")

        with zipfile.ZipFile(epub_path, "w") as zf:
            zf.writestr("mimetype", "application/epub+zip")
            zf.writestr("content.opf", "<?xml version='1.0'?><package></package>")

        cover_data, internal_path = EPUBCoverExtractor.extract_cover(epub_path)

        self.assertIsNone(cover_data)
        self.assertIsNone(internal_path)

    def test_extract_cover_invalid_epub(self):
        """Test that invalid EPUB raises CoverExtractionError."""
        invalid_epub = os.path.join(self.temp_dir, "invalid.epub")

        with open(invalid_epub, "w") as f:
            f.write("not a valid epub file")

        with self.assertRaises(CoverExtractionError):
            EPUBCoverExtractor.extract_cover(invalid_epub)

    def test_list_images(self):
        """Test listing all images in EPUB."""
        epub_path = os.path.join(self.temp_dir, "test.epub")

        img_bytes = BytesIO()
        Image.new("RGB", (100, 150), color="green").save(img_bytes, format="JPEG")

        with zipfile.ZipFile(epub_path, "w") as zf:
            zf.writestr("cover.jpg", img_bytes.getvalue())
            zf.writestr("images/img1.png", img_bytes.getvalue())
            zf.writestr("images/img2.gif", img_bytes.getvalue())
            zf.writestr("text.html", "<html></html>")

        images = EPUBCoverExtractor.list_images(epub_path)

        self.assertEqual(len(images), 3)
        self.assertIn("cover.jpg", images)
        self.assertIn("images/img1.png", images)
        self.assertIn("images/img2.gif", images)


class PDFCoverExtractorTestCase(TestCase):
    """Test cases for PDF cover extraction."""

    def test_extract_cover_with_pdf2image(self):
        """Test PDF extraction using pdf2image."""
        # Mock pdf2image returning a PIL Image
        mock_image = MagicMock()
        mock_bytes = BytesIO()
        mock_image.save.side_effect = lambda buf, **kwargs: buf.write(b"fake_image_data")

        mock_convert = MagicMock(return_value=[mock_image])

        # Need to manually inject the function since it might not exist
        with patch("books.utils.cover_extractor.HAS_PDF2IMAGE", True):
            import books.utils.cover_extractor as extractor_module

            original_func = getattr(extractor_module, "convert_from_path", None)
            try:
                # Inject the mock function
                extractor_module.convert_from_path = mock_convert
                cover_data = PDFCoverExtractor.extract_cover("/fake/path.pdf")

                mock_convert.assert_called_once_with("/fake/path.pdf", dpi=150, first_page=1, last_page=1)
                self.assertIsNotNone(cover_data)
            finally:
                # Restore original state
                if original_func is not None:
                    extractor_module.convert_from_path = original_func
                elif hasattr(extractor_module, "convert_from_path"):
                    delattr(extractor_module, "convert_from_path")

    @patch("books.utils.cover_extractor.HAS_PDF2IMAGE", False)
    @patch("books.utils.cover_extractor.HAS_PYPDF2", True)
    @patch("books.utils.cover_extractor.PdfReader")
    def test_extract_cover_with_pypdf2_fallback(self, mock_reader_class):
        """Test PDF extraction falls back to PyPDF2 when pdf2image not available."""
        # Mock PyPDF2 reader
        mock_reader = MagicMock()
        mock_page = MagicMock()
        mock_reader.pages = [mock_page]
        mock_reader_class.return_value = mock_reader

        # Mock image extraction from page
        img_bytes = BytesIO()
        Image.new("RGB", (100, 150), color="red").save(img_bytes, format="JPEG")

        mock_obj = MagicMock()
        mock_obj.get_data.return_value = img_bytes.getvalue()
        mock_obj.__getitem__ = lambda self, key: "/Image" if key == "/Subtype" else None

        mock_page.__getitem__ = lambda self, key: {"/Resources": {"/XObject": MagicMock(get_object=lambda: {"img": mock_obj})}}[key]

        cover_data = PDFCoverExtractor.extract_cover("/fake/path.pdf")

        # Should use PyPDF2
        self.assertIsNotNone(cover_data)


class ArchiveCoverExtractorTestCase(TestCase):
    """Test cases for comic archive cover extraction."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up test files."""
        import shutil

        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def _create_test_cbz(self, images=None):
        """Create a test CBZ file with images."""
        cbz_path = os.path.join(self.temp_dir, "test.cbz")

        if images is None:
            images = ["001.jpg", "002.jpg", "003.jpg"]

        img_bytes = BytesIO()
        Image.new("RGB", (100, 150), color="blue").save(img_bytes, format="JPEG")

        with zipfile.ZipFile(cbz_path, "w") as zf:
            for img_name in images:
                zf.writestr(img_name, img_bytes.getvalue())

        return cbz_path

    def test_extract_cover_from_cbz(self):
        """Test extracting first image from CBZ."""
        cbz_path = self._create_test_cbz(["001.jpg", "002.jpg", "003.jpg"])

        cover_data, internal_path = ArchiveCoverExtractor.extract_cover(cbz_path)

        self.assertIsNotNone(cover_data)
        self.assertEqual(internal_path, "001.jpg")

    def test_extract_cover_sorted_alphabetically(self):
        """Test that images are sorted alphabetically."""
        cbz_path = self._create_test_cbz(["page_03.jpg", "page_01.jpg", "page_02.jpg"])

        cover_data, internal_path = ArchiveCoverExtractor.extract_cover(cbz_path)

        self.assertIsNotNone(cover_data)
        # Should get first alphabetically
        self.assertEqual(internal_path, "page_01.jpg")

    def test_extract_cover_skips_macos_metadata(self):
        """Test that __MACOSX files are skipped."""
        cbz_path = os.path.join(self.temp_dir, "test.cbz")

        img_bytes = BytesIO()
        Image.new("RGB", (100, 150), color="blue").save(img_bytes, format="JPEG")

        with zipfile.ZipFile(cbz_path, "w") as zf:
            zf.writestr("__MACOSX/._001.jpg", b"metadata")
            zf.writestr("001.jpg", img_bytes.getvalue())
            zf.writestr("002.jpg", img_bytes.getvalue())

        cover_data, internal_path = ArchiveCoverExtractor.extract_cover(cbz_path)

        self.assertIsNotNone(cover_data)
        # Should skip __MACOSX and get real image
        self.assertEqual(internal_path, "001.jpg")

    def test_extract_cover_no_images(self):
        """Test CBZ with no images returns None."""
        cbz_path = os.path.join(self.temp_dir, "test.cbz")

        with zipfile.ZipFile(cbz_path, "w") as zf:
            zf.writestr("readme.txt", "No images here")

        cover_data, internal_path = ArchiveCoverExtractor.extract_cover(cbz_path)

        self.assertIsNone(cover_data)
        self.assertIsNone(internal_path)

    def test_extract_cover_invalid_cbz(self):
        """Test that invalid CBZ raises CoverExtractionError."""
        invalid_cbz = os.path.join(self.temp_dir, "invalid.cbz")

        with open(invalid_cbz, "w") as f:
            f.write("not a valid zip file")

        with self.assertRaises(CoverExtractionError):
            ArchiveCoverExtractor.extract_cover(invalid_cbz)

    def test_extract_cover_unsupported_format(self):
        """Test that unsupported archive format raises error."""
        with self.assertRaises(CoverExtractionError) as cm:
            ArchiveCoverExtractor.extract_cover("/path/to/file.rar")

        # CBR should raise error about missing rarfile library or unsupported format
        self.assertIn("archive", str(cm.exception).lower())

    @patch("books.utils.cover_extractor.HAS_RARFILE", True)
    @patch("books.utils.cover_extractor.rarfile")
    def test_extract_cover_from_cbr(self, mock_rarfile):
        """Test extracting first image from CBR."""
        # Mock rarfile.RarFile
        mock_rf = MagicMock()
        mock_rf.namelist.return_value = ["001.jpg", "002.jpg"]

        img_bytes = BytesIO()
        Image.new("RGB", (100, 150), color="blue").save(img_bytes, format="JPEG")
        mock_rf.read.return_value = img_bytes.getvalue()

        mock_rarfile.RarFile.return_value.__enter__ = lambda self: mock_rf
        mock_rarfile.RarFile.return_value.__exit__ = lambda self, *args: None

        cover_data, internal_path = ArchiveCoverExtractor.extract_cover("/fake/test.cbr")

        self.assertIsNotNone(cover_data)
        self.assertEqual(internal_path, "001.jpg")
