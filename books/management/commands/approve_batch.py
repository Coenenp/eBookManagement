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
import random
import re
import uuid
from collections import Counter
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from books.utils.cover_cache import CoverCache

CRITERIA_VERSION = "v2"

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
    "format",
    "title stoplist",
    "title equals author",
    "duplicate",
    "suspicious pattern",
    "cover shared",
    "cover rejected by review",
    "cover empty",
    "cover url (needs download)",
    "cover missing file",
    "cover invalid image",
    "cover placeholder",
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


def _cover_reason(cover_path):
    """Return the cover sub-reason, or None when the cover qualifies.

    Reuses the move flow's ``_cover_flag`` validator (which resolves
    media-relative paths via the single ``CoverCache.resolve_path`` resolver).
    A URL cover does not qualify yet (downloads land in a later PR).
    """
    from books.utils.safe_move.book import _cover_flag

    if not cover_path:
        return "cover empty"
    if cover_path.startswith(("http://", "https://")):
        return "cover url (needs download)"
    flag = _cover_flag(cover_path)
    if flag == "cover-missing":
        return "cover missing file"
    if flag == "cover-invalid":
        return "cover invalid image"
    from books.utils.cover_quality import cover_quality_flag

    quality = cover_quality_flag(CoverCache.resolve_path(cover_path))
    if quality in ("placeholder", "shape"):
        return "cover placeholder"
    return None


