"""
Metadata management views.
"""

import logging

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404
from django.views.generic import DetailView, ListView

from books.constants import PAGINATION
from books.mixins import MetadataContextMixin, SimpleNavigationMixin
from books.models import Book, BookAuthor, BookCover, BookFile, BookGenre, BookMetadata, BookPublisher, BookSeries, BookTitle

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
        """Get context for comprehensive cover selection grid with all sources."""

        all_covers = []
        current_final_cover = book.finalmetadata.final_cover_path if hasattr(book, "finalmetadata") else ""

        # 1. Original/Internal Cover from BookFile
        book_file = book.primary_file
        if book_file and book_file.cover_path:
            source_type = book_file.cover_source_type or "external"
            source_label, source_icon, badge_class = self._get_source_display(source_type)

            all_covers.append(
                {
                    "id": f"original_{book_file.id}",
                    "path": book_file.cover_path,
                    "url": self._get_cover_url(book_file.cover_path),
                    "source_type": source_type,
                    "source_label": source_label,
                    "source_icon": source_icon,
                    "source_badge_class": badge_class,
                    "width": book_file.cover_width,
                    "height": book_file.cover_height,
                    "quality_score": book_file.cover_quality_score,
                    "confidence": None,  # Original doesn't have confidence
                    "is_final": book_file.cover_path == current_final_cover,
                    "can_download": False,  # Already local
                    "is_downloaded": True,
                }
            )

        # 2. Manually Uploaded Cover (if different from original)
        if book_file and book_file.original_cover_path and book_file.original_cover_path != book_file.cover_path:
            all_covers.append(
                {
                    "id": f"uploaded_{book_file.id}",
                    "path": book_file.cover_path,
                    "url": self._get_cover_url(book_file.cover_path),
                    "source_type": "manual",
                    "source_label": "Manual Upload",
                    "source_icon": "fa-upload",
                    "source_badge_class": "bg-primary",
                    "width": book_file.cover_width,
                    "height": book_file.cover_height,
                    "quality_score": book_file.cover_quality_score,
                    "confidence": None,
                    "is_final": book_file.cover_path == current_final_cover,
                    "can_download": False,
                    "is_downloaded": True,
                }
            )

        # 3. External/API Covers from BookCover model
        for cover in book.covers.filter(is_active=True).select_related("source").order_by("-confidence", "-is_high_resolution"):
            source_name = cover.source.name if cover.source else "Unknown"

            all_covers.append(
                {
                    "id": cover.id,
                    "path": cover.cover_path,
                    "url": cover.cover_path,  # BookCover already has full URL/path
                    "source_type": "api",
                    "source_label": source_name,
                    "source_icon": self._get_api_icon(source_name),
                    "source_badge_class": "bg-info",
                    "width": cover.width,
                    "height": cover.height,
                    "quality_score": None,  # Can add quality detection later
                    "confidence": cover.confidence,
                    "is_final": cover.cover_path == current_final_cover,
                    "can_download": not cover.is_local_file,  # Can download if it's a URL
                    "is_downloaded": cover.is_local_file,
                }
            )

        return {"all_covers": all_covers, "book": book}

    def _get_source_display(self, source_type):
        """Get display info for cover source type."""
        source_mapping = {
            "epub_internal": ("EPUB Internal", "fa-book", "bg-success"),
            "pdf_page": ("PDF Page", "fa-file-pdf", "bg-danger"),
            "archive_first": ("CBZ/CBR", "fa-file-archive", "bg-warning"),
            "mobi_internal": ("MOBI Internal", "fa-book-reader", "bg-secondary"),
            "manual": ("Manual Upload", "fa-upload", "bg-primary"),
            "external": ("External File", "fa-image", "bg-secondary"),
        }
        return source_mapping.get(source_type, ("Unknown", "fa-question", "bg-secondary"))

    def _get_api_icon(self, source_name):
        """Get icon for API source."""
        icons = {
            "Google Books": "fa-google",
            "Open Library": "fa-book-open",
            "Goodreads": "fa-book",
            "ComicVine": "fa-mask",
        }
        return icons.get(source_name, "fa-cloud")

    def _get_cover_url(self, cover_path):
        """Convert cover path to URL for display."""
        from django.conf import settings

        if not cover_path:
            return ""

        # Already a URL
        if cover_path.startswith("http://") or cover_path.startswith("https://"):
            return cover_path

        # Convert local path to media URL
        if cover_path.startswith(settings.MEDIA_ROOT):
            relative_path = cover_path[len(settings.MEDIA_ROOT) :].lstrip("\\/")
            return settings.MEDIA_URL + relative_path.replace("\\", "/")

        # Assume it's already a media URL
        return cover_path

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


from .metadata_update import BookMetadataUpdateView  # noqa: E402,F401
