"""
Tests for Unified Cover Selection System (Phase 2 Enhancement)

Tests cover:
- Cover selection from all sources (internal, uploaded, API)
- Radio button selection (final cover)
- Checkbox selection (download multiple)
- Image cleanup option
- EPUB embedding with selected cover
- Orphaned image detection and removal
- Preview functionality
- Complete workflow integration
"""

import shutil
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, TransactionTestCase
from django.urls import reverse

from books.models import Book, BookCover, BookFile, DataSource, FinalMetadata, ScanFolder
from books.utils.batch_renamer import BatchRenamer
from books.utils.epub import embed_metadata_in_epub, preview_metadata_changes

User = get_user_model()


class UnifiedCoverSelectionContextTestCase(TestCase):
    """Test cover context gathering from all sources."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.client.login(username="testuser", password="testpass")

        # Create scan folder
        self.scan_folder = ScanFolder.objects.create(path="/test/scans", name="Test Scans")

        # Create book
        self.book = Book.objects.create(scan_folder=self.scan_folder, title="Test Book", author="Test Author")

        # Create final metadata
        self.final_metadata = FinalMetadata.objects.create(book=self.book, final_title="Test Book", final_author="Test Author", final_cover_path="")

        # Create data sources
        self.source_scan = DataSource.objects.get_or_create(name=DataSource.FILESCAN, defaults={"trust_level": 0.8})[0]
        self.source_google = DataSource.objects.get_or_create(name="Google Books", defaults={"trust_level": 0.7})[0]

    def test_cover_context_includes_original_cover(self):
        """Test that original EPUB internal cover is included."""
        # Create BookFile with internal cover
        book_file = BookFile.objects.create(
            book=self.book,
            file_path="/test/book.epub",
            file_format="epub",
            cover_path="/test/covers/original.jpg",
            cover_source_type="epub_internal",
            cover_width=1200,
            cover_height=1600,
            cover_quality_score=85,
        )

        response = self.client.get(reverse("books:book_metadata", kwargs={"pk": self.book.id}))
        self.assertEqual(response.status_code, 200)

        # Check context has all_covers
        all_covers = response.context.get("all_covers", [])
        self.assertGreater(len(all_covers), 0)

        # Find original cover
        original_cover = next((c for c in all_covers if c["source_type"] == "epub_internal"), None)
        self.assertIsNotNone(original_cover)
        self.assertEqual(original_cover["path"], "/test/covers/original.jpg")
        self.assertEqual(original_cover["source_label"], "EPUB Internal")
        self.assertEqual(original_cover["width"], 1200)
        self.assertEqual(original_cover["height"], 1600)
        self.assertEqual(original_cover["quality_score"], 85)
        self.assertFalse(original_cover["can_download"])  # Already local

    def test_cover_context_includes_uploaded_cover(self):
        """Test that manually uploaded cover is included."""
        book_file = BookFile.objects.create(
            book=self.book,
            file_path="/test/book.epub",
            file_format="epub",
            cover_path="/media/uploads/custom_cover.jpg",
            original_cover_path="/test/covers/original.jpg",  # Different from current
            cover_source_type="manual",
            cover_width=1500,
            cover_height=2000,
            cover_quality_score=95,
        )

        response = self.client.get(reverse("books:book_metadata", kwargs={"pk": self.book.id}))
        all_covers = response.context.get("all_covers", [])

        # Should have both original and uploaded
        uploaded_cover = next((c for c in all_covers if c["source_type"] == "manual"), None)
        self.assertIsNotNone(uploaded_cover)
        self.assertEqual(uploaded_cover["source_label"], "Manual Upload")
        self.assertEqual(uploaded_cover["source_badge_class"], "bg-primary")

    def test_cover_context_includes_api_covers(self):
        """Test that external API covers are included."""
        BookFile.objects.create(book=self.book, file_path="/test/book.epub", file_format="epub")

        # Create API covers
        cover1 = BookCover.objects.create(
            book=self.book, source=self.source_google, cover_path="https://books.google.com/cover1.jpg", width=800, height=1200, confidence=0.85, is_active=True
        )

        response = self.client.get(reverse("books:book_metadata", kwargs={"pk": self.book.id}))
        all_covers = response.context.get("all_covers", [])

        api_cover = next((c for c in all_covers if c["source_label"] == "Google Books"), None)
        self.assertIsNotNone(api_cover)
        self.assertEqual(api_cover["confidence"], 0.85)
        self.assertTrue(api_cover["can_download"])  # URL, not local

    def test_final_cover_is_marked(self):
        """Test that currently selected final cover is marked."""
        book_file = BookFile.objects.create(book=self.book, file_path="/test/book.epub", file_format="epub", cover_path="/test/covers/original.jpg")

        # Set as final cover
        self.final_metadata.final_cover_path = "/test/covers/original.jpg"
        self.final_metadata.save()

        response = self.client.get(reverse("books:book_metadata", kwargs={"pk": self.book.id}))
        all_covers = response.context.get("all_covers", [])

        final_cover = next((c for c in all_covers if c["is_final"]), None)
        self.assertIsNotNone(final_cover)
        self.assertEqual(final_cover["path"], "/test/covers/original.jpg")


class CoverSelectionPostTestCase(TestCase):
    """Test cover selection via POST (radio button)."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.client.login(username="testuser", password="testpass")

        self.scan_folder = ScanFolder.objects.create(path="/test/scans", name="Test")
        self.book = Book.objects.create(scan_folder=self.scan_folder)
        self.final_metadata = FinalMetadata.objects.create(book=self.book, final_title="Test", final_cover_path="")
        BookFile.objects.create(book=self.book, file_path="/test/book.epub", file_format="epub")

    def test_select_final_cover_via_radio(self):
        """Test selecting final cover via radio button."""
        post_data = {
            "action": "save",
            "final_cover_path": "/test/covers/selected.jpg",
            "final_title": "Test",
        }

        response = self.client.post(reverse("books:book_metadata_update", kwargs={"pk": self.book.id}), data=post_data)

        # Refresh from DB
        self.final_metadata.refresh_from_db()
        self.assertEqual(self.final_metadata.final_cover_path, "/test/covers/selected.jpg")

    def test_change_final_cover(self):
        """Test changing the final cover selection."""
        # Set initial cover
        self.final_metadata.final_cover_path = "/test/covers/old.jpg"
        self.final_metadata.save()

        # Change to new cover
        post_data = {
            "action": "save",
            "final_cover_path": "/test/covers/new.jpg",
            "final_title": "Test",
        }

        self.client.post(reverse("books:book_metadata_update", kwargs={"pk": self.book.id}), data=post_data)

        self.final_metadata.refresh_from_db()
        self.assertEqual(self.final_metadata.final_cover_path, "/test/covers/new.jpg")


