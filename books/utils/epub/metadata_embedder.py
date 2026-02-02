"""
EPUB metadata embedding functionality.

Embeds metadata, cover images, and OPF data directly into EPUB files,
eliminating the need for external companion files.
"""

import logging
import shutil
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Dict, Optional

from books.models import Book
from books.utils.epub.structure_fixer import repair_epub_structure, validate_epub_structure

logger = logging.getLogger(__name__)


def embed_metadata_in_epub(epub_path: Path, book: Book, cover_path: Optional[Path] = None) -> bool:
    """
    Embed metadata directly into an EPUB file.

    This function:
    1. Extracts the EPUB to a temporary directory
    2. Updates the internal OPF metadata
    3. Embeds cover image if provided
    4. Cleans and validates the OPF
    5. Repacks the EPUB

    Args:
        epub_path: Path to the EPUB file
        book: Book model instance with metadata
        cover_path: Optional path to cover image to embed

    Returns:
        True if successful, False otherwise
    """
    try:
        logger.info(f"Embedding metadata into EPUB: {epub_path.name}")

        with tempfile.TemporaryDirectory() as temp_dir:
            extract_dir = Path(temp_dir)

            # Extract EPUB
            logger.debug("Extracting EPUB...")
            _extract_epub(epub_path, extract_dir)

            # Find OPF file
            opf_path = _find_opf_file(extract_dir)
            if not opf_path:
                logger.error("No OPF file found in EPUB")
                return False

            logger.debug(f"Found OPF: {opf_path.relative_to(extract_dir)}")

            # Update OPF metadata
            logger.debug("Updating OPF metadata...")
            _update_opf_metadata(opf_path, book)

            # Normalize OPF structure
            logger.debug("Normalizing OPF structure...")
            _normalize_opf(opf_path)

            # Embed cover if provided
            if cover_path and cover_path.exists():
                logger.debug(f"Embedding cover: {cover_path.name}")
                _embed_cover_image(extract_dir, opf_path, cover_path)

            # Validate and repair EPUB structure
            logger.debug("Validating EPUB structure...")
            issues = validate_epub_structure(extract_dir, opf_path)

            if issues.has_issues():
                logger.warning(f"Found issues: {issues.summary()}")
                fixes = repair_epub_structure(extract_dir, opf_path, issues)
                if fixes:
                    logger.info(f"Applied fixes: {', '.join(fixes)}")

            # Create backup
            backup_path = epub_path.with_suffix(".epub.bak")
            shutil.copy2(epub_path, backup_path)
            logger.debug(f"Created backup: {backup_path.name}")

            # Repack EPUB
            logger.debug("Repacking EPUB...")
            _repack_epub(extract_dir, epub_path)

            logger.info(f"Successfully embedded metadata in {epub_path.name}")
            return True

    except Exception as e:
        logger.error(f"Failed to embed metadata in EPUB: {e}", exc_info=True)
        return False


def _extract_epub(epub_path: Path, extract_dir: Path) -> None:
    """Extract EPUB to directory."""
    with zipfile.ZipFile(epub_path, "r") as zip_ref:
        zip_ref.extractall(extract_dir)


def _find_opf_file(extract_dir: Path) -> Optional[Path]:
    """Find the OPF file in extracted EPUB."""
    for opf_file in extract_dir.rglob("*.opf"):
        return opf_file
    return None


def _update_opf_metadata(opf_path: Path, book: Book) -> None:
    """
    Update OPF file with book metadata.

    Updates:
    - Title
    - Author
    - Language
    - Publisher
    - Description
    - Publication date
    - Series information
    """
    try:
        # Parse OPF
        tree = ET.parse(opf_path)
        root = tree.getroot()

        # Define namespaces
        namespaces = {"opf": "http://www.idpf.org/2007/opf", "dc": "http://purl.org/dc/elements/1.1/", "dcterms": "http://purl.org/dc/terms/"}

        # Register namespaces
        for prefix, uri in namespaces.items():
            ET.register_namespace(prefix, uri)

        # Get metadata element
        metadata = root.find(".//opf:metadata", namespaces)
        if metadata is None:
            logger.warning("No metadata element found in OPF")
            return

        # Get book's final metadata
        final_meta = book.finalmetadata if hasattr(book, "finalmetadata") else None

        # Update title
        if final_meta and final_meta.final_title:
            _update_or_create_element(metadata, "dc:title", final_meta.final_title, namespaces)

        # Update author
        if final_meta and final_meta.final_author:
            _update_or_create_element(metadata, "dc:creator", final_meta.final_author, namespaces)

        # Update language
        if final_meta and final_meta.language:
            _update_or_create_element(metadata, "dc:language", final_meta.language, namespaces)

        # Update publisher
        if final_meta and final_meta.final_publisher:
            _update_or_create_element(metadata, "dc:publisher", final_meta.final_publisher, namespaces)

        # Update description
        if final_meta and final_meta.description:
            _update_or_create_element(metadata, "dc:description", final_meta.description, namespaces)

        # Save updated OPF
        tree.write(opf_path, encoding="utf-8", xml_declaration=True)
        logger.debug("OPF metadata updated successfully")

    except Exception as e:
        logger.error(f"Failed to update OPF metadata: {e}", exc_info=True)
        raise


