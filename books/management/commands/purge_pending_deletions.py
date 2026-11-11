"""Management command: purge archives for pending-deletion moves.

Usage::

    python manage.py purge_pending_deletions [--older-than DAYS] [--limit M]
    python manage.py purge_pending_deletions --confirm N [--older-than DAYS]

Without ``--confirm`` it lists every eligible row and deletes nothing, and it
never writes (no row is demoted, no file deleted). With ``--confirm N`` it
demotes definite mismatches to ``failed_verification``, leaves unreadable rows
``pending_deletion``, and deletes the archive files only when ``N`` exactly
matches the eligible count computed at run time; otherwise it deletes nothing
and exits with an error. Only the archive file is deleted (never the library
source, which was already removed by ``finalize_move``); empty folders below
the archive root are pruned but the root itself is never removed.
"""

import os
from datetime import timedelta
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from books.models import FileMove
from books.utils.safe_move.archive import default_archive_root
from books.utils.safe_move.recovery import _is_synthesized_cover
from books.utils.safe_move.routine import _sha256


def _row_reason(row):
    """Return a failure reason for a pending-deletion row, or None if purgeable.

    Reasons: ``archive-missing``, ``archive-hash``, ``target-changed``,
    ``path-changed`` (the DB no longer points at the target via the row's
    ``db_field``), or ``unreadable`` (an OSError reading a file).
    """
    if not row.archived_path:
        return "archive-missing"
    if not Path(row.archived_path).is_file():
        return "archive-missing"
    try:
        archive_hash = _sha256(row.archived_path)
    except OSError:
        return "unreadable"
    if archive_hash != row.original_sha256:
        return "archive-hash"

    book = row.book
    pf = book.primary_file if book is not None else None
    field = row.db_field if row.kind == FileMove.Kind.COMPANION else FileMove.DBField.FILE_PATH
    if field and (pf is None or getattr(pf, field) != row.target_path):
        return "path-changed"
    if not Path(row.target_path).is_file():
        return "target-changed"
    try:
        target_hash = _sha256(row.target_path)
    except OSError:
        return "unreadable"
    if target_hash != row.new_sha256:
        return "target-changed"
    return None


def _prune_empty_dirs(path, archive_root):
    """Remove empty directories below ``archive_root``, never the root itself."""
    root = Path(archive_root).resolve()
    cur = Path(path).resolve()
    try:
        cur.relative_to(root)
    except ValueError:
        return
    while cur != root:
        try:
            cur.rmdir()  # only succeeds when the directory is empty
        except OSError:
            break
        cur = cur.parent


class Command(BaseCommand):
    help = "Purge archives for pending-deletion moves (exact count confirmation)."

    def add_arguments(self, parser):
        parser.add_argument("--confirm", type=int, help="Exact eligible count to confirm deletion.")
        parser.add_argument("--older-than", type=int, default=0, help="Only rows older than N days (default 0).")
        parser.add_argument("--limit", type=int, help="Maximum number of rows to process.")

    def handle(self, *args, **options):
        confirm = options["confirm"]
        older_than = options["older_than"]
        limit = options["limit"]

        qs = FileMove.objects.filter(state=FileMove.State.PENDING_DELETION)
        if older_than:
            cutoff = timezone.now() - timedelta(days=older_than)
            qs = qs.filter(updated_at__lt=cutoff)
        qs = qs.order_by("pk")
        if limit:
            qs = qs[:limit]

        rows = list(qs)
        # A keep_source row (synthesized cover) has an empty archived_path: it
        # has no archive file to delete, so it is neither a FAIL nor part of the
        # eligible/confirmation count. Only a COMPANION row tracking COVER_PATH
        # qualifies; every other empty-archived_path row is a normal row whose
        # archive is missing and is reported as archive-missing.
        keep_source = [r for r in rows if _is_synthesized_cover(r)]
        rest = [r for r in rows if not _is_synthesized_cover(r)]
        categorized = [(r, _row_reason(r)) for r in rest]
        eligible = [r for r, reason in categorized if reason is None]
        failed = [(r, reason) for r, reason in categorized if reason is not None]

        for r, reason in failed:
            self.stdout.write(f"FAIL {r.pk} book={r.book_id} reason={reason} {r.archived_path}")

        count = len(eligible)
        for r in eligible:
            self.stdout.write(f"{r.pk} book={r.book_id} {r.archived_path}")

        if confirm is None:
            # Dry run: report only, write nothing (no state changes, no deletes).
            self.stdout.write(f"{count} eligible row(s); no files deleted")
            return

        if confirm != count:
            raise CommandError(
                f"confirmation count {confirm} does not match eligible count {count}; nothing deleted"
            )

        # Demote definite mismatches to failed_verification; unreadable rows
        # stay pending_deletion (re-reported, not demoted).
        for r, reason in failed:
            if reason != "unreadable":
                r.state = FileMove.State.FAILED_VERIFICATION
                r.save(update_fields=["state", "updated_at"])

        purged = 0
        failed_unlink = 0
        for r in eligible:
            archive_root = self._archive_root_for(r)
            archived = r.archived_path
            parent = str(Path(archived).parent)
            try:
                os.unlink(archived)
            except OSError as exc:
                self.stdout.write(f"UNLINK-FAILED {r.pk} book={r.book_id} {archived}: {exc}")
                failed_unlink += 1
                continue
            if archive_root:
                _prune_empty_dirs(parent, archive_root)
            r.state = FileMove.State.PURGED
            r.purged_at = timezone.now()
            r.save(update_fields=["state", "purged_at", "updated_at"])
            purged += 1
        self.stdout.write(f"Purged {purged} archive file(s)")
        if failed_unlink:
            self.stdout.write(f"{failed_unlink} unlink failure(s)")

        # keep_source rows have no archive to delete: complete them directly.
        for r in keep_source:
            r.state = FileMove.State.PURGED
            r.purged_at = timezone.now()
            r.save(update_fields=["state", "purged_at", "updated_at"])

    def _archive_root_for(self, row):
        book = row.book
        if book is not None and book.scan_folder is not None:
            return default_archive_root(book.scan_folder.path)
        return None
