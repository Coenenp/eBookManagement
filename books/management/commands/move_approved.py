"""Management command: move approved books into their final location.

Usage::

    python manage.py move_approved [--limit N] [--scan-folder P] [--language L]
        [--content-type T] [--folder-pattern P] [--filename-pattern P] [--execute]

Without ``--execute`` it is a dry run: it prints one line per eligible book and
a ``planned N, skipped M`` summary, but writes and moves nothing. With
``--execute`` it moves one book at a time, tags the journal rows with a single
``batch_id``, and prints ``moved / needs_review / failed / skipped`` counts.
"""

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

DEFAULT_FOLDER_PATTERN = "${category}/${author.sortname}/${bookseries.title}"
DEFAULT_FILENAME_PATTERN = "${author.sortname} - ${bookseries.title} #${bookseries.number} - ${title}.${ext}"


class Command(BaseCommand):
    help = "Move approved books into their final location (dry run by default)."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=50)
        parser.add_argument("--scan-folder")
        parser.add_argument("--language")
        parser.add_argument("--content-type")
        parser.add_argument("--folder-pattern", default=DEFAULT_FOLDER_PATTERN)
        parser.add_argument("--filename-pattern", default=DEFAULT_FILENAME_PATTERN)
        parser.add_argument("--execute", action="store_true")

    def handle(self, *args, **options):
        limit = options["limit"]
        folder_pattern = options["folder_pattern"]
        filename_pattern = options["filename_pattern"]
        execute = options["execute"]

        qs = self._build_queryset(options)

        planned = []
        skipped = []
        for book in qs:
            if len(planned) >= limit:
                break
            if not is_renamable(book):
                continue
            reason = self._skip_reason(book)
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
                # Tag every journal row created during this book's call (the
                # main move plus its companions) with the run's batch id,
                # including rows of books that end needs_review or failed.
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

    def _compute_target(self, book, folder_pattern, filename_pattern):
        engine = RenamingEngine()
        base_dir = Path(book.scan_folder.path)
        folder = engine.process_template(folder_pattern, book) if folder_pattern else ""
        filename = engine.process_template(filename_pattern, book)
        target = base_dir / folder / filename if folder else base_dir / filename
        return str(resolve_collision(str(target)))
