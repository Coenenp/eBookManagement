"""Tests for the ${language_name} renaming token.

The token resolves a book's stored language code to its English name (from the
``ScanFolder.language`` choices), case-insensitively and ignoring region
subtabs, with ``Unknown Language`` as the fallback. Resolution is exercised in
two ways:

* ``LanguageNameTokenTests`` drives ``process_template`` against a lightweight
  book stand-in so arbitrary codes (``en-US``, ``xx``, ``""``) reach the token
  unnormalised and the resolution logic is exercised directly.

* ``LanguageNameTokenDatabaseTests`` exercises the token through real ``Book``
  and ``FinalMetadata`` rows saved to the test database, so the language value
  the token actually sees is the value ``FinalMetadata.save`` normalises and
  stores (not the raw input).
"""

from types import SimpleNamespace

from django.test import SimpleTestCase, TestCase

from books.models import LANGUAGE_CHOICES
from books.models_metadata import FinalMetadata
from books.models import Book
from books.utils.language_names import LANGUAGE_NAMES
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

    def test_language_name_resolves_every_langid_code(self):
        for code, name in LANGUAGE_NAMES.items():
            with self.subTest(code=code):
                result = self.engine.process_template("${language_name}", _book(code))
                self.assertEqual(result, name)

    def test_language_names_match_scanfolder_choices(self):
        for code, name in LANGUAGE_CHOICES:
            if code in ("", "und"):
                continue
            with self.subTest(code=code):
                self.assertEqual(LANGUAGE_NAMES.get(code), name)

    def test_language_names_survive_path_sanitiser(self):
        for code, name in LANGUAGE_NAMES.items():
            with self.subTest(code=code):
                self.assertEqual(self.engine._normalize_path(name), name)

    def test_language_names_unique_and_nonempty(self):
        self.assertGreater(len(LANGUAGE_NAMES), 0)
        names = list(LANGUAGE_NAMES.values())
        self.assertEqual(len(names), len(set(names)))
        for name in names:
            self.assertTrue(name and name.strip())


class LanguageNameTokenDatabaseTests(TestCase):
    """Exercise ${language_name} through real saved FinalMetadata + Book rows."""

    def _save(self, language):
        book = Book.objects.create(content_type="ebook")
        FinalMetadata.objects.create(
            book=book,
            final_title="Great Book",
            final_author="Jane Doe",
            language=language,
        )
        book.refresh_from_db()
        stored = FinalMetadata.objects.get(book=book).language
        return book, stored

    def test_language_normalisation_stored_values(self):
        """Assert what FinalMetadata.save stores for each raw language input."""
        expected = {"en": "en", "en-US": "en", "und": "und", "": ""}
        for raw, want in expected.items():
            with self.subTest(raw=raw):
                _book_row, stored = self._save(raw)
                self.assertEqual(stored, want)

    def test_language_unmapped_code_stores_und(self):
        """An unmapped code (``xx``) normalises to None and stores ``und``."""
        book, stored = self._save("xx")
        self.assertEqual(stored, "und")
        engine = RenamingEngine()
        self.assertEqual(engine.process_template("${language_name}", book), "Unknown Language")

    def test_language_name_via_saved_finalmetadata(self):
        engine = RenamingEngine()
        cases = {
            "en": "English",
            "en-US": "English",  # normalised to "en" on save
            "und": "Unknown Language",
            "": "Unknown Language",
        }
        for raw, expected in cases.items():
            book, stored = self._save(raw)
            with self.subTest(raw=raw, stored=stored):
                result = engine.process_template("${language_name}", book)
                self.assertEqual(result, expected)
