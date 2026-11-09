"""Lossless EPUB fixer: analyze and repair structural issues without modifying the source.

Imports the read-only parser from books.utils.epub_check and never edits it.
Every fix is lossless in spirit: it drops or corrects OPF/XHTML metadata but
never rewrites the bytes of an entry that does not need a change.
"""

import posixpath
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from lxml import etree as ET

from books.utils.epub_check.reader import EpubReader
from books.utils.epub_check.rules import MEDIA_TYPE_BY_EXT, XHTML_MEDIA_TYPES
from books.utils.epub_fix import cover_page as _cover_page

OPF_NS = "http://www.idpf.org/2007/opf"
DC_NS = "http://purl.org/dc/elements/1.1/"
DCTERMS_NS = "http://purl.org/dc/terms/"
CALIBRE_NS = "http://calibre.kovidgoyal.net/2009/metadata"

# lxml preserves comments and namespace prefixes natively on round-trip, so the
# OPF is edited with lxml and no global namespace registration is needed.
# resolve_entities=False + no_network=True: a hostile OPF must not exfiltrate
# local files or fetch remote resources (XXE-safe).
_OPF_PARSER = ET.XMLParser(remove_comments=False, resolve_entities=False, no_network=True)

MIMETYPE_VALUE = b"application/epub+zip"

# An internal ENTITY declaration in the OPF (``<!ENTITY name "value">``) is a
# red flag for hostile input; the fixer refuses to write any output rather than
# round-trip it. External entities (SYSTEM/PUBLIC) are already handled by the
# XXE-safe parser and are deliberately not matched here.
_OPF_INTERNAL_ENTITY = re.compile(rb"<!\s*ENTITY\s+[\w:.-]+\s+\"", re.IGNORECASE)

IMAGE_MEDIA_BY_EXT = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".svg": "image/svg+xml",
}

_REFERENCE_EXTS = (".xhtml", ".html", ".htm", ".css", ".svg")


@dataclass
class Fix:
    code: str
    description: str


def plan_fixes(input_path, cover=None, fix_encoding=False) -> List[Fix]:
    """Return the fixes that would be applied to ``input_path`` (no writes)."""
    plan, _entries, _dropped, _modified = _compute(str(input_path), cover, fix_encoding)
    return plan


# --------------------------------------------------------------------------- #
# cover handling
# --------------------------------------------------------------------------- #


def _validate_cover(cover_path) -> Tuple[bytes, str, str]:
    """Return (bytes, extension, media-type) for a valid cover image.

    Raises ValueError for an unreadable path or a non-image extension, so the
    caller refuses to produce any output.
    """
    p = Path(cover_path)
    if not p.is_file():
        raise ValueError(f"cover image is not a readable file: {cover_path}")
    ext = p.suffix.lower()
    media_type = IMAGE_MEDIA_BY_EXT.get(ext)
    if media_type is None:
        raise ValueError(f"cover is not a recognised image type: {cover_path}")
    try:
        data = p.read_bytes()
    except OSError as exc:
        raise ValueError(f"cover image is unreadable: {cover_path} ({exc})") from exc
    return data, ext, media_type


def _cover_referenced(href, source, names) -> bool:
    """True if any XHTML/CSS/SVG entry references the cover's file name."""
    base = posixpath.basename(href)
    if not base:
        return False
    needle = base.encode("utf-8")
    for arc in names:
        ext = posixpath.splitext(arc)[1].lower()
        if ext in _REFERENCE_EXTS:
            data = source.get(arc)
            if data and needle in data:
                return True
    return False


def _choose_cover_href(ext, manifest_hrefs, names, opf_dir):
    """Pick ``cover.<ext>``, or the smallest free ``cover-<n>.<ext>``.

    ``cover.<ext>`` is used only when that href is not already declared in the
    manifest and its resolved package path is not present in ``names``.
    Otherwise ``cover-<n>.<ext>`` is chosen with the smallest free ``n``
    (starting at 2), so the new cover never collides with an existing item or
    entry.
    """
    candidate = "cover" + ext
    n = 2
    while True:
        resolved = posixpath.normpath(posixpath.join(opf_dir, candidate)) if opf_dir else candidate
        if candidate not in manifest_hrefs and resolved not in names:
            return candidate, resolved
        candidate = f"cover-{n}{ext}"
        n += 1


