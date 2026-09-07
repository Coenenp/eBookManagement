"""
Management command to clean and deduplicate author data.

This command:
1. Identifies and removes invalid author names (years, dates)
2. Merges duplicate authors with different casing/formatting
3. Updates author names by cleaning birth/death dates
"""

import logging
from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db import transaction

from books.models import Author, BookAuthor
from books.utils.author_matching import find_potential_duplicates, suggest_canonical_name
from books.utils.authors import clean_author_name, normalize_author_name

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
        do_all = options["all"]

        if do_all:
            options["remove_invalid"] = True
            options["merge_duplicates"] = True
            options["clean_names"] = True

        self.stdout.write(self.style.SUCCESS("\n" + "=" * 70))
        self.stdout.write(self.style.SUCCESS("AUTHOR CLEANING AND DEDUPLICATION"))
        self.stdout.write(self.style.SUCCESS("=" * 70))

        if dry_run:
            self.stdout.write(self.style.WARNING("\n⚠️  DRY RUN MODE - No changes will be made\n"))

        stats = {
            "invalid_removed": 0,
            "duplicates_merged": 0,
            "names_cleaned": 0,
            "fuzzy_duplicates_found": 0,
        }

        # Step 1: Remove invalid authors
        if options["remove_invalid"]:
            self.stdout.write("\n" + "-" * 70)
            self.stdout.write(self.style.NOTICE("STEP 1: Removing invalid author names"))
            self.stdout.write("-" * 70)
            stats["invalid_removed"] = self._remove_invalid_authors(dry_run)

        # Step 2: Clean author names
        if options["clean_names"]:
            self.stdout.write("\n" + "-" * 70)
            self.stdout.write(self.style.NOTICE("STEP 2: Cleaning author names"))
            self.stdout.write("-" * 70)
            stats["names_cleaned"] = self._clean_author_names(dry_run)

        # Step 3: Merge duplicates (exact)
        if options["merge_duplicates"]:
            self.stdout.write("\n" + "-" * 70)
            self.stdout.write(self.style.NOTICE("STEP 3: Merging duplicate authors (exact match)"))
            self.stdout.write("-" * 70)
            stats["duplicates_merged"] = self._merge_duplicate_authors(dry_run)

        # Step 4: Find fuzzy duplicates
        if options["find_fuzzy_duplicates"]:
            self.stdout.write("\n" + "-" * 70)
            self.stdout.write(self.style.NOTICE("STEP 4: Finding potential duplicates (fuzzy matching)"))
            self.stdout.write("-" * 70)
            threshold = options["fuzzy_threshold"]
            stats["fuzzy_duplicates_found"] = self._find_fuzzy_duplicates(dry_run, threshold)

        # Summary
        self.stdout.write("\n" + "=" * 70)
        self.stdout.write(self.style.SUCCESS("SUMMARY"))
        self.stdout.write("=" * 70)
        self.stdout.write(f"  Invalid authors removed: {stats['invalid_removed']}")
        self.stdout.write(f"  Author names cleaned: {stats['names_cleaned']}")
        self.stdout.write(f"  Duplicate authors merged: {stats['duplicates_merged']}")
        if options["find_fuzzy_duplicates"]:
            self.stdout.write(f"  Fuzzy duplicate groups found: {stats['fuzzy_duplicates_found']}")
        self.stdout.write("=" * 70 + "\n")

        if not any([options["remove_invalid"], options["clean_names"], options["merge_duplicates"], options["find_fuzzy_duplicates"]]):
            self.stdout.write(self.style.WARNING("\nNo operations selected. Use --help to see options.\n"))

    def _remove_invalid_authors(self, dry_run):
        """Remove authors with invalid names (years, empty names, etc.)"""
        invalid_count = 0

        for author in Author.objects.all():
            cleaned = clean_author_name(author.name)

            # If cleaning results in empty or very short name, it's invalid
            if not cleaned or len(cleaned) < 2:
                book_count = BookAuthor.objects.filter(author=author).count()
                self.stdout.write(self.style.WARNING(f"  ✗ INVALID: '{author.name}' (used in {book_count} books)"))

                if not dry_run:
                    # Remove all book associations
                    BookAuthor.objects.filter(author=author).delete()
                    # Delete the author
                    author.delete()

                invalid_count += 1

        if invalid_count == 0:
            self.stdout.write(self.style.SUCCESS("  ✓ No invalid authors found"))

        return invalid_count

    def _clean_author_names(self, dry_run):
        """Clean existing author names by removing dates, etc."""
        cleaned_count = 0

        for author in Author.objects.all():
            original_name = author.name
            cleaned_name = clean_author_name(original_name)

            # Skip if no change or if invalid
            if not cleaned_name or cleaned_name == original_name:
                continue

            self.stdout.write(self.style.NOTICE(f"  🧹 CLEAN: '{original_name}' -> '{cleaned_name}'"))

            if not dry_run:
                author.name = cleaned_name
                # Recalculate normalized name
                author.name_normalized = normalize_author_name(cleaned_name)
                author.save()

            cleaned_count += 1

        if cleaned_count == 0:
            self.stdout.write(self.style.SUCCESS("  ✓ No author names need cleaning"))

        return cleaned_count

    def _merge_duplicate_authors(self, dry_run):
        """Merge authors that are duplicates due to different casing/formatting"""
        merged_count = 0

        # Group authors by normalized name
        normalized_groups = defaultdict(list)
        for author in Author.objects.all():
            normalized_groups[author.name_normalized].append(author)

        # Find groups with duplicates
        for norm_name, authors in normalized_groups.items():
            if len(authors) <= 1:
                continue

            # Sort by ID to keep the oldest author
            authors = sorted(authors, key=lambda a: a.id)
            primary_author = authors[0]
            duplicates = authors[1:]

            # Display info
            self.stdout.write(self.style.NOTICE(f"\n  🔗 MERGE GROUP (normalized: '{norm_name}'):"))
            self.stdout.write(self.style.SUCCESS(f"     ✓ KEEP: '{primary_author.name}' (ID: {primary_author.id})"))

            for dup in duplicates:
                book_count = BookAuthor.objects.filter(author=dup).count()
                self.stdout.write(self.style.WARNING(f"     ✗ MERGE: '{dup.name}' (ID: {dup.id}, {book_count} books)"))

            if not dry_run:
                # Merge using transaction
                with transaction.atomic():
                    for dup in duplicates:
                        # Update all BookAuthor entries to point to primary author
                        BookAuthor.objects.filter(author=dup).update(author=primary_author)
                        # Delete the duplicate
                        dup.delete()
                        merged_count += 1

        if merged_count == 0:
            self.stdout.write(self.style.SUCCESS("  ✓ No duplicate authors found"))

        return merged_count

    def _find_fuzzy_duplicates(self, dry_run, threshold):
        """Find potential duplicate authors using fuzzy matching"""

        # Get all authors
        authors = [(a.id, a.name) for a in Author.objects.all()]

        if len(authors) < 2:
            self.stdout.write(self.style.WARNING("  ⚠️  Not enough authors to compare"))
            return 0

        self.stdout.write(f"  🔍 Analyzing {len(authors)} authors with threshold {threshold}...")

        # Find potential duplicates
        duplicate_groups = find_potential_duplicates(authors, threshold)

        if not duplicate_groups:
            self.stdout.write(self.style.SUCCESS("  ✓ No fuzzy duplicates found"))
            return 0

        # Display results
        for i, group in enumerate(duplicate_groups, 1):
            similarity = group["similarity"]
            author_list = group["authors"]

            self.stdout.write(self.style.NOTICE(f"\n  🔗 POTENTIAL DUPLICATE GROUP #{i} (similarity: {similarity:.2%}):"))

            # Suggest canonical name
            names = [name for _, name in author_list]
            canonical = suggest_canonical_name(names)

            self.stdout.write(self.style.SUCCESS(f"     💡 SUGGESTED CANONICAL: '{canonical}'"))

            for author_id, author_name in author_list:
                book_count = BookAuthor.objects.filter(author_id=author_id).count()
                marker = "✓" if author_name == canonical else "→"
                self.stdout.write(f"     {marker} '{author_name}' (ID: {author_id}, {book_count} books)")

            if not dry_run:
                # Note: Fuzzy matching only reports duplicates, doesn't auto-merge
                # Users should review and manually confirm merges via web UI
                pass

        self.stdout.write(self.style.NOTICE("\n  💡 TIP: Review these potential duplicates at http://127.0.0.1:8000/authors/duplicates/"))

        return len(duplicate_groups)
