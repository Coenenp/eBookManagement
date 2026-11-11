"""Tests for the move_approved management command."""

import shutil
import tempfile
from io import StringIO
from pathlib import Path
from unittest import mock

from django.core.management import call_command
from django.test import TestCase

from books.models import BookFile, FileMove, FinalMetadata
from books.tests.test_helpers import create_test_book_with_file, create_test_scan_folder


class MoveApprovedCommandTests(TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(self.temp_dir, ignore_errors=True))
        self.scan_folder = create_test_scan_folder(temp_dir=self.temp_dir)

    def _make_book(self, name, language="en", is_reviewed=True, series="", series_number=None, content_type="ebook"):
        path = Path(self.temp_dir) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"%PDF-1.4 fake pdf")
        book = create_test_book_with_file(
            file_path=str(path),
            file_format="pdf",
            scan_folder=self.scan_folder,
            content_type=content_type,
        )
        FinalMetadata.objects.create(
            book=book,
            final_title=Path(name).stem,
            is_reviewed=is_reviewed,
            language=language,
            final_series=series,
            final_series_number=series_number,
        )
        return book, path

    def _run(self, **options):
        out = StringIO()
        call_command("move_approved", stdout=out, **options)
        return out.getvalue()

    def test_default_is_dry_run_and_nothing_moves(self):
        book, path = self._make_book("d.pdf")
        out = self._run()
        self.assertTrue(path.exists())  # nothing moved
        self.assertIn("planned 1", out)
        self.assertIn(f"{book.id} |", out)

    def test_execute_moves_approved_and_tags_batch_id(self):
        book, path = self._make_book("m.pdf")
        out = self._run(execute=True, folder_pattern="Approved", filename_pattern="${title}.${ext}")
        self.assertFalse(path.exists())  # moved
        self.assertTrue((Path(self.temp_dir) / "Approved" / "m.pdf").exists())
        self.assertIn("moved 1", out)
        row = FileMove.objects.get(book=book, kind=FileMove.Kind.MAIN)
        self.assertTrue(row.batch_id)

    def test_unapproved_not_listed_nor_moved(self):
        book, path = self._make_book("u.pdf", is_reviewed=False)
        out = self._run(execute=True, folder_pattern="Approved", filename_pattern="${title}.${ext}")
        self.assertTrue(path.exists())  # not moved
        self.assertNotIn(f"{book.id} |", out)
        self.assertIn("moved 0", out)

    def test_limit(self):
        b1, _ = self._make_book("b1.pdf")
        b2, _ = self._make_book("b2.pdf")
        b3, _ = self._make_book("b3.pdf")
        out = self._run(limit=2)
        self.assertIn("planned 2, skipped 0", out)
        self.assertIn(f"{b1.id} |", out)
        self.assertIn(f"{b2.id} |", out)
        self.assertNotIn(f"{b3.id} |", out)

    def test_ordering_known_language_before_und_and_empty(self):
        known, _ = self._make_book("known.pdf", language="en")
        und, _ = self._make_book("und.pdf", language="und")
        empty, _ = self._make_book("empty.pdf", language="")
        out = self._run()
        plan_lines = [
            l for l in out.splitlines()
            if l.split("|")[0].strip() in {str(known.id), str(und.id), str(empty.id)}
        ]
        ids = [int(l.split("|")[0].strip()) for l in plan_lines]
        self.assertEqual(ids, [known.id, und.id, empty.id])

    def test_language_filter(self):
        en_book, _ = self._make_book("en.pdf", language="en")
        nl_book, _ = self._make_book("nl.pdf", language="nl")
        out = self._run(language="en", folder_pattern="Approved", filename_pattern="${title}.${ext}")
        self.assertIn(f"{en_book.id} |", out)
        self.assertNotIn(f"{nl_book.id} |", out)

    def test_planned_filemove_skipped_and_listed(self):
        book, path = self._make_book("p.pdf")
        FileMove.objects.create(
            book=book,
            kind=FileMove.Kind.MAIN,
            db_field=FileMove.DBField.FILE_PATH,
            source_path=book.file_path,
            target_path=str(Path(self.temp_dir) / "elsewhere" / "p.pdf"),
            state=FileMove.State.PLANNED,
        )
        out = self._run()
        self.assertIn(f"skipped {book.id}", out)
        self.assertIn("planned 0, skipped 1", out)
        self.assertTrue(path.exists())

    def test_becomes_unapproved_between_selection_and_move(self):
        book, path = self._make_book("ba.pdf")
        with mock.patch(
            "books.management.commands.move_approved.is_renamable",
            side_effect=[True, False],
        ):
            out = self._run(execute=True, folder_pattern="Approved", filename_pattern="${title}.${ext}")
        self.assertTrue(path.exists())  # not moved
        self.assertIn(f"skipped {book.id}", out)

    def test_one_failing_book_does_not_stop_run(self):
        good, good_path = self._make_book("a-good.pdf")
        bad, bad_path = self._make_book("a-bad.pdf")
        bad_path.unlink()  # missing source -> safe_move_book raises
        out = self._run(execute=True, folder_pattern="Approved", filename_pattern="${title}.${ext}")
        self.assertFalse(good_path.exists())
        self.assertTrue((Path(self.temp_dir) / "Approved" / "a-good.pdf").exists())
        self.assertIn("moved 1", out)
        self.assertIn("failed 1", out)
