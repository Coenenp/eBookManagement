"""EPUB metadata extraction utilities.

This module provides functions for extracting metadata from EPUB files
including title, author, publisher, language, and ISBN information.
"""

import logging

from django.db import IntegrityError
from ebooklib import epub

from books.models import BookMetadata, BookPublisher, BookTitle, DataSource, Publisher
from books.utils.author import attach_authors
from books.utils.isbn import normalize_isbn
from books.utils.language import normalize_language

logger = logging.getLogger("books.scanner")


def _get_epub_internal_source():
    """Get or create the EPUB Internal DataSource."""
    source, created = DataSource.objects.get_or_create(
        name=DataSource.EPUB_INTERNAL, defaults={"trust_level": 0.8}
    )
    return source


def extract(book):
    try:
        epub_book = epub.read_epub(book.file_path)
        source = _get_epub_internal_source()

        # Title
        titles = epub_book.get_metadata("DC", "title")
        if titles and titles[0][0]:
            title_text = titles[0][0].strip()
            if title_text:  # Only create if non-empty after stripping
                BookTitle.objects.get_or_create(
                    book=book,
                    title=title_text,
                    source=source,
                    defaults={"confidence": source.trust_level},
                )

        # Authors
        creators = epub_book.get_metadata("DC", "creator")
        raw_names = [c[0] for c in creators if c and c[0]]
        attach_authors(book, raw_names, source, confidence=source.trust_level)

        # Publisher
        publishers = epub_book.get_metadata("DC", "publisher")
        if publishers and publishers[0][0]:
            raw_publisher = publishers[0][0].strip()
            if raw_publisher:  # Only create if non-empty after stripping
                normalized_name = raw_publisher.lower()

                existing = Publisher.objects.filter(
                    name__iexact=normalized_name
                ).first()
                publisher_obj = existing or Publisher.objects.create(name=raw_publisher)

                try:
                    BookPublisher.objects.get_or_create(
                        book=book,
                        publisher=publisher_obj,
                        source=source,
                        defaults={"confidence": source.trust_level},
                    )
                except IntegrityError as e:
                    logger.warning(f"Duplicate BookPublisher skipped: {e}")

        # Other fields
        fields = [
            ("language", normalize_language),
            ("identifier", normalize_isbn),
            ("description", lambda x: x[:1000]),  # truncate long descriptions
        ]

        for dc_field, normalizer in fields:
            values = epub_book.get_metadata("DC", dc_field)
            if values:
                raw_value = values[0][0].strip()
                field_value = (
                    normalizer(raw_value) if callable(normalizer) else raw_value
                )
                if not field_value:
                    continue
                BookMetadata.objects.get_or_create(
                    book=book,
                    field_name=dc_field if dc_field != "identifier" else "isbn",
                    source=source,
                    defaults={
                        "field_value": field_value,
                        "confidence": source.trust_level,
                    },
                )

    except Exception as e:
        logger.warning(f"EPUB metadata extraction failed for {book.file_path}: {e}")
