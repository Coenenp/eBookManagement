"""Tests for the EPUB cover-page rewrite (books/utils/epub_fix/cover_page.py).

Every EPUB is built in code with ``zipfile`` (no binary fixtures). The pure
functions (``find_cover_page``, ``classify_cover_page``, ``rewrite_cover_page``,
``relative_href``) are exercised directly, and the wiring through ``_compute``
is exercised with real EPUBs and a cover image on disk.
"""

import hashlib
import posixpath
import shutil
import tempfile
import zipfile
from pathlib import Path

from django.test import SimpleTestCase
from lxml import etree as ET

from books.utils.epub_fix import cover_page as cp
from books.utils.epub_fix.fixer import _compute
from books.utils.epub_fix.writer import write_epub

MIMETYPE = b"application/epub+zip"


def _container(rootfile="OEBPS/content.opf"):
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
        f'<rootfiles><rootfile full-path="{rootfile}" media-type="application/oebps-package+xml"/></rootfiles>'
        "</container>"
    ).encode("utf-8")


def _write_zip(path, files):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("mimetype", MIMETYPE, compress_type=zipfile.ZIP_STORED)
        order = ["META-INF/container.xml"] + [n for n in files if n != "META-INF/container.xml"]
        for n in order:
            z.writestr(n, files[n], compress_type=zipfile.ZIP_DEFLATED)


def _pure_img_page(ref, wrapper="div"):
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>c</title></head>'
        f'<body><{wrapper}><img src="{ref}" alt="cover"/></{wrapper}></body></html>'
    ).encode("utf-8")


def _svg_page(ref):
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>c</title></head><body>'
        '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
        'width="100%" height="100%" viewBox="0 0 600 800">'
        f'<image width="600" height="800" xlink:href="{ref}"/></svg>'
        "</body></html>"
    ).encode("utf-8")


def _text_page():
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>c</title></head>'
        '<body><div><img src="images/cover.jpg" alt="cover"/></div><p>Chapter One</p></body></html>'
    ).encode("utf-8")


def _two_image_page():
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>c</title></head>'
        '<body><div><img src="images/cover.jpg"/><img src="images/back.jpg"/></div></body></html>'
    ).encode("utf-8")


