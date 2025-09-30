"""Query construction helpers for book listings and navigation.

This module centralizes queryset building so views stay thin and logic
can be unit tested in isolation. Functions accept primitive parameters
or dicts (e.g. request.GET) rather than HttpRequest objects.
"""
from __future__ import annotations
from typing import Dict, Any
from django.db.models import Q, QuerySet
from books.models import Book


REVIEW_TYPE_FILTERS = {
    'needs_review': Q(finalmetadata__is_reviewed=False) | Q(finalmetadata__is_reviewed__isnull=True) | Q(finalmetadata__isnull=True),
    'low_confidence': Q(finalmetadata__overall_confidence__lt=0.5),
    'incomplete': Q(finalmetadata__completeness_score__lt=0.5),
    'missing_cover': Q(finalmetadata__has_cover=False) | Q(finalmetadata__isnull=True),
    'duplicates': Q(is_duplicate=True),
    'placeholders': Q(is_placeholder=True),
    'corrupted': Q(is_corrupted=True),
}

SORT_FIELDS = {
    'title': 'finalmetadata__final_title',
    'author': 'finalmetadata__final_author',
    'confidence': 'finalmetadata__overall_confidence',
    'completeness': 'finalmetadata__completeness_score',
    'last_scanned': 'last_scanned',
    'format': 'file_format',
    'size': 'file_size',
    'path': 'file_path',
    'reviewed': 'finalmetadata__is_reviewed',
}


def base_book_queryset() -> QuerySet:
    return Book.objects.select_related('finalmetadata', 'scan_folder').prefetch_related(
        'titles__source',
        'bookauthor__author', 'bookauthor__source',
        'bookgenre__genre', 'bookgenre__source',
        'series_info__series', 'series_info__source'
    )


def apply_review_type_filter(qs: QuerySet, review_type: str | None) -> QuerySet:
    if review_type in REVIEW_TYPE_FILTERS:
        return qs.filter(REVIEW_TYPE_FILTERS[review_type])
    return qs


def apply_standard_filters(qs: QuerySet, params: Dict[str, Any]) -> QuerySet:
    search = params.get('search_query')
    if search:
        qs = qs.filter(
            Q(titles__title__icontains=search) |
            Q(bookauthor__author__name__icontains=search) |
            Q(finalmetadata__final_title__icontains=search) |
            Q(finalmetadata__final_author__icontains=search) |
            Q(finalmetadata__final_series__icontains=search) |
            Q(finalmetadata__final_publisher__icontains=search) |
            Q(file_path__icontains=search)
        ).distinct()

    # Simple key/value filters
    if (lang := params.get('language')):
        if lang.strip():
            qs = qs.filter(finalmetadata__language=lang)
    if (fmt := params.get('file_format')):
        if fmt.strip():
            qs = qs.filter(file_format=fmt)

    # Boolean-style flags
    placeholder = params.get('has_placeholder')
    if placeholder == 'true':
        qs = qs.filter(is_placeholder=True)
    elif placeholder == 'false':
        qs = qs.filter(is_placeholder=False)

    corrupted = params.get('corrupted')
    if corrupted == 'true':
        qs = qs.filter(is_corrupted=True)
    elif corrupted == 'false':
        qs = qs.filter(is_corrupted=False)

    # Needs review composite condition
    needs_review = params.get('needs_review')
    if needs_review == 'true':
        qs = qs.filter(Q(finalmetadata__is_reviewed=False) | Q(finalmetadata__is_reviewed__isnull=True) | Q(finalmetadata__isnull=True))
    elif needs_review == 'false':
        qs = qs.filter(finalmetadata__is_reviewed=True)

    # Confidence buckets
    confidence = params.get('confidence')
    if confidence == 'high':
        qs = qs.filter(finalmetadata__overall_confidence__gte=0.8)
    elif confidence == 'medium':
        qs = qs.filter(finalmetadata__overall_confidence__gte=0.5, finalmetadata__overall_confidence__lt=0.8)
    elif confidence == 'low':
        qs = qs.filter(finalmetadata__overall_confidence__lt=0.5)

    # Missing metadata filters
    missing = params.get('missing')
    missing_map = {
        'title': Q(finalmetadata__final_title__isnull=True) | Q(finalmetadata__final_title__exact=''),
        'author': Q(finalmetadata__final_author__isnull=True) | Q(finalmetadata__final_author__exact=''),
        'cover': Q(finalmetadata__final_cover_path__isnull=True) | Q(finalmetadata__final_cover_path__exact=''),
        'series': Q(finalmetadata__final_series__isnull=True) | Q(finalmetadata__final_series__exact=''),
        'publisher': Q(finalmetadata__final_publisher__isnull=True) | Q(finalmetadata__final_publisher__exact=''),
        'metadata': Q(finalmetadata__isnull=True),
    }
    if missing in missing_map:
        qs = qs.filter(missing_map[missing])

    # Datasource filter by ID or name (flexible)
    datasource = params.get('datasource')
    if datasource and datasource.strip():
        qs = qs.filter(
            Q(titles__source_id=datasource) |
            Q(bookauthor__source_id=datasource) |
            Q(covers__source_id=datasource) |
            Q(series_info__source_id=datasource) |
            Q(bookpublisher__source_id=datasource) |
            Q(bookgenre__source_id=datasource) |
            Q(metadata__source_id=datasource)
        ).distinct()

    # Scan folder filter
    scan_folder = params.get('scan_folder')
    if scan_folder and scan_folder.strip():
        qs = qs.filter(scan_folder_id=scan_folder)

    return qs


def apply_sorting(qs: QuerySet, sort: str | None, order: str | None) -> QuerySet:
    field = SORT_FIELDS.get(sort or 'last_scanned', 'last_scanned')
    prefix = '-' if (order or 'desc') == 'desc' else ''
    return qs.order_by(f'{prefix}{field}')


def build_book_queryset(params: Dict[str, Any]) -> QuerySet:
    """Compose full queryset following the same rules as the original view code."""
    qs = base_book_queryset()
    qs = apply_review_type_filter(qs, params.get('review_type'))
    qs = apply_standard_filters(qs, params)
    qs = apply_sorting(qs, params.get('sort'), params.get('order'))
    return qs
