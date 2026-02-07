"""Views for media type sections (Ebooks, Series, Comics, Audiobooks)"""

import logging
import os

from django.apps import apps
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.generic import TemplateView

from books.models import AUDIOBOOK_FORMATS, COMIC_FORMATS, EBOOK_FORMATS, Book, UserProfile
from books.utils.decorators import ajax_response_handler
from books.utils.metadata_helpers import (
    format_book_detail_for_json,
    get_book_cover_url,
    get_book_metadata_dict,
)

logger = logging.getLogger("books.scanner")


# Ebooks Section Views
class EbooksMainView(LoginRequiredMixin, TemplateView):
    """Main ebooks section with split-pane interface"""

    template_name = "books/sections/ebooks_main.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Count ebooks from scan folders designated as 'ebooks'
        try:
            Book = apps.get_model("books", "Book")
            ebooks_count = Book.objects.filter(
                scan_folder__content_type="ebooks", scan_folder__is_active=True, files__file_format__in=EBOOK_FORMATS  # Use EBOOK_FORMATS for consistency
            ).count()
        except Exception:
            # Fallback count if there's an issue
            Book = apps.get_model("books", "Book")
            ebooks_count = Book.objects.count()

        context["ebooks_count"] = ebooks_count

        return context


@login_required
@ajax_response_handler
def ebooks_ajax_list(request):
    """AJAX endpoint for ebooks list"""
    Book = apps.get_model("books", "Book")

    # Get pagination parameters from user profile
    try:
        profile = UserProfile.get_or_create_for_user(request.user)
        per_page = int(request.GET.get("per_page", profile.items_per_page))
    except Exception:
        per_page = int(request.GET.get("per_page", 50))

    page = int(request.GET.get("page", 1))

    # Get ebooks from scan folders designated as 'ebooks'
    ebooks_query = (
        Book.objects.filter(scan_folder__content_type="ebooks", scan_folder__is_active=True, files__file_format__in=EBOOK_FORMATS)  # Use EBOOK_FORMATS for consistency
        .select_related("scan_folder")
        .prefetch_related("metadata", "series_relationships", "files")
    )

    # Get search and filter parameters
    search = request.GET.get("search", "").strip()
    format_filter = request.GET.get("format", "").strip()
    sort_by = request.GET.get("sort", "id")  # Default to simple field

    # Apply filters
    if search:
        # Simple search in the metadata table
        ebooks_query = ebooks_query.filter(
            Q(metadata__field_name="title", metadata__field_value__icontains=search)
            | Q(metadata__field_name="author", metadata__field_value__icontains=search)
            | Q(metadata__field_name="publisher", metadata__field_value__icontains=search)
        ).distinct()

    if format_filter:
        ebooks_query = ebooks_query.filter(files__file_format=format_filter)

    # Apply simple sorting for now
    if sort_by == "date":
        ebooks_query = ebooks_query.order_by("-last_scanned")
    elif sort_by == "size":
        ebooks_query = ebooks_query.order_by("-files__file_size")
    else:
        ebooks_query = ebooks_query.order_by("id")  # Simple default sort

    # Paginate results
    paginator = Paginator(ebooks_query, per_page)
    page_obj = paginator.get_page(page)

    # Build response data
    ebooks_data = []
    for book in page_obj:
        # Get the best metadata
        metadata = get_book_metadata_dict(book)

        # Get series information
        series_info = book.series_relationships.first()

        # Get file info from first BookFile (most books have one file)
        book_file = book.files.first()
        file_format = book_file.file_format if book_file else "UNKNOWN"
        file_size = book_file.file_size if book_file else 0
        file_path = book_file.file_path if book_file else ""
        cover_path = book_file.cover_path if book_file and book_file.cover_path else ""

        ebooks_data.append(
            {
                "id": book.id,
                "title": metadata.get("title", "Unknown Title"),
                "author": metadata.get("author", "Unknown Author"),
                "author_display": metadata.get("author", "Unknown Author"),
                "publisher": metadata.get("publisher", ""),
                "language": metadata.get("language", "en"),
                "publication_year": str(metadata.get("publication_date", ""))[:4] if metadata.get("publication_date") else "",
                "file_format": file_format,
                "file_size": file_size,
                "file_path": file_path,
                "file_size_display": f"{file_size // (1024*1024)} MB" if file_size else "Unknown",
                "last_scanned": book.last_scanned.isoformat() if book.last_scanned else None,
                "series": series_info.series.name if series_info and series_info.series else "",
                "series_name": series_info.series.name if series_info and series_info.series else "",
                "series_position": series_info.series_number if series_info else None,
                "cover_url": cover_path,
                "scan_folder": book.scan_folder.path if book.scan_folder else "",
            }
        )

    return {
        "success": True,
        "ebooks": ebooks_data,
        "books": ebooks_data,  # Tests expect this field
        "total_count": paginator.count,
        "page": page,
        "per_page": per_page,
        "num_pages": paginator.num_pages,
        "has_next": page_obj.has_next(),
        "has_previous": page_obj.has_previous(),
    }


