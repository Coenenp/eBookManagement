"""File-move journal and purge ledger models for the books app."""

from django.db import models

from books.models import Book


class FileMove(models.Model):
    """Journal of a single safe book-file move, plus its purge ledger.

    One row tracks a move from ``source_path`` through the safe-move state
    machine to ``pending_deletion`` and finally ``purged``. The row is the
    single place recovery (``recover_file_moves``) and purge
    (``purge_pending_deletions``) read from, so a crash at any point can be
    resumed or rolled back without guessing.
    """

    class State(models.TextChoices):
        PLANNED = "planned", "Planned"
        TMP_WRITTEN = "tmp_written", "Temp written"
        TMP_VERIFIED = "tmp_verified", "Temp verified"
        ARCHIVED = "archived", "Archived"
        COMMITTED = "committed", "Committed"
        DB_UPDATED = "db_updated", "DB updated"
        PENDING_DELETION = "pending_deletion", "Pending deletion"
        PURGED = "purged", "Purged"
        ROLLED_BACK = "rolled_back", "Rolled back"
        NEEDS_REVIEW = "needs_review", "Needs review"
        FAILED = "failed", "Failed"
        FAILED_VERIFICATION = "failed_verification", "Failed verification"

    book = models.ForeignKey(Book, on_delete=models.SET_NULL, null=True, blank=True, related_name="file_moves")

    source_path = models.TextField()
    target_path = models.TextField()
    archived_path = models.TextField(blank=True)
    tmp_path = models.TextField(blank=True)

    state = models.CharField(max_length=32, choices=State.choices, default=State.PLANNED)

    original_sha256 = models.CharField(max_length=64, blank=True)
    archived_sha256 = models.CharField(max_length=64, blank=True)
    new_sha256 = models.CharField(max_length=64, blank=True)

    review_flags = models.JSONField(default=list, blank=True)
    error = models.TextField(blank=True)
    previous_paths = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    purged_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["state"]),
        ]

    def __str__(self):
        book_label = f"Book {self.book_id}" if self.book_id else "No book"
        return f"FileMove {book_label} - {self.state}"
