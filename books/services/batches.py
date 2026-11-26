"""Approve-batch service: holds, reject and apply for a batch of eligible books.

This is the single source of truth for the ``approve_batch`` writing actions.
Both the management command and the batch review page (UI) call
:func:`apply_batch`, :func:`reject_books`, :func:`read_holds` and
:func:`add_holds`, so the command stays a thin printer.

Approval is staged and gated: ``apply_batch`` approves exactly the manifest
ids after re-checking every criterion at apply time; ``reject_books`` records
a rejection (hold) for one book; the holds file (``rejected_ids.txt`` in the
manifest folder) persists every held-back id so later runs skip it. Nothing is
approved without an exact confirm count and no file is ever moved.
"""

import hashlib
import json
import random
import re
import uuid
from collections import Counter
from pathlib import Path

from django.utils import timezone

from books.utils.cover_cache import CoverCache
from books.utils.name_match import name_agrees

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
    "name mismatch",
    "series junk",
    "series number",
    "series from title",
    "title noise",
    "url in name",
    "cover shared",
    "cover rejected by review",
    "cover empty",
    "cover url (needs download)",
    "cover missing file",
    "cover invalid image",
    "cover placeholder",
    "cover shape",
    "cover small",
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
    if quality == "placeholder":
        return "cover placeholder"
    if quality == "shape":
        return "cover shape"
    if quality == "small":
        return "cover small"
    return None


_SERIES_DIGIT_ADJACENT_RE = re.compile(r"[a-zA-Z]\d|\d[a-zA-Z]")


def _series_is_junk(series):
    """True when a non-empty series name looks like junk (unreviewable)."""
    s = (series or "").strip()
    if not s:
        return False
    # A bracketed annotation ("[ ed.]") marks an anthology/editor note, not a
    # real series name.
    if "[" in s or "]" in s:
        return True
    # No letter at all: "4 3 2" carries no series identity.
    if not any(ch.isalpha() for ch in s):
        return True
    # A digit directly attached to a letter: "martin6".
    if _SERIES_DIGIT_ADJACENT_RE.search(s):
        return True
    # A single token that is all lowercase and has at least one cased letter:
    # "martin". A single token in a script without case (Hebrew, Chinese, Thai)
    # has token.lower() == token.upper() and is therefore not junk.
    tokens = s.split()
    if (
        len(tokens) == 1
        and tokens[0].lower() != tokens[0].upper()
        and tokens[0] == tokens[0].lower()
    ):
        return True
    return False


_URL_IN_NAME_RE = re.compile(r"https?://|www\.", re.IGNORECASE)


def _series_number_value(series_number):
    """The series number read as a number (float), or None when empty/unparseable."""
    s = (series_number or "").strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _series_from_title(title, series, series_number):
    """True when the series merely repeats the title's words plus its number."""
    s = (series or "").strip()
    if not s:
        return False
    series_val = _series_number_value(series_number)
    if series_val is None:
        return False
    words = (title or "").split()
    if len(words) < 2:
        return False
    last = words[-1]
    if not last.isdigit():
        return False
    if _series_number_value(last) != series_val:
        return False
    return " ".join(words[:-1]).casefold() == s.casefold()


_TITLE_SERIES_MARKER_RE = re.compile(r"#\s*\d")


def _title_is_noisy(title, series_number):
    """True when the final title carries a marker that does not belong in it."""
    t = (title or "").strip()
    if not t:
        return False
    # (1) starts with "by " (case-insensitive); (2) contains " - ".
    if t.casefold().startswith("by "):
        return True
    if " - " in t:
        return True
    # (3) a series marker: "#" directly followed (after optional spaces) by a
    # digit, e.g. "Strange the Dreamer #2_UK".
    if _TITLE_SERIES_MARKER_RE.search(t):
        return True
    # (4) a series number repeated at the start of the title: the first word is
    # all digits and equals the series number ("023" and "23").
    first_word = t.split()[0]
    if first_word.isdigit():
        series_val = _series_number_value(series_number)
        if series_val is not None and _series_number_value(first_word) == series_val:
            return True
    return False


def _url_in_name(title, author):
    """True when the final title or author carries a URL-like marker."""
    return bool(_URL_IN_NAME_RE.search(f"{title or ''} {author or ''}"))


# ------------------------------------------------------------------ #
# Context (one streaming pass over the library, no per-book queries)
# ------------------------------------------------------------------ #


def _build_context():
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


