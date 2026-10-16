"""Tests for _get_best_isbn wiring (M1-OCR item 4 follow-up).

Covers that the disambiguated ISBN is chosen from LOCAL candidates only: the
file's declared metadata (EPUB/OPF) outranks a legacy content scan, external
query-result ISBNs are excluded, and ambiguity returns no ISBN plus the
AMBIGUOUS_ISBN reason.
"""

import os
import shutil
import tempfile

from django.test import TestCase

from books.models import Book, BookMetadata, DataSource, ScanFolder, UnresolvedReason
from books.scanner.external import _get_best_isbn

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
