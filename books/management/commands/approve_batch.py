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

The whole pipeline lives in :mod:`books.services.batches` (``select_batch``,
``batch_report``, ``write_batch_files``, ``read_holds``, ``add_holds``,
``reject_books`` and ``apply_batch``) so the command and the batch review
page share one implementation. This command only parses options, calls the
service, and prints.
"""

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from books.services.batches import (
    CRITERIA_LABELS,
    CRITERIA_VERSION,
    DEFAULT_MANIFEST_DIR,
    MAX_SAMPLE,
    MAX_SIZE,
    SUSPICIOUS_PATTERNS,
    _apply_command_text,
    _planned_target,
    _sample_line,
    _title_is_noisy,
    apply_batch,
    batch_report,
    reject_books,
    select_batch,
    write_batch_files,
)

__all__ = [
    "CRITERIA_VERSION",
    "DEFAULT_MANIFEST_DIR",
    "MAX_SAMPLE",
    "SUSPICIOUS_PATTERNS",
    "_title_is_noisy",
    "Command",
]


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

    def _manifest_dir(self, options):
        return Path(options["manifest_dir"]) if options["manifest_dir"] else DEFAULT_MANIFEST_DIR

    def _planned_target(self, book):
        return _planned_target(book)

    def _prepare(self, options):
        manifest_dir = self._manifest_dir(options)
        selection = select_batch(
            size=min(options["size"], MAX_SIZE),
            seed=options["seed"],
            manifest_dir=manifest_dir,
        )
        result = write_batch_files(selection, manifest_dir)
        for line in result["file_lines"]:
            self.stdout.write(line)
        self.stdout.write(f"batch_id: {selection['batch_id']}")
        self.stdout.write(f"manifest: {result['manifest_path']}")
        for corroborated, bid in selection["sample_entries"]:
            self.stdout.write(
                _sample_line(
                    bid, corroborated, selection["ctx"], selection["targets"].get(bid, "")
                )
            )
        self.stdout.write(_apply_command_text(result["manifest_path"], len(result["manifest"]["ids"])))

    def _report(self, options):
        manifest_dir = self._manifest_dir(options)
        report = batch_report(manifest_dir=manifest_dir)
        self.stdout.write(f"total books: {report['total']}")
        self.stdout.write(f"eligible: {report['eligible']}")
        self.stdout.write("exclusions:")
        for label in CRITERIA_LABELS:
            self.stdout.write(f"  {label}: {report['exclusions'].get(label, 0)}")
        self.stdout.write("eligible by format:")
        for fmt, n in sorted(report["by_format"].items()):
            self.stdout.write(f"  {fmt}: {n}")
        self.stdout.write("eligible by language:")
        for lang, n in sorted(report["by_language"].items()):
            self.stdout.write(f"  {lang}: {n}")
        self.stdout.write("eligible by confidence tier:")
        for tier, n in sorted(report["by_tier"].items()):
            self.stdout.write(f"  {tier}: {n}")
        self.stdout.write(_apply_command_text(str(manifest_dir / "<batch_id>.json"), report["eligible"]))

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
