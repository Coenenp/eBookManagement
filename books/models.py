"""Django models for ebook library management.

This module defines the database models for managing ebooks, metadata,
authors, publishers, genres, and scan operations. Includes comprehensive
relationship management and final metadata synchronization.
"""
from django.db import models
from django.utils import timezone
from .mixins.sync import FinalMetadataSyncMixin
from .mixins.metadata import SourceConfidenceMixin, HashFieldMixin
from django.core.validators import MinValueValidator, MaxValueValidator
from books.utils.language import normalize_language
import os

import logging

logger = logging.getLogger('books.scanner')
logger.debug("Logger is working!")

LANGUAGE_CHOICES = [
    ('en', 'English'),
    ('fr', 'French'),
    ('de', 'German'),
    ('nl', 'Dutch'),
    ('es', 'Spanish'),
    ('it', 'Italian'),
    ('pt', 'Portuguese'),
    ('ja', 'Japanese'),
    ('ko', 'Korean'),
    ('zh', 'Chinese'),
    ('ru', 'Russian'),
    ('pl', 'Polish'),
    ('he', 'Hebrew'),
    ('hu', 'Hungarian'),
    ('tr', 'Turkish'),
    ('ca', 'Catalan'),
    ('id', 'Indonesian'),
]


class DataSource(models.Model):
    """Sources of metadata (filename, internal, API, etc.)"""
    FILENAME = 'Filename'
    EPUB_INTERNAL = 'EPUB'
    MOBI_INTERNAL = 'MOBI'
    PDF_INTERNAL = 'PDF'
    OPF_FILE = 'OPF File'
    OPEN_LIBRARY = 'Open Library'
    GOOGLE_BOOKS = 'Google Books'
    COMICVINE = 'Comic Vine'
    OPEN_LIBRARY_COVERS = 'Open Library Covers'
    GOOGLE_BOOKS_COVERS = 'Google Books Covers'
    ORIGINAL_SCAN = 'Original Scan'
    MANUAL = 'Manual Entry'
    CONTENT_SCAN = 'ISBN Content Scan'

    SOURCE_CHOICES = [
        (FILENAME, 'Filename'),
        (EPUB_INTERNAL, 'EPUB'),
        (MOBI_INTERNAL, 'MOBI'),
        (PDF_INTERNAL, 'PDF'),
        (OPF_FILE, 'OPF File'),
        (OPEN_LIBRARY, 'Open Library'),
        (GOOGLE_BOOKS, 'Google Books'),
        (COMICVINE, 'Comic Vine'),
        (OPEN_LIBRARY_COVERS, 'Open Library Covers'),
        (GOOGLE_BOOKS_COVERS, 'Google Books Covers'),
        (ORIGINAL_SCAN, 'Original Scan'),
        (MANUAL, 'Manual Entry'),
        (CONTENT_SCAN, 'ISBN Content Scan'),
    ]

    # Enforce unique names for canonical data sources; tests and bootstrap rely on uniqueness
    name = models.CharField(max_length=50, choices=SOURCE_CHOICES, unique=True)
    trust_level = models.FloatField(
        default=0.5,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text="Trust level for this source (0.0-1.0)"
    )

    priority = models.IntegerField(default=1, help_text="Source priority for ordering")
    is_active = models.BooleanField(default=True, help_text="Whether this source is active")

    def __str__(self):
        return self.get_name_display()

    @property
    def title_count(self):
        """Count of titles from this data source"""
        return self.booktitle_set.filter(is_active=True).count()

    @property
    def author_count(self):
        """Count of authors from this data source"""
        return self.bookauthor_set.filter(is_active=True).count()

    @property
    def genre_count(self):
        """Count of genres from this data source"""
        return self.bookgenre_set.filter(is_active=True).count()

    @property
    def series_count(self):
        """Count of series from this data source"""
        return self.bookseries_set.filter(is_active=True).count()

    @property
    def cover_count(self):
        """Count of covers from this data source"""
        return self.bookcover_set.filter(is_active=True).count()

    @property
    def metadata_count(self):
        """Total count of all metadata entries from this data source"""
        return (
            self.title_count +
            self.author_count +
            self.genre_count +
            self.series_count +
            self.cover_count
        )

    class Meta:
        ordering = ['-trust_level', 'name']


class ScanFolder(models.Model):
    CONTENT_TYPE_CHOICES = [
        ('ebooks', '📘 Ebooks'),
        ('comics', '🖼️ Comics'),
        ('audiobooks', '🔊 Audiobooks'),
    ]

    name = models.CharField(max_length=100, default='Untitled', blank=False, null=False)
    path = models.CharField(max_length=500)
    content_type = models.CharField(
        max_length=20,
        choices=CONTENT_TYPE_CHOICES,
        default='ebooks',
        help_text="Type of content in this scan folder"
    )
    language = models.CharField(max_length=10, choices=LANGUAGE_CHOICES, default='en')
    is_active = models.BooleanField(default=True)
    last_scanned = models.DateTimeField(null=True, blank=True)
    # Optional: created_at for admin tracking
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.get_content_type_display()})"

    def count_files_on_disk(self):
        """Count ebook files recursively in the scan folder path on disk"""
        import os
        import glob

        if not os.path.exists(self.path):
            return 0

        # Define file patterns based on content type
        if self.content_type == 'comics':
            # Comics include traditional formats AND PDFs (many comics are distributed as PDFs)
            patterns = ['**/*.cbr', '**/*.cbz', '**/*.cb7', '**/*.cbt', '**/*.pdf']
        elif self.content_type == 'audiobooks':
            patterns = ['**/*.mp3', '**/*.m4a', '**/*.m4b', '**/*.aac', '**/*.flac', '**/*.ogg', '**/*.wav']
        elif self.content_type == 'ebooks':
            # Ebooks include all digital book formats
            patterns = ['**/*.epub', '**/*.pdf', '**/*.mobi', '**/*.azw', '**/*.azw3', '**/*.fb2', '**/*.lit', '**/*.prc']
        else:
            # Default to ebook patterns for unknown types
            patterns = ['**/*.epub', '**/*.pdf', '**/*.mobi', '**/*.azw', '**/*.azw3', '**/*.fb2']

        file_count = 0
        for pattern in patterns:
            try:
                files = glob.glob(os.path.join(self.path, pattern), recursive=True)
                file_count += len(files)
            except (OSError, PermissionError):
                # Handle cases where we can't access the directory
                continue

        return file_count

    def get_scan_progress_info(self):
        """Get information about scan progress (scanned vs total files)"""
        scanned_count = self.book_set.count()
        total_files = self.count_files_on_disk()

        if total_files == 0:
            percentage = 100 if scanned_count == 0 else 0
        else:
            percentage = (scanned_count / total_files) * 100

        return {
            'scanned': scanned_count,
            'total_files': total_files,
            'percentage': round(percentage, 1),
            'needs_scan': total_files > scanned_count
        }


