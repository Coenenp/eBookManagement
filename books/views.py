"""Django views for ebook library management.

This module contains views for book listing, detail display, metadata management,
cover handling, scanning operations, and administrative functions. Includes
both class-based and function-based views with comprehensive filtering and search.
"""
from django.shortcuts import render, get_object_or_404, redirect
from django.views.generic import View, ListView, DetailView, CreateView, DeleteView, TemplateView
from django.contrib import messages
from django.contrib.auth import authenticate, login
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy, reverse
from django.http import JsonResponse
from django.utils import timezone
from django.db.models import Q, Count, Avg
from django.db import transaction
from django.views.decorators.http import require_http_methods, require_POST
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from functools import wraps
from .models import (
    Book, ScanFolder, BookTitle, BookAuthor, Author, BookSeries, Series, BookCover, BookPublisher, Publisher,
    BookGenre, Genre, BookMetadata, FinalMetadata, ScanLog, DataSource, ScanStatus, LANGUAGE_CHOICES, FileOperation
)
from .forms import ScanFolderForm, BookSearchForm, MetadataReviewForm, UserRegisterForm
from .book_utils import (
    MetadataProcessor, CoverManager, GenreManager,
    MetadataResetter, BookStatusManager, MetadataConflictAnalyzer,
    MetadataRemover
)
from books.utils.image_utils import encode_cover_to_base64  # ,download_and_store_cover
import subprocess
import sys
import os
import logging
import json


logger = logging.getLogger('books.scanner')


def signup(request):
    if request.method == 'POST':
        form = UserRegisterForm(request.POST)
        if form.is_valid():
            form.save()
            user = authenticate(
                username=form.cleaned_data['username'],
                password=form.cleaned_data['password1']
            )

            if user is not None:
                login(request, user)
                return redirect('books:dashboard')
    else:
        form = UserRegisterForm()
    return render(request, 'books/signup.html', {'form': form})


class DashboardView(LoginRequiredMixin, TemplateView):
    """Main dashboard view with comprehensive statistics and overview"""
    template_name = 'books/dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Single optimized query with annotations
        metadata_qs = FinalMetadata.objects.select_related('book')
        first_review_target = metadata_qs.filter(is_reviewed=False).order_by('book__id').first()

        metadata_stats = FinalMetadata.objects.select_related('book').aggregate(
            total_books=Count('book'),
            books_with_metadata=Count('book', filter=~Q(final_title='')),
            books_with_isbn=Count('book', filter=Q(isbn__isnull=False)),
            books_in_series=Count('book', filter=Q(final_series__isnull=False)),
            books_with_cover=Count('book', filter=~Q(final_cover_path='')),
            missing_cover_count=Count('book', filter=Q(has_cover=False)),
            needs_review_count=Count('book', filter=Q(is_reviewed=False)),
            avg_confidence=Avg('overall_confidence'),
            avg_completeness=Avg('completeness_score'),
            high_confidence_count=Count('book', filter=Q(overall_confidence__gte=0.8)),
            medium_confidence_count=Count('book', filter=Q(overall_confidence__gte=0.5, overall_confidence__lt=0.8)),
            low_confidence_count=Count('book', filter=Q(overall_confidence__lt=0.5)),
        )

        # Additional Book model stats
        book_stats = Book.objects.aggregate(
            total_books=Count('id'),
            books_with_original_cover=Count('id', filter=~Q(cover_path='')),
            placeholder_count=Count('id', filter=Q(is_placeholder=True)),
            duplicate_count=Count('id', filter=Q(is_duplicate=True)),
            corrupted_count=Count('id', filter=Q(is_corrupted=True)),
        )

        # Merge stats and calculate percentages
        total_books = book_stats['total_books']
        context.update({
            **metadata_stats,
            **book_stats,
            'completion_percentage': (metadata_stats['books_with_metadata'] / total_books * 100) if total_books else 0,
            'books_with_isbn_percentage': (metadata_stats['books_with_isbn'] / total_books * 100) if total_books else 0,
            'books_in_series_percentage': (metadata_stats['books_in_series'] / total_books * 100) if total_books else 0,
            'cover_percentage': (metadata_stats['books_with_cover'] / total_books * 100) if total_books else 0,
            'missing_cover_percentage': (metadata_stats['missing_cover_count'] / total_books * 100) if total_books else 0,
            'needs_review_percentage': (metadata_stats['needs_review_count'] / total_books * 100) if total_books else 0,
            'books_with_original_cover_percentage': (book_stats['books_with_original_cover'] / total_books * 100) if total_books else 0,
            'placeholder_percentage': (book_stats['placeholder_count'] / total_books * 100) if total_books else 0,
            'duplicate_percentage': (book_stats['duplicate_count'] / total_books * 100) if total_books else 0,
            'corrupted_percentage': (book_stats['corrupted_count'] / total_books * 100) if total_books else 0,
        })

        # Metadata quality metrics
        metadata_stats = metadata_qs.aggregate(
            avg_confidence=Avg('overall_confidence'),
            avg_completeness=Avg('completeness_score'),
            high_confidence_count=Count('id', filter=Q(overall_confidence__gte=0.8)),
            medium_confidence_count=Count('id', filter=Q(overall_confidence__gte=0.5, overall_confidence__lt=0.8)),
            low_confidence_count=Count('id', filter=Q(overall_confidence__lt=0.5)),
        )
        context.update({
            'avg_confidence': (metadata_stats['avg_confidence'] or 0) * 100,
            'avg_completeness': (metadata_stats['avg_completeness'] or 0) * 100,
            'high_confidence_count': metadata_stats['high_confidence_count'],
            'medium_confidence_count': metadata_stats['medium_confidence_count'],
            'low_confidence_count': metadata_stats['low_confidence_count'],
        })

        # File format distribution
        format_stats = Book.objects.values('file_format').annotate(
            count=Count('id')
        ).order_by('-count')[:10]
        context['format_stats'] = format_stats

        # Recent activity
        context['recent_logs'] = ScanLog.objects.select_related('scan_folder').order_by('-timestamp')[:10]
        context['recent_books'] = Book.objects.select_related('finalmetadata').prefetch_related(
            'titles__source',
            'bookauthor__author',
        ).order_by('-last_scanned')[:10]

        for book in context['recent_books']:
            final_meta = book.final_metadata
            cover_path = final_meta.final_cover_path if final_meta else None
            if cover_path and not cover_path.startswith("http") and os.path.exists(cover_path):
                final_meta.cover_base64 = encode_cover_to_base64(cover_path)
            elif final_meta:
                final_meta.cover_base64 = None

        # Low confidence books needing attention
        context['low_confidence_books'] = metadata_qs.filter(
            overall_confidence__lt=0.5
        ).select_related('book')[:10]

        # Books needing review (include books without FinalMetadata)
        context['needs_review_books'] = Book.objects.filter(
            Q(finalmetadata__is_reviewed=False) | Q(finalmetadata__isnull=True)
        ).select_related('finalmetadata').prefetch_related(
            'titles__source',
            'bookauthor__author',
        )[:10]

        # Scan folder stats
        context['scan_folders'] = ScanFolder.objects.annotate(
            book_count=Count('book')
        ).order_by('path')

        # Errors & warnings
        context['error_count'] = ScanLog.objects.filter(level='ERROR').count()
        context['warning_count'] = ScanLog.objects.filter(level='WARNING').count()

        # First target for review
        context['first_review_target'] = first_review_target.book if first_review_target else None

        return context


