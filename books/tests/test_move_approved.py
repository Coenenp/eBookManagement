"""Tests for the move_approved management command."""

import os
import shutil
import tempfile
from io import StringIO
from pathlib import Path
from unittest import mock

from django.core.management import call_command
from django.test import TestCase

from books.management.commands.move_approved import fit_path
from books.models import BookFile, FileMove, FinalMetadata
from books.tests.test_helpers import create_test_book_with_file, create_test_scan_folder
from books.utils.safe_move import safe_move_book


class MoveApprovedCommandTests(TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(self.temp_dir, ignore_errors=True))
        self.scan_folder = create_test_scan_folder(temp_dir=self.temp_dir)

    def _make_book(self, name, language="en", is_reviewed=True, series="", series_number=None, content_type="ebook", author=""):
        path = Path(self.temp_dir) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"%PDF-1.4 fake pdf")
        book = create_test_book_with_file(
            file_path=str(path),
            file_format="pdf",
            scan_folder=self.scan_folder,
            content_type=content_type,
        )
        cover = Path(self.temp_dir) / "_default_cover.jpg"
        if not cover.exists():
            cover.write_bytes(b"\xff\xd8\xff\xd9")
        FinalMetadata.objects.create(
            book=book,
            final_title=Path(name).stem,
            is_reviewed=is_reviewed,
            language=language,
            final_series=series,
            final_series_number=series_number,
            final_author=author,
            final_cover_path=str(cover),
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

    def test_target_anchored_at_scan_folder_root(self):
        book, path = self._make_book("sub/s.pdf")
        expected = str(Path(self.temp_dir) / "English" / "Books" / "s.pdf")
        out = self._run(folder_pattern="English/Books", filename_pattern="${title}.${ext}")
        self.assertIn(f"-> {expected}", out)
        out2 = self._run(execute=True, folder_pattern="English/Books", filename_pattern="${title}.${ext}")
        self.assertTrue(Path(expected).exists())
        self.assertFalse(path.exists())

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

    def test_compute_target_failure_marks_failed_and_continues(self):
        from books.management.commands.move_approved import Command

        good, good_path = self._make_book("a-good.pdf")
        bad, bad_path = self._make_book("a-bad.pdf")
        real = Command._compute_target

        def _raise_for_bad(self, book, folder_pattern, filename_pattern):
            if book.finalmetadata.final_title == "a-bad":
                raise RuntimeError("boom")
            return real(self, book, folder_pattern, filename_pattern)

        with mock.patch.object(Command, "_compute_target", _raise_for_bad):
            out = self._run(execute=True, folder_pattern="Approved", filename_pattern="${title}.${ext}")
        self.assertFalse(good_path.exists())
        self.assertTrue((Path(self.temp_dir) / "Approved" / "a-good.pdf").exists())
        self.assertIn("moved 1", out)
        self.assertIn(f"failed {bad.id} |", out)
        self.assertIn("failed 1", out)

    def test_queryset_filters_unreviewed(self):
        unapproved, _ = self._make_book("u.pdf", is_reviewed=False)
        with mock.patch("books.management.commands.move_approved.is_renamable", return_value=True):
            out = self._run(folder_pattern="Approved", filename_pattern="${title}.${ext}")
        self.assertNotIn(f"{unapproved.id} |", out)
        self.assertIn("planned 0", out)

    def test_execute_prints_failed_and_needs_review_lines(self):
        bad, bad_path = self._make_book("a-bad.pdf")
        bad_path.unlink()  # missing source -> failed
        epub_path = Path(self.temp_dir) / "garbage.epub"
        epub_path.write_bytes(b"this is not a zip at all")
        epub_book = create_test_book_with_file(
            file_path=str(epub_path), file_format="epub", scan_folder=self.scan_folder,
        )
        FinalMetadata.objects.create(book=epub_book, final_title="garbage", is_reviewed=True, language="en")
        out = self._run(execute=True, folder_pattern="Approved", filename_pattern="${title}.${ext}")
        self.assertIn(f"failed {bad.id} |", out)
        self.assertIn(f"needs_review {epub_book.id} |", out)

    def test_batch_id_tagged_on_failed_and_needs_review_rows(self):
        bad, bad_path = self._make_book("a-bad.pdf")
        bad_path.unlink()
        epub_path = Path(self.temp_dir) / "garbage.epub"
        epub_path.write_bytes(b"this is not a zip at all")
        epub_book = create_test_book_with_file(
            file_path=str(epub_path), file_format="epub", scan_folder=self.scan_folder,
        )
        FinalMetadata.objects.create(book=epub_book, final_title="garbage", is_reviewed=True, language="en")
        out = self._run(execute=True, folder_pattern="Approved", filename_pattern="${title}.${ext}")
        for book in (bad, epub_book):
            rows = FileMove.objects.filter(book=book)
            self.assertTrue(rows.exists())
            self.assertTrue(all(r.batch_id for r in rows))

    def test_batch_id_tagged_only_on_own_book(self):
        book, path = self._make_book("own.pdf")
        other, _ = self._make_book("other.pdf", is_reviewed=False)
        real = safe_move_book

        def _inject(b, target, cover_path=None):
            FileMove.objects.create(
                book=other, kind=FileMove.Kind.MAIN, db_field=FileMove.DBField.FILE_PATH,
                source_path=str(path), target_path=target, state=FileMove.State.PLANNED,
            )
            return real(b, target, cover_path=cover_path)

        with mock.patch("books.management.commands.move_approved.safe_move_book", side_effect=_inject):
            out = self._run(execute=True, folder_pattern="Approved", filename_pattern="${title}.${ext}")
        injected = FileMove.objects.get(book=other)
        self.assertEqual(injected.batch_id, "")
        own_rows = FileMove.objects.filter(book=book)
        self.assertTrue(all(r.batch_id for r in own_rows))

    def test_skip_book_without_scan_folder(self):
        path = Path(self.temp_dir) / "orphan.pdf"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"%PDF-1.4 fake pdf")
        book = create_test_book_with_file(
            file_path=str(path), file_format="pdf", scan_folder=None, content_type="ebook",
        )
        FinalMetadata.objects.create(book=book, final_title="orphan", is_reviewed=True, language="en")
        out = self._run()
        self.assertIn(f"skipped {book.id} | no scan folder", out)
        self.assertIn("planned 0, skipped 1", out)
        out2 = self._run(execute=True, folder_pattern="Approved", filename_pattern="${title}.${ext}")
        self.assertIn(f"skipped {book.id} | no scan folder", out2)

    def test_execute_skips_when_target_exists(self):
        book, path = self._make_book("c.pdf")
        target = Path(self.temp_dir) / "Approved" / "c.pdf"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"existing")
        out = self._run(execute=True, folder_pattern="Approved", filename_pattern="${title}.${ext}")
        self.assertIn(f"skipped {book.id} | target-exists", out)
        self.assertTrue(path.exists())
        self.assertEqual(target.read_bytes(), b"existing")
        self.assertIn("moved 0", out)

    def test_different_file_same_name_collision_skips_second(self):
        b1, p1 = self._make_book("one/same.pdf")
        b2, p2 = self._make_book("two/same.pdf")
        out = self._run(execute=True, folder_pattern="Approved", filename_pattern="${title}.${ext}")
        target = Path(self.temp_dir) / "Approved" / "same.pdf"
        self.assertTrue(target.exists())
        self.assertIn("moved 1", out)
        self.assertIn("target-exists", out)
        self.assertEqual([p.exists() for p in (p1, p2)].count(True), 1)


    def test_execute_epub_media_relative_cover_embeds_and_lands_beside(self):
        import zipfile

        from django.conf import settings

        from books.tests.test_safe_move_book import _write_epub

        path = Path(self.temp_dir) / "sub" / "book.epub"
        path.parent.mkdir(parents=True, exist_ok=True)
        _write_epub(path)
        book = create_test_book_with_file(
            file_path=str(path), file_format="epub",
            scan_folder=self.scan_folder, content_type="ebook",
        )
        FinalMetadata.objects.create(
            book=book, final_title="book", is_reviewed=True,
            language="en", final_author="Jane Doe",
        )
        media = Path(settings.MEDIA_ROOT) / "cover_cache" / "mv_approved.jpg"
        media.parent.mkdir(parents=True, exist_ok=True)
        media.write_bytes(b"\xff\xd8\xff\xe0CURATED")
        fm = book.finalmetadata
        fm.final_cover_path = "cover_cache/mv_approved.jpg"
        fm.save(update_fields=["final_cover_path"])

        out = self._run(execute=True, folder_pattern="Approved", filename_pattern="${title}.${ext}")
        self.assertIn("moved 1", out)
        target = Path(self.temp_dir) / "Approved" / "book.epub"
        self.assertTrue(target.is_file())
        row = FileMove.objects.get(book=book, kind=FileMove.Kind.MAIN)
        self.assertEqual(row.state, FileMove.State.PENDING_DELETION)
        self.assertNotIn("cover-missing", row.review_flags or [])
        self.assertNotIn("cover-invalid", row.review_flags or [])
        with zipfile.ZipFile(target) as z:
            names = z.namelist()
            cover_name = next(
                n for n in names if n.lower().endswith((".jpg", ".jpeg", ".png"))
            )
            self.assertEqual(z.read(cover_name), media.read_bytes())
        beside = Path(self.temp_dir) / "Approved" / "book.jpg"
        self.assertTrue(beside.is_file())
        self.assertEqual(beside.read_bytes(), media.read_bytes())

    def test_dry_run_reports_cover_missing_skip(self):
        book, path = self._make_book("nocover.pdf")
        book.finalmetadata.final_cover_path = ""
        book.finalmetadata.save(update_fields=["final_cover_path"])
        out = self._run()
        self.assertIn(f"skipped {book.id} | cover-missing", out)
        self.assertTrue(path.exists())  # nothing moved
        self.assertFalse(FileMove.objects.filter(book=book).exists())

    def test_dry_run_reports_target_exists_skip(self):
        book, path = self._make_book("exists.pdf")
        target = Path(self.temp_dir) / "Approved" / "exists.pdf"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"existing")
        out = self._run(folder_pattern="Approved", filename_pattern="${title}.${ext}")
        self.assertIn(f"skipped {book.id} | target-exists", out)
        self.assertTrue(path.exists())  # nothing moved
        self.assertFalse(FileMove.objects.filter(book=book).exists())

    def test_execute_prints_same_skip_reasons_as_dry_run(self):
        b1, p1 = self._make_book("nocover.pdf")
        b1.finalmetadata.final_cover_path = ""
        b1.finalmetadata.save(update_fields=["final_cover_path"])
        b2, p2 = self._make_book("exists.pdf")
        target = Path(self.temp_dir) / "Approved" / "exists.pdf"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"existing")
        dry = self._run(folder_pattern="Approved", filename_pattern="${title}.${ext}")
        exec_out = self._run(
            execute=True, folder_pattern="Approved", filename_pattern="${title}.${ext}"
        )
        self.assertIn(f"skipped {b1.id} | cover-missing", dry)
        self.assertIn(f"skipped {b2.id} | target-exists", dry)
        self.assertIn(f"needs_review {b1.id} | cover-missing", exec_out)
        self.assertIn(f"skipped {b2.id} | target-exists", exec_out)


