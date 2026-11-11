"""Tests for the hardened safe-move routine and the book-level ``safe_move_book``.

Item 1 (routine hardening) is exercised with ``SimpleTestCase`` against the
file-level ``safe_move_file``/``finalize_move``. Item 3 (``safe_move_book``) is
exercised with a real database and real files in temporary directories, using
the DB helpers in ``books/tests/test_helpers.py``.
"""

import hashlib
import shutil
import tempfile
import zipfile
from pathlib import Path
from unittest import mock

from django.test import SimpleTestCase, TestCase

from books.models import Book, BookFile, FileMove, FinalMetadata, FileOperation, ScanFolder
from books.tests.test_helpers import create_test_book_with_file
from books.utils.safe_move import (
    NeedsReview,
    finalize_move,
    safe_move_book,
    safe_move_file,
)

MIMETYPE = b"application/epub+zip"


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _container(rootfile="OEBPS/content.opf"):
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
        '<rootfiles><rootfile full-path="'
        + rootfile
        + '" media-type="application/oebps-package+xml"/></rootfiles></container>'
    ).encode("utf-8")


def _opf(with_manifest=True):
    manifest = (
        '<manifest><item id="c1" href="chapter1.xhtml" media-type="application/xhtml+xml"/></manifest>'
        if with_manifest
        else ""
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="uid">'
        '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
        '<dc:identifier id="uid">urn:uuid:test</dc:identifier>'
        '<dc:title>Test</dc:title><dc:language>en</dc:language></metadata>'
        + manifest
        + '<spine><itemref idref="c1"/></spine></package>'
    ).encode("utf-8")


def _xhtml():
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>t</title></head>'
        "<body><p>x</p></body></html>"
    ).encode("utf-8")


def _write_epub(path, opf=None):
    files = {
        "mimetype": MIMETYPE,
        "META-INF/container.xml": _container(),
        "OEBPS/content.opf": _opf() if opf is None else opf,
        "OEBPS/chapter1.xhtml": _xhtml(),
    }
    with zipfile.ZipFile(path, "w") as z:
        names = ["mimetype"] + [n for n in files if n != "mimetype"]
        for n in names:
            z.writestr(n, files[n], compress_type=zipfile.ZIP_STORED if n == "mimetype" else zipfile.ZIP_DEFLATED)


