"""
Ebook & Series Renamer - Template Engine

JMTE-compatible template processing for flexible file and folder renaming.
Supports dynamic tokens, automatic omission of empty values, and character normalization.
"""

import logging
import re
from pathlib import Path
from typing import List, Optional, Tuple

from django.db import models

from books.models import DataSource
from books.utils.authors import author_file_as, find_author_by_name, normalize_author_name
from books.utils.surname_particles import sort_name, split_author

logger = logging.getLogger(__name__)


def is_renamable(book):
    """Return True when a book is fully approved and may be renamed or moved.

    A book with no ``FinalMetadata`` row, or whose ``is_reviewed`` is False, is
    not renamable. Only fully approved books may be renamed or moved.
    """
    from books.models import FinalMetadata

    if book.pk is None:
        return False
    return FinalMetadata.objects.filter(book=book, is_reviewed=True).exists()


# Windows reserved device names that a folder/file component must never take,
# because the filesystem (and SMB clients) will not store them verbatim. The
# comparison is case-insensitive and also matches a name followed by a period
# and an extension (e.g. "con.txt").
RESERVED_DEVICE_NAMES = frozenset(
    ["con", "prn", "aux", "nul"]
    + ["com%d" % i for i in range(1, 10)]
    + ["lpt%d" % i for i in range(1, 10)]
)


def _is_reserved_device(name: str) -> bool:
    """Return True when ``name`` is a Windows reserved device name."""
    base = name.lower()
    if "." in base:
        base = base.split(".", 1)[0]
    return base in RESERVED_DEVICE_NAMES


def _split_stem_ext(name: str) -> Tuple[str, str]:
    """Split a file name into (stem, extension); a trailing dot is not an extension."""
    dot = name.rfind(".")
    if 0 < dot < len(name) - 1:
        return name[:dot], name[dot:]
    return name, ""


