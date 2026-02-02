"""
Tests for batch renamer collision handling.
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.test import TestCase

from books.models import Book, FinalMetadata, ScanFolder
from books.utils.batch_renamer import BatchRenamer


class BatchRenamerCollisionTests(TestCase):
    """Test cases for batch renamer with collision handling."""

    def setUp(self):
        """Set up test environment."""
        self.test_dir = tempfile.mkdtemp()

        # Create a scan folder
        self.scan_folder = ScanFolder.objects.create(path=self.test_dir, name="Test Folder")

        # Create a test book file
        self.book_file_path = os.path.join(self.test_dir, "original.epub")
        Path(self.book_file_path).touch()

        # Create a book
        self.book = Book.objects.create(scan_folder=self.scan_folder)

        # Create BookTitle for the book
        from books.models import BookTitle, DataSource

        source = DataSource.objects.get_or_create(name=DataSource.INITIAL_SCAN)[0]
        BookTitle.objects.create(
            book=self.book,
            title="Test Book",
            source=source,
            confidence=1.0,
            is_active=True,
        )

        # Create BookFile for the book
        from books.models import BookFile

        BookFile.objects.create(
            book=self.book,
            file_path=self.book_file_path,
            file_format="epub",
            file_size=1024000,
        )

        # Create final metadata
        self.metadata = FinalMetadata.objects.create(book=self.book, final_title="Test Book", final_author="Test Author", is_reviewed=True)

    def tearDown(self):
        """Clean up test environment."""
        import shutil

        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_collision_adds_suffix_to_main_file(self):
        """Test that collision adds (2) suffix to main file."""
        # Create target file that will cause collision
        target_path = os.path.join(self.test_dir, "Test Book.epub")
        Path(target_path).touch()

        # Create renamer and add book
        renamer = BatchRenamer(dry_run=True)
        renamer.add_book(self.book, folder_pattern="", filename_pattern="${title}.${ext}", include_companions=False)

        # Check that the operation has the collision-resolved path
        self.assertEqual(len(renamer.operations), 1)
        op = renamer.operations[0]

        # Should have (2) suffix
        expected_target = os.path.join(self.test_dir, "Test Book (2).epub")
        self.assertEqual(str(op.target_path), expected_target)

    def test_collision_applies_same_suffix_to_companions(self):
        """Test that companion files get the same collision suffix as main file."""
        # Create target file that will cause collision
        target_path = os.path.join(self.test_dir, "Test Book.epub")
        Path(target_path).touch()

        # Create companion files for the book
        cover_path = os.path.join(self.test_dir, "original.jpg")
        opf_path = os.path.join(self.test_dir, "original.opf")
        Path(cover_path).touch()
        Path(opf_path).touch()

        # Create renamer and add book
        renamer = BatchRenamer(dry_run=True)
        renamer.add_book(self.book, folder_pattern="", filename_pattern="${title}.${ext}", include_companions=True)

        # Should have main file + 2 companion files
        self.assertEqual(len(renamer.operations), 3)

        # All should have (2) suffix
        for op in renamer.operations:
            target_name = os.path.basename(str(op.target_path))
            self.assertIn(" (2)", target_name)

    def test_no_collision_no_suffix(self):
        """Test that no suffix is added when there's no collision."""
        # Don't create target file - no collision

        # Create renamer and add book
        renamer = BatchRenamer(dry_run=True)
        renamer.add_book(self.book, folder_pattern="", filename_pattern="${title}.${ext}", include_companions=False)

        # Check that the operation has the normal path (no suffix)
        self.assertEqual(len(renamer.operations), 1)
        op = renamer.operations[0]

        # Should NOT have (2) suffix
        expected_target = os.path.join(self.test_dir, "Test Book.epub")
        self.assertEqual(str(op.target_path), expected_target)
        self.assertNotIn(" (2)", str(op.target_path))

    def test_multiple_collisions_increments_suffix(self):
        """Test that multiple collisions increment the suffix number."""
        # Create multiple existing files
        Path(os.path.join(self.test_dir, "Test Book.epub")).touch()
        Path(os.path.join(self.test_dir, "Test Book (2).epub")).touch()
        Path(os.path.join(self.test_dir, "Test Book (3).epub")).touch()

        # Create renamer and add book
        renamer = BatchRenamer(dry_run=True)
        renamer.add_book(self.book, folder_pattern="", filename_pattern="${title}.${ext}", include_companions=False)

        # Should get (4) suffix
        self.assertEqual(len(renamer.operations), 1)
        op = renamer.operations[0]

        expected_target = os.path.join(self.test_dir, "Test Book (4).epub")
        self.assertEqual(str(op.target_path), expected_target)

    @patch("books.utils.batch_renamer.shutil.move")
    def test_collision_handling_in_execution(self, mock_move):
        """Test that collision handling works during actual execution."""
        # Create target file that will cause collision
        target_path = os.path.join(self.test_dir, "Test Book.epub")
        Path(target_path).touch()

        # Create renamer and execute
        renamer = BatchRenamer(dry_run=False)
        renamer.add_book(self.book, folder_pattern="", filename_pattern="${title}.${ext}", include_companions=False)

        # Execute operations
        result = renamer.execute_operations()

        # Should have called move with collision-resolved path
        expected_target = os.path.join(self.test_dir, "Test Book (2).epub")
        mock_move.assert_called_once_with(self.book_file_path, expected_target)

        # Should report success
        self.assertEqual(result.successful, 1)
        self.assertEqual(result.failed, 0)
