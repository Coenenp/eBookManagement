"""
Tests for file collision handling utilities.
"""

import os
import tempfile
from pathlib import Path

from django.test import TestCase

from books.utils.file_collision import (
    apply_suffix_to_path,
    get_collision_suffix,
    resolve_collision,
)


class FileCollisionTests(TestCase):
    """Test cases for file collision resolution."""

    def setUp(self):
        """Set up test environment."""
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up test environment."""
        import shutil

        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_resolve_collision_no_collision(self):
        """Test that resolve_collision returns original path when no collision."""
        target_path = os.path.join(self.test_dir, "book.epub")
        result = resolve_collision(target_path)
        self.assertEqual(result, target_path)

    def test_resolve_collision_with_existing_file(self):
        """Test that resolve_collision adds (2) when file exists."""
        # Create existing file
        existing_path = os.path.join(self.test_dir, "book.epub")
        Path(existing_path).touch()

        # Try to resolve collision
        result = resolve_collision(existing_path)
        expected = os.path.join(self.test_dir, "book (2).epub")
        self.assertEqual(result, expected)

    def test_resolve_collision_multiple_collisions(self):
        """Test that resolve_collision handles multiple existing files."""
        # Create existing files
        Path(os.path.join(self.test_dir, "book.epub")).touch()
        Path(os.path.join(self.test_dir, "book (2).epub")).touch()
        Path(os.path.join(self.test_dir, "book (3).epub")).touch()

        # Try to resolve collision
        target_path = os.path.join(self.test_dir, "book.epub")
        result = resolve_collision(target_path)
        expected = os.path.join(self.test_dir, "book (4).epub")
        self.assertEqual(result, expected)

    def test_resolve_collision_preserves_extension(self):
        """Test that resolve_collision preserves file extension."""
        # Create existing file
        existing_path = os.path.join(self.test_dir, "cover.jpg")
        Path(existing_path).touch()

        # Try to resolve collision
        result = resolve_collision(existing_path)
        expected = os.path.join(self.test_dir, "cover (2).jpg")
        self.assertEqual(result, expected)
        self.assertTrue(result.endswith(".jpg"))

    def test_get_collision_suffix_no_collision(self):
        """Test get_collision_suffix returns None when no collision."""
        original = os.path.join(self.test_dir, "book.epub")
        resolved = os.path.join(self.test_dir, "book.epub")
        result = get_collision_suffix(original, resolved)
        self.assertIsNone(result)

    def test_get_collision_suffix_with_collision(self):
        """Test get_collision_suffix extracts suffix correctly."""
        original = os.path.join(self.test_dir, "book.epub")
        resolved = os.path.join(self.test_dir, "book (2).epub")
        result = get_collision_suffix(original, resolved)
        self.assertEqual(result, " (2)")

    def test_get_collision_suffix_higher_number(self):
        """Test get_collision_suffix works with higher numbers."""
        original = os.path.join(self.test_dir, "book.epub")
        resolved = os.path.join(self.test_dir, "book (42).epub")
        result = get_collision_suffix(original, resolved)
        self.assertEqual(result, " (42)")

    def test_apply_suffix_to_path_no_suffix(self):
        """Test apply_suffix_to_path with None suffix."""
        path = os.path.join(self.test_dir, "cover.jpg")
        result = apply_suffix_to_path(path, None)
        self.assertEqual(result, path)

    def test_apply_suffix_to_path_with_suffix(self):
        """Test apply_suffix_to_path applies suffix correctly."""
        path = os.path.join(self.test_dir, "cover.jpg")
        result = apply_suffix_to_path(path, " (2)")
        expected = os.path.join(self.test_dir, "cover (2).jpg")
        self.assertEqual(result, expected)

    def test_apply_suffix_to_path_preserves_extension(self):
        """Test apply_suffix_to_path preserves extension."""
        path = os.path.join(self.test_dir, "metadata.opf")
        result = apply_suffix_to_path(path, " (3)")
        expected = os.path.join(self.test_dir, "metadata (3).opf")
        self.assertEqual(result, expected)
        self.assertTrue(result.endswith(".opf"))

    def test_apply_suffix_to_path_maintains_directory(self):
        """Test apply_suffix_to_path maintains directory structure."""
        subdir = os.path.join(self.test_dir, "books", "series")
        os.makedirs(subdir, exist_ok=True)
        path = os.path.join(subdir, "book.epub")
        result = apply_suffix_to_path(path, " (2)")
        expected = os.path.join(subdir, "book (2).epub")
        self.assertEqual(result, expected)

    def test_companion_files_get_same_suffix(self):
        """Test that companion files can get the same suffix as main file."""
        # Create main file
        main_path = os.path.join(self.test_dir, "book.epub")
        Path(main_path).touch()

        # Resolve collision for main file
        resolved_main = resolve_collision(main_path)
        suffix = get_collision_suffix(main_path, resolved_main)

        # Apply same suffix to companion files
        cover_path = os.path.join(self.test_dir, "book.jpg")
        opf_path = os.path.join(self.test_dir, "book.opf")

        resolved_cover = apply_suffix_to_path(cover_path, suffix)
        resolved_opf = apply_suffix_to_path(opf_path, suffix)

        # All should have the same suffix
        self.assertEqual(suffix, " (2)")
        self.assertEqual(resolved_cover, os.path.join(self.test_dir, "book (2).jpg"))
        self.assertEqual(resolved_opf, os.path.join(self.test_dir, "book (2).opf"))

    def test_resolve_collision_max_attempts(self):
        """Test that resolve_collision raises error after max attempts."""
        # Create files for all attempts (this would be very slow, so we test with small max)
        # Note: This test is more conceptual - in reality we'd mock the exists check
        with self.assertRaises(RuntimeError):
            # Create a path and try to resolve with max_attempts=0
            target_path = os.path.join(self.test_dir, "book.epub")
            Path(target_path).touch()
            resolve_collision(target_path, max_attempts=0)
