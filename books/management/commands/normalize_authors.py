"""
Management command to normalize every author name in the library.

This command is the shell counterpart of the "normalize all author names"
action available in the web UI (Settings -> Library Maintenance). It runs
``run_author_cleanup(clean_names=True)`` and prints a before/after report for
each changed author.
"""

import logging

from django.core.management.base import BaseCommand

from books.services.author_cleanup import normalize_all_author_names

logger = logging.getLogger("books.scanner")


class Command(BaseCommand):
    help = "Normalize every author name in one operation"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be changed without saving",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        self.stdout.write(self.style.SUCCESS("=" * 70))
        self.stdout.write(self.style.SUCCESS("NORMALIZE AUTHOR NAMES"))
        self.stdout.write(self.style.SUCCESS("=" * 70))

        if dry_run:
            self.stdout.write(self.style.WARNING("\nDRY RUN MODE - No changes will be made\n"))

        stats = normalize_all_author_names(dry_run=dry_run)

        if stats["names_cleaned"] == 0:
            self.stdout.write(self.style.SUCCESS("No author names need normalization."))
        else:
            for entry in stats["cleaned_names"]:
                self.stdout.write(self.style.NOTICE(f"CLEAN: '{entry['before']}' -> '{entry['after']}'"))

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("SUMMARY"))
        self.stdout.write(f"Author names normalized: {stats['names_cleaned']}")
        self.stdout.write("=" * 70)
