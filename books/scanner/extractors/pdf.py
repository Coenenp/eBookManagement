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
            title_text = meta.title.strip()
            if title_text:  # Only create if non-empty after stripping
                BookTitle.objects.get_or_create(
                    book=book,
                    title=title_text,
                    source=source,
                    defaults={'confidence': source.trust_level}
                )

        if meta.author:
            author_text = meta.author.strip()
            if author_text:  # Only create if non-empty after stripping
                raw_names = [author_text]
                attach_authors(book, raw_names, source, confidence=source.trust_level)

        if meta.creator:
            creator_text = meta.creator.strip()
            if creator_text:  # Only create if non-empty after stripping
                BookMetadata.objects.get_or_create(
                    book=book,
                    field_name='creator',
                    source=source,
                    defaults={'field_value': creator_text, 'confidence': source.trust_level}
                )

    except Exception as e:
        logger.warning(f"PDF metadata extraction failed for {book.file_path}: {e}")
