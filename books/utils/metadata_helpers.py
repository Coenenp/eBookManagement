"""
Helper functions for extracting and formatting book metadata.
Consolidates repeated logic from sections.py and other views.
"""

import os

from django.conf import settings


def get_book_metadata_dict(book):
    """
    Get metadata as dictionary from book, preferring final metadata.

    Returns a standardized metadata dictionary with fallback values.
    Used across all section views (ebooks, comics, audiobooks, series).

    Args:
        book: Book instance

    Returns:
        dict: Metadata dictionary with keys: title, author, publisher, description,
              isbn, language, publication_date
    """
    try:
        final_meta = book.finalmetadata
        if final_meta:
            metadata = {
                "title": final_meta.final_title or "Unknown Title",
                "author": final_meta.final_author or "Unknown Author",
                "publisher": final_meta.final_publisher or "",
                "description": final_meta.description or "",
                "isbn": final_meta.isbn or "",
                "language": final_meta.language or "",
                "publication_date": final_meta.publication_year,
            }
            return metadata
    except Exception:
        pass

    # Fallback to metadata entries if no final metadata
    metadata_dict = {
        "title": "Unknown Title",
        "author": "Unknown Author",
        "publisher": "",
        "description": "",
        "isbn": "",
        "language": "",
        "publication_date": None,
    }

    # Get metadata entries
    has_metadata = False
    for meta in book.metadata.filter(is_active=True):
        has_metadata = True
        field_name = meta.field_name.lower()
        if field_name == "title":
            metadata_dict["title"] = meta.field_value or "Unknown Title"
        elif field_name == "author":
            metadata_dict["author"] = meta.field_value or "Unknown Author"
        elif field_name == "publisher":
            metadata_dict["publisher"] = meta.field_value or ""
        elif field_name == "description":
            metadata_dict["description"] = meta.field_value or ""
        elif field_name == "isbn":
            metadata_dict["isbn"] = meta.field_value or ""
        elif field_name == "language":
            metadata_dict["language"] = meta.field_value or ""
        elif field_name == "publication_date":
            try:
                metadata_dict["publication_date"] = int(meta.field_value) if meta.field_value else None
            except (ValueError, TypeError):
                metadata_dict["publication_date"] = None

    # If has metadata but no title, use filename as last resort
    if has_metadata and metadata_dict["title"] == "Unknown Title":
        first_file = book.files.first()
        filename = os.path.basename(first_file.file_path) if first_file and first_file.file_path else "Unknown Title"
        metadata_dict["title"] = filename

    return metadata_dict


def get_book_cover_url(book):
    """
    Get cover URL for a book, handling both HTTP URLs and local paths.

    Tries final metadata cover path first, then falls back to cover entries.

    Args:
        book: Book instance

    Returns:
        str: Cover URL (HTTP or media URL) or empty string if no cover found
    """
    # Try to get the final metadata cover path
    try:
        final_meta = book.final_metadata
        if final_meta and final_meta.final_cover_path:
            cover_path = final_meta.final_cover_path
            if cover_path.startswith("http"):
                return cover_path
            else:
                # Convert local path to media URL
                if cover_path.startswith(settings.MEDIA_ROOT):
                    relative_path = cover_path[len(settings.MEDIA_ROOT) :].lstrip("\\/")
                    return settings.MEDIA_URL + relative_path.replace("\\", "/")
                return cover_path
    except (AttributeError, ValueError, TypeError):
        pass

    # Fallback to cover entries
    try:
        cover = book.covers.filter(is_final=True).first()
        if not cover:
            cover = book.covers.first()

        if cover:
            if cover.cover_url and cover.cover_url.startswith("http"):
                return cover.cover_url
            elif cover.cover_path:
                if cover.cover_path.startswith(settings.MEDIA_ROOT):
                    relative_path = cover.cover_path[len(settings.MEDIA_ROOT) :].lstrip("\\/")
                    return settings.MEDIA_URL + relative_path.replace("\\", "/")
                return cover.cover_path
    except Exception:
        pass

    return ""


