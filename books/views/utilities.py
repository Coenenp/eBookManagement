"""
Standalone utility functions for views.
These are functions (not mixins) that can be imported directly.
"""

import os
import re

from django.apps import apps
from django.core.cache import cache
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db.models import Avg, Count, Q

from books.constants import UTILITY_PAGINATION_DEFAULT


def get_filter_params(request_params):
    """
    Extract and validate filter parameters from request.

    Args:
        request_params: Django QueryDict from request.GET

    Returns:
        dict: Cleaned filter parameters
    """
    filters = {}

    # Text filters
    if request_params.get("search_query"):
        filters["search_query"] = request_params.get("search_query").strip()

    if request_params.get("author"):
        filters["author"] = request_params.get("author").strip()

    if request_params.get("format"):
        filters["format"] = request_params.get("format").strip()

    if request_params.get("language"):
        filters["language"] = request_params.get("language").strip()

    # Boolean filters
    if request_params.get("corrupted"):
        filters["corrupted"] = request_params.get("corrupted").lower() in ("true", "1", "yes")

    if request_params.get("missing"):
        filters["missing"] = request_params.get("missing").lower() in ("true", "1", "yes")

    # Numeric filters
    if request_params.get("confidence"):
        try:
            filters["confidence"] = float(request_params.get("confidence"))
        except (ValueError, TypeError):
            pass

    if request_params.get("scan_folder"):
        try:
            filters["scan_folder"] = int(request_params.get("scan_folder"))
        except (ValueError, TypeError):
            pass

    return filters


def build_filter_context(filters):
    """
    Build context dictionary for filter display in templates.

    Args:
        filters: Dictionary of filter parameters

    Returns:
        dict: Context for template rendering
    """
    context = {"active_filters": {}, "filter_count": 0, "has_filters": False}

    # Process each filter type
    for key, value in filters.items():
        if value:  # Only include non-empty filters
            context["active_filters"][key] = value
            context["filter_count"] += 1

    context["has_filters"] = context["filter_count"] > 0

    return context


def paginate_queryset(queryset, request, per_page=UTILITY_PAGINATION_DEFAULT):
    """
    Paginate a queryset with error handling.

    Args:
        queryset: Django QuerySet to paginate
        request: Django HttpRequest object
        per_page: Number of items per page (default from constants)

    Returns:
        tuple: (paginated_object_list, page_obj, is_paginated)
    """
    paginator = Paginator(queryset, per_page)
    page = request.GET.get("page", 1)

    try:
        page_obj = paginator.page(page)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)

    return (page_obj.object_list, page_obj, paginator.num_pages > 1)


def format_file_size(size_bytes):
    """
    Format file size in human readable format.

    Args:
        size_bytes: Size in bytes

    Returns:
        str: Formatted size string
    """
    if size_bytes == 0:
        return "0 B"

    size_names = ["B", "KB", "MB", "GB", "TB"]
    i = 0

    while size_bytes >= 1024.0 and i < len(size_names) - 1:
        size_bytes /= 1024.0
        i += 1

    return f"{size_bytes:.1f} {size_names[i]}"


def get_dashboard_stats():
    """
    Get dashboard statistics with caching.

    Returns:
        dict: Dashboard statistics
    """
    cache_key = "dashboard_stats"
    stats = cache.get(cache_key)

    if stats is None:
        try:
            Book = apps.get_model("books", "Book")
            FinalMetadata = apps.get_model("books", "FinalMetadata")

            # Basic counts
            total_books = Book.objects.count()

            # Metadata stats
            metadata_stats = FinalMetadata.objects.aggregate(
                avg_confidence=Avg("overall_confidence"), avg_completeness=Avg("completeness_score"), reviewed_count=Count("id", filter=Q(is_reviewed=True))
            )

            stats = {
                "total_books": total_books,
                "avg_confidence": (metadata_stats.get("avg_confidence") or 0) * 100,
                "avg_completeness": (metadata_stats.get("avg_completeness") or 0) * 100,
                "reviewed_count": metadata_stats.get("reviewed_count", 0),
                "needs_review_count": total_books - metadata_stats.get("reviewed_count", 0),
            }

            # Cache for 5 minutes
            cache.set(cache_key, stats, 300)

        except Exception as e:
            # Fallback stats on error
            stats = {"total_books": 0, "avg_confidence": 0, "avg_completeness": 0, "reviewed_count": 0, "needs_review_count": 0, "error": str(e)}

    return stats


def sanitize_filename(filename):
    """
    Sanitize filename for safe filesystem usage.

    Args:
        filename: Original filename

    Returns:
        str: Sanitized filename
    """
    if not filename:
        return "untitled"

    # Remove or replace invalid characters
    filename = re.sub(r'[<>:"/\\|?*]', "_", filename)

    # Remove control characters
    filename = "".join(char for char in filename if ord(char) >= 32)

    # Trim whitespace and dots
    filename = filename.strip(" .")

    # Ensure it's not empty
    if not filename:
        filename = "untitled"

    # Limit length
    if len(filename) > 200:
        name, ext = os.path.splitext(filename)
        filename = name[: 200 - len(ext)] + ext

    return filename


def generate_filename_from_metadata(book):
    """
    Generate a filename based on book metadata.

    Args:
        book: Book model instance

    Returns:
        str: Generated filename
    """
    try:
        # Get metadata
        if hasattr(book, "finalmetadata") and book.finalmetadata:
            title = book.finalmetadata.final_title or "Unknown Title"
            author = book.finalmetadata.final_author or "Unknown Author"
        else:
            title = "Unknown Title"
            author = "Unknown Author"

        # Clean up title and author
        title = sanitize_filename(title)
        author = sanitize_filename(author)

        # Get file extension
        file_path = book.primary_file.file_path if book.primary_file else ""
        ext = os.path.splitext(file_path)[1] if file_path else ".unknown"

        # Create filename: "Author - Title.ext"
        filename = f"{author} - {title}{ext}"

        # Final sanitization
        filename = sanitize_filename(filename)

        return filename

    except Exception:
        # Fallback to original filename or generic name
        if book.primary_file and book.primary_file.file_path:
            return os.path.basename(book.primary_file.file_path)
        else:
            return "unknown_book.unknown"
