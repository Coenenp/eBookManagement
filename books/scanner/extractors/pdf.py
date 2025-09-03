"""PDF metadata extraction utilities.

This module provides functions for extracting metadata from PDF files
including title, author, and document properties.
"""
from PyPDF2 import PdfReader
from books.models import DataSource, BookTitle, BookMetadata
from books.utils.author import attach_authors
import logging

logger = logging.getLogger("books.scanner")


def extract(book):
    try:
        reader = PdfReader(book.file_path)
        source = DataSource.objects.get(name=DataSource.PDF_INTERNAL)
        meta = reader.metadata

        if meta.title:
            BookTitle.objects.get_or_create(
                book=book,
                title=meta.title.strip(),
                source=source,
                defaults={'confidence': source.trust_level}
            )

        if meta.author:
            raw_names = [meta.author.strip()]
            attach_authors(book, raw_names, source, confidence=source.trust_level)

        if meta.creator:
            BookMetadata.objects.get_or_create(
                book=book,
                field_name='creator',
                source=source,
                defaults={'field_value': meta.creator.strip(), 'confidence': source.trust_level}
            )

    except Exception as e:
        logger.warning(f"PDF metadata extraction failed for {book.file_path}: {e}")
