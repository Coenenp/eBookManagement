"""Review lifecycle: approving a book clears unresolved_reason; automated
writers never write a reason onto an already-approved book.

Two halves:
- Writer guards: mark_unresolved / flag_unresolved / _set_unresolved_reason /
  finalize_unresolved_reason must skip a book whose FinalMetadata.is_reviewed
  is True (leave unresolved_reason unchanged, no error) and still write the
  reason when is_reviewed is False.
- Approval paths: the three views/functions that set is_reviewed=True must
  leave unresolved_reason empty afterwards, without clobbering unrelated
  FinalMetadata fields (stale-instance safety via update_fields/mark_resolved).
"""

import json
import shutil
import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.urls import reverse

from books.models import FinalMetadata, UnresolvedReason
from books.scanner.match_verification import (
    _set_unresolved_reason,
    flag_unresolved,
    mark_resolved,
    mark_unresolved,
)
from books.scanner.resolver import finalize_unresolved_reason
from books.tests.test_helpers import create_test_book_with_file, create_test_scan_folder


class WriterGuardTests(TestCase):
    """Automated writers: skip approved books, write on unapproved."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)
        self.scan_folder = create_test_scan_folder(temp_dir=self.temp_dir)

    def _book(self, is_reviewed, unresolved_reason=""):
        path = Path(self.temp_dir) / "b.epub"
        path.touch()
        book = create_test_book_with_file(
            file_path=str(path), file_format="epub", scan_folder=self.scan_folder
        )
        FinalMetadata.objects.create(
            book=book,
            final_title="T",
            is_reviewed=is_reviewed,
            unresolved_reason=unresolved_reason,
        )
        return book

    # --- (b) skip on reviewed ------------------------------------------------

    def test_mark_unresolved_skips_reviewed(self):
        book = self._book(is_reviewed=True)
        mark_unresolved(book, UnresolvedReason.NO_MATCH)
        self.assertEqual(FinalMetadata.objects.get(book=book).unresolved_reason, "")

    def test_flag_unresolved_skips_reviewed(self):
        book = self._book(is_reviewed=True)
        flag_unresolved(book, UnresolvedReason.AMBIGUOUS_ISBN)
        self.assertEqual(FinalMetadata.objects.get(book=book).unresolved_reason, "")

    def test_set_unresolved_reason_skips_reviewed(self):
        book = self._book(is_reviewed=True)
        _set_unresolved_reason(book, UnresolvedReason.UNCERTAIN)
        self.assertEqual(FinalMetadata.objects.get(book=book).unresolved_reason, "")

    def test_finalize_unresolved_reason_skips_reviewed(self):
        book = self._book(is_reviewed=True)
        finalize_unresolved_reason(book)
        self.assertEqual(FinalMetadata.objects.get(book=book).unresolved_reason, "")

    # --- (c) still write on unapproved ---------------------------------------

    def test_mark_unresolved_writes_unreviewed(self):
        book = self._book(is_reviewed=False)
        mark_unresolved(book, UnresolvedReason.NO_MATCH)
        self.assertEqual(FinalMetadata.objects.get(book=book).unresolved_reason, UnresolvedReason.NO_MATCH)

    def test_flag_unresolved_writes_unreviewed(self):
        book = self._book(is_reviewed=False)
        flag_unresolved(book, UnresolvedReason.AMBIGUOUS_ISBN)
        self.assertEqual(FinalMetadata.objects.get(book=book).unresolved_reason, UnresolvedReason.AMBIGUOUS_ISBN)

    def test_set_unresolved_reason_writes_unreviewed(self):
        book = self._book(is_reviewed=False)
        _set_unresolved_reason(book, UnresolvedReason.UNCERTAIN)
        self.assertEqual(FinalMetadata.objects.get(book=book).unresolved_reason, UnresolvedReason.UNCERTAIN)

    def test_finalize_unresolved_reason_writes_unreviewed(self):
        book = self._book(is_reviewed=False)
        finalize_unresolved_reason(book)  # no external source -> NEITHER_SOURCE
        self.assertEqual(FinalMetadata.objects.get(book=book).unresolved_reason, UnresolvedReason.NEITHER_SOURCE)


class ApprovalClearsUnresolvedReasonTests(TestCase):
    """Each approval path leaves unresolved_reason empty after approving."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)
        self.scan_folder = create_test_scan_folder(temp_dir=self.temp_dir)
        self.user = get_user_model().objects.create_user(username="approver", password="x")
        self.client.force_login(self.user)

    def _book_with_flag(self):
        path = Path(self.temp_dir) / "b.epub"
        path.touch()
        book = create_test_book_with_file(
            file_path=str(path), file_format="epub", scan_folder=self.scan_folder
        )
        FinalMetadata.objects.create(
            book=book,
            final_title="T",
            final_author="Author",
            is_reviewed=False,
            unresolved_reason=UnresolvedReason.NO_MATCH,
        )
        return book

    def test_metadata_update_approval_clears_reason(self):
        book = self._book_with_flag()
        resp = self.client.post(
            reverse("books:book_metadata_update", kwargs={"pk": book.id}),
            {"final_title": "T", "is_reviewed": "on"},
        )
        self.assertEqual(resp.status_code, 302)
        fm = FinalMetadata.objects.get(book=book)
        self.assertTrue(fm.is_reviewed)
        self.assertEqual(fm.unresolved_reason, "")

    def test_ajax_approval_clears_reason(self):
        book = self._book_with_flag()
        url = reverse("books:ajax_submit_ai_feedback", kwargs={"book_id": book.id})
        resp = self.client.post(
            url,
            data=json.dumps({"corrections": {"title": "T"}, "rating": 4}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["success"])
        fm = FinalMetadata.objects.get(book=book)
        self.assertTrue(fm.is_reviewed)
        self.assertEqual(fm.unresolved_reason, "")

    def test_ai_feedback_function_approval_clears_reason(self):
        from books.views.ai_feedback import submit_ai_feedback

        raw = getattr(submit_ai_feedback, "__wrapped__", submit_ai_feedback)
        book = self._book_with_flag()
        request = RequestFactory().post("/", content_type="application/json")
        request._body = json.dumps({"corrections": {"title": "T"}}).encode()
        request.user = self.user
        resp = raw(request, book.id)
        self.assertTrue(json.loads(resp.content.decode())["success"])
        fm = FinalMetadata.objects.get(book=book)
        self.assertTrue(fm.is_reviewed)
        self.assertEqual(fm.unresolved_reason, "")


class ApprovalPreservesUnrelatedFieldsTests(TestCase):
    """Approval must not clobber fields changed through a separate instance."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)
        self.scan_folder = create_test_scan_folder(temp_dir=self.temp_dir)
        self.user = get_user_model().objects.create_user(username="stale", password="x")
        self.client.force_login(self.user)

    def _book_with_flag(self):
        path = Path(self.temp_dir) / "b.epub"
        path.touch()
        book = create_test_book_with_file(
            file_path=str(path), file_format="epub", scan_folder=self.scan_folder
        )
        FinalMetadata.objects.create(
            book=book,
            final_title="T",
            is_reviewed=False,
            unresolved_reason=UnresolvedReason.NO_MATCH,
        )
        return book

    def _change_field_through_b(self, book):
        # Instance B writes a field the approval path must not overwrite.
        fm_b = FinalMetadata.objects.get(book=book)
        fm_b.publication_year = 1999
        fm_b.save(update_fields=["publication_year"])

    def test_ajax_preserves_unrelated_field(self):
        book = self._book_with_flag()
        self._change_field_through_b(book)
        url = reverse("books:ajax_submit_ai_feedback", kwargs={"book_id": book.id})
        self.client.post(
            url,
            data=json.dumps({"corrections": {"title": "T"}, "rating": 4}),
            content_type="application/json",
        )
        fm = FinalMetadata.objects.get(book=book)
        self.assertEqual(fm.publication_year, 1999)

    def test_ai_feedback_function_preserves_unrelated_field(self):
        from books.views.ai_feedback import submit_ai_feedback

        raw = getattr(submit_ai_feedback, "__wrapped__", submit_ai_feedback)
        book = self._book_with_flag()
        self._change_field_through_b(book)
        request = RequestFactory().post("/", content_type="application/json")
        request._body = json.dumps({"corrections": {"title": "T"}}).encode()
        request.user = self.user
        raw(request, book.id)
        fm = FinalMetadata.objects.get(book=book)
        self.assertEqual(fm.publication_year, 1999)

    def test_mark_resolved_preserves_unrelated_field(self):
        book = self._book_with_flag()
        self._change_field_through_b(book)
        mark_resolved(book)
        fm = FinalMetadata.objects.get(book=book)
        self.assertEqual(fm.publication_year, 1999)
        self.assertEqual(fm.unresolved_reason, "")


class ApprovalPreservesLanguageFlagTests(TestCase):
    """Approval keeps a language flag: the language reclassification flow, not
    approval, resolves language_undetermined / language_disagreement."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)
        self.scan_folder = create_test_scan_folder(temp_dir=self.temp_dir)
        self.user = get_user_model().objects.create_user(username="lang", password="x")
        self.client.force_login(self.user)

    def _book_with_language_flag(self, reason):
        path = Path(self.temp_dir) / "b.epub"
        path.touch()
        book = create_test_book_with_file(
            file_path=str(path), file_format="epub", scan_folder=self.scan_folder
        )
        FinalMetadata.objects.create(
            book=book,
            final_title="T",
            final_author="Author",
            is_reviewed=False,
            unresolved_reason=reason,
        )
        return book

    def _assert_kept(self, book, reason):
        fm = FinalMetadata.objects.get(book=book)
        self.assertTrue(fm.is_reviewed)
        self.assertEqual(fm.unresolved_reason, reason)

    def test_metadata_update_approval_keeps_language_flag(self):
        for reason in (UnresolvedReason.LANGUAGE_DISAGREEMENT, UnresolvedReason.LANGUAGE_UNDETERMINED):
            with self.subTest(reason=reason):
                book = self._book_with_language_flag(reason)
                resp = self.client.post(
                    reverse("books:book_metadata_update", kwargs={"pk": book.id}),
                    {"final_title": "T", "is_reviewed": "on"},
                )
                self.assertEqual(resp.status_code, 302)
                self._assert_kept(book, reason)

    def test_ajax_approval_keeps_language_flag(self):
        for reason in (UnresolvedReason.LANGUAGE_DISAGREEMENT, UnresolvedReason.LANGUAGE_UNDETERMINED):
            with self.subTest(reason=reason):
                book = self._book_with_language_flag(reason)
                url = reverse("books:ajax_submit_ai_feedback", kwargs={"book_id": book.id})
                resp = self.client.post(
                    url,
                    data=json.dumps({"corrections": {"title": "T"}, "rating": 4}),
                    content_type="application/json",
                )
                self.assertEqual(resp.status_code, 200)
                self._assert_kept(book, reason)

    def test_ai_feedback_function_approval_keeps_language_flag(self):
        from books.views.ai_feedback import submit_ai_feedback

        raw = getattr(submit_ai_feedback, "__wrapped__", submit_ai_feedback)
        for reason in (UnresolvedReason.LANGUAGE_DISAGREEMENT, UnresolvedReason.LANGUAGE_UNDETERMINED):
            with self.subTest(reason=reason):
                book = self._book_with_language_flag(reason)
                request = RequestFactory().post("/", content_type="application/json")
                request._body = json.dumps({"corrections": {"title": "T"}}).encode()
                request.user = self.user
                resp = raw(request, book.id)
                self.assertTrue(json.loads(resp.content.decode())["success"])
                self._assert_kept(book, reason)