class Book(HashFieldMixin, models.Model):
    """Main book record with file paths"""
    FORMAT_CHOICES = [
        ('epub', 'EPUB'),
        ('mobi', 'MOBI'),
        ('pdf', 'PDF'),
        ('cbr', 'CBR'),
        ('cbz', 'CBZ'),
        ('placeholder', 'Placeholder'),
    ]

    file_path = models.CharField(max_length=1000, help_text="Full file path")  # Consistent with BookCover.cover_path
    file_path_hash = models.CharField(max_length=64, unique=True, editable=False, default='')  # SHA256 hash for uniqueness
    file_format = models.CharField(max_length=20, choices=FORMAT_CHOICES)
    file_size = models.BigIntegerField(null=True, blank=True)
    cover_path = models.CharField(max_length=1000, blank=True, help_text="Local cover file path")  # Consistent field type
    opf_path = models.CharField(max_length=1000, blank=True, help_text="OPF metadata file path")  # Consistent field type

    # Scan metadata
    first_scanned = models.DateTimeField(auto_now_add=True)
    last_scanned = models.DateTimeField(auto_now=True)
    scan_folder = models.ForeignKey(ScanFolder, on_delete=models.CASCADE, null=True)

    # Status flags
    is_placeholder = models.BooleanField(default=False)
    is_duplicate = models.BooleanField(default=False)
    is_corrupted = models.BooleanField(default=False)
    is_available = models.BooleanField(default=True, help_text="Whether the book file is still available on disk")
    last_scan_status = models.CharField(max_length=20, blank=True, null=True, help_text="Status from last scan: 'found', 'removed', 'updated'")

    def save(self, *args, **kwargs):
        """Generate hash of file_path for unique constraint"""
        from django.db import IntegrityError

        if self.file_path:
            self.file_path_hash = self.generate_hash(self.file_path)

        try:
            super().save(*args, **kwargs)
        except IntegrityError as e:
            if 'file_path_hash' in str(e):
                # Handle duplicate file_path_hash by checking if book already exists
                import logging
                logger = logging.getLogger("books.models")
                logger.warning(f"Duplicate file_path_hash for {self.file_path}: {e}")

                # If this is an update operation (book has pk), check if file_path changed
                if self.pk:
                    existing = Book.objects.get(pk=self.pk)
                    if existing.file_path != self.file_path:
                        # File path changed and conflicts with another book
                        raise IntegrityError(f"File path {self.file_path} already exists in database")
                else:
                    # New book creation - check if book already exists
                    try:
                        existing_book = Book.objects.get(file_path_hash=self.file_path_hash)
                        raise IntegrityError(f"Book with file path {self.file_path} already exists (ID: {existing_book.id})")
                    except Book.DoesNotExist:
                        # Hash collision or other integrity issue
                        raise
            else:
                # Different integrity error
                raise

    @classmethod
    def get_or_create_by_path(cls, file_path, defaults=None):
        """Get or create book by file path, using hash for lookup"""
        from django.db import IntegrityError

        # Create a temporary instance to use the generate_hash method
        temp_instance = cls()
        file_path_hash = temp_instance.generate_hash(file_path)

        try:
            book = cls.objects.get(file_path_hash=file_path_hash)
            return book, False
        except cls.DoesNotExist:
            if defaults is None:
                defaults = {}
            defaults['file_path'] = file_path
            defaults['file_path_hash'] = file_path_hash

            try:
                book = cls.objects.create(**defaults)
                return book, True
            except IntegrityError:
                # Handle race condition where another process created the book
                # between our check and creation attempt
                try:
                    book = cls.objects.get(file_path_hash=file_path_hash)
                    return book, False
                except cls.DoesNotExist:
                    # If still not found, there might be a different integrity issue
                    # Try with a slightly modified path to avoid infinite loops
                    import logging
                    logger = logging.getLogger("books.models")
                    logger.warning(f"Integrity error creating book for path: {file_path}")
                    raise

    def __str__(self):
        if self.is_placeholder:
            return f"Placeholder: {os.path.basename(self.file_path)}"
        return os.path.basename(self.file_path)

    @property
    def filename(self):
        return os.path.basename(self.file_path)

    @property
    def final_metadata(self):
        try:
            return self.finalmetadata
        except FinalMetadata.DoesNotExist:
            return None

    @property
    def relative_path(self):
        import os

        if self.scan_folder and self.scan_folder.path and self.file_path:
            scan_root = os.path.normpath(self.scan_folder.path)
            full_path = os.path.normpath(self.file_path)
            # Trim scan folder prefix
            subpath = full_path.replace(scan_root, '').lstrip(os.sep)
            # Remove the filename from the subpath
            return os.path.dirname(subpath)
        return ''

    class Meta:
        ordering = ['-last_scanned', 'file_path']


class Author(models.Model):
    """Normalized author names with first and last name support"""
    name = models.CharField(max_length=200)
    first_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100, blank=True)
    name_normalized = models.CharField(max_length=200, db_index=True, unique=True)
    is_reviewed = models.BooleanField(default=False, help_text="Mark authors you've verified or finalized")

    def save(self, *args, **kwargs):
        from books.utils.authors import parse_author_name, normalize_author_name

        # Ensure name field is populated from first_name and last_name if name is empty
        if not self.name and (self.first_name or self.last_name):
            name_parts = []
            if self.first_name:
                name_parts.append(self.first_name.strip())
            if self.last_name:
                name_parts.append(self.last_name.strip())
            self.name = " ".join(name_parts)

        # Only extract if first and last aren't already set
        if not (self.first_name and self.last_name):
            self.first_name, self.last_name = parse_author_name(self.name)

        # Now normalize the name after we have proper first_name and last_name
        self.name_normalized = normalize_author_name(f"{self.first_name} {self.last_name}")

        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["first_name", "last_name"],
                name="unique_author_name_combo"
            )
        ]


