"""
Integration tests for EPUB metadata embedding with OPF normalization.
"""

import shutil
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from django.test import TestCase

from books.models import Book, BookFile, FinalMetadata
from books.utils.epub.metadata_embedder import embed_metadata_in_epub


class EPUBMetadataEmbeddingTestCase(TestCase):
    """Test full EPUB metadata embedding workflow."""

    def setUp(self):
        """Set up test EPUB file."""
        self.test_dir = Path(tempfile.mkdtemp())
        self.epub_path = self.test_dir / "test_book.epub"

        # Create a minimal valid EPUB
        self._create_test_epub()

        # Create test book with metadata
        self.book = self._create_test_book()

    def tearDown(self):
        """Clean up test files."""
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    def _create_test_epub(self):
        """Create a minimal valid EPUB file for testing."""
        with zipfile.ZipFile(self.epub_path, "w", zipfile.ZIP_DEFLATED) as epub:
            # Add mimetype (must be first and uncompressed)
            epub.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)

            # Add META-INF/container.xml
            container_xml = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>"""
            epub.writestr("META-INF/container.xml", container_xml)

            # Add OPF with messy structure and Calibre metadata
            messy_opf = """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" unique-identifier="bookid" version="2.0">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf" xmlns:calibre="http://calibre.kovidgoyal.net/2009/metadata">
    <dc:description>Old description</dc:description>
    <meta name="calibre:timestamp" content="2024-01-01T00:00:00+00:00"/>
    <dc:title>Old Title</dc:title>
    <dc:language>en</dc:language>
    <meta name="calibre:user_metadata:#myseries" content="{}"/>
    <dc:creator>Old Author</dc:creator>
    <meta name="calibre:rating" content="8"/>
    <dc:identifier id="bookid">test-id-123</dc:identifier>
  </metadata>
  <manifest>
    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
  </manifest>
  <spine toc="ncx">
  </spine>
