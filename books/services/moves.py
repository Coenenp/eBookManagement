"""Move-planning and move-execution service for the approved-book pipeline.

This is the single source of truth for ``move_approved``. Both the management
command and the moves page (UI) call :func:`plan_moves` (dry-run plan) and
:func:`run_moves` (execute the plan). ``fit_path`` and the pattern/target
helpers live here too, so the command stays a thin printer.
"""

import uuid
from pathlib import Path, PurePosixPath, PureWindowsPath

from django.db.models import Case, Count, IntegerField, Max, Value, When

from books.models import Book, FileMove
from books.utils.renaming_engine import RenamingEngine, is_renamable
from books.utils.safe_move import NeedsReview, safe_move_book
from books.utils.safe_move.book import _cover_flag

# A move in one of these states is still in flight; recover it with
# ``recover_file_moves --apply`` rather than re-selecting the book.
UNRESOLVED_STATES = (
    FileMove.State.PLANNED,
    FileMove.State.QUEUED,
    FileMove.State.TMP_WRITTEN,
    FileMove.State.TMP_VERIFIED,
    FileMove.State.ARCHIVED,
    FileMove.State.COMMITTED,
    FileMove.State.DB_UPDATED,
)

# Known-language books come first, then ``und``, then the empty value.
LANGUAGE_ORDER = Case(
    When(finalmetadata__language="und", then=Value(1)),
    When(finalmetadata__language="", then=Value(2)),
    When(finalmetadata__language__isnull=True, then=Value(2)),
    default=Value(0),
    output_field=IntegerField(),
)

# Per-content-type approved layout (used when neither --folder-pattern nor
# --filename-pattern is supplied).
EBOOK_SERIES_FOLDER = "${language_name}/Books/${author.sortname}/${bookseries.title}"
EBOOK_SERIES_FILENAME = "${author.sortname} - ${bookseries.title} #${bookseries.number} - ${title}.${ext}"
EBOOK_STANDALONE_FOLDER = "${language_name}/Books/${author.sortname}"
EBOOK_STANDALONE_FILENAME = "${author.sortname} - ${title}.${ext}"
COMIC_SERIES_FOLDER = "${language_name}/Comics/${bookseries.title}"
COMIC_SERIES_FILENAME = "${bookseries.title} #${bookseries.number} - ${title}.${ext}"
COMIC_STANDALONE_FOLDER = "${language_name}/Comics/${title}"
COMIC_STANDALONE_FILENAME = "${title}.${ext}"


def fit_path(target, limit=240):
    """Shorten an over-long ``target`` path to at most ``limit`` characters.

    Deterministic and lossless below the limit: at or under ``limit`` the path
    is returned unchanged. Above it, the filename stem (the title part) is
    shortened first — never below 20 characters plus the extension — and then
    the folder components are shortened from the deepest up. A backslash or a
    drive letter marks a Windows path (``PureWindowsPath``); otherwise the path
    is treated as POSIX. The drive or UNC root is always preserved, and after
    shortening no component ends in a trailing space or dot.
    """
    s = str(target)
    if len(s) <= limit:
        return s
    windows = "\\" in s or (len(s) >= 2 and s[0].isalpha() and s[1] == ":")
    cls = PureWindowsPath if windows else PurePosixPath
    p = cls(s)
    anchor = p.anchor
    stem = p.stem
    ext = p.suffix
    dirs = list(p.parts[1:-1])

    def _joined():
        return str(cls(anchor).joinpath(*dirs, stem + ext))

    # 1. Shorten the filename stem, keeping at least 20 characters + ext.
    while len(_joined()) > limit and len(stem) > 20:
        stem = stem[:-1]

    # 2. Shorten folder components from the deepest up.
    while len(_joined()) > limit:
        shortened = False
        for i in range(len(dirs) - 1, -1, -1):
            if len(dirs[i]) > 1:
                dirs[i] = dirs[i][:-1]
                shortened = True
                break
        if not shortened:
            break

    # 3. Strip trailing spaces and dots from every component.
    stem = stem.rstrip(" .")
    dirs = [d.rstrip(" .") for d in dirs]
    return str(cls(anchor).joinpath(*dirs, stem + ext))


