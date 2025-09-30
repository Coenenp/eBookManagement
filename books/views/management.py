"""
Management views for book library administration.

This module contains views for scanning folders, managing data sources,
and handling authors, genres, and series management.
"""
import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView
from django.urls import reverse_lazy
from django.apps import apps
from django.http import JsonResponse

# Import mixins and utilities
from ..mixins.navigation import BookNavigationMixin


# Get models dynamically to avoid circular imports
def get_model(model_name):
    return apps.get_model('books', model_name)


logger = logging.getLogger(__name__)

# =============================================================================
# SCAN FOLDER MANAGEMENT VIEWS
# =============================================================================


class ScanFolderListView(LoginRequiredMixin, BookNavigationMixin, ListView):
    """List all configured scan folders with statistics."""
    template_name = 'books/scan_folder_list.html'
    # Using default context_object_name which will be 'scanfolder_list'

    def get_model(self):
        return get_model('ScanFolder')

    def get_queryset(self):
        from django.db.models import Count
        ScanFolder = self.get_model()
        return ScanFolder.objects.annotate(
            book_count=Count('book')
        ).order_by('name')

    @property
    def model(self):
        return self.get_model()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        ScanFolder = self.get_model()
        context.update({
            'total_folders': ScanFolder.objects.count(),
            'active_folders': ScanFolder.objects.filter(is_active=True).count(),
        })
        return context


class AddScanFolderView(LoginRequiredMixin, BookNavigationMixin, CreateView):
    """Add a new scan folder."""
    template_name = 'books/add_scan_folder.html'
    # form_class = ScanFolderForm  # TODO: Create ScanFolderForm
    fields = ['name', 'path', 'is_active']
    success_url = reverse_lazy('books:scan_folder_list')

    def get_model(self):
        return get_model('ScanFolder')

    def get_queryset(self):
        return self.get_model().objects.all()


class DeleteScanFolderView(LoginRequiredMixin, BookNavigationMixin, DeleteView):
    """Delete a scan folder with safety checks."""
    template_name = 'books/confirm_delete.html'
    success_url = reverse_lazy('books:scan_folder_list')

    def get_model(self):
        return get_model('ScanFolder')

    def get_queryset(self):
        return self.get_model().objects.all()


@login_required
def trigger_scan(request):
    """Trigger a manual scan of all configured folders."""
    if request.method == 'POST':
        try:
            # TODO: Implement actual scanner functionality
            # This is a placeholder for the scanner functionality
            messages.success(
                request,
                "Scan functionality will be implemented when scanner classes are created."
            )
        except Exception as e:
            logger.error(f"Error triggering scan: {e}")
            messages.error(request, f"Error triggering scan: {e}")

    return redirect('books:scan_folder_list')

# =============================================================================
# DATA SOURCE MANAGEMENT VIEWS
# =============================================================================


class DataSourceListView(LoginRequiredMixin, BookNavigationMixin, ListView):
    """List all configured data sources."""
    template_name = 'books/data_source_list.html'
    context_object_name = 'data_sources'

    def get_model(self):
        return get_model('DataSource')

    def get_queryset(self):
        DataSource = self.get_model()
        return DataSource.objects.all().order_by('name')


class DataSourceCreateView(LoginRequiredMixin, BookNavigationMixin, CreateView):
    """Create a new data source."""
    template_name = 'books/data_source/create.html'
    # form_class = DataSourceForm  # TODO: Create DataSourceForm
    fields = ['name', 'base_url', 'trust_level']
    success_url = reverse_lazy('books:data_source_list')

    def get_model(self):
        return get_model('DataSource')


class DataSourceUpdateView(LoginRequiredMixin, BookNavigationMixin, UpdateView):
    """Update an existing data source."""
    template_name = 'books/data_source/update.html'
    # form_class = DataSourceForm  # TODO: Create DataSourceForm
    fields = ['name', 'base_url', 'trust_level']
    success_url = reverse_lazy('books:data_source_list')

    def get_model(self):
        return get_model('DataSource')


@login_required
def update_trust(request, pk):
    """Update trust level for a data source."""
    DataSource = get_model('DataSource')
    data_source = get_object_or_404(DataSource, pk=pk)

    if request.method == 'POST':
        trust_level = request.POST.get('trust_level')
        if trust_level in ['high', 'medium', 'low']:
            data_source.trust_level = trust_level
            data_source.save()
            messages.success(request, f"Trust level updated for {data_source.name}")
        else:
            messages.error(request, "Invalid trust level")

    return redirect('books:data_source_list')

# =============================================================================
# AUTHOR MANAGEMENT VIEWS
# =============================================================================


class AuthorListView(LoginRequiredMixin, BookNavigationMixin, ListView):
    """List all authors with management options."""
    template_name = 'books/author_list.html'
    context_object_name = 'authors'
    paginate_by = 50

    def get_model(self):
        return get_model('Author')

    def get_queryset(self):
        Author = self.get_model()
        return Author.objects.all().order_by('name')


