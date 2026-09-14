"""
Book renaming view classes.

Contains the class-based views for the book renaming/organization workflow.
"""

from django.apps import apps
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import models
from django.views.generic import ListView

from books.constants import PAGINATION
from books.models import COMIC_FORMATS


def get_model(model_name):
    return apps.get_model("books", model_name)


class BookRenamerView(LoginRequiredMixin, ListView):
    """Enhanced view for organizing and renaming reviewed books with template patterns."""

    template_name = "books/book_renamer.html"
    context_object_name = "books"
    paginate_by = PAGINATION["book_renamer"]

    def get_model(self):
        return get_model("Book")

    def get_queryset(self):
        """Return reviewed books that can be renamed/organized."""
        Book = self.get_model()

        # Get books that have been reviewed and are ready for renaming
        queryset = (
            Book.objects.filter(finalmetadata__is_reviewed=True)
            .select_related("finalmetadata", "scan_folder")
            .order_by("finalmetadata__final_series", "finalmetadata__final_series_number", "finalmetadata__final_title")
        )

        # Apply filters if provided
        request = getattr(self, "request", None)
        if request:
            # Search filter
            search = request.GET.get("search")
            if search:
                queryset = queryset.filter(
                    models.Q(finalmetadata__final_title__icontains=search)
                    | models.Q(finalmetadata__final_author__icontains=search)
                    | models.Q(finalmetadata__final_series__icontains=search)
                )

            # Content type filter (ebook, audiobook, comic)
            content_type = request.GET.get("content_type")
            if content_type:
                queryset = queryset.filter(content_type=content_type)

            # File format filter (epub, pdf, cbz, mp3, etc.)
            file_format = request.GET.get("file_format")
            if file_format:
                queryset = queryset.filter(files__file_format__iexact=file_format).distinct()

            # Language filter
            language = request.GET.get("language")
            if language:
                queryset = queryset.filter(finalmetadata__language__iexact=language)

            # Issue type filter for comic books (legacy support)
            issue_type = request.GET.get("issue_type")
            if issue_type:
                queryset = queryset.filter(metadata__field_name="issue_type", metadata__field_value=issue_type, metadata__is_active=True).distinct()

        return queryset

    def get_context_data(self, **kwargs):
        """Add enhanced context with pattern templates and token reference."""
        context = super().get_context_data(**kwargs)

        # Import here to avoid circular imports
        from books.models import UserProfile
        from books.utils.renaming_engine import PREDEFINED_PATTERNS

        # Add predefined patterns
        context["predefined_patterns"] = PREDEFINED_PATTERNS

        # Add token reference for the UI
        token_reference = self._get_token_reference()
        context["available_tokens"] = token_reference
        context["token_reference"] = token_reference  # Some tests expect this key

        # Add pattern validator for frontend validation
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
                    default_template_key = f"system-{key}"
                    break

        context["default_template_key"] = default_template_key
        context["include_companion_files"] = profile.include_companion_files

        # Process books for enhanced display
        context["books_with_previews"] = self._enhance_books_with_previews(
            context["books"], self.request.GET.get("folder_pattern", ""), self.request.GET.get("filename_pattern", "")
        )

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

    def _enhance_books_with_previews(self, books, folder_pattern, filename_pattern):
        """Enhance books with rename previews if patterns are provided."""
        enhanced_books = []

        # If patterns are provided, use them to generate previews
        if folder_pattern and filename_pattern:
            from pathlib import Path

            from books.utils.file_collision import resolve_collision
            from books.utils.renaming_engine import RenamingEngine

            engine = RenamingEngine()

            for book in books:
                try:
                    target_folder = engine.process_template(folder_pattern, book) if folder_pattern else ""
                    target_filename = engine.process_template(filename_pattern, book)

                    if target_filename:
                        # Build target path
                        if book.file_path:
                            book_base_dir = Path(book.file_path).parent
                            target_path = book_base_dir / target_folder / target_filename

                            # Resolve collision to show actual final path with suffix
                            resolved_path = resolve_collision(str(target_path))

                            # Format for display (relative path)
                            preview_path = f"{target_folder}/{Path(resolved_path).name}" if target_folder else Path(resolved_path).name
                        else:
                            preview_path = f"{target_folder}/{target_filename}" if target_folder else target_filename
                    else:
                        preview_path = None
                except Exception:
                    preview_path = "Error generating preview"

                enhanced_books.append(
                    {
                        "book": book,
                        "current_path": getattr(book, "file_path", ""),
                        "preview": preview_path,
                        "new_path": preview_path,  # Add new_path for test compatibility
                        "warnings": self._generate_warnings(book),
                    }
                )
        else:
            # No patterns provided, generate suggested paths and warnings
            for book in books:
                current_path = getattr(book, "file_path", "")
                new_path = self._generate_suggested_path(book)

                enhanced_books.append({"book": book, "current_path": current_path, "preview": None, "new_path": new_path, "warnings": self._generate_warnings(book)})

        return enhanced_books

    def _generate_suggested_path(self, book):
        """Generate suggested file path for book organization."""
        if not hasattr(book, "finalmetadata") or not book.finalmetadata:
            return "/eBooks Library/Uncategorized/"

        metadata = book.finalmetadata
        # Basic path structure: /eBooks Library/[Format]/[Language]/[Category]/[Author]/[Series]/[Title]
        parts = [
            "eBooks Library",
            getattr(metadata, "final_format", "Unknown Format"),
            getattr(metadata, "final_language", "Unknown Language"),
            getattr(metadata, "final_category", "Books"),
            getattr(metadata, "final_author", "Unknown Author"),
        ]

        # Add series if available
        if getattr(metadata, "final_series", None):
            parts.append(metadata.final_series)

        # Add title as filename
        title = getattr(metadata, "final_title", "Unknown Title")
        filename = f"{title}.{getattr(metadata, 'final_format', 'epub').lower()}"

        return "/" + "/".join(parts) + "/" + filename

    def _generate_warnings(self, book):
        """Generate warnings for problematic books."""
        warnings = []

        if not hasattr(book, "finalmetadata") or not book.finalmetadata:
            warnings.append("No final metadata available")
            return warnings

        metadata = book.finalmetadata

        # Check for missing critical fields
        if not getattr(metadata, "final_title", None):
            warnings.append("Missing title")

        if not getattr(metadata, "final_author", None):
            warnings.append("Missing author")

        if not getattr(metadata, "final_format", None):
            warnings.append("Missing format information")

        # Check for series issues
        series = getattr(metadata, "final_series", None)
        series_number = getattr(metadata, "final_series_number", None)

        if series and not series_number:
            warnings.append("Series specified but no series number")

        if series_number and not series:
            warnings.append("Series number specified but no series name")

        return warnings

    def _get_series_groups(self, books):
        """Group books by series for template display."""
        series_map = {}

        for book in books:
            if hasattr(book, "finalmetadata") and book.finalmetadata:
                series_name = getattr(book.finalmetadata, "final_series", None) or "Standalone Books"
                if series_name not in series_map:
                    series_map[series_name] = {"name": series_name, "count": 0, "numbers": [], "books": []}

                series_map[series_name]["count"] += 1
                series_map[series_name]["books"].append(book)

                # Add series number if available
                series_number = getattr(book.finalmetadata, "final_series_number", None)
                if series_number:
                    series_map[series_name]["numbers"].append(str(series_number))

        return list(series_map.values())

    def _analyze_series_completion(self):
        """Analyze series completion status."""
        Book = self.get_model()

        # Get all series with their books
        series_analysis = {}
        books = Book.objects.filter(finalmetadata__is_reviewed=True).select_related("finalmetadata")

        for book in books:
            if hasattr(book, "finalmetadata") and book.finalmetadata:
                series_name = getattr(book.finalmetadata, "final_series", None)
                if series_name:
                    if series_name not in series_analysis:
                        series_analysis[series_name] = {"name": series_name, "books": [], "numbers": set(), "complete": False}

                    series_analysis[series_name]["books"].append(book)
                    series_number = getattr(book.finalmetadata, "final_series_number", None)
                    if series_number:
                        series_analysis[series_name]["numbers"].add(int(series_number))

        # Determine completeness
        for series_name, data in series_analysis.items():
            if data["numbers"]:
                expected_numbers = set(range(1, max(data["numbers"]) + 1))
                data["complete"] = data["numbers"] == expected_numbers
            else:
                data["complete"] = False

        return {
            "complete_series": [name for name, data in series_analysis.items() if data["complete"]],
            "incomplete_series": [name for name, data in series_analysis.items() if not data["complete"]],
            "series_analysis": series_analysis,
        }

    def _generate_comic_file_path(self, book):
        """Generate comic book file path based on metadata."""
        try:
            # Get metadata
            metadata = {}
            for meta in book.metadata.filter(is_active=True):
                metadata[meta.field_name] = meta.field_value

            series_name = getattr(book.finalmetadata, "final_series", "") or metadata.get("series", "Unknown Series")
            issue_type = metadata.get("issue_type", "main_series")
            original_filename = book.file_path.split("/")[-1] if book.file_path else "unknown.cbz"

            # Generate file prefix based on issue type
            if issue_type == "main_series":
                issue_number = metadata.get("issue_number", "01")
                prefix = f"{series_name} - {int(issue_number):02d}"
            elif issue_type == "annual":
                annual_number = metadata.get("annual_number", "1")
                prefix = f"{series_name} - A{annual_number:0>2}"
            elif issue_type == "special":
                prefix = f"{series_name} - S01"
            elif issue_type == "collection":
                prefix = f"{series_name} - SP01"
            else:
                prefix = f"{series_name} - 01"

            # Build full path: CBR/Nederlands/Stripalbums/SeriesName/SeriesName - Deel 01 - Compleet/filename
            full_path = f"CBR/Nederlands/Stripalbums/{series_name}/{series_name} - Deel 01 - Compleet/{prefix} - {original_filename}"

            return full_path

        except Exception:
            # Fallback to simple path
            return f"CBR/Nederlands/Stripalbums/Unknown/Unknown - 01 - {book.file_path.split('/')[-1] if book.file_path else 'unknown.cbz'}"

    def _get_comic_subfolder(self, issue_type, metadata):
        """Get comic subfolder based on issue type."""
        subfolder_map = {
            "annual": "Annuals",
            "special": "Specials",
            "collection": "Collections",
            "one_shot": "One-Shots",
            "preview": "Previews",
            "alternate_reality": "Alternate Reality",
            "crossover": "Events",
            "main_series": "Unknown",  # Default fallback
        }
        return subfolder_map.get(issue_type, "Unknown")

    def _generate_comic_filename(self, issue_type, metadata, series, book):
        """Generate comic filename based on metadata."""
        title = getattr(book.finalmetadata, "final_title", "Unknown Title")

        if issue_type == "main_series":
            issue_number = metadata.get("issue_number", 1)
            return f"{series} #{issue_number:03d} - {title}"
        elif issue_type == "annual":
            annual_number = metadata.get("annual_number", 1)
            return f"{series} Annual #{annual_number} - {title}"
        elif issue_type == "special":
            return f"{series} Special - {title}"
        elif issue_type == "one_shot":
            return f"{series} One-Shot - {title}"
        else:
            return f"{series} - {title}"

    def _analyze_comic_series_completion(self):
        """Analyze comic series completion for comic books."""
        # Get all comic books (CBZ, CBR formats)
        comic_books = self.get_queryset().filter(files__file_format__in=COMIC_FORMATS, finalmetadata__final_series__isnull=False).exclude(finalmetadata__final_series="")

        series_data = {}

        for book in comic_books:
            series_name = book.finalmetadata.final_series
            if series_name not in series_data:
                series_data[series_name] = {"name": series_name, "main_series_count": 0, "annuals_count": 0, "specials_count": 0, "is_complete": True}  # Default to complete

            # Get issue type from metadata
            issue_type = "main_series"  # Default
            for meta in book.metadata.filter(field_name="issue_type", is_active=True):
                issue_type = meta.field_value
                break

            # Count by type
            if issue_type == "annual":
                series_data[series_name]["annuals_count"] += 1
            elif issue_type in ["special", "one_shot"]:
                series_data[series_name]["specials_count"] += 1
            else:
                series_data[series_name]["main_series_count"] += 1

        return {
            "all_series": list(series_data.values()),
            "complete_series": [s for s in series_data.values() if s["is_complete"]],
            "incomplete_series": [s for s in series_data.values() if not s["is_complete"]],
            "total_series": len(series_data),
            "complete_count": len([s for s in series_data.values() if s["is_complete"]]),
            "incomplete_count": len([s for s in series_data.values() if not s["is_complete"]]),
        }
