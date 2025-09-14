"""Django models for ebook library management.

This module defines the database models for managing ebooks, metadata,
authors, publishers, genres, and scan operations. Includes comprehensive
relationship mo                surname_prefixes = {
                    "o'", 'mac', 'mc', 'van', 'von', 'vander', 'vonder', 'van der',
                    'von der', 'van den', 'von den', 'vanden', 'vonden', 'del', 'della',
                    "d'", 'du', 'de', 'di', 'ter', 'lo', 'gel', 'van t'
                }for book metadata synchronization.
"""
from django.db import models
from .mixins import FinalMetadataSyncMixin
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
    OPEN_LIBRARY_COVERS = 'Open Library Covers'
    GOOGLE_BOOKS_COVERS = 'Google Books Covers'
    ORIGINAL_SCAN = 'Original Scan'
    MANUAL = 'Manual Entry'
    CONTENT_SCAN = 'content_scan'

    SOURCE_CHOICES = [
        (FILENAME, 'Filename'),
        (EPUB_INTERNAL, 'EPUB'),
        (MOBI_INTERNAL, 'MOBI'),
        (PDF_INTERNAL, 'PDF'),
        (OPF_FILE, 'OPF File'),
        (OPEN_LIBRARY, 'Open Library'),
        (GOOGLE_BOOKS, 'Google Books'),
        (OPEN_LIBRARY_COVERS, 'Open Library Covers'),
        (GOOGLE_BOOKS_COVERS, 'Google Books Covers'),
        (ORIGINAL_SCAN, 'Original Scan'),
        (MANUAL, 'Manual Entry'),
        (CONTENT_SCAN, 'Content Scan'),
    ]

    name = models.CharField(max_length=50, choices=SOURCE_CHOICES, unique=True)
    trust_level = models.FloatField(
        default=0.5,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text="Trust level for this source (0.0-1.0)"
    )

    def __str__(self):
        return self.get_name_display()

    class Meta:
        ordering = ['-trust_level', 'name']


class ScanFolder(models.Model):
    name = models.CharField(max_length=100, default='Untitled', blank=False, null=False)
    path = models.CharField(max_length=500)
    language = models.CharField(max_length=10, choices=LANGUAGE_CHOICES, default='en')
    is_active = models.BooleanField(default=True)
    last_scanned = models.DateTimeField(null=True, blank=True)
    # Optional: created_at for admin tracking
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Book(models.Model):
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

    def save(self, *args, **kwargs):
        """Generate hash of file_path for unique constraint"""
        import hashlib
        if self.file_path:
            self.file_path_hash = hashlib.sha256(self.file_path.encode('utf-8')).hexdigest()
        super().save(*args, **kwargs)

    @classmethod
    def get_or_create_by_path(cls, file_path, defaults=None):
        """Get or create book by file path, using hash for lookup"""
        import hashlib
        file_path_hash = hashlib.sha256(file_path.encode('utf-8')).hexdigest()

        try:
            book = cls.objects.get(file_path_hash=file_path_hash)
            return book, False
        except cls.DoesNotExist:
            if defaults is None:
                defaults = {}
            defaults['file_path'] = file_path
            defaults['file_path_hash'] = file_path_hash
            book = cls.objects.create(**defaults)
            return book, True

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
            name_clean = self.name.strip()
            parts = name_clean.replace(",", "").split()

            # If comma-separated, assume inverted format: Last, First
            if "," in self.name and len(parts) >= 2:
                self.last_name = parts[0]
                self.first_name = " ".join(parts[1:])
            else:
                # Prefix-aware splitting
                surname_prefixes = {
                    'o’', 'mac', 'mc', 'van', 'von', 'vander', 'vonder', 'van der',
                    'von der', 'van den', 'von den', 'vanden', 'vonden', 'del', 'della',
                    'd’', 'du', 'de', 'di', 'ter', 'lo', 'gel'
                }

                parts = [p.strip() for p in self.name.split()]
                first = []
                last = []

                # Look for surname prefixes starting from each position
                found_prefix = False
                for i in range(len(parts)):
                    # Check if any prefix starts at position i
                    for prefix in surname_prefixes:
                        prefix_parts = prefix.split()
                        # Check if we have enough remaining parts to match the prefix
                        if i + len(prefix_parts) <= len(parts):
                            # Check if the parts match the prefix (case insensitive)
                            if all(parts[i + j].lower() == prefix_parts[j] for j in range(len(prefix_parts))):
                                # Found a prefix, everything from here is last name
                                first = parts[:i]
                                last = parts[i:]
                                found_prefix = True
                                break
                    if found_prefix:
                        break

                # If no prefix found, use traditional splitting (last word as surname)
                if not found_prefix:
                    if len(parts) > 1:
                        first = parts[:-1]
                        last = [parts[-1]]
                    else:
                        first = []
                        last = parts

                self.first_name = " ".join(first).strip()
                self.last_name = " ".join(last).strip()

        # Now normalize the name after we have proper first_name and last_name
        self.name_normalized = self.normalize_name(f"{self.first_name} {self.last_name}")

        super().save(*args, **kwargs)

    @staticmethod
    def normalize_name(name):
        import re
        name = re.sub(r"[^\w\s]", "", name.lower().strip())
        return " ".join(name.split())

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


