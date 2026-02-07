"""
Books views package.

This package organizes views into focused modules for better maintainability.
All views are imported here to maintain backward compatibility.

REFACTORING STATUS:
✅ Core views (core.py) - Main book functionality
✅ Metadata views (metadata.py) - Metadata management
✅ Management views (management.py) - Admin functionality
✅ AJAX views (ajax.py) - All AJAX endpoints
✅ Simple views (simple.py) - Utility views
✅ User Settings views (user_settings.py) - User preferences
✅ Scanning views (scanning.py) - Background scanning operations
✅ Sections views (sections.py) - Media type sections
⏳ Renaming views (renaming.py) - TODO: Book renaming (~1,500 lines)
⏳ AI Feedback views (ai_feedback.py) - TODO: AI integration
"""

# Legacy imports for backward compatibility
# ruff: noqa: I001
import os  # noqa: F401
import subprocess  # noqa: F401

import requests  # noqa: F401
from django.conf import settings  # noqa: F401
from django.contrib import messages  # noqa: F401
from django.core.files.storage import default_storage  # noqa: F401
from django.http import JsonResponse  # noqa: F401
from django.shortcuts import redirect
from django.urls import reverse  # noqa: F401

from books.models import Book

# AI Feedback views - BASIC PLACEHOLDERS CREATED
from .ai_feedback import AIFeedbackDetailView, AIFeedbackListView, submit_ai_feedback  # noqa: F401

# AJAX views - COMPLETED (includes 80+ consolidated placeholder functions)
from .ajax import *  # noqa: F401,F403

# API Status views - NEW
from .api_status import APIStatusView, api_health_status, resume_failed_api_calls, retry_all_priority, retry_book_api  # noqa: F401

# Core views - COMPLETED
from .core import BookDetailView, BookListView, DashboardView, DeletedBooksView, UploadFileView, clear_cache_view, debug_view, signup, system_status_view  # noqa: F401

# Management views - COMPLETED
from .management import (  # noqa: F401
    AddScanFolderView,
    AuthorBulkDeleteView,
    AuthorCreateView,
    AuthorDeleteView,
    AuthorListView,
    AuthorMarkReviewedView,
    AuthorUpdateView,
    DataSourceDeleteView,
    DataSourceListView,
    DataSourceUpdateView,
    DeleteScanFolderView,
    EditScanFolderView,
    GenreBulkDeleteView,
    GenreCreateView,
    GenreDeleteView,
    GenreListView,
    GenreMarkReviewedView,
    GenreUpdateView,
    ScanFolderListView,
    ScanStatusView,
    SeriesCreateView,
    SeriesDetailView,
    SeriesListView,
    SeriesUpdateView,
    TriggerScanView,
    TriggerSingleScanView,
    bulk_management,
    current_scan_status,
    trigger_scan,
    update_trust,
)

# Metadata views - COMPLETED
from .metadata import BookMetadataUpdateView, BookMetadataView  # noqa: F401

# Placeholder imports for incomplete modules - will be replaced as modules are created
# Renaming views - ENHANCED WITH PATTERN ENGINE
from .renaming import (  # noqa: F401
    BookRenamerExecuteView,
    BookRenamerFileDetailsView,
    BookRenamerHistoryView,
    BookRenamerPreviewView,
    BookRenamerRevertView,
    BookRenamerView,
    TemplateManagementView,
    bulk_rename_view,
    delete_rename_template,
    execute_batch_rename,
    load_rename_templates,
    preview_pattern,
    preview_rename,
    rename_book,
    rename_book_form,
    save_rename_template,
    validate_pattern,
)

# Scanning views - COMPLETED (moved from views_modules/scanning.py)
from .scanning import (  # noqa: F401
    active_scans_ajax,
    api_status_ajax,
    cancel_scan_ajax,
    scan_dashboard,
    scan_folder_progress_ajax,
    scan_history,
    scan_progress_ajax,
    scanning_help,
    start_book_rescan,
    start_folder_scan,
)

# Sections views - COMPLETED (moved from views_modules/sections.py)
from .sections import (  # noqa: F401
    AudiobooksMainView,
    ComicsMainView,
    EbooksMainView,
    SeriesMainView,
    audiobooks_ajax_detail,
    audiobooks_ajax_download,
    audiobooks_ajax_list,
    comics_ajax_detail,
    comics_ajax_download,
    comics_ajax_list,
    ebooks_ajax_detail,
    ebooks_ajax_list,
    series_ajax_list,
)

