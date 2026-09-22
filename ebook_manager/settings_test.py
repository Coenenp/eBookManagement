"""Test settings for ebook_manager.

Every filesystem-backed resource a test could touch -- the database, the
media root, and the file-based cache -- is redirected into a fresh,
per-run temporary directory. No test can therefore read or write anything
outside that directory, and a cleanup-orphans style test can never delete
the real cover cache again.
"""

import atexit
import shutil
import tempfile
from pathlib import Path

from .settings import *  # noqa: F401,F403

TESTING = True

# A per-run temporary directory that holds the isolated database, media, and
# cache. ``mkdtemp`` guarantees a unique directory per test process, so two
# concurrent runs can never collide.
_TEST_TMP = Path(tempfile.mkdtemp(prefix="ebook_test_"))

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": _TEST_TMP / "test_db.sqlite3",
        "TEST": {
            "NAME": _TEST_TMP / "test_db.sqlite3",
        },
    }
}

# The real MEDIA_ROOT (from .env, /workspace/state/media) is overridden so
# cover-cache extraction and cleanup operate on throwaway files only. Keep it
# a str: application code does ``cover_path.startswith(settings.MEDIA_ROOT)``
# and string slicing, which a pathlib.Path would break.
MEDIA_ROOT = str(_TEST_TMP / "media")

# The file-based cache also lives in the temp dir, so scan/quota counters
# never bleed into the persistent ``cache_storage/`` symlinked from the repo.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.filebased.FileBasedCache",
        "LOCATION": str(_TEST_TMP / "cache_storage"),
        "OPTIONS": {"MAX_ENTRIES": 1000},
    }
}


def _cleanup_test_tmp():
    """Remove the per-run temp dir at exit, only if still inside the temp dir."""
    tmp_root = Path(tempfile.gettempdir()).resolve()
    try:
        resolved = _TEST_TMP.resolve()
    except OSError:
        return
    # Refuse to delete anything that is not (still) inside the system temp
    # directory, as a guard against path confusion.
    if resolved == tmp_root or tmp_root in resolved.parents:
        shutil.rmtree(resolved, ignore_errors=True)


atexit.register(_cleanup_test_tmp)
