"""Views for media type sections (Ebooks, Series, Comics, Audiobooks)"""

from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from django.views.generic import TemplateView
from django.db.models import Q
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.apps import apps


def get_book_metadata_dict(book):
    """Get metadata as dictionary from book, preferring final metadata"""
    try:
        final_meta = book.finalmetadata
        if final_meta:
            return {
                'title': final_meta.final_title or 'Unknown Title',
                'author': final_meta.final_author or 'Unknown Author',
                'publisher': final_meta.final_publisher or '',
                'description': final_meta.description or '',
                'isbn': final_meta.isbn or '',
                'language': final_meta.language or '',
                'publication_date': final_meta.publication_year,
            }
    except Exception:
        pass

    # Fallback to metadata entries if no final metadata
    metadata_dict = {
        'title': 'Unknown Title',  # Default fallback - will be overridden if metadata exists
        'author': 'Unknown Author',
        'publisher': '',
        'description': '',
        'isbn': '',
        'language': '',
        'publication_date': None,
    }

    # Get metadata entries
    has_metadata = False
    for meta in book.metadata.filter(is_active=True):
        has_metadata = True
        field_name = meta.field_name.lower()
        if field_name == 'title':
            metadata_dict['title'] = meta.field_value or 'Unknown Title'
        elif field_name == 'author':
            metadata_dict['author'] = meta.field_value or 'Unknown Author'
        elif field_name == 'publisher':
            metadata_dict['publisher'] = meta.field_value or ''
        elif field_name == 'description':
            metadata_dict['description'] = meta.field_value or ''
        elif field_name == 'isbn':
            metadata_dict['isbn'] = meta.field_value or ''
        elif field_name == 'language':
            metadata_dict['language'] = meta.field_value or ''
        elif field_name == 'publication_date':
            try:
                metadata_dict['publication_date'] = int(meta.field_value) if meta.field_value else None
            except (ValueError, TypeError):
                metadata_dict['publication_date'] = None

    # If no metadata at all, stick with fallback values
    # If has metadata but no title, could use filename as last resort
    if has_metadata and metadata_dict['title'] == 'Unknown Title':
        metadata_dict['title'] = book.filename or 'Unknown Title'

    return metadata_dict


def get_book_cover_url(book):
    """Get cover URL for a book"""
    # Try to get the final metadata cover path
    try:
        final_meta = book.final_metadata
        if final_meta and final_meta.final_cover_path:
            cover_path = final_meta.final_cover_path
            if cover_path.startswith('http'):
                return cover_path
            else:
                # Convert local path to media URL
                from django.conf import settings
                if cover_path.startswith(settings.MEDIA_ROOT):
                    relative_path = cover_path[len(settings.MEDIA_ROOT):].lstrip('\\/')
                    return settings.MEDIA_URL + relative_path.replace('\\', '/')
    except (AttributeError, ValueError, TypeError):
        # Handle cases where metadata model doesn't exist or has invalid data
        pass

    # Fallback to book's cover_path
    if book.cover_path:
        from django.conf import settings
        if book.cover_path.startswith('http'):
            return book.cover_path
        elif book.cover_path.startswith(settings.MEDIA_ROOT):
            relative_path = book.cover_path[len(settings.MEDIA_ROOT):].lstrip('\\/')
            return settings.MEDIA_URL + relative_path.replace('\\', '/')

    return None


class EbooksMainView(LoginRequiredMixin, TemplateView):
    """Main ebooks section with split-pane interface"""
    template_name = 'books/sections/ebooks_main.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Count ebooks from scan folders designated as 'ebooks'
        try:
            Book = apps.get_model('books', 'Book')
            ebooks_count = Book.objects.filter(
                scan_folder__content_type='ebooks',
                scan_folder__is_active=True
            ).count()
        except Exception:
            # Fallback count if there's an issue
            Book = apps.get_model('books', 'Book')
            ebooks_count = Book.objects.count()

        context['ebooks_count'] = ebooks_count

        return context