# --------------------------------------------------------------------------- #
# encoding declaration
# --------------------------------------------------------------------------- #


def _needs_encoding_decl(raw: bytes) -> bool:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return False
    head = text[:200]
    if "encoding=" in head or "charset" in head.lower():
        return False
    return True


def _add_encoding_decl(raw: bytes) -> bytes:
    # Keep a leading UTF-8 BOM first, and insert the encoding declaration
    # before any standalone= pseudo-attribute (the XML spec requires that order).
    bom = b""
    if raw.startswith(b"\xef\xbb\xbf"):
        bom = b"\xef\xbb\xbf"
        raw = raw[3:]
    text = raw.decode("utf-8")
    stripped = text.lstrip()
    if stripped.startswith("<?xml") and "?>" in text:
        end = text.find("?>")
        decl = text[:end]
        if "encoding=" not in decl:
            if "standalone=" in decl:
                i = decl.find("standalone=")
                decl = decl[:i] + 'encoding="utf-8" ' + decl[i:]
            else:
                decl = decl + ' encoding="utf-8"'
        text = decl + text[end:]
    else:
        text = '<?xml version="1.0" encoding="utf-8"?>\n' + text
    return bom + text.encode("utf-8")


# --------------------------------------------------------------------------- #
# core analysis
# --------------------------------------------------------------------------- #


def _set_or_create_text(parent, ns, local, value):
    """Set the text of the first {ns}local child of ``parent``, or append one.

    Returns True when the element was created or its text changed.
    """
    tag = f"{{{ns}}}{local}"
    elem = parent.find(tag)
    if elem is None:
        elem = ET.SubElement(parent, tag)
        elem.text = value
        return True
    if elem.text != value:
        elem.text = value
        return True
    return False


def _replace_children(parent, ns, local, new_elems):
    """Replace every {ns}local child with ``new_elems`` at the first's spot."""
    tag = f"{{{ns}}}{local}"
    existing = parent.findall(tag)

    def _sig(el):
        return (el.tag, el.text or "", tuple(sorted(el.attrib.items())))

    if [_sig(e) for e in existing] == [_sig(e) for e in new_elems]:
        return False
    index = list(parent).index(existing[0]) if existing else len(list(parent))
    for e in existing:
        parent.remove(e)
    for i, el in enumerate(new_elems):
        parent.insert(index + i, el)
    return True


def _set_meta_name_content(metadata_el, name, content):
    for meta in metadata_el.findall(f"{{{OPF_NS}}}meta"):
        if meta.get("name") == name:
            if meta.get("content") != content:
                meta.set("content", content)
                return True
            return False
    el = ET.SubElement(metadata_el, f"{{{OPF_NS}}}meta")
    el.set("name", name)
    el.set("content", content)
    return True


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


def _unique_id(existing_ids, prefix):
    n = 1
    while f"{prefix}-{n}" in existing_ids:
        n += 1
    return f"{prefix}-{n}"


def _creator_role(metadata_el, creator):
    """Return a dc:creator's role: opf:role attr, a refines role meta, or None."""
    role = (creator.get(f"{{{OPF_NS}}}role") or "").strip()
    if role:
        return role
    cid = creator.get("id")
    if cid:
        for meta in metadata_el.findall(f"{{{OPF_NS}}}meta"):
            if meta.get("refines") == f"#{cid}" and meta.get("property") == "role":
                text = (meta.text or "").strip()
                if text:
                    return text
    return None


