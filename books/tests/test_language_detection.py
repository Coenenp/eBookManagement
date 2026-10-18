"""Tests for M1-OCR item 2: slice-voting language detection.

Covers the pure slice-voting function (vote floor + agreement + total gates,
no confidence gate) and the ``detect_language`` integration (embedded-metadata
and scan-folder languages as comparison signals; the content code wins; a
folder contradiction raises no flag; an embedded contradiction raises
LANGUAGE_DISAGREEMENT).
"""

from unittest import mock

from django.test import TestCase

from books.models import (
    Book,
    BookMetadata,
    DataSource,
    FinalMetadata,
    ScanFolder,
    UnresolvedReason,
)
from books.utils.language import (
    SLICE_VOTE_CHARS,
    detect_language,
    detect_language_from_slices,
    registered_scan_folder_languages,
)

# Sample texts, each well above the 150-char per-slice vote floor and 300-char
# total gate.
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


class DetectLanguageFromSlicesTests(TestCase):
    """The pure voting function: vote floor + agreement + total, no confidence."""

    def test_two_agreeing_slices_accepted(self):
        self.assertEqual(detect_language_from_slices([DUTCH_TEXT, DUTCH_TEXT]), "nl")
        self.assertEqual(detect_language_from_slices([ENGLISH_TEXT, ENGLISH_TEXT]), "en")

    def test_single_voting_slice_rejected(self):
        # Only one slice clears the vote floor, so no code is accepted.
        short = "Deze tekst is te kort."
        self.assertIsNone(detect_language_from_slices([DUTCH_TEXT, short]))

    def test_short_text_rejected(self):
        # Both slices are below the vote floor.
        short_a = "a" * (SLICE_VOTE_CHARS - 1)
        short_b = "b" * (SLICE_VOTE_CHARS - 1)
        self.assertIsNone(detect_language_from_slices([short_a, short_b]))

    def test_disagreeing_slices_rejected(self):
        self.assertIsNone(detect_language_from_slices([DUTCH_TEXT, ENGLISH_TEXT]))

    def test_empty_or_none_slices_rejected(self):
        self.assertIsNone(detect_language_from_slices(None))
        self.assertIsNone(detect_language_from_slices([]))
        self.assertIsNone(detect_language_from_slices(["", ""]))

    def test_no_confidence_gate(self):
        # A detector reporting very low confidence still yields the code: langid
        # normalized confidence is no longer a decision gate.
        with mock.patch("books.utils.language._get_langid_identifier") as m:
            m.return_value.classify.return_value = ("nl", 0.01)
            self.assertEqual(detect_language_from_slices([DUTCH_TEXT, DUTCH_TEXT]), "nl")

    def test_restricted_language_set(self):
        code = detect_language_from_slices([DUTCH_TEXT, DUTCH_TEXT], languages=["en", "nl", "fr", "de"])
        self.assertEqual(code, "nl")