class CoverDownloadTestCase(TestCase):
    """Test cover download via checkboxes."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.client.login(username="testuser", password="testpass")

        self.scan_folder = ScanFolder.objects.create(path="/test/scans", name="Test")
        self.book = Book.objects.create(scan_folder=self.scan_folder)
        self.final_metadata = FinalMetadata.objects.create(book=self.book, final_title="Test")
        BookFile.objects.create(book=self.book, file_path="/test/book.epub", file_format="epub")

        self.source = DataSource.objects.get_or_create(name="Google Books", defaults={"trust_level": 0.7})[0]

    @patch("books.views.metadata.BookMetadataUpdateView._download_covers")
    def test_download_multiple_covers(self, mock_download):
        """Test downloading multiple covers via checkboxes."""
        # Create API covers
        cover1 = BookCover.objects.create(book=self.book, source=self.source, cover_path="https://example.com/cover1.jpg", is_active=True)
        cover2 = BookCover.objects.create(book=self.book, source=self.source, cover_path="https://example.com/cover2.jpg", is_active=True)

        post_data = {
            "action": "save",
            "selected_covers": [str(cover1.id), str(cover2.id)],
            "final_title": "Test",
        }

        self.client.post(reverse("books:book_metadata_update", kwargs={"pk": self.book.id}), data=post_data)

        # Verify download was called
        mock_download.assert_called_once()
        args = mock_download.call_args[0]
        self.assertEqual(len(args[2]), 2)  # cover_urls list


class EPUBOrphanedImageDetectionTestCase(TestCase):
    """Test orphaned image detection in EPUB preview."""

    def setUp(self):
        """Create test EPUB with orphaned images."""
        self.test_dir = Path(tempfile.mkdtemp())
        self.epub_path = self.test_dir / "test.epub"

        # Create minimal EPUB structure
        self._create_test_epub_with_orphans()

        # Create book
        self.book = Book.objects.create(title="Test")
        FinalMetadata.objects.create(book=self.book, final_title="Test Book", final_author="Test Author")

    def tearDown(self):
        """Clean up test directory."""
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    def _create_test_epub_with_orphans(self):
        """Create EPUB with orphaned images."""
        with zipfile.ZipFile(self.epub_path, "w", zipfile.ZIP_DEFLATED) as epub:
            # mimetype
            epub.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)

            # container.xml
            container_xml = """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>"""
            epub.writestr("META-INF/container.xml", container_xml)

            # OPF with only ONE cover referenced
            opf_content = """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>Test Book</dc:title>
    <dc:creator>Test Author</dc:creator>
    <meta name="cover" content="cover-image"/>
  </metadata>
  <manifest>
    <item id="cover-image" href="images/cover.jpg" media-type="image/jpeg"/>
    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
  </manifest>
  <spine toc="ncx">
  </spine>
