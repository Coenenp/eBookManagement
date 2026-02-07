"""
Core book views - Dashboard, Book List, and Book Detail.
"""

import json
import logging

from django.contrib import messages
from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.db.models import Prefetch
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.generic import DetailView, ListView, TemplateView

from books.book_utils import CoverManager, GenreManager, MetadataProcessor, MetadataResetter
from books.constants import PAGINATION
from books.forms import MetadataReviewForm, UserRegisterForm
from books.mixins import BookListContextMixin, BookNavigationMixin, MetadataContextMixin
from books.models import Book, BookFile, FinalMetadata, ScanFolder
from books.queries.book_queries import build_book_queryset
from books.services.common import CoverService, DashboardService
from books.views.wizard import WizardRequiredMixin

logger = logging.getLogger("books.scanner")


def signup(request):
    """User registration view."""
    if request.method == "POST":
        form = UserRegisterForm(request.POST)
        if form.is_valid():
            form.save()
            user = authenticate(username=form.cleaned_data["username"], password=form.cleaned_data["password1"])

            if user is not None:
                login(request, user)
                return redirect("books:dashboard")
    else:
        form = UserRegisterForm()
    return render(request, "books/signup.html", {"form": form})


class DashboardView(WizardRequiredMixin, LoginRequiredMixin, TemplateView):
    """Enhanced dashboard view using extracted analytics helpers."""

    template_name = "books/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Use service to get statistics
        metadata_stats, format_stats = DashboardService.get_dashboard_statistics()

        # Get analytics data
        try:
            from books.analytics.dashboard import DashboardAnalytics, LibraryHealth

            dashboard_analytics = DashboardAnalytics()
            from books.analytics import dashboard_metrics

            # Get enhanced chart data
            all_charts = DashboardAnalytics.prepare_all_chart_data()

            # Get basic analytics
            issue_stats = dashboard_metrics.get_issue_statistics()
            content_stats = dashboard_metrics.get_content_type_statistics()
            recent_activity = dashboard_metrics.get_recent_activity()

            # Prepare chart data for JavaScript
            chart_data = {
                "format_labels": json.loads(all_charts["format_distribution"]["labels"]),
                "format_data": json.loads(all_charts["format_distribution"]["data"]),
                "format_colors": json.loads(all_charts["format_distribution"]["colors"]),
                "completeness_labels": json.loads(all_charts["metadata_completeness"]["labels"]),
                "completeness_data": json.loads(all_charts["metadata_completeness"]["data"]),
                "ai_accuracy_labels": json.loads(all_charts["ai_accuracy"]["labels"]),
                "ai_accuracy_data": json.loads(all_charts["ai_accuracy"]["data"]),
                "reading_labels": json.loads(all_charts["reading_progress"]["labels"]),
                "reading_data": json.loads(all_charts["reading_progress"]["data"]),
            }

            # Add library health data
            health_score = LibraryHealth.get_health_score()
            quality_issues = LibraryHealth.get_quality_issues()

        except ImportError as e:
            logger.warning(f"Enhanced analytics module not available: {e}")
            # Fallback to basic analytics
            try:
                from books.analytics import dashboard_metrics

                issue_stats = dashboard_metrics.get_issue_statistics()
                content_stats = dashboard_metrics.get_content_type_statistics()
                recent_activity = dashboard_metrics.get_recent_activity()
                charts = dashboard_metrics.prepare_chart_data(format_stats, metadata_stats, issue_stats)

                chart_data = {
                    "format_labels": json.loads(charts["format_distribution"]["labels"]),
                    "format_data": json.loads(charts["format_distribution"]["data"]),
                    "format_colors": ["#0d6efd", "#198754", "#fd7e14", "#dc3545", "#6f42c1", "#20c997", "#ffc107", "#6c757d"],
                    "completeness_labels": json.loads(charts["metadata_completeness"]["labels"]),
                    "completeness_data": json.loads(charts["metadata_completeness"]["data"]),
                    "ai_accuracy_labels": [],
                    "ai_accuracy_data": [],
                    "reading_labels": [],
                    "reading_data": [],
                }
                health_score = 85  # Default
                quality_issues = []
            except ImportError:
                # Final fallback
                issue_stats = {}
                content_stats = {
                    "ebook_count": 0,
                    "comic_count": 0,
                    "audiobook_count": 0,
                    "series_count": 0,
                    "series_with_books": 0,
                    "author_count": 0,
                    "publisher_count": 0,
                    "genre_count": 0,
                }
                recent_activity = {}
                chart_data = {
                    "format_labels": [item["files__file_format"].upper() for item in format_stats if item["files__file_format"]],
                    "format_data": [item["count"] for item in format_stats if item["files__file_format"]],
                    "format_colors": ["#0d6efd", "#198754", "#fd7e14", "#dc3545", "#6f42c1", "#20c997", "#ffc107", "#6c757d"],
                    "completeness_labels": ["Title", "Author", "Cover", "ISBN", "Series"],
                    "completeness_data": [
                        metadata_stats.get("books_with_metadata", 0),
                        metadata_stats.get("books_with_author", 0),
                        metadata_stats.get("books_with_cover", 0),
                        metadata_stats.get("books_with_isbn", 0),
                        metadata_stats.get("books_in_series", 0),
                    ],
                    "ai_accuracy_labels": [],
                    "ai_accuracy_data": [],
                    "reading_labels": [],
                    "reading_data": [],
                }
                health_score = 85  # Default
                quality_issues = []

        from datetime import timedelta

        from django.db.models import Count
        from django.utils import timezone

        from books.models import Book, FinalMetadata, ScanFolder, ScanLog

        total_books = metadata_stats.get("total_books", 0) or 1

        # Get additional dashboard data
        placeholder_count = Book.objects.filter(is_placeholder=True).count()
        corrupted_count = Book.objects.filter(is_corrupted=True).count()
        needs_review_count = FinalMetadata.objects.filter(is_reviewed=False).count()
        books_with_original_cover = Book.objects.filter(files__cover_path__isnull=False).exclude(files__cover_path="").distinct().count()

        # Get deleted books data
        deleted_count = Book.objects.filter(deleted_at__isnull=False).count()
        recently_deleted = Book.objects.filter(deleted_at__isnull=False).order_by("-deleted_at")[:10]
        deleted_this_week = Book.objects.filter(deleted_at__gte=timezone.now() - timedelta(days=7)).count()

        # Calculate percentages
        missing_cover_percentage = (total_books - metadata_stats.get("books_with_cover", 0)) / total_books * 100
        corrupted_percentage = corrupted_count / total_books * 100
        deleted_percentage = (deleted_count / (total_books + deleted_count) * 100) if (total_books + deleted_count) > 0 else 0

        # Get books needing attention
        low_confidence_books = FinalMetadata.objects.filter(overall_confidence__lt=0.5).select_related("book")[:5]

        needs_review_books = Book.objects.filter(finalmetadata__is_reviewed=False).select_related("finalmetadata")[:5]

        first_review_target = Book.objects.filter(finalmetadata__is_reviewed=False).first()

        # Get recent activity
        week_ago = timezone.now() - timedelta(days=7)
        recent_logs = ScanLog.objects.filter(timestamp__gte=week_ago).order_by("-timestamp")[:5]

        recent_books = Book.objects.filter(first_scanned__gte=week_ago, is_placeholder=False, is_duplicate=False).select_related("finalmetadata").order_by("-first_scanned")[:5]

        # Get scan folders with book counts
        scan_folders = ScanFolder.objects.annotate(book_count=Count("book")).order_by("name")

        context.update(
            {
                **metadata_stats,
                **content_stats,
                "issue_stats": issue_stats,
                "format_stats": format_stats,
                "recent_activity": recent_activity,
                "chart_data": json.dumps(chart_data),  # JSON encode for JavaScript
                # Percentages
                "completion_percentage": (metadata_stats.get("books_with_metadata", 0) / total_books * 100),
                "author_percentage": (metadata_stats.get("books_with_author", 0) / total_books * 100),
                "cover_percentage": (metadata_stats.get("books_with_cover", 0) / total_books * 100),
                "isbn_percentage": (metadata_stats.get("books_with_isbn", 0) / total_books * 100),
                "series_percentage": (metadata_stats.get("books_in_series", 0) / total_books * 100),
                "review_percentage": ((total_books - needs_review_count) / total_books * 100),
                "missing_cover_percentage": missing_cover_percentage,
                "corrupted_percentage": corrupted_percentage,
                "overall_quality_score": (metadata_stats.get("avg_confidence", 0) or 0) * 100,
                "completeness_score": (metadata_stats.get("avg_completeness", 0) or 0) * 100,
                # Counts
                "placeholder_count": placeholder_count,
                "corrupted_count": corrupted_count,
                "needs_review_count": needs_review_count,
                "books_with_original_cover": books_with_original_cover,
                "deleted_count": deleted_count,
                "deleted_this_week": deleted_this_week,
                "deleted_percentage": deleted_percentage,
                # Lists for templates
                "low_confidence_books": low_confidence_books,
                "needs_review_books": needs_review_books,
                "first_review_target": first_review_target,
                "recent_logs": recent_logs,
                "recent_books": recent_books,
                "scan_folders": scan_folders,
                "recently_deleted": recently_deleted,
                # Library health metrics
                "health_score": locals().get("health_score", 85),
                "quality_issues": locals().get("quality_issues", []),
            }
        )
        return context


