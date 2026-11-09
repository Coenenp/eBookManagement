"""Tests for EPUB metadata sync: build_epub_metadata and the fixer OPF writing.

Every EPUB is built in-code with zipfile (no binary fixtures). The dict
builder is exercised against the database; the OPF writing is exercised
against a plain metadata dict through ``write_epub``.
"""

import hashlib
import re
import shutil
import tempfile
import zipfile
from pathlib import Path

from django.test import SimpleTestCase, TestCase

from books.models import Author, BookAuthor, BookGenre, DataSource, FinalMetadata, Genre, ScanFolder
from books.tests.test_helpers import create_test_book_with_file
from books.utils.epub_fix import write_epub
from books.utils.safe_move.metadata_sync import build_epub_metadata

MIMETYPE = b"application/epub+zip"


def _container(rootfile="OEBPS/content.opf"):
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
        '<rootfiles><rootfile full-path="'
        + rootfile
        + '" media-type="application/oebps-package+xml"/></rootfiles></container>'
    ).encode("utf-8")


def _xhtml():
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>t</title></head>'
        "<body><p>x</p></body></html>"
    ).encode("utf-8")


def _opf(version="2.0", extra=""):
    """A metadata block carrying namespaces, a comment and an unknown element."""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<package xmlns="http://www.idpf.org/2007/opf" version="{version}" unique-identifier="uid" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" '
        'xmlns:dcterms="http://purl.org/dc/terms/" '
        'xmlns:opf="http://www.idpf.org/2007/opf" '
        'xmlns:calibre="http://calibre.kovidgoyal.net/2009/metadata">'
        "<!-- keep me -->"
        "<metadata>"
        '<dc:identifier id="uid">urn:uuid:test</dc:identifier>'
        "<dc:title>Old Title</dc:title><dc:language>en</dc:language>"
        "<x-unknown xmlns:x=\"urn:custom\">mystery</x-unknown>"
        + extra
        + "</metadata>"
        '<manifest><item id="c1" href="chapter1.xhtml" media-type="application/xhtml+xml"/></manifest>'
        '<spine><itemref idref="c1"/></spine></package>'
    ).encode("utf-8")


def _opf_isbn_uid(version="2.0", value="9781111111111"):
    """An OPF whose unique-identifier element is itself an ISBN identifier."""
    if version.startswith("3"):
        ident = f'<dc:identifier id="uid">urn:isbn:{value}</dc:identifier>'
    else:
        ident = f'<dc:identifier id="uid" opf:scheme="ISBN">{value}</dc:identifier>'
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<package xmlns="http://www.idpf.org/2007/opf" version="{version}" unique-identifier="uid" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" '
        'xmlns:opf="http://www.idpf.org/2007/opf">'
        "<metadata>"
        + ident
        + "<dc:title>Old Title</dc:title><dc:language>en</dc:language>"
        "</metadata>"
        '<manifest><item id="c1" href="chapter1.xhtml" media-type="application/xhtml+xml"/></manifest>'
        '<spine><itemref idref="c1"/></spine></package>'
    ).encode("utf-8")


def _opf_no_opf_prefix():
    """An OPF declaring only the default namespace (no xmlns:opf)."""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="uid">'
        "<metadata>"
        '<dc:identifier xmlns:dc="http://purl.org/dc/elements/1.1/" id="uid">urn:uuid:test</dc:identifier>'
        '<dc:title xmlns:dc="http://purl.org/dc/elements/1.1/">Old Title</dc:title>'
        '<dc:language xmlns:dc="http://purl.org/dc/elements/1.1/">en</dc:language>'
        "</metadata>"
        '<manifest><item id="c1" href="chapter1.xhtml" media-type="application/xhtml+xml"/></manifest>'
        '<spine><itemref idref="c1"/></spine></package>'
    ).encode("utf-8")


def _write_epub(path, opf):
    files = {
        "mimetype": MIMETYPE,
        "META-INF/container.xml": _container(),
        "OEBPS/content.opf": opf,
        "OEBPS/chapter1.xhtml": _xhtml(),
    }
    with zipfile.ZipFile(path, "w") as z:
        names = ["mimetype"] + [n for n in files if n != "mimetype"]
        for n in names:
            z.writestr(n, files[n], compress_type=zipfile.ZIP_STORED if n == "mimetype" else zipfile.ZIP_DEFLATED)