class AuthorCreateView(LoginRequiredMixin, BookNavigationMixin, CreateView):
    """Create a new author."""
    template_name = 'books/author/create.html'
    # form_class = AuthorForm  # TODO: Create AuthorForm
    fields = ['name', 'sort_name', 'bio', 'image_url', 'goodreads_id', 'amazon_url']
    success_url = reverse_lazy('books:author_list')

    def get_model(self):
        return get_model('Author')


class AuthorUpdateView(LoginRequiredMixin, BookNavigationMixin, UpdateView):
    """Update an existing author."""
    template_name = 'books/author/update.html'
    # form_class = AuthorForm  # TODO: Create AuthorForm
    fields = ['name', 'sort_name', 'bio', 'image_url', 'goodreads_id', 'amazon_url']
    success_url = reverse_lazy('books:author_list')

    def get_model(self):
        return get_model('Author')


class AuthorDeleteView(LoginRequiredMixin, BookNavigationMixin, DeleteView):
    """Delete an author with safety checks."""
    template_name = 'books/confirm_delete.html'
    success_url = reverse_lazy('books:author_list')

    def get_model(self):
        return get_model('Author')


class AuthorBulkDeleteView(LoginRequiredMixin, BookNavigationMixin, ListView):
    """Bulk delete authors."""
    template_name = 'books/author/bulk_delete.html'
    context_object_name = 'authors'

    def get_model(self):
        return get_model('Author')

    def post(self, request, *args, **kwargs):
        """Handle bulk delete POST request."""
        from django.shortcuts import redirect
        from django.contrib import messages

        Author = self.get_model()
        selected_authors = request.POST.getlist('selected_authors')

        if not selected_authors:
            messages.warning(request, 'No authors selected for deletion.')
            return redirect('books:author_list')

        # Only delete unreviewed authors
        authors_to_delete = Author.objects.filter(
            id__in=selected_authors,
            is_reviewed=False
        )

        deleted_count = authors_to_delete.count()

        if deleted_count == 0:
            messages.info(request, 'No authors deleted. Only unreviewed authors can be bulk deleted.')
        else:
            authors_to_delete.delete()
            messages.success(request, f'Successfully deleted {deleted_count} author(s).')

        return redirect('books:author_list')


class AuthorMarkReviewedView(LoginRequiredMixin, BookNavigationMixin, ListView):
    """Mark authors as reviewed."""
    template_name = 'books/author/mark_reviewed.html'
    context_object_name = 'authors'

    def get_model(self):
        return get_model('Author')

    def post(self, request, *args, **kwargs):
        """Handle mark reviewed POST request."""
        from django.shortcuts import redirect
        from django.contrib import messages

        Author = self.get_model()
        selected_authors = request.POST.getlist('selected_authors')

        if not selected_authors:
            messages.warning(request, 'No authors selected.')
            return redirect('books:author_list')

        # Update unreviewed authors to reviewed
        authors_to_update = Author.objects.filter(
            id__in=selected_authors,
            is_reviewed=False
        )

        updated_count = authors_to_update.count()

        if updated_count == 0:
            messages.info(request, 'No changes made. Selected authors are already reviewed.')
        else:
            authors_to_update.update(is_reviewed=True)
            messages.success(request, f'Successfully marked {updated_count} author(s) as reviewed.')

        return redirect('books:author_list')

# =============================================================================
# GENRE MANAGEMENT VIEWS
# =============================================================================


class GenreListView(LoginRequiredMixin, BookNavigationMixin, ListView):
    """List all genres with management options."""
    template_name = 'books/genre_list.html'
    context_object_name = 'genres'
    paginate_by = 50

    def get_model(self):
        return get_model('Genre')

    def get_queryset(self):
        Genre = self.get_model()
        return Genre.objects.all().order_by('name')


class GenreCreateView(LoginRequiredMixin, BookNavigationMixin, CreateView):
    """Create a new genre."""
    template_name = 'books/genre/create.html'
    # form_class = GenreForm  # TODO: Create GenreForm
    fields = ['name', 'description']
    success_url = reverse_lazy('books:genre_list')

    def get_model(self):
        return get_model('Genre')


class GenreUpdateView(LoginRequiredMixin, BookNavigationMixin, UpdateView):
    """Update an existing genre."""
    template_name = 'books/genre/update.html'
    # form_class = GenreForm  # TODO: Create GenreForm
    fields = ['name', 'description']
    success_url = reverse_lazy('books:genre_list')

    def get_model(self):
        return get_model('Genre')


class GenreBulkDeleteView(LoginRequiredMixin, BookNavigationMixin, ListView):
    """Bulk delete genres."""
    template_name = 'books/genre/bulk_delete.html'
    context_object_name = 'genres'

    def get_model(self):
        return get_model('Genre')

    def post(self, request, *args, **kwargs):
        """Handle bulk delete POST request."""
        from django.shortcuts import redirect
        from django.contrib import messages

        Genre = self.get_model()
        selected_genres = request.POST.getlist('selected_genres')

        if not selected_genres:
            messages.warning(request, 'No genres selected for deletion.')
            return redirect('books:genre_list')

        # Only delete unreviewed genres
        genres_to_delete = Genre.objects.filter(
            id__in=selected_genres,
            is_reviewed=False
        )

        deleted_count = genres_to_delete.count()

        if deleted_count == 0:
            messages.info(request, 'No genres deleted. Only unreviewed genres can be bulk deleted.')
        else:
            genres_to_delete.delete()
            messages.success(request, f'Successfully deleted {deleted_count} genre(s).')

        return redirect('books:genre_list')


