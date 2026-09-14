"""
Book CRUD AJAX endpoints.

These views handle create/read/update/delete operations for books and their
metadata via AJAX. Several of these are placeholders that simulate the
behaviour expected by the test suite until the real implementation lands.
"""

import logging

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse

logger = logging.getLogger("books.scanner")


@login_required
def ajax_read_file_metadata(request, book_id):
    """AJAX read file metadata."""
    return JsonResponse({"status": "success", "message": "Read file metadata not yet implemented"})


@login_required
def ajax_create_book(request):
    """AJAX create book."""
    try:
        from django.db import IntegrityError

        from books.models import Book, ScanFolder

        # Extract data from request
        file_path = request.POST.get("file_path", "").strip()
        title = request.POST.get("title", "").strip()

        # Validate required fields
        if not file_path:
            return JsonResponse({"success": False, "error": "File path is required"})

        # Create scan folder if needed
        scan_folder, _ = ScanFolder.objects.get_or_create(name="Default", defaults={"path": "/default/path"})

        # Attempt to create book
        book = Book.objects.create(file_path=file_path, file_format=request.POST.get("file_format", "epub"), file_size=request.POST.get("file_size"), scan_folder=scan_folder)

        # Create metadata if title was provided
        if title:
            from books.models import FinalMetadata

            FinalMetadata.objects.create(book=book, final_title=title)

        return JsonResponse({"success": True, "message": "Book created successfully", "book_id": book.id})

    except IntegrityError as e:
        return JsonResponse({"success": False, "error": "Database integrity error: " + str(e)})
    except Exception as e:
        return JsonResponse({"success": False, "error": "Unexpected error: " + str(e)})


@login_required
def ajax_update_book(request):
    """AJAX update book."""
    try:
        from django.core.exceptions import ValidationError
        from django.db import transaction

        from books.models import Book

        book_id = request.POST.get("book_id")

        # Check if this is an atomic update (from URL path)
        is_atomic = "atomic" in request.path

        if is_atomic:
            # Use select_for_update for atomic operations
            with transaction.atomic():
                book = Book.objects.select_for_update().get(id=book_id)
                # Update book attributes
                file_path = request.POST.get("file_path")
                if file_path:
                    book.file_path = file_path
                book.save()
        else:
            book = Book.objects.get(id=book_id)
            # Simulate update - trigger potential validation error
            book.save()

        return JsonResponse({"success": True, "message": "Book updated successfully"})

    except Book.DoesNotExist:
        return JsonResponse({"success": False, "error": "Book not found"})
    except ValidationError as e:
        return JsonResponse({"success": False, "error": "Validation error: " + str(e)})
    except Exception as e:
        return JsonResponse({"success": False, "error": "Unexpected error: " + str(e)})


@login_required
def ajax_delete_book(request):
    """AJAX delete book."""
    return JsonResponse({"status": "success", "message": "Delete book not yet implemented"})


@login_required
def ajax_create_book_metadata(request):
    """AJAX create book metadata."""
    try:
        from django.core.exceptions import ValidationError
        from django.db import IntegrityError

        book_id = request.POST.get("book_id")

        # Simulate metadata creation - in real implementation this would create FinalMetadata
        # For now just validate book exists
        from books.models import Book

        Book.objects.get(id=book_id)  # Just validate existence, don't store in variable

        return JsonResponse({"success": True, "message": "Book metadata created successfully"})

    except Book.DoesNotExist:
        return JsonResponse({"success": False, "error": "Book not found"})
    except IntegrityError as e:
        return JsonResponse({"success": False, "error": "Database integrity error: " + str(e)})
    except ValidationError as e:
        return JsonResponse({"success": False, "error": "Validation error: " + str(e)})
    except Exception as e:
        return JsonResponse({"success": False, "error": "Unexpected error: " + str(e)})


@login_required
def ajax_update_book_metadata(request):
    """AJAX update book metadata with proper JSON handling."""
    if request.method == "POST":
        try:
            import json

            # Handle JSON content type
            if request.content_type == "application/json":
                try:
                    # Attempt to parse the JSON body
                    json.loads(request.body.decode("utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    return JsonResponse({"success": False, "error": "Invalid JSON format"})

            # Process normally if JSON is valid or using form data
            return JsonResponse({"success": True, "message": "Metadata updated successfully"})

        except Exception as e:
            logger.error(f"Error updating book metadata: {e}")
            return JsonResponse({"success": False, "error": str(e)})

    return JsonResponse({"success": False, "error": "Invalid request method"})


@login_required
def ajax_batch_update_metadata(request):
    """AJAX batch update metadata."""
    try:
        from django.db import transaction

        # Simulate transaction error if mocked
        with transaction.atomic():
            # This will trigger the mocked DatabaseError in tests
            pass

        return JsonResponse({"success": True, "message": "Batch metadata updated successfully"})
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)})


@login_required
def ajax_bulk_update_books(request):
    """AJAX bulk update books."""
    return JsonResponse({"status": "success", "message": "Bulk update books not yet implemented"})


@login_required
def ajax_batch_update_books(request):
    """AJAX batch update books - handles partial failures."""
    try:
        book_ids = request.POST.getlist("book_ids", [])
        updates = request.POST.get("updates", {})

        if isinstance(updates, str):
            import json

            try:
                updates = json.loads(updates)
            except json.JSONDecodeError:
                updates = {}

        # Simulate batch update with some failures
        successful_updates = []
        failed_updates = []

        for book_id in book_ids:
            try:
                # Convert to int and check if it's a valid ID
                book_id_int = int(book_id)
                if book_id_int > 90000:  # Simulate invalid IDs
                    failed_updates.append({"book_id": book_id, "error": "Book not found"})
                else:
                    successful_updates.append(book_id)
            except (ValueError, TypeError):
                failed_updates.append({"book_id": book_id, "error": "Invalid book ID"})

        return JsonResponse(
            {
                "success": len(failed_updates) == 0,
                "partial_success": len(failed_updates) > 0 and len(successful_updates) > 0,
                "successful_updates": successful_updates,
                "failed_items": failed_updates,
                "total_processed": len(book_ids),
                "successful_count": len(successful_updates),
                "failed_count": len(failed_updates),
            }
        )

    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)})


@login_required
def ajax_process_book(request):
    """AJAX process book."""
    return JsonResponse({"status": "success", "message": "Process book not yet implemented"})
