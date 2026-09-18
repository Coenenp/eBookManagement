"""
Shared author cleanup service.

This module contains the actual cleanup logic used by both the
``clean_authors`` management command and the web UI (Settings ->
Library Maintenance). Keeping the logic here avoids duplication and
ensures both entry points behave identically.
"""

import logging
from collections import defaultdict

from django.db import transaction

from books.models import Author, BookAuthor, FinalMetadata
from books.utils.author_matching import find_potential_duplicates, suggest_canonical_name
from books.utils.authors import clean_author_name, normalize_author_name, parse_author_name

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


def normalize_all_author_names(*, dry_run=False):
    """
    Normalize every author name in the library in a single operation.

    This is a convenience wrapper around ``run_author_cleanup`` that only
    performs name cleaning. It exists so both the management command and the
    web UI have a dedicated, unambiguous entry point for the bulk normalize
    action requested by the author-maintenance story.

    Args:
        dry_run: When True, report changes without persisting them.

    Returns:
        The same stats dict produced by ``run_author_cleanup``.
    """
    return run_author_cleanup(clean_names=True, dry_run=dry_run)


def _resolve_book_author(book):
    """Return the primary active author for a book, if one exists."""
    relationship = book.author_relationships.filter(is_active=True).order_by("-is_main_author", "-confidence").first()
    return relationship.author if relationship else None


def _select_primary_author(author_ids, canonical_name):
    """Choose the Author object that should survive a canonicalization merge."""
    primary = Author.objects.filter(id__in=author_ids, name=canonical_name).order_by("id").first()
    if primary is not None:
        return primary

    return Author.objects.filter(id__in=author_ids).order_by("id").first()


def _merge_author_relationships(source_author, target_author):
    """
    Re-point every BookAuthor relationship from ``source_author`` to
    ``target_author`` without creating duplicate (book, author, role, source)
    relationships.
    """
    for relationship in source_author.book_relationships.all():
        conflicting = (
            target_author.book_relationships.filter(
                book=relationship.book,
                role=relationship.role,
                source=relationship.source,
            )
            .exclude(pk=relationship.pk)
            .first()
        )

        if conflicting is not None:
            if relationship.confidence > conflicting.confidence:
                conflicting.confidence = relationship.confidence
            conflicting.is_main_author = conflicting.is_main_author or relationship.is_main_author
            conflicting.save(update_fields=["confidence", "is_main_author"])
            relationship.delete()
        else:
            # Use QuerySet.update to avoid BookAuthor.save() re-syncing metadata
            # mid-transaction; FinalMetadata is updated explicitly below.
            BookAuthor.objects.filter(pk=relationship.pk).update(author=target_author)


def fix_all_books_by_author(book, *, threshold=0.85):
    """
    Canonicalize the author of ``book`` across every matching book.

    The book's primary author is resolved, fuzzy duplicate detection is used to
    find related author records, and ``suggest_canonical_name`` selects the
    canonical spelling. All matching ``BookAuthor`` relationships are then
    re-pointed to one Author and every affected ``FinalMetadata.final_author``
    is renamed in a single transaction.

    Args:
        book: The Book whose primary author should be canonicalized.
        threshold: Fuzzy-matching threshold used by ``find_potential_duplicates``.

    Returns:
        dict describing the result, including the canonical name and the number
        of books affected.
    """
    author = _resolve_book_author(book)
    if author is None:
        return {"success": False, "reason": "no_author", "book_id": book.id}

    authors = [(a.id, a.name) for a in Author.objects.all()]
    duplicate_groups = find_potential_duplicates(authors, threshold)

    group = None
    for candidate in duplicate_groups:
        candidate_ids = [author_id for author_id, _ in candidate["authors"]]
        if author.id in candidate_ids:
            group = candidate
            break

    if group is None:
        group_ids = [author.id]
        names = [author.name]
    else:
        group_ids = [author_id for author_id, _ in group["authors"]]
        names = [name for _, name in group["authors"]]

    canonical_name = suggest_canonical_name(names)

    with transaction.atomic():
        primary = _select_primary_author(group_ids, canonical_name)

        # Keep name, normalized name, and parsed components in sync.
        primary.name = canonical_name
        primary.first_name, primary.last_name = parse_author_name(canonical_name)
        primary.name_normalized = normalize_author_name(canonical_name)
        primary.save(update_fields=["name", "first_name", "last_name", "name_normalized"])

        merged_authors = []
        for duplicate in Author.objects.filter(id__in=group_ids).exclude(id=primary.id):
            merged_authors.append({"id": duplicate.id, "name": duplicate.name})
            _merge_author_relationships(duplicate, primary)
            duplicate.delete()

        affected_book_ids = list(BookAuthor.objects.filter(author=primary).values_list("book_id", flat=True).distinct())
        metadata_updated = FinalMetadata.objects.filter(book_id__in=affected_book_ids).update(final_author=canonical_name)

    return {
        "success": True,
        "book_id": book.id,
        "author_id": primary.id,
        "canonical_name": canonical_name,
        "merged_authors": merged_authors,
        "books_affected": len(affected_book_ids),
        "metadata_updated": metadata_updated,
    }
