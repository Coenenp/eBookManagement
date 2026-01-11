"""
Navigation mixins for book views.
"""


class BookNavigationMixin:
    """Mixin to provide navigation context for book views."""

    def get_navigation_context(self, book):
        """Get navigation context for prev/next books with multiple navigation types."""
        from django.apps import apps

        Book = apps.get_model("books", "Book")

        context = {}

        # Get current book metadata for filtering
        current_metadata = getattr(book, "finalmetadata", None)
        current_author = current_metadata.final_author if current_metadata else None
        current_series = current_metadata.final_series if current_metadata else None

        # Base queryset for navigation
        base_queryset = Book.objects.select_related("finalmetadata").filter(is_placeholder=False)

        # Navigation by chronological order (ID-based)
        prev_book = base_queryset.filter(id__lt=book.id).order_by("-id").first()
        next_book = base_queryset.filter(id__gt=book.id).order_by("id").first()
        context["prev_book"] = prev_book
        context["next_book"] = next_book
        context["prev_book_id"] = prev_book.id if prev_book else None
        context["next_book_id"] = next_book.id if next_book else None

        # Navigation by same author
        if current_author:
            same_author_qs = base_queryset.filter(finalmetadata__final_author=current_author)
            context["prev_same_author"] = same_author_qs.filter(id__lt=book.id).order_by("-id").first()
            context["next_same_author"] = same_author_qs.filter(id__gt=book.id).order_by("id").first()

        # Navigation by same series (if book is part of series)
        if current_series:
            same_series_qs = base_queryset.filter(finalmetadata__final_series=current_series)
            # Order by series number if available, otherwise by ID
            context["prev_same_series"] = same_series_qs.filter(id__lt=book.id).order_by("-finalmetadata__final_series_number", "-id").first()
            context["next_same_series"] = same_series_qs.filter(id__gt=book.id).order_by("finalmetadata__final_series_number", "id").first()

        # Navigation by review status
        context["prev_reviewed"] = base_queryset.filter(finalmetadata__is_reviewed=True, id__lt=book.id).order_by("-id").first()

        context["next_reviewed"] = base_queryset.filter(finalmetadata__is_reviewed=True, id__gt=book.id).order_by("id").first()

        # Previous/next unreviewed books
        context["prev_unreviewed"] = base_queryset.filter(finalmetadata__is_reviewed=False, id__lt=book.id).order_by("-id").first()

        context["next_unreviewed"] = base_queryset.filter(finalmetadata__is_reviewed=False, id__gt=book.id).order_by("id").first()

        return context


class SimpleNavigationMixin:
    """Simple navigation mixin for basic prev/next functionality."""

    def get_simple_navigation_context(self, book):
        """Get basic navigation context for prev/next books."""
        from django.apps import apps

        Book = apps.get_model("books", "Book")

        all_books = list(Book.objects.order_by("id").values_list("id", flat=True))
        try:
            index = all_books.index(book.id)
            prev_book_id = all_books[index - 1] if index > 0 else None
            next_book_id = all_books[index + 1] if index + 1 < len(all_books) else None
        except ValueError:
            prev_book_id = None
            next_book_id = None

        return {
            "prev_book_id": prev_book_id,
            "next_book_id": next_book_id,
        }