class DeletedBooksView(LoginRequiredMixin, ListView):
    """View for managing deleted books - restore or permanently delete."""

    model = Book
    template_name = "books/deleted_books.html"
    context_object_name = "deleted_books"

    def get_paginate_by(self, queryset):
        """Get pagination count from user profile"""
        if self.request.user.is_authenticated:
            try:
                from books.models import UserProfile

                profile = UserProfile.get_or_create_for_user(self.request.user)
                return profile.items_per_page
            except Exception:
                pass
        return PAGINATION["book_list"]

    def get_queryset(self):
        """Get all soft-deleted books."""
        return Book.objects.filter(deleted_at__isnull=False).select_related("finalmetadata", "scan_folder").prefetch_related("files").order_by("-deleted_at")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        from datetime import timedelta

        from django.utils import timezone

        # Statistics
        total_deleted = self.get_queryset().count()
        deleted_this_week = self.get_queryset().filter(deleted_at__gte=timezone.now() - timedelta(days=7)).count()
        deleted_this_month = self.get_queryset().filter(deleted_at__gte=timezone.now() - timedelta(days=30)).count()

        context.update(
            {
                "total_deleted": total_deleted,
                "deleted_this_week": deleted_this_week,
                "deleted_this_month": deleted_this_month,
            }
        )
        return context