class BookListView(LoginRequiredMixin, ListView):
    model = Book
    template_name = 'books/book_list.html'
    context_object_name = 'books'
    paginate_by = 50

    def get_queryset(self):
        queryset = self._get_base_queryset()
        queryset = self._apply_review_type_filter(queryset)
        queryset = self._apply_standard_filters(queryset)
        queryset = self._apply_sorting(queryset)
        return queryset

    def _get_base_queryset(self):
        return Book.objects.select_related(
            'finalmetadata',
            'scan_folder'
        ).prefetch_related(
            'titles__source',
            'bookauthor__author',
            'bookauthor__source',
            'bookgenre__genre',
            'bookgenre__source',
            'series_info__series',
            'series_info__source'
        )

    def _apply_review_type_filter(self, queryset):
        review_type = self.request.GET.get('review_type', '')
        filter_map = {
            # Handle books without FinalMetadata (during scanning) and those needing review
            'needs_review': Q(finalmetadata__is_reviewed=False) | Q(finalmetadata__is_reviewed__isnull=True) | Q(finalmetadata__isnull=True),
            'low_confidence': Q(finalmetadata__overall_confidence__lt=0.5),
            'incomplete': Q(finalmetadata__completeness_score__lt=0.5),
            'missing_cover': Q(finalmetadata__has_cover=False) | Q(finalmetadata__isnull=True),
            'duplicates': Q(is_duplicate=True),
            'placeholders': Q(is_placeholder=True),
            'corrupted': Q(is_corrupted=True),
        }
        if review_type in filter_map:
            queryset = queryset.filter(filter_map[review_type])
        return queryset

    def _apply_standard_filters(self, queryset):
        GET = self.request.GET

        if search := GET.get('search_query'):
            # Include books without FinalMetadata by searching their basic fields and file_path
            queryset = queryset.filter(
                Q(titles__title__icontains=search) |
                Q(bookauthor__author__name__icontains=search) |
                Q(finalmetadata__final_title__icontains=search) |
                Q(finalmetadata__final_author__icontains=search) |
                Q(finalmetadata__final_series__icontains=search) |
                Q(finalmetadata__final_publisher__icontains=search) |
                Q(file_path__icontains=search)
            ).distinct()

        filter_conditions = {}

        # Only add if non-empty
        if lang := GET.get('language'):
            if lang.strip():
                filter_conditions['language'] = {'finalmetadata__language': lang}

        if fmt := GET.get('file_format'):
            if fmt.strip():
                filter_conditions['file_format'] = {'file_format': fmt}

        # Assign these to variables first, then add to filter_conditions
        has_placeholder = {
            'true': {'is_placeholder': True},
            'false': {'is_placeholder': False}
        }.get(GET.get('has_placeholder'))

        if has_placeholder:
            filter_conditions['has_placeholder'] = has_placeholder

        needs_review = {
            # Include books without FinalMetadata (they definitely need review)
            'true': Q(finalmetadata__is_reviewed=False) | Q(finalmetadata__is_reviewed__isnull=True) | Q(finalmetadata__isnull=True),
            'false': Q(finalmetadata__is_reviewed=True)
        }.get(GET.get('needs_review'))

        if needs_review:
            filter_conditions['needs_review'] = needs_review

        corrupted = {
            'true': {'is_corrupted': True},
            'false': {'is_corrupted': False}
        }.get(GET.get('corrupted'))

        if corrupted:
            filter_conditions['corrupted'] = corrupted

        # Apply all filters
        for key, condition in filter_conditions.items():
            if condition:
                queryset = queryset.filter(**condition) if isinstance(condition, dict) else queryset.filter(condition)

        # Confidence filter
        confidence = GET.get('confidence')
        if confidence == 'high':
            queryset = queryset.filter(finalmetadata__overall_confidence__gte=0.8)
        elif confidence == 'medium':
            queryset = queryset.filter(
                finalmetadata__overall_confidence__gte=0.5,
                finalmetadata__overall_confidence__lt=0.8
            )
        elif confidence == 'low':
            queryset = queryset.filter(finalmetadata__overall_confidence__lt=0.5)

        # Missing metadata filter
        missing = GET.get('missing')
        missing_map = {
            'title': Q(finalmetadata__final_title__isnull=True) | Q(finalmetadata__final_title__exact=''),
            'author': Q(finalmetadata__final_author__isnull=True) | Q(finalmetadata__final_author__exact=''),
            'cover': Q(finalmetadata__final_cover_path__isnull=True) | Q(finalmetadata__final_cover_path__exact=''),
            'series': Q(finalmetadata__final_series__isnull=True) | Q(finalmetadata__final_series__exact=''),
            'publisher': Q(finalmetadata__final_publisher__isnull=True) | Q(finalmetadata__final_publisher__exact=''),
            'metadata': Q(finalmetadata__isnull=True),
        }
        if missing in missing_map:
            queryset = queryset.filter(missing_map[missing])

        return queryset

    def _apply_sorting(self, queryset):
        sort_by = self.request.GET.get('sort', 'last_scanned')
        sort_order = self.request.GET.get('order', 'desc')
        sort_fields = {
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

        field = sort_fields.get(sort_by, 'last_scanned')
        prefix = '-' if sort_order == 'desc' else ''
        return queryset.order_by(f'{prefix}{field}')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        metadata_qs = FinalMetadata.objects.select_related('book')

        context['search_form'] = BookSearchForm(data=self.request.GET or None)

        context.update({
            'total_books': Book.objects.count(),
            'placeholder_count': Book.objects.filter(is_placeholder=True).count(),
            'needs_review_count': metadata_qs.filter(is_reviewed=False).count(),
            'missing_cover_count': metadata_qs.filter(has_cover=False).count(),
            'duplicate_count': Book.objects.filter(is_duplicate=True).count(),
            'corrupted_count': Book.objects.filter(is_corrupted=True).count(),
            'isbn_count': metadata_qs.filter(isbn__isnull=False).count(),
            'search_query': self.request.GET.get('search_query', ''),
            'language_filter': self.request.GET.get('language', ''),
            'format_filter': self.request.GET.get('file_format', ''),
            'confidence_filter': self.request.GET.get('confidence', ''),
            'corrupted_filter': self.request.GET.get('corrupted', ''),
            'missing_filter': self.request.GET.get('missing', ''),
            'sort_by': self.request.GET.get('sort', 'last_scanned'),
            'sort_order': self.request.GET.get('order', 'desc'),
            'review_type': self.request.GET.get('review_type', ''),
            'query_params': self.request.GET.copy(),
        })

        books = context.get('object_list', [])  # or use context['page_obj'] if paginated
        processed = []

        for book in books:
            # Safely get cover path, handling books without finalmetadata
            try:
                cover_path = getattr(book.finalmetadata, 'final_cover_path', '') or book.cover_path
            except Exception:
                cover_path = book.cover_path

            is_url = str(cover_path).startswith("http")
            base64_image = encode_cover_to_base64(cover_path) if cover_path and not is_url else None

            processed.append({
                "book": book,
                "cover_path": cover_path,
                "cover_base64": base64_image,
            })

        context["books_with_covers"] = processed

        if 'page' in context['query_params']:
            del context['query_params']['page']

        context['formats'] = Book.objects.values_list('file_format', flat=True).distinct().order_by('file_format')

        # Get all language values from database and filter to only valid ISO codes
        all_languages = FinalMetadata.objects.values_list('language', flat=True).distinct()
        valid_language_codes = [code for code, name in LANGUAGE_CHOICES]
        used_languages = [lang for lang in all_languages if lang in valid_language_codes]

        # Create language choices for template - only include languages actually used in the database
        lang_dict = dict(LANGUAGE_CHOICES)
        context['languages'] = [(code, lang_dict[code]) for code in used_languages if code in lang_dict]

        metadata_stats = FinalMetadata.objects.aggregate(
            avg_confidence=Avg('overall_confidence'),
            avg_completeness=Avg('completeness_score')
        )
        context['avg_confidence'] = (metadata_stats['avg_confidence'] or 0) * 100
        context['avg_completeness'] = (metadata_stats['avg_completeness'] or 0) * 100

        context['review_counts'] = {
            'needs_review': Book.objects.filter(finalmetadata__is_reviewed__in=[False, None]).count(),
            'low_confidence': Book.objects.filter(finalmetadata__overall_confidence__lt=0.5).count(),
            'incomplete': Book.objects.filter(finalmetadata__completeness_score__lt=0.5).count(),
            'missing_cover': Book.objects.filter(finalmetadata__has_cover=False).count(),
            'duplicates': Book.objects.filter(is_duplicate=True).count(),
            'placeholders': Book.objects.filter(is_placeholder=True).count(),
        }

        context['first_review_target'] = Book.objects.filter(finalmetadata__is_reviewed__in=[False, None]).order_by('id').first()

        context['review_tabs'] = [
            ('needs_review', 'Needs Review', context['review_counts']['needs_review'], 'primary'),
            ('low_confidence', 'Low Confidence', context['review_counts']['low_confidence'], 'warning'),
            ('incomplete', 'Incomplete', context['review_counts']['incomplete'], 'info'),
            ('missing_cover', 'Missing Cover', context['review_counts']['missing_cover'], 'secondary'),
            ('duplicates', 'Duplicates', context['review_counts']['duplicates'], 'light'),
            ('placeholders', 'Placeholders', context['review_counts']['placeholders'], 'dark'),
            ('corrupted', 'Corrupted', context['corrupted_count'], 'danger'),
        ]

        return context


class BookDetailView(LoginRequiredMixin, DetailView):
    model = Book
    template_name = 'books/book_detail.html'
    context_object_name = 'book'

    def get_object(self):
        # Only prefetch what's immediately needed
        return get_object_or_404(
            Book.objects.select_related(
                'finalmetadata',
                'scan_folder'
            ),
            pk=self.kwargs['pk']
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        book = self.object

        if self.request.GET.get('tab') == 'edit':
            # Full prefetch only for edit mode
            book = Book.objects.prefetch_related(
                'titles__source',
                'bookauthor__author',
                'bookauthor__source',
                'bookgenre__genre',
                'bookgenre__source',
                'series_info__series',
                'series_info__source',
                'bookpublisher__publisher',
                'bookpublisher__source',
                'metadata__source',
                'covers__source'
            ).get(pk=book.pk)

        # Get or create final metadata
        final_metadata, created = FinalMetadata.objects.get_or_create(
            book=book,
            defaults={
                'final_title': '',
                'final_author': '',
                'final_series': '',
                'final_series_number': '',
                'final_publisher': '',
                'final_cover_path': book.cover_path or '',
                'language': book.scan_folder.language if book.scan_folder else 'en',
                'isbn': '',
                'publication_year': None,
                'description': '',
                'is_reviewed': False,
            }
        )

        context['final_metadata'] = final_metadata

        # Get all available metadata for dropdowns
        context.update(self._get_metadata_context(book))

        # Create form for edit tab
        context['form'] = MetadataReviewForm(instance=final_metadata, book=book)

        # Cover handling
        context.update(self._get_cover_context(book, final_metadata))

        # Navigation handling
        context.update(self._get_navigation_context(book))

        return context

    def _get_metadata_context(self, book):
        """Get metadata context for template."""
        context = {}

        # Get all metadata grouped by type
        context['all_titles'] = book.titles.filter(is_active=True).order_by('-confidence')
        context['all_authors'] = book.bookauthor.filter(is_active=True).order_by('-confidence', '-is_main_author')
        context['all_genres'] = book.bookgenre.filter(is_active=True).order_by('-confidence')
        context['all_series'] = book.series_info.filter(is_active=True).order_by('-confidence')

        # If no series relationships but there is series info in final metadata or series_number metadata, show it
        if not context['all_series'].exists():
            series_number_metadata = book.metadata.filter(is_active=True, field_name='series_number').first()
            if series_number_metadata or (book.finalmetadata and book.finalmetadata.final_series):
                # Create a context entry to show series information
                context['has_series_number_only'] = True
                context['series_number_metadata'] = series_number_metadata
                context['final_series_name'] = getattr(book.finalmetadata, 'final_series', '') if book.finalmetadata else ''
                context['final_series_number'] = getattr(book.finalmetadata, 'final_series_number', '') if book.finalmetadata else ''

        context['all_publishers'] = book.bookpublisher.filter(is_active=True).order_by('-confidence')
        context['all_covers'] = book.covers.filter(is_active=True).order_by('-confidence', '-is_high_resolution')

        # Group additional metadata by field name for dropdowns (exclude series_number as it's handled in series section)
        additional_metadata = book.metadata.filter(is_active=True).exclude(field_name='series_number').order_by('field_name', '-confidence')
        metadata_by_field = {}

        # Field mapping from metadata field names to FinalMetadata attribute names
        field_mapping = {
            'description': 'description',
            'isbn': 'isbn',
            'publication_year': 'publication_year',
            'language': 'language',
            # Add any other fields as needed
        }

        for metadata in additional_metadata:
            is_final = False
            is_top_choice = False
            if book.finalmetadata:
                # Get the correct final metadata field name
                final_field_name = field_mapping.get(metadata.field_name, metadata.field_name)
                final_value = getattr(book.finalmetadata, final_field_name, None)
                # Handle None values and empty strings
                if final_value is not None and str(final_value).strip():
                    is_final = str(metadata.field_value) == str(final_value)

            field_entries = metadata_by_field.setdefault(metadata.field_name, [])

            # Mark as top choice if this is the first (highest confidence) entry and no final selection exists
            if not field_entries:  # First entry for this field
                has_final_selection = any(entry.get('is_final_selected', False) for entry in field_entries)
                if not has_final_selection and not is_final:
                    is_top_choice = True

            field_entries.append({
                'instance': metadata,
                'is_final_selected': is_final,
                'is_top_choice': is_top_choice
            })

        # After processing all entries, mark top choices for fields without final selections
        for field_name, entries in metadata_by_field.items():
            has_final_selection = any(entry['is_final_selected'] for entry in entries)
            if not has_final_selection and entries:
                entries[0]['is_top_choice'] = True

        context['metadata_by_field'] = metadata_by_field

        # Current genres for checkboxes
        current_genres = list(book.bookgenre.filter(is_active=True).values_list('genre__name', flat=True))
        context['current_genres'] = current_genres

        # Data sources ordered by trust level
        context['data_sources'] = DataSource.objects.all().order_by('-trust_level')

        # Conflict detection
        context['has_conflicts'] = (
            context['all_titles'].count() > 1 or
            context['all_authors'].count() > 1 or
            context['all_series'].count() > 1 or
            context['all_publishers'].count() > 1
        )

        return context

    def _get_cover_context(self, book, final_metadata):
        """Get cover context for template."""
        context = {}
        context['primary_cover'] = final_metadata.final_cover_path or book.cover_path

        if context['primary_cover'] and not context['primary_cover'].startswith("http"):
            context['primary_cover_base64'] = encode_cover_to_base64(context['primary_cover'])
        else:
            context['primary_cover_base64'] = None

        context['book_cover_base64'] = encode_cover_to_base64(book.cover_path)
        return context

    def _get_navigation_context(self, book):
        """Get navigation context for flexible book navigation."""
        context = {}

        # Get current book metadata for filtering
        current_metadata = getattr(book, 'finalmetadata', None)
        current_author = current_metadata.final_author if current_metadata else None
        current_series = current_metadata.final_series if current_metadata else None
        current_reviewed = current_metadata.is_reviewed if current_metadata else False

        # Base queryset for navigation
        base_queryset = Book.objects.select_related('finalmetadata').filter(is_placeholder=False)

        # Navigation by chronological order (ID-based)
        prev_book = base_queryset.filter(id__lt=book.id).order_by('-id').first()
        next_book = base_queryset.filter(id__gt=book.id).order_by('id').first()
        context['prev_book_id'] = prev_book.id if prev_book else None
        context['next_book_id'] = next_book.id if next_book else None

        # Navigation by same author
        if current_author:
            same_author_qs = base_queryset.filter(finalmetadata__final_author=current_author)
            context['prev_same_author'] = same_author_qs.filter(id__lt=book.id).order_by('-id').first()
            context['next_same_author'] = same_author_qs.filter(id__gt=book.id).order_by('id').first()

        # Navigation by same series (if book is part of series)
        if current_series:
            same_series_qs = base_queryset.filter(finalmetadata__final_series=current_series)
            # Order by series number if available, otherwise by ID
            context['prev_same_series'] = same_series_qs.filter(id__lt=book.id).order_by('-finalmetadata__final_series_number', '-id').first()
            context['next_same_series'] = same_series_qs.filter(id__gt=book.id).order_by('finalmetadata__final_series_number', 'id').first()

        # Navigation by review status
        if current_reviewed:
            # Next unreviewed book
            context['next_unreviewed'] = base_queryset.filter(
                finalmetadata__is_reviewed=False,
                id__gt=book.id
            ).order_by('id').first()

            # Previous reviewed book
            context['prev_reviewed'] = base_queryset.filter(
                finalmetadata__is_reviewed=True,
                id__lt=book.id
            ).order_by('-id').first()
        else:
            # Next reviewed book
            context['next_reviewed'] = base_queryset.filter(
                finalmetadata__is_reviewed=True,
                id__gt=book.id
            ).order_by('id').first()

            # Previous unreviewed book
            context['prev_unreviewed'] = base_queryset.filter(
                finalmetadata__is_reviewed=False,
                id__lt=book.id
            ).order_by('-id').first()

        # Navigation by needs review (books with conflicts or low confidence)
        needs_review_qs = base_queryset.filter(
            Q(finalmetadata__is_reviewed=False) |
            Q(bookauthor__confidence__lt=0.7) |
            Q(titles__confidence__lt=0.7) |
            Q(series_info__confidence__lt=0.7)
        ).distinct()
        prev_needs_review = needs_review_qs.filter(id__lt=book.id).order_by('-id').first()
        next_needs_review = needs_review_qs.filter(id__gt=book.id).order_by('id').first()
        context['prev_needsreview_id'] = prev_needs_review.id if prev_needs_review else None
        context['next_needsreview_id'] = next_needs_review.id if next_needs_review else None

        return context

    def post(self, request, *args, **kwargs):
        """Handle form submission for metadata updates from edit tab."""
        self.object = self.get_object()
        book = self.get_object()
        final_metadata = getattr(book, 'finalmetadata', None)

        if not final_metadata:
            messages.error(request, "Final metadata not found.")
            return redirect('books:book_detail', pk=book.id)

        # Handle reset action
        if request.POST.get('action') == 'reset':
            return self._handle_reset(request, book, final_metadata)

        # Handle save action
        form = MetadataReviewForm(request.POST, request.FILES, instance=final_metadata, book=book)

        if form.is_valid():
            try:
                with transaction.atomic():
                    logger.debug("POST data received:")
                    for key, value in request.POST.items():
                        if 'manual_entry' in key:
                            logger.debug(f"  {key}: {value}")

                    # Process manual entries FIRST - this creates the metadata entries
                    MetadataProcessor.handle_manual_entries(request, book, form.cleaned_data)

                    # Then save the form (this updates final_metadata)
                    final_metadata = form.save(commit=False)
                    final_metadata.book = book

                    # Handle cover file upload
                    if 'new_cover_upload' in request.FILES:
                        uploaded_path = CoverManager.handle_cover_upload(request, book, request.FILES['new_cover_upload'])
                        if uploaded_path:
                            logger.debug(f"Cover uploaded successfully: {uploaded_path}")

                    # Handle genre updates
                    GenreManager.handle_genre_updates(request, book, form)

                    # Set manual update flag to prevent auto-override of user choices
                    final_metadata._manual_update = True

                    # Save final metadata
                    final_metadata.save()

                    # Update final values to ensure latest data is selected
                    final_metadata.update_final_values()

                messages.success(request, "Final metadata updated successfully!")

                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'success': True,
                        'message': 'Final metadata updated successfully!'
                    })

                return redirect('books:book_detail', pk=book.id)

            except Exception as e:
                logger.error(f"Error updating metadata for book {book.id}: {e}")
                logger.exception("Full traceback:")  # This will log the full stack trace
                messages.error(request, f"Error updating metadata: {str(e)}")

                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'success': False,
                        'errors': {'__all__': [f'Error updating metadata: {str(e)}']}
                    })

        else:
            logger.warning(f"Form validation errors for book {book.id}: {form.errors}")
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'errors': form.errors
                })

        # Re-render page with form errors
        context = self.get_context_data()
        context['form'] = form
        return render(request, self.template_name, context)

    def _handle_reset(self, request, book, final_metadata):
        """Reset all fields to current final_metadata values."""
        try:
            MetadataResetter.reset_to_best_values(book, final_metadata)
            messages.success(request, "Metadata values have been reset to best available options.")
        except Exception as e:
            logger.error(f"Error resetting metadata for book {book.id}: {e}")
            messages.error(request, f"Error resetting metadata: {str(e)}")

        return redirect('books:book_detail', pk=book.id)