def _build_queryset(scan_folder=None, language=None, content_type=None):
    qs = Book.objects.select_related("finalmetadata", "scan_folder")
    qs = qs.filter(finalmetadata__is_reviewed=True)
    if scan_folder:
        qs = qs.filter(scan_folder__path=scan_folder)
    if language:
        qs = qs.filter(finalmetadata__language__iexact=language)
    if content_type:
        qs = qs.filter(content_type=content_type)
    qs = qs.annotate(lang_order=LANGUAGE_ORDER).order_by(
        "lang_order",
        "scan_folder__name",
        "finalmetadata__final_series",
        "finalmetadata__final_series_number",
        "finalmetadata__final_title",
    )
    return qs


def _skip_reason(book):
    if book.scan_folder is None:
        return "no scan folder"
    row = FileMove.objects.filter(book=book).order_by("-pk").first()
    if row is None:
        return None
    if row.state in UNRESOLVED_STATES:
        return f"unresolved {row.state} (recover_file_moves --apply)"
    if row.state == FileMove.State.NEEDS_REVIEW:
        return "needs_review"
    if row.state in (FileMove.State.FAILED, FileMove.State.FAILED_VERIFICATION):
        return "failed"
    if row.state in (FileMove.State.PENDING_DELETION, FileMove.State.PURGED):
        return "completed"
    return None  # rolled_back -> eligible


def _patterns_for(book):
    """Return (folder_pattern, filename_pattern) for a book, or (None, None)."""
    fm = book.finalmetadata
    series = (fm.final_series if fm else None) or ""
    if book.content_type == "ebook":
        if series:
            return EBOOK_SERIES_FOLDER, EBOOK_SERIES_FILENAME
        return EBOOK_STANDALONE_FOLDER, EBOOK_STANDALONE_FILENAME
    if book.content_type == "comic":
        if series:
            return COMIC_SERIES_FOLDER, COMIC_SERIES_FILENAME
        return COMIC_STANDALONE_FOLDER, COMIC_STANDALONE_FILENAME
    return None, None


def _resolve_patterns(book, folder_pattern, filename_pattern):
    if folder_pattern is None and filename_pattern is None:
        return _patterns_for(book)
    default_folder, default_filename = _patterns_for(book)
    if folder_pattern is None:
        folder_pattern = default_folder
    if filename_pattern is None:
        filename_pattern = default_filename
    return folder_pattern, filename_pattern


def _compute_target(book, folder_pattern, filename_pattern):
    folder_pattern, filename_pattern = _resolve_patterns(
        book, folder_pattern, filename_pattern
    )
    engine = RenamingEngine()
    base_dir = Path(book.scan_folder.path)
    folder = engine.process_template(folder_pattern, book) if folder_pattern else ""
    filename = engine.process_template(filename_pattern, book, filename=True)
    target = base_dir / folder / filename if folder else base_dir / filename
    return fit_path(str(target), limit=232)


def _cover_flags(book):
    """Return the cover review flags for a book ([] when the cover is fine)."""
    final_cover_path = book.finalmetadata.final_cover_path if book.finalmetadata else ""
    flag = _cover_flag(final_cover_path) if final_cover_path else "cover-missing"
    return [flag] if flag is not None else []


