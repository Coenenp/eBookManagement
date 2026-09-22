"""View-level tests for the Rescan form (``start_book_rescan``).

The Rescan tab posts a ``rescan_type`` radio (``all`` / ``folder`` /
``specific``) plus an optional ``enable_external_apis`` checkbox (Deep Scan).
These tests exercise every option -- each with and without Deep Scan -- with the
scanner fully mocked, and assert the correct background target is dispatched
with the right arguments.
"""

import shutil

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from books.tests.test_helpers import create_test_book_with_file, create_test_scan_folder


@patch("books.views.scanning.threading.Thread")
@patch("books.views.scanning._check_and_process_queue")
@patch("books.views.scanning.get_all_active_scans")
@patch("books.views.scanning.add_active_scan")
@patch("books.views.scanning.background_scan_folder")
@patch("books.views.scanning.background_rescan_books")
class RescanFormViewTest(TestCase):
    """Rescan options dispatch to the correct scanner with the right flags."""

    def setUp(self):
        user = get_user_model().objects.create_user(username="rescanform", password="pw")
        self.client.force_login(user)
        self.folder = create_test_scan_folder(name="Scratch")
        self.addCleanup(shutil.rmtree, self.folder.path, ignore_errors=True)
        self.book1 = create_test_book_with_file(file_path="/scan/a.epub", scan_folder=self.folder)
        self.book2 = create_test_book_with_file(file_path="/scan/b.epub", scan_folder=self.folder)

    def _post(self, **data):
        return self.client.post(reverse("books:start_book_rescan"), data)

    @staticmethod
    def _thread_call(mock_thread):
        """Return (target, args) passed to the background thread."""
        kwargs = mock_thread.call_args.kwargs
        return kwargs["target"], kwargs["args"]

    # --- rescan all books ---------------------------------------------------

    def test_all_books_with_deep_scan(
        self, mock_rescan, mock_scan_folder, mock_add, mock_active, mock_queue, mock_thread
    ):
        response = self._post(rescan_type="all", enable_external_apis="on")

        self.assertEqual(response.status_code, 302)
        target, args = self._thread_call(mock_thread)
        self.assertIs(target, mock_rescan)
        _, book_ids, deep = args
        self.assertCountEqual(book_ids, [self.book1.id, self.book2.id])
        self.assertIs(deep, True)

    def test_all_books_without_deep_scan(
        self, mock_rescan, mock_scan_folder, mock_add, mock_active, mock_queue, mock_thread
    ):
        response = self._post(rescan_type="all")

        self.assertEqual(response.status_code, 302)
        target, args = self._thread_call(mock_thread)
        self.assertIs(target, mock_rescan)
        _, book_ids, deep = args
        self.assertCountEqual(book_ids, [self.book1.id, self.book2.id])
        self.assertIs(deep, False)

    # --- one folder ----------------------------------------------------------

    def test_folder_with_deep_scan(
        self, mock_rescan, mock_scan_folder, mock_add, mock_active, mock_queue, mock_thread
    ):
        mock_active.return_value = []

        response = self._post(
            rescan_type="folder", folder_id=str(self.folder.id), enable_external_apis="on"
        )

        self.assertEqual(response.status_code, 302)
        target, args = self._thread_call(mock_thread)
        self.assertIs(target, mock_scan_folder)
        _, path, language, deep, content_type, name, rescan, resume = args
        self.assertEqual(path, self.folder.path)
        self.assertIs(deep, True)
        self.assertIs(rescan, True)

    def test_folder_without_deep_scan(
        self, mock_rescan, mock_scan_folder, mock_add, mock_active, mock_queue, mock_thread
    ):
        mock_active.return_value = []

        response = self._post(rescan_type="folder", folder_id=str(self.folder.id))

        self.assertEqual(response.status_code, 302)
        target, args = self._thread_call(mock_thread)
        self.assertIs(target, mock_scan_folder)
        _, path, language, deep, content_type, name, rescan, resume = args
        self.assertEqual(path, self.folder.path)
        self.assertIs(deep, False)

    # --- specific IDs ---------------------------------------------------------

    def test_specific_ids_with_deep_scan(
        self, mock_rescan, mock_scan_folder, mock_add, mock_active, mock_queue, mock_thread
    ):
        response = self._post(
            rescan_type="specific",
            book_ids=f"{self.book1.id},{self.book2.id}",
            enable_external_apis="on",
        )

        self.assertEqual(response.status_code, 302)
        target, args = self._thread_call(mock_thread)
        self.assertIs(target, mock_rescan)
        _, book_ids, deep = args
        self.assertEqual(book_ids, [self.book1.id, self.book2.id])
        self.assertIs(deep, True)

    def test_specific_ids_without_deep_scan(
        self, mock_rescan, mock_scan_folder, mock_add, mock_active, mock_queue, mock_thread
    ):
        response = self._post(
            rescan_type="specific", book_ids=f"{self.book1.id},{self.book2.id}"
        )

        self.assertEqual(response.status_code, 302)
        target, args = self._thread_call(mock_thread)
        self.assertIs(target, mock_rescan)
        _, book_ids, deep = args
        self.assertEqual(book_ids, [self.book1.id, self.book2.id])
        self.assertIs(deep, False)

    def test_specific_ids_ignore_stale_folder_id(
        self, mock_rescan, mock_scan_folder, mock_add, mock_active, mock_queue, mock_thread
    ):
        """A stale folder_id must never hijack a 'specific IDs' rescan."""
        response = self._post(
            rescan_type="specific",
            book_ids=f"{self.book1.id}",
            folder_id=str(self.folder.id),  # stale value from the folder select
        )

        self.assertEqual(response.status_code, 302)
        target, args = self._thread_call(mock_thread)
        self.assertIs(target, mock_rescan)  # NOT mock_scan_folder
        _, book_ids, _ = args
        self.assertEqual(book_ids, [self.book1.id])
