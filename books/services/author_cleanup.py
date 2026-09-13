"""
Shared author cleanup service.

This module contains the actual cleanup logic used by both the
``clean_authors`` management command and the web UI (Settings ->
Library Maintenance). Keeping the logic here avoids duplication and
ensures both entry points behave identically.
"""

import logging
from collections import defaultdict

from books.models import Author, BookAuthor
from books.utils.authors import clean_author_name, normalize_author_name

logger = logging.getLogger("books.scanner")


def run_author_cleanup(*, remove_invalid=False, clean_names=False, merge_duplicates=False, dry_run=False):
    """
    Run the requested author cleanup operations.

    Args:
        remove_invalid: Remove authors whose names resolve to empty/invalid values.
        clean_names: Normalize author names by stripping birth/death dates and
            formatting artifacts.
        merge_duplicates: Merge authors whose normalized names are identical.
        dry_run: When True, compute and report results without persisting changes.

    Returns:
        dict with summary counts and per-operation details for display in the UI:
        {
            "invalid_removed": int,
            "names_cleaned": int,
            "duplicates_merged": int,
            "invalid_authors": [{"id", "name", "book_count"}, ...],
            "cleaned_names": [{"id", "before", "after"}, ...],
            "merged_groups": [{"primary": {...}, "duplicates": [...]}, ...],
        }
    """
    stats = {
        "invalid_removed": 0,
        "names_cleaned": 0,
        "duplicates_merged": 0,
        "invalid_authors": [],
        "cleaned_names": [],
        "merged_groups": [],
    }

    if remove_invalid:
        _remove_invalid_authors(stats, dry_run)

    if clean_names:
        _clean_author_names(stats, dry_run)

    if merge_duplicates:
        _merge_duplicate_authors(stats, dry_run)

    return stats


def _remove_invalid_authors(stats, dry_run):
    """Remove authors whose names are empty or resolve to a bare year."""
    for author in Author.objects.all().iterator():
        cleaned = clean_author_name(author.name)

        if cleaned and len(cleaned) >= 2:
            continue

        book_count = BookAuthor.objects.filter(author=author).count()
        stats["invalid_authors"].append({"id": author.id, "name": author.name, "book_count": book_count})
        stats["invalid_removed"] += 1

        if not dry_run:
            BookAuthor.objects.filter(author=author).delete()
            author.delete()


def _clean_author_names(stats, dry_run):
    """Normalize author names by removing dates and formatting artifacts."""
    for author in Author.objects.all().iterator():
        original_name = author.name
        cleaned_name = clean_author_name(original_name)

        if not cleaned_name or cleaned_name == original_name:
            continue

        stats["cleaned_names"].append({"id": author.id, "before": original_name, "after": cleaned_name})
        stats["names_cleaned"] += 1

        if not dry_run:
            author.name = cleaned_name
            # Re-run name normalization so it stays in sync with the new name.
            author.name_normalized = normalize_author_name(cleaned_name)
            author.save(update_fields=["name", "name_normalized"])


def _merge_duplicate_authors(stats, dry_run):
    """Merge authors that share the same normalized name."""
    normalized_groups = defaultdict(list)
    for author in Author.objects.all().iterator():
        normalized_groups[author.name_normalized].append(author)

    for authors in normalized_groups.values():
        if len(authors) <= 1:
            continue

        # Keep the oldest author (lowest id) as the canonical entry.
        authors = sorted(authors, key=lambda a: a.id)
        primary = authors[0]
        duplicates = authors[1:]

        group = {
            "primary": {"id": primary.id, "name": primary.name},
            "duplicates": [],
        }

        for dup in duplicates:
            book_count = BookAuthor.objects.filter(author=dup).count()
            group["duplicates"].append({"id": dup.id, "name": dup.name, "book_count": book_count})
            stats["duplicates_merged"] += 1

            if not dry_run:
                BookAuthor.objects.filter(author=dup).update(author=primary)
                dup.delete()

        stats["merged_groups"].append(group)
