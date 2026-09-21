"""Guard the test isolation boundary.

These tests fail if the test settings resolve any filesystem-backed resource
-- the database, MEDIA_ROOT, or the file-based cache -- outside the system
temporary directory. The whole point is to make it impossible for a test
(e.g. a cover-cache orphan cleanup) to delete real data.

The guard is portable: it asserts the resources live under
``tempfile.gettempdir()`` rather than hard-coding sandbox-specific paths.
"""

import os
import tempfile
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


def _is_inside_tempdir(path):
    """Return True when ``path`` resolves inside the system temp directory."""
    try:
        resolved = Path(path).resolve()
    except (OSError, TypeError):
        resolved = Path(os.path.abspath(str(path)))
    tmp_root = Path(tempfile.gettempdir()).resolve()
    return resolved == tmp_root or tmp_root in resolved.parents


class TestMediaRootIsolation(SimpleTestCase):
    def test_media_root_is_inside_tempdir(self):
        """MEDIA_ROOT during tests must live inside the system temp dir."""
        self.assertTrue(
            _is_inside_tempdir(settings.MEDIA_ROOT),
            f"MEDIA_ROOT={settings.MEDIA_ROOT} is not inside the system temp "
            f"directory; a test could delete real cached covers.",
        )


class TestDatabaseIsolation(SimpleTestCase):
    def test_default_database_is_inside_tempdir(self):
        """The test database must live inside the system temp dir (or memory)."""
        db_name = settings.DATABASES["default"]["NAME"]
        if str(db_name) == ":memory:":
            return
        self.assertTrue(
            _is_inside_tempdir(db_name),
            f"Test database NAME={db_name} is not inside the system temp directory.",
        )


class TestCacheIsolation(SimpleTestCase):
    def test_file_cache_is_inside_tempdir(self):
        """The file-based cache must live inside the system temp dir."""
        location = settings.CACHES["default"].get("LOCATION")
        if not location:
            return
        self.assertTrue(
            _is_inside_tempdir(location),
            f"Cache LOCATION={location} is not inside the system temp directory.",
        )