class BookAuthor(FinalMetadataSyncMixin, SourceConfidenceMixin, models.Model):
    """M2M relationship between books and authors with source tracking"""
    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name='bookauthor')
    author = models.ForeignKey(Author, on_delete=models.CASCADE)
    is_main_author = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.post_deactivation_sync()

    class Meta:
        unique_together = ['book', 'author', 'source']
        ordering = ['-confidence', '-is_main_author']


class BookTitle(FinalMetadataSyncMixin, SourceConfidenceMixin, models.Model):
    """Book titles from different sources"""
    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name='titles')
    title = models.CharField(max_length=500)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.post_deactivation_sync()

    def __str__(self):
        return f"{self.title} ({self.source})"

    class Meta:
        unique_together = ['book', 'title', 'source']
        ordering = ['-confidence']


class BookCover(FinalMetadataSyncMixin, SourceConfidenceMixin, HashFieldMixin, models.Model):
    """Book covers from different sources with metadata"""
    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name='covers')
    cover_path = models.CharField(max_length=1000, help_text="Local file path or URL")
    cover_path_hash = models.CharField(max_length=64, editable=False)  # SHA256 hash for uniqueness

    # Cover metadata
    width = models.IntegerField(null=True, blank=True)
    height = models.IntegerField(null=True, blank=True)
    file_size = models.BigIntegerField(null=True, blank=True)
    format = models.CharField(max_length=10, blank=True, help_text="jpg, png, gif, etc.")

    # Quality indicators
    is_high_resolution = models.BooleanField(default=False)
    aspect_ratio = models.FloatField(null=True, blank=True)

    # Status flags (is_active and created_at are provided by SourceConfidenceMixin)

    def save(self, *args, **kwargs):
        # Generate hash of cover_path for uniqueness constraints
        self.cover_path_hash = self.generate_hash(self.cover_path)

        # Calculate aspect ratio if width and height are available
        if self.width and self.height:
            self.aspect_ratio = self.width / self.height
            # Consider high resolution if width >= 600 or height >= 800
            self.is_high_resolution = self.width >= 600 or self.height >= 800
        super().save(*args, **kwargs)

        # Trigger FinalMetadata re-sync
        self.post_deactivation_sync()

    def __str__(self):
        return f"Cover for {self.book.filename} from {self.source} ({self.confidence:.2f})"

    @property
    def is_local_file(self):
        """Check if cover is a local file path vs URL"""
        return not (self.cover_path.startswith('http://') or self.cover_path.startswith('https://'))

    @property
    def resolution_str(self):
        """Human readable resolution string"""
        if self.width and self.height:
            return f"{self.width}x{self.height}"
        return "Unknown"

    class Meta:
        unique_together = ['book', 'cover_path_hash', 'source']
        ordering = ['-confidence', '-is_high_resolution', '-width']


class Series(models.Model):
    """Book series"""
    name = models.CharField(max_length=200, unique=True)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['name']
        verbose_name_plural = "Series"


class BookSeries(FinalMetadataSyncMixin, SourceConfidenceMixin, models.Model):
    """Book series information with source tracking"""
    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name='series_info')
    series = models.ForeignKey(Series, on_delete=models.CASCADE, null=True, blank=True)
    series_number = models.CharField(max_length=20, null=True, blank=True)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.post_deactivation_sync()

    class Meta:
        unique_together = ['book', 'series', 'source']
        ordering = ['-confidence']
        verbose_name_plural = "Book Series"


class Genre(models.Model):
    """Book genres/categories"""
    name = models.CharField(max_length=100, unique=True)
    is_reviewed = models.BooleanField(default=False, help_text="Mark genres you've verified or finalized")

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['name']


class BookGenre(models.Model):
    """M2M relationship between books and genres with source tracking"""
    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name='bookgenre')
    genre = models.ForeignKey(Genre, on_delete=models.CASCADE)
    source = models.ForeignKey(DataSource, on_delete=models.CASCADE)
    confidence = models.FloatField(
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)]
    )
    is_active = models.BooleanField(default=True, help_text="Uncheck to hide this without deleting it.")
    created_at = models.DateTimeField(auto_now_add=True)

    @classmethod
    def create_or_update_best(cls, book, genre, source, confidence=1.0, is_active=True):
        """
        Create or update BookGenre with best source and confidence.
        If a BookGenre for this book+genre already exists, compare sources and confidence.
        Keep the entry with the highest trust level + confidence combination.
        """
        from django.db import transaction

        with transaction.atomic():
            # Check if any BookGenre exists for this book+genre combination
            existing_entries = cls.objects.filter(book=book, genre=genre)

            if not existing_entries.exists():
                # No existing entry, create new one
                return cls.objects.create(
                    book=book,
                    genre=genre,
                    source=source,
                    confidence=confidence,
                    is_active=is_active
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
                best_existing.save()

                # Deactivate other entries for the same book+genre
                existing_entries.exclude(id=best_existing.id).update(is_active=False)

                logger.debug(f"Updated BookGenre {best_existing.id} for book {book.id}, genre '{genre.name}' "
                             f"with better source '{source.name}' (score: {new_score:.3f} vs {best_existing_score:.3f})")
                return best_existing
            else:
                # Existing entry is better or equal, just ensure it's active
                if not best_existing.is_active:
                    best_existing.is_active = True
                    best_existing.save()

                logger.debug(f"Kept existing BookGenre {best_existing.id} for book {book.id}, genre '{genre.name}' "
                             f"(existing score: {best_existing_score:.3f} vs new: {new_score:.3f})")
                return best_existing

    class Meta:
        unique_together = ['book', 'genre', 'source']


class Publisher(models.Model):
    name = models.CharField(max_length=255, unique=True)
    is_reviewed = models.BooleanField(default=False, help_text="Mark publishers you've verified or finalized")

    def __str__(self):
        return self.name


class BookPublisher(FinalMetadataSyncMixin, SourceConfidenceMixin, models.Model):
    """M2M relationship between books and publishers with source tracking."""
    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name='bookpublisher')
    publisher = models.ForeignKey(Publisher, on_delete=models.CASCADE, related_name='publisher_books')

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.post_deactivation_sync()

    def __str__(self):
        title = getattr(self.book.finalmetadata, "final_title", "Untitled")
        return f"{title} → {self.publisher.name} ({self.source.name})"

    class Meta:
        unique_together = ['book', 'publisher', 'source']
        ordering = ['-confidence']


