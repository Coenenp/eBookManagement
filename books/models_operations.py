"""Scan, queue, and user-related models for the books app."""

from django.db import models
from django.utils import timezone

from books.models import Book, ScanFolder


class ScanLog(models.Model):
    """Log entries for scan operations."""

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
    """Current scan status tracking."""

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
    """Track completed scans and their detailed outcomes."""

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
        """Calculate success rate."""
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
        """Generate human-readable summary."""
        parts = []

        if self.status == "completed":
            parts.append(f"Successfully processed {self.files_processed} files")
        elif self.status == "failed":
            parts.append("Scan failed")
        elif self.status == "cancelled":
            parts.append("Scan was cancelled")
        elif self.status == "partial":
            parts.append(f"Partially completed: {self.files_processed}/{self.total_files_found} files")

        if self.books_added > 0:
            parts.append(f"Added {self.books_added} new books")
        if self.books_updated > 0:
            parts.append(f"Updated {self.books_updated} existing books")
        if self.books_removed > 0:
            parts.append(f"Removed {self.books_removed} books")
        if self.errors_count > 0:
            parts.append(f"{self.errors_count} errors")
        if self.warnings_count > 0:
            parts.append(f"{self.warnings_count} warnings")
        if self.external_apis_used and self.api_requests_made > 0:
            parts.append(f"Made {self.api_requests_made} API requests")

        parts.append(f"Duration: {self.duration_formatted}")

        return " - ".join(parts)


class FileOperation(models.Model):
    """Track file operations for complete reversal capability."""

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
    """Store user feedback on AI predictions."""

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
        return (self.feedback_rating - 1) / 4.0


class UserProfile(models.Model):
    """User preferences and settings."""

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
    default_view_mode = models.CharField(max_length=10, choices=[("table", "Table"), ("grid", "Grid")], default="table")
    show_covers_in_list = models.BooleanField(default=True)
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
        """Save a custom renaming pattern."""
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
        """Remove a saved pattern by name."""
        self.saved_patterns = [p for p in self.saved_patterns if p.get("name") != name]
        self.save()

    def get_pattern(self, name):
        """Get a saved pattern by name."""
        for pattern in self.saved_patterns:
            if pattern.get("name") == name:
                return pattern
        return None

    @classmethod
    def get_or_create_for_user(cls, user):
        """Get or create profile for user."""
        profile, created = cls.objects.get_or_create(user=user)
        return profile


class SetupWizard(models.Model):
    """Track user setup wizard progress."""

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
    folder_languages = models.JSONField(default=dict, blank=True, help_text="Language preferences for each folder")
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
        """Calculate completion percentage."""
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
        """Get the next step in the wizard."""
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
        """Get the previous step in the wizard."""
        step_order = [choice[0] for choice in self.WIZARD_STEPS]
        try:
            current_index = step_order.index(self.current_step)
            if current_index > 0:
                return step_order[current_index - 1]
        except ValueError:
            pass
        return "welcome"

    def mark_step_completed(self, step):
        """Mark a specific step as completed."""
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
        """Mark wizard as skipped."""
        self.is_skipped = True
        self.is_completed = True
        self.completed_at = timezone.now()
        self.current_step = "complete"
        self.save()

    @classmethod
    def get_or_create_for_user(cls, user):
        """Get or create setup wizard for user."""
        wizard, created = cls.objects.get_or_create(user=user)
        return wizard, created


class ScanQueue(models.Model):
    """Model to track pending/future scans."""

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
        """Generate a summary of what will be scanned."""
        targets = []

        if self.scan_type == "folder" and self.folder_paths:
            folder_count = len(self.folder_paths)
            if folder_count == 1:
                targets.append(self.folder_paths[0])
            else:
                targets.append(f"{folder_count} folders")

        elif self.scan_type == "book_ids" and self.book_ids:
            targets.append(f"{len(self.book_ids)} specific books")

        elif self.scan_type == "series" and self.series_names:
            if len(self.series_names) == 1:
                targets.append(f"Series: {self.series_names[0]}")
            else:
                targets.append(f"{len(self.series_names)} series")

        elif self.scan_type == "author" and self.author_names:
            if len(self.author_names) == 1:
                targets.append(f"Author: {self.author_names[0]}")
            else:
                targets.append(f"{len(self.author_names)} authors")

        elif self.scan_type == "full":
            targets.append("Full library scan")

        elif self.scan_type == "incremental":
            targets.append("Incremental scan")

        return " | ".join(targets) if targets else "No targets specified"

    @property
    def options_summary(self):
        """Generate a summary of scan options."""
        options = []
        if self.rescan_existing:
            options.append("Rescan existing")
        if self.update_metadata:
            options.append("Update metadata")
        if self.fetch_covers:
            options.append("Fetch covers")
        if self.deep_scan:
            options.append("Deep scan")
        return " | ".join(options) if options else "Standard options"

    @property
    def is_ready_to_execute(self):
        """Check if this queue item is ready to be executed."""
        if self.status != "pending":
            return False
        if self.scheduled_for and timezone.now() < self.scheduled_for:
            return False
        return True

    @property
    def priority_display(self):
        """Get a human-readable priority label."""
        return self.get_priority_display()

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
        return self.status in ["failed", "cancelled"] and self.retry_count < self.max_retries

    def mark_processing(self, job_id):
        """Mark this queue item as currently processing."""
        self.status = "processing"
        self.actual_scan_job_id = job_id
        self.started_at = timezone.now()
        self.save(update_fields=["status", "actual_scan_job_id", "started_at", "updated_at"])

    def mark_completed(self):
        """Mark this queue item as completed."""
        self.status = "completed"
        self.completed_at = timezone.now()
        self.save(update_fields=["status", "completed_at", "updated_at"])

    def mark_failed(self, error_message=""):
        """Mark this queue item as failed."""
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
