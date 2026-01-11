"""Django models for ebook library management.

This module defines the database models for managing ebooks, metadata,
authors, publishers, genres, and scan operations. Includes comprehensive
relationship management and final metadata synchronization.
"""

import logging
import os
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction
from django.utils import timezone

from books.utils.language import normalize_language

from .mixins.metadata import HashFieldMixin, SourceConfidenceMixin
from .mixins.sync import FinalMetadataSyncMixin

# API tracking models will be defined at the end of this file

logger = logging.getLogger("books.scanner")


# File format constants for consistent usage across the application
COMIC_FORMATS = ["cbr", "cbz", "cb7", "cbt", "pdf"]
EBOOK_FORMATS = ["epub", "pdf", "mobi", "azw", "azw3", "fb2", "lit", "prc"]
AUDIOBOOK_FORMATS = ["mp3", "m4a", "m4b", "aac", "flac", "ogg", "wav"]

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
    language = models.CharField(max_length=10, choices=LANGUAGE_CHOICES, default="en")
    is_active = models.BooleanField(default=True)
    last_scanned = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        """Validate path exists and is accessible"""
        if self.path:
            try:
                path = Path(self.path).resolve()
                # Only validate if we can resolve the path
                if path.exists():
                    if not path.is_dir():
                        raise ValidationError({"path": "Path is not a directory"})
                # Note: We don't raise error for non-existent paths to allow
                # tests and staging environments where paths may not exist yet
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
        """Get file extensions for this scan folder based on content type"""
        if self.content_type == "comics":
            return [".cbr", ".cbz", ".cb7", ".cbt", ".pdf"]
        elif self.content_type == "audiobooks":
            return [".mp3", ".m4a", ".m4b", ".aac", ".flac", ".ogg", ".wav"]
        elif self.content_type == "ebooks":
            return [".epub", ".pdf", ".mobi", ".azw", ".azw3", ".fb2", ".lit", ".prc"]
        else:
            return [".epub", ".pdf", ".mobi", ".azw", ".azw3", ".fb2"]

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

    # Reading/Progress tracking
    is_read = models.BooleanField(default=False)
    read_date = models.DateTimeField(null=True, blank=True)
    current_position = models.IntegerField(default=0)

    # Companion files
    cover_path = models.CharField(max_length=1000, blank=True)
    opf_path = models.CharField(max_length=1000, blank=True)

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
        return f"{title} → {self.publisher.name} ({self.source.name})"

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


