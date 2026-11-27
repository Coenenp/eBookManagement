"""Tests for the revert_moves service and its management command."""

import hashlib
import os
import shutil
import tempfile
from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase

from books.models import BookFile, FileMove
from books.services.moves import revert_moves
from books.tests.test_helpers import create_test_book_with_file, create_test_scan_folder


class RevertMovesTests(TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(self.temp_dir, ignore_errors=True))
        self.scan_folder = create_test_scan_folder(temp_dir=self.temp_dir)

    def _moved_book(self, name, nested=False):
        """Simulate a completed safe move: source archived, file at target,
        BookFile pointing at the target, and a pending_deletion journal row."""
        src = Path(self.temp_dir) / "src" / name
        src.parent.mkdir(parents=True, exist_ok=True)
        data = b"%PDF-1.4 fake pdf " + name.encode()
        src.write_bytes(data)
        book = create_test_book_with_file(
            file_path=str(src), file_format="pdf",
            scan_folder=self.scan_folder, content_type="ebook",
        )
        archive = Path(self.temp_dir) / "Archive [To Delete]" / name
        archive.parent.mkdir(parents=True, exist_ok=True)
        target = Path(self.temp_dir) / ("Approved" if not nested else "Approved/sub") / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(src), str(archive))
        os.rename(str(src), str(target))
        pf = book.primary_file
        pf.file_path = str(target)
        pf.save(update_fields=["file_path"])
        h = hashlib.sha256(data).hexdigest()
        row = FileMove.objects.create(
            book=book,
            kind=FileMove.Kind.MAIN,
            db_field=FileMove.DBField.FILE_PATH,
            source_path=str(src),
            target_path=str(target),
            archived_path=str(archive),
            state=FileMove.State.PENDING_DELETION,
            original_sha256=h,
            archived_sha256=h,
            new_sha256=h,
            previous_paths={"file_path": str(src), "cover_path": "", "opf_path": "", "final_path": ""},
        )
        return book, src, target, archive, row, data

    def test_dry_run_changes_nothing(self):
        book, src, target, archive, row, data = self._moved_book("dr.pdf")
        result = revert_moves(book_ids=[book.id])
        self.assertTrue(result["dry_run"])
        self.assertEqual(result["counts"]["planned"], 1)
        self.assertEqual(result["counts"]["restored"], 0)
        # Nothing changed on disk or in the DB.
        self.assertTrue(target.exists())
        self.assertFalse(src.exists())
        self.assertEqual(book.primary_file.file_path, str(target))
        row.refresh_from_db()
        self.assertEqual(row.state, FileMove.State.PENDING_DELETION)

    def test_execute_restores_files_and_paths(self):
        book, src, target, archive, row, data = self._moved_book("ex.pdf")
        result = revert_moves(book_ids=[book.id], execute=True)
        self.assertFalse(result["dry_run"])
        self.assertEqual(result["counts"]["restored"], 1)
        self.assertTrue(src.is_file())
        self.assertEqual(src.read_bytes(), data)  # original restored
        self.assertFalse(target.exists())  # moved file deleted
        book.refresh_from_db()
        self.assertEqual(book.primary_file.file_path, str(src))
        row.refresh_from_db()
        self.assertEqual(row.state, FileMove.State.ROLLED_BACK)

    def test_missing_archive_refuses(self):
        book, src, target, archive, row, data = self._moved_book("ma.pdf")
        archive.unlink()  # archive missing
        result = revert_moves(book_ids=[book.id], execute=True)
        self.assertEqual(result["counts"]["restored"], 0)
        self.assertEqual([r["reason"] for r in result["refusals"]], ["archive-missing"])
        self.assertFalse(src.exists())  # nothing restored
        self.assertTrue(target.exists())  # nothing deleted
        row.refresh_from_db()
        self.assertEqual(row.state, FileMove.State.PENDING_DELETION)

    def test_hash_mismatch_refuses(self):
        book, src, target, archive, row, data = self._moved_book("hm.pdf")
        archive.write_bytes(b"corrupted")  # hash differs
        result = revert_moves(book_ids=[book.id], execute=True)
        self.assertEqual(result["counts"]["restored"], 0)
        self.assertEqual([r["reason"] for r in result["refusals"]], ["archive-hash-mismatch"])
        self.assertFalse(src.exists())
        self.assertTrue(target.exists())
        row.refresh_from_db()
        self.assertEqual(row.state, FileMove.State.PENDING_DELETION)

    def test_second_run_changes_nothing(self):
        book, src, target, archive, row, data = self._moved_book("2nd.pdf")
        revert_moves(book_ids=[book.id], execute=True)
        result = revert_moves(book_ids=[book.id], execute=True)
        self.assertEqual(result["counts"]["planned"], 0)
        self.assertEqual(result["counts"]["restored"], 0)
        self.assertTrue(result["counts"]["nothing_to_do"])

    def test_rolled_back_rows_ignored(self):
        book, src, target, archive, row, data = self._moved_book("rb.pdf")
        row.state = FileMove.State.ROLLED_BACK
        row.save(update_fields=["state"])
        result = revert_moves(book_ids=[book.id], execute=True)
        self.assertEqual(result["counts"]["planned"], 0)
        self.assertEqual(result["counts"]["restored"], 0)
        self.assertTrue(target.exists())  # not reverted

    def test_duplicate_rows_deduped(self):
        book, src, target, archive, row, data = self._moved_book("dup.pdf")
        result = revert_moves(book_ids=[book.id, book.id], execute=True)
        self.assertEqual(result["counts"]["planned"], 1)
        self.assertEqual(result["counts"]["restored"], 1)

    def test_empty_folders_removed_non_empty_left(self):
        # Nested empty target folder -> removed after revert.
        b1, s1, t1, a1, r1, d1 = self._moved_book("e1.pdf", nested=True)
        # A sibling folder that stays non-empty -> left alone.
        keep = Path(self.temp_dir) / "Approved" / "keep" / "other.txt"
        keep.parent.mkdir(parents=True, exist_ok=True)
        keep.write_bytes(b"stay")
        result = revert_moves(book_ids=[b1.id], execute=True)
        self.assertEqual(result["counts"]["restored"], 1)
        self.assertFalse((Path(self.temp_dir) / "Approved" / "sub").exists())
        self.assertTrue(keep.exists())
        self.assertTrue((Path(self.temp_dir) / "Approved" / "keep").exists())


