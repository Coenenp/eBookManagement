"""
Cover cache management for extracted internal covers.

This module handles caching of covers extracted from EPUBs, PDFs, and archives.
Extracted covers are stored in MEDIA_ROOT/cover_cache/ with a hash-based naming
scheme to ensure uniqueness and enable efficient lookups.
"""

import hashlib
import logging
from pathlib import Path
from typing import Optional, Tuple

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

logger = logging.getLogger(__name__)


class CoverCache:
    """Manages caching of extracted cover images."""

    CACHE_DIR = "cover_cache"

    @classmethod
    def get_cache_path(cls, book_file_path: str, internal_path: Optional[str] = None) -> str:
        """
        Generate a cache path for a cover image.

        Args:
            book_file_path: Absolute path to the book file
            internal_path: Optional internal path within archive/EPUB

        Returns:
            Relative path within media storage (e.g., 'cover_cache/abc123.jpg')
        """
        # Create a unique hash from the book path and internal path
        hash_input = f"{book_file_path}::{internal_path or ''}"
        file_hash = hashlib.sha256(hash_input.encode()).hexdigest()[:16]

        # Use .jpg extension for all cached covers (we'll convert if needed)
        cache_filename = f"{file_hash}.jpg"
        # Always use forward slashes for consistency across platforms
        return f"{cls.CACHE_DIR}/{cache_filename}"

    @classmethod
    def save_cover(cls, book_file_path: str, cover_data: bytes, internal_path: Optional[str] = None) -> Tuple[bool, str]:
        """
        Save a cover image to the cache.

        Args:
            book_file_path: Absolute path to the book file
            cover_data: Binary image data
            internal_path: Optional internal path within archive/EPUB

        Returns:
            Tuple of (success: bool, cache_path: str)
        """
        try:
            cache_path = cls.get_cache_path(book_file_path, internal_path)

            # Ensure cache directory exists
            cache_dir = Path(settings.MEDIA_ROOT) / cls.CACHE_DIR
            cache_dir.mkdir(parents=True, exist_ok=True)

            # Save the cover image
            saved_path = default_storage.save(cache_path, ContentFile(cover_data))

            logger.info(f"Cached cover for {book_file_path} at {saved_path}")
            return True, saved_path

        except Exception as e:
            logger.error(f"Failed to cache cover for {book_file_path}: {e}")
            return False, ""

    @classmethod
    def get_cover(cls, book_file_path: str, internal_path: Optional[str] = None) -> Optional[str]:
        """
        Retrieve a cached cover image path.

        Args:
            book_file_path: Absolute path to the book file
            internal_path: Optional internal path within archive/EPUB

        Returns:
            Relative path within media storage if cached, None otherwise
        """
        cache_path = cls.get_cache_path(book_file_path, internal_path)

        if default_storage.exists(cache_path):
            return cache_path

        return None

    @classmethod
    def has_cover(cls, book_file_path: str, internal_path: Optional[str] = None) -> bool:
        """
        Check if a cover is cached.

        Args:
            book_file_path: Absolute path to the book file
            internal_path: Optional internal path within archive/EPUB

        Returns:
            True if cached, False otherwise
        """
        cache_path = cls.get_cache_path(book_file_path, internal_path)
        return default_storage.exists(cache_path)

    @classmethod
    def delete_cover(cls, book_file_path: str, internal_path: Optional[str] = None) -> bool:
        """
        Delete a cached cover image.

        Args:
            book_file_path: Absolute path to the book file
            internal_path: Optional internal path within archive/EPUB

        Returns:
            True if deleted, False if not found or error
        """
        try:
            cache_path = cls.get_cache_path(book_file_path, internal_path)

            if default_storage.exists(cache_path):
                default_storage.delete(cache_path)
                logger.info(f"Deleted cached cover for {book_file_path}")
                return True

            return False

        except Exception as e:
            logger.error(f"Failed to delete cached cover for {book_file_path}: {e}")
            return False

    @classmethod
    def clear_all(cls) -> Tuple[int, int]:
        """
        Clear all cached covers.

        Returns:
            Tuple of (deleted_count: int, error_count: int)
        """
        deleted = 0
        errors = 0

        try:
            cache_dir = Path(settings.MEDIA_ROOT) / cls.CACHE_DIR

            if not cache_dir.exists():
                logger.info("Cover cache directory does not exist")
                return 0, 0

            for cover_file in cache_dir.glob("*.jpg"):
                try:
                    cover_file.unlink()
                    deleted += 1
                except Exception as e:
                    logger.error(f"Failed to delete {cover_file}: {e}")
                    errors += 1

            logger.info(f"Cleared cover cache: {deleted} deleted, {errors} errors")
            return deleted, errors

        except Exception as e:
            logger.error(f"Failed to clear cover cache: {e}")
            return deleted, errors

    @classmethod
    def get_cache_size(cls) -> Tuple[int, int]:
        """
        Get statistics about the cover cache.

        Returns:
            Tuple of (file_count: int, total_bytes: int)
        """
        try:
            cache_dir = Path(settings.MEDIA_ROOT) / cls.CACHE_DIR

            if not cache_dir.exists():
                return 0, 0

            files = list(cache_dir.glob("*.jpg"))
            total_size = sum(f.stat().st_size for f in files if f.is_file())

            return len(files), total_size

        except Exception as e:
            logger.error(f"Failed to get cache statistics: {e}")
            return 0, 0