class FinalMetadata(models.Model):
    """
    Final, consolidated metadata for a book after review.
    This represents the user's chosen metadata from various sources.
    """

    book = models.OneToOneField("Book", on_delete=models.CASCADE, related_name="finalmetadata")

    # Core fields
    final_title = models.CharField(max_length=500, blank=True)
    final_title_confidence = models.FloatField(default=0.0)

    final_author = models.CharField(max_length=500, blank=True)
    final_author_confidence = models.FloatField(default=0.0)

    final_series = models.CharField(max_length=200, blank=True, null=True)
    final_series_number = models.CharField(max_length=20, blank=True, null=True)
    final_series_confidence = models.FloatField(default=0.0)

    # Cover metadata
    final_cover_path = models.CharField(max_length=1000, blank=True)
    final_cover_confidence = models.FloatField(default=0.0)

    # Additional fields
    final_publisher = models.CharField(max_length=200, blank=True)
    final_publisher_confidence = models.FloatField(default=0.0)

    language = models.CharField(max_length=10, blank=True)
    isbn = models.CharField(max_length=20, blank=True)
    publication_year = models.IntegerField(null=True, blank=True)
    description = models.TextField(blank=True)

    # Reading tracking fields
    is_read = models.BooleanField(default=False, help_text="Whether this book has been read")
    read_date = models.DateTimeField(null=True, blank=True, help_text="When the book was marked as read")
    reading_progress = models.IntegerField(default=0, help_text="Reading progress percentage (0-100)")

    # Audiobook-specific tracking fields
    current_position_seconds = models.IntegerField(default=0, help_text="Current playback position in seconds")
    total_duration_seconds = models.IntegerField(null=True, blank=True, help_text="Total duration in seconds")
    last_played = models.DateTimeField(null=True, blank=True, help_text="When the audiobook was last played")
    is_finished = models.BooleanField(default=False, help_text="Whether the audiobook has been finished")

    # Overall metrics
    overall_confidence = models.FloatField(default=0.0)
    completeness_score = models.FloatField(default=0.0)

    # Denormalized flags for faster filtering
    has_cover = models.BooleanField(default=False)
    has_isbn = models.BooleanField(default=False)
    has_description = models.BooleanField(default=False)
    metadata_complete = models.BooleanField(default=False)

    # Status
    is_reviewed = models.BooleanField(default=False)
    is_renamed = models.BooleanField(default=False)
    final_path = models.CharField(max_length=1000, blank=True)
    last_updated = models.DateTimeField(auto_now=True)

    def calculate_overall_confidence(self):
        """Calculate weighted overall confidence"""
        weights = {
            "title": 0.3,
            "author": 0.3,
            "series": 0.15,
            "cover": 0.25,
        }

        score = (
            self.final_title_confidence * weights["title"]
            + self.final_author_confidence * weights["author"]
            + self.final_series_confidence * weights["series"]
            + self.final_cover_confidence * weights["cover"]
        )

        self.overall_confidence = score
        return score

    def calculate_completeness_score(self):
        """Calculate how complete the metadata is"""
        fields = [
            bool(self.final_title),
            bool(self.final_author),
            bool(self.final_cover_path),
            bool(self.final_publisher),
            bool(self.language),
            bool(self.isbn),
            bool(self.publication_year),
            bool(self.description),
        ]

        self.completeness_score = sum(fields) / len(fields)
        return self.completeness_score

    def update_dynamic_field(self, field_name):
        """Update a single dynamic field from metadata sources"""
        try:
            next_value = self.book.metadata.filter(field_name=field_name, is_active=True).select_related("source").order_by("-confidence").first()

            if next_value and next_value.field_value:
                value = next_value.field_value

                if field_name == "publication_year":
                    try:
                        import re

                        year_match = re.search(r"\b(18|19|20)\d{2}\b", str(value))
                        if year_match:
                            year = int(year_match.group())
                            if 1000 < year <= 2100:
                                setattr(self, field_name, year)
                                return
                        setattr(self, field_name, None)
                    except Exception as e:
                        logger.warning(f"Error parsing year from '{value}': {e}")
                        setattr(self, field_name, None)
                else:
                    setattr(self, field_name, value)
            else:
                setattr(self, field_name, None if field_name == "publication_year" else "")

        except Exception as e:
            logger.error(f"Error updating field '{field_name}' for book {self.book.id}: {e}")
            setattr(self, field_name, None if field_name == "publication_year" else "")

    def update_final_title(self):
        """Update final title from sources"""
        try:
            next_title = self.book.titles.select_related("source").filter(is_active=True).order_by("-confidence").first()

            self.final_title = next_title.title if next_title else ""
            self.final_title_confidence = next_title.confidence if next_title else 0.0
        except Exception as e:
            logger.error(f"Error updating final title for book {self.book.id}: {e}")
            self.final_title = ""
            self.final_title_confidence = 0.0

    def update_final_author(self):
        """Update final author from sources"""
        try:
            next_author = self.book.author_relationships.select_related("author", "source").filter(is_active=True).order_by("-confidence", "-is_main_author").first()

            self.final_author = next_author.author.name if next_author and next_author.author else ""
            self.final_author_confidence = next_author.confidence if next_author else 0.0
        except Exception as e:
            logger.error(f"Error updating final author for book {self.book.id}: {e}")
            self.final_author = ""
            self.final_author_confidence = 0.0

    def update_final_cover(self):
        """Update final cover from sources"""
        try:
            next_cover = self.book.covers.select_related("source").filter(is_active=True).order_by("-confidence", "-is_high_resolution").first()

            if next_cover:
                self.final_cover_path = next_cover.cover_path
                self.final_cover_confidence = next_cover.confidence
                self.has_cover = True
            elif self.book.primary_file and self.book.primary_file.cover_path:
                self.final_cover_path = self.book.primary_file.cover_path
                self.final_cover_confidence = 0.9
                self.has_cover = True
            else:
                self.final_cover_path = ""
                self.final_cover_confidence = 0.0
                self.has_cover = False
        except Exception as e:
            logger.error(f"Error updating final cover for book {self.book.id}: {e}")
            self.final_cover_path = ""
            self.final_cover_confidence = 0.0
            self.has_cover = False

    def update_final_publisher(self):
        """Update final publisher from sources"""
        try:
            next_publisher = self.book.publisher_relationships.select_related("publisher", "source").filter(is_active=True).order_by("-confidence").first()

            self.final_publisher = next_publisher.publisher.name if next_publisher and next_publisher.publisher else ""
            self.final_publisher_confidence = next_publisher.confidence if next_publisher else 0.0
        except Exception as e:
            logger.error(f"Error updating final publisher for book {self.book.id}: {e}")
            self.final_publisher = ""
            self.final_publisher_confidence = 0.0

    def update_final_series(self):
        """Update final series from sources"""
        try:
            next_series = self.book.series_relationships.select_related("series", "source").filter(is_active=True).order_by("-confidence").first()

            self.final_series = next_series.series.name if next_series and next_series.series else ""
            self.final_series_number = next_series.series_number or "" if next_series else ""
            self.final_series_confidence = next_series.confidence if next_series else 0.0
        except Exception as e:
            logger.error(f"Error updating final series for book {self.book.id}: {e}")
            self.final_series = ""
            self.final_series_number = ""
            self.final_series_confidence = 0.0

    def sync_from_sources(self, force=False, save_after=True):
        """
        Explicitly sync final metadata from all sources.
        This pulls the highest-confidence metadata from all related tables.

        Args:
            force: If True, update even if is_reviewed is True
            save_after: If True, automatically save after syncing

        Returns:
            bool: True if sync was performed, False if skipped
        """
        if self.is_reviewed and not force:
            logger.debug("Skipping sync for reviewed book", extra={"book_id": self.book.id})
            return False

        try:
            # Update all metadata fields from sources
            self.update_final_title()
            self.update_final_author()
            self.update_final_series()
            self.update_final_cover()
            self.update_final_publisher()

            # Update dynamic fields (ISBN, language, description, etc.)
            dynamic_fields = ["publication_year", "description", "isbn", "language"]
            for field_name in dynamic_fields:
                self.update_dynamic_field(field_name)

            # Recalculate scores
            self.calculate_overall_confidence()
            self.calculate_completeness_score()

            # Update denormalized flags
            self.has_isbn = bool(self.isbn)
            self.has_description = bool(self.description)
            self.metadata_complete = self.completeness_score >= 0.8

            logger.info(
                "Synced final metadata from sources",
                extra={
                    "book_id": self.book.id,
                    "title": self.final_title,
                    "author": self.final_author,
                    "confidence": f"{self.overall_confidence:.2f}",
                    "completeness": f"{self.completeness_score:.2f}",
                },
            )

            if save_after:
                # Use update_fields to avoid recursion and be more efficient
                self.save(
                    update_fields=[
                        "final_title",
                        "final_title_confidence",
                        "final_author",
                        "final_author_confidence",
                        "final_series",
                        "final_series_number",
                        "final_series_confidence",
                        "final_cover_path",
                        "final_cover_confidence",
                        "final_publisher",
                        "final_publisher_confidence",
                        "language",
                        "isbn",
                        "publication_year",
                        "description",
                        "overall_confidence",
                        "completeness_score",
                        "has_cover",
                        "has_isbn",
                        "has_description",
                        "metadata_complete",
                        "last_updated",
                    ]
                )

            return True

        except Exception as e:
            logger.error(
                "Error syncing metadata from sources",
                extra={"book_id": self.book.id, "error": str(e)},
                exc_info=True,
            )
            return False

    def mark_as_renamed(self, new_file_path, user=None):
        """Mark this book as renamed and store the new path"""
        self.is_renamed = True
        self.final_path = new_file_path
        self.save(update_fields=["is_renamed", "final_path"])

        FileOperation.objects.create(
            book=self.book,
            operation_type="rename",
            status="completed",
            original_file_path=(self.book.primary_file.file_path if self.book.primary_file else ""),
            new_file_path=new_file_path,
            operation_date=timezone.now(),
            user=user,
            notes="Book renamed via renaming interface",
        )

        logger.info(
            "Book renamed",
            extra={
                "book_id": self.book.id,
                "old_path": (self.book.primary_file.file_path if self.book.primary_file else ""),
                "new_path": new_file_path,
            },
        )

    def save(self, *args, **kwargs):
        """
        Save with intelligent auto-update logic.

        Auto-sync behavior:
        1. On creation (first save):
           - Auto-syncs if no explicit values provided
           - Auto-syncs if not reviewed
           - Can be disabled with auto_sync=False

        2. On updates (subsequent saves):
           - Does NOT auto-sync (prevents recursion)
           - Triggered updates should call sync_from_sources() explicitly
           - Manual edits are preserved

        Always:
        - Normalizes data (language, publication_year)
        - Updates denormalized flags
        - Calculates scores if missing
        """
        # Detect if this is creation or update
        is_creating = self._state.adding if hasattr(self, "_state") else self.pk is None

        # Allow disabling auto-sync via parameter
        auto_sync = kwargs.pop("auto_sync", True)

        # Check if user provided explicit values (heuristic: any non-default values)
        has_explicit_values = any(
            [
                self.final_title,
                self.final_author,
                self.final_series,
                self.final_cover_path,
                self.final_publisher,
                self.isbn,
                self.language,
                self.description,
            ]
        )

        # CRITICAL: Only auto-sync on CREATION, not on updates
        # This prevents infinite recursion when sync_from_sources() calls save()
        if is_creating and auto_sync and not self.is_reviewed and not has_explicit_values:
            logger.debug("Auto-syncing on creation", extra={"book_id": self.book.id})
            # Sync but don't save again (we're in the middle of saving)
            self.sync_from_sources(save_after=False)

        # Always normalize data
        if self.language:
            self.language = normalize_language(self.language)

        if isinstance(self.publication_year, str):
            year_str = self.publication_year.strip()
            self.publication_year = int(year_str) if year_str.isdigit() else None

        # Always update denormalized flags
        self.has_cover = bool(self.final_cover_path)
        self.has_isbn = bool(self.isbn)
        self.has_description = bool(self.description)

        # Calculate scores if missing or zero
        if not self.overall_confidence:
            self.calculate_overall_confidence()
        if not self.completeness_score:
            self.calculate_completeness_score()

        self.metadata_complete = self.completeness_score >= 0.8

        # Finally, perform the actual save
        super().save(*args, **kwargs)

    @classmethod
    def create_for_book(cls, book, auto_sync=True, **kwargs):
        """
        Convenience method to create FinalMetadata with clear sync control.

        Args:
            book: Book instance
            auto_sync: Whether to auto-sync from sources on creation (default: True)
            **kwargs: Explicit field values to set

        Returns:
            FinalMetadata instance (already saved)
        """
        final_metadata = cls(book=book, **kwargs)
        final_metadata.save(auto_sync=auto_sync)
        return final_metadata

    def __str__(self):
        return f"{self.final_title or 'Unknown'} by {self.final_author or 'Unknown'}"

    class Meta:
        indexes = [
            models.Index(fields=["is_reviewed"]),
            models.Index(fields=["overall_confidence"]),
            models.Index(fields=["completeness_score"]),
            models.Index(fields=["has_cover"]),
            models.Index(fields=["has_isbn"]),
            models.Index(fields=["metadata_complete"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(models.Q(final_title_confidence__gte=0) & models.Q(final_title_confidence__lte=1)),
                name="valid_title_confidence",
            ),
            models.CheckConstraint(
                condition=(models.Q(publication_year__isnull=True) | (models.Q(publication_year__gte=1000) & models.Q(publication_year__lte=2100))),
                name="valid_publication_year",
            ),
        ]


class ScanLog(models.Model):
    """Log entries for scan operations"""

    LOG_LEVELS = [
        ("INFO", "Info"),
        ("WARNING", "Warning"),
        ("ERROR", "Error"),
    ]

    timestamp = models.DateTimeField(auto_now_add=True)
    level = models.CharField(max_length=10, choices=LOG_LEVELS)
    message = models.TextField()
    file_path = models.CharField(max_length=1000, blank=True)
    scan_folder = models.ForeignKey(ScanFolder, on_delete=models.CASCADE, null=True)

    # Aggregate counters
    books_found = models.IntegerField(default=0)
    books_processed = models.IntegerField(default=0)
    errors_count = models.IntegerField(default=0)

    class Meta:
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["-timestamp", "level"]),
        ]

    def __str__(self):
        return f"{self.timestamp.strftime('%Y-%m-%d %H:%M')} - {self.level}: {self.message[:100]}"


