"""Tests for the sidecar OPF builder and ``verify_opf_root``.

``build_sidecar_opf`` is a pure function (dict in, bytes out); ``verify_opf_root``
compares a parsed OPF root against the same dict. No database is touched, so
these run under ``SimpleTestCase``.
"""

import shutil
import tempfile
import uuid
from pathlib import Path

from django.test import SimpleTestCase
from lxml import etree as ET

from books.utils.safe_move.metadata_sync import verify_opf_root
from books.utils.safe_move.sidecar_opf import build_sidecar_opf, parse_sidecar_opf

OPF_NS = "http://www.idpf.org/2007/opf"
DC_NS = "http://purl.org/dc/elements/1.1/"
NS = {"dc": DC_NS, "opf": OPF_NS}

FULL = {
    "title": "Great Book",
    "authors": [{"name": "Jane Doe", "file_as": "Doe, Jane"}],
    "language": "en",
    "publisher": "Acme",
    "year": 1999,
    "description": "A great read",
    "subjects": ["Fiction", "Drama"],
    "isbn": "9781234567890",
    "series": "The Series",
    "series_index": "2",
}


def _old_opf(*, identifier=b"urn:uuid:old-id", scheme=b"UUID", uid=b"uid", extra=b""):
    scheme_attr = b' opf:scheme="' + scheme + b'"' if scheme else b""
    return (
        b'<?xml version="1.0" encoding="UTF-8"?>'
        b'<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="'
        + uid
        + b'" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">'
        b"<metadata>"
        b'<dc:identifier id="'
        + uid
        + b'"'
        + scheme_attr
        + b">"
        + identifier
        + b"</dc:identifier>"
        + extra
        + b"</metadata></package>"
    )


def _meta(root, name):
    m = root.find("opf:metadata", NS)
    for mm in m.findall("opf:meta", NS):
        if mm.get("name") == name:
            return mm
    return None


class BuildSidecarOpfTests(SimpleTestCase):
    def test_full_dict_writes_all_fields(self):
        out = build_sidecar_opf(FULL)
        root = parse_sidecar_opf(out)
        m = root.find("opf:metadata", NS)
        self.assertEqual(m.find("dc:title", NS).text, "Great Book")
        creators = m.findall("dc:creator", NS)
        self.assertEqual([c.text for c in creators], ["Jane Doe"])
        self.assertEqual(creators[0].get(f"{{{OPF_NS}}}role"), "aut")
        self.assertEqual(creators[0].get(f"{{{OPF_NS}}}file-as"), "Doe, Jane")
        self.assertEqual(m.find("dc:language", NS).text, "en")
        self.assertEqual(m.find("dc:publisher", NS).text, "Acme")
        self.assertEqual(m.find("dc:date", NS).text, "1999")
        self.assertEqual(m.find("dc:description", NS).text, "A great read")
        self.assertEqual([s.text for s in m.findall("dc:subject", NS)], ["Fiction", "Drama"])
        isbn = [i for i in m.findall("dc:identifier", NS) if i.get(f"{{{OPF_NS}}}scheme") == "ISBN"]
        self.assertEqual(len(isbn), 1)
        self.assertEqual(isbn[0].text, "9781234567890")
        self.assertEqual(_meta(root, "calibre:series").get("content"), "The Series")
        self.assertEqual(_meta(root, "calibre:series_index").get("content"), "2")

    def test_package_identifier_reused(self):
        out = build_sidecar_opf({"title": "T"}, old_opf_bytes=_old_opf())
        root = parse_sidecar_opf(out)
        self.assertEqual(root.get("unique-identifier"), "uid")
        ident = root.find("opf:metadata/dc:identifier", NS)
        self.assertEqual(ident.get("id"), "uid")
        self.assertEqual(ident.get(f"{{{OPF_NS}}}scheme"), "UUID")
        self.assertEqual(ident.text, "urn:uuid:old-id")

    def test_fresh_uuid_when_no_old_bytes(self):
        out = build_sidecar_opf({"title": "T"})
        root = parse_sidecar_opf(out)
        self.assertEqual(root.get("unique-identifier"), "BookId")
        ident = root.find("opf:metadata/dc:identifier", NS)
        self.assertEqual(ident.get("id"), "BookId")
        self.assertTrue(ident.text.startswith("urn:uuid:"))
        self.assertIsNone(ident.get(f"{{{OPF_NS}}}scheme"))

    def test_unparsable_old_bytes_give_new_uuid(self):
        out = build_sidecar_opf({"title": "T"}, old_opf_bytes=b"not xml at all")
        root = parse_sidecar_opf(out)
        ident = root.find("opf:metadata/dc:identifier", NS)
        self.assertTrue(ident.text.startswith("urn:uuid:"))
        self.assertNotEqual(ident.text, "urn:uuid:old-id")

    def test_cover_reference_only_when_cover_name(self):
        out = build_sidecar_opf({"title": "T"}, cover_name="cover.jpg")
        root = parse_sidecar_opf(out)
        self.assertEqual(_meta(root, "cover").get("content"), "cover-image")
        item = root.find("opf:manifest/opf:item", NS)
        self.assertEqual(item.get("id"), "cover-image")
        self.assertEqual(item.get("href"), "cover.jpg")
        self.assertEqual(item.get("media-type"), "image/jpeg")
        ref = root.find("opf:guide/opf:reference", NS)
        self.assertEqual(ref.get("type"), "cover")
        self.assertEqual(ref.get("href"), "cover.jpg")

        out2 = build_sidecar_opf({"title": "T"})
        root2 = parse_sidecar_opf(out2)
        self.assertIsNone(_meta(root2, "cover"))
        self.assertIsNone(root2.find("opf:manifest", NS))
        self.assertIsNone(root2.find("opf:guide", NS))

    def test_dict_without_series_writes_no_series_meta(self):
        meta = {"title": "T"}
        out = build_sidecar_opf(meta)
        root = parse_sidecar_opf(out)
        self.assertIsNone(_meta(root, "calibre:series"))
        self.assertIsNone(_meta(root, "calibre:series_index"))

    def test_stale_values_from_old_opf_gone(self):
        old = _old_opf(
            extra=(
                b"<dc:publisher>Old Pub</dc:publisher>"
                b"<dc:subject>Old Subject</dc:subject>"
                b'<meta name="calibre:series" content="Old Series"/>'
            )
        )
        out = build_sidecar_opf(
            {"title": "New", "publisher": "New Pub", "subjects": ["New Subject"], "series": "New Series"},
            old_opf_bytes=old,
        )
        root = parse_sidecar_opf(out)
        m = root.find("opf:metadata", NS)
        self.assertEqual(m.find("dc:publisher", NS).text, "New Pub")
        self.assertEqual([s.text for s in m.findall("dc:subject", NS)], ["New Subject"])
        self.assertEqual(_meta(root, "calibre:series").get("content"), "New Series")
        self.assertNotIn(b"Old Pub", out)
        self.assertNotIn(b"Old Subject", out)
        self.assertNotIn(b"Old Series", out)

    def test_escaping_round_trip(self):
        meta = {
            "title": 'A & B <C> "quoted" \u2014 caf\u00e9',
            "authors": [{"name": "X & Y <Z>", "file_as": "Z, X & Y"}],
            "description": 'd & e <f> "g" \u00f1',
        }
        out = build_sidecar_opf(meta)
        root = parse_sidecar_opf(out)
        m = root.find("opf:metadata", NS)
        self.assertEqual(m.find("dc:title", NS).text, 'A & B <C> "quoted" \u2014 caf\u00e9')
        self.assertEqual(m.find("dc:creator", NS).text, "X & Y <Z>")
        self.assertEqual(m.find("dc:creator", NS).get(f"{{{OPF_NS}}}file-as"), "Z, X & Y")
        self.assertEqual(m.find("dc:description", NS).text, 'd & e <f> "g" \u00f1')

    def test_external_entity_not_resolved(self):
        secret = b"XXE_SECRET_MARKER"
        secret_path = Path(tempfile.mkdtemp()) / "secret.txt"
        secret_path.write_bytes(secret)
        self.addCleanup(shutil.rmtree, str(secret_path.parent), ignore_errors=True)
        old = (
            b'<?xml version="1.0"?>'
            b'<!DOCTYPE package [<!ENTITY xxe SYSTEM "file://' + str(secret_path).encode() + b'">]>'
            b'<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="uid">'
            b"<metadata><dc:identifier xmlns:dc=\"http://purl.org/dc/elements/1.1/\" id=\"uid\">&xxe;</dc:identifier>"
            b"</metadata></package>"
        )
        out = build_sidecar_opf({"title": "Safe"}, old_opf_bytes=old)
        self.assertNotIn(secret, out)

    def test_empty_values_omitted(self):
        out = build_sidecar_opf({"title": "T", "publisher": "", "description": None, "subjects": ["", "Real"]})
        root = parse_sidecar_opf(out)
        m = root.find("opf:metadata", NS)
        self.assertIsNone(m.find("dc:publisher", NS))
        self.assertIsNone(m.find("dc:description", NS))
        self.assertEqual([s.text for s in m.findall("dc:subject", NS)], ["Real"])