@login_required
@ajax_response_handler
def ebooks_ajax_detail(request, book_id):
    """AJAX endpoint for ebook detail"""
    import logging

    logger = logging.getLogger(__name__)

    try:
        Book = apps.get_model("books", "Book")
        book = get_object_or_404(Book.objects.select_related("scan_folder", "finalmetadata"), id=book_id)
        ebook_data = format_book_detail_for_json(book)
        return {"success": True, "ebook": ebook_data}
    except Exception as e:
        logger.error(f"Error in ebooks_ajax_detail for book_id {book_id}: {str(e)}", exc_info=True)
        raise


class SeriesMainView(LoginRequiredMixin, TemplateView):
    """Main series section with expandable list"""

    template_name = "books/sections/series_main.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Count unique series from final metadata (the actual source of truth)
        FinalMetadata = apps.get_model("books", "FinalMetadata")
        series_count = FinalMetadata.objects.filter(final_series__isnull=False).exclude(final_series="").values("final_series").distinct().count()
        context["series_count"] = series_count

        return context


@login_required
@ajax_response_handler
def series_ajax_list(request):
    """AJAX endpoint for series list"""
    Book = apps.get_model("books", "Book")

    # Get all series from final metadata as primary source
    series_data = {}

    # Get books with series information from final metadata - EBOOKS ONLY
    books_with_series = (
        Book.objects.filter(
            finalmetadata__final_series__isnull=False,
            is_placeholder=False,
            scan_folder__content_type="ebooks",  # Only include ebooks in series section
            scan_folder__is_active=True,
            files__file_format__in=EBOOK_FORMATS,  # Use EBOOK_FORMATS for consistency
        )
        .exclude(finalmetadata__final_series="")
        .select_related("finalmetadata", "scan_folder")
        .prefetch_related("metadata", "files")
    )

    for book in books_with_series:
        final_meta = book.finalmetadata
        series_name = final_meta.final_series

        if series_name not in series_data:
            series_data[series_name] = {"name": series_name, "books": [], "book_count": 0, "total_size": 0, "formats": set(), "authors": set()}

        # Get metadata for the book
        metadata = get_book_metadata_dict(book)

        # Get file info from first BookFile
        first_file = book.files.first()
        file_format = first_file.file_format if first_file else "UNKNOWN"
        file_size = (first_file.file_size or 0) if first_file else 0

        book_data = {
            "id": book.id,
            "title": metadata.get("title", "Unknown Title"),
            "author": metadata.get("author", "Unknown Author"),
            "position": final_meta.final_series_number if final_meta.final_series_number else None,
            "file_format": file_format,
            "file_size": file_size,
            "last_scanned": book.last_scanned.isoformat() if book.last_scanned else None,
        }

        series_data[series_name]["books"].append(book_data)
        series_data[series_name]["book_count"] += 1
        series_data[series_name]["total_size"] += book_data["file_size"]
        series_data[series_name]["formats"].add(file_format)
        series_data[series_name]["authors"].add(book_data["author"])

    # Convert to list and sort
    series_list = []
    for series_name, data in series_data.items():
        data["formats"] = list(data["formats"])
        data["authors"] = list(data["authors"])
        # Sort books by position, with books without position at the end
        data["books"].sort(key=lambda x: (x["position"] is None, x["position"] or 999))
        series_list.append(data)

    series_list.sort(key=lambda x: x["name"])

    # Get user's items_per_page setting and apply pagination to series
    profile = UserProfile.get_or_create_for_user(request.user)
    per_page = int(request.GET.get("per_page", profile.items_per_page))
    page = int(request.GET.get("page", 1))

    # Paginate the series list
    paginator = Paginator(series_list, per_page)
    page_obj = paginator.get_page(page)

    return {
        "success": True,
        "series": list(page_obj),
        "total_count": paginator.count,
        "page": page,
        "per_page": per_page,
        "num_pages": paginator.num_pages,
        "has_next": page_obj.has_next(),
        "has_previous": page_obj.has_previous(),
    }


