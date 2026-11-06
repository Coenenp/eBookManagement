"""Lossless EPUB fixer: analyze and repair structural issues without modifying the source.

Imports the read-only parser from books.utils.epub_check and never edits it.
Every fix is lossless in spirit: it drops or corrects OPF/XHTML metadata but
never rewrites the bytes of an entry that does not need a change.
"""

import posixpath
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from lxml import etree as ET

from books.utils.epub_check.reader import EpubReader
from books.utils.epub_check.rules import MEDIA_TYPE_BY_EXT, XHTML_MEDIA_TYPES

OPF_NS = "http://www.idpf.org/2007/opf"

# lxml preserves comments and namespace prefixes natively on round-trip, so the
# OPF is edited with lxml and no global namespace registration is needed.
# resolve_entities=False + no_network=True: a hostile OPF must not exfiltrate
# local files or fetch remote resources (XXE-safe).
_OPF_PARSER = ET.XMLParser(remove_comments=False, resolve_entities=False, no_network=True)

MIMETYPE_VALUE = b"application/epub+zip"

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


def _compute(input_path, cover=None, fix_encoding=False):
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
                # Choose a unique manifest id when "cover-image" is already taken.
                new_cover_id = "cover-image"
                if new_cover_id in manifest_ids:
                    n = 2
                    while f"cover-image-{n}" in manifest_ids:
                        n += 1
                    new_cover_id = f"cover-image-{n}"
                opf_dir = posixpath.dirname(opf_path) if opf_path else ""
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
