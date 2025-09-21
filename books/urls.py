"""URL configuration for books application.

This module defines URL patterns for the books app including book views,
authentication, cover handling, and administrative functions.
"""
from django.contrib.auth import views as auth_views
from django.views.generic import RedirectView
from django.urls import path, reverse_lazy
from django.conf import settings
from django.conf.urls.static import static
from . import views
from .views_modules.scanning import (
    scan_dashboard, start_folder_scan, start_book_rescan, scan_progress_ajax,
    api_status_ajax, active_scans_ajax, cancel_scan_ajax, scan_history, scanning_help
)
from .views_modules.sections import (
    EbooksMainView, ebooks_ajax_list, ebooks_ajax_detail,
    SeriesMainView, series_ajax_list,
    ComicsMainView, comics_ajax_list,
    AudiobooksMainView, audiobooks_ajax_list, audiobooks_ajax_detail
)

# Register app namespace for reverse lookups
app_name = 'books'

urlpatterns = [
    # Authentication
    path('', RedirectView.as_view(url=reverse_lazy('books:dashboard'), permanent=False)),
    path('signup/', views.signup, name='signup'),
    path('login/', auth_views.LoginView.as_view(template_name='books/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(template_name='books/logout.html'), name='logout'),

    # Dashboard
    path('dashboard/', views.DashboardView.as_view(), name='dashboard'),

    # User settings and preferences
    path('settings/', views.UserSettingsView.as_view(), name='user_settings'),
    path('settings/preview-theme/', views.preview_theme, name='preview_theme'),
    path('settings/clear-theme-preview/', views.clear_theme_preview, name='clear_theme_preview'),

    # Book management
    path('books/', views.BookListView.as_view(), name='book_list'),

    # Media Type Sections
    path('ebooks/', EbooksMainView.as_view(), name='ebooks_main'),
    path('ebooks/ajax/list/', ebooks_ajax_list, name='ebooks_ajax_list'),
    path('ebooks/ajax/detail/<int:book_id>/', ebooks_ajax_detail, name='ebooks_ajax_detail'),

    path('series/', SeriesMainView.as_view(), name='series_main'),
    path('series/ajax/list/', series_ajax_list, name='series_ajax_list'),

    path('comics/', ComicsMainView.as_view(), name='comics_main'),
    path('comics/ajax/list/', comics_ajax_list, name='comics_ajax_list'),

    path('audiobooks/', AudiobooksMainView.as_view(), name='audiobooks_main'),
    path('audiobooks/ajax/list/', audiobooks_ajax_list, name='audiobooks_ajax_list'),
    path('audiobooks/ajax/detail/<int:book_id>/', audiobooks_ajax_detail, name='audiobooks_ajax_detail'),
    path('book/<int:pk>/', views.BookDetailView.as_view(), name='book_detail'),
    path('book/<int:pk>/metadata/', views.BookMetadataView.as_view(), name='book_metadata'),
    path('book/<int:pk>/metadata/update/', views.BookMetadataUpdateView.as_view(), name='book_metadata_update'),
    path('book/<int:book_id>/toggle_review/', views.toggle_needs_review, name='toggle_needs_review'),
    path('book/<int:book_id>/rescan/', views.rescan_external_metadata, name='rescan_external_metadata'),

    # Author management
    path('authors/', views.AuthorListView.as_view(), name='author_list'),
    path('authors/bulk-delete/', views.AuthorBulkDeleteView.as_view(), name='author_bulk_delete'),
    path('authors/mark-reviewed/', views.AuthorMarkReviewedView.as_view(), name='author_mark_reviewed'),

    # Genre management
    path('genres/', views.GenreListView.as_view(), name='genre_list'),
    path('genres/bulk-delete/', views.GenreBulkDeleteView.as_view(), name='genre_bulk_delete'),
    path('genres/mark-reviewed/', views.GenreMarkReviewedView.as_view(), name='genre_mark_reviewed'),

    # Book renaming/organization
    path('rename-books/', views.BookRenamerView.as_view(), name='book_renamer'),
    path('rename-books/preview/', views.BookRenamerPreviewView.as_view(), name='book_renamer_preview'),
    path('rename-books/execute/', views.BookRenamerExecuteView.as_view(), name='book_renamer_execute'),
    path('rename-books/file-details/', views.BookRenamerFileDetailsView.as_view(), name='book_renamer_file_details'),
    path('rename-books/revert/', views.BookRenamerRevertView.as_view(), name='book_renamer_revert'),
    path('rename-books/history/', views.BookRenamerHistoryView.as_view(), name='book_renamer_history'),

    # Background scanning
    path('scanning/', scan_dashboard, name='scan_dashboard'),
    path('scanning/start-folder/', start_folder_scan, name='start_folder_scan'),
    path('scanning/start-rescan/', start_book_rescan, name='start_book_rescan'),
    path('scanning/progress/<str:job_id>/', scan_progress_ajax, name='scan_progress_ajax'),
    path('scanning/api-status/', api_status_ajax, name='api_status_ajax'),
    path('scanning/active-scans/', active_scans_ajax, name='active_scans_ajax'),
    path('scanning/cancel/<str:job_id>/', cancel_scan_ajax, name='cancel_scan_ajax'),
    path('scanning/history/', scan_history, name='scan_history'),
    path('scanning/help/', scanning_help, name='scanning_help'),

    # Scan folder management
    path('scan_folders/', views.ScanFolderListView.as_view(), name='scan_folder_list'),
    path('scan_folders/add/', views.AddScanFolderView.as_view(), name='add_scan_folder'),
    path('scan_folders/<int:pk>/delete/', views.DeleteScanFolderView.as_view(), name='delete_scan_folder'),

    # Scanning
    path('trigger_scan/', views.TriggerScanView.as_view(), name='trigger_scan'),
    path('scan_status/', views.ScanStatusView.as_view(), name='scan_status'),
    path('scan_status/live/', views.current_scan_status, name='live_scan_status'),

    # Data source management
    path('data_sources/', views.DataSourceListView.as_view(), name='data_source_list'),
    path('data_sources/<int:pk>/update_trust/', views.update_trust, name='update_trust'),

    # AI Feedback and Training
    path('ai-feedback/', views.AIFeedbackListView.as_view(), name='ai_feedback_list'),
    path('ai-feedback/<int:pk>/', views.AIFeedbackDetailView.as_view(), name='ai_feedback_detail'),

    # AJAX endpoints
    path('ajax/book/<int:book_id>/update_status/', views.ajax_update_book_status, name='ajax_update_book_status'),
    path('ajax/book/<int:book_id>/conflicts/', views.ajax_get_metadata_conflicts, name='ajax_get_metadata_conflicts'),
    path('ajax/book/<int:book_id>/remove_metadata/', views.ajax_get_metadata_remove, name='ajax_get_metadata_remove'),
    path('ajax/book/<int:book_id>/upload_cover/', views.ajax_upload_cover, name='ajax_upload_cover'),
    path('ajax/book/<int:book_id>/manage_cover/', views.ajax_manage_cover, name='ajax_manage_cover'),
    path('ajax/book/<int:book_id>/rescan/', views.ajax_rescan_external_metadata, name='ajax_rescan_external_metadata'),

    # Book management AJAX
    path('ajax/create-book/', views.ajax_create_book, name='ajax_create_book'),
    path('ajax/update-book/', views.ajax_update_book, name='ajax_update_book'),
    path('ajax/delete-book/', views.ajax_delete_book, name='ajax_delete_book'),
    path('ajax/create-book-metadata/', views.ajax_create_book_metadata, name='ajax_create_book_metadata'),
    path('ajax/update-book-metadata/', views.ajax_update_book_metadata, name='ajax_update_book_metadata'),
    path('ajax/batch-update-metadata/', views.ajax_batch_update_metadata, name='ajax_batch_update_metadata'),
    path('ajax/bulk-update-books/', views.ajax_bulk_update_books, name='ajax_bulk_update_books'),

    # Scanning AJAX
    path('ajax/trigger-scan/', views.ajax_trigger_scan, name='ajax_trigger_scan'),
    path('ajax/add-scan-folder/', views.ajax_add_scan_folder, name='ajax_add_scan_folder'),

    # File operations AJAX
    path('ajax/upload-file/', views.ajax_upload_file, name='ajax_upload_file'),
    path('ajax/upload-multiple-files/', views.ajax_upload_multiple_files, name='ajax_upload_multiple_files'),
    path('ajax/upload-progress/', views.ajax_upload_progress, name='ajax_upload_progress'),
    path('ajax/copy-book-file/', views.ajax_copy_book_file, name='ajax_copy_book_file'),
    path('ajax/delete-book-file/', views.ajax_delete_book_file, name='ajax_delete_book_file'),
    path('ajax/validate-file-format/', views.ajax_validate_file_format, name='ajax_validate_file_format'),
    path('ajax/validate-file-integrity/', views.ajax_validate_file_integrity, name='ajax_validate_file_integrity'),
    path('ajax/check-file-corruption/', views.ajax_check_file_corruption, name='ajax_check_file_corruption'),
    path('ajax/processing-status/', views.ajax_processing_status, name='ajax_processing_status'),
    path('ajax/add-to-processing-queue/', views.ajax_add_to_processing_queue, name='ajax_add_to_processing_queue'),

    # User settings AJAX
    path('ajax/update-theme-settings/', views.ajax_update_theme_settings, name='ajax_update_theme_settings'),
    path('ajax/preview-theme/', views.ajax_preview_theme, name='ajax_preview_theme'),
    path('ajax/reset-theme/', views.ajax_reset_theme, name='ajax_reset_theme'),
    path('ajax/update-language/', views.ajax_update_language, name='ajax_update_language'),
    path('ajax/get-supported-languages/', views.ajax_get_supported_languages, name='ajax_get_supported_languages'),
    path('ajax/update-display-options/', views.ajax_update_display_options, name='ajax_update_display_options'),
    path('ajax/clear-user-cache/', views.ajax_clear_user_cache, name='ajax_clear_user_cache'),
    path('ajax/update-dashboard-layout/', views.ajax_update_dashboard_layout, name='ajax_update_dashboard_layout'),
    path('ajax/update-favorite-genres/', views.ajax_update_favorite_genres, name='ajax_update_favorite_genres'),
    path('ajax/update-reading-progress/', views.ajax_update_reading_progress, name='ajax_update_reading_progress'),
    path('ajax/update-custom-tags/', views.ajax_update_custom_tags, name='ajax_update_custom_tags'),
    path('ajax/export-preferences/', views.ajax_export_preferences, name='ajax_export_preferences'),
    path('ajax/import-preferences/', views.ajax_import_preferences, name='ajax_import_preferences'),
    path('ajax/update-user-preferences/', views.ajax_update_user_preferences, name='ajax_update_user_preferences'),

    # Library management AJAX
    path('ajax/create-library-folder/', views.ajax_create_library_folder, name='ajax_create_library_folder'),
    path('ajax/check-disk-space/', views.ajax_check_disk_space, name='ajax_check_disk_space'),
    path('ajax/test-connection/', views.ajax_test_connection, name='ajax_test_connection'),
    path('ajax/search-books/', views.ajax_search_books, name='ajax_search_books'),
    path('ajax/get-statistics/', views.ajax_get_statistics, name='ajax_get_statistics'),
    path('ajax/clear-cache/', views.ajax_clear_cache, name='ajax_clear_cache'),

    # Error handling and debugging AJAX
    path('ajax/trigger-error/', views.ajax_trigger_error, name='ajax_trigger_error'),
    path('ajax/force-error/', views.ajax_force_error, name='ajax_force_error'),
    path('ajax/debug-operation/', views.ajax_debug_operation, name='ajax_debug_operation'),
    path('ajax/long-running-operation/', views.ajax_long_running_operation, name='ajax_long_running_operation'),

    # Cover handling AJAX
    path('ajax/fetch-cover-image/', views.ajax_fetch_cover_image, name='ajax_fetch_cover_image'),

    # AI AJAX endpoints
    path('ajax/book/<int:book_id>/ai-feedback/', views.ajax_submit_ai_feedback, name='ajax_submit_ai_feedback'),
    path('ajax/ai/retrain/', views.ajax_retrain_ai_models, name='ajax_retrain_ai_models'),
    path('ajax/ai/status/', views.ajax_ai_model_status, name='ajax_ai_model_status'),
    path('ajax/ai-suggest-metadata/', views.ajax_ai_suggest_metadata, name='ajax_ai_suggest_metadata'),

    # Management views AJAX
    path('ajax/bulk-rename-preview/', views.ajax_bulk_rename_preview, name='ajax_bulk_rename_preview'),
    path('ajax/bulk-rename-execute/', views.ajax_bulk_rename_execute, name='ajax_bulk_rename_execute'),

    # Legacy view name mappings for existing URLs
    path('book_create/', views.ajax_create_book, name='book_create'),
    path('preview_rename/', views.ajax_bulk_rename_preview, name='preview_rename'),
    path('bulk_rename_preview/', views.ajax_bulk_rename_preview, name='bulk_rename_preview'),
    path('bulk_rename_execute/', views.ajax_bulk_rename_execute, name='bulk_rename_execute'),
    path('rename_book/', views.ajax_update_book, name='rename_book'),
    path('upload_file/', views.ajax_upload_file, name='upload_file'),
    path('delete_file/', views.ajax_delete_book_file, name='delete_file'),
    path('clear_cache/', views.ajax_clear_cache, name='clear_cache'),
    path('debug_view/', views.ajax_debug_operation, name='debug_view'),
    path('system_status/', views.ajax_get_statistics, name='system_status'),
    path('ai_suggest_metadata/<int:book_id>/', views.ajax_ai_suggest_metadata, name='ai_suggest_metadata'),
    path('submit_ai_feedback/', views.ajax_submit_ai_feedback, name='submit_ai_feedback'),
    path('logout/', views.logout_view, name='logout'),
    path('metadata_list/', views.BookMetadataView.as_view(), name='metadata_list'),
    path('dashboard/', views.DashboardView.as_view(), name='dashboard'),

    # ISBN lookup
    path('ajax/isbn-lookup/<str:isbn>/', views.isbn_lookup, name='isbn_lookup'),
]

# Serve media files during development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
