"""Book-level safe move: journal the move and keep the DB and files in sync.

``safe_move_book`` moves a book's primary file, driving the file-level
``safe_move_file`` routine and recording every step in a :class:`FileMove`
journal row so a crash at any point can be recovered by ``resolve_move``.
After the main file is finalized, companion files (cover, OPF, sidecar files)
are moved under their own child :class:`FileMove` rows.
"""

from pathlib import Path

from django.db import transaction
from django.db.models import Q

from books.models import BookFile, FileMove, FinalMetadata
from books.utils.batch_renamer import CompanionFileFinder
from books.utils.cover_cache import CoverCache
from books.utils.epub_fix.fixer import IMAGE_MEDIA_BY_EXT, _validate_cover
from books.utils.renaming_engine import is_renamable
from books.utils.safe_move.archive import default_archive_root
from books.utils.safe_move.recovery import _check_c_passes, _revert_db, resolve_move
from books.utils.safe_move.metadata_sync import build_epub_metadata, verify_opf_root
from books.utils.safe_move.sidecar_opf import build_sidecar_opf, parse_sidecar_opf
from books.utils.safe_move.routine import (
    NeedsReview,
    finalize_move,
    rollback_move,
    safe_move_file,
)


_MAGIC_BY_EXT = {
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
    ".png": (b"\x89PNG\r\n\x1a\n",),
    ".gif": (b"GIF87a", b"GIF89a"),
}


def _cover_flag(cover_path):
    """Classify a requested cover path; return a review flag or None.

    None means no cover change was requested (or the cover is valid). An empty
    string, a missing file, a directory, or an unreadable file maps to
    "cover-missing"; an existing file whose extension is not a recognised image
    type, or whose leading bytes do not match that type's magic signature, maps
    to "cover-invalid".

    The path/extension/readability checks are delegated to the fixer's
    ``_validate_cover`` (reused, not copied). Only the leading magic bytes are
    read here — never the whole file — so classifying a cover does not load it
    into memory.
    """
    if cover_path is None:
        return None
    if cover_path == "":
        return "cover-missing"
    p = Path(CoverCache.resolve_path(cover_path))
    if not p.is_file():
        return "cover-missing"
    try:
        _validate_cover(str(p))
    except ValueError:
        # _validate_cover raises for both a non-image extension and an
        # unreadable path; distinguish the two so the flag stays precise.
        if p.suffix.lower() not in IMAGE_MEDIA_BY_EXT:
            return "cover-invalid"
        return "cover-missing"
    signatures = _MAGIC_BY_EXT.get(p.suffix.lower())
    if signatures is not None:
        try:
            with p.open("rb") as fh:
                head = fh.read(8)
        except OSError:
            return "cover-missing"
        if not any(head.startswith(sig) for sig in signatures):
            return "cover-invalid"
    return None


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


def _duplicate_content_flag(book, hash_value):
    """Return ``duplicate-content:<book id>`` when another book's MAIN FileMove
    journal row already records ``hash_value`` as ``original_sha256`` or
    ``new_sha256``, else None. Companion moves (cover/OPF/sidecar) are ignored
    so two books sharing a cover or companion are never duplicates. One query
    per hash (indexed on ``original_sha256`` and ``new_sha256``); never loads
    all hashes into memory."""
    if not hash_value:
        return None
    other_book_id = (
        FileMove.objects
        .filter(Q(original_sha256=hash_value) | Q(new_sha256=hash_value), kind=FileMove.Kind.MAIN)
        .exclude(book=book)
        .values_list("book_id", flat=True)
        .first()
    )
    if other_book_id is not None:
        return f"duplicate-content:{other_book_id}"
    return None


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