# Simple utility views - COMPLETED
from .simple import (  # noqa: F401
    AboutView,
    HelpView,
    PrivacyPolicyView,
    StatisticsView,
    debug_view_info,
    export_library_csv,
    get_navigation_data,
    isbn_lookup,
    library_statistics_json,
    logout_view,
    quick_search,
    rescan_external_metadata,
    system_status,
    toggle_needs_review,
)

# User Settings views - COMPLETED
from .user_settings import UserSettingsView, clear_theme_preview, preview_theme, reset_to_defaults, save_default_template  # noqa: F401

# Utility functions - COMPLETED (needed by tests and views)
from .utilities import (  # noqa: F401
    build_filter_context,
    format_file_size,
    generate_filename_from_metadata,
    get_dashboard_stats,
    get_filter_params,
    paginate_queryset,
    sanitize_filename,
)


# Backwards compatibility redirect for QuickProcessView
def quick_process_redirect(request):
    """Redirect /quick-process/ to first unreviewed book in workflow mode."""
    next_book = Book.objects.filter(finalmetadata__isnull=False).exclude(finalmetadata__is_reviewed=True).order_by("id").first()

    if next_book:
        return redirect(f"{reverse('books:book_metadata', kwargs={'pk': next_book.id})}?workflow=1")
    else:
        messages.info(request, "No books to process. All books have been reviewed!")
        return redirect("books:dashboard")


# Mock function for testing error handling
def problematic_function():
    """Mock function that can be patched to raise exceptions in tests."""
    return "Normal operation"


__all__ = [
    # Core views
    "signup",
    "DashboardView",
    "BookListView",
    "BookDetailView",
    # Metadata views
    "BookMetadataView",
    "BookMetadataUpdateView",
    # Management views
    "ScanFolderListView",
    "AddScanFolderView",
    "EditScanFolderView",
    "DeleteScanFolderView",
    "TriggerSingleScanView",
    "TriggerScanView",
    "ScanStatusView",
    "DataSourceListView",
    "DataSourceUpdateView",
    "DataSourceDeleteView",
    "AuthorListView",
    "AuthorCreateView",
    "AuthorUpdateView",
    "AuthorDeleteView",
    "AuthorBulkDeleteView",
    "AuthorMarkReviewedView",
    "GenreListView",
    "GenreCreateView",
    "GenreUpdateView",
    "GenreDeleteView",
    "GenreBulkDeleteView",
    "GenreMarkReviewedView",
    "SeriesListView",
    "SeriesCreateView",
    "SeriesUpdateView",
    "SeriesDetailView",
    "trigger_scan",
    "update_trust",
    "current_scan_status",
    "bulk_management",
    # Book renaming views
    "BookRenamerView",
    "TemplateManagementView",
    "BookRenamerPreviewView",
    "BookRenamerExecuteView",
    "BookRenamerFileDetailsView",
    "BookRenamerRevertView",
    "BookRenamerHistoryView",
    "bulk_rename_view",
    "rename_book_form",
    "rename_book",
    "preview_rename",
    "preview_pattern",
    "execute_batch_rename",
    "validate_pattern",
    # AI Feedback views
    "AIFeedbackListView",
    "AIFeedbackDetailView",
    "submit_ai_feedback",
    # User settings
    "UserSettingsView",
    "preview_theme",
    "clear_theme_preview",
    # Simple utility views and functions
    "AboutView",
    "PrivacyPolicyView",
    "HelpView",
    "StatisticsView",
    "library_statistics_json",
    "system_status",
    "get_navigation_data",
    "quick_search",
    "export_library_csv",
    "debug_view_info",
    "toggle_needs_review",
    "rescan_external_metadata",
    "isbn_lookup",
    "logout_view",
    # Scanning views
    "scan_dashboard",
    "start_folder_scan",
    "start_book_rescan",
    "scan_progress_ajax",
    "scan_folder_progress_ajax",
    "api_status_ajax",
    "active_scans_ajax",
    "cancel_scan_ajax",
    "scan_history",
    "scanning_help",
    # Media sections views
    "EbooksMainView",
    "ebooks_ajax_list",
    "ebooks_ajax_detail",
    "SeriesMainView",
    "series_ajax_list",
    "ComicsMainView",
    "comics_ajax_list",
    "comics_ajax_detail",
    "comics_ajax_toggle_read",
    "comics_ajax_download",
    "AudiobooksMainView",
    "audiobooks_ajax_list",
    "audiobooks_ajax_detail",
    "audiobooks_ajax_toggle_read",
    "audiobooks_ajax_download",
    "audiobooks_ajax_update_progress",
    # Utility functions
    "get_filter_params",
    "build_filter_context",
    "paginate_queryset",
    "format_file_size",
    "get_dashboard_stats",
    "sanitize_filename",
    "generate_filename_from_metadata",
]
