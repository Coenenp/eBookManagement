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
    path('book/<int:pk>/', views.BookDetailView.as_view(), name='book_detail'),
    path('book/<int:pk>/metadata/', views.BookMetadataView.as_view(), name='book_metadata'),
    path('book/<int:pk>/metadata/update/', views.BookMetadataUpdateView.as_view(), name='book_metadata_update'),
    path('book/<int:book_id>/toggle_review/', views.toggle_needs_review, name='toggle_needs_review'),

    # Author management
    path('authors/', views.AuthorListView.as_view(), name='author_list'),
    path('authors/bulk-delete/', views.AuthorBulkDeleteView.as_view(), name='author_bulk_delete'),
    path('authors/mark-reviewed/', views.AuthorMarkReviewedView.as_view(), name='author_mark_reviewed'),

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

    # AJAX endpoints
    path('ajax/book/<int:book_id>/update_status/', views.ajax_update_book_status, name='ajax_update_book_status'),
    path('ajax/book/<int:book_id>/conflicts/', views.ajax_get_metadata_conflicts, name='ajax_get_metadata_conflicts'),
    path('ajax/book/<int:book_id>/remove_metadata/', views.ajax_get_metadata_remove, name='ajax_get_metadata_remove'),
    path('ajax/book/<int:book_id>/upload_cover/', views.ajax_upload_cover, name='ajax_upload_cover'),
    path('ajax/book/<int:book_id>/manage_cover/', views.ajax_manage_cover, name='ajax_manage_cover'),
]

# Serve media files during development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
