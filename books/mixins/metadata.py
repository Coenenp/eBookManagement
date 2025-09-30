"""
Metadata processing mixins for book views and models.
"""
from django.db import models
from django.db.models import Q, Avg
from django.core.validators import MinValueValidator, MaxValueValidator


class SourceConfidenceMixin(models.Model):
    """Common mixin for models that track source and confidence."""
    source = models.ForeignKey('books.DataSource', on_delete=models.CASCADE)
    confidence = models.FloatField(
        default=1.0,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)]
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Uncheck to hide this metadata without deleting it."
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        abstract = True


class HashFieldMixin(models.Model):
    """Common mixin for models that need hash fields for uniqueness."""

    def generate_hash(self, value):
        """Generate SHA256 hash for the given value."""
        import hashlib
        return hashlib.sha256(str(value).encode('utf-8')).hexdigest()

    class Meta:
        abstract = True


class MetadataContextMixin:
    """Mixin to provide metadata context for book views."""

    def get_metadata_context(self, book):
        """Get metadata context for template."""
        context = {}

        # Get all metadata grouped by type
        context['all_titles'] = book.titles.filter(is_active=True).order_by('-confidence')
        context['all_authors'] = book.bookauthor.filter(is_active=True).order_by('-confidence', '-is_main_author')
        context['all_genres'] = book.bookgenre.filter(is_active=True).order_by('-confidence')
        context['all_series'] = book.series_info.filter(is_active=True).order_by('-confidence')

        # If no series relationships but there is series info in final metadata
        if not context['all_series'].exists():
            series_number_metadata = book.metadata.filter(is_active=True, field_name='series_number').first()
            if series_number_metadata or (book.finalmetadata and book.finalmetadata.final_series):
                context['has_series_number_only'] = True
                context['series_number_metadata'] = series_number_metadata
                context['final_series_name'] = getattr(book.finalmetadata, 'final_series', '') if book.finalmetadata else ''
                context['final_series_number'] = getattr(book.finalmetadata, 'final_series_number', '') if book.finalmetadata else ''

        context['all_publishers'] = book.bookpublisher.filter(is_active=True).order_by('-confidence')
        context['all_covers'] = book.covers.filter(is_active=True).order_by('-confidence', '-is_high_resolution')

        # Current genres for checkboxes
        current_genres = list(book.bookgenre.filter(is_active=True).values_list('genre__name', flat=True))
        context['current_genres'] = current_genres

        # Data sources ordered by trust level
        from django.apps import apps
        DataSource = apps.get_model('books', 'DataSource')
        context['data_sources'] = DataSource.objects.all().order_by('-trust_level')

        # Conflict detection
        context['has_conflicts'] = (
            context['all_titles'].count() > 1 or
            context['all_authors'].count() > 1 or
            context['all_series'].count() > 1 or
            context['all_publishers'].count() > 1
        )

        return context

    def get_metadata_fields_context(self, book):
        """Get additional metadata fields for the review form"""
        from ..models import LANGUAGE_CHOICES

        return {
            'series_number_metadata': book.metadata.filter(field_name='series_number', is_active=True).order_by('-confidence'),
            'description_metadata': book.metadata.filter(field_name='description', is_active=True).order_by('-confidence'),
            'isbn_metadata': book.metadata.filter(field_name='isbn', is_active=True).order_by('-confidence'),
            'year_metadata': book.metadata.filter(field_name='publication_year', is_active=True).order_by('-confidence'),
            'language_metadata': book.metadata.filter(field_name='language', is_active=True).order_by('-confidence'),
            'language_choices': LANGUAGE_CHOICES,
        }


class BookListContextMixin:
    """Mixin to provide context for book list views."""

    def get_list_statistics_context(self):
        """Get statistics for book list context."""
        from django.apps import apps
        LANGUAGE_CHOICES = getattr(apps.get_model('books', 'Book'), 'LANGUAGE_CHOICES', [])
        DataSource = apps.get_model('books', 'DataSource')

        metadata_stats = apps.get_model('books', 'FinalMetadata').objects.aggregate(
            avg_confidence=Avg('overall_confidence'),
            avg_completeness=Avg('completeness_score')
        )

        # Get all language values from database and filter to only valid ISO codes
        all_languages = apps.get_model('books', 'FinalMetadata').objects.values_list('language', flat=True).distinct()
        valid_language_codes = [code for code, name in LANGUAGE_CHOICES] if LANGUAGE_CHOICES else []
        used_languages = [lang for lang in all_languages if lang in valid_language_codes]

        # Create language choices for template
        lang_dict = dict(LANGUAGE_CHOICES) if LANGUAGE_CHOICES else {}
        languages = [(code, lang_dict[code]) for code in used_languages if code in lang_dict]

        # Get all datasources that have been used for metadata
        used_datasources = DataSource.objects.filter(
            Q(booktitle__isnull=False) |
            Q(bookauthor__isnull=False) |
            Q(bookgenre__isnull=False) |
            Q(bookseries__isnull=False) |
            Q(bookpublisher__isnull=False) |
            Q(bookcover__isnull=False) |
            Q(bookmetadata__isnull=False)
        ).distinct().values_list('name', 'name').order_by('name')

        context = {
            'avg_confidence': (metadata_stats['avg_confidence'] or 0) * 100,
            'avg_completeness': (metadata_stats['avg_completeness'] or 0) * 100,
            'languages': languages,
            'datasources': used_datasources,
        }

        return context

    def get_filter_context(self):
        """Get filter context for template rendering."""
        from ..views.utilities import get_filter_params, build_filter_context

        # Extract filter parameters from request
        filters = get_filter_params(self.request.GET)

        # Build context for template
        filter_context = build_filter_context(filters)

        # Add review counts for review filters
        from django.apps import apps
        Book = apps.get_model('books', 'Book')

        review_counts = {
            'needs_review': Book.objects.filter(
                Q(finalmetadata__is_reviewed=False) | Q(finalmetadata__isnull=True)
            ).count(),
            'low_confidence': Book.objects.filter(
                finalmetadata__overall_confidence__lt=0.5
            ).count(),
            'incomplete': Book.objects.filter(
                finalmetadata__completeness_score__lt=0.7
            ).count(),
            'missing_cover': Book.objects.filter(
                finalmetadata__has_cover=False
            ).count(),
            'duplicates': Book.objects.filter(is_duplicate=True).count(),
            'placeholders': Book.objects.filter(is_placeholder=True).count(),
        }

        filter_context['review_counts'] = review_counts
        filter_context['corrupted_count'] = Book.objects.filter(is_corrupted=True).count()

        return filter_context