class BookMetadataView(LoginRequiredMixin, DetailView):
    """
    Dedicated metadata review view - cleaned and optimized
    """
    model = Book
    template_name = 'books/book_metadata.html'
    context_object_name = 'book'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        book = context['book']

        # Navigation logic - extracted to helper method
        context.update(self._get_navigation_context(book))

        # Metadata context - reusing method from BookDetailView
        context.update(self._get_metadata_context(book))

        # Additional metadata fields specific to metadata review
        context.update(self._get_metadata_fields_context(book))

        return context

    def _get_navigation_context(self, book):
        """Get navigation context for prev/next books"""
        all_books = list(Book.objects.order_by("id").values_list("id", flat=True))
        try:
            index = all_books.index(book.id)
            prev_book_id = all_books[index - 1] if index > 0 else None
            next_book_id = all_books[index + 1] if index + 1 < len(all_books) else None
        except ValueError:
            prev_book_id = None
            next_book_id = None

        # Find next book needing review
        next_needsreview = Book.objects.filter(
            id__gt=book.id,
            finalmetadata__is_reviewed__in=[False, None]
        ).order_by("id").first()

        return {
            'prev_book_id': prev_book_id,
            'next_book_id': next_book_id,
            'next_needs_review_id': getattr(next_needsreview, "id", None),
        }

    def _get_metadata_context(self, book):
        """Get metadata context - reusing from BookDetailView"""
        context = {}
        context['all_titles'] = book.titles.filter(is_active=True).order_by('-confidence')
        context['all_authors'] = book.bookauthor.filter(is_active=True).order_by('-confidence', '-is_main_author')
        context['all_series'] = book.series_info.filter(is_active=True).order_by('-confidence')

        # If no series relationships but there is series info in final metadata or series_number metadata, show it
        if not context['all_series'].exists():
            series_number_metadata = book.metadata.filter(is_active=True, field_name='series_number').first()
            if series_number_metadata or (book.finalmetadata and book.finalmetadata.final_series):
                # Create a context entry to show series information
                context['has_series_number_only'] = True
                context['series_number_metadata'] = series_number_metadata
                context['final_series_name'] = getattr(book.finalmetadata, 'final_series', '') if book.finalmetadata else ''
                context['final_series_number'] = getattr(book.finalmetadata, 'final_series_number', '') if book.finalmetadata else ''

        context['all_publishers'] = book.bookpublisher.filter(is_active=True).order_by('-confidence')
        context['all_genres'] = book.bookgenre.filter(is_active=True).order_by('-confidence')
        context['all_covers'] = book.covers.filter(is_active=True).order_by('-confidence', '-is_high_resolution')
        context['current_genres'] = list(book.bookgenre.filter(is_active=True).values_list('genre__name', flat=True))
        return context

    def _get_metadata_fields_context(self, book):
        """Get additional metadata fields for the review form"""
        return {
            'series_number_metadata': book.metadata.filter(field_name='series_number', is_active=True).order_by('-confidence'),
            'description_metadata': book.metadata.filter(field_name='description', is_active=True).order_by('-confidence'),
            'isbn_metadata': book.metadata.filter(field_name='isbn', is_active=True).order_by('-confidence'),
            'year_metadata': book.metadata.filter(field_name='publication_year', is_active=True).order_by('-confidence'),
            'language_metadata': book.metadata.filter(field_name='language', is_active=True).order_by('-confidence'),
            'language_choices': LANGUAGE_CHOICES,
        }