def _read_opf(path):
    from lxml import etree

    with zipfile.ZipFile(path) as z:
        return etree.fromstring(z.read("OEBPS/content.opf"))


def _mutate_opf_epub(path, mutator):
    """Apply ``mutator(root)`` to the OPF entry of ``path`` in place."""
    import os

    from lxml import etree

    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        entries = {n: z.read(n) for n in names}
    root = etree.fromstring(entries["OEBPS/content.opf"])
    mutator(root)
    entries["OEBPS/content.opf"] = etree.tostring(root, encoding="utf-8", xml_declaration=True)
    tmp = str(path) + ".tmp"
    with zipfile.ZipFile(tmp, "w") as z:
        z.writestr("mimetype", entries["mimetype"], compress_type=zipfile.ZIP_STORED)
        for n in names:
            if n == "mimetype":
                continue
            z.writestr(n, entries[n], compress_type=zipfile.ZIP_DEFLATED)
    os.replace(tmp, path)


class OpfMetadataSyncTests(SimpleTestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, str(self.root), ignore_errors=True)

    def _sync(self, metadata, *, version="2.0", extra=""):
        src = self.root / "in.epub"
        _write_epub(src, _opf(version=version, extra=extra))
        out = self.root / "out.epub"
        write_epub(str(src), str(out), metadata=metadata)
        return _read_opf(out)

    def _sync_opf(self, opf_bytes, metadata):
        src = self.root / "in.epub"
        _write_epub(src, opf_bytes)
        out = self.root / "out.epub"
        write_epub(str(src), str(out), metadata=metadata)
        return _read_opf(out)

    # -- (a) all fields written -------------------------------------------------

    def test_all_fields_written(self):
        meta = {
            "title": "Great Book",
            "authors": [{"name": "Jane Doe", "file_as": "Doe, Jane"}, {"name": "John Smith", "file_as": "Smith, John"}],
            "language": "en",
            "publisher": "Acme",
            "year": 1999,
            "description": "A great read",
            "subjects": ["Fiction", "Drama"],
            "isbn": "9781234567890",
            "series": "The Series",
            "series_index": "2",
        }
        root = self._sync(meta)
        NS = {"dc": "http://purl.org/dc/elements/1.1/", "opf": "http://www.idpf.org/2007/opf"}
        m = root.find("opf:metadata", NS)
        self.assertEqual(m.find("dc:title", NS).text, "Great Book")
        creators = m.findall("dc:creator", NS)
        self.assertEqual([c.text for c in creators], ["Jane Doe", "John Smith"])
        self.assertEqual(creators[0].get("{http://www.idpf.org/2007/opf}file-as"), "Doe, Jane")
        self.assertEqual(creators[1].get("{http://www.idpf.org/2007/opf}file-as"), "Smith, John")
        self.assertEqual(m.find("dc:language", NS).text, "en")
        self.assertEqual(m.find("dc:publisher", NS).text, "Acme")
        self.assertEqual(m.find("dc:date", NS).text, "1999")
        self.assertEqual(m.find("dc:description", NS).text, "A great read")
        self.assertEqual([s.text for s in m.findall("dc:subject", NS)], ["Fiction", "Drama"])

    # -- (b) empty/missing never overwrites ------------------------------------

    def test_empty_value_never_overwrites(self):
        root = self._sync({"language": "fr"})  # title/others absent -> left alone
        NS = {"dc": "http://purl.org/dc/elements/1.1/", "opf": "http://www.idpf.org/2007/opf"}
        m = root.find("opf:metadata", NS)
        self.assertEqual(m.find("dc:title", NS).text, "Old Title")
        self.assertEqual(m.find("dc:language", NS).text, "fr")

    def test_missing_value_never_overwrites(self):
        root = self._sync({"title": "", "language": "en"})
        NS = {"dc": "http://purl.org/dc/elements/1.1/", "opf": "http://www.idpf.org/2007/opf"}
        m = root.find("opf:metadata", NS)
        self.assertEqual(m.find("dc:title", NS).text, "Old Title")

    # -- (c) unique identifier untouched, ISBN separate ------------------------

    def test_unique_identifier_untouched_isbn_separate_epub2(self):
        root = self._sync({"isbn": "9781234567890"}, version="2.0")
        NS = {"dc": "http://purl.org/dc/elements/1.1/", "opf": "http://www.idpf.org/2007/opf"}
        m = root.find("opf:metadata", NS)
        uniq = [i for i in m.findall("dc:identifier", NS) if i.get("id") == "uid"]
        self.assertEqual(len(uniq), 1)
        self.assertEqual(uniq[0].text, "urn:uuid:test")
        isbn = [i for i in m.findall("dc:identifier", NS) if i.get("{http://www.idpf.org/2007/opf}scheme") == "ISBN"]
        self.assertEqual(len(isbn), 1)
        self.assertEqual(isbn[0].text, "9781234567890")

    def test_isbn_urn_form_epub3(self):
        root = self._sync({"isbn": "9781234567890"}, version="3.0")
        NS = {"dc": "http://purl.org/dc/elements/1.1/", "opf": "http://www.idpf.org/2007/opf"}
        m = root.find("opf:metadata", NS)
        texts = [i.text for i in m.findall("dc:identifier", NS)]
        self.assertIn("urn:isbn:9781234567890", texts)
        self.assertIn("urn:uuid:test", texts)

    # -- (d) fidelity -----------------------------------------------------------

    def test_comments_namespaces_unknown_elements_survive(self):
        root = self._sync({"title": "New Title"})
        with zipfile.ZipFile(self.root / "out.epub") as z:
            opf = z.read("OEBPS/content.opf").decode("utf-8")
        self.assertIn("<!-- keep me -->", opf)
        self.assertIn("x-unknown", opf)
        self.assertIn('xmlns:calibre="http://calibre.kovidgoyal.net/2009/metadata"', opf)
        NS = {"dc": "http://purl.org/dc/elements/1.1/", "opf": "http://www.idpf.org/2007/opf"}
        self.assertEqual(root.find("opf:metadata/dc:title", NS).text, "New Title")

    # -- (e) series -------------------------------------------------------------

    def test_series_calibre_epub2(self):
        root = self._sync({"series": "S", "series_index": "3"}, version="2.0")
        NS = {"opf": "http://www.idpf.org/2007/opf"}
        metas = {mm.get("name"): mm.get("content") for mm in root.findall("opf:metadata/opf:meta", NS)}
        self.assertEqual(metas.get("calibre:series"), "S")
        self.assertEqual(metas.get("calibre:series_index"), "3")

    def test_series_belongs_to_collection_epub3(self):
        root = self._sync({"series": "S", "series_index": "3"}, version="3.0")
        NS = {"opf": "http://www.idpf.org/2007/opf"}
        metas = root.findall("opf:metadata/opf:meta", NS)
        coll = [mm for mm in metas if mm.get("property") == "belongs-to-collection"]
        self.assertEqual(len(coll), 1)
        self.assertEqual(coll[0].text, "S")
        cid = coll[0].get("id")
        ref = "#" + cid
        ct = [mm for mm in metas if mm.get("refines") == ref and mm.get("property") == "collection-type"]
        gp = [mm for mm in metas if mm.get("refines") == ref and mm.get("property") == "group-position"]
        self.assertEqual(len(ct), 1)
        self.assertEqual(ct[0].text, "series")
        self.assertEqual(len(gp), 1)
        self.assertEqual(gp[0].text, "3")

    # -- (f) dcterms:modified --------------------------------------------------

    def test_modified_epub3_only(self):
        root2 = self._sync({"title": "T"}, version="2.0")
        NS = {"opf": "http://www.idpf.org/2007/opf"}
        mod2 = [mm for mm in root2.findall("opf:metadata/opf:meta", NS) if mm.get("property") == "dcterms:modified"]
        self.assertEqual(mod2, [])
        root3 = self._sync({"title": "T"}, version="3.0")
        mod3 = [mm for mm in root3.findall("opf:metadata/opf:meta", NS) if mm.get("property") == "dcterms:modified"]
        self.assertEqual(len(mod3), 1)
        self.assertRegex(mod3[0].text, r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

    # -- (g) idempotent ---------------------------------------------------------

    def test_idempotent(self):
        meta = {
            "title": "T", "authors": [{"name": "A One", "file_as": "One, A"}],
            "language": "en", "publisher": "P", "year": 2000, "description": "d",
            "subjects": ["s1", "s2"], "isbn": "9781234567890", "series": "S", "series_index": "2",
        }
        src = self.root / "in.epub"
        _write_epub(src, _opf())
        out1 = self.root / "out1.epub"
        out2 = self.root / "out2.epub"
        write_epub(str(src), str(out1), metadata=meta)
        write_epub(str(out1), str(out2), metadata=meta)

        def canon(path):
            root = _read_opf(path)
            NS = {"opf": "http://www.idpf.org/2007/opf"}
            for mm in root.findall("opf:metadata/opf:meta", NS):
                if mm.get("property") == "dcterms:modified":
                    mm.text = "X"
            from lxml import etree

            return etree.tostring(root)

        self.assertEqual(canon(out1), canon(out2))

    # -- (h) several authors keep order ----------------------------------------

    def test_several_authors_keep_order(self):
        meta = {
            "authors": [
                {"name": "Alpha", "file_as": "Alpha"},
                {"name": "Beta", "file_as": "Beta"},
                {"name": "Gamma", "file_as": "Gamma"},
            ]
        }
        root = self._sync(meta)
        NS = {"dc": "http://purl.org/dc/elements/1.1/", "opf": "http://www.idpf.org/2007/opf"}
        creators = root.findall("opf:metadata/dc:creator", NS)
        self.assertEqual([c.text for c in creators], ["Alpha", "Beta", "Gamma"])

    # -- (i) escaping round-trip ------------------------------------------------

    def test_escaping_round_trip(self):
        meta = {"title": 'A & B <C> "quoted" \u2014 caf\u00e9', "description": 'x & y <z> "q" \u00f1'}
        root = self._sync(meta)
        NS = {"dc": "http://purl.org/dc/elements/1.1/", "opf": "http://www.idpf.org/2007/opf"}
        m = root.find("opf:metadata", NS)
        self.assertEqual(m.find("dc:title", NS).text, 'A & B <C> "quoted" \u2014 caf\u00e9')
        self.assertEqual(m.find("dc:description", NS).text, 'x & y <z> "q" \u00f1')

    # -- (j) metadata None is byte-identical -----------------------------------

    def test_metadata_none_byte_identical(self):
        src = self.root / "in.epub"
        opf = _opf()
        _write_epub(src, opf)
        out = self.root / "out.epub"
        write_epub(str(src), str(out), metadata=None)
        with zipfile.ZipFile(out) as z:
            data = z.read("OEBPS/content.opf")
            self.assertEqual(data, opf)
            self.assertEqual(
                hashlib.sha256(data).hexdigest(),
                "e19edfd00a102ad75b845896e074df7325c7045b00d587bf8d44aa500a7d8dab",
            )
        # An empty dict must produce byte-identical output to metadata=None.
        out2 = self.root / "out2.epub"
        write_epub(str(src), str(out2), metadata={})
        with zipfile.ZipFile(out2) as z:
            self.assertEqual(z.read("OEBPS/content.opf"), data)

    # -- (k) XXE-safe -----------------------------------------------------------

    def test_external_entity_not_resolved(self):
        secret = self.root / "secret.txt"
        secret.write_text("XXE_LEAKED_MARKER")
        opf = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<!DOCTYPE package [<!ENTITY xxe SYSTEM "file://' + str(secret) + '">]>\n'
            '<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="uid">'
            '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
            '<dc:identifier id="uid">urn:uuid:test</dc:identifier>'
            '<dc:title>&xxe;</dc:title><dc:language>en</dc:language></metadata>'
            '<manifest><item id="c1" href="chapter1.xhtml" media-type="application/xhtml+xml"/></manifest>'
            '<spine><itemref idref="c1"/></spine></package>'
        ).encode("utf-8")
        src = self.root / "in.epub"
        _write_epub(src, opf)
        out = self.root / "out.epub"
        write_epub(str(src), str(out), metadata={"title": "Safe"})
        with zipfile.ZipFile(out) as z:
            self.assertNotIn(b"XXE_LEAKED_MARKER", z.read("OEBPS/content.opf"))

    # -- (l) unique identifier that is an ISBN is never modified --------------

    _OPF_NS = "http://www.idpf.org/2007/opf"
    _DC_NS = "http://purl.org/dc/elements/1.1/"

    def test_unique_identifier_isbn_kept_epub2(self):
        root = self._sync_opf(_opf_isbn_uid("2.0", "9781111111111"), {"isbn": "9782222222222"})
        NS = {"dc": self._DC_NS, "opf": self._OPF_NS}
        m = root.find("opf:metadata", NS)
        idents = m.findall("dc:identifier", NS)
        uid = [i for i in idents if i.get("id") == "uid"]
        self.assertEqual(len(uid), 1)
        self.assertEqual(uid[0].text, "9781111111111")  # text untouched
        self.assertEqual(uid[0].get(f"{{{self._OPF_NS}}}scheme"), "ISBN")  # attribute kept
        # dict ISBN added as a separate identifier without an id
        others = [i for i in idents if i.get("id") != "uid"]
        self.assertEqual([i.text for i in others], ["9782222222222"])
        self.assertIsNone(others[0].get("id"))
        self.assertEqual(others[0].get(f"{{{self._OPF_NS}}}scheme"), "ISBN")

    def test_unique_identifier_isbn_kept_epub3(self):
        root = self._sync_opf(_opf_isbn_uid("3.0", "9781111111111"), {"isbn": "9782222222222"})
        NS = {"dc": self._DC_NS, "opf": self._OPF_NS}
        m = root.find("opf:metadata", NS)
        idents = m.findall("dc:identifier", NS)
        uid = [i for i in idents if i.get("id") == "uid"]
        self.assertEqual(len(uid), 1)
        self.assertEqual(uid[0].text, "urn:isbn:9781111111111")  # text untouched
        others = [i for i in idents if i.get("id") != "uid"]
        self.assertEqual([i.text for i in others], ["urn:isbn:9782222222222"])
        self.assertIsNone(others[0].get("id"))

    def test_unique_identifier_isbn_equal_no_add(self):
        root = self._sync_opf(_opf_isbn_uid("2.0", "9781111111111"), {"isbn": "9781111111111"})
        NS = {"dc": self._DC_NS, "opf": self._OPF_NS}
        m = root.find("opf:metadata", NS)
        idents = m.findall("dc:identifier", NS)
        self.assertEqual(len(idents), 1)  # nothing added
        self.assertEqual(idents[0].text, "9781111111111")

    # -- (m) EPUB 3 creators use refines metas ---------------------------------

    def test_epub3_creators_use_refines_metas(self):
        meta = {
            "authors": [{"name": "Jane Doe", "file_as": "Doe, Jane"}, {"name": "John Smith", "file_as": "Smith, John"}],
        }
        root = self._sync(meta, version="3.0")
        NS = {"dc": self._DC_NS, "opf": self._OPF_NS}
        m = root.find("opf:metadata", NS)
        creators = m.findall("dc:creator", NS)
        self.assertEqual([c.text for c in creators], ["Jane Doe", "John Smith"])
        for c in creators:
            self.assertIsNone(c.get(f"{{{self._OPF_NS}}}role"))
            self.assertIsNone(c.get(f"{{{self._OPF_NS}}}file-as"))
        ids = [c.get("id") for c in creators]
        self.assertEqual(len(set(ids)), 2)  # unique ids
        all_ids = [e.get("id") for e in root.iter() if e.get("id")]
        self.assertEqual(len(all_ids), len(set(all_ids)))  # unique among the whole OPF
        for c in creators:
            cid = c.get("id")
            roles = [mm for mm in m.findall("opf:meta", NS) if mm.get("refines") == f"#{cid}" and mm.get("property") == "role"]
            self.assertEqual(len(roles), 1)
            self.assertEqual(roles[0].get("scheme"), "marc:relators")
            self.assertEqual(roles[0].text, "aut")
        fas = {mm.get("refines"): mm.text for mm in m.findall("opf:meta", NS) if mm.get("property") == "file-as"}
        self.assertEqual(fas[f"#{ids[0]}"], "Doe, Jane")
        self.assertEqual(fas[f"#{ids[1]}"], "Smith, John")

    def test_epub2_creators_keep_opf_attributes(self):
        meta = {"authors": [{"name": "Jane Doe", "file_as": "Doe, Jane"}]}
        root = self._sync(meta, version="2.0")
        NS = {"dc": self._DC_NS, "opf": self._OPF_NS}
        m = root.find("opf:metadata", NS)
        c = m.find("dc:creator", NS)
        self.assertEqual(c.get(f"{{{self._OPF_NS}}}role"), "aut")
        self.assertEqual(c.get(f"{{{self._OPF_NS}}}file-as"), "Doe, Jane")
        self.assertIsNone(c.get("id"))

    # -- (n) non-author creators and contributors are preserved ---------------

    def test_epub2_translator_and_contributor_preserved(self):
        extra = (
            '<dc:creator opf:role="aut" opf:file-as="Old, Author">Old Author</dc:creator>'
            '<dc:creator id="trl1" opf:role="trl">Jane Translator</dc:creator>'
            '<dc:contributor opf:role="edt">Ed Editor</dc:contributor>'
        )
        meta = {"authors": [{"name": "New Author", "file_as": "Author, New"}]}
        root = self._sync(meta, version="2.0", extra=extra)
        NS = {"dc": self._DC_NS, "opf": self._OPF_NS}
        m = root.find("opf:metadata", NS)
        creators = m.findall("dc:creator", NS)
        self.assertEqual([c.text for c in creators], ["New Author", "Jane Translator"])
        self.assertEqual(creators[0].get(f"{{{self._OPF_NS}}}role"), "aut")
        trl = creators[1]
        self.assertEqual(trl.get("id"), "trl1")
        self.assertEqual(trl.get(f"{{{self._OPF_NS}}}role"), "trl")
        contribs = m.findall("dc:contributor", NS)
        self.assertEqual([c.text for c in contribs], ["Ed Editor"])
        self.assertEqual(contribs[0].get(f"{{{self._OPF_NS}}}role"), "edt")

    def test_epub3_illustrator_preserved(self):
        extra = (
            '<dc:creator id="aut1">Old Author</dc:creator>'
            '<meta refines="#aut1" property="role" scheme="marc:relators">aut</meta>'
            '<dc:creator id="ill1">Ill Illustrator</dc:creator>'
            '<meta refines="#ill1" property="role" scheme="marc:relators">ill</meta>'
        )
        meta = {"authors": [{"name": "New Author"}]}
        root = self._sync(meta, version="3.0", extra=extra)
        NS = {"dc": self._DC_NS, "opf": self._OPF_NS}
        m = root.find("opf:metadata", NS)
        creators = m.findall("dc:creator", NS)
        self.assertEqual([c.text for c in creators], ["New Author", "Ill Illustrator"])
        ill = creators[1]
        self.assertEqual(ill.get("id"), "ill1")
        ill_role = [mm for mm in m.findall("opf:meta", NS) if mm.get("refines") == "#ill1" and mm.get("property") == "role"]
        self.assertEqual(len(ill_role), 1)
        self.assertEqual(ill_role[0].text, "ill")
        # the removed author's refines meta is gone
        self.assertEqual([mm for mm in m.findall("opf:meta", NS) if mm.get("refines") == "#aut1"], [])
        # the new author carries a role=aut refines meta
        new_id = creators[0].get("id")
        new_role = [mm for mm in m.findall("opf:meta", NS) if mm.get("refines") == f"#{new_id}" and mm.get("property") == "role"]
        self.assertEqual(len(new_role), 1)
        self.assertEqual(new_role[0].text, "aut")

    # -- (o) date: year prefix ------------------------------------------------

    def test_date_year_prefix_untouched(self):
        root = self._sync({"year": 1999}, version="2.0", extra="<dc:date>1999-05-12</dc:date>")
        NS = {"dc": self._DC_NS, "opf": self._OPF_NS}
        self.assertEqual(root.find("opf:metadata/dc:date", NS).text, "1999-05-12")

    def test_date_different_year_rewritten(self):
        root = self._sync({"year": 1999}, version="2.0", extra="<dc:date>2001-03-04</dc:date>")
        NS = {"dc": self._DC_NS, "opf": self._OPF_NS}
        self.assertEqual(root.find("opf:metadata/dc:date", NS).text, "1999")

    # -- (p) no xmlns:opf fixture serialises opf (never ns0) ------------------

    def test_no_opf_prefix_fixture_serializes_opf_not_ns0(self):
        src = self.root / "in.epub"
        _write_epub(src, _opf_no_opf_prefix())
        out = self.root / "out.epub"
        write_epub(str(src), str(out), metadata={"authors": [{"name": "Jane Doe", "file_as": "Doe, Jane"}]})
        with zipfile.ZipFile(out) as z:
            opf_out = z.read("OEBPS/content.opf").decode("utf-8")
        self.assertIn("opf:role", opf_out)
        self.assertIn("opf:file-as", opf_out)
        self.assertNotIn("ns0", opf_out)

    # -- (q) verification guards ----------------------------------------------

    def test_verify_epub_metadata_guards(self):
        from books.utils.safe_move.metadata_sync import verify_epub_metadata

        meta = {
            "title": "Great Book",
            "authors": [{"name": "Jane Doe", "file_as": "Doe, Jane"}],
            "language": "en",
            "publisher": "Acme",
            "year": 1999,
            "description": "A great read",
            "subjects": ["Fiction"],
            "isbn": "9781234567890",
            "series": "The Series",
            "series_index": "2",
        }
        src = self.root / "in.epub"
        _write_epub(src, _opf())
        out = self.root / "out.epub"
        write_epub(str(src), str(out), metadata=meta)
        self.assertEqual(verify_epub_metadata(str(out), meta), [])  # clean OPF verifies

        OPF = self._OPF_NS
        DC = self._DC_NS
        NS = {"opf": OPF, "dc": DC}

        def _first_txt(root, path):
            root.find(path, NS).text = "MUTATED"

        def _first_of_many(root, path):
            root.findall(path, NS)[0].text = "MUTATED"

        def _isbn(root):
            for ident in root.findall("opf:metadata/dc:identifier", NS):
                if ident.get(f"{{{OPF}}}scheme") == "ISBN":
                    ident.text = "1111111111111"
                    return

        def _meta_name(root, name):
            for mm in root.findall("opf:metadata/opf:meta", NS):
                if mm.get("name") == name:
                    mm.set("content", "MUTATED")
                    return

        mutators = {
            "title": lambda r: _first_txt(r, "opf:metadata/dc:title"),
            "language": lambda r: _first_txt(r, "opf:metadata/dc:language"),
            "publisher": lambda r: _first_txt(r, "opf:metadata/dc:publisher"),
            "description": lambda r: _first_txt(r, "opf:metadata/dc:description"),
            "year": lambda r: _first_txt(r, "opf:metadata/dc:date"),
            "authors": lambda r: _first_of_many(r, "opf:metadata/dc:creator"),
            "subjects": lambda r: _first_of_many(r, "opf:metadata/dc:subject"),
            "isbn": _isbn,
            "series": lambda r: _meta_name(r, "calibre:series"),
            "series_index": lambda r: _meta_name(r, "calibre:series_index"),
        }
        for field, mutate in mutators.items():
            with self.subTest(field=field):
                mutated = self.root / f"mut_{field}.epub"
                shutil.copy(str(out), str(mutated))
                _mutate_opf_epub(str(mutated), mutate)
                self.assertEqual(verify_epub_metadata(str(mutated), meta), [field])


