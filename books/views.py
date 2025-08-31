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
from django.urls import reverse_lazy
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
    BookGenre, BookMetadata, FinalMetadata, ScanLog, DataSource, ScanStatus, LANGUAGE_CHOICES
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
            cover_path = getattr(book.finalmetadata, 'final_cover_path', '') or book.cover_path
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
        context['languages'] = FinalMetadata.objects.values_list('language', flat=True).distinct().order_by('language')

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

        return context

    def _get_metadata_context(self, book):
        """Get metadata context for template."""
        context = {}

        # Get all metadata grouped by type
        context['all_titles'] = book.titles.filter(is_active=True).order_by('-confidence')
        context['all_authors'] = book.bookauthor.filter(is_active=True).order_by('-confidence', '-is_main_author')
        context['all_genres'] = book.bookgenre.filter(is_active=True).order_by('-confidence')
        context['all_series'] = book.series_info.filter(is_active=True).order_by('-confidence')
        context['all_publishers'] = book.bookpublisher.filter(is_active=True).order_by('-confidence')
        context['all_covers'] = book.covers.filter(is_active=True).order_by('-confidence', '-is_high_resolution')

        # Group additional metadata by field name for dropdowns
        additional_metadata = book.metadata.filter(is_active=True).order_by('field_name', '-confidence')
        metadata_by_field = {}

        for metadata in additional_metadata:
            is_final = False
            if book.finalmetadata:
                final_value = getattr(book.finalmetadata, metadata.field_name, None)
                is_final = str(metadata.field_value) == str(final_value)

            metadata_by_field.setdefault(metadata.field_name, []).append({
                'instance': metadata,
                'is_final_selected': is_final
            })

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
                    # DEBUG: Log all POST data to see what manual entries are flagged
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

            return redirect('books:book_metadata', pk=book.id)

        except Exception as e:
            logger.error(f"Error updating metadata for book {pk}: {e}")
            messages.error(request, f"An error occurred while updating metadata: {str(e)}")
            return redirect('books:book_metadata', pk=pk)

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

        final_year = request.POST.get('final_publication_year', '').strip()
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
            final_value = request.POST.get(f'final_{field_name}', '').strip()
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
        return context

    def post(self, request, *args, **kwargs):
        try:
            from django.utils import timezone

            folder_path = request.POST.get('folder_path')

            # Create or update scan status immediately
            scan_status, created = ScanStatus.objects.get_or_create(
                defaults={
                    'status': 'Running',
                    'progress': 0,
                    'started': timezone.now(),
                    'message': 'Initializing scan...'
                }
            )

            # If status already exists, update it
            if not created:
                scan_status.status = 'Running'
                scan_status.progress = 0
                scan_status.started = timezone.now()
                scan_status.message = 'Initializing scan...'
                scan_status.save()

            if folder_path:
                # Single folder scan
                subprocess.Popen(
                    [sys.executable, 'manage.py', 'scan_ebooks', '--folder', folder_path],
                    cwd=os.getcwd()
                )

                # Update scan status message
                scan_status.message = f'Scan started for folder: {folder_path}'
                scan_status.save()

                messages.success(request, f"Book scan started for folder: {folder_path}")
            else:
                # Full scan of all active folders
                active_folders = ScanFolder.objects.filter(is_active=True)
                folder_count = active_folders.count()

                if folder_count == 0:
                    scan_status.status = 'Failed'
                    scan_status.message = 'No active folders found to scan'
                    scan_status.save()
                    messages.error(request, "No active folders found to scan.")
                    return redirect('books:trigger_scan')

                # Start full scan (let the management command handle all active folders)
                subprocess.Popen(
                    [sys.executable, 'manage.py', 'scan_ebooks'],
                    cwd=os.getcwd()
                )

                # Update scan status message
                scan_status.message = f'Full scan started for {folder_count} active folder{"s" if folder_count != 1 else ""}'
                scan_status.save()

                messages.success(request, f"Full book scan started for {folder_count} active folder{'s' if folder_count != 1 else ''}.")

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

        context['scan_status'] = ScanStatus.objects.last()

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

    scan_status, created = ScanStatus.objects.get_or_create(
        defaults={
            'status': 'Running',
            'progress': 0,
            'started': timezone.now(),
            'message': 'Initializing scan...'
        }
    )

    if not created:
        scan_status.status = 'Running'
        scan_status.progress = 0
        scan_status.started = timezone.now()
        scan_status.message = 'Initializing scan...'
        scan_status.save()

    cmd = [sys.executable, 'manage.py', 'scan_ebooks']
    if scan_type == 'folder':
        cmd.extend(['--folder', folder_path])
    elif scan_type == 'rescan':
        cmd.append('--rescan')

    subprocess.Popen(cmd, cwd=os.getcwd())

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
    scan_status = ScanStatus.objects.last()
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