@login_required
def ebooks_ajax_list(request):
    """AJAX endpoint for ebooks list"""
    try:
        Book = apps.get_model('books', 'Book')

        # Get ebooks from scan folders designated as 'ebooks'
        ebooks_query = Book.objects.filter(
            scan_folder__content_type='ebooks',
            scan_folder__is_active=True
        ).select_related('scan_folder').prefetch_related(
            'metadata',
            'series_info'
        )

        # Get search and filter parameters
        search = request.GET.get('search', '').strip()
        format_filter = request.GET.get('format', '').strip()
        sort_by = request.GET.get('sort', 'id')  # Default to simple field

        # Apply filters
        if search:
            # Simple search in the metadata table
            ebooks_query = ebooks_query.filter(
                Q(metadata__field_name='title', metadata__field_value__icontains=search) |
                Q(metadata__field_name='author', metadata__field_value__icontains=search) |
                Q(metadata__field_name='publisher', metadata__field_value__icontains=search)
            ).distinct()

        if format_filter:
            ebooks_query = ebooks_query.filter(file_format=format_filter)

        # Apply simple sorting for now
        if sort_by == 'date':
            ebooks_query = ebooks_query.order_by('-last_scanned')
        elif sort_by == 'size':
            ebooks_query = ebooks_query.order_by('-file_size')
        else:
            ebooks_query = ebooks_query.order_by('id')  # Simple default sort

        # Limit results for performance
        ebooks = ebooks_query[:500]  # Limit to 500 items

        # Build response data
        ebooks_data = []
        for book in ebooks:
            # Get the best metadata
            metadata = get_book_metadata_dict(book)

            # Get series information
            series_info = book.series_info.first()

            ebooks_data.append({
                'id': book.id,
                'title': metadata.get('title', 'Unknown Title'),
                'author': metadata.get('author', 'Unknown Author'),
                'author_display': metadata.get('author', 'Unknown Author'),  # For compatibility
                'publisher': metadata.get('publisher', ''),
                'file_format': book.file_format,
                'file_size': book.file_size,
                'file_size_display': f"{book.file_size // (1024*1024)} MB" if book.file_size else "Unknown",
                'last_scanned': book.last_scanned.isoformat() if book.last_scanned else None,
                'series_name': series_info.series.name if series_info and series_info.series else '',
                'series_position': series_info.series_number if series_info else None,
                'cover_url': book.cover_path if book.cover_path else '',
            })

        return JsonResponse({
            'success': True,
            'ebooks': ebooks_data,
            'total_count': len(ebooks_data)
        })

    except Exception as e:
        import traceback
        return JsonResponse({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc() if request.user.is_superuser else None
        }, status=500)


@login_required
def ebooks_ajax_detail(request, book_id):
    """AJAX endpoint for ebook detail"""
    try:
        Book = apps.get_model('books', 'Book')

        # Check if book exists first
        if not Book.objects.filter(id=book_id).exists():
            return JsonResponse({
                'success': False,
                'error': f'Book with ID {book_id} not found'
            }, status=404)

        book = get_object_or_404(Book, id=book_id)

        # Get metadata safely
        try:
            metadata = get_book_metadata_dict(book)
        except Exception:
            metadata = {
                'title': book.filename or 'Unknown Title',
                'author': 'Unknown Author',
                'publisher': '',
                'description': '',
                'isbn': '',
                'language': '',
                'publication_date': None,
            }

        # Get series information safely
        try:
            series_info = book.series_info.first()
            series_name = series_info.series.name if series_info and series_info.series else ''
            series_position = series_info.series_number if series_info else None
        except Exception:
            series_name = ''
            series_position = None

        # Get genres safely
        genres = []
        try:
            for meta in book.metadata.all():
                if hasattr(meta, 'genre') and meta.genre:
                    genres.extend([g.strip() for g in meta.genre.split(',') if g.strip()])
            genres = list(set(genres))  # Remove duplicates
        except Exception:
            genres = []

        # Get cover URL safely
        try:
            cover_url = get_book_cover_url(book)
        except Exception:
            cover_url = ''

        ebook_data = {
            'id': book.id,
            'title': metadata.get('title', 'Unknown Title'),
            'author': metadata.get('author', 'Unknown Author'),
            'narrator': metadata.get('narrator', ''),
            'publisher': metadata.get('publisher', ''),
            'description': metadata.get('description', ''),
            'isbn': metadata.get('isbn', ''),
            'language': metadata.get('language', ''),
            'publication_date': metadata.get('publication_date'),
            'file_format': book.file_format or 'UNKNOWN',
            'file_size': book.file_size,
            'file_path': book.file_path,
            'last_scanned': book.last_scanned.isoformat() if book.last_scanned else None,
            'series_name': series_name,
            'series_position': series_position,
            'genres': genres,
            'cover_url': cover_url,
        }

        return JsonResponse({
            'success': True,
            'ebook': ebook_data
        })

    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        return JsonResponse({
            'success': False,
            'error': str(e),
            'details': error_details
        }, status=500)


class SeriesMainView(LoginRequiredMixin, TemplateView):
    """Main series section with expandable list"""
    template_name = 'books/sections/series_main.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Count unique series from final metadata (the actual source of truth)
        FinalMetadata = apps.get_model('books', 'FinalMetadata')
        series_count = FinalMetadata.objects.filter(
            final_series__isnull=False
        ).exclude(final_series='').values('final_series').distinct().count()
        context['series_count'] = series_count

        return context


