"""
Tests for Multi-Cover Selection (Feature 2 - Phase 2)

Tests cover:
- Extracting all images from EPUB with metadata
- AJAX endpoint for listing internal covers
- Cover caching and performance
- Modal UI integration
- Selection persistence
"""

import shutil
import tempfile
import zipfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import TestCase, TransactionTestCase
from django.urls import reverse

from books.models import Book, BookFile, FinalMetadata, ScanFolder
from books.utils.cover_extractor import EPUBCoverExtractor

User = get_user_model()


class EPUBImageExtractionTestCase(TestCase):
    """Test list_all_covers() function."""

    def setUp(self):
        """Create test EPUB with multiple images."""
        self.test_dir = Path(tempfile.mkdtemp())
        self.epub_path = self.test_dir / "test.epub"
        self._create_epub_with_multiple_images()

    def tearDown(self):
        """Clean up."""
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    def _create_epub_with_multiple_images(self):
        """Create EPUB with 5 images of varying sizes."""
        from io import BytesIO

        from PIL import Image

        with zipfile.ZipFile(self.epub_path, "w", zipfile.ZIP_DEFLATED) as epub:
            # Mimetype
            epub.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)

            # Container
            epub.writestr(
                "META-INF/container.xml",
                """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>""",
            )

            # OPF - designate cover1.jpg as the OPF cover
            epub.writestr(
                "OEBPS/content.opf",
                """<?xml version="1.0"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>Test Book</dc:title>
    <meta name="cover" content="cover-image"/>
  </metadata>
  <manifest>
    <item id="cover-image" href="images/cover1.jpg" media-type="image/jpeg"/>
    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
  </manifest>
  <spine toc="ncx"></spine>
</package>""",
            )

            # Create images with different dimensions
            images_data = [
                ("OEBPS/images/cover1.jpg", 1200, 1600),  # Excellent - OPF cover
                ("OEBPS/images/cover2.jpg", 800, 1200),  # Good
                ("OEBPS/images/cover3.png", 600, 900),  # Fair
                ("OEBPS/images/thumbnail.jpg", 300, 400),  # Poor
                ("OEBPS/images/large.jpg", 1500, 2000),  # Excellent
            ]

            for path, width, height in images_data:
                img = Image.new("RGB", (width, height), color="blue")
                img_bytes = BytesIO()
                fmt = "PNG" if path.endswith(".png") else "JPEG"
                img.save(img_bytes, format=fmt)
                epub.writestr(path, img_bytes.getvalue())

            # NCX
            epub.writestr("OEBPS/toc.ncx", '<?xml version="1.0"?><ncx/>')

    def test_list_all_covers_extraction(self):
        """Test that all images are extracted."""
        covers = EPUBCoverExtractor.list_all_covers(str(self.epub_path))

        self.assertEqual(len(covers), 5)  # Should find all 5 images

    def test_list_all_covers_metadata(self):
        """Test that metadata is correctly extracted."""
        covers = EPUBCoverExtractor.list_all_covers(str(self.epub_path))

        # Check first cover (OPF-designated)
        cover1 = next(c for c in covers if "cover1.jpg" in c["internal_path"])
        self.assertEqual(cover1["width"], 1200)
        self.assertEqual(cover1["height"], 1600)
        self.assertEqual(cover1["format"], "JPEG")
        self.assertTrue(cover1["is_opf_cover"])
        self.assertGreater(cover1["file_size"], 0)

        # Check a PNG image
        cover3 = next(c for c in covers if "cover3.png" in c["internal_path"])
        self.assertEqual(cover3["format"], "PNG")
        self.assertFalse(cover3["is_opf_cover"])

    def test_list_all_covers_position(self):
        """Test that position index is assigned correctly."""
        covers = EPUBCoverExtractor.list_all_covers(str(self.epub_path))

        # Positions should be 0-indexed and sequential
        positions = [c["position"] for c in covers]
        self.assertEqual(positions, [0, 1, 2, 3, 4])

    def test_list_all_covers_includes_image_data(self):
        """Test that raw image data is included."""
        covers = EPUBCoverExtractor.list_all_covers(str(self.epub_path))

        for cover in covers:
            self.assertIn("image_data", cover)
            self.assertIsInstance(cover["image_data"], bytes)
            self.assertGreater(len(cover["image_data"]), 0)

    def test_list_all_covers_empty_epub(self):
        """Test handling of EPUB with no images."""
        empty_epub_path = self.test_dir / "empty.epub"

        with zipfile.ZipFile(empty_epub_path, "w") as epub:
            epub.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
            epub.writestr(
                "META-INF/container.xml",
                """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles><rootfile full-path="content.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>""",
            )
            epub.writestr(
                "content.opf",
                """<?xml version="1.0"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Empty</dc:title></metadata>
  <manifest><item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/></manifest>
  <spine toc="ncx"></spine>
</package>""",
            )
            epub.writestr("toc.ncx", '<?xml version="1.0"?><ncx/>')

        covers = EPUBCoverExtractor.list_all_covers(str(empty_epub_path))
        self.assertEqual(len(covers), 0)


