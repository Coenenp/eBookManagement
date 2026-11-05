"""Tests for the epub_check package (books/utils/epub_check).

Each rule is exercised against a synthetic EPUB built in-memory with zipfile:
one valid EPUB (must yield zero findings) and one deliberately broken EPUB per
rule (must yield that rule's finding). No binary fixtures are committed.
"""

import io
import json
import shutil
import tempfile
import zipfile
from pathlib import Path

from django.core.management import call_command
from django.test import SimpleTestCase

from books.utils.epub_check import check_epub
from books.utils.epub_check.reader import EpubReader
from books.utils.epub_check.rules import ALL_RULES

MIMETYPE = b"application/epub+zip"


# --------------------------------------------------------------------------- #
# Synthetic EPUB builders
# --------------------------------------------------------------------------- #


def _xhtml(body="<p>Hello</p>", encoding=True, malformed=False):
    decl = '<?xml version="1.0" encoding="utf-8"?>\n' if encoding else ""
    if malformed:
        return (decl + "<html><body><p>unclosed</html>").encode("utf-8")
    return (
        decl
        + '<!DOCTYPE html><html xmlns="http://www.w3.org/1999/xhtml">'
        + "<head><title>t</title></head><body>"
        + body
        + "</body></html>"
    ).encode("utf-8")


def _container(rootfile="OEBPS/content.opf", malformed=False):
    if malformed:
        return b"<container><rootfiles>"
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<container version="1.0" '
        'xmlns="urn:oasis:names:tc:opendocument:xmlns:container">\n'
        "  <rootfiles>\n"
        f'    <rootfile full-path="{rootfile}" '
        'media-type="application/oebps-package+xml"/>\n'
        "  </rootfiles>\n"
        "</container>"
    ).encode("utf-8")


def _opf(items, spine, version="3.0", malformed=False):
    manifest = "".join(
        f'<item id="{i}" href="{h}" media-type="{m}" properties="{p}"/>'
        for (i, h, m, p) in items
    )
    spine_xml = "".join(f'<itemref idref="{s}"/>' for s in spine)
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<package xmlns="http://www.idpf.org/2007/opf" version="{version}" '
        'unique-identifier="uid">\n'
        '  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">\n'
        '    <dc:identifier id="uid">urn:uuid:test</dc:identifier>\n'
        "    <dc:title>Test</dc:title>\n"
        "    <dc:language>en</dc:language>\n"
        '    <meta property="dcterms:modified">2024-01-01T00:00:00Z</meta>\n'
        "  </metadata>\n"
        f"  <manifest>{manifest}</manifest>\n"
        f"  <spine>{spine_xml}</spine>\n"
        "</package>"
    )
    if malformed:
        body = body.replace("</package>", "")
    return body.encode("utf-8")


DEFAULT_ITEMS = [
    ("nav", "nav.xhtml", "application/xhtml+xml", "nav"),
    ("cover", "cover.xhtml", "application/xhtml+xml", ""),
    ("cover-image", "cover.jpg", "image/jpeg", "cover-image"),
    ("c1", "chapter1.xhtml", "application/xhtml+xml", ""),
]
DEFAULT_SPINE = ["cover", "c1"]


def valid_files():
    return {
        "mimetype": MIMETYPE,
        "META-INF/container.xml": _container(),
        "OEBPS/content.opf": _opf(DEFAULT_ITEMS, DEFAULT_SPINE, version="3.0"),
        "OEBPS/nav.xhtml": _xhtml(
            body='<nav xmlns:epub="http://www.idpf.org/2007/ops">'
            '<ol><li><a href="chapter1.xhtml">c1</a></li></ol></nav>'
        ),
        "OEBPS/cover.xhtml": _xhtml(),
        "OEBPS/cover.jpg": b"\xff\xd8\xff\xd9",
        "OEBPS/chapter1.xhtml": _xhtml(),
    }


