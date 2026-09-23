"""Metadata resolution and confidence scoring.

This module provides functions for resolving final metadata from multiple
sources and calculating confidence scores for metadata accuracy.
"""

import logging
import re

from books.models import DataSource, FinalMetadata, UnresolvedReason

from books.utils.language import detect_language

logger = logging.getLogger("books.scanner")


def resolve_final_metadata(book):
    """Generate final metadata suggestions for a book"""
    final_metadata, _ = FinalMetadata.objects.get_or_create(book=book)

    # A human-reviewed book's manual edits must survive any automatic
    # (re)resolution — a rescan must never overwrite them.
    if getattr(final_metadata, "is_reviewed", False):
        return final_metadata

    # Title
    best_title = book.titles.filter(is_active=True).order_by("-confidence").first()
    if best_title:
        final_metadata.final_title = best_title.title
        final_metadata.final_title_confidence = best_title.confidence

    # Author
    best_author = book.author_relationships.filter(is_active=True).order_by("-confidence", "-is_main_author").first()
    if best_author:
        final_metadata.final_author = best_author.author.name
        final_metadata.final_author_confidence = best_author.confidence

    # Series
    best_series = book.series_relationships.filter(is_active=True).order_by("-confidence").first()
    if best_series:
        final_metadata.final_series = best_series.series.name
        final_metadata.final_series_number = str(best_series.series_number) if best_series.series_number is not None else ""
        final_metadata.final_series_confidence = best_series.confidence

    # Cover
    best_cover = book.covers.filter(is_active=True).order_by("-confidence", "-is_high_resolution", "-width").first()
    if best_cover and best_cover.cover_path:
        final_metadata.final_cover_path = best_cover.cover_path
        final_metadata.final_cover_confidence = best_cover.confidence
        final_metadata.has_cover = True
    else:
        final_metadata.has_cover = False

    # Publisher
    best_pub = book.publisher_relationships.filter(is_active=True).order_by("-confidence").first()
    if best_pub:
        final_metadata.final_publisher = best_pub.publisher.name
        final_metadata.final_publisher_confidence = best_pub.confidence

    # Additional metadata (language handled explicitly below)
    metadata_fields = {
        "isbn": "isbn",
        "publication_year": "publication_year",
        "description": "description",
    }

    for field_name, attr_name in metadata_fields.items():
        best_metadata = book.metadata.filter(field_name=field_name).filter(is_active=True).order_by("-confidence").first()
        if best_metadata:
            value = best_metadata.field_value
            if field_name == "publication_year":
                try:
                    # Handles strings like "1998", "circa 2005", "Published in 2012"
                    year_match = re.search(r"\b(18|19|20)\d{2}\b", str(value))
                    if year_match:
                        year = int(year_match.group())
                        if 1000 < year <= 2100:  # sanity check
                            final_metadata.publication_year = year
                        else:
                            logger.warning(f"[YEAR OUT OF RANGE] Parsed year '{year}' from '{value}'")
                    else:
                        logger.warning(f"[YEAR PARSE FAIL] No valid year found in '{value}'")
                except Exception as e:
                    logger.warning(f"[YEAR CAST ERROR] field_value='{value}' — {e}")
            else:
                setattr(final_metadata, attr_name, value)

    # Explicit language recording: detect from embedded/external metadata
    # first, then inherit from the scan folder, normalized to a canonical code.
    detected_language = detect_language(book)
    if detected_language:
        final_metadata.language = detected_language
        logger.info(f"[LANGUAGE DETECTED] Book {book.id} -> '{detected_language}'")

    # Confidence aggregation
    final_metadata.calculate_overall_confidence()
    final_metadata.save()

    # Flag books no external source resolved (routing: "flag what neither
    # source resolves").
    finalize_unresolved_reason(book)


EXTERNAL_SOURCE_NAMES = (
    DataSource.OPEN_LIBRARY,
    DataSource.GOOGLE_BOOKS,
    DataSource.COMICVINE,
)


def finalize_unresolved_reason(book):
    """Set NEITHER_SOURCE once all sources are exhausted.

    After external lookup + resolution, a book that still has no metadata from
    any external source (and no more-specific flag like UNCERTAIN / NO_MATCH /
    UNMAPPED_SERIES) was resolved by neither source, so it is flagged for the
    review queue.
    """
    final_metadata = FinalMetadata.objects.filter(book=book).first()
    if final_metadata is None or final_metadata.unresolved_reason:
        # No record to flag, or a more specific reason already set.
        return

    external_sources = DataSource.objects.filter(name__in=EXTERNAL_SOURCE_NAMES)
    has_external_title = book.titles.filter(source__in=external_sources, is_active=True).exists()
    has_external_author = book.author_relationships.filter(source__in=external_sources, is_active=True).exists()
    if not (has_external_title or has_external_author):
        final_metadata.unresolved_reason = UnresolvedReason.NEITHER_SOURCE
        final_metadata.save(update_fields=["unresolved_reason"])
        logger.info(f"[NEITHER SOURCE] Book {book.id} unresolved by any external source")