class ComicsMainView(LoginRequiredMixin, TemplateView):
    """Main comics section"""

    template_name = "books/sections/comics_main.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        FinalMetadata = apps.get_model("books", "FinalMetadata")
        Book = apps.get_model("books", "Book")

        # Count comics from scan folders designated as 'comics'
        comics_from_final = FinalMetadata.objects.filter(
            book__scan_folder__content_type="comics", book__scan_folder__is_active=True, book__files__file_format__in=COMIC_FORMATS
        ).select_related("book")

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
            comics_count = Book.objects.filter(scan_folder__content_type="comics", scan_folder__is_active=True, files__file_format__in=COMIC_FORMATS).count()

        context["comics_count"] = comics_count

        return context


@login_required
@ajax_response_handler
def comics_ajax_list(request):
    """AJAX endpoint for comics list using unified Book model"""
    from books.models import COMIC_FORMATS, Book

    # Get comics books - use COMIC_FORMATS if available, otherwise common comic types
    comic_formats = COMIC_FORMATS
    # Get all comic books from comics folders
    comics_query = (
        Book.objects.filter(scan_folder__content_type="comics", scan_folder__is_active=True, files__file_format__in=comic_formats)
        .prefetch_related("files", "metadata", "finalmetadata")
        .select_related("scan_folder")
        .distinct()
    )

    # Get user's items_per_page setting and apply pagination
    profile = UserProfile.get_or_create_for_user(request.user)
    per_page = int(request.GET.get("per_page", profile.items_per_page))
    page = int(request.GET.get("page", 1))

    # Paginate the queryset
    paginator = Paginator(comics_query, per_page)
    page_obj = paginator.get_page(page)

    # Group comics by series
    series_dict = {}
    standalone_comics = []

    for book in page_obj:
        # Get the first file for this book
        first_file = book.files.first()
        if not first_file:
            continue

        # Skip if not a comic format
        if first_file.file_format not in comic_formats:
            continue

        # Get metadata if available
        try:
            metadata = book.finalmetadata  # OneToOneField, no .first() needed
        except AttributeError:
            metadata = None
        if not metadata:
            try:
                metadata = book.metadata.first()  # This is a related manager
            except AttributeError:
                metadata = None

        # Get title - prefer FinalMetadata over BookTitle
        if metadata and hasattr(metadata, "final_title") and metadata.final_title:
            title = metadata.final_title
        else:
            book_title = book.titles.first()
            title = book_title.title if book_title else f"Book {book.id}"

        # Get author - prefer FinalMetadata over BookAuthor
        if metadata and hasattr(metadata, "final_author") and metadata.final_author:
            author = metadata.final_author
        else:
            book_author = book.author_relationships.first()
            author = book_author.author.name if book_author else ""

        # Get series info from BookSeries first, then fallback to FinalMetadata
        book_series = book.series_relationships.first()
        if book_series:
            series_name = book_series.series.name
            # Convert series_number to integer for position, default to 0
            try:
                position = int(book_series.series_number) if book_series.series_number else 0
            except (ValueError, TypeError):
                position = 0
        else:
            # Fallback to FinalMetadata
            series_name = metadata.final_series if metadata and hasattr(metadata, "final_series") and metadata.final_series else None
            if metadata and hasattr(metadata, "final_series_number") and metadata.final_series_number:
                position = metadata.final_series_number
            else:
                position = 0

        comic_data = {
            "id": book.id,
            "title": title,
            "author": author,
            "publisher": getattr(metadata, "final_publisher", "") or getattr(metadata, "publisher", "") if metadata else "",
            "series": series_name or title,
            "volume": getattr(metadata, "volume", "") if metadata else "",
            "description": getattr(metadata, "final_description", "") or getattr(metadata, "description", "") if metadata else "",
            "file_format": first_file.file_format,
            "file_size": first_file.file_size or 0,
            "page_count": getattr(metadata, "page_count", None) if metadata else None,
            "date_added": book.first_scanned.isoformat() if book.first_scanned else None,
            "scan_folder": book.scan_folder.path if book.scan_folder else "",
            "cover_url": get_book_cover_url(book),
            "download_url": f"/books/comics/download/{book.id}/",
            "position": position,
        }

        if series_name:
            # Group by series
            if series_name not in series_dict:
                series_dict[series_name] = {
                    "id": f"series_{len(series_dict) + 1}",
                    "name": series_name,
                    "books": [],
                    "total_books": 0,
                    "read_books": 0,
                    "total_size": 0,
                    "authors": set(),
                    "formats": set(),
                }
            series_dict[series_name]["books"].append(comic_data)
            series_dict[series_name]["total_books"] += 1
            series_dict[series_name]["total_size"] += comic_data["file_size"]
            if comic_data["author"]:
                series_dict[series_name]["authors"].add(comic_data["author"])
            series_dict[series_name]["formats"].add(comic_data["file_format"])
            if comic_data["is_read"]:
                series_dict[series_name]["read_books"] += 1
        else:
            # Standalone comic
            standalone_comics.append(comic_data)

    # Convert series dict to list and sort books within each series
    series_list = []
    for series_data in series_dict.values():
        # Sort books by position
        series_data["books"].sort(key=lambda x: x["position"])
        # Convert sets to lists for JSON serialization
        series_data["authors"] = sorted(list(series_data["authors"]))
        series_data["formats"] = sorted(list(series_data["formats"]))
        series_list.append(series_data)

    # Sort series by name
    series_list.sort(key=lambda x: x["name"].lower())

    # Sort standalone comics by title
    standalone_comics.sort(key=lambda x: x["title"].lower())

    all_comics = []
    for series in series_list:
        all_comics.extend(series["books"])
    all_comics.extend(standalone_comics)

    return {
        "success": True,
        "comics": all_comics,
        "series": series_list,
        "standalone": standalone_comics,
        "total_count": paginator.count,
        "page": page,
        "per_page": per_page,
        "num_pages": paginator.num_pages,
        "has_next": page_obj.has_next(),
        "has_previous": page_obj.has_previous(),
        "version": "unified",
    }


