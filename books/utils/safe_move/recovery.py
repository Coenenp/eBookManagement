"""Recovery for interrupted safe moves.

``resolve_move`` reads a :class:`FileMove` row's state and resumes or rolls back
the move so a crash at any point never leaves a book without a valid file. It is
idempotent (re-running it on an already-resolved row is a no-op), never deletes
the library source before ``finalize_move``, and never deletes an archive copy
whose hash differs from the row.
"""

from pathlib import Path

from books.models import BookFile, FileMove, FileOperation
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


def _db_field(row):
    """The BookFile field this move tracks (``file_path`` for the main move,
    ``row.db_field`` for a companion, ``""`` for an untracked sidecar)."""
    if row.kind == FileMove.Kind.COMPANION:
        return row.db_field
    return FileMove.DBField.FILE_PATH


def _db_path_matches(row, pf):
    """True when the book file's tracked path for this row equals the target.

    A sidecar companion (blank ``db_field``) has no tracked DB field, so it is
    always treated as matching (the DB has nothing to point at it).
    """
    field = _db_field(row)
    if not field:
        return True
    return getattr(pf, field, None) == row.target_path


def _archive_matches(row):
    if not row.archived_path or not Path(row.archived_path).is_file():
        return False
    expected = row.archived_sha256 or row.original_sha256
    return bool(expected) and _sha256(row.archived_path) == expected


def _archive_present(row):
    return bool(row.archived_path) and Path(row.archived_path).is_file()


def _source_matches(row):
    if not row.source_path or not Path(row.source_path).is_file():
        return False
    return bool(row.original_sha256) and _sha256(row.source_path) == row.original_sha256


def _remove_archive_if_match(row):
    if _archive_matches(row):
        _remove(row.archived_path)


def _is_synthesized_cover(row):
    """True for the synthesized-cover companion row.

    A keep_source cover move writes no archive copy, so its ``archived_path``
    is empty. Only a COMPANION row tracking COVER_PATH qualifies; every other
    row with an empty ``archived_path`` is a normal move whose archive is
    simply missing.
    """
    return (
        row.kind == FileMove.Kind.COMPANION
        and row.db_field == FileMove.DBField.COVER_PATH
        and not row.archived_path
    )


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
        # A keep_source move (synthesized cover) writes no archive copy, so its
        # archived_path is empty; finalize_move must skip the archive check and
        # must not delete the read-only source.
        keep_source=_is_synthesized_cover(row),
    )


def _check_c_passes(row):
    """Check C: the fresh BookFile points at the target (via the row's db_field),
    the target is a file with the expected hash, and an EPUB has no blocking
    checker code."""
    target = row.target_path
    pf = _book_file(row)
    if pf is None or not _db_path_matches(row, pf):
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
    """Restore the BookFile/FinalMetadata paths from ``previous_paths`` and mark
    the rename history row created for this move as reverted."""
    book = row.book
    prev = row.previous_paths or {}
    field = _db_field(row)
    pf = _book_file(row)
    if pf is not None and field:
        if field == FileMove.DBField.FILE_PATH:
            pf.file_path = prev.get("file_path", pf.file_path)
        else:
            setattr(pf, field, prev.get(field, getattr(pf, field)))
        pf.save()  # recomputes file_path_hash when file_path changed
    if book is not None and field == FileMove.DBField.FILE_PATH:
        fm = book.final_metadata
        if fm is not None:
            fm.final_path = prev.get("final_path", fm.final_path)
            fm.is_renamed = False
            fm.save(update_fields=["final_path", "is_renamed"])
        # The rename history row for this move now describes an undone move.
        FileOperation.objects.filter(
            book=book, operation_type="rename", status="completed", new_file_path=row.target_path
        ).update(status="reverted")


def _set_state(row, state):
    row.state = state
    row.save(update_fields=["state", "updated_at"])


def _is_sidecar(row):
    """True for a companion row with a blank ``db_field`` (no DB field to track)."""
    return row.kind == FileMove.Kind.COMPANION and not row.db_field


