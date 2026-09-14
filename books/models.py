"""Django models for ebook library management.

This module defines the core models for managing ebooks, metadata,
authors, publishers, genres, and scan folders. Larger, self-contained model
groups have been extracted into sibling modules (models_metadata,
models_operations, and models_api) and are re-exported below.
"""

import logging
import os
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction
from django.utils import timezone

from .mixins.metadata import HashFieldMixin, SourceConfidenceMixin
from .mixins.sync import FinalMetadataSyncMixin

logger = logging.getLogger("books.scanner")


# File format constants for consistent usage across the application
COMIC_FORMATS = ["cbr", "cbz", "cb7", "cbt", "pdf"]
EBOOK_FORMATS = ["epub", "pdf", "mobi", "azw", "azw3", "fb2", "lit", "prc"]
AUDIOBOOK_FORMATS = ["mp3", "m4a", "m4b", "aac", "flac", "ogg", "wav"]

# Cover source types for tracking where covers come from
COVER_SOURCE_TYPES = [
    ("external", "External companion file"),
    ("epub_internal", "EPUB embedded cover"),
    ("pdf_page", "PDF first page"),
    ("archive_first", "First image in CBZ/CBR"),
    ("mobi_internal", "MOBI embedded cover"),
    ("manual", "Manual upload"),
]

# Standard metadata field names for use with BookMetadata table
STANDARD_METADATA_FIELDS = {
    # Universal fields (all content types)
    "description": "description",
    "isbn": "isbn",
    "language": "language",
    "publication_year": "publication_year",
    # Audiobook-specific metadata
    "narrator": "narrator",
    # Comic issue-specific metadata
    "issue_number": "issue_number",
    "volume": "volume",
    "writer": "writer",
    "artist": "artist",
    "cover_date": "cover_date",
    "release_date": "release_date",
    # Additional metadata
    "page_count": "page_count",
    "chapter_count": "chapter_count",
}

LANGUAGE_CHOICES = [
    ("", "Not defined"),
    ("en", "English"),
    ("fr", "French"),
    ("de", "German"),
    ("nl", "Dutch"),
    ("es", "Spanish"),
    ("it", "Italian"),
    ("pt", "Portuguese"),
    ("ja", "Japanese"),
    ("ko", "Korean"),
    ("zh", "Chinese"),
    ("ru", "Russian"),
    ("pl", "Polish"),
    ("he", "Hebrew"),
    ("hu", "Hungarian"),
    ("tr", "Turkish"),
    ("ca", "Catalan"),
    ("id", "Indonesian"),
]


class DataSource(models.Model):
    """Sources of metadata (initial scan, internal, API, etc.)"""

    INITIAL_SCAN = "Initial Scan"
    EPUB_INTERNAL = "EPUB"
    MOBI_INTERNAL = "MOBI"
    PDF_INTERNAL = "PDF"
    OPF_FILE = "OPF File"
    OPEN_LIBRARY = "Open Library"
    GOOGLE_BOOKS = "Google Books"
    COMICVINE = "Comic Vine"
    OPEN_LIBRARY_COVERS = "Open Library Covers"
    GOOGLE_BOOKS_COVERS = "Google Books Covers"
    MANUAL = "Manual Entry"
    CONTENT_SCAN = "ISBN Content Scan"

    SOURCE_CHOICES = [
        (INITIAL_SCAN, "Initial Scan"),
        (EPUB_INTERNAL, "EPUB"),
        (MOBI_INTERNAL, "MOBI"),
        (PDF_INTERNAL, "PDF"),
        (OPF_FILE, "OPF File"),
        (OPEN_LIBRARY, "Open Library"),
        (GOOGLE_BOOKS, "Google Books"),
        (COMICVINE, "Comic Vine"),
        (OPEN_LIBRARY_COVERS, "Open Library Covers"),
        (GOOGLE_BOOKS_COVERS, "Google Books Covers"),
        (MANUAL, "Manual Entry"),
        (CONTENT_SCAN, "ISBN Content Scan"),
    ]

    name = models.CharField(max_length=50, choices=SOURCE_CHOICES, unique=True)
    trust_level = models.FloatField(
        default=0.5,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text="Trust level for this source (0.0-1.0)",
    )
    priority = models.IntegerField(default=1, help_text="Source priority for ordering")
    is_active = models.BooleanField(default=True, help_text="Whether this source is active")

    def __str__(self):
        return self.get_name_display()

    @property
    def title_count(self):
        """Count of titles from this data source"""
        return self.title_relationships.filter(is_active=True).count()

    @property
    def author_count(self):
        """Count of authors from this data source"""
        return self.author_relationships.filter(is_active=True).count()

    @property
    def genre_count(self):
        """Count of genres from this data source"""
        return self.genre_relationships.filter(is_active=True).count()

    @property
    def series_count(self):
        """Count of series from this data source"""
        return self.series_relationships.filter(is_active=True).count()

    @property
    def cover_count(self):
        """Count of covers from this data source"""
        return self.cover_relationships.filter(is_active=True).count()

    @property
    def publisher_count(self):
        """Count of publishers from this data source"""
        return self.publisher_relationships.filter(is_active=True).count()

    @property
    def metadata_count(self):
        """Total count of all metadata entries from this data source"""
        return self.title_count + self.author_count + self.genre_count + self.series_count + self.cover_count + self.publisher_count

    class Meta:
        ordering = ["-trust_level", "name"]