def _exclusion(book, fm, ctx):
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
    source_path = ctx["primary_file"].get(book.id, ("", ""))[0]
    if not name_agrees(title, author, source_path):
        return "name mismatch"
    if _series_is_junk(fm.final_series):
        return "series junk"
    series_num = _series_number_value(fm.final_series_number)
    if series_num is not None and series_num >= 1000:
        return "series number"
    if _series_from_title(title, fm.final_series, fm.final_series_number):
        return "series from title"
    if _title_is_noisy(title, fm.final_series_number):
        return "title noise"
    if _url_in_name(title, author):
        return "url in name"
    cover_path = fm.final_cover_path
    if cover_path and not cover_path.startswith(("http://", "https://")):
        if ctx["cover_use"].get(cover_path, 0) > 1:
            return "cover shared"
    cover_reason = _cover_reason(fm.final_cover_path)
    if cover_reason:
        return cover_reason
    return None


# ------------------------------------------------------------------ #
# Holds (rejected_ids.txt)
# ------------------------------------------------------------------ #


def read_holds(manifest_dir):
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


def add_holds(ids, manifest_dir, reason):
    """Append one ``<id><TAB><reason>`` line per id to ``rejected_ids.txt``.

    A hold made with exclude ids persists: later runs skip every id that
    appears here (``read_holds`` reads only the id column).
    """
    path = Path(manifest_dir) / "rejected_ids.txt"
    with open(path, "a") as fh:
        for rid in ids:
            fh.write(f"{rid}\t{reason}\n")


def _parse_exclude_ids(raw):
    """Parse the comma separated ``--exclude-ids`` value.

    Returns ``(ids, error)``; ``error`` is a refusal message or ``None``.
    """
    if not raw:
        return [], None
    ids = []
    for part in str(raw).split(","):
        part = part.strip()
        if not part:
            continue
        if not part.isdigit():
            return None, f"refusing: invalid exclude id {part!r}"
        ids.append(int(part))
    return ids, None


# ------------------------------------------------------------------ #
# Service functions
# ------------------------------------------------------------------ #


def reject_books(manifest_path, reject_id, reason):
    """Record a rejection (hold) for one book in a prepared manifest.

    Returns a dict with either a ``refusal`` message (the id is not in the
    manifest) or a ``line`` to print. The hold is recorded in the manifest's
    ``excluded`` map and appended to ``rejected_ids.txt``.
    """
    manifest_path = Path(manifest_path)
    data = json.loads(manifest_path.read_text())
    reason = reason or ""
    if reject_id not in data.get("ids", []):
        return {"refusal": f"refusing: reject id {reject_id} not in manifest"}
    excluded = data.setdefault("excluded", {})
    excluded[str(reject_id)] = reason
    # Leave the status prepared: one held-back book never blocks the batch.
    manifest_path.write_text(json.dumps(data, indent=2))
    clean = reason.replace("\t", " ").replace("\n", " ").replace("\r", " ")
    add_holds([reject_id], manifest_path.parent, clean)
    return {"line": f"rejected {reject_id}: {reason}"}


def apply_batch(
    manifest_path,
    confirm,
    exclude_ids,
    exclude_reason,
    allow_high_exclusion,
    manifest_dir=None,
):
    """Apply a prepared batch: approve exactly the manifest ids, re-checking
    every criterion at apply time. Never moves files.

    Returns a dict with either a ``refusal`` message (blocked manifest, wrong
    confirm count, an invalid or unknown exclude id, or the exclusion valve),
    or the ``approved``/``skipped`` results and their counts.
    """
    from books.models import Book
    from books.scanner.match_verification import mark_resolved

    manifest_path = Path(manifest_path)
    data = json.loads(manifest_path.read_text())
    if data.get("status") == "blocked":
        return {"refusal": "refusing: manifest is blocked"}

    ids = data.get("ids", [])
    if confirm != len(ids):
        return {"refusal": f"refusing: confirm {confirm} != id count {len(ids)}"}

    exclude_ids, parse_error = _parse_exclude_ids(exclude_ids)
    if parse_error:
        return {"refusal": parse_error}
    for eid in exclude_ids:
        if eid not in ids:
            return {"refusal": f"refusing: exclude id {eid} not in manifest"}

    # Every held-back id lives in the manifest "excluded" map (id -> reason),
    # whether it came from --reject-id or from this run's --exclude-ids.
    excluded = data.setdefault("excluded", {})
    exclude_reason = exclude_reason or "review"
    excluded.update({str(eid): exclude_reason for eid in exclude_ids})

    total = len(ids)
    excluded_count = len(excluded)
    if excluded_count * 100 > 30 * total and not allow_high_exclusion:
        pct = excluded_count * 100.0 / total
        return {"refusal": f"refusing: {pct:.1f}% of manifest ids excluded (limit 30%)"}

    manifest_dir = Path(manifest_dir) if manifest_dir else manifest_path.parent

    # Write this run's --exclude-ids records before the approval loop, so a
    # crash mid-apply loses nothing.
    if exclude_ids:
        add_holds(exclude_ids, manifest_dir, exclude_reason)
        manifest_path.write_text(json.dumps(data, indent=2))

    excluded_ids = {int(k) for k in excluded}
    ctx = _build_context()
    approved = []
    skipped = []
    for bid in ids:
        if bid in excluded_ids:
            skipped.append({"id": bid, "reason": excluded.get(str(bid), "cover review")})
            continue
        book = Book.objects.select_related("finalmetadata").filter(id=bid).first()
        if book is None:
            skipped.append({"id": bid, "reason": "missing"})
            continue
        fm = _get_fm(book)
        if fm is None:
            skipped.append({"id": bid, "reason": "no final metadata"})
            continue
        reason = _exclusion(book, fm, ctx)
        if reason:
            skipped.append({"id": bid, "reason": reason})
            continue
        fm.is_reviewed = True
        fm.save(update_fields=["is_reviewed"])
        mark_resolved(book)
        approved.append(bid)

    data["status"] = "applied"
    data["applied_at"] = timezone.now().isoformat()
    data["applied_ids"] = approved
    manifest_path.write_text(json.dumps(data, indent=2))

    return {
        "approved": approved,
        "skipped": skipped,
        "approved_count": len(approved),
        "skipped_count": len(skipped),
    }