def _move_companion(book, parent, source, target, db_field, *, scan_folder, scan_label, archive_root, cover_name=None, keep_source=False):
    """Move one companion under its own child :class:`FileMove` row.

    Mirrors the main move (archive, journal, Check C, finalize) but with
    ``repack_epub`` disabled and a ``db_field`` update instead of ``file_path``.
    A NeedsReview or unexpected exception leaves the companion original in
    place, ends ``needs_review``/``failed``, and flags the parent; the main move
    is never rolled back.
    """
    primary_file = book.primary_file

    # The cover companion is regenerated as a copy of the curated
    # FinalMetadata.final_cover_path (valid magic bytes) under the new stem,
    # through the generated-content hook; the old companion cover is archived
    # like any other companion. An empty/invalid curated cover keeps the
    # companion moved unchanged (its cover-missing / cover-invalid flag is set
    # by safe_move_book).
    cover_content = None
    if db_field == FileMove.DBField.COVER_PATH:
        fm = book.final_metadata
        curated = fm.final_cover_path if fm else ""
        if curated and _cover_flag(curated) is None:
            resolved = CoverCache.resolve_path(curated)
            cover_content = Path(resolved).read_bytes()
            target = str(Path(target).with_suffix(Path(resolved).suffix))

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

    # The OPF companion is regenerated from the curated metadata: its target is
    # the generated bytes, verified back through ``verify_opf_root``. The cover
    # companion is likewise generated content (a copy of the curated cover).
    content = cover_content
    verify = None
    if db_field == FileMove.DBField.OPF_PATH:
        metadata = build_epub_metadata(book)
        try:
            old_opf_bytes = Path(source).read_bytes()
        except OSError:
            old_opf_bytes = None
        content = build_sidecar_opf(metadata, cover_name=cover_name, old_opf_bytes=old_opf_bytes)

        def _verify_opf(tmp_path):
            try:
                root = parse_sidecar_opf(Path(tmp_path).read_bytes())
            except Exception:
                raise NeedsReview(["opf-unparsable"])
            mismatches = verify_opf_root(root, metadata)
            if mismatches:
                raise NeedsReview([f"opf-mismatch:{f}" for f in mismatches])

        verify = _verify_opf

    try:
        result = safe_move_file(
            source, target, scan_root=scan_folder.path, scan_label=scan_label,
            archive_root=archive_root, repack_epub=False, on_step=on_step,
            content=content, verify=verify, keep_source=keep_source,
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
    # A requested cover that cannot be embedded must not block the move: proceed
    # without a cover change and record the reason as a review flag instead.
    is_epub_repack = repack_epub and Path(source_path).suffix.lower() == ".epub"
    cover_flag = _cover_flag(cover_path) if is_epub_repack else None
    # Resolve the cover once here so the repack and the cover embed receive the
    # resolved filesystem path (a media-relative path like ``cover_cache/abc.jpg``
    # resolves against MEDIA_ROOT), never the raw relative path.
    effective_cover = None
    if cover_flag is None and cover_path:
        effective_cover = CoverCache.resolve_path(cover_path)
    metadata = build_epub_metadata(book) if is_epub_repack else None
    scan_label = f"{scan_folder.name} {scan_folder.id}"
    archive_root = default_archive_root(scan_folder.path)
    final_metadata = book.final_metadata

    # A missing or invalid final cover blocks the move before anything is
    # copied, archived or deleted: the row ends needs_review with the
    # cover-missing / cover-invalid flag. The path is resolved against the
    # media root via the single CoverCache resolver, so a media-relative path
    # (e.g. ``cover_cache/abc.jpg``) is checked against MEDIA_ROOT.
    final_cover_path = final_metadata.final_cover_path if final_metadata else ""
    final_cover_flag = None
    if primary_file.cover_path:
        final_cover_flag = _cover_flag(final_cover_path) if final_cover_path else "cover-missing"

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

    # Blocking cover check: a missing/invalid final cover ends the move in
    # needs_review before anything is copied, archived or deleted.
    if final_cover_flag is not None:
        FileMove.objects.filter(pk=row.pk).update(
            state=FileMove.State.NEEDS_REVIEW,
            review_flags=[final_cover_flag],
        )
        raise NeedsReview([final_cover_flag])

    initial_flags = []
    for flag in (cover_flag,):
        if flag is not None and flag not in initial_flags:
            initial_flags.append(flag)
    if initial_flags:
        FileMove.objects.filter(pk=row.pk).update(review_flags=initial_flags)

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
    def _recheck_approval():
        # Re-read approval from the database (a fresh query, not the cached
        # object) immediately before the commit rename, for the main move only.
        if not FinalMetadata.objects.filter(book=book, is_reviewed=True).exists():
            raise NeedsReview(["approval-revoked"])

    try:
        result = safe_move_file(
            source_path, target, scan_root=scan_folder.path,
            scan_label=scan_label, archive_root=archive_root,
            repack_epub=repack_epub, cover_path=effective_cover,
            fix_encoding=fix_encoding, on_step=on_step, metadata=metadata,
            before_commit=_recheck_approval,
            check_duplicate=lambda h: _duplicate_content_flag(book, h),
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

    # Merge the routine's review flags (e.g. cover-page-not-updated) onto the
    # row, the same way the pre-flight cover flags are stored.
    if result.review_flags:
        row.refresh_from_db()
        flags = list(row.review_flags or [])
        for f in result.review_flags:
            if f not in flags:
                flags.append(f)
        FileMove.objects.filter(pk=row.pk).update(review_flags=flags)

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
    # Part C: when the curated cover is valid but no companion cover exists on
    # disk, synthesize one beside the book. The curated file is a read-only
    # template: it is never moved, archived or deleted.
    synthetic_cover_source = None
    if final_cover_path and _cover_flag(final_cover_path) is None:
        if not primary_file.cover_path or not Path(primary_file.cover_path).is_file():
            curated = Path(CoverCache.resolve_path(final_cover_path))
            synthetic_cover_source = str(curated)
            companions.insert(0, (
                synthetic_cover_source,
                FileMove.DBField.COVER_PATH,
                str(Path(target).with_suffix(curated.suffix)),
            ))
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
    # rolls back the main move. The cover companion is first in the list by
    # construction; its target name is passed to the OPF sidecar only when the
    # cover actually moved (its child row reached pending_deletion), so a
    # failed cover leaves the OPF without a cover reference.
    cover_name = None
    for source, db_field, comp_target in companions:
        child = _move_companion(
            book, row, source, comp_target, db_field,
            scan_folder=scan_folder, scan_label=scan_label, archive_root=archive_root,
            cover_name=cover_name,
            keep_source=(source == synthetic_cover_source),
        )
        if db_field == FileMove.DBField.COVER_PATH and child.state == FileMove.State.PENDING_DELETION:
            cover_name = Path(child.target_path).name

    return row
