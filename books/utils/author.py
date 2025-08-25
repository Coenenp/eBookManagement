from books.models import Author, BookAuthor
import logging
from django.db import models

logger = logging.getLogger("books.scanner")


def split_author_parts(raw_name):
    """Returns a tuple (first_name, last_name) from a raw author name"""
    parts = raw_name.strip().replace(",", "").split()
    if "," in raw_name and len(parts) >= 2:
        # Last, First format
        return " ".join(parts[1:]), parts[0]
    elif len(parts) == 1:
        return parts[0], ""  # fallback
    else:
        return " ".join(parts[:-1]), parts[-1]


def attach_authors(book, raw_names, source, confidence=0.8):
    for i, raw_name in enumerate(raw_names[:3]):
        raw_name = raw_name.strip()

        first, last = split_author_parts(raw_name)
        name_normalized = Author.normalize_name(f"{first} {last}")

        # Try to match by normalized name or by first+last directly
        author = Author.objects.filter(
            models.Q(name_normalized=name_normalized) |
            models.Q(first_name__iexact=first.strip(), last_name__iexact=last.strip())
        ).first()

        if not author:
            author = Author(name=raw_name, first_name=first.strip(), last_name=last.strip())
            author.save()
            logger.info(f"[AUTHOR CREATED] {raw_name} , normalized as '{author.name_normalized}'")

        BookAuthor.objects.get_or_create(
            book=book,
            author=author,
            source=source,
            defaults={
                "confidence": confidence,
                "is_main_author": i == 0,
            }
        )