class BookMetadataUpdateView(LoginRequiredMixin, View):
    """
    FIXED metadata update view - addresses all reported bugs
    """
    def post(self, request, pk):
        try:
            book = get_object_or_404(Book, pk=pk)
            final_metadata, created = FinalMetadata.objects.get_or_create(book=book)

            updated_fields = []

            # Process fields in correct order
            updated_fields.extend(self._process_text_fields(request, final_metadata))
            updated_fields.extend(self._process_cover_field(request, final_metadata, book))
            updated_fields.extend(self._process_numeric_fields(request, final_metadata))
            updated_fields.extend(self._process_genre_fields(request, book))
            updated_fields.extend(self._process_metadata_fields(request, final_metadata, book))

            # Handle review status
            is_reviewed = 'is_reviewed' in request.POST
            if is_reviewed != final_metadata.is_reviewed:
                final_metadata.is_reviewed = is_reviewed
                updated_fields.append('reviewed status')

            final_metadata.updated_at = timezone.now()

            # Save with flag to prevent auto-update since we've made manual changes
            final_metadata._manual_update = True
            final_metadata.save()

            if updated_fields:
                book_title = final_metadata.final_title or book.filename
                messages.success(
                    request,
                    f"Successfully updated {', '.join(updated_fields)} for '{book_title}'"
                )
            else:
                messages.info(request, "No changes were made to the metadata.")

            # Redirect back to the edit tab
            redirect_url = reverse('books:book_detail', kwargs={'pk': book.id}) + '?tab=edit'
            return redirect(redirect_url)

        except Exception as e:
            logger.error(f"Error updating metadata for book {pk}: {e}")
            messages.error(request, f"An error occurred while updating metadata: {str(e)}")
            # Redirect back to the edit tab even on error
            redirect_url = reverse('books:book_detail', kwargs={'pk': pk}) + '?tab=edit'
            return redirect(redirect_url)

    def _process_text_fields(self, request, final_metadata):
        """Process title, author, series, publisher fields"""
        updated_fields = []

        text_fields = {
            'final_title': ('Title', 'manual_title'),
            'final_author': ('Author', 'manual_author'),
            'final_series': ('Series', 'manual_series'),
            'final_publisher': ('Publisher', 'manual_publisher'),
        }

        for field_name, (display_name, manual_field) in text_fields.items():
            result = self._process_field_with_manual(request, final_metadata, field_name, manual_field, display_name)
            if result:
                updated_fields.append(result)

        # Handle series number with validation
        series_number_result = self._process_series_number(request, final_metadata)
        if series_number_result:
            updated_fields.append(series_number_result)

        return updated_fields

    def _process_series_number(self, request, final_metadata):
        """Process series number with validation that series is selected"""
        final_series_number = request.POST.get('final_series_number', '').strip()
        manual_series_number = request.POST.get('manual_series_number', '').strip()

        # Determine the series number value
        series_number_value = None
        if final_series_number == '__manual__' and manual_series_number:
            series_number_value = manual_series_number
        elif final_series_number and final_series_number != '__manual__':
            series_number_value = final_series_number

        # If series number is provided, ensure a series is also selected
        if series_number_value:
            final_series = request.POST.get('final_series', '').strip()
            manual_series = request.POST.get('manual_series', '').strip()

            has_series = (
                (final_series and final_series != '__manual__') or
                (final_series == '__manual__' and manual_series) or
                final_metadata.final_series
            )

            if not has_series:
                messages.warning(request, "Series number was ignored because no series was selected.")
                return None

            # Save the series number
            final_metadata.final_series_number = series_number_value

            # Also create metadata entry for tracking
            manual_source, _ = DataSource.objects.get_or_create(
                name=DataSource.MANUAL,
                defaults={'trust_level': 0.9}
            )

            BookMetadata.objects.update_or_create(
                book=final_metadata.book,
                field_name='series_number',
                source=manual_source,
                defaults={
                    'field_value': series_number_value,
                    'confidence': 1.0,
                    'is_active': True
                }
            )

            return 'series number'

        elif not series_number_value:
            # Clear series number if not provided
            final_metadata.final_series_number = ''

        return None

    def _process_field_with_manual(self, request, final_metadata, field_name, manual_field, display_name):
        """Process individual field with manual entry support"""
        final_value = request.POST.get(field_name, '').strip()
        manual_value = request.POST.get(manual_field, '').strip()

        value_to_save = None
        is_manual = False

        if final_value == '__manual__' and manual_value:
            value_to_save = manual_value
            is_manual = True
        elif final_value and final_value != '__manual__':
            value_to_save = final_value
        elif not final_value:
            # Clear the field
            setattr(final_metadata, field_name, '')
            return None

        if value_to_save:
            setattr(final_metadata, field_name, value_to_save)

            if is_manual:
                # Create metadata entries for manual inputs
                self._create_manual_metadata_entry(final_metadata.book, field_name, value_to_save)
                return f'{display_name} (manual)'
            else:
                return display_name

        return None

    def _create_manual_metadata_entry(self, book, field_name, value):
        """Create metadata entries for manual inputs"""
        manual_source, _ = DataSource.objects.get_or_create(
            name=DataSource.MANUAL,
            defaults={'trust_level': 0.9}
        )

        if field_name == 'final_title':
            BookTitle.objects.update_or_create(
                book=book,
                source=manual_source,
                defaults={
                    'title': value,
                    'confidence': 1.0,
                    'is_active': True
                }
            )
        elif field_name == 'final_author':
            author_obj, _ = Author.objects.get_or_create(name=value)
            BookAuthor.objects.update_or_create(
                book=book,
                author=author_obj,
                source=manual_source,
                defaults={
                    'confidence': 1.0,
                    'is_main_author': True,
                    'is_active': True
                }
            )
        elif field_name == 'final_publisher':
            publisher_obj, _ = Publisher.objects.get_or_create(name=value)
            BookPublisher.objects.update_or_create(
                book=book,
                publisher=publisher_obj,
                source=manual_source,
                defaults={
                    'confidence': 1.0,
                    'is_active': True
                }
            )
        elif field_name == 'final_series':
            series_obj, _ = Series.objects.get_or_create(name=value)
            BookSeries.objects.update_or_create(
                book=book,
                source=manual_source,
                defaults={
                    'series': series_obj,
                    'confidence': 1.0,
                    'is_active': True
                }
            )

    def _process_cover_field(self, request, final_metadata, book):
        """Process cover selection and upload - ENHANCED for immediate upload."""
        updated_fields = []
        final_cover_path = request.POST.get('final_cover_path', '').strip()
        cover_upload = request.FILES.get('cover_upload')

        if final_cover_path == 'custom_upload' and cover_upload:
            # Handle traditional form upload
            result = CoverManager.handle_cover_upload(request, book, cover_upload)
            if result['success']:
                final_metadata.final_cover_path = result['cover_path']
                updated_fields.append('cover (uploaded)')
        elif final_cover_path and final_cover_path != 'custom_upload':
            # Handle selection of existing cover
            final_metadata.final_cover_path = final_cover_path
            updated_fields.append('cover')
        elif final_cover_path.startswith(settings.MEDIA_URL):
            # Handle AJAX uploaded cover (already processed)
            final_metadata.final_cover_path = final_cover_path
            updated_fields.append('cover (pre-uploaded)')

        return updated_fields

    def _process_numeric_fields(self, request, final_metadata):
        """Process publication year - FIXED to store in both places"""
        updated_fields = []

        final_year = request.POST.get('publication_year', '').strip()
        manual_year = request.POST.get('manual_publication_year', '').strip()

        year_value = None
        is_manual = False

        if final_year == '__manual__' and manual_year:
            try:
                year_value = int(manual_year)
                is_manual = True
            except ValueError:
                messages.error(request, "Invalid publication year format.")
                return updated_fields
        elif final_year and final_year != '__manual__':
            try:
                year_value = int(final_year)
            except ValueError:
                messages.error(request, "Invalid publication year format.")
                return updated_fields

        if year_value and 1000 <= year_value <= 2100:
            # Store in FinalMetadata
            final_metadata.publication_year = year_value

            # Also create/update BookMetadata entry for consistency
            manual_source, _ = DataSource.objects.get_or_create(
                name=DataSource.MANUAL if is_manual else DataSource.GOOGLE_BOOKS,
                defaults={'trust_level': 0.9}
            )

            BookMetadata.objects.update_or_create(
                book=final_metadata.book,
                field_name='publication_year',
                source=manual_source,
                defaults={
                    'field_value': str(year_value),
                    'confidence': 1.0 if is_manual else 0.8,
                    'is_active': True
                }
            )

            updated_fields.append('publication year (manual)' if is_manual else 'publication year')
        elif final_year == '' or not final_year:
            # Clear the field
            final_metadata.publication_year = None

        return updated_fields

    def _process_metadata_fields(self, request, final_metadata, book):
        """Process ISBN, Language, and Description fields - FIXED"""
        updated_fields = []

        metadata_fields = {
            'isbn': ('ISBN', 'manual_isbn'),
            'language': ('Language', 'manual_language'),
            'description': ('Description', 'manual_description'),
        }

        for field_name, (display_name, manual_field) in metadata_fields.items():
            final_value = request.POST.get(field_name, '').strip()
            manual_value = request.POST.get(manual_field, '').strip()

            value_to_save = None
            is_manual = False

            if final_value == '__manual__' and manual_value:
                value_to_save = manual_value
                is_manual = True
            elif final_value and final_value != '__manual__':
                value_to_save = final_value

            if value_to_save:
                # Store in FinalMetadata
                setattr(final_metadata, field_name, value_to_save)

                # Also create/update BookMetadata entry
                source_name = DataSource.MANUAL if is_manual else DataSource.GOOGLE_BOOKS
                manual_source, _ = DataSource.objects.get_or_create(
                    name=source_name,
                    defaults={'trust_level': 0.9}
                )

                BookMetadata.objects.update_or_create(
                    book=book,
                    field_name=field_name,
                    source=manual_source,
                    defaults={
                        'field_value': value_to_save,
                        'confidence': 1.0 if is_manual else 0.8,
                        'is_active': True
                    }
                )

                updated_fields.append(f'{display_name} (manual)' if is_manual else display_name)
            elif final_value == '' or not final_value:
                # Clear the field
                setattr(final_metadata, field_name, '')

        return updated_fields

    def _process_genre_fields(self, request, book):
        """Process genre selection - FIXED to handle multiple genres correctly"""
        updated_fields = []
        selected_genres = request.POST.getlist('final_genres')
        manual_genres = request.POST.get('manual_genres', '').strip()

        try:
            # Use the fixed GenreManager
            GenreManager.handle_genre_updates(request, book, None)

            total_genres = len(selected_genres)
            if manual_genres:
                manual_count = len([g.strip() for g in manual_genres.split(',') if g.strip()])
                total_genres += manual_count

            if total_genres > 0:
                updated_fields.append(f'genres ({total_genres} selected)')
            elif 'final_genres' in request.POST:
                updated_fields.append('genres (cleared)')

        except Exception as e:
            logger.error(f"Error processing genres for book {book.id}: {e}")
            messages.error(request, f"Error updating genres: {str(e)}")

        return updated_fields

    def get(self, request, pk):
        """Redirect GET requests to the metadata view page"""
        return redirect('books:book_metadata', pk=pk)


class ScanFolderListView(LoginRequiredMixin, ListView):
    model = ScanFolder
    template_name = 'books/scan_folder_list.html'
    context_object_name = 'scan_folders'

    def get_queryset(self):
        return ScanFolder.objects.annotate(
            book_count=Count('book')
        ).order_by('path')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['total_folders'] = ScanFolder.objects.count()
        context['active_folders'] = ScanFolder.objects.filter(is_active=True).count()
        context['form'] = ScanFolderForm()
        return context


class AddScanFolderView(LoginRequiredMixin, CreateView):
    model = ScanFolder
    form_class = ScanFolderForm
    template_name = 'books/add_scan_folder.html'
    success_url = reverse_lazy('books:scan_folder_list')

    def form_valid(self, form):
        messages.success(self.request, f"Scan folder '{form.instance.path}' added successfully.")
        return super().form_valid(form)


class DeleteScanFolderView(LoginRequiredMixin, DeleteView):
    model = ScanFolder
    template_name = 'books/delete_scan_folder.html'
    success_url = reverse_lazy('books:scan_folder_list')

    def delete(self, request, *args, **kwargs):
        folder = self.get_object()
        messages.success(request, f"Scan folder '{folder.path}' deleted successfully.")
        return super().delete(request, *args, **kwargs)


class TriggerScanView(LoginRequiredMixin, TemplateView):
    template_name = 'books/trigger_scan.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_folders'] = ScanFolder.objects.filter(is_active=True)
        context['recent_logs'] = ScanLog.objects.order_by('-timestamp')[:10]
        context['last_scan'] = ScanStatus.objects.order_by('-started').first()
        return context

    def post(self, request, *args, **kwargs):
        try:
            folder_path = request.POST.get('folder_path')
            scan_mode = request.POST.get('scan_mode', 'normal')

            # Create a new scan status for this scan
            scan_status = ScanStatus.objects.create(
                status='Running',
                progress=0,
                message='Initializing scan...'
            )

            # Build command based on scan mode and options
            project_dir = getattr(settings, 'BASE_DIR', os.getcwd())
            manage_py_path = os.path.join(project_dir, 'manage.py')
            cmd = [sys.executable, manage_py_path, 'scan_ebooks']

            # Add folder path if specified
            if folder_path:
                cmd.append(folder_path)

            # Add scan mode flags
            if scan_mode == 'rescan':
                cmd.append('--rescan')
            elif scan_mode == 'resume':
                cmd.append('--resume')

            # Start the subprocess
            subprocess.Popen(cmd, cwd=project_dir)

            # Update scan status message based on mode
            if folder_path:
                base_message = f'Scan started for folder: {folder_path}'
            else:
                active_folders = ScanFolder.objects.filter(is_active=True)
                folder_count = active_folders.count()

                if folder_count == 0:
                    scan_status.status = 'Failed'
                    scan_status.message = 'No active folders found to scan'
                    scan_status.save()
                    messages.error(request, "No active folders found to scan.")
                    return redirect('books:trigger_scan')

                base_message = f'Full scan started for {folder_count} active folder{"s" if folder_count != 1 else ""}'

            # Add mode description to message
            mode_descriptions = {
                'normal': '',
                'resume': ' (resuming from interruption)',
                'rescan': ' (full rescan mode)'
            }

            final_message = base_message + mode_descriptions.get(scan_mode, '')
            scan_status.message = final_message
            scan_status.save()

            messages.success(request, final_message.replace('started', 'initiated'))
            return redirect('books:scan_status')

        except Exception as e:
            logger.error(f"Error starting book scan: {e}")

            # Update scan status to failed if something goes wrong
            try:
                scan_status = ScanStatus.objects.last()
                if scan_status:
                    scan_status.status = 'Failed'
                    scan_status.message = f'Failed to start scan: {str(e)}'
                    scan_status.save()
            except Exception as status_error:
                logger.error(f"Error updating scan status: {status_error}")

            messages.error(request, f"Failed to start book scan: {e}")
            return redirect('books:trigger_scan')