def _epub3_authors_match(metadata_el, author_creators, authors):
    """True when the author-role creators already mirror ``authors``.

    Each entry's name matches a creator's text, its role refines meta is
    ``aut``, and its file-as refines meta equals the entry's file-as (both
    absent, or both present and equal), all in document order.
    """
    named = [a for a in authors if a.get("name")]
    if len(author_creators) != len(named):
        return False
    for creator, author in zip(author_creators, named):
        if (creator.text or "").strip() != str(author["name"]):
            return False
        cid = creator.get("id")
        role = None
        file_as = None
        if cid:
            for meta in metadata_el.findall(f"{{{OPF_NS}}}meta"):
                if meta.get("refines") == f"#{cid}":
                    prop = meta.get("property")
                    if prop == "role":
                        role = (meta.text or "").strip()
                    elif prop == "file-as":
                        file_as = (meta.text or "").strip()
        if role != "aut":
            return False
        want_file_as = author.get("file_as")
        if want_file_as:
            if file_as != str(want_file_as):
                return False
        elif file_as is not None:
            return False
    return True


def _set_creators(metadata_el, authors, is_epub3, existing_ids):
    """Replace author-role dc:creator elements with the dict authors.

    A creator is an author when it carries opf:role ``aut``, a refines role
    meta of ``aut``, or no role at all. Non-author creators and dc:contributor
    elements are left untouched; refines metas targeting a removed creator are
    removed. New authors are inserted at the position of the first replaced
    creator. EPUB 3 authors carry a unique id plus refines metas for role and
    file-as; EPUB 2 authors carry opf:role/opf:file-as attributes.
    """
    role_attr = f"{{{OPF_NS}}}role"
    fileas_attr = f"{{{OPF_NS}}}file-as"
    author_creators = [
        c for c in metadata_el.findall(f"{{{DC_NS}}}creator")
        if _creator_role(metadata_el, c) in (None, "aut")
    ]

    # Idempotency: when the author creators already mirror the dict (text,
    # role aut, file-as through refines) leave them and their refines metas
    # untouched so repeated syncs are byte-stable apart from dcterms:modified.
    if is_epub3 and _epub3_authors_match(metadata_el, author_creators, authors):
        return False

    new_elems = []
    for author in authors:
        name = author.get("name")
        if not name:
            continue
        el = ET.Element(f"{{{DC_NS}}}creator", nsmap={"opf": OPF_NS})
        el.text = str(name)
        if is_epub3:
            cid = _unique_id(existing_ids, "creator")
            el.set("id", cid)
            existing_ids.add(cid)
            new_elems.append(el)
            role_meta = ET.Element(f"{{{OPF_NS}}}meta")
            role_meta.set("refines", f"#{cid}")
            role_meta.set("property", "role")
            role_meta.set("scheme", "marc:relators")
            role_meta.text = "aut"
            new_elems.append(role_meta)
            file_as = author.get("file_as")
            if file_as:
                fa = ET.Element(f"{{{OPF_NS}}}meta")
                fa.set("refines", f"#{cid}")
                fa.set("property", "file-as")
                fa.text = str(file_as)
                new_elems.append(fa)
        else:
            el.set(role_attr, "aut")
            file_as = author.get("file_as")
            if file_as:
                el.set(fileas_attr, str(file_as))
            new_elems.append(el)

    removed_ids = [c.get("id") for c in author_creators if c.get("id")]

    def _sig(el):
        return (el.tag, el.text or "", tuple(sorted(el.attrib.items())))

    # Idempotency: unchanged EPUB 2 authors (no ids/metas to reconcile) return
    # without touching the tree.
    if not removed_ids and [_sig(c) for c in author_creators] == [_sig(e) for e in new_elems]:
        return False

    insert_index = list(metadata_el).index(author_creators[0]) if author_creators else len(list(metadata_el))

    changed = False
    for c in author_creators:
        metadata_el.remove(c)
        changed = True
    for meta in list(metadata_el.findall(f"{{{OPF_NS}}}meta")):
        ref = meta.get("refines")
        if ref and ref.startswith("#") and ref[1:] in removed_ids:
            metadata_el.remove(meta)
            changed = True
    for i, el in enumerate(new_elems):
        metadata_el.insert(insert_index + i, el)
    if new_elems:
        changed = True

    return changed