class DetectLanguageIntegrationTests(TestCase):
    """detect_language(book, text_slices=...) uses embedded + folder signals."""

    def setUp(self):
        self.en_folder = ScanFolder.objects.create(path="/tmp/lang-en", name="English", language="en")
        self.nl_folder = ScanFolder.objects.create(path="/tmp/lang-nl", name="Nederlands", language="nl")
        self.book = Book.objects.create(content_type="ebook", scan_folder=self.en_folder)
        self.source, _ = DataSource.objects.get_or_create(name=DataSource.INITIAL_SCAN, defaults={"trust_level": 0.5})

    def test_registered_scan_folder_languages(self):
        self.assertEqual(registered_scan_folder_languages(), {"en", "nl"})

    def test_accepted_writes_content_scan_row_and_returns_code(self):
        lang = detect_language(self.book, text_slices=[DUTCH_TEXT, DUTCH_TEXT])
        self.assertEqual(lang, "nl")
        # Provenance row written under the same source content-ISBN uses.
        row = BookMetadata.objects.filter(
            book=self.book, field_name="language", source__name=DataSource.CONTENT_SCAN
        ).first()
        self.assertIsNotNone(row)
        self.assertEqual(row.field_value, "nl")
        # No language flag was raised.
        self.assertFalse(FinalMetadata.objects.filter(book=self.book).exclude(unresolved_reason="").exists())

    def test_single_voting_slice_falls_back_to_folder(self):
        # Only one slice clears the vote floor, so the slices cannot vote; the
        # result falls back to the folder language with no flag and no row.
        short = "Deze tekst is te kort."
        lang = detect_language(self.book, text_slices=[DUTCH_TEXT, short])
        self.assertEqual(lang, "en")
        self.assertFalse(
            FinalMetadata.objects.filter(book=self.book).exclude(unresolved_reason="").exists()
        )
        self.assertFalse(
            BookMetadata.objects.filter(
                book=self.book, field_name="language", source__name=DataSource.CONTENT_SCAN
            ).exists()
        )

    def test_short_text_falls_back_to_folder(self):
        # Both slices are below the vote floor -> cannot vote -> folder language.
        lang = detect_language(self.book, text_slices=["a" * 10, "b" * 10])
        self.assertEqual(lang, "en")
        self.assertFalse(
            FinalMetadata.objects.filter(book=self.book).exclude(unresolved_reason="").exists()
        )

    def test_disagreeing_slices_rejected(self):
        lang = detect_language(self.book, text_slices=[DUTCH_TEXT, ENGLISH_TEXT])
        self.assertEqual(lang, "und")
        fm = FinalMetadata.objects.get(book=self.book)
        self.assertEqual(fm.unresolved_reason, UnresolvedReason.LANGUAGE_UNDETERMINED)

    def test_embedded_contradiction_flags_and_content_wins(self):
        # Burgersdijk shape: a Dutch translation whose embedded tag says English.
        # The content code (nl) wins and the book is flagged for the disagreement.
        book = Book.objects.create(content_type="ebook", scan_folder=self.nl_folder)
        BookMetadata.objects.create(
            book=book, field_name="language", field_value="eng",
            source=self.source, confidence=0.9, is_active=True,
        )
        lang = detect_language(book, text_slices=[DUTCH_TEXT, DUTCH_TEXT])
        self.assertEqual(lang, "nl")
        fm = FinalMetadata.objects.get(book=book)
        self.assertEqual(fm.unresolved_reason, UnresolvedReason.LANGUAGE_DISAGREEMENT)

    def test_dutch_in_english_folder_no_flag(self):
        # A folder contradiction is not an error: the content code wins with no
        # flag, so the book is reclassified rather than sent to review.
        lang = detect_language(self.book, text_slices=[DUTCH_TEXT, DUTCH_TEXT])
        self.assertEqual(lang, "nl")
        self.assertFalse(FinalMetadata.objects.filter(book=self.book).exclude(unresolved_reason="").exists())

    def test_bilingual_file_stays_undetermined(self):
        # Genuinely bilingual content: the slices disagree, so the book stays
        # undetermined even though embedded and folder each suggest a language.
        book = Book.objects.create(content_type="ebook", scan_folder=self.nl_folder)
        BookMetadata.objects.create(
            book=book, field_name="language", field_value="eng",
            source=self.source, confidence=0.9, is_active=True,
        )
        lang = detect_language(book, text_slices=[ENGLISH_TEXT, DUTCH_TEXT])
        self.assertEqual(lang, "und")
        fm = FinalMetadata.objects.get(book=book)
        self.assertEqual(fm.unresolved_reason, UnresolvedReason.LANGUAGE_UNDETERMINED)

    def test_language_flag_does_not_overwrite_existing_reason(self):
        book = Book.objects.create(content_type="ebook", scan_folder=self.nl_folder)
        BookMetadata.objects.create(
            book=book, field_name="language", field_value="eng",
            source=self.source, confidence=0.9, is_active=True,
        )
        fm = FinalMetadata(book=book, unresolved_reason=UnresolvedReason.NO_MATCH)
        fm.save(auto_sync=False)
        lang = detect_language(book, text_slices=[DUTCH_TEXT, DUTCH_TEXT])
        self.assertEqual(lang, "nl")
        fm.refresh_from_db()
        self.assertEqual(fm.unresolved_reason, UnresolvedReason.NO_MATCH)

    def test_no_slices_falls_back_to_folder(self):
        # Backward-compatible path: no text -> existing embedded/folder fallback.
        self.assertEqual(detect_language(self.book), "en")