class BookMetadata(FinalMetadataSyncMixin, SourceConfidenceMixin, HashFieldMixin, models.Model):
    """Additional metadata fields with source tracking"""
    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name='metadata')
    field_name = models.CharField(max_length=100)
    field_value = models.TextField()
    field_value_hash = models.CharField(max_length=64, editable=False)  # SHA256 hash for uniqueness

    def save(self, *args, **kwargs):
        # Generate hash of field_value for uniqueness constraints
        self.field_value_hash = self.generate_hash(self.field_value)
        super().save(*args, **kwargs)
        self.post_deactivation_sync()

    class Meta:
        unique_together = ['book', 'field_name', 'field_value_hash', 'source']
        ordering = ['-confidence']

    def __str__(self):
        return f"{self.field_name}: {self.field_value} ({self.source.name})"


class FinalMetadata(models.Model):
    """Final suggested metadata per book"""
    book = models.OneToOneField(Book, on_delete=models.CASCADE)

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

    # Overall metrics
    overall_confidence = models.FloatField(default=0.0)
    completeness_score = models.FloatField(default=0.0)

    # Status
    is_reviewed = models.BooleanField(default=False)
    has_cover = models.BooleanField(default=False)
    last_updated = models.DateTimeField(auto_now=True)

    def calculate_overall_confidence(self):
        """Calculate weighted overall confidence"""
        weights = {
            'title': 0.3,
            'author': 0.3,
            'series': 0.15,
            'cover': 0.25,
        }

        score = (
            self.final_title_confidence * weights['title'] +
            self.final_author_confidence * weights['author'] +
            self.final_series_confidence * weights['series'] +
            self.final_cover_confidence * weights['cover']
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
        try:
            next_value = self.book.metadata.filter(
                field_name=field_name,
                is_active=True
            ).order_by('-confidence').first()

            if next_value and next_value.field_value:
                value = next_value.field_value

                # Handle special cases for publication_year
                if field_name == 'publication_year':
                    try:
                        # Handles strings like "1998", "circa 2005", "Published in 2012"
                        import re
                        year_match = re.search(r'\b(18|19|20)\d{2}\b', str(value))
                        if year_match:
                            year = int(year_match.group())
                            if 1000 < year <= 2100:  # sanity check
                                setattr(self, field_name, year)
                                logger.debug(f"Selected {field_name}: {year} (from metadata)")
                                return
                        # If we can't parse a valid year, set to None
                        setattr(self, field_name, None)
                        logger.debug(f"Selected {field_name}: None (couldn't parse '{value}')")
                    except Exception as e:
                        logger.warning(f"Error parsing year from '{value}': {e}")
                        setattr(self, field_name, None)
                else:
                    setattr(self, field_name, value)
                    logger.debug(f"Selected {field_name}: {value} (from metadata)")
            else:
                # Set appropriate default for the field type
                if field_name == 'publication_year':
                    setattr(self, field_name, None)
                else:
                    setattr(self, field_name, '')
                logger.debug(f"Selected {field_name}: {getattr(self, field_name)} (default - no metadata)")

        except Exception as e:
            logger.error(f"Error updating dynamic field '{field_name}' for book {self.book.id}: {e}")
            # Set appropriate default for the field type
            if field_name == 'publication_year':
                setattr(self, field_name, None)
            else:
                setattr(self, field_name, '')

    def update_final_title(self):
        try:
            next_title = self.book.titles.filter(is_active=True).order_by('-confidence').first()
            self.final_title = next_title.title if next_title else ''
            self.final_title_confidence = next_title.confidence if next_title else 0.0
        except Exception as e:
            logger.error(f"Error updating final title for book {self.book.id}: {e}")
            self.final_title = ''
            self.final_title_confidence = 0.0

    def update_final_author(self):
        try:
            next_author = self.book.bookauthor.filter(is_active=True).order_by('-confidence', '-is_main_author').first()
            self.final_author = next_author.author.name if next_author and next_author.author else ''
            self.final_author_confidence = next_author.confidence if next_author else 0.0
        except Exception as e:
            logger.error(f"Error updating final author for book {self.book.id}: {e}")
            self.final_author = ''
            self.final_author_confidence = 0.0

    def update_final_cover(self):
        try:
            next_cover = self.book.covers.filter(is_active=True).order_by('-confidence', '-is_high_resolution').first()
            if next_cover:
                self.final_cover_path = next_cover.cover_path
                self.final_cover_confidence = next_cover.confidence
                self.has_cover = True
            elif self.book.cover_path:
                self.final_cover_path = self.book.cover_path
                self.final_cover_confidence = 0.9  # Default confidence for original cover
                self.has_cover = True
            else:
                self.final_cover_path = ''
                self.final_cover_confidence = 0.0
                self.has_cover = False
        except Exception as e:
            logger.error(f"Error updating final cover for book {self.book.id}: {e}")
            self.final_cover_path = ''
            self.final_cover_confidence = 0.0
            self.has_cover = False

    def update_final_publisher(self):
        try:
            next_publisher = self.book.bookpublisher.filter(is_active=True).order_by('-confidence').first()
            self.final_publisher = next_publisher.publisher.name if next_publisher and next_publisher.publisher else ''
            self.final_publisher_confidence = next_publisher.confidence if next_publisher else 0.0
        except Exception as e:
            logger.error(f"Error updating final publisher for book {self.book.id}: {e}")
            self.final_publisher = ''
            self.final_publisher_confidence = 0.0

    def update_final_series(self):
        try:
            next_series = self.book.series_info.filter(is_active=True).order_by('-confidence').first()
            self.final_series = next_series.series.name if next_series and next_series.series else ''
            # Allow both None and empty string, but prefer empty string for consistency
            self.final_series_number = next_series.series_number or '' if next_series else ''
            self.final_series_confidence = next_series.confidence if next_series else 0.0
        except Exception as e:
            logger.error(f"Error updating final series for book {self.book.id}: {e}")
            self.final_series = ''
            self.final_series_number = ''
            self.final_series_confidence = 0.0

    def update_final_values(self):
        """Update all final metadata fields from related sources"""
        self.update_final_title()
        self.update_final_author()
        self.update_final_series()
        self.update_final_cover()
        self.update_final_publisher()

        # Update dynamic fields (publication_year, description, isbn, language)
        dynamic_fields = ['publication_year', 'description', 'isbn', 'language']
        for field_name in dynamic_fields:
            self.update_dynamic_field(field_name)

        self.calculate_overall_confidence()
        self.calculate_completeness_score()

        logger.debug(
            f"Updated values for book {self.book.id}: "
            f"title='{self.final_title}', author='{self.final_author}', "
            f"series='{self.final_series}', cover='{self.final_cover_path}', "
            f"publisher='{self.final_publisher}', year='{self.publication_year}', "
            f"isbn='{self.isbn}', confidence={self.overall_confidence:.2f}, "
            f"completeness={self.completeness_score:.2f}"
        )

    def save(self, *args, **kwargs):
        # Check if this is a manual update (set by views when user makes manual changes)
        manual_update = getattr(self, '_manual_update', False)
        # Capture whether this is a create and any explicitly provided last_updated
        creating_flag = getattr(self, '_state', None) and getattr(self._state, 'adding', False)
        requested_last_updated = getattr(self, 'last_updated', None)

        # Only auto-update on initial creation when no explicit values were provided.
        # Tests often create FinalMetadata with explicit field values; we must respect them.
        core_fields = [
            self.final_title,
            self.final_author,
            self.final_series,
            self.final_cover_path,
            self.final_publisher,
            self.isbn,
            self.language,
            self.description,
        ]
        has_explicit_values = any(bool(v) for v in core_fields)
        creating = getattr(self, '_state', None) and getattr(self._state, 'adding', False)

        should_auto_update = (
            not self.is_reviewed and not manual_update and creating and not has_explicit_values
            and (self.overall_confidence in (None, 0.0)) and (self.completeness_score in (None, 0.0))
        )

        if should_auto_update:
            logger.debug(f"Auto-updating metadata before saving book {self.book.id}")
            self.update_final_values()
        elif manual_update:
            logger.debug(f"Skipping auto-update for book {self.book.id} due to manual changes")

        # Normalize publication_year: allow tests to pass '' and coerce safely
        try:
            if isinstance(self.publication_year, str):
                year_str = self.publication_year.strip()
                self.publication_year = int(year_str) if year_str.isdigit() else None
        except Exception:
            self.publication_year = None

        if self.language:
            self.language = normalize_language(self.language)

        # Preserve explicitly provided has_cover; otherwise infer from final_cover_path
        if not self.has_cover:
            self.has_cover = bool(self.final_cover_path)
        # Preserve explicitly provided scores; only compute if missing or we auto-updated.
        if should_auto_update or self.overall_confidence is None:
            self.calculate_overall_confidence()
        if should_auto_update or self.completeness_score is None:
            self.calculate_completeness_score()

        logger.debug(f"Saving FinalMetadata for book {self.book.id}")
        super().save(*args, **kwargs)

        # If an explicit last_updated was provided on creation, restore it (auto_now overrides on save)
        try:
            if creating_flag and requested_last_updated is not None:
                FinalMetadata.objects.filter(pk=self.pk).update(last_updated=requested_last_updated)
        except Exception:
            # Non-fatal: if update fails, keep auto_now value
            pass

    def __str__(self):
        return f"{self.final_title or 'Unknown'} by {self.final_author or 'Unknown'}"


class ScanLog(models.Model):
    """Log entries for scan operations"""
    LOG_LEVELS = [
        ('INFO', 'Info'),
        ('WARNING', 'Warning'),
        ('ERROR', 'Error'),
    ]

    timestamp = models.DateTimeField(auto_now_add=True)
    level = models.CharField(max_length=10, choices=LOG_LEVELS)
    message = models.TextField()
    file_path = models.CharField(max_length=1000, blank=True)
    scan_folder = models.ForeignKey(ScanFolder, on_delete=models.CASCADE, null=True)
    # Aggregate counters for test expectations and dashboard stats
    books_found = models.IntegerField(default=0)
    books_processed = models.IntegerField(default=0)
    errors_count = models.IntegerField(default=0)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.timestamp.strftime('%Y-%m-%d %H:%M')} - {self.level}: {self.message[:100]}"


