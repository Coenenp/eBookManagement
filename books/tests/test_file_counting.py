"""
Test cases for scanning file counting functionality.
"""

import os
import tempfile
from pathlib import Path

from django.test import TestCase

from books.scanner.folder import _collect_files


class FileCountingTests(TestCase):
    """Test cases for file counting and collection logic."""

    def test_file_collection_and_counting(self):
        """Test that file collection and counting works correctly."""
        # Create a temporary directory with test files
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create some test ebook files
            test_files = [
                "book1.epub",
                "book2.mobi",
                "book3.pdf",
                "book4.azw3",
                "book5.cbz",
                # Matching OPF files (should not be counted separately)
                "book1.opf",
                "book2.opf",
                # Standalone OPF files (should be counted)
                "standalone1.opf",
                "standalone2.opf",
                # Cover files
                "book1_cover.jpg",
                "book2_cover.png",
                # Non-relevant files
                "readme.txt",
                "data.xml"
            ]

            for filename in test_files:
                file_path = Path(temp_dir) / filename
                file_path.write_text("test content")

            # Test file collection
            ebook_extensions = {'.epub', '.mobi', '.pdf', '.azw', '.azw3', '.cbr', '.cbz'}
            cover_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}

            ebook_files, cover_files, opf_files = _collect_files(temp_dir, ebook_extensions, cover_extensions)

            # Verify basic file collection
            self.assertEqual(len(ebook_files), 5, "Should find 5 ebook files")
            self.assertEqual(len(cover_files), 2, "Should find 2 cover files")
            self.assertEqual(len(opf_files), 4, "Should find 4 OPF files")

            # Count standalone OPF files
            standalone_opf_count = 0
            standalone_opf_files = []
            for opf_path in opf_files:
                opf_base = os.path.splitext(opf_path)[0]
                has_matching_ebook = any(
                    os.path.splitext(ebook_path)[0] == opf_base
                    for ebook_path in ebook_files
                )
                if not has_matching_ebook:
                    standalone_opf_count += 1
                    standalone_opf_files.append(os.path.basename(opf_path))

            total_files = len(ebook_files) + standalone_opf_count

            # Verify counting logic
            self.assertEqual(standalone_opf_count, 2, "Should find 2 standalone OPF files")
            self.assertIn("standalone1.opf", standalone_opf_files)
            self.assertIn("standalone2.opf", standalone_opf_files)

            expected_total = 5 + 2  # 5 ebooks + 2 standalone OPFs
            self.assertEqual(total_files, expected_total, f"Total files to process should be {expected_total}")

    def test_empty_directory(self):
        """Test file collection in empty directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            ebook_extensions = {'.epub', '.mobi', '.pdf', '.azw', '.azw3', '.cbr', '.cbz'}
            cover_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}

            ebook_files, cover_files, opf_files = _collect_files(temp_dir, ebook_extensions, cover_extensions)

            self.assertEqual(len(ebook_files), 0, "Empty directory should have no ebook files")
            self.assertEqual(len(cover_files), 0, "Empty directory should have no cover files")
            self.assertEqual(len(opf_files), 0, "Empty directory should have no OPF files")

    def test_only_irrelevant_files(self):
        """Test file collection with only irrelevant files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create only non-ebook files
            irrelevant_files = ["readme.txt", "data.xml", "image.jpg", "document.doc", "book_cover.jpg"]

            for filename in irrelevant_files:
                file_path = Path(temp_dir) / filename
                file_path.write_text("test content")

            ebook_extensions = {'.epub', '.mobi', '.pdf', '.azw', '.azw3', '.cbr', '.cbz'}
            cover_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}

            ebook_files, cover_files, opf_files = _collect_files(temp_dir, ebook_extensions, cover_extensions)

            self.assertEqual(len(ebook_files), 0, "Should find no ebook files")
            self.assertEqual(len(cover_files), 1, "Should find 1 cover file (book_cover.jpg)")
            self.assertEqual(len(opf_files), 0, "Should find no OPF files")

    def test_nested_directory_structure(self):
        """Test file collection in nested directory structure."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create nested directory structure
            subdir1 = Path(temp_dir) / "subdir1"
            subdir2 = Path(temp_dir) / "subdir2"
            subdir1.mkdir()
            subdir2.mkdir()

            # Create files in different directories
            (Path(temp_dir) / "book1.epub").write_text("content")
            (subdir1 / "book2.mobi").write_text("content")
            (subdir2 / "book3.pdf").write_text("content")

            ebook_extensions = {'.epub', '.mobi', '.pdf', '.azw', '.azw3', '.cbr', '.cbz'}
            cover_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}

            ebook_files, cover_files, opf_files = _collect_files(temp_dir, ebook_extensions, cover_extensions)

            self.assertEqual(len(ebook_files), 3, "Should find all 3 ebook files in nested structure")

            # Verify files from all directories are included
            basenames = [os.path.basename(f) for f in ebook_files]
            self.assertIn("book1.epub", basenames)
            self.assertIn("book2.mobi", basenames)
            self.assertIn("book3.pdf", basenames)

    def test_case_insensitive_extensions(self):
        """Test that file extensions are handled case-insensitively."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create files with mixed case extensions
            test_files = ["book1.EPUB", "book2.Mobi", "book3.PDF", "COVER.JPG"]

            for filename in test_files:
                file_path = Path(temp_dir) / filename
                file_path.write_text("test content")

            ebook_extensions = {'.epub', '.mobi', '.pdf', '.azw', '.azw3', '.cbr', '.cbz'}
            cover_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}

            ebook_files, cover_files, opf_files = _collect_files(temp_dir, ebook_extensions, cover_extensions)

            self.assertEqual(len(ebook_files), 3, "Should find all ebooks regardless of case")
            self.assertEqual(len(cover_files), 1, "Should find cover file regardless of case")

    def test_special_characters_in_filenames(self):
        """Test file collection with special characters and spaces in filenames."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create files with special characters and spaces
            test_files = [
                "book with spaces.epub",
                "book-with-dashes.mobi",
                "book_with_underscores.pdf",
                "book[with]brackets.azw3",
                "book(with)parentheses.cbz",
                "book&with&ampersands.epub",
                "book with spaces cover.jpg"
            ]

            for filename in test_files:
                file_path = Path(temp_dir) / filename
                file_path.write_text("test content")

            ebook_extensions = {'.epub', '.mobi', '.pdf', '.azw', '.azw3', '.cbr', '.cbz'}
            cover_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}

            ebook_files, cover_files, opf_files = _collect_files(temp_dir, ebook_extensions, cover_extensions)

            self.assertEqual(len(ebook_files), 6, "Should find all ebooks with special characters")
            self.assertEqual(len(cover_files), 1, "Should find cover file with special characters")

    def test_mixed_opf_scenarios(self):
        """Test various OPF file scenarios."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create files with various OPF relationships
            test_files = [
                "book1.epub",
                "book1.opf",  # Matching OPF
                "book2.mobi",
                "book2.opf",  # Matching OPF
                "orphan1.opf",  # Standalone OPF
                "orphan2.opf",  # Standalone OPF
                "metadata.opf"  # Standalone OPF with different name pattern
            ]

            for filename in test_files:
                file_path = Path(temp_dir) / filename
                file_path.write_text("test content")

            ebook_extensions = {'.epub', '.mobi', '.pdf', '.azw', '.azw3', '.cbr', '.cbz'}
            cover_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}

            ebook_files, cover_files, opf_files = _collect_files(temp_dir, ebook_extensions, cover_extensions)

            self.assertEqual(len(ebook_files), 2, "Should find 2 ebook files")
            self.assertEqual(len(opf_files), 5, "Should find 5 OPF files")

            # Test standalone OPF counting logic
            standalone_opf_count = 0
            for opf_path in opf_files:
                opf_base = os.path.splitext(opf_path)[0]
                has_matching_ebook = any(
                    os.path.splitext(ebook_path)[0] == opf_base
                    for ebook_path in ebook_files
                )
                if not has_matching_ebook:
                    standalone_opf_count += 1

            self.assertEqual(standalone_opf_count, 3, "Should find 3 standalone OPF files")