class ScanStatus(models.Model):
    """Current scan status tracking"""

    STATUS_CHOICES = [
        ("Pending", "Pending"),
        ("Running", "Running"),
        ("Completed", "Completed"),
        ("Failed", "Failed"),
    ]

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="Pending")
    progress = models.IntegerField(default=0)
    message = models.TextField(blank=True, null=True)
    started = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    # Resume tracking
    last_processed_file = models.TextField(blank=True, null=True)
    total_files = models.IntegerField(default=0)
    processed_files = models.IntegerField(default=0)
    scan_folders = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.status} ({self.progress}%) at {self.updated.strftime('%Y-%m-%d %H:%M:%S')}"


class ScanHistory(models.Model):
    """Track completed scans and their detailed outcomes"""

    SCAN_TYPES = [
        ("scan", "Initial Scan"),
        ("rescan", "Rescan"),
        ("resume", "Resume Scan"),
    ]

    STATUS_CHOICES = [
        ("completed", "Completed Successfully"),
        ("failed", "Failed"),
        ("cancelled", "Cancelled"),
        ("partial", "Partially Completed"),
    ]

    job_id = models.CharField(max_length=100, unique=True)
    scan_type = models.CharField(max_length=20, choices=SCAN_TYPES, default="scan")
    folder_path = models.TextField()
    folder_name = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)

    # Timing
    started_at = models.DateTimeField()
    completed_at = models.DateTimeField()
    duration_seconds = models.IntegerField()

    # Statistics
    total_files_found = models.IntegerField(default=0)
    files_processed = models.IntegerField(default=0)
    files_skipped = models.IntegerField(default=0)
    files_failed = models.IntegerField(default=0)

    books_added = models.IntegerField(default=0)
    books_updated = models.IntegerField(default=0)
    books_removed = models.IntegerField(default=0)

    warnings_count = models.IntegerField(default=0)
    errors_count = models.IntegerField(default=0)

    external_apis_used = models.BooleanField(default=False)
    api_requests_made = models.IntegerField(default=0)

    error_message = models.TextField(blank=True, null=True)
    summary = models.TextField(blank=True, null=True)
    metadata_json = models.JSONField(default=dict)

    scan_folder = models.ForeignKey("ScanFolder", on_delete=models.CASCADE, null=True, blank=True)

    class Meta:
        ordering = ["-completed_at", "-started_at"]
        verbose_name = "Scan History Entry"
        verbose_name_plural = "Scan History Entries"
        indexes = [
            models.Index(fields=["job_id"]),
            models.Index(fields=["status"]),
            models.Index(fields=["-completed_at"]),
        ]

    def __str__(self):
        return f"{self.scan_type.title()} of '{self.folder_name}' - {self.status} ({self.completed_at.strftime('%Y-%m-%d %H:%M')})"

    @property
    def success_rate(self):
        """Calculate success rate"""
        if self.total_files_found == 0:
            return 0
        return (self.files_processed / self.total_files_found) * 100

    @property
    def duration_formatted(self):
        """Get human-readable duration"""
        minutes, seconds = divmod(self.duration_seconds, 60)
        hours, minutes = divmod(minutes, 60)

        if hours > 0:
            return f"{hours}h {minutes}m {seconds}s"
        elif minutes > 0:
            return f"{minutes}m {seconds}s"
        else:
            return f"{seconds}s"

    def generate_summary(self):
        """Generate human-readable summary"""
        parts = []

        if self.status == "completed":
            parts.append(f"✅ Successfully processed {self.files_processed} files")
        elif self.status == "failed":
            parts.append("❌ Scan failed")
        elif self.status == "cancelled":
            parts.append("⏹️ Scan was cancelled")
        elif self.status == "partial":
            parts.append(f"⚠️ Partially completed: {self.files_processed}/{self.total_files_found} files")

        if self.books_added > 0:
            parts.append(f"📚 Added {self.books_added} new books")
        if self.books_updated > 0:
            parts.append(f"🔄 Updated {self.books_updated} existing books")
        if self.books_removed > 0:
            parts.append(f"🗑️ Removed {self.books_removed} books")
        if self.errors_count > 0:
            parts.append(f"⚠️ {self.errors_count} errors")
        if self.warnings_count > 0:
            parts.append(f"⚠️ {self.warnings_count} warnings")
        if self.external_apis_used and self.api_requests_made > 0:
            parts.append(f"🌐 Made {self.api_requests_made} API requests")

        parts.append(f"⏱️ Duration: {self.duration_formatted}")

        return " • ".join(parts)