class ScanStatus(models.Model):
    STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('Running', 'Running'),
        ('Completed', 'Completed'),
        ('Failed', 'Failed'),
    ]

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')
    progress = models.IntegerField(default=0)
    message = models.TextField(blank=True, null=True)
    started = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    # Resume tracking fields
    last_processed_file = models.TextField(blank=True, null=True, help_text="Last file path that was completely processed")
    total_files = models.IntegerField(default=0, help_text="Total number of files to process")
    processed_files = models.IntegerField(default=0, help_text="Number of files processed so far")
    scan_folders = models.TextField(blank=True, null=True, help_text="JSON list of folders being scanned")

    def __str__(self):
        return f"{self.status} ({self.progress}%) at {self.updated.strftime('%Y-%m-%d %H:%M:%S')}"


class ScanHistory(models.Model):
    """Track completed scans and their detailed outcomes."""

    SCAN_TYPES = [
        ('scan', 'Initial Scan'),
        ('rescan', 'Rescan'),
        ('resume', 'Resume Scan'),
    ]

    STATUS_CHOICES = [
        ('completed', 'Completed Successfully'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
        ('partial', 'Partially Completed'),
    ]

    # Basic scan information
    job_id = models.CharField(max_length=100, unique=True, help_text="Unique job identifier")
    scan_type = models.CharField(max_length=20, choices=SCAN_TYPES, default='scan')
    folder_path = models.TextField(help_text="Path of the scanned folder")
    folder_name = models.CharField(max_length=255, help_text="Name of the scanned folder")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)

    # Timing information
    started_at = models.DateTimeField(help_text="When the scan started")
    completed_at = models.DateTimeField(help_text="When the scan finished")
    duration_seconds = models.IntegerField(help_text="Total scan duration in seconds")

    # File processing statistics
    total_files_found = models.IntegerField(default=0, help_text="Total files discovered")
    files_processed = models.IntegerField(default=0, help_text="Files successfully processed")
    files_skipped = models.IntegerField(default=0, help_text="Files skipped (already processed)")
    files_failed = models.IntegerField(default=0, help_text="Files that failed processing")

    # Book statistics
    books_added = models.IntegerField(default=0, help_text="New books added")
    books_updated = models.IntegerField(default=0, help_text="Existing books updated")
    books_removed = models.IntegerField(default=0, help_text="Books marked as removed")

    # Error and warning counts
    warnings_count = models.IntegerField(default=0, help_text="Number of warnings encountered")
    errors_count = models.IntegerField(default=0, help_text="Number of errors encountered")

    # External API usage
    external_apis_used = models.BooleanField(default=False, help_text="Whether external APIs were queried")
    api_requests_made = models.IntegerField(default=0, help_text="Number of API requests made")

    # Additional details
    error_message = models.TextField(blank=True, null=True, help_text="Error message if scan failed")
    summary = models.TextField(blank=True, null=True, help_text="Human-readable summary of scan results")
    metadata_json = models.JSONField(default=dict, help_text="Additional scan metadata and statistics")

    # Relationships
    scan_folder = models.ForeignKey('ScanFolder', on_delete=models.CASCADE, null=True, blank=True)

    class Meta:
        ordering = ['-completed_at', '-started_at']
        verbose_name = 'Scan History Entry'
        verbose_name_plural = 'Scan History Entries'
        indexes = [
            models.Index(fields=['job_id']),
            models.Index(fields=['status']),
            models.Index(fields=['completed_at']),
        ]

    def __str__(self):
        return f"{self.scan_type.title()} of '{self.folder_name}' - {self.status} ({self.completed_at.strftime('%Y-%m-%d %H:%M')})"

    @property
    def success_rate(self):
        """Calculate the success rate of file processing."""
        if self.total_files_found == 0:
            return 0
        return (self.files_processed / self.total_files_found) * 100

    @property
    def duration_formatted(self):
        """Get human-readable duration."""
        minutes, seconds = divmod(self.duration_seconds, 60)
        hours, minutes = divmod(minutes, 60)

        if hours > 0:
            return f"{hours}h {minutes}m {seconds}s"
        elif minutes > 0:
            return f"{minutes}m {seconds}s"
        else:
            return f"{seconds}s"

    def generate_summary(self):
        """Generate a human-readable summary of the scan results."""
        parts = []

        if self.status == 'completed':
            parts.append(f"✅ Successfully processed {self.files_processed} files")
        elif self.status == 'failed':
            parts.append("❌ Scan failed")
        elif self.status == 'cancelled':
            parts.append("⏹️ Scan was cancelled")
        elif self.status == 'partial':
            parts.append(f"⚠️ Partially completed: {self.files_processed}/{self.total_files_found} files")

        if self.books_added > 0:
            parts.append(f"📚 Added {self.books_added} new books")

        if self.books_updated > 0:
            parts.append(f"🔄 Updated {self.books_updated} existing books")

        if self.books_removed > 0:
            parts.append(f"🗑️ Removed {self.books_removed} books")

        if self.errors_count > 0:
            parts.append(f"⚠️ {self.errors_count} errors encountered")

        if self.warnings_count > 0:
            parts.append(f"⚠️ {self.warnings_count} warnings")

        if self.external_apis_used and self.api_requests_made > 0:
            parts.append(f"🌐 Made {self.api_requests_made} API requests")

        parts.append(f"⏱️ Duration: {self.duration_formatted}")

        return " • ".join(parts)


