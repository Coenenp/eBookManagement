"""Custom template filters for various data manipulation.

This module provides template filters for mathematical operations,
text processing, and data formatting in Django templates.
"""
from django import template
import urllib.parse
import os
import logging
import bleach

logger = logging.getLogger('books.scanner')
register = template.Library()

# Store built-in hash function before defining template filter
builtin_hash = hash


@register.filter
def mul(value, arg):
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return 0


@register.filter
def div(value, arg):
    try:
        arg_float = float(arg)
        if arg_float == 0:
            return 0
        return float(value) / arg_float
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


@register.filter
def lookup(dictionary, key):
    """Look up a key in a dictionary."""
    if isinstance(dictionary, dict):
        return dictionary.get(key)
    return None


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
def safe_confidence_format(confidence):
    """Safely format confidence values."""
    try:
        if confidence is None:
            return "0.00"
        return f"{float(confidence):.2f}"
    except (ValueError, TypeError):
        return "0.00"


@register.filter
def sanitize_html(text):
    """Sanitize HTML content, allowing only safe tags."""
    if not text:
        return ''

    # First remove dangerous tags and their content entirely
    import re
    # Remove script tags and all their content
    text = re.sub(r'<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>', '', text, flags=re.IGNORECASE)
    # Remove style tags and all their content
    text = re.sub(r'<style\b[^<]*(?:(?!<\/style>)<[^<]*)*<\/style>', '', text, flags=re.IGNORECASE)

    allowed_tags = ['b', 'i', 'em', 'strong', 'p', 'br', 'ul', 'ol', 'li']
    allowed_attributes = {}  # No attributes allowed for safety
    return bleach.clean(text, tags=allowed_tags, attributes=allowed_attributes, strip=True)


@register.filter
def sanitize_description(text):
    """Sanitize description content, handling HTML properly and cleaning up common issues."""
    if not text:
        return ''

    # Remove unwanted HTML class attributes and clean up common external content
    import re

    # Remove class attributes from p tags and other elements
    text = re.sub(r'<([^>]+)\s+class="[^"]*"([^>]*)>', r'<\1\2>', text)

    # Convert common HTML entities and encoding issues
    # Do specific pattern replacements in correct order
    text = text.replace('â€œ', '"')    # Left double quote
    text = text.replace('â€™', "'")    # Right single quote (do before â€)
    text = text.replace('â€˜', "'")    # Left single quote (do before â€)
    text = text.replace('â€', '"')     # Right double quote (do last)

    # Clean up excessive line breaks
    text = re.sub(r'<br\s*/?>\s*<br\s*/?>\s*<br\s*/?>', '<br><br>', text)

    # Allow description-appropriate tags
    allowed_tags = ['b', 'i', 'em', 'strong', 'p', 'br', 'ul', 'ol', 'li']
    allowed_attributes = {}  # No attributes for safety

    cleaned_text = bleach.clean(text, tags=allowed_tags, attributes=allowed_attributes, strip=True)

    # Clean up source citations at the end
    cleaned_text = re.sub(r'\s*\(source:\s*[^)]+\)\s*$', '', cleaned_text, flags=re.IGNORECASE)

    return cleaned_text


@register.filter
def language_name(language_code):
    """Convert language code to readable name."""
    from books.utils.language_manager import LanguageManager
    return LanguageManager.get_language_name(language_code)


@register.simple_tag(takes_context=True)
def url_replace(context, **kwargs):
    """Replace query parameters in current URL."""
    request = context['request']
    query = request.GET.copy()
    for key, value in kwargs.items():
        query[key] = value
    return query.urlencode()


@register.filter
def is_valid_isbn(isbn):
    """Check if an ISBN is valid for external API lookups."""
    if not isbn:
        return False

    # Remove any formatting
    clean_isbn = isbn.replace('-', '').replace(' ', '')

    # Check if it's a valid length (10 or 13 digits)
    if len(clean_isbn) not in [10, 13]:
        return False

    # Check if it contains only digits (and possibly 'X' for ISBN-10)
    if len(clean_isbn) == 10:
        return clean_isbn[:-1].isdigit() and (clean_isbn[-1].isdigit() or clean_isbn[-1].upper() == 'X')
    else:  # 13 digits
        return clean_isbn.isdigit()


@register.filter
def isbn_type(isbn):
    """Return the type of ISBN (ISBN-10, ISBN-13, or Invalid)."""
    if not isbn:
        return "No ISBN"

    clean_isbn = isbn.replace('-', '').replace(' ', '')

    if len(clean_isbn) == 10:
        if clean_isbn[:-1].isdigit() and (clean_isbn[-1].isdigit() or clean_isbn[-1].upper() == 'X'):
            return "ISBN-10"
    elif len(clean_isbn) == 13:
        if clean_isbn.isdigit():
            return "ISBN-13"

    return "Invalid"


@register.filter
def hash(value):
    """Return a hash of the given value, useful for creating unique IDs."""
    return str(abs(builtin_hash(str(value))))