</package>"""
            epub.writestr("OEBPS/content.opf", messy_opf)

    def _create_test_book(self):
        """Create a test book with final metadata."""
        # Create book
        book = Book.objects.create(content_type="ebook")

        # Create associated book file (first file is automatically primary)
        BookFile.objects.create(book=book, file_path=str(self.epub_path), file_format="EPUB")

        # Create final metadata
        FinalMetadata.objects.create(
            book=book, final_title="New Title", final_author="New Author", language="fr", final_publisher="Test Publisher", description="New detailed description"
        )

        return book

    def test_embed_metadata_updates_opf(self):
        """Test that metadata is correctly embedded in EPUB."""
        # Create a cover image for testing
        cover_path = self.test_dir / "cover.jpg"
        cover_path.write_bytes(b"fake image data")

        # Embed metadata
        result = embed_metadata_in_epub(self.epub_path, self.book, cover_path)

        # Verify success
        self.assertTrue(result, "Metadata embedding should succeed")

        # Extract and verify OPF
        with zipfile.ZipFile(self.epub_path, "r") as epub:
            opf_content = epub.read("OEBPS/content.opf").decode("utf-8")

        # Parse OPF
        root = ET.fromstring(opf_content)
        namespaces = {"opf": "http://www.idpf.org/2007/opf", "dc": "http://purl.org/dc/elements/1.1/"}

        # Verify metadata was updated
        title = root.find(".//dc:title", namespaces)
        self.assertIsNotNone(title)
        self.assertEqual(title.text, "New Title")

        author = root.find(".//dc:creator", namespaces)
        self.assertIsNotNone(author)
        self.assertEqual(author.text, "New Author")

        language = root.find(".//dc:language", namespaces)
        self.assertIsNotNone(language)
        self.assertEqual(language.text, "fr")

        publisher = root.find(".//dc:publisher", namespaces)
        self.assertIsNotNone(publisher)
        self.assertEqual(publisher.text, "Test Publisher")

        description = root.find(".//dc:description", namespaces)
        self.assertIsNotNone(description)
        self.assertEqual(description.text, "New detailed description")

    def test_calibre_metadata_removed(self):
        """Test that Calibre metadata is removed during embedding."""
        result = embed_metadata_in_epub(self.epub_path, self.book)
        self.assertTrue(result)

        # Extract and verify OPF
        with zipfile.ZipFile(self.epub_path, "r") as epub:
            opf_content = epub.read("OEBPS/content.opf").decode("utf-8")

        # Verify no Calibre metadata remains
        self.assertNotIn("calibre:", opf_content.lower())
        self.assertNotIn("calibre_", opf_content.lower())

    def test_metadata_elements_reordered(self):
        """Test that metadata elements are in the correct order."""
        result = embed_metadata_in_epub(self.epub_path, self.book)
        self.assertTrue(result)

        # Extract and parse OPF
        with zipfile.ZipFile(self.epub_path, "r") as epub:
            opf_content = epub.read("OEBPS/content.opf").decode("utf-8")

        root = ET.fromstring(opf_content)
        namespaces = {"opf": "http://www.idpf.org/2007/opf", "dc": "http://purl.org/dc/elements/1.1/"}

        metadata = root.find(".//opf:metadata", namespaces)
        self.assertIsNotNone(metadata)

        # Get element order
        elements = []
        for elem in metadata:
            tag = elem.tag
            if tag.startswith("{http://purl.org/dc/elements/1.1/}"):
                local = tag.replace("{http://purl.org/dc/elements/1.1/}", "")
                elements.append(f"dc:{local}")
            elif tag.startswith("{http://www.idpf.org/2007/opf}"):
                local = tag.replace("{http://www.idpf.org/2007/opf}", "")
                elements.append(f"opf:{local}")

        # Verify identifier comes before title
        if "dc:identifier" in elements and "dc:title" in elements:
            id_index = elements.index("dc:identifier")
            title_index = elements.index("dc:title")
            self.assertLess(id_index, title_index, "identifier should come before title")

        # Verify title comes before creator
        if "dc:title" in elements and "dc:creator" in elements:
            title_index = elements.index("dc:title")
            creator_index = elements.index("dc:creator")
            self.assertLess(title_index, creator_index, "title should come before creator")

    def test_opf_formatting_consistent(self):
        """Test that OPF formatting is consistent."""
        result = embed_metadata_in_epub(self.epub_path, self.book)
        self.assertTrue(result)

        # Extract OPF
        with zipfile.ZipFile(self.epub_path, "r") as epub:
            opf_content = epub.read("OEBPS/content.opf").decode("utf-8")

        # Verify consistent indentation (2 spaces)
        lines = opf_content.split("\n")
        for line in lines:
            if line and line[0] == " ":
                # Count leading spaces
                spaces = len(line) - len(line.lstrip(" "))
                # Should be multiple of 2
                self.assertEqual(spaces % 2, 0, f"Line should have even number of spaces: {line}")

    def test_backup_created(self):
        """Test that a backup file is created."""
        backup_path = self.epub_path.with_suffix(".epub.bak")

        # Ensure backup doesn't exist
        if backup_path.exists():
            backup_path.unlink()

        result = embed_metadata_in_epub(self.epub_path, self.book)
        self.assertTrue(result)

        # Verify backup was created
        self.assertTrue(backup_path.exists(), "Backup file should be created")

    def test_cover_embedded(self):
        """Test that cover image is embedded in EPUB."""
        cover_path = self.test_dir / "cover.jpg"
        cover_path.write_bytes(b"fake jpg image data")

        result = embed_metadata_in_epub(self.epub_path, self.book, cover_path)
        self.assertTrue(result)

        # Verify cover is in EPUB
        with zipfile.ZipFile(self.epub_path, "r") as epub:
            file_list = epub.namelist()

            # Should have a cover image
            cover_files = [f for f in file_list if "cover" in f.lower() and f.endswith((".jpg", ".jpeg", ".png"))]
            self.assertGreater(len(cover_files), 0, "Should have cover image in EPUB")

            # Verify OPF references cover
            opf_content = epub.read("OEBPS/content.opf").decode("utf-8")
            root = ET.fromstring(opf_content)
            namespaces = {"opf": "http://www.idpf.org/2007/opf"}

            # Check manifest for cover
            manifest = root.find(".//opf:manifest", namespaces)
            cover_item = manifest.find(".//opf:item[@id='cover-image']", namespaces)
            self.assertIsNotNone(cover_item, "Manifest should have cover-image item")

    def test_normalization_produces_identical_results(self):
        """Test that normalizing the same EPUB twice produces identical file sizes."""
        # Create two identical EPUBs
        epub2_path = self.test_dir / "test_book2.epub"
        shutil.copy2(self.epub_path, epub2_path)

        # Create second book with same metadata
        book2 = Book.objects.create(content_type="ebook")

        # Create associated book file
        BookFile.objects.create(book=book2, file_path=str(epub2_path), file_format="EPUB")

        FinalMetadata.objects.create(
            book=book2, final_title="New Title", final_author="New Author", language="fr", final_publisher="Test Publisher", description="New detailed description"
        )

        # Embed metadata in both
        result1 = embed_metadata_in_epub(self.epub_path, self.book)
        result2 = embed_metadata_in_epub(epub2_path, book2)

        self.assertTrue(result1)
        self.assertTrue(result2)

        # Compare file sizes (should be identical due to normalization)
        size1 = self.epub_path.stat().st_size
        size2 = epub2_path.stat().st_size

        self.assertEqual(size1, size2, "Normalized EPUBs with identical metadata should have identical file sizes")
