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

The writing actions (holds, reject and apply) live in
:mod:`books.services.batches` (``read_holds``, ``add_holds``,
``reject_books`` and ``apply_batch``) so the command and the batch review
page share one implementation. This command parses options, calls the
service, and prints.
"""

import hashlib
import json
import random
import re
import uuid
from collections import Counter
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from books.utils.cover_cache import CoverCache

from books.services.batches import (
    CORROBORATED_THRESHOLD,
    CRITERIA_LABELS,
    CRITERIA_VERSION,
    DEFAULT_MANIFEST_DIR,
    MAX_SAMPLE,
    MAX_SIZE,
    SUSPICIOUS_PATTERNS,
    _build_context,
    _conf,
    _exclusion,
    _get_fm,
    _title_is_noisy,
    apply_batch,
    read_holds,
    reject_books,
)

__all__ = [
    "CRITERIA_VERSION",
    "DEFAULT_MANIFEST_DIR",
    "MAX_SAMPLE",
    "SUSPICIOUS_PATTERNS",
    "_title_is_noisy",
    "Command",
]


def _apply_command_text(manifest_path, n_ids):
    """The exact command to apply a prepared batch, with the manifest path and
    id count filled in; only ``--exclude-ids`` is left for the user to type."""
    return (
        "python manage.py approve_batch --apply "
        f"--manifest {manifest_path} --confirm {n_ids} "
        "--exclude-ids <comma separated ids>"
    )


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
    # Contact sheets and review exclusions
    # ------------------------------------------------------------------ #

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
    # Review page
    # ------------------------------------------------------------------ #

    def _path_tail(self, source_path):
        """The last two path components (folder and file name) for display."""
        parts = [p for p in re.split(r"[\\/]+", source_path or "") if p]
        return " / ".join(parts[-2:])

    def _cover_data_uri(self, cover_path):
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

    def _write_review_page(self, selected, ctx, manifest_dir, batch_id, sample_ids, targets):
        """Write a self-contained review HTML page (no scripts, no external assets)."""
        import html

        from books.models import Book
        from books.utils.renaming_engine import RenamingEngine

        ids = sorted(bid for _corr, bid in selected)
        if not ids:
            return None

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
            cover_uri = self._cover_data_uri(cover_path)
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
                f"<td>{html.escape(self._path_tail(source))}</td>"
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
        self.stdout.write(f"review page: {path}")
        return path.name

    # ------------------------------------------------------------------ #
    # Modes
    # ------------------------------------------------------------------ #

    def _prepare(self, options):
        from books.models import Book

        size = min(options["size"], MAX_SIZE)
        manifest_dir = Path(options["manifest_dir"]) if options["manifest_dir"] else DEFAULT_MANIFEST_DIR
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
        seed = options["seed"]
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
            targets[bid] = self._planned_target(book)

        manifest = {
            "batch_id": batch_id,
            "criteria_version": CRITERIA_VERSION,
            "ids": [bid for _corr, bid in selected],
            "sample_ids": [bid for _corr, bid in sample_entries],
            "status": "prepared",
        }
        manifest["sheets"] = self._write_contact_sheets(selected, ctx, manifest_dir, batch_id)
        manifest["review_page"] = self._write_review_page(
            selected, ctx, manifest_dir, batch_id, sample_ids, targets
        )

        manifest_path = manifest_dir / f"{batch_id}.json"
        manifest_path.write_text(json.dumps(manifest, indent=2))

        self.stdout.write(f"batch_id: {batch_id}")
        self.stdout.write(f"manifest: {manifest_path}")
        for corroborated, bid in sample_entries:
            self.stdout.write(self._sample_line(bid, corroborated, ctx, targets.get(bid, "")))
        self.stdout.write(_apply_command_text(manifest_path, len(manifest["ids"])))

    def _sample_line(self, bid, corroborated, ctx, target=None):
        """Full detail line for one sampled entry; the planner runs only here."""
        from books.models import Book

        book = Book.objects.select_related("finalmetadata", "scan_folder").filter(id=bid).first()
        fm = _get_fm(book)
        source, fmt = ctx["primary_file"].get(bid, ("", ""))
        tier = "corroborated" if corroborated else "standard"
        if target is None:
            target = self._planned_target(book)
        cover = CoverCache.resolve_path(fm.final_cover_path or "")
        return (
            f"{bid} | {fm.final_title or ''} | {fm.final_author or ''} | "
            f"{fm.language or ''} | {fmt} | {tier} | {source} | {target} | {cover}"
        )

    def _report(self, options):
        from books.models import Book

        manifest_dir = Path(options["manifest_dir"]) if options["manifest_dir"] else DEFAULT_MANIFEST_DIR
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
        self.stdout.write(_apply_command_text(str(manifest_dir / "<batch_id>.json"), eligible_count))

    def _reject(self, options):
        result = reject_books(
            manifest_path=Path(options["manifest"]),
            reject_id=options["reject_id"],
            reason=options["reason"],
        )
        if result.get("refusal"):
            raise CommandError(result["refusal"])
        self.stdout.write(result["line"])

    def _apply(self, options):
        result = apply_batch(
            manifest_path=options["manifest"],
            confirm=options["confirm"],
            exclude_ids=options.get("exclude_ids"),
            exclude_reason=options.get("exclude_reason") or "review",
            allow_high_exclusion=options.get("allow_high_exclusion", False),
        )
        if result.get("refusal"):
            raise CommandError(result["refusal"])
        for entry in result["skipped"]:
            self.stdout.write(f"skipped {entry['id']}: {entry['reason']}")
        self.stdout.write(f"approved {result['approved_count']}, skipped {result['skipped_count']}")
