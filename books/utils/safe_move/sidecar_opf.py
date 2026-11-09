"""Build a Calibre OPF 2.0 sidecar for a book's curated metadata.

Django free. ``build_sidecar_opf`` turns the same plain metadata dict the
in-EPUB sync consumes into a standalone OPF file (bytes), reusing the old
sidecar's package identifier when one exists so Calibre keeps seeing the same
book across regenerations. Nothing else is copied from the old file.
"""

import uuid
from posixpath import splitext

from lxml import etree as ET

OPF_NS = "http://www.idpf.org/2007/opf"
DC_NS = "http://purl.org/dc/elements/1.1/"

# XXE-safe parser for the old sidecar: an external entity must never resolve.
_OPF_PARSER = ET.XMLParser(remove_comments=False, resolve_entities=False, no_network=True)

IMAGE_MEDIA_BY_EXT = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".svg": "image/svg+xml",
}


def _number_str(value):
    try:
        f = float(value)
    except (ValueError, TypeError):
        return None
    if f == int(f):
        return str(int(f))
    return str(f)


def _year_str(year):
    try:
        return str(int(year))
    except (ValueError, TypeError):
        return str(year)


def _package_identifier(old_opf_bytes):
    """Return ``(text, scheme, id)`` of the old package identifier, or None.

    The package identifier is the ``dc:identifier`` whose ``id`` equals the
    package's ``unique-identifier`` attribute. Parsed XXE-safely; an unparsable
    or identifier-less file returns None (caller falls back to a fresh uuid).
    """
    if not old_opf_bytes:
        return None
    try:
        root = ET.fromstring(old_opf_bytes, _OPF_PARSER)
    except Exception:
        return None
    uid = root.get("unique-identifier")
    for ident in root.iter(f"{{{DC_NS}}}identifier"):
        if ident.get("id") == uid:
            return (
                ident.text or "",
                ident.get(f"{{{OPF_NS}}}scheme"),
                ident.get("id"),
            )
    return None


def _dc(parent, local, value):
    el = ET.SubElement(parent, f"{{{DC_NS}}}{local}")
    el.text = str(value)
    return el


def _meta(parent, name, content):
    el = ET.SubElement(parent, f"{{{OPF_NS}}}meta")
    el.set("name", name)
    el.set("content", str(content))
    return el


def parse_sidecar_opf(data):
    """Parse sidecar OPF bytes XXE-safely; raises on unparsable input."""
    return ET.fromstring(data, _OPF_PARSER)


def build_sidecar_opf(metadata, cover_name=None, old_opf_bytes=None):
    """Build a Calibre OPF 2.0 sidecar from a plain metadata dict; return bytes.

    ``metadata`` is the same plain dict ``build_epub_metadata`` produces:
    ``title``, ``authors`` (``{"name", "file_as"}``), ``language``,
    ``publisher``, ``year``, ``description``, ``subjects``, ``isbn``,
    ``series`` and ``series_index``. Empty values are omitted.

    The package identifier is reused from ``old_opf_bytes`` (text, opf:scheme
    and id) when present, otherwise a fresh ``uuid4`` identifier. Nothing else
    is copied from the old file. A cover reference (``meta name="cover"``, a
    manifest item and a guide reference of type ``cover``) is emitted only when
    ``cover_name`` is given.
    """
    metadata = metadata or {}
    ident = _package_identifier(old_opf_bytes)
    if ident is not None:
        ident_text, ident_scheme, ident_id = ident
        ident_id = ident_id or "BookId"
    else:
        ident_text = "urn:uuid:" + str(uuid.uuid4())
        ident_scheme = None
        ident_id = "BookId"

    root = ET.Element(
        f"{{{OPF_NS}}}package",
        attrib={"version": "2.0", "unique-identifier": ident_id},
        nsmap={None: OPF_NS, "dc": DC_NS, "opf": OPF_NS},
    )
    metadata_el = ET.SubElement(root, f"{{{OPF_NS}}}metadata")

    ident_el = ET.SubElement(metadata_el, f"{{{DC_NS}}}identifier")
    ident_el.set("id", ident_id)
    if ident_scheme:
        ident_el.set(f"{{{OPF_NS}}}scheme", ident_scheme)
    ident_el.text = ident_text

    if metadata.get("title"):
        _dc(metadata_el, "title", metadata["title"])

    for author in metadata.get("authors") or []:
        if not isinstance(author, dict):
            continue
        name = author.get("name")
        if not name:
            continue
        el = ET.SubElement(metadata_el, f"{{{DC_NS}}}creator")
        el.set(f"{{{OPF_NS}}}role", "aut")
        file_as = author.get("file_as")
        if file_as:
            el.set(f"{{{OPF_NS}}}file-as", str(file_as))
        el.text = str(name)

    if metadata.get("language"):
        _dc(metadata_el, "language", metadata["language"])
    if metadata.get("publisher"):
        _dc(metadata_el, "publisher", metadata["publisher"])
    if metadata.get("year"):
        _dc(metadata_el, "date", _year_str(metadata["year"]))
    if metadata.get("description"):
        _dc(metadata_el, "description", metadata["description"])
    for subject in metadata.get("subjects") or []:
        if subject:
            _dc(metadata_el, "subject", subject)
    if metadata.get("isbn"):
        isbn_el = ET.SubElement(metadata_el, f"{{{DC_NS}}}identifier")
        isbn_el.set(f"{{{OPF_NS}}}scheme", "ISBN")
        isbn_el.text = str(metadata["isbn"])
    if metadata.get("series"):
        _meta(metadata_el, "calibre:series", str(metadata["series"]))
        idx = _number_str(metadata.get("series_index"))
        if idx is not None:
            _meta(metadata_el, "calibre:series_index", idx)

    if cover_name:
        _meta(metadata_el, "cover", "cover-image")
        manifest_el = ET.SubElement(root, f"{{{OPF_NS}}}manifest")
        ext = splitext(cover_name)[1].lower()
        media_type = IMAGE_MEDIA_BY_EXT.get(ext, "image/jpeg")
        item = ET.SubElement(manifest_el, f"{{{OPF_NS}}}item")
        item.set("id", "cover-image")
        item.set("href", cover_name)
        item.set("media-type", media_type)
        guide_el = ET.SubElement(root, f"{{{OPF_NS}}}guide")
        ref = ET.SubElement(guide_el, f"{{{OPF_NS}}}reference")
        ref.set("type", "cover")
        ref.set("href", cover_name)

    return ET.tostring(root, encoding="utf-8", xml_declaration=True)