class VerifyOpfRootTests(SimpleTestCase):
    def _mutated(self, mutate):
        root = parse_sidecar_opf(build_sidecar_opf(FULL))
        mutate(root)
        return root

    def test_clean_sidecar_verifies(self):
        root = parse_sidecar_opf(build_sidecar_opf(FULL))
        self.assertEqual(verify_opf_root(root, FULL), [])

    def _assert_changed(self, mutate, field):
        root = self._mutated(mutate)
        self.assertEqual(verify_opf_root(root, FULL), [field])

    def test_each_field_reported_exactly(self):
        m = lambda r: r.find("opf:metadata", NS)

        def change_text(path):
            def _mut(root):
                m(root).find(path, NS).text = "MUTATED"
            return _mut

        def change_creator(root):
            m(root).find("dc:creator", NS).text = "MUTATED"

        def change_subject(root):
            m(root).findall("dc:subject", NS)[0].text = "MUTATED"

        def change_isbn(root):
            for i in m(root).findall("dc:identifier", NS):
                if i.get(f"{{{OPF_NS}}}scheme") == "ISBN":
                    i.text = "1111111111111"

        def change_series(root):
            _meta(root, "calibre:series").set("content", "MUTATED")

        def change_series_index(root):
            _meta(root, "calibre:series_index").set("content", "99")

        cases = [
            ("title", change_text("dc:title")),
            ("language", change_text("dc:language")),
            ("publisher", change_text("dc:publisher")),
            ("year", change_text("dc:date")),
            ("description", change_text("dc:description")),
            ("authors", change_creator),
            ("subjects", change_subject),
            ("isbn", change_isbn),
            ("series", change_series),
            ("series_index", change_series_index),
        ]
        for field, mutate in cases:
            with self.subTest(field=field):
                self._assert_changed(mutate, field)

    def test_no_metadata_element_reports_all_keys(self):
        root = ET.fromstring(
            b'<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="uid"></package>'
        )
        self.assertEqual(verify_opf_root(root, {"title": "T"}), ["title"])
