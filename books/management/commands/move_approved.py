"""Management command: move approved books into their final location.

Usage::

    python manage.py move_approved [--limit N] [--scan-folder P] [--language L]
        [--content-type T] [--folder-pattern P] [--filename-pattern P] [--execute]

Without ``--execute`` it is a dry run: it prints one line per eligible book and
a ``planned N, skipped M`` summary, but writes and moves nothing. With
``--execute`` it moves one book at a time, tags the journal rows with a single
``batch_id``, and prints ``moved / needs_review / failed / skipped`` counts.

The planning and execution live in :mod:`books.services.moves` (``plan_moves``
and ``run_moves``) so the command and the moves page share one implementation.
This command only parses options, calls the service, and prints.
"""

from django.core.management.base import BaseCommand

from books.services.moves import (
    dry_run_report,
    fit_path,
    plan_moves,
    run_moves,
)


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
        plan = plan_moves(
            limit=options["limit"],
            scan_folder=options["scan_folder"],
            language=options["language"],
            content_type=options["content_type"],
            folder_pattern=options["folder_pattern"],
            filename_pattern=options["filename_pattern"],
        )

        if not options["execute"]:
            report = dry_run_report(plan)
            for entry in report["planned"]:
                self.stdout.write(
                    f"{entry['id']} | {entry['language']} | {entry['source']} -> {entry['target']}"
                )
            for skip in report["skipped"]:
                self.stdout.write(f"skipped {skip['id']} | {skip['reason']}")
            self.stdout.write(
                f"planned {len(report['planned'])}, skipped {len(report['skipped'])}"
            )
            return

        result = run_moves(
            plan,
            folder_pattern=options["folder_pattern"],
            filename_pattern=options["filename_pattern"],
        )
        for entry in result["results"]:
            if entry["result"] == "needs_review":
                self.stdout.write(
                    f"needs_review {entry['id']} | {', '.join(entry['codes'])}"
                )
            elif entry["result"] == "failed":
                self.stdout.write(f"failed {entry['id']} | {entry['error']}")
        for skip in plan["skipped"] + result["extra_skipped"]:
            self.stdout.write(f"skipped {skip['id']} | {skip['reason']}")
        self.stdout.write(
            f"moved {result['moved']}, needs_review {result['needs_review']}, "
            f"failed {result['failed']}, skipped {result['skipped']}"
        )
