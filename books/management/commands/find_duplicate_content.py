"""Management command: find_duplicate_content (read-only).

Lists groups of books that share a content hash across the FileMove journal's
``original_sha256`` and ``new_sha256`` columns, with counts and book ids. The
grouping is done with a single SQL aggregation over a ``UNION ALL`` of the two
hash columns (empty hashes and rows with no book excluded), read in chunks from
the cursor, so the full hash set is never materialised in Python.
"""

from django.core.management.base import BaseCommand
from django.db import connection
from django.db.models import Q

from books.models import FileMove


class Command(BaseCommand):
    help = "List groups of books sharing a content hash (read-only)."

    def handle(self, *args, **options):
        table = FileMove._meta.db_table
        cursor = connection.cursor()
        cursor.execute(
            f"""
            SELECT h, COUNT(DISTINCT book_id) AS n
            FROM (
                SELECT original_sha256 AS h, book_id FROM {table}
                UNION ALL
                SELECT new_sha256 AS h, book_id FROM {table}
            ) AS hashes
            WHERE h <> '' AND book_id IS NOT NULL
            GROUP BY h
            HAVING COUNT(DISTINCT book_id) > 1
            ORDER BY h
            """
        )

        groups = []
        while True:
            rows = cursor.fetchmany(1000)
            if not rows:
                break
            for h, _n in rows:
                book_ids = sorted(
                    FileMove.objects
                    .filter(Q(original_sha256=h) | Q(new_sha256=h))
                    .exclude(book__isnull=True)
                    .values_list("book_id", flat=True)
                    .distinct()
                )
                groups.append((h, book_ids))

        for h, book_ids in groups:
            self.stdout.write(f"{h} {len(book_ids)} {' '.join(map(str, book_ids))}")
        self.stdout.write(f"{len(groups)} duplicate group(s)")