def _set_subjects(metadata_el, subjects):
    new_elems = []
    for s in subjects:
        if not s:
            continue
        el = ET.Element(f"{{{DC_NS}}}subject")
        el.text = str(s)
        new_elems.append(el)
    return _replace_children(metadata_el, DC_NS, "subject", new_elems)


def _set_isbn(metadata_el, isbn, is_epub3, unique_id):
    scheme = f"{{{OPF_NS}}}scheme"
    new_text = f"urn:isbn:{isbn}" if is_epub3 else str(isbn)
    target = None
    for ident in metadata_el.findall(f"{{{DC_NS}}}identifier"):
        if unique_id is not None and ident.get("id") == unique_id:
            continue  # never modify the package unique identifier
        if ident.get(scheme) == "ISBN":
            target = ident
            break
        if is_epub3 and (ident.text or "").startswith("urn:isbn:"):
            target = ident
            break
    if target is not None:
        changed = target.text != new_text
        if changed:
            target.text = new_text
        if not is_epub3 and target.get(scheme) != "ISBN":
            target.set(scheme, "ISBN")
            changed = True
        return changed
    # No other ISBN exists: if the unique identifier already carries this exact
    # ISBN value, nothing to add.
    for ident in metadata_el.findall(f"{{{DC_NS}}}identifier"):
        if unique_id is not None and ident.get("id") == unique_id:
            text = ident.text or ""
            if is_epub3 and text == new_text:
                return False
            if not is_epub3 and ident.get(scheme) == "ISBN" and text == new_text:
                return False
    el = ET.SubElement(metadata_el, f"{{{DC_NS}}}identifier", nsmap={"opf": OPF_NS})
    el.text = new_text
    if not is_epub3:
        el.set(scheme, "ISBN")
    return True


def _set_series(metadata_el, series, series_index, is_epub3):
    changed = _set_meta_name_content(metadata_el, "calibre:series", str(series))
    if series_index:
        idx = _number_str(series_index)
        if idx is not None:
            changed = _set_meta_name_content(metadata_el, "calibre:series_index", idx) or changed
    if is_epub3:
        changed = _set_collection(metadata_el, str(series), series_index) or changed
    return changed


def _set_collection(metadata_el, series, series_index):
    changed = False
    coll = None
    for meta in metadata_el.findall(f"{{{OPF_NS}}}meta"):
        if meta.get("property") == "belongs-to-collection":
            coll = meta
            break
    if coll is None:
        coll = ET.SubElement(metadata_el, f"{{{OPF_NS}}}meta")
        coll.set("property", "belongs-to-collection")
        coll.set("id", "series-1")
        coll.text = series
        changed = True
    elif coll.text != series:
        coll.text = series
        changed = True
    cid = coll.get("id") or "series-1"
    ref = f"#{cid}"
    ct = gp = None
    for meta in metadata_el.findall(f"{{{OPF_NS}}}meta"):
        if meta.get("refines") == ref:
            prop = meta.get("property")
            if prop == "collection-type":
                ct = meta
            elif prop == "group-position":
                gp = meta
    if ct is None:
        ct = ET.SubElement(metadata_el, f"{{{OPF_NS}}}meta")
        ct.set("refines", ref)
        ct.set("property", "collection-type")
        ct.text = "series"
        changed = True
    elif ct.text != "series":
        ct.text = "series"
        changed = True
    idx = _number_str(series_index)
    if idx is not None:
        if gp is None:
            gp = ET.SubElement(metadata_el, f"{{{OPF_NS}}}meta")
            gp.set("refines", ref)
            gp.set("property", "group-position")
            gp.text = idx
            changed = True
        elif gp.text != idx:
            gp.text = idx
            changed = True
    return changed


