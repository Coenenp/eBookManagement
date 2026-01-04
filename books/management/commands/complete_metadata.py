"""
Management command to complete metadata for books that exist in the database
but have incomplete metadata (missing FinalMetadata records).

This is useful for resuming scans that were interrupted during the metadata
collection phase.
"""

import logging

from django.core.management.base import BaseCommand

from books.models import Book, FinalMetadata

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Complete metadata for books that exist but have incomplete metadata"

    def add_arguments(self, parser):
        parser.add_argument(
            "--folder",
            type=str,
            help="Specific folder path to process (optional)",
        )
        parser.add_argument(
            "--scan-folder-id",
            type=int,
            help="Specific ScanFolder ID to process (optional)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Only show which books would be processed, don't actually process them",
        )

    def handle(self, *args, **options):
        self.stdout.write("Finding books with incomplete metadata...")

        # Build query to find incomplete books
        query = Book.objects.exclude(
            # Exclude books that have FinalMetadata (considered complete)
            id__in=FinalMetadata.objects.values_list("book_id", flat=True)
        ).exclude(
            # Exclude corrupted books
            is_corrupted=True
        )

        # Apply folder filters if specified
        if options["folder"]:
            query = query.filter(file_path__startswith=options["folder"])

        if options["scan_folder_id"]:
            query = query.filter(scan_folder_id=options["scan_folder_id"])

        incomplete_books = list(query.order_by("id"))

        if not incomplete_books:
            self.stdout.write(self.style.SUCCESS("No incomplete books found!"))
            return

        self.stdout.write(
            f"Found {len(incomplete_books)} books needing metadata completion"
        )

        if options["dry_run"]:
            self.stdout.write("\nBooks that would be processed:")
            for book in incomplete_books[:10]:  # Show first 10
                self.stdout.write(f"  Book {book.id}: {book.file_path}")
            if len(incomplete_books) > 10:
                self.stdout.write(f"  ... and {len(incomplete_books) - 10} more")
            return

        # Process the books
        self.stdout.write("Starting metadata completion...")

        # Import the required functions
        from books.scanner.folder import (
            query_metadata_and_covers,
            resolve_final_metadata,
        )

        success_count = 0
        error_count = 0

        for i, book in enumerate(incomplete_books, 1):
            try:
                self.stdout.write(
                    f"Processing book {book.id} ({i}/{len(incomplete_books)}): {book.file_path}"
                )

                # Skip the file creation part, book already exists
                # Go straight to metadata collection steps
                query_metadata_and_covers(book)
                resolve_final_metadata(book)

                success_count += 1

                if i % 10 == 0:
                    self.stdout.write(f"  Completed {i}/{len(incomplete_books)} books")

            except Exception as e:
                error_count += 1
                self.stdout.write(
                    self.style.ERROR(f"Error processing book {book.id}: {str(e)}")
                )
                logger.error(f"Error completing metadata for book {book.id}: {e}")

        self.stdout.write(
            self.style.SUCCESS(
                f"Metadata completion finished. "
                f"Success: {success_count}, Errors: {error_count}"
            )
        )
