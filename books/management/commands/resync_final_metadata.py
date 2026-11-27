"""Recompute final title/author/series for unreviewed books without re-scanning.

The writing action lives in :func:`books.services.authors.resync_final_metadata`
so the command and the metadata resync screen (UI) share one implementation.
This command only parses options, calls the service, prints and writes the CSV.
"""

import csv

from django.core.management.base import BaseCommand

from books.services.authors import resync_final_metadata


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

        result = resync_final_metadata(execute=execute, limit=limit)

        csv_file = None
        csv_writer = None
        if csv_path:
            csv_file = open(csv_path, "w", newline="", encoding="utf-8")
            csv_writer = csv.writer(csv_file)
            csv_writer.writerow(["book_id", "field", "old", "new"])

        csv_written = 0
        try:
            for row in result["changes"]:
                if csv_writer is not None:
                    csv_writer.writerow(list(row))
                csv_written += 1
        finally:
            if csv_file is not None:
                csv_file.close()

        self.stdout.write(f"Checked {result['checked']} books")
        self.stdout.write(f"Changed titles: {result['changed_titles']}")
        self.stdout.write(f"Changed authors: {result['changed_authors']}")
        self.stdout.write(f"Changed series: {result['changed_series']}")
        if csv_path:
            self.stdout.write(f"Wrote {csv_written} changed fields to {csv_path}")
