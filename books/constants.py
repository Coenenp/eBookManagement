"""
Centralized constants and configuration values for the books app.

This module contains all hardcoded values that might need to be changed,
making them easy to find and maintain in one location.
"""

# ============================================================================
# PAGINATION SETTINGS
# ============================================================================

# Default number of items per page for various list views
DEFAULT_ITEMS_PER_PAGE = 50

# Pagination for specific views (can override DEFAULT_ITEMS_PER_PAGE)
PAGINATION = {
    # Standard pagination for most list views
    "default": 25,
    # Metadata and analysis views
    "metadata_list": 50,
    "ai_feedback": 50,
    "api_status": 50,
    # Management views
    "author_list": 50,
    "genre_list": 50,
    "publisher_list": 50,
    "series_list": 50,
    "scan_folder_list": 20,
    # Book views
    "book_list": 50,
    "book_library": 50,
    "book_renamer": 50,
    # User preferences
    "default_user_preference": 50,
}


# ============================================================================
# METADATA SOURCE WEIGHTS
# ============================================================================

# Weights for calculating metadata completeness scores
# Higher weight = more important for completeness calculation
# Total should sum to 1.0 for percentage-based completeness
METADATA_SOURCE_WEIGHTS = {
    "google_books": 0.3,  # Google Books API
    "open_library": 0.4,  # Open Library API
    # Add more sources here as needed:
    # 'goodreads': 0.2,
    # 'calibre': 0.1,
}

# Completeness thresholds for scan priority assignment
COMPLETENESS_THRESHOLDS = {
    "complete": 0.9,  # >= 90% complete - no scan needed
    "low": 0.7,  # >= 70% complete - low priority scan
    "medium": 0.4,  # >= 40% complete - medium priority scan
    # < 40% = high priority scan
}


# ============================================================================
# SCAN PRIORITIES
# ============================================================================

# Priority levels for scan queue
SCAN_PRIORITY = {
    "low": 1,
    "normal": 2,
    "high": 3,
    "urgent": 4,
}

# Priority levels for folder/book rescans
RESCAN_PRIORITY = {
    "normal": 2,
    "folder_rescan": 3,  # High priority for folder rescans
}

# Priority icons for UI display
PRIORITY_ICONS = {
    1: "⬇️",  # Low
    2: "➡️",  # Normal
    3: "⬆️",  # High
    4: "🔴",  # Urgent
}


# ============================================================================
# DATA SOURCE PRIORITIES
# ============================================================================

# Default priority for data sources (lower number = higher priority)
DEFAULT_SOURCE_PRIORITY = 1


# ============================================================================
# USER SETTINGS DEFAULTS
# ============================================================================

# Default theme (Bootswatch theme name)
DEFAULT_THEME = "flatly"

# Default items per page for user preferences
DEFAULT_USER_ITEMS_PER_PAGE = 50


# ============================================================================
# SCAN QUEUE SETTINGS
# ============================================================================

# Number of recent active scans to display
RECENT_ACTIVE_SCANS_LIMIT = 5


# ============================================================================
# PAGINATION UTILITIES
# ============================================================================

# Default per_page for paginate_queryset utility function
UTILITY_PAGINATION_DEFAULT = 50
