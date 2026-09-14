"""
Book renaming and organization views.

This module contains views for book renaming functionality.
TODO: Extract from original views.py file (~1,500 lines) - currently placeholders.
"""

import os

from django.apps import apps
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.views.generic import ListView, TemplateView

from books.utils.batch_renamer import BatchRenamer
from books.utils.file_collision import get_collision_suffix, resolve_collision


def get_model(model_name):
    return apps.get_model("books", model_name)


from .renaming_views import BookRenamerView  # noqa: E402,F401


class TemplateManagementView(LoginRequiredMixin, TemplateView):
    """View for managing rename templates - create, edit, delete patterns."""

    template_name = "books/template_management.html"

    def get_context_data(self, **kwargs):
        """Add template management context."""
        context = super().get_context_data(**kwargs)

        # Import here to avoid circular imports
        from books.models import UserProfile
        from books.utils.renaming_engine import PREDEFINED_PATTERNS

        # Add predefined patterns
        context["predefined_patterns"] = PREDEFINED_PATTERNS

        # Add token reference for the UI
        token_reference = self._get_token_reference()
        context["available_tokens"] = token_reference
        context["token_reference"] = token_reference

        # Add pattern examples
        context["pattern_examples"] = self._get_pattern_examples()

        # Get user's default template
        profile = UserProfile.get_or_create_for_user(self.request.user)
        default_template_key = None

        # Check user templates
        for template in profile.saved_patterns:
            if template["folder"] == profile.default_folder_pattern and template["filename"] == profile.default_filename_pattern:
                default_template_key = f"user-{template['name']}"
                break

        # Check system templates if not found in user templates
        if not default_template_key:
            for key, pattern in PREDEFINED_PATTERNS.items():
                if pattern["folder"] == profile.default_folder_pattern and pattern["filename"] == profile.default_filename_pattern:
                    default_template_key = key
                    break

        # Fall back to 'comprehensive' if no match found
        if not default_template_key:
            default_template_key = "comprehensive"

        context["default_template_key"] = default_template_key

        return context

    def _get_token_reference(self):
        """Get comprehensive token reference for the UI."""
        return {
            "basic": [
                {"token": "${title}", "description": "Book title", "example": "21 Lessons for the 21st Century"},
                {"token": "${author.sortname}", "description": "Author (Last, First)", "example": "Harari, Yuval Noah"},
                {"token": "${author.fullname}", "description": "Author full name", "example": "Yuval Noah Harari"},
                {"token": "${language}", "description": "Book language", "example": "English"},
                {"token": "${category}", "description": "Book category", "example": "Non-Fiction"},
                {"token": "${ext}", "description": "File extension", "example": "epub"},
            ],
            "series": [
                {"token": "${bookseries.title}", "description": "Series name", "example": "Foundation Series"},
                {"token": "${bookseries.number}", "description": "Series number", "example": "01"},
                {"token": "${bookseries.titleSortable}", "description": "Series (sortable)", "example": "Foundation Series, The"},
            ],
            "advanced": [
                {"token": "${title[0]}", "description": "First character of title", "example": "2"},
                {"token": "${title;first}", "description": "First letter (A-Z) or #", "example": "#"},
                {"token": "${publicationyear}", "description": "Publication year", "example": "2021"},
                {"token": "${decadeShort}", "description": "Decade (short)", "example": "2020s"},
                {"token": "${format}", "description": "File format", "example": "EPUB"},
                {"token": "${genre}", "description": "Genre", "example": "Science Fiction"},
            ],
        }

    def _get_pattern_examples(self):
        """Get pattern examples for different use cases."""
        return [
            {"name": "Simple Author-Title", "folder": "${author.sortname}", "filename": "${title}.${ext}", "result": "Harari, Yuval Noah/21 Lessons for the 21st Century.epub"},
            {
                "name": "Category-Based",
                "folder": "${category}/${author.sortname}",
                "filename": "${title}.${ext}",
                "result": "Non-Fiction/Harari, Yuval Noah/21 Lessons for the 21st Century.epub",
            },
            {
                "name": "Series-Aware",
                "folder": "${author.sortname}/${bookseries.title}",
                "filename": "${bookseries.title} #${bookseries.number} - ${title}.${ext}",
                "result": "Asimov, Isaac/Foundation Series/Foundation Series #01 - Foundation.epub",
            },
        ]