class RevertMovesCommandTests(TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(self.temp_dir, ignore_errors=True))
        self.scan_folder = create_test_scan_folder(temp_dir=self.temp_dir)

    def _moved_book(self, name):
        src = Path(self.temp_dir) / "src" / name
        src.parent.mkdir(parents=True, exist_ok=True)
        data = b"%PDF-1.4 fake pdf " + name.encode()
        src.write_bytes(data)
        book = create_test_book_with_file(
            file_path=str(src), file_format="pdf",
            scan_folder=self.scan_folder, content_type="ebook",
        )
        archive = Path(self.temp_dir) / "Archive [To Delete]" / name
        archive.parent.mkdir(parents=True, exist_ok=True)
        target = Path(self.temp_dir) / "Approved" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(src), str(archive))
        os.rename(str(src), str(target))
        pf = book.primary_file
        pf.file_path = str(target)
        pf.save(update_fields=["file_path"])
        h = hashlib.sha256(data).hexdigest()
        row = FileMove.objects.create(
            book=book, kind=FileMove.Kind.MAIN, db_field=FileMove.DBField.FILE_PATH,
            source_path=str(src), target_path=str(target), archived_path=str(archive),
            state=FileMove.State.PENDING_DELETION, original_sha256=h, archived_sha256=h,
            new_sha256=h,
            previous_paths={"file_path": str(src), "cover_path": "", "opf_path": "", "final_path": ""},
        )
        return book, src, target, archive, row

    def test_dry_run_default_and_prints_only(self):
        book, src, target, archive, row = self._moved_book("cmd.pdf")
        out = StringIO()
        call_command("revert_moves", "--book-id", str(book.id), stdout=out)
        value = out.getvalue()
        self.assertIn("dry run", value)
        self.assertIn("restore book", value)
        # Dry run default: nothing changed.
        self.assertTrue(target.exists())
        row.refresh_from_db()
        self.assertEqual(row.state, FileMove.State.PENDING_DELETION)

    def test_execute_restores(self):
        book, src, target, archive, row = self._moved_book("cmd2.pdf")
        out = StringIO()
        call_command("revert_moves", "--book-id", str(book.id), "--execute", stdout=out)
        self.assertIn("restored 1", out.getvalue())
        self.assertTrue(src.is_file())
        self.assertFalse(target.exists())