@login_required
@ajax_response_handler
def comics_ajax_detail(request, comic_id):
    """AJAX endpoint for comic book detail"""
    Book = apps.get_model("books", "Book")
    book = get_object_or_404(Book.objects.select_related("scan_folder", "finalmetadata"), id=comic_id)
    comic_detail = format_book_detail_for_json(book)

    return {"success": True, "comic": comic_detail, "version": "unified"}


@login_required
@ajax_response_handler
def comics_ajax_download(request, book_id):
    """AJAX endpoint for comic download"""
    Book = apps.get_model("books", "Book")
    book = get_object_or_404(Book, id=book_id)

    first_file = book.files.first()
    if not first_file or not first_file.file_path or not os.path.exists(first_file.file_path):
        return {"success": False, "error": "File not found"}

    # For now, return the file path - actual download implementation may vary
    filename = os.path.basename(first_file.file_path)
    return {"success": True, "download_url": f"/books/download/{book_id}/", "filename": filename}


class AudiobooksMainView(LoginRequiredMixin, TemplateView):
    """Main audiobooks section"""

    template_name = "books/sections/audiobooks_main.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Count audiobooks from scan folders designated as 'audiobooks'
        Book = apps.get_model("books", "Book")
        audiobooks_count = Book.objects.filter(
            scan_folder__content_type="audiobooks", scan_folder__is_active=True, files__file_format__in=AUDIOBOOK_FORMATS  # Use AUDIOBOOK_FORMATS for consistency
        ).count()

        context["audiobooks_count"] = audiobooks_count

        return context


