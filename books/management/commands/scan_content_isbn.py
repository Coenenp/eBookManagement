"""Management command to scan ebook content for ISBN numbers.

This command scans the actual content of ebooks (first and last pages)
to find ISBN numbers that might not be in the metadata.
"""

import logging

from django.core.management.base import BaseCommand, CommandError

from books.models import Book, BookMetadata
from books.scanner.extractors.content_isbn import (
    bulk_scan_content_isbns,
    save_content_isbns,
)

logger = logging.getLogger("books.scanner")


class Command(BaseCommand):
    help = "Scan ebook content for ISBN numbers"

    def add_arguments(self, parser):
        parser.add_argument("--book-id", type=int, help="Scan specific book by ID")
        parser.add_argument(
            "--filename",
            type=str,
            help="Scan specific book by filename (partial match)",
        )
        parser.add_argument(
            "--pages",
            type=int,
            default=10,
            help="Number of pages to scan from beginning and end (default: 10)",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Re-scan books that already have content-scanned ISBNs",
        )
        parser.add_argument(
            "--missing-isbn-only",
            action="store_true",
            help="Only scan books that have no ISBN metadata at all",
        )
        parser.add_argument("--limit", type=int, help="Limit number of books to process")
        parser.add_argument(
            "--file-type",
            choices=["epub", "pdf", "mobi"],
            help="Only scan specific file types",
        )

    def handle(self, *args, **options):
        # Set up logging
        logging.basicConfig(level=logging.INFO)

        # Build queryset based on options
        queryset = Book.objects.all()

        if options["book_id"]:
            queryset = queryset.filter(id=options["book_id"])

        if options["filename"]:
            queryset = queryset.filter(filename__icontains=options["filename"])

        if options["file_type"]:
            ext = f".{options['file_type']}"
            queryset = queryset.filter(filename__iendswith=ext)

        if options["missing_isbn_only"]:
            # Only books with no ISBN metadata at all
            books_with_isbn = BookMetadata.objects.filter(field_name="isbn").values_list("book_id", flat=True)
            queryset = queryset.exclude(id__in=books_with_isbn)

        if not options["force"]:
            # Exclude books that already have content-scanned ISBNs
            books_with_content_isbn = BookMetadata.objects.filter(field_name="isbn", source__name="content_scan").values_list("book_id", flat=True)
            queryset = queryset.exclude(id__in=books_with_content_isbn)

        if options["limit"]:
            queryset = queryset[: options["limit"]]

        # Count total books to process
        try:
            total_books = queryset.count()
        except (TypeError, AttributeError):
            # Handle mocked querysets in tests
            total_books = len(list(queryset))

        if total_books == 0:
            self.stdout.write(self.style.WARNING("No books match the specified criteria."))
            return

        self.stdout.write(f"Scanning {total_books} books for content ISBNs...")

        # Process single book or bulk scan
        if options["book_id"]:
            try:
                book = queryset.get()
                self.stdout.write(f"Scanning book: {book.filename}")
                save_content_isbns(book)

                # Check results
                content_isbns = BookMetadata.objects.filter(book=book, field_name="isbn", source__name="content_scan").count()

                if content_isbns > 0:
                    self.stdout.write(self.style.SUCCESS(f"Found {content_isbns} ISBN(s) in content"))
                else:
                    self.stdout.write(self.style.WARNING("No ISBNs found in content"))

            except Book.DoesNotExist:
                raise CommandError(f'Book with ID {options["book_id"]} does not exist')

        else:
            # Bulk scan
            stats = bulk_scan_content_isbns(books_queryset=queryset, page_limit=options["pages"])

            # Report results
            self.stdout.write(
                self.style.SUCCESS(
                    f"Content ISBN scan completed!\n"
                    f"Books processed: {stats['total_books']}\n"
                    f"Books with ISBNs found: {stats['books_with_isbns']}\n"
                    f"Total ISBNs found: {stats['total_isbns_found']}\n"
                    f"Errors: {stats['errors']}"
                )
            )

            if stats["errors"] > 0:
                self.stdout.write(self.style.WARNING(f"There were {stats['errors']} errors. Check the logs for details."))
