import re
import logging

from books.models import FinalMetadata

logger = logging.getLogger(__name__)


def resolve_final_metadata(book):
    """Generate final metadata suggestions for a book"""
    final_metadata, _ = FinalMetadata.objects.get_or_create(book=book)

    # 🖋️ Title
    best_title = book.titles.filter(is_active=True).order_by('-confidence').first()
    if best_title:
        final_metadata.final_title = best_title.title
        final_metadata.final_title_confidence = best_title.confidence

    # 👤 Author
    best_author = book.bookauthor.filter(is_active=True).order_by('-confidence', '-is_main_author').first()
    if best_author:
        final_metadata.final_author = best_author.author.name
        final_metadata.final_author_confidence = best_author.confidence

    # 📚 Series
    best_series = book.series_info.filter(is_active=True).order_by('-confidence').first()
    if best_series:
        final_metadata.final_series = best_series.series.name
        final_metadata.final_series_number = best_series.series_number if best_series.series_number is not None else 0
        final_metadata.final_series_confidence = best_series.confidence

    # 📕 Cover
    best_cover = book.covers.filter(is_active=True).order_by('-confidence', '-is_high_resolution', '-width').first()
    if best_cover and best_cover.cover_path:
        final_metadata.final_cover_path = best_cover.cover_path
        final_metadata.final_cover_confidence = best_cover.confidence
        final_metadata.has_cover = True
    else:
        final_metadata.has_cover = False

    # 🏢 Publisher
    best_pub = book.bookpublisher.filter(is_active=True).order_by('-confidence').first()
    if best_pub:
        final_metadata.final_publisher = best_pub.publisher.name
        final_metadata.final_publisher_confidence = best_pub.confidence

    # 📑 Additional metadata
    metadata_fields = {
        'language': 'language',
        'isbn': 'isbn',
        'publication_year': 'publication_year',
        'description': 'description',
    }

    for field_name, attr_name in metadata_fields.items():
        best_metadata = (
            book.metadata.filter(field_name=field_name)
            .filter(is_active=True)
            .order_by('-confidence')
            .first()
        )
        if best_metadata:
            value = best_metadata.field_value
            if field_name == 'publication_year':
                try:
                    # Handles strings like "1998", "circa 2005", "Published in 2012"
                    year_match = re.search(r'\b(18|19|20)\d{2}\b', str(value))
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

    # 🔢 Confidence aggregation
    final_metadata.calculate_overall_confidence()
    final_metadata.save()
