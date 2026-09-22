"""Guards that fail if a test mutates or deletes tracked repository files.

A test that deletes the repository's own files (such as ``books/migrations/``)
is a defect, not something to tolerate: the test suite must never alter tracked
repository files. These guards assert the essential tracked files are still
present (and non-empty where it matters) so any such mutation surfaces as a hard
failure instead of a silent ``git status`` surprise.
"""

from pathlib import Path

from django.conf import settings
from django.test import TestCase


class RepoFileIntegrityTest(TestCase):
    def test_books_migrations_directory_present(self):
        migrations_dir = Path(settings.BASE_DIR) / "books" / "migrations"
        self.assertTrue(
            migrations_dir.is_dir(),
            "books/migrations/ is missing - a test deleted tracked repository files",
        )

    def test_books_migrations_initial_migration_present(self):
        init_file = Path(settings.BASE_DIR) / "books" / "migrations" / "0001_initial.py"
        self.assertTrue(
            init_file.is_file(),
            "books/migrations/0001_initial.py is missing - a test deleted tracked repository files",
        )
        self.assertGreater(
            init_file.stat().st_size,
            0,
            "books/migrations/0001_initial.py is empty - a test truncated it",
        )
