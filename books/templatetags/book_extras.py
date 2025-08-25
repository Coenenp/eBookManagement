# book_extras.py - Fix the template path and improve error handling
from django import template
from books.utils.image_utils import encode_cover_to_base64
import os

register = template.Library()


@register.inclusion_tag('books/partials/book_cover.html')
def book_cover(book, size='medium', badge=None):
    """Render book cover with lazy loading and error handling"""
    try:
        # Get cover from books_with_covers context data first (if available)
        cover_path = ''
        base64_image = None

        # Check if we have cover data from the view context
        if hasattr(book, '_cover_data'):
            cover_path = book._cover_data.get('cover_path', '')
            base64_image = book._cover_data.get('cover_base64')
        else:
            # Fallback to model data
            if hasattr(book, 'finalmetadata') and book.finalmetadata:
                cover_path = getattr(book.finalmetadata, 'final_cover_path', '') or ''
            else:
                cover_path = getattr(book, 'cover_path', '') or ''

        is_url = str(cover_path).startswith(("http://", "https://"))

        # Only encode if it's a local file, exists, and we don't already have base64
        if cover_path and not is_url and not base64_image:
            try:
                if os.path.exists(cover_path):
                    base64_image = encode_cover_to_base64(cover_path)
            except Exception:
                # If encoding fails, fall back to regular path
                base64_image = None

        return {
            'book': book,
            'cover_path': cover_path,
            'is_url': is_url,
            'size': size,
            'badge': badge,
            'base64_image': base64_image,
        }
    except Exception as e:
        # Log error in production
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error rendering book cover for book {getattr(book, 'id', 'unknown')}: {e}")

        # Fallback for any errors
        return {
            'book': book,
            'cover_path': '',
            'is_url': False,
            'size': size,
            'badge': badge,
            'base64_image': None,
        }