class ScanFolder(HashFieldMixin, models.Model):
    CONTENT_TYPE_CHOICES = [
        ("ebooks", "Ebooks"),
        ("comics", "Comics"),
        ("audiobooks", "Audiobooks"),
    ]

    name = models.CharField(max_length=100, default="Untitled", blank=False, null=False)
    path = models.CharField(max_length=500)
    path_hash = models.CharField(max_length=64, editable=False, default="", unique=True)
    content_type = models.CharField(
        max_length=20,
        choices=CONTENT_TYPE_CHOICES,
        default="ebooks",
        help_text="Type of content in this scan folder",
    )
    language = models.CharField(
        max_length=10,
        choices=LANGUAGE_CHOICES,
        default="",
        blank=True,
        help_text="Default language for books in this folder (used for API searches if not specified in metadata)",
    )
    is_active = models.BooleanField(default=True)
    last_scanned = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        """Validate path exists, is accessible, and is not a duplicate."""
        if self.path:
            try:
                path = Path(self.path).resolve()
                normalized = str(path).rstrip("\\/").lower()

                # Check for duplicate or parent/child overlap with existing folders
                existing = ScanFolder.objects.exclude(id=self.id)
                for folder in existing:
                    try:
                        existing_path = Path(folder.path).resolve()
                        existing_normalized = str(existing_path).rstrip("\\/").lower()

                        # Exact duplicate
                        if normalized == existing_normalized:
                            raise ValidationError({"path": f'This folder is already added as "{folder.name}".'})

                        # Check if one is a parent of the other
                        if normalized.startswith(existing_normalized + os.sep):
                            raise ValidationError({"path": f'This folder is a subfolder of "{folder.name}" ({folder.path}). ' f"Remove the parent folder instead."})
                        if existing_normalized.startswith(normalized + os.sep):
                            raise ValidationError({"path": f'"{folder.name}" ({folder.path}) is a subfolder of this path. ' f"Remove the subfolder first."})
                    except (OSError, RuntimeError):
                        pass  # Skip unresolvable paths

                # Only validate if we can resolve the path
                if path.exists():
                    if not path.is_dir():
                        raise ValidationError({"path": "Path is not a directory"})
                # Note: We don't raise error for non-existent paths to allow
                # tests and staging environments where paths may not exist yet
            except ValidationError:
                raise
            except (OSError, RuntimeError) as e:
                # Log warning but don't fail - path might be created later
                logger.warning(f"Path validation warning for {self.path}: {e}")
                # Only raise for truly invalid paths (permission errors, etc)
                if "Permission denied" in str(e):
                    raise ValidationError({"path": f"Invalid path: {e}"})

    def save(self, *args, **kwargs):
        """Generate hash of path for unique constraint"""
        # Allow skipping validation for tests or programmatic creation
        skip_validation = kwargs.pop("skip_validation", False)

        if self.path:
            self.path_hash = self.generate_hash(self.path)

        if not skip_validation:
            self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.get_content_type_display()})"

    def count_files_on_disk(self):
        """Count ebook files recursively using os.walk (faster than glob)"""
        from django.core.cache import cache

        if not os.path.exists(self.path):
            return 0

        # Create cache key
        try:
            last_modified = os.path.getmtime(self.path)
        except OSError:
            last_modified = timezone.now().timestamp()

        cache_key = f"folder_file_count_{self.id}_{self.content_type}_{int(last_modified)}"
        cached_count = cache.get(cache_key)
        if cached_count is not None:
            return cached_count

        # Get extensions for this content type
        extensions = self.get_extensions()
        file_count = 0

        try:
            for root, dirs, files in os.walk(self.path):
                for file in files:
                    if any(file.lower().endswith(ext) for ext in extensions):
                        file_count += 1
        except (OSError, PermissionError) as e:
            logger.warning(f"Error counting files in {self.path}: {e}")
            return 0

        # Cache for 5 minutes
        cache.set(cache_key, file_count, 300)
        return file_count

    def get_extensions(self):
        """Get file extensions for this scan folder based on content type.

        The folder's content_type is authoritative (set by the user).
        All common formats are accepted regardless of content type
        (e.g., PDF works for both comics and ebooks, CBZ works for both).
        """
        # Base ebook/comic formats (shared across content types)
        document_formats = [".epub", ".pdf", ".mobi", ".azw", ".azw3", ".fb2", ".lit", ".prc"]
        archive_formats = [".cbr", ".cbz", ".cb7", ".cbt"]
        audio_formats = [".mp3", ".m4a", ".m4b", ".aac", ".flac", ".ogg", ".wav"]

        if self.content_type == "audiobooks":
            return audio_formats
        # Both ebooks and comics accept all document + archive formats
        return document_formats + archive_formats

    def get_scan_progress_info(self):
        """Get information about scan progress"""
        scanned_count = self.book_set.count()
        total_files = self.count_files_on_disk()

        if total_files == 0:
            percentage = 100 if scanned_count == 0 else 0
        else:
            percentage = (scanned_count / total_files) * 100

        return {
            "scanned": scanned_count,
            "total_files": total_files,
            "percentage": round(percentage, 1),
            "needs_scan": total_files > scanned_count,
        }

    class Meta:
        verbose_name = "Scan Folder"
        verbose_name_plural = "Scan Folders"