def _update_or_create_element(metadata, tag: str, value: str, namespaces: Dict[str, str]) -> None:
    """Update existing element or create new one."""
    element = metadata.find(tag, namespaces)
    if element is not None:
        element.text = value
    else:
        # Create new element
        namespace, local = tag.split(":")
        new_elem = ET.SubElement(metadata, f"{{{namespaces[namespace]}}}{local}")
        new_elem.text = value


def _normalize_opf(opf_path: Path) -> None:
    """
    Normalize OPF file structure for consistency.

    This function:
    - Removes Calibre-specific metadata
    - Reorders metadata elements in a consistent order
    - Normalizes whitespace and indentation
    - Ensures consistent XML formatting

    This helps ensure EPUBs with identical content have identical file sizes,
    aiding in duplicate detection.
    """
    try:
        # Parse OPF
        tree = ET.parse(opf_path)
        root = tree.getroot()

        # Define namespaces
        namespaces = {
            "opf": "http://www.idpf.org/2007/opf",
            "dc": "http://purl.org/dc/elements/1.1/",
            "dcterms": "http://purl.org/dc/terms/",
            "calibre": "http://calibre.kovidgoyal.net/2009/metadata",
        }

        # Register namespaces
        for prefix, uri in namespaces.items():
            ET.register_namespace(prefix, uri)

        # Get metadata element
        metadata = root.find(".//opf:metadata", namespaces)
        if metadata is None:
            logger.warning("No metadata element found in OPF")
            return

        # Remove Calibre metadata
        _remove_calibre_metadata(metadata, namespaces)

        # Reorder metadata elements
        _reorder_metadata_elements(metadata, namespaces)

        # Format and save with consistent indentation
        _indent_xml(root)
        tree.write(opf_path, encoding="utf-8", xml_declaration=True)

        logger.debug("OPF normalized successfully")

    except Exception as e:
        logger.error(f"Failed to normalize OPF: {e}", exc_info=True)
        raise


def _remove_calibre_metadata(metadata, namespaces: Dict[str, str]) -> None:
    """Remove Calibre-specific metadata elements."""
    # Remove elements with calibre namespace
    for elem in list(metadata):
        if elem.tag.startswith("{http://calibre.kovidgoyal.net"):
            metadata.remove(elem)

    # Remove calibre-specific meta tags
    calibre_patterns = ["calibre:", "calibre_", "timestamp", "user_metadata", "user_categories"]

    for meta in list(metadata.findall(".//opf:meta", namespaces)):
        name = meta.get("name", "")
        content = meta.get("content", "")

        # Remove if matches Calibre patterns
        if any(pattern in name.lower() or pattern in content.lower() for pattern in calibre_patterns):
            metadata.remove(meta)


def _reorder_metadata_elements(metadata, namespaces: Dict[str, str]) -> None:
    """
    Reorder metadata elements in a consistent order.

    Order:
    1. dc:identifier
    2. dc:title
    3. dc:creator
    4. dc:language
    5. dc:publisher
    6. dc:date
    7. dc:description
    8. dc:subject
    9. dc:rights
    10. dc:contributor
    11. All other dc: elements
    12. All meta elements
    """
    # Define preferred order
    preferred_order = ["dc:identifier", "dc:title", "dc:creator", "dc:language", "dc:publisher", "dc:date", "dc:description", "dc:subject", "dc:rights", "dc:contributor"]

    # Extract all elements
    elements = list(metadata)
    metadata.clear()

    # Group elements by type
    ordered_elements = []
    dc_elements = {}
    meta_elements = []
    other_elements = []

    for elem in elements:
        tag_name = _get_tag_name(elem, namespaces)

        if tag_name.startswith("dc:"):
            if tag_name not in dc_elements:
                dc_elements[tag_name] = []
            dc_elements[tag_name].append(elem)
        elif tag_name == "opf:meta":
            meta_elements.append(elem)
        else:
            other_elements.append(elem)

    # Add elements in preferred order
    for tag in preferred_order:
        if tag in dc_elements:
            ordered_elements.extend(dc_elements[tag])
            del dc_elements[tag]

    # Add remaining dc: elements (alphabetically)
    for tag in sorted(dc_elements.keys()):
        ordered_elements.extend(dc_elements[tag])

    # Add meta elements
    ordered_elements.extend(meta_elements)

    # Add other elements
    ordered_elements.extend(other_elements)

    # Re-add all elements in order
    for elem in ordered_elements:
        metadata.append(elem)


