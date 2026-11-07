"""Book-level safe move: journal the move and keep the DB and files in sync.

``safe_move_book`` moves a book's primary file, driving the file-level
``safe_move_file`` routine and recording every step in a :class:`FileMove`
journal row so a crash at any point can be recovered by ``resolve_move``.
"""

from django.db import transaction

from books.models import BookFile, FileMove
from books.utils.renaming_engine import is_renamable
from books.utils.safe_move.archive import default_archive_root
from books.utils.safe_move.recovery import _check_c_passes, _revert_db, resolve_move
from books.utils.safe_move.routine import (
    NeedsReview,
    finalize_move,
    rollback_move,
    safe_move_file,
)


def _mark_failed_and_cleanup(row, error):
    """Record a failure, best-effort recover the files, then re-raise later.

    Records the error text (keeping the current state so ``resolve_move`` knows
    which stage it is cleaning up), runs the resolver to remove any partial
    files, and finally stamps the row ``failed``.
    """
    FileMove.objects.filter(pk=row.pk).update(error=str(error))
    row.refresh_from_db()
    try:
        resolve_move(row, apply=True)
    except Exception:
        pass  # best-effort: the journal error text and failed state are enough
    FileMove.objects.filter(pk=row.pk).update(state=FileMove.State.FAILED)
    row.refresh_from_db()
    return row


def safe_move_book(book, target_path, *, cover_path=None, repack_epub=True, fix_encoding=False):
    """Move ``book``'s primary file to ``target_path``; returns the FileMove row.

    The returned row ends in ``pending_deletion`` on success, ``needs_review``
    when a blocking check fails, ``rolled_back`` when post-commit verification
    fails, or ``failed`` when an unexpected exception occurs (which is also
    re-raised). The library source is never deleted before finalization.
    """
    target = str(target_path)

    # (a) Refuse an unapproved or incomplete book before creating any row.
    if not is_renamable(book):
        raise ValueError("book is not approved for moving")
    scan_folder = book.scan_folder
    if scan_folder is None:
        raise ValueError("book has no scan folder")
    primary_file = book.primary_file
    if primary_file is None or not primary_file.file_path:
        raise ValueError("book has no primary file")

    source_path = primary_file.file_path
    scan_label = f"{scan_folder.name} {scan_folder.id}"
    archive_root = default_archive_root(scan_folder.path)
    final_metadata = book.final_metadata

    # (b) Journal the move (planned) with the paths needed to roll back, before
    # any file operation happens.
    previous_paths = {
        "file_path": primary_file.file_path,
        "cover_path": primary_file.cover_path,
        "opf_path": primary_file.opf_path,
        "final_path": final_metadata.final_path if final_metadata else "",
    }
    row = FileMove.objects.create(
        book=book,
        source_path=source_path,
        target_path=target,
        archived_path="",
        tmp_path="",
        state=FileMove.State.PLANNED,
        previous_paths=previous_paths,
    )

    def on_step(name, step_state):
        # The finalize step has no FileMove state; skip it (the caller sets
        # ``pending_deletion`` explicitly after finalize).
        if name == "finalized":
            return
        with transaction.atomic():
            FileMove.objects.filter(pk=row.pk).update(
                state=name,
                tmp_path=step_state.get("tmp", ""),
                archived_path=step_state.get("archived_path", ""),
                original_sha256=step_state.get("original_sha256", ""),
                archived_sha256=step_state.get("archived_sha256") or "",
            )

    # (c) Run the file-level routine with the journaling callback.
    try:
        result = safe_move_file(
            source_path, target, scan_root=scan_folder.path,
            scan_label=scan_label, archive_root=archive_root,
            repack_epub=repack_epub, cover_path=cover_path,
            fix_encoding=fix_encoding, on_step=on_step,
        )
    except NeedsReview as exc:
        # (d) Blocking check failed: record needs_review, nothing else changes.
        FileMove.objects.filter(pk=row.pk).update(
            state=FileMove.State.NEEDS_REVIEW,
            review_flags=list(exc.codes),
        )
        raise

    row.refresh_from_db()
    row.new_sha256 = result.new_sha256
    row.save(update_fields=["new_sha256", "updated_at"])

    # (e) Update the DB paths in one transaction, then mark db_updated.
    try:
        with transaction.atomic():
            pf = BookFile.objects.get(pk=primary_file.pk)
            pf.file_path = target
            pf.save()  # recomputes file_path_hash
            final_metadata.mark_as_renamed(target)
            FileMove.objects.filter(pk=row.pk).update(state=FileMove.State.DB_UPDATED)
    except Exception as exc:
        _mark_failed_and_cleanup(row, exc)
        raise
    row.refresh_from_db()

    # (f) Check C: re-read the fresh BookFile and verify path + hash + EPUB.
    if not _check_c_passes(row):
        _revert_db(row)
        rollback_move(result)
        FileMove.objects.filter(pk=row.pk).update(state=FileMove.State.ROLLED_BACK)
        row.refresh_from_db()
        return row

    # (g) Finalize (delete the source only after re-verification), then purge
    # ledger state pending_deletion.
    try:
        finalize_move(result)
    except Exception as exc:
        _mark_failed_and_cleanup(row, exc)
        raise
    FileMove.objects.filter(pk=row.pk).update(state=FileMove.State.PENDING_DELETION)
    row.refresh_from_db()
    return row
