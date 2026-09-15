"""
Management command to clean and deduplicate author data.

This command:
1. Identifies and removes invalid author names (years, dates)
2. Merges duplicate authors with different casing/formatting
3. Updates author names by cleaning birth/death dates
4. Finds fuzzy duplicate candidates (report only; review in the web UI)

The core cleanup logic lives in ``books.services.author_cleanup`` so that the
same operations are also available to end users via Settings -> Library
Maintenance in the web UI.
"""

import logging

from django.core.management.base import BaseCommand

from books.models import Author, BookAuthor
from books.services.author_cleanup import run_author_cleanup
from books.utils.author_matching import find_potential_duplicates, suggest_canonical_name

logger = logging.getLogger("books.scanner")


class Command(BaseCommand):
    help = "Clean author names and merge duplicates"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be done without making changes",
        )
        parser.add_argument(
            "--remove-invalid",
            action="store_true",
            help="Remove authors with invalid names (years, etc.)",
        )
        parser.add_argument(
            "--merge-duplicates",
            action="store_true",
            help="Merge duplicate authors with different casing",
        )
        parser.add_argument(
            "--find-fuzzy-duplicates",
            action="store_true",
            help="Find potential duplicates using fuzzy matching",
        )
        parser.add_argument(
            "--fuzzy-threshold",
            type=float,
            default=0.85,
            help="Similarity threshold for fuzzy matching (0.0-1.0, default: 0.85)",
        )
        parser.add_argument(
            "--clean-names",
            action="store_true",
            help="Clean existing author names (remove dates, etc.)",
        )
        parser.add_argument(
            "--all",
            action="store_true",
            help="Run all cleaning operations",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        if options["all"]:
            options["remove_invalid"] = True
            options["merge_duplicates"] = True
            options["clean_names"] = True

        remove_invalid = options["remove_invalid"]
        clean_names = options["clean_names"]
        merge_duplicates = options["merge_duplicates"]
        find_fuzzy = options["find_fuzzy_duplicates"]

        self.stdout.write(self.style.SUCCESS("\n" + "=" * 70))
        self.stdout.write(self.style.SUCCESS("AUTHOR CLEANING AND DEDUPLICATION"))
        self.stdout.write(self.style.SUCCESS("=" * 70))

        if dry_run:
            self.stdout.write(self.style.WARNING("\n  DRY RUN MODE - No changes will be made\n"))

        ran_cleanup = any([remove_invalid, clean_names, merge_duplicates])
        if ran_cleanup:
            stats = run_author_cleanup(
                remove_invalid=remove_invalid,
                clean_names=clean_names,
                merge_duplicates=merge_duplicates,
                dry_run=dry_run,
            )
            self._print_cleanup_stats(stats, remove_invalid, clean_names, merge_duplicates)

        if find_fuzzy:
            self._find_fuzzy_duplicates(dry_run, options["fuzzy_threshold"])

        if not ran_cleanup and not find_fuzzy:
            self.stdout.write(self.style.WARNING("\nNo operations selected. Use --help to see options.\n"))

    def _print_cleanup_stats(self, stats, remove_invalid, clean_names, merge_duplicates):
        if remove_invalid:
            self.stdout.write("\n" + "-" * 70)
            self.stdout.write(self.style.NOTICE("STEP 1: Removing invalid author names"))
            self.stdout.write("-" * 70)
            for entry in stats["invalid_authors"]:
                self.stdout.write(self.style.WARNING(f"   INVALID: '{entry['name']}' (used in {entry['book_count']} books)"))
            if stats["invalid_removed"] == 0:
                self.stdout.write(self.style.SUCCESS("   No invalid authors found"))

        if clean_names:
            self.stdout.write("\n" + "-" * 70)
            self.stdout.write(self.style.NOTICE("STEP 2: Cleaning author names"))
            self.stdout.write("-" * 70)
            for entry in stats["cleaned_names"]:
                self.stdout.write(self.style.NOTICE(f"   CLEAN: '{entry['before']}' -> '{entry['after']}'"))
            if stats["names_cleaned"] == 0:
                self.stdout.write(self.style.SUCCESS("   No author names need cleaning"))

        if merge_duplicates:
            self.stdout.write("\n" + "-" * 70)
            self.stdout.write(self.style.NOTICE("STEP 3: Merging duplicate authors (exact match)"))
            self.stdout.write("-" * 70)
            for group in stats["merged_groups"]:
                self.stdout.write(self.style.SUCCESS(f"      KEEP: '{group['primary']['name']}' (ID: {group['primary']['id']})"))
                for dup in group["duplicates"]:
                    self.stdout.write(self.style.WARNING(f"      MERGE: '{dup['name']}' (ID: {dup['id']}, {dup['book_count']} books)"))
            if stats["duplicates_merged"] == 0:
                self.stdout.write(self.style.SUCCESS("   No duplicate authors found"))

        self.stdout.write("\n" + "=" * 70)
        self.stdout.write(self.style.SUCCESS("SUMMARY"))
        self.stdout.write("=" * 70)
        self.stdout.write(f"  Invalid authors removed: {stats['invalid_removed']}")
        self.stdout.write(f"  Author names cleaned: {stats['names_cleaned']}")
        self.stdout.write(f"  Duplicate authors merged: {stats['duplicates_merged']}")
        self.stdout.write("=" * 70 + "\n")

    def _find_fuzzy_duplicates(self, dry_run, threshold):
        """Find potential duplicate authors using fuzzy matching."""

        authors = [(a.id, a.name) for a in Author.objects.all()]

        self.stdout.write("\n" + "-" * 70)
        self.stdout.write(self.style.NOTICE("STEP 4: Finding potential duplicates (fuzzy matching)"))
        self.stdout.write("-" * 70)

        if len(authors) < 2:
            self.stdout.write(self.style.WARNING("    Not enough authors to compare"))
            return 0

        self.stdout.write(f"   Analyzing {len(authors)} authors with threshold {threshold}...")

        duplicate_groups = find_potential_duplicates(authors, threshold)

        if not duplicate_groups:
            self.stdout.write(self.style.SUCCESS("   No fuzzy duplicates found"))
            return 0

        for i, group in enumerate(duplicate_groups, 1):
            similarity = group["similarity"]
            author_list = group["authors"]

            self.stdout.write(self.style.NOTICE(f"\n   POTENTIAL DUPLICATE GROUP #{i} (similarity: {similarity:.2%}):"))

            names = [name for _, name in author_list]
            canonical = suggest_canonical_name(names)

            self.stdout.write(self.style.SUCCESS(f"      SUGGESTED CANONICAL: '{canonical}'"))

            for author_id, author_name in author_list:
                book_count = BookAuthor.objects.filter(author_id=author_id).count()
                marker = "KEEP" if author_name == canonical else "MERGE"
                self.stdout.write(f"     {marker} '{author_name}' (ID: {author_id}, {book_count} books)")

        self.stdout.write(self.style.NOTICE("\n   TIP: Review these potential duplicates in the web UI under Authors -> Duplicates."))

        return len(duplicate_groups)
