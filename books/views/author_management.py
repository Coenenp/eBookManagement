"""
Views for advanced author management features.

Provides UI for:
- Reviewing potential duplicate authors
- Merging authors with confirmation
- Enriching author profiles from external sources
"""

import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from books.models import Author, Book, BookAuthor
from books.services.author_cleanup import (
    fix_all_books_by_author,
    normalize_all_author_names,
    run_author_cleanup,
)
from books.utils.author_matching import find_potential_duplicates, suggest_canonical_name

logger = logging.getLogger("books.scanner")


@login_required
def duplicate_authors_list(request):
    """
    Display list of potential duplicate authors for manual review.
    """
    # Get threshold from query params (default 0.85)
    threshold = float(request.GET.get("threshold", "0.85"))

    # Clamp threshold between 0.5 and 1.0
    threshold = max(0.5, min(1.0, threshold))

    # Get all authors
    authors = [(a.id, a.name) for a in Author.objects.all()]

    # Find potential duplicates
    duplicate_groups = find_potential_duplicates(authors, threshold)

    # Enrich with database info
    for group in duplicate_groups:
        enriched_authors = []
        for author_id, author_name in group["authors"]:
            author = Author.objects.get(id=author_id)
            book_count = BookAuthor.objects.filter(author=author).count()
            enriched_authors.append(
                {
                    "id": author_id,
                    "name": author_name,
                    "book_count": book_count,
                    "first_name": author.first_name,
                    "last_name": author.last_name,
                }
            )
        group["enriched_authors"] = enriched_authors

        # Add canonical suggestion
        names = [a["name"] for a in enriched_authors]
        group["suggested_canonical"] = suggest_canonical_name(names)

    context = {
        "duplicate_groups": duplicate_groups,
        "threshold": threshold,
        "total_authors": len(authors),
    }

    return render(request, "books/author_duplicates.html", context)


@login_required
@require_POST
def merge_authors(request):
    """
    Merge multiple authors into a single canonical author.
    """
    # Get author IDs to merge
    author_ids = request.POST.getlist("author_ids[]")
    primary_author_id = request.POST.get("primary_author_id")
    new_name = request.POST.get("new_name", "").strip()

    if not author_ids or len(author_ids) < 2:
        return JsonResponse({"success": False, "error": "At least 2 authors must be selected to merge"}, status=400)

    if not primary_author_id:
        return JsonResponse({"success": False, "error": "Primary author must be selected"}, status=400)

    try:
        with transaction.atomic():
            # Get primary author
            primary_author = Author.objects.get(id=primary_author_id)

            # Optionally update primary author's name
            if new_name and new_name != primary_author.name:
                primary_author.name = new_name
                primary_author.save()
                logger.info(f"[AUTHOR MERGE] Updated primary author name to: {new_name}")

            # Merge other authors into primary
            merged_names = []
            total_books = 0

            for author_id in author_ids:
                if author_id == primary_author_id:
                    continue

                author = Author.objects.get(id=author_id)
                merged_names.append(author.name)

                # Update all BookAuthor entries
                book_authors = BookAuthor.objects.filter(author=author)
                book_count = book_authors.count()
                total_books += book_count

                book_authors.update(author=primary_author)

                # Delete the merged author
                author.delete()

                logger.info(f"[AUTHOR MERGE] Merged '{author.name}' into '{primary_author.name}' ({book_count} books)")

            return JsonResponse(
                {
                    "success": True,
                    "message": f'Successfully merged {len(merged_names)} authors into "{primary_author.name}" ({total_books} books affected)',
                    "primary_author": {
                        "id": primary_author.id,
                        "name": primary_author.name,
                    },
                    "merged_names": merged_names,
                }
            )

    except Author.DoesNotExist:
        return JsonResponse({"success": False, "error": "One or more authors not found"}, status=404)

    except Exception as e:
        logger.error(f"[AUTHOR MERGE ERROR] {str(e)}")
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@login_required
def author_profile(request, author_id):
    """
    Display detailed author profile with option to enrich from external sources.
    """
    author = get_object_or_404(Author, id=author_id)

    # Get author's books
    book_authors = BookAuthor.objects.filter(author=author).select_related("book")
    books = [ba.book for ba in book_authors]

    context = {
        "author": author,
        "books": books,
        "book_count": len(books),
    }

    return render(request, "books/author_profile.html", context)


