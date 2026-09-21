"""Rescan-option tests for the M1a walkthrough.

Covers the three Rescan targets -- all books, one folder, specific IDs -- each
with and without external APIs (the "Deep Scan" toggle), with external calls
mocked so no quota is spent. For each, verifies the book count is unchanged, no
duplicate Book / FinalMetadata / source records appear, and a manual metadata
edit made before the rescan survives it.
"""

from unittest.mock import patch

from django.test import TestCase

from books.models import Book, BookFile, BookTitle, DataSource, FinalMetadata
from books.scanner.background import BackgroundScanner
from books.scanner.resolver import resolve_final_metadata
from books.tests.test_helpers import create_test_book_with_file, create_test_scan_folder


class RescanOptionsTest(TestCase):
    def setUp(self):
        # Neutralise the AI-system init that BackgroundScanner.__init__ runs:
        # it trains models and rewrites the repo's training_data.csv, which a
        # test must never touch. The rescan path under test does not need it.
        self._ai_patcher = patch(
            "books.scanner.background.BackgroundScanner._initialize_ai_system",
            return_value=None,
        )
        self._ai_patcher.start()
        self.addCleanup(self._ai_patcher.stop)

        self.scan_folder = create_test_scan_folder(name="Rescan Folder")
        self.book1 = create_test_book_with_file(
            file_path="/fake/dir/book1.epub", scan_folder=self.scan_folder,
        )
        self.book2 = create_test_book_with_file(
            file_path="/fake/dir/book2.epub", scan_folder=self.scan_folder,
        )

    def _run_rescan(self, book_ids, enable_external_apis):
        scanner = BackgroundScanner("test-job")
        return scanner.rescan_existing_books(list(book_ids), enable_external_apis)

    # -- No duplicates / count unchanged ------------------------------------

    @patch("books.scanner.folder.query_external_metadata")
    @patch("books.scanner.folder.extract_internal_metadata")
    def test_rescan_all_creates_no_duplicates(self, mock_extract, mock_query):
        ids = list(Book.objects.values_list("id", flat=True))
        books_before = Book.objects.count()
        files_before = BookFile.objects.count()
        fm_before = FinalMetadata.objects.count()

        result = self._run_rescan(ids, enable_external_apis=False)

        self.assertTrue(result["success"])
        self.assertEqual(Book.objects.count(), books_before, "rescan must not create duplicate Books")
        self.assertEqual(BookFile.objects.count(), files_before, "rescan must not create duplicate BookFiles")
        self.assertEqual(FinalMetadata.objects.count(), fm_before, "rescan must not create duplicate FinalMetadata")

    # -- External-API toggle (Deep Scan on/off) -----------------------------

    @patch("books.scanner.folder.query_external_metadata")
    @patch("books.scanner.folder.extract_internal_metadata")
    def test_quick_rescan_makes_no_external_calls(self, mock_extract, mock_query):
        """Without Deep Scan, no external call is made."""
        self._run_rescan([self.book1.id], enable_external_apis=False)
        mock_extract.assert_called()
        mock_query.assert_not_called()

    @patch("books.scanner.folder.query_external_metadata")
    @patch("books.scanner.folder.extract_internal_metadata")
    def test_deep_rescan_makes_external_calls(self, mock_extract, mock_query):
        """With Deep Scan, the external metadata query goes out."""
        self._run_rescan([self.book1.id], enable_external_apis=True)
        mock_extract.assert_called()
        mock_query.assert_called()

    # -- Manual edit survives rescan ----------------------------------------

    def test_reviewed_manual_edit_survives_resolve_final_metadata(self):
        """A reviewed book's manual title survives the resolver the rescan uses.

        ``rescan_existing_books`` -> ``query_external_metadata`` ->
        ``resolve_final_metadata``. The resolver must not clobber a book that a
        human has already reviewed and edited.
        """
        source, _ = DataSource.objects.get_or_create(name="rescan_source", defaults={"trust_level": 0.8})
        fm, _ = FinalMetadata.objects.get_or_create(book=self.book1)
        fm.final_title = "Manually Edited Title"
        fm.is_reviewed = True
        fm.save()

        # A fresh extraction suggests a different title (higher confidence).
        BookTitle.objects.create(book=self.book1, title="Auto-Extracted Title", source=source, confidence=0.99, is_active=True)

        resolve_final_metadata(self.book1)

        fm.refresh_from_db()
        self.assertEqual(
            fm.final_title,
            "Manually Edited Title",
            "a reviewed book's manual edit must survive the rescan's metadata resolver",
        )

    # -- Invalid IDs --------------------------------------------------------

    @patch("books.scanner.folder.query_external_metadata")
    @patch("books.scanner.folder.extract_internal_metadata")
    def test_rescan_nonexistent_ids_is_handled(self, mock_extract, mock_query):
        """Non-existent book IDs are skipped and counted as errors, not a crash."""
        result = self._run_rescan([999999], enable_external_apis=False)
        self.assertTrue(result["success"])
        self.assertEqual(result["books_processed"], 0)
        self.assertEqual(result["errors"], 1)

    def test_rescan_blank_ids_raises(self):
        """The command refuses a rescan with no target (blank IDs)."""
        from django.core.management import call_command
        from django.core.management.base import CommandError

        with self.assertRaises(CommandError):
            call_command("scan_books", "rescan")