class CoverPageUnitTests(SimpleTestCase):
    def test_classify_pure_img(self):
        kind, ref = cp.classify_cover_page(_pure_img_page("images/cover.jpg"))
        self.assertEqual((kind, ref), ("pure", "images/cover.jpg"))

    def test_classify_svg_wrapper(self):
        kind, ref = cp.classify_cover_page(_svg_page("images/cover.jpg"))
        self.assertEqual((kind, ref), ("pure", "images/cover.jpg"))

    def test_classify_text_page_not_pure(self):
        kind, ref = cp.classify_cover_page(_text_page())
        self.assertEqual((kind, ref), ("not-pure", None))

    def test_classify_two_images_not_pure(self):
        kind, ref = cp.classify_cover_page(_two_image_page())
        self.assertEqual((kind, ref), ("not-pure", None))

    def test_classify_garbage_not_pure(self):
        kind, ref = cp.classify_cover_page(b"not xml at all")
        self.assertEqual((kind, ref), ("not-pure", None))

    def test_rewrite_replaces_single_occurrence(self):
        page = _pure_img_page("images/cover.jpg")
        out = cp.rewrite_cover_page(page, "images/cover.jpg", "cover.jpg")
        self.assertIsNotNone(out)
        self.assertNotIn(b"images/cover.jpg", out)
        self.assertEqual(out.count(b'cover.jpg'), 1)

    def test_rewrite_refuses_multiple_occurrences(self):
        page = (
            b'<html xmlns="http://www.w3.org/1999/xhtml"><body>'
            b'<img src="images/cover.jpg"/><img src="images/cover.jpg"/></body></html>'
        )
        self.assertIsNone(cp.rewrite_cover_page(page, "images/cover.jpg", "cover.jpg"))

    def test_rewrite_refuses_absent(self):
        page = _pure_img_page("images/other.jpg")
        self.assertIsNone(cp.rewrite_cover_page(page, "images/cover.jpg", "cover.jpg"))

    def test_rewrite_only_substitutes_the_value(self):
        page = b'<div id="x">PREFIX</div><img src="images/cover.jpg" alt="c"/>'
        out = cp.rewrite_cover_page(page, "images/cover.jpg", "cover.jpg")
        # only the single attribute value is replaced; surrounding bytes identical
        self.assertEqual(out, b'<div id="x">PREFIX</div><img src="cover.jpg" alt="c"/>')

    def test_relative_href_up_one_level(self):
        self.assertEqual(cp.relative_href("OEBPS/text/cover.xhtml", "OEBPS/images/cover.jpg"), "../images/cover.jpg")

    def test_relative_href_same_dir(self):
        self.assertEqual(cp.relative_href("OEBPS/cover.xhtml", "OEBPS/cover.jpg"), "cover.jpg")

    def test_find_cover_page_first_spine_item(self):
        opf = (
            '<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf" version="2.0">'
            '<manifest><item id="c" href="cover.xhtml" media-type="application/xhtml+xml"/>'
            '<item id="i" href="images/cover.jpg" media-type="image/jpeg"/></manifest>'
            '<spine><itemref idref="c"/></spine></package>'
        ).encode("utf-8")
        root = ET.fromstring(opf, cp._PAGE_PARSER)
        entries = {"OEBPS/cover.xhtml": b"x", "OEBPS/images/cover.jpg": b"i"}
        self.assertEqual(cp.find_cover_page(root, "OEBPS/content.opf", entries), "OEBPS/cover.xhtml")

    def test_find_cover_page_guide_overrides_spine(self):
        opf = (
            '<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf" version="2.0">'
            '<manifest><item id="ch" href="chapter1.xhtml" media-type="application/xhtml+xml"/>'
            '<item id="cv" href="cover.xhtml" media-type="application/xhtml+xml"/></manifest>'
            '<spine><itemref idref="ch"/><itemref idref="cv"/></spine>'
            '<guide><reference type="cover" href="cover.xhtml"/></guide></package>'
        ).encode("utf-8")
        root = ET.fromstring(opf, cp._PAGE_PARSER)
        entries = {"OEBPS/chapter1.xhtml": b"x", "OEBPS/cover.xhtml": b"c"}
        self.assertEqual(cp.find_cover_page(root, "OEBPS/content.opf", entries), "OEBPS/cover.xhtml")


