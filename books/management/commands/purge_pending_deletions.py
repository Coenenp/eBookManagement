"""Management command: purge archives for pending-deletion moves.

Usage::

    python manage.py purge_pending_deletions [--older-than DAYS] [--limit M]
    python manage.py purge_pending_deletions --confirm N [--older-than DAYS]

Without ``--confirm`` it lists every eligible row and deletes nothing (exit 0).
With ``--confirm N`` it deletes the archive files only when ``N`` exactly
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
from books.utils.safe_move.routine import _sha256


def _row_passes(row):
    """A pending-deletion row is purgeable only when its archive copy and its
    target both verify against the recorded hashes."""
    if not row.archived_path or not Path(row.archived_path).is_file():
        return False
    if _sha256(row.archived_path) != row.original_sha256:
        return False
    book = row.book
    pf = book.primary_file if book is not None else None
    if pf is None or pf.file_path != row.target_path:
        return False
    if not Path(row.target_path).is_file():
        return False
    if _sha256(row.target_path) != row.new_sha256:
        return False
    return True


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
        eligible = [r for r in rows if _row_passes(r)]
        failed = [r for r in rows if r not in eligible]

        # A row that fails verification is marked and skipped, never purged.
        for r in failed:
            r.state = FileMove.State.FAILED_VERIFICATION
            r.save(update_fields=["state", "updated_at"])

        count = len(eligible)
        for r in eligible:
            self.stdout.write(f"{r.pk} book={r.book_id} {r.archived_path}")

        if confirm is None:
            self.stdout.write(f"{count} eligible row(s); no files deleted")
            return

        if confirm != count:
            raise CommandError(
                f"confirmation count {confirm} does not match eligible count {count}; nothing deleted"
            )

        purged = 0
        for r in eligible:
            archive_root = self._archive_root_for(r)
            archived = r.archived_path
            parent = str(Path(archived).parent)
            try:
                os.unlink(archived)
            except OSError:
                continue
            if archive_root:
                _prune_empty_dirs(parent, archive_root)
            r.state = FileMove.State.PURGED
            r.purged_at = timezone.now()
            r.save(update_fields=["state", "purged_at", "updated_at"])
            purged += 1
        self.stdout.write(f"Purged {purged} archive file(s)")

    def _archive_root_for(self, row):
        book = row.book
        if book is not None and book.scan_folder is not None:
            return default_archive_root(book.scan_folder.path)
        return None
