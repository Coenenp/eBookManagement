"""Tests for PR D: explicit language recording, content-type gating (Google
Books fallback for Dutch comics), and NO_MATCH / NEITHER_SOURCE aggregation."""

from unittest.mock import Mock, patch

from django.test import TestCase, override_settings

from books.models import (
    Book,
    BookMetadata,
    BookTitle,
    DataSource,
    FinalMetadata,
    ScanFolder,
    UnresolvedReason,
)
from books.scanner.extractors.comic import _enrich_with_comicvine, _google_books_fallback_for_comic
from books.scanner.match_verification import mark_unresolved
from books.scanner.resolver import finalize_unresolved_reason, resolve_final_metadata
from books.utils.language import detect_language


class DetectLanguageTests(TestCase):
    def setUp(self):
        self.scan_folder = ScanFolder.objects.create(path="/tmp/lang-test", name="Lang Test", language="nl")
        self.book = Book.objects.create(content_type="ebook", scan_folder=self.scan_folder)
        self.source, _ = DataSource.objects.get_or_create(name=DataSource.INITIAL_SCAN, defaults={"trust_level": 0.5})

    def test_metadata_language_wins_over_folder(self):
        BookMetadata.objects.create(
            book=self.book, field_name="language", field_value="eng",
            source=self.source, confidence=0.9, is_active=True,
        )
        self.assertEqual(detect_language(self.book), "en")

    def test_folder_language_is_normalized(self):
        self.assertEqual(detect_language(self.book), "nl")

    def test_no_signal_returns_none(self):
        scan_folder = ScanFolder.objects.create(path="/tmp/lang-none", name="No Lang")
        book = Book.objects.create(content_type="ebook", scan_folder=scan_folder)
        self.assertIsNone(detect_language(book))

    def test_highest_confidence_metadata_wins(self):
        BookMetadata.objects.create(
            book=self.book, field_name="language", field_value="eng",
            source=self.source, confidence=0.5, is_active=True,
        )
        BookMetadata.objects.create(
            book=self.book, field_name="language", field_value="dutch",
            source=self.source, confidence=0.9, is_active=True,
        )
        self.assertEqual(detect_language(self.book), "nl")

    def test_undetermined_metadata_falls_through_to_folder(self):
        # "und" is not a concrete language, so a concrete folder language wins.
        BookMetadata.objects.create(
            book=self.book, field_name="language", field_value="und",
            source=self.source, confidence=0.9, is_active=True,
        )
        self.assertEqual(detect_language(self.book), "nl")

    def test_only_undetermined_signal_returns_und(self):
        scan_folder = ScanFolder.objects.create(path="/tmp/lang-und", name="Und")
        book = Book.objects.create(content_type="ebook", scan_folder=scan_folder)
        BookMetadata.objects.create(
            book=book, field_name="language", field_value="other",
            source=self.source, confidence=0.9, is_active=True,
        )
        self.assertEqual(detect_language(book), "und")


class ResolverLanguageTests(TestCase):
    def test_resolve_records_language_explicitly(self):
        scan_folder = ScanFolder.objects.create(path="/tmp/resolve-lang", name="Resolve Lang", language="fr")
        book = Book.objects.create(content_type="ebook", scan_folder=scan_folder)
        resolve_final_metadata(book)  # mutates + saves FinalMetadata, returns None
        fm = FinalMetadata.objects.get(book=book)
        self.assertEqual(fm.language, "fr")