</package>"""
            epub.writestr("OEBPS/content.opf", opf_content)

            # Add referenced cover
            epub.writestr("OEBPS/images/cover.jpg", b"fake jpg data")

            # Add ORPHANED images (not in manifest)
            epub.writestr("OEBPS/images/old_cover1.jpg", b"orphan 1")
            epub.writestr("OEBPS/images/old_cover2.png", b"orphan 2")
            epub.writestr("OEBPS/images/old_cover3.gif", b"orphan 3")

            # Add NCX
            epub.writestr("OEBPS/toc.ncx", '<?xml version="1.0"?><ncx/>')

    def test_detect_orphaned_images_in_preview(self):
        """Test that preview detects orphaned images."""
        preview = preview_metadata_changes(self.epub_path, self.book)

        self.assertIsNotNone(preview.files_to_remove)
        self.assertEqual(len(preview.files_to_remove), 3)  # 3 orphaned images

        # Verify orphaned images are identified
        orphan_names = [Path(f).name for f in preview.files_to_remove]
        self.assertIn("old_cover1.jpg", orphan_names)
        self.assertIn("old_cover2.png", orphan_names)
        self.assertIn("old_cover3.gif", orphan_names)

        # Referenced cover should NOT be in orphans
        self.assertNotIn("cover.jpg", orphan_names)

    def test_preview_summary_includes_orphan_count(self):
        """Test that preview summary includes orphaned image count."""
        from books.utils.epub import generate_preview_summary

        preview = preview_metadata_changes(self.epub_path, self.book)
        summary = generate_preview_summary(preview)

        self.assertIn("orphaned_images_count", summary)
        self.assertEqual(summary["orphaned_images_count"], 3)


class EPUBImageCleanupTestCase(TransactionTestCase):
    """Test EPUB image cleanup functionality."""

    def setUp(self):
        """Create test EPUB."""
        self.test_dir = Path(tempfile.mkdtemp())
        self.epub_path = self.test_dir / "test.epub"
        self._create_test_epub_with_orphans()

        self.book = Book.objects.create(title="Test")
        FinalMetadata.objects.create(book=self.book, final_title="Test Book", final_author="Test Author")

    def tearDown(self):
        """Clean up."""
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    def _create_test_epub_with_orphans(self):
        """Create EPUB with orphaned images."""
        with zipfile.ZipFile(self.epub_path, "w", zipfile.ZIP_DEFLATED) as epub:
            epub.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)

            container_xml = """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>"""
            epub.writestr("META-INF/container.xml", container_xml)

            opf_content = """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>Test Book</dc:title>
  </metadata>
  <manifest>
    <item id="cover-image" href="images/cover.jpg" media-type="image/jpeg"/>
    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
  </manifest>
  <spine toc="ncx"></spine>
