"""Test settings for ebook_manager.

Uses a dedicated file-based SQLite database so tests never touch the live
MariaDB/MySQL database, even when run outside of pytest's environment.
"""

from .settings import *  # noqa: F401,F403
from .settings import BASE_DIR

TESTING = True

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "test_db.sqlite3",
        "TEST": {
            "NAME": BASE_DIR / "test_db.sqlite3",
        },
    }
}
