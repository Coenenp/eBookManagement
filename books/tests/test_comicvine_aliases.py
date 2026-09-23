"""Tests for the Dutch -> canonical ComicVine series-name alias table."""

from unittest.mock import Mock, patch

from django.test import TestCase, override_settings

from books.scanner.extractors.comic import _enrich_with_comicvine
from books.scanner.extractors.comicvine_aliases import SERIES_ALIASES, canonicalize_series, has_alias


class ComicVineAliasesTests(TestCase):
    """Unit tests for the alias table resolver."""

    def test_known_aliases_resolve_to_canonical(self):
        self.assertEqual(canonicalize_series("Alex"), "Alix")
        self.assertEqual(canonicalize_series("De Reizen van Alex"), "Les Voyages d'Alix")
        self.assertEqual(canonicalize_series("De Jeugd van Alex"), "Alix Origines")

    def test_matching_is_case_insensitive_and_trimmed(self):
        self.assertEqual(canonicalize_series("  alex "), "Alix")
        self.assertEqual(canonicalize_series("ALEX"), "Alix")

    def test_unknown_series_passes_through_unchanged(self):
        self.assertEqual(canonicalize_series("De Kleine Robbe"), "De Kleine Robbe")
        self.assertEqual(canonicalize_series("Alex Senator"), "Alex Senator")

    def test_none_and_empty_inputs(self):
        self.assertIsNone(canonicalize_series(None))
        self.assertEqual(canonicalize_series(""), "")

    def test_alias_table_is_a_dict(self):
        # Guard: the table is a plain, extensible mapping.
        self.assertIsInstance(SERIES_ALIASES, dict)
        self.assertIn("alex", SERIES_ALIASES)

    def test_has_alias(self):
        self.assertTrue(has_alias("Alex"))
        self.assertTrue(has_alias("  alex "))
        self.assertFalse(has_alias("De Kleine Robbe"))
        self.assertFalse(has_alias("Alex Senator"))
        self.assertFalse(has_alias(None))
        self.assertFalse(has_alias(""))


class ComicVineAliasWiringTests(TestCase):
    """The active enrichment path must canonicalize the series before searching."""

    @patch("books.scanner.extractors.comicvine.ComicVineAPI")
    @override_settings(COMICVINE_API_KEY="test_key")
    def test_enrich_uses_canonical_series_name(self, mock_api_class):
        mock_api = Mock()
        mock_api.search_issue.return_value = None
        mock_api_class.return_value = mock_api

        book = Mock()
        book.id = 1

        _enrich_with_comicvine(book, {"series": "Alex", "series_number": "17"})

        mock_api.search_issue.assert_called_once_with("Alix #17")

    @patch("books.scanner.extractors.comicvine.ComicVineAPI")
    @override_settings(COMICVINE_API_KEY="test_key")
    def test_enrich_passes_through_non_aliased_series(self, mock_api_class):
        mock_api = Mock()
        mock_api.search_issue.return_value = None
        mock_api_class.return_value = mock_api

        book = Mock()
        book.id = 2

        _enrich_with_comicvine(book, {"series": "De Kleine Robbe", "series_number": "1"})

        mock_api.search_issue.assert_called_once_with("De Kleine Robbe #1")

    @patch("books.scanner.extractors.comicvine.ComicVineAPI")
    @override_settings(COMICVINE_API_KEY="test_key")
    def test_unmapped_series_failure_is_flagged(self, mock_api_class):
        mock_api = Mock()
        mock_api.search_issue.return_value = None
        mock_api_class.return_value = mock_api

        book = Mock()
        book.id = 3

        with self.assertLogs("books.scanner", level="DEBUG") as cm:
            _enrich_with_comicvine(book, {"series": "De Dooltocht van Alex", "series_number": "1"})

        self.assertTrue(any("[COMICVINE UNMAPPED SERIES]" in m for m in cm.output))

    @patch("books.scanner.extractors.comicvine.ComicVineAPI")
    @override_settings(COMICVINE_API_KEY="test_key")
    def test_aliased_series_failure_is_not_flagged_unmapped(self, mock_api_class):
        mock_api = Mock()
        mock_api.search_issue.return_value = None
        mock_api_class.return_value = mock_api

        book = Mock()
        book.id = 4

        with self.assertLogs("books.scanner", level="DEBUG") as cm:
            _enrich_with_comicvine(book, {"series": "Alex", "series_number": "99"})

        self.assertFalse(any("[COMICVINE UNMAPPED SERIES]" in m for m in cm.output))
