"""Parity tests: the move_approved command and the moves service agree."""

import shutil
import tempfile
from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase

from books.models import FileMove, FinalMetadata
from books.services.moves import dry_run_report, move_status, plan_moves, run_moves
from books.tests.test_helpers import create_test_book_with_file, create_test_scan_folder


class MoveServiceParityTests(TestCase):
    def setUp(self):
        self._temp_dirs = []

    def tearDown(self):
        for d in self._temp_dirs:
            shutil.rmtree(d, ignore_errors=True)

    def _new_folder(self):
        temp_dir = tempfile.mkdtemp()
        self._temp_dirs.append(temp_dir)
        scan_folder = create_test_scan_folder(temp_dir=temp_dir)
        return temp_dir, scan_folder

    def _make_book(self, temp_dir, scan_folder, name, language="en", content_type="ebook"):
        path = Path(temp_dir) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"%PDF-1.4 fake pdf " + name.encode())
        book = create_test_book_with_file(
            file_path=str(path),
            file_format="pdf",
            scan_folder=scan_folder,
            content_type=content_type,
        )
        cover = Path(temp_dir) / "_default_cover.jpg"
        if not cover.exists():
            cover.write_bytes(b"\xff\xd8\xff\xd9")
        FinalMetadata.objects.create(
            book=book,
            final_title=Path(name).stem,
            is_reviewed=True,
            language=language,
            final_cover_path=str(cover),
        )
        return book, path

    def _command(self, **options):
        out = StringIO()
        call_command("move_approved", stdout=out, **options)
        return out.getvalue()

    def test_command_and_service_plan_agree(self):
        temp_dir, scan_folder = self._new_folder()
        book, path = self._make_book(temp_dir, scan_folder, "parity.pdf", language="en")
        target = str(Path(temp_dir) / "Approved" / "parity.pdf")

        out = self._command(folder_pattern="Approved", filename_pattern="${title}.${ext}")
        self.assertEqual(out, f"{book.id} | en | {path} -> {target}\nplanned 1, skipped 0\n")

        plan = plan_moves(folder_pattern="Approved", filename_pattern="${title}.${ext}")
        report = dry_run_report(plan)
        self.assertEqual(len(report["planned"]), 1)
        entry = report["planned"][0]
        self.assertEqual(
            (entry["id"], entry["language"], entry["source"], entry["target"]),
            (book.id, "en", str(path), target),
        )
        self.assertEqual(report["skipped"], [])

    def test_command_and_service_move_rows_and_counts_agree(self):
        # Command path, isolated in its own scan folder.
        cmd_dir, cmd_folder = self._new_folder()
        cmd_book, _ = self._make_book(cmd_dir, cmd_folder, "cmd.pdf")
        out = self._command(
            scan_folder=cmd_folder.path, execute=True,
            folder_pattern="Approved", filename_pattern="${title}.${ext}",
        )
        cmd_rows = list(
            FileMove.objects.filter(book=cmd_book).order_by("pk").values_list(
                "state", "source_path", "target_path", "batch_id"
            )
        )
        cmd_summary = out.splitlines()[-1]

        # Service path, isolated in its own scan folder.
        svc_dir, svc_folder = self._new_folder()
        svc_book, _ = self._make_book(svc_dir, svc_folder, "svc.pdf")
        plan = plan_moves(
            scan_folder=svc_folder.path,
            folder_pattern="Approved", filename_pattern="${title}.${ext}",
        )
        result = run_moves(plan, folder_pattern="Approved", filename_pattern="${title}.${ext}")
        svc_rows = list(
            FileMove.objects.filter(book=svc_book).order_by("pk").values_list(
                "state", "source_path", "target_path", "batch_id"
            )
        )

        # Same counts.
        self.assertEqual(
            cmd_summary,
            f"moved {result['moved']}, needs_review {result['needs_review']}, "
            f"failed {result['failed']}, skipped {result['skipped']}",
        )
        # Same FileMove state sequence and batch-id tagging.
        self.assertEqual([r[0] for r in cmd_rows], [r[0] for r in svc_rows])
        self.assertTrue(all(r[3] for r in cmd_rows))
        self.assertTrue(all(r[3] for r in svc_rows))
        # Same source -> target transformation (basename preserved).
        self.assertEqual(Path(cmd_rows[0][2]).name, "cmd.pdf")
        self.assertEqual(Path(svc_rows[0][2]).name, "svc.pdf")

    def test_rolled_back_main_row_is_planned_again(self):
        temp_dir, scan_folder = self._new_folder()
        book, path = self._make_book(temp_dir, scan_folder, "rb.pdf")
        FileMove.objects.create(
            book=book,
            kind=FileMove.Kind.MAIN,
            db_field=FileMove.DBField.FILE_PATH,
            source_path=book.file_path,
            target_path=str(Path(temp_dir) / "x" / "rb.pdf"),
            state=FileMove.State.ROLLED_BACK,
        )
        plan = plan_moves(folder_pattern="Approved", filename_pattern="${title}.${ext}")
        self.assertEqual(len(plan["planned"]), 1)
        self.assertEqual(plan["planned"][0]["id"], book.id)
        self.assertEqual(plan["skipped"], [])


