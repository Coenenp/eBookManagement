"""Management command: approve a batch of eligible books.

Approval is staged and gated: ``--prepare`` (the default) selects eligible
books, draws a deterministic sample, and writes a manifest; ``--report``
summarises the criteria across the whole library; ``--reject-id`` blocks a
prepared manifest; and ``--apply`` approves exactly the manifest ids after
re-checking every criterion at apply time. Nothing is approved without an
exact ``--confirm`` count and no file is ever moved.

Usage::

    python manage.py approve_batch [--report]
    python manage.py approve_batch [--size N] [--seed S] [--manifest-dir P]
    python manage.py approve_batch --reject-id N --reason TEXT --manifest M
    python manage.py approve_batch --apply --manifest M --confirm N
"""

import hashlib
import json
import os
import random
import re
import uuid
from collections import Counter
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

CRITERIA_VERSION = "v1"

# Default manifest directory lives outside the repository / working tree.
DEFAULT_MANIFEST_DIR = Path("/workspace/state/approve_batch_manifests")

# Supported primary-file formats for approval.
APPROVABLE_FORMATS = ("epub", "cbz", "cbr")

# Titles that must never be auto-approved (case-insensitive).
STOPLIST_TITLES = ("test", "untitled", "unknown", "title", "no title", "document")

# Authors that must never be auto-approved (case-insensitive).
STOPLIST_AUTHORS = ("unknown", "anonymous", "n/a", "none")

# A trailing file extension inside a title marks it as a filename, not a title.
TITLE_EXTENSION_RE = re.compile(
    r"\.(epub|cbz|cbr|cb7|cbt|pdf|mobi|azw|azw3|fb2|lit|prc|mp3|m4a|m4b)$",
    re.IGNORECASE,
)

# One constant list of suspicious-pattern checks. Each entry is a
# (name, predicate) pair; the predicate takes (title, author) and returns
# True when the book trips that pattern (and must therefore be excluded).
SUSPICIOUS_PATTERNS = [
    ("contains_http", lambda t, a: "http" in t.lower() or "http" in a.lower()),
    ("contains_www", lambda t, a: "www" in t.lower() or "www" in a.lower()),
    ("contains_at", lambda t, a: "@" in t or "@" in a),
    ("title_has_extension", lambda t, a: bool(TITLE_EXTENSION_RE.search(t.strip()))),
    ("all_digit_title", lambda t, a: t.strip().isdigit()),
    ("title_too_short", lambda t, a: len(t.strip()) < 2),
    ("title_too_long", lambda t, a: len(t.strip()) > 200),
    ("author_has_digit", lambda t, a: any(ch.isdigit() for ch in a)),
    ("author_in_stoplist", lambda t, a: a.strip().lower() in STOPLIST_AUTHORS),
    ("title_contains_copy_of", lambda t, a: "copy of" in t.lower()),
    ("title_contains_scan", lambda t, a: "scan" in t.lower()),
]

# Exclusion reasons, in the order the criteria are evaluated. ``_exclusion``
# returns the first (and only the first) reason that applies, so the report can
# attribute each excluded book to exactly one criterion.
CRITERIA_LABELS = [
    "no final metadata",
    "already reviewed",
    "unresolved reason",
    "language",
    "title confidence",
    "author confidence",
    "cover confidence",
    "cover file",
    "format",
    "title stoplist",
    "title equals author",
    "duplicate",
    "suspicious pattern",
]

CONFIDENCE_THRESHOLD = 0.80
CORROBORATED_THRESHOLD = 0.90
MAX_SIZE = 200
MAX_SAMPLE = 20


def _norm_text(value):
    """casefold, strip punctuation, collapse whitespace."""
    v = (value or "").casefold()
    v = re.sub(r"[^\w\s]", " ", v)
    return re.sub(r"\s+", " ", v).strip()


def _norm_author(value):
    """Normalize an author and reduce it to a sorted token form."""
    return " ".join(sorted(_norm_text(value).split()))


def _conf(value):
    """Treat a None confidence as 0.0 (fields are non-null, but be safe)."""
    return value if value is not None else 0.0


def _get_fm(book):
    """Return the book's FinalMetadata, or None when it has no row."""
    from books.models import FinalMetadata

    try:
        return book.finalmetadata
    except FinalMetadata.DoesNotExist:
        return None


def _resolve_cover_path(cover_path):
    """Resolve a cover path to a filesystem path.

    A relative path is resolved against ``settings.MEDIA_ROOT`` (the same key
    the move flow uses for ``cover_cache/...`` paths); an absolute path and an
    empty value are returned unchanged.
    """
    if not cover_path:
        return ""
    if os.path.isabs(cover_path):
        return cover_path
    return os.path.join(settings.MEDIA_ROOT, cover_path)


