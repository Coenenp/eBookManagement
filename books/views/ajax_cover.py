"""
Phase 2 Cover Management AJAX Endpoints

Handles:
- Manual cover upload/replace for BookFile
- Multi-cover selection from internal images
- Cover quality analysis
- Cover restoration
"""

import logging

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_http_methods, require_POST

from books.forms import CoverUploadForm
from books.models import BookFile
from books.utils.cover_cache import CoverCache
from books.utils.decorators import ajax_response_handler

logger = logging.getLogger("books.cover")


@ajax_response_handler
@require_POST
@login_required
def ajax_upload_bookfile_cover(request, bookfile_id):
    """
    Upload a manual cover for a BookFile.

    This replaces the auto-detected cover with a user-uploaded image.
    The original cover path is saved for restoration capability.

    POST /ajax/bookfile/<id>/upload_cover/
    Files: cover_image (image file)

    Returns:
        {
            "success": true,
            "cover_url": "/media/cover_cache/abc123.jpg",
            "cover_path": "cover_cache/abc123.jpg",
            "width": 800,
            "height": 1200,
            "quality_score": 85,
            "message": "Cover uploaded successfully"
        }
    """
    # Get BookFile first (raises Http404 if not found - handled by decorator)
    bookfile = get_object_or_404(BookFile, pk=bookfile_id)

    try:
        # Validate form
        form = CoverUploadForm(request.POST, request.FILES)
        if not form.is_valid():
            return JsonResponse({"success": False, "errors": form.errors}, status=400)

        # Get validated image and dimensions
        cover_image = form.cleaned_data["cover_image"]
        width, height = form.get_dimensions()

        # Read image data
        cover_data = cover_image.read()

        # Save original cover path if not already saved
        if not bookfile.original_cover_path and bookfile.cover_path:
            bookfile.original_cover_path = bookfile.cover_path

        # Save to cache with special key for manual uploads
        cache_path = CoverCache.save_cover(bookfile.file_path, cover_data, internal_path="manual_upload")

        if not cache_path:
            return JsonResponse({"success": False, "error": "Failed to save cover to cache"}, status=500)

        # Calculate quality score (simple version for now)
        quality_score = _calculate_quality_score(width, height, len(cover_data))

        # Update BookFile
        bookfile.cover_path = cache_path
        bookfile.cover_source_type = "manual"
        bookfile.has_internal_cover = False
        bookfile.cover_internal_path = ""
        bookfile.cover_width = width
        bookfile.cover_height = height
        bookfile.cover_quality_score = quality_score
        bookfile.save()

        # Generate URL for display
        cover_url = f"{settings.MEDIA_URL}{cache_path}"

        logger.info(f"Manual cover uploaded for BookFile {bookfile_id}: {cache_path}")

        return JsonResponse(
            {
                "success": True,
                "cover_url": cover_url,
                "cover_path": cache_path,
                "width": width,
                "height": height,
                "quality_score": quality_score,
                "message": "Cover uploaded successfully",
            }
        )

    except Exception as e:
        logger.error(f"Error uploading cover for BookFile {bookfile_id}: {e}", exc_info=True)
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@ajax_response_handler
@require_POST
@login_required
def ajax_restore_original_cover(request, bookfile_id):
    """
    Restore the original auto-detected cover, removing manual upload.

    POST /ajax/bookfile/<id>/restore_cover/

    Returns:
        {
            "success": true,
            "cover_url": "/media/cover_cache/def456.jpg",
            "cover_path": "cover_cache/def456.jpg",
            "message": "Original cover restored"
        }
    """
    # Get BookFile first (raises Http404 if not found)
    bookfile = get_object_or_404(BookFile, pk=bookfile_id)

    try:
        if not bookfile.original_cover_path:
            return JsonResponse({"success": False, "error": "No original cover to restore"}, status=400)

        # Delete manual upload from cache
        if bookfile.cover_source_type == "manual" and bookfile.cover_path:
            try:
                CoverCache.delete_cover(bookfile.file_path, "manual_upload")
            except Exception as e:
                logger.warning(f"Failed to delete manual cover from cache: {e}")

        # Restore original cover
        original_path = bookfile.original_cover_path
        bookfile.cover_path = original_path
        bookfile.cover_source_type = _infer_source_type(bookfile)
        bookfile.original_cover_path = ""
        bookfile.save()

        cover_url = f"{settings.MEDIA_URL}{original_path}"

        logger.info(f"Restored original cover for BookFile {bookfile_id}")

        return JsonResponse({"success": True, "cover_url": cover_url, "cover_path": original_path, "message": "Original cover restored"})

    except Exception as e:
        logger.error(f"Error restoring cover for BookFile {bookfile_id}: {e}", exc_info=True)
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@ajax_response_handler
@require_http_methods(["GET"])
@login_required
def ajax_get_cover_info(request, bookfile_id):
    """
    Get current cover information for a BookFile.

    GET /ajax/bookfile/<id>/cover_info/

    Returns:
        {
            "success": true,
            "has_cover": true,
            "cover_url": "/media/cover_cache/abc123.jpg",
            "cover_source": "manual",
            "width": 800,
            "height": 1200,
            "quality_score": 85,
            "has_original": true,
            "can_restore": true
        }
    """
    # Get BookFile first (raises Http404 if not found)
    bookfile = get_object_or_404(BookFile, pk=bookfile_id)

    try:
        has_cover = bool(bookfile.cover_path)
        cover_url = f"{settings.MEDIA_URL}{bookfile.cover_path}" if has_cover else None

        return JsonResponse(
            {
                "success": True,
                "has_cover": has_cover,
                "cover_url": cover_url,
                "cover_path": bookfile.cover_path,
                "cover_source": bookfile.cover_source_type,
                "width": bookfile.cover_width,
                "height": bookfile.cover_height,
                "quality_score": bookfile.cover_quality_score,
                "has_original": bool(bookfile.original_cover_path),
                "can_restore": bool(bookfile.original_cover_path and bookfile.cover_source_type == "manual"),
            }
        )

    except Exception as e:
        logger.error(f"Error getting cover info for BookFile {bookfile_id}: {e}")
        return JsonResponse({"success": False, "error": str(e)}, status=500)


def _calculate_quality_score(width, height, file_size):
    """
    Calculate a simple quality score (0-100) based on dimensions and file size.

    Higher scores indicate better quality.
    More sophisticated analysis will be added in Feature 5.
    """
    score = 50  # Base score

    # Resolution score (0-30 points)
    pixels = width * height
    if pixels >= 1000000:  # >= 1MP
        score += 30
    elif pixels >= 500000:  # >= 0.5MP
        score += 20
    elif pixels >= 250000:  # >= 0.25MP
        score += 10

    # Aspect ratio score (0-10 points) - prefer portrait ~1.5:1
    aspect_ratio = height / width if width > 0 else 0
    if 1.4 <= aspect_ratio <= 1.6:
        score += 10
    elif 1.2 <= aspect_ratio <= 1.8:
        score += 5

    # File size score (0-10 points) - bigger usually means better quality
    if file_size >= 150000:  # >= 150KB
        score += 10
    elif file_size >= 75000:  # >= 75KB
        score += 5

    return min(100, max(0, score))


def _infer_source_type(bookfile):
    """Infer cover source type from file format and internal_path"""
    if bookfile.cover_internal_path:
        ext = bookfile.file_format.lower()
        if ext in ["epub", "mobi", "azw3"]:
            return f"{ext}_internal"
        elif ext in ["cbz", "cbr"]:
            return "archive_first"
        elif ext == "pdf":
            return "pdf_page"
    return "external"
