"""Author name processing utilities.

This module provides functions for parsing, normalizing, and handling
author names including split operations and database lookups.
"""

import logging

from django.db import models

from books.models import Author, BookAuthor
from books.utils.authors import normalize_author_name

logger = logging.getLogger("books.scanner")


def split_author_parts(raw_name):
    """Returns a tuple (first_name, last_name) from a raw author name"""
    if not raw_name or not raw_name.strip():
        return "", ""

    parts = raw_name.strip().replace(",", "").split()
    if not parts:  # Handle case where only whitespace/commas
        return "", ""

    if "," in raw_name and len(parts) >= 2:
        # Last, First format
        return " ".join(parts[1:]), parts[0]
    elif len(parts) == 1:
        return parts[0], ""  # Single name goes to first_name
    else:
        return " ".join(parts[:-1]), parts[-1]


def attach_authors(book, raw_names, source, confidence=0.8):
    for i, raw_name in enumerate(raw_names[:3]):
        raw_name = raw_name.strip()

        first, last = split_author_parts(raw_name)
        name_normalized = normalize_author_name(f"{first} {last}")

        # Try to match by normalized name or by first+last directly
        author = Author.objects.filter(models.Q(name_normalized=name_normalized) | models.Q(first_name__iexact=first.strip(), last_name__iexact=last.strip())).first()

        if not author:
            author = Author(name=raw_name, first_name=first.strip(), last_name=last.strip())
            author.save()
            logger.info(f"[AUTHOR CREATED] {raw_name} , normalized as '{author.name_normalized}'")

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