class BookQuerySet(models.QuerySet):
    """Custom QuerySet for common Book queries"""

    def available(self):
        """Get available books (not deleted, not corrupted)"""
        return self.filter(is_available=True, deleted_at__isnull=True, is_corrupted=False)

    def needs_metadata(self):
        """Get books with incomplete metadata"""
        return self.filter(finalmetadata__completeness_score__lt=0.7)

    def with_complete_metadata(self):
        """Get books with eager-loaded metadata"""
        return self.select_related("finalmetadata", "scan_folder").prefetch_related(
            "titles__source",
            "author_relationships__author",
            "author_relationships__source",
            "covers__source",
        )

    def needs_review(self):
        """Get books that need manual review"""
        return self.filter(models.Q(finalmetadata__is_reviewed=False) & models.Q(finalmetadata__overall_confidence__lt=0.6))

    def by_content_type(self, content_type):
        """Filter by content type"""
        return self.filter(content_type=content_type)


class Book(HashFieldMixin, models.Model):
    """Unified content record - represents a single work"""

    CONTENT_TYPE_CHOICES = [
        ("ebook", "Ebook"),
        ("audiobook", "Audiobook"),
        ("comic", "Comic Issue"),
    ]

    content_type = models.CharField(max_length=20, choices=CONTENT_TYPE_CHOICES, default="ebook")

    # Scan metadata
    first_scanned = models.DateTimeField(auto_now_add=True)
    last_scanned = models.DateTimeField(auto_now=True)
    scan_folder = models.ForeignKey(ScanFolder, on_delete=models.CASCADE, null=True)

    # Status flags
    is_placeholder = models.BooleanField(default=False)
    is_duplicate = models.BooleanField(default=False)
    is_corrupted = models.BooleanField(default=False)
    is_available = models.BooleanField(default=True)
    last_scan_status = models.CharField(max_length=20, blank=True, null=True)

    # Soft delete support
    deleted_at = models.DateTimeField(null=True, blank=True)

    objects = BookQuerySet.as_manager()

    @classmethod
    def find_by_title(cls, title, content_type="ebook"):
        """Find existing book by title (exact match)"""
        book_title = (
            BookTitle.objects.filter(
                title__iexact=title,
                book__content_type=content_type,
                is_active=True,
                book__deleted_at__isnull=True,
            )
            .select_related("book")
            .first()
        )

        return book_title.book if book_title else None

    @classmethod
    def create_with_title(cls, title, content_type="ebook", source=None, confidence=0.8, **kwargs):
        """Create new book with title"""
        if source is None:
            source = DataSource.objects.get(name=DataSource.INITIAL_SCAN)

        with transaction.atomic():
            book = cls.objects.create(content_type=content_type, **kwargs)
            BookTitle.objects.create(
                book=book,
                title=title,
                source=source,
                confidence=confidence,
                is_active=True,
            )
            return book

    @classmethod
    def get_or_create_by_path(cls, file_path, **kwargs):
        """Get or create book by file path, preventing duplicates"""
        from .models import BookFile

        # Try to find existing BookFile with this path
        book_file = BookFile.objects.filter(file_path=file_path).select_related("book").first()

        if book_file:
            return book_file.book, False

        # Create new book with file
        with transaction.atomic():
            # Extract title from kwargs or use filename
            title = kwargs.pop("title", None)
            if not title:
                title = os.path.splitext(os.path.basename(file_path))[0]

            source = kwargs.pop("source", None)
            if source is None:
                source = DataSource.objects.get(name=DataSource.INITIAL_SCAN)

            # Create book with title
            book = cls.create_with_title(title=title, source=source, **kwargs)

            # Create BookFile
            BookFile.objects.create(
                book=book,
                file_path=file_path,
                file_format=os.path.splitext(file_path)[1].lstrip(".").lower(),
                is_primary=True,
            )

            return book, True

    def soft_delete(self):
        """Soft delete this book"""
        self.deleted_at = timezone.now()
        self.is_available = False
        self.save(update_fields=["deleted_at", "is_available"])

        logger.info("Soft deleted book", extra={"book_id": self.id, "title": self.title})

    def __str__(self):
        primary_title = self.titles.filter(is_active=True).first()
        title_str = primary_title.title if primary_title else f"Book #{self.pk}"

        if self.is_placeholder:
            return f"Placeholder: {title_str}"
        return title_str

    @property
    def title(self):
        """Get the primary title for backwards compatibility"""
        primary_title = self.titles.filter(is_active=True).first()
        return primary_title.title if primary_title else f"Untitled Book #{self.pk}"

    @property
    def primary_file(self):
        """Get the primary BookFile for this book"""
        # Use prefetched_files if available to avoid additional queries
        if hasattr(self, "prefetched_files") and self.prefetched_files:
            return self.prefetched_files[0]
        return self.files.first()

    @property
    def final_metadata(self):
        try:
            return self.finalmetadata
        except FinalMetadata.DoesNotExist:
            return None

    @property
    def effective_path(self):
        """Get the current effective file path"""
        if hasattr(self, "finalmetadata") and self.finalmetadata and self.finalmetadata.is_renamed:
            if self.finalmetadata.final_path:
                return self.finalmetadata.final_path

        primary_file = self.primary_file
        return primary_file.file_path if primary_file else ""

    @property
    def file_path(self):
        """Backward compatibility: get file path from primary file"""
        primary_file = self.primary_file
        return primary_file.file_path if primary_file else ""

    @property
    def file_path_hash(self):
        """Get file path hash from primary file"""
        primary_file = self.primary_file
        return primary_file.file_path_hash if primary_file else ""

    @property
    def file_format(self):
        """Backward compatibility: get file format from primary file"""
        primary_file = self.primary_file
        return primary_file.file_format if primary_file else ""

    @property
    def filename(self):
        """Get filename from primary file"""
        primary_file = self.primary_file
        return primary_file.filename if primary_file else ""

    @property
    def file_size(self):
        """Get file size from primary file"""
        primary_file = self.primary_file
        return primary_file.file_size if primary_file else 0

    @property
    def relative_path(self):
        """Get relative path from scan folder to the primary file"""
        primary_file = self.primary_file
        if self.scan_folder and self.scan_folder.path and primary_file and primary_file.file_path:
            scan_root = os.path.normpath(self.scan_folder.path)
            full_path = os.path.normpath(primary_file.file_path)
            subpath = full_path.replace(scan_root, "").lstrip(os.sep)
            return os.path.dirname(subpath)
        return ""

    class Meta:
        ordering = ["-last_scanned", "id"]
        indexes = [
            models.Index(fields=["content_type", "scan_folder"]),
            models.Index(fields=["is_placeholder", "is_corrupted"]),
            models.Index(fields=["last_scanned"]),
            models.Index(fields=["deleted_at"]),
            models.Index(fields=["is_available"]),
        ]