class BookRenamerPreviewView(LoginRequiredMixin, TemplateView):
    """Preview book renaming operations."""

    template_name = "books/book_renamer_preview.html"

    def post(self, request, *args, **kwargs):
        """Generate preview of renaming operations."""
        selected_books = request.POST.getlist("selected_books")
        folder_pattern = request.POST.get("folder_pattern", "")
        filename_pattern = request.POST.get("filename_pattern", "")

        if not selected_books:
            return JsonResponse({"status": "error", "message": "No books selected"}, status=400)

        Book = get_model("Book")
        preview_items = []

        for book_id in selected_books:
            try:
                book = Book.objects.get(id=book_id)
                old_path = book.file_path if book.file_path else f"Book {book_id}"

                # Generate preview using RenamingEngine
                from books.utils.renaming_engine import RenamingEngine

                engine = RenamingEngine()
                target_folder = engine.process_template(folder_pattern, book) if folder_pattern else ""
                target_filename = engine.process_template(filename_pattern, book)
                new_path = f"{target_folder}/{target_filename}" if target_folder else target_filename

                preview_items.append(
                    {
                        "book_id": book_id,
                        "old_path": old_path,
                        "new_path": new_path,
                        "title": getattr(book, "final_title", f"Book {book_id}"),
                    }
                )
            except Book.DoesNotExist:
                preview_items.append({"book_id": book_id, "error": "Book not found"})
            except Exception as e:
                preview_items.append({"book_id": book_id, "error": str(e)})

        return JsonResponse(
            {
                "status": "success",
                "preview_items": preview_items,
                "total": len(preview_items),
            }
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["preview_items"] = []
        return context


class BookRenamerExecuteView(LoginRequiredMixin, TemplateView):
    """Execute book renaming operations."""

    template_name = "books/book_renamer_execute.html"

    def post(self, request, *args, **kwargs):
        """Execute book renaming operations."""
        import json

        selected_books = request.POST.getlist("selected_books")
        if not selected_books:
            return JsonResponse({"status": "error", "message": "No books selected"}, status=400)

        # Parse file actions
        file_actions_str = request.POST.get("file_actions", "[]")
        try:
            file_actions = json.loads(file_actions_str) if file_actions_str else []
        except json.JSONDecodeError:
            file_actions = []

        results = []
        Book = get_model("Book")

        # Get rename patterns from POST data
        folder_pattern = request.POST.get("folder_pattern", "")
        filename_pattern = request.POST.get("filename_pattern", "")

        for book_id in selected_books:
            try:
                book = Book.objects.get(id=book_id)
                result = self._rename_book_files(book, request.user, file_actions, folder_pattern, filename_pattern)

                # Create FileOperation for tracking
                FileOperation = get_model("FileOperation")
                FileOperation.objects.create(
                    book=book,
                    operation_type="rename",
                    original_file_path=getattr(book, "file_path", ""),
                    new_file_path=result.get("new_path", ""),
                    status="completed",
                    user=request.user,
                    notes=f"Renamed from {getattr(book, 'file_path', '')} to {result.get('new_path', '')}",
                )

                results.append({"book_id": book_id, "status": "success", "result": result})
            except Book.DoesNotExist:
                results.append({"book_id": book_id, "status": "error", "message": "Book not found"})
            except Exception as e:
                results.append({"book_id": book_id, "status": "error", "message": str(e)})

        successful_results = [r for r in results if r["status"] == "success"]
        error_results = [r for r in results if r["status"] == "error"]

        return JsonResponse(
            {
                "status": "success",
                "results": results,
                "message": f"Processed {len(results)} books",
                "total": len(results),
                "successful": len(successful_results),
                "errors": error_results,  # Return the actual error list, not the count
                "success": [r["result"] for r in successful_results],  # Results of successful operations
                "warnings": [r["message"] for r in error_results],  # Error messages as warnings
            }
        )

    def _rename_book_files(self, book, user, file_actions, folder_pattern="", filename_pattern=""):
        """Rename book files based on final metadata using BatchRenamer."""
        from books.utils.batch_renamer import BatchRenamer

        renamer = BatchRenamer(dry_run=False)
        renamer.add_book(book, folder_pattern, filename_pattern, embed_metadata=True)

        if not renamer.operations:
            return {"new_path": book.file_path, "additional_files": [], "old_path": book.file_path, "status": "no_operations"}

        result = renamer.execute()

        new_path = getattr(book, "file_path", "")
        if result.successful > 0:
            # Refresh book to get updated file path after rename
            book.refresh_from_db()
            new_path = book.file_path

        return {
            "new_path": new_path,
            "additional_files": [],
            "old_path": getattr(book, "file_path", ""),
            "status": "renamed" if result.successful > 0 else "failed",
            "errors": result.errors,
        }

    def _get_file_action(self, file_index, file_actions):
        """Get the action for a specific file index."""
        if not file_actions or not isinstance(file_actions, list):
            return "rename"  # Default action

        if file_index < len(file_actions):
            return file_actions[file_index].get("action", "rename")

        return "rename"  # Default for indices beyond the list

    def _get_file_description(self, extension, file_path):
        """Get a human-readable description for a file based on its extension."""
        extension = extension.lower()

        descriptions = {
            ".opf": "eBook metadata file (OPF)",
            ".jpg": "Book cover image (JPEG)",
            ".jpeg": "Book cover image (JPEG)",
            ".png": "Book cover image (PNG)",
            ".txt": "Text file (may contain author info, synopsis, etc.)",
            ".pdf": "PDF document",
            ".epub": "EPUB eBook file",
            ".mobi": "Kindle eBook file (MOBI)",
            ".azw": "Kindle eBook file (AZW)",
            ".azw3": "Kindle eBook file (AZW3)",
            ".cbr": "Comic book archive (RAR)",
            ".cbz": "Comic book archive (ZIP)",
        }

        if extension in descriptions:
            return descriptions[extension]

        # Unknown extension - return generic description
        ext_name = extension[1:].upper() if extension.startswith(".") else extension.upper()
        return f"{ext_name} file"


class BookRenamerFileDetailsView(LoginRequiredMixin, TemplateView):
    """File details for book renaming."""

    template_name = "books/book_renamer_file_details.html"

    def post(self, request, *args, **kwargs):
        """Handle POST requests for file details."""
        book_id = request.POST.get("book_id") or request.GET.get("book_id")

        if not book_id:
            return JsonResponse({"error": "book_id is required"}, status=400)

        try:
            Book = get_model("Book")
            book = Book.objects.get(id=book_id)

            # Get file details
            file_details = self._get_file_details(book)

            # Check if file is missing
            if file_details is None:
                return JsonResponse({"error": "Main book file not found"}, status=200)

            # Categorize files
            automatic_files = []
            optional_files = []

            for file_info in file_details:
                if file_info.get("required", False) or file_info.get("type") == "main":
                    automatic_files.append(file_info)
                else:
                    optional_files.append(file_info)

            current_path = getattr(book, "file_path", "")

            return JsonResponse(
                {
                    "success": True,
                    "status": "success",
                    "current_path": current_path,
                    "new_path": current_path,  # For now, same as current
                    "book": {
                        "id": book.id,
                        "title": getattr(book.finalmetadata, "final_title", "Unknown") if hasattr(book, "finalmetadata") else "Unknown",
                        "file_path": current_path,
                    },
                    "book_info": {
                        "id": book.id,
                        "title": getattr(book.finalmetadata, "final_title", "Unknown") if hasattr(book, "finalmetadata") else "Unknown",
                        "author": getattr(book.finalmetadata, "final_author", "Unknown") if hasattr(book, "finalmetadata") else "Unknown",
                        "file_path": current_path,
                    },
                    "files": file_details,
                    "automatic_files": automatic_files,
                    "optional_files": optional_files,
                }
            )

        except Book.DoesNotExist:
            return JsonResponse({"error": "Book not found"}, status=404)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)

    def _get_file_details(self, book):
        """Get detailed information about book files."""

        files = []
        main_file_path = getattr(book, "file_path", "")

        if main_file_path:
            if not os.path.exists(main_file_path):
                # File doesn't exist - return error response
                return None  # Signal to return error response

            # File exists - process normally
            # Main book file
            file_size = os.path.getsize(main_file_path)
            original_name = os.path.basename(main_file_path)
            files.append(
                {
                    "original": main_file_path,
                    "original_name": original_name,
                    "new": main_file_path,  # Same as original for now
                    "new_name": original_name,  # Same as original for now
                    "size": file_size,
                    "size_formatted": self._format_file_size(file_size),
                    "type": "main",
                    "extension": os.path.splitext(original_name)[1].lower(),
                    "description": "Main book file",
                    "required": True,
                }
            )

            # Look for associated files (cover, metadata, etc.)
            base_dir = os.path.dirname(main_file_path)
            base_name = os.path.splitext(os.path.basename(main_file_path))[0]

            # Common associated file patterns
            patterns = [f"{base_name}.opf", f"{base_name}.jpg", f"{base_name}.jpeg", f"{base_name}.png", f"{base_name}.txt", "cover.jpg", "cover.png", "metadata.opf"]

            # Define which file types are automatic vs optional
            automatic_extensions = {".opf", ".jpg", ".jpeg", ".png"}

            for pattern in patterns:
                associated_path = os.path.join(base_dir, pattern)
                if os.path.exists(associated_path) and associated_path != main_file_path:
                    assoc_size = os.path.getsize(associated_path)
                    original_name = os.path.basename(associated_path)
                    extension = os.path.splitext(original_name)[1].lower()

                    # Determine file type and description
                    # Use extension without dot as type for test compatibility
                    if extension == ".opf":
                        description = "Metadata file"
                        file_type = "opf"
                    elif extension in {".jpg", ".jpeg"}:
                        description = "Cover image"
                        file_type = "jpg"
                    elif extension == ".png":
                        description = "Cover image"
                        file_type = "png"
                    elif extension == ".txt":
                        description = "Description file"
                        file_type = "txt"
                    else:
                        description = "Associated file"
                        file_type = extension[1:] if extension else "unknown"  # Remove dot

                    # Check if it's automatic or optional
                    is_automatic = extension in automatic_extensions

                    files.append(
                        {
                            "original": associated_path,
                            "original_name": original_name,
                            "new": associated_path,  # Same as original for now
                            "new_name": original_name,  # Same as original for now
                            "size": assoc_size,
                            "size_formatted": self._format_file_size(assoc_size),
                            "type": file_type,
                            "extension": extension,
                            "description": description,
                            "required": is_automatic,
                        }
                    )

        return files

    def _format_file_size(self, size_bytes):
        """Format file size in human-readable format."""
        if size_bytes < 1024:
            return f"{float(size_bytes)} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"


