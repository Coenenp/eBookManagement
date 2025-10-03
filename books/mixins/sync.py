"""
Model synchronization mixins for books app.
"""
import logging

logger = logging.getLogger(__name__)


class FinalMetadataSyncMixin:
    """
    Mixin that updates FinalMetadata when a related metadata record is marked inactive.
    """

    metadata_type_map = {
        'BookTitle': 'title',
        'BookAuthor': 'final_author',
        'BookCover': 'final_cover_path',
        'BookSeries': 'final_series',
        'BookPublisher': 'final_publisher',
        'BookMetadata': {
            'language': 'language',
            'isbn': 'isbn',
            'publication_year': 'publication_year',
            'description': 'description',
        },
    }

    def post_deactivation_sync(self):
        try:
            final = getattr(self.book, 'finalmetadata', None)
            if not final or self.is_active:
                return

            model_name = self.__class__.__name__

            if model_name == 'BookTitle' and hasattr(self, 'title') and self.title == final.final_title:
                final.update_final_title()

            elif model_name == 'BookAuthor' and hasattr(self, 'author') and self.author and self.author.name == final.final_author:
                final.update_final_author()

            elif model_name == 'BookCover' and hasattr(self, 'cover_path') and self.cover_path == final.final_cover_path:
                final.update_final_cover()

            elif model_name == 'BookSeries' and hasattr(self, 'series') and self.series and self.series.name == final.final_series:
                final.update_final_series()

            elif model_name == 'BookPublisher' and hasattr(self, 'publisher') and self.publisher and self.publisher.name == final.final_publisher:
                final.update_final_publisher()

            elif model_name == 'BookMetadata':
                field = self.field_name.lower()
                target_field = self.metadata_type_map.get('BookMetadata', {}).get(field)
                if target_field and getattr(final, target_field) == self.field_value:
                    final.update_dynamic_field(target_field)
        except Exception as e:
            logger.error(f"Error in post_deactivation_sync: {e}")

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.post_deactivation_sync()
