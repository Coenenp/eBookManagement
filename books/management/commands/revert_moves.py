"""Management command: revert completed moves back to their originals.

Usage::

    python manage.py revert_moves [--batch-id B] [--book-id N ...] [--execute]

Without ``--execute`` it is a dry run: it lists exactly what an execute would
restore and delete, but changes nothing. ``--book-id`` is repeatable. The revert
logic lives in :func:`books.services.moves.revert_moves`; this command only
parses options, calls the service, and prints the result.
"""

from django.core.management.base import BaseCommand

from books.services.moves import revert_moves


class Command(BaseCommand):
    help = "Revert completed moves to their archived originals (dry run by default)."

    def add_arguments(self, parser):
        parser.add_argument("--batch-id", default=None)
        parser.add_argument("--book-id", action="append", type=int, default=None)
        parser.add_argument("--execute", action="store_true")

    def handle(self, *args, **options):
        result = revert_moves(
            batch_id=options["batch_id"],
            book_ids=options["book_id"],
            execute=options["execute"],
        )

        for row in result["plan"]:
            self.stdout.write(
                f"restore book {row['book_id']} | {row['source_path']} <- {row['archived_path']}"
            )
            self.stdout.write(f"delete {row['target_path']}")
        for refusal in result["refusals"]:
            self.stdout.write(f"refusal {refusal['id']} | {refusal['reason']}")
        for failed in result["failed"]:
            self.stdout.write(f"failed {failed['id']} | {failed['reason']}")

        counts = result["counts"]
        if counts["nothing_to_do"]:
            self.stdout.write("nothing to do")
        elif result["dry_run"]:
            self.stdout.write(
                f"dry run, planned {counts['planned']}, refusals {counts['refused']}"
            )
        else:
            self.stdout.write(
                f"restored {counts['restored']}, planned {counts['planned']}, "
                f"refusals {counts['refused']}"
            )
