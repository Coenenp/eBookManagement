"""MOBI metadata extraction utilities.

This module provides functions for extracting metadata from MOBI files
including title, author, publisher, and other bibliographic information.
"""
import mobi
from django.db import IntegrityError
from books.utils.author import attach_authors
from books.models import DataSource, Publisher, BookPublisher, BookMetadata, BookTitle
import logging
import os
import json

logger = logging.getLogger("books.scanner")


def extract(book):
    try:
        # Extract the MOBI file
        tempdir, filepath = mobi.extract(book.file_path)

        metadata_file = os.path.join(tempdir, "metadata.json")
        metadata = {}

        if os.path.exists(metadata_file):
            with open(metadata_file, "r", encoding="utf-8") as f:
                metadata = json.load(f)
        else:
            logger.warning(f"No metadata.json found in {tempdir}")
            return None  # Graceful fallback

        # Pull metadata fields
        title = metadata.get("title")
        author = metadata.get("creator")
        encoding = metadata.get("encoding")
        publisher = metadata.get("publisher")

        logger.info(f"Title: {title or 'Unknown'}, Author: {author or 'Unknown'}, Encoding: {encoding or 'Unknown'}")

        # Get internal source
        source = DataSource.objects.get(name=DataSource.MOBI_INTERNAL)

        # Title
        if title:
            BookTitle.objects.get_or_create(
                book=book,
                title=title.strip(),
                source=source,
                defaults={'confidence': 0.9}
            )

        # Authors
        if author:
            attach_authors(book, [author], source, confidence=0.9)

        # Publisher
        if publisher:
            cleaned_name = publisher.strip()

            existing_pub = Publisher.objects.filter(name__iexact=cleaned_name).first()
            if existing_pub:
                pub_obj = existing_pub
            else:
                pub_obj = Publisher.objects.create(name=cleaned_name)
            try:
                BookPublisher.objects.get_or_create(
                    book=book,
                    publisher=pub_obj,
                    source=source,
                    defaults={'confidence': 0.8}
                )
            except IntegrityError as e:
                logger.warning(f"[BOOKPUBLISHER DUPLICATE] Could not create BookPublisher for {book.file_path}: {e}")

        # Optional fields to record
        optional_fields = {
            'encoding': encoding
        }

        for field, value in optional_fields.items():
            if value:
                BookMetadata.objects.get_or_create(
                    book=book,
                    field_name=field,
                    source=source,
                    defaults={'field_value': value.strip(), 'confidence': 0.8}
                )

        return {
            "title": title,
            "author": author,
            "encoding": encoding,
            "publisher": publisher,
            "source": source,
            "raw_metadata": metadata,
        }

    except Exception as e:
        logger.warning(f"MOBI metadata extraction failed for {book.file_path}: {e}")
        return None
