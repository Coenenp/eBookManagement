"""Template tags for book display and metadata rendering.

This module provides consolidated template tags for book cover display,
metadata badges, and other book-related UI components.
"""

# book_extras.py - Consolidated template tags for book display
import logging
import os

import requests
from django import template
from django.conf import settings

from books.utils.image_utils import encode_cover_to_base64

register = template.Library()
logger = logging.getLogger("books.scanner")


def download_and_cache_cover(cover_url, book_id):
    """Download a cover URL and cache it locally, return base64 encoded version"""
    try:
        logger.info(f"Starting download for cover URL: {cover_url}")

        # Create cache directory if it doesn't exist
        cache_dir = os.path.join(settings.MEDIA_ROOT, "cover_cache")
        os.makedirs(cache_dir, exist_ok=True)
        logger.info(f"Cache directory: {cache_dir}")

        # Create filename from URL hash and book ID
        url_hash = str(hash(cover_url))[-8:]  # Last 8 chars of hash
        filename = f"book_{book_id}_cover_{url_hash}.jpg"
        cache_path = os.path.join(cache_dir, filename)
        logger.info(f"Cache path: {cache_path}")

        # Check if already cached
        if os.path.exists(cache_path):
            logger.info(f"Found cached file: {cache_path}")
            base64_result = encode_cover_to_base64(cache_path)
            logger.info(f"Base64 encoding result length: {len(base64_result) if base64_result else 0}")
            return base64_result

        # Download and cache the image
        logger.info(f"Downloading cover from: {cover_url}")
        response = requests.get(cover_url, timeout=10)
        response.raise_for_status()
        logger.info(f"Download successful, content length: {len(response.content)}")

        with open(cache_path, "wb") as f:
            f.write(response.content)
        logger.info(f"Saved to cache: {cache_path}")

        # Return base64 encoded version
        base64_result = encode_cover_to_base64(cache_path)
        logger.info(f"Base64 encoding result length: {len(base64_result) if base64_result else 0}")
        return base64_result

    except Exception as e:
        logger.error(f"Error downloading/caching cover from {cover_url}: {e}")
        return None


def _get_fallback_context(book, size, badge):
    """Return fallback context for template rendering errors"""
    return {
        "book": book,
        "cover_path": "",
        "is_url": False,
        "size": size,
        "badge": badge,
        "base64_image": None,
    }


def _process_cover_for_display(cover_path, book, add_cache_busting=False, skip_download=False):
    """
    Helper function to process cover paths for display.
    Handles URL downloading, local file encoding, and returns processed data.

    Args:
        skip_download: If True, don't download URL covers (for list views with many books)
    """
    if not cover_path:
        return "", False, None

    is_url = str(cover_path).startswith(("http://", "https://"))
    base64_image = None

    if is_url:
        # For list views, skip downloading to avoid blocking page load
        if skip_download:
            logger.debug(f"Skipping download for book {getattr(book, 'id', 'unknown')} (list view optimization)")
            return cover_path, True, None  # Return URL as-is, will be lazy loaded by browser

        # Download and cache URL-based covers, convert to base64
        book_id = getattr(book, "id", "unknown")
        logger.info(f"Processing URL cover for book {book_id}: {cover_path}")
        base64_image = download_and_cache_cover(cover_path, book_id)

        if base64_image:
            logger.info(f"Successfully got base64 image, length: {len(base64_image)}")
            is_url = False  # We have base64, don't need URL
        elif add_cache_busting:
            # Add cache busting parameter to force browser refresh
            logger.warning("Failed to download/cache cover, adding cache busting")
            timestamp = book.finalmetadata.last_updated.timestamp() if hasattr(book, "finalmetadata") and book.finalmetadata else ""
            separator = "&" if "?" in cover_path else "?"
            cover_path += f"{separator}t={timestamp}"
    else:
        # Handle local file paths - always encode to base64 for consistent display
        try:
            if os.path.exists(cover_path):
                logger.debug(f"Encoding local file to base64: {cover_path}")
                base64_image = encode_cover_to_base64(cover_path)
                if base64_image:
                    logger.debug(f"Successfully encoded to base64, length: {len(base64_image)}")
        except Exception as e:
            logger.error(f"Error encoding local file {cover_path}: {e}")
            base64_image = None

    return cover_path, is_url, base64_image


@register.inclusion_tag("books/partials/book_cover.html")
def book_cover_from_metadata(cover, book, size="medium", badge=None):
    """Render book cover from metadata cover object, with URL downloading and caching"""
    try:
        cover_path = getattr(cover, "cover_path", "") or ""
        logger.info(f"book_cover_from_metadata called with cover_path: {cover_path}")

        # Process the cover using shared logic
        cover_path, is_url, base64_image = _process_cover_for_display(cover_path, book, add_cache_busting=True)

        result = {
            "book": book,
            "cover_path": cover_path,
            "is_url": is_url,
            "size": size,
            "badge": badge,
            "base64_image": base64_image,
        }
        logger.info(f"Returning template context: is_url={is_url}, has_base64={bool(base64_image)}")
        return result
    except Exception as e:
        logger.error(f"Error rendering metadata cover for book {getattr(book, 'id', 'unknown')}: {e}")
        return _get_fallback_context(book, size, badge)


