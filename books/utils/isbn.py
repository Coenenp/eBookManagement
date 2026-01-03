"""ISBN validation and normalization utilities.

This module provides functions for processing ISBN numbers including
validation, normalization, and format conversion operations.
"""
import re
from datetime import datetime


def normalize_isbn(raw):
    """Extract, validate, and normalize ISBN input to 13-digit format."""
    if not raw:
        return None

    raw = raw.lower().strip()

    # Strip known prefixes
    prefixes = ['urn:isbn:', 'isbn:', 'urn:', 'isbn']
    for prefix in prefixes:
        if raw.startswith(prefix):
            raw = raw[len(prefix):]

    # Extract digits only
    raw_digits = re.sub(r'[^0-9xX]', '', raw)

    # Check for ISBN-10 format
    if len(raw_digits) == 10:
        if is_valid_isbn10(raw_digits):
            return convert_to_isbn13(raw_digits)
        else:
            return None

    # Check for ISBN-13 format
    if len(raw_digits) == 13:
        return raw_digits if is_valid_isbn13(raw_digits) else None

    return None


def is_valid_isbn13(isbn):
    """Validate ISBN-13 using check digit."""
    if not re.match(r'^\d{13}$', isbn):
        return False
    total = sum((int(num) if i % 2 == 0 else int(num) * 3) for i, num in enumerate(isbn[:12]))
    check = (10 - (total % 10)) % 10
    return check == int(isbn[-1])


def is_valid_isbn10(isbn):
    """Validate ISBN-10 using check digit."""
    if not re.match(r'^\d{9}[\dXx]$', isbn):
        return False
    total = sum((10 - i) * (10 if ch in 'Xx' else int(ch)) for i, ch in enumerate(isbn))
    return total % 11 == 0


def convert_to_isbn13(isbn10):
    """Convert ISBN-10 to ISBN-13."""
    core = '978' + isbn10[:-1]
    total = sum((int(num) if i % 2 == 0 else int(num) * 3) for i, num in enumerate(core))
    check = (10 - (total % 10)) % 10
    return core + str(check)


def normalize_publication_year(raw):
    """
    Validate and normalize publication year.

    Args:
        raw: Raw year input (string or int)

    Returns:
        int: Validated year between 1450 and current_year + 5, or None if invalid
    """
    if not raw:
        return None

    try:
        # Convert to string and extract first 4 digits
        year_str = str(raw).strip()
        year_match = re.search(r'\d{4}', year_str)

        if not year_match:
            return None

        year_int = int(year_match.group())

        # Validate range (1450 = printing press invention to current year + 5 for upcoming books)
        current_year = datetime.now().year
        if 1450 <= year_int <= current_year + 5:
            return year_int

        return None

    except (ValueError, AttributeError):
        return None
