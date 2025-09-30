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

# Import settings for backward compatibility with tests
from django.conf import settings  # noqa: F401

# Core views - COMPLETED
from .core import (  # noqa: F401
    signup, DashboardView, BookListView, BookDetailView
)

# Metadata views - COMPLETED
from .metadata import (  # noqa: F401
    BookMetadataView, BookMetadataUpdateView
)

# Management views - COMPLETED
from .management import (  # noqa: F401
    ScanFolderListView, AddScanFolderView, DeleteScanFolderView, trigger_scan,
    DataSourceListView, DataSourceCreateView, DataSourceUpdateView, update_trust,
    AuthorListView, AuthorCreateView, AuthorUpdateView, AuthorDeleteView,
    AuthorBulkDeleteView, AuthorMarkReviewedView,
    GenreListView, GenreCreateView, GenreUpdateView, GenreBulkDeleteView, GenreMarkReviewedView,
    SeriesListView, SeriesCreateView, SeriesUpdateView, SeriesDetailView,
    TriggerScanView, ScanStatusView, current_scan_status, bulk_management
)

# AJAX views - COMPLETED (includes 80+ consolidated placeholder functions)
# Import all AJAX functions with wildcards to catch all needed functions
from .ajax import *  # noqa: F401,F403

# Simple utility views - COMPLETED
from .simple import (  # noqa: F401
    AboutView, PrivacyPolicyView, HelpView, StatisticsView,
    library_statistics_json, system_status, get_navigation_data,
    quick_search, export_library_csv, debug_view_info,
    toggle_needs_review, rescan_external_metadata, isbn_lookup, logout_view
)

# Placeholder imports for incomplete modules - will be replaced as modules are created
# Renaming views - BASIC PLACEHOLDERS CREATED
from .renaming import (  # noqa: F401
    BookRenamerView, BookRenamerPreviewView, BookRenamerExecuteView,
    BookRenamerFileDetailsView, BookRenamerRevertView, BookRenamerHistoryView,
    bulk_rename_view, rename_book_form
)

# AI Feedback views - BASIC PLACEHOLDERS CREATED
from .ai_feedback import (  # noqa: F401
    AIFeedbackListView, AIFeedbackDetailView, submit_ai_feedback
)

# User Settings views - COMPLETED
from .user_settings import (  # noqa: F401
    UserSettingsView, preview_theme, clear_theme_preview
)

# Scanning views - COMPLETED (moved from views_modules/scanning.py)
from .scanning import (  # noqa: F401
    scan_dashboard, start_folder_scan, start_book_rescan,
    scan_progress_ajax, api_status_ajax, active_scans_ajax,
    cancel_scan_ajax, scan_history, scanning_help
)

# Sections views - COMPLETED (moved from views_modules/sections.py)
from .sections import (  # noqa: F401
    EbooksMainView, ebooks_ajax_list, ebooks_ajax_detail,
    SeriesMainView, series_ajax_list, ComicsMainView, comics_ajax_list,
    AudiobooksMainView, audiobooks_ajax_list, audiobooks_ajax_detail
)

# Utility functions - COMPLETED (needed by tests and views)
from .utilities import (  # noqa: F401
    get_filter_params, build_filter_context, paginate_queryset, format_file_size,
    get_dashboard_stats, sanitize_filename, generate_filename_from_metadata
)

# Mock function for testing error handling


def problematic_function():
    """Mock function that can be patched to raise exceptions in tests."""
    return "Normal operation"


__all__ = [
    # Core views
    'signup', 'DashboardView', 'BookListView', 'BookDetailView',

    # Metadata views
    'BookMetadataView', 'BookMetadataUpdateView',

    # Management views
    'ScanFolderListView', 'AddScanFolderView', 'DeleteScanFolderView',
    'TriggerScanView', 'ScanStatusView', 'DataSourceListView',
    'DataSourceCreateView', 'DataSourceUpdateView',
    'AuthorListView', 'AuthorCreateView', 'AuthorUpdateView', 'AuthorDeleteView',
    'AuthorBulkDeleteView', 'AuthorMarkReviewedView',
    'GenreListView', 'GenreCreateView', 'GenreUpdateView', 'GenreBulkDeleteView', 'GenreMarkReviewedView',
    'SeriesListView', 'SeriesCreateView', 'SeriesUpdateView', 'SeriesDetailView',
    'trigger_scan', 'update_trust', 'current_scan_status', 'bulk_management',

    # Book renaming views
    'BookRenamerView', 'BookRenamerPreviewView', 'BookRenamerExecuteView',
    'BookRenamerFileDetailsView', 'BookRenamerRevertView', 'BookRenamerHistoryView',
    'bulk_rename_view', 'rename_book_form',

    # AI Feedback views
    'AIFeedbackListView', 'AIFeedbackDetailView', 'submit_ai_feedback',

    # User settings
    'UserSettingsView', 'preview_theme', 'clear_theme_preview',

    # Simple utility views and functions
    'AboutView', 'PrivacyPolicyView', 'HelpView', 'StatisticsView',
    'library_statistics_json', 'system_status', 'get_navigation_data',
    'quick_search', 'export_library_csv', 'debug_view_info',
    'toggle_needs_review', 'rescan_external_metadata', 'isbn_lookup', 'logout_view',

    # Scanning views
    'scan_dashboard', 'start_folder_scan', 'start_book_rescan',
    'scan_progress_ajax', 'api_status_ajax', 'active_scans_ajax',
    'cancel_scan_ajax', 'scan_history', 'scanning_help',

    # Media sections views
    'EbooksMainView', 'ebooks_ajax_list', 'ebooks_ajax_detail',
    'SeriesMainView', 'series_ajax_list', 'ComicsMainView', 'comics_ajax_list',
    'AudiobooksMainView', 'audiobooks_ajax_list', 'audiobooks_ajax_detail',

    # Utility functions
    'get_filter_params', 'build_filter_context', 'paginate_queryset', 'format_file_size',
    'get_dashboard_stats', 'sanitize_filename', 'generate_filename_from_metadata',
]