@register.inclusion_tag("books/partials/book_cover.html")
def book_cover(book, size="medium", badge=None, skip_download=False):
    """
    Render book cover with lazy loading and error handling

    Args:
        skip_download: If True, don't download covers (for list views with many books)
    """
    try:
        # Get cover path from different sources
        cover_path = ""
        base64_image = None

        # Check if we have cover data from the view context first
        if hasattr(book, "_cover_data"):
            cover_path = book._cover_data.get("cover_path", "")
            base64_image = book._cover_data.get("cover_base64")
        else:
            # Fallback to model data
            if hasattr(book, "finalmetadata") and book.finalmetadata:
                cover_path = getattr(book.finalmetadata, "final_cover_path", "") or ""
            else:
                cover_path = getattr(book, "cover_path", "") or ""

            # If no cover from finalmetadata, try to get from first file
            if not cover_path and hasattr(book, "prefetched_files") and book.prefetched_files:
                first_file = book.prefetched_files[0]
                cover_path = getattr(first_file, "cover_path", "") or ""
            elif not cover_path and hasattr(book, "primary_file") and book.primary_file:
                cover_path = getattr(book.primary_file, "cover_path", "") or ""

        # Only process if we don't already have base64 from context
        if not base64_image:
            cover_path, is_url, base64_image = _process_cover_for_display(cover_path, book, add_cache_busting=False, skip_download=skip_download)
        else:
            # We have base64 from context, determine if original was URL
            is_url = str(cover_path).startswith(("http://", "https://"))
            if base64_image:
                is_url = False  # We have base64, don't need URL

        return {
            "book": book,
            "cover_path": cover_path,
            "is_url": is_url,
            "size": size,
            "badge": badge,
            "base64_image": base64_image,
        }
    except Exception as e:
        logger.error(f"Error rendering book cover for book {getattr(book, 'id', 'unknown')}: {e}")
        return _get_fallback_context(book, size, badge)


@register.filter
def safe_finalmetadata(book, field_name):
    """Safely access finalmetadata fields, returning None or default if metadata doesn't exist"""
    try:
        if hasattr(book, "finalmetadata") and book.finalmetadata:
            return getattr(book.finalmetadata, field_name, None)
        return None
    except Exception:
        return None


@register.filter
def has_finalmetadata(book):
    """Check if book has finalmetadata safely"""
    try:
        return hasattr(book, "finalmetadata") and book.finalmetadata is not None
    except Exception:
        return False


@register.filter
def language_display(language_code):
    """Convert language code to full language name for display"""
    from books.utils.language_manager import LanguageManager

    if not language_code:
        return ""

    return LanguageManager.get_language_name(language_code)


@register.filter
def language_name(language_code):
    """Convert language code to full language name for display (alias for language_display)"""
    return language_display(language_code)


@register.filter
def format_confidence(confidence):
    """Format confidence value as percentage string"""
    if confidence is None:
        return "N/A"

    try:
        # Convert to percentage and format
        percentage = float(confidence) * 100
        return f"{percentage:.0f}%"
    except (ValueError, TypeError):
        return "N/A"


@register.simple_tag
def get_book_cover_url(book_file, default=""):
    """
    Get the cover URL for a BookFile, handling both external and internal covers.

    For external companion covers, returns the file path directly.
    For internal covers (EPUB, PDF, archives), returns the cached cover path.
    If cover is not yet cached but has_internal_cover is True, extracts on-demand.

    Args:
        book_file: BookFile instance
        default: Default value if no cover found

    Returns:
        URL/path to cover image or default value
    """
    if not book_file:
        return default

    # If cover_path is already set, use it
    if book_file.cover_path:
        # Return the media URL for the cover
        from django.conf import settings

        # For cached covers, construct the media URL
        if book_file.cover_path.startswith("cover_cache/"):
            return f"{settings.MEDIA_URL}{book_file.cover_path}"

        # For external companion files, return the path
        return book_file.cover_path

    # If no cover_path but has_internal_cover, extract on-demand
    if book_file.has_internal_cover and book_file.file_path:
        from books.utils.cover_cache import CoverCache
        from books.utils.cover_extractor import (
            ArchiveCoverExtractor,
            CoverExtractionError,
            EPUBCoverExtractor,
            PDFCoverExtractor,
        )

        # Check if already cached
        cached = CoverCache.get_cover(book_file.file_path, book_file.cover_internal_path)
        if cached:
            from django.conf import settings

            # Update book_file with cached path
            book_file.cover_path = cached
            book_file.save(update_fields=["cover_path"])
            return f"{settings.MEDIA_URL}{cached}"

        # Extract on-demand based on source type
        try:
            cover_data = None
            internal_path = book_file.cover_internal_path

            if book_file.cover_source_type == "epub_internal":
                cover_data, internal_path = EPUBCoverExtractor.extract_cover(book_file.file_path)
            elif book_file.cover_source_type == "pdf_page":
                cover_data = PDFCoverExtractor.extract_cover(book_file.file_path)
                internal_path = "page_1"
            elif book_file.cover_source_type == "archive_first":
                cover_data, internal_path = ArchiveCoverExtractor.extract_cover(book_file.file_path)

            if cover_data:
                success, cache_path = CoverCache.save_cover(book_file.file_path, cover_data, internal_path)
                if success:
                    from django.conf import settings

                    # Update book_file with cached path
                    book_file.cover_path = cache_path
                    book_file.save(update_fields=["cover_path"])
                    return f"{settings.MEDIA_URL}{cache_path}"

        except CoverExtractionError as e:
            logger.warning(f"On-demand cover extraction failed for {book_file.file_path}: {e}")
        except Exception as e:
            logger.error(f"Unexpected error in on-demand cover extraction: {e}")

    return default
