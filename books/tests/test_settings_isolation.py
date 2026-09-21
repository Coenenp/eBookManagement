"""Guard the test isolation boundary.

These tests fail if the test settings point any filesystem-backed resource at
the real state volume (``/workspace/state``) or the NAS (``/mnt/sample``). The
whole point is to make it impossible for a test -- e.g. a cover-cache orphan
cleanup -- to delete real data.
"""

import os
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

# Paths the test suite must never write to or read real data from.
_FORBIDDEN_ROOTS = [
    Path("/workspace/state"),
    Path("/mnt/sample"),
]


def _is_inside(path, roots):
    """Return True when ``path`` is inside, or equal to, any forbidden root."""
    try:
        resolved = Path(path).resolve()
    except OSError:
        resolved = Path(os.path.abspath(str(path)))
    return any(resolved == root or root in resolved.parents for root in roots)


class TestMediaRootIsolation(SimpleTestCase):
    def test_media_root_is_not_under_workspace_state(self):
        """MEDIA_ROOT during tests must never point at the real state volume."""
        self.assertFalse(
            _is_inside(settings.MEDIA_ROOT, _FORBIDDEN_ROOTS),
            f"MEDIA_ROOT={settings.MEDIA_ROOT} resolves inside a forbidden "
            f"root; a test could delete real cached covers.",
        )


class TestDatabaseIsolation(SimpleTestCase):
    def test_default_database_is_not_under_workspace_state(self):
        """The test database must not live on the real state volume."""
        db_name = settings.DATABASES["default"]["NAME"]
        # In-memory SQLite (":memory:") is already fully isolated.
        if str(db_name) == ":memory:":
            return
        self.assertFalse(
            _is_inside(db_name, _FORBIDDEN_ROOTS),
            f"Test database NAME={db_name} resolves inside a forbidden root.",
        )


class TestCacheIsolation(SimpleTestCase):
    def test_file_cache_is_not_under_workspace_state(self):
        """The file-based cache must not leak into the persistent store."""
        location = settings.CACHES["default"].get("LOCATION")
        if not location:
            return
        self.assertFalse(
            _is_inside(location, _FORBIDDEN_ROOTS),
            f"Cache LOCATION={location} resolves inside a forbidden root.",
        )