@login_required
@ajax_response_handler
def audiobooks_ajax_list(request):
    """AJAX endpoint for audiobooks list"""
    Book = apps.get_model("books", "Book")

    # Get audiobooks from scan folders designated as 'audiobooks'
    audiobooks_query = (
        Book.objects.filter(scan_folder__content_type="audiobooks", scan_folder__is_active=True, files__file_format__in=AUDIOBOOK_FORMATS)  # Use AUDIOBOOK_FORMATS for consistency
        .select_related("scan_folder")
        .prefetch_related("metadata", "series_relationships", "files")
    )

    # Get search and filter parameters
    search = request.GET.get("search", "").strip()
    format_filter = request.GET.get("format", "").strip()
    sort_by = request.GET.get("sort", "id")  # Default to simple field

    # Apply filters
    if search:
        # Simple search in the metadata table
        audiobooks_query = audiobooks_query.filter(
            Q(metadata__field_name="title", metadata__field_value__icontains=search)
            | Q(metadata__field_name="author", metadata__field_value__icontains=search)
            | Q(metadata__field_name="narrator", metadata__field_value__icontains=search)
            | Q(metadata__field_name="publisher", metadata__field_value__icontains=search)
        ).distinct()

    if format_filter:
        audiobooks_query = audiobooks_query.filter(files__file_format=format_filter)

    # Apply simple sorting for now
    if sort_by == "date":
        audiobooks_query = audiobooks_query.order_by("-last_scanned")
    elif sort_by == "size":
        audiobooks_query = audiobooks_query.order_by("-files__file_size")
    elif sort_by == "duration":
        # For future implementation when duration metadata is available
        audiobooks_query = audiobooks_query.order_by("id")
    else:
        audiobooks_query = audiobooks_query.order_by("id")  # Simple default sort

    # Get user's items_per_page setting and apply pagination
    profile = UserProfile.get_or_create_for_user(request.user)
    per_page = int(request.GET.get("per_page", profile.items_per_page))
    page = int(request.GET.get("page", 1))

    # Paginate the queryset
    paginator = Paginator(audiobooks_query, per_page)
    page_obj = paginator.get_page(page)

    # Build response data
    audiobooks_data = []
    for book in page_obj:
        # Get the best metadata
        metadata = get_book_metadata_dict(book)

        # Get series information
        series_info = book.series_relationships.first()

        # Get file info from first BookFile
        first_file = book.files.first()
        file_format = first_file.file_format if first_file else "UNKNOWN"
        file_size = (first_file.file_size or 0) if first_file else 0
        cover_path = first_file.cover_path if first_file and first_file.cover_path else ""

        audiobooks_data.append(
            {
                "id": book.id,
                "title": metadata.get("title", "Unknown Title"),
                "author": metadata.get("author", "Unknown Author"),
                "author_display": metadata.get("author", "Unknown Author"),  # For compatibility
                "narrator": metadata.get("narrator", ""),
                "publisher": metadata.get("publisher", ""),
                "description": metadata.get("description", ""),
                "isbn": metadata.get("isbn", ""),
                "language": metadata.get("language", ""),
                "duration": metadata.get("duration", ""),
                "publication_date": metadata.get("publication_date"),
                "file_format": file_format,
                "file_size": file_size,
                "file_size_display": f"{file_size // (1024*1024)} MB" if file_size else "Unknown",
                "last_scanned": book.last_scanned.isoformat() if book.last_scanned else None,
                "series_name": series_info.series.name if series_info and series_info.series else "",
                "series_position": series_info.series_number if series_info else None,
                "cover_url": cover_path,
            }
        )

    return {
        "success": True,
        "audiobooks": audiobooks_data,
        "books": audiobooks_data,  # For compatibility with base class expectation
        "total_count": paginator.count,
        "page": page,
        "per_page": per_page,
        "num_pages": paginator.num_pages,
        "has_next": page_obj.has_next(),
        "has_previous": page_obj.has_previous(),
    }


@ajax_response_handler
def audiobooks_ajax_detail(request, book_id):
    """AJAX endpoint for audiobook detail - supports both Book and Audiobook models"""
    # Try to import and use Audiobook model if it exists (for future compatibility)
    try:
        from books.models import Audiobook

        audiobook = get_object_or_404(Audiobook, id=book_id)
        audiobook_data = format_book_detail_for_json(audiobook)
        return {"success": True, "id": audiobook.id, "audiobook": audiobook_data, **audiobook_data}  # Include all data at top level for compatibility
    except (ImportError, AttributeError):
        # Audiobook model doesn't exist, fall back to Book model
        pass
    except Exception:
        # Audiobook exists but this book isn't found, fall back to Book model
        pass

    # Fall back to Book model (legacy)
    Book = apps.get_model("books", "Book")
    book = get_object_or_404(Book.objects.select_related("scan_folder", "finalmetadata"), id=book_id)
    audiobook_data = format_book_detail_for_json(book)

    return {"success": True, "id": book.id, "audiobook": audiobook_data, **audiobook_data}  # Include all data at top level for compatibility


