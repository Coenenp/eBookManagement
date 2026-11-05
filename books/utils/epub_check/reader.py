"""Open an EPUB container and expose its structure to the rule engine."""

import posixpath
import xml.etree.ElementTree as ET
import zipfile
from typing import Dict, List, Optional

OPF_NS = {"opf": "http://www.idpf.org/2007/opf"}
CONTAINER_NS = {"c": "urn:oasis:names:tc:opendocument:xmlns:container"}

CONTAINER_ARC = "META-INF/container.xml"
MIMETYPE_ARC = "mimetype"


class EpubReader:
    """Read-only view of an EPUB zip.

    Exposes the mimetype, the container document, the OPF (as an ElementTree
    root), the manifest (list of item dicts), the spine (list of idrefs) and the
    nav item (for EPUB 3).
    """

    def __init__(self, path):
        self.path = str(path)
        self.zip = zipfile.ZipFile(self.path, "r")
        self.namelist = self.zip.namelist()
        self.mimetype = self._read_mimetype()
        self.container_root = self._parse_container()
        self.opf_path = self._find_opf()
        self.opf_root = self._parse_opf() if self.opf_path else None
        self.version = self._detect_version()
        self.manifest = self._extract_manifest()
        self.spine = self._extract_spine()
        self.nav_item = self._find_nav()

    # -- low-level readers -------------------------------------------------- #

    def read(self, arcname: str) -> bytes:
        return self.zip.read(arcname)

    def close(self) -> None:
        self.zip.close()

    def _read_mimetype(self) -> Optional[Dict]:
        if MIMETYPE_ARC not in self.namelist:
            return None
        try:
            info = self.zip.getinfo(MIMETYPE_ARC)
            return {
                "value": self.zip.read(MIMETYPE_ARC).decode("utf-8", "replace").strip(),
                "first": self.namelist[0] == MIMETYPE_ARC,
                "compress_type": info.compress_type,
            }
        except Exception:
            return None

    def _parse_container(self) -> Optional[ET.Element]:
        if CONTAINER_ARC not in self.namelist:
            return None
        try:
            return ET.fromstring(self.zip.read(CONTAINER_ARC))
        except Exception:
            return None

    def _find_opf(self) -> Optional[str]:
        if self.container_root is None:
            return None
        rootfile = self.container_root.find(".//c:rootfile", CONTAINER_NS)
        if rootfile is None:
            return None
        full = rootfile.get("full-path")
        return posixpath.normpath(full) if full else None

    def _parse_opf(self) -> Optional[ET.Element]:
        if self.opf_path is None or self.opf_path not in self.namelist:
            return None
        try:
            return ET.fromstring(self.zip.read(self.opf_path))
        except Exception:
            return None

    def _detect_version(self) -> Optional[str]:
        if self.opf_root is None:
            return None
        return self.opf_root.get("version")

    # -- structural views --------------------------------------------------- #

    def _extract_manifest(self) -> List[Dict]:
        items: List[Dict] = []
        if self.opf_root is None:
            return items
        manifest = self.opf_root.find("opf:manifest", OPF_NS)
        if manifest is None:
            return items
        opf_dir = posixpath.dirname(self.opf_path) if self.opf_path else ""
        for it in manifest.findall("opf:item", OPF_NS):
            href = it.get("href", "")
            resolved = posixpath.normpath(posixpath.join(opf_dir, href)) if href else ""
            items.append(
                {
                    "id": it.get("id"),
                    "href": href,
                    "media_type": it.get("media-type"),
                    "properties": it.get("properties") or "",
                    "resolved": resolved,
                }
            )
        return items

    def _extract_spine(self) -> List[str]:
        if self.opf_root is None:
            return []
        spine = self.opf_root.find("opf:spine", OPF_NS)
        if spine is None:
            return []
        return [ir.get("idref") for ir in spine.findall("opf:itemref", OPF_NS)]

    def _find_nav(self) -> Optional[Dict]:
        for m in self.manifest:
            if "nav" in (m["properties"] or "").split():
                return m
        return None