class FitPathTests(TestCase):
    def test_short_path_unchanged(self):
        p = "/tmp/lib/English/Books/Smith, John/Title.pdf"
        self.assertEqual(fit_path(p), p)

    def test_long_title_shortened(self):
        stem = "T" * 300
        p = f"/tmp/lib/English/Books/Author/{stem}.pdf"
        r = fit_path(p)
        self.assertLessEqual(len(r), 240)
        self.assertTrue(r.endswith(".pdf"))
        kept = os.path.splitext(os.path.basename(r))[0]
        self.assertGreaterEqual(len(kept), 20)
        self.assertLess(len(kept), 300)

    def test_long_author_folder_shortened(self):
        author = "A" * 300
        p = f"/tmp/lib/English/Books/{author}/Title.pdf"
        r = fit_path(p)
        self.assertLessEqual(len(r), 240)
        self.assertTrue(r.endswith("Title.pdf"))

    def test_long_title_and_author(self):
        author = "A" * 200
        stem = "T" * 200
        p = f"/tmp/lib/English/Books/{author}/{stem}.pdf"
        r = fit_path(p)
        self.assertLessEqual(len(r), 240)
        self.assertEqual(fit_path(p), r)  # deterministic

    def test_drive_path_shortens_folders_keeps_root_and_title(self):
        folder = "F" * 300
        p = "Z:\\Books\\" + folder + "\\title.pdf"
        r = fit_path(p)
        self.assertLessEqual(len(r), 240)
        self.assertTrue(r.startswith("Z:\\Books\\"))
        self.assertTrue(r.endswith("\\title.pdf"))
        self.assertEqual(fit_path(p), r)  # deterministic
        for comp in r.split("\\"):
            if comp:
                self.assertFalse(comp.endswith((" ", ".")), comp)

    def test_unc_path_shortens_folders_keeps_root_and_title(self):
        folder = "F" * 300
        p = "\\\\nas\\share\\" + folder + "\\title.pdf"
        r = fit_path(p)
        self.assertLessEqual(len(r), 240)
        self.assertTrue(r.startswith("\\\\nas\\share\\"))
        self.assertTrue(r.endswith("\\title.pdf"))
        self.assertEqual(fit_path(p), r)
        for comp in r.split("\\"):
            if comp:
                self.assertFalse(comp.endswith((" ", ".")), comp)

    def test_no_component_ends_in_space_or_dot(self):
        title = "T" * 240
        p = f"/tmp/lib/Author ./{title}.pdf"
        r = fit_path(p)
        self.assertLessEqual(len(r), 240)
        self.assertTrue(r.startswith("/"))
        self.assertEqual(fit_path(p), r)  # deterministic
        for comp in r.split("/"):
            if comp:
                self.assertFalse(comp.endswith((" ", ".")), comp)


