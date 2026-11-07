"""Recovery for interrupted safe moves.

``resolve_move`` reads a :class:`FileMove` row's state and resumes or rolls back
the move so a crash at any point never leaves a book without a valid file. It is
idempotent (re-running it on an already-resolved row is a no-op), never deletes
the library source before ``finalize_move``, and never deletes an archive copy
whose hash differs from the row.
"""

from pathlib import Path

from books.models import BookFile, FileMove
from books.utils.epub_check import check_epub
from books.utils.safe_move.routine import (
    _BLOCKING_CODES,
    _EPUB_SUFFIXES,
    _remove,
    _sha256,
    MoveResult,
    finalize_move,
)


def _book_file(row):
    book = row.book
    return book.primary_file if book is not None else None


def _archive_matches(row):
    if not row.archived_path or not Path(row.archived_path).is_file():
        return False
    expected = row.archived_sha256 or row.original_sha256
    return bool(expected) and _sha256(row.archived_path) == expected


def _remove_archive_if_match(row):
    if _archive_matches(row):
        _remove(row.archived_path)


def _result_from_row(row):
    return MoveResult(
        source=row.source_path,
        target=row.target_path,
        archived_path=row.archived_path,
        original_sha256=row.original_sha256,
        archived_sha256=row.archived_sha256,
        new_sha256=row.new_sha256,
        repacked=False,
        review_flags=list(row.review_flags or []),
        created_target=True,
        tmp_path=row.tmp_path,
    )


def _check_c_passes(row):
    """Check C: the fresh BookFile points at the target, the target is a file
    with the expected hash, and an EPUB has no blocking checker code."""
    target = row.target_path
    pf = _book_file(row)
    if pf is None or pf.file_path != target:
        return False
    tgt = Path(target)
    if not tgt.is_file():
        return False
    if _sha256(target) != row.new_sha256:
        return False
    if tgt.suffix.lower() in _EPUB_SUFFIXES:
        report = check_epub(target)
        if {f.code for f in report.findings if f.code in _BLOCKING_CODES}:
            return False
    return True


def _revert_db(row):
    """Restore the BookFile/FinalMetadata paths from ``previous_paths``."""
    book = row.book
    prev = row.previous_paths or {}
    pf = _book_file(row)
    if pf is not None:
        pf.file_path = prev.get("file_path", pf.file_path)
        pf.cover_path = prev.get("cover_path", pf.cover_path)
        pf.opf_path = prev.get("opf_path", pf.opf_path)
        pf.save()  # recomputes file_path_hash
    if book is not None:
        fm = book.final_metadata
        if fm is not None:
            fm.final_path = prev.get("final_path", fm.final_path)
            fm.is_renamed = False
            fm.save(update_fields=["final_path", "is_renamed"])


def _set_state(row, state):
    row.state = state
    row.save(update_fields=["state", "updated_at"])


def resolve_move(row, apply=True):
    """Resume or roll back an interrupted move; returns the action taken.

    Actions: ``rolled_back`` (temp/archive/target removed, source intact),
    ``finalized`` (DB already updated and Check C passed -> delete source and
    set pending_deletion), or ``noop`` (state not in the recovery table, or the
    preconditions for the state do not hold).
    """
    S = FileMove.State
    state = row.state

    if state in (S.PLANNED, S.TMP_WRITTEN, S.TMP_VERIFIED):
        if apply:
            _remove(row.tmp_path)
            _remove(row.tmp_path + ".part")
            _set_state(row, S.ROLLED_BACK)
        return "rolled_back"

    if state == S.ARCHIVED:
        if apply:
            _remove(row.tmp_path)
            _remove(row.tmp_path + ".part")
            _remove_archive_if_match(row)
            _set_state(row, S.ROLLED_BACK)
        return "rolled_back"

    if state == S.COMMITTED:
        # Target exists and the DB still points at the old source: undo.
        pf = _book_file(row)
        if Path(row.target_path).is_file() and (pf is None or pf.file_path != row.target_path):
            if apply:
                _remove(row.target_path)
                _remove_archive_if_match(row)
                _set_state(row, S.ROLLED_BACK)
            return "rolled_back"
        return "noop"

    if state == S.DB_UPDATED:
        pf = _book_file(row)
        if pf is not None and pf.file_path == row.target_path and Path(row.source_path).is_file():
            if _check_c_passes(row):
                if apply:
                    finalize_move(_result_from_row(row))
                    _set_state(row, S.PENDING_DELETION)
                return "finalized"
            if apply:
                _revert_db(row)
                _remove(row.target_path)
                _remove_archive_if_match(row)
                _remove(row.tmp_path)
                _remove(row.tmp_path + ".part")
                _set_state(row, S.ROLLED_BACK)
            return "rolled_back"
        return "noop"

    return "noop"
