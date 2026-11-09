"""Cover-page detection and rewrite for the lossless EPUB fixer.

Django free. The cover *page* is the XHTML/SVG spine item that shows the cover
*image*. When a new cover image is embedded, a pure cover page (a body holding
only a single image reference, with no text) is rewritten so that image points
at the newly embedded cover; any other page is left byte-for-byte untouched and
flagged. Everything here parses with ``resolve_entities=False`` and
``no_network=True`` so a hostile page cannot resolve local files or fetch
remote resources (XXE-safe).
"""

import hashlib
import posixpath
import zipfile

from lxml import etree as ET

OPF_NS = "http://www.idpf.org/2007/opf"
XHTML_NS = "http://www.w3.org/1999/xhtml"
SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"
CONTAINER_NS = "urn:oasis:names:tc:opendocument:xmlns:container"

_PAGE_PARSER = ET.XMLParser(remove_comments=False, resolve_entities=False, no_network=True)

_WRAPPER_TAGS = {
    f"{{{XHTML_NS}}}div",
    f"{{{XHTML_NS}}}p",
    f"{{{SVG_NS}}}svg",
    "div",
    "p",
    "svg",
}


def _resolve(from_path, ref):
    """Resolve ``ref`` (relative to ``from_path``'s directory) to a package path."""
    base = posixpath.dirname(from_path)
    return posixpath.normpath(posixpath.join(base, ref)) if base else posixpath.normpath(ref)


def find_cover_page(opf_root, opf_path, entries):
    """Return the archive path of the cover page, or None.

    The cover page is the guide ``reference`` with ``type="cover"`` when one is
    present, otherwise the first spine item. The returned path is the resolved
    archive path, and is only returned when it exists in ``entries``.
    """
    guide = opf_root.find(f"{{{OPF_NS}}}guide")
    if guide is not None:
        for ref in guide.findall(f"{{{OPF_NS}}}reference"):
            if (ref.get("type") or "").strip().lower() == "cover":
                href = ref.get("href")
                if href:
                    path = _resolve(opf_path, href)
                    if path in entries:
                        return path

    manifest = opf_root.find(f"{{{OPF_NS}}}manifest")
    href_by_id = {}
    if manifest is not None:
        for item in manifest.findall(f"{{{OPF_NS}}}item"):
            mid = item.get("id")
            href = item.get("href")
            if mid and href:
                href_by_id[mid] = href

    spine = opf_root.find(f"{{{OPF_NS}}}spine")
    if spine is not None:
        for itemref in spine.findall(f"{{{OPF_NS}}}itemref"):
            href = href_by_id.get(itemref.get("idref"))
            if href:
                path = _resolve(opf_path, href)
                if path in entries:
                    return path
    return None


def _find_body(root):
    body = root.find(f"{{{XHTML_NS}}}body")
    if body is not None:
        return body
    for el in root.iter():
        tag = el.tag if isinstance(el.tag, str) else ""
        if tag == "body" or tag.endswith("}body"):
            return el
    return None


def _image_elements(body):
    """Return ``[(element, ref), ...]`` for every img / svg image under ``body``."""
    result = []
    for el in body.iter():
        tag = el.tag if isinstance(el.tag, str) else ""
        if not isinstance(tag, str):
            continue
        local = tag.rsplit("}", 1)[-1]
        if local == "img":
            result.append((el, el.get("src") or ""))
        elif local == "image" and tag.startswith(f"{{{SVG_NS}}}"):
            result.append((el, el.get("href") or el.get(f"{{{XLINK_NS}}}href") or ""))
    return result


def classify_cover_page(page_bytes):
    """Classify a cover page as ("pure", image_ref) or ("not-pure", None).

    "pure" means that, ignoring whitespace, the body holds no text and exactly
    one image reference (an ``img`` with ``src``, or an svg ``image`` with
    ``href``/``xlink:href``) nested only in ``div``/``p``/``svg`` wrappers.
    """
    try:
        root = ET.fromstring(page_bytes, _PAGE_PARSER)
    except Exception:
        return ("not-pure", None)

    body = _find_body(root)
    if body is None:
        return ("not-pure", None)

    if "".join(body.itertext()).strip():
        return ("not-pure", None)

    images = _image_elements(body)
    if len(images) != 1:
        return ("not-pure", None)

    el, ref = images[0]
    node = el.getparent()
    while node is not None and node is not body:
        if node.tag not in _WRAPPER_TAGS:
            return ("not-pure", None)
        node = node.getparent()
    if node is not body:
        return ("not-pure", None)
    return ("pure", ref)


def rewrite_cover_page(page_bytes, old_ref, new_ref):
    """Replace the single occurrence of ``old_ref`` with ``new_ref``.

    Exact byte substitution: returns the new bytes when ``old_ref`` occurs
    exactly once in ``page_bytes``, otherwise None.
    """
    if old_ref is None or new_ref is None:
        return None
    old = old_ref.encode("utf-8")
    new = new_ref.encode("utf-8")
    if page_bytes.count(old) != 1:
        return None
    return page_bytes.replace(old, new)


def relative_href(from_path, to_path):
    """Return the POSIX relative reference from ``from_path`` to ``to_path``."""
    return posixpath.relpath(to_path, posixpath.dirname(from_path) or ".")


def check_cover_page(epub_path, cover_sha256):
    """Verify the cover page resolves to the embedded cover.

    Returns ``"ok"`` (pure page resolves to an entry whose SHA-256 equals the
    cover's), ``"not-pure"`` (cover page present but not a pure image page),
    ``"none"`` (no cover page / unreadable package) or ``"mismatch"`` (pure
    page whose image does not resolve to the cover bytes).
    """
    with zipfile.ZipFile(epub_path, "r") as z:
        names = z.namelist()
        entries = {n: z.read(n) for n in names}

    opf_path = None
    if "META-INF/container.xml" in entries:
        try:
            croot = ET.fromstring(entries["META-INF/container.xml"], _PAGE_PARSER)
            rf = croot.find(f".//{{{CONTAINER_NS}}}rootfile")
            if rf is not None and rf.get("full-path"):
                opf_path = posixpath.normpath(rf.get("full-path"))
        except Exception:
            opf_path = None
    if opf_path is None or opf_path not in entries:
        return "none"

    try:
        opf_root = ET.fromstring(entries[opf_path], _PAGE_PARSER)
    except Exception:
        return "none"

    page = find_cover_page(opf_root, opf_path, entries)
    if page is None:
        return "none"

    kind, image_ref = classify_cover_page(entries[page])
    if kind != "pure":
        return "not-pure"

    resolved = _resolve(page, image_ref)
    data = entries.get(resolved)
    if data is None:
        return "mismatch"
    return "ok" if hashlib.sha256(data).hexdigest() == cover_sha256 else "mismatch"
