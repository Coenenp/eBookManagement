"""Test that the cover-selection grid falls back to the real placeholder.

The cover grid's onerror handler used to point at ``no-cover.png``, a file that
does not exist, so a missing cover image left a broken image and kept the
metadata page from firing ``load``. It must point at ``cover-placeholder.svg``,
which is the same placeholder the CoverCache already serves.
"""

from pathlib import Path

from django.conf import settings
from django.template import engines
from django.test import SimpleTestCase


class CoverSelectionGridFallbackTest(SimpleTestCase):
    def _render(self):
        template = engines["django"].from_string(
            '{% include "books/partials/_cover_selection_grid.html" %}'
        )
        cover = {
            "url": "/media/cover_cache/missing.jpg",
            "path": "cover_cache/missing.jpg",
            "source_label": "EPUB Internal",
            "source_badge_class": "bg-success",
            "source_icon": "fa-book",
            "is_final": True,
            "width": 600,
            "height": 800,
            "quality_score": 90,
            "confidence": 0.8,
            "can_download": False,
            "is_downloaded": False,
            "id": 1,
        }
        book = {"file_format": "epub", "id": 1}
        return template.render({"all_covers": [cover], "book": book})

    def test_onerror_fallback_uses_placeholder_svg(self):
        html = self._render()
        self.assertIn("cover-placeholder.svg", html)
        self.assertNotIn("no-cover.png", html)

    def test_placeholder_static_file_exists(self):
        static_file = (
            Path(settings.BASE_DIR)
            / "books"
            / "static"
            / "book"
            / "images"
            / "cover-placeholder.svg"
        )
        self.assertTrue(static_file.is_file(), f"placeholder missing: {static_file}")
