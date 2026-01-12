"""OPF metadata extraction utilities.

This module provides functions for extracting metadata from OPF (Open Packaging Format)
files commonly used in EPUB and other ebook formats for comprehensive metadata.
"""

import logging
import re

from lxml import etree as ET

from books.models import (
    BookMetadata,
    BookPublisher,
    BookSeries,
    BookTitle,
    DataSource,
    Publisher,
    Series,
)
from books.utils.author import attach_authors
from books.utils.isbn import normalize_isbn
from books.utils.language import normalize_language

logger = logging.getLogger("books.scanner")


def _get_opf_file_source():
    """Get or create the OPF File DataSource."""
    source, created = DataSource.objects.get_or_create(name=DataSource.OPF_FILE, defaults={"trust_level": 0.9})
    return source


def extract(book):
    try:
        # Get the opf_path from the first BookFile
        book_file = book.files.first()
        if not book_file or not book_file.opf_path:
            return

        source = _get_opf_file_source()

        with open(book_file.opf_path, "r", encoding="utf-8") as f:
            root = ET.parse(f).getroot()

        ns = {
            "opf": "http://www.idpf.org/2007/opf",
            "dc": "http://purl.org/dc/elements/1.1/",
        }

        # Title
        title_elem = root.find(".//dc:title", ns)
        if title_elem is not None and title_elem.text:
            title_text = title_elem.text.strip()
            if title_text:  # Only create if non-empty after stripping
                BookTitle.objects.get_or_create(
                    book=book,
                    title=title_text,
                    source=source,
                    defaults={"confidence": source.trust_level},
                )

        # Authors
        creators = root.findall(".//dc:creator", ns)
        raw_names = [c.text.strip() for c in creators if c.text]
        attach_authors(book, raw_names, source, confidence=source.trust_level)

        # Publisher (handled separately from OPF .xml)
        pub_elem = root.find(".//dc:publisher", ns)
        if pub_elem is not None and pub_elem.text:
            pub_name = pub_elem.text.strip()
            if pub_name:  # Only create if non-empty after stripping
                existing_pub = Publisher.objects.filter(name__iexact=pub_name).first()
                if existing_pub:
                    pub_obj = existing_pub
                else:
                    pub_obj = Publisher.objects.create(name=pub_name)

                BookPublisher.objects.get_or_create(
                    book=book,
                    publisher=pub_obj,
                    source=source,
                    defaults={"confidence": source.trust_level},
                )

        # Series metadata (Calibre-style)
        series_name_elem = root.find('.//opf:meta[@name="calibre:series"]', ns)
        series_index_elem = root.find('.//opf:meta[@name="calibre:series_index"]', ns)

        if series_name_elem is not None and series_name_elem.get("content"):
            series_name = series_name_elem.get("content").strip()
            volume = None
            if series_index_elem is not None and series_index_elem.get("content"):
                volume = series_index_elem.get("content").strip()

            series_obj, _ = Series.objects.get_or_create(name=series_name)
            BookSeries.objects.get_or_create(
                book=book,
                series=series_obj,
                defaults={
                    "series_number": volume,
                    "confidence": source.trust_level,
                    "source": source,
                },
            )

        # Field extraction
        field_map = {
            "language": "language",
            "identifier": "isbn",
            "description": "description",
            "date": "publication_year",
        }

        for dc_field, model_field in field_map.items():
            elem = root.find(f".//dc:{dc_field}", ns)
            if elem is not None and elem.text:
                value = elem.text.strip()
                if not value:
                    continue
                if model_field == "language":
                    value = normalize_language(value)
                    if value:  # Only create if normalization succeeded
                        BookMetadata.objects.get_or_create(
                            book=book,
                            field_name=model_field,
                            source=source,
                            defaults={
                                "field_value": value,
                                "confidence": source.trust_level,
                            },
                        )
                elif model_field == "isbn":
                    value = normalize_isbn(value)
                    if value:  # Only create if normalization succeeded
                        BookMetadata.objects.get_or_create(
                            book=book,
                            field_name=model_field,
                            source=source,
                            defaults={
                                "field_value": value,
                                "confidence": source.trust_level,
                            },
                        )
                elif model_field == "publication_year":
                    match = re.search(r"\b\d{4}\b", value)
                    if match:
                        BookMetadata.objects.get_or_create(
                            book=book,
                            field_name=model_field,
                            source=source,
                            defaults={
                                "field_value": match.group(),
                                "confidence": source.trust_level,
                            },
                        )
                else:
                    BookMetadata.objects.get_or_create(
                        book=book,
                        field_name=model_field,
                        source=source,
                        defaults={
                            "field_value": value,
                            "confidence": source.trust_level,
                        },
                    )

    except Exception as e:
        book_file = book.files.first()
        opf_path = book_file.opf_path if book_file else "unknown"
        logger.warning(f"OPF metadata extraction failed for {opf_path}: {e}")
