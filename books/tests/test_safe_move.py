"""Tests for the safe_move package (books/utils/safe_move).

Every EPUB is built in-code with zipfile (no binary fixtures). Archive helpers
are tested for mirrored structure, refusals and collision suffixes; the move
routine is tested for each check, crash recovery and rollback.
"""

import hashlib
import shutil
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from unittest import mock

from django.test import SimpleTestCase, override_settings

from books.utils.safe_move import (
    MoveResult,
    NeedsReview,
    finalize_move,
    rollback_move,
    safe_move_file,
)
from books.utils.safe_move.archive import archive_destination, default_archive_root

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


def _opf(items, spine):
    manifest = "".join(
        f'<item id="{i}" href="{h}" media-type="{m}" properties="{p}"/>'
        for (i, h, m, p) in items
    )
    spine_xml = "".join(f'<itemref idref="{s}"/>' for s in spine)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="uid">'
        '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
        '<dc:identifier id="uid">urn:uuid:test</dc:identifier>'
        "<dc:title>Test</dc:title><dc:language>en</dc:language></metadata>"
        f"<manifest>{manifest}</manifest><spine>{spine_xml}</spine></package>"
    ).encode("utf-8")


def _xhtml():
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>t</title></head>'
        "<body><p>x</p></body></html>"
    ).encode("utf-8")


def _make_epub(path, mimetype="first", items=None, spine=None, chapter=None):
    items = items or [("c1", "chapter1.xhtml", "application/xhtml+xml", "")]
    spine = spine or ["c1"]
    files = {
        "mimetype": MIMETYPE,
        "META-INF/container.xml": _container(),
        "OEBPS/content.opf": _opf(items, spine),
        "OEBPS/chapter1.xhtml": _xhtml() if chapter is None else chapter,
    }
    with zipfile.ZipFile(path, "w") as z:
        names = ["mimetype"] + [n for n in files if n != "mimetype"]
        if mimetype != "first":
            names = [n for n in files if n != "mimetype"] + ["mimetype"]
        for n in names:
            z.writestr(n, files[n], compress_type=zipfile.ZIP_STORED if n == "mimetype" else zipfile.ZIP_DEFLATED)


class ArchiveHelperTests(SimpleTestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, str(self.root), ignore_errors=True)
        self.scan_root = self.root / "lib"
        self.scan_root.mkdir()

    def test_default_archive_root_sibling(self):
        self.assertEqual(
            default_archive_root(str(self.scan_root)),
            str(self.scan_root.parent / "Archive [To Delete]"),
        )

    @override_settings(ARCHIVE_ROOT="/custom/archive")
    def test_default_archive_root_from_settings(self):
        self.assertEqual(default_archive_root(str(self.scan_root)), "/custom/archive")

    def test_mirrored_structure(self):
        src = self.scan_root / "sub" / "dir" / "book.epub"
        src.parent.mkdir(parents=True)
        src.write_bytes(b"x")
        dest = archive_destination(str(src), str(self.scan_root), "Sample [To Delete] 1", str(self.root / "archive"))
        self.assertEqual(
            Path(dest),
            self.root / "archive" / "Sample [To Delete] 1" / "sub" / "dir" / "book.epub",
        )

    def test_refuses_source_outside_scan_root(self):
        src = self.root / "outside.epub"
        src.write_bytes(b"x")
        with self.assertRaises(ValueError):
            archive_destination(str(src), str(self.scan_root), "label", str(self.root / "archive"))

    def test_refuses_symlink_escape(self):
        outside = self.root / "outside.epub"
        outside.write_bytes(b"secret")
        link = self.scan_root / "link.epub"
        link.symlink_to(outside)
        with self.assertRaises(ValueError):
            archive_destination(str(link), str(self.scan_root), "label", str(self.root / "archive"))

    def test_refuses_archive_root_inside_scan_root(self):
        src = self.scan_root / "book.epub"
        src.write_bytes(b"x")
        inside = self.scan_root / "archive"
        with self.assertRaises(ValueError):
            archive_destination(str(src), str(self.scan_root), "label", str(inside))

    def test_collision_suffix_timestamp(self):
        src = self.scan_root / "book.epub"
        src.write_bytes(b"x")
        archive_root = self.root / "archive"
        base = archive_root / "label" / "book.epub"
        base.parent.mkdir(parents=True)
        base.write_bytes(b"existing")
        dest = archive_destination(str(src), str(self.scan_root), "label", str(archive_root))
        self.assertNotEqual(Path(dest), base)
        self.assertIn("(archived ", Path(dest).stem)
        self.assertFalse(Path(dest).exists())

    def test_collision_counter(self):
        src = self.scan_root / "book.epub"
        src.write_bytes(b"x")
        archive_root = self.root / "archive"
        base = archive_root / "label" / "book.epub"
        base.parent.mkdir(parents=True)
        base.write_bytes(b"a")
        stamped = base.with_name("book(archived 20261106T120000).epub")
        stamped.write_bytes(b"b")
        stamped2 = base.with_name("book(archived 20261106T120000)-2.epub")
        stamped2.write_bytes(b"c")

        class FakeDT:
            @staticmethod
            def now():
                return datetime(2026, 11, 6, 12, 0, 0)

        with mock.patch("books.utils.safe_move.archive.datetime", FakeDT):
            dest = archive_destination(str(src), str(self.scan_root), "label", str(archive_root))
        self.assertEqual(Path(dest), base.with_name("book(archived 20261106T120000)-3.epub"))