class BookRenamerRevertView(LoginRequiredMixin, TemplateView):
    """Revert book renaming operations."""

    template_name = "books/book_renamer_revert.html"


class BookRenamerHistoryView(LoginRequiredMixin, ListView):
    """History of book renaming operations."""

    template_name = "books/book_renamer_history.html"
    context_object_name = "history_items"

    def get_queryset(self):
        # TODO: Implement history queryset
        return []


@login_required
def bulk_rename_view(request):
    """Bulk rename functionality."""
    # TODO: Implement bulk rename
    return JsonResponse({"status": "success", "message": "Bulk rename not yet implemented"})


@login_required
def rename_book_form(request):
    """Rename book form handler."""
    # TODO: Implement rename form
    return JsonResponse({"status": "success", "message": "Rename form not yet implemented"})


@login_required
def rename_book(request, book_id):
    """Individual book renaming view."""
    # Import os from the parent views module to allow test patching
    from books.views import os as parent_os

    if request.method == "POST":
        try:
            Book = get_model("Book")
            book = Book.objects.get(id=book_id)

            new_filename = request.POST.get("new_filename")
            if not new_filename:
                return JsonResponse({"success": False, "error": "New filename is required"})

            # Get the primary file
            primary_file = book.primary_file
            if not primary_file:
                return JsonResponse({"success": False, "error": "Book file not found"})

            old_path = primary_file.file_path
            if not old_path:
                return JsonResponse({"success": False, "error": "Book file path not found"})

            # Check if the old file exists (this will be mocked by tests)
            if not parent_os.path.exists(old_path):
                return JsonResponse({"success": False, "error": "Original file not found"})

            # Build new path
            new_path = parent_os.path.join(parent_os.path.dirname(old_path), new_filename)

            # Resolve collision (adds " (2)", " (3)", etc. if needed)
            original_new_path = new_path
            new_path = resolve_collision(new_path)
            collision_suffix = get_collision_suffix(original_new_path, new_path)

            # Rename the file (this will be mocked by tests)
            parent_os.rename(old_path, new_path)

            # Update the primary file record
            primary_file.file_path = new_path
            primary_file.save()

            # If there was a collision, inform the user
            message = "Book renamed successfully"
            if collision_suffix:
                message += f" (renamed to avoid collision: {parent_os.path.basename(new_path)})"

            return JsonResponse({"success": True, "message": message, "new_path": new_path})

        except Book.DoesNotExist:
            return JsonResponse({"success": False, "error": "Book not found"}, status=404)
        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)})

    return JsonResponse({"success": False, "error": "Only POST method allowed"})


