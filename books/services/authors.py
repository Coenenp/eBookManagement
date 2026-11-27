"""Author-order service.

This is the single source of truth for the ``set_author_order`` writing
action.  Both the management command and the author order screen (UI) call
:func:`store_author_order`, so the command stays a thin printer.
"""

from books.utils.authors import find_author_by_name, normalize_author_name


def _find_collision(author, first, last):
    """Return the Author row (if any) that already holds the wanted pair.

    The pair must be a full first+last name; an empty first name cannot collide
    with the ``unique_author_name_combo`` constraint.  The row found by the
    natural-order name itself never counts as a collision.
    """
    from books.models import Author

    if not (first and last):
        return None
    qs = Author.objects.filter(first_name=first, last_name=last)
    if author is not None:
        qs = qs.exclude(pk=author.pk)
    return qs.order_by("id").first()


def _move_and_dedupe_book_authors(source_author, target_author):
    """Move every BookAuthor link from ``source_author`` to ``target_author``.

    A link whose book/role/source already exists on the target is dropped (the
    target's row wins), so no duplicate ``(book, author, role, source)`` row is
    ever created.
    """
    from books.models import BookAuthor

    held = set(
        BookAuthor.objects.filter(author=target_author).values_list(
            "book_id", "role", "source_id"
        )
    )
    for ba in list(BookAuthor.objects.filter(author=source_author)):
        key = (ba.book_id, ba.role, ba.source_id)
        if key in held:
            ba.delete()
        else:
            BookAuthor.objects.filter(pk=ba.pk).update(author=target_author)
            held.add(key)


def _collision_line(name, first, last, author, colliding):
    """One line describing the collision and the merge a run would perform."""
    return (
        f"Collision: '{colliding.name}' already holds first_name='{first}', "
        f"last_name='{last}'; would move BookAuthor links from "
        f"'{author.name}' to it, delete '{author.name}', rename the kept row "
        f"to '{name}' and set it reviewed"
    )


def _refusal_line(author, colliding, first, last):
    """One line refusing the merge because the natural-order row is reviewed."""
    return (
        f"Refused: '{author.name}' is already reviewed; will not merge it into "
        f"'{colliding.name}' which holds first_name='{first}', last_name='{last}'"
    )


def store_author_order(name, last, first, execute):
    """Store a reviewed first/last order for the author keyed by ``name``.

    Returns a dict with ``lines`` (the exact text to print), ``merged`` and, on
    execute, ``author_id``.  A dry run writes nothing; an execute writes the
    reviewed order (or performs the collision merge) and reports the result.
    """
    from django.db import transaction

    from books.models import Author

    normalized = normalize_author_name(name)

    if not execute:
        lines = [
            f"Would store order for '{name}' (normalized '{normalized}'): "
            f"first_name='{first}', last_name='{last}', is_reviewed=True"
        ]
        author = find_author_by_name(name)
        colliding = _find_collision(author, first, last)
        if colliding is not None:
            if author is not None and author.is_reviewed:
                lines.append(_refusal_line(author, colliding, first, last))
            else:
                lines.append(_collision_line(name, first, last, author, colliding))
        return {"lines": lines, "merged": False, "author_id": None}

    author = find_author_by_name(name)
    colliding = _find_collision(author, first, last)

    if colliding is not None:
        if author is not None and author.is_reviewed:
            return {
                "lines": [_refusal_line(author, colliding, first, last)],
                "merged": False,
                "author_id": None,
            }
        with transaction.atomic():
            if author is not None:
                _move_and_dedupe_book_authors(author, colliding)
                author.delete()
            Author.objects.filter(pk=colliding.pk).update(
                name=name, name_normalized=normalized, is_reviewed=True
            )
            kept = Author.objects.get(pk=colliding.pk)
    else:
        if author is None:
            author = Author(name=name)
            author.save()
        # Author.save recomputes name_normalized from first_name+last_name, so
        # write the reviewed order with a queryset update to keep the stored
        # values (and the name_normalized keyed to the natural-order name).
        Author.objects.filter(pk=author.pk).update(
            first_name=first, last_name=last, is_reviewed=True
        )
        kept = Author.objects.get(pk=author.pk)

    line = (
        f"Stored order: name='{kept.name}', first_name='{kept.first_name}', "
        f"last_name='{kept.last_name}', is_reviewed={kept.is_reviewed}"
    )
    return {"lines": [line], "merged": colliding is not None, "author_id": kept.pk}


FIELDS = [
    "final_title",
    "final_title_confidence",
    "final_author",
    "final_author_confidence",
    "final_series",
    "final_series_number",
    "final_series_confidence",
]


def _same(old, new):
    if old is None:
        old = ""
    if new is None:
        new = ""
    return old == new


def resync_final_metadata(execute=False, limit=None):
    """Recompute final title/author/series for unreviewed books.

    This is the single source of truth for the ``resync_final_metadata``
    writing action; both the management command and the metadata resync
    screen (UI) call it, so the command stays a thin printer.  It re-runs the
    three final-value update functions and returns the result as data:
    ``checked``, ``changed_titles``, ``changed_authors``, ``changed_series``
    and ``changes`` (a list of ``(book_id, field, old, new)`` tuples for the
    CSV).  Approved books (``is_reviewed=True``) are never touched, and only
    the seven final fields are written via ``update_fields``.
    """
    from books.models import FinalMetadata

    qs = FinalMetadata.objects.filter(is_reviewed=False).select_related("book").order_by("id")
    if limit is not None:
        qs = qs[:limit]

    changed_titles = 0
    changed_authors = 0
    changed_series = 0
    checked = 0
    changes = []

    for fm in qs.iterator():
        checked += 1
        old = {f: getattr(fm, f) for f in FIELDS}

        fm.update_final_title()
        fm.update_final_author()
        fm.update_final_series()

        changed = [f for f in FIELDS if not _same(old[f], getattr(fm, f))]
        if not changed:
            continue

        if not _same(old["final_title"], fm.final_title) or not _same(
            old["final_title_confidence"], fm.final_title_confidence
        ):
            changed_titles += 1
        if not _same(old["final_author"], fm.final_author) or not _same(
            old["final_author_confidence"], fm.final_author_confidence
        ):
            changed_authors += 1
        if (
            not _same(old["final_series"], fm.final_series)
            or not _same(old["final_series_number"], fm.final_series_number)
            or not _same(old["final_series_confidence"], fm.final_series_confidence)
        ):
            changed_series += 1

        for f in changed:
            changes.append((fm.book_id, f, old[f], getattr(fm, f)))

        if execute:
            fm.save(update_fields=FIELDS)

    return {
        "checked": checked,
        "changed_titles": changed_titles,
        "changed_authors": changed_authors,
        "changed_series": changed_series,
        "changes": changes,
    }
