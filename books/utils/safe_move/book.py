"""Book-level safe move: journal the move and keep the DB and files in sync.

``safe_move_book`` moves a book's primary file, driving the file-level
``safe_move_file`` routine and recording every step in a :class:`FileMove`
journal row so a crash at any point can be recovered by ``resolve_move``.
After the main file is finalized, companion files (cover, OPF, sidecar files)
are moved under their own child :class:`FileMove` rows.
"""

from pathlib import Path

from django.db import transaction

from books.models import BookFile, FileMove
from books.utils.batch_renamer import CompanionFileFinder
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


def _flag_companion_failure(parent, source):
    """Append ``companion-failed:<file name>`` to the parent's review flags."""
    name = Path(source).name
    flag = f"companion-failed:{name}"
    parent.refresh_from_db()
    flags = list(parent.review_flags or [])
    if flag not in flags:
        flags.append(flag)
    FileMove.objects.filter(pk=parent.pk).update(review_flags=flags)


def _flag_companion_shared(parent, source):
    """Append ``companion-shared:<file name>`` to the parent's review flags."""
    name = Path(source).name
    flag = f"companion-shared:{name}"
    parent.refresh_from_db()
    flags = list(parent.review_flags or [])
    if flag not in flags:
        flags.append(flag)
    FileMove.objects.filter(pk=parent.pk).update(review_flags=flags)


def _flag_companion_outside(parent, source):
    """Append ``companion-outside:<file name>`` to the parent's review flags."""
    name = Path(source).name
    flag = f"companion-outside:{name}"
    parent.refresh_from_db()
    flags = list(parent.review_flags or [])
    if flag not in flags:
        flags.append(flag)
    FileMove.objects.filter(pk=parent.pk).update(review_flags=flags)


def _discover_companions(primary_file, target_path):
    """Return ``([(source, db_field, target), ...], [shared], [outside])``.

    Sources are ``BookFile.cover_path`` / ``BookFile.opf_path`` (tracked with a
    ``db_field``) plus any sidecar files ``CompanionFileFinder`` discovers. Each
    target is the main file's stem plus the companion's own extension, in the
    main file's target folder; two companions with the same extension get a
    `` (2)``, `` (3)`` suffix.

    A cover/OPF path also referenced by another book, or a sidecar that belongs
    to another book (another book's tracked cover/OPF path, or a file whose
    stem matches another book's primary file in the same folder), is never
    claimed: it is left in place and reported in the returned ``shared`` list
    instead. A cover/OPF path outside the main file's source folder tree is
    also left in place and reported in the ``outside`` list.
    """
    finder = CompanionFileFinder()
    target_folder = Path(target_path).parent
    main_stem = Path(target_path).stem

    source_folder = str(Path(primary_file.file_path).parent)
    _source_folder_path = Path(source_folder).resolve()

    def _is_inside_source_folder(path):
        try:
            Path(path).resolve().relative_to(_source_folder_path)
            return True
        except ValueError:
            return False

    # Other books' primary-file stems in the SAME source folder, as plain path
    # values (no model instances), scoped by a folder-prefix filter.
    other_primary_stems = {
        Path(p).stem
        for p in BookFile.objects.exclude(pk=primary_file.pk)
        .filter(file_path__startswith=source_folder)
        .values_list("file_path", flat=True)
    }

    def _tracked_elsewhere(path):
        """True when another BookFile in this folder tracks ``path`` (cover/OPF)."""
        others = BookFile.objects.exclude(pk=primary_file.pk)
        return (
            others.filter(cover_path=path).exists()
            or others.filter(opf_path=path).exists()
        )

    ordered = []  # (source, db_field, extension)
    seen_sources = set()
    shared = []
    outside = []

    def add(source, db_field):
        s = str(source)
        if s in seen_sources:
            return
        seen_sources.add(s)
        ordered.append((s, db_field, Path(s).suffix.lower()))

    if primary_file.cover_path and Path(primary_file.cover_path).is_file():
        if not _is_inside_source_folder(primary_file.cover_path):
            outside.append(str(primary_file.cover_path))
        elif _tracked_elsewhere(str(primary_file.cover_path)):
            shared.append(str(primary_file.cover_path))
        else:
            add(primary_file.cover_path, FileMove.DBField.COVER_PATH)
    if primary_file.opf_path and Path(primary_file.opf_path).is_file():
        if not _is_inside_source_folder(primary_file.opf_path):
            outside.append(str(primary_file.opf_path))
        elif _tracked_elsewhere(str(primary_file.opf_path)):
            shared.append(str(primary_file.opf_path))
        else:
            add(primary_file.opf_path, FileMove.DBField.OPF_PATH)
    for cf in finder.find_companion_files(primary_file.file_path):
        s = str(cf)
        if _tracked_elsewhere(s) or Path(s).stem in other_primary_stems:
            if s not in shared and s not in seen_sources:
                shared.append(s)
            continue
        add(cf, "")

    result = []
    seen_ext = {}
    for source, db_field, ext in ordered:
        n = seen_ext.get(ext, 0)
        if n:
            name = f"{main_stem} ({n + 1}){ext}"
        else:
            name = f"{main_stem}{ext}"
        seen_ext[ext] = n + 1
        result.append((source, db_field, str(target_folder / name)))
    return result, shared, outside