def _set_modified(metadata_el):
    from datetime import datetime, timezone

    value = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for meta in metadata_el.findall(f"{{{OPF_NS}}}meta"):
        if meta.get("property") == "dcterms:modified":
            meta.text = value
            return True
    el = ET.SubElement(metadata_el, f"{{{OPF_NS}}}meta")
    el.set("property", "dcterms:modified")
    el.text = value
    return True


def _sync_metadata(opf_root, metadata):
    """Write curated metadata into the OPF ``metadata`` element in place.

    Returns True when the OPF changed. Empty/missing values are skipped so an
    existing element is never clobbered.
    """
    if not metadata:
        return False
    NS = {"opf": OPF_NS}
    metadata_el = opf_root.find("opf:metadata", NS)
    if metadata_el is None:
        return False
    is_epub3 = (opf_root.get("version") or "").startswith("3")
    existing_ids = {el.get("id") for el in opf_root.iter() if el.get("id")}
    unique_id = opf_root.get("unique-identifier")
    changed = False

    for key, local in (("title", "title"), ("language", "language"),
                       ("publisher", "publisher"), ("description", "description")):
        value = metadata.get(key)
        if value:
            changed = _set_or_create_text(metadata_el, DC_NS, local, str(value)) or changed

    year = metadata.get("year")
    if year:
        year_str = _year_str(year)
        date_el = metadata_el.find(f"{{{DC_NS}}}date")
        if date_el is None or not (date_el.text or "").startswith(year_str):
            changed = _set_or_create_text(metadata_el, DC_NS, "date", year_str) or changed

    authors = metadata.get("authors")
    if authors:
        changed = _set_creators(metadata_el, authors, is_epub3, existing_ids) or changed

    subjects = metadata.get("subjects")
    if subjects:
        changed = _set_subjects(metadata_el, subjects) or changed

    isbn = metadata.get("isbn")
    if isbn:
        changed = _set_isbn(metadata_el, isbn, is_epub3, unique_id) or changed

    series = metadata.get("series")
    if series:
        changed = _set_series(metadata_el, series, metadata.get("series_index"), is_epub3) or changed

    if is_epub3:
        changed = _set_modified(metadata_el) or changed

    return changed


