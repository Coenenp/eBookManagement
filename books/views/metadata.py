"""
Metadata management views.
"""
import logging
from django.shortcuts import get_object_or_404, redirect, render, reverse
from django.views.generic import DetailView, View, ListView
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin

from books.models import (
    Book, FinalMetadata, BookTitle, BookAuthor, Author, BookSeries, Series,
    BookPublisher, Publisher, BookMetadata, DataSource
)
from books.mixins import SimpleNavigationMixin, MetadataContextMixin
from books.book_utils import CoverManager, GenreManager

logger = logging.getLogger('books.scanner')


class BookMetadataListView(LoginRequiredMixin, ListView):
    """
    List view for book metadata - shows all books for metadata management
    """
    model = Book
    template_name = 'books/book_list.html'
    context_object_name = 'books'
    paginate_by = 50

    def get_queryset(self):
        return Book.objects.all().select_related('scan_folder').prefetch_related('finalmetadata_set')


class BookMetadataView(LoginRequiredMixin, DetailView, SimpleNavigationMixin, MetadataContextMixin):
    """
    Dedicated metadata review view - cleaned and optimized
    """
    model = Book
    template_name = 'books/book_metadata.html'
    context_object_name = 'book'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        book = context['book']

        # Navigation logic using mixin
        context.update(self.get_simple_navigation_context(book))

        # Metadata context using mixin
        context.update(self.get_metadata_context(book))

        # Additional metadata fields specific to metadata review
        context.update(self.get_metadata_fields_context(book))

        return context


class BookMetadataUpdateView(LoginRequiredMixin, View):
    """
    FIXED metadata update view - addresses all reported bugs
    """
    def post(self, request, pk):
        try:
            book = get_object_or_404(Book, pk=pk)
            final_metadata, created = FinalMetadata.objects.get_or_create(book=book)

            # Basic validation - check if title is empty when explicitly provided
            final_title = request.POST.get('final_title', '').strip()
            if 'final_title' in request.POST and not final_title:
                messages.error(request, "Title cannot be empty when provided.")
                # Return to metadata view with error
                context = self._get_metadata_view_context(book)
                context['errors'] = True
                return render(request, 'books/book_metadata.html', context)

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

            # last_updated is auto-updated by Django

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

            # Redirect back to the edit tab
            redirect_url = reverse('books:book_detail', kwargs={'pk': book.id}) + '?tab=edit'
            return redirect(redirect_url)

        except Exception as e:
            logger.error(f"Error updating metadata for book {pk}: {e}")
            messages.error(request, f"An error occurred while updating metadata: {str(e)}")
            # Redirect back to the edit tab even on error
            redirect_url = reverse('books:book_detail', kwargs={'pk': pk}) + '?tab=edit'
            return redirect(redirect_url)

    def _get_metadata_view_context(self, book):
        """Get context data for metadata view (used for validation errors)"""
        metadata_view = BookMetadataView()
        metadata_view.object = book
        return metadata_view.get_context_data()

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
        """Process cover selection and upload."""
        from django.conf import settings

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
        """Process publication year."""
        updated_fields = []

        final_year = request.POST.get('publication_year', '').strip()
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
        """Process ISBN, Language, and Description fields."""
        updated_fields = []

        metadata_fields = {
            'isbn': ('ISBN', 'manual_isbn'),
            'language': ('Language', 'manual_language'),
            'description': ('Description', 'manual_description'),
        }

        for field_name, (display_name, manual_field) in metadata_fields.items():
            final_value = request.POST.get(field_name, '').strip()
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
        """Process genre selection."""
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