def _move_companion(book, parent, source, target, db_field, *, scan_folder, scan_label, archive_root):
    """Move one companion under its own child :class:`FileMove` row.

    Mirrors the main move (archive, journal, Check C, finalize) but with
    ``repack_epub`` disabled and a ``db_field`` update instead of ``file_path``.
    A NeedsReview or unexpected exception leaves the companion original in
    place, ends ``needs_review``/``failed``, and flags the parent; the main move
    is never rolled back.
    """
    primary_file = book.primary_file
    previous_paths = {db_field: getattr(primary_file, db_field)} if db_field else {}
    child = FileMove.objects.create(
        book=book,
        parent=parent,
        kind=FileMove.Kind.COMPANION,
        db_field=db_field,
        source_path=str(source),
        target_path=str(target),
        archived_path="",
        tmp_path="",
        state=FileMove.State.PLANNED,
        previous_paths=previous_paths,
    )

    def on_step(name, step_state):
        if name == "finalized":
            return
        with transaction.atomic():
            FileMove.objects.filter(pk=child.pk).update(
                state=name,
                tmp_path=step_state.get("tmp", ""),
                archived_path=step_state.get("archived_path", ""),
                original_sha256=step_state.get("original_sha256", ""),
                archived_sha256=step_state.get("archived_sha256") or "",
                new_sha256=step_state.get("new_sha256") or "",
            )

    try:
        result = safe_move_file(
            source, target, scan_root=scan_folder.path, scan_label=scan_label,
            archive_root=archive_root, repack_epub=False, on_step=on_step,
        )
    except NeedsReview as exc:
        FileMove.objects.filter(pk=child.pk).update(
            state=FileMove.State.NEEDS_REVIEW, review_flags=list(exc.codes),
        )
        _flag_companion_failure(parent, source)
        return child
    except Exception as exc:
        _mark_failed_and_cleanup(child, exc)
        _flag_companion_failure(parent, source)
        return child

    child.refresh_from_db()
    child.new_sha256 = result.new_sha256
    child.save(update_fields=["new_sha256", "updated_at"])

    try:
        with transaction.atomic():
            if db_field:
                pf = BookFile.objects.get(pk=primary_file.pk)
                setattr(pf, db_field, target)
                pf.save(update_fields=[db_field])
            FileMove.objects.filter(pk=child.pk).update(state=FileMove.State.DB_UPDATED)
    except Exception as exc:
        _mark_failed_and_cleanup(child, exc)
        _flag_companion_failure(parent, source)
        return child
    child.refresh_from_db()

    if not _check_c_passes(child):
        _revert_db(child)
        rollback_move(result)
        FileMove.objects.filter(pk=child.pk).update(state=FileMove.State.ROLLED_BACK)
        child.refresh_from_db()
        return child

    try:
        finalize_move(result)
    except Exception as exc:
        _mark_failed_and_cleanup(child, exc)
        _flag_companion_failure(parent, source)
        return child
    FileMove.objects.filter(pk=child.pk).update(state=FileMove.State.PENDING_DELETION)
    child.refresh_from_db()
    return child


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
        kind=FileMove.Kind.MAIN,
        db_field=FileMove.DBField.FILE_PATH,
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
                new_sha256=step_state.get("new_sha256") or "",
            )

    # (c) Run the file-level routine with the journaling callback. Any
    # exception other than NeedsReview fails the move (partial files removed by
    # the resolver) and is re-raised; a pre-flight refusal (missing source,
    # existing target) also ends in failed, never planned.
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
    except Exception as exc:
        _mark_failed_and_cleanup(row, exc)
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

    # Discover companions while the main source still exists (finalize deletes it).
    companions, shared, outside = _discover_companions(primary_file, target)
    for shared_source in shared:
        _flag_companion_shared(row, shared_source)
    for outside_source in outside:
        _flag_companion_outside(row, outside_source)

    # (g) Finalize (delete the source only after re-verification), then purge
    # ledger state pending_deletion.
    try:
        finalize_move(result)
    except Exception as exc:
        _mark_failed_and_cleanup(row, exc)
        raise
    FileMove.objects.filter(pk=row.pk).update(state=FileMove.State.PENDING_DELETION)
    row.refresh_from_db()

    # (h) Move companions under their own child rows. A companion failure never
    # rolls back the main move.
    for source, db_field, comp_target in companions:
        _move_companion(
            book, row, source, comp_target, db_field,
            scan_folder=scan_folder, scan_label=scan_label, archive_root=archive_root,
        )

    return row
