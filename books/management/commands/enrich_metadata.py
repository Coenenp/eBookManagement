"""Management command to re-enrich existing books.

This command re-runs the local content ISBN scan, then (optionally) queries
external APIs with the discovered ISBN, and finally re-resolves final metadata.
It is the primary tool for repairing data from an earlier low-quality
filename-only scan.

Examples:
    python manage.py enrich_metadata --missing-isbn-only
    python manage.py enrich_metadata --all --purge-low-trust
    python manage.py enrich_metadata --folder "/path/to/books" --dry-run
    python manage.py enrich_metadata --book-ids 1 2 3 --no-external
"""

import logging

from django.core.management.base import BaseCommand
from django.db.models import Q

from books.models import Book, BookMetadata, DataSource
from books.scanner.external import query_metadata_and_covers
from books.scanner.extractors.content_isbn import ensure_content_isbn
from books.scanner.resolver import resolve_final_metadata

logger = logging.getLogger("books.scanner")


class Command(BaseCommand):
    help = "Re-enrich existing books: content ISBN scan, ISBN-driven external metadata, and final resolution"

    def add_arguments(self, parser):
        parser.add_argument("--book-ids", nargs="+", type=int, help="Process specific book IDs")
        parser.add_argument("--folder", type=str, help="Process books in a specific scan folder path")
        parser.add_argument(
            "--missing-isbn-only",
            action="store_true",
            help="Only books that currently have no ISBN metadata",
        )
        parser.add_argument(
            "--low-confidence-only",
            action="store_true",
            help="Only books with low overall confidence or no FinalMetadata",
        )
        parser.add_argument(
            "--no-external",
            action="store_true",
            help="Skip external API queries (local ISBN scan only)",
        )
        parser.add_argument(
            "--purge-low-trust",
            action="store_true",
            help="Deactivate low-trust Initial Scan (filename) metadata after enrichment",
        )
        parser.add_argument("--limit", type=int, help="Limit the number of books to process")
        parser.add_argument("--dry-run", action="store_true", help="Only list matching books without processing")

    def handle(self, *args, **options):
        queryset = Book.objects.filter(deleted_at__isnull=True, is_corrupted=False)

        if options["book_ids"]:
            queryset = queryset.filter(id__in=options["book_ids"])

        if options["folder"]:
            queryset = queryset.filter(scan_folder__path__startswith=options["folder"])

        if options["missing_isbn_only"]:
            books_with_isbn = BookMetadata.objects.filter(field_name="isbn", is_active=True).values_list("book_id", flat=True)
            queryset = queryset.exclude(id__in=books_with_isbn)

        if options["low_confidence_only"]:
            queryset = queryset.filter(Q(finalmetadata__isnull=True) | Q(finalmetadata__overall_confidence__lt=0.6))

        if options["limit"]:
            queryset = queryset[: options["limit"]]

        books = list(queryset.order_by("id"))
        total = len(books)
        self.stdout.write(f"Found {total} books to enrich")

        if options["dry_run"]:
            for book in books[:50]:
                self.stdout.write(f"Book {book.id}: {book.file_path}")
            if total > 50:
                self.stdout.write(f"  ... and {total - 50} more")
            return

        success = 0
        errors = 0
        for i, book in enumerate(books, 1):
            try:
                self.stdout.write(f"[{i}/{total}] Book {book.id}: {book.file_path}")

                # 1. Local content ISBN scan (only runs if the book has no ISBN yet)
                ensure_content_isbn(book)

                # 2. External enrichment (ISBN-driven when an ISBN is available)
                if not options["no_external"]:
                    query_metadata_and_covers(book)

                # 3. Re-resolve final metadata from all sources
                resolve_final_metadata(book)

                # 4. Optional cleanup of low-trust filename metadata
                if options["purge_low_trust"]:
                    purged = self._purge_low_trust_metadata(book)
                    if purged:
                        self.stdout.write(f"Deactivated {purged} low-trust Initial Scan rows")

                success += 1
            except Exception as e:
                errors += 1
                logger.error(f"Enrichment failed for book {book.id}: {e}")

        self.stdout.write(self.style.SUCCESS(f"Enrichment complete: {success} succeeded, {errors} failed"))

    def _purge_low_trust_metadata(self, book):
        """Deactivate low-trust 'Initial Scan' (filename) rows when a better source exists."""
        initial_scan = DataSource.INITIAL_SCAN
        changed = 0

        for relation_name in ("titles", "author_relationships", "series_relationships", "metadata"):
            manager = getattr(book, relation_name)
            active_rows = list(manager.filter(is_active=True))
            if not active_rows:
                continue

            # Only purge filename junk if a higher-trust source is already present.
            best = max(active_rows, key=lambda r: r.confidence or 0.0)
            if best.source.name == initial_scan:
                continue

            purge_ids = [row.id for row in active_rows if row.source.name == initial_scan and (row.confidence or 0.0) < 0.3]
            if purge_ids:
                changed += manager.filter(id__in=purge_ids).update(is_active=False)

        return changed