@login_required
def series_ajax_list(request):
    """AJAX endpoint for series list"""
    try:
        Book = apps.get_model('books', 'Book')

        # Get all series from final metadata as primary source
        series_data = {}

        # Get books with series information from final metadata
        books_with_series = Book.objects.filter(
            finalmetadata__final_series__isnull=False,
            is_placeholder=False
        ).exclude(
            finalmetadata__final_series=''
        ).select_related('finalmetadata').prefetch_related('metadata')

        for book in books_with_series:
            final_meta = book.finalmetadata
            series_name = final_meta.final_series

            if series_name not in series_data:
                series_data[series_name] = {
                    'name': series_name,
                    'books': [],
                    'book_count': 0,
                    'total_size': 0,
                    'formats': set(),
                    'authors': set()
                }

            # Get metadata for the book
            metadata = get_book_metadata_dict(book)

            book_data = {
                'id': book.id,
                'title': metadata.get('title', 'Unknown Title'),
                'author': metadata.get('author', 'Unknown Author'),
                'position': final_meta.final_series_number if final_meta.final_series_number else None,
                'file_format': book.file_format,
                'file_size': book.file_size or 0,
                'last_scanned': book.last_scanned.isoformat() if book.last_scanned else None,
            }

            series_data[series_name]['books'].append(book_data)
            series_data[series_name]['book_count'] += 1
            series_data[series_name]['total_size'] += book_data['file_size']
            series_data[series_name]['formats'].add(book.file_format)
            series_data[series_name]['authors'].add(book_data['author'])

        # Convert to list and sort
        series_list = []
        for series_name, data in series_data.items():
            data['formats'] = list(data['formats'])
            data['authors'] = list(data['authors'])
            # Sort books by position, with books without position at the end
            data['books'].sort(key=lambda x: (x['position'] is None, x['position'] or 999))
            series_list.append(data)

        series_list.sort(key=lambda x: x['name'])

        return JsonResponse({
            'success': True,
            'series': series_list,
            'total_count': len(series_list)
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


class ComicsMainView(LoginRequiredMixin, TemplateView):
    """Main comics section"""
    template_name = 'books/sections/comics_main.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        FinalMetadata = apps.get_model('books', 'FinalMetadata')
        Book = apps.get_model('books', 'Book')

        # Count comics from scan folders designated as 'comics'
        comics_from_final = FinalMetadata.objects.filter(
            book__scan_folder__content_type='comics',
            book__scan_folder__is_active=True,
            book__file_format__in=['cbr', 'cbz']
        ).select_related('book')

        # Count unique series + standalone comics
        series_names = set()
        standalone_count = 0

        for final_meta in comics_from_final:
            if final_meta.final_series and final_meta.final_series.strip():
                series_names.add(final_meta.final_series.strip())
            else:
                standalone_count += 1

        comics_count = len(series_names) + standalone_count

        # If no comics in final metadata, fall back to scan folder detection
        if comics_count == 0:
            comics_count = Book.objects.filter(
                scan_folder__content_type='comics',
                scan_folder__is_active=True,
                file_format__in=['cbr', 'cbz']
            ).count()

        context['comics_count'] = comics_count

        return context


@login_required
def comics_ajax_list(request):
    """AJAX endpoint for comics list"""
    try:
        FinalMetadata = apps.get_model('books', 'FinalMetadata')

        # Get comics from FinalMetadata - filter by scan folder content type
        comics_from_final = FinalMetadata.objects.filter(
            book__scan_folder__content_type='comics',
            book__scan_folder__is_active=True,
            book__file_format__in=['cbr', 'cbz']
        ).select_related('book', 'book__scan_folder')

        # Group by series if available
        series_data = {}
        standalone_comics = []

        for final_meta in comics_from_final:
            book = final_meta.book
            if not book:
                continue

            book_data = {
                'id': book.id,
                'title': final_meta.final_title or 'Unknown Title',
                'author': final_meta.final_author or 'Unknown Author',
                'file_format': book.file_format,
                'file_size': book.file_size,
                'last_scanned': book.last_scanned.isoformat() if book.last_scanned else None,
                'position': final_meta.final_series_number,
            }

            # Check if this comic is part of a series
            if final_meta.final_series and final_meta.final_series.strip():
                series_name = final_meta.final_series.strip()
                if series_name not in series_data:
                    series_data[series_name] = {
                        'name': series_name,
                        'books': [],
                        'book_count': 0,
                        'total_size': 0,
                        'authors': set(),
                        'formats': set()
                    }

                series_data[series_name]['books'].append(book_data)
                series_data[series_name]['book_count'] += 1
                series_data[series_name]['total_size'] += book_data['file_size'] or 0
                if book_data['author'] and book_data['author'] != 'Unknown Author':
                    series_data[series_name]['authors'].add(book_data['author'])
                if book_data['file_format']:
                    series_data[series_name]['formats'].add(book_data['file_format'])
            else:
                standalone_comics.append(book_data)

        # Convert sets to lists for JSON serialization and sort books
        for series_name, data in series_data.items():
            data['authors'] = list(data['authors'])
            data['formats'] = list(data['formats'])
            # Sort books by position, handling None values
            data['books'].sort(key=lambda x: float(x['position']) if x['position'] and str(x['position']).replace('.', '').isdigit() else 999.0)

        # Convert series to list and sort
        series_list = list(series_data.values())
        series_list.sort(key=lambda x: x['name'])

        # Sort standalone comics by title
        standalone_comics.sort(key=lambda x: x['title'])

        return JsonResponse({
            'success': True,
            'series': series_list,
            'standalone': standalone_comics,
            'total_count': len(series_list) + len(standalone_comics)
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


class AudiobooksMainView(LoginRequiredMixin, TemplateView):
    """Main audiobooks section"""
    template_name = 'books/sections/audiobooks_main.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Count audiobooks from scan folders designated as 'audiobooks'
        Book = apps.get_model('books', 'Book')
        audiobooks_count = Book.objects.filter(
            scan_folder__content_type='audiobooks',
            scan_folder__is_active=True
        ).count()

        context['audiobooks_count'] = audiobooks_count

        return context


@login_required
def audiobooks_ajax_list(request):
    """AJAX endpoint for audiobooks list"""
    try:
        Book = apps.get_model('books', 'Book')

        # Get audiobooks from scan folders designated as 'audiobooks'
        audiobooks_query = Book.objects.filter(
            scan_folder__content_type='audiobooks',
            scan_folder__is_active=True
        ).select_related('scan_folder').prefetch_related(
            'metadata',
            'series_info'
        ).order_by('id')  # Use simple ordering instead of metadata__title

        audiobooks_data = []
        for book in audiobooks_query:
            metadata = get_book_metadata_dict(book)
            series_info = book.series_info.first()

            audiobooks_data.append({
                'id': book.id,
                'title': metadata.get('title', 'Unknown Title'),
                'author': metadata.get('author', 'Unknown Author'),
                'narrator': metadata.get('narrator', ''),  # Will be added if available
                'duration': metadata.get('duration', ''),  # Will be added if available
                'file_format': book.file_format or 'UNKNOWN',
                'file_size': book.file_size,
                'last_scanned': book.last_scanned.isoformat() if book.last_scanned else None,
                'series_name': series_info.series.name if series_info and series_info.series else '',
                'series_position': series_info.series_number if series_info else None,
            })

        return JsonResponse({
            'success': True,
            'audiobooks': audiobooks_data,
            'total_count': len(audiobooks_data)
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
def audiobooks_ajax_detail(request, book_id):
    """AJAX endpoint for audiobook detail"""
    try:
        Book = apps.get_model('books', 'Book')

        # Check if book exists first
        if not Book.objects.filter(id=book_id).exists():
            return JsonResponse({
                'success': False,
                'error': f'Book with ID {book_id} not found'
            }, status=404)

        book = get_object_or_404(Book, id=book_id)
        metadata = get_book_metadata_dict(book)

        # Get series information
        series_info = book.series_info.first()

        # Get cover URL
        cover_url = get_book_cover_url(book)

        audiobook_data = {
            'id': book.id,
            'title': metadata.get('title', 'Unknown Title'),
            'author': metadata.get('author', 'Unknown Author'),
            'narrator': metadata.get('narrator', ''),
            'publisher': metadata.get('publisher', ''),
            'description': metadata.get('description', ''),
            'isbn': metadata.get('isbn', ''),
            'language': metadata.get('language', ''),
            'duration': metadata.get('duration', ''),
            'publication_date': metadata.get('publication_date'),
            'file_format': book.file_format or 'UNKNOWN',
            'file_size': book.file_size,
            'file_path': book.file_path,
            'last_scanned': book.last_scanned.isoformat() if book.last_scanned else None,
            'series_name': series_info.series.name if series_info and series_info.series else '',
            'series_position': series_info.series_number if series_info else None,
            'cover_url': cover_url,
        }

        return JsonResponse({
            'success': True,
            'audiobook': audiobook_data
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
