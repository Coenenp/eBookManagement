"""Rename gate: only fully approved books (FinalMetadata.is_reviewed True) may be renamed or moved."""

import json
import shutil
import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TransactionTestCase

from books.models import FinalMetadata, UnresolvedReason
from books.tests.test_helpers import create_test_book_with_file
from books.utils.batch_renamer import BatchRenamer
from books.utils.renaming_engine import is_renamable
from books.views.renaming import BookRenamerPreviewView


class RenameGateTests(TransactionTestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(self.temp_dir, ignore_errors=True))

    def _make_book(self, name, is_reviewed=None, unresolved_reason=""):
        """Create a book + file. is_reviewed=None means no FinalMetadata row."""
        path = Path(self.temp_dir) / name
        path.touch()
        book = create_test_book_with_file(file_path=str(path), file_format="epub")
        if is_reviewed is not None:
            FinalMetadata.objects.create(
                book=book,
                final_title=Path(name).stem,
                is_reviewed=is_reviewed,
                unresolved_reason=unresolved_reason,
            )
        return book, path

    # --- predicate ---

    def test_no_finalmetadata_is_not_renamable(self):
        book, _ = self._make_book("nofm.epub", is_reviewed=None)
        self.assertFalse(is_renamable(book))

    def test_unapproved_is_not_renamable(self):
        book, _ = self._make_book("unapp.epub", is_reviewed=False)
        self.assertFalse(is_renamable(book))

    def test_approved_is_renamable(self):
        book, _ = self._make_book("app.epub", is_reviewed=True)
        self.assertTrue(is_renamable(book))

    # --- batch selection skips unapproved ---

    def test_batch_skips_unapproved_clean_book(self):
        book, path = self._make_book("unapp.epub", is_reviewed=False)
        renamer = BatchRenamer(dry_run=False)
        renamer.add_book(book, "Approved", "${title}.${ext}")
        self.assertEqual(renamer.operations, [])
        skipped = renamer.get_skipped_books()
        self.assertEqual(len(skipped), 1)
        self.assertEqual(skipped[0]["book_id"], book.id)
        self.assertEqual(skipped[0]["reason"], "not approved")
        self.assertEqual(skipped[0]["unresolved_reason"], "")
        self.assertTrue(path.exists())

    def test_batch_skips_language_disagreement_with_reason(self):
        book, _ = self._make_book(
            "ld.epub", is_reviewed=False, unresolved_reason=UnresolvedReason.LANGUAGE_DISAGREEMENT
        )
        renamer = BatchRenamer(dry_run=False)
        renamer.add_book(book, "Approved", "${title}.${ext}")
        skipped = renamer.get_skipped_books()
        self.assertEqual(skipped[0]["reason"], "not approved")
        self.assertEqual(skipped[0]["unresolved_reason"], UnresolvedReason.LANGUAGE_DISAGREEMENT)

    def test_batch_skips_no_match_with_reason(self):
        book, _ = self._make_book(
            "nm.epub", is_reviewed=False, unresolved_reason=UnresolvedReason.NO_MATCH
        )
        renamer = BatchRenamer(dry_run=False)
        renamer.add_book(book, "Approved", "${title}.${ext}")
        skipped = renamer.get_skipped_books()
        self.assertEqual(skipped[0]["reason"], "not approved")
        self.assertEqual(skipped[0]["unresolved_reason"], UnresolvedReason.NO_MATCH)

    # --- approved book renames even with a flag ---

    def test_approved_book_renames_despite_flag(self):
        book, path = self._make_book(
            "appflag.epub", is_reviewed=True, unresolved_reason=UnresolvedReason.NO_MATCH
        )
        renamer = BatchRenamer(dry_run=False)
        renamer.add_book(book, "Approved", "${title}.${ext}")
        self.assertEqual(len(renamer.operations), 1)
        successful, failed, errors = renamer.execute_operations()
        self.assertEqual(failed, 0)
        self.assertGreater(successful, 0)
        self.assertFalse(path.exists())
        self.assertTrue((Path(self.temp_dir) / "Approved" / "appflag.epub").exists())

    # --- revoked between selection and execute is not moved ---

    def test_revoked_before_execute_is_not_moved(self):
        book, path = self._make_book("revoke.epub", is_reviewed=True)
        renamer = BatchRenamer(dry_run=False)
        renamer.add_book(book, "Approved", "${title}.${ext}")
        self.assertEqual(len(renamer.operations), 1)

        fm = FinalMetadata.objects.get(book=book)
        fm.is_reviewed = False
        fm.save(update_fields=["is_reviewed"])

        successful, failed, errors = renamer.execute_operations()
        self.assertEqual(successful, 0)
        self.assertTrue(path.exists())
        self.assertEqual(len(renamer.get_skipped_books()), 1)

    # --- preview skips unapproved with reason ---

    def test_preview_skips_unapproved(self):
        book, _ = self._make_book("prev.epub", is_reviewed=False)
        user = get_user_model().objects.create_user(username="u", password="p")
        request = RequestFactory().post(
            "/",
            {"selected_books": [str(book.id)], "folder_pattern": "", "filename_pattern": "${title}.${ext}"},
        )
        request.user = user
        data = json.loads(BookRenamerPreviewView().post(request).content)
        items = data["preview_items"]
        self.assertEqual(len(items), 1)
        self.assertTrue(items[0].get("skipped"))
        self.assertEqual(items[0]["reason"], "not approved")

    # --- preview and BatchRenamer select identical sets ---

    def test_preview_and_batch_select_identical_sets(self):
        approved, _ = self._make_book("a.epub", is_reviewed=True)
        unapproved, _ = self._make_book("b.epub", is_reviewed=False)
        nofm, _ = self._make_book("c.epub", is_reviewed=None)
        books = [approved, unapproved, nofm]

        renamer = BatchRenamer(dry_run=False)
        renamer.add_books(books, "Approved", "${title}.${ext}")
        batch_selected = {op.book_id for op in renamer.operations}

        user = get_user_model().objects.create_user(username="u2", password="p")
        request = RequestFactory().post(
            "/",
            {"selected_books": [str(b.id) for b in books], "folder_pattern": "", "filename_pattern": "${title}.${ext}"},
        )
        request.user = user
        data = json.loads(BookRenamerPreviewView().post(request).content)
        preview_selected = {
            int(item["book_id"]) for item in data["preview_items"] if not item.get("skipped")
        }

        self.assertEqual(batch_selected, {approved.id})
        self.assertEqual(preview_selected, {approved.id})