class BookFile(HashFieldMixin, models.Model):
    """Individual files that make up a book/content work"""

    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name="files")

    # Core file information
    file_path = models.CharField(max_length=1000)
    file_path_hash = models.CharField(max_length=64, editable=False, default="", db_index=True)
    file_format = models.CharField(max_length=20)
    file_size = models.BigIntegerField(null=True, blank=True)

    # Audiobook file properties
    duration_seconds = models.IntegerField(null=True, blank=True)
    chapter_number = models.IntegerField(null=True, blank=True)
    chapter_title = models.CharField(max_length=500, blank=True)
    track_number = models.IntegerField(null=True, blank=True)
    bitrate = models.CharField(max_length=20, blank=True)
    sample_rate = models.CharField(max_length=20, blank=True)

    # Comic file properties
    page_count = models.IntegerField(null=True, blank=True)

    # Companion files
    cover_path = models.CharField(max_length=1000, blank=True)
    opf_path = models.CharField(max_length=1000, blank=True)

    # Cover source tracking
    cover_source_type = models.CharField(max_length=20, choices=COVER_SOURCE_TYPES, default="external", help_text="Where the cover image comes from")
    has_internal_cover = models.BooleanField(default=False, help_text="Whether the file contains an embedded cover")
    cover_internal_path = models.CharField(max_length=500, blank=True, help_text="Path within archive/EPUB for internal covers")

    # Phase 2: Cover enhancements
    cover_image_preference = models.CharField(max_length=500, blank=True, help_text="User-selected internal path for preferred cover")
    cover_quality_score = models.IntegerField(null=True, blank=True, help_text="Calculated quality score (0-100)")
    cover_width = models.IntegerField(null=True, blank=True, help_text="Cover image width in pixels")
    cover_height = models.IntegerField(null=True, blank=True, help_text="Cover image height in pixels")
    original_cover_path = models.CharField(max_length=500, blank=True, help_text="Original auto-detected cover path (before manual upload)")

    # Scanning metadata
    first_scanned = models.DateTimeField(auto_now_add=True)
    last_scanned = models.DateTimeField(auto_now=True)

    # Auto-generated sortable fields
    chapter_sort = models.FloatField(default=999.0)

    def save(self, *args, **kwargs):
        """Generate hash and sort fields before saving"""
        if self.file_path:
            self.file_path_hash = self.generate_hash(self.file_path)

        if self.chapter_number:
            try:
                self.chapter_sort = float(self.chapter_number)
            except (ValueError, TypeError):
                self.chapter_sort = 999.0

        super().save(*args, **kwargs)

    def __str__(self):
        if self.book.content_type == "audiobook" and self.chapter_number:
            return f"{self.book.title} - Chapter {self.chapter_number}"
        return f"{self.book.title} - {os.path.basename(self.file_path)}"

    @property
    def filename(self):
        """Get just the filename from the full path"""
        return os.path.basename(self.file_path)

    @property
    def extension(self):
        """Get file extension"""
        return os.path.splitext(self.file_path)[1].lower()

    class Meta:
        ordering = ["book", "chapter_sort", "track_number"]
        indexes = [
            models.Index(fields=["book", "file_format"]),
            models.Index(fields=["book", "chapter_number"]),
            models.Index(fields=["file_path_hash"]),
        ]
        constraints = [models.UniqueConstraint(fields=["book", "file_path_hash"], name="unique_book_file_path")]


