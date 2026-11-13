"""Management command: find_duplicate_content (read-only).

Lists groups of books that share a content hash across the FileMove journal's
``original_sha256`` and ``new_sha256`` columns, with counts and book ids. Rows
are streamed with ``.iterator()`` so the full hash set is never materialised as
a queryset.
"""

from collections import defaultdict

from django.core.management.base import BaseCommand

from books.models import FileMove


class Command(BaseCommand):
    help = "List groups of books sharing a content hash (read-only)."

    def handle(self, *args, **options):
        hash_to_books = defaultdict(set)
        for row in FileMove.objects.exclude(book__isnull=True).iterator():
            book_id = row.book_id
            for h in (row.original_sha256, row.new_sha256):
                if h:
                    hash_to_books[h].add(book_id)

        groups = [
            (h, sorted(book_ids))
            for h, book_ids in hash_to_books.items()
            if len(book_ids) > 1
        ]
        groups.sort(key=lambda g: g[0])

        for h, book_ids in groups:
            self.stdout.write(f"{h} {len(book_ids)} {' '.join(map(str, book_ids))}")
        self.stdout.write(f"{len(groups)} duplicate group(s)")