class FileOperation(models.Model):
    """Track file rename operations for complete reversal capability."""
    OPERATION_TYPES = [
        ('rename', 'File Rename'),
        ('move', 'File Move'),
        ('create_folder', 'Folder Creation'),
    ]

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('reverted', 'Reverted'),
    ]

    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name='file_operations')
    operation_type = models.CharField(max_length=20, choices=OPERATION_TYPES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

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

    # Additional files affected (JSON list)
    additional_files = models.TextField(default='[]', help_text='JSON list of additional files moved')

    # Operation metadata
    operation_date = models.DateTimeField(auto_now_add=True)
    batch_id = models.UUIDField(null=True, blank=True, help_text='Groups operations from same batch')
    notes = models.TextField(blank=True)
    error_message = models.TextField(blank=True)

    # User who performed the operation
    user = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        db_table = 'books_fileoperation'
        ordering = ['-operation_date']

    def __str__(self):
        return f"{self.operation_type} - {self.book.finalmetadata.final_title if self.book.finalmetadata else self.book.id} - {self.status}"


class AIFeedback(models.Model):
    """Store user feedback on AI predictions for model improvement."""

    RATING_CHOICES = [
        (1, 'Poor - Completely wrong'),
        (2, 'Fair - Some correct elements'),
        (3, 'Good - Mostly correct'),
        (4, 'Very Good - Almost perfect'),
        (5, 'Excellent - Perfect prediction'),
    ]

    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name='ai_feedback')
    user = models.ForeignKey('auth.User', on_delete=models.CASCADE)

    # Original context
    original_filename = models.CharField(max_length=500, help_text='Original filename used for AI prediction')
    ai_predictions = models.TextField(help_text='JSON of AI predictions for each field')
    prediction_confidence = models.FloatField(null=True, blank=True, help_text='Overall AI prediction confidence')

    # User corrections
    user_corrections = models.TextField(help_text='JSON of user corrections to AI predictions')
    feedback_rating = models.IntegerField(
        choices=RATING_CHOICES,
        help_text='User rating of AI prediction quality'
    )
    comments = models.TextField(blank=True, help_text='Additional user feedback or comments')

    # Training status
    needs_retraining = models.BooleanField(default=True, help_text='Whether this feedback should be used for retraining')
    processed_for_training = models.BooleanField(default=False, help_text='Whether this feedback was used in training')

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'books_aifeedback'
        ordering = ['-created_at']
        unique_together = ['book', 'user']  # One feedback per book per user

    def __str__(self):
        return f"AI Feedback for {self.book.finalmetadata.final_title if self.book.finalmetadata else self.book.id} - Rating: {self.feedback_rating}"

    def get_ai_predictions_dict(self):
        """Parse AI predictions JSON safely."""
        import json
        try:
            return json.loads(self.ai_predictions)
        except (json.JSONDecodeError, ValueError):
            return {}

    def get_user_corrections_dict(self):
        """Parse user corrections JSON safely."""
        import json
        try:
            return json.loads(self.user_corrections)
        except (json.JSONDecodeError, ValueError):
            return {}

    def get_accuracy_score(self):
        """Calculate accuracy score based on rating."""
        # Convert 1-5 rating to 0-1 accuracy score
        return (self.feedback_rating - 1) / 4.0