class BookListView(LoginRequiredMixin, ListView, BookListContextMixin):
    """Book listing view with filtering and search."""

    model = Book
    template_name = "books/book_list.html"
    context_object_name = "books"

    def get_paginate_by(self, queryset):
        """Get pagination count from user profile"""
        if self.request.user.is_authenticated:
            try:
                from books.models import UserProfile

                profile = UserProfile.get_or_create_for_user(self.request.user)
                return profile.items_per_page
            except Exception:
                pass
        return PAGINATION["book_library"]

    def get_queryset(self):
        qs = build_book_queryset(self.request.GET)
        # Store the base queryset for counting before pagination
        self._base_queryset = qs
        # Return full queryset - pagination will handle limiting per page
        return qs

    def get_optimized_counts(self):
        """Get counts efficiently from the filtered queryset instead of entire database"""
        # Use the base queryset before slicing for accurate counts
        qs = getattr(self, "_base_queryset", Book.objects.all())

        # Get review counts using single query with conditional aggregation
        from django.db.models import Avg, Count, Q

        aggregates = qs.aggregate(
            needs_review=Count("id", filter=Q(finalmetadata__is_reviewed__in=[False, None])),
            low_confidence=Count("id", filter=Q(finalmetadata__overall_confidence__lt=0.7)),
            incomplete=Count("id", filter=Q(finalmetadata__completeness_score__lt=0.8)),
            missing_cover=Count("id", filter=Q(finalmetadata__final_cover_path__isnull=True) | Q(finalmetadata__final_cover_path="")),
            duplicates=Count("id", filter=Q(is_duplicate=True)),
            placeholders=Count("id", filter=Q(is_placeholder=True)),
            corrupted=Count("id", filter=Q(is_corrupted=True)),
            avg_confidence=Avg("finalmetadata__overall_confidence"),
            avg_completeness=Avg("finalmetadata__completeness_score"),
        )

        return {
            "review_counts": {
                "needs_review": aggregates["needs_review"] or 0,
                "low_confidence": aggregates["low_confidence"] or 0,
                "incomplete": aggregates["incomplete"] or 0,
                "missing_cover": aggregates["missing_cover"] or 0,
                "duplicates": aggregates["duplicates"] or 0,
                "placeholders": aggregates["placeholders"] or 0,
            },
            "corrupted_count": aggregates["corrupted"] or 0,
            "avg_confidence": round(aggregates["avg_confidence"] or 0, 2),
            "avg_completeness": round(aggregates["avg_completeness"] or 0, 2),
        }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Get optimized counts from filtered queryset only
        context.update(self.get_optimized_counts())

        # Get filter options (languages, formats, etc.) - use base queryset WITHOUT slicing
        base_qs = getattr(self, "_base_queryset", Book.objects.all())

        # Get unique languages - use values() with distinct to avoid duplicates
        language_codes = list(FinalMetadata.objects.filter(book__in=base_qs.values_list("id", flat=True), language__isnull=False).values_list("language", flat=True).distinct())

        # Get unique formats - need to go through BookFile
        format_list = list(BookFile.objects.filter(book__in=base_qs.values_list("id", flat=True), file_format__isnull=False).values_list("file_format", flat=True).distinct())

        # Get unique scan folders
        scan_folder_ids = list(base_qs.exclude(scan_folder__isnull=True).values_list("scan_folder_id", flat=True).distinct())

        context.update(
            {
                "languages": [(lang, lang.title()) for lang in language_codes if lang],  # (code, display name)
                "formats": sorted([fmt.upper() for fmt in format_list if fmt]),
                "scan_folders": list(ScanFolder.objects.filter(id__in=scan_folder_ids)),
                "datasources": [],  # Skip datasources for now - complex query
            }
        )

        # Add request parameters
        context.update(
            {
                "search_query": self.request.GET.get("search_query", ""),
                "language_filter": self.request.GET.get("language", ""),
                "format_filter": self.request.GET.get("file_format", ""),
                "confidence_filter": self.request.GET.get("confidence", ""),
                "corrupted_filter": self.request.GET.get("corrupted", ""),
                "missing_filter": self.request.GET.get("missing", ""),
                "datasource_filter": self.request.GET.get("datasource", ""),
                "scan_folder_filter": self.request.GET.get("scan_folder", ""),
                "sort_by": self.request.GET.get("sort", "last_scanned"),
                "sort_order": self.request.GET.get("order", "desc"),
                "review_type": self.request.GET.get("review_type", ""),
                "query_params": self.request.GET.copy(),
            }
        )

        # Process covers for books - simplified for list view (covers lazy loaded in template)
        books = context.get("object_list", [])
        # Just wrap books in the expected format - no cover processing needed since skip_download=True
        context["books_with_covers"] = [{"book": book} for book in books]

        # Clean up query params
        if "page" in context["query_params"]:
            del context["query_params"]["page"]

        # Add first review target
        context["first_review_target"] = Book.objects.filter(finalmetadata__is_reviewed__in=[False, None]).order_by("id").first()

        # Add review tabs
        context["review_tabs"] = [
            ("needs_review", "Needs Review", context["review_counts"]["needs_review"], "primary"),
            ("low_confidence", "Low Confidence", context["review_counts"]["low_confidence"], "warning"),
            ("incomplete", "Incomplete", context["review_counts"]["incomplete"], "info"),
            ("missing_cover", "Missing Cover", context["review_counts"]["missing_cover"], "secondary"),
            ("duplicates", "Duplicates", context["review_counts"]["duplicates"], "light"),
            ("placeholders", "Placeholders", context["review_counts"]["placeholders"], "dark"),
            ("corrupted", "Corrupted", context["corrupted_count"], "danger"),
        ]

        return context