class NotAcceptedPathTests(TestCase):
    """When slices cannot vote, detect_language falls back exactly as without
    text instead of forcing 'und'; LANGUAGE_UNDETERMINED is raised only when
    voting slices disagree or no embedded/folder language exists."""

    def setUp(self):
        self.nl_folder = ScanFolder.objects.create(path="/tmp/no-vote-nl", name="Nederlands", language="nl")
        self.en_folder = ScanFolder.objects.create(path="/tmp/no-vote-en", name="English", language="en")
        self.source, _ = DataSource.objects.get_or_create(name=DataSource.INITIAL_SCAN, defaults={"trust_level": 0.5})

    def test_epub_embedded_nl_under_6000_chars_returns_nl(self):
        # An EPUB under 6000 non-whitespace chars yields a single slice, which
        # cannot vote. It must fall back to the embedded 'nl', not 'und'.
        book = Book.objects.create(content_type="ebook", scan_folder=self.en_folder)
        BookMetadata.objects.create(
            book=book, field_name="language", field_value="nl",
            source=self.source, confidence=0.9, is_active=True,
        )
        lang = detect_language(book, text_slices=["Dit is een korte Nederlandse zin."])
        self.assertEqual(lang, "nl")
        self.assertFalse(
            BookMetadata.objects.filter(book=book, field_name="language", source__name=DataSource.CONTENT_SCAN).exists()
        )
        self.assertFalse(FinalMetadata.objects.filter(book=book).exclude(unresolved_reason="").exists())

    def test_five_page_pdf_in_nl_folder_returns_nl(self):
        # A 5-page PDF yields one slice (no middle), which cannot vote; fall back
        # to the scan-folder language.
        book = Book.objects.create(content_type="ebook", scan_folder=self.nl_folder)
        lang = detect_language(book, text_slices=["kort tekstje"])
        self.assertEqual(lang, "nl")
        self.assertFalse(
            BookMetadata.objects.filter(book=book, field_name="language", source__name=DataSource.CONTENT_SCAN).exists()
        )

    def test_unreadable_file_returns_same_as_no_text(self):
        # An unreadable file yields no usable text; the result must match
        # detect_language(book) with no text at all.
        book = Book.objects.create(content_type="ebook", scan_folder=self.nl_folder)
        expected = detect_language(book)
        self.assertEqual(detect_language(book, text_slices=[""]), expected)

    def test_no_content_scan_row_and_no_und_preview(self):
        # None of the not-accepted paths writes a Content Scan row, and none
        # resolves to 'und' (so the rename preview never renders '[und]').
        from books.utils.renaming_engine import RenamingEngine

        book = Book.objects.create(content_type="ebook", scan_folder=self.nl_folder)
        lang = detect_language(book, text_slices=["te kort"])
        self.assertEqual(lang, "nl")
        self.assertNotEqual(lang, "und")
        self.assertFalse(
            BookMetadata.objects.filter(book=book, field_name="language", source__name=DataSource.CONTENT_SCAN).exists()
        )
        fm = FinalMetadata.objects.get_or_create(book=book)[0]
        fm.language = lang
        fm.save(auto_sync=False)
        engine = RenamingEngine()
        preview = engine.process_template("${language}", book)
        self.assertEqual(engine._get_language(), "nl")
        self.assertNotIn("[und]", preview)

    def test_no_vote_without_any_language_flags_undetermined(self):
        # No embedded or folder language AND slices cannot vote -> 'und' + flag.
        folder = ScanFolder.objects.create(path="/tmp/no-vote-none", name="No Lang")
        book = Book.objects.create(content_type="ebook", scan_folder=folder)
        lang = detect_language(book, text_slices=["te kort"])
        self.assertEqual(lang, "und")
        fm = FinalMetadata.objects.get(book=book)
        self.assertEqual(fm.unresolved_reason, UnresolvedReason.LANGUAGE_UNDETERMINED)


