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

    # AI AJAX endpoints
    path('ajax/book/<int:book_id>/ai-feedback/', views.ajax_submit_ai_feedback, name='ajax_submit_ai_feedback'),
    path('ajax/ai/retrain/', views.ajax_retrain_ai_models, name='ajax_retrain_ai_models'),
    path('ajax/ai/status/', views.ajax_ai_model_status, name='ajax_ai_model_status'),

    # ISBN lookup
    path('ajax/isbn-lookup/<str:isbn>/', views.isbn_lookup, name='isbn_lookup'),
]

# Serve media files during development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