# ------------------------------------------------------------------ #
# Report and prepare
# ------------------------------------------------------------------ #


def _apply_command_text(manifest_path, n_ids):
    """The exact command to apply a prepared batch, with the manifest path and
    id count filled in; only ``--exclude-ids`` is left for the user to type."""
    return (
        "python manage.py approve_batch --apply "
        f"--manifest {manifest_path} --confirm {n_ids} "
        "--exclude-ids <comma separated ids>"
    )


def _planned_target(book):
    """Planned destination using the shared moves planner."""
    if book.scan_folder is None:
        return ""
    from books.services.moves import _compute_target, _patterns_for

    try:
        folder_pattern, filename_pattern = _patterns_for(book)
        return _compute_target(book, folder_pattern, filename_pattern)
    except Exception as exc:
        return f"planner error: {type(exc).__name__}: {exc}"


def _target_parts(target, scan_path):
    """Split a planned target into ``(folder, file name)``.

    ``folder`` is the directory part without the scan-folder prefix (so it
    starts with the language folder); ``file name`` is the base name.
    """
    if not target:
        return "", ""
    t = Path(target)
    filename = t.name
    folder = str(t.parent)
    if scan_path:
        scan = str(Path(scan_path)).rstrip("/\\")
        if folder == scan:
            folder = ""
        elif folder.startswith(scan + "/") or folder.startswith(scan + "\\"):
            folder = folder[len(scan) + 1 :]
    return folder, filename


def _write_contact_sheets(selected, ctx, manifest_dir, batch_id):
    """Write contact sheets for every id of the batch, 50 covers per sheet.

    Returns ``(sheet_names, lines)``: the sheet file names (recorded in the
    manifest) and the resolved paths to print for the reviewer.
    """
    from PIL import Image, ImageDraw, ImageFont

    from books.models import FinalMetadata

    ids = [bid for _corr, bid in selected]
    if not ids:
        return [], []

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
    lines = []
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
        lines.append(f"contact sheet: {manifest_dir / name}")
    return sheet_names, lines


def _path_tail(source_path):
    """The last two path components (folder and file name) for display."""
    parts = [p for p in re.split(r"[\\/]+", source_path or "") if p]
    return " / ".join(parts[-2:])


def _cover_data_uri(cover_path):
    """A JPEG data URI thumbnail (max 150x225 px), or None when unreadable."""
    import base64
    import io

    from PIL import Image

    resolved = CoverCache.resolve_path(cover_path)
    try:
        im = Image.open(resolved).convert("RGB")
        im.thumbnail((150, 225))
        buf = io.BytesIO()
        im.save(buf, format="JPEG")
        return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception:
        return None