class BuildEpubMetadataTests(TestCase):
    def setUp(self):
        self.scan_folder = ScanFolder.objects.create(
            path=tempfile.mkdtemp(), name="Sample [To Delete]", content_type="ebooks", is_active=True,
        )
        self.source = DataSource.objects.create(name="test_source", trust_level=0.8)
        self.book = create_test_book_with_file(
            file_path="/tmp/x.epub", file_format="epub", scan_folder=self.scan_folder,
        )
        self.final = FinalMetadata.objects.create(
            book=self.book,
            final_title="Great Book",
            final_author="",
            final_publisher="Acme",
            language="en",
            isbn="9781234567890",
            publication_year=1999,
            description="A great read",
            final_series="The Series",
            final_series_number="2",
            is_reviewed=True,
        )

    def _author(self, name, first, last):
        author = Author.objects.create(name=name, first_name=first, last_name=last)
        BookAuthor.objects.create(book=self.book, author=author, source=self.source, is_main_author=True, confidence=0.9)
        return author

    def _genre(self, name, confidence):
        genre = Genre.objects.create(name=name)
        BookGenre.objects.create(book=self.book, genre=genre, source=self.source, confidence=confidence, is_active=True)
        return genre

    def test_dict_keys_and_empty_omission(self):
        self._author("Jane Doe", "Jane", "Doe")
        self._genre("Fiction", 0.9)
        d = build_epub_metadata(self.book)
        self.assertEqual(d["title"], "Great Book")
        self.assertEqual(d["language"], "en")
        self.assertEqual(d["publisher"], "Acme")
        self.assertEqual(d["year"], 1999)
        self.assertEqual(d["description"], "A great read")
        self.assertEqual(d["isbn"], "9781234567890")
        self.assertEqual(d["series"], "The Series")
        self.assertEqual(d["series_index"], "2")
        self.assertEqual(d["subjects"], ["Fiction"])
        self.assertEqual(d["authors"], [{"name": "Jane Doe", "file_as": "Doe, Jane"}])

    def test_authors_from_main_relationships_file_as(self):
        self._author("Jane Doe", "Jane", "Doe")
        self._author("John Smith", "John", "Smith")
        d = build_epub_metadata(self.book)
        self.assertEqual(d["authors"], [
            {"name": "Jane Doe", "file_as": "Doe, Jane"},
            {"name": "John Smith", "file_as": "Smith, John"},
        ])

    def test_authors_fallback_splits_final_author(self):
        self.final.final_author = "Doe, Jane; Smith, John"
        self.final.save()
        d = build_epub_metadata(self.book)
        self.assertEqual(d["authors"], [{"name": "Doe, Jane"}, {"name": "Smith, John"}])

    def test_authors_fallback_splits_on_and(self):
        self.final.final_author = "Jane Doe and John Smith"
        self.final.save()
        d = build_epub_metadata(self.book)
        self.assertEqual(d["authors"], [{"name": "Jane Doe"}, {"name": "John Smith"}])

    def test_subjects_highest_confidence_first(self):
        self._genre("Zeta", 0.5)
        self._genre("Alpha", 0.9)
        self._genre("Beta", 0.7)
        d = build_epub_metadata(self.book)
        self.assertEqual(d["subjects"], ["Alpha", "Beta", "Zeta"])

    def test_authors_ordered_confidence_then_id(self):
        for name, first, last in [("Zeta", "Zeta", "Zz"), ("Alpha", "Alpha", "Aa"), ("Beta", "Beta", "Bb")]:
            author = Author.objects.create(name=name, first_name=first, last_name=last)
            BookAuthor.objects.create(book=self.book, author=author, source=self.source, is_main_author=True, confidence=0.5)
        d = build_epub_metadata(self.book)
        # Equal confidence -> insertion (id) order is the tie-break.
        self.assertEqual([a["name"] for a in d["authors"]], ["Zeta", "Alpha", "Beta"])

    def test_subjects_ordered_confidence_then_name(self):
        for name in ["Zeta", "Alpha", "Beta"]:
            genre = Genre.objects.create(name=name)
            BookGenre.objects.create(book=self.book, genre=genre, source=self.source, confidence=0.5, is_active=True)
        d = build_epub_metadata(self.book)
        # Equal confidence -> genre name ascending is the tie-break.
        self.assertEqual(d["subjects"], ["Alpha", "Beta", "Zeta"])