class Author(models.Model):
    """Normalized author names"""

    name = models.CharField(max_length=200)
    first_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100, blank=True)
    name_normalized = models.CharField(max_length=200, db_index=True, unique=True)
    is_reviewed = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        from books.utils.authors import normalize_author_name, parse_author_name

        if not self.name and (self.first_name or self.last_name):
            name_parts = []
            if self.first_name:
                name_parts.append(self.first_name.strip())
            if self.last_name:
                name_parts.append(self.last_name.strip())
            self.name = " ".join(name_parts)

        if not (self.first_name and self.last_name):
            self.first_name, self.last_name = parse_author_name(self.name)

        # Truncate fields to prevent database errors
        # This can happen with very long filenames or incorrectly parsed metadata
        self.name = (self.name or "")[:200]
        self.first_name = (self.first_name or "")[:100]
        self.last_name = (self.last_name or "")[:100]

        self.name_normalized = normalize_author_name(f"{self.first_name} {self.last_name}")[:200]
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["first_name", "last_name"], name="unique_author_name_combo")]


class BookAuthor(FinalMetadataSyncMixin, SourceConfidenceMixin, models.Model):
    """M2M relationship between books and authors"""

    AUTHOR_ROLES = [
        ("author", "Author"),
        ("writer", "Writer"),
        ("artist", "Artist"),
        ("narrator", "Narrator"),
        ("editor", "Editor"),
        ("illustrator", "Illustrator"),
        ("translator", "Translator"),
    ]

    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name="author_relationships")
    author = models.ForeignKey(Author, on_delete=models.CASCADE, related_name="book_relationships")
    source = models.ForeignKey(DataSource, on_delete=models.CASCADE, related_name="author_relationships")
    role = models.CharField(max_length=20, choices=AUTHOR_ROLES, default="author")
    is_main_author = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.post_deactivation_sync()

    class Meta:
        unique_together = ["book", "author", "role", "source"]
        ordering = ["-confidence", "-is_main_author"]
        indexes = [
            models.Index(fields=["book", "is_active", "-confidence"]),
            models.Index(fields=["author", "is_active"]),
        ]


