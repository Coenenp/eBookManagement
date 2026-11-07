"""Management command: recover interrupted file moves.

Usage::

    python manage.py recover_file_moves [--apply]

Without ``--apply`` it reports what each recoverable :class:`FileMove` row
would do. With ``--apply`` it resolves each row via ``resolve_move``.
"""

from collections import Counter

from django.core.management.base import BaseCommand

from books.models import FileMove
from books.utils.safe_move.recovery import resolve_move


class Command(BaseCommand):
    help = "Recover interrupted file moves (dry run by default)."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Actually resolve rows (default: dry run).")

    def handle(self, *args, **options):
        apply = options["apply"]
        recoverable = (
            FileMove.State.PLANNED,
            FileMove.State.TMP_WRITTEN,
            FileMove.State.TMP_VERIFIED,
            FileMove.State.ARCHIVED,
            FileMove.State.COMMITTED,
            FileMove.State.DB_UPDATED,
        )
        rows = list(FileMove.objects.filter(state__in=recoverable).order_by("pk"))

        state_counts = Counter(r.state for r in rows)
        action_counts = Counter()

        self.stdout.write(f"{len(rows)} recoverable move(s)" + ("" if apply else " (dry run)"))
        for r in rows:
            action = resolve_move(r, apply=apply)
            action_counts[action] += 1
            self.stdout.write(f"  {r.pk} {r.state} -> {action}")

        self.stdout.write("By state:")
        for st, n in sorted(state_counts.items()):
            self.stdout.write(f"  {st}: {n}")
        self.stdout.write("By action:")
        for act, n in sorted(action_counts.items()):
            self.stdout.write(f"  {act}: {n}")