class Command(BaseCommand):
    help = "Approve a batch of eligible books (prepare/report/apply/reject)."

    def add_arguments(self, parser):
        parser.add_argument("--report", action="store_true")
        parser.add_argument("--prepare", action="store_true")
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--manifest")
        parser.add_argument("--confirm", type=int)
        parser.add_argument("--reject-id", type=int)
        parser.add_argument("--reason")
        parser.add_argument("--size", type=int, default=25)
        parser.add_argument("--seed", type=int)
        parser.add_argument("--manifest-dir")

    def handle(self, *args, **options):
        if options["report"]:
            self._report(options)
        elif options["apply"]:
            self._apply(options)
        elif options["reject_id"] is not None:
            self._reject(options)
        else:
            self._prepare(options)

    # ------------------------------------------------------------------ #
    # Context (one streaming pass over the library, no per-book queries)
    # ------------------------------------------------------------------ #

    def _build_context(self):
        """Primary-file map and duplicate counters, each in a single pass."""
        from books.models import Book, BookFile

        ctx = {}

        primary_file = {}
        for row in (
            BookFile.objects.order_by("book_id", "chapter_sort", "track_number")
            .values_list("book_id", "file_path", "file_format")
            .iterator()
        ):
            if row[0] not in primary_file:
                primary_file[row[0]] = (row[1] or "", (row[2] or "").lower())
        ctx["primary_file"] = primary_file

        dup_title_author = Counter()
        dup_isbn = Counter()
        for title, author, isbn in (
            Book.objects.filter(finalmetadata__isnull=False)
            .values_list("finalmetadata__final_title", "finalmetadata__final_author", "finalmetadata__isbn")
            .iterator()
        ):
            dup_title_author[(_norm_text(title), _norm_author(author))] += 1
            isbn = (isbn or "").strip()
            if isbn:
                dup_isbn[isbn] += 1
        ctx["dup_title_author"] = dup_title_author
        ctx["dup_isbn"] = dup_isbn

        return ctx

    # ------------------------------------------------------------------ #
    # Criteria
    # ------------------------------------------------------------------ #

    def _exclusion(self, book, fm, ctx):
        """Return the first failing criterion label, or None if eligible."""
        if fm is None:
            return "no final metadata"
        if fm.is_reviewed:
            return "already reviewed"
        if fm.unresolved_reason:
            return "unresolved reason"
        lang = (fm.language or "").strip()
        if not lang or lang == "und":
            return "language"
        if _conf(fm.final_title_confidence) < CONFIDENCE_THRESHOLD:
            return "title confidence"
        if _conf(fm.final_author_confidence) < CONFIDENCE_THRESHOLD:
            return "author confidence"
        if _conf(fm.final_cover_confidence) < CONFIDENCE_THRESHOLD:
            return "cover confidence"
        if not fm.final_cover_path or not os.path.exists(_resolve_cover_path(fm.final_cover_path)):
            return "cover file"
        if ctx["primary_file"].get(book.id, ("", ""))[1] not in APPROVABLE_FORMATS:
            return "format"
        title = fm.final_title or ""
        if title.strip().lower() in STOPLIST_TITLES:
            return "title stoplist"
        if _norm_text(title) == _norm_text(fm.final_author):
            return "title equals author"
        key = (_norm_text(title), _norm_author(fm.final_author))
        if ctx["dup_title_author"].get(key, 0) > 1:
            return "duplicate"
        isbn = (fm.isbn or "").strip()
        if isbn and ctx["dup_isbn"].get(isbn, 0) > 1:
            return "duplicate"
        author = fm.final_author or ""
        for _name, pred in SUSPICIOUS_PATTERNS:
            if pred(title, author):
                return "suspicious pattern"
        return None

    def _planned_target(self, book):
        """Planned destination using the same planner as move_approved."""
        if book.scan_folder is None:
            return ""
        from books.management.commands.move_approved import Command as MoveApprovedCommand

        try:
            mv = MoveApprovedCommand()
            folder_pattern, filename_pattern = mv._patterns_for(book)
            return mv._compute_target(book, folder_pattern, filename_pattern)
        except Exception as exc:
            return f"planner error: {type(exc).__name__}: {exc}"

    # ------------------------------------------------------------------ #
    # Modes
    # ------------------------------------------------------------------ #

    def _prepare(self, options):
        from books.models import Book

        size = min(options["size"], MAX_SIZE)
        ctx = self._build_context()

        eligible = []  # minimal tuples: (corroborated, book_id)
        for book in (
            Book.objects.select_related("finalmetadata", "scan_folder").order_by("id").iterator()
        ):
            fm = _get_fm(book)
            if self._exclusion(book, fm, ctx):
                continue
            corroborated = _conf(fm.final_title_confidence) >= CORROBORATED_THRESHOLD
            eligible.append((corroborated, book.id))

        eligible.sort(key=lambda e: (-e[0], e[1]))
        selected = eligible[:size]

        batch_id = str(uuid.uuid4())
        seed = options["seed"]
        if seed is None:
            seed = int.from_bytes(hashlib.md5(batch_id.encode()).digest()[:4], "big")
        rng = random.Random(seed)
        n_sample = min(len(selected), MAX_SAMPLE)
        sample_entries = rng.sample(selected, n_sample) if n_sample else []

        manifest = {
            "batch_id": batch_id,
            "criteria_version": CRITERIA_VERSION,
            "ids": [bid for _corr, bid in selected],
            "sample_ids": [bid for _corr, bid in sample_entries],
            "status": "prepared",
        }

        manifest_dir = Path(options["manifest_dir"]) if options["manifest_dir"] else DEFAULT_MANIFEST_DIR
        manifest_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = manifest_dir / f"{batch_id}.json"
        manifest_path.write_text(json.dumps(manifest, indent=2))

        self.stdout.write(f"batch_id: {batch_id}")
        self.stdout.write(f"manifest: {manifest_path}")
        for corroborated, bid in sample_entries:
            self.stdout.write(self._sample_line(bid, corroborated, ctx))

    def _sample_line(self, bid, corroborated, ctx):
        """Full detail line for one sampled entry; the planner runs only here."""
        from books.models import Book

        book = Book.objects.select_related("finalmetadata", "scan_folder").filter(id=bid).first()
        fm = _get_fm(book)
        source, fmt = ctx["primary_file"].get(bid, ("", ""))
        tier = "corroborated" if corroborated else "standard"
        target = self._planned_target(book)
        return (
            f"{bid} | {fm.final_title or ''} | {fm.final_author or ''} | "
            f"{fm.language or ''} | {fmt} | {tier} | {source} | {target}"
        )

    def _report(self, options):
        from books.models import Book

        ctx = self._build_context()
        total = Book.objects.count()

        excluded = Counter()
        by_format = Counter()
        by_language = Counter()
        by_tier = Counter()
        eligible_count = 0

        for book in (
            Book.objects.select_related("finalmetadata", "scan_folder").order_by("id").iterator()
        ):
            fm = _get_fm(book)
            reason = self._exclusion(book, fm, ctx)
            if reason:
                excluded[reason] += 1
                continue
            eligible_count += 1
            by_format[ctx["primary_file"].get(book.id, ("", ""))[1]] += 1
            by_language[fm.language or ""] += 1
            tier = "corroborated" if _conf(fm.final_title_confidence) >= CORROBORATED_THRESHOLD else "standard"
            by_tier[tier] += 1

        self.stdout.write(f"total books: {total}")
        self.stdout.write(f"eligible: {eligible_count}")
        self.stdout.write("exclusions:")
        for label in CRITERIA_LABELS:
            self.stdout.write(f"  {label}: {excluded.get(label, 0)}")
        self.stdout.write("eligible by format:")
        for fmt, n in sorted(by_format.items()):
            self.stdout.write(f"  {fmt}: {n}")
        self.stdout.write("eligible by language:")
        for lang, n in sorted(by_language.items()):
            self.stdout.write(f"  {lang}: {n}")
        self.stdout.write("eligible by confidence tier:")
        for tier, n in sorted(by_tier.items()):
            self.stdout.write(f"  {tier}: {n}")

    def _reject(self, options):
        manifest_path = Path(options["manifest"])
        data = json.loads(manifest_path.read_text())
        data["status"] = "blocked"
        data["rejection_reason"] = options["reason"] or ""
        data["rejected_id"] = options["reject_id"]
        manifest_path.write_text(json.dumps(data, indent=2))
        self.stdout.write(f"blocked {options['reject_id']}: {options['reason']}")

    def _apply(self, options):
        from books.models import Book
        from books.scanner.match_verification import mark_resolved

        manifest_path = Path(options["manifest"])
        data = json.loads(manifest_path.read_text())
        if data.get("status") == "blocked":
            raise CommandError("refusing: manifest is blocked")

        ids = data.get("ids", [])
        confirm = options["confirm"]
        if confirm != len(ids):
            raise CommandError(f"refusing: confirm {confirm} != id count {len(ids)}")

        ctx = self._build_context()
        approved = []
        skipped = 0
        for bid in ids:
            book = Book.objects.select_related("finalmetadata").filter(id=bid).first()
            if book is None:
                skipped += 1
                self.stdout.write(f"skipped {bid}: missing")
                continue
            fm = _get_fm(book)
            if fm is None:
                skipped += 1
                self.stdout.write(f"skipped {bid}: no final metadata")
                continue
            reason = self._exclusion(book, fm, ctx)
            if reason:
                skipped += 1
                self.stdout.write(f"skipped {bid}: {reason}")
                continue
            fm.is_reviewed = True
            fm.save(update_fields=["is_reviewed"])
            mark_resolved(book)
            approved.append(bid)

        data["status"] = "applied"
        data["applied_at"] = timezone.now().isoformat()
        data["applied_ids"] = approved
        manifest_path.write_text(json.dumps(data, indent=2))
        self.stdout.write(f"approved {len(approved)}, skipped {skipped}")
