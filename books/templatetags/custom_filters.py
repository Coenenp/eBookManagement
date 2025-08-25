from django import template
import urllib.parse
import os
import logging

register = template.Library()


@register.filter
def mul(value, arg):
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return 0


@register.filter
def field_label(value):
    return value.replace('_', ' ').title()


@register.filter
def dict_get(d, key):
    if isinstance(d, dict):
        return d.get(key, '')
    return ''  # Fallback if d isn't a dict


@register.filter
def getattr_safe(obj, attr_name):
    """Gets an attribute from an object by name. Returns '' if not found."""
    return getattr(obj, attr_name, '')


@register.filter
def get_item(dictionary, key):
    return dictionary.get(key)


@register.simple_tag
def querystring(querydict, key, value):
    query = querydict.copy()
    query[key] = value
    return urllib.parse.urlencode(query)


@register.filter
def prettify_field_name(value):
    return value.replace('_', ' ').title()


@register.filter
def get_display_title(book):
    """Return the best available title for a book."""
    try:
        if hasattr(book, 'finalmetadata') and book.finalmetadata:
            final_title = getattr(book.finalmetadata, 'final_title', None)
            if final_title:
                return final_title

        # Try to get first title
        if hasattr(book, 'titles'):
            first_title = book.titles.first()
            if first_title and hasattr(first_title, 'title'):
                return first_title.title

        # Fallback to filename without extension
        if hasattr(book, 'filename'):
            return os.path.splitext(book.filename)[0]

        return 'Unknown Title'
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Error getting display title for book {getattr(book, 'id', 'unknown')}: {e}")
        return 'Unknown Title'


@register.filter
def get_display_author(book):
    """Return the best available author for a book."""
    try:
        if hasattr(book, 'finalmetadata') and book.finalmetadata.final_author:
            return book.finalmetadata.final_author
        first_author = book.bookauthor.first()
        return first_author.author.name if first_author and first_author.author else 'Unknown Author'
    except Exception:
        return 'Unknown Author'


@register.filter
def get_cover_path(book):
    """Return the best available cover path or base64 string."""
    try:
        if hasattr(book, 'finalmetadata') and book.finalmetadata:
            cover = book.finalmetadata.final_cover_path or book.finalmetadata.cover_base64
            return cover if cover else 'No Cover'
        return book.cover_path or 'No Cover'
    except Exception:
        return 'No Cover'


@register.filter
def safe_confidence_format(confidence):
    """Safely format confidence values."""
    try:
        if confidence is None:
            return "0.00"
        return f"{float(confidence):.2f}"
    except (ValueError, TypeError):
        return "0.00"

# In custom_filters.py, your sanitizeText is incomplete:
@register.filter
def sanitize_html(text):
    if not text:
        return ''
    
    # Use bleach library for proper HTML sanitization
    import bleach
    allowed_tags = ['b', 'i', 'em', 'strong']
    return bleach.clean(text, tags=allowed_tags, strip=True)
