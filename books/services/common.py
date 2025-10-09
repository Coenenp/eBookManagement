"""
Cover management service for handling book cover operations.
"""
import logging
from books.utils.image_utils import encode_cover_to_base64

logger = logging.getLogger('books.scanner')


class CoverService:
    """Service class for handling book cover operations."""

    @staticmethod
    def get_cover_context(book, final_metadata):
        """Get cover context for template."""
        context = {}

        # Get cover path from first file if not in final metadata
        fallback_cover = ''
        if book.files.exists():
            first_file = book.files.first()
            fallback_cover = first_file.cover_path or ''

        context['primary_cover'] = final_metadata.final_cover_path or fallback_cover

        if context['primary_cover'] and not context['primary_cover'].startswith("http"):
            context['primary_cover_base64'] = encode_cover_to_base64(context['primary_cover'])
        else:
            context['primary_cover_base64'] = None

        context['book_cover_base64'] = encode_cover_to_base64(fallback_cover)
        return context

    @staticmethod
    def process_covers_for_book_list(books):
        """Process cover paths for a list of books."""
        processed = []

        for book in books:
            # Safely get cover path, handling books without finalmetadata
            try:
                final_cover = getattr(book.finalmetadata, 'final_cover_path', '')
                # Get fallback from first file
                fallback_cover = ''
                if book.files.exists():
                    first_file = book.files.first()
                    fallback_cover = first_file.cover_path or ''
                cover_path = final_cover or fallback_cover
            except Exception:
                # Get fallback from first file
                fallback_cover = ''
                if book.files.exists():
                    first_file = book.files.first()
                    fallback_cover = first_file.cover_path or ''
                cover_path = fallback_cover

            is_url = str(cover_path).startswith("http")
            base64_image = encode_cover_to_base64(cover_path) if cover_path and not is_url else None

            processed.append({
                "book": book,
                "cover_path": cover_path,
                "cover_base64": base64_image,
            })

        return processed


class FilePathService:
    """Service for handling file path operations."""

    @staticmethod
    def clean_filename(name):
        """Clean filename to be filesystem safe."""
        if name is None:
            return "Unknown"
        if name == "":
            return ""

        import re
        # Convert to string if not already
        cleaned = str(name)

        # Replace colon with dash
        cleaned = re.sub(r':', ' - ', cleaned)

        # Replace slashes and other invalid characters with dashes
        cleaned = re.sub(r'[/\\<>*|?]', '-', cleaned)

        # Remove other invalid characters
        cleaned = re.sub(r'[\"!]', '', cleaned)

        # Replace multiple dashes with single dash
        cleaned = re.sub(r'-+', '-', cleaned)

        # Replace multiple spaces with single space
        cleaned = re.sub(r'\s+', ' ', cleaned)

        # Trim and limit length
        cleaned = cleaned.strip()[:100]

        # Handle spaces-only input after trimming
        if not cleaned:
            return ""

        return cleaned if cleaned else "Unknown"

    @staticmethod
    def format_author_name(author_name):
        """Format author name as 'Last, First'."""
        if not author_name:
            return "Unknown Author"

        # Try to parse "First Last" format
        parts = author_name.strip().split()
        if len(parts) >= 2:
            first = ' '.join(parts[:-1])
            last = parts[-1]
            return f"{last}, {first}"
        else:
            return author_name


class DashboardService:
    """Service for dashboard-related operations."""

    @staticmethod
    def get_dashboard_statistics():
        """Get dashboard statistics."""
        from books.models import FinalMetadata, Book
        from django.db.models import Count, Avg, Q

        # Get total book count from Book model, not FinalMetadata
        total_books = Book.objects.exclude(is_placeholder=True).count()

        metadata_stats = FinalMetadata.objects.select_related('book').aggregate(
            books_with_metadata=Count('book', filter=~Q(final_title='')),
            books_with_author=Count('book', filter=~Q(final_author='')),
            books_with_cover=Count('book', filter=Q(has_cover=True)),
            books_with_isbn=Count('book', filter=~Q(isbn='')),
            books_in_series=Count('book', filter=~Q(final_series='')),
            needs_review_count=Count('book', filter=Q(is_reviewed=False)),
            avg_confidence=Avg('overall_confidence'),
            avg_completeness=Avg('completeness_score'),
            high_confidence_count=Count('book', filter=Q(overall_confidence__gte=0.8)),
            medium_confidence_count=Count('book', filter=Q(overall_confidence__gte=0.5, overall_confidence__lt=0.8)),
            low_confidence_count=Count('book', filter=Q(overall_confidence__lt=0.5)),
        )

        # Add the correct total book count
        metadata_stats['total_books'] = total_books

        format_stats = Book.objects.exclude(is_placeholder=True).values('files__file_format').annotate(
            count=Count('id')
        ).filter(files__file_format__isnull=False).order_by('-count')

        return metadata_stats, format_stats