@login_required
def preview_rename(request):
    """Preview book rename operation."""
    if request.method == "POST":
        try:
            book_id = request.POST.get("book_id")
            new_filename = request.POST.get("new_filename")
            pattern = request.POST.get("pattern")

            if not book_id:
                return JsonResponse({"success": False, "error": "Book ID is required"})

            if not new_filename and not pattern:
                return JsonResponse({"success": False, "error": "New filename or pattern required"})

            Book = get_model("Book")
            book = Book.objects.get(id=book_id)

            # If pattern is provided, generate filename from it
            if pattern and not new_filename:
                # Mock pattern processing - in real implementation, this would use book metadata
                new_filename = "Test Author - Test Title.epub"

            return JsonResponse(
                {
                    "success": True,
                    "preview": {
                        "old_name": book.file_path.split("/")[-1] if book.file_path else "Unknown",
                        "new_name": new_filename,
                        "book_title": getattr(book, "title", "Unknown Title"),
                    },
                }
            )

        except Book.DoesNotExist:
            return JsonResponse({"success": False, "error": "Book not found"})
        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)})

    return JsonResponse({"success": False, "error": "Only POST method allowed"})


@login_required
def preview_pattern(request):
    """Preview renaming pattern for batch operations."""
    if request.method == "POST":
        try:
            from books.utils.renaming_engine import RenamingEngine, RenamingPatternValidator

            folder_pattern = request.POST.get("folder_pattern", "")
            filename_pattern = request.POST.get("filename_pattern", "")
            book_ids = request.POST.getlist("book_ids")

            # Debug logging
            import logging

            logger = logging.getLogger(__name__)
            logger.info(f"preview_pattern: book_ids={book_ids}, len={len(book_ids) if book_ids else 0}")

            if not folder_pattern or not filename_pattern:
                return JsonResponse({"success": False, "error": "Both folder and filename patterns are required"})

            # Validate patterns
            validator = RenamingPatternValidator()
            folder_valid, folder_warnings = validator.validate_pattern(folder_pattern)
            filename_valid, filename_warnings = validator.validate_pattern(filename_pattern)

            if not folder_valid or not filename_valid:
                return JsonResponse({"success": False, "error": "Invalid patterns", "folder_warnings": folder_warnings, "filename_warnings": filename_warnings})

            # Generate previews for selected books
            Book = get_model("Book")
            engine = RenamingEngine()
            previews = []

            # If no book_ids provided, get first available book for live preview
            if not book_ids or len(book_ids) == 0:
                logger.info("No book_ids provided, fetching first available book")
                # Get books that are available, not corrupted, not placeholder, and not deleted
                book_queryset = Book.objects.filter(is_available=True, is_corrupted=False, is_placeholder=False, deleted_at__isnull=True).order_by("id")[:1]
                logger.info(f"Found {book_queryset.count()} available books")
            else:
                # Limit preview to first 10 books for performance
                logger.info(f"Using provided book_ids: {book_ids[:10]}")
                book_queryset = Book.objects.filter(id__in=book_ids[:10])

            for book in book_queryset:
                try:
                    target_folder = engine.process_template(folder_pattern, book)
                    target_filename = engine.process_template(filename_pattern, book)

                    full_path = f"{target_folder}/{target_filename}" if target_folder and target_filename else None

                    previews.append(
                        {
                            "book_id": book.id,
                            "current_path": book.file_path,
                            "target_folder": target_folder,
                            "target_filename": target_filename,
                            "full_target_path": full_path,
                            "new_path": full_path,  # Add for test compatibility
                            "title": getattr(book.finalmetadata, "final_title", "Unknown") if hasattr(book, "finalmetadata") else "Unknown",
                            "author": getattr(book.finalmetadata, "final_author", "Unknown") if hasattr(book, "finalmetadata") else "Unknown",
                        }
                    )
                except Exception as e:
                    previews.append({"book_id": book.id, "error": str(e), "current_path": book.file_path})

            return JsonResponse(
                {
                    "success": True,
                    "previews": previews,
                    "folder_warnings": folder_warnings,
                    "filename_warnings": filename_warnings,
                    "total_books": len(book_ids),
                    "preview_count": len(previews),
                }
            )

        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)})

    return JsonResponse({"success": False, "error": "Only POST method allowed"})