class Command(BaseCommand):
    help = "Approve a batch of eligible books (prepare/report/apply/reject)."

    def add_arguments(self, parser):
        parser.add_argument("--report", action="store_true")
        parser.add_argument("--prepare", action="store_true")
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--manifest")
        parser.add_argument("--confirm", type=int)
        parser.add_argument("--exclude-ids")
        parser.add_argument("--exclude-reason", default="review")
        parser.add_argument("--allow-high-exclusion", action="store_true")
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
        cover_use = Counter()
        for title, author, isbn, cover_path in (
            Book.objects.filter(finalmetadata__isnull=False)
            .values_list(
                "finalmetadata__final_title",
                "finalmetadata__final_author",
                "finalmetadata__isbn",
                "finalmetadata__final_cover_path",
            )
            .iterator()
        ):
            dup_title_author[(_norm_text(title), _norm_author(author))] += 1
            isbn = (isbn or "").strip()
            if isbn:
                dup_isbn[isbn] += 1
            if cover_path and not cover_path.startswith(("http://", "https://")):
                cover_use[cover_path] += 1
        ctx["dup_title_author"] = dup_title_author
        ctx["dup_isbn"] = dup_isbn
        ctx["cover_use"] = cover_use

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
        cover_path = fm.final_cover_path
        if cover_path and not cover_path.startswith(("http://", "https://")):
            if ctx["cover_use"].get(cover_path, 0) > 1:
                return "cover shared"
        cover_reason = _cover_reason(fm.final_cover_path)
        if cover_reason:
            return cover_reason
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
    # Contact sheets and review exclusions
    # ------------------------------------------------------------------ #

    def _read_rejected_ids(self, manifest_dir):
        """Book ids rejected by cover review, read once per run into a set.

        ``rejected_ids.txt`` holds one ``<id><TAB><reason>`` line per rejected
        book; only the first column (the id) is read back. A missing file means
        no ids have been rejected yet.
        """
        path = Path(manifest_dir) / "rejected_ids.txt"
        if not path.exists():
            return set()
        ids = set()
        for line in path.read_text().splitlines():
            col = line.split("\t", 1)[0].strip()
            if col.isdigit():
                ids.add(int(col))
        return ids

    def _parse_exclude_ids(self, raw):
        """Parse the comma separated ``--exclude-ids`` value into ints."""
        if not raw:
            return []
        ids = []
        for part in str(raw).split(","):
            part = part.strip()
            if not part:
                continue
            if not part.isdigit():
                raise CommandError(f"refusing: invalid exclude id {part!r}")
            ids.append(int(part))
        return ids

    def _write_contact_sheets(self, selected, ctx, manifest_dir, batch_id):
        """Write contact sheets for every id of the batch, 50 covers per sheet.

        Each thumbnail is at most 150 by 225 pixels in a 10-column grid, with
        a label under it showing the book id and primary file format. A cover
        that cannot be opened is drawn as a red ``ERR`` label. Sheet file names
        are returned (and recorded in the manifest); the resolved paths are
        printed for the reviewer.
        """
        from PIL import Image, ImageDraw, ImageFont

        from books.models import FinalMetadata

        ids = [bid for _corr, bid in selected]
        if not ids:
            return []

        cover_paths = dict(
            FinalMetadata.objects.filter(book_id__in=ids).values_list(
                "book_id", "final_cover_path"
            )
        )

        COLS = 10
        SHEET_SIZE = 50
        THUMB_W, THUMB_H = 150, 225
        PAD = 4
        LABEL_H = 18
        cell_w = THUMB_W + PAD
        cell_h = THUMB_H + LABEL_H + PAD

        try:
            font = ImageFont.load_default()
        except Exception:  # pragma: no cover - Pillow always ships a default font
            font = None

        sheet_names = []
        for offset in range(0, len(ids), SHEET_SIZE):
            chunk = ids[offset : offset + SHEET_SIZE]
            rows = (len(chunk) + COLS - 1) // COLS
            sheet = Image.new("RGB", (COLS * cell_w, rows * cell_h), "white")
            draw = ImageDraw.Draw(sheet)
            for i, bid in enumerate(chunk):
                col = i % COLS
                row = i // COLS
                x = col * cell_w + PAD // 2
                y = row * cell_h + PAD // 2
                fmt = ctx["primary_file"].get(bid, ("", ""))[1]
                label = f"{bid} {fmt}"
                resolved = CoverCache.resolve_path(cover_paths.get(bid, "") or "")
                try:
                    thumb = Image.open(resolved).convert("RGB")
                    thumb.thumbnail((THUMB_W, THUMB_H))
                    sheet.paste(thumb, (x, y))
                except Exception:
                    draw.text((x, y), "ERR", fill=(255, 0, 0), font=font)
                draw.text((x, y + THUMB_H + 2), label, fill=(0, 0, 0), font=font)
            name = f"{batch_id}sheet{offset // SHEET_SIZE + 1}.png"
            sheet.save(manifest_dir / name)
            sheet_names.append(name)
            self.stdout.write(f"contact sheet: {manifest_dir / name}")
        return sheet_names

    # ------------------------------------------------------------------ #
    # Modes
    # ------------------------------------------------------------------ #

    def _prepare(self, options):
        from books.models import Book

        size = min(options["size"], MAX_SIZE)
        manifest_dir = Path(options["manifest_dir"]) if options["manifest_dir"] else DEFAULT_MANIFEST_DIR
        manifest_dir.mkdir(parents=True, exist_ok=True)
        rejected = self._read_rejected_ids(manifest_dir)
        ctx = self._build_context()

        eligible = []  # minimal tuples: (corroborated, book_id)
        for book in (
            Book.objects.select_related("finalmetadata", "scan_folder").order_by("id").iterator()
        ):
            if book.id in rejected:
                continue
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
        manifest["sheets"] = self._write_contact_sheets(selected, ctx, manifest_dir, batch_id)

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
        cover = CoverCache.resolve_path(fm.final_cover_path or "")
        return (
            f"{bid} | {fm.final_title or ''} | {fm.final_author or ''} | "
            f"{fm.language or ''} | {fmt} | {tier} | {source} | {target} | {cover}"
        )

    def _report(self, options):
        from books.models import Book

        manifest_dir = Path(options["manifest_dir"]) if options["manifest_dir"] else DEFAULT_MANIFEST_DIR
        rejected = self._read_rejected_ids(manifest_dir)
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
            if book.id in rejected:
                excluded["cover rejected by review"] += 1
                continue
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
        rid = options["reject_id"]
        reason = options["reason"] or ""
        if rid not in data.get("ids", []):
            raise CommandError(f"refusing: reject id {rid} not in manifest")
        excluded = data.setdefault("excluded", {})
        excluded[str(rid)] = reason
        # Leave the status prepared: one held-back book never blocks the batch.
        manifest_path.write_text(json.dumps(data, indent=2))
        clean = reason.replace("\t", " ").replace("\n", " ").replace("\r", " ")
        with open(manifest_path.parent / "rejected_ids.txt", "a") as fh:
            fh.write(f"{rid}\t{clean}\n")
        self.stdout.write(f"rejected {rid}: {reason}")

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

        exclude_ids = self._parse_exclude_ids(options.get("exclude_ids"))
        for eid in exclude_ids:
            if eid not in ids:
                raise CommandError(f"refusing: exclude id {eid} not in manifest")

        # Every held-back id lives in the manifest "excluded" map (id -> reason),
        # whether it came from --reject-id or from this run's --exclude-ids.
        excluded = data.setdefault("excluded", {})
        exclude_reason = options.get("exclude_reason") or "review"
        excluded.update({str(eid): exclude_reason for eid in exclude_ids})

        total = len(ids)
        excluded_count = len(excluded)
        if excluded_count * 100 > 30 * total and not options.get("allow_high_exclusion"):
            pct = excluded_count * 100.0 / total
            raise CommandError(
                f"refusing: {pct:.1f}% of manifest ids excluded (limit 30%)"
            )

        # Write this run's --exclude-ids records before the approval loop, so a
        # crash mid-apply loses nothing.
        if exclude_ids:
            with open(manifest_path.parent / "rejected_ids.txt", "a") as fh:
                for eid in exclude_ids:
                    fh.write(f"{eid}\t{exclude_reason}\n")
            manifest_path.write_text(json.dumps(data, indent=2))

        excluded_ids = {int(k) for k in excluded}
        ctx = self._build_context()
        approved = []
        skipped = 0
        for bid in ids:
            if bid in excluded_ids:
                skipped += 1
                self.stdout.write(f"skipped {bid}: {excluded.get(str(bid), 'cover review')}")
                continue
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