class SafeMoveRoutineTests(SimpleTestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, str(self.root), ignore_errors=True)
        self.scan_root = self.root / "lib"
        self.scan_root.mkdir()
        self.archive_root = self.root / "Archive [To Delete]"
        self.scan_label = "Sample [To Delete] 1"
        self.target_dir = self.root / "Moved"

    def _src(self, name="sub/book.txt", data=b"hello world"):
        p = self.scan_root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        return p

    def _target(self, name="book.txt"):
        return self.target_dir / name

    def _move(self, source, target, **kw):
        return safe_move_file(
            str(source), str(target), scan_root=str(self.scan_root),
            scan_label=self.scan_label, archive_root=str(self.archive_root), **kw,
        )

    # -- success / finalize --------------------------------------------------

    def test_move_pdf_like_file_and_finalize(self):
        src = self._src("docs/report.pdf", data=b"%PDF-1.4 fake pdf bytes")
        tgt = self._target("report.pdf")
        src_hash = _sha256(src)
        result = self._move(src, tgt)
        self.assertTrue(result.repacked is False)
        self.assertEqual(result.original_sha256, src_hash)
        self.assertEqual(result.archived_sha256, src_hash)
        self.assertTrue(Path(result.archived_path).is_file())
        self.assertTrue(tgt.exists())
        self.assertTrue(src.exists())

        finalize_move(result)
        self.assertFalse(src.exists())
        self.assertTrue(tgt.exists())
        self.assertTrue(Path(result.archived_path).is_file())

    def test_move_cbz(self):
        src = self.scan_root / "comic.cbz"
        src.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(src, "w") as z:
            z.writestr("page1.jpg", b"\xff\xd8\xff\xd9")
        tgt = self._target("comic.cbz")
        result = self._move(src, tgt)
        self.assertEqual(result.review_flags, [])
        self.assertTrue(tgt.exists())

    def test_move_epub_repacked(self):
        src = self.scan_root / "book.epub"
        src.parent.mkdir(parents=True, exist_ok=True)
        _make_epub(src)
        tgt = self._target("book.epub")
        result = self._move(src, tgt)
        self.assertTrue(result.repacked)
        # no cover in this minimal EPUB -> a non-blocking OPF-005 flag only.
        self.assertEqual(result.review_flags, ["OPF-005"])
        self.assertTrue(tgt.exists())

    def test_move_epub_flags_malformed_xhtml_not_blocking(self):
        src = self.scan_root / "book.epub"
        src.parent.mkdir(parents=True, exist_ok=True)
        _make_epub(src, chapter=b"<html><body><p>unclosed")
        tgt = self._target("book.epub")
        result = self._move(src, tgt)
        self.assertIn("HTM-001", result.review_flags)
        self.assertTrue(tgt.exists())

    # -- refusals ------------------------------------------------------------

    def test_refuses_missing_source(self):
        with self.assertRaises(FileNotFoundError):
            self._move(self.scan_root / "missing.txt", self._target())

    def test_refuses_target_equals_source(self):
        src = self._src()
        with self.assertRaises(ValueError):
            self._move(src, src)

    def test_refuses_existing_target(self):
        src = self._src()
        tgt = self._target()
        tgt.parent.mkdir(parents=True)
        tgt.write_bytes(b"already here")
        with self.assertRaises(FileExistsError):
            self._move(src, tgt)

    # -- check A: empty temp -------------------------------------------------

    def test_check_a_empty_temp_needs_review(self):
        src = self._src("empty.txt", data=b"")
        tgt = self._target("empty.txt")
        with self.assertRaises(NeedsReview) as ctx:
            self._move(src, tgt)
        self.assertIn("empty", ctx.exception.codes)
        self.assertFalse(tgt.exists())
        self.assertFalse(Path(str(tgt) + ".moving").exists())

    # -- check B: epub blocking / zip corrupt / non-epub hash -----------------

    def test_check_b_epub_blocking_container(self):
        # An EPUB the fixer cannot repair (no container.xml -> CONTAINER-001)
        # must raise NeedsReview and leave nothing behind.
        src = self.scan_root / "book.epub"
        src.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(src, "w") as z:
            z.writestr("mimetype", MIMETYPE, compress_type=zipfile.ZIP_STORED)
            z.writestr("OEBPS/chapter1.xhtml", _xhtml(), compress_type=zipfile.ZIP_DEFLATED)
        tgt = self._target("book.epub")
        with self.assertRaises(NeedsReview) as ctx:
            self._move(src, tgt)
        self.assertIn("CONTAINER-001", ctx.exception.codes)
        self.assertFalse(tgt.exists())

    def test_check_b_zip_corrupt(self):
        src = self.scan_root / "bad.cbz"
        src.parent.mkdir(parents=True, exist_ok=True)
        src.write_bytes(b"not a zip at all")
        tgt = self._target("bad.cbz")
        with self.assertRaises(NeedsReview) as ctx:
            self._move(src, tgt)
        self.assertIn("zip-corrupt", ctx.exception.codes)

    def test_check_b_non_epub_hash_mismatch(self):
        src = self._src(data=b"original bytes")
        tgt = self._target()
        with mock.patch("books.utils.safe_move.routine.shutil.copy2") as cp:
            def fake_copy(s, d, **kw):
                Path(d).write_bytes(b"wrong bytes")
            cp.side_effect = fake_copy
            with self.assertRaises(NeedsReview) as ctx:
                self._move(src, tgt)
        self.assertIn("hash-mismatch", ctx.exception.codes)
        self.assertFalse(tgt.exists())

    # -- check D: archive hash ------------------------------------------------

    def test_check_d_archive_hash_mismatch(self):
        src = self.scan_root / "book.epub"
        src.parent.mkdir(parents=True, exist_ok=True)
        _make_epub(src)
        tgt = self._target("book.epub")
        real_copy2 = shutil.copy2
        calls = []

        def fake_copy2(s, d, **kw):
            calls.append(str(d))
            if str(d).endswith(".moving"):
                return real_copy2(s, d, **kw)
            # corrupt the archive copy
            Path(d).write_bytes(b"corrupt archive")
            return d

        with mock.patch("books.utils.safe_move.routine.shutil.copy2", side_effect=fake_copy2):
            with self.assertRaises(NeedsReview) as ctx:
                self._move(src, tgt)
        self.assertIn("archive-hash", ctx.exception.codes)
        self.assertFalse(tgt.exists())

    # -- rollback -------------------------------------------------------------

    def test_rollback_removes_target_and_archive_leaves_source(self):
        src = self._src(data=b"keep me")
        src_hash = _sha256(src)
        tgt = self._target()
        result = self._move(src, tgt)
        rollback_move(result)
        self.assertTrue(src.exists())
        self.assertEqual(_sha256(src), src_hash)
        self.assertFalse(tgt.exists())
        self.assertFalse(Path(result.archived_path).exists())
        self.assertFalse(Path(result.tmp_path).exists())
        self.assertFalse(Path(result.tmp_path + ".part").exists())

    # -- crash injection per step --------------------------------------------

    def test_crash_injection_each_step(self):
        for step in ("planned", "tmp_written", "tmp_verified", "archived", "committed"):
            with self.subTest(step=step):
                src = self._src("sub/book.txt", data=b"crash test bytes")
                src_hash = _sha256(src)
                tgt = self._target("book.txt")
                captured = {}

                def on_step(name, state):
                    captured.update(state)
                    if name == step:
                        raise RuntimeError("crash at " + name)

                with self.assertRaises(RuntimeError):
                    self._move(src, tgt, on_step=on_step)

                # source is intact with its original hash at every point.
                self.assertTrue(src.exists())
                self.assertEqual(_sha256(src), src_hash)

                if step == "committed":
                    # target, source and archive copy all exist before rollback.
                    self.assertTrue(tgt.exists())
                    self.assertTrue(Path(captured["archived_path"]).exists())
                    self.assertTrue(src.exists())

                result = MoveResult(
                    source=captured["source"],
                    target=captured["target"],
                    archived_path=captured["archived_path"],
                    original_sha256=captured["original_sha256"],
                    archived_sha256=captured.get("archived_sha256") or "",
                    new_sha256="",
                    repacked=captured.get("repacked", False),
                    review_flags=captured.get("review_flags", []),
                    created_target=captured.get("created_target", False),
                    tmp_path=captured["tmp"],
                )
                rollback_move(result)

                # source still intact, no temp file remains.
                self.assertTrue(src.exists())
                self.assertEqual(_sha256(src), src_hash)
                self.assertFalse(Path(captured["tmp"]).exists())
                self.assertFalse(Path(captured["tmp"] + ".part").exists())
                self.assertFalse(tgt.exists())
                self.assertFalse(Path(captured["archived_path"]).exists())

    # -- finalize re-verification --------------------------------------------

    def test_finalize_refuses_when_archive_missing(self):
        src = self._src(data=b"data")
        tgt = self._target()
        result = self._move(src, tgt)
        Path(result.archived_path).unlink()
        with self.assertRaises(NeedsReview):
            finalize_move(result)
        self.assertTrue(src.exists())

    def test_finalize_refuses_when_target_missing(self):
        src = self._src(data=b"data")
        tgt = self._target()
        result = self._move(src, tgt)
        tgt.unlink()
        with self.assertRaises(NeedsReview):
            finalize_move(result)
        self.assertTrue(src.exists())