class RenamingEngine:
    """
    Core template engine for ebook renaming with JMTE-style token processing.
    """

    # Character normalization rules
    INVALID_CHARS = r'[<>:"/\\|?*&]'
    REPLACEMENT_CHAR = "_"

    def __init__(self):
        self.token_registry = {}
        self._author_sort_cache = {}
        self._reviewed_author_cache = {}
        self._register_default_tokens()

    def _register_default_tokens(self):
        """Register built-in token processors."""
        self.token_registry.update(
            {
                "title": self._get_title,
                "book.title": self._get_title,
                "originalTitle": self._get_original_title,
                "titleSortable": self._get_title_sortable,
                "originalFilename": self._get_original_filename,
                "publicationyear": self._get_publication_year,
                "year": self._get_publication_year,  # Common alias
                "decadeLong": self._get_decade_long,
                "decadeShort": self._get_decade_short,
                "bookseries.title": self._get_series_title,
                "series_name": self._get_series_title,  # Common alias
                "bookseries.number": self._get_series_number_padded,
                "series_number": self._get_series_number,  # Common alias
                "series_number_padded": self._get_series_number_padded,  # Two-digit format
                "bookseries.titleSortable": self._get_series_title_sortable,
                "author.lastname": self._get_author_lastname,
                "author.firstname": self._get_author_firstname,
                "author.fullname": self._get_author_fullname,
                "author.sortname": self._get_author_sortname,
                "author_sort": self._get_author_sortname,  # Common alias
                "language": self._get_language,
                "language_name": self._get_language_name,
                "format": self._get_format,
                "category": self._get_category,
                "genre": self._get_genre,
                "publisher": self._get_publisher,
                "ext": self._get_extension,
            }
        )

    def process_template(self, template: str, book: models.Model, companion_file: Optional[str] = None, filename: bool = False) -> str:
        """
        Process a template string with book metadata tokens.

        Args:
            template: Template string with ${token} placeholders
            book: Book model instance
            companion_file: Optional companion file extension override
            filename: True when the template resolves to a file name (the last
                component is then a file, not a folder); default False

        Returns:
            Processed template with tokens replaced by actual values
        """
        if not template:
            return ""

        # Store context for token processors
        self.current_book = book
        self.current_companion = companion_file

        # Find all tokens in the template
        token_pattern = r"\$\{([^}]+)\}"
        tokens = re.findall(token_pattern, template)

        processed = template

        for token in tokens:
            value = self._resolve_token(token)

            # Replace token with resolved value
            token_placeholder = "${" + token + "}"

            if value:
                # A slash or backslash that arrived inside a token value must
                # not be treated as a path separator later in _normalize_path,
                # so it is replaced up front (pattern separators stay literal).
                value_str = (
                    str(value)
                    .replace("/", self.REPLACEMENT_CHAR)
                    .replace("\\", self.REPLACEMENT_CHAR)
                )
                processed = processed.replace(token_placeholder, value_str)
            else:
                # Handle empty token omission
                processed = self._omit_empty_token(processed, token_placeholder)

        # Clean up the final result
        processed = self._normalize_path(processed, filename=filename)

        return processed

    def _resolve_token(self, token: str) -> Optional[str]:
        """
        Resolve a single token to its value.

        Args:
            token: Token name (without ${})

        Returns:
            Token value or None if empty/not found
        """
        # Handle array/substring access like title[0] or title[0,2]
        if "[" in token and "]" in token:
            return self._resolve_array_token(token)

        # Handle modifier functions like title;first
        if ";" in token:
            return self._resolve_modified_token(token)

        # Standard token lookup
        processor = self.token_registry.get(token)
        if processor:
            try:
                value = processor()
                return value if value else None
            except Exception as e:
                logger.warning(f"Error processing token '{token}': {e}")
                return None

        logger.warning(f"Unknown token: '{token}'")
        return None

    def _resolve_array_token(self, token: str) -> Optional[str]:
        """Handle array-style token access like title[0] or title[0,2]."""
        base_token = token.split("[")[0]
        array_part = token.split("[")[1].rstrip("]")

        # Get base value
        processor = self.token_registry.get(base_token)
        if not processor:
            return None

        try:
            base_value = processor()
            if not base_value:
                return None

            # Parse array access
            if "," in array_part:
                # Substring like [0,2]
                start, end = map(int, array_part.split(","))
                return base_value[start:end] if len(base_value) > start else None
            else:
                # Single character like [0]
                index = int(array_part)
                return base_value[index] if len(base_value) > index else None

        except (ValueError, IndexError, TypeError):
            return None

    def _resolve_modified_token(self, token: str) -> Optional[str]:
        """Handle modified tokens like title;first."""
        base_token, modifier = token.split(";", 1)

        processor = self.token_registry.get(base_token)
        if not processor:
            return None

        try:
            base_value = processor()
            if not base_value:
                return None

            if modifier == "first":
                # Return first letter or # for numbers
                first_char = base_value[0].upper()
                return first_char if first_char.isalpha() else "#"

        except (IndexError, TypeError):
            return None

    def _omit_empty_token(self, text: str, token_placeholder: str) -> str:
        """
        Remove empty tokens and clean up surrounding separators.

        This implements the automatic omission behavior where empty tokens
        don't leave behind separators or empty folder levels.
        """
        # Remove the token placeholder
        text = text.replace(token_placeholder, "")

        # Clean up common patterns left by empty tokens
        patterns_to_clean = [
            r"/+",  # Multiple slashes -> single slash
            r"\\+",  # Multiple backslashes -> single backslash
            r"\s*-\s*-\s*",  # Double dashes with spaces
            r"\s*-\s*$",  # Trailing dash
            r"\s*/\s*/",  # Spaces around double slashes
            r"^\s*/+",  # Leading slashes
            r"/+\s*$",  # Trailing slashes
            r"\s*\(\s*\)",  # Empty parentheses with spaces
            r"\s*#\s*-",  # Hash followed by dash (series number omission)
            r"\s+",  # Multiple spaces -> single space (do this before leading dash cleanup)
            r"^\s*-\s*",  # Leading dash with spaces
        ]

        for pattern in patterns_to_clean:
            if pattern == r"\s+":
                text = re.sub(pattern, " ", text)
            elif pattern == r"/+":
                text = re.sub(pattern, "/", text)
            elif pattern == r"\\+":
                text = re.sub(pattern, "\\\\", text)  # Escape backslash for replacement
            elif pattern == r"\s*#\s*-":
                text = re.sub(pattern, " -", text)  # Replace hash-dash with just dash
            else:
                text = re.sub(pattern, "", text)

        return text.strip()

    def _sanitize_component(self, part: str, filename: bool = False) -> str:
        """Sanitise one path component (a folder name or a file name).

        Invalid filesystem characters are replaced and runs of whitespace are
        collapsed first (unchanged behaviour). A folder component then has its
        leading spaces and trailing periods/spaces stripped, and a file name has
        trailing spaces stripped from its stem (the extension is left alone).
        Either way, a component that becomes empty is replaced by an underscore
        and a Windows reserved device name is prefixed with an underscore.
        """
        part = re.sub(r'[<>:"|?*!]', self.REPLACEMENT_CHAR, part)
        part = re.sub(r"\s+", " ", part)
        if filename:
            stem, ext = _split_stem_ext(part)
            stem = stem.strip(" ")
            if not stem:
                stem = "_"
            if _is_reserved_device(stem):
                stem = "_" + stem
            return stem + ext
        name = part.lstrip(" ").rstrip(" .")
        if not name:
            name = "_"
        if _is_reserved_device(name):
            name = "_" + name
        return name

    def _normalize_path(self, path: str, filename: bool = False) -> str:
        """
        Normalize path for filesystem compatibility.

        - Replace invalid characters with underscores
        - Collapse multiple spaces
        - Strip trailing periods/spaces and leading spaces from folder components
        - Prefix Windows reserved device names, replace empty components
        - Strip trailing spaces from a file name stem, leaving its extension
        - Preserve path separators
        """
        if not path:
            return ""

        # Split on path separators to normalize each component separately
        parts = []

        # Handle both forward and back slashes
        for part in re.split(r"[/\\]", path):
            if part.strip():  # Skip empty parts
                normalized_part = self._sanitize_component(part, filename=filename)
                if normalized_part:
                    parts.append(normalized_part)

        # Rejoin with forward slashes (standard path separator)
        normalized = "/".join(parts)

        # Clean up path separators
        normalized = re.sub(r"[/\\]+", "/", normalized)

        # Remove leading/trailing separators and spaces
        normalized = normalized.strip("/ \\")

        return normalized

    # Token processor methods
    def _get_title(self) -> Optional[str]:
        """Get book title."""
        # Try FinalMetadata first
        if hasattr(self.current_book, "finalmetadata") and self.current_book.finalmetadata:
            title = self.current_book.finalmetadata.final_title
            if title:
                return title

        # Fallback to direct book attribute
        title = getattr(self.current_book, "title", None)
        if title:
            return title

        # Final fallback - try to extract from file name if available
        if hasattr(self.current_book, "bookfile") and self.current_book.bookfile:
            file_name = self.current_book.bookfile.file_name
            if file_name:
                # Remove extension and return as title
                import os

                return os.path.splitext(file_name)[0]

        return None

    def _get_original_title(self) -> Optional[str]:
        """Get original title (if different from current title)."""
        # For now, return same as title - could be enhanced with original language title
        return self._get_title()

    @staticmethod
    def _sort_title(title):
        """Move a leading article to the end for sorting (The Matrix -> Matrix, The)."""
        if not title:
            return None
        for article in ("The ", "A ", "An "):
            if title.startswith(article):
                return f"{title[len(article):].strip()}, {article.strip()}"
        return title

    def _get_title_sortable(self) -> Optional[str]:
        """Get title formatted for sorting (The Matrix -> Matrix, The)."""
        return self._sort_title(self._get_title())

    def _get_original_filename(self) -> Optional[str]:
        """Get original filename without extension."""
        file_path = getattr(self.current_book, "file_path", "")
        if file_path:
            return Path(file_path).stem
        return None

    def _get_publication_year(self) -> Optional[str]:
        """Get publication year."""
        if hasattr(self.current_book, "finalmetadata") and self.current_book.finalmetadata:
            pub_year = self.current_book.finalmetadata.publication_year
            if pub_year:
                return str(pub_year)
        # Fallback to direct field
        pub_year = getattr(self.current_book, "publication_year", None)
        return str(pub_year) if pub_year else None

    def _get_decade_long(self) -> Optional[str]:
        """Get decade in long format (2020-2029)."""
        year_str = self._get_publication_year()
        if year_str:
            year = int(year_str)
            decade_start = (year // 10) * 10
            return f"{decade_start}–{decade_start + 9}"
        return None

    def _get_decade_short(self) -> Optional[str]:
        """Get decade in short format (2020s)."""
        year_str = self._get_publication_year()
        if year_str:
            year = int(year_str)
            decade_start = (year // 10) * 10
            return f"{decade_start}s"
        return None

    def _get_series_title(self) -> Optional[str]:
        """Get series title."""
        if hasattr(self.current_book, "finalmetadata") and self.current_book.finalmetadata:
            return self.current_book.finalmetadata.final_series
        # Fallback to direct field
        return getattr(self.current_book, "series_name", None)

    def _get_series_number_value(self) -> Optional[int]:
        """Return the raw series number as an integer, or None."""
        if hasattr(self.current_book, "finalmetadata") and self.current_book.finalmetadata:
            series_num = self.current_book.finalmetadata.final_series_number
            if series_num:
                return int(series_num)
        series_num = getattr(self.current_book, "series_number", None)
        if series_num:
            return int(series_num)
        return None

    def _get_series_number(self) -> Optional[str]:
        """Get series number as a simple integer."""
        value = self._get_series_number_value()
        return str(value) if value is not None else None

    def _get_series_number_padded(self) -> Optional[str]:
        """Get series number with zero padding (01, 02, etc.)."""
        value = self._get_series_number_value()
        return f"{value:02d}" if value is not None else None

    def _get_series_title_sortable(self) -> Optional[str]:
        """Get series title formatted for sorting."""
        return self._sort_title(self._get_series_title())

    def _get_author_lastname(self) -> Optional[str]:
        """Get author last name."""
        author = self._get_author_fullname()
        if not author:
            return None
        _, last = split_author(author)
        return last or None

    def _get_author_firstname(self) -> Optional[str]:
        """Get author first name."""
        author = self._get_author_fullname()
        if not author:
            return None
        first, _ = split_author(author)
        return first or None

    def _get_author_fullname(self) -> Optional[str]:
        """Get full author name."""
        # Try FinalMetadata first
        if hasattr(self.current_book, "finalmetadata") and self.current_book.finalmetadata:
            author = self.current_book.finalmetadata.final_author
            if author:
                return author

        # Fallback to direct book attribute
        if hasattr(self.current_book, "author"):
            author = getattr(self.current_book, "author", None)
            if author:
                return author

        # No fallback - return None so the token gets omitted
        return None

    _AUTHOR_SOURCE_PRIORITY = [
        DataSource.OPF_FILE,
        DataSource.EPUB_INTERNAL,
        DataSource.OPEN_LIBRARY,
        DataSource.GOOGLE_BOOKS,
    ]

    def _stored_author_sort_form(self, final_author: str) -> Optional[str]:
        """Return a stored comma-form author name from an official source whose
        words equal the final author's words (case-insensitive), or None.

        Official sources are tried in priority order and ``Initial Scan`` is
        never considered.  The result is cached per engine instance keyed by
        book id and final author, so two ``process_template`` calls for the
        same book run the BookAuthor query once.
        """
        rows = getattr(self.current_book, "author_relationships", None)
        if rows is None:
            return None

        key = (self.current_book.pk, final_author)
        if key in self._author_sort_cache:
            return self._author_sort_cache[key]

        rows = rows.select_related("author", "source").filter(
            source__name__in=self._AUTHOR_SOURCE_PRIORITY
        )
        order = {name: i for i, name in enumerate(self._AUTHOR_SOURCE_PRIORITY)}
        rows = sorted(rows, key=lambda r: order.get(r.source.name, len(order)))
        target_words = sorted(w.lower() for w in re.split(r"[ ,]+", final_author) if w)
        result = None
        for row in rows:
            name = row.author.name
            if "," in name:
                words = sorted(w.lower() for w in re.split(r"[ ,]+", name) if w)
                if words == target_words:
                    result = name
                    break
        self._author_sort_cache[key] = result
        return result

    def _reviewed_author_sort_form(self, final_author: str) -> Optional[str]:
        """Return the reviewed sort form for a final author, or None.

        Looks up the ``Author`` whose ``name_normalized`` equals the normalized
        final author and which is reviewed (``is_reviewed`` True, non-empty
        ``last_name``), and returns ``"last_name, first_name"`` (just the last
        name when ``first_name`` is empty), copied exactly as stored.

        The result is cached per engine instance keyed by the normalized name,
        so each distinct final author runs at most one indexed query per engine
        instance.
        """
        if getattr(self.current_book, "author_relationships", None) is None:
            return None
        normalized = normalize_author_name(final_author)
        if not normalized:
            return None
        if normalized in self._reviewed_author_cache:
            return self._reviewed_author_cache[normalized]

        result = None
        author = find_author_by_name(final_author)
        if author is not None and author.is_reviewed and author.last_name:
            result = author_file_as(final_author)
        self._reviewed_author_cache[normalized] = result
        return result

    def _get_author_sortname(self) -> Optional[str]:
        """Get author name in sortable format (Last, First)."""
        # First try to get from FinalMetadata final_author_sort if available
        if hasattr(self.current_book, "finalmetadata") and self.current_book.finalmetadata:
            if hasattr(self.current_book.finalmetadata, "final_author_sort") and self.current_book.finalmetadata.final_author_sort:
                return self.current_book.finalmetadata.final_author_sort

        author = self._get_author_fullname()
        if not author:
            return None

        # A reviewed author's stored order wins over the stored comma form and
        # the splitter.
        reviewed = self._reviewed_author_sort_form(author)
        if reviewed:
            return reviewed

        # Only names without a comma consult the stored official-source rows.
        if "," not in author:
            stored = self._stored_author_sort_form(author)
            if stored:
                return stored

        return sort_name(author)

    def _get_language(self) -> Optional[str]:
        """Get book language."""
        if hasattr(self.current_book, "finalmetadata") and self.current_book.finalmetadata:
            return self.current_book.finalmetadata.language
        # Fallback to direct field
        return getattr(self.current_book, "language", None)

    def _get_language_name(self) -> str:
        """Get the English display name for the book's language code.

        Resolves the stored language code to its English name via the
        ``LANGUAGE_NAMES`` table, case-insensitively and ignoring a region
        subtag (``en-US`` -> ``English``). An empty value, ``und``, or any
        unmapped code resolves to ``Unknown Language``.
        """
        from books.utils.language_names import LANGUAGE_NAMES

        code = self._get_language()
        if not code:
            return "Unknown Language"
        base = code.strip().lower().split("-")[0].split("_")[0]
        if not base or base == "und":
            return "Unknown Language"
        return LANGUAGE_NAMES.get(base, "Unknown Language")

    def _get_format(self) -> Optional[str]:
        """Get file format."""
        file_format = getattr(self.current_book, "file_format", "")
        return file_format.upper() if file_format else None

    def _get_category(self) -> Optional[str]:
        """Get book category."""
        if hasattr(self.current_book, "finalmetadata") and self.current_book.finalmetadata:
            # Try to determine category from genre
            genre = self._get_genre()
            if genre:
                # Simple category mapping based on genre
                fiction_keywords = ["fiction", "novel", "fantasy", "science fiction", "mystery", "romance", "thriller"]
                if any(keyword in genre.lower() for keyword in fiction_keywords):
                    return "Fiction"
                else:
                    return "Non-Fiction"
        # Fallback to direct field
        return getattr(self.current_book, "category", None)

    def _get_genre(self) -> Optional[str]:
        """Get book genre."""
        if hasattr(self.current_book, "genre_relationships") and self.current_book.genre_relationships.exists():
            # Get the first active genre with highest confidence
            genre_relation = self.current_book.genre_relationships.filter(is_active=True).order_by("-confidence").first()
            if genre_relation and genre_relation.genre:
                return genre_relation.genre.name
        return None

    def _get_publisher(self) -> Optional[str]:
        """Get book publisher."""
        if hasattr(self.current_book, "publisher_relationships") and self.current_book.publisher_relationships.exists():
            # Get the first active publisher with highest confidence
            publisher_relation = self.current_book.publisher_relationships.filter(is_active=True).order_by("-confidence").first()
            if publisher_relation and publisher_relation.publisher:
                return publisher_relation.publisher.name
        # Fallback to direct field
        return getattr(self.current_book, "publisher", None)

    def _get_extension(self) -> Optional[str]:
        """Get file extension."""
        if self.current_companion:
            # For companion files, use their extension
            return self.current_companion.lstrip(".")

        file_path = getattr(self.current_book, "file_path", "")
        if file_path:
            return Path(file_path).suffix.lstrip(".")

        # Fallback to file_format
        file_format = getattr(self.current_book, "file_format", "")
        return file_format.lower() if file_format else "epub"


class RenamingPatternValidator:
    """
    Validates renaming patterns and checks for common issues.
    """

    def __init__(self):
        self.engine = RenamingEngine()

    def validate_pattern(self, pattern: str) -> Tuple[bool, List[str]]:
        """
        Validate a renaming pattern.

        Args:
            pattern: Template pattern to validate

        Returns:
            Tuple of (is_valid, list_of_warnings)
        """
        warnings = []

        if not pattern.strip():
            return False, ["Pattern cannot be empty"]

        # Check for malformed token syntax
        if "${" in pattern or "}" in pattern:
            # Check for unmatched braces
            open_count = pattern.count("${")
            close_count = pattern.count("}")
            if open_count != close_count:
                return False, ["Malformed token syntax - unmatched braces"]

        # Check for invalid tokens
        token_pattern = r"\$\{([^}]+)\}"
        tokens = re.findall(token_pattern, pattern)

        for token in tokens:
            if not self._is_valid_token(token):
                warnings.append(f"Unknown token: ${{{token}}}")

        # Check for path length concerns
        if len(pattern) > 200:
            warnings.append("Pattern may generate very long paths")

        # Check for missing essential elements
        has_title = any("title" in token for token in tokens)
        has_author = any("author" in token for token in tokens)
        has_extension = any(token == "ext" for token in tokens)

        if not has_title and not has_author:
            warnings.append("Pattern should include author or title for file identification")

        if not has_extension:
            warnings.append("Pattern should include file extension token (${ext})")

        is_valid = len([w for w in warnings if "Unknown token" in w]) == 0

        return is_valid, warnings

    def _is_valid_token(self, token: str) -> bool:
        """Check if a token is valid."""
        # Handle array access
        if "[" in token:
            base_token = token.split("[")[0]
            return base_token in self.engine.token_registry

        # Handle modifiers
        if ";" in token:
            base_token = token.split(";")[0]
            return base_token in self.engine.token_registry

        return token in self.engine.token_registry

    def preview_pattern(self, pattern: str, book: models.Model) -> str:
        """
        Generate a preview of what the pattern will produce.

        Args:
            pattern: Template pattern
            book: Book instance to use for preview

        Returns:
            Preview string showing the generated path
        """
        try:
            return self.engine.process_template(pattern, book)
        except Exception as e:
            return f"Error: {str(e)}"


# Predefined pattern templates for common use cases
PREDEFINED_PATTERNS = {
    "language_separated": {
        "name": "Language-Separated Library",
        "folder": "${language}/${author.sortname}",
        "filename": "${title}.${ext}",
        "description": "Organizes by language, then author",
    },
    "category_author": {
        "name": "Category and Author",
        "folder": "${category}/${author.sortname}",
        "filename": "${title}.${ext}",
        "description": "Organizes by category (Fiction/Non-Fiction), then author",
    },
    "series_aware": {
        "name": "Series-Aware Organization",
        "folder": "${category}/${author.sortname}/${bookseries.title}",
        "filename": "${bookseries.title} #${bookseries.number} - ${title}.${ext}",
        "description": "Groups series books together with numbered filenames",
    },
    "simple_author_title": {
        "name": "Simple Author-Title",
        "folder": "${author.sortname}",
        "filename": "${author.sortname} - ${title}.${ext}",
        "description": "Simple organization by author with readable filenames",
    },
    "comprehensive": {
        "name": "Comprehensive Library",
        "folder": "${format}/${language}/${category}/${author.sortname}/${bookseries.title}",
        "filename": "${author.sortname} - ${bookseries.title} #${bookseries.number} - ${title}.${ext}",
        "description": "Full metadata-driven organization",
    },
}