class ScanStatusView(LoginRequiredMixin, ListView):
    model = ScanLog
    template_name = 'books/scan_status.html'
    context_object_name = 'logs'
    paginate_by = 100

    def get_queryset(self):
        level_filter = self.request.GET.get('level', '')
        queryset = ScanLog.objects.select_related('scan_folder').order_by('-timestamp')

        if level_filter:
            queryset = queryset.filter(level=level_filter)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context['recent_books'] = Book.objects.select_related('finalmetadata').order_by('-last_scanned')[:10]
        context['error_count'] = ScanLog.objects.filter(level='ERROR').count()
        context['warning_count'] = ScanLog.objects.filter(level='WARNING').count()
        context['info_count'] = ScanLog.objects.filter(level='INFO').count()

        context['level_filter'] = self.request.GET.get('level', '')
        context['log_levels'] = [
            ('DEBUG', 'Debug'),
            ('INFO', 'Info'),
            ('WARNING', 'Warning'),
            ('ERROR', 'Error'),
        ]

        context['scan_folders'] = ScanFolder.objects.annotate(
            book_count=Count('book')
        ).order_by('-last_scanned')

        context['scan_status'] = ScanStatus.objects.order_by('-started').first()

        return context


class DataSourceListView(LoginRequiredMixin, ListView):
    """View for managing data sources and their trust levels"""
    model = DataSource
    template_name = 'books/data_source_list.html'
    context_object_name = 'data_sources'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        sources = DataSource.objects.all()
        source_count = sources.count()

        # Attach per-source metadata counts first
        for source in sources:
            source.title_count = BookTitle.objects.filter(source=source).count()
            source.author_count = BookAuthor.objects.filter(source=source).count()
            source.genre_count = BookGenre.objects.filter(source=source).count()
            source.series_count = BookSeries.objects.filter(source=source).count()
            source.metadata_count = BookMetadata.objects.filter(source=source).count()
            source.cover_count = BookCover.objects.filter(source=source).count()
            source.publisher_count = BookPublisher.objects.filter(source=source).count()

        # Then compute summary metrics
        high_trust_count = sources.filter(trust_level__gte=0.8).count()
        metadata_total = sum(source.metadata_count for source in sources)
        avg_trust_level = round(
            sum(source.trust_level for source in sources) / max(source_count, 1),
            2
        )
        top_source = max(sources, key=lambda s: s.metadata_count, default=None)

        context.update({
            "data_sources": sources,
            "high_trust_count": high_trust_count,
            "metadata_total": metadata_total,
            "avg_trust_level": avg_trust_level,
            "top_source": top_source,
        })

        return context


class AuthorListView(LoginRequiredMixin, ListView):
    model = Author
    template_name = 'books/author_list.html'
    context_object_name = 'authors'
    paginate_by = 25

    def get_queryset(self):
        query = self.request.GET.get('search', '')
        reviewed_filter = self.request.GET.get('is_reviewed', '')

        base_qs = Author.objects.all()

        if query:
            base_qs = base_qs.filter(
                Q(name__icontains=query) |
                Q(first_name__icontains=query) |
                Q(last_name__icontains=query)
            )

        if reviewed_filter == 'true':
            base_qs = base_qs.filter(is_reviewed=True)
        elif reviewed_filter == 'false':
            base_qs = base_qs.filter(is_reviewed=False)

        return base_qs.order_by('name')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['search_query'] = self.request.GET.get('search', '')
        context['author_sources'] = {
            author.id: list(BookAuthor.objects.filter(author=author).values_list('source__name', flat=True).distinct())
            for author in context['authors']
        }
        return context


class AuthorBulkDeleteView(LoginRequiredMixin, View):
    def post(self, request):
        selected_ids = request.POST.getlist('selected_authors')
        authors = Author.objects.filter(id__in=selected_ids, is_reviewed=False)

        deleted = []
        for author in authors:
            BookAuthor.objects.filter(author=author).delete()
            author.delete()
            deleted.append(author.name)

        if deleted:
            messages.success(request, f"Deleted {len(deleted)} authors: {', '.join(deleted[:5])}...")
        else:
            messages.info(request, "No authors deleted. Reviewed authors are protected.")

        return redirect('books:author_list')


class AuthorDeleteView(LoginRequiredMixin, DeleteView):
    model = Author
    template_name = 'books/author_confirm_delete.html'
    success_url = reverse_lazy('books:author_list')

    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        author_name = self.object.name
        BookAuthor.objects.filter(author=self.object).delete()
        self.object.delete()
        messages.success(request, f'Author "{author_name}" and their metadata entries were deleted.')
        return redirect(self.success_url)


class AuthorMarkReviewedView(LoginRequiredMixin, View):
    def post(self, request):
        selected_ids = request.POST.getlist('selected_authors')
        updated = Author.objects.filter(id__in=selected_ids, is_reviewed=False).update(is_reviewed=True)

        if updated:
            messages.success(request, f"Marked {updated} author(s) as reviewed.")
        else:
            messages.info(request, "No changes made. All selected authors were already reviewed.")

        return redirect('books:author_list')


# ------------------------
# Genre Management Views
# ------------------------

class GenreListView(LoginRequiredMixin, ListView):
    model = Genre
    template_name = 'books/genre_list.html'
    context_object_name = 'genres'
    paginate_by = 25

    def get_queryset(self):
        query = self.request.GET.get('search', '')
        reviewed_filter = self.request.GET.get('is_reviewed', '')

        base_qs = Genre.objects.all()

        if query:
            base_qs = base_qs.filter(name__icontains=query)

        if reviewed_filter == 'true':
            base_qs = base_qs.filter(is_reviewed=True)
        elif reviewed_filter == 'false':
            base_qs = base_qs.filter(is_reviewed=False)

        return base_qs.order_by('name')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['search_query'] = self.request.GET.get('search', '')
        context['genre_sources'] = {
            genre.id: list(BookGenre.objects.filter(genre=genre).values_list('source__name', flat=True).distinct())
            for genre in context['genres']
        }
        return context


class GenreBulkDeleteView(LoginRequiredMixin, View):
    def post(self, request):
        selected_ids = request.POST.getlist('selected_genres')
        genres = Genre.objects.filter(id__in=selected_ids, is_reviewed=False)

        deleted = []
        for genre in genres:
            BookGenre.objects.filter(genre=genre).delete()
            genre.delete()
            deleted.append(genre.name)

        if deleted:
            messages.success(request, f"Deleted {len(deleted)} genres: {', '.join(deleted[:5])}...")
        else:
            messages.info(request, "No genres deleted. Reviewed genres are protected.")

        return redirect('books:genre_list')


class GenreDeleteView(LoginRequiredMixin, DeleteView):
    model = Genre
    template_name = 'books/genre_confirm_delete.html'
    success_url = reverse_lazy('books:genre_list')

    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        genre_name = self.object.name
        BookGenre.objects.filter(genre=self.object).delete()
        self.object.delete()
        messages.success(request, f'Genre "{genre_name}" and their metadata entries were deleted.')
        return redirect(self.success_url)


class GenreMarkReviewedView(LoginRequiredMixin, View):
    def post(self, request):
        selected_ids = request.POST.getlist('selected_genres')
        updated = Genre.objects.filter(id__in=selected_ids, is_reviewed=False).update(is_reviewed=True)

        if updated:
            messages.success(request, f"Marked {updated} genre(s) as reviewed.")
        else:
            messages.info(request, "No changes made. All selected genres were already reviewed.")

        return redirect('books:genre_list')


# =============================================================================
# BOOK RENAMING/ORGANIZATION VIEWS
# =============================================================================

