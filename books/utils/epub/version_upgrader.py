"""
EPUB Version Detection and Upgrading

Detects EPUB version and upgrades EPUB 1.0/2.0 files to EPUB 3.0 format.
Handles malformed files and ensures proper EPUB 3.0 structure.
"""

import logging
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)


def detect_epub_version(opf_path: Path) -> Optional[str]:
    """
    Detect EPUB version from OPF file.

    Args:
        opf_path: Path to OPF file

    Returns:
        Version string (e.g., "1.0", "2.0", "3.0") or None if cannot detect
    """
    try:
        tree = ET.parse(opf_path)
        root = tree.getroot()

        # Get version from package element
        version = root.get("version")

        if version:
            logger.debug(f"Detected EPUB version: {version}")
            return version

        # Fallback: check for EPUB 3 specific elements
        ns = {"opf": "http://www.idpf.org/2007/opf"}

        # EPUB 3 has nav document with properties attribute
        manifest = root.find(".//opf:manifest", ns)
        if manifest is not None:
            nav_item = manifest.find(".//opf:item[@properties='nav']", ns)
            if nav_item is not None:
                logger.debug("Detected EPUB 3.0 (nav document present)")
                return "3.0"

        # Default to 2.0 if version attribute missing
        logger.debug("No version found, assuming EPUB 2.0")
        return "2.0"

    except Exception as e:
        logger.error(f"Error detecting EPUB version: {e}", exc_info=True)
        return None


def upgrade_epub_to_3(extract_dir: Path, opf_path: Path) -> bool:
    """
    Upgrade EPUB 1.0/2.0 to EPUB 3.0 format.

    Performs:
    - Updates package version to 3.0
    - Converts NCX to EPUB 3 navigation document
    - Updates metadata format to EPUB 3
    - Adds required EPUB 3 elements
    - Fixes common structural issues

    Args:
        extract_dir: Directory with extracted EPUB contents
        opf_path: Path to OPF file

    Returns:
        True if upgrade successful, False otherwise
    """
    try:
        current_version = detect_epub_version(opf_path)

        if current_version == "3.0":
            logger.debug("Already EPUB 3.0, no upgrade needed")
            return True

        logger.info(f"Upgrading EPUB {current_version} -> 3.0")

        # Parse OPF
        tree = ET.parse(opf_path)
        root = tree.getroot()

        # Define namespaces
        ns = {
            "opf": "http://www.idpf.org/2007/opf",
            "dc": "http://purl.org/dc/elements/1.1/",
        }

        # Register namespaces
        ET.register_namespace("", "http://www.idpf.org/2007/opf")
        ET.register_namespace("dc", "http://purl.org/dc/elements/1.1/")

        # Update package version
        root.set("version", "3.0")

        # Add unique-identifier if missing
        if not root.get("unique-identifier"):
            root.set("unique-identifier", "uuid_id")

        # Ensure metadata has proper structure
        _upgrade_metadata_to_epub3(root, ns)

        # Generate EPUB 3 navigation from NCX (if exists)
        nav_created = _convert_ncx_to_nav(extract_dir, opf_path, root, ns)

        if nav_created:
            logger.info("Converted NCX to EPUB 3 navigation")

        # Update manifest items with proper EPUB 3 properties
        _update_manifest_properties(root, ns)

        # Save upgraded OPF
        tree.write(opf_path, encoding="utf-8", xml_declaration=True)

        logger.info("Successfully upgraded to EPUB 3.0")
        return True

    except Exception as e:
        logger.error(f"Error upgrading EPUB to 3.0: {e}", exc_info=True)
        return False