class BookAuthor(FinalMetadataSyncMixin, models.Model):
    """M2M relationship between books and authors with source tracking"""
    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name='bookauthor')
    author = models.ForeignKey(Author, on_delete=models.CASCADE)
    source = models.ForeignKey(DataSource, on_delete=models.CASCADE)
    confidence = models.FloatField(
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)]
    )
    is_main_author = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True, help_text="Uncheck to hide this metadata without deleting it.")
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.post_deactivation_sync()

    class Meta:
        unique_together = ['book', 'author', 'source']
        ordering = ['-confidence', '-is_main_author']


class BookTitle(FinalMetadataSyncMixin, models.Model):
    """Book titles from different sources"""
    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name='titles')
    title = models.CharField(max_length=500)
    source = models.ForeignKey(DataSource, on_delete=models.CASCADE)
    confidence = models.FloatField(
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)]
    )
    is_active = models.BooleanField(default=True, help_text="Uncheck to hide this metadata without deleting it.")
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.post_deactivation_sync()

    def __str__(self):
        return f"{self.title} ({self.source})"

    class Meta:
        unique_together = ['book', 'title', 'source']
        ordering = ['-confidence']


class BookCover(FinalMetadataSyncMixin, models.Model):
    """Book covers from different sources with metadata"""
    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name='covers')
    cover_path = models.CharField(max_length=1000, help_text="Local file path or URL")
    cover_path_hash = models.CharField(max_length=64, editable=False)  # SHA256 hash for uniqueness
    source = models.ForeignKey(DataSource, on_delete=models.CASCADE)
    confidence = models.FloatField(
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)]
    )

    # Cover metadata
    width = models.IntegerField(null=True, blank=True)
    height = models.IntegerField(null=True, blank=True)
    file_size = models.BigIntegerField(null=True, blank=True)
    format = models.CharField(max_length=10, blank=True, help_text="jpg, png, gif, etc.")

    # Quality indicators
    is_high_resolution = models.BooleanField(default=False)
    aspect_ratio = models.FloatField(null=True, blank=True)

    # Status flags
    is_active = models.BooleanField(default=True, help_text="Uncheck to hide this metadata without deleting it.")
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        # Generate hash of cover_path for uniqueness constraints
        import hashlib
        self.cover_path_hash = hashlib.sha256(str(self.cover_path).encode('utf-8')).hexdigest()

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


class BookSeries(FinalMetadataSyncMixin, models.Model):
    """Book series information with source tracking"""
    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name='series_info')
    series = models.ForeignKey(Series, on_delete=models.CASCADE, null=True, blank=True)
    series_number = models.CharField(max_length=20, null=True, blank=True)
    source = models.ForeignKey(DataSource, on_delete=models.CASCADE)
    confidence = models.FloatField(
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)]
    )
    is_active = models.BooleanField(default=True, help_text="Uncheck to hide this metadata without deleting it.")
    created_at = models.DateTimeField(auto_now_add=True)

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


class BookPublisher(FinalMetadataSyncMixin, models.Model):
    """M2M relationship between books and publishers with source tracking."""
    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name='bookpublisher')
    publisher = models.ForeignKey(Publisher, on_delete=models.CASCADE, related_name='publisher_books')
    source = models.ForeignKey(DataSource, on_delete=models.CASCADE)
    confidence = models.FloatField(
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)]
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Uncheck to hide this metadata without deleting it."
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.post_deactivation_sync()

    def __str__(self):
        title = getattr(self.book.finalmetadata, "final_title", "Untitled")
        return f"{title} → {self.publisher.name} ({self.source.name})"

    class Meta:
        unique_together = ['book', 'publisher', 'source']
        ordering = ['-confidence']


class BookMetadata(FinalMetadataSyncMixin, models.Model):
    """Additional metadata fields with source tracking"""
    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name='metadata')
    field_name = models.CharField(max_length=100)
    field_value = models.TextField()
    field_value_hash = models.CharField(max_length=64, editable=False)  # SHA256 hash for uniqueness
    source = models.ForeignKey(DataSource, on_delete=models.CASCADE)
    confidence = models.FloatField(
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)]
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Uncheck to ignore this metadata field for selection and display."
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        # Generate hash of field_value for uniqueness constraints
        import hashlib
        self.field_value_hash = hashlib.sha256(str(self.field_value).encode('utf-8')).hexdigest()
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
            self.final_cover_path = next_cover.cover_path if next_cover else ''
            self.final_cover_confidence = next_cover.confidence if next_cover else 0.0
            self.has_cover = bool(next_cover)
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

        if not self.is_reviewed and not manual_update:
            logger.debug(f"Auto-updating metadata before saving book {self.book.id}")
            self.update_final_values()
        elif manual_update:
            logger.debug(f"Skipping auto-update for book {self.book.id} due to manual changes")

        if self.language:
            self.language = normalize_language(self.language)

        self.has_cover = bool(self.final_cover_path)
        self.calculate_overall_confidence()
        self.calculate_completeness_score()

        logger.debug(f"Saving FinalMetadata for book {self.book.id}")
        super().save(*args, **kwargs)

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
