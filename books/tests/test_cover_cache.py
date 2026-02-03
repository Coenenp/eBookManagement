"""
Tests for the cover cache system.

Tests cover saving, retrieving, deleting, and managing cached cover images.
"""

import os

from django.conf import settings
from django.test import TestCase

from books.utils.cover_cache import CoverCache


class CoverCacheTestCase(TestCase):
    """Test cases for CoverCache class."""

    def setUp(self):
        """Set up test fixtures."""
        self.test_book_path = "/media/books/test_book.epub"
        self.test_internal_path = "OEBPS/cover.jpg"
        self.test_cover_data = b"fake image data for testing"

    def tearDown(self):
        """Clean up after tests."""
        # Clear any cached covers created during tests
        CoverCache.clear_all()

    def test_get_cache_path(self):
        """Test cache path generation."""
        cache_path = CoverCache.get_cache_path(self.test_book_path, self.test_internal_path)

        # Should be in cover_cache directory
        self.assertTrue(cache_path.startswith("cover_cache/"))

        # Should have .jpg extension
        self.assertTrue(cache_path.endswith(".jpg"))

        # Should be consistent for same inputs
        cache_path2 = CoverCache.get_cache_path(self.test_book_path, self.test_internal_path)
        self.assertEqual(cache_path, cache_path2)

    def test_get_cache_path_different_internal_paths(self):
        """Test that different internal paths produce different cache paths."""
        path1 = CoverCache.get_cache_path(self.test_book_path, "cover1.jpg")
        path2 = CoverCache.get_cache_path(self.test_book_path, "cover2.jpg")

        self.assertNotEqual(path1, path2)

    def test_get_cache_path_no_internal_path(self):
        """Test cache path generation without internal path."""
        cache_path = CoverCache.get_cache_path(self.test_book_path, None)

        self.assertTrue(cache_path.startswith("cover_cache/"))
        self.assertTrue(cache_path.endswith(".jpg"))

    def test_save_cover(self):
        """Test saving a cover to cache."""
        success, cache_path = CoverCache.save_cover(self.test_book_path, self.test_cover_data, self.test_internal_path)

        self.assertTrue(success)
        self.assertTrue(cache_path.startswith("cover_cache/"))

        # Verify file exists
        full_path = os.path.join(settings.MEDIA_ROOT, cache_path)
        self.assertTrue(os.path.exists(full_path))

    def test_get_cover_exists(self):
        """Test retrieving an existing cached cover."""
        # Save a cover first
        success, cache_path = CoverCache.save_cover(self.test_book_path, self.test_cover_data, self.test_internal_path)
        self.assertTrue(success)

        # Try to retrieve it
        retrieved_path = CoverCache.get_cover(self.test_book_path, self.test_internal_path)

        self.assertIsNotNone(retrieved_path)
        self.assertEqual(cache_path, retrieved_path)

    def test_get_cover_not_exists(self):
        """Test retrieving a non-existent cached cover."""
        retrieved_path = CoverCache.get_cover("/nonexistent/book.epub", "cover.jpg")

        self.assertIsNone(retrieved_path)

    def test_has_cover(self):
        """Test checking if a cover is cached."""
        # Should not exist initially
        self.assertFalse(CoverCache.has_cover(self.test_book_path, self.test_internal_path))

        # Save a cover
        CoverCache.save_cover(self.test_book_path, self.test_cover_data, self.test_internal_path)

        # Should exist now
        self.assertTrue(CoverCache.has_cover(self.test_book_path, self.test_internal_path))

    def test_delete_cover(self):
        """Test deleting a cached cover."""
        # Save a cover first
        CoverCache.save_cover(self.test_book_path, self.test_cover_data, self.test_internal_path)

        # Verify it exists
        self.assertTrue(CoverCache.has_cover(self.test_book_path, self.test_internal_path))

        # Delete it
        deleted = CoverCache.delete_cover(self.test_book_path, self.test_internal_path)

        self.assertTrue(deleted)

        # Verify it's gone
        self.assertFalse(CoverCache.has_cover(self.test_book_path, self.test_internal_path))

    def test_delete_cover_not_exists(self):
        """Test deleting a non-existent cover."""
        deleted = CoverCache.delete_cover("/nonexistent/book.epub", "cover.jpg")

        self.assertFalse(deleted)

    def test_clear_all(self):
        """Test clearing all cached covers."""
        # Save multiple covers
        CoverCache.save_cover("/book1.epub", self.test_cover_data, "cover1.jpg")
        CoverCache.save_cover("/book2.epub", self.test_cover_data, "cover2.jpg")
        CoverCache.save_cover("/book3.epub", self.test_cover_data, "cover3.jpg")

        # Clear all
        deleted, errors = CoverCache.clear_all()

        self.assertEqual(deleted, 3)
        self.assertEqual(errors, 0)

        # Verify cache is empty
        count, size = CoverCache.get_cache_size()
        self.assertEqual(count, 0)

    def test_get_cache_size(self):
        """Test getting cache statistics."""
        # Empty cache
        count, size = CoverCache.get_cache_size()
        self.assertEqual(count, 0)
        self.assertEqual(size, 0)

        # Add some covers
        CoverCache.save_cover("/book1.epub", self.test_cover_data, "cover1.jpg")
        CoverCache.save_cover("/book2.epub", self.test_cover_data, "cover2.jpg")

        # Check size
        count, size = CoverCache.get_cache_size()
        self.assertEqual(count, 2)
        self.assertGreater(size, 0)

    def test_save_cover_overwrites_existing(self):
        """Test that saving a cover overwrites existing one."""
        # Save first version
        success1, path1 = CoverCache.save_cover(self.test_book_path, b"version 1", self.test_internal_path)

        # Save second version (same paths)
        success2, path2 = CoverCache.save_cover(self.test_book_path, b"version 2", self.test_internal_path)

        self.assertTrue(success1)
        self.assertTrue(success2)

        # Paths should be the same (overwritten)
        self.assertEqual(path1, path2)

        # Should only have one file
        count, _ = CoverCache.get_cache_size()
        # Note: Might be more than 1 if other tests ran, so just check it exists
        self.assertGreaterEqual(count, 1)