class RoutineHardeningTests(SimpleTestCase):
    """Item 1: repack exceptions, finalize target hash, target re-check."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, str(self.root), ignore_errors=True)
        self.scan_root = self.root / "lib"
        self.scan_root.mkdir()
        self.archive_root = self.root / "Archive [To Delete]"
        self.scan_label = "Sample [To Delete] 1"

    def _move(self, source, target, **kw):
        return safe_move_file(
            str(source), str(target), scan_root=str(self.scan_root),
            scan_label=self.scan_label, archive_root=str(self.archive_root), **kw,
        )

    def _src(self, name, data=b"hello world"):
        p = self.scan_root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        return p

    # -- (a) repack exceptions become NeedsReview and clean up ----------------

    def test_repack_garbage_epub_needs_review(self):
        src = self._src("bad.epub", data=b"this is not a zip at all")
        tgt = self.root / "Moved" / "bad.epub"
        with self.assertRaises(NeedsReview) as ctx:
            self._move(src, tgt)
        self.assertEqual(ctx.exception.codes, ["repack-failed:BadZipFile"])
        self.assertFalse(tgt.exists())
        self.assertFalse(Path(str(tgt) + ".moving").exists())
        self.assertFalse(Path(str(tgt) + ".moving.part").exists())
        self.assertTrue(src.exists())

    def test_repack_no_manifest_with_cover_needs_review(self):
        src = self._src("nomanifest.epub")
        _write_epub(src, opf=_opf(with_manifest=False))
        cover = self.root / "cover.jpg"
        cover.write_bytes(b"\xff\xd8\xff\xd9")
        tgt = self.root / "Moved" / "nomanifest.epub"
        with self.assertRaises(NeedsReview) as ctx:
            self._move(src, tgt, cover_path=str(cover))
        self.assertEqual(ctx.exception.codes, ["repack-failed:ValueError"])
        self.assertFalse(tgt.exists())
        self.assertFalse(Path(str(tgt) + ".moving").exists())
        self.assertTrue(src.exists())

    def test_repack_invalid_cover_path_needs_review(self):
        src = self._src("good.epub")
        _write_epub(src)
        tgt = self.root / "Moved" / "good.epub"
        with self.assertRaises(NeedsReview) as ctx:
            self._move(src, tgt, cover_path=str(self.root / "missing.jpg"))
        self.assertEqual(ctx.exception.codes, ["repack-failed:ValueError"])
        self.assertFalse(tgt.exists())
        self.assertFalse(Path(str(tgt) + ".moving").exists())
        self.assertTrue(src.exists())

    # -- (b) finalize requires the target hash to match -----------------------

    def test_finalize_target_hash_mismatch(self):
        src = self._src("report.pdf", data=b"%PDF-1.4 fake")
        tgt = self.root / "Moved" / "report.pdf"
        result = self._move(src, tgt)
        tgt.write_bytes(b"tampered after commit")
        with self.assertRaises(NeedsReview) as ctx:
            finalize_move(result)
        self.assertEqual(ctx.exception.codes, ["target-hash"])
        self.assertTrue(src.exists())

    # -- (c) re-check the target immediately before os.replace ----------------

    def test_recheck_target_exists_raises_file_exists(self):
        src = self._src("book.txt", data=b"content")
        tgt = self.root / "Moved" / "book.txt"
        captured = {}

        def on_step(name, state):
            captured.update(state)
            if name == "archived":
                tgt.parent.mkdir(parents=True, exist_ok=True)
                tgt.write_bytes(b"race writer")

        with self.assertRaises(FileExistsError):
            self._move(src, tgt, on_step=on_step)
        self.assertTrue(src.exists())
        self.assertEqual(tgt.read_bytes(), b"race writer")  # someone else's file left alone
        self.assertFalse(Path(str(tgt) + ".moving").exists())
        self.assertFalse(Path(captured["archived_path"]).exists())


class SafeMoveBookTests(TestCase):
    """Item 3: ``safe_move_book`` end to end."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, str(self.root), ignore_errors=True)
        self.scan_root = self.root / "lib"
        self.scan_root.mkdir()
        self.scan_folder = ScanFolder.objects.create(
            path=str(self.scan_root), name="Sample [To Delete]", content_type="ebooks", is_active=True,
        )
        self.target_dir = self.root / "Moved"

    def _make_book(self, name="sub/book.txt", data=b"hello world", *, reviewed=True, file_format=None):
        src = self.scan_root / name
        src.parent.mkdir(parents=True, exist_ok=True)
        src.write_bytes(data)
        book = create_test_book_with_file(
            file_path=str(src), file_format=file_format, scan_folder=self.scan_folder,
        )
        if reviewed:
            FinalMetadata.objects.create(book=book, final_title=Path(name).stem, is_reviewed=True)
        return book, src

    def test_success_path(self):
        book, src = self._make_book("sub/book.txt", data=b"move me please")
        target = self.target_dir / "book.txt"
        row = safe_move_book(book, str(target))

        self.assertEqual(row.state, FileMove.State.PENDING_DELETION)
        # DB updated: BookFile points at the target.
        fresh = BookFile.objects.get(book=book)
        self.assertEqual(fresh.file_path, str(target))
        # Source gone, archive present, target present.
        self.assertFalse(src.exists())
        self.assertTrue(target.is_file())
        self.assertTrue(Path(row.archived_path).is_file())
        self.assertEqual(_sha256(row.archived_path), row.original_sha256)
        # RenameHistory (FileOperation) row created.
        self.assertTrue(FileOperation.objects.filter(book=book, operation_type="rename").exists())

    def test_unapproved_refused_with_no_row(self):
        book, src = self._make_book("sub/book.txt", reviewed=False)
        target = self.target_dir / "book.txt"
        with self.assertRaises(ValueError):
            safe_move_book(book, str(target))
        self.assertEqual(FileMove.objects.filter(book=book).count(), 0)
        self.assertTrue(src.exists())
        self.assertFalse(target.exists())

    def test_garbage_epub_needs_review(self):
        book, src = self._make_book("sub/bad.epub", data=b"not a zip", file_format="epub")
        target = self.target_dir / "bad.epub"
        with self.assertRaises(NeedsReview):
            safe_move_book(book, str(target))
        row = FileMove.objects.get(book=book)
        self.assertEqual(row.state, FileMove.State.NEEDS_REVIEW)
        self.assertEqual(row.review_flags, ["repack-failed:BadZipFile"])
        # Files and DB unchanged.
        self.assertTrue(src.exists())
        self.assertFalse(target.exists())
        fresh = BookFile.objects.get(book=book)
        self.assertEqual(fresh.file_path, str(src))

    def test_renamehistory_failure_db_unchanged_source_intact(self):
        book, src = self._make_book("sub/book.txt", data=b"keep me")
        target = self.target_dir / "book.txt"
        with mock.patch("books.models_operations.FileOperation.objects.create", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                safe_move_book(book, str(target))
        # DB unchanged: BookFile still points at the source, no rename record.
        fresh = BookFile.objects.get(book=book)
        self.assertEqual(fresh.file_path, str(src))
        self.assertFalse(FileOperation.objects.filter(book=book, operation_type="rename").exists())
        # Source intact, target removed by the resolver.
        self.assertTrue(src.exists())
        self.assertFalse(target.exists())

    def test_check_c_failure_reverts(self):
        book, src = self._make_book("sub/book.txt", data=b"verify me")
        target = self.target_dir / "book.txt"
        with mock.patch("books.utils.safe_move.book._check_c_passes", return_value=False):
            row = safe_move_book(book, str(target))
        self.assertEqual(row.state, FileMove.State.ROLLED_BACK)
        # DB reverted to the previous paths.
        fresh = BookFile.objects.get(book=book)
        self.assertEqual(fresh.file_path, str(src))
        fm = FinalMetadata.objects.get(book=book)
        self.assertEqual(fm.final_path, "")
        # Source intact, target and archive rolled back.
        self.assertTrue(src.exists())
        self.assertFalse(target.exists())
        self.assertFalse(Path(row.archived_path).exists())

    # -- item 1: safe_move_book failures --------------------------------------

    def test_missing_source_ends_failed(self):
        book, src = self._make_book("sub/book.txt", data=b"gone soon")
        src.unlink()
        target = self.target_dir / "book.txt"
        with self.assertRaises(FileNotFoundError):
            safe_move_book(book, str(target))
        row = FileMove.objects.get(book=book)
        self.assertEqual(row.state, FileMove.State.FAILED)
        self.assertTrue(row.error)

    def test_existing_target_ends_failed(self):
        book, src = self._make_book("sub/book.txt", data=b"keep me")
        target = self.target_dir / "book.txt"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"already here")
        with self.assertRaises(FileExistsError):
            safe_move_book(book, str(target))
        row = FileMove.objects.get(book=book)
        self.assertEqual(row.state, FileMove.State.FAILED)
        self.assertTrue(src.exists())

    def test_oserror_at_archive_step_ends_failed_and_cleans_up(self):
        book, src = self._make_book("sub/book.txt", data=b"keep me")
        target = self.target_dir / "book.txt"
        calls = []

        def fake_fsync(path):
            calls.append(str(path))
            # Raise only for the archive copy, not the .moving temp file.
            if "Archive [To Delete]" in str(path):
                raise OSError("fsync failed")

        with mock.patch("books.utils.safe_move.routine._fsync_file", side_effect=fake_fsync):
            with self.assertRaises(OSError):
                safe_move_book(book, str(target))
        row = FileMove.objects.get(book=book)
        self.assertEqual(row.state, FileMove.State.FAILED)
        self.assertTrue(row.error)
        self.assertTrue(src.exists())  # source intact
        self.assertFalse(target.exists())
        self.assertFalse(Path(str(target) + ".moving").exists())
        self.assertFalse(Path(row.archived_path).exists())  # archive removed

    # -- item 5: history row + stale saves ------------------------------------

    def test_check_c_failure_marks_history_reverted(self):
        book, src = self._make_book("sub/book.txt", data=b"verify me")
        target = self.target_dir / "book.txt"
        with mock.patch("books.utils.safe_move.book._check_c_passes", return_value=False):
            row = safe_move_book(book, str(target))
        self.assertEqual(row.state, FileMove.State.ROLLED_BACK)
        op = FileOperation.objects.get(book=book, operation_type="rename")
        self.assertEqual(op.status, "reverted")

    def test_mark_as_renamed_preserves_concurrent_language_update(self):
        book, src = self._make_book("sub/book.txt", data=b"move me")
        fm = FinalMetadata.objects.get(book=book)
        fm.language = "en"
        fm.save(update_fields=["language"])

        # A stale instance of the same FinalMetadata row (loaded before B).
        stale = FinalMetadata.objects.get(book=book)
        # Another instance (B) changes the language after A was loaded.
        fm.language = "nl"
        fm.save(update_fields=["language"])

        # mark_as_renamed on the stale instance must not clobber B's update.
        stale.mark_as_renamed(str(self.target_dir / "book.txt"))

        fm.refresh_from_db()
        self.assertEqual(fm.language, "nl")  # survives the stale mark_as_renamed

    # -- item 6/7/9: companions ----------------------------------------------

    def _make_book_with_companions(self):
        book, src = self._make_book("sub/book.pdf", data=b"%PDF-1.4 fake pdf")
        sub = src.parent
        cover = sub / "cover.jpg"
        cover.write_bytes(b"\xff\xd8\xff\xd9")
        opf = sub / "book.opf"
        opf.write_bytes(b"<package></package>")
        txt = sub / "book.txt"
        txt.write_bytes(b"sidecar text")
        bf = BookFile.objects.get(book=book)
        bf.cover_path = str(cover)
        bf.opf_path = str(opf)
        bf.save(update_fields=["cover_path", "opf_path"])
        return book, src, cover, opf, txt

    def test_book_with_companions_moves_completely(self):
        book, src, cover, opf, txt = self._make_book_with_companions()
        target = self.target_dir / "book.pdf"
        row = safe_move_book(book, str(target))
        self.assertEqual(row.state, FileMove.State.PENDING_DELETION)
        # Main moved, source gone.
        self.assertFalse(src.exists())
        self.assertTrue(target.is_file())
        # Companions recreated under the new stem in the target folder.
        self.assertTrue((self.target_dir / "book.jpg").is_file())
        self.assertTrue((self.target_dir / "book.opf").is_file())
        self.assertTrue((self.target_dir / "book.txt").is_file())
        # Companion originals gone; archive copies present.
        self.assertFalse(cover.exists())
        self.assertFalse(opf.exists())
        self.assertFalse(txt.exists())
        children = FileMove.objects.filter(parent=row, kind=FileMove.Kind.COMPANION)
        self.assertEqual(children.count(), 3)
        for c in children:
            self.assertEqual(c.state, FileMove.State.PENDING_DELETION)
            self.assertTrue(Path(c.archived_path).is_file())
        # DB fields updated.
        bf = BookFile.objects.get(book=book)
        self.assertEqual(bf.file_path, str(target))
        self.assertEqual(bf.cover_path, str(self.target_dir / "book.jpg"))
        self.assertEqual(bf.opf_path, str(self.target_dir / "book.opf"))

    def test_cover_companion_is_copy_of_final_cover_path(self):
        book, src, cover, opf, txt = self._make_book_with_companions()
        curated = self.scan_root / "curated.jpg"
        curated.write_bytes(b"\xff\xd8\xff\xe0CURATED")
        fm = book.finalmetadata
        fm.final_cover_path = str(curated)
        fm.save(update_fields=["final_cover_path"])
        target = self.target_dir / "book.pdf"
        row = safe_move_book(book, str(target))
        self.assertEqual(row.state, FileMove.State.PENDING_DELETION)
        # The cover beside the book is a copy of final_cover_path, not the old cover.
        new_cover = self.target_dir / "book.jpg"
        self.assertTrue(new_cover.is_file())
        self.assertEqual(new_cover.read_bytes(), b"\xff\xd8\xff\xe0CURATED")
        # The old companion cover is archived (gone from the source folder).
        self.assertFalse(cover.exists())
        # BookFile.cover_path points at the new cover in the same move.
        bf = BookFile.objects.get(book=book)
        self.assertEqual(bf.cover_path, str(new_cover))
        # Only one cover file beside the book.
        self.assertEqual(sorted(p.name for p in self.target_dir.glob("*.jpg")), ["book.jpg"])

    # -- A2: curated-cover flags ---------------------------------------------

    def _set_curated(self, book, name="curated.jpg", data=b"\xff\xd8\xff\xe0CURATED"):
        p = self.scan_root / name
        p.write_bytes(data)
        fm = book.finalmetadata
        fm.final_cover_path = str(p)
        fm.save(update_fields=["final_cover_path"])
        return p

    def test_curated_cover_valid_has_no_flag(self):
        book, src, cover, opf, txt = self._make_book_with_companions()
        curated = self._set_curated(book)
        target = self.target_dir / "book.pdf"
        row = safe_move_book(book, str(target))
        self.assertEqual(row.state, FileMove.State.PENDING_DELETION)
        row.refresh_from_db()
        flags = row.review_flags or []
        self.assertNotIn("cover-missing", flags)
        self.assertNotIn("cover-invalid", flags)
        new_cover = self.target_dir / "book.jpg"
        self.assertEqual(new_cover.read_bytes(), curated.read_bytes())

    def test_curated_cover_empty_flags_cover_missing_once(self):
        book, src, cover, opf, txt = self._make_book_with_companions()
        # final_cover_path is "" by default.
        target = self.target_dir / "book.pdf"
        row = safe_move_book(book, str(target))
        row.refresh_from_db()
        flags = row.review_flags or []
        self.assertEqual(flags.count("cover-missing"), 1)
        self.assertNotIn("cover-invalid", flags)

    def test_curated_cover_invalid_flags_cover_invalid_once(self):
        book, src, cover, opf, txt = self._make_book_with_companions()
        bad = self.scan_root / "bad.jpg"
        bad.write_bytes(b"this is not really a jpeg image")
        fm = book.finalmetadata
        fm.final_cover_path = str(bad)
        fm.save(update_fields=["final_cover_path"])
        target = self.target_dir / "book.pdf"
        row = safe_move_book(book, str(target))
        row.refresh_from_db()
        flags = row.review_flags or []
        self.assertEqual(flags.count("cover-invalid"), 1)
        self.assertNotIn("cover-missing", flags)

    def test_epub_empty_curated_cover_flags_cover_missing_once(self):
        # EPUB with an empty curated cover: the embed cover flag and the final
        # cover flag both map to cover-missing, and the dedup keeps it once.
        book, src = self._make_epub_book()
        sub = src.parent
        cover = sub / "cover.jpg"
        cover.write_bytes(b"\xff\xd8\xff\xd9")
        bf = BookFile.objects.get(book=book)
        bf.cover_path = str(cover)
        bf.save(update_fields=["cover_path"])
        target = self.target_dir / "book.epub"
        row = safe_move_book(book, str(target), cover_path="")
        row.refresh_from_db()
        flags = row.review_flags or []
        self.assertEqual(flags.count("cover-missing"), 1)

    def test_valid_curated_copy_clears_stale_flag(self):
        # An invalid old companion must not leave a cover-invalid flag when a
        # valid curated cover is copied over it.
        book, src, cover, opf, txt = self._make_book_with_companions()
        cover.write_bytes(b"stale garbage bytes")
        curated = self._set_curated(book)
        target = self.target_dir / "book.pdf"
        row = safe_move_book(book, str(target))
        row.refresh_from_db()
        flags = row.review_flags or []
        self.assertNotIn("cover-invalid", flags)
        self.assertNotIn("cover-missing", flags)
        self.assertEqual((self.target_dir / "book.jpg").read_bytes(), curated.read_bytes())

    # -- A3: curated png over jpg companion ----------------------------------

    def test_curated_png_over_jpg_companion(self):
        from lxml import etree as ET

        book, src, cover, opf, txt = self._make_book_with_companions()
        png = self.scan_root / "curated.png"
        png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 8)
        fm = book.finalmetadata
        fm.final_cover_path = str(png)
        fm.save(update_fields=["final_cover_path"])
        target = self.target_dir / "book.pdf"
        row = safe_move_book(book, str(target))
        self.assertEqual(row.state, FileMove.State.PENDING_DELETION)
        # cover beside the book is <stem>.png, a copy of the curated png
        new_cover = self.target_dir / "book.png"
        self.assertTrue(new_cover.is_file())
        self.assertEqual(new_cover.read_bytes(), png.read_bytes())
        # BookFile.cover_path points at it
        bf = BookFile.objects.get(book=book)
        self.assertEqual(bf.cover_path, str(new_cover))
        # old jpg archived (gone from the source folder)
        self.assertFalse(cover.exists())
        # sidecar OPF references <stem>.png
        target_opf = self.target_dir / "book.opf"
        self.assertTrue(target_opf.is_file())
        root = ET.fromstring(target_opf.read_bytes())
        NS = {"opf": "http://www.idpf.org/2007/opf"}
        item = root.find("opf:manifest/opf:item", NS)
        self.assertEqual(item.get("href"), "book.png")
        ref = root.find("opf:guide/opf:reference", NS)
        self.assertEqual(ref.get("href"), "book.png")

    def test_discover_companions_cover_before_opf(self):
        from books.utils.safe_move.book import _discover_companions

        book, src, cover, opf, txt = self._make_book_with_companions()
        primary_file = BookFile.objects.get(book=book)
        result, shared, outside = _discover_companions(
            primary_file, str(self.target_dir / "book.pdf")
        )
        db_fields = [db_field for _source, db_field, _target in result]
        self.assertIn(FileMove.DBField.COVER_PATH, db_fields)
        self.assertIn(FileMove.DBField.OPF_PATH, db_fields)
        self.assertLess(
            db_fields.index(FileMove.DBField.COVER_PATH),
            db_fields.index(FileMove.DBField.OPF_PATH),
        )

    def test_failing_companion_leaves_main_done_and_flags_parent(self):
        book, src, cover, opf, txt = self._make_book_with_companions()
        target = self.target_dir / "book.pdf"
        real = safe_move_file

        def fake(source, tgt, **kw):
            if str(source).endswith("book.txt"):
                raise NeedsReview(["companion-bad"])
            return real(source, tgt, **kw)

        with mock.patch("books.utils.safe_move.book.safe_move_file", side_effect=fake):
            row = safe_move_book(book, str(target))
        self.assertEqual(row.state, FileMove.State.PENDING_DELETION)  # main done
        self.assertFalse(src.exists())
        self.assertTrue(target.is_file())
        self.assertTrue((self.target_dir / "book.jpg").is_file())
        self.assertTrue((self.target_dir / "book.opf").is_file())
        # Failing companion: original in place, no target, flag on parent.
        self.assertTrue(txt.exists())
        self.assertFalse((self.target_dir / "book.txt").exists())
        row.refresh_from_db()
        self.assertIn("companion-failed:book.txt", row.review_flags)
        child = FileMove.objects.get(parent=row, source_path=str(txt))
        self.assertEqual(child.state, FileMove.State.NEEDS_REVIEW)

    # -- companion isolation --------------------------------------------------

    def test_two_books_one_folder_move_one_leaves_other_alone(self):
        book1, src1 = self._make_book("sub/book1.pdf", data=b"%PDF-1.4 one")
        book2, src2 = self._make_book("sub/book2.pdf", data=b"%PDF-1.4 two")
        sub = src1.parent
        cover1 = sub / "book1.jpg"
        cover1.write_bytes(b"c1")
        sidecar1 = sub / "book1.txt"
        sidecar1.write_bytes(b"s1")
        cover2 = sub / "book2.jpg"
        cover2.write_bytes(b"c2")
        sidecar2 = sub / "book2.txt"
        sidecar2.write_bytes(b"s2")
        bf1 = BookFile.objects.get(book=book1)
        bf1.cover_path = str(cover1)
        bf1.save(update_fields=["cover_path"])
        bf2 = BookFile.objects.get(book=book2)
        bf2.cover_path = str(cover2)
        bf2.save(update_fields=["cover_path"])

        target = self.target_dir / "book1.pdf"
        row = safe_move_book(book1, str(target))
        self.assertEqual(row.state, FileMove.State.PENDING_DELETION)
        self.assertFalse(src1.exists())
        self.assertTrue(target.is_file())
        self.assertTrue((self.target_dir / "book1.jpg").is_file())
        self.assertTrue((self.target_dir / "book1.txt").is_file())
        self.assertFalse(cover1.exists())
        self.assertFalse(sidecar1.exists())
        # book2 is untouched.
        self.assertTrue(src2.exists())
        self.assertTrue(cover2.exists())
        self.assertTrue(sidecar2.exists())
        self.assertFalse((self.target_dir / "book2.pdf").exists())
        self.assertFalse((self.target_dir / "book2.jpg").exists())
        self.assertFalse((self.target_dir / "book2.txt").exists())

    def test_shared_cover_between_two_books_not_moved(self):
        book1, src1 = self._make_book("sub/book1.pdf", data=b"%PDF-1.4 one")
        book2, src2 = self._make_book("sub/book2.pdf", data=b"%PDF-1.4 two")
        sub = src1.parent
        cover = sub / "cover.jpg"
        cover.write_bytes(b"\xff\xd8\xff\xd9")
        bf1 = BookFile.objects.get(book=book1)
        bf1.cover_path = str(cover)
        bf1.save(update_fields=["cover_path"])
        bf2 = BookFile.objects.get(book=book2)
        bf2.cover_path = str(cover)
        bf2.save(update_fields=["cover_path"])

        target = self.target_dir / "book1.pdf"
        row = safe_move_book(book1, str(target))
        self.assertEqual(row.state, FileMove.State.PENDING_DELETION)
        self.assertFalse(src1.exists())
        self.assertTrue(target.is_file())
        # Shared cover is not moved or archived.
        self.assertTrue(cover.exists())
        self.assertFalse((self.target_dir / "cover.jpg").is_file())
        row.refresh_from_db()
        self.assertIn("companion-shared:cover.jpg", row.review_flags)

    def test_sidecar_of_another_book_not_claimed(self):
        book1, src1 = self._make_book("sub/book1.pdf", data=b"%PDF-1.4 one")
        book2, src2 = self._make_book("sub/book2.pdf", data=b"%PDF-1.4 two")
        sub = src1.parent
        cover = sub / "cover.jpg"
        cover.write_bytes(b"\xff\xd8\xff\xd9")
        bf2 = BookFile.objects.get(book=book2)
        bf2.cover_path = str(cover)
        bf2.save(update_fields=["cover_path"])

        target = self.target_dir / "book1.pdf"
        row = safe_move_book(book1, str(target))
        self.assertEqual(row.state, FileMove.State.PENDING_DELETION)
        self.assertFalse(src1.exists())
        # book2's cover is a sidecar of another book: not claimed, not moved.
        self.assertTrue(cover.exists())
        self.assertFalse((self.target_dir / "cover.jpg").is_file())
        self.assertTrue(src2.exists())

    def test_same_stem_different_folder_moves_normally(self):
        book1, src1 = self._make_book("sub/book.pdf", data=b"%PDF-1.4 one")
        book2, src2 = self._make_book("otherdir/book.pdf", data=b"%PDF-1.4 two")
        sub = src1.parent
        cover = sub / "cover.jpg"
        cover.write_bytes(b"c1")
        sidecar = sub / "book.txt"
        sidecar.write_bytes(b"s1")
        bf1 = BookFile.objects.get(book=book1)
        bf1.cover_path = str(cover)
        bf1.save(update_fields=["cover_path"])

        target = self.target_dir / "book.pdf"
        row = safe_move_book(book1, str(target))
        self.assertEqual(row.state, FileMove.State.PENDING_DELETION)
        self.assertFalse(src1.exists())
        # A book with the same stem in a different folder is unrelated: the
        # cover and sidecar move normally.
        self.assertTrue((self.target_dir / "book.jpg").is_file())
        self.assertTrue((self.target_dir / "book.txt").is_file())
        self.assertFalse(cover.exists())
        self.assertFalse(sidecar.exists())
        self.assertTrue(src2.exists())

    def test_same_stem_same_folder_sidecar_ambiguous(self):
        book1, src1 = self._make_book("sub/book.pdf", data=b"%PDF-1.4 one")
        book2, src2 = self._make_book("sub/book.epub", data=b"epub data")
        sub = src1.parent
        sidecar = sub / "book.txt"
        sidecar.write_bytes(b"s1")

        target = self.target_dir / "book.pdf"
        row = safe_move_book(book1, str(target))
        self.assertEqual(row.state, FileMove.State.PENDING_DELETION)
        self.assertFalse(src1.exists())
        # Same folder, same stem (pdf beside epub): the sidecar is ambiguous.
        self.assertTrue(sidecar.exists())
        self.assertFalse((self.target_dir / "book.txt").is_file())
        row.refresh_from_db()
        self.assertIn("companion-shared:book.txt", row.review_flags)

    def test_cover_tracked_by_another_bookfile_same_book_shared(self):
        book1, src1 = self._make_book("sub/book.pdf", data=b"%PDF-1.4 one")
        sub = src1.parent
        cover = sub / "cover.jpg"
        cover.write_bytes(b"\xff\xd8\xff\xd9")
        # A second BookFile of the same book also tracks the cover.
        BookFile.objects.create(book=book1, file_path=str(sub / "book.epub"), file_format="epub", cover_path=str(cover))
        bf1 = BookFile.objects.get(book=book1, file_format="pdf")
        bf1.cover_path = str(cover)
        bf1.save(update_fields=["cover_path"])

        target = self.target_dir / "book.pdf"
        row = safe_move_book(book1, str(target))
        self.assertEqual(row.state, FileMove.State.PENDING_DELETION)
        self.assertFalse(src1.exists())
        # Cover tracked by another BookFile of the same book: shared, not moved.
        self.assertTrue(cover.exists())
        self.assertFalse((self.target_dir / "cover.jpg").is_file())
        row.refresh_from_db()
        self.assertIn("companion-shared:cover.jpg", row.review_flags)

    def test_cover_outside_source_folder_not_moved_flagged(self):
        book1, src1 = self._make_book("sub/book.pdf", data=b"%PDF-1.4 one")
        sub = src1.parent
        # Cover in a sibling directory (outside the main file's source folder).
        sibling = self.scan_root / "sibling"
        sibling.mkdir(parents=True, exist_ok=True)
        cover = sibling / "cover.jpg"
        cover.write_bytes(b"c1")
        bf1 = BookFile.objects.get(book=book1)
        bf1.cover_path = str(cover)
        bf1.save(update_fields=["cover_path"])

        target = self.target_dir / "book.pdf"
        row = safe_move_book(book1, str(target))
        self.assertEqual(row.state, FileMove.State.PENDING_DELETION)
        self.assertFalse(src1.exists())
        # Cover outside the source folder is neither moved nor archived.
        self.assertTrue(cover.exists())
        self.assertFalse((self.target_dir / "cover.jpg").is_file())
        bf1.refresh_from_db()
        self.assertEqual(bf1.cover_path, str(cover))  # DB value unchanged
        row.refresh_from_db()
        self.assertIn("companion-outside:cover.jpg", row.review_flags)

    def test_cover_in_subfolder_stays_allowed(self):
        book1, src1 = self._make_book("sub/book.pdf", data=b"%PDF-1.4 one")
        sub = src1.parent
        # Cover in a subfolder below the source folder is allowed.
        subsub = sub / "assets"
        subsub.mkdir(parents=True, exist_ok=True)
        cover = subsub / "cover.jpg"
        cover.write_bytes(b"c1")
        bf1 = BookFile.objects.get(book=book1)
        bf1.cover_path = str(cover)
        bf1.save(update_fields=["cover_path"])

        target = self.target_dir / "book.pdf"
        row = safe_move_book(book1, str(target))
        self.assertEqual(row.state, FileMove.State.PENDING_DELETION)
        self.assertFalse(src1.exists())
        self.assertTrue((self.target_dir / "book.jpg").is_file())
        self.assertFalse(cover.exists())

    # -- cover is non-fatal ---------------------------------------------------

    def _make_epub_book(self, name="sub/book.epub"):
        src = self.scan_root / name
        src.parent.mkdir(parents=True, exist_ok=True)
        _write_epub(src)
        book = create_test_book_with_file(
            file_path=str(src), file_format="epub", scan_folder=self.scan_folder,
        )
        FinalMetadata.objects.create(book=book, final_title=Path(name).stem, is_reviewed=True)
        return book, src

    def _cover(self, name="cover.jpg", data=b"\xff\xd8\xff\xd9"):
        p = self.scan_root / name
        p.write_bytes(data)
        return p

    def test_missing_cover_path_moves_and_flags_cover_missing(self):
        book, src = self._make_epub_book()
        target = self.target_dir / "book.epub"
        row = safe_move_book(book, str(target), cover_path=str(self.scan_root / "missing.jpg"))
        self.assertEqual(row.state, FileMove.State.PENDING_DELETION)
        row.refresh_from_db()
        self.assertIn("cover-missing", row.review_flags)
        self.assertFalse(src.exists())
        self.assertTrue(target.is_file())

    def test_empty_cover_path_moves_and_flags_cover_missing(self):
        book, src = self._make_epub_book()
        target = self.target_dir / "book.epub"
        row = safe_move_book(book, str(target), cover_path="")
        self.assertEqual(row.state, FileMove.State.PENDING_DELETION)
        row.refresh_from_db()
        self.assertIn("cover-missing", row.review_flags)

    def test_invalid_cover_image_moves_and_flags_cover_invalid(self):
        book, src = self._make_epub_book()
        bad = self._cover("cover.txt", data=b"not an image")
        target = self.target_dir / "book.epub"
        row = safe_move_book(book, str(target), cover_path=str(bad))
        self.assertEqual(row.state, FileMove.State.PENDING_DELETION)
        row.refresh_from_db()
        self.assertIn("cover-invalid", row.review_flags)

    def test_valid_cover_is_embedded_and_no_flag(self):
        book, src = self._make_epub_book()
        cover = self._cover()
        target = self.target_dir / "book.epub"
        row = safe_move_book(book, str(target), cover_path=str(cover))
        self.assertEqual(row.state, FileMove.State.PENDING_DELETION)
        row.refresh_from_db()
        self.assertNotIn("cover-missing", row.review_flags)
        self.assertNotIn("cover-invalid", row.review_flags)
        with zipfile.ZipFile(target) as z:
            self.assertTrue(any(n.endswith(".jpg") for n in z.namelist()), z.namelist())

    def test_non_epub_with_cover_path_moves_normally(self):
        book, src = self._make_book("sub/book.pdf", data=b"%PDF-1.4 fake", file_format="pdf")
        cover = self._cover()
        target = self.target_dir / "book.pdf"
        row = safe_move_book(book, str(target), cover_path=str(cover))
        self.assertEqual(row.state, FileMove.State.PENDING_DELETION)
        row.refresh_from_db()
        self.assertNotIn("cover-missing", row.review_flags)
        self.assertNotIn("cover-invalid", row.review_flags)

    def test_garbage_bytes_jpg_moves_and_flags_cover_invalid(self):
        book, src = self._make_epub_book()
        bad = self._cover("cover.jpg", data=b"this is not really a jpeg image")
        target = self.target_dir / "book.epub"
        row = safe_move_book(book, str(target), cover_path=str(bad))
        self.assertEqual(row.state, FileMove.State.PENDING_DELETION)
        row.refresh_from_db()
        self.assertIn("cover-invalid", row.review_flags)
        self.assertNotIn("cover-missing", row.review_flags)

    def test_zero_byte_jpg_moves_and_flags_cover_invalid(self):
        book, src = self._make_epub_book()
        bad = self._cover("cover.jpg", data=b"")
        target = self.target_dir / "book.epub"
        row = safe_move_book(book, str(target), cover_path=str(bad))
        self.assertEqual(row.state, FileMove.State.PENDING_DELETION)
        row.refresh_from_db()
        self.assertIn("cover-invalid", row.review_flags)
        self.assertNotIn("cover-missing", row.review_flags)

    def test_directory_named_cover_jpg_flags_cover_missing(self):
        book, src = self._make_epub_book()
        cover_dir = self.scan_root / "cover.jpg"
        cover_dir.mkdir()
        target = self.target_dir / "book.epub"
        row = safe_move_book(book, str(target), cover_path=str(cover_dir))
        self.assertEqual(row.state, FileMove.State.PENDING_DELETION)
        row.refresh_from_db()
        self.assertIn("cover-missing", row.review_flags)
        self.assertNotIn("cover-invalid", row.review_flags)

    def test_valid_jpg_and_png_embed_with_no_flag(self):
        book, src = self._make_epub_book()
        jpg = self._cover("cover.jpg", data=b"\xff\xd8\xff\xd9")
        target = self.target_dir / "book.epub"
        row = safe_move_book(book, str(target), cover_path=str(jpg))
        self.assertEqual(row.state, FileMove.State.PENDING_DELETION)
        row.refresh_from_db()
        self.assertNotIn("cover-missing", row.review_flags)
        self.assertNotIn("cover-invalid", row.review_flags)
        with zipfile.ZipFile(target) as z:
            self.assertTrue(any(n.endswith(".jpg") for n in z.namelist()), z.namelist())

        book2, src2 = self._make_epub_book("sub/book2.epub")
        png = self._cover("cover.png", data=b"\x89PNG\r\n\x1a\n" + b"\x00" * 8)
        target2 = self.target_dir / "book2.epub"
        row2 = safe_move_book(book2, str(target2), cover_path=str(png))
        self.assertEqual(row2.state, FileMove.State.PENDING_DELETION)
        row2.refresh_from_db()
        self.assertNotIn("cover-missing", row2.review_flags)
        self.assertNotIn("cover-invalid", row2.review_flags)
        with zipfile.ZipFile(target2) as z:
            self.assertTrue(any(n.endswith(".png") for n in z.namelist()), z.namelist())