def _write_review_page(selected, ctx, manifest_dir, batch_id, sample_ids, targets):
    """Write a self-contained review HTML page (no scripts, no external assets).

    Returns ``(page_name, line)``; both are ``None`` when there is nothing to
    review.
    """
    import html

    from books.models import Book
    from books.utils.renaming_engine import RenamingEngine

    ids = sorted(bid for _corr, bid in selected)
    if not ids:
        return None, None

    books = {
        b.id: b
        for b in Book.objects.select_related("finalmetadata", "scan_folder").filter(
            id__in=ids
        )
    }
    engine = RenamingEngine()
    corroborated = {bid: c for c, bid in selected}

    rows = []
    for bid in ids:
        book = books.get(bid)
        fm = book.finalmetadata if book is not None else None
        title = (fm.final_title if fm else None) or ""
        language = (fm.language if fm else None) or ""
        series = (fm.final_series if fm else None) or ""
        series_number = (fm.final_series_number if fm else None) or ""
        cover_path = (fm.final_cover_path if fm else None) or ""

        last_name = ""
        first_name = ""
        if book is not None:
            engine.current_book = book
            sortname = engine._get_author_sortname() or ""
            if "," in sortname:
                last_name, first_name = sortname.split(",", 1)
            else:
                last_name = sortname
            last_name = (last_name or "").strip()
            first_name = (first_name or "").strip()

        source, fmt = ctx["primary_file"].get(bid, ("", ""))
        tier = "corroborated" if corroborated.get(bid, False) else "standard"
        target = targets.get(bid, "")
        scan_path = book.scan_folder.path if (book is not None and book.scan_folder) else ""
        folder, filename = _target_parts(target, scan_path)
        cover_uri = _cover_data_uri(cover_path)
        cover_cell = (
            f'<img src="{html.escape(cover_uri, quote=True)}" alt="cover">'
            if cover_uri
            else "ERR"
        )
        mark = "&#10003;" if bid in sample_ids else ""
        row_class = ' class="sampled"' if bid in sample_ids else ""
        cells = (
            f"<td>{cover_cell}</td>"
            f"<td>{html.escape(str(bid))}</td>"
            f"<td>{html.escape(title)}</td>"
            f"<td>{html.escape(last_name)}</td>"
            f"<td>{html.escape(first_name)}</td>"
            f"<td>{html.escape(series)}</td>"
            f"<td>{html.escape(series_number)}</td>"
            f"<td>{html.escape(language)}</td>"
            f"<td>{html.escape(fmt)}</td>"
            f"<td>{html.escape(tier)}</td>"
            f"<td>{html.escape(folder)}</td>"
            f"<td>{html.escape(filename)}</td>"
            f"<td>{html.escape(_path_tail(source))}</td>"
            f"<td>{mark}</td>"
        )
        rows.append(f"<tr{row_class}>{cells}</tr>")

    hold = html.escape(
        "To hold back books use --apply --manifest <manifest path> "
        "--confirm <count> --exclude-ids <ids> --exclude-reason <text>"
    )
    page = (
        '<!doctype html><html><head><meta charset="utf-8">'
        f"<title>Batch review {html.escape(batch_id)}</title>"
        "<style>"
        "table{border-collapse:collapse}th,td{border:1px solid #999;padding:4px;"
        "vertical-align:top}tr.sampled{background:#fff59d}"
        "</style></head><body>"
        f"<h1>Batch {html.escape(batch_id)}</h1>"
        f"<p>criteria version: {html.escape(CRITERIA_VERSION)}</p>"
        f"<p>{hold}</p>"
        "<table><thead><tr><th>cover</th><th>id</th><th>title</th><th>last name</th>"
        "<th>first name</th><th>series</th><th>number</th><th>language</th><th>format</th>"
        "<th>tier</th><th>folder</th><th>file name</th><th>source path</th><th>sample</th>"
        "</tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table></body></html>"
    )
    path = manifest_dir / f"{batch_id}_review.html"
    path.write_text(page)
    return path.name, f"review page: {path}"


def _sample_line(bid, corroborated, ctx, target=None):
    """Full detail line for one sampled entry; the planner runs only here."""
    from books.models import Book

    book = Book.objects.select_related("finalmetadata", "scan_folder").filter(id=bid).first()
    fm = _get_fm(book)
    source, fmt = ctx["primary_file"].get(bid, ("", ""))
    tier = "corroborated" if corroborated else "standard"
    if target is None:
        target = _planned_target(book)
    cover = CoverCache.resolve_path(fm.final_cover_path or "")
    return (
        f"{bid} | {fm.final_title or ''} | {fm.final_author or ''} | "
        f"{fm.language or ''} | {fmt} | {tier} | {source} | {target} | {cover}"
    )


