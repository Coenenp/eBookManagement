"""Tests for M1-OCR item 1: langid-based language detection.

Covers the pure text-detection function (length + confidence gates) and the
``detect_language`` integration (embedded-metadata and scan-folder languages
as comparison signals that flag the book on disagreement).
"""

from unittest import mock

from django.test import TestCase

from books.models import Book, BookMetadata, DataSource, FinalMetadata, ScanFolder, UnresolvedReason
from books.utils.language import (
    MIN_LANGUAGE_CONFIDENCE,
    MIN_LANGUAGE_TEXT_CHARS,
    detect_language,
    detect_language_from_text,
    registered_scan_folder_languages,
)

# Sample texts, each well above the 300-non-whitespace-character gate.
DUTCH_TEXT = (
    "Nederland is een land in West-Europa dat bekend staat om zijn windmolens, "
    "tulpen en grachten. De hoofdstad van Nederland is Amsterdam, maar de regering "
    "zetelt in Den Haag. De Nederlandse taal wordt door ongeveer vierentwintig "
    "miljoen mensen gesproken, zowel in Nederland als in Vlaanderen en Suriname. "
    "Veel Nederlanders spreken daarnaast ook Engels en Duits, omdat deze talen op "
    "school worden onderwezen. De Nederlandse literatuur kent vele beroemde "
    "schrijvers, zoals Multatuli, Louis Couperus en Annie M.G. Schmidt. Kinderen "
    "in Nederland lezen graag boeken zoals Jip en Janneke, geschreven door Annie "
    "Schmidt. De Nederlandse keuken bestaat onder andere uit stamppot, haring en "
    "poffertjes. Elk jaar in april viert Nederland Koningsdag, een nationale "
    "feestdag met vrijmarkten en oranje kleding. De Nederlandse geschiedenis is "
    "rijk aan handel, kunst en ontdekkingsreizen over de wereldzeeën."
)

ENGLISH_TEXT = (
    "The English language is one of the most widely spoken languages in the world, "
    "with hundreds of millions of native speakers and even more who use it as a "
    "second language. It originated in medieval England and has since spread across "
    "the globe through trade, colonization, and culture. English literature includes "
    "celebrated authors such as William Shakespeare, Charles Dickens, Jane Austen, "
    "and Mark Twain. Many people learn English because it is the dominant language "
    "of science, technology, business, and international communication. The grammar "
    "of English is relatively simple compared to some other languages, but its "
    "spelling is famously irregular. English vocabulary borrows heavily from Latin, "
    "French, and Germanic roots, giving it a very large lexicon. Every year, new "
    "words are added to dictionaries as the language continues to evolve and adapt "
    "to modern life around the world."
)

FRENCH_TEXT = (
    "La langue française est une langue romane parlée par des millions de personnes "
    "à travers le monde, notamment en France, en Belgique, en Suisse, au Canada et "
    "dans plusieurs pays d'Afrique. Elle est issue du latin et a évolué au fil des "
    "siècles pour devenir une langue de culture, de diplomatie et de littérature. "
    "La littérature française compte des écrivains célèbres tels que Victor Hugo, "
    "Marcel Proust, Gustave Flaubert et Albert Camus. Le français est réputé pour "
    "sa richesse et sa précision, mais aussi pour la complexité de sa grammaire et "
    "de son orthographe. De nombreux mots français ont été empruntés par d'autres "
    "langues, notamment dans les domaines de la cuisine, de la mode et des arts. "
    "Chaque année, la francophonie est célébrée à travers le monde par des "
    "festivals et des rencontres culturelles."
)

GERMAN_TEXT = (
    "Die deutsche Sprache ist eine westgermanische Sprache, die von über hundert "
    "Millionen Menschen als Mutter- oder Zweitsprache gesprochen wird. Sie ist die "
    "Amtssprache in Deutschland, Österreich, der Schweiz, Luxemburg und "
    "Liechtenstein und wird darüber hinaus in vielen anderen Ländern gesprochen. "
    "Die deutsche Literatur zählt berühmte Schriftsteller wie Johann Wolfgang von "
    "Goethe, Friedrich Schiller, Thomas Mann und Hermann Hesse. Die deutsche "
    "Grammatik gilt als anspruchsvoll, insbesondere wegen der vier Fälle, der drei "
    "Geschlechter und der zusammengesetzten Wörter, die sehr lang werden können. "
    "Deutschland ist bekannt für seine Musik, seine Philosophie und seine "
    "Wissenschaft, und viele bedeutende Denker und Künstler haben auf Deutsch "
    "geschrieben und gearbeitet. Jedes Jahr lernen viele Menschen auf der ganzen "
    "Welt Deutsch, um in diesen reichen Traditionen zu lesen und zu forschen."
)