def _upgrade_metadata_to_epub3(root, ns: Dict[str, str]) -> None:
    """
    Upgrade metadata section to EPUB 3.0 format.

    EPUB 3 changes:
    - Uses meta elements with property attribute instead of name/content
    - Requires modified timestamp
    - Uses refines for relationships
    """
    metadata = root.find(".//opf:metadata", ns)
    if metadata is None:
        logger.warning("No metadata element found")
        return

    # Ensure dc:identifier with uuid_id
    identifier = metadata.find(".//dc:identifier", ns)
    if identifier is None:
        identifier = ET.SubElement(metadata, "{http://purl.org/dc/elements/1.1/}identifier")
        identifier.set("id", "uuid_id")
        identifier.text = "urn:uuid:00000000-0000-0000-0000-000000000000"
    else:
        if not identifier.get("id"):
            identifier.set("id", "uuid_id")

    # Add modified timestamp (required in EPUB 3)
    from datetime import datetime

    modified_exists = False
    for meta in metadata.findall(".//opf:meta", ns):
        if meta.get("property") == "dcterms:modified":
            modified_exists = True
            break

    if not modified_exists:
        meta = ET.SubElement(metadata, "{http://www.idpf.org/2007/opf}meta")
        meta.set("property", "dcterms:modified")
        meta.text = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def _convert_ncx_to_nav(extract_dir: Path, opf_path: Path, root, ns: Dict[str, str]) -> bool:
    """
    Convert NCX table of contents to EPUB 3 navigation document.

    Args:
        extract_dir: Extracted EPUB directory
        opf_path: Path to OPF file
        root: OPF root element
        ns: Namespaces dict

    Returns:
        True if navigation created, False otherwise
    """
    try:
        opf_dir = opf_path.parent
        manifest = root.find(".//opf:manifest", ns)

        if manifest is None:
            logger.warning("No manifest found")
            return False

        # Check if nav already exists
        nav_item = manifest.find(".//opf:item[@properties='nav']", ns)
        if nav_item is not None:
            logger.debug("Navigation document already exists")
            return False

        # Find NCX file
        ncx_item = manifest.find(".//opf:item[@media-type='application/x-dtbncx+xml']", ns)
        ncx_path = None

        if ncx_item is not None:
            ncx_href = ncx_item.get("href")
            if ncx_href:
                ncx_path = (opf_dir / ncx_href).resolve()

        # Parse NCX if exists
        toc_entries = []
        if ncx_path and ncx_path.exists():
            toc_entries = _parse_ncx_toc(ncx_path)

        # If no NCX or empty, generate from spine
        if not toc_entries:
            toc_entries = _generate_toc_from_spine(root, ns, manifest)

        # Create EPUB 3 navigation document
        nav_content = _generate_epub3_nav(toc_entries)

        # Save navigation document
        nav_path = opf_dir / "nav.xhtml"
        nav_path.write_text(nav_content, encoding="utf-8")

        # Add to manifest
        nav_item = ET.SubElement(manifest, "{http://www.idpf.org/2007/opf}item")
        nav_item.set("id", "nav")
        nav_item.set("href", "nav.xhtml")
        nav_item.set("media-type", "application/xhtml+xml")
        nav_item.set("properties", "nav")

        logger.debug("Created EPUB 3 navigation document")
        return True

    except Exception as e:
        logger.error(f"Error converting NCX to nav: {e}", exc_info=True)
        return False


def _parse_ncx_toc(ncx_path: Path) -> list:
    """Parse NCX file and extract table of contents."""
    toc_entries = []

    try:
        tree = ET.parse(ncx_path)
        root = tree.getroot()

        # NCX namespace
        ncx_ns = {"ncx": "http://www.daisy.org/z3986/2005/ncx/"}

        # Find navMap
        nav_map = root.find(".//ncx:navMap", ncx_ns)
        if nav_map is not None:
            for nav_point in nav_map.findall(".//ncx:navPoint", ncx_ns):
                label = nav_point.find(".//ncx:navLabel/ncx:text", ncx_ns)
                content = nav_point.find(".//ncx:content", ncx_ns)

                if label is not None and content is not None:
                    title = label.text or "Untitled"
                    href = content.get("src", "")

                    if href:
                        toc_entries.append({"title": title, "href": href})

        logger.debug(f"Parsed {len(toc_entries)} entries from NCX")

    except Exception as e:
        logger.warning(f"Error parsing NCX: {e}")

    return toc_entries


def _generate_toc_from_spine(root, ns: Dict[str, str], manifest) -> list:
    """Generate TOC from spine if no NCX available."""
    toc_entries = []

    try:
        # Build manifest lookup
        manifest_lookup = {}
        for item in manifest.findall(".//opf:item", ns):
            item_id = item.get("id")
            if item_id:
                manifest_lookup[item_id] = item.get("href")

        # Get spine items
        spine = root.find(".//opf:spine", ns)
        if spine is not None:
            for i, itemref in enumerate(spine.findall(".//opf:itemref", ns), 1):
                idref = itemref.get("idref")
                if idref and idref in manifest_lookup:
                    href = manifest_lookup[idref]
                    toc_entries.append({"title": f"Chapter {i}", "href": href})

        logger.debug(f"Generated {len(toc_entries)} TOC entries from spine")

    except Exception as e:
        logger.warning(f"Error generating TOC from spine: {e}")

    return toc_entries


def _generate_epub3_nav(toc_entries: list) -> str:
    """Generate EPUB 3 navigation XHTML document."""
    nav_content = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<head>
    <title>Table of Contents</title>
    <meta charset="utf-8"/>
</head>
<body>
    <nav epub:type="toc" id="toc">
        <h1>Table of Contents</h1>
        <ol>
"""

    for entry in toc_entries:
        title = entry.get("title", "Untitled")
        href = entry.get("href", "#")
        # Escape XML special characters
        title = title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        nav_content += f'            <li><a href="{href}">{title}</a></li>\n'

    nav_content += """        </ol>
    </nav>
</body>
</html>"""

    return nav_content


def _update_manifest_properties(root, ns: Dict[str, str]) -> None:
    """Update manifest items with proper EPUB 3 properties."""
    manifest = root.find(".//opf:manifest", ns)
    if manifest is None:
        return

    # Update cover image properties
    for item in manifest.findall(".//opf:item", ns):
        item_id = item.get("id", "")
        media_type = item.get("media-type", "")

        # Mark cover image
        if "cover" in item_id.lower() and media_type.startswith("image/"):
            current_props = item.get("properties", "")
            if "cover-image" not in current_props:
                item.set("properties", "cover-image")

        # Ensure XHTML files have proper media type
        if media_type == "text/html":
            item.set("media-type", "application/xhtml+xml")