class FinalizeUnresolvedReasonTests(TestCase):
    def setUp(self):
        self.scan_folder = ScanFolder.objects.create(path="/tmp/finalize", name="Finalize")
        self.book = Book.objects.create(content_type="ebook", scan_folder=self.scan_folder)
        # resolve_final_metadata creates FinalMetadata in the real flow; finalize
        # assumes an existing record and only flags it.
        self.fm = FinalMetadata(book=self.book)
        self.fm.save(auto_sync=False)

    def test_no_external_metadata_flags_neither_source(self):
        finalize_unresolved_reason(self.book)
        self.fm.refresh_from_db()
        self.assertEqual(self.fm.unresolved_reason, UnresolvedReason.NEITHER_SOURCE)

    def test_external_title_prevents_flag(self):
        source, _ = DataSource.objects.get_or_create(name=DataSource.GOOGLE_BOOKS, defaults={"trust_level": 0.7})
        BookTitle.objects.create(book=self.book, title="Some Book", source=source, confidence=0.9, is_active=True)
        finalize_unresolved_reason(self.book)
        self.fm.refresh_from_db()
        self.assertEqual(self.fm.unresolved_reason, "")

    def test_specific_flag_is_preserved(self):
        mark_unresolved(self.book, UnresolvedReason.UNCERTAIN)
        finalize_unresolved_reason(self.book)
        self.fm.refresh_from_db()
        self.assertEqual(self.fm.unresolved_reason, UnresolvedReason.UNCERTAIN)


class ComicGoogleBooksFallbackTests(TestCase):
    def setUp(self):
        self.scan_folder = ScanFolder.objects.create(path="/tmp/gb-fallback", name="GB Fallback", language="nl")
        self.book = Book.objects.create(content_type="comic", scan_folder=self.scan_folder)

    @patch("books.scanner.external._query_google_books_combined")
    def test_dutch_comic_triggers_gb_fallback_with_series_context(self, mock_gb):
        _google_books_fallback_for_comic(self.book, {"series": "Alex", "title": "De Zwarte Klauw"})
        mock_gb.assert_called_once()
        # title/series context, not title-only
        _, query_title, _ = mock_gb.call_args[0]
        self.assertIn("Alex", query_title)

    @patch("books.scanner.external._query_google_books_combined")
    def test_non_dutch_comic_skips_fallback(self, mock_gb):
        scan_folder = ScanFolder.objects.create(path="/tmp/gb-en", name="GB EN", language="en")
        book = Book.objects.create(content_type="comic", scan_folder=scan_folder)
        _google_books_fallback_for_comic(book, {"series": "Alex", "title": "Foo"})
        mock_gb.assert_not_called()

    @patch("books.scanner.external._query_google_books_combined")
    def test_no_title_or_series_skips_fallback(self, mock_gb):
        _google_books_fallback_for_comic(self.book, {})
        mock_gb.assert_not_called()


class ComicEnrichmentFallbackWiringTests(TestCase):
    """The enrichment gate (verified=False) must actually call the fallback."""

    @patch("books.scanner.extractors.comic._google_books_fallback_for_comic")
    @patch("books.scanner.extractors.comicvine.ComicVineAPI")
    @override_settings(COMICVINE_API_KEY="test_key")
    def test_unresolved_comic_triggers_gb_fallback(self, mock_api_class, mock_fallback):
        mock_api = Mock()
        mock_api.search_issue.return_value = None
        mock_api_class.return_value = mock_api

        scan_folder = ScanFolder.objects.create(path="/tmp/wiring", name="Wiring", language="nl")
        book = Book.objects.create(content_type="comic", scan_folder=scan_folder)

        _enrich_with_comicvine(book, {"series": "De Dooltocht van Alex", "series_number": "1"})

        mock_fallback.assert_called_once()

    @patch("books.scanner.extractors.comic._google_books_fallback_for_comic")
    @patch("books.scanner.extractors.comicvine.ComicVineAPI")
    @override_settings(COMICVINE_API_KEY="test_key")
    def test_verified_comic_skips_gb_fallback(self, mock_api_class, mock_fallback):
        mock_api = Mock()
        mock_api.search_issue.return_value = {
            "name": "Le Fils de Spartacus",
            "issue_number": "17",
            "volume": {"name": "Alix", "publisher": {"name": "Casterman"}},
        }
        mock_api_class.return_value = mock_api

        scan_folder = ScanFolder.objects.create(path="/tmp/wiring-v", name="WiringV", language="nl")
        book = Book.objects.create(content_type="comic", scan_folder=scan_folder)

        _enrich_with_comicvine(book, {"series": "Alex", "series_number": "17"})

        mock_fallback.assert_not_called()
