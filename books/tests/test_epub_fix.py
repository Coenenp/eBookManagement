"""Tests for the epub_fix package (books/utils/epub_fix).

Every EPUB is built in-code with zipfile (no binary fixtures). For each fix rule
we assert the lossless contract: the broken input is fixed, the checker stops
reporting that code, untouched entries stay byte-identical, the input hash is
unchanged, a second run changes nothing, and the output path differs from input.
"""

import hashlib
import io
import shutil
import tempfile
import zipfile
from pathlib import Path
from unittest import mock

from django.core.management import call_command
from django.test import SimpleTestCase

from books.utils.epub_check import check_epub
from books.utils.epub_fix import fix_epub, plan_fixes, write_epub

MIMETYPE = b"application/epub+zip"

NO_DECL_XHTML = (
    b'<html xmlns="http://www.w3.org/1999/xhtml">'
    b"<head><title>t</title></head><body><p>x</p></body></html>"
)


def _xhtml(body="<p>Hello</p>", encoding=True):
    decl = '<?xml version="1.0" encoding="utf-8"?>\n' if encoding else ""
    return (
        decl
        + '<!DOCTYPE html><html xmlns="http://www.w3.org/1999/xhtml">'
        + "<head><title>t</title></head><body>"
        + body
        + "</body></html>"
    ).encode("utf-8")


def _container(rootfile="OEBPS/content.opf"):
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<container version="1.0" '
        'xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
        '<rootfiles><rootfile full-path="'
        + rootfile
        + '" media-type="application/oebps-package+xml"/></rootfiles></container>'
    ).encode("utf-8")


def _opf(items, spine, version="2.0"):
    manifest = "".join(
        f'<item id="{i}" href="{h}" media-type="{m}" properties="{p}"/>'
        for (i, h, m, p) in items
    )
    spine_xml = "".join(f'<itemref idref="{s}"/>' for s in spine)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<package xmlns="http://www.idpf.org/2007/opf" version="{version}" '
        'unique-identifier="uid">'
        '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
        '<dc:identifier id="uid">urn:uuid:test</dc:identifier>'
        "<dc:title>Test</dc:title><dc:language>en</dc:language></metadata>"
        f"<manifest>{manifest}</manifest>"
        f"<spine>{spine_xml}</spine></package>"
    ).encode("utf-8")


DEFAULT_ITEMS = [
    ("cover", "cover.xhtml", "application/xhtml+xml", ""),
    ("cover-image", "cover.jpg", "image/jpeg", "cover-image"),
    ("c1", "chapter1.xhtml", "application/xhtml+xml", ""),
]
DEFAULT_SPINE = ["cover", "c1"]


def valid_files():
    return {
        "mimetype": MIMETYPE,
        "META-INF/container.xml": _container(),
        "OEBPS/content.opf": _opf(DEFAULT_ITEMS, DEFAULT_SPINE),
        "OEBPS/cover.xhtml": _xhtml(),
        "OEBPS/cover.jpg": b"\xff\xd8\xff\xd9",
        "OEBPS/chapter1.xhtml": _xhtml(),
    }


def _write_zip(path, files, order=None, compress=None):
    with zipfile.ZipFile(path, "w") as z:
        names = order if order is not None else list(files.keys())
        for name in names:
            data = files[name]
            ctype = zipfile.ZIP_STORED if name == "mimetype" else zipfile.ZIP_DEFLATED
            if compress and name in compress:
                ctype = compress[name]
            z.writestr(name, data, compress_type=ctype)


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _codes(report):
    return {f.code for f in report.findings}


def _entry_hashes(path):
    with zipfile.ZipFile(path) as z:
        return {n: hashlib.sha256(z.read(n)).hexdigest() for n in z.namelist()}