class UserProfile(models.Model):
    """User preferences and settings"""
    THEME_CHOICES = [
        ('flatly', 'Flatly'),
        ('cosmo', 'Cosmo'),
        ('bootstrap', 'Bootstrap Default'),
        ('cerulean', 'Cerulean'),
        ('cyborg', 'Cyborg'),
        ('darkly', 'Darkly'),
        ('journal', 'Journal'),
        ('litera', 'Litera'),
        ('lumen', 'Lumen'),
        ('lux', 'Lux'),
        ('materia', 'Materia'),
        ('minty', 'Minty'),
        ('morph', 'Morph'),
        ('pulse', 'Pulse'),
        ('quartz', 'Quartz'),
        ('sandstone', 'Sandstone'),
        ('simplex', 'Simplex'),
        ('sketchy', 'Sketchy'),
        ('slate', 'Slate'),
        ('solar', 'Solar'),
        ('spacelab', 'Spacelab'),
        ('superhero', 'Superhero'),
        ('united', 'United'),
        ('vapor', 'Vapor'),
        ('yeti', 'Yeti'),
        ('zephyr', 'Zephyr'),
    ]

    user = models.OneToOneField('auth.User', on_delete=models.CASCADE, related_name='profile')

    # Theme preferences
    theme = models.CharField(
        max_length=20,
        choices=THEME_CHOICES,
        default='flatly',
        help_text='Selected Bootswatch theme'
    )

    # Other UI preferences
    items_per_page = models.IntegerField(default=50, help_text='Number of items to show per page')
    show_covers_in_list = models.BooleanField(default=True, help_text='Show book covers in list views')
    default_view_mode = models.CharField(
        max_length=10,
        choices=[('table', 'Table'), ('grid', 'Grid')],
        default='table',
        help_text='Default view mode for lists'
    )

    # Privacy preferences
    share_reading_progress = models.BooleanField(default=False, help_text='Share reading progress with other users')

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'books_userprofile'
        verbose_name = 'User Profile'
        verbose_name_plural = 'User Profiles'

    def __str__(self):
        return f"{self.user.username}'s Profile"

    @classmethod
    def get_or_create_for_user(cls, user):
        """Get or create profile for user"""
        profile, created = cls.objects.get_or_create(user=user)
        return profile


class SetupWizard(models.Model):
    """Track user setup wizard progress and completion."""

    WIZARD_STEPS = [
        ('welcome', 'Welcome'),
        ('folders', 'Folder Selection'),
        ('content_types', 'Content Type Assignment'),
        ('scrapers', 'Scraper Configuration'),
        ('complete', 'Setup Complete'),
    ]

    user = models.OneToOneField('auth.User', on_delete=models.CASCADE, related_name='setup_wizard')

    # Step completion tracking
    welcome_completed = models.BooleanField(default=False)
    folders_completed = models.BooleanField(default=False)
    content_types_completed = models.BooleanField(default=False)
    scrapers_completed = models.BooleanField(default=False)

    # Overall completion
    is_completed = models.BooleanField(default=False)
    is_skipped = models.BooleanField(default=False)

    # Progress tracking
    current_step = models.CharField(max_length=20, choices=WIZARD_STEPS, default='welcome')

    # Configuration data (JSON fields for flexibility)
    selected_folders = models.JSONField(default=list, blank=True, help_text="List of selected folder paths")
    folder_content_types = models.JSONField(default=dict, blank=True, help_text="Mapping of folders to content types")
    scraper_config = models.JSONField(default=dict, blank=True, help_text="Scraper configuration settings")

    # Timestamps
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    last_step_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'books_setupwizard'
        verbose_name = 'Setup Wizard'
        verbose_name_plural = 'Setup Wizards'

    def __str__(self):
        return f"Setup Wizard for {self.user.username} - {self.get_current_step_display()}"

    @property
    def progress_percentage(self):
        """Calculate completion percentage."""
        completed_steps = sum([
            self.welcome_completed,
            self.folders_completed,
            self.content_types_completed,
            self.scrapers_completed,
        ])
        return int((completed_steps / 4) * 100)

    @property
    def next_step(self):
        """Get the next step in the wizard."""
        step_order = [choice[0] for choice in self.WIZARD_STEPS]
        try:
            current_index = step_order.index(self.current_step)
            if current_index < len(step_order) - 1:
                return step_order[current_index + 1]
        except ValueError:
            pass
        return 'complete'

    @property
    def previous_step(self):
        """Get the previous step in the wizard."""
        step_order = [choice[0] for choice in self.WIZARD_STEPS]
        try:
            current_index = step_order.index(self.current_step)
            if current_index > 0:
                return step_order[current_index - 1]
        except ValueError:
            pass
        return 'welcome'

    def mark_step_completed(self, step):
        """Mark a specific step as completed."""
        step_mapping = {
            'welcome': 'welcome_completed',
            'folders': 'folders_completed',
            'content_types': 'content_types_completed',
            'scrapers': 'scrapers_completed',
        }

        if step in step_mapping:
            setattr(self, step_mapping[step], True)
            self.current_step = self.next_step

            # Check if wizard is complete
            if all([
                self.welcome_completed,
                self.folders_completed,
                self.content_types_completed,
                self.scrapers_completed,
            ]):
                self.is_completed = True
                self.completed_at = timezone.now()
                self.current_step = 'complete'

            self.save()

    def skip_wizard(self):
        """Mark wizard as skipped."""
        self.is_skipped = True
        self.is_completed = True
        self.completed_at = timezone.now()
        self.current_step = 'complete'
        self.save()

    @classmethod
    def get_or_create_for_user(cls, user):
        """Get or create setup wizard for user."""
        wizard, created = cls.objects.get_or_create(user=user)
        return wizard, created


