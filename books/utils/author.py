"""Author name processing utilities.

This module provides functions for parsing, normalizing, and handling
author names including split operations and database lookups.
"""

import logging

from django.db import models

from books.models import Author, BookAuthor
from books.utils.authors import clean_author_name, normalize_author_name
from books.utils.surname_particles import split_author

logger = logging.getLogger("books.scanner")


def split_author_parts(raw_name):
    """Returns a tuple (first_name, last_name) from a raw author name."""
    return split_author(raw_name)


def attach_authors(book, raw_names, source, confidence=0.8):
    """
    Attach authors to a book, cleaning and validating names from any source.

    Args:
        book: Book instance
        raw_names: List of raw author name strings
        source: DataSource instance
        confidence: Confidence score for this metadata
    """
    for i, raw_name in enumerate(raw_names[:3]):
        raw_name = raw_name.strip()

        # Clean the author name (remove dates, normalize formatting)
        cleaned_name = clean_author_name(raw_name)

        # Skip if cleaning resulted in empty/invalid name
        if not cleaned_name or len(cleaned_name) < 2:
            logger.warning(f"[AUTHOR REJECTED] Invalid author name: '{raw_name}' (cleaned: '{cleaned_name}')")
            continue

        first, last = split_author_parts(cleaned_name)
        name_normalized = normalize_author_name(f"{first} {last}")

        # Try to match by normalized name or by first+last directly
        author = Author.objects.filter(models.Q(name_normalized=name_normalized) | models.Q(first_name__iexact=first.strip(), last_name__iexact=last.strip())).first()

        if not author:
            author = Author(name=cleaned_name, first_name=first.strip(), last_name=last.strip())
            author.save()
            logger.info(f"[AUTHOR CREATED] {cleaned_name} (from raw: '{raw_name}'), normalized as '{author.name_normalized}'")
        elif raw_name != cleaned_name:
            # Log when we cleaned a problematic name
            logger.info(f"[AUTHOR CLEANED] '{raw_name}' -> '{cleaned_name}' (matched existing author: {author.name})")

        BookAuthor.objects.update_or_create(
            book=book,
            author=author,
            source=source,
            defaults={
                "confidence": confidence,
                "is_main_author": i == 0,
                "is_active": True,
            },
        )