class CoverPageComputeTests(SimpleTestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, str(self.tmp), ignore_errors=True)

    def _cover_file(self, name="new.jpg", data=b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\xff\xd9"):
        p = self.tmp / name
        p.write_bytes(data)
        return str(p)

    def _epub(self, page_bytes, image_bytes=b"OLDIMAGE", *, guide=None, spine="coverpage",
              page_arc="OEBPS/cover.xhtml", image_arc="OEBPS/images/cover.jpg",
              extra_manifest="", opf_path="OEBPS/content.opf", extra_files=None):
        opf_dir = posixpath.dirname(opf_path)
        page_href = posixpath.relpath(page_arc, opf_dir)
        image_href = posixpath.relpath(image_arc, opf_dir)
        manifest = (
            f'<manifest><item id="coverpage" href="{page_href}" media-type="application/xhtml+xml"/>'
            f'<item id="coverimg" href="{image_href}" media-type="image/jpeg"/>{extra_manifest}</manifest>'
        )
        spine_xml = "".join(f'<itemref idref="{s}"/>' for s in spine.split(",") if s)
        guide_xml = guide or ""
        opf = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="uid">'
            '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
            '<dc:identifier id="uid">urn:uuid:test</dc:identifier>'
            '<dc:title>T</dc:title><dc:language>en</dc:language>'
            '<meta name="cover" content="coverimg"/>'
            '</metadata>'
            f"{manifest}<spine>{spine_xml}</spine>{guide_xml}</package>"
        ).encode("utf-8")
        files = {
            "META-INF/container.xml": _container(opf_path),
            opf_path: opf,
            image_arc: image_bytes,
        }
        if page_bytes is not None:
            files[page_arc] = page_bytes
        if extra_files:
            files.update(extra_files)
        path = self.tmp / "in.epub"
        _write_zip(path, files)
        return str(path)

    def _compute(self, path, cover=None):
        return _compute(str(path), cover, False, None)

    def _codes(self, fixes):
        return [f.code for f in fixes]

    # (a) a pure img page now points to the new cover and resolves to the new bytes
    def test_pure_img_page_rewritten_to_new_cover(self):
        src = self._epub(_pure_img_page("images/cover.jpg"))
        cover = self._cover_file("new.jpg", data=b"\xff\xd8\xffNEWCOVER")
        fixes, entries, _dropped, modified = self._compute(src, cover)
        self.assertIn("COVER-PAGE", self._codes(fixes))
        self.assertIn("OEBPS/cover.xhtml", modified)
        page = entries["OEBPS/cover.xhtml"]
        self.assertNotIn(b"images/cover.jpg", page)
        self.assertIn(b'src="cover.jpg"', page)
        # the image the page now points at resolves to the new cover bytes
        self.assertEqual(entries["OEBPS/cover.jpg"], b"\xff\xd8\xffNEWCOVER")

    # (b) an svg image wrapper
    def test_svg_wrapper_rewritten(self):
        src = self._epub(_svg_page("images/cover.jpg"))
        cover = self._cover_file("new.jpg", data=b"\xff\xd8\xffSVGCOVER")
        fixes, entries, _dropped, modified = self._compute(src, cover)
        self.assertIn("COVER-PAGE", self._codes(fixes))
        page = entries["OEBPS/cover.xhtml"]
        self.assertNotIn(b"images/cover.jpg", page)
        self.assertIn(b'xlink:href="cover.jpg"', page)

    # (c) a page with text / two images stays byte-for-byte and holds COVER-PAGE-SKIP
    def test_text_page_skipped_byte_for_byte(self):
        page = _text_page()
        src = self._epub(page)
        cover = self._cover_file()
        fixes, entries, _dropped, modified = self._compute(src, cover)
        self.assertIn("COVER-PAGE-SKIP", self._codes(fixes))
        self.assertNotIn("COVER-PAGE", self._codes(fixes))
        self.assertNotIn("OEBPS/cover.xhtml", modified)
        self.assertEqual(entries["OEBPS/cover.xhtml"], page)

    def test_two_image_page_skipped(self):
        page = _two_image_page()
        src = self._epub(page)
        cover = self._cover_file()
        fixes, entries, _dropped, modified = self._compute(src, cover)
        self.assertIn("COVER-PAGE-SKIP", self._codes(fixes))
        self.assertNotIn("COVER-PAGE", self._codes(fixes))
        self.assertEqual(entries["OEBPS/cover.xhtml"], page)

    # (d) a guide cover reference to a page that is not the first spine item is used
    def test_guide_reference_not_first_spine(self):
        page = _pure_img_page("images/cover.jpg")
        chapter = _text_page()
        guide = '<guide><reference type="cover" href="cover.xhtml"/></guide>'
        src = self._epub(page, guide=guide, spine="chapter1,coverpage",
                         extra_manifest='<item id="chapter1" href="chapter1.xhtml" media-type="application/xhtml+xml"/>',
                         extra_files={"OEBPS/chapter1.xhtml": chapter})
        cover = self._cover_file()
        fixes, entries, _dropped, modified = self._compute(src, cover)
        self.assertIn("COVER-PAGE", self._codes(fixes))
        self.assertIn("OEBPS/cover.xhtml", modified)
        self.assertNotIn("OEBPS/chapter1.xhtml", modified)

    # (e) page in OEBPS/text and image in OEBPS/images gives a correct relative ref
    def test_relative_ref_across_dirs(self):
        page = _pure_img_page("images/cover.jpg")
        # page at OEBPS/text/cover.xhtml, old image at OEBPS/images/cover.jpg; the
        # new cover lands at OEBPS/cover.jpg, so the page must reference it as
        # "../cover.jpg" (the cross-directory relative reference).
        src = self._epub(page, page_arc="OEBPS/text/cover.xhtml", image_arc="OEBPS/images/cover.jpg")
        cover = self._cover_file()
        fixes, entries, _dropped, modified = self._compute(src, cover)
        self.assertIn("COVER-PAGE", self._codes(fixes))
        page_out = entries["OEBPS/text/cover.xhtml"]
        self.assertIn(b'../cover.jpg', page_out)
        self.assertNotIn(b'images/cover.jpg', page_out)

    # (f) every byte outside the replaced attribute value is identical
    def test_bytes_outside_value_identical(self):
        marker = b'<!--MARKER-DO-NOT-TOUCH-->'
        page = _pure_img_page("images/cover.jpg").replace(b"</body>", marker + b"</body>")
        src = self._epub(page)
        cover = self._cover_file()
        _fixes, entries, _dropped, _modified = self._compute(src, cover)
        out = entries["OEBPS/cover.xhtml"]
        self.assertIn(marker, out)
        # everything except the single value substitution is preserved: strip the
        # two candidate values and the remainder must be byte-identical.
        before = page.replace(b"images/cover.jpg", b"")
        after = out.replace(b"cover.jpg", b"")
        self.assertEqual(after, before)

    # (g) a page that references the old image twice is skipped
    def test_duplicate_reference_skipped(self):
        page = (
            b'<html xmlns="http://www.w3.org/1999/xhtml"><body><div>'
            b'<img src="images/cover.jpg"/><img src="images/cover.jpg"/></div></body></html>'
        )
        src = self._epub(page)
        cover = self._cover_file()
        fixes, entries, _dropped, modified = self._compute(src, cover)
        self.assertIn("COVER-PAGE-SKIP", self._codes(fixes))
        self.assertNotIn("COVER-PAGE", self._codes(fixes))
        self.assertEqual(entries["OEBPS/cover.xhtml"], page)

    # (h) a second pass with the same cover changes nothing
    def test_already_resolving_page_unchanged(self):
        # The cover page already references "cover.jpg" (same directory), which is
        # exactly where the new cover lands, so nothing is rewritten.
        page = _pure_img_page("cover.jpg")
        src = self._epub(page)
        cover = self._cover_file()
        fixes, entries, _dropped, modified = self._compute(src, cover)
        self.assertNotIn("COVER-PAGE", self._codes(fixes))
        self.assertNotIn("OEBPS/cover.xhtml", modified)
        self.assertEqual(entries["OEBPS/cover.xhtml"], page)

    # (i) no cover means no page edit
    def test_no_cover_no_page_edit(self):
        page = _pure_img_page("images/cover.jpg")
        src = self._epub(page)
        fixes, entries, _dropped, modified = self._compute(src, None)
        self.assertNotIn("COVER-PAGE", self._codes(fixes))
        self.assertNotIn("COVER-PAGE-SKIP", self._codes(fixes))
        self.assertNotIn("OEBPS/cover.xhtml", modified)
        self.assertEqual(entries["OEBPS/cover.xhtml"], page)

    # (j) the old image entry is still in the zip and the manifest
    def test_old_image_kept(self):
        src = self._epub(_pure_img_page("images/cover.jpg"))
        cover = self._cover_file()
        _fixes, entries, _dropped, _modified = self._compute(src, cover)
        self.assertIn("OEBPS/images/cover.jpg", entries)
        self.assertNotIn("OEBPS/images/cover.jpg", _dropped)
        opf = entries["OEBPS/content.opf"]
        self.assertIn(b'id="coverimg"', opf)

    # (k) an external entity in the page is not resolved
    def test_external_entity_not_resolved(self):
        secret = b"TOP-SECRET-EXFILTRATION"
        secret_path = self.tmp / "secret.txt"
        secret_path.write_bytes(secret)
        entity_uri = secret_path.as_uri()
        page = (
            b'<?xml version="1.0" encoding="utf-8"?>\n'
            b'<!DOCTYPE html [<!ENTITY xxe SYSTEM "' + entity_uri.encode() + b'">]>\n'
            b'<html xmlns="http://www.w3.org/1999/xhtml"><head><title>c</title></head>'
            b'<body><div><img src="images/cover.jpg" alt="&xxe;"/></div></body></html>'
        )
        src = self._epub(page)
        cover = self._cover_file()
        fixes, entries, _dropped, _modified = self._compute(src, cover)
        # the external entity is never resolved (no_network/resolve_entities=False):
        # the secret never leaks into the output, and the page carrying the entity
        # is left byte-for-byte untouched rather than edited.
        self.assertNotIn(secret, entries["OEBPS/cover.xhtml"])
        self.assertNotIn(secret, b"".join(entries.values()))
        self.assertIn("COVER-PAGE-SKIP", self._codes(fixes))
        self.assertEqual(entries["OEBPS/cover.xhtml"], page)

    # (l) a manifest entry whose page is missing skips without an error
    def test_missing_page_skips(self):
        # the spine's only item declares a page whose file is absent from the zip
        src = self._epub(None, guide=None)
        cover = self._cover_file()
        fixes, entries, _dropped, _modified = self._compute(src, cover)
        self.assertIn("COVER-PAGE-SKIP", self._codes(fixes))
        self.assertNotIn("COVER-PAGE", self._codes(fixes))

    # (m) a pure page whose image path also occurs in an alt attribute is
    # ambiguous: the rewrite is skipped and check_cover_page reports "not-pure".
    def test_ambiguous_pure_page_not_pure(self):
        page = (
            b'<html xmlns="http://www.w3.org/1999/xhtml"><body><div>'
            b'<img src="images/cover.jpg" alt="images/cover.jpg"/></div></body></html>'
        )
        src = self._epub(page)
        cover_path = self._cover_file(data=b"\xff\xd8\xffNEWCOVER")
        fixes, entries, _dropped, _modified = self._compute(src, cover_path)
        self.assertIn("COVER-PAGE-SKIP", self._codes(fixes))
        self.assertNotIn("COVER-PAGE", self._codes(fixes))
        self.assertEqual(entries["OEBPS/cover.xhtml"], page)
        out = self.tmp / "out.epub"
        write_epub(str(src), str(out), cover_path=cover_path)
        result = cp.check_cover_page(str(out), hashlib.sha256(b"\xff\xd8\xffNEWCOVER").hexdigest())
        self.assertEqual(result, "not-pure")

    # (n) the old cover already sits at the path the new cover would take by
    # default ("cover.jpg"); the new cover lands at "cover-2.jpg" and the old
    # entry is kept.
    def test_common_layout_old_cover_at_new_path(self):
        page = _pure_img_page("cover.jpg")
        src = self._epub(page, image_arc="OEBPS/cover.jpg")
        cover_path = self._cover_file(data=b"\xff\xd8\xffNEWCOVER")
        fixes, entries, _dropped, _modified = self._compute(src, cover_path)
        self.assertIn("COVER-EMBED", self._codes(fixes))
        # the new cover takes a fresh name, never the occupied "cover.jpg"
        self.assertIn("OEBPS/cover-2.jpg", entries)
        self.assertIn("OEBPS/cover.jpg", entries)  # old cover kept
        page_out = entries["OEBPS/cover.xhtml"]
        self.assertIn(b'src="cover-2.jpg"', page_out)
        self.assertNotIn(b'src="cover.jpg"', page_out)
        out = self.tmp / "out.epub"
        write_epub(str(src), str(out), cover_path=cover_path)
        result = cp.check_cover_page(str(out), hashlib.sha256(b"\xff\xd8\xffNEWCOVER").hexdigest())
        self.assertEqual(result, "ok")

    # (o) a second pass with the same cover is a no-op: same entry names, same
    # manifest, identical cover page, and no cover-1.jpg / extra manifest item.
    def test_two_pass_idempotent(self):
        page = _pure_img_page("cover.jpg")
        src = self._epub(page, image_arc="OEBPS/cover.jpg")
        cover_path = self._cover_file(data=b"\xff\xd8\xffNEWCOVER")
        out1 = self.tmp / "out1.epub"
        write_epub(str(src), str(out1), cover_path=cover_path)
        out2 = self.tmp / "out2.epub"
        write_epub(str(out1), str(out2), cover_path=cover_path)
        with zipfile.ZipFile(out1) as z1, zipfile.ZipFile(out2) as z2:
            n1, n2 = set(z1.namelist()), set(z2.namelist())
            self.assertEqual(n2, n1)
            self.assertEqual(z2.read("OEBPS/cover.xhtml"), z1.read("OEBPS/cover.xhtml"))
            self.assertEqual(z2.read("OEBPS/content.opf"), z1.read("OEBPS/content.opf"))
        self.assertNotIn("OEBPS/cover-1.jpg", n2)
        self.assertNotIn("OEBPS/cover-3.jpg", n2)

    def _epub_already_embedded(self, page_bytes, cover_bytes=b"\xff\xd8\xffNEWCOVER",
                               old_image_bytes=b"OLDIMAGE"):
        """An EPUB whose ``cover-image`` manifest item already holds the selected
        cover bytes, while the pure cover page points at a different image."""
        opf = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="uid">'
            '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
            '<dc:identifier id="uid">urn:uuid:test</dc:identifier>'
            '<dc:title>T</dc:title><dc:language>en</dc:language>'
            '<meta name="cover" content="coverimg"/>'
            '</metadata>'
            '<manifest>'
            '<item id="coverpage" href="cover.xhtml" media-type="application/xhtml+xml"/>'
            '<item id="oldimg" href="old.jpg" media-type="image/jpeg"/>'
            '<item id="coverimg" href="cover.jpg" media-type="image/jpeg" properties="cover-image"/>'
            '</manifest>'
            '<spine><itemref idref="coverpage"/></spine>'
            '</package>'
        ).encode("utf-8")
        files = {
            "META-INF/container.xml": _container("OEBPS/content.opf"),
            "OEBPS/content.opf": opf,
            "OEBPS/cover.xhtml": page_bytes,
            "OEBPS/old.jpg": old_image_bytes,
            "OEBPS/cover.jpg": cover_bytes,
        }
        path = self.tmp / "already_embedded.epub"
        _write_zip(path, files)
        return str(path)

    # (p) the cover-image item already holds the selected bytes while the pure
    # page points at a different image: after the repack the page resolves to
    # the cover item and check_cover_page reports "ok".
    def test_already_embedded_cover_item_page_rewritten(self):
        cover_bytes = b"\xff\xd8\xffNEWCOVER"
        page = _pure_img_page("old.jpg")
        src = self._epub_already_embedded(page, cover_bytes=cover_bytes)
        cover = self._cover_file("sel.jpg", data=cover_bytes)
        fixes, entries, _dropped, _modified = self._compute(src, cover)
        self.assertIn("COVER-PAGE", self._codes(fixes))
        self.assertNotIn("COVER-EMBED", self._codes(fixes))
        self.assertIn(b'src="cover.jpg"', entries["OEBPS/cover.xhtml"])
        self.assertNotIn(b"old.jpg", entries["OEBPS/cover.xhtml"])
        out = self.tmp / "out.epub"
        write_epub(str(src), str(out), cover_path=cover)
        result = cp.check_cover_page(str(out), hashlib.sha256(cover_bytes).hexdigest())
        self.assertEqual(result, "ok")

    # (q) a second pass over the already-embedded EPUB is stable.
    def test_already_embedded_two_pass_stable(self):
        cover_bytes = b"\xff\xd8\xffNEWCOVER"
        page = _pure_img_page("old.jpg")
        src = self._epub_already_embedded(page, cover_bytes=cover_bytes)
        cover = self._cover_file("sel.jpg", data=cover_bytes)
        out1 = self.tmp / "out1.epub"
        write_epub(str(src), str(out1), cover_path=cover)
        out2 = self.tmp / "out2.epub"
        write_epub(str(out1), str(out2), cover_path=cover)
        with zipfile.ZipFile(out1) as z1, zipfile.ZipFile(out2) as z2:
            self.assertEqual(set(z2.namelist()), set(z1.namelist()))
            self.assertEqual(z2.read("OEBPS/cover.xhtml"), z1.read("OEBPS/cover.xhtml"))
            self.assertEqual(z2.read("OEBPS/content.opf"), z1.read("OEBPS/content.opf"))

    # (r) the cover item already holds the bytes and the page already points at
    # it: nothing changes (guard).
    def test_already_embedded_page_already_pointing_no_change(self):
        cover_bytes = b"\xff\xd8\xffNEWCOVER"
        page = _pure_img_page("cover.jpg")
        src = self._epub_already_embedded(page, cover_bytes=cover_bytes)
        cover = self._cover_file("sel.jpg", data=cover_bytes)
        fixes, entries, _dropped, modified = self._compute(src, cover)
        self.assertNotIn("COVER-PAGE", self._codes(fixes))
        self.assertNotIn("COVER-EMBED", self._codes(fixes))
        self.assertNotIn("OEBPS/cover.xhtml", modified)
        self.assertEqual(entries["OEBPS/cover.xhtml"], page)