class FileOperation(models.Model):
    """Track file operations for complete reversal capability"""

    OPERATION_TYPES = [
        ("rename", "File Rename"),
        ("move", "File Move"),
        ("create_folder", "Folder Creation"),
    ]

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("completed", "Completed"),
        ("failed", "Failed"),
        ("reverted", "Reverted"),
    ]

    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name="file_operations")
    operation_type = models.CharField(max_length=20, choices=OPERATION_TYPES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")

    # Original state
    original_file_path = models.CharField(max_length=1000, blank=True)
    original_cover_path = models.CharField(max_length=1000, blank=True)
    original_opf_path = models.CharField(max_length=1000, blank=True)
    original_folder_path = models.CharField(max_length=1000, blank=True)

    # New state
    new_file_path = models.CharField(max_length=1000, blank=True)
    new_cover_path = models.CharField(max_length=1000, blank=True)
    new_opf_path = models.CharField(max_length=1000, blank=True)
    new_folder_path = models.CharField(max_length=1000, blank=True)

    # Additional files affected
    additional_files = models.TextField(default="[]")

    # Operation metadata
    operation_date = models.DateTimeField(auto_now_add=True)
    batch_id = models.UUIDField(null=True, blank=True)
    notes = models.TextField(blank=True)
    error_message = models.TextField(blank=True)

    user = models.ForeignKey("auth.User", on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        db_table = "books_fileoperation"
        ordering = ["-operation_date"]
        indexes = [
            models.Index(fields=["-operation_date"]),
            models.Index(fields=["book", "status"]),
            models.Index(fields=["batch_id"]),
        ]

    def __str__(self):
        book_title = self.book.final_metadata.final_title if self.book.final_metadata else f"Book {self.book.id}"
        return f"{self.operation_type} - {book_title} - {self.status}"


class AIFeedback(models.Model):
    """Store user feedback on AI predictions"""

    RATING_CHOICES = [
        (1, "Poor - Completely wrong"),
        (2, "Fair - Some correct elements"),
        (3, "Good - Mostly correct"),
        (4, "Very Good - Almost perfect"),
        (5, "Excellent - Perfect prediction"),
    ]

    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name="ai_feedback")
    user = models.ForeignKey("auth.User", on_delete=models.CASCADE)

    # Original context
    original_filename = models.CharField(max_length=500)
    ai_predictions = models.TextField()
    prediction_confidence = models.FloatField(null=True, blank=True)

    # User corrections
    user_corrections = models.TextField()
    feedback_rating = models.IntegerField(choices=RATING_CHOICES)
    comments = models.TextField(blank=True)

    # Training status
    needs_retraining = models.BooleanField(default=True)
    processed_for_training = models.BooleanField(default=False)

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "books_aifeedback"
        ordering = ["-created_at"]
        unique_together = ["book", "user"]
        indexes = [
            models.Index(fields=["-created_at"]),
            models.Index(fields=["needs_retraining"]),
        ]

    def __str__(self):
        book_title = self.book.final_metadata.final_title if self.book.final_metadata else f"Book {self.book.id}"
        return f"AI Feedback for {book_title} - Rating: {self.feedback_rating}"

    def get_ai_predictions_dict(self):
        """Parse AI predictions JSON safely"""
        import json

        try:
            return json.loads(self.ai_predictions)
        except (json.JSONDecodeError, ValueError):
            return {}

    def get_user_corrections_dict(self):
        """Parse user corrections JSON safely"""
        import json

        try:
            return json.loads(self.user_corrections)
        except (json.JSONDecodeError, ValueError):
            return {}

    def get_accuracy_score(self):
        """Calculate accuracy score based on rating"""
        return (self.feedback_rating - 1) / 4.0


class UserProfile(models.Model):
    """User preferences and settings"""

    THEME_CHOICES = [
        ("flatly", "Flatly"),
        ("cosmo", "Cosmo"),
        ("bootstrap", "Bootstrap Default"),
        ("cerulean", "Cerulean"),
        ("cyborg", "Cyborg"),
        ("darkly", "Darkly"),
        ("journal", "Journal"),
        ("litera", "Litera"),
        ("lumen", "Lumen"),
        ("lux", "Lux"),
        ("materia", "Materia"),
        ("minty", "Minty"),
        ("morph", "Morph"),
        ("pulse", "Pulse"),
        ("quartz", "Quartz"),
        ("sandstone", "Sandstone"),
        ("simplex", "Simplex"),
        ("sketchy", "Sketchy"),
        ("slate", "Slate"),
        ("solar", "Solar"),
        ("spacelab", "Spacelab"),
        ("superhero", "Superhero"),
        ("united", "United"),
        ("vapor", "Vapor"),
        ("yeti", "Yeti"),
        ("zephyr", "Zephyr"),
    ]

    user = models.OneToOneField("auth.User", on_delete=models.CASCADE, related_name="profile")

    # Theme preferences
    theme = models.CharField(max_length=20, choices=THEME_CHOICES, default="flatly")

    # UI preferences
    items_per_page = models.IntegerField(default=50)
    show_covers_in_list = models.BooleanField(default=True)
    default_view_mode = models.CharField(max_length=10, choices=[("table", "Table"), ("grid", "Grid")], default="table")

    # Privacy
    share_reading_progress = models.BooleanField(default=False)

    # Renaming preferences
    default_folder_pattern = models.CharField(
        max_length=500,
        blank=True,
        default="${category}/${author.sortname}/${bookseries.title}",
    )
    default_filename_pattern = models.CharField(
        max_length=500,
        blank=True,
        default="${author.sortname} - ${bookseries.title} #${bookseries.number} - ${title}.${ext}",
    )
    saved_patterns = models.JSONField(default=list, blank=True)
    include_companion_files = models.BooleanField(default=True)

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "books_userprofile"
        verbose_name = "User Profile"
        verbose_name_plural = "User Profiles"

    def __str__(self):
        return f"{self.user.username}'s Profile"

    def save_pattern(self, name, folder_pattern, filename_pattern, description=""):
        """Save a custom renaming pattern"""
        pattern = {
            "name": name,
            "folder": folder_pattern,
            "filename": filename_pattern,
            "description": description,
        }

        # Remove existing pattern with same name
        self.saved_patterns = [p for p in self.saved_patterns if p.get("name") != name]
        self.saved_patterns.append(pattern)
        self.save()

    def remove_pattern(self, name):
        """Remove a saved pattern by name"""
        self.saved_patterns = [p for p in self.saved_patterns if p.get("name") != name]
        self.save()

    def get_pattern(self, name):
        """Get a saved pattern by name"""
        for pattern in self.saved_patterns:
            if pattern.get("name") == name:
                return pattern
        return None

    @classmethod
    def get_or_create_for_user(cls, user):
        """Get or create profile for user"""
        profile, created = cls.objects.get_or_create(user=user)
        return profile


class SetupWizard(models.Model):
    """Track user setup wizard progress"""

    WIZARD_STEPS = [
        ("welcome", "Welcome"),
        ("folders", "Folder Selection"),
        ("content_types", "Content Type Assignment"),
        ("scrapers", "Scraper Configuration"),
        ("complete", "Setup Complete"),
    ]

    user = models.OneToOneField("auth.User", on_delete=models.CASCADE, related_name="setup_wizard")

    # Step completion tracking
    welcome_completed = models.BooleanField(default=False)
    folders_completed = models.BooleanField(default=False)
    content_types_completed = models.BooleanField(default=False)
    scrapers_completed = models.BooleanField(default=False)

    # Overall completion
    is_completed = models.BooleanField(default=False)
    is_skipped = models.BooleanField(default=False)

    # Progress tracking
    current_step = models.CharField(max_length=20, choices=WIZARD_STEPS, default="welcome")

    # Configuration data
    selected_folders = models.JSONField(default=list, blank=True)
    folder_content_types = models.JSONField(default=dict, blank=True)
    scraper_config = models.JSONField(default=dict, blank=True)

    # Timestamps
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    last_step_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "books_setupwizard"
        verbose_name = "Setup Wizard"
        verbose_name_plural = "Setup Wizards"

    def __str__(self):
        return f"Setup Wizard for {self.user.username} - {self.get_current_step_display()}"

    @property
    def progress_percentage(self):
        """Calculate completion percentage"""
        completed_steps = sum(
            [
                self.welcome_completed,
                self.folders_completed,
                self.content_types_completed,
                self.scrapers_completed,
            ]
        )
        return int((completed_steps / 4) * 100)

    @property
    def next_step(self):
        """Get the next step in the wizard"""
        step_order = [choice[0] for choice in self.WIZARD_STEPS]
        try:
            current_index = step_order.index(self.current_step)
            if current_index < len(step_order) - 1:
                return step_order[current_index + 1]
        except ValueError:
            pass
        return "complete"

    @property
    def previous_step(self):
        """Get the previous step in the wizard"""
        step_order = [choice[0] for choice in self.WIZARD_STEPS]
        try:
            current_index = step_order.index(self.current_step)
            if current_index > 0:
                return step_order[current_index - 1]
        except ValueError:
            pass
        return "welcome"

    def mark_step_completed(self, step):
        """Mark a specific step as completed"""
        step_mapping = {
            "welcome": "welcome_completed",
            "folders": "folders_completed",
            "content_types": "content_types_completed",
            "scrapers": "scrapers_completed",
        }

        if step in step_mapping:
            setattr(self, step_mapping[step], True)
            self.current_step = self.next_step

            # Check if wizard is complete
            if all(
                [
                    self.welcome_completed,
                    self.folders_completed,
                    self.content_types_completed,
                    self.scrapers_completed,
                ]
            ):
                self.is_completed = True
                self.completed_at = timezone.now()
                self.current_step = "complete"

            self.save()

    def skip_wizard(self):
        """Mark wizard as skipped"""
        self.is_skipped = True
        self.is_completed = True
        self.completed_at = timezone.now()
        self.current_step = "complete"
        self.save()

    @classmethod
    def get_or_create_for_user(cls, user):
        """Get or create setup wizard for user"""
        wizard, created = cls.objects.get_or_create(user=user)
        return wizard, created


class ScanQueue(models.Model):
    """Model to track pending/future scans"""

    QUEUE_STATUS_CHOICES = [
        ("pending", "Pending"),
        ("scheduled", "Scheduled"),
        ("processing", "Processing"),
        ("completed", "Completed"),
        ("failed", "Failed"),
        ("cancelled", "Cancelled"),
    ]

    SCAN_TYPE_CHOICES = [
        ("folder", "Folder Scan"),
        ("book_ids", "Specific Book IDs"),
        ("series", "Series Scan"),
        ("author", "Author Scan"),
        ("full", "Full Library Scan"),
        ("incremental", "Incremental Scan"),
    ]

    PRIORITY_CHOICES = [
        (1, "Low"),
        (2, "Normal"),
        (3, "High"),
        (4, "Urgent"),
    ]

    # Basic information
    name = models.CharField(max_length=200)
    scan_type = models.CharField(max_length=20, choices=SCAN_TYPE_CHOICES, default="folder")
    status = models.CharField(max_length=20, choices=QUEUE_STATUS_CHOICES, default="pending")
    priority = models.IntegerField(choices=PRIORITY_CHOICES, default=2)

    # Scan parameters
    folder_paths = models.JSONField(default=list, blank=True)
    book_ids = models.JSONField(default=list, blank=True)
    series_names = models.JSONField(default=list, blank=True)
    author_names = models.JSONField(default=list, blank=True)

    # Scan options
    rescan_existing = models.BooleanField(default=False)
    update_metadata = models.BooleanField(default=True)
    fetch_covers = models.BooleanField(default=True)
    deep_scan = models.BooleanField(default=False)

    # Scheduling
    scheduled_for = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey("auth.User", on_delete=models.CASCADE)

    # Execution tracking
    estimated_files = models.IntegerField(default=0)
    estimated_duration = models.IntegerField(default=0)
    actual_scan_job_id = models.CharField(max_length=50, blank=True)

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    # Error tracking
    error_message = models.TextField(blank=True)
    retry_count = models.IntegerField(default=0)
    max_retries = models.IntegerField(default=3)

    class Meta:
        ordering = ["-priority", "created_at"]
        verbose_name = "Scan Queue Item"
        verbose_name_plural = "Scan Queue"
        indexes = [
            models.Index(fields=["status", "priority"]),
            models.Index(fields=["scan_type"]),
            models.Index(fields=["scheduled_for"]),
            models.Index(fields=["created_by"]),
            models.Index(fields=["-created_at"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.get_scan_type_display()}) - {self.get_status_display()}"

    @property
    def target_summary(self):
        """Generate a summary of what will be scanned"""
        targets = []

        if self.scan_type == "folder" and self.folder_paths:
            folder_count = len(self.folder_paths)
            if folder_count == 1:
                targets.append(f"📁 {self.folder_paths[0]}")
            else:
                targets.append(f"📁 {folder_count} folders")

        elif self.scan_type == "book_ids" and self.book_ids:
            targets.append(f"📚 {len(self.book_ids)} specific books")

        elif self.scan_type == "series" and self.series_names:
            if len(self.series_names) == 1:
                targets.append(f"📑 Series: {self.series_names[0]}")
            else:
                targets.append(f"📑 {len(self.series_names)} series")

        elif self.scan_type == "author" and self.author_names:
            if len(self.author_names) == 1:
                targets.append(f"✍️ Author: {self.author_names[0]}")
            else:
                targets.append(f"✍️ {len(self.author_names)} authors")

        elif self.scan_type == "full":
            targets.append("🗂️ Full library scan")

        elif self.scan_type == "incremental":
            targets.append("⚡ Incremental scan")

        return " | ".join(targets) if targets else "No targets specified"

    @property
    def options_summary(self):
        """Generate a summary of scan options"""
        options = []
        if self.rescan_existing:
            options.append("♻️ Rescan existing")
        if self.update_metadata:
            options.append("🔄 Update metadata")
        if self.fetch_covers:
            options.append("🖼️ Fetch covers")
        if self.deep_scan:
            options.append("🔍 Deep scan")
        return " | ".join(options) if options else "Standard options"

    @property
    def is_ready_to_execute(self):
        """Check if this queue item is ready to be executed"""
        if self.status != "pending":
            return False
        if self.scheduled_for and timezone.now() < self.scheduled_for:
            return False
        return True

    @property
    def priority_display(self):
        """Get priority with emoji indicator"""
        priority_icons = {1: "⬇️", 2: "➡️", 3: "⬆️", 4: "🔴"}
        return f"{priority_icons.get(self.priority, '➡️')} {self.get_priority_display()}"

    @property
    def estimated_duration_formatted(self):
        """Get human-readable estimated duration"""
        if self.estimated_duration <= 0:
            return "Unknown"

        seconds = self.estimated_duration
        hours, remainder = divmod(seconds, 3600)
        minutes, seconds = divmod(remainder, 60)

        if hours > 0:
            return f"{hours}h {minutes}m"
        elif minutes > 0:
            return f"{minutes}m"
        else:
            return f"{seconds}s"

    def can_retry(self):
        """Check if this item can be retried"""
        return self.status in ["failed", "cancelled"] and self.retry_count < self.max_retries

    def mark_processing(self, job_id):
        """Mark this queue item as currently processing"""
        self.status = "processing"
        self.actual_scan_job_id = job_id
        self.started_at = timezone.now()
        self.save(update_fields=["status", "actual_scan_job_id", "started_at", "updated_at"])

    def mark_completed(self):
        """Mark this queue item as completed"""
        self.status = "completed"
        self.completed_at = timezone.now()
        self.save(update_fields=["status", "completed_at", "updated_at"])

    def mark_failed(self, error_message=""):
        """Mark this queue item as failed"""
        self.status = "failed"
        self.error_message = error_message
        self.retry_count += 1
        self.completed_at = timezone.now()
        self.save(
            update_fields=[
                "status",
                "error_message",
                "retry_count",
                "completed_at",
                "updated_at",
            ]
        )


# API Access Tracking Models for Intelligent Scanning


class APIAccessLog(HashFieldMixin, models.Model):
    """Tracks API access attempts and results for each book"""

    # API Status Choices
    SUCCESS = "success"
    RATE_LIMITED = "rate_limited"
    FAILED = "failed"
    NOT_ATTEMPTED = "not_attempted"

    STATUS_CHOICES = [
        (SUCCESS, "Success"),
        (RATE_LIMITED, "Rate Limited"),
        (FAILED, "Failed"),
        (NOT_ATTEMPTED, "Not Attempted"),
    ]

    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name="api_access_logs")
    data_source = models.ForeignKey(DataSource, on_delete=models.CASCADE, related_name="api_access_logs")

    # Access tracking
    last_attempt = models.DateTimeField(null=True, blank=True)
    last_success = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=NOT_ATTEMPTED)

    # Attempt statistics
    total_attempts = models.IntegerField(default=0)
    successful_attempts = models.IntegerField(default=0)
    failed_attempts = models.IntegerField(default=0)
    rate_limited_attempts = models.IntegerField(default=0)

    # Result tracking
    metadata_retrieved = models.BooleanField(default=False)
    cover_retrieved = models.BooleanField(default=False)
    items_found = models.IntegerField(default=0, help_text="Number of metadata items retrieved")

    # Quality metrics
    confidence_score = models.FloatField(
        default=0.0,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text="Average confidence of retrieved metadata",
    )

    # Error tracking
    last_error = models.TextField(blank=True, help_text="Last error message if any")
    consecutive_failures = models.IntegerField(default=0)

    # Scheduling
    next_retry_after = models.DateTimeField(null=True, blank=True)
    should_retry = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ["book", "data_source"]
        ordering = ["-last_attempt"]
        indexes = [
            models.Index(fields=["book", "status"]),
            models.Index(fields=["data_source", "status"]),
            models.Index(fields=["status", "should_retry"]),
            models.Index(fields=["next_retry_after"]),
        ]

    def __str__(self):
        return f"{self.book.title} - {self.data_source.name}: {self.status}"

    @property
    def success_rate(self):
        """Calculate success rate percentage"""

        if self.total_attempts == 0:
            return 0.0
        return (self.successful_attempts / self.total_attempts) * 100

    @property
    def is_healthy(self):
        """Check if this API source is healthy for this book"""
        return self.consecutive_failures < 3 and (self.success_rate >= 50 or self.total_attempts < 2)

    @property
    def can_retry_now(self):
        """Check if we can retry this API now"""
        if not self.should_retry:
            return False
        if self.next_retry_after and timezone.now() < self.next_retry_after:
            return False
        return True

    def record_attempt(
        self,
        success=True,
        error_message="",
        items_found=0,
        confidence=0.0,
        metadata_retrieved=False,
        cover_retrieved=False,
    ):
        """Record an API access attempt"""
        from datetime import timedelta

        self.last_attempt = timezone.now()
        self.total_attempts += 1

        if success:
            self.status = self.SUCCESS
            self.successful_attempts += 1
            self.last_success = timezone.now()
            self.consecutive_failures = 0
            self.items_found += items_found
            self.metadata_retrieved = self.metadata_retrieved or metadata_retrieved
            self.cover_retrieved = self.cover_retrieved or cover_retrieved

            # Update confidence score (weighted average)
            if confidence > 0:
                total_weight = self.successful_attempts
                current_weight = self.successful_attempts - 1
                if total_weight > 0:
                    self.confidence_score = (self.confidence_score * current_weight + confidence) / total_weight
                else:
                    self.confidence_score = confidence

            self.next_retry_after = None

        else:
            self.failed_attempts += 1
            self.consecutive_failures += 1
            self.last_error = error_message

            if "rate limit" in error_message.lower():
                self.status = self.RATE_LIMITED
                self.rate_limited_attempts += 1
                # Exponential backoff for rate limits
                backoff_hours = min(24, 2 ** min(self.rate_limited_attempts, 8))
                self.next_retry_after = timezone.now() + timedelta(hours=backoff_hours)
            else:
                self.status = self.FAILED
                # Shorter backoff for other failures
                backoff_minutes = min(360, 30 * self.consecutive_failures)
                self.next_retry_after = timezone.now() + timedelta(minutes=backoff_minutes)

            # Stop retrying if too many consecutive failures
            if self.consecutive_failures >= 5:
                self.should_retry = False

        self.save()

    def reset_retry_state(self):
        """Reset retry state to allow new attempts"""
        self.should_retry = True
        self.consecutive_failures = 0
        self.next_retry_after = None
        self.save()