class BookRenamerView(LoginRequiredMixin, ListView):
    """View for organizing and renaming reviewed books with preview functionality."""
    model = Book
    template_name = 'books/book_renamer.html'
    context_object_name = 'books'
    paginate_by = 50

    def get_queryset(self):
        """Get reviewed books that can be renamed."""
        queryset = Book.objects.filter(
            finalmetadata__is_reviewed=True,
            is_placeholder=False
        ).select_related(
            'finalmetadata'
        ).prefetch_related(
            'bookauthor__author',
            'series_info__series',
            'bookgenre__genre'
        )

        # Apply filters
        search = self.request.GET.get('search', '')
        author = self.request.GET.get('author', '')
        language = self.request.GET.get('language', '')
        file_format = self.request.GET.get('file_format', '')
        confidence_min = self.request.GET.get('confidence_min', '')
        has_series = self.request.GET.get('has_series', '')
        genre = self.request.GET.get('genre', '')
        show_complete_series = self.request.GET.get('complete_series', '')

        if search:
            queryset = queryset.filter(
                Q(finalmetadata__final_title__icontains=search) |
                Q(finalmetadata__final_author__icontains=search)
            )

        if author:
            queryset = queryset.filter(finalmetadata__final_author__icontains=author)

        if language:
            queryset = queryset.filter(finalmetadata__language=language)

        if file_format:
            queryset = queryset.filter(file_format=file_format)

        if confidence_min:
            try:
                conf_min = float(confidence_min)
                queryset = queryset.filter(confidence__gte=conf_min)
            except ValueError:
                pass

        if has_series == 'true':
            queryset = queryset.filter(finalmetadata__final_series__isnull=False)
        elif has_series == 'false':
            queryset = queryset.filter(finalmetadata__final_series__isnull=True)

        if genre:
            queryset = queryset.filter(bookgenre__genre__name__icontains=genre)

        # Filter for complete series only
        if show_complete_series == 'true':
            complete_series_books = self._get_complete_series_books()
            if complete_series_books:
                queryset = queryset.filter(id__in=complete_series_books)
            else:
                queryset = queryset.none()

        return queryset.distinct().order_by(
            'finalmetadata__final_author',
            'finalmetadata__final_series',
            'finalmetadata__final_series_number',
            'finalmetadata__final_title'
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Add filter options
        context['languages'] = LANGUAGE_CHOICES
        context['formats'] = Book.FORMAT_CHOICES
        context['search_query'] = self.request.GET.get('search', '')
        context['author_filter'] = self.request.GET.get('author', '')
        context['language_filter'] = self.request.GET.get('language', '')
        context['format_filter'] = self.request.GET.get('file_format', '')
        context['confidence_filter'] = self.request.GET.get('confidence_min', '')
        context['series_filter'] = self.request.GET.get('has_series', '')
        context['genre_filter'] = self.request.GET.get('genre', '')
        context['complete_series_filter'] = self.request.GET.get('complete_series', '')

        # Analyze series completion
        series_analysis = self._analyze_series_completion()
        context['complete_series'] = series_analysis['complete_series']
        context['incomplete_series'] = series_analysis['incomplete_series']

        # Generate new file paths for each book with warnings
        books_with_paths = []
        for book in context['books']:
            new_path = self._generate_new_file_path(book)
            warnings = self._generate_warnings(book)
            books_with_paths.append({
                'book': book,
                'current_path': book.file_path,
                'new_path': new_path,
                'can_rename': self._can_rename_book(book),
                'warnings': warnings,
                'is_complete_series': self._is_book_in_complete_series(book, series_analysis['complete_series'])
            })

        context['books_with_paths'] = books_with_paths

        return context

    def _analyze_series_completion(self):
        """Analyze all series to find complete ones with no gaps."""
        series_data = {}

        # Get all books with series information
        books_with_series = Book.objects.filter(
            finalmetadata__is_reviewed=True,
            finalmetadata__final_series__isnull=False,
            finalmetadata__final_series_number__isnull=False,
            is_placeholder=False
        ).select_related('finalmetadata')

        # Group by author and series
        for book in books_with_series:
            fm = book.finalmetadata
            author = fm.final_author or "Unknown Author"
            series = fm.final_series

            key = f"{author}||{series}"
            if key not in series_data:
                series_data[key] = {
                    'author': author,
                    'series': series,
                    'books': [],
                    'numbers': set()
                }

            try:
                series_num = float(fm.final_series_number)
                series_data[key]['books'].append({
                    'book': book,
                    'number': series_num,
                    'title': fm.final_title
                })
                series_data[key]['numbers'].add(series_num)
            except (ValueError, TypeError):
                # Skip books with invalid series numbers
                continue

        complete_series = []
        incomplete_series = []

        for key, data in series_data.items():
            if len(data['books']) < 2:
                continue  # Skip single book "series"

            numbers = sorted(data['numbers'])

            # Check if series is complete (no gaps from 1 to max)
            is_complete = (
                len(numbers) >= 2 and  # At least 2 books
                numbers[0] == 1.0 and  # Starts with 1
                all(numbers[i] == numbers[i-1] + 1 for i in range(1, len(numbers)))  # No gaps
            )

            series_info = {
                'author': data['author'],
                'series': data['series'],
                'books': sorted(data['books'], key=lambda x: x['number']),
                'count': len(data['books']),
                'numbers': numbers,
                'key': key
            }

            if is_complete:
                complete_series.append(series_info)
            else:
                # Analyze what's missing
                max_num = int(max(numbers))
                missing = [i for i in range(1, max_num + 1) if i not in numbers]
                series_info['missing_numbers'] = missing
                incomplete_series.append(series_info)

        return {
            'complete_series': complete_series,
            'incomplete_series': incomplete_series
        }

    def _is_book_in_complete_series(self, book, complete_series):
        """Check if a book is part of a complete series."""
        if not book.finalmetadata or not book.finalmetadata.final_series:
            return False

        fm = book.finalmetadata
        author = fm.final_author or "Unknown Author"
        series = fm.final_series

        for series_info in complete_series:
            if series_info['author'] == author and series_info['series'] == series:
                return True
        return False

    def _get_complete_series_books(self):
        """Get book IDs that are part of complete series."""
        series_analysis = self._analyze_series_completion()
        book_ids = []

        for series_info in series_analysis['complete_series']:
            for book_data in series_info['books']:
                book_ids.append(book_data['book'].id)

        return book_ids

    def _generate_warnings(self, book):
        """Generate warnings for potential issues with the book."""
        warnings = []
        fm = book.finalmetadata

        # Check for missing metadata
        if not fm.final_author or fm.final_author.strip() == "":
            warnings.append({
                'type': 'warning',
                'message': 'Missing author information'
            })

        if not fm.final_title or fm.final_title.strip() == "":
            warnings.append({
                'type': 'warning',
                'message': 'Missing title information'
            })

        # Check confidence levels
        if hasattr(fm, 'overall_confidence') and fm.overall_confidence is not None:
            if fm.overall_confidence < 0.5:
                warnings.append({
                    'type': 'danger',
                    'message': f'Low confidence score: {fm.overall_confidence:.2f}'
                })
            elif fm.overall_confidence < 0.7:
                warnings.append({
                    'type': 'warning',
                    'message': f'Medium confidence score: {fm.overall_confidence:.2f}'
                })

        # Check for series consistency
        if fm.final_series and not fm.final_series_number:
            warnings.append({
                'type': 'warning',
                'message': 'Series name present but missing series number'
            })
        elif fm.final_series_number and not fm.final_series:
            warnings.append({
                'type': 'warning',
                'message': 'Series number present but missing series name'
            })

        # Check for duplicate file names
        if self._check_for_duplicate_paths(book):
            warnings.append({
                'type': 'danger',
                'message': 'Potential duplicate file path detected'
            })

        # Check file existence
        if not self._can_rename_book(book):
            warnings.append({
                'type': 'danger',
                'message': 'Original file not found'
            })

        return warnings

    def _check_for_duplicate_paths(self, book):
        """Check if the generated path would conflict with existing files."""
        new_path = self._generate_new_file_path(book)

        # Check if any other book would generate the same path
        other_books = Book.objects.filter(
            finalmetadata__is_reviewed=True,
            is_placeholder=False
        ).exclude(id=book.id).select_related('finalmetadata')

        for other_book in other_books:
            other_path = self._generate_new_file_path(other_book)
            if new_path == other_path:
                return True
        return False

    def _generate_new_file_path(self, book):
        """Generate the new organized file path based on the suggested structure."""
        try:
            fm = book.finalmetadata
            base_library = "eBooks Library"

            # Format (EPUB, PDF, etc.)
            file_format = book.file_format.upper() if book.file_format else "UNKNOWN"

            # Language
            language = "Unknown"
            if fm.language:
                # Convert language code to readable name
                lang_dict = dict(LANGUAGE_CHOICES)
                language = lang_dict.get(fm.language, fm.language)

            # Main Category (for now, default to Fiction/Non-Fiction based on genres)
            category = self._determine_category(book)

            # Author (Last, First format)
            author = self._format_author_name(fm.final_author)

            # Series handling
            if fm.final_series and fm.final_series_number:
                # Series book
                series_folder = self._clean_filename(fm.final_series)
                book_folder = f"{fm.final_series_number} - {self._clean_filename(fm.final_title)}"
                filename_base = f"{author} - {fm.final_series} #{fm.final_series_number} - {fm.final_title}"
            else:
                # Standalone book
                series_folder = None
                book_folder = self._clean_filename(fm.final_title)
                filename_base = f"{author} - {fm.final_title}"

            # Clean filename
            filename_base = self._clean_filename(filename_base)
            file_extension = book.file_format.lower() if book.file_format else "epub"

            # Construct path
            if series_folder:
                folder_path = f"{base_library}/{file_format}/{language}/{category}/{self._clean_filename(author)}/{series_folder}/{book_folder}"
            else:
                folder_path = f"{base_library}/{file_format}/{language}/{category}/{self._clean_filename(author)}/{book_folder}"

            new_file_path = f"{folder_path}/{filename_base}.{file_extension}"

            return new_file_path

        except Exception as e:
            return f"Error generating path: {str(e)}"

    def _determine_category(self, book):
        """Determine main category based on genres."""
        fiction_indicators = ['fiction', 'novel', 'romance', 'mystery', 'thriller', 'fantasy', 'sci-fi', 'science fiction']

        genres = book.bookgenre.filter(is_active=True).values_list('genre__name', flat=True)
        genre_names = [g.lower() for g in genres]

        for genre in genre_names:
            if any(indicator in genre for indicator in fiction_indicators):
                return "Fiction"

        # Default categories based on common patterns
        if any(g in genre_names for g in ['biography', 'history', 'science', 'technology', 'business']):
            return "Non-Fiction"
        elif any(g in genre_names for g in ['reference', 'manual', 'guide', 'cookbook']):
            return "Reference"

        return "Fiction"  # Default

    def _format_author_name(self, author_name):
        """Format author name as 'Last, First'."""
        if not author_name:
            return "Unknown Author"

        # Try to parse "First Last" format
        parts = author_name.strip().split()
        if len(parts) >= 2:
            first = ' '.join(parts[:-1])
            last = parts[-1]
            return f"{last}, {first}"
        else:
            return author_name

    def _clean_filename(self, name):
        """Clean filename to be filesystem safe."""
        if not name:
            return "Unknown"

        import re
        # Remove invalid characters
        cleaned = re.sub(r'[<>:"/\\|?*]', '', str(name))
        # Replace multiple spaces with single space
        cleaned = re.sub(r'\s+', ' ', cleaned)
        # Trim and limit length
        cleaned = cleaned.strip()[:100]

        return cleaned if cleaned else "Unknown"

    def _can_rename_book(self, book):
        """Check if book can be safely renamed."""
        import os
        return os.path.exists(book.file_path) if book.file_path else False


class BookRenamerPreviewView(LoginRequiredMixin, View):
    """AJAX view to preview renaming changes."""

    def post(self, request):
        selected_ids = request.POST.getlist('selected_books')
        if not selected_ids:
            return JsonResponse({'error': 'No books selected'}, status=400)

        books = Book.objects.filter(
            id__in=selected_ids,
            finalmetadata__is_reviewed=True,
            is_placeholder=False
        ).select_related('finalmetadata')

        preview_data = []
        for book in books:
            renamer_view = BookRenamerView()
            new_path = renamer_view._generate_new_file_path(book)

            preview_data.append({
                'id': book.id,
                'title': book.finalmetadata.final_title,
                'author': book.finalmetadata.final_author,
                'current_path': book.file_path,
                'new_path': new_path,
                'can_rename': renamer_view._can_rename_book(book)
            })

        return JsonResponse({'preview': preview_data})


class BookRenamerExecuteView(LoginRequiredMixin, View):
    """Execute the actual file renaming with operation tracking."""

    def post(self, request):
        import uuid
        import json

        selected_ids = request.POST.getlist('selected_books')
        if not selected_ids:
            return JsonResponse({'error': 'No books selected'}, status=400)

        books = Book.objects.filter(
            id__in=selected_ids,
            finalmetadata__is_reviewed=True,
            is_placeholder=False
        ).select_related('finalmetadata')

        # Generate batch ID for this operation
        batch_id = uuid.uuid4()

        results = {
            'success': [],
            'errors': [],
            'warnings': [],
            'total': len(books),
            'batch_id': str(batch_id)
        }

        for book in books:
            try:
                # Create file operation record first
                file_op = FileOperation.objects.create(
                    book=book,
                    operation_type='rename',
                    batch_id=batch_id,
                    user=request.user,
                    original_file_path=book.file_path or '',
                    original_cover_path=book.cover_path or '',
                    original_opf_path=getattr(book, 'opf_path', '') or '',
                    original_folder_path=os.path.dirname(book.file_path) if book.file_path else '',
                )

                # Generate warnings before rename
                warnings = self._generate_warnings(book)

                success_data = self._rename_book_files(book, file_op)
                if success_data:
                    file_op.status = 'completed'
                    file_op.new_file_path = success_data['new_path']
                    file_op.new_cover_path = success_data.get('new_cover_path', '')
                    file_op.new_opf_path = success_data.get('new_opf_path', '')
                    file_op.new_folder_path = os.path.dirname(success_data['new_path'])
                    file_op.additional_files = json.dumps(success_data.get('additional_files', []))
                    file_op.save()

                    result_data = {
                        'id': book.id,
                        'title': book.finalmetadata.final_title,
                        'old_path': file_op.original_file_path,
                        'new_path': success_data['new_path'],
                        'operation_id': file_op.id
                    }

                    if warnings:
                        result_data['warnings'] = warnings
                        results['warnings'].append(result_data)
                    else:
                        results['success'].append(result_data)
                else:
                    file_op.status = 'failed'
                    file_op.error_message = 'Failed to rename files'
                    file_op.save()

                    results['errors'].append({
                        'id': book.id,
                        'title': book.finalmetadata.final_title,
                        'error': 'Failed to rename files',
                        'operation_id': file_op.id
                    })

            except Exception as e:
                # Update file operation if it exists
                try:
                    file_op.status = 'failed'
                    file_op.error_message = str(e)
                    file_op.save()
                    operation_id = file_op.id
                except Exception:
                    operation_id = None

                results['errors'].append({
                    'id': book.id,
                    'title': book.finalmetadata.final_title,
                    'error': str(e),
                    'operation_id': operation_id
                })

        return JsonResponse(results)

    def _generate_warnings(self, book):
        """Generate warnings for the book (same as in BookRenamerView)."""
        warnings = []
        fm = book.finalmetadata

        # Check for missing metadata
        if not fm.final_author or fm.final_author.strip() == "":
            warnings.append('Missing author information')

        if not fm.final_title or fm.final_title.strip() == "":
            warnings.append('Missing title information')

        # Check confidence levels
        if hasattr(fm, 'overall_confidence') and fm.overall_confidence is not None:
            if fm.overall_confidence < 0.5:
                warnings.append(f'Low confidence score: {fm.overall_confidence:.2f}')
            elif fm.overall_confidence < 0.7:
                warnings.append(f'Medium confidence score: {fm.overall_confidence:.2f}')

        return warnings

    def _rename_book_files(self, book, file_op):
        """Rename all files associated with a book with detailed tracking."""
        import os
        import shutil

        renamer_view = BookRenamerView()
        new_path = renamer_view._generate_new_file_path(book)

        if not book.file_path or not os.path.exists(book.file_path):
            return False

        try:
            # Create directory structure
            new_dir = os.path.dirname(new_path)
            os.makedirs(new_dir, exist_ok=True)

            # Get base paths
            old_base = os.path.splitext(book.file_path)[0]
            new_base = os.path.splitext(new_path)[0]

            # Files to rename
            files_to_rename = []
            additional_files = []

            # Main file
            if os.path.exists(book.file_path):
                files_to_rename.append((book.file_path, new_path))

            # Associated files (cover, opf, txt, etc.)
            for ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.opf', '.txt', '.json']:
                old_file = old_base + ext
                if os.path.exists(old_file):
                    new_file = new_base + ext
                    files_to_rename.append((old_file, new_file))
                    additional_files.append({
                        'original': old_file,
                        'new': new_file,
                        'type': ext.replace('.', '')
                    })

            # Look for other related files (different naming patterns)
            old_dir = os.path.dirname(book.file_path)
            old_filename = os.path.splitext(os.path.basename(book.file_path))[0]

            if os.path.exists(old_dir):
                for filename in os.listdir(old_dir):
                    if filename.startswith(old_filename) and filename != os.path.basename(book.file_path):
                        old_file = os.path.join(old_dir, filename)
                        new_filename = filename.replace(old_filename, os.path.splitext(os.path.basename(new_path))[0])
                        new_file = os.path.join(new_dir, new_filename)

                        files_to_rename.append((old_file, new_file))
                        additional_files.append({
                            'original': old_file,
                            'new': new_file,
                            'type': 'related'
                        })

            # Perform the renames
            renamed_files = []
            try:
                for old_file, new_file in files_to_rename:
                    shutil.move(old_file, new_file)
                    renamed_files.append(new_file)

                # Update database
                book.file_path = new_path

                # Update cover path
                if book.cover_path and book.cover_path.startswith(old_base):
                    new_cover_path = book.cover_path.replace(old_base, new_base)
                    book.cover_path = new_cover_path
                else:
                    new_cover_path = book.cover_path

                # Update OPF path if it exists
                if hasattr(book, 'opf_path') and book.opf_path and book.opf_path.startswith(old_base):
                    new_opf_path = book.opf_path.replace(old_base, new_base)
                    book.opf_path = new_opf_path
                else:
                    new_opf_path = getattr(book, 'opf_path', '')

                book.save()

                return {
                    'new_path': new_path,
                    'new_cover_path': new_cover_path,
                    'new_opf_path': new_opf_path,
                    'additional_files': additional_files
                }

            except Exception as e:
                # Rollback on error
                for i, (old_file, new_file) in enumerate(files_to_rename[:len(renamed_files)]):
                    try:
                        shutil.move(new_file, old_file)
                    except Exception:
                        pass
                raise e

        except Exception:
            return False


class BookRenamerRevertView(LoginRequiredMixin, View):
    """Revert file rename operations using operation tracking."""

    def post(self, request):

        batch_id = request.POST.get('batch_id')
        operation_ids = request.POST.getlist('operation_ids')

        if not batch_id and not operation_ids:
            return JsonResponse({'error': 'No operations specified for reversal'}, status=400)

        # Get operations to revert
        if batch_id:
            operations = FileOperation.objects.filter(
                batch_id=batch_id,
                status='completed'
            ).select_related('book')
        else:
            operations = FileOperation.objects.filter(
                id__in=operation_ids,
                status='completed'
            ).select_related('book')

        results = {
            'success': [],
            'errors': [],
            'total': len(operations)
        }

        for operation in operations:
            try:
                success = self._revert_file_operation(operation)
                if success:
                    operation.status = 'reverted'
                    operation.save()

                    results['success'].append({
                        'operation_id': operation.id,
                        'book_id': operation.book.id,
                        'title': operation.book.finalmetadata.final_title if operation.book.finalmetadata else 'Unknown',
                        'reverted_from': operation.new_file_path,
                        'reverted_to': operation.original_file_path
                    })
                else:
                    results['errors'].append({
                        'operation_id': operation.id,
                        'book_id': operation.book.id,
                        'title': operation.book.finalmetadata.final_title if operation.book.finalmetadata else 'Unknown',
                        'error': 'Failed to revert file operation'
                    })
            except Exception as e:
                results['errors'].append({
                    'operation_id': operation.id,
                    'book_id': operation.book.id,
                    'title': operation.book.finalmetadata.final_title if operation.book.finalmetadata else 'Unknown',
                    'error': str(e)
                })

        return JsonResponse(results)

    def _revert_file_operation(self, operation):
        """Revert a single file operation."""
        import os
        import shutil
        import json

        try:
            book = operation.book

            # Check if new files exist
            if not os.path.exists(operation.new_file_path):
                return False

            # Create original directory if needed
            original_dir = os.path.dirname(operation.original_file_path)
            os.makedirs(original_dir, exist_ok=True)

            # Revert main file
            shutil.move(operation.new_file_path, operation.original_file_path)

            # Revert additional files
            if operation.additional_files:
                try:
                    additional_files = json.loads(operation.additional_files)
                    for file_info in additional_files:
                        if os.path.exists(file_info['new']):
                            # Create directory for original file if needed
                            os.makedirs(os.path.dirname(file_info['original']), exist_ok=True)
                            shutil.move(file_info['new'], file_info['original'])
                except (json.JSONDecodeError, KeyError):
                    # Continue even if additional files fail
                    pass

            # Update database
            book.file_path = operation.original_file_path

            if operation.original_cover_path:
                book.cover_path = operation.original_cover_path

            if hasattr(book, 'opf_path') and operation.original_opf_path:
                book.opf_path = operation.original_opf_path

            book.save()

            # Try to remove empty directories
            try:
                new_dir = os.path.dirname(operation.new_file_path)
                if os.path.exists(new_dir) and not os.listdir(new_dir):
                    os.rmdir(new_dir)

                    # Try to remove parent directories if empty
                    parent_dir = os.path.dirname(new_dir)
                    while parent_dir and parent_dir != os.path.dirname(parent_dir):
                        if os.path.exists(parent_dir) and not os.listdir(parent_dir):
                            os.rmdir(parent_dir)
                            parent_dir = os.path.dirname(parent_dir)
                        else:
                            break
            except OSError:
                # Don't fail the revert if directory cleanup fails
                pass

            return True

        except Exception:
            return False


class BookRenamerHistoryView(LoginRequiredMixin, ListView):
    """View recent file operations with revert capabilities."""
    model = FileOperation
    template_name = 'books/book_renamer_history.html'
    context_object_name = 'operations'
    paginate_by = 50

    def get_queryset(self):
        return FileOperation.objects.select_related('book', 'book__finalmetadata', 'user').order_by('-operation_date')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Group operations by batch for easier reversal
        operations_by_batch = {}
        for operation in context['operations']:
            if operation.batch_id:
                batch_id = str(operation.batch_id)
                if batch_id not in operations_by_batch:
                    operations_by_batch[batch_id] = []
                operations_by_batch[batch_id].append(operation)

        context['operations_by_batch'] = operations_by_batch
        return context


# =============================================================================
# AJAX VIEWS
# =============================================================================


def ajax_response_handler(view_func):
    """Decorator to standardize AJAX response handling"""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        try:
            if request.method == 'POST' and request.content_type == 'application/json':
                request.json = json.loads(request.body)

            result = view_func(request, *args, **kwargs)

            if isinstance(result, dict):
                return JsonResponse(result)
            return result

        except json.JSONDecodeError:
            return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
        except Exception as e:
            logger.error(f"Error in {view_func.__name__}: {e}")
            return JsonResponse({'success': False, 'error': str(e)}, status=500)

    return wrapper


@ajax_response_handler
@require_http_methods(["POST"])
def ajax_update_book_status(request, book_id):
    """AJAX view to update book status flags."""
    return BookStatusManager.update_book_status(request, book_id)


@ajax_response_handler
@require_http_methods(["POST"])
def ajax_update_book_metadata(request, book_id):
    """Update book metadata via AJAX."""
    book = get_object_or_404(Book, id=book_id)
    data = request.json

    final_metadata, _ = FinalMetadata.objects.get_or_create(book=book)

    updatable_fields = [
        'final_title', 'final_author', 'final_series', 'final_series_number',
        'final_publisher', 'language', 'publication_date'
    ]

    for field in updatable_fields:
        if field in data:
            setattr(final_metadata, field, data[field])

    final_metadata.is_reviewed = True
    final_metadata.save()

    return {
        'success': True,
        'message': 'Metadata updated successfully',
        'confidence': final_metadata.overall_confidence,
        'completeness': final_metadata.completeness_score,
    }


@ajax_response_handler
def ajax_get_metadata_conflicts(request, book_id):
    """AJAX view to get metadata conflicts for a book."""
    return MetadataConflictAnalyzer.get_metadata_conflicts(request, book_id)


@ajax_response_handler
@require_http_methods(["POST"])
def ajax_trigger_scan(request):
    """Trigger a scan via AJAX."""
    data = request.json
    folder_path = data.get('folder_path')
    scan_type = data.get('scan_type', 'full')

    if scan_type == 'folder' and not folder_path:
        return {
            'success': False,
            'error': 'No folder path provided for folder scan'
        }

    # Always create a new scan status entry for each scan
    scan_status = ScanStatus.objects.create(
        status='Running',
        progress=0,
        message='Initializing scan...'
    )

    # Add better error handling for subprocess
    # Use Django's BASE_DIR to ensure we're in the correct directory
    project_dir = getattr(settings, 'BASE_DIR', os.getcwd())
    manage_py_path = os.path.join(project_dir, 'manage.py')

    cmd = [sys.executable, manage_py_path, 'scan_ebooks']
    if scan_type == 'folder':
        cmd.append(folder_path)
    elif scan_type == 'rescan':
        cmd.append('--rescan')

    try:
        subprocess.Popen(cmd, cwd=project_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        logger.info(f"Started scan process with command: {' '.join(cmd)} in directory: {project_dir}")
    except Exception as e:
        logger.error(f"Failed to start scan process: {e}")
        scan_status.status = 'Error'
        scan_status.message = f'Failed to start scan: {str(e)}'
        scan_status.save()
        return {'success': False, 'error': f'Failed to start scan: {str(e)}'}

    message = 'Scan initiated'
    scan_message = 'Scan started'

    if scan_type == 'folder':
        message += f' for folder: {folder_path}'
        scan_message += f' for folder: {folder_path}'
    elif scan_type == 'rescan':
        message += ' (rescan mode)'
        scan_message += ' (rescan mode)'

    scan_status.message = scan_message
    scan_status.save()

    return {'success': True, 'message': message}


@ajax_response_handler
@require_POST
def ajax_upload_cover(request, book_id):
    """AJAX endpoint for immediate cover upload and preview."""
    try:
        book = Book.objects.get(pk=book_id)

        if 'cover_file' not in request.FILES:
            return JsonResponse({
                'success': False,
                'error': 'No file provided'
            }, status=400)

        uploaded_file = request.FILES['cover_file']

        # Validate file
        if not uploaded_file.content_type.startswith('image/'):
            return JsonResponse({
                'success': False,
                'error': 'File must be an image'
            }, status=400)

        # Upload and create cover entry
        result = CoverManager.handle_cover_upload(request, book, uploaded_file)

        if result['success']:
            return JsonResponse({
                'success': True,
                'cover_path': result['cover_path'],
                'cover_id': result['cover_id'],
                'filename': result['filename'],
                'message': 'Cover uploaded successfully'
            })
        else:
            return JsonResponse({
                'success': False,
                'error': result['error']
            }, status=500)

    except Book.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Book not found'
        }, status=404)
    except Exception as e:
        logger.error(f"Error in ajax_upload_cover for book {book_id}: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@ajax_response_handler
@require_POST
def ajax_manage_cover(request, book_id):
    """AJAX endpoint for cover management."""
    return CoverManager.manage_cover_action(request, book_id)


@ajax_response_handler
@csrf_exempt
def ajax_get_metadata_remove(request, book_id):
    """Remove metadata entry via AJAX."""
    return MetadataRemover.remove_metadata(request, book_id)


# =============================================================================
# SCAN FOLDER MANAGEMENT
# =============================================================================

def scan_folders_manage(request):
    """Combined scan folder management view."""
    if request.method == 'POST':
        form = ScanFolderForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Scan folder added successfully!')
            return redirect('scan_folders')
    else:
        form = ScanFolderForm()

    folders = ScanFolder.objects.annotate(
        book_count=Count('book')
    ).order_by('path')

    context = {
        'form': form,
        'folders': folders,
        'total_folders': folders.count(),
        'active_folders': folders.filter(is_active=True).count(),
    }

    return render(request, 'books/scan_folders_manage.html', context)


@ajax_response_handler
@require_http_methods(["POST"])
def delete_scan_folder_ajax(request, folder_id):
    """Delete a scan folder via AJAX."""
    folder = get_object_or_404(ScanFolder, id=folder_id)
    folder_path = folder.path
    folder.delete()

    return {
        'success': True,
        'message': f'Deleted scan folder: {folder_path}'
    }


@ajax_response_handler
def current_scan_status(request):
    """Return current scan status as JSON."""
    scan_status = ScanStatus.objects.order_by('-started').first()
    if scan_status:
        return {
            'status': scan_status.status,
            'progress': scan_status.progress,
            'started': scan_status.started.strftime('%B %d, %Y %H:%M'),
            'message': scan_status.message or "No additional information."
        }
    return JsonResponse({'error': 'No active scan.'}, status=404)


# =============================================================================
# SIMPLE VIEWS
# =============================================================================


def book_detail(request, book_id):
    """Simple book detail view with navigation."""
    book = get_object_or_404(Book, pk=book_id)
    final_metadata = getattr(book, "finalmetadata", None)

    all_books = list(Book.objects.order_by("id").values_list("id", flat=True))
    index = all_books.index(book.id)

    prev_book_id = all_books[index - 1] if index > 0 else None
    next_book_id = all_books[index + 1] if index + 1 < len(all_books) else None

    # Find next book that still needs review
    next_needsreview = Book.objects.filter(
        id__gt=book.id,
        finalmetadata__is_reviewed__in=[False, None]
    ).order_by("id").first()

    next_needsreview_id = getattr(next_needsreview, "id", None)

    return render(request, "books/book_detail.html", {
        "book": book,
        "final_metadata": final_metadata,
        "prev_book_id": prev_book_id,
        "next_book_id": next_book_id,
        "next_needsreview_id": next_needsreview_id
    })


@require_POST
def toggle_needs_review(request, book_id):
    """Toggle the needs review status of a book."""
    book = get_object_or_404(Book, pk=book_id)
    final_metadata = getattr(book, "finalmetadata", None)

    if final_metadata:
        final_metadata.is_reviewed = not final_metadata.is_reviewed
        final_metadata.save()

    return redirect('books:book_detail', pk=book.id)


@csrf_exempt
@require_POST
def rescan_external_metadata(request, book_id):
    """Rescan external metadata using current final metadata as search terms."""
    import traceback
    from django.http import JsonResponse
    from books.scanner.external import query_metadata_and_covers_with_terms
    from django.core.cache import cache

    try:
        book = get_object_or_404(Book, pk=book_id)

        # Handle both JSON and form data
        if request.content_type == 'application/json':
            import json
            data = json.loads(request.body)
            sources = data.get('sources', [])
            clear_existing = data.get('clear_existing', False)
            force_refresh = data.get('force_refresh', False)
            title_override = data.get('title_search', '').strip()
            author_override = data.get('author_search', '').strip()
            isbn_override = data.get('isbn_override', '').strip()
            series_override = data.get('series_override', '').strip()
        else:
            # Get parameters from POST data
            sources = request.POST.getlist('sources[]')
            clear_existing = request.POST.get('clear_existing') == 'true'
            force_refresh = request.POST.get('force_refresh') == 'true'

            # Get override search terms
            title_override = request.POST.get('title_override', '').strip()
            author_override = request.POST.get('author_override', '').strip()
            isbn_override = request.POST.get('isbn_override', '').strip()
            series_override = request.POST.get('series_override', '').strip()

        logger.info(f"Starting external metadata rescan for book {book_id}")
        logger.info(f"Sources: {sources}")
        logger.info(f"Clear existing: {clear_existing}")
        logger.info(f"Force refresh: {force_refresh}")

        # Get current final metadata or use overrides
        final_metadata = getattr(book, 'finalmetadata', None)

        search_title = title_override
        search_author = author_override
        search_isbn = isbn_override
        search_series = series_override

        if not search_title and final_metadata:
            search_title = final_metadata.final_title or ''
        if not search_author and final_metadata:
            search_author = final_metadata.final_author or ''
        if not search_isbn and final_metadata:
            search_isbn = final_metadata.isbn or ''
        if not search_series and final_metadata:
            search_series = final_metadata.final_series or ''

        # Fall back to basic book data if no final metadata
        if not search_title:
            # Try to get title from existing titles
            first_title = book.titles.filter(is_active=True).order_by('-confidence').first()
            if first_title:
                search_title = first_title.title
            else:
                # Last resort: use filename without extension
                search_title = os.path.splitext(book.filename)[0]
        if not search_author:
            # Try to get author from existing book authors
            first_author = book.bookauthor.filter(is_main_author=True, is_active=True).first()
            if first_author:
                search_author = first_author.author.name

        logger.info(f"Search terms - Title: '{search_title}', Author: '{search_author}', ISBN: '{search_isbn}', Series: '{search_series}'")

        if not search_title and not search_author and not search_isbn:
            return JsonResponse({
                'success': False,
                'error': 'No search terms available. Please provide at least a title, author, or ISBN.'
            })

        # Clear cache if force refresh is enabled
        if force_refresh:
            cache_keys = [
                f"google_books_{search_title}_{search_author}",
                f"openlibrary_{search_title}_{search_author}",
                f"goodreads_{search_title}_{search_author}",
            ]
            if search_isbn:
                cache_keys.extend([
                    f"google_books_isbn_{search_isbn}",
                    f"openlibrary_isbn_{search_isbn}",
                ])
            for key in cache_keys:
                cache.delete(key)

        # Clear existing external metadata if requested
        if clear_existing:
            logger.info("Clearing existing external metadata")
            external_sources = ['google_books', 'open_library', 'goodreads']

            # Clear metadata from external sources
            book.titles.filter(source__name__in=external_sources).update(is_active=False)
            book.bookauthor.filter(source__name__in=external_sources).update(is_active=False)
            book.bookgenre.filter(source__name__in=external_sources).update(is_active=False)
            book.series_info.filter(source__name__in=external_sources).update(is_active=False)
            book.bookpublisher.filter(source__name__in=external_sources).update(is_active=False)
            book.metadata.filter(source__name__in=external_sources).update(is_active=False)
            book.covers.filter(source__name__in=external_sources).update(is_active=False)

        # Count existing metadata before rescan
        before_counts = {
            'titles': book.titles.filter(is_active=True).count(),
            'authors': book.bookauthor.filter(is_active=True).count(),
            'genres': book.bookgenre.filter(is_active=True).count(),
            'series': book.series_info.filter(is_active=True).count(),
            'publishers': book.bookpublisher.filter(is_active=True).count(),
            'covers': book.covers.filter(is_active=True).count(),
            'metadata': book.metadata.filter(is_active=True).count(),
        }

        # Perform the external metadata query using custom search terms
        # Note: This uses the new function that accepts custom search terms
        try:
            query_metadata_and_covers_with_terms(book, search_title, search_author, search_isbn)
        except Exception as e:
            logger.error(f"Error during external metadata query: {e}")
            return JsonResponse({
                'success': False,
                'error': f'Error querying external sources: {str(e)}'
            })

        # Count new metadata after rescan
        after_counts = {
            'titles': book.titles.filter(is_active=True).count(),
            'authors': book.bookauthor.filter(is_active=True).count(),
            'genres': book.bookgenre.filter(is_active=True).count(),
            'series': book.series_info.filter(is_active=True).count(),
            'publishers': book.bookpublisher.filter(is_active=True).count(),
            'covers': book.covers.filter(is_active=True).count(),
            'metadata': book.metadata.filter(is_active=True).count(),
        }

        # Calculate what was added
        added_counts = {
            key: after_counts[key] - before_counts[key]
            for key in before_counts.keys()
        }

        logger.info(f"External metadata rescan completed for book {book_id}")
        logger.info(f"Added metadata: {added_counts}")

        return JsonResponse({
            'success': True,
            'message': 'External metadata rescan completed successfully',
            'search_terms': {
                'title': search_title,
                'author': search_author,
                'isbn': search_isbn,
                'series': search_series,
            },
            'sources_queried': sources,
            'before_counts': before_counts,
            'after_counts': after_counts,
            'added_counts': added_counts,
        })

    except Exception as e:
        logger.error(f"Error in rescan_external_metadata: {e}")
        logger.error(traceback.format_exc())
        return JsonResponse({
            'success': False,
            'error': f'An error occurred during the rescan: {str(e)}'
        })


@require_POST
def ajax_rescan_external_metadata(request, book_id):
    """AJAX wrapper for rescan_external_metadata for the metadata page quick rescan."""
    import json

    try:
        # Parse the request data
        data = json.loads(request.body)

        # Extract search terms and options
        search_terms = data.get('searchTerms', {})
        sources = data.get('sources', ['google', 'openlibrary', 'goodreads'])
        options = data.get('options', {})

        # Prepare the data for the existing rescan function
        rescan_data = {
            'sources': sources,
            'clear_existing': options.get('clearExisting', False),
            'force_refresh': options.get('forceRefresh', True),
            'title_search': search_terms.get('title', ''),
            'author_search': search_terms.get('author', ''),
            'isbn_override': search_terms.get('isbn', ''),
            'series_override': search_terms.get('series', '')
        }

        # Create a new request object with the formatted data
        from django.http import HttpRequest
        new_request = HttpRequest()
        new_request.method = 'POST'
        new_request.content_type = 'application/json'
        new_request._body = json.dumps(rescan_data).encode('utf-8')
        new_request.user = request.user

        # Call the existing rescan function
        response = rescan_external_metadata(new_request, book_id)

        # Extract JSON data from the response
        if hasattr(response, 'content'):
            response_data = json.loads(response.content.decode('utf-8'))
            # Add new_metadata_count for the UI
            if response_data.get('success'):
                added_counts = response_data.get('added_counts', {})
                total_new = sum(added_counts.values())
                response_data['new_metadata_count'] = total_new
            return JsonResponse(response_data)
        else:
            return response

    except Exception as e:
        logger.error(f"Error in ajax_rescan_external_metadata: {e}")
        return JsonResponse({
            'success': False,
            'error': f'An error occurred during the quick rescan: {str(e)}'
        })


@ajax_response_handler
@require_POST
def update_trust(request, pk):
    """Update trust level for a data source."""
    data_source = get_object_or_404(DataSource, pk=pk)
    trust_level_str = request.POST.get('trust_level')

    if trust_level_str is None:
        return {'success': False, 'error': 'Missing trust_level'}

    try:
        trust_level = float(trust_level_str)
    except (ValueError, TypeError):
        return {'success': False, 'error': 'Invalid trust_level format'}

    if not (0.0 <= trust_level <= 1.0):
        return {'success': False, 'error': 'Trust level must be between 0.0 and 1.0'}

    data_source.trust_level = trust_level
    data_source.save()

    return {
        'success': True,
        'message': 'Trust level updated successfully',
        'new_trust_level': trust_level
    }