def _get_tag_name(elem, namespaces: Dict[str, str]) -> str:
    """Get simplified tag name (e.g., 'dc:title' from '{http://...}title')."""
    tag = elem.tag

    # Try to match namespace
    for prefix, uri in namespaces.items():
        if tag.startswith(f"{{{uri}}}"):
            local = tag[len(f"{{{uri}}}") :]
            return f"{prefix}:{local}"

    return tag


def _indent_xml(elem, level=0):
    """
    Add consistent indentation to XML tree.

    This ensures consistent whitespace formatting across all EPUBs.
    """
    indent = "\n" + "  " * level

    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = indent + "  "
        if not elem.tail or not elem.tail.strip():
            elem.tail = indent

        for child in elem:
            _indent_xml(child, level + 1)

        if not child.tail or not child.tail.strip():
            child.tail = indent
    else:
        if level and (not elem.tail or not elem.tail.strip()):
            elem.tail = indent


def _embed_cover_image(extract_dir: Path, opf_path: Path, cover_path: Path) -> None:
    """Embed cover image into EPUB."""
    try:
        # Copy cover to EPUB
        opf_dir = opf_path.parent
        images_dir = opf_dir / "images"
        images_dir.mkdir(exist_ok=True)

        # Determine cover filename
        cover_ext = cover_path.suffix
        internal_cover_path = images_dir / f"cover{cover_ext}"

        # Copy cover file
        shutil.copy2(cover_path, internal_cover_path)
        logger.debug(f"Copied cover to {internal_cover_path.relative_to(extract_dir)}")

        # Update OPF to reference cover
        tree = ET.parse(opf_path)
        root = tree.getroot()

        namespaces = {"opf": "http://www.idpf.org/2007/opf", "dc": "http://purl.org/dc/elements/1.1/"}

        # Add cover to manifest
        manifest = root.find(".//opf:manifest", namespaces)
        if manifest is not None:
            # Check if cover already exists
            cover_item = manifest.find(".//opf:item[@id='cover-image']", namespaces)
            if cover_item is None:
                # Create new cover item
                relative_cover = internal_cover_path.relative_to(opf_dir)
                media_type = _get_media_type(cover_ext)

                ET.SubElement(manifest, "{http://www.idpf.org/2007/opf}item", {"id": "cover-image", "href": str(relative_cover).replace("\\", "/"), "media-type": media_type})

            # Add cover metadata
            metadata = root.find(".//opf:metadata", namespaces)
            if metadata is not None:
                # Remove existing cover meta
                for meta in metadata.findall(".//opf:meta[@name='cover']", namespaces):
                    metadata.remove(meta)

                # Add new cover meta
                ET.SubElement(metadata, "{http://www.idpf.org/2007/opf}meta", {"name": "cover", "content": "cover-image"})

        # Save updated OPF
        tree.write(opf_path, encoding="utf-8", xml_declaration=True)
        logger.debug("Cover reference added to OPF")

    except Exception as e:
        logger.error(f"Failed to embed cover: {e}", exc_info=True)
        raise


def _get_media_type(extension: str) -> str:
    """Get media type for image extension."""
    media_types = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".gif": "image/gif", ".svg": "image/svg+xml"}
    return media_types.get(extension.lower(), "image/jpeg")


def _repack_epub(extract_dir: Path, output_path: Path) -> None:
    """Repack directory into EPUB file."""
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as epub_zip:
        # mimetype must be first and uncompressed
        mimetype_path = extract_dir / "mimetype"
        if mimetype_path.exists():
            epub_zip.write(mimetype_path, "mimetype", compress_type=zipfile.ZIP_STORED)

        # Add all other files
        for file_path in extract_dir.rglob("*"):
            if file_path.is_file() and file_path.name != "mimetype":
                arc_name = file_path.relative_to(extract_dir)
                epub_zip.write(file_path, arc_name, compress_type=zipfile.ZIP_DEFLATED)

    logger.debug(f"EPUB repacked to {output_path}")