class ScanSession(HashFieldMixin, models.Model):
    """Tracks scanning sessions and their API usage patterns"""

    session_id = models.CharField(max_length=100, unique=True)
    scan_folder = models.ForeignKey(
        ScanFolder,
        on_delete=models.CASCADE,
        related_name="scan_sessions",
        null=True,
        blank=True,
    )

    # Session configuration
    external_apis_enabled = models.BooleanField(default=True)
    enabled_sources = models.JSONField(default=list, help_text="List of enabled data source names")

    # Progress tracking
    total_books = models.IntegerField(default=0)
    processed_books = models.IntegerField(default=0)
    books_with_external_data = models.IntegerField(default=0)

    # API usage during session
    api_calls_made = models.JSONField(default=dict, help_text="Count of API calls per source")
    api_failures = models.JSONField(default=dict, help_text="Count of failures per source")
    rate_limits_hit = models.JSONField(default=dict, help_text="Rate limit incidents per source")

    # Session status
    is_active = models.BooleanField(default=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    was_interrupted = models.BooleanField(default=False)

    # Resumption tracking
    can_resume = models.BooleanField(default=False)
    resume_queue = models.JSONField(default=list, help_text="List of book IDs needing API data")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["is_active", "can_resume"]),
            models.Index(fields=["session_id"]),
        ]

    def __str__(self):
        return f"Scan Session {self.session_id} - {self.processed_books}/{self.total_books}"

    @property
    def completion_percentage(self):
        """Calculate completion percentage"""
        if self.total_books == 0:
            return 0.0
        return (self.processed_books / self.total_books) * 100

    @property
    def external_data_percentage(self):
        """Calculate percentage of books with external data"""
        if self.processed_books == 0:
            return 0.0
        return (self.books_with_external_data / self.processed_books) * 100

    def add_book_to_resume_queue(self, book_id, missing_sources=None):
        """Add a book to the resumption queue"""
        book_data = {
            "book_id": book_id,
            "missing_sources": missing_sources or [],
            "added_at": timezone.now().isoformat(),
        }

        # Avoid duplicates
        existing_ids = [item["book_id"] for item in self.resume_queue]
        if book_id not in existing_ids:
            self.resume_queue.append(book_data)
            self.can_resume = True
            self.save(update_fields=["resume_queue", "can_resume"])

    def remove_book_from_resume_queue(self, book_id):
        """Remove a book from the resumption queue"""
        self.resume_queue = [item for item in self.resume_queue if item["book_id"] != book_id]
        self.can_resume = len(self.resume_queue) > 0
        self.save(update_fields=["resume_queue", "can_resume"])

    def record_api_call(self, source_name, success=True, rate_limited=False):
        """Record an API call during this session"""
        # Initialize counters if needed
        if source_name not in self.api_calls_made:
            self.api_calls_made[source_name] = 0
        if source_name not in self.api_failures:
            self.api_failures[source_name] = 0
        if source_name not in self.rate_limits_hit:
            self.rate_limits_hit[source_name] = 0

        self.api_calls_made[source_name] += 1

        if not success:
            self.api_failures[source_name] += 1

        if rate_limited:
            self.rate_limits_hit[source_name] += 1

        self.save(update_fields=["api_calls_made", "api_failures", "rate_limits_hit"])