def format_book_detail_for_json(book):
    """
    Format a book instance into a standardized JSON-serializable dictionary.

    Consolidates the near-identical logic from ebooks_ajax_detail, comics_ajax_detail,
    audiobooks_ajax_detail, and series_ajax_detail views.

    Args:
        book: Book instance

    Returns:
        dict: Complete book data including metadata, files, covers, and tabs
    """
    # Get metadata
    metadata = get_book_metadata_dict(book)

    # Get series information
    series_info = book.series_relationships.first()
    series_name = series_info.series.name if series_info and series_info.series else ""
    series_position = series_info.series_number if series_info else None

    # Get cover URL
    cover_url = get_book_cover_url(book)

    # Build files list
    files_list = []
    for book_file in book.files.all():
        files_list.append(
            {
                "id": book_file.id,
                "filename": os.path.basename(book_file.file_path),
                "file_path": book_file.file_path,
                "file_format": book_file.file_format,
                "file_size": book_file.file_size,
                "file_size_display": f"{book_file.file_size // (1024*1024)} MB" if book_file.file_size else "0 MB",
            }
        )

    # Build covers list
    covers_list = []
    if cover_url:
        covers_list.append({"id": "primary", "source": "Final Metadata", "url": cover_url, "is_final": True})

    # Add additional covers from cover entries
    for cover in book.covers.all():
        cover_media_url = ""
        # BookCover model uses cover_path, not cover_url
        if cover.cover_path:
            if cover.cover_path.startswith("http"):
                # External URL
                cover_media_url = cover.cover_path
            elif cover.cover_path.startswith(settings.MEDIA_ROOT):
                # Local file - convert to media URL
                relative_path = cover.cover_path[len(settings.MEDIA_ROOT) :].lstrip("\\/")
                cover_media_url = settings.MEDIA_URL + relative_path.replace("\\", "/")
            else:
                # Other path
                cover_media_url = cover.cover_path

        if cover_media_url:
            if cover_media_url != cover_url:  # Don't duplicate primary cover
                covers_list.append(
                    {"id": cover.id, "source": cover.source.name if cover.source else "Unknown", "url": cover_media_url, "is_final": getattr(cover, "is_final_metadata", False)}
                )

    # Build metadata sources list for metadata tab
    metadata_sources = []
    for meta in book.metadata.all():
        metadata_sources.append(
            {
                "id": meta.id,
                "source": meta.source.name if meta.source else "Unknown",
                "field_name": meta.field_name,
                "field_value": meta.field_value,
                "confidence": meta.confidence,
                "is_active": meta.is_active,
            }
        )

    # Get first file for top-level format and path
    first_file = book.files.first()
    file_format = first_file.file_format if first_file else None
    file_path = first_file.file_path if first_file else None
    file_size = first_file.file_size if first_file else None

    # Get scan folder information safely
    scan_folder_id = None
    scan_folder_path = None
    scan_folder_name = None
    try:
        if hasattr(book, "scan_folder") and book.scan_folder:
            scan_folder_id = getattr(book.scan_folder, "id", None)
            scan_folder_path = getattr(book.scan_folder, "path", None)  # Changed from 'folder_path' to 'path'
            scan_folder_name = getattr(book.scan_folder, "name", None)
    except Exception:
        # Handle case where scan_folder doesn't exist or is inaccessible
        pass

    # Build the complete book data
    book_data = {
        "id": book.id,
        "title": metadata.get("title", "Unknown Title"),
        "author": metadata.get("author", "Unknown Author"),
        "publisher": metadata.get("publisher", ""),
        "description": metadata.get("description", ""),
        "isbn": metadata.get("isbn", ""),
        "language": metadata.get("language", ""),
        "publication_date": metadata.get("publication_date"),
        "series_name": series_name,
        "series_position": series_position,
        "cover_url": cover_url,
        "last_scanned": book.last_scanned.isoformat() if book.last_scanned else None,
        # Add top-level file info for easy access
        "file_format": file_format,
        "file_path": file_path,
        "file_size": file_size,
        "scan_folder_id": scan_folder_id,
        "scan_folder_path": scan_folder_path,
        "scan_folder_name": scan_folder_name,
        # Tab data for right panel
        "files": files_list,
        "covers": covers_list,
        "metadata": metadata_sources,
        "file_count": len(files_list),
    }

    return book_data
