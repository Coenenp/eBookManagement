"""Final consolidated metadata model for the books app."""

import logging
from difflib import SequenceMatcher

from django.db import models
from django.utils import timezone

from books.utils.language import normalize_language

logger = logging.getLogger("books.scanner")


def _normalize(value):
    """Lowercase and strip a string for loose comparison."""
    return (value or "").strip().lower()


class UnresolvedReason(models.TextChoices):
    """Why a book's metadata is unresolved, surfaced in the review queue.

    Blank (default) means resolved. Each value is its own filterable category;
    UNCERTAIN is kept distinct so the uncalibrated middle band can be watched
    in practice before the gold set lands.
    """

    UNCERTAIN = "uncertain", "Uncertain match"
    UNMAPPED_SERIES = "unmapped_series", "Unmapped series"
    NO_MATCH = "no_match", "No matching candidate"
    NEITHER_SOURCE = "neither_source", "Neither source resolved"


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

    # Audiobook-specific metadata
    total_duration_seconds = models.IntegerField(null=True, blank=True, help_text="Total duration in seconds")

    # Overall metrics
    overall_confidence = models.FloatField(default=0.0)
    completeness_score = models.FloatField(default=0.0)
    accuracy_score = models.FloatField(default=0.0)

    # Denormalized flags for faster filtering
    has_cover = models.BooleanField(default=False)
    has_isbn = models.BooleanField(default=False)
    has_description = models.BooleanField(default=False)
    metadata_complete = models.BooleanField(default=False)

    # Status
    is_reviewed = models.BooleanField(default=False)
    is_renamed = models.BooleanField(default=False)
    unresolved_reason = models.CharField(max_length=20, choices=UnresolvedReason.choices, blank=True, default="")
    final_path = models.CharField(max_length=1000, blank=True)
    last_updated = models.DateTimeField(auto_now=True)

    def calculate_overall_confidence(self):
        """Calculate weighted overall confidence."""
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
        """Calculate how complete the metadata is."""
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

    def calculate_accuracy_score(self):
        """Calculate a per-book accuracy score: how likely the metadata is CORRECT.

        Distinct from ``overall_confidence`` (source trust) and
        ``completeness_score`` (field fill rate). Measures evidence agreement:

            accuracy = 0.35 * title_corroboration
                     + 0.35 * author_corroboration
                     + 0.30 * identifier_strength

        - title/author corroboration: how strongly independent candidate values
          agree with the final value. A lone value is uncorroborated (0.5 at
          best); multiple agreeing values raise the score toward 1.0.
        - identifier_strength: 1.0 when an ISBN is present, else 0.0 (correctness
          then rests on title/author agreement alone, capping ISBN-less books).

        Match verification (rejecting non-matching external candidates before
        merge) feeds this score by keeping wrong high-trust values out of the
        candidate set. Thresholds are calibrated on the gold set in a later
        milestone.
        """
        self.accuracy_score = (
            0.35 * self._corroboration(self.final_title, self._candidate_titles())
            + 0.35 * self._corroboration(self.final_author, self._candidate_authors())
            + 0.30 * self._identifier_strength()
        )
        return self.accuracy_score

    def _candidate_titles(self):
        return [t.title for t in self.book.titles.filter(is_active=True) if t.title]

    def _candidate_authors(self):
        return [
            a.author.name
            for a in self.book.author_relationships.select_related("author").filter(is_active=True)
            if a.author and a.author.name
        ]

    @staticmethod
    def _corroboration(final_value, candidates):
        """Agreement of candidates with the final value, in [0, 1].

        A single candidate that equals the final value is uncorroborated (0.5);
        agreement across two or more independent candidates raises the score.
        """
        final_n = _normalize(final_value)
        if not final_n:
            return 0.0
        sims = [_normalize(c) for c in candidates]
        sims = [SequenceMatcher(None, final_n, c).ratio() for c in sims if c]
        if not sims:
            return 0.0
        if len(sims) == 1:
            return 0.5 if sims[0] >= 0.8 else 0.0
        agreeing = sum(1 for s in sims if s >= 0.8)
        return agreeing / len(sims)

    def _identifier_strength(self):
        # A present ISBN is a strong identifier (boosts accuracy toward 1.0).
        # Absent, it contributes nothing: correctness then rests on title/author
        # corroboration alone (capping ISBN-less books below the ISBN-backed case).
        # Checksum verification and ISBN match are handled by match verification
        # (strong-identifier rule); comics rely on series+issue corroboration,
        # which is added in a later step.
        return 1.0 if self.isbn else 0.0

    def update_dynamic_field(self, field_name):
        """Update a single dynamic field from metadata sources."""
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
        """Update final title from sources."""
        try:
            next_title = self.book.titles.select_related("source").filter(is_active=True).order_by("-confidence").first()

            self.final_title = next_title.title if next_title else ""
            self.final_title_confidence = next_title.confidence if next_title else 0.0
        except Exception as e:
            logger.error(f"Error updating final title for book {self.book.id}: {e}")
            self.final_title = ""
            self.final_title_confidence = 0.0

    def update_final_author(self):
        """Update final author from sources."""
        try:
            next_author = self.book.author_relationships.select_related("author", "source").filter(is_active=True).order_by("-confidence", "-is_main_author").first()

            self.final_author = next_author.author.name if next_author and next_author.author else ""
            self.final_author_confidence = next_author.confidence if next_author else 0.0
        except Exception as e:
            logger.error(f"Error updating final author for book {self.book.id}: {e}")
            self.final_author = ""
            self.final_author_confidence = 0.0

    def update_final_cover(self):
        """Update final cover from sources."""
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
        """Update final publisher from sources."""
        try:
            next_publisher = self.book.publisher_relationships.select_related("publisher", "source").filter(is_active=True).order_by("-confidence").first()

            self.final_publisher = next_publisher.publisher.name if next_publisher and next_publisher.publisher else ""
            self.final_publisher_confidence = next_publisher.confidence if next_publisher else 0.0
        except Exception as e:
            logger.error(f"Error updating final publisher for book {self.book.id}: {e}")
            self.final_publisher = ""
            self.final_publisher_confidence = 0.0

    def update_final_series(self):
        """Update final series from sources."""
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
            self.calculate_accuracy_score()

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
                    "accuracy": f"{self.accuracy_score:.2f}",
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
                        "accuracy_score",
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
        """Mark this book as renamed and store the new path."""
        from books.models_operations import FileOperation

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
        if not self.accuracy_score:
            self.calculate_accuracy_score()

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
            models.Index(fields=["accuracy_score"]),
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