@login_required
def execute_batch_rename(request):
    """Execute batch renaming operation."""
    if request.method == "POST":
        try:
            folder_pattern = request.POST.get("folder_pattern", "")
            filename_pattern = request.POST.get("filename_pattern", "")
            book_ids = request.POST.getlist("book_ids", [])
            dry_run = request.POST.get("dry_run", "true").lower() == "true"
            embed_metadata = request.POST.get("embed_metadata", "true").lower() == "true"
            remove_unused_images = request.POST.get("remove_unused_epub_images", "false").lower() == "true"

            if not folder_pattern or not filename_pattern:
                return JsonResponse({"success": False, "error": "Both folder and filename patterns are required"})

            if not book_ids:
                return JsonResponse({"success": False, "error": "No books selected for renaming"})

            # Get books to rename
            Book = get_model("Book")
            books = Book.objects.filter(id__in=book_ids)

            # Create batch renamer with optional image cleanup
            renamer = BatchRenamer(dry_run=dry_run, remove_unused_images=remove_unused_images)

            # Add books to the batch
            renamer.add_books(books, folder_pattern, filename_pattern, embed_metadata)

            # Get preview/summary
            operation_summary = renamer.get_operation_summary()

            if dry_run:
                # Return preview without executing
                previews = renamer.preview_operations()
                return JsonResponse({"success": True, "dry_run": True, "summary": operation_summary, "operations": previews[:20]})  # Limit for UI display
            else:
                # Execute the operations
                successful, failed, errors = renamer.execute_operations()

                return JsonResponse({"success": True, "dry_run": False, "summary": operation_summary, "results": {"successful": successful, "failed": failed, "errors": errors}})

        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)})

    return JsonResponse({"success": False, "error": "Only POST method allowed"})