def select_batch(size, seed=None, manifest_dir=None):
    """Select the next batch of eligible books. Writes nothing.

    Returns a dict with the selection data the command and the batch review
    page both need:

    * ``batch_id`` — the new batch's uuid.
    * ``selected`` — the eligible ``(corroborated, book_id)`` pairs, sorted
      corroborated-first then by id, capped at ``size``.
    * ``sample_entries`` / ``sample_ids`` — the deterministic sample.
    * ``targets`` — the planned target per selected id.
    * ``ctx`` — the streaming context (primary files, duplicate counters).
    """
    from books.models import Book

    size = min(size, MAX_SIZE)
    manifest_dir = Path(manifest_dir) if manifest_dir else DEFAULT_MANIFEST_DIR
    manifest_dir.mkdir(parents=True, exist_ok=True)
    rejected = read_holds(manifest_dir)
    ctx = _build_context()

    eligible = []  # minimal tuples: (corroborated, book_id)
    for book in (
        Book.objects.select_related("finalmetadata", "scan_folder").order_by("id").iterator()
    ):
        if book.id in rejected:
            continue
        fm = _get_fm(book)
        if _exclusion(book, fm, ctx):
            continue
        corroborated = _conf(fm.final_title_confidence) >= CORROBORATED_THRESHOLD
        eligible.append((corroborated, book.id))

    eligible.sort(key=lambda e: (-e[0], e[1]))
    selected = eligible[:size]

    batch_id = str(uuid.uuid4())
    if seed is None:
        seed = int.from_bytes(hashlib.md5(batch_id.encode()).digest()[:4], "big")
    rng = random.Random(seed)
    n_sample = min(len(selected), MAX_SAMPLE)
    sample_entries = rng.sample(selected, n_sample) if n_sample else []
    sample_ids = {bid for _corr, bid in sample_entries}

    # Planned targets run for every selected book (up to MAX_SIZE), so the
    # review page can show the target for the whole batch, not just the sample.
    targets = {}
    for _corr, bid in selected:
        book = Book.objects.select_related("finalmetadata", "scan_folder").filter(id=bid).first()
        targets[bid] = _planned_target(book)

    return {
        "batch_id": batch_id,
        "selected": selected,
        "sample_entries": sample_entries,
        "sample_ids": sample_ids,
        "targets": targets,
        "ctx": ctx,
    }


def write_batch_files(selection, manifest_dir):
    """Write the manifest, contact sheets and review page for a selection.

    Returns a dict with ``manifest_path``, the final ``manifest`` dict and
    ``file_lines`` (the ordered "contact sheet" / "review page" lines to
    print), so the command prints exactly what it printed before.
    """
    ctx = selection["ctx"]
    selected = selection["selected"]
    batch_id = selection["batch_id"]
    sample_ids = selection["sample_ids"]
    targets = selection["targets"]

    manifest = {
        "batch_id": batch_id,
        "criteria_version": CRITERIA_VERSION,
        "ids": [bid for _corr, bid in selected],
        "sample_ids": [bid for _corr, bid in selection["sample_entries"]],
        "status": "prepared",
    }
    sheets, sheet_lines = _write_contact_sheets(selected, ctx, manifest_dir, batch_id)
    manifest["sheets"] = sheets
    review_name, review_line = _write_review_page(
        selected, ctx, manifest_dir, batch_id, sample_ids, targets
    )
    manifest["review_page"] = review_name

    manifest_path = Path(manifest_dir) / f"{batch_id}.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))

    file_lines = list(sheet_lines)
    if review_line is not None:
        file_lines.append(review_line)

    return {
        "manifest_path": manifest_path,
        "manifest": manifest,
        "file_lines": file_lines,
    }


def batch_report(manifest_dir=None):
    """Summarise the criteria across the whole library. Writes nothing.

    Returns ``total``, ``eligible``, ``exclusions`` (one count per criterion
    label in CRITERIA_LABELS order), and the eligible ``by_format``,
    ``by_language`` and ``by_tier`` counters.
    """
    from books.models import Book

    manifest_dir = Path(manifest_dir) if manifest_dir else DEFAULT_MANIFEST_DIR
    rejected = read_holds(manifest_dir)
    ctx = _build_context()
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
        reason = _exclusion(book, fm, ctx)
        if reason:
            excluded[reason] += 1
            continue
        eligible_count += 1
        by_format[ctx["primary_file"].get(book.id, ("", ""))[1]] += 1
        by_language[fm.language or ""] += 1
        tier = "corroborated" if _conf(fm.final_title_confidence) >= CORROBORATED_THRESHOLD else "standard"
        by_tier[tier] += 1

    return {
        "total": total,
        "eligible": eligible_count,
        "exclusions": {label: excluded.get(label, 0) for label in CRITERIA_LABELS},
        "by_format": dict(by_format),
        "by_language": dict(by_language),
        "by_tier": dict(by_tier),
    }
