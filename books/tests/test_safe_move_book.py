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
