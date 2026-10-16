"""Tests for _get_best_isbn wiring (M1-OCR item 4 follow-up).

Covers that the disambiguated ISBN is chosen from LOCAL candidates only: the
file's declared metadata (EPUB/OPF) outranks a legacy content scan, external
query-result ISBNs are excluded, and ambiguity returns no ISBN plus the
AMBIGUOUS_ISBN reason.
"""

import os
import shutil
import tempfile
from unittest import mock

from django.test import TestCase

from books.models import Book, BookMetadata, BookTitle, DataSource, FinalMetadata, ScanFolder, UnresolvedReason
from books.scanner.external import _get_best_isbn, query_metadata_and_covers

ISBN_DECLARED = "9780306406157"
ISBN_CONTENT_A = "9780132350884"
ISBN_CONTENT_B = "9780747532699"
ISBN_EXTERNAL = "9780201633610"


class GetBestIsbnTests(TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.scan_folder = ScanFolder.objects.create(path=self.temp_dir, name="ISBN Scan Folder")
        self.book = Book.objects.create(content_type="ebook", scan_folder=self.scan_folder)

        def src(name):
            return DataSource.objects.get_or_create(name=name, defaults={"trust_level": 0.8})[0]

        self.epub = src(DataSource.EPUB_INTERNAL)
        self.opf = src(DataSource.OPF_FILE)
        self.content_scan = src(DataSource.CONTENT_SCAN)
        self.google = src(DataSource.GOOGLE_BOOKS)

    def tearDown(self):
        if hasattr(self, "temp_dir") and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def _add_isbn(self, source, value):
        BookMetadata.objects.create(
            book=self.book,
            field_name="isbn",
            field_value=value,
            source=source,
            confidence=0.9,
            is_active=True,
        )

    def test_declared_isbn_wins_over_content_scan(self):
        self._add_isbn(self.content_scan, ISBN_CONTENT_A)
        self._add_isbn(self.epub, ISBN_DECLARED)
        result = _get_best_isbn(self.book)
        self.assertEqual(result.isbn, ISBN_DECLARED)
        self.assertEqual(result.reason, "")

    def test_single_declared_isbn(self):
        self._add_isbn(self.epub, ISBN_DECLARED)
        result = _get_best_isbn(self.book)
        self.assertEqual(result.isbn, ISBN_DECLARED)

    def test_multiple_content_scan_isbns_ambiguous(self):
        # Two legacy CONTENT_SCAN rows (both ELSEWHERE) tie: no guess, flagged.
        self._add_isbn(self.content_scan, ISBN_CONTENT_A)
        self._add_isbn(self.content_scan, ISBN_CONTENT_B)
        result = _get_best_isbn(self.book)
        self.assertIsNone(result.isbn)
        self.assertEqual(result.reason, UnresolvedReason.AMBIGUOUS_ISBN)

    def test_external_isbn_excluded(self):
        # An external query-result ISBN is not a local candidate: no ISBN used.
        self._add_isbn(self.google, ISBN_EXTERNAL)
        result = _get_best_isbn(self.book)
        self.assertIsNone(result.isbn)
        self.assertEqual(result.reason, "")

    def test_no_isbn_returns_none(self):
        result = _get_best_isbn(self.book)
        self.assertIsNone(result.isbn)
        self.assertEqual(result.reason, "")


class QueryMetadataAndCoversAmbiguousTests(TestCase):
    """Characterization: query_metadata_and_covers with an ambiguous ISBN.

    Documents that the AMBIGUOUS_ISBN flag written up front is later overwritten
    by the match-verification verdict: mark_resolved clears it (VERIFIED) and
    mark_unresolved replaces it (UNCERTAIN / NO_MATCH), because both call
    _set_unresolved_reason unconditionally. See the proposal in PROGRESS.md.
    """

    TITLE = "Alpha Beta Gamma"
    ISBN_A = "9780306406157"
    ISBN_B = "9780132350884"

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.scan_folder = ScanFolder.objects.create(path=self.temp_dir, name="ISBN Ambiguous Scan Folder")
        self.book = Book.objects.create(content_type="ebook", scan_folder=self.scan_folder)
        content_scan = DataSource.objects.get_or_create(name=DataSource.CONTENT_SCAN, defaults={"trust_level": 0.8})[0]
        # A title so the lookup runs even though the ISBN disambiguates to None.
        BookTitle.objects.create(book=self.book, title=self.TITLE, source=content_scan, confidence=0.9, is_active=True)
        # Two distinct CONTENT_SCAN ISBNs -> ambiguous (reason AMBIGUOUS_ISBN).
        for isbn in (self.ISBN_A, self.ISBN_B):
            BookMetadata.objects.create(book=self.book, field_name="isbn", field_value=isbn, source=content_scan, confidence=0.9, is_active=True)

    def tearDown(self):
        if hasattr(self, "temp_dir") and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def _run(self, ol_doc):
        """Run query_metadata_and_covers with the API clients mocked.

        Open Library returns ``ol_doc`` (driving the title/author verdict);
        Google Books returns no items so it produces no verdict.
        """
        ol_client = mock.MagicMock()
        ol_client.make_request.return_value = {"docs": [ol_doc]}
        gb_client = mock.MagicMock()
        gb_client.make_request.return_value = {}  # no "items" -> skipped

        def _get_client(name):
            return {"open_library": ol_client, "google_books": gb_client}.get(name)

        with mock.patch("books.scanner.external.get_api_client", side_effect=_get_client):
            query_metadata_and_covers(self.book)
        return ol_client

    def test_ambiguous_isbn_runs_title_query_without_isbn(self):
        ol_client = self._run({"title": self.TITLE, "author_name": [], "isbn": []})
        qstring = ol_client.make_request.call_args.kwargs["params"]["q"]
        self.assertNotIn("isbn:", qstring)
        self.assertIn(self.TITLE, qstring)

    def test_verified_verdict_clears_ambiguous_flag(self):
        # Exact title -> VERIFIED -> mark_resolved -> "" (clears AMBIGUOUS_ISBN).
        self._run({"title": self.TITLE, "author_name": [], "isbn": []})
        fm = FinalMetadata.objects.get(book=self.book)
        self.assertEqual(fm.unresolved_reason, "")

    def test_uncertain_verdict_overwrites_ambiguous_flag(self):
        # Partial title -> UNCERTAIN -> mark_unresolved(UNCERTAIN).
        self._run({"title": "Alpha Beta", "author_name": [], "isbn": []})
        fm = FinalMetadata.objects.get(book=self.book)
        self.assertEqual(fm.unresolved_reason, UnresolvedReason.UNCERTAIN)

    def test_no_match_verdict_overwrites_ambiguous_flag(self):
        # Unrelated title -> REJECTED -> mark_unresolved(NO_MATCH).
        self._run({"title": "Totally Unrelated", "author_name": [], "isbn": []})
        fm = FinalMetadata.objects.get(book=self.book)
        self.assertEqual(fm.unresolved_reason, UnresolvedReason.NO_MATCH)