class BookTitle(FinalMetadataSyncMixin, SourceConfidenceMixin, models.Model):
    """Book titles from different sources"""

    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name="titles")
    source = models.ForeignKey(DataSource, on_delete=models.CASCADE, related_name="title_relationships")
    title = models.CharField(max_length=500, blank=False)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.post_deactivation_sync()

    def __str__(self):
        return f"{self.title} ({self.source})"

    class Meta:
        unique_together = ["book", "title", "source"]
        ordering = ["-confidence"]
        indexes = [
            models.Index(fields=["book", "is_active", "-confidence"]),
        ]
        constraints = [models.CheckConstraint(condition=~models.Q(title=""), name="title_not_empty")]


class BookCover(FinalMetadataSyncMixin, SourceConfidenceMixin, HashFieldMixin, models.Model):
    """Book covers from different sources"""

    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name="covers")
    source = models.ForeignKey(DataSource, on_delete=models.CASCADE, related_name="cover_relationships")
    cover_path = models.CharField(max_length=1000)
    cover_path_hash = models.CharField(max_length=64, editable=False)

    # Cover metadata
    width = models.IntegerField(null=True, blank=True)
    height = models.IntegerField(null=True, blank=True)
    file_size = models.BigIntegerField(null=True, blank=True)
    format = models.CharField(max_length=10, blank=True)

    # Quality indicators
    is_high_resolution = models.BooleanField(default=False)
    aspect_ratio = models.FloatField(null=True, blank=True)

    def save(self, *args, **kwargs):
        self.cover_path_hash = self.generate_hash(self.cover_path)

        if self.width and self.height:
            self.aspect_ratio = self.width / self.height
            self.is_high_resolution = self.width >= 600 or self.height >= 800

        super().save(*args, **kwargs)
        self.post_deactivation_sync()

    def __str__(self):
        book_title = getattr(self.book, "title", f"Book {self.book.id}")
        return f"Cover for {book_title} from {self.source} ({self.confidence:.2f})"

    @property
    def is_local_file(self):
        """Check if cover is a local file path vs URL"""
        return not (self.cover_path.startswith("http://") or self.cover_path.startswith("https://"))

    @property
    def resolution_str(self):
        """Human readable resolution string"""
        if self.width and self.height:
            return f"{self.width}x{self.height}"
        return "Unknown"

    class Meta:
        unique_together = ["book", "cover_path_hash", "source"]
        ordering = ["-confidence", "-is_high_resolution", "-width"]
        indexes = [
            models.Index(fields=["book", "is_active", "-confidence"]),
        ]