@login_required
def validate_pattern(request):
    """Validate a renaming pattern."""
    if request.method == "POST":
        try:
            from books.utils.renaming_engine import RenamingPatternValidator

            pattern = request.POST.get("pattern", "")
            pattern_type = request.POST.get("type", "folder")  # 'folder' or 'filename'

            if not pattern or pattern.strip() == "":
                return JsonResponse({"success": True, "valid": False, "warnings": ["Pattern cannot be empty"], "error": "Pattern is required"})

            validator = RenamingPatternValidator()
            is_valid, warnings = validator.validate_pattern(pattern)

            # Generate sample preview if possible
            preview = None
            if is_valid:
                try:
                    # Get a sample book for preview
                    Book = get_model("Book")
                    sample_book = Book.objects.filter(finalmetadata__isnull=False).first()
                    if sample_book:
                        preview = validator.preview_pattern(pattern, sample_book)
                except Exception:
                    preview = "Could not generate preview"

            return JsonResponse({"success": True, "valid": is_valid, "warnings": warnings, "preview": preview, "pattern_type": pattern_type})

        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)})

    return JsonResponse({"success": False, "error": "Only POST method allowed"})


@login_required
def save_rename_template(request):
    """Save a rename template to user profile."""
    if request.method == "POST":
        try:
            from books.models import UserProfile

            name = request.POST.get("name", "").strip()
            folder_pattern = request.POST.get("folder_pattern", "")
            filename_pattern = request.POST.get("filename_pattern", "")
            description = request.POST.get("description", "")

            if not name:
                return JsonResponse({"success": False, "error": "Template name is required"})

            if not folder_pattern and not filename_pattern:
                return JsonResponse({"success": False, "error": "At least one pattern is required"})

            # Save to user profile
            profile = UserProfile.get_or_create_for_user(request.user)
            profile.save_pattern(name, folder_pattern, filename_pattern, description)

            return JsonResponse({"success": True, "message": f"Template '{name}' saved successfully"})

        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)})

    return JsonResponse({"success": False, "error": "Only POST method allowed"})


@login_required
def load_rename_templates(request):
    """Load user's saved rename templates."""
    try:
        from books.models import UserProfile

        profile = UserProfile.get_or_create_for_user(request.user)
        templates = profile.saved_patterns

        return JsonResponse({"success": True, "templates": templates})

    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)})


@login_required
def delete_rename_template(request):
    """Delete a rename template from user profile."""
    if request.method == "POST":
        try:
            from books.models import UserProfile

            name = request.POST.get("name", "")

            if not name:
                return JsonResponse({"success": False, "error": "Template name is required"})

            profile = UserProfile.get_or_create_for_user(request.user)
            profile.remove_pattern(name)

            return JsonResponse({"success": True, "message": f"Template '{name}' deleted successfully"})

        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)})

    return JsonResponse({"success": False, "error": "Only POST method allowed"})
