"""Management command: move approved books into their final location.

Usage::

    python manage.py move_approved [--limit N] [--scan-folder P] [--language L]
        [--content-type T] [--folder-pattern P] [--filename-pattern P] [--execute]

Without ``--execute`` it is a dry run: it prints one line per eligible book and
a ``planned N, skipped M`` summary, but writes and moves nothing. With
``--execute`` it moves one book at a time, tags the journal rows with a single
``batch_id``, and prints ``moved / needs_review / failed / skipped`` counts.
"""

import os
import uuid
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db.models import Case, IntegerField, Max, Value, When

from books.models import FileMove
from books.utils.file_collision import resolve_collision
from books.utils.renaming_engine import RenamingEngine, is_renamable
from books.utils.safe_move import NeedsReview, safe_move_book

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
    the folder components are shortened from the deepest up.
    """
    s = str(target)
    if len(s) <= limit:
        return s
    parts = s.split("/")
    leaf = parts[-1]
    stem, ext = os.path.splitext(leaf)
    dirs = parts[:-1]

    def _joined():
        return "/".join(dirs + [stem + ext])

    # 1. Shorten the stem (title part), keeping at least 20 characters + ext.
    while len(_joined()) > limit and len(stem) > 20:
        stem = stem[:-1]

    # 2. Shorten folder components from the deepest up. Index 0 is the empty
    #    root segment and is left alone.
    while len(_joined()) > limit:
        shortened = False
        for i in range(len(dirs) - 1, 0, -1):
            if len(dirs[i]) > 1:
                dirs[i] = dirs[i][:-1]
                shortened = True
                break
        if not shortened:
            break
    return _joined()


class Command(BaseCommand):
    help = "Move approved books into their final location (dry run by default)."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=50)
        parser.add_argument("--scan-folder")
        parser.add_argument("--language")
        parser.add_argument("--content-type")
        parser.add_argument("--folder-pattern", default=None)
        parser.add_argument("--filename-pattern", default=None)
        parser.add_argument("--execute", action="store_true")

    def handle(self, *args, **options):
        limit = options["limit"]
        folder_pattern = options["folder_pattern"]
        filename_pattern = options["filename_pattern"]
        execute = options["execute"]

        qs = self._build_queryset(options)
        override = folder_pattern is not None or filename_pattern is not None

        planned = []
        skipped = []
        for book in qs:
            if len(planned) >= limit:
                break
            if not is_renamable(book):
                continue
            reason = self._skip_reason(book)
            if reason is None and not override:
                fp, _fn = self._patterns_for(book)
                if fp is None:
                    reason = "no pattern yet"
            if reason:
                skipped.append((book, reason))
            else:
                planned.append(book)

        if not execute:
            for book in planned:
                target = self._compute_target(book, folder_pattern, filename_pattern)
                language = book.finalmetadata.language if book.finalmetadata else ""
                self.stdout.write(f"{book.id} | {language} | {book.file_path} -> {target}")
            for book, reason in skipped:
                self.stdout.write(f"skipped {book.id} | {reason}")
            self.stdout.write(f"planned {len(planned)}, skipped {len(skipped)}")
            return

        batch_id = str(uuid.uuid4())
        moved = needs_review = failed = 0
        extra_skipped = []
        for book in planned:
            # Re-check approval immediately before the move.
            if not is_renamable(book):
                extra_skipped.append((book, "not approved"))
                continue
            max_pk_before = FileMove.objects.aggregate(mx=Max("pk"))["mx"] or 0
            try:
                target = self._compute_target(book, folder_pattern, filename_pattern)
                cover_path = book.finalmetadata.final_cover_path if book.finalmetadata else None
                safe_move_book(book, target, cover_path=cover_path)
                moved += 1
            except NeedsReview as exc:
                needs_review += 1
                self.stdout.write(f"needs_review {book.id} | {', '.join(exc.codes)}")
            except Exception as exc:
                failed += 1
                self.stdout.write(f"failed {book.id} | {exc}")
            finally:
                # Tag only this book's journal rows created during the call
                # (the main move plus its companions) with the run's batch id.
                FileMove.objects.filter(book=book, pk__gt=max_pk_before).update(batch_id=batch_id)

        for book, reason in skipped + extra_skipped:
            self.stdout.write(f"skipped {book.id} | {reason}")
        total_skipped = len(skipped) + len(extra_skipped)
        self.stdout.write(f"moved {moved}, needs_review {needs_review}, failed {failed}, skipped {total_skipped}")

    def _build_queryset(self, options):
        from books.models import Book

        qs = Book.objects.select_related("finalmetadata", "scan_folder")
        qs = qs.filter(finalmetadata__is_reviewed=True)
        if options.get("scan_folder"):
            qs = qs.filter(scan_folder__path=options["scan_folder"])
        if options.get("language"):
            qs = qs.filter(finalmetadata__language__iexact=options["language"])
        if options.get("content_type"):
            qs = qs.filter(content_type=options["content_type"])
        qs = qs.annotate(lang_order=LANGUAGE_ORDER).order_by(
            "lang_order",
            "scan_folder__name",
            "finalmetadata__final_series",
            "finalmetadata__final_series_number",
            "finalmetadata__final_title",
        )
        return qs

    def _skip_reason(self, book):
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

    def _patterns_for(self, book):
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

    def _resolve_patterns(self, book, folder_pattern, filename_pattern):
        if folder_pattern is None and filename_pattern is None:
            return self._patterns_for(book)
        return folder_pattern, filename_pattern

    def _compute_target(self, book, folder_pattern, filename_pattern):
        folder_pattern, filename_pattern = self._resolve_patterns(
            book, folder_pattern, filename_pattern
        )
        engine = RenamingEngine()
        base_dir = Path(book.scan_folder.path)
        folder = engine.process_template(folder_pattern, book) if folder_pattern else ""
        filename = engine.process_template(filename_pattern, book)
        target = base_dir / folder / filename if folder else base_dir / filename
        target = fit_path(str(target))
        return str(resolve_collision(str(target)))
