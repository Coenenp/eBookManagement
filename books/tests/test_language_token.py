"""Tests for the ${language_name} renaming token.

The token resolves a book's stored language code to its English name (from the
``ScanFolder.language`` choices), case-insensitively and ignoring region
subtabs, with ``Unknown Language`` as the fallback. Resolution is exercised
through ``process_template`` against a lightweight book stand-in so arbitrary
codes (``en-US``, ``xx``, ``""``) reach the token unnormalised.
"""

from types import SimpleNamespace

from django.test import SimpleTestCase

from books.models import LANGUAGE_CHOICES
from books.utils.renaming_engine import RenamingEngine


def _book(language, title="Great Book", author="Jane Doe"):
    finalmetadata = SimpleNamespace(language=language, final_title=title, final_author=author)
    return SimpleNamespace(finalmetadata=finalmetadata)


class LanguageNameTokenTests(SimpleTestCase):
    def setUp(self):
        self.engine = RenamingEngine()

    def test_language_name_resolves_every_choice(self):
        for code, name in LANGUAGE_CHOICES:
            expected = "Unknown Language" if code in ("", "und") else name
            with self.subTest(code=code):
                result = self.engine.process_template("${language_name}", _book(code))
                self.assertEqual(result, expected)

    def test_language_name_case_insensitive_and_region(self):
        for code in ("EN", "En", "en-US", "en_us"):
            with self.subTest(code=code):
                result = self.engine.process_template("${language_name}", _book(code))
                self.assertEqual(result, "English")

    def test_language_name_unknown_codes(self):
        for code in ("", "und", "xx", "zz-XX"):
            with self.subTest(code=code):
                result = self.engine.process_template("${language_name}", _book(code))
                self.assertEqual(result, "Unknown Language")

    def test_language_token_unchanged(self):
        result = self.engine.process_template("${language}", _book("en"))
        self.assertEqual(result, "en")

    def test_language_name_full_pattern(self):
        result = self.engine.process_template("${language_name}/${author.sortname}/${title}", _book("en"))
        self.assertEqual(result, "English/Doe, Jane/Great Book")