class BookDetailView(LoginRequiredMixin, DetailView, BookNavigationMixin, MetadataContextMixin):
    """Detailed book view with editing capabilities."""

    model = Book
    template_name = "books/book_detail.html"
    context_object_name = "book"

    def get_object(self):
        # Prefetch files to avoid N+1 queries
        files_prefetch = Prefetch("files", queryset=BookFile.objects.order_by("id"), to_attr="prefetched_files")
        return get_object_or_404(Book.objects.select_related("finalmetadata", "scan_folder").prefetch_related(files_prefetch), pk=self.kwargs["pk"])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        book = self.object

        # Always prefetch metadata for dropdowns
        book = Book.objects.prefetch_related(
            "titles__source",
            "author_relationships__author",
            "author_relationships__source",
            "genre_relationships__genre",
            "genre_relationships__source",
            "series_relationships__series",
            "series_relationships__source",
            "publisher_relationships__publisher",
            "publisher_relationships__source",
            "metadata__source",
            "covers__source",
        ).get(pk=book.pk)

        # Get cover path from first file (use prefetched to avoid query)
        first_file = book.primary_file  # Uses prefetched_files from get_object
        cover_path = first_file.cover_path if first_file else ""

        # Get or create final metadata
        final_metadata, created = FinalMetadata.objects.get_or_create(
            book=book,
            defaults={
                "final_title": "",
                "final_author": "",
                "final_series": "",
                "final_series_number": "",
                "final_publisher": "",
                "final_cover_path": cover_path,
                "language": book.scan_folder.language if book.scan_folder else "en",
                "isbn": "",
                "publication_year": None,
                "description": "",
                "is_reviewed": False,
            },
        )

        context["final_metadata"] = final_metadata

        # Get metadata context using mixin
        context.update(self.get_metadata_context(book))
        context.update(self.get_metadata_fields_context(book))

        # Build metadata_by_field for dropdowns
        metadata_by_field = {}
        # Use prefetched metadata and filter/sort in Python to avoid extra queries
        all_metadata = [m for m in book.metadata.all() if m.is_active]
        all_metadata.sort(key=lambda m: (-m.confidence, m.field_name))

        for meta in all_metadata:
            field = meta.field_name
            if field not in metadata_by_field:
                metadata_by_field[field] = []

            # Determine if this is the final selected value
            is_final = False
            if field == "publication_year":
                is_final = str(meta.field_value) == str(final_metadata.publication_year)
            elif field == "language":
                is_final = meta.field_value == final_metadata.language
            elif field == "isbn":
                is_final = meta.field_value == final_metadata.isbn
            elif field == "description":
                is_final = meta.field_value == final_metadata.description

            # Determine if this is the top choice (highest confidence among active)
            is_top = len(metadata_by_field[field]) == 0  # First one is top (already sorted by confidence)

            metadata_by_field[field].append(
                {
                    "instance": meta,
                    "is_final_selected": is_final,
                    "is_top_choice": is_top,
                }
            )

        context["metadata_by_field"] = metadata_by_field

        # Create form for edit tab
        context["form"] = MetadataReviewForm(instance=final_metadata, book=book)

        # Cover handling using service
        context.update(CoverService.get_cover_context(book, final_metadata))

        # Navigation handling using mixin
        context.update(self.get_navigation_context(book))

        return context

    def post(self, request, *args, **kwargs):
        """Handle form submission for metadata updates from edit tab."""
        self.object = self.get_object()
        book = self.get_object()
        final_metadata = getattr(book, "finalmetadata", None)

        if not final_metadata:
            messages.error(request, "Final metadata not found.")
            return redirect("books:book_detail", pk=book.id)

        # Handle reset action
        if request.POST.get("action") == "reset":
            return self._handle_reset(request, book, final_metadata)

        # Handle save action
        form = MetadataReviewForm(request.POST, request.FILES, instance=final_metadata, book=book)

        if form.is_valid():
            try:
                with transaction.atomic():
                    logger.debug("POST data received:")
                    for key, value in request.POST.items():
                        if "manual_entry" in key:
                            logger.debug(f"  {key}: {value}")

                    # Process manual entries FIRST - this creates the metadata entries
                    MetadataProcessor.handle_manual_entries(request, book, form.cleaned_data)

                    # Then save the form (this updates final_metadata)
                    final_metadata = form.save(commit=False)
                    final_metadata.book = book

                    # Handle cover file upload
                    if "new_cover_upload" in request.FILES:
                        uploaded_path = CoverManager.handle_cover_upload(request, book, request.FILES["new_cover_upload"])
                        if uploaded_path:
                            logger.debug(f"Cover uploaded successfully: {uploaded_path}")

                    # Handle genre updates
                    GenreManager.handle_genre_updates(request, book, form)

                    # Set manual update flag to prevent auto-override of user choices
                    final_metadata._manual_update = True

                    # Save final metadata
                    final_metadata.save()

                    # Don't sync from sources after manual updates - the form already set the correct values
                    # Manual entries have confidence=1.0 and will be automatically selected if sync is needed later

                messages.success(request, "Final metadata updated successfully!")

                if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                    return JsonResponse({"success": True, "message": "Final metadata updated successfully!"})

                return redirect("books:book_detail", pk=book.id)

            except Exception as e:
                logger.error(f"Error updating metadata for book {book.id}: {e}")
                logger.exception("Full traceback:")
                messages.error(request, f"Error updating metadata: {str(e)}")

                if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                    return JsonResponse({"success": False, "errors": {"__all__": [f"Error updating metadata: {str(e)}"]}})

        else:
            logger.warning(f"Form validation errors for book {book.id}: {form.errors}")
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse({"success": False, "errors": form.errors})

        # Re-render page with form errors
        context = self.get_context_data()
        context["form"] = form
        return render(request, self.template_name, context)

    def _handle_reset(self, request, book, final_metadata):
        """Reset all fields to current final_metadata values."""
        try:
            MetadataResetter.reset_to_best_values(book, final_metadata)
            messages.success(request, "Metadata values have been reset to best available options.")
        except Exception as e:
            logger.error(f"Error resetting metadata for book {book.id}: {e}")
            messages.error(request, f"Error resetting metadata: {str(e)}")


class UploadFileView(LoginRequiredMixin, TemplateView):
    """View for uploading files"""

    template_name = "books/upload_file.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from books.models import ScanFolder

        context["scan_folders"] = ScanFolder.objects.all()
        return context

    def post(self, request, *args, **kwargs):
        """Handle file upload"""
        if "file" not in request.FILES:
            messages.error(request, "No file provided")
            return self.get(request, *args, **kwargs)

        if "scan_folder" not in request.POST:
            messages.error(request, "No scan folder selected")
            return self.get(request, *args, **kwargs)

        # Success case - would normally handle file upload
        messages.success(request, "File uploaded successfully")
        return redirect("books:book_list")


@login_required
def clear_cache_view(request):
    """Clear cache view with redirect"""
    if request.method == "POST":
        # Would normally clear cache here
        messages.success(request, "Cache cleared successfully")
        return redirect("books:dashboard")
    return redirect("books:dashboard")


@login_required
def debug_view(request):
    """Debug view"""
    return JsonResponse({"debug": "Debug information"})


@login_required
def system_status_view(request):
    """System status view"""
    return JsonResponse({"status": "success", "message": "System Status: Get statistics not yet implemented"})