class DetectLanguageFromTextTests(TestCase):
    """The pure detection function: correct detection + the two gates."""

    def test_dutch_sample(self):
        code, confidence = detect_language_from_text(DUTCH_TEXT)
        self.assertEqual(code, "nl")
        self.assertGreaterEqual(confidence, MIN_LANGUAGE_CONFIDENCE)

    def test_english_sample(self):
        code, confidence = detect_language_from_text(ENGLISH_TEXT)
        self.assertEqual(code, "en")
        self.assertGreaterEqual(confidence, MIN_LANGUAGE_CONFIDENCE)

    def test_french_sample(self):
        code, confidence = detect_language_from_text(FRENCH_TEXT)
        self.assertEqual(code, "fr")
        self.assertGreaterEqual(confidence, MIN_LANGUAGE_CONFIDENCE)

    def test_german_sample(self):
        code, confidence = detect_language_from_text(GERMAN_TEXT)
        self.assertEqual(code, "de")
        self.assertGreaterEqual(confidence, MIN_LANGUAGE_CONFIDENCE)

    def test_short_sample_fails_length_gate(self):
        # Far below MIN_LANGUAGE_TEXT_CHARS non-whitespace characters.
        short = "The quick brown fox jumps over the lazy dog."
        self.assertLess(sum(1 for c in short if not c.isspace()), MIN_LANGUAGE_TEXT_CHARS)
        self.assertIsNone(detect_language_from_text(short))

    def test_empty_text_fails_length_gate(self):
        self.assertIsNone(detect_language_from_text(""))
        self.assertIsNone(detect_language_from_text(None))

    @mock.patch("books.utils.language._get_langid_identifier")
    def test_low_confidence_sample_fails_confidence_gate(self, mock_identifier):
        # A long enough sample whose detector confidence is below the floor.
        mock_identifier.return_value.classify.return_value = ("en", 0.50)
        self.assertIsNone(detect_language_from_text(ENGLISH_TEXT))

    def test_restricted_language_set(self):
        # Dutch text classified against an explicit candidate set still resolves
        # to Dutch; against a set without Dutch it cannot.
        code, _ = detect_language_from_text(DUTCH_TEXT, languages=["en", "nl", "fr", "de"])
        self.assertEqual(code, "nl")


class DetectLanguageIntegrationTests(TestCase):
    """detect_language(book, extracted_text=...) uses embedded + folder signals."""

    def setUp(self):
        # Register both an English and a Dutch folder so the production language
        # restriction resolves to {en, nl}.
        self.en_folder = ScanFolder.objects.create(path="/tmp/lang-en", name="English", language="en")
        self.nl_folder = ScanFolder.objects.create(path="/tmp/lang-nl", name="Nederlands", language="nl")
        self.book = Book.objects.create(content_type="ebook", scan_folder=self.en_folder)
        self.source, _ = DataSource.objects.get_or_create(name=DataSource.INITIAL_SCAN, defaults={"trust_level": 0.5})

    def test_registered_scan_folder_languages(self):
        self.assertEqual(registered_scan_folder_languages(), {"en", "nl"})

    def test_disagreement_with_embedded_tag_flags(self):
        # Embedded metadata says English, but the extracted text is Dutch.
        BookMetadata.objects.create(
            book=self.book,
            field_name="language",
            field_value="eng",
            source=self.source,
            confidence=0.9,
            is_active=True,
        )
        lang = detect_language(self.book, extracted_text=DUTCH_TEXT)
        self.assertEqual(lang, "nl")
        fm = FinalMetadata.objects.get(book=self.book)
        self.assertEqual(fm.unresolved_reason, UnresolvedReason.LANGUAGE_DISAGREEMENT)

    def test_contradiction_with_folder_flags(self):
        # No embedded language; the book sits in an English folder but the text
        # is Dutch. The folder language must never be written as the detection.
        lang = detect_language(self.book, extracted_text=DUTCH_TEXT)
        self.assertEqual(lang, "nl")
        fm = FinalMetadata.objects.get(book=self.book)
        self.assertEqual(fm.unresolved_reason, UnresolvedReason.LANGUAGE_DISAGREEMENT)

    def test_gate_failure_flags_undetermined(self):
        # Extracted text too short: flagged LANGUAGE_UNDETERMINED, language "und",
        # and the folder language (en) is NOT written as the detection.
        lang = detect_language(self.book, extracted_text="Hello there.")
        self.assertEqual(lang, "und")
        fm = FinalMetadata.objects.get(book=self.book)
        self.assertEqual(fm.unresolved_reason, UnresolvedReason.LANGUAGE_UNDETERMINED)

    def test_no_extracted_text_falls_back_to_folder(self):
        # Backward-compatible path: no text -> existing embedded/folder fallback.
        self.assertEqual(detect_language(self.book), "en")
