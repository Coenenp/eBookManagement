"""Tests for the find_duplicate_content management command (Part C)."""

import shutil
import tempfile
from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase

from books.models import Book, BookFile, FileMove, ScanFolder


class FindDuplicateContentTests(TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, str(self.root), ignore_errors=True)
        self.scan_root = self.root / "lib"
        self.scan_root.mkdir()
        self.scan_folder = ScanFolder.objects.create(
            path=str(self.scan_root), name="Sample [To Delete]", content_type="ebooks", is_active=True,
        )

    def _book(self):
        book = Book.objects.create(content_type="ebook", scan_folder=self.scan_folder)
        BookFile.objects.create(book=book, file_path=str(self.scan_root / f"b{book.pk}.txt"), file_format="txt")
        return book

    def _move(self, book, original="", new=""):
        return FileMove.objects.create(
            book=book, kind=FileMove.Kind.MAIN, db_field=FileMove.DBField.FILE_PATH,
            source_path=str(self.scan_root / "s.txt"), target_path=str(self.scan_root / "t.txt"),
            state=FileMove.State.PENDING_DELETION,
            original_sha256=original, new_sha256=new,
        )

    def _companion_move(self, book, original="", new=""):
        return FileMove.objects.create(
            book=book, kind=FileMove.Kind.COMPANION, db_field=FileMove.DBField.COVER_PATH,
            source_path=str(self.scan_root / "cover.jpg"), target_path=str(self.scan_root / "c.jpg"),
            state=FileMove.State.PENDING_DELETION,
            original_sha256=original, new_sha256=new,
        )

    def test_hash_fields_are_indexed(self):
        self.assertTrue(FileMove._meta.get_field("original_sha256").db_index)
        self.assertTrue(FileMove._meta.get_field("new_sha256").db_index)

    def test_companion_hashes_not_duplicates(self):
        # Two books sharing a cover (companion) hash are not content duplicates.
        b1 = self._book()
        b2 = self._book()
        self._companion_move(b1, original="coverhash", new="coverhash")
        self._companion_move(b2, original="coverhash", new="coverhash")
        out = StringIO()
        call_command("find_duplicate_content", stdout=out)
        self.assertIn("0 duplicate group(s)", out.getvalue())

    def test_duplicate_content_flag_ignores_companion(self):
        from books.utils.safe_move.book import _duplicate_content_flag

        b1 = self._book()
        b2 = self._book()
        self._companion_move(b1, original="coverhash")
        self.assertIsNone(_duplicate_content_flag(b2, "coverhash"))

    def test_lists_groups_sharing_a_hash(self):
        b1 = self._book()
        b2 = self._book()
        b3 = self._book()
        self._move(b1, original="aaa", new="bbb")
        self._move(b2, original="aaa", new="ccc")  # shares original "aaa" with b1
        self._move(b3, original="ddd", new="bbb")  # shares new "bbb" with b1
        out = StringIO()
        call_command("find_duplicate_content", stdout=out)
        text = out.getvalue()
        self.assertIn(f"aaa 2 {b1.id} {b2.id}", text)
        self.assertIn(f"bbb 2 {b1.id} {b3.id}", text)

    def test_unique_hash_not_listed(self):
        b1 = self._book()
        b2 = self._book()
        self._move(b1, original="aaa", new="bbb")
        self._move(b2, original="ccc", new="ddd")
        out = StringIO()
        call_command("find_duplicate_content", stdout=out)
        text = out.getvalue()
        self.assertNotIn("aaa", text)
        self.assertNotIn("bbb", text)

    def test_same_book_hash_not_a_group(self):
        b1 = self._book()
        self._move(b1, original="aaa", new="aaa")
        out = StringIO()
        call_command("find_duplicate_content", stdout=out)
        text = out.getvalue()
        self.assertNotIn("aaa", text)

    def test_empty_hash_not_listed(self):
        b1 = self._book()
        b2 = self._book()
        self._move(b1, original="", new="")
        self._move(b2, original="", new="")
        out = StringIO()
        call_command("find_duplicate_content", stdout=out)
        self.assertIn("0 duplicate group(s)", out.getvalue())
