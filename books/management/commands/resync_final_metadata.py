"""Recompute final title/author/series for unreviewed books without re-scanning.

Iterates the FinalMetadata rows that are not reviewed and re-runs the three
final-value update functions, then reports (and optionally persists) which of
the seven final title/author/series fields changed. Approved books
(is_reviewed=True) are never touched, and only those seven fields are ever
written, so covers, publishers, language and the confidence/completeness/
accuracy scores are left exactly as they are.
"""

import csv

from django.core.management.base import BaseCommand

from books.models import FinalMetadata

FIELDS = [
    "final_title",
    "final_title_confidence",
    "final_author",
    "final_author_confidence",
    "final_series",
    "final_series_number",
    "final_series_confidence",
]


def _same(old, new):
    if old is None:
        old = ""
    if new is None:
        new = ""
    return old == new


class Command(BaseCommand):
    help = "Recompute final title/author/series for unreviewed books (no re-scan)."

    def add_arguments(self, parser):
        parser.add_argument("--execute", action="store_true", help="Persist changes.")
        parser.add_argument("--limit", type=int, help="Stop after this many books.")
        parser.add_argument("--csv", help="Write one row per changed field to this path.")

    def handle(self, *args, **options):
        execute = options["execute"]
        limit = options["limit"]
        csv_path = options["csv"]

        qs = FinalMetadata.objects.filter(is_reviewed=False).select_related("book").order_by("id")
        if limit is not None:
            qs = qs[:limit]

        changed_titles = 0
        changed_authors = 0
        changed_series = 0
        checked = 0
        csv_written = 0

        csv_file = None
        csv_writer = None
        if csv_path:
            csv_file = open(csv_path, "w", newline="", encoding="utf-8")
            csv_writer = csv.writer(csv_file)
            csv_writer.writerow(["book_id", "field", "old", "new"])

        try:
            for fm in qs.iterator():
                checked += 1
                old = {f: getattr(fm, f) for f in FIELDS}

                fm.update_final_title()
                fm.update_final_author()
                fm.update_final_series()

                changed = [f for f in FIELDS if not _same(old[f], getattr(fm, f))]
                if not changed:
                    continue

                if not _same(old["final_title"], fm.final_title) or not _same(
                    old["final_title_confidence"], fm.final_title_confidence
                ):
                    changed_titles += 1
                if not _same(old["final_author"], fm.final_author) or not _same(
                    old["final_author_confidence"], fm.final_author_confidence
                ):
                    changed_authors += 1
                if (
                    not _same(old["final_series"], fm.final_series)
                    or not _same(old["final_series_number"], fm.final_series_number)
                    or not _same(old["final_series_confidence"], fm.final_series_confidence)
                ):
                    changed_series += 1

                for f in changed:
                    if csv_writer is not None:
                        csv_writer.writerow([fm.book_id, f, old[f], getattr(fm, f)])
                    csv_written += 1

                if execute:
                    fm.save(update_fields=FIELDS)
        finally:
            if csv_file is not None:
                csv_file.close()

        self.stdout.write(f"Checked {checked} books")
        self.stdout.write(f"Changed titles: {changed_titles}")
        self.stdout.write(f"Changed authors: {changed_authors}")
        self.stdout.write(f"Changed series: {changed_series}")
        if csv_path:
            self.stdout.write(f"Wrote {csv_written} changed fields to {csv_path}")