@login_required
@require_POST
def enrich_author_profile(request, author_id):
    """
    Fetch additional author information from external sources.
    """
    author = get_object_or_404(Author, id=author_id)

    try:
        # Import here to avoid circular dependency
        from books.scanner.external import enrich_author_from_external_sources

        success, data = enrich_author_from_external_sources(author)

        if success:
            return JsonResponse(
                {
                    "success": True,
                    "message": "Author profile enriched successfully",
                    "data": data,
                }
            )
        else:
            return JsonResponse(
                {
                    "success": False,
                    "error": "Could not find author information in external sources",
                },
                status=404,
            )

    except Exception as e:
        logger.error(f"[AUTHOR ENRICH ERROR] {str(e)}")
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@login_required
@require_POST
def clean_authors_ajax(request):
    """
    Run author cleanup operations from the Settings UI.

    Supports the same operations as the ``clean_authors`` management command,
    exposed here so end users can maintain their library without a shell.
    Set ``dry_run`` to true to preview changes before applying them.
    """
    remove_invalid = request.POST.get("remove_invalid", "false") == "true"
    clean_names = request.POST.get("clean_names", "false") == "true"
    merge_duplicates = request.POST.get("merge_duplicates", "false") == "true"
    dry_run = request.POST.get("dry_run", "true") == "true"

    if not any([remove_invalid, clean_names, merge_duplicates]):
        return JsonResponse({"success": False, "error": "No cleanup operation selected"}, status=400)

    try:
        stats = run_author_cleanup(
            remove_invalid=remove_invalid,
            clean_names=clean_names,
            merge_duplicates=merge_duplicates,
            dry_run=dry_run,
        )

        logger.info(f"[AUTHOR CLEANUP] dry_run={dry_run} " f"removed={stats['invalid_removed']} " f"cleaned={stats['names_cleaned']} " f"merged={stats['duplicates_merged']}")

        return JsonResponse(
            {
                "success": True,
                "dry_run": dry_run,
                "stats": stats,
            }
        )

    except Exception as e:
        logger.error(f"[AUTHOR CLEANUP ERROR] {str(e)}")
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@login_required
@require_POST
def normalize_authors_ajax(request):
    """
    Normalize every author name in one operation.

    Runs ``run_author_cleanup(clean_names=True)`` and reports the before/after
    ``cleaned_names`` list so callers can show exactly what changed.
    """
    dry_run = request.POST.get("dry_run", "false") == "true"

    try:
        stats = normalize_all_author_names(dry_run=dry_run)

        logger.info(f"[AUTHOR NORMALIZE] dry_run={dry_run} cleaned={stats['names_cleaned']}")

        return JsonResponse(
            {
                "success": True,
                "dry_run": dry_run,
                "names_cleaned": stats["names_cleaned"],
                "cleaned_names": stats["cleaned_names"],
            }
        )

    except Exception as e:
        logger.error(f"[AUTHOR NORMALIZE ERROR] {str(e)}")
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@login_required
@require_POST
def fix_books_by_author(request, book_id):
    """
    Canonicalize the author of the given book across all matching books.

    This is the "fix all books by this author" flow triggered from a book
    detail page. It resolves the book's primary author, finds fuzzy duplicates,
    picks a canonical name, and updates BookAuthor + FinalMetadata atomically.
    """
    book = get_object_or_404(Book, pk=book_id)

    try:
        result = fix_all_books_by_author(book)
    except Exception as e:
        logger.error(f"[AUTHOR FIX ERROR] book_id={book_id} {str(e)}")
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse({"success": False, "error": str(e)}, status=500)
        messages.error(request, f"Error fixing author: {str(e)}")
        return redirect("books:book_detail", pk=book.id)

    if not result.get("success"):
        reason = result.get("reason", "unknown")
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse(result, status=400)
        messages.warning(request, f"No author to fix on this book ({reason}).")
        return redirect("books:book_detail", pk=book.id)

    message = f'Author canonicalized as "{result["canonical_name"]}" ' f"across {result['books_affected']} book(s) " f"({result['metadata_updated']} metadata record(s) updated)."
    logger.info(f"[AUTHOR FIX] {message}")

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse(result)

    messages.success(request, message)
    return redirect("books:book_detail", pk=book.id)