class EpubMetadataWiringTests(TestCase):
    """safe_move_book builds the metadata dict and passes it through the fixer."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, str(self.root), ignore_errors=True)
        self.scan_root = self.root / "lib"
        self.scan_root.mkdir()
        self.scan_folder = ScanFolder.objects.create(
            path=str(self.scan_root), name="Sample [To Delete]", content_type="ebooks", is_active=True,
        )
        self.target_dir = self.root / "Moved"

    def _epub_book(self, name="sub/book.epub", *, reviewed=True):
        src = self.scan_root / name
        src.parent.mkdir(parents=True, exist_ok=True)
        _write_epub(src)
        book = create_test_book_with_file(
            file_path=str(src), file_format="epub", scan_folder=self.scan_folder,
        )
        if reviewed:
            FinalMetadata.objects.create(
                book=book, final_title="Great Book", final_author="Jane Doe",
                language="en", final_publisher="Acme", publication_year=1999,
                description="A great read", isbn="9781234567890", is_reviewed=True,
            )
        return book, src

    def test_approved_epub_gets_metadata(self):
        book, src = self._epub_book()
        target = self.target_dir / "book.epub"
        row = safe_move_book(book, str(target))
        self.assertEqual(row.state, FileMove.State.PENDING_DELETION)
        from lxml import etree

        with zipfile.ZipFile(target) as z:
            root = etree.fromstring(z.read("OEBPS/content.opf"))
        NS = {"dc": "http://purl.org/dc/elements/1.1/", "opf": "http://www.idpf.org/2007/opf"}
        m = root.find("opf:metadata", NS)
        self.assertEqual(m.find("dc:title", NS).text, "Great Book")
        self.assertEqual(m.find("dc:creator", NS).text, "Jane Doe")
        self.assertEqual(m.find("dc:publisher", NS).text, "Acme")
        self.assertEqual(m.find("dc:date", NS).text, "1999")

    def test_unapproved_epub_writes_nothing(self):
        book, src = self._epub_book(reviewed=False)
        target = self.target_dir / "book.epub"
        with self.assertRaises(ValueError):
            safe_move_book(book, str(target))
        self.assertTrue(src.exists())
        self.assertFalse(target.exists())
        self.assertEqual(FileMove.objects.filter(book=book).count(), 0)

    def test_pdf_moves_unchanged(self):
        src = self.scan_root / "sub/book.pdf"
        src.parent.mkdir(parents=True, exist_ok=True)
        data = b"%PDF-1.4 fake pdf bytes"
        src.write_bytes(data)
        book = create_test_book_with_file(
            file_path=str(src), file_format="pdf", scan_folder=self.scan_folder,
        )
        FinalMetadata.objects.create(book=book, final_title="Pdf Title", is_reviewed=True)
        target = self.target_dir / "book.pdf"
        row = safe_move_book(book, str(target))
        self.assertEqual(row.state, FileMove.State.PENDING_DELETION)
        self.assertEqual(target.read_bytes(), data)

    def test_repack_off_leaves_epub_unchanged(self):
        book, src = self._epub_book()
        with zipfile.ZipFile(src) as z:
            before = z.read("OEBPS/content.opf")
        target = self.target_dir / "book.epub"
        row = safe_move_book(book, str(target), repack_epub=False)
        self.assertEqual(row.state, FileMove.State.PENDING_DELETION)
        with zipfile.ZipFile(target) as z:
            self.assertEqual(z.read("OEBPS/content.opf"), before)

    def test_metadata_mismatch_needs_review_no_archive(self):
        from books.utils.epub_fix import fixer as fixer_mod

        book, src = self._epub_book()
        target = self.target_dir / "book.epub"
        real_sync = fixer_mod._sync_metadata

        def drop_title(opf_root, metadata):
            reduced = {k: v for k, v in metadata.items() if k != "title"}
            return real_sync(opf_root, reduced)

        with mock.patch("books.utils.epub_fix.fixer._sync_metadata", side_effect=drop_title):
            with self.assertRaises(NeedsReview) as ctx:
                safe_move_book(book, str(target))
        self.assertIn("metadata-mismatch:title", ctx.exception.codes)
        row = FileMove.objects.get(book=book)
        self.assertEqual(row.state, FileMove.State.NEEDS_REVIEW)
        self.assertTrue(src.exists())
        self.assertFalse(target.exists())
        self.assertFalse(Path(row.archived_path).exists())
        self.assertFalse(Path(str(target) + ".moving").exists())


def _cover_opf():
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="uid">'
        '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
        '<dc:identifier id="uid">urn:uuid:test</dc:identifier>'
        '<dc:title>Test</dc:title><dc:language>en</dc:language>'
        '<meta name="cover" content="coverimg"/></metadata>'
        '<manifest>'
        '<item id="coverpage" href="cover.xhtml" media-type="application/xhtml+xml"/>'
        '<item id="coverimg" href="images/cover.jpg" media-type="image/jpeg"/>'
        '</manifest>'
        '<spine><itemref idref="coverpage"/></spine></package>'
    ).encode("utf-8")


def _pure_cover_page():
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>c</title></head>'
        '<body><div><img src="images/cover.jpg" alt="cover"/></div></body></html>'
    ).encode("utf-8")


def _text_cover_page():
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>c</title></head>'
        '<body><div><img src="images/cover.jpg" alt="cover"/></div><p>Chapter One</p></body></html>'
    ).encode("utf-8")


def _ambiguous_cover_page():
    # a pure page whose image path also occurs in the alt attribute: the
    # reference is ambiguous, so the rewrite is skipped (page not updated).
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>c</title></head>'
        '<body><div><img src="images/cover.jpg" alt="images/cover.jpg"/></div></body></html>'
    ).encode("utf-8")


def _write_cover_epub(path, page_bytes):
    files = {
        "mimetype": MIMETYPE,
        "META-INF/container.xml": _container(),
        "OEBPS/content.opf": _cover_opf(),
        "OEBPS/cover.xhtml": page_bytes,
        "OEBPS/images/cover.jpg": b"OLDIMAGEBYTES",
    }
    with zipfile.ZipFile(path, "w") as z:
        names = ["mimetype"] + [n for n in files if n != "mimetype"]
        for n in names:
            z.writestr(n, files[n], compress_type=zipfile.ZIP_STORED if n == "mimetype" else zipfile.ZIP_DEFLATED)


class CoverPageMoveTests(TestCase):
    """safe_move_book cover-page verification (Check B)."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, str(self.root), ignore_errors=True)
        self.scan_root = self.root / "lib"
        self.scan_root.mkdir()
        self.scan_folder = ScanFolder.objects.create(
            path=str(self.scan_root), name="Sample [To Delete]", content_type="ebooks", is_active=True,
        )
        self.target_dir = self.root / "Moved"

    def _make_cover_epub_book(self, page_bytes):
        src = self.scan_root / "sub/book.epub"
        src.parent.mkdir(parents=True, exist_ok=True)
        _write_cover_epub(src, page_bytes)
        book = create_test_book_with_file(
            file_path=str(src), file_format="epub", scan_folder=self.scan_folder,
        )
        FinalMetadata.objects.create(book=book, final_title="Cover Book", is_reviewed=True)
        return book, src

    def _cover(self, data=b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\xff\xd9"):
        p = self.scan_root / "new.jpg"
        p.write_bytes(data)
        return p

    def test_pure_page_rewritten_and_no_flag(self):
        book, src = self._make_cover_epub_book(_pure_cover_page())
        cover = self._cover(data=b"\xff\xd8\xffNEWCOVER")
        target = self.target_dir / "book.epub"
        row = safe_move_book(book, str(target), cover_path=str(cover))
        self.assertEqual(row.state, FileMove.State.PENDING_DELETION)
        row.refresh_from_db()
        self.assertNotIn("cover-page-not-updated", row.review_flags)
        self.assertNotIn("cover-page-mismatch", row.review_flags)
        with zipfile.ZipFile(target) as z:
            page = z.read("OEBPS/cover.xhtml")
            names = z.namelist()
        self.assertNotIn(b"images/cover.jpg", page)
        self.assertIn(b'src="cover.jpg"', page)
        self.assertIn("OEBPS/cover.jpg", names)
        with zipfile.ZipFile(target) as z:
            self.assertEqual(z.read("OEBPS/cover.jpg"), b"\xff\xd8\xffNEWCOVER")

    def test_text_page_moves_and_flags_cover_page_not_updated(self):
        book, src = self._make_cover_epub_book(_text_cover_page())
        cover = self._cover()
        target = self.target_dir / "book.epub"
        row = safe_move_book(book, str(target), cover_path=str(cover))
        self.assertEqual(row.state, FileMove.State.PENDING_DELETION)
        row.refresh_from_db()
        self.assertIn("cover-page-not-updated", row.review_flags)
        self.assertTrue(target.is_file())

    def test_ambiguous_pure_page_moves_and_flags_not_updated(self):
        book, src = self._make_cover_epub_book(_ambiguous_cover_page())
        cover = self._cover(data=b"\xff\xd8\xffNEWCOVER")
        target = self.target_dir / "book.epub"
        row = safe_move_book(book, str(target), cover_path=str(cover))
        self.assertEqual(row.state, FileMove.State.PENDING_DELETION)
        row.refresh_from_db()
        self.assertIn("cover-page-not-updated", row.review_flags)
        self.assertNotIn("cover-page-mismatch", row.review_flags)
        self.assertTrue(target.is_file())

    def test_cover_page_mismatch_needs_review(self):
        book, src = self._make_cover_epub_book(_pure_cover_page())
        cover = self._cover(data=b"\xff\xd8\xffNEWCOVER")
        target = self.target_dir / "book.epub"
        with mock.patch("books.utils.epub_fix.cover_page.rewrite_cover_page", return_value=None):
            with self.assertRaises(NeedsReview) as ctx:
                safe_move_book(book, str(target), cover_path=str(cover))
        self.assertEqual(ctx.exception.codes, ["cover-page-mismatch"])
        row = FileMove.objects.get(book=book)
        self.assertEqual(row.state, FileMove.State.NEEDS_REVIEW)
        self.assertEqual(row.review_flags, ["cover-page-mismatch"])
        self.assertTrue(src.exists())  # source untouched
        self.assertFalse(target.exists())  # no target
        self.assertFalse(Path(row.archived_path).exists())  # no archive copy
        self.assertFalse(Path(str(target) + ".moving").exists())  # no temp file

    def test_missing_cover_leaves_page_and_flags_cover_missing(self):
        book, src = self._make_cover_epub_book(_pure_cover_page())
        target = self.target_dir / "book.epub"
        row = safe_move_book(book, str(target), cover_path=str(self.scan_root / "missing.jpg"))
        self.assertEqual(row.state, FileMove.State.PENDING_DELETION)
        row.refresh_from_db()
        self.assertIn("cover-missing", row.review_flags)
        with zipfile.ZipFile(target) as z:
            page = z.read("OEBPS/cover.xhtml")
        self.assertIn(b"images/cover.jpg", page)  # page untouched


class SidecarOpfTests(TestCase):
    """Item: the sidecar OPF companion is regenerated from curated metadata."""

    OLD_OPF = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="uid" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">'
        '<metadata>'
        '<dc:identifier id="uid" opf:scheme="UUID">urn:uuid:old-sidecar-id</dc:identifier>'
        '<dc:title>Old Sidecar Title</dc:title><dc:language>en</dc:language>'
        '<dc:publisher>Old Publisher</dc:publisher>'
        '<dc:subject>Old Subject</dc:subject>'
        '<meta name="calibre:series" content="Old Series"/>'
        '<meta name="calibre:series_index" content="9"/>'
        '</metadata></package>'
    ).encode("utf-8")

    OPF_NS = "http://www.idpf.org/2007/opf"
    DC_NS = "http://purl.org/dc/elements/1.1/"
    NS = {"dc": DC_NS, "opf": OPF_NS}

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, str(self.root), ignore_errors=True)
        self.scan_root = self.root / "lib"
        self.scan_root.mkdir()
        self.scan_folder = ScanFolder.objects.create(
            path=str(self.scan_root), name="Sample [To Delete]", content_type="ebooks", is_active=True,
        )
        self.target_dir = self.root / "Moved"

    def _sidecar_book(self):
        src = self.scan_root / "sub/book.epub"
        src.parent.mkdir(parents=True, exist_ok=True)
        _write_epub(src)
        book = create_test_book_with_file(
            file_path=str(src), file_format="epub", scan_folder=self.scan_folder,
        )
        FinalMetadata.objects.create(
            book=book, final_title="Great Book", final_author="Jane Doe",
            language="en", final_publisher="Acme", publication_year=1999,
            description="A great read", isbn="9781234567890",
            final_series="The Series", final_series_number="2", is_reviewed=True,
        )
        sidecar = src.parent / "book.opf"
        sidecar.write_bytes(self.OLD_OPF)
        cover = src.parent / "cover.jpg"
        cover.write_bytes(b"\xff\xd8\xff\xd9")
        bf = BookFile.objects.get(book=book)
        bf.opf_path = str(sidecar)
        bf.cover_path = str(cover)
        bf.save(update_fields=["opf_path", "cover_path"])
        return book, src, sidecar, cover

    def test_target_opf_holds_final_metadata_and_cover_reference(self):
        from lxml import etree as ET

        book, src, sidecar, cover = self._sidecar_book()
        target = self.target_dir / "book.epub"
        row = safe_move_book(book, str(target))
        self.assertEqual(row.state, FileMove.State.PENDING_DELETION)
        target_opf = self.target_dir / "book.opf"
        self.assertTrue(target_opf.is_file())
        root = ET.fromstring(target_opf.read_bytes())
        m = root.find("opf:metadata", self.NS)
        self.assertEqual(m.find("dc:title", self.NS).text, "Great Book")
        self.assertEqual(m.find("dc:creator", self.NS).text, "Jane Doe")
        self.assertEqual(m.find("dc:publisher", self.NS).text, "Acme")
        self.assertEqual(m.find("dc:date", self.NS).text, "1999")
        series = [mm for mm in m.findall("opf:meta", self.NS) if mm.get("name") == "calibre:series"]
        self.assertEqual(series[0].get("content"), "The Series")
        # Stale values from the old sidecar are gone.
        raw = target_opf.read_bytes()
        self.assertNotIn(b"Old Sidecar Title", raw)
        self.assertNotIn(b"Old Publisher", raw)
        self.assertNotIn(b"Old Series", raw)
        # Cover reference to the moved cover file.
        cover_meta = [mm for mm in m.findall("opf:meta", self.NS) if mm.get("name") == "cover"]
        self.assertEqual(cover_meta[0].get("content"), "cover-image")
        item = root.find("opf:manifest/opf:item", self.NS)
        self.assertEqual(item.get("href"), "book.jpg")
        ref = root.find("opf:guide/opf:reference", self.NS)
        self.assertEqual(ref.get("type"), "cover")
        self.assertEqual(ref.get("href"), "book.jpg")
        self.assertTrue((self.target_dir / "book.jpg").is_file())

    def test_failing_cover_leaves_opf_without_cover_reference(self):
        from lxml import etree as ET

        book, src, sidecar, cover = self._sidecar_book()
        target = self.target_dir / "book.epub"
        real = safe_move_file

        def fake(source, tgt, **kw):
            if Path(source) == Path(cover):
                raise NeedsReview(["cover-bad"])
            return real(source, tgt, **kw)

        with mock.patch("books.utils.safe_move.book.safe_move_file", side_effect=fake):
            row = safe_move_book(book, str(target))

        # Main move intact.
        self.assertEqual(row.state, FileMove.State.PENDING_DELETION)
        self.assertFalse(src.exists())
        self.assertTrue(target.is_file())
        # Cover companion failed: original in place, no target cover, parent flagged.
        self.assertTrue(cover.exists())
        self.assertFalse((self.target_dir / "book.jpg").exists())
        row.refresh_from_db()
        self.assertIn("companion-failed:cover.jpg", row.review_flags)
        # OPF still moves, but references no cover.
        target_opf = self.target_dir / "book.opf"
        self.assertTrue(target_opf.is_file())
        root = ET.fromstring(target_opf.read_bytes())
        m = root.find("opf:metadata", self.NS)
        cover_meta = [mm for mm in m.findall("opf:meta", self.NS) if mm.get("name") == "cover"]
        self.assertEqual(cover_meta, [])
        self.assertIsNone(root.find("opf:manifest/opf:item", self.NS))
        self.assertIsNone(root.find("opf:guide/opf:reference", self.NS))

    def test_archive_holds_original_and_source_gone(self):
        book, src, sidecar, cover = self._sidecar_book()
        target = self.target_dir / "book.epub"
        row = safe_move_book(book, str(target))
        child = FileMove.objects.get(parent=row, db_field=FileMove.DBField.OPF_PATH)
        self.assertEqual(Path(child.archived_path).read_bytes(), self.OLD_OPF)
        self.assertFalse(sidecar.exists())

    def test_book_without_opf_path_creates_no_opf(self):
        src = self.scan_root / "sub/book.epub"
        src.parent.mkdir(parents=True, exist_ok=True)
        _write_epub(src)
        book = create_test_book_with_file(
            file_path=str(src), file_format="epub", scan_folder=self.scan_folder,
        )
        FinalMetadata.objects.create(book=book, final_title="Great Book", is_reviewed=True)
        cover = src.parent / "cover.jpg"
        cover.write_bytes(b"\xff\xd8\xff\xd9")
        bf = BookFile.objects.get(book=book)
        bf.cover_path = str(cover)
        bf.save(update_fields=["cover_path"])
        target = self.target_dir / "book.epub"
        row = safe_move_book(book, str(target))
        self.assertEqual(row.state, FileMove.State.PENDING_DELETION)
        self.assertFalse((self.target_dir / "book.opf").exists())
        self.assertFalse(FileMove.objects.filter(parent=row, db_field=FileMove.DBField.OPF_PATH).exists())

    def test_failing_opf_verify_leaves_original_and_flags_parent(self):
        book, src, sidecar, cover = self._sidecar_book()
        target = self.target_dir / "book.epub"
        with mock.patch("books.utils.safe_move.book.verify_opf_root", return_value=["title"]):
            row = safe_move_book(book, str(target))
        # Main move intact.
        self.assertEqual(row.state, FileMove.State.PENDING_DELETION)
        self.assertFalse(src.exists())
        self.assertTrue(target.is_file())
        # OPF companion failed: original in place, no target, no archive copy.
        self.assertTrue(sidecar.exists())
        self.assertFalse((self.target_dir / "book.opf").exists())
        child = FileMove.objects.get(parent=row, db_field=FileMove.DBField.OPF_PATH)
        self.assertEqual(child.state, FileMove.State.NEEDS_REVIEW)
        self.assertEqual(child.review_flags, ["opf-mismatch:title"])
        self.assertFalse(Path(child.archived_path).exists())
        row.refresh_from_db()
        self.assertIn("companion-failed:book.opf", row.review_flags)

    def test_resolve_move_generated_content_child_every_state(self):
        from books.utils.safe_move import resolve_move
        from books.utils.safe_move.metadata_sync import build_epub_metadata
        from books.utils.safe_move.sidecar_opf import build_sidecar_opf

        book, src, sidecar, cover = self._sidecar_book()
        metadata = build_epub_metadata(book)
        generated = build_sidecar_opf(metadata, cover_name="book.jpg", old_opf_bytes=sidecar.read_bytes())
        original = sidecar.read_bytes()
        target = self.target_dir / "book.opf"
        archive = self.root / "archive" / "book.opf"
        target.parent.mkdir(parents=True, exist_ok=True)
        archive.parent.mkdir(parents=True, exist_ok=True)
        orig_hash = hashlib.sha256(original).hexdigest()
        new_hash = hashlib.sha256(generated).hexdigest()
        bf = BookFile.objects.get(book=book)

        cases = [
            (FileMove.State.PLANNED, "rolled_back"),
            (FileMove.State.TMP_WRITTEN, "rolled_back"),
            (FileMove.State.TMP_VERIFIED, "rolled_back"),
            (FileMove.State.ARCHIVED, "rolled_back"),
            (FileMove.State.COMMITTED, "rolled_back"),
            (FileMove.State.DB_UPDATED, "finalized"),
            (FileMove.State.PENDING_DELETION, "noop"),
        ]
        for state, expected in cases:
            with self.subTest(state=state):
                for p in (target, archive, sidecar):
                    if p.exists():
                        p.unlink()
                sidecar.write_bytes(original)
                if state in (FileMove.State.ARCHIVED, FileMove.State.COMMITTED,
                             FileMove.State.DB_UPDATED, FileMove.State.PENDING_DELETION):
                    archive.write_bytes(original)
                if state in (FileMove.State.COMMITTED, FileMove.State.DB_UPDATED,
                             FileMove.State.PENDING_DELETION):
                    target.write_bytes(generated)
                if state == FileMove.State.PENDING_DELETION:
                    sidecar.unlink()
                bf.opf_path = str(target) if state == FileMove.State.DB_UPDATED else str(sidecar)
                bf.save(update_fields=["opf_path"])
                row = FileMove.objects.create(
                    book=book, kind=FileMove.Kind.COMPANION, db_field=FileMove.DBField.OPF_PATH,
                    source_path=str(sidecar), target_path=str(target), archived_path=str(archive),
                    state=state, original_sha256=orig_hash, archived_sha256=orig_hash, new_sha256=new_hash,
                )
                action = resolve_move(row, apply=True)
                self.assertEqual(action, expected)
                row.refresh_from_db()
                if expected == "rolled_back":
                    self.assertTrue(sidecar.exists())
                    self.assertFalse(target.exists())
                elif expected == "finalized":
                    self.assertFalse(sidecar.exists())
                    self.assertEqual(row.state, FileMove.State.PENDING_DELETION)
                elif expected == "noop":
                    self.assertEqual(row.state, FileMove.State.PENDING_DELETION)
