"""
Cover cache management for extracted internal covers.

This module handles caching of covers extracted from EPUBs, PDFs, and archives.
Extracted covers are stored in MEDIA_ROOT/cover_cache/ with a hash-based naming
scheme to ensure uniqueness and enable efficient lookups.
"""

import hashlib
import logging
import os
from pathlib import Path
from typing import Optional, Tuple

from django.conf import settings
from django.core.files.storage import default_storage

logger = logging.getLogger(__name__)


class CoverCache:
    """Manages caching of extracted cover images."""

    CACHE_DIR = "cover_cache"
    PLACEHOLDER_REL = "book/images/cover-placeholder.svg"
    COVER_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}

    @classmethod
    def _iter_cache_files(cls):
        """Yield cached cover files matching supported image extensions."""
        cache_dir = Path(settings.MEDIA_ROOT) / cls.CACHE_DIR
        if not cache_dir.exists():
            return
        for path in cache_dir.iterdir():
            if path.is_file() and path.suffix.lower() in cls.COVER_EXTENSIONS:
                yield path

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
        cache_path = cls.get_cache_path(book_file_path, internal_path)

        # Ensure cache directory exists
        cache_dir = Path(settings.MEDIA_ROOT) / cls.CACHE_DIR
        cache_dir.mkdir(parents=True, exist_ok=True)

        # Write to a temporary file first, then atomically replace the target so a
        # failed write never destroys a previously cached cover.
        final_path = cache_dir / Path(cache_path).name
        tmp_path = cache_dir / f".{final_path.name}.tmp"

        try:
            with open(tmp_path, "wb") as f:
                f.write(cover_data)
            os.replace(tmp_path, final_path)
        except Exception as e:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass
            logger.error(f"Failed to cache cover for {book_file_path}: {e}")
            return False, ""

        logger.info(f"Cached cover for {book_file_path} at {cache_path}")
        return True, cache_path

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
    def media_exists(cls, relative_path: Optional[str]) -> bool:
        """Return True when a media-relative path exists in storage."""
        if not relative_path:
            return False
        return default_storage.exists(str(relative_path).replace("\\", "/").lstrip("/"))

    @classmethod
    def placeholder_url(cls) -> str:
        """Return the static URL for the placeholder cover image."""
        from django.conf import settings

        return f"{settings.STATIC_URL}{cls.PLACEHOLDER_REL}"

    @classmethod
    def cleanup_orphans(cls, dry_run: bool = False) -> Tuple[int, int]:
        """Delete cached covers not referenced by any ``BookFile``.

        Returns a ``(deleted, errors)`` tuple. With ``dry_run=True`` the first
        value is the number of files that *would* be deleted.
        """
        try:
            from books.models import BookFile
        except ImportError:
            return 0, 0

        referenced = set()
        for cover_path, original_path in BookFile.objects.values_list("cover_path", "original_cover_path"):
            for value in (cover_path, original_path):
                if value:
                    referenced.add(str(value).replace("\\", "/").lstrip("/"))

        cache_dir = Path(settings.MEDIA_ROOT) / cls.CACHE_DIR
        if not cache_dir.exists():
            return 0, 0

        deleted = 0
        errors = 0
        for cover_file in cls._iter_cache_files():
            relative = f"{cls.CACHE_DIR}/{cover_file.name}"
            if relative in referenced:
                continue
            if dry_run:
                deleted += 1
                continue
            try:
                cover_file.unlink()
                deleted += 1
            except Exception as e:
                logger.error(f"Failed to delete orphaned cover {cover_file}: {e}")
                errors += 1

        return deleted, errors

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

            for cover_file in cls._iter_cache_files():
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

            files = list(cls._iter_cache_files())
            total_size = sum(f.stat().st_size for f in files if f.is_file())

            return len(files), total_size

        except Exception as e:
            logger.error(f"Failed to get cache statistics: {e}")
            return 0, 0
