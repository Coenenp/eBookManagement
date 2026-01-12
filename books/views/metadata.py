"""
Metadata management views.
"""

import logging

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404, redirect, reverse
from django.views.generic import DetailView, ListView, View

from books.book_utils import CoverManager, GenreManager
from books.constants import PAGINATION
from books.mixins import MetadataContextMixin, SimpleNavigationMixin
from books.models import Author, Book, BookAuthor, BookCover, BookFile, BookGenre, BookMetadata, BookPublisher, BookSeries, BookTitle, DataSource, FinalMetadata, Publisher, Series

logger = logging.getLogger("books.scanner")


class BookMetadataListView(LoginRequiredMixin, ListView):
    """
    List view for book metadata - shows all books for metadata management
    """

    model = Book
    template_name = "books/book_list.html"
    context_object_name = "books"
    paginate_by = PAGINATION["metadata_list"]

    def get_queryset(self):
        return Book.objects.all().select_related("scan_folder").prefetch_related("finalmetadata_set")


class BookMetadataView(LoginRequiredMixin, DetailView, SimpleNavigationMixin, MetadataContextMixin):
    """
    Dedicated metadata review view - cleaned and optimized
    """

    model = Book
    template_name = "books/book_metadata.html"
    context_object_name = "book"

    def get_object(self):
        """Optimize by prefetching all relationships needed for metadata display"""
        return get_object_or_404(
            Book.objects.select_related("finalmetadata", "scan_folder").prefetch_related(
                Prefetch("titles", queryset=BookTitle.objects.filter(is_active=True).select_related("source").order_by("-confidence")),
                Prefetch("author_relationships", queryset=BookAuthor.objects.filter(is_active=True).select_related("author", "source").order_by("-confidence", "-is_main_author")),
                Prefetch("genre_relationships", queryset=BookGenre.objects.filter(is_active=True).select_related("genre", "source").order_by("-confidence")),
                Prefetch("series_relationships", queryset=BookSeries.objects.filter(is_active=True).select_related("series", "source").order_by("-confidence")),
                Prefetch("publisher_relationships", queryset=BookPublisher.objects.filter(is_active=True).select_related("publisher", "source").order_by("-confidence")),
                Prefetch("covers", queryset=BookCover.objects.filter(is_active=True).select_related("source").order_by("-confidence", "-is_high_resolution")),
                Prefetch("metadata", queryset=BookMetadata.objects.filter(is_active=True).select_related("source").order_by("-confidence")),
                Prefetch("files", queryset=BookFile.objects.order_by("id"), to_attr="prefetched_files"),
            ),
            pk=self.kwargs["pk"],
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        book = context["book"]

        # Navigation logic using mixin
        context.update(self.get_simple_navigation_context(book))

        # Metadata context using mixin
        context.update(self.get_metadata_context(book))

        # Additional metadata fields specific to metadata review
        context.update(self.get_metadata_fields_context(book))

        # Cover selection context (for cover grid partial)
        context.update(self._get_cover_selection_context(book))

        # File operations context (for rename/move partial)
        context.update(self._get_file_operations_context(book))

        # Duplicate detection context (for duplicate partial)
        context.update(self._get_duplicates_context(book))

        # Workflow context (for prev/next navigation)
        context.update(self._get_workflow_context())

        return context

    def _get_cover_selection_context(self, book):
        """Get context for cover selection grid."""
        covers = [
            {
                "id": cover.id,
                "url": cover.cover_path,
                "source": cover.source.name,
                "width": cover.width,
                "height": cover.height,
                "confidence": cover.confidence,
                "is_active": cover.is_active,
            }
            for cover in book.covers.filter(is_active=True).select_related("source")
        ]

        return {"covers": covers}

    def _get_file_operations_context(self, book):
        """Get context for file rename/move operations."""
        import os

        from books.models import UserProfile
        from books.utils.batch_renamer import CompanionFileFinder
        from books.utils.renaming_engine import PREDEFINED_PATTERNS, RenamingEngine

        book_file = book.files.first()
        file_path = book_file.file_path if book_file else None

        companion_files = []
        if file_path and os.path.exists(file_path):
            finder = CompanionFileFinder()
            companion_paths = finder.find_companion_files(file_path)
            for comp_path in companion_paths:
                companion_files.append(
                    {
                        "path": comp_path,
                        "name": os.path.basename(comp_path),
                        "size": os.path.getsize(comp_path) if os.path.exists(comp_path) else 0,
                    }
                )

        # Get user's saved templates from UserProfile
        rename_templates = []
        default_folder_pattern = "${author.sortname}"
        default_filename_pattern = "${title}.${ext}"
        include_companion_files = True  # Default value
        default_template_key = None

        if self.request.user.is_authenticated:
            profile = UserProfile.get_or_create_for_user(self.request.user)

            # Get user's default patterns
            if profile.default_folder_pattern:
                default_folder_pattern = profile.default_folder_pattern
            if profile.default_filename_pattern:
                default_filename_pattern = profile.default_filename_pattern
            include_companion_files = profile.include_companion_files

            # Add user's saved custom patterns
            for pattern in profile.saved_patterns:
                rename_templates.append(
                    {
                        "name": pattern.get("name", "Unnamed"),
                        "folder": pattern.get("folder", ""),
                        "filename": pattern.get("filename", ""),
                        "description": pattern.get("description", ""),
                        "is_custom": True,
                    }
                )

        # Add predefined patterns as fallback/examples
        for key, pattern in PREDEFINED_PATTERNS.items():
            rename_templates.append(
                {
                    "name": pattern["name"],
                    "folder": pattern["folder"],
                    "filename": pattern["filename"],
                    "description": pattern.get("description", ""),
                    "is_custom": False,
                }
            )

        # Use user's default patterns
        folder_pattern = default_folder_pattern
        filename_pattern = default_filename_pattern

        # Determine default template key by matching patterns
        for key, pattern in PREDEFINED_PATTERNS.items():
            if pattern["folder"] == default_folder_pattern and pattern["filename"] == default_filename_pattern:
                default_template_key = f"system-{key}"
                break

        # Generate preview with default pattern
        preview_path = "No file path available"
        if book:
            try:
                engine = RenamingEngine()
                target_folder = engine.process_template(folder_pattern, book)
                target_filename = engine.process_template(filename_pattern, book)
                preview_path = f"{target_folder}/{target_filename}" if target_folder else target_filename
            except Exception as e:
                preview_path = f"Error generating preview: {str(e)}"

        return {
            "book_file": book_file,
            "file_path": file_path,
            "companion_files": companion_files,
            "folder_pattern": folder_pattern,
            "filename_pattern": filename_pattern,
            "rename_templates": rename_templates,
            "preview_path": preview_path,
            "include_companion_files": include_companion_files,
            "default_template_key": default_template_key,
        }

    def _get_duplicates_context(self, book):
        """Find potential duplicate books."""
        duplicates = []
        book_file = book.files.first()

        if not book_file:
            return {"duplicates": duplicates}

        # Find by file hash (exact duplicates)
        if book_file.file_path_hash:
            duplicate_files = BookFile.objects.filter(file_path_hash=book_file.file_path_hash).exclude(book=book).select_related("book", "book__finalmetadata")

            for dup_file in duplicate_files:
                duplicates.append(
                    {
                        "type": "exact",
                        "book": dup_file.book,
                        "file_path": dup_file.file_path,
                        "reason": "Identical file hash",
                    }
                )

        # Find by similar metadata (title + author)
        if hasattr(book, "finalmetadata") and book.finalmetadata:
            fm = book.finalmetadata
            if fm.final_title and fm.final_author:
                similar_books = (
                    Book.objects.filter(finalmetadata__final_title__iexact=fm.final_title, finalmetadata__final_author__iexact=fm.final_author)
                    .exclude(id=book.id)
                    .select_related("finalmetadata")
                    .prefetch_related("files")
                )

                for similar_book in similar_books:
                    dup_file = similar_book.files.first()
                    duplicates.append(
                        {
                            "type": "similar",
                            "book": similar_book,
                            "file_path": dup_file.file_path if dup_file else "Unknown",
                            "reason": "Same title and author",
                        }
                    )

        return {"duplicates": duplicates}

    def _get_workflow_context(self):
        """Get context for workflow mode (prev/next navigation)."""
        # Check if in workflow mode
        workflow_mode = self.request.GET.get("workflow") == "1"

        if not workflow_mode:
            return {"workflow_mode": False}

        # Get next unreviewed book
        next_book = Book.objects.filter(finalmetadata__isnull=False).exclude(finalmetadata__is_reviewed=True).order_by("id").first()

        # Get previous reviewed book
        prev_book = Book.objects.filter(finalmetadata__is_reviewed=True).order_by("-id").first()

        return {
            "workflow_mode": True,
            "next_book": next_book,
            "prev_book": prev_book,
        }


class BookMetadataUpdateView(LoginRequiredMixin, View, SimpleNavigationMixin, MetadataContextMixin):
    """
    Enhanced metadata update view with full workflow support
    """

    def post(self, request, pk):
        action = request.POST.get("action", "save")
        book = get_object_or_404(Book, pk=pk)

        # Handle different actions
        if action == "skip":
            return self._handle_skip(request, book)
        elif action == "delete":
            return self._handle_delete(request, book)
        elif action in ["save", "save_next"]:
            return self._handle_save(request, book, action)
        else:
            messages.error(request, f"Unknown action: {action}")
            return redirect("books:book_metadata", pk=pk)

    def _handle_skip(self, request, book):
        """Skip this book and move to next in workflow."""
        messages.info(request, f"Skipped book {book.id}.")

        # Get next book in workflow
        next_book = Book.objects.filter(finalmetadata__isnull=False).exclude(finalmetadata__is_reviewed=True).exclude(id=book.id).order_by("id").first()

        if next_book:
            return redirect(f"{reverse('books:book_metadata', kwargs={'pk': next_book.id})}?workflow=1")
        else:
            messages.info(request, "No more books to process.")
            return redirect("books:dashboard")

    def _handle_delete(self, request, book):
        """Delete book and all associated files."""
        import os

        from books.utils.batch_renamer import CompanionFileFinder

        try:
            # Delete all files
            for book_file in book.files.all():
                if book_file.file_path and os.path.exists(book_file.file_path):
                    try:
                        os.remove(book_file.file_path)
                        logger.info(f"Deleted file: {book_file.file_path}")
                    except Exception as e:
                        logger.error(f"Error deleting file {book_file.file_path}: {e}")

                # Delete companion files
                if book_file.file_path:
                    finder = CompanionFileFinder()
                    companions = finder.find_companion_files(book_file.file_path)
                    for comp_path in companions:
                        try:
                            if os.path.exists(comp_path):
                                os.remove(comp_path)
                                logger.info(f"Deleted companion file: {comp_path}")
                        except Exception as e:
                            logger.error(f"Error deleting companion file {comp_path}: {e}")

            book_id = book.id
            book.soft_delete()
            messages.success(request, f"Book {book_id} and all associated files deleted.")

            # If in workflow mode, go to next book
            if request.POST.get("workflow") == "1":
                next_book = Book.objects.filter(finalmetadata__isnull=False).exclude(finalmetadata__is_reviewed=True).order_by("id").first()

                if next_book:
                    return redirect(f"{reverse('books:book_metadata', kwargs={'pk': next_book.id})}?workflow=1")

            return redirect("books:dashboard")

        except Exception as e:
            logger.error(f"Error deleting book {book.id}: {e}", exc_info=True)
            messages.error(request, f"Error deleting book: {str(e)}")
            return redirect("books:book_metadata", pk=book.id)

    def _handle_save(self, request, book, action):
        """Save metadata and optionally perform file operations."""
        try:
            final_metadata, created = FinalMetadata.objects.get_or_create(book=book)

            # Validate required fields
            final_title = request.POST.get("final_title", "").strip()
            if not final_title:
                messages.error(request, "Title is required and cannot be empty.")
                return redirect("books:book_metadata", pk=book.id)

            updated_fields = []

            # Process fields in correct order
            updated_fields.extend(self._process_text_fields(request, final_metadata))
            updated_fields.extend(self._process_cover_field(request, final_metadata, book))
            updated_fields.extend(self._process_numeric_fields(request, final_metadata))
            updated_fields.extend(self._process_genre_fields(request, book))
            updated_fields.extend(self._process_metadata_fields(request, final_metadata, book))

            # Handle duplicates
            duplicate_action = request.POST.get("duplicate_action")
            if duplicate_action == "keep_existing":
                self._delete_book_files(book)
                book.soft_delete()
                messages.success(request, "Book deleted. Kept the existing copy.")
                return self._get_next_redirect(request, action)
            elif duplicate_action == "keep_this":
                duplicate_ids = request.POST.getlist("duplicate_ids")
                for dup_id in duplicate_ids:
                    try:
                        dup_book = Book.objects.get(id=dup_id)
                        self._delete_book_files(dup_book)
                        dup_book.soft_delete()
                    except Book.DoesNotExist:
                        pass
                if duplicate_ids:
                    messages.info(request, f"Deleted {len(duplicate_ids)} duplicate(s).")

            # Handle file operations if patterns provided
            folder_pattern = request.POST.get("folder_pattern", "").strip()
            filename_pattern = request.POST.get("filename_pattern", "").strip()

            if folder_pattern and filename_pattern:
                updated_fields.extend(self._handle_file_operations(request, book, final_metadata, folder_pattern, filename_pattern))

            # Handle cover downloads
            cover_urls = request.POST.getlist("selected_covers")
            if cover_urls:
                self._download_covers(request, book, cover_urls)
                updated_fields.append("downloaded covers")

            # Handle review status
            is_reviewed = "is_reviewed" in request.POST or action == "save_next"
            if is_reviewed != final_metadata.is_reviewed:
                final_metadata.is_reviewed = is_reviewed
                updated_fields.append("reviewed status")

            # Save with flag to prevent auto-update
            final_metadata._manual_update = True
            final_metadata.save()

            if updated_fields:
                book_title = final_metadata.final_title or f"Book {book.id}"
                messages.success(request, f"Successfully updated {', '.join(updated_fields)} for '{book_title}'")
            else:
                messages.info(request, "No changes were made to the metadata.")

            return self._get_next_redirect(request, action, book.id)

        except Exception as e:
            logger.error(f"Error updating metadata for book {book.id}: {e}")
            messages.error(request, f"An error occurred while updating metadata: {str(e)}")
            return redirect("books:book_metadata", pk=book.id)

    def _get_metadata_view_context(self, book):
        """Get context data for metadata view (used for validation errors)"""
        metadata_view = BookMetadataView()
        metadata_view.object = book
        return metadata_view.get_context_data()

    def _process_text_fields(self, request, final_metadata):
        """Process title, author, series, publisher fields"""
        updated_fields = []

        text_fields = {
            "final_title": ("Title", "manual_title"),
            "final_author": ("Author", "manual_author"),
            "final_series": ("Series", "manual_series"),
            "final_publisher": ("Publisher", "manual_publisher"),
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
        final_series_number = request.POST.get("final_series_number", "").strip()
        manual_series_number = request.POST.get("manual_series_number", "").strip()

        # Determine the series number value
        series_number_value = None
        if final_series_number == "__manual__" and manual_series_number:
            series_number_value = manual_series_number
        elif final_series_number and final_series_number != "__manual__":
            series_number_value = final_series_number

        # If series number is provided, ensure a series is also selected
        if series_number_value:
            final_series = request.POST.get("final_series", "").strip()
            manual_series = request.POST.get("manual_series", "").strip()

            has_series = (final_series and final_series != "__manual__") or (final_series == "__manual__" and manual_series) or final_metadata.final_series

            if not has_series:
                messages.warning(request, "Series number was ignored because no series was selected.")
                return None

            # Save the series number
            final_metadata.final_series_number = series_number_value

            # Also create metadata entry for tracking
            manual_source, _ = DataSource.objects.get_or_create(name=DataSource.MANUAL, defaults={"trust_level": 0.9})

            BookMetadata.objects.update_or_create(
                book=final_metadata.book, field_name="series_number", source=manual_source, defaults={"field_value": series_number_value, "confidence": 1.0, "is_active": True}
            )

            # Update any existing BookSeries relationship to include the series number
            book_series = BookSeries.objects.filter(book=final_metadata.book, is_active=True).order_by("-confidence").first()

            if book_series:
                book_series.series_number = series_number_value
                book_series.save()

            return "series number"

        elif not series_number_value:
            # Clear series number if not provided
            final_metadata.final_series_number = ""

        return None

    def _process_field_with_manual(self, request, final_metadata, field_name, manual_field, display_name):
        """Process individual field with manual entry support"""
        final_value = request.POST.get(field_name, "").strip()
        manual_value = request.POST.get(manual_field, "").strip()

        value_to_save = None
        is_manual = False

        if final_value == "__manual__" and manual_value:
            value_to_save = manual_value
            is_manual = True
        elif final_value and final_value != "__manual__":
            value_to_save = final_value
        elif not final_value:
            # Clear the field
            setattr(final_metadata, field_name, "")
            return None

        if value_to_save:
            setattr(final_metadata, field_name, value_to_save)

            if is_manual:
                # Create metadata entries for manual inputs
                self._create_manual_metadata_entry(final_metadata.book, field_name, value_to_save)
                return f"{display_name} (manual)"
            else:
                # For certain fields, always create relationships even for non-manual entries
                if field_name in ["final_series", "final_author", "final_publisher"]:
                    self._create_manual_metadata_entry(final_metadata.book, field_name, value_to_save)
                return display_name

        return None

    def _create_manual_metadata_entry(self, book, field_name, value):
        """Create metadata entries for manual inputs"""
        manual_source, _ = DataSource.objects.get_or_create(name=DataSource.MANUAL, defaults={"trust_level": 0.9})

        if field_name == "final_title":
            BookTitle.objects.update_or_create(book=book, source=manual_source, defaults={"title": value, "confidence": 1.0, "is_active": True})
        elif field_name == "final_author":
            author_obj, _ = Author.objects.get_or_create(name=value)
            BookAuthor.objects.update_or_create(book=book, author=author_obj, source=manual_source, defaults={"confidence": 1.0, "is_main_author": True, "is_active": True})
        elif field_name == "final_publisher":
            publisher_obj, _ = Publisher.objects.get_or_create(name=value)
            BookPublisher.objects.update_or_create(book=book, publisher=publisher_obj, source=manual_source, defaults={"confidence": 1.0, "is_active": True})
        elif field_name == "final_series":
            series_obj, _ = Series.objects.get_or_create(name=value)
            BookSeries.objects.update_or_create(book=book, source=manual_source, defaults={"series": series_obj, "confidence": 1.0, "is_active": True})

    def _process_cover_field(self, request, final_metadata, book):
        """Process cover selection and upload."""
        from django.conf import settings

        updated_fields = []
        final_cover_path = request.POST.get("final_cover_path", "").strip()
        cover_upload = request.FILES.get("cover_upload")

        if final_cover_path == "custom_upload" and cover_upload:
            # Handle traditional form upload
            result = CoverManager.handle_cover_upload(request, book, cover_upload)
            if result["success"]:
                final_metadata.final_cover_path = result["cover_path"]
                updated_fields.append("cover (uploaded)")
        elif final_cover_path and final_cover_path != "custom_upload":
            # Handle selection of existing cover
            final_metadata.final_cover_path = final_cover_path
            updated_fields.append("cover")
        elif final_cover_path.startswith(settings.MEDIA_URL):
            # Handle AJAX uploaded cover (already processed)
            final_metadata.final_cover_path = final_cover_path
            updated_fields.append("cover (pre-uploaded)")

        return updated_fields

    def _process_numeric_fields(self, request, final_metadata):
        """Process publication year."""
        updated_fields = []

        final_year = request.POST.get("publication_year", "").strip()
        manual_year = request.POST.get("manual_publication_year", "").strip()

        year_value = None
        is_manual = False

        if final_year == "__manual__" and manual_year:
            try:
                year_value = int(manual_year)
                is_manual = True
            except ValueError:
                messages.error(request, "Invalid publication year format.")
                return updated_fields
        elif final_year and final_year != "__manual__":
            try:
                year_value = int(final_year)
            except ValueError:
                messages.error(request, "Invalid publication year format.")
                return updated_fields

        if year_value and 1000 <= year_value <= 2100:
            # Store in FinalMetadata
            final_metadata.publication_year = year_value

            # Also create/update BookMetadata entry for consistency
            manual_source, _ = DataSource.objects.get_or_create(name=DataSource.MANUAL if is_manual else DataSource.GOOGLE_BOOKS, defaults={"trust_level": 0.9})

            BookMetadata.objects.update_or_create(
                book=final_metadata.book,
                field_name="publication_year",
                source=manual_source,
                defaults={"field_value": str(year_value), "confidence": 1.0 if is_manual else 0.8, "is_active": True},
            )

            updated_fields.append("publication year (manual)" if is_manual else "publication year")
        elif final_year == "" or not final_year:
            # Clear the field
            final_metadata.publication_year = None

        return updated_fields

    def _process_metadata_fields(self, request, final_metadata, book):
        """Process ISBN, Language, and Description fields."""
        updated_fields = []

        metadata_fields = {
            "isbn": ("ISBN", "manual_isbn"),
            "language": ("Language", "manual_language"),
            "description": ("Description", "manual_description"),
        }

        for field_name, (display_name, manual_field) in metadata_fields.items():
            final_value = request.POST.get(field_name, "").strip()
            manual_value = request.POST.get(manual_field, "").strip()

            value_to_save = None
            is_manual = False

            if final_value == "__manual__" and manual_value:
                value_to_save = manual_value
                is_manual = True
            elif final_value and final_value != "__manual__":
                value_to_save = final_value

            if value_to_save:
                # Store in FinalMetadata
                setattr(final_metadata, field_name, value_to_save)

                # Also create/update BookMetadata entry
                source_name = DataSource.MANUAL if is_manual else DataSource.GOOGLE_BOOKS
                manual_source, _ = DataSource.objects.get_or_create(name=source_name, defaults={"trust_level": 0.9})

                BookMetadata.objects.update_or_create(
                    book=book, field_name=field_name, source=manual_source, defaults={"field_value": value_to_save, "confidence": 1.0 if is_manual else 0.8, "is_active": True}
                )

                updated_fields.append(f"{display_name} (manual)" if is_manual else display_name)
            elif final_value == "" or not final_value:
                # Clear the field
                setattr(final_metadata, field_name, "")

        return updated_fields

    def _process_genre_fields(self, request, book):
        """Process genre selection."""
        updated_fields = []
        selected_genres = request.POST.getlist("final_genres")
        manual_genres = request.POST.get("manual_genres", "").strip()

        try:
            # Use the fixed GenreManager
            GenreManager.handle_genre_updates(request, book, None)

            total_genres = len(selected_genres)
            if manual_genres:
                manual_count = len([g.strip() for g in manual_genres.split(",") if g.strip()])
                total_genres += manual_count

            if total_genres > 0:
                updated_fields.append(f"genres ({total_genres} selected)")
            elif "final_genres" in request.POST:
                updated_fields.append("genres (cleared)")

        except Exception as e:
            logger.error(f"Error processing genres for book {book.id}: {e}")
            messages.error(request, f"Error updating genres: {str(e)}")

        return updated_fields

    def _handle_file_operations(self, request, book, final_metadata, folder_pattern, filename_pattern):
        """Handle file rename/move operations."""
        import shutil
        from pathlib import Path

        from books.utils.opf_generator import get_opf_filename, save_opf_file
        from books.utils.renaming_engine import RenamingEngine

        updated_fields = []
        book_file = book.files.first()

        if not book_file or not book_file.file_path:
            return updated_fields

        try:
            old_path = book_file.file_path

            # Generate new path
            engine = RenamingEngine()
            target_folder = engine.process_template(folder_pattern, book)
            target_filename = engine.process_template(filename_pattern, book)

            base_path = Path(book.scan_folder.path if book.scan_folder else "/media/ebooks")
            new_path = base_path / target_folder / target_filename

            # Move file
            if str(new_path) != old_path:
                new_path.parent.mkdir(parents=True, exist_ok=True)

                # Handle existing file
                if new_path.exists():
                    counter = 1
                    while new_path.exists():
                        stem = new_path.stem
                        suffix = new_path.suffix
                        new_path = new_path.parent / f"{stem}_{counter}{suffix}"
                        counter += 1

                shutil.move(old_path, str(new_path))
                book_file.file_path = str(new_path)
                book_file.save()
                updated_fields.append("file moved/renamed")
                logger.info(f"Moved file: {old_path} -> {new_path}")

                # Move companion files
                include_companions = request.POST.get("include_companions") == "on"
                if include_companions:
                    self._move_companion_files(old_path, str(new_path))
                    updated_fields.append("companion files moved")

                # Create/update OPF file
                opf_path = str(new_path.parent / get_opf_filename(new_path.name))
                save_opf_file(final_metadata, opf_path, new_path.name)
                book_file.opf_path = opf_path
                book_file.save()
                updated_fields.append("OPF file created")

                # Update final_path
                final_metadata.final_path = str(new_path)
                final_metadata.mark_as_renamed(str(new_path), user=request.user if request.user.is_authenticated else None)

        except Exception as e:
            logger.error(f"Error moving file for book {book.id}: {e}", exc_info=True)
            messages.error(request, f"Error moving file: {str(e)}")

        return updated_fields

    def _move_companion_files(self, old_book_path, new_book_path):
        """Move companion files alongside the renamed book."""
        import shutil
        from pathlib import Path

        from books.utils.batch_renamer import CompanionFileFinder

        finder = CompanionFileFinder()
        companion_files = finder.find_companion_files(old_book_path)

        old_base = Path(old_book_path).stem
        new_base = Path(new_book_path).stem
        new_dir = Path(new_book_path).parent

        for companion_path in companion_files:
            comp_file = Path(companion_path)
            comp_name = comp_file.name

            if comp_name.startswith(old_base):
                new_comp_name = comp_name.replace(old_base, new_base, 1)
            else:
                new_comp_name = comp_name

            new_comp_path = new_dir / new_comp_name

            try:
                if comp_file.exists():
                    shutil.move(str(comp_file), str(new_comp_path))
                    logger.info(f"Moved companion file: {comp_file} -> {new_comp_path}")
            except Exception as e:
                logger.error(f"Error moving companion file {comp_file}: {e}")

    def _download_covers(self, request, book, cover_urls):
        """Download selected covers."""
        from pathlib import Path

        import requests

        book_file = book.files.first()
        if not book_file or not book_file.file_path:
            return

        book_dir = Path(book_file.file_path).parent
        book_base = Path(book_file.file_path).stem

        for idx, cover_url in enumerate(cover_urls):
            if not cover_url:
                continue

            try:
                cover_filename = f"{book_base}_cover_{idx}.jpg" if idx > 0 else f"{book_base}_cover.jpg"
                cover_path = book_dir / cover_filename

                response = requests.get(cover_url, timeout=10)
                response.raise_for_status()

                with open(cover_path, "wb") as f:
                    f.write(response.content)

                logger.info(f"Downloaded cover to: {cover_path}")

                # Update BookFile cover_path if this is the first cover
                if idx == 0:
                    book_file.cover_path = str(cover_path)
                    book_file.save()

            except Exception as e:
                logger.error(f"Error downloading cover from {cover_url}: {e}")

    def _delete_book_files(self, book):
        """Delete all files associated with a book."""
        import os

        from books.utils.batch_renamer import CompanionFileFinder

        for book_file in book.files.all():
            if book_file.file_path and os.path.exists(book_file.file_path):
                try:
                    os.remove(book_file.file_path)
                    logger.info(f"Deleted file: {book_file.file_path}")
                except Exception as e:
                    logger.error(f"Error deleting file {book_file.file_path}: {e}")

            if book_file.file_path:
                finder = CompanionFileFinder()
                companions = finder.find_companion_files(book_file.file_path)
                for comp_path in companions:
                    try:
                        if os.path.exists(comp_path):
                            os.remove(comp_path)
                            logger.info(f"Deleted companion file: {comp_path}")
                    except Exception as e:
                        logger.error(f"Error deleting companion file {comp_path}: {e}")

    def _get_next_redirect(self, request, action, current_book_id=None):
        """Get redirect URL based on action and workflow mode."""
        workflow_mode = request.POST.get("workflow") == "1" or request.GET.get("workflow") == "1"

        if action == "save_next" or workflow_mode:
            # Find next unreviewed book
            next_book = Book.objects.filter(finalmetadata__isnull=False).exclude(finalmetadata__is_reviewed=True)

            if current_book_id:
                next_book = next_book.exclude(id=current_book_id)

            next_book = next_book.order_by("id").first()

            if next_book:
                return redirect(f"{reverse('books:book_metadata', kwargs={'pk': next_book.id})}?workflow=1")
            else:
                messages.info(request, "All books have been processed!")
                return redirect("books:dashboard")
        else:
            # Return to book detail
            return redirect("books:book_detail", pk=current_book_id) if current_book_id else redirect("books:dashboard")

    def get(self, request, pk):
        """Redirect GET requests to the metadata view page"""
        return redirect("books:book_metadata", pk=pk)
