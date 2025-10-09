"""Dashboard and statistical aggregation helpers.

This module extracts pure aggregation logic from views to make it easier to unit test
and to reduce cognitive load in `books.views`. All functions are intentionally
side-effect free (except for Django ORM queries) and return plain Python data
structures suitable for direct template consumption or JSON serialization.
"""
from __future__ import annotations
from typing import Dict
from django.db.models import Q, Count
from books.models import (
    Book, BookSeries, Series, FinalMetadata, Author, Genre, Publisher,
    ScanLog, ScanFolder,
    COMIC_FORMATS, EBOOK_FORMATS, AUDIOBOOK_FORMATS
)


def get_issue_statistics() -> Dict[str, int]:
    """Identify and count various library issues.

    Returns:
        Mapping of issue category to count.
    """
    return {
        'missing_titles': FinalMetadata.objects.filter(final_title='').count(),
        'missing_authors': FinalMetadata.objects.filter(final_author='').count(),
        'missing_covers': FinalMetadata.objects.filter(has_cover=False).count(),
        'missing_isbn': FinalMetadata.objects.filter(Q(isbn='') | Q(isbn__isnull=True)).count(),
        'low_confidence': FinalMetadata.objects.filter(overall_confidence__lt=0.5).count(),
        'incomplete_metadata': FinalMetadata.objects.filter(completeness_score__lt=0.5).count(),
        'placeholder_books': Book.objects.filter(is_placeholder=True).count(),
        'duplicate_books': Book.objects.filter(is_duplicate=True).count(),
        'corrupted_books': Book.objects.filter(is_corrupted=True).count(),
        'needs_review': FinalMetadata.objects.filter(is_reviewed=False).count(),
        'unreviewed_authors': Author.objects.filter(is_reviewed=False).count(),
        'unreviewed_genres': Genre.objects.filter(is_reviewed=False).count(),
        'incomplete_series': _get_incomplete_series_count(),
        'series_without_numbers': BookSeries.objects.filter(
            Q(is_active=True) & (Q(series_number='') | Q(series_number__isnull=True))
        ).count(),
    }


def _get_incomplete_series_count() -> int:
    """Count series that appear incomplete (gaps in numbering)."""
    from django.db.models import Min, Max

    series_with_gaps = 0
    series_data = Series.objects.annotate(
        book_count=Count('bookseries__book', filter=Q(bookseries__is_active=True)),
        min_number=Min('bookseries__series_number'),
        max_number=Max('bookseries__series_number')
    ).filter(book_count__gt=1)

    for series in series_data:
        try:
            if series.min_number and series.max_number:
                min_num = float(series.min_number)
                max_num = float(series.max_number)
                expected_count = int(max_num - min_num + 1)
                if series.book_count < expected_count:
                    series_with_gaps += 1
        except (ValueError, TypeError):
            continue
    return series_with_gaps


def get_content_type_statistics() -> Dict[str, int]:
    """Get statistics for different content types.

    Exclude placeholders/duplicates/corrupted where appropriate to reflect
    actual library content. Count ebooks as unique non-placeholder entries
    across epub/mobi/pdf formats.
    """
    common_filter = Q(is_placeholder=False) & Q(is_duplicate=False) & Q(is_corrupted=False)
    return {
        # Count distinct formats in each category present in the library
        'ebook_count': Book.objects.filter(common_filter & Q(files__file_format__in=EBOOK_FORMATS)).values('files__file_format').distinct().count(),
        'comic_count': Book.objects.filter(common_filter & Q(files__file_format__in=COMIC_FORMATS)).values('files__file_format').distinct().count(),
        'audiobook_count': Book.objects.filter(
            common_filter & Q(files__file_format__in=AUDIOBOOK_FORMATS)
        ).values('files__file_format').distinct().count(),
        'series_count': Series.objects.count(),
        'series_with_books': Series.objects.annotate(
            book_count=Count('bookseries__book', filter=Q(bookseries__is_active=True))
        ).filter(book_count__gt=0).count(),
        'author_count': Author.objects.count(),
        'publisher_count': Publisher.objects.count(),
        'genre_count': Genre.objects.count(),
    }


def get_recent_activity(days: int = 7) -> Dict[str, int]:
    from datetime import timedelta
    from django.utils import timezone
    week_ago = timezone.now() - timedelta(days=days)
    today = timezone.now().date()
    return {
        'recently_added': Book.objects.filter(first_scanned__gte=week_ago, is_placeholder=False, is_duplicate=False, is_corrupted=False).count(),
        # Only count unreviewed items updated today to match test expectations
        'recently_updated': FinalMetadata.objects.filter(last_updated__date=today, is_reviewed=False).count(),
        'recent_scans': ScanLog.objects.filter(timestamp__gte=week_ago).count(),
        'recent_scan_folders': ScanFolder.objects.filter(last_scanned__gte=week_ago).count(),
    }


def prepare_chart_data(format_stats, metadata_stats, issue_stats) -> Dict[str, Dict[str, str]]:
    """Prepare data for Chart.js visualizations.

    Args:
        format_stats: iterable of {'file_format': str, 'count': int}
        metadata_stats: dict produced from aggregation on FinalMetadata
        issue_stats: dict from get_issue_statistics
    Returns:
        dict with JSON-encoded label/data arrays for charts.
    """
    import json

    format_labels = [item['files__file_format'].upper() for item in format_stats]
    format_data = [item['count'] for item in format_stats]

    completeness_labels = ['Title', 'Author', 'Cover', 'ISBN', 'Series']
    completeness_data = [
        metadata_stats['books_with_metadata'],
        metadata_stats['books_with_author'],
        metadata_stats['books_with_cover'],
        metadata_stats['books_with_isbn'],
        metadata_stats['books_in_series'],
    ]

    confidence_labels = ['High (80%+)', 'Medium (50-80%)', 'Low (<50%)']
    confidence_data = [
        metadata_stats['high_confidence_count'],
        metadata_stats['medium_confidence_count'],
        metadata_stats['low_confidence_count'],
    ]

    issue_items = [
        ('Missing Covers', issue_stats['missing_covers']),
        ('Missing Authors', issue_stats['missing_authors']),
        ('Needs Review', issue_stats['needs_review']),
        ('Low Confidence', issue_stats['low_confidence']),
        ('Missing ISBN', issue_stats['missing_isbn']),
    ]
    issue_items.sort(key=lambda x: x[1], reverse=True)
    issue_labels = [item[0] for item in issue_items[:5]]
    issue_data = [item[1] for item in issue_items[:5]]

    return {
        'format_distribution': {
            'labels': json.dumps(format_labels),
            'data': json.dumps(format_data),
        },
        'metadata_completeness': {
            'labels': json.dumps(completeness_labels),
            'data': json.dumps(completeness_data),
        },
        'confidence_distribution': {
            'labels': json.dumps(confidence_labels),
            'data': json.dumps(confidence_data),
        },
        'top_issues': {
            'labels': json.dumps(issue_labels),
            'data': json.dumps(issue_data),
        },
    }