class GenreMarkReviewedView(LoginRequiredMixin, BookNavigationMixin, ListView):
    """Mark genres as reviewed."""
    template_name = 'books/genre/mark_reviewed.html'
    context_object_name = 'genres'

    def get_model(self):
        return get_model('Genre')

    def post(self, request, *args, **kwargs):
        """Handle mark reviewed POST request."""
        from django.shortcuts import redirect
        from django.contrib import messages

        Genre = self.get_model()
        selected_genres = request.POST.getlist('selected_genres')

        if not selected_genres:
            messages.warning(request, 'No genres selected.')
            return redirect('books:genre_list')

        # Update unreviewed genres to reviewed
        genres_to_update = Genre.objects.filter(
            id__in=selected_genres,
            is_reviewed=False
        )

        updated_count = genres_to_update.count()

        if updated_count == 0:
            messages.info(request, 'No changes made. Selected genres are already reviewed.')
        else:
            genres_to_update.update(is_reviewed=True)
            messages.success(request, f'Successfully marked {updated_count} genre(s) as reviewed.')

        return redirect('books:genre_list')

# =============================================================================
# SERIES MANAGEMENT VIEWS
# =============================================================================


class SeriesListView(LoginRequiredMixin, BookNavigationMixin, ListView):
    """List all series with management options."""
    template_name = 'books/series_list.html'
    context_object_name = 'series'
    paginate_by = 50

    def get_model(self):
        return get_model('Series')

    def get_queryset(self):
        Series = self.get_model()
        return Series.objects.all().order_by('name')


class SeriesCreateView(LoginRequiredMixin, BookNavigationMixin, CreateView):
    """Create a new series."""
    template_name = 'books/series/create.html'
    # form_class = SeriesForm  # TODO: Create SeriesForm
    fields = ['name', 'description', 'goodreads_id', 'amazon_url']
    success_url = reverse_lazy('books:series_list')

    def get_model(self):
        return get_model('Series')


class SeriesUpdateView(LoginRequiredMixin, BookNavigationMixin, UpdateView):
    """Update an existing series."""
    template_name = 'books/series/update.html'
    # form_class = SeriesForm  # TODO: Create SeriesForm
    fields = ['name', 'description', 'goodreads_id', 'amazon_url']
    success_url = reverse_lazy('books:series_list')

    def get_model(self):
        return get_model('Series')


class SeriesDetailView(LoginRequiredMixin, DetailView):
    """Display detailed information about a series."""
    template_name = 'books/series_detail.html'
    context_object_name = 'series'

    def get_model(self):
        return get_model('Series')

# =============================================================================
# TRIGGER SCAN VIEW
# =============================================================================


class TriggerScanView(LoginRequiredMixin, BookNavigationMixin, ListView):
    """View for triggering scans."""
    template_name = 'books/trigger_scan.html'
    context_object_name = 'scan_folders'

    def get_model(self):
        return get_model('ScanFolder')

    def get_queryset(self):
        ScanFolder = self.get_model()
        return ScanFolder.objects.filter(is_active=True)

    def post(self, request, *args, **kwargs):
        """Handle scan trigger POST requests."""
        try:
            # TODO: Implement actual scanner functionality
            # This is a placeholder for the scanner functionality
            messages.success(
                request,
                "Scan functionality will be implemented when scanner classes are created."
            )
        except Exception as e:
            logger.error(f"Error triggering scan: {e}")
            messages.error(request, f"Error triggering scan: {e}")

        return redirect('books:scan_folder_list')


class ScanStatusView(LoginRequiredMixin, BookNavigationMixin, ListView):
    """Display current scan status."""
    template_name = 'books/scan_status.html'
    context_object_name = 'scan_folders'

    def get_model(self):
        return get_model('ScanFolder')

    def get_queryset(self):
        from django.db.models import Count
        ScanFolder = self.get_model()
        return ScanFolder.objects.annotate(
            book_count=Count('book')
        ).order_by('name')


@login_required
def current_scan_status(request):
    """AJAX endpoint for current scan status."""
    # TODO: Implement actual scan status checking
    return JsonResponse({
        'status': 'idle',
        'message': 'No active scans',
        'progress': 0
    })


@login_required
def bulk_management(request):
    """View for bulk management operations."""
    Book = get_model('Book')
    Author = get_model('Author')
    Genre = get_model('Genre')
    Series = get_model('Series')

    context = {
        'active_tab': 'bulk_management',
        'total_books': Book.objects.count(),
        'total_authors': Author.objects.count(),
        'total_genres': Genre.objects.count(),
        'total_series': Series.objects.count(),
    }
    return render(request, 'books/management/bulk_management.html', context)
