"""
Ebook & Series Renamer - Template Engine

JMTE-compatible template processing for flexible file and folder renaming.
Supports dynamic tokens, automatic omission of empty values, and character normalization.
"""
import re
import logging
from typing import Optional, List, Tuple
from pathlib import Path
from django.db import models


logger = logging.getLogger(__name__)


class RenamingEngine:
    """
    Core template engine for ebook renaming with JMTE-style token processing.
    """

    # Character normalization rules
    INVALID_CHARS = r'[<>:"/\\|?*&]'
    REPLACEMENT_CHAR = '_'

    def __init__(self):
        self.token_registry = {}
        self._register_default_tokens()

    def _register_default_tokens(self):
        """Register built-in token processors."""
        self.token_registry.update({
            'title': self._get_title,
            'book.title': self._get_title,
            'originalTitle': self._get_original_title,
            'titleSortable': self._get_title_sortable,
            'originalFilename': self._get_original_filename,
            'publicationyear': self._get_publication_year,
            'decadeLong': self._get_decade_long,
            'decadeShort': self._get_decade_short,
            'bookseries.title': self._get_series_title,
            'bookseries.number': self._get_series_number,
            'bookseries.titleSortable': self._get_series_title_sortable,
            'author.lastname': self._get_author_lastname,
            'author.firstname': self._get_author_firstname,
            'author.fullname': self._get_author_fullname,
            'author.sortname': self._get_author_sortname,
            'language': self._get_language,
            'format': self._get_format,
            'category': self._get_category,
            'genre': self._get_genre,
            'ext': self._get_extension,
        })

    def process_template(self, template: str, book: models.Model,
                         companion_file: Optional[str] = None) -> str:
        """
        Process a template string with book metadata tokens.

        Args:
            template: Template string with ${token} placeholders
            book: Book model instance
            companion_file: Optional companion file extension override

        Returns:
            Processed template with tokens replaced by actual values
        """
        if not template:
            return ""

        # Store context for token processors
        self.current_book = book
        self.current_companion = companion_file

        # Find all tokens in the template
        token_pattern = r'\$\{([^}]+)\}'
        tokens = re.findall(token_pattern, template)

        processed = template

        for token in tokens:
            value = self._resolve_token(token)

            # Replace token with resolved value
            token_placeholder = '${' + token + '}'

            if value:
                processed = processed.replace(token_placeholder, str(value))
            else:
                # Handle empty token omission
                processed = self._omit_empty_token(processed, token_placeholder)

        # Clean up the final result
        processed = self._normalize_path(processed)

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
        if '[' in token and ']' in token:
            return self._resolve_array_token(token)

        # Handle modifier functions like title;first
        if ';' in token:
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
        base_token = token.split('[')[0]
        array_part = token.split('[')[1].rstrip(']')

        # Get base value
        processor = self.token_registry.get(base_token)
        if not processor:
            return None

        try:
            base_value = processor()
            if not base_value:
                return None

            # Parse array access
            if ',' in array_part:
                # Substring like [0,2]
                start, end = map(int, array_part.split(','))
                return base_value[start:end] if len(base_value) > start else None
            else:
                # Single character like [0]
                index = int(array_part)
                return base_value[index] if len(base_value) > index else None

        except (ValueError, IndexError, TypeError):
            return None

    def _resolve_modified_token(self, token: str) -> Optional[str]:
        """Handle modified tokens like title;first."""
        base_token, modifier = token.split(';', 1)

        processor = self.token_registry.get(base_token)
        if not processor:
            return None

        try:
            base_value = processor()
            if not base_value:
                return None

            if modifier == 'first':
                # Return first letter or # for numbers
                first_char = base_value[0].upper()
                return first_char if first_char.isalpha() else '#'

        except (IndexError, TypeError):
            return None

    def _omit_empty_token(self, text: str, token_placeholder: str) -> str:
        """
        Remove empty tokens and clean up surrounding separators.

        This implements the automatic omission behavior where empty tokens
        don't leave behind separators or empty folder levels.
        """
        # Remove the token placeholder
        text = text.replace(token_placeholder, '')

        # Clean up common patterns left by empty tokens
        patterns_to_clean = [
            r'/+',  # Multiple slashes -> single slash
            r'\\+',  # Multiple backslashes -> single backslash
            r'\s*-\s*-\s*',  # Double dashes with spaces
            r'\s*-\s*$',  # Trailing dash
            r'\s*/\s*/',  # Spaces around double slashes
            r'^\s*/+',  # Leading slashes
            r'/+\s*$',  # Trailing slashes
            r'\s*\(\s*\)',  # Empty parentheses with spaces
            r'\s*#\s*-',  # Hash followed by dash (series number omission)
            r'\s+',  # Multiple spaces -> single space (do this before leading dash cleanup)
            r'^\s*-\s*',  # Leading dash with spaces
        ]

        for pattern in patterns_to_clean:
            if pattern == r'\s+':
                text = re.sub(pattern, ' ', text)
            elif pattern == r'/+':
                text = re.sub(pattern, '/', text)
            elif pattern == r'\\+':
                text = re.sub(pattern, '\\\\', text)  # Escape backslash for replacement
            elif pattern == r'\s*#\s*-':
                text = re.sub(pattern, ' -', text)  # Replace hash-dash with just dash
            else:
                text = re.sub(pattern, '', text)

        return text.strip()

    def _normalize_path(self, path: str) -> str:
        """
        Normalize path for filesystem compatibility.

        - Replace invalid characters with underscores
        - Collapse multiple spaces
        - Handle portable naming requirements
        - Preserve path separators
        """
        if not path:
            return ""

        # Split on path separators to normalize each component separately
        parts = []

        # Handle both forward and back slashes
        for part in re.split(r'[/\\]', path):
            if part.strip():  # Skip empty parts
                # Replace invalid filesystem characters except path separators
                normalized_part = re.sub(r'[<>:"|?*&]', self.REPLACEMENT_CHAR, part)
                # Collapse multiple spaces
                normalized_part = re.sub(r'\s+', ' ', normalized_part)
                normalized_part = normalized_part.strip()
                if normalized_part:
                    parts.append(normalized_part)

        # Rejoin with forward slashes (standard path separator)
        normalized = '/'.join(parts)

        # Clean up path separators
        normalized = re.sub(r'[/\\]+', '/', normalized)

        # Remove leading/trailing separators and spaces
        normalized = normalized.strip('/ \\')

        return normalized

    # Token processor methods
    def _get_title(self) -> Optional[str]:
        """Get book title."""
        if hasattr(self.current_book, 'finalmetadata') and self.current_book.finalmetadata:
            return self.current_book.finalmetadata.final_title
        return getattr(self.current_book, 'title', None)

    def _get_original_title(self) -> Optional[str]:
        """Get original title (if different from current title)."""
        # For now, return same as title - could be enhanced with original language title
        return self._get_title()

    def _get_title_sortable(self) -> Optional[str]:
        """Get title formatted for sorting (The Matrix -> Matrix, The)."""
        title = self._get_title()
        if not title:
            return None

        # Move articles to the end
        articles = ['The ', 'A ', 'An ']
        for article in articles:
            if title.startswith(article):
                return f"{title[len(article):].strip()}, {article.strip()}"

        return title

    def _get_original_filename(self) -> Optional[str]:
        """Get original filename without extension."""
        file_path = getattr(self.current_book, 'file_path', '')
        if file_path:
            return Path(file_path).stem
        return None

    def _get_publication_year(self) -> Optional[str]:
        """Get publication year."""
        if hasattr(self.current_book, 'finalmetadata') and self.current_book.finalmetadata:
            pub_year = self.current_book.finalmetadata.publication_year
            if pub_year:
                return str(pub_year)
        # Fallback to direct field
        pub_year = getattr(self.current_book, 'publication_year', None)
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
        if hasattr(self.current_book, 'finalmetadata') and self.current_book.finalmetadata:
            return self.current_book.finalmetadata.final_series
        # Fallback to direct field
        return getattr(self.current_book, 'series_name', None)

    def _get_series_number(self) -> Optional[str]:
        """Get series number."""
        if hasattr(self.current_book, 'finalmetadata') and self.current_book.finalmetadata:
            series_num = self.current_book.finalmetadata.final_series_number
            if series_num:
                return f"{int(series_num):02d}"  # Format as 01, 02, etc.
        # Fallback to direct book field
        series_num = getattr(self.current_book, 'series_number', None)
        if series_num:
            return f"{int(series_num):02d}"  # Format as 01, 02, etc.
        return None

    def _get_series_title_sortable(self) -> Optional[str]:
        """Get series title formatted for sorting."""
        series_title = self._get_series_title()
        if not series_title:
            return None

        # Same logic as title sortable
        articles = ['The ', 'A ', 'An ']
        for article in articles:
            if series_title.startswith(article):
                return f"{series_title[len(article):].strip()}, {article.strip()}"

        return series_title

    def _get_author_lastname(self) -> Optional[str]:
        """Get author last name."""
        author = self._get_author_fullname()
        if author and ',' in author:
            # Already in "Last, First" format
            return author.split(',')[0].strip()
        elif author and ' ' in author:
            # "First Last" format
            return author.split()[-1]
        return author

    def _get_author_firstname(self) -> Optional[str]:
        """Get author first name."""
        author = self._get_author_fullname()
        if author and ',' in author:
            # "Last, First" format
            parts = author.split(',')
            return parts[1].strip() if len(parts) > 1 else None
        elif author and ' ' in author:
            # "First Last" format - return all but last part
            parts = author.split()
            return ' '.join(parts[:-1]) if len(parts) > 1 else None
        return None

    def _get_author_fullname(self) -> Optional[str]:
        """Get full author name."""
        if hasattr(self.current_book, 'finalmetadata') and self.current_book.finalmetadata:
            return self.current_book.finalmetadata.final_author
        return getattr(self.current_book, 'author', None)

    def _get_author_sortname(self) -> Optional[str]:
        """Get author name in sortable format (Last, First)."""
        author = self._get_author_fullname()
        if not author:
            return None

        if ',' in author:
            # Already in correct format
            return author
        elif ' ' in author:
            # Convert "First Last" to "Last, First"
            parts = author.split()
            last_name = parts[-1]
            first_names = ' '.join(parts[:-1])
            return f"{last_name}, {first_names}"

        return author

    def _get_language(self) -> Optional[str]:
        """Get book language."""
        if hasattr(self.current_book, 'finalmetadata') and self.current_book.finalmetadata:
            return self.current_book.finalmetadata.language
        # Fallback to direct field
        return getattr(self.current_book, 'language', None)

    def _get_format(self) -> Optional[str]:
        """Get file format."""
        file_format = getattr(self.current_book, 'file_format', '')
        return file_format.upper() if file_format else None

    def _get_category(self) -> Optional[str]:
        """Get book category."""
        if hasattr(self.current_book, 'finalmetadata') and self.current_book.finalmetadata:
            # Try to determine category from genre
            genre = self._get_genre()
            if genre:
                # Simple category mapping based on genre
                fiction_keywords = ['fiction', 'novel', 'fantasy', 'science fiction', 'mystery', 'romance', 'thriller']
                if any(keyword in genre.lower() for keyword in fiction_keywords):
                    return "Fiction"
                else:
                    return "Non-Fiction"
        # Fallback to direct field
        return getattr(self.current_book, 'category', None)

    def _get_genre(self) -> Optional[str]:
        """Get book genre."""
        if hasattr(self.current_book, 'genre_relationships') and self.current_book.genre_relationships.exists():
            # Get the first active genre with highest confidence
            genre_relation = self.current_book.genre_relationships.filter(is_active=True).order_by('-confidence').first()
            if genre_relation and genre_relation.genre:
                return genre_relation.genre.name
        return None

    def _get_extension(self) -> Optional[str]:
        """Get file extension."""
        if self.current_companion:
            # For companion files, use their extension
            return self.current_companion.lstrip('.')

        file_path = getattr(self.current_book, 'file_path', '')
        if file_path:
            return Path(file_path).suffix.lstrip('.')

        # Fallback to file_format
        file_format = getattr(self.current_book, 'file_format', '')
        return file_format.lower() if file_format else 'epub'


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
        if '${' in pattern or '}' in pattern:
            # Check for unmatched braces
            open_count = pattern.count('${')
            close_count = pattern.count('}')
            if open_count != close_count:
                return False, ["Malformed token syntax - unmatched braces"]

        # Check for invalid tokens
        token_pattern = r'\$\{([^}]+)\}'
        tokens = re.findall(token_pattern, pattern)

        for token in tokens:
            if not self._is_valid_token(token):
                warnings.append(f"Unknown token: ${{{token}}}")

        # Check for path length concerns
        if len(pattern) > 200:
            warnings.append("Pattern may generate very long paths")

        # Check for missing essential elements
        has_title = any('title' in token for token in tokens)
        has_author = any('author' in token for token in tokens)
        has_extension = any(token == 'ext' for token in tokens)

        if not has_title and not has_author:
            warnings.append("Pattern should include author or title for file identification")

        if not has_extension:
            warnings.append("Pattern should include file extension token (${ext})")

        is_valid = len([w for w in warnings if "Unknown token" in w]) == 0

        return is_valid, warnings

    def _is_valid_token(self, token: str) -> bool:
        """Check if a token is valid."""
        # Handle array access
        if '[' in token:
            base_token = token.split('[')[0]
            return base_token in self.engine.token_registry

        # Handle modifiers
        if ';' in token:
            base_token = token.split(';')[0]
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
    'language_separated': {
        'name': 'Language-Separated Library',
        'folder': '${language}/${author.sortname}',
        'filename': '${title}.${ext}',
        'description': 'Organizes by language, then author'
    },
    'category_author': {
        'name': 'Category and Author',
        'folder': '${category}/${author.sortname}',
        'filename': '${title}.${ext}',
        'description': 'Organizes by category (Fiction/Non-Fiction), then author'
    },
    'series_aware': {
        'name': 'Series-Aware Organization',
        'folder': '${category}/${author.sortname}/${bookseries.title}',
        'filename': '${bookseries.title} #${bookseries.number} - ${title}.${ext}',
        'description': 'Groups series books together with numbered filenames'
    },
    'simple_author_title': {
        'name': 'Simple Author-Title',
        'folder': '${author.sortname}',
        'filename': '${author.sortname} - ${title}.${ext}',
        'description': 'Simple organization by author with readable filenames'
    },
    'comprehensive': {
        'name': 'Comprehensive Library',
        'folder': '${format}/${language}/${category}/${author.sortname}/${bookseries.title}',
        'filename': '${author.sortname} - ${bookseries.title} #${bookseries.number} - ${title}.${ext}',
        'description': 'Full metadata-driven organization'
    }
}
