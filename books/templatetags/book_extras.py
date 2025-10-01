"""Template tags for book display and metadata rendering.

This module provides consolidated template tags for book cover display,
metadata badges, and other book-related UI components.
"""
# book_extras.py - Consolidated template tags for book display
from django import template
from books.utils.image_utils import encode_cover_to_base64
import os
import logging
import requests
from django.conf import settings

register = template.Library()
logger = logging.getLogger('books.scanner')


def download_and_cache_cover(cover_url, book_id):
    """Download a cover URL and cache it locally, return base64 encoded version"""
    try:
        logger.info(f"Starting download for cover URL: {cover_url}")

        # Create cache directory if it doesn't exist
        cache_dir = os.path.join(settings.MEDIA_ROOT, 'cover_cache')
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

        with open(cache_path, 'wb') as f:
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
        'book': book,
        'cover_path': '',
        'is_url': False,
        'size': size,
        'badge': badge,
        'base64_image': None,
    }


def _process_cover_for_display(cover_path, book, add_cache_busting=False):
    """
    Helper function to process cover paths for display.
    Handles URL downloading, local file encoding, and returns processed data.
    """
    if not cover_path:
        return '', False, None

    is_url = str(cover_path).startswith(("http://", "https://"))
    base64_image = None

    if is_url:
        # Download and cache URL-based covers, convert to base64
        book_id = getattr(book, 'id', 'unknown')
        logger.info(f"Processing URL cover for book {book_id}: {cover_path}")
        base64_image = download_and_cache_cover(cover_path, book_id)

        if base64_image:
            logger.info(f"Successfully got base64 image, length: {len(base64_image)}")
            is_url = False  # We have base64, don't need URL
        elif add_cache_busting:
            # Add cache busting parameter to force browser refresh
            logger.warning("Failed to download/cache cover, adding cache busting")
            timestamp = book.finalmetadata.last_updated.timestamp() if hasattr(book, 'finalmetadata') and book.finalmetadata else ''
            separator = "&" if '?' in cover_path else "?"
            cover_path += f"{separator}t={timestamp}"
    else:
        # Handle local file paths
        try:
            if os.path.exists(cover_path):
                logger.info(f"Processing local file: {cover_path}")
                base64_image = encode_cover_to_base64(cover_path)
                logger.info(f"Local file base64 result length: {len(base64_image) if base64_image else 0}")
        except Exception as e:
            logger.error(f"Error encoding local file {cover_path}: {e}")
            base64_image = None

    return cover_path, is_url, base64_image


@register.inclusion_tag('books/partials/book_cover.html')
def book_cover_from_metadata(cover, book, size='medium', badge=None):
    """Render book cover from metadata cover object, with URL downloading and caching"""
    try:
        cover_path = getattr(cover, 'cover_path', '') or ''
        logger.info(f"book_cover_from_metadata called with cover_path: {cover_path}")

        # Process the cover using shared logic
        cover_path, is_url, base64_image = _process_cover_for_display(
            cover_path, book, add_cache_busting=True
        )

        result = {
            'book': book,
            'cover_path': cover_path,
            'is_url': is_url,
            'size': size,
            'badge': badge,
            'base64_image': base64_image,
        }
        logger.info(f"Returning template context: is_url={is_url}, has_base64={bool(base64_image)}")
        return result
    except Exception as e:
        logger.error(f"Error rendering metadata cover for book {getattr(book, 'id', 'unknown')}: {e}")
        return _get_fallback_context(book, size, badge)


@register.inclusion_tag('books/partials/book_cover.html')
def book_cover(book, size='medium', badge=None):
    """Render book cover with lazy loading and error handling"""
    try:
        # Get cover path from different sources
        cover_path = ''
        base64_image = None

        # Check if we have cover data from the view context first
        if hasattr(book, '_cover_data'):
            cover_path = book._cover_data.get('cover_path', '')
            base64_image = book._cover_data.get('cover_base64')
        else:
            # Fallback to model data
            if hasattr(book, 'finalmetadata') and book.finalmetadata:
                cover_path = getattr(book.finalmetadata, 'final_cover_path', '') or ''
            else:
                cover_path = getattr(book, 'cover_path', '') or ''

        # Only process if we don't already have base64 from context
        if not base64_image:
            cover_path, is_url, base64_image = _process_cover_for_display(
                cover_path, book, add_cache_busting=False
            )
        else:
            # We have base64 from context, determine if original was URL
            is_url = str(cover_path).startswith(("http://", "https://"))
            if base64_image:
                is_url = False  # We have base64, don't need URL

        return {
            'book': book,
            'cover_path': cover_path,
            'is_url': is_url,
            'size': size,
            'badge': badge,
            'base64_image': base64_image,
        }
    except Exception as e:
        logger.error(f"Error rendering book cover for book {getattr(book, 'id', 'unknown')}: {e}")
        return _get_fallback_context(book, size, badge)


@register.filter
def safe_finalmetadata(book, field_name):
    """Safely access finalmetadata fields, returning None or default if metadata doesn't exist"""
    try:
        if hasattr(book, 'finalmetadata') and book.finalmetadata:
            return getattr(book.finalmetadata, field_name, None)
        return None
    except Exception:
        return None


@register.filter
def has_finalmetadata(book):
    """Check if book has finalmetadata safely"""
    try:
        return hasattr(book, 'finalmetadata') and book.finalmetadata is not None
    except Exception:
        return False


@register.filter
def language_display(language_code):
    """Convert language code to full language name for display"""
    from books.utils.language_manager import LanguageManager

    if not language_code:
        return ''

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