def plan_moves(
    *,
    limit=50,
    scan_folder=None,
    language=None,
    content_type=None,
    folder_pattern=None,
    filename_pattern=None,
):
    """Return the move plan for approved books. Writes nothing.

    Returns a dict with two lists:

    * ``planned`` — one entry per book that will be move-attempted, each with
      ``id``, ``language``, ``source`` (current path), ``target`` (computed
      destination) and ``flags`` (cover review flags, ``[]`` when clean).
    * ``skipped`` — one entry per book that will not be moved, each with
      ``id`` and ``reason``.

    Target-exists and cover flags are not applied here: those are dry-run
    reporting concerns (:func:`dry_run_report`) and runtime concerns
    (:func:`run_moves` re-checks target-exists; ``safe_move_book`` surfaces
    cover flags as ``NeedsReview``).
    """
    qs = _build_queryset(scan_folder=scan_folder, language=language, content_type=content_type)
    override = folder_pattern is not None or filename_pattern is not None

    planned = []
    skipped = []
    for book in qs:
        if len(planned) >= limit:
            break
        if not is_renamable(book):
            continue
        reason = _skip_reason(book)
        if reason is None and not override:
            fp, _fn = _patterns_for(book)
            if fp is None:
                reason = "no pattern yet"
        if reason:
            skipped.append({"id": book.id, "reason": reason})
        else:
            planned.append(book)

    entries = []
    for book in planned:
        try:
            target = _compute_target(book, folder_pattern, filename_pattern)
        except Exception:
            # A target that cannot be computed is left for run_moves, which
            # re-computes it and marks the book failed (see run_moves).
            target = None
        language_val = book.finalmetadata.language if book.finalmetadata else ""
        entries.append(
            {
                "id": book.id,
                "language": language_val,
                "source": book.file_path,
                "target": target,
                "flags": _cover_flags(book),
            }
        )

    return {"planned": entries, "skipped": skipped}


def dry_run_report(plan):
    """Derive the dry-run view of a plan (target-exists and cover skips)."""
    planned_out = []
    dry_skips = []
    for entry in plan["planned"]:
        if entry["target"] is None:
            dry_skips.append({"id": entry["id"], "reason": "target error"})
        elif Path(entry["target"]).exists():
            dry_skips.append({"id": entry["id"], "reason": "target-exists"})
        elif entry["flags"]:
            dry_skips.append({"id": entry["id"], "reason": entry["flags"][0]})
        else:
            planned_out.append(entry)
    return {"planned": planned_out, "skipped": plan["skipped"] + dry_skips}


def run_moves(plan, *, folder_pattern=None, filename_pattern=None):
    """Execute a move plan through ``safe_move_book`` and the FileMove journal.

    Returns a dict with the per-book ``results`` (in execution order), the
    ``extra_skipped`` books discovered at runtime (not approved, target now
    exists), the counts ``moved``/``needs_review``/``failed``/``skipped`` and
    the run's ``batch_id``.
    """
    batch_id = str(uuid.uuid4())
    moved = needs_review = failed = 0
    extra_skipped = []
    results = []

    for entry in plan["planned"]:
        book = Book.objects.get(pk=entry["id"])
        # Re-check approval immediately before the move.
        if not is_renamable(book):
            extra_skipped.append({"id": book.id, "reason": "not approved"})
            continue
        max_pk_before = FileMove.objects.aggregate(mx=Max("pk"))["mx"] or 0
        try:
            target = _compute_target(book, folder_pattern, filename_pattern)
            if Path(target).exists():
                extra_skipped.append({"id": book.id, "reason": "target-exists"})
                continue
            cover_path = book.finalmetadata.final_cover_path if book.finalmetadata else None
            safe_move_book(book, target, cover_path=cover_path)
            moved += 1
            results.append({"id": book.id, "result": "moved"})
        except NeedsReview as exc:
            needs_review += 1
            results.append({"id": book.id, "result": "needs_review", "codes": list(exc.codes)})
        except Exception as exc:
            failed += 1
            results.append({"id": book.id, "result": "failed", "error": str(exc)})
        finally:
            # Tag only this book's journal rows created during the call
            # (the main move plus its companions) with the run's batch id.
            FileMove.objects.filter(book=book, pk__gt=max_pk_before).update(batch_id=batch_id)

    skipped = len(plan["skipped"]) + len(extra_skipped)
    return {
        "results": results,
        "extra_skipped": extra_skipped,
        "moved": moved,
        "needs_review": needs_review,
        "failed": failed,
        "skipped": skipped,
        "batch_id": batch_id,
    }