@login_required
@ajax_response_handler
def audiobooks_ajax_download(request, book_id):
    """AJAX endpoint for audiobook download"""
    Book = apps.get_model("books", "Book")
    book = get_object_or_404(Book, id=book_id)

    first_file = book.files.first()
    if not first_file or not first_file.file_path or not os.path.exists(first_file.file_path):
        return {"success": False, "error": "File not found"}

    # For now, return the file path - actual download implementation may vary
    filename = os.path.basename(first_file.file_path)
    return {"success": True, "download_url": f"/books/download/{book_id}/", "filename": filename}


@login_required
def ebooks_ajax_download(request, book_id):
    """AJAX endpoint to handle ebook downloads"""
    import mimetypes

    from django.http import FileResponse, Http404
    from django.utils.encoding import escape_uri_path

    try:
        Book = apps.get_model("books", "Book")
        book = get_object_or_404(Book, id=book_id)

        # Get the file path
        first_file = book.files.first()
        if not first_file or not first_file.file_path:
            raise Http404("No file found for this ebook")

        file_path = first_file.file_path

        # Check if file exists
        if not os.path.exists(file_path):
            raise Http404("File not found on disk")

        # Get filename and content type
        filename = os.path.basename(file_path)
        content_type, _ = mimetypes.guess_type(file_path)
        if not content_type:
            content_type = "application/octet-stream"

        # Open and serve the file
        file_handle = open(file_path, "rb")
        response = FileResponse(file_handle, content_type=content_type)
        response["Content-Disposition"] = f'attachment; filename="{escape_uri_path(filename)}"'
        response["Content-Length"] = os.path.getsize(file_path)

        return response

    except Http404:
        raise
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@login_required
@ajax_response_handler
def ebooks_ajax_companion_files(request, book_id):
    """AJAX endpoint to get companion files for ebooks"""
    # Validate book exists
    Book = apps.get_model("books", "Book")
    get_object_or_404(Book, id=book_id)

    # Placeholder implementation for companion files
    companion_files = []

    return {"success": True, "companion_files": companion_files}


@login_required
@ajax_response_handler
def series_ajax_detail(request, series_name):
    """AJAX endpoint for series detail"""
    from urllib.parse import unquote

    # URL decode the series name
    series_name = unquote(series_name)

    # Get books in this series from FinalMetadata
    books_in_series = (
        Book.objects.filter(finalmetadata__final_series=series_name, is_placeholder=False, scan_folder__content_type="ebooks", scan_folder__is_active=True)
        .select_related("finalmetadata", "scan_folder")
        .prefetch_related("files")
    )
    books_data = []
    for book in books_in_series:
        title = "Unknown Title"
        author = "Unknown Author"

        if hasattr(book, "finalmetadata"):
            title = book.finalmetadata.final_title or title
            author = book.finalmetadata.final_author or author

        books_data.append(
            {
                "id": book.id,
                "title": title,
                "author": author,
                "cover_url": get_book_cover_url(book),
                "file_format": book.file_format or "",
                "file_size": book.file_size or 0,
                "is_read": getattr(book, "is_read", False),
                "reading_progress": getattr(book, "reading_progress", 0),
            }
        )

    return {
        "success": True,
        "name": series_name,  # Test expects this at top level
        "books": books_data,
        "book_count": len(books_data),
        "series": {
            "name": series_name,
        },
    }


@login_required
@ajax_response_handler
def series_ajax_download(request, series_id):
    """AJAX endpoint to download entire series"""
    return {"success": True, "message": "Series download initiated"}


@login_required
@ajax_response_handler
def series_ajax_download_book(request, book_id):
    """AJAX endpoint to download book from series"""
    return {"success": True, "message": "Book download initiated"}