class ApprovedLayoutTests(TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(self.temp_dir, ignore_errors=True))
        self.scan_folder = create_test_scan_folder(temp_dir=self.temp_dir)

    def _make_book(self, name, language="en", series="", series_number=None, content_type="ebook", author=""):
        path = Path(self.temp_dir) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"%PDF-1.4 fake pdf")
        book = create_test_book_with_file(
            file_path=str(path), file_format="pdf", scan_folder=self.scan_folder, content_type=content_type,
        )
        cover = Path(self.temp_dir) / "_default_cover.jpg"
        if not cover.exists():
            cover.write_bytes(b"\xff\xd8\xff\xd9")
        FinalMetadata.objects.create(
            book=book, final_title=Path(name).stem, is_reviewed=True, language=language,
            final_series=series, final_series_number=series_number, final_author=author,
            final_cover_path=str(cover),
        )
        return book

    def _target(self, book):
        out = StringIO()
        call_command("move_approved", stdout=out)
        for line in out.getvalue().splitlines():
            if line.startswith(f"{book.id} |"):
                return line.split(" -> ", 1)[1]
        return None

    def test_ebook_series_target(self):
        book = self._make_book("My Book.pdf", series="The Series", series_number="7", author="John Smith", content_type="ebook")
        expected = str(Path(self.temp_dir) / "English" / "Books" / "Smith, John" / "The Series"
                       / "Smith, John - The Series #07 - My Book.pdf")
        self.assertEqual(self._target(book), expected)

    def test_ebook_standalone_target(self):
        book = self._make_book("Standalone.pdf", author="John Smith", content_type="ebook")
        expected = str(Path(self.temp_dir) / "English" / "Books" / "Smith, John" / "Smith, John - Standalone.pdf")
        self.assertEqual(self._target(book), expected)

    def test_comic_series_target(self):
        book = self._make_book("Issue One.pdf", series="Batman", series_number="3", content_type="comic")
        expected = str(Path(self.temp_dir) / "English" / "Comics" / "Batman" / "Batman #03 - Issue One.pdf")
        self.assertEqual(self._target(book), expected)

    def test_comic_standalone_target(self):
        book = self._make_book("Solo.pdf", content_type="comic")
        expected = str(Path(self.temp_dir) / "English" / "Comics" / "Solo" / "Solo.pdf")
        self.assertEqual(self._target(book), expected)

    def test_other_content_type_skipped_no_pattern(self):
        book = self._make_book("Audiobook.pdf", content_type="audiobook")
        out = StringIO()
        call_command("move_approved", stdout=out)
        self.assertIn(f"skipped {book.id} | no pattern yet", out.getvalue())

    def test_folder_pattern_only_uses_default_filename(self):
        book = self._make_book("My Book.pdf", author="John Smith", content_type="ebook")
        out = StringIO()
        call_command("move_approved", stdout=out, folder_pattern="Custom")
        line = next(l for l in out.getvalue().splitlines() if l.startswith(f"{book.id} |"))
        target = line.split(" -> ", 1)[1]
        expected = str(Path(self.temp_dir) / "Custom" / "Smith, John - My Book.pdf")
        self.assertEqual(target, expected)

    def test_filename_pattern_only_uses_default_folder(self):
        book = self._make_book("My Book.pdf", author="John Smith", content_type="ebook")
        out = StringIO()
        call_command("move_approved", stdout=out, filename_pattern="${title}.${ext}")
        line = next(l for l in out.getvalue().splitlines() if l.startswith(f"{book.id} |"))
        target = line.split(" -> ", 1)[1]
        expected = str(Path(self.temp_dir) / "English" / "Books" / "Smith, John" / "My Book.pdf")
        self.assertEqual(target, expected)