class BookAPICompleteness(models.Model):
    """Tracks API completeness for each book to optimize future scans"""

    book = models.OneToOneField(
        Book,
        on_delete=models.CASCADE,
        related_name="api_completeness",
        primary_key=True,
    )

    # Source completion tracking
    google_books_complete = models.BooleanField(default=False)
    open_library_complete = models.BooleanField(default=False)
    goodreads_complete = models.BooleanField(default=False)

    # Last successful access
    google_books_last_success = models.DateTimeField(null=True, blank=True)
    open_library_last_success = models.DateTimeField(null=True, blank=True)
    goodreads_last_success = models.DateTimeField(null=True, blank=True)

    # Metadata completeness scores
    metadata_completeness = models.FloatField(
        default=0.0,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text="Overall metadata completeness (0.0-1.0)",
    )

    # Priority for next scan
    scan_priority = models.CharField(
        max_length=20,
        choices=[
            ("high", "High - Missing critical data"),
            ("medium", "Medium - Some data missing"),
            ("low", "Low - Mostly complete"),
            ("complete", "Complete - All sources accessed"),
        ],
        default="high",
    )

    needs_external_scan = models.BooleanField(default=True)
    missing_sources = models.JSONField(default=list, help_text="List of sources that need to be attempted")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["scan_priority", "needs_external_scan"]),
            models.Index(fields=["metadata_completeness"]),
        ]

    def __str__(self):
        return f"{self.book.title} - Completeness: {self.metadata_completeness:.2f}"

    def calculate_completeness(self):
        """Calculate overall metadata completeness based on available data"""
        from books.constants import COMPLETENESS_THRESHOLDS, METADATA_SOURCE_WEIGHTS

        weights = METADATA_SOURCE_WEIGHTS

        total_score = 0.0
        for source_name, weight in weights.items():
            field_name = f"{source_name.lower().replace(' ', '_')}_complete"
            if hasattr(self, field_name) and getattr(self, field_name):
                total_score += weight

        self.metadata_completeness = total_score

        # Update scan priority using thresholds from constants
        if self.metadata_completeness >= COMPLETENESS_THRESHOLDS["complete"]:
            self.scan_priority = "complete"
            self.needs_external_scan = False
        elif self.metadata_completeness >= COMPLETENESS_THRESHOLDS["low"]:
            self.scan_priority = "low"
        elif self.metadata_completeness >= COMPLETENESS_THRESHOLDS["medium"]:
            self.scan_priority = "medium"
        else:
            self.scan_priority = "high"

        self.save(
            update_fields=[
                "metadata_completeness",
                "scan_priority",
                "needs_external_scan",
            ]
        )

    def mark_source_complete(self, source_name):
        """Mark a specific source as complete"""
        field_mapping = {
            "Google Books": "google_books_complete",
            "Open Library": "open_library_complete",
        }

        date_mapping = {
            "Google Books": "google_books_last_success",
            "Open Library": "open_library_last_success",
        }

        if source_name in field_mapping:
            setattr(self, field_mapping[source_name], True)
            setattr(self, date_mapping[source_name], timezone.now())

            # Remove from missing sources
            if source_name in self.missing_sources:
                self.missing_sources.remove(source_name)

            self.calculate_completeness()

    def add_missing_source(self, source_name):
        """Add a source to the missing list"""
        if source_name not in self.missing_sources:
            self.missing_sources.append(source_name)
            self.needs_external_scan = True
            self.save(update_fields=["missing_sources", "needs_external_scan"])