class RescanLanguageTests(TestCase):
    """Rescan behaviour: LANGUAGE_DISAGREEMENT persists across a second scan
    when embedded metadata still contradicts the content code, and a changed
    content detection replaces the earlier Content Scan row."""

    def setUp(self):
        self.nl_folder = ScanFolder.objects.create(path="/tmp/rescan-lang", name="Nederlands", language="nl")
        self.book = Book.objects.create(content_type="ebook", scan_folder=self.nl_folder)
        self.source, _ = DataSource.objects.get_or_create(name=DataSource.INITIAL_SCAN, defaults={"trust_level": 0.5})

    def test_second_scan_keeps_language_disagreement(self):
        # Embedded metadata claims English; content is Dutch. First scan flags
        # disagreement and the content code wins.
        BookMetadata.objects.create(
            book=self.book, field_name="language", field_value="eng",
            source=self.source, confidence=0.9, is_active=True,
        )
        lang = detect_language(self.book, text_slices=[DUTCH_TEXT, DUTCH_TEXT])
        self.assertEqual(lang, "nl")
        self.assertEqual(
            FinalMetadata.objects.get(book=self.book).unresolved_reason,
            UnresolvedReason.LANGUAGE_DISAGREEMENT,
        )

        # A second scan (same embedded contradiction) must KEEP the flag, not
        # overwrite it and not re-derive "und".
        lang2 = detect_language(self.book, text_slices=[DUTCH_TEXT, DUTCH_TEXT])
        self.assertEqual(lang2, "nl")
        self.assertEqual(
            FinalMetadata.objects.get(book=self.book).unresolved_reason,
            UnresolvedReason.LANGUAGE_DISAGREEMENT,
        )

    def test_changed_detection_replaces_earlier_content_row(self):
        # First detection is Dutch -> one Content Scan row "nl".
        detect_language(self.book, text_slices=[DUTCH_TEXT, DUTCH_TEXT])
        rows = BookMetadata.objects.filter(
            book=self.book, field_name="language", source__name=DataSource.CONTENT_SCAN
        )
        self.assertEqual(rows.count(), 1)
        self.assertEqual(rows.first().field_value, "nl")

        # A changed detection (English) must replace the row, not add a second.
        detect_language(self.book, text_slices=[ENGLISH_TEXT, ENGLISH_TEXT])
        rows = BookMetadata.objects.filter(
            book=self.book, field_name="language", source__name=DataSource.CONTENT_SCAN
        )
        self.assertEqual(rows.count(), 1)
        self.assertEqual(rows.first().field_value, "en")

    def test_embedded_language_excludes_content_scan_rows(self):
        # After a content scan writes a Content Scan row, _embedded_language must
        # NOT read it back as embedded metadata (otherwise a rescan would treat
        # its own prior answer as the file's declaration).
        from books.utils.language import _embedded_language

        detect_language(self.book, text_slices=[DUTCH_TEXT, DUTCH_TEXT])  # writes "nl" row
        self.assertIsNone(_embedded_language(self.book))


class VerdictStageKeepsLanguageFlagsTests(TestCase):
    """The verdict stage must not clear language flags (M1-OCR item 4 isolation)."""

    def test_mark_resolved_preserves_language_flag(self):
        from books.scanner.match_verification import mark_resolved

        folder = ScanFolder.objects.create(path="/tmp/verdict", name="Verdict", language="nl")
        book = Book.objects.create(content_type="ebook", scan_folder=folder)
        # Disagreeing slices -> genuinely undetermined -> flag.
        lang = detect_language(book, text_slices=[DUTCH_TEXT, ENGLISH_TEXT])
        self.assertEqual(lang, "und")
        mark_resolved(book)
        fm = FinalMetadata.objects.get(book=book)
        self.assertEqual(fm.unresolved_reason, UnresolvedReason.LANGUAGE_UNDETERMINED)


class ResolverLanguageTests(TestCase):
    """resolve_final_metadata passes text slices through to detect_language."""

    def test_resolve_records_content_language_over_folder(self):
        from books.scanner.resolver import resolve_final_metadata

        folder = ScanFolder.objects.create(path="/tmp/resolve", name="Resolve", language="en")
        book = Book.objects.create(content_type="ebook", scan_folder=folder)
        resolve_final_metadata(book, text_slices=[DUTCH_TEXT, DUTCH_TEXT])
        fm = FinalMetadata.objects.get(book=book)
        self.assertEqual(fm.language, "nl")