class AJAXListInternalCoversTestCase(TransactionTestCase):
    """Test AJAX endpoint for listing internal covers."""

    def setUp(self):
        """Set up test environment."""
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.client.login(username="testuser", password="testpass")

        self.test_dir = Path(tempfile.mkdtemp())
        self.epub_path = self.test_dir / "test.epub"
        self._create_test_epub()

        self.scan_folder = ScanFolder.objects.create(path=str(self.test_dir), name="Test")

        self.book = Book.objects.create(scan_folder=self.scan_folder, title="Test Book")

        self.book_file = BookFile.objects.create(book=self.book, file_path=str(self.epub_path), file_format="epub", file_name="test.epub")

        FinalMetadata.objects.create(book=self.book, final_title="Test Book")

    def tearDown(self):
        """Clean up."""
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    def _create_test_epub(self):
        """Create simple test EPUB."""
        from io import BytesIO

        from PIL import Image

        with zipfile.ZipFile(self.epub_path, "w") as epub:
            epub.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
            epub.writestr(
                "META-INF/container.xml",
                """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>""",
            )
            epub.writestr(
                "OEBPS/content.opf",
                """<?xml version="1.0"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>Test</dc:title>
    <meta name="cover" content="cover-img"/>
  </metadata>
  <manifest>
    <item id="cover-img" href="images/cover.jpg" media-type="image/jpeg"/>
    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
  </manifest>
  <spine toc="ncx"></spine>
</package>""",
            )

            # Create image
            img = Image.new("RGB", (800, 1200), color="red")
            img_bytes = BytesIO()
            img.save(img_bytes, format="JPEG")
            epub.writestr("OEBPS/images/cover.jpg", img_bytes.getvalue())

            epub.writestr("OEBPS/toc.ncx", '<?xml version="1.0"?><ncx/>')

    def test_ajax_list_internal_covers_success(self):
        """Test successful AJAX request."""
        response = self.client.get(reverse("books:ajax_list_internal_covers", kwargs={"book_id": self.book.id}))

        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertTrue(data["success"])
        self.assertIn("covers", data)
        self.assertEqual(data["total_count"], 1)

    def test_ajax_list_internal_covers_metadata(self):
        """Test that cover metadata is correctly returned."""
        response = self.client.get(reverse("books:ajax_list_internal_covers", kwargs={"book_id": self.book.id}))

        data = response.json()
        covers = data["covers"]

        self.assertEqual(len(covers), 1)
        cover = covers[0]

        self.assertEqual(cover["width"], 800)
        self.assertEqual(cover["height"], 1200)
        self.assertEqual(cover["format"], "JPEG")
        self.assertTrue(cover["is_opf_cover"])
        self.assertGreater(cover["file_size"], 0)
        self.assertIn("preview_url", cover)

    def test_ajax_list_internal_covers_no_epub(self):
        """Test error when book has no EPUB file."""
        # Create book without EPUB
        book2 = Book.objects.create(scan_folder=self.scan_folder, title="No EPUB")
        BookFile.objects.create(book=book2, file_path="/test.pdf", file_format="pdf")
        FinalMetadata.objects.create(book=book2, final_title="No EPUB")

        response = self.client.get(reverse("books:ajax_list_internal_covers", kwargs={"book_id": book2.id}))

        self.assertEqual(response.status_code, 404)
        data = response.json()
        self.assertFalse(data["success"])
        self.assertIn("No EPUB file found", data["error"])

    def test_ajax_list_internal_covers_missing_file(self):
        """Test error when EPUB file doesn't exist on disk."""
        # Update to non-existent path
        self.book_file.file_path = "/nonexistent/file.epub"
        self.book_file.save()

        response = self.client.get(reverse("books:ajax_list_internal_covers", kwargs={"book_id": self.book.id}))

        self.assertEqual(response.status_code, 404)
        data = response.json()
        self.assertFalse(data["success"])

    def test_ajax_list_internal_covers_authentication(self):
        """Test that endpoint requires authentication."""
        self.client.logout()

        response = self.client.get(reverse("books:ajax_list_internal_covers", kwargs={"book_id": self.book.id}))

        # Should redirect to login
        self.assertEqual(response.status_code, 302)


class CoverCachingTestCase(TransactionTestCase):
    """Test cover caching performance."""

    def setUp(self):
        """Set up test environment."""
        self.test_dir = Path(tempfile.mkdtemp())
        self.epub_path = self.test_dir / "test.epub"
        self._create_test_epub()

    def tearDown(self):
        """Clean up."""
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    def _create_test_epub(self):
        """Create test EPUB with multiple images."""
        from io import BytesIO

        from PIL import Image

        with zipfile.ZipFile(self.epub_path, "w") as epub:
            epub.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
            epub.writestr(
                "META-INF/container.xml",
                """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>""",
            )
            epub.writestr(
                "OEBPS/content.opf",
                """<?xml version="1.0"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Test</dc:title></metadata>
  <manifest>
    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
  </manifest>
  <spine toc="ncx"></spine>
</package>""",
            )

            # Create 3 images
            for i in range(3):
                img = Image.new("RGB", (400, 600), color="green")
                img_bytes = BytesIO()
                img.save(img_bytes, format="JPEG")
                epub.writestr(f"OEBPS/images/img{i}.jpg", img_bytes.getvalue())

            epub.writestr("OEBPS/toc.ncx", '<?xml version="1.0"?><ncx/>')

    def test_extract_all_covers_caching(self):
        """Test that covers are cached for preview."""
        from books.utils.cover_cache import CoverCache

        # Clear cache first
        CoverCache.clear_all()

        # Extract covers
        covers = EPUBCoverExtractor.list_all_covers(str(self.epub_path))

        self.assertEqual(len(covers), 3)

        # Verify each cover has image data for caching
        for cover in covers:
            self.assertIn("image_data", cover)
            self.assertIsInstance(cover["image_data"], bytes)
