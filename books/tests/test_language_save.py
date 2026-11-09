"""Tests for FinalMetadata.save language normalisation.

A non-empty language value that ``normalize_language`` cannot map is kept as
its lowercase code when that code is a known langid code (a key of
``LANGUAGE_NAMES``), and stored as ``und`` otherwise.
"""

from django.db import IntegrityError
from django.test import TestCase

from books.models import Book
from books.models_metadata import FinalMetadata

# langid model codes that are NOT keys of normalize_language's map (computed
# with the project venv: 80 codes). 'la' and 'eo' are already in this list.
UNMAPPED_CODES = [
    "af", "am", "an", "ar", "as", "az", "be", "bg", "bn", "br", "bs", "cs",
    "cy", "da", "dz", "el", "eo", "et", "eu", "fa", "fi", "fo", "ga", "gl",
    "gu", "hi", "hr", "ht", "hy", "is", "jv", "ka", "kk", "km", "kn", "ku",
    "ky", "la", "lb", "lo", "lt", "lv", "mg", "mk", "ml", "mn", "mr", "ms",
    "mt", "nb", "ne", "nn", "no", "oc", "or", "pa", "ps", "qu", "ro", "rw",
    "se", "si", "sk", "sl", "sq", "sr", "sv", "sw", "ta", "te", "th", "tl",
    "ug", "uk", "ur", "vi", "vo", "wa", "xh", "zu",
]


class LanguageSaveTests(TestCase):
    def _save(self, language):
        book = Book.objects.create(content_type="ebook")
        try:
            FinalMetadata.objects.create(
                book=book,
                final_title="Great Book",
                final_author="Jane Doe",
                language=language,
            )
        except IntegrityError as exc:
            self.fail(f"saving language={language!r} raised IntegrityError: {exc}")
        return FinalMetadata.objects.get(book=book).language

    def test_langid_codes_keep_lowercase_code(self):
        for code in UNMAPPED_CODES:
            with self.subTest(code=code):
                self.assertEqual(self._save(code), code)

    def test_unknown_codes_store_und(self):
        for code in ["xx", "zxx"]:
            with self.subTest(code=code):
                self.assertEqual(self._save(code), "und")

    def test_mapped_codes_keep_value(self):
        for raw, want in [("en", "en"), ("fr", "fr"), ("de", "de"), ("nl", "nl"),
                          ("en-US", "en"), ("eng", "en"), ("und", "und")]:
            with self.subTest(raw=raw):
                self.assertEqual(self._save(raw), want)

    def test_empty_and_none_store_empty(self):
        self.assertEqual(self._save(""), "")
        self.assertEqual(self._save(None), "")
