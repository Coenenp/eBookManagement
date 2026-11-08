"""Tests for the recovery resolver, the purge command, and the archive guards.

Item 4 (``resolve_move``) is tested one test per table row, plus the
``recover_file_moves`` command's dry-run/apply behaviour. Item 5 covers
``purge_pending_deletions`` (dry run, count mismatch, success, changed target,
missing archive). Item 6 covers the ``ScanFolder.clean`` archive guard and the
scanner's ``_collect_files`` directory skip.
"""

import hashlib
import io
import shutil
import tempfile
from pathlib import Path
from unittest import mock

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from books.models import Book, BookFile, FileMove, FinalMetadata, ScanFolder
from books.scanner.folder import _collect_files
from books.utils.safe_move.archive import ARCHIVE_FOLDER_NAME, default_archive_root
from books.utils.safe_move.recovery import resolve_move


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _book_with_file(scan_folder, file_path):
    """Create a Book + BookFile whose primary file is ``file_path``."""
    book = Book.objects.create(content_type="ebook", scan_folder=scan_folder)
    BookFile.objects.create(book=book, file_path=str(file_path), file_format="txt")
    return book


class ResolverTests(TestCase):
    """Item 4: ``resolve_move`` per table row."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, str(self.root), ignore_errors=True)
        self.scan_root = self.root / "lib"
        self.scan_root.mkdir()
        self.archive_root = self.root / "Archive [To Delete]"
        self.scan_folder = ScanFolder.objects.create(
            path=str(self.scan_root), name="Sample [To Delete]", content_type="ebooks", is_active=True,
        )

    def _row(self, state, source, target, archive=None, *, original=None, archived=None, new=None, tmp=None,
             book_file_path=None, previous_paths=None):
        book = _book_with_file(self.scan_folder, book_file_path or source)
        if previous_paths is None:
            previous_paths = {"file_path": str(source), "cover_path": "", "opf_path": "", "final_path": ""}
        return FileMove.objects.create(
            book=book,
            source_path=str(source),
            target_path=str(target),
            archived_path=str(archive) if archive else "",
            tmp_path=str(tmp) if tmp else "",
            state=state,
            original_sha256=original or "",
            archived_sha256=archived or "",
            new_sha256=new or "",
            previous_paths=previous_paths,
        )

    def test_resolve_planned_like_states(self):
        for state in (FileMove.State.PLANNED, FileMove.State.TMP_WRITTEN, FileMove.State.TMP_VERIFIED):
            with self.subTest(state=state):
                tmp = self.root / "book.txt.moving"
                tmp.write_bytes(b"x")
                row = self._row(state, self.scan_root / "book.txt", self.root / "Moved" / "book.txt", tmp=tmp)
                self.assertEqual(resolve_move(row), "rolled_back")
                row.refresh_from_db()
                self.assertEqual(row.state, FileMove.State.ROLLED_BACK)
                self.assertFalse(tmp.exists())

    def test_resolve_archived_removes_archive_only_when_hash_matches(self):
        src = self.scan_root / "book.txt"
        src.write_bytes(b"data")
        archive = self.archive_root / "Sample [To Delete] 1" / "book.txt"
        archive.parent.mkdir(parents=True, exist_ok=True)
        archive.write_bytes(b"data")
        tmp = self.root / "book.txt.moving"
        tmp.write_bytes(b"x")

        row = self._row(FileMove.State.ARCHIVED, src, self.root / "Moved" / "book.txt",
                        archive=archive, original=_sha256(src), archived=_sha256(src), tmp=tmp)
        self.assertEqual(resolve_move(row), "rolled_back")
        row.refresh_from_db()
        self.assertEqual(row.state, FileMove.State.ROLLED_BACK)
        self.assertFalse(tmp.exists())
        self.assertFalse(archive.exists())
        self.assertTrue(src.exists())

    def test_resolve_archived_keeps_archive_when_hash_differs(self):
        src = self.scan_root / "book.txt"
        src.write_bytes(b"data")
        archive = self.archive_root / "Sample [To Delete] 1" / "book.txt"
        archive.parent.mkdir(parents=True, exist_ok=True)
        archive.write_bytes(b"other file, do not delete")
        row = self._row(FileMove.State.ARCHIVED, src, self.root / "Moved" / "book.txt",
                        archive=archive, original=_sha256(src), archived=_sha256(src))
        self.assertEqual(resolve_move(row), "rolled_back")
        self.assertTrue(archive.exists())  # hash differs -> never deleted
        self.assertTrue(src.exists())

    def test_resolve_committed_removes_target_and_archive(self):
        src = self.scan_root / "book.txt"
        src.write_bytes(b"data")
        target = self.root / "Moved" / "book.txt"
        target.parent.mkdir(parents=True)
        target.write_bytes(b"data")
        archive = self.archive_root / "Sample [To Delete] 1" / "book.txt"
        archive.parent.mkdir(parents=True, exist_ok=True)
        archive.write_bytes(b"data")
        # DB still points at the old source.
        row = self._row(FileMove.State.COMMITTED, src, target, archive=archive,
                        original=_sha256(src), archived=_sha256(src), book_file_path=str(src))
        self.assertEqual(resolve_move(row), "rolled_back")
        row.refresh_from_db()
        self.assertEqual(row.state, FileMove.State.ROLLED_BACK)
        self.assertFalse(target.exists())
        self.assertFalse(archive.exists())
        self.assertTrue(src.exists())

    def test_resolve_db_updated_finalizes(self):
        src = self.scan_root / "book.txt"
        src.write_bytes(b"data")
        target = self.root / "Moved" / "book.txt"
        target.parent.mkdir(parents=True)
        target.write_bytes(b"data")
        archive = self.archive_root / "Sample [To Delete] 1" / "book.txt"
        archive.parent.mkdir(parents=True, exist_ok=True)
        archive.write_bytes(b"data")
        h = _sha256(src)
        row = self._row(FileMove.State.DB_UPDATED, src, target, archive=archive,
                        original=h, archived=h, new=h, book_file_path=str(target))
        self.assertEqual(resolve_move(row), "finalized")
        row.refresh_from_db()
        self.assertEqual(row.state, FileMove.State.PENDING_DELETION)
        self.assertFalse(src.exists())  # source deleted only after finalize
        self.assertTrue(target.exists())
        self.assertTrue(archive.exists())

    def test_resolve_db_updated_reverts_on_check_c_failure(self):
        src = self.scan_root / "book.txt"
        src.write_bytes(b"data")
        target = self.root / "Moved" / "book.txt"
        target.parent.mkdir(parents=True)
        target.write_bytes(b"different data")  # target no longer matches
        archive = self.archive_root / "Sample [To Delete] 1" / "book.txt"
        archive.parent.mkdir(parents=True, exist_ok=True)
        archive.write_bytes(b"data")
        h = _sha256(src)
        row = self._row(FileMove.State.DB_UPDATED, src, target, archive=archive,
                        original=h, archived=h, new=h, book_file_path=str(target))
        self.assertEqual(resolve_move(row), "rolled_back")
        row.refresh_from_db()
        self.assertEqual(row.state, FileMove.State.ROLLED_BACK)
        self.assertTrue(src.exists())
        self.assertFalse(target.exists())
        self.assertFalse(archive.exists())
        # DB reverted to the source.
        self.assertEqual(BookFile.objects.get(book=row.book).file_path, str(src))

    def test_recover_command_dry_run_then_apply(self):
        tmp = self.root / "book.txt.moving"
        tmp.write_bytes(b"x")
        row = self._row(FileMove.State.PLANNED, self.scan_root / "book.txt",
                        self.root / "Moved" / "book.txt", tmp=tmp)
        out = io.StringIO()
        call_command("recover_file_moves", stdout=out)
        row.refresh_from_db()
        self.assertEqual(row.state, FileMove.State.PLANNED)  # dry run: nothing applied
        self.assertTrue(tmp.exists())
        self.assertIn("dry run", out.getvalue())

        out = io.StringIO()
        call_command("recover_file_moves", "--apply", stdout=out)
        row.refresh_from_db()
        self.assertEqual(row.state, FileMove.State.ROLLED_BACK)
        self.assertFalse(tmp.exists())
        self.assertIn("rolled_back", out.getvalue())

    # -- resolve_move gap (a): archived with a target already committed -------

    def test_resolve_archived_removes_target_when_committed_not_advanced(self):
        src = self.scan_root / "book.txt"
        src.write_bytes(b"data")
        target = self.root / "Moved" / "book.txt"
        target.parent.mkdir(parents=True)
        target.write_bytes(b"data")  # os.replace already happened
        archive = self.archive_root / "Sample [To Delete] 1" / "book.txt"
        archive.parent.mkdir(parents=True, exist_ok=True)
        archive.write_bytes(b"data")
        h = _sha256(src)
        row = self._row(FileMove.State.ARCHIVED, src, target, archive=archive,
                        original=h, archived=h, new=h, book_file_path=str(src))
        self.assertEqual(resolve_move(row), "rolled_back")
        row.refresh_from_db()
        self.assertEqual(row.state, FileMove.State.ROLLED_BACK)
        self.assertFalse(target.exists())
        self.assertFalse(archive.exists())
        self.assertTrue(src.exists())

    # -- resolve_move gap (b): planned-like states remove a matching archive --

    def test_resolve_planned_like_states_remove_matching_archive(self):
        for state in (FileMove.State.PLANNED, FileMove.State.TMP_WRITTEN, FileMove.State.TMP_VERIFIED):
            with self.subTest(state=state):
                src = self.scan_root / "book.txt"
                src.write_bytes(b"data")
                archive = self.archive_root / "Sample [To Delete] 1" / "book.txt"
                archive.parent.mkdir(parents=True, exist_ok=True)
                archive.write_bytes(b"data")
                row = self._row(state, src, self.root / "Moved" / "book.txt",
                                archive=archive, original=_sha256(src))
                self.assertEqual(resolve_move(row), "rolled_back")
                self.assertFalse(archive.exists())
                self.assertTrue(src.exists())

    # -- resolve_move gap (c): db_updated with the source already gone --------

    def test_resolve_db_updated_source_gone_finalizes(self):
        src = self.scan_root / "book.txt"  # never written -> already gone
        target = self.root / "Moved" / "book.txt"
        target.parent.mkdir(parents=True)
        target.write_bytes(b"data")
        archive = self.archive_root / "Sample [To Delete] 1" / "book.txt"
        archive.parent.mkdir(parents=True, exist_ok=True)
        archive.write_bytes(b"data")
        h = _sha256(target)
        row = self._row(FileMove.State.DB_UPDATED, src, target, archive=archive,
                        original=h, archived=h, new=h, book_file_path=str(target))
        self.assertFalse(src.exists())
        self.assertEqual(resolve_move(row), "finalized")
        row.refresh_from_db()
        self.assertEqual(row.state, FileMove.State.PENDING_DELETION)
        self.assertTrue(target.exists())
        self.assertTrue(archive.exists())

    def test_resolve_db_updated_source_gone_archive_missing_fails(self):
        src = self.scan_root / "book.txt"  # never written -> already gone
        target = self.root / "Moved" / "book.txt"
        target.parent.mkdir(parents=True)
        target.write_bytes(b"data")
        archive = self.archive_root / "Sample [To Delete] 1" / "book.txt"  # not created
        h = _sha256(target)
        row = self._row(FileMove.State.DB_UPDATED, src, target, archive=archive,
                        original=h, archived=h, new=h, book_file_path=str(target))
        self.assertEqual(resolve_move(row), "failed")
        row.refresh_from_db()
        self.assertEqual(row.state, FileMove.State.FAILED)
        self.assertEqual(row.error, "archive-missing-after-source-removed")
        self.assertTrue(target.exists())  # nothing deleted

    # -- negative deletion paths: a hash disagreeing with the journal must -----
    # -- keep every file and end the row failed, never delete. ------------------

    def test_resolve_archived_target_hash_differs_keeps_everything_fails(self):
        src = self.scan_root / "book.txt"
        src.write_bytes(b"data")
        target = self.root / "Moved" / "book.txt"
        target.parent.mkdir(parents=True)
        target.write_bytes(b"tampered")  # hash differs from the journal's new_sha256
        archive = self.archive_root / "Sample [To Delete] 1" / "book.txt"
        archive.parent.mkdir(parents=True, exist_ok=True)
        archive.write_bytes(b"data")
        h = _sha256(src)
        row = self._row(FileMove.State.ARCHIVED, src, target, archive=archive,
                        original=h, archived=h, new=h, book_file_path=str(src))
        self.assertEqual(resolve_move(row), "failed")
        row.refresh_from_db()
        self.assertEqual(row.state, FileMove.State.FAILED)
        self.assertTrue(row.error)
        self.assertTrue(target.exists())   # kept (hash disagrees -> never delete)
        self.assertTrue(src.exists())      # kept
        self.assertTrue(archive.exists())  # kept

    def test_resolve_planned_like_states_keep_archive_when_source_missing(self):
        for state in (FileMove.State.PLANNED, FileMove.State.TMP_WRITTEN, FileMove.State.TMP_VERIFIED):
            with self.subTest(state=state):
                src = self.scan_root / "book.txt"  # never written -> source missing
                archive = self.archive_root / "Sample [To Delete] 1" / "book.txt"
                archive.parent.mkdir(parents=True, exist_ok=True)
                archive.write_bytes(b"data")
                h = _sha256(archive)
                row = self._row(state, src, self.root / "Moved" / "book.txt",
                                archive=archive, original=h)
                self.assertEqual(resolve_move(row), "failed")
                row.refresh_from_db()
                self.assertEqual(row.state, FileMove.State.FAILED)
                self.assertTrue(row.error)
                self.assertTrue(archive.exists())  # never deleted

    def test_resolve_planned_like_states_keep_archive_when_source_changed(self):
        for state in (FileMove.State.PLANNED, FileMove.State.TMP_WRITTEN, FileMove.State.TMP_VERIFIED):
            with self.subTest(state=state):
                src = self.scan_root / "book.txt"
                src.write_bytes(b"changed source")  # hash differs from original_sha256
                archive = self.archive_root / "Sample [To Delete] 1" / "book.txt"
                archive.parent.mkdir(parents=True, exist_ok=True)
                archive.write_bytes(b"data")
                original_h = _sha256(archive)  # journal says the original was "data"
                row = self._row(state, src, self.root / "Moved" / "book.txt",
                                archive=archive, original=original_h)
                self.assertEqual(resolve_move(row), "failed")
                row.refresh_from_db()
                self.assertEqual(row.state, FileMove.State.FAILED)
                self.assertTrue(row.error)
                self.assertTrue(archive.exists())  # never deleted
                self.assertTrue(src.exists())

    def test_resolve_planned_like_states_keep_archive_when_archive_differs(self):
        for state in (FileMove.State.PLANNED, FileMove.State.TMP_WRITTEN, FileMove.State.TMP_VERIFIED):
            with self.subTest(state=state):
                src = self.scan_root / "book.txt"
                src.write_bytes(b"data")
                archive = self.archive_root / "Sample [To Delete] 1" / "book.txt"
                archive.parent.mkdir(parents=True, exist_ok=True)
                archive.write_bytes(b"other file, do not delete")  # hash differs
                h = _sha256(src)
                row = self._row(state, src, self.root / "Moved" / "book.txt",
                                archive=archive, original=h)
                self.assertEqual(resolve_move(row), "failed")
                row.refresh_from_db()
                self.assertEqual(row.state, FileMove.State.FAILED)
                self.assertTrue(row.error)
                self.assertTrue(archive.exists())  # never deleted
                self.assertTrue(src.exists())

    def test_resolve_db_updated_source_gone_target_hash_differs_fails(self):
        src = self.scan_root / "book.txt"  # never written -> already gone
        target = self.root / "Moved" / "book.txt"
        target.parent.mkdir(parents=True)
        target.write_bytes(b"tampered")  # hash differs from new_sha256
        archive = self.archive_root / "Sample [To Delete] 1" / "book.txt"
        archive.parent.mkdir(parents=True, exist_ok=True)
        archive.write_bytes(b"data")
        h = _sha256(archive)
        row = self._row(FileMove.State.DB_UPDATED, src, target, archive=archive,
                        original=h, archived=h, new=h, book_file_path=str(target))
        self.assertEqual(resolve_move(row), "failed")
        row.refresh_from_db()
        self.assertEqual(row.state, FileMove.State.FAILED)
        self.assertTrue(row.error)
        self.assertTrue(target.exists())   # kept (hash disagrees)
        self.assertTrue(archive.exists())  # kept

    def test_resolve_db_updated_source_gone_archive_hash_differs_fails(self):
        src = self.scan_root / "book.txt"  # never written -> already gone
        target = self.root / "Moved" / "book.txt"
        target.parent.mkdir(parents=True)
        target.write_bytes(b"data")
        archive = self.archive_root / "Sample [To Delete] 1" / "book.txt"
        archive.parent.mkdir(parents=True, exist_ok=True)
        archive.write_bytes(b"other file")  # hash differs from archived_sha256
        h = _sha256(target)
        row = self._row(FileMove.State.DB_UPDATED, src, target, archive=archive,
                        original=h, archived=h, new=h, book_file_path=str(target))
        self.assertEqual(resolve_move(row), "failed")
        row.refresh_from_db()
        self.assertEqual(row.state, FileMove.State.FAILED)
        self.assertTrue(row.error)
        self.assertTrue(target.exists())   # kept
        self.assertTrue(archive.exists())  # kept (hash disagrees)

    # -- child (companion) rows recover against db_field ----------------------

    def _child_row(self, state, source, target, *, db_field=FileMove.DBField.COVER_PATH,
                   archive=None, original=None, new=None, cover_path=None):
        book = _book_with_file(self.scan_folder, str(self.scan_root / "book.txt"))
        bf = BookFile.objects.get(book=book)
        bf.cover_path = cover_path if cover_path is not None else str(source)
        bf.save(update_fields=["cover_path"])
        return FileMove.objects.create(
            book=book, kind=FileMove.Kind.COMPANION, db_field=db_field,
            source_path=str(source), target_path=str(target),
            archived_path=str(archive) if archive else "",
            tmp_path="", state=state,
            original_sha256=original or "",
            archived_sha256=original or "",
            new_sha256=new or "",
            previous_paths={db_field: str(source)},
        )

    def test_resolve_child_db_updated_finalizes_via_cover_path(self):
        src = self.scan_root / "cover.jpg"
        src.write_bytes(b"img")
        target = self.root / "Moved" / "book.jpg"
        target.parent.mkdir(parents=True)
        target.write_bytes(b"img")
        archive = self.archive_root / "Sample [To Delete] 1" / "cover.jpg"
        archive.parent.mkdir(parents=True, exist_ok=True)
        archive.write_bytes(b"img")
        h = _sha256(src)
        row = self._child_row(FileMove.State.DB_UPDATED, src, target,
                              archive=archive, original=h, new=h, cover_path=str(target))
        self.assertEqual(resolve_move(row), "finalized")
        row.refresh_from_db()
        self.assertEqual(row.state, FileMove.State.PENDING_DELETION)
        self.assertFalse(src.exists())

    def test_resolve_child_committed_rolls_back_when_cover_not_pointing(self):
        src = self.scan_root / "cover.jpg"
        src.write_bytes(b"img")
        target = self.root / "Moved" / "book.jpg"
        target.parent.mkdir(parents=True)
        target.write_bytes(b"img")
        archive = self.archive_root / "Sample [To Delete] 1" / "cover.jpg"
        archive.parent.mkdir(parents=True, exist_ok=True)
        archive.write_bytes(b"img")
        h = _sha256(src)
        # cover_path still points at the source, not the target.
        row = self._child_row(FileMove.State.COMMITTED, src, target,
                              archive=archive, original=h, new=h, cover_path=str(src))
        self.assertEqual(resolve_move(row), "rolled_back")
        self.assertFalse(target.exists())
        self.assertFalse(archive.exists())
        self.assertTrue(src.exists())

    def test_resolve_child_planned_like_states_remove_archive(self):
        for state in (FileMove.State.PLANNED, FileMove.State.TMP_WRITTEN, FileMove.State.TMP_VERIFIED,
                      FileMove.State.ARCHIVED):
            with self.subTest(state=state):
                src = self.scan_root / "cover.jpg"
                src.write_bytes(b"img")
                archive = self.archive_root / "Sample [To Delete] 1" / "cover.jpg"
                archive.parent.mkdir(parents=True, exist_ok=True)
                archive.write_bytes(b"img")
                row = self._child_row(state, src, self.root / "Moved" / "book.jpg",
                                      archive=archive, original=_sha256(src))
                self.assertEqual(resolve_move(row), "rolled_back")
                self.assertFalse(archive.exists())
                self.assertTrue(src.exists())

    # -- sidecar (blank db_field) recovery ----------------------------------

    def _sidecar_row(self, state, source, target, *, archive=None, original=None,
                     archived=None, new=None, tmp=None):
        book = _book_with_file(self.scan_folder, str(self.scan_root / "book.txt"))
        return FileMove.objects.create(
            book=book, kind=FileMove.Kind.COMPANION, db_field="",
            source_path=str(source), target_path=str(target),
            archived_path=str(archive) if archive else "",
            tmp_path=str(tmp) if tmp else "", state=state,
            original_sha256=original or "", archived_sha256=archived or "", new_sha256=new or "",
            previous_paths={},
        )

    def test_resolve_sidecar_committed_archived_rolls_back(self):
        for state in (FileMove.State.COMMITTED, FileMove.State.ARCHIVED):
            with self.subTest(state=state):
                src = self.scan_root / "book.txt"
                src.write_bytes(b"data")
                target = self.root / "Moved" / "book.txt"
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(b"data")
                archive = self.archive_root / "Sample [To Delete] 1" / "book.txt"
                archive.parent.mkdir(parents=True, exist_ok=True)
                archive.write_bytes(b"data")
                h = _sha256(src)
                row = self._sidecar_row(state, src, target, archive=archive,
                                        original=h, archived=h, new=h)
                self.assertEqual(resolve_move(row), "rolled_back")
                row.refresh_from_db()
                self.assertEqual(row.state, FileMove.State.ROLLED_BACK)
                self.assertFalse(target.exists())
                self.assertFalse(archive.exists())
                self.assertTrue(src.exists())

    def test_resolve_sidecar_hash_disagreement_ends_failed(self):
        for state in (FileMove.State.COMMITTED, FileMove.State.ARCHIVED):
            with self.subTest(state=state):
                src = self.scan_root / "book.txt"
                src.write_bytes(b"data")
                target = self.root / "Moved" / "book.txt"
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(b"tampered")  # differs from new_sha256
                archive = self.archive_root / "Sample [To Delete] 1" / "book.txt"
                archive.parent.mkdir(parents=True, exist_ok=True)
                archive.write_bytes(b"data")
                h = _sha256(src)
                row = self._sidecar_row(state, src, target, archive=archive,
                                        original=h, archived=h, new=h)
                self.assertEqual(resolve_move(row), "failed")
                row.refresh_from_db()
                self.assertEqual(row.state, FileMove.State.FAILED)
                self.assertTrue(row.error)
                self.assertTrue(target.exists())
                self.assertTrue(archive.exists())
                self.assertTrue(src.exists())

    # -- apply vs no-apply parity -------------------------------------------

    def _build(self, state, *, kind=FileMove.Kind.MAIN, db_field=FileMove.DBField.FILE_PATH,
               original=None, archived=None, new=None,
               src_exists=True, src_data=b"data",
               tgt_exists=True, tgt_data=b"data",
               arch_exists=True, arch_data=b"data",
               book_file_path=None):
        src = self.scan_root / "book.txt"
        target = self.root / "Moved" / "book.txt"
        archive = self.archive_root / "Sample [To Delete] 1" / "book.txt"

        def _write(p, exists, data):
            p.parent.mkdir(parents=True, exist_ok=True)
            if exists:
                p.write_bytes(data)
            elif p.exists():
                p.unlink()

        _write(src, src_exists, src_data)
        _write(target, tgt_exists, tgt_data)
        _write(archive, arch_exists, arch_data)

        book = _book_with_file(self.scan_folder, book_file_path or str(src))
        return FileMove.objects.create(
            book=book, kind=kind, db_field=db_field,
            source_path=str(src), target_path=str(target),
            archived_path=str(archive) if arch_exists else "",
            tmp_path="", state=state,
            original_sha256=original or "", archived_sha256=archived or "", new_sha256=new or "",
            previous_paths={"file_path": str(src), "cover_path": "", "opf_path": "", "final_path": ""},
        )

    def test_resolve_move_apply_and_no_apply_return_same_verdict(self):
        S = FileMove.State
        H = hashlib.sha256(b"data").hexdigest()
        target = str(self.root / "Moved" / "book.txt")
        source = str(self.scan_root / "book.txt")
        scenarios = [
            ("planned_no_archive", dict(state=S.PLANNED, src_exists=False)),
            ("planned_archive_match", dict(state=S.PLANNED, original=H, archived=H)),
            ("planned_archive_differs", dict(state=S.PLANNED, arch_data=b"other", original=H, archived=H)),
            ("planned_source_missing", dict(state=S.PLANNED, src_exists=False, original=H, archived=H)),
            ("planned_source_changed", dict(state=S.PLANNED, src_data=b"changed", original=H, archived=H)),
            ("archived_target_missing", dict(state=S.ARCHIVED, tgt_exists=False, original=H, archived=H)),
            ("archived_target_match_not_pointing", dict(state=S.ARCHIVED, original=H, archived=H, new=H, book_file_path=source)),
            ("archived_target_mismatch", dict(state=S.ARCHIVED, tgt_data=b"tampered", original=H, archived=H, new=H)),
            ("committed_not_pointing", dict(state=S.COMMITTED, original=H, archived=H, new=H, book_file_path=source)),
            ("committed_pointing", dict(state=S.COMMITTED, original=H, archived=H, new=H, book_file_path=target)),
            ("db_updated_finalize", dict(state=S.DB_UPDATED, original=H, archived=H, new=H, book_file_path=target)),
            ("db_updated_checkc_fail", dict(state=S.DB_UPDATED, tgt_data=b"tampered", original=H, archived=H, new=H, book_file_path=target)),
            ("db_updated_source_gone_finalize", dict(state=S.DB_UPDATED, src_exists=False, original=H, archived=H, new=H, book_file_path=target)),
            ("db_updated_source_gone_archive_missing", dict(state=S.DB_UPDATED, src_exists=False, arch_exists=False, original=H, archived=H, new=H, book_file_path=target)),
            ("db_updated_source_gone_target_mismatch", dict(state=S.DB_UPDATED, src_exists=False, tgt_data=b"tampered", original=H, archived=H, new=H, book_file_path=target)),
            ("sidecar_committed_consistent", dict(state=S.COMMITTED, kind=FileMove.Kind.COMPANION, db_field="", original=H, archived=H, new=H)),
            ("sidecar_archived_target_mismatch", dict(state=S.ARCHIVED, kind=FileMove.Kind.COMPANION, db_field="", tgt_data=b"tampered", original=H, archived=H, new=H)),
        ]
        for name, kwargs in scenarios:
            with self.subTest(scenario=name):
                va = resolve_move(self._build(**kwargs), apply=True)
                vb = resolve_move(self._build(**kwargs), apply=False)
                self.assertEqual(va, vb, f"apply=True -> {va!r}, apply=False -> {vb!r}")


class PurgeCommandTests(TestCase):
    """Item 5: ``purge_pending_deletions``."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, str(self.root), ignore_errors=True)
        self.scan_root = self.root / "lib"
        self.scan_root.mkdir()
        self.archive_root = self.root / "Archive [To Delete]"
        self.scan_folder = ScanFolder.objects.create(
            path=str(self.scan_root), name="Sample [To Delete]", content_type="ebooks", is_active=True,
        )
        self.target_dir = self.root / "Moved"
        self.target_dir.mkdir()

    def _pending_row(self, target_data=b"data", archive_data=b"data", *, archive_exists=True):
        expected = b"data"
        target = self.target_dir / "book.txt"
        target.write_bytes(target_data)
        book = _book_with_file(self.scan_folder, str(target))
        label = f"{self.scan_folder.name} {self.scan_folder.id}"
        archive = self.archive_root / label / "sub" / "book.txt"
        archive.parent.mkdir(parents=True, exist_ok=True)
        if archive_exists:
            archive.write_bytes(archive_data)
        return FileMove.objects.create(
            book=book,
            source_path=str(self.scan_root / "old" / "book.txt"),
            target_path=str(target),
            archived_path=str(archive),
            tmp_path="",
            state=FileMove.State.PENDING_DELETION,
            original_sha256=hashlib.sha256(expected).hexdigest(),
            archived_sha256=_sha256(archive) if archive_exists else "",
            new_sha256=hashlib.sha256(expected).hexdigest(),
        ), target, archive

    def test_dry_run_deletes_nothing(self):
        row, target, archive = self._pending_row()
        out = io.StringIO()
        call_command("purge_pending_deletions", stdout=out)
        self.assertTrue(archive.exists())
        self.assertTrue(target.exists())
        row.refresh_from_db()
        self.assertEqual(row.state, FileMove.State.PENDING_DELETION)
        self.assertIn("no files deleted", out.getvalue())

    def test_count_mismatch_deletes_nothing(self):
        row, target, archive = self._pending_row()
        out = io.StringIO()
        with self.assertRaises(CommandError):
            call_command("purge_pending_deletions", confirm=99, stdout=out)
        self.assertTrue(archive.exists())
        self.assertTrue(target.exists())
        row.refresh_from_db()
        self.assertEqual(row.state, FileMove.State.PENDING_DELETION)

    def test_success_purges_and_prunes_empty_dirs(self):
        row, target, archive = self._pending_row()
        label_dir = archive.parent.parent  # .../Archive [To Delete]/<label>
        out = io.StringIO()
        call_command("purge_pending_deletions", confirm=1, stdout=out)
        self.assertFalse(archive.exists())
        self.assertTrue(target.exists())  # only the archive is deleted
        self.assertFalse(archive.parent.exists())  # empty "sub" pruned
        self.assertFalse(label_dir.exists())  # empty label dir pruned
        self.assertTrue(self.archive_root.exists())  # root never pruned
        row.refresh_from_db()
        self.assertEqual(row.state, FileMove.State.PURGED)
        self.assertIsNotNone(row.purged_at)

    def test_changed_target_demoted_only_on_confirm(self):
        row, target, archive = self._pending_row(target_data=b"changed after commit")
        out = io.StringIO()
        call_command("purge_pending_deletions", stdout=out)  # dry run: no write
        self.assertTrue(archive.exists())  # not purged
        row.refresh_from_db()
        self.assertEqual(row.state, FileMove.State.PENDING_DELETION)
        self.assertIn("target-changed", out.getvalue())
        out = io.StringIO()
        call_command("purge_pending_deletions", confirm=0, stdout=out)
        row.refresh_from_db()
        self.assertEqual(row.state, FileMove.State.FAILED_VERIFICATION)

    def test_missing_archive_demoted_only_on_confirm(self):
        row, target, archive = self._pending_row(archive_exists=False)
        out = io.StringIO()
        call_command("purge_pending_deletions", stdout=out)
        self.assertTrue(target.exists())
        self.assertIn("archive-missing", out.getvalue())
        row.refresh_from_db()
        self.assertEqual(row.state, FileMove.State.PENDING_DELETION)
        out = io.StringIO()
        call_command("purge_pending_deletions", confirm=0, stdout=out)
        row.refresh_from_db()
        self.assertEqual(row.state, FileMove.State.FAILED_VERIFICATION)

    def test_hash_mismatch_demoted_only_on_confirm(self):
        row, target, archive = self._pending_row(archive_data=b"tampered archive")
        out = io.StringIO()
        call_command("purge_pending_deletions", stdout=out)
        row.refresh_from_db()
        self.assertEqual(row.state, FileMove.State.PENDING_DELETION)  # dry run unchanged
        self.assertIn("archive-hash", out.getvalue())
        out = io.StringIO()
        call_command("purge_pending_deletions", confirm=0, stdout=out)
        row.refresh_from_db()
        self.assertEqual(row.state, FileMove.State.FAILED_VERIFICATION)

    def test_unreadable_archive_not_demoted(self):
        row, target, archive = self._pending_row()

        def fake(path):
            if str(path) == str(archive):
                raise OSError("unreadable")
            return _sha256(path)

        with mock.patch("books.management.commands.purge_pending_deletions._sha256", side_effect=fake):
            out = io.StringIO()
            call_command("purge_pending_deletions", confirm=0, stdout=out)
        row.refresh_from_db()
        self.assertEqual(row.state, FileMove.State.PENDING_DELETION)  # not demoted
        self.assertIn("unreadable", out.getvalue())
        self.assertTrue(archive.exists())

    def test_purge_removes_child_archive_copy(self):
        target = self.target_dir / "book.jpg"
        target.write_bytes(b"img")
        book = _book_with_file(self.scan_folder, str(self.target_dir / "book.pdf"))
        bf = BookFile.objects.get(book=book)
        bf.cover_path = str(target)
        bf.save(update_fields=["cover_path"])
        label = f"{self.scan_folder.name} {self.scan_folder.id}"
        archive = self.archive_root / label / "sub" / "cover.jpg"
        archive.parent.mkdir(parents=True, exist_ok=True)
        archive.write_bytes(b"img")
        h = hashlib.sha256(b"img").hexdigest()
        child = FileMove.objects.create(
            book=book, kind=FileMove.Kind.COMPANION, db_field=FileMove.DBField.COVER_PATH,
            source_path=str(self.scan_root / "cover.jpg"),
            target_path=str(target), archived_path=str(archive), tmp_path="",
            state=FileMove.State.PENDING_DELETION,
            original_sha256=h, archived_sha256=h, new_sha256=h,
        )
        out = io.StringIO()
        call_command("purge_pending_deletions", confirm=1, stdout=out)
        self.assertFalse(archive.exists())
        child.refresh_from_db()
        self.assertEqual(child.state, FileMove.State.PURGED)
        self.assertIsNotNone(child.purged_at)