class ScanQueue(models.Model):
    """Model to track pending/future scans in the queue."""

    QUEUE_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('scheduled', 'Scheduled'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]

    SCAN_TYPE_CHOICES = [
        ('folder', 'Folder Scan'),
        ('book_ids', 'Specific Book IDs'),
        ('series', 'Series Scan'),
        ('author', 'Author Scan'),
        ('full', 'Full Library Scan'),
        ('incremental', 'Incremental Scan'),
    ]

    PRIORITY_CHOICES = [
        (1, 'Low'),
        (2, 'Normal'),
        (3, 'High'),
        (4, 'Urgent'),
    ]

    # Basic information
    name = models.CharField(max_length=200, help_text="Name/description of the scan job")
    scan_type = models.CharField(max_length=20, choices=SCAN_TYPE_CHOICES, default='folder')
    status = models.CharField(max_length=20, choices=QUEUE_STATUS_CHOICES, default='pending')
    priority = models.IntegerField(choices=PRIORITY_CHOICES, default=2, help_text="Scan priority (higher = more urgent)")

    # Scan parameters
    folder_paths = models.JSONField(default=list, blank=True, help_text="List of folder paths to scan")
    book_ids = models.JSONField(default=list, blank=True, help_text="List of specific book IDs to process")
    series_names = models.JSONField(default=list, blank=True, help_text="List of series names to scan")
    author_names = models.JSONField(default=list, blank=True, help_text="List of author names to scan")

    # Scan options
    rescan_existing = models.BooleanField(default=False, help_text="Re-scan books that already exist")
    update_metadata = models.BooleanField(default=True, help_text="Update metadata for existing books")
    fetch_covers = models.BooleanField(default=True, help_text="Fetch cover images")
    deep_scan = models.BooleanField(default=False, help_text="Perform deep content analysis")

    # Scheduling
    scheduled_for = models.DateTimeField(null=True, blank=True, help_text="When to execute this scan")
    created_by = models.ForeignKey('auth.User', on_delete=models.CASCADE, help_text="User who created this queue item")

    # Execution tracking
    estimated_files = models.IntegerField(default=0, help_text="Estimated number of files to process")
    estimated_duration = models.IntegerField(default=0, help_text="Estimated duration in seconds")
    actual_scan_job_id = models.CharField(max_length=50, blank=True, help_text="Job ID when scan starts executing")

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    # Error tracking
    error_message = models.TextField(blank=True, help_text="Error details if scan failed")
    retry_count = models.IntegerField(default=0, help_text="Number of times this scan has been retried")
    max_retries = models.IntegerField(default=3, help_text="Maximum number of retry attempts")

    class Meta:
        ordering = ['-priority', 'created_at']
        verbose_name = 'Scan Queue Item'
        verbose_name_plural = 'Scan Queue'
        indexes = [
            models.Index(fields=['status', 'priority']),
            models.Index(fields=['scan_type']),
            models.Index(fields=['scheduled_for']),
            models.Index(fields=['created_by']),
        ]

    def __str__(self):
        return f"{self.name} ({self.get_scan_type_display()}) - {self.get_status_display()}"

    @property
    def target_summary(self):
        """Generate a summary of what will be scanned."""
        targets = []

        if self.scan_type == 'folder' and self.folder_paths:
            folder_count = len(self.folder_paths)
            if folder_count == 1:
                targets.append(f"📁 {self.folder_paths[0]}")
            else:
                targets.append(f"📁 {folder_count} folders")

        elif self.scan_type == 'book_ids' and self.book_ids:
            targets.append(f"📚 {len(self.book_ids)} specific books")

        elif self.scan_type == 'series' and self.series_names:
            if len(self.series_names) == 1:
                targets.append(f"📑 Series: {self.series_names[0]}")
            else:
                targets.append(f"📑 {len(self.series_names)} series")

        elif self.scan_type == 'author' and self.author_names:
            if len(self.author_names) == 1:
                targets.append(f"✍️ Author: {self.author_names[0]}")
            else:
                targets.append(f"✍️ {len(self.author_names)} authors")

        elif self.scan_type == 'full':
            targets.append("🗂️ Full library scan")

        elif self.scan_type == 'incremental':
            targets.append("⚡ Incremental scan")

        return " | ".join(targets) if targets else "No targets specified"

    @property
    def options_summary(self):
        """Generate a summary of scan options."""
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
        """Check if this queue item is ready to be executed."""
        if self.status != 'pending':
            return False
        if self.scheduled_for and timezone.now() < self.scheduled_for:
            return False
        return True

    @property
    def priority_display(self):
        """Get priority with emoji indicator."""
        priority_icons = {1: "⬇️", 2: "➡️", 3: "⬆️", 4: "🔴"}
        return f"{priority_icons.get(self.priority, '➡️')} {self.get_priority_display()}"

    @property
    def estimated_duration_formatted(self):
        """Get human-readable estimated duration."""
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
        """Check if this item can be retried."""
        return (self.status in ['failed', 'cancelled'] and self.retry_count < self.max_retries)

    def mark_processing(self, job_id):
        """Mark this queue item as currently processing."""
        self.status = 'processing'
        self.actual_scan_job_id = job_id
        self.started_at = timezone.now()
        self.save(update_fields=['status', 'actual_scan_job_id', 'started_at', 'updated_at'])

    def mark_completed(self):
        """Mark this queue item as completed."""
        self.status = 'completed'
        self.completed_at = timezone.now()
        self.save(update_fields=['status', 'completed_at', 'updated_at'])

    def mark_failed(self, error_message=""):
        """Mark this queue item as failed."""
        self.status = 'failed'
        self.error_message = error_message
        self.retry_count += 1
        self.completed_at = timezone.now()
        self.save(update_fields=['status', 'error_message', 'retry_count', 'completed_at', 'updated_at'])