class Series(models.Model):
    """Content series"""

    name = models.CharField(max_length=200, unique=True, blank=False)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "Series"
        constraints = [models.CheckConstraint(condition=~models.Q(name=""), name="series_name_not_empty")]


class BookSeries(FinalMetadataSyncMixin, SourceConfidenceMixin, models.Model):
    """Series information with source tracking"""

    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name="series_relationships")
    series = models.ForeignKey(
        Series,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="book_relationships",
    )
    source = models.ForeignKey(DataSource, on_delete=models.CASCADE, related_name="series_relationships")
    series_number = models.CharField(max_length=20, null=True, blank=True)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.post_deactivation_sync()

    class Meta:
        unique_together = ["book", "series", "source"]
        ordering = ["-confidence"]
        verbose_name_plural = "Book Series"
        indexes = [
            models.Index(fields=["book", "is_active", "-confidence"]),
            models.Index(fields=["series", "is_active"]),
        ]


class Genre(models.Model):
    """Book genres/categories"""

    name = models.CharField(max_length=100, unique=True, blank=False)
    is_reviewed = models.BooleanField(default=False)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ["name"]
        constraints = [models.CheckConstraint(condition=~models.Q(name=""), name="genre_name_not_empty")]


class BookGenre(models.Model):
    """M2M relationship between books and genres with source tracking"""

    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name="genre_relationships")
    genre = models.ForeignKey(Genre, on_delete=models.CASCADE, related_name="book_relationships")
    source = models.ForeignKey(DataSource, on_delete=models.CASCADE, related_name="genre_relationships")
    confidence = models.FloatField(validators=[MinValueValidator(0.0), MaxValueValidator(1.0)])
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @classmethod
    def create_or_update_best(cls, book, genre, source, confidence=1.0, is_active=True):
        """
        Create or update BookGenre with best source and confidence.
        Uses select_for_update for true atomicity.
        """
        with transaction.atomic():
            # Lock existing entries for this book+genre combination
            existing_entries = list(cls.objects.select_for_update().filter(book=book, genre=genre))

            if not existing_entries:
                # No existing entry, create new one
                return cls.objects.create(
                    book=book,
                    genre=genre,
                    source=source,
                    confidence=confidence,
                    is_active=is_active,
                )

            # Calculate combined score for new entry
            new_score = source.trust_level * confidence

            # Find best existing entry
            best_existing = None
            best_existing_score = 0

            for entry in existing_entries:
                existing_score = entry.source.trust_level * entry.confidence
                if existing_score > best_existing_score:
                    best_existing = entry
                    best_existing_score = existing_score

            # Compare scores
            if new_score > best_existing_score:
                # New entry is better, update the best existing one
                best_existing.source = source
                best_existing.confidence = confidence
                best_existing.is_active = is_active
                best_existing.save(update_fields=["source", "confidence", "is_active"])

                # Deactivate other entries
                for entry in existing_entries:
                    if entry.id != best_existing.id:
                        entry.is_active = False
                        entry.save(update_fields=["is_active"])

                logger.debug(
                    f"Updated BookGenre {best_existing.id}",
                    extra={
                        "book_id": book.id,
                        "genre": genre.name,
                        "source": source.name,
                        "new_score": new_score,
                        "old_score": best_existing_score,
                    },
                )
                return best_existing
            else:
                # Existing entry is better, ensure it's active
                if not best_existing.is_active:
                    best_existing.is_active = True
                    best_existing.save(update_fields=["is_active"])

                return best_existing

    class Meta:
        unique_together = ["book", "genre", "source"]
        indexes = [
            models.Index(fields=["book", "is_active"]),
            models.Index(fields=["genre", "is_active"]),
        ]