</package>"""
            epub.writestr("OEBPS/content.opf", opf_content)
            epub.writestr("OEBPS/images/cover.jpg", b"cover data")
            epub.writestr("OEBPS/images/orphan1.jpg", b"orphan 1")
            epub.writestr("OEBPS/images/orphan2.png", b"orphan 2")
            epub.writestr("OEBPS/toc.ncx", '<?xml version="1.0"?><ncx/>')

    def test_embed_metadata_without_cleanup(self):
        """Test embedding metadata keeps orphaned images."""
        success = embed_metadata_in_epub(self.epub_path, self.book, cover_path=None, remove_unused_images=False)
        self.assertTrue(success)

        # Verify orphans still exist
        with zipfile.ZipFile(self.epub_path, "r") as epub:
            files = epub.namelist()
            self.assertIn("OEBPS/images/orphan1.jpg", files)
            self.assertIn("OEBPS/images/orphan2.png", files)

    def test_embed_metadata_with_cleanup(self):
        """Test embedding metadata removes orphaned images."""
        success = embed_metadata_in_epub(self.epub_path, self.book, cover_path=None, remove_unused_images=True)  # Enable cleanup
        self.assertTrue(success)

        # Verify orphans are removed
        with zipfile.ZipFile(self.epub_path, "r") as epub:
            files = epub.namelist()
            self.assertNotIn("OEBPS/images/orphan1.jpg", files)
            self.assertNotIn("OEBPS/images/orphan2.png", files)

            # Referenced cover should still exist
            self.assertIn("OEBPS/images/cover.jpg", files)

    def test_embed_new_cover_with_cleanup(self):
        """Test embedding new cover and removing old ones."""
        # Create new cover file
        new_cover_path = self.test_dir / "new_cover.jpg"
        new_cover_path.write_bytes(b"new cover data")

        success = embed_metadata_in_epub(self.epub_path, self.book, cover_path=new_cover_path, remove_unused_images=True)
        self.assertTrue(success)

        with zipfile.ZipFile(self.epub_path, "r") as epub:
            files = epub.namelist()

            # Old orphans should be gone
            self.assertNotIn("OEBPS/images/orphan1.jpg", files)
            self.assertNotIn("OEBPS/images/orphan2.png", files)

            # New cover should exist
            # (embedded as images/cover.jpg or images/cover.{ext})
            cover_files = [f for f in files if "images/cover" in f and f.endswith(".jpg")]
            self.assertGreater(len(cover_files), 0)


class BatchRenamerIntegrationTestCase(TransactionTestCase):
    """Test complete workflow with BatchRenamer."""

    def setUp(self):
        """Set up test environment."""
        self.test_dir = Path(tempfile.mkdtemp())
        self.epub_path = self.test_dir / "test.epub"
        self._create_test_epub()

        self.scan_folder = ScanFolder.objects.create(path=str(self.test_dir), name="Test Scans")

        self.book = Book.objects.create(scan_folder=self.scan_folder, title="Test Book")

        BookFile.objects.create(book=self.book, file_path=str(self.epub_path), file_format="epub", file_name="test.epub")

        self.final_metadata = FinalMetadata.objects.create(book=self.book, final_title="Test Book", final_author="Test Author", final_cover_path="")

    def tearDown(self):
        """Clean up."""
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    def _create_test_epub(self):
        """Create test EPUB."""
        with zipfile.ZipFile(self.epub_path, "w") as epub:
            epub.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
            epub.writestr(
                "META-INF/container.xml",
                """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>""",
            )
            epub.writestr(
                "OEBPS/content.opf",
                """<?xml version="1.0"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>Old Title</dc:title>
  </metadata>
  <manifest>
    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
  </manifest>
  <spine toc="ncx"></spine>