class ArchiveGuardTests(TestCase):
    """Item 6: ``ScanFolder.clean`` guard and ``_collect_files`` skip."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, str(self.root), ignore_errors=True)

    def test_rejects_path_inside_configured_archive_root(self):
        with self.settings(ARCHIVE_ROOT=str(self.root / "archroot")):
            for bad in (str(self.root / "archroot"), str(self.root / "archroot" / "sub")):
                with self.subTest(path=bad):
                    sf = ScanFolder(path=bad, name="x")
                    with self.assertRaises(ValidationError):
                        sf.clean()

    def test_rejects_path_containing_configured_archive_root(self):
        with self.settings(ARCHIVE_ROOT=str(self.root / "archroot")):
            sf = ScanFolder(path=str(self.root), name="x")
            with self.assertRaises(ValidationError):
                sf.clean()

    def test_rejects_default_archive_root_of_existing_folder(self):
        existing = ScanFolder.objects.create(path=str(self.root / "lib"), name="lib", content_type="ebooks")
        default_root = default_archive_root(existing.path)
        sf = ScanFolder(path=str(default_root), name="x")
        with self.assertRaises(ValidationError):
            sf.clean()

    def test_rejects_folder_named_archive(self):
        sf = ScanFolder(path=str(self.root / ARCHIVE_FOLDER_NAME), name="x")
        with self.assertRaises(ValidationError):
            sf.clean()

    def test_collect_files_skips_archive_directory(self):
        normal = self.root / "normal"
        normal.mkdir()
        (normal / "book.epub").write_bytes(b"epub")
        archived = self.root / ARCHIVE_FOLDER_NAME
        archived.mkdir()
        (archived / "hidden.epub").write_bytes(b"epub")
        found, _covers, _opfs = _collect_files(str(self.root), [".epub"], [".jpg"])
        found = [Path(p).name for p in found]
        self.assertIn("book.epub", found)
        self.assertNotIn("hidden.epub", found)
