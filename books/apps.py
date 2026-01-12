"""Django application configuration for books app.

This module configures the books Django application and handles
initialization tasks including data source bootstrapping.
"""

from django.apps import AppConfig
from django.db.models.signals import post_migrate


class BooksConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "books"

    def ready(self):
        import sys

        from django.conf import settings

        from books.scanner.bootstrap import ensure_data_sources

        # Only run bootstrap during production migrations, not tests
        def bootstrap_handler(sender, **kwargs):
            # Detect test mode by checking if 'test' is in command line args
            is_testing = "test" in sys.argv or hasattr(settings, "TESTING") and settings.TESTING
            if not is_testing and sender == self:
                ensure_data_sources()

        post_migrate.connect(bootstrap_handler, sender=self)