</package>""",
            )
            epub.writestr("OEBPS/toc.ncx", '<?xml version="1.0"?><ncx/>')

    def test_batch_renamer_with_cleanup_flag(self):
        """Test BatchRenamer passes cleanup flag correctly."""
        # Create renamer with cleanup enabled
        renamer = BatchRenamer(dry_run=False, remove_unused_images=True)

        self.assertTrue(renamer.remove_unused_images)

    def test_batch_renamer_without_cleanup_flag(self):
        """Test BatchRenamer without cleanup."""
        renamer = BatchRenamer(dry_run=False, remove_unused_images=False)

        self.assertFalse(renamer.remove_unused_images)


class WorkflowIntegrationTestCase(TestCase):
    """Test complete end-to-end workflow."""

    def setUp(self):
        """Set up complete test environment."""
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.client.login(username="testuser", password="testpass")

        self.scan_folder = ScanFolder.objects.create(path="/test", name="Test")
        self.book = Book.objects.create(scan_folder=self.scan_folder)
        self.final_metadata = FinalMetadata.objects.create(book=self.book, final_title="Test", final_cover_path="")
        BookFile.objects.create(book=self.book, file_path="/test/book.epub", file_format="epub")

        self.source = DataSource.objects.get_or_create(name="Google Books", defaults={"trust_level": 0.7})[0]

    def test_complete_workflow_steps(self):
        """Test complete workflow: select, download, save."""
        # Step 1: User views metadata page
        response = self.client.get(reverse("books:book_metadata", kwargs={"pk": self.book.id}))
        self.assertEqual(response.status_code, 200)
        self.assertIn("all_covers", response.context)

        # Step 2: User selects final cover and downloads others
        api_cover = BookCover.objects.create(book=self.book, source=self.source, cover_path="https://example.com/cover.jpg", is_active=True)

        post_data = {
            "action": "save",
            "final_cover_path": "/test/covers/selected.jpg",
            "selected_covers": [str(api_cover.id)],
            "final_title": "Test",
        }

        with patch("books.views.metadata.BookMetadataUpdateView._download_covers"):
            response = self.client.post(reverse("books:book_metadata_update", kwargs={"pk": self.book.id}), data=post_data)

        # Step 3: Verify final_cover_path saved
        self.final_metadata.refresh_from_db()
        self.assertEqual(self.final_metadata.final_cover_path, "/test/covers/selected.jpg")

    def test_workflow_with_cleanup_checkbox(self):
        """Test workflow includes cleanup option."""
        post_data = {
            "action": "save",
            "final_cover_path": "/test/covers/selected.jpg",
            "remove_unused_epub_images": "true",  # Cleanup enabled
            "final_title": "Test",
        }

        response = self.client.post(reverse("books:book_metadata_update", kwargs={"pk": self.book.id}), data=post_data)

        # Verify saved successfully
        self.final_metadata.refresh_from_db()
        self.assertEqual(self.final_metadata.final_cover_path, "/test/covers/selected.jpg")


class AJAXPreviewTestCase(TestCase):
    """Test AJAX preview endpoint with orphan detection."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.client.login(username="testuser", password="testpass")

        self.test_dir = Path(tempfile.mkdtemp())
        self.epub_path = self.test_dir / "test.epub"
        self._create_test_epub()

        self.scan_folder = ScanFolder.objects.create(path=str(self.test_dir), name="Test")
        self.book = Book.objects.create(scan_folder=self.scan_folder)

        BookFile.objects.create(book=self.book, file_path=str(self.epub_path), file_format="epub")

        FinalMetadata.objects.create(book=self.book, final_title="Test", final_cover_path="")

    def tearDown(self):
        """Clean up."""
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    def _create_test_epub(self):
        """Create test EPUB with orphans."""
        with zipfile.ZipFile(self.epub_path, "w") as epub:
            epub.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
            epub.writestr(
                "META-INF/container.xml",
                """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>""",
            )
            epub.writestr(
                "OEBPS/content.opf",
                """<?xml version="1.0"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Test</dc:title></metadata>
  <manifest>
    <item id="cover" href="images/cover.jpg" media-type="image/jpeg"/>
    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
  </manifest>
  <spine toc="ncx"></spine>
</package>""",
            )
            epub.writestr("OEBPS/images/cover.jpg", b"cover")
            epub.writestr("OEBPS/images/orphan.jpg", b"orphan")
            epub.writestr("OEBPS/toc.ncx", '<?xml version="1.0"?><ncx/>')

    def test_ajax_preview_returns_orphan_count(self):
        """Test AJAX preview includes orphaned_images_count."""
        response = self.client.post(reverse("books:ajax_preview_epub_changes", kwargs={"book_id": self.book.id}))

        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertTrue(data["success"])
        self.assertIn("orphaned_images_count", data)
        self.assertEqual(data["orphaned_images_count"], 1)  # 1 orphan

    def test_ajax_preview_returns_files_to_remove(self):
        """Test AJAX preview includes files_to_remove list."""
        response = self.client.post(reverse("books:ajax_preview_epub_changes", kwargs={"book_id": self.book.id}))

        data = response.json()
        self.assertIn("files_to_remove", data)
        self.assertEqual(len(data["files_to_remove"]), 1)
        self.assertIn("orphan.jpg", data["files_to_remove"][0])
