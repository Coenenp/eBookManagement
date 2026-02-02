"""
Tests for rename preview with collision resolution.
"""

import os
import tempfile
from pathlib import Path

from django.test import TestCase

from books.models import Book, BookFile, BookTitle, DataSource, FinalMetadata, ScanFolder
from books.utils.batch_renamer import BatchRenamer


class RenamePreviewCollisionTests(TestCase):
    """Test cases for rename preview with collision handling."""

    def setUp(self):
        """Set up test environment."""
        self.test_dir = tempfile.mkdtemp()

        # Create scan folder
        self.scan_folder = ScanFolder.objects.create(path=self.test_dir, name="Test Folder")

        # Create first book
        self.book1_file = os.path.join(self.test_dir, "book1.epub")
        Path(self.book1_file).touch()

        self.book1 = Book.objects.create(scan_folder=self.scan_folder)

        source = DataSource.objects.get_or_create(name=DataSource.INITIAL_SCAN)[0]
        BookTitle.objects.create(
            book=self.book1,
            title="Test Book",
            source=source,
            confidence=1.0,
            is_active=True,
        )

        BookFile.objects.create(
            book=self.book1,
            file_path=self.book1_file,
            file_format="epub",
            file_size=1024000,
        )

        FinalMetadata.objects.create(book=self.book1, final_title="Test Book", final_author="Test Author", is_reviewed=True)

        # Create second book
        self.book2_file = os.path.join(self.test_dir, "book2.epub")
        Path(self.book2_file).touch()

        self.book2 = Book.objects.create(scan_folder=self.scan_folder)

        BookTitle.objects.create(
            book=self.book2,
            title="Test Book",  # Same title - will cause collision
            source=source,
            confidence=1.0,
            is_active=True,
        )

        BookFile.objects.create(
            book=self.book2,
            file_path=self.book2_file,
            file_format="epub",
            file_size=1024000,
        )

        FinalMetadata.objects.create(book=self.book2, final_title="Test Book", final_author="Test Author", is_reviewed=True)

    def tearDown(self):
        """Clean up test environment."""
        import shutil

        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_preview_shows_collision_suffix(self):
        """Test that preview shows collision suffix when target file exists."""
        # Create target file that will cause collision for book2
        target_path = os.path.join(self.test_dir, "Test Book.epub")
        Path(target_path).touch()

        # Create renamer with dry_run=True (preview mode)
        renamer = BatchRenamer(dry_run=True)
        renamer.add_books([self.book2], folder_pattern="", filename_pattern="${title}.${ext}")

        # Get preview
        previews = renamer.preview_operations()

        self.assertEqual(len(previews), 1)
        preview = previews[0]

        # Preview should show the collision-resolved path
        self.assertIn(" (2)", preview["target_path"])
        self.assertTrue(preview["target_path"].endswith("Test Book (2).epub"))

    def test_preview_no_suffix_when_no_collision(self):
        """Test that preview shows no suffix when no collision."""
        # Don't create target file - no collision

        renamer = BatchRenamer(dry_run=True)
        renamer.add_books([self.book1], folder_pattern="", filename_pattern="${title}.${ext}")

        previews = renamer.preview_operations()

        self.assertEqual(len(previews), 1)
        preview = previews[0]

        # Preview should NOT have collision suffix
        self.assertNotIn(" (2)", preview["target_path"])
        self.assertTrue(preview["target_path"].endswith("Test Book.epub"))

    def test_preview_multiple_books_with_collisions(self):
        """Test preview with multiple books showing collision suffixes."""
        # Create target files
        Path(os.path.join(self.test_dir, "Test Book.epub")).touch()
        Path(os.path.join(self.test_dir, "Test Book (2).epub")).touch()

        # Create third book
        book3_file = os.path.join(self.test_dir, "book3.epub")
        Path(book3_file).touch()

        book3 = Book.objects.create(scan_folder=self.scan_folder)

        source = DataSource.objects.get_or_create(name=DataSource.INITIAL_SCAN)[0]
        BookTitle.objects.create(
            book=book3,
            title="Test Book",
            source=source,
            confidence=1.0,
            is_active=True,
        )

        BookFile.objects.create(
            book=book3,
            file_path=book3_file,
            file_format="epub",
            file_size=1024000,
        )

        FinalMetadata.objects.create(book=book3, final_title="Test Book", final_author="Test Author", is_reviewed=True)

        # Preview all books separately to show how collision detection works
        renamer = BatchRenamer(dry_run=True)
        renamer.add_books([self.book2, book3], folder_pattern="", filename_pattern="${title}.${ext}")

        previews = renamer.preview_operations()

        # Should have 2 operations
        self.assertEqual(len(previews), 2)

        # Both books will independently detect existing files and both get (3)
        # This is correct - each preview is independent and checks disk state
        for preview in previews:
            target_name = Path(preview["target_path"]).name
            # Both will see Test Book.epub and Test Book (2).epub exist, so both get (3)
            self.assertEqual(target_name, "Test Book (3).epub")

    def test_preview_with_companion_files(self):
        """Test that companion files in preview get same suffix as main file."""
        # Create target that will cause collision
        target_path = os.path.join(self.test_dir, "Test Book.epub")
        Path(target_path).touch()

        # Create companion files
        cover_path = os.path.join(self.test_dir, "book1.jpg")
        opf_path = os.path.join(self.test_dir, "book1.opf")
        Path(cover_path).touch()
        Path(opf_path).touch()

        # Update book file to point to companion files
        book_file = self.book1.files.first()
        book_file.cover_path = cover_path
        book_file.opf_path = opf_path
        book_file.save()

        renamer = BatchRenamer(dry_run=True)
        renamer.add_books([self.book1], folder_pattern="", filename_pattern="${title}.${ext}", include_companions=True)

        previews = renamer.preview_operations()

        # Should have main file + companions
        self.assertGreater(len(previews), 1)

        # All should have (2) suffix
        for preview in previews:
            target_name = Path(preview["target_path"]).name
            self.assertIn(" (2)", target_name)