class MoveStatusTests(TestCase):
    def _row(self, state, **kwargs):
        return FileMove.objects.create(
            kind=FileMove.Kind.MAIN,
            db_field=FileMove.DBField.FILE_PATH,
            source_path="/tmp/mv/book.pdf",
            target_path="/tmp/mv/out/book.pdf",
            state=state,
            **kwargs,
        )

    def test_counts_cover_every_state(self):
        states = [s[0] for s in FileMove.State.choices]
        for state in states:
            self._row(state)
        status = move_status()
        self.assertEqual(set(status["counts_per_state"]), set(states))
        for state in states:
            self.assertEqual(status["counts_per_state"][state], 1)

    def test_counts_per_batch(self):
        self._row(FileMove.State.PLANNED, batch_id="b1")
        self._row(FileMove.State.PLANNED, batch_id="b1")
        self._row(FileMove.State.PLANNED, batch_id="b2")
        self._row(FileMove.State.PLANNED, batch_id="")
        status = move_status()
        self.assertEqual(status["counts_per_batch"], {"b1": 2, "b2": 1})

    def test_review_rows_have_error_and_flags(self):
        nr = self._row(FileMove.State.NEEDS_REVIEW, error="", review_flags=["cover-missing"])
        fl = self._row(FileMove.State.FAILED, error="boom", review_flags=[])
        self._row(FileMove.State.PLANNED)  # not a review row
        status = move_status()
        by_id = {r["id"]: r for r in status["review_rows"]}
        self.assertEqual(set(by_id), {nr.id, fl.id})
        self.assertEqual(by_id[nr.id]["review_flags"], ["cover-missing"])
        self.assertEqual(by_id[nr.id]["error"], "")
        self.assertEqual(by_id[fl.id]["error"], "boom")

    def test_completed_rows_latest_first(self):
        older = self._row(FileMove.State.PURGED)
        newer = self._row(FileMove.State.PENDING_DELETION)
        self._row(FileMove.State.PLANNED)  # not completed
        status = move_status()
        self.assertEqual([r["id"] for r in status["completed_rows"]], [newer.id, older.id])

    def test_writes_nothing(self):
        for state in (FileMove.State.PLANNED, FileMove.State.NEEDS_REVIEW, FileMove.State.PURGED):
            self._row(state)
        before = list(FileMove.objects.order_by("pk").values_list("id", "state", "error", "review_flags"))
        move_status()
        after = list(FileMove.objects.order_by("pk").values_list("id", "state", "error", "review_flags"))
        self.assertEqual(after, before)