def _compute(input_path, cover=None, fix_encoding=False, metadata=None):
    """Analyze the EPUB and return (plan, entries, dropped, modified).

    ``entries`` is an ordered arcname -> bytes map of the final package (the
    ``mimetype`` entry is always present). ``dropped``/``modified`` list the
    arcnames removed/changed relative to the source.
    """
    fixes: List[Fix] = []
    dropped: List[str] = []
    modified: List[str] = []

    cover_info: Optional[Tuple[bytes, str, str]] = None
    if cover is not None:
        cover_info = _validate_cover(cover)

    reader = EpubReader(input_path)
    try:
        names = list(reader.namelist)
        source = {n: reader.read(n) for n in names}
        opf_path = reader.opf_path
        manifest = list(reader.manifest)
        manifest_hrefs = {m["href"] for m in manifest}
        spine = list(reader.spine)

        entries: Dict[str, bytes] = {n: source[n] for n in names}

        # --- MIMETYPE-001 ------------------------------------------------- #
        if "mimetype" not in entries:
            entries["mimetype"] = MIMETYPE_VALUE
            fixes.append(Fix("MIMETYPE-001", "mimetype entry missing; add it first and stored"))
        elif reader.mimetype is None:
            fixes.append(Fix("MIMETYPE-001", "mimetype entry unreadable; repack first and stored"))
        else:
            mm = reader.mimetype
            if not mm["first"] or mm["compress_type"] != zipfile.ZIP_STORED:
                fixes.append(Fix("MIMETYPE-001", "mimetype not first/stored; repack first and stored"))

        # --- OPF analysis ------------------------------------------------- #
        manifest_ids = {m["id"] for m in manifest}
        removed_spine = [s for s in spine if s not in manifest_ids]
        kept_spine = [s for s in spine if s in manifest_ids]
        kept_spine_set = set(kept_spine)

        manifest_kept: List[Dict] = []
        for m in manifest:
            if m["resolved"] not in names and m["id"] not in kept_spine_set:
                fixes.append(Fix("OPF-002", f"drop manifest item '{m['id']}' (missing file '{m['href']}')"))
            else:
                manifest_kept.append(m)

        if removed_spine:
            fixes.append(Fix("OPF-003", "drop spine itemref(s) not in manifest: " + ", ".join(removed_spine)))

        media_fix_ids: Dict[str, str] = {}
        for m in manifest_kept:
            ext = posixpath.splitext(m["href"] or "")[1].lower()
            expected = MEDIA_TYPE_BY_EXT.get(ext)
            if expected and m["media_type"] and m["media_type"] != expected:
                media_fix_ids[m["id"]] = expected
                fixes.append(Fix("OPF-006", f"media-type '{m['media_type']}' -> '{expected}' for '{m['href']}'"))

        enc_fix: List[str] = []
        if fix_encoding:
            for m in manifest_kept:
                if m["media_type"] in XHTML_MEDIA_TYPES and m["resolved"] in names:
                    if _needs_encoding_decl(source[m["resolved"]]):
                        enc_fix.append(m["resolved"])
                        fixes.append(Fix("HTM-002", f"add XML encoding declaration to '{m['href']}'"))

        # --- OPF mutation ------------------------------------------------- #
        opf_bytes = source.get(opf_path) if opf_path else None
        if opf_bytes is not None and _OPF_INTERNAL_ENTITY.search(opf_bytes):
            raise ValueError("OPF declares entities")
        opf_root = ET.fromstring(opf_bytes, _OPF_PARSER) if opf_bytes is not None else None
        cover_arc: Optional[str] = None
        removed_cover_files: List[str] = []

        if opf_root is not None:
            NS = {"opf": OPF_NS}
            manifest_el = opf_root.find("opf:manifest", NS)
            spine_el = opf_root.find("opf:spine", NS)
            metadata_el = opf_root.find("opf:metadata", NS)
            changed = False

            if spine_el is not None and removed_spine:
                for ir in list(spine_el.findall("opf:itemref", NS)):
                    if ir.get("idref") not in manifest_ids:
                        spine_el.remove(ir)
                        changed = True

            kept_ids = {m["id"] for m in manifest_kept}
            if manifest_el is not None:
                for item in list(manifest_el.findall("opf:item", NS)):
                    if item.get("id") not in kept_ids:
                        manifest_el.remove(item)
                        changed = True
                for item in list(manifest_el.findall("opf:item", NS)):
                    mid = item.get("id")
                    if mid in media_fix_ids:
                        item.set("media-type", media_fix_ids[mid])
                        changed = True

            if cover_info is not None:
                if manifest_el is None or metadata_el is None:
                    raise ValueError("package has no manifest or metadata element; cannot embed cover")
                cdata, cext, cmt = cover_info
                opf_dir = posixpath.dirname(opf_path) if opf_path else ""

                # Idempotency: when the incoming cover bytes already sit at an
                # existing cover-image entry, the cover is already embedded; a
                # second pass with the same cover must change nothing (no new
                # entry, no new manifest item, no page rewrite).
                already_embedded = False
                for item in list(manifest_el.findall("opf:item", NS)):
                    if "cover-image" in (item.get("properties") or "").split():
                        href = item.get("href", "")
                        resolved = (
                            posixpath.normpath(posixpath.join(opf_dir, href))
                            if opf_dir
                            else posixpath.normpath(href)
                        )
                        if resolved in entries and entries[resolved] == cdata:
                            already_embedded = True
                            break

                if not already_embedded:
                    # Choose a unique manifest id when "cover-image" is already taken.
                    new_cover_id = "cover-image"
                    if new_cover_id in manifest_ids:
                        n = 2
                        while f"cover-image-{n}" in manifest_ids:
                            n += 1
                        new_cover_id = f"cover-image-{n}"
                    # Replace the existing cover. A page-referenced old image keeps
                    # its manifest item (declared) but loses the cover-image
                    # property; an unreferenced old image is dropped entirely.
                    for item in list(manifest_el.findall("opf:item", NS)):
                        props = (item.get("properties") or "").split()
                        if "cover-image" in props:
                            href = item.get("href", "")
                            if _cover_referenced(href, source, names):
                                remaining = [p for p in props if p != "cover-image"]
                                if remaining:
                                    item.set("properties", " ".join(remaining))
                                else:
                                    item.attrib.pop("properties", None)
                                changed = True
                            else:
                                removed_cover_files.append(href)
                                manifest_el.remove(item)
                                changed = True
                    cover_href, cover_arc = _choose_cover_href(cext, manifest_hrefs, names, opf_dir)
                    item = ET.SubElement(manifest_el, f"{{{OPF_NS}}}item")
                    item.set("id", new_cover_id)
                    item.set("href", cover_href)
                    item.set("media-type", cmt)
                    item.set("properties", "cover-image")
                    changed = True
                    for meta in list(metadata_el.findall("opf:meta", NS)):
                        if meta.get("name") == "cover":
                            meta.set("content", new_cover_id)
                            break
                    else:
                        meta = ET.SubElement(metadata_el, f"{{{OPF_NS}}}meta")
                        meta.set("name", "cover")
                        meta.set("content", new_cover_id)
                    fixes.append(Fix("COVER-EMBED", f"embed cover image as '{cover_href}' (manifest id '{new_cover_id}')"))

            # --- COVER-PAGE rewrite ----------------------------------------- #
            if cover_info is not None and opf_root is not None and cover_arc is not None:
                page = _cover_page.find_cover_page(opf_root, opf_path, entries)
                if page is None:
                    fixes.append(Fix("COVER-PAGE-SKIP", "no cover page found in the archive"))
                else:
                    kind, image_ref = _cover_page.classify_cover_page(entries[page])
                    if kind != "pure":
                        fixes.append(Fix("COVER-PAGE-SKIP", f"cover page '{page}' is not a pure image page"))
                    else:
                        resolved = posixpath.normpath(
                            posixpath.join(posixpath.dirname(page), image_ref)
                        ) if posixpath.dirname(page) else posixpath.normpath(image_ref)
                        if resolved == cover_arc:
                            pass  # already points at the new cover; nothing to change
                        else:
                            new_ref = _cover_page.relative_href(page, cover_arc)
                            rewritten = _cover_page.rewrite_cover_page(entries[page], image_ref, new_ref)
                            if rewritten is None:
                                fixes.append(Fix("COVER-PAGE-SKIP", f"cover page '{page}' image reference is not unique"))
                            else:
                                entries[page] = rewritten
                                modified.append(page)
                                fixes.append(Fix("COVER-PAGE", f"rewrite cover page '{page}' image to '{new_ref}'"))

            if metadata:
                changed = _sync_metadata(opf_root, metadata) or changed

            if changed:
                entries[opf_path] = ET.tostring(opf_root.getroottree(), encoding="utf-8", xml_declaration=True)
                modified.append(opf_path)

        # --- HTM-002 entry rewrite ---------------------------------------- #
        for arc in enc_fix:
            entries[arc] = _add_encoding_decl(source[arc])
            modified.append(arc)

        # --- cover file replacement (drop unreferenced old cover files) ---- #
        for href in removed_cover_files:
            opf_dir = posixpath.dirname(opf_path) if opf_path else ""
            resolved = posixpath.normpath(posixpath.join(opf_dir, href)) if opf_dir else href
            if resolved in entries and resolved != cover_arc:
                del entries[resolved]
                dropped.append(resolved)

        if cover_info is not None and cover_arc is not None:
            entries[cover_arc] = cover_info[0]

    finally:
        reader.close()

    return fixes, entries, dropped, modified