def _rollback_sidecar(row, apply):
    """Roll back a sidecar (blank-db_field) companion row.

    The DB has no field pointing at a sidecar, so rollback is decided purely by
    file hashes: the source and archive must match the journal, and the target
    (if present) must match ``new_sha256``. Any disagreement ends the row failed
    with an error string and deletes nothing.
    """
    tgt = Path(row.target_path)
    if tgt.is_file() and (not row.new_sha256 or _sha256(tgt) != row.new_sha256):
        if apply:
            FileMove.objects.filter(pk=row.pk).update(
                state=FileMove.State.FAILED, error="target-hash-mismatch"
            )
        return "failed"
    if not _source_matches(row):
        if apply:
            FileMove.objects.filter(pk=row.pk).update(
                state=FileMove.State.FAILED, error="source-mismatch-before-rollback"
            )
        return "failed"
    if _archive_present(row) and not _archive_matches(row):
        if apply:
            FileMove.objects.filter(pk=row.pk).update(
                state=FileMove.State.FAILED, error="archive-hash-mismatch-before-rollback"
            )
        return "failed"
    if apply:
        _remove(row.tmp_path)
        _remove(row.tmp_path + ".part")
        if tgt.is_file():
            _remove(row.target_path)
        _remove_archive_if_match(row)
        _set_state(row, FileMove.State.ROLLED_BACK)
    return "rolled_back"


def resolve_move(row, apply=True):
    """Resume or roll back an interrupted move; returns the action taken.

    Actions: ``rolled_back`` (temp/archive/target removed, source intact),
    ``finalized`` (DB already updated and Check C passed -> delete source and
    set pending_deletion), ``failed`` (source gone but the archive no longer
    verifies), or ``noop`` (state not in the recovery table, or the
    preconditions for the state do not hold).
    """
    S = FileMove.State
    state = row.state

    if state in (S.PLANNED, S.TMP_WRITTEN, S.TMP_VERIFIED):
        # A partial archive copy may have been written before the crash; remove
        # it only when the source is intact and both the source and the archive
        # hash to the journal's original. Otherwise keep every file and fail.
        fail = _archive_present(row) and not (_source_matches(row) and _archive_matches(row))
        if apply:
            _remove(row.tmp_path)
            _remove(row.tmp_path + ".part")
            if fail:
                FileMove.objects.filter(pk=row.pk).update(
                    state=S.FAILED, error="archive-unverifiable-before-rollback"
                )
            elif _archive_present(row):
                _remove(row.archived_path)
                _set_state(row, S.ROLLED_BACK)
            else:
                _set_state(row, S.ROLLED_BACK)
        return "failed" if fail else "rolled_back"

    if state == S.ARCHIVED:
        if _is_sidecar(row):
            return _rollback_sidecar(row, apply)
        tgt = Path(row.target_path)
        fail = tgt.is_file() and bool(row.new_sha256) and _sha256(tgt) != row.new_sha256
        if apply:
            _remove(row.tmp_path)
            _remove(row.tmp_path + ".part")
            if fail:
                # Target hash disagrees with the journal: keep every file and fail.
                FileMove.objects.filter(pk=row.pk).update(
                    state=S.FAILED, error="target-hash-mismatch"
                )
            else:
                pf = _book_file(row)
                if (
                    tgt.is_file()
                    and row.new_sha256
                    and _sha256(tgt) == row.new_sha256
                    and not _db_path_matches(row, pf)
                ):
                    _remove(row.target_path)
                _remove_archive_if_match(row)
                _set_state(row, S.ROLLED_BACK)
        return "failed" if fail else "rolled_back"

    if state == S.COMMITTED:
        if _is_sidecar(row):
            return _rollback_sidecar(row, apply)
        # Target exists and the DB still points at the old source: undo.
        pf = _book_file(row)
        if Path(row.target_path).is_file() and not _db_path_matches(row, pf):
            if apply:
                _remove(row.target_path)
                _remove_archive_if_match(row)
                _set_state(row, S.ROLLED_BACK)
            return "rolled_back"
        return "noop"

    if state == S.DB_UPDATED:
        pf = _book_file(row)
        if not _db_path_matches(row, pf):
            return "noop"
        if Path(row.source_path).is_file():
            # Source still present: finalize or roll back as usual.
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
        # Source already gone (crash after finalize, before pending_deletion).
        tgt = Path(row.target_path)
        target_ok = tgt.is_file() and bool(row.new_sha256) and _sha256(tgt) == row.new_sha256
        # A synthesized-cover row writes no archive copy, so an empty
        # archived_path is expected and the target alone must verify. Every
        # other row needs a matching archive before the source is gone.
        if _is_synthesized_cover(row):
            if target_ok:
                if apply:
                    _set_state(row, S.PENDING_DELETION)
                return "finalized"
        elif target_ok and _archive_matches(row):
            if apply:
                _set_state(row, S.PENDING_DELETION)
            return "finalized"
        # Archive missing or differs and the source is gone: nothing to delete.
        if apply:
            FileMove.objects.filter(pk=row.pk).update(
                state=S.FAILED, error="archive-missing-after-source-removed"
            )
        return "failed"

    return "noop"
