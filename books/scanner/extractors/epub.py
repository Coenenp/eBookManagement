from django.db import IntegrityError
from ebooklib import epub
from books.models import DataSource, BookTitle, Publisher, BookPublisher, BookMetadata
from books.utils.language import normalize_language
from books.utils.isbn import normalize_isbn
from books.utils.author import attach_authors
import logging

logger = logging.getLogger('books.scanner')


def extract(book):
    try:
        epub_book = epub.read_epub(book.file_path)
        source = DataSource.objects.get(name=DataSource.EPUB_INTERNAL)

        # Title
        titles = epub_book.get_metadata('DC', 'title')
        if titles:
            BookTitle.objects.get_or_create(
                book=book,
                title=titles[0][0],
                source=source,
                defaults={'confidence': 0.9}
            )

        # Authors
        creators = epub_book.get_metadata('DC', 'creator')
        raw_names = [c[0] for c in creators if c and c[0]]
        attach_authors(book, raw_names, source, confidence=0.9)

        # Publisher
        publishers = epub_book.get_metadata('DC', 'publisher')
        if publishers:
            raw_publisher = publishers[0][0].strip()
            normalized_name = raw_publisher.lower()

            existing = Publisher.objects.filter(name__iexact=normalized_name).first()
            publisher_obj = existing or Publisher.objects.create(name=raw_publisher)

            try:
                BookPublisher.objects.get_or_create(
                    book=book,
                    publisher=publisher_obj,
                    source=source,
                    defaults={'confidence': 0.8}
                )
            except IntegrityError as e:
                logger.warning(f"Duplicate BookPublisher skipped: {e}")

        # Other fields
        fields = [
            ('language', normalize_language),
            ('identifier', normalize_isbn),
            ('description', lambda x: x[:1000])  # truncate long descriptions
        ]

        for dc_field, normalizer in fields:
            values = epub_book.get_metadata('DC', dc_field)
            if values:
                raw_value = values[0][0].strip()
                field_value = normalizer(raw_value) if callable(normalizer) else raw_value
                if not field_value:
                    continue
                BookMetadata.objects.get_or_create(
                    book=book,
                    field_name=dc_field if dc_field != 'identifier' else 'isbn',
                    source=source,
                    defaults={'field_value': field_value, 'confidence': 0.8}
                )

    except Exception as e:
        logger.warning(f"EPUB metadata extraction failed for {book.file_path}: {e}")