class Publisher(models.Model):
    """Publishers"""

    name = models.CharField(max_length=255, unique=True, blank=False)
    is_reviewed = models.BooleanField(default=False)

    def __str__(self):
        return self.name

    class Meta:
        constraints = [models.CheckConstraint(condition=~models.Q(name=""), name="publisher_name_not_empty")]


class BookPublisher(FinalMetadataSyncMixin, SourceConfidenceMixin, models.Model):
    """M2M relationship between books and publishers"""

    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name="publisher_relationships")
    publisher = models.ForeignKey(Publisher, on_delete=models.CASCADE, related_name="book_relationships")
    source = models.ForeignKey(DataSource, on_delete=models.CASCADE, related_name="publisher_relationships")

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.post_deactivation_sync()

    def __str__(self):
        title = getattr(self.book.final_metadata, "final_title", "Untitled") if self.book.final_metadata else "Untitled"
        return f"{title} -> {self.publisher.name} ({self.source.name})"

    class Meta:
        unique_together = ["book", "publisher", "source"]
        ordering = ["-confidence"]
        indexes = [
            models.Index(fields=["book", "is_active", "-confidence"]),
            models.Index(fields=["publisher", "is_active"]),
        ]


class BookMetadata(FinalMetadataSyncMixin, SourceConfidenceMixin, HashFieldMixin, models.Model):
    """Additional metadata fields with source tracking"""

    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name="metadata")
    source = models.ForeignKey(DataSource, on_delete=models.CASCADE, related_name="metadata_relationships")
    field_name = models.CharField(max_length=100, blank=False)
    field_value = models.TextField(blank=False)
    field_value_hash = models.CharField(max_length=64, editable=False)

    def save(self, *args, **kwargs):
        self.field_value_hash = self.generate_hash(self.field_value)
        super().save(*args, **kwargs)
        self.post_deactivation_sync()

    class Meta:
        unique_together = ["book", "field_name", "field_value_hash", "source"]
        ordering = ["-confidence"]
        indexes = [
            models.Index(fields=["book", "field_name", "is_active"]),
        ]
        constraints = [
            models.CheckConstraint(condition=~models.Q(field_name=""), name="metadata_field_name_not_empty"),
            models.CheckConstraint(
                condition=~models.Q(field_value=""),
                name="metadata_field_value_not_empty",
            ),
        ]

    def __str__(self):
        return f"{self.field_name}: {self.field_value[:50]} ({self.source.name})"


# Re-export models that live in focused sibling modules so existing imports
# such as ``from books.models import FinalMetadata`` keep working unchanged.
from .models_api import APIAccessLog, BookAPICompleteness, ScanSession  # noqa: E402,F401
from .models_metadata import FinalMetadata  # noqa: E402,F401
from .models_operations import (  # noqa: E402,F401
    AIFeedback,
    FileOperation,
    ScanHistory,
    ScanLog,
    ScanQueue,
    ScanStatus,
    SetupWizard,
    UserProfile,
)
