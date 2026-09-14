"""API access tracking models for intelligent scanning."""

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from books.mixins.metadata import HashFieldMixin
from books.models import Book, DataSource, ScanFolder


class APIAccessLog(HashFieldMixin, models.Model):
    """Tracks API access attempts and results for each book."""

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
        """Calculate success rate percentage."""
        if self.total_attempts == 0:
            return 0.0
        return (self.successful_attempts / self.total_attempts) * 100

    @property
    def is_healthy(self):
        """Check if this API source is healthy for this book."""
        return self.consecutive_failures < 3 and (self.success_rate >= 50 or self.total_attempts < 2)

    @property
    def can_retry_now(self):
        """Check if we can retry this API now."""
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
        """Record an API access attempt."""
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
        """Reset retry state to allow new attempts."""
        self.should_retry = True
        self.consecutive_failures = 0
        self.next_retry_after = None
        self.save()


class ScanSession(HashFieldMixin, models.Model):
    """Tracks scanning sessions and their API usage patterns."""

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
        """Calculate completion percentage."""
        if self.total_books == 0:
            return 0.0
        return (self.processed_books / self.total_books) * 100

    @property
    def external_data_percentage(self):
        """Calculate percentage of books with external data."""
        if self.processed_books == 0:
            return 0.0
        return (self.books_with_external_data / self.processed_books) * 100

    def add_book_to_resume_queue(self, book_id, missing_sources=None):
        """Add a book to the resumption queue."""
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
        """Remove a book from the resumption queue."""
        self.resume_queue = [item for item in self.resume_queue if item["book_id"] != book_id]
        self.can_resume = len(self.resume_queue) > 0
        self.save(update_fields=["resume_queue", "can_resume"])

    def record_api_call(self, source_name, success=True, rate_limited=False):
        """Record an API call during this session."""
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
    """Tracks API completeness for each book to optimize future scans."""

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
        """Calculate overall metadata completeness based on available data."""
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
        """Mark a specific source as complete."""
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
        """Add a source to the missing list."""
        if source_name not in self.missing_sources:
            self.missing_sources.append(source_name)
            self.needs_external_scan = True
            self.save(update_fields=["missing_sources", "needs_external_scan"])