def write_epub(path, files, order=None, compress=None):
    """Write an EPUB zip. ``order`` controls entry order; ``compress`` maps
    arcname -> compression type (mimetype defaults to STORED)."""
    with zipfile.ZipFile(path, "w") as z:
        names = order if order is not None else list(files.keys())
        for name in names:
            data = files[name]
            ctype = zipfile.ZIP_STORED if name == "mimetype" else zipfile.ZIP_DEFLATED
            if compress and name in compress:
                ctype = compress[name]
            z.writestr(name, data, compress_type=ctype)


def _codes(report):
    return {f.code for f in report.findings}


class EpubCheckTests(SimpleTestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def _path(self, name):
        return Path(self.temp_dir) / name

    def _write(self, name, files, **kwargs):
        p = self._path(name)
        write_epub(p, files, **kwargs)
        return p

    # -- reader ------------------------------------------------------------- #

    def test_reader_exposes_container_opf_manifest_spine_nav(self):
        p = self._write("v.epub", valid_files())
        r = EpubReader(p)
        self.assertEqual(r.opf_path, "OEBPS/content.opf")
        self.assertIsNotNone(r.opf_root)
        self.assertIsNotNone(r.container_root)
        ids = {m["id"] for m in r.manifest}
        self.assertTrue({"nav", "cover", "cover-image", "c1"} <= ids)
        self.assertEqual(r.spine, ["cover", "c1"])
        self.assertEqual(r.version, "3.0")
        self.assertIsNotNone(r.nav_item)

    # -- valid EPUB --------------------------------------------------------- #

    def test_valid_epub_has_no_findings(self):
        p = self._write("valid.epub", valid_files())
        report = check_epub(p)
        self.assertEqual(report.findings, [])
        self.assertTrue(report.ok)

    # -- rule 1: mimetype first + stored ------------------------------------ #

    def test_rule_mimetype_not_first(self):
        files = valid_files()
        order = [n for n in files if n != "mimetype"] + ["mimetype"]
        p = self._write("bad.epub", files, order=order)
        self.assertIn("MIMETYPE-001", _codes(check_epub(p)))

    def test_rule_mimetype_compressed(self):
        p = self._write("bad.epub", valid_files(), compress={"mimetype": zipfile.ZIP_DEFLATED})
        self.assertIn("MIMETYPE-001", _codes(check_epub(p)))

    # -- rule 2: container.xml --------------------------------------------- #

    def test_rule_container_missing(self):
        files = valid_files()
        del files["META-INF/container.xml"]
        p = self._write("bad.epub", files)
        self.assertIn("CONTAINER-001", _codes(check_epub(p)))

    def test_rule_container_malformed(self):
        files = valid_files()
        files["META-INF/container.xml"] = _container(malformed=True)
        p = self._write("bad.epub", files)
        self.assertIn("CONTAINER-001", _codes(check_epub(p)))

    # -- rule 3: OPF -------------------------------------------------------- #

    def test_rule_opf_malformed(self):
        files = valid_files()
        files["OEBPS/content.opf"] = _opf(DEFAULT_ITEMS, DEFAULT_SPINE, malformed=True)
        p = self._write("bad.epub", files)
        self.assertIn("OPF-001", _codes(check_epub(p)))

    def test_rule_opf_missing_from_container(self):
        files = valid_files()
        files["META-INF/container.xml"] = _container(rootfile="OEBPS/nope.opf")
        p = self._write("bad.epub", files)
        self.assertIn("OPF-001", _codes(check_epub(p)))

    # -- rule 4: manifest items exist --------------------------------------- #

    def test_rule_manifest_missing_file(self):
        files = valid_files()
        items = DEFAULT_ITEMS + [("ghost", "ghost.xhtml", "application/xhtml+xml", "")]
        files["OEBPS/content.opf"] = _opf(items, DEFAULT_SPINE)
        p = self._write("bad.epub", files)
        self.assertIn("OPF-002", _codes(check_epub(p)))

    # -- rule 5: spine ids in manifest -------------------------------------- #

    def test_rule_spine_unknown_id(self):
        files = valid_files()
        files["OEBPS/content.opf"] = _opf(DEFAULT_ITEMS, ["cover", "ghost"])
        p = self._write("bad.epub", files)
        self.assertIn("OPF-003", _codes(check_epub(p)))

    # -- rule 6: nav for EPUB 3 --------------------------------------------- #

    def test_rule_nav_missing_epub3(self):
        files = valid_files()
        items = [it for it in DEFAULT_ITEMS if it[0] != "nav"]
        files["OEBPS/content.opf"] = _opf(items, DEFAULT_SPINE, version="3.0")
        p = self._write("bad.epub", files)
        self.assertIn("OPF-004", _codes(check_epub(p)))

    # -- rule 7: cover declared + present ----------------------------------- #

    def test_rule_cover_declared_but_missing(self):
        files = valid_files()
        del files["OEBPS/cover.jpg"]
        p = self._write("bad.epub", files)
        self.assertIn("OPF-005", _codes(check_epub(p)))

    # -- rule 8: media types match extensions ------------------------------- #

    def test_rule_media_type_mismatch(self):
        files = valid_files()
        items = [("c1", "chapter1.xhtml", "image/jpeg", "")] + [
            it for it in DEFAULT_ITEMS if it[0] != "c1"
        ]
        files["OEBPS/content.opf"] = _opf(items, DEFAULT_SPINE)
        p = self._write("bad.epub", files)
        self.assertIn("OPF-006", _codes(check_epub(p)))

    # -- rule 9: XHTML well formed ------------------------------------------ #

    def test_rule_xhtml_malformed(self):
        files = valid_files()
        files["OEBPS/chapter1.xhtml"] = _xhtml(malformed=True)
        p = self._write("bad.epub", files)
        self.assertIn("HTM-001", _codes(check_epub(p)))

    # -- rule 10: encoding declared ----------------------------------------- #

    def test_rule_encoding_missing(self):
        files = valid_files()
        files["OEBPS/chapter1.xhtml"] = _xhtml(encoding=False)
        p = self._write("bad.epub", files)
        self.assertIn("HTM-002", _codes(check_epub(p)))

    # -- report / registry -------------------------------------------------- #

    def test_report_json_roundtrip(self):
        files = valid_files()
        order = [n for n in files if n != "mimetype"] + ["mimetype"]
        p = self._write("bad.epub", files, order=order)
        report = check_epub(p)
        data = json.loads(report.to_json())
        self.assertEqual(data["file"], str(p))
        self.assertFalse(data["ok"])
        self.assertTrue(any(f["code"] == "MIMETYPE-001" for f in data["findings"]))
        self.assertTrue(
            all("code" in f and "severity" in f and "message" in f for f in data["findings"])
        )

    def test_rule_registry_is_populated(self):
        self.assertGreaterEqual(len(ALL_RULES), 10)
        codes = {r.code for r in ALL_RULES}
        self.assertTrue(
            {
                "MIMETYPE-001",
                "CONTAINER-001",
                "OPF-001",
                "OPF-002",
                "OPF-003",
                "OPF-004",
                "OPF-005",
                "OPF-006",
                "HTM-001",
                "HTM-002",
            }
            <= codes
        )

    # -- management command -------------------------------------------------- #

    def test_management_command_single_file_json(self):
        files = valid_files()
        order = [n for n in files if n != "mimetype"] + ["mimetype"]
        p = self._write("bad.epub", files, order=order)
        out = io.StringIO()
        call_command("epub_check", str(p), json=True, stdout=out)
        data = json.loads(out.getvalue())
        self.assertFalse(data["ok"])

    def test_management_command_folder(self):
        good = self._path("good.epub")
        write_epub(good, valid_files())
        out = io.StringIO()
        call_command("epub_check", self.temp_dir, stdout=out)
        self.assertIn("good.epub", out.getvalue())