class EpubFixTests(SimpleTestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def _path(self, name):
        return Path(self.temp_dir) / name

    def _write(self, name, files, **kwargs):
        p = self._path(name)
        _write_zip(p, files, **kwargs)
        return p

    def _assert_lossless(self, files, code, *, order=None, compress=None, changed=()):
        src = self._write("in.epub", files, order=order, compress=compress)
        src_hash = _sha256(src)
        before = _entry_hashes(src)
        out = Path(fix_epub(src))
        self.assertNotEqual(out.resolve(), src.resolve())
        self.assertEqual(_sha256(src), src_hash)
        self.assertNotIn(code, _codes(check_epub(out)))
        after = _entry_hashes(out)
        for name, h in before.items():
            if name not in changed:
                self.assertEqual(after.get(name), h, f"{name} should be byte-identical")
        self.assertEqual(plan_fixes(out), [])

    # -- MIMETYPE-001 ---------------------------------------------------------

    def test_mimetype_repacked_first_and_stored(self):
        files = valid_files()
        order = [n for n in files if n != "mimetype"] + ["mimetype"]
        self._assert_lossless(files, "MIMETYPE-001", order=order)

    def test_mimetype_compressed_repaired(self):
        files = valid_files()
        self._assert_lossless(files, "MIMETYPE-001", compress={"mimetype": zipfile.ZIP_DEFLATED})

    # -- OPF-003 --------------------------------------------------------------

    def test_opf003_drops_unknown_spine_idref(self):
        files = valid_files()
        files["OEBPS/content.opf"] = _opf(DEFAULT_ITEMS, DEFAULT_SPINE + ["ghost"])
        self._assert_lossless(files, "OPF-003", changed=("OEBPS/content.opf",))

    # -- OPF-002 --------------------------------------------------------------

    def test_opf002_drops_unreferenced_missing_manifest_item(self):
        files = valid_files()
        items = DEFAULT_ITEMS + [("ghost", "ghost.xhtml", "application/xhtml+xml", "")]
        files["OEBPS/content.opf"] = _opf(items, DEFAULT_SPINE)
        self._assert_lossless(files, "OPF-002", changed=("OEBPS/content.opf",))

    def test_opf002_keeps_spine_referenced_missing_item(self):
        files = valid_files()
        items = DEFAULT_ITEMS + [("ghost", "ghost.xhtml", "application/xhtml+xml", "")]
        files["OEBPS/content.opf"] = _opf(items, DEFAULT_SPINE + ["ghost"])
        src = self._write("in.epub", files)
        out = Path(fix_epub(src))
        self.assertIn("OPF-002", _codes(check_epub(out)))
        with zipfile.ZipFile(out) as z:
            opf = z.read("OEBPS/content.opf").decode("utf-8")
        self.assertIn('id="ghost"', opf)

    # -- OPF-006 --------------------------------------------------------------

    def test_opf006_corrects_media_type(self):
        files = valid_files()
        items = [("c1", "chapter1.xhtml", "image/jpeg", "")] + [
            it for it in DEFAULT_ITEMS if it[0] != "c1"
        ]
        files["OEBPS/content.opf"] = _opf(items, DEFAULT_SPINE)
        self._assert_lossless(files, "OPF-006", changed=("OEBPS/content.opf",))

    # -- HTM-002 --------------------------------------------------------------

    def test_htm002_adds_encoding_declaration(self):
        files = valid_files()
        files["OEBPS/chapter1.xhtml"] = NO_DECL_XHTML
        self._assert_lossless(files, "HTM-002", changed=("OEBPS/chapter1.xhtml",))

    # -- writer ---------------------------------------------------------------

    def test_writer_mimetype_first_stored_rest_deflated(self):
        files = valid_files()
        order = [n for n in files if n != "mimetype"] + ["mimetype"]
        src = self._write("in.epub", files, order=order)
        out = Path(fix_epub(src))
        with zipfile.ZipFile(out) as z:
            infos = z.infolist()
            self.assertEqual(infos[0].filename, "mimetype")
            self.assertEqual(infos[0].compress_type, zipfile.ZIP_STORED)
            for info in infos[1:]:
                self.assertEqual(info.compress_type, zipfile.ZIP_DEFLATED)

    def test_writer_removes_part_file_on_failure(self):
        src = self._write("s.epub", valid_files())
        out = self._path("out.epub")
        with mock.patch("books.utils.epub_fix.writer.os.replace", side_effect=OSError("boom")):
            with self.assertRaises(OSError):
                write_epub(src, out)
        self.assertFalse(Path(str(out) + ".part").exists())
        self.assertFalse(out.exists())

    # -- cover ----------------------------------------------------------------

    def _cover_file(self, name="cover.jpg", data=b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\xff\xd9"):
        p = self._path(name)
        p.write_bytes(data)
        return p

    def test_cover_embedded_and_opf005_gone(self):
        files = valid_files()
        items = [it for it in DEFAULT_ITEMS if it[0] != "cover-image"]
        files["OEBPS/content.opf"] = _opf(items, DEFAULT_SPINE)
        del files["OEBPS/cover.jpg"]
        src = self._write("in.epub", files)
        self.assertIn("OPF-005", _codes(check_epub(src)))
        cover = self._cover_file("new.jpg")
        out = Path(fix_epub(src, cover=str(cover)))
        self.assertNotIn("OPF-005", _codes(check_epub(out)))
        with zipfile.ZipFile(out) as z:
            self.assertIn("OEBPS/cover.jpg", z.namelist())
            opf = z.read("OEBPS/content.opf").decode("utf-8")
        self.assertIn('properties="cover-image"', opf)
        self.assertIn('name="cover"', opf)

    def test_cover_replaces_declared_cover(self):
        files = valid_files()
        src = self._write("in.epub", files)
        cover = self._cover_file("new.png", data=b"\x89PNG\r\n\x1a\n")
        out = Path(fix_epub(src, cover=str(cover)))
        with zipfile.ZipFile(out) as z:
            names = z.namelist()
            self.assertIn("OEBPS/cover.png", names)
            self.assertNotIn("OEBPS/cover.jpg", names)

    def test_cover_refuses_non_image(self):
        src = self._write("in.epub", valid_files())
        txt = self._path("cover.txt")
        txt.write_text("not an image")
        with self.assertRaises(ValueError):
            fix_epub(src, cover=str(txt))
        self.assertEqual(list(Path(self.temp_dir).glob("*_fixed.epub")), [])

    def test_cover_refuses_unreadable(self):
        src = self._write("in.epub", valid_files())
        with self.assertRaises(ValueError):
            fix_epub(src, cover=str(self._path("missing.jpg")))
        self.assertEqual(list(Path(self.temp_dir).glob("*_fixed.epub")), [])

    # -- path safety ----------------------------------------------------------

    def test_fix_epub_refuses_equal_output_path(self):
        src = self._write("in.epub", valid_files())
        with self.assertRaises(ValueError):
            fix_epub(src, output_path=str(src))

    def test_output_path_differs_from_input(self):
        src = self._write("in.epub", valid_files())
        out = fix_epub(src)
        self.assertNotEqual(Path(out).resolve(), src.resolve())
        self.assertEqual(Path(out).name, "in_fixed.epub")

    # -- command --------------------------------------------------------------

    def test_command_apply_writes_fixed_name(self):
        files = valid_files()
        order = [n for n in files if n != "mimetype"] + ["mimetype"]
        src = self._write("book.epub", files, order=order)
        call_command("epub_fix", str(src), apply=True, output_dir=self.temp_dir)
        out = self._path("book_fixed.epub")
        self.assertTrue(out.exists())
        self.assertNotIn("MIMETYPE-001", _codes(check_epub(out)))

    def test_command_plan_only_without_apply(self):
        files = valid_files()
        order = [n for n in files if n != "mimetype"] + ["mimetype"]
        src = self._write("book.epub", files, order=order)
        out = io.StringIO()
        call_command("epub_fix", str(src), stdout=out)
        self.assertIn("Plan for", out.getvalue())
        self.assertFalse(self._path("book_fixed.epub").exists())
