"""
OPF Generation Utilities

This module provides functions for generating OPF (Open Packaging Format)
metadata files from FinalMetadata objects. The generated OPF files contain
all curated metadata in a standards-compliant format that can be read by
other ebook management tools.
"""
from datetime import datetime
from pathlib import Path
from lxml import etree as ET
import logging

logger = logging.getLogger("books.scanner")


def generate_opf_from_final_metadata(final_metadata, ebook_filename=None):
    """
    Generate OPF XML content from a FinalMetadata object.

    Args:
        final_metadata: FinalMetadata instance containing curated metadata
        ebook_filename: Optional filename of the ebook file (for manifest)

    Returns:
        str: Complete OPF XML content
    """
    try:
        # Create root element with namespaces
        root = ET.Element("{http://www.idpf.org/2007/opf}package",
                          attrib={
                              "version": "2.0",
                              "unique-identifier": "BookId"
                          })

        # Add namespace declarations
        root.set("{http://www.w3.org/2000/xmlns/}opf", "http://www.idpf.org/2007/opf")
        root.set("{http://www.w3.org/2000/xmlns/}dc", "http://purl.org/dc/elements/1.1/")
        root.set("{http://www.w3.org/2000/xmlns/}dcterms", "http://purl.org/dc/terms/")

        # Metadata section
        metadata = ET.SubElement(root, "{http://www.idpf.org/2007/opf}metadata")

        # Required Dublin Core elements
        _add_dc_element(metadata, "identifier",
                        final_metadata.isbn or f"ebook-manager-{final_metadata.book.id}",
                        attrib={"id": "BookId"})

        _add_dc_element(metadata, "title", final_metadata.final_title or "Unknown Title")
        _add_dc_element(metadata, "creator", final_metadata.final_author or "Unknown Author",
                        attrib={"{http://www.idpf.org/2007/opf}role": "aut"})
        _add_dc_element(metadata, "language", final_metadata.language or "en")

        # Optional Dublin Core elements
        if final_metadata.final_publisher:
            _add_dc_element(metadata, "publisher", final_metadata.final_publisher)

        if hasattr(final_metadata, 'description') and final_metadata.description:
            _add_dc_element(metadata, "description", final_metadata.description)

        if hasattr(final_metadata, 'publication_year') and final_metadata.publication_year:
            try:
                # Format as ISO date
                year = int(final_metadata.publication_year)
                date_str = f"{year}-01-01"
                _add_dc_element(metadata, "date", date_str)
            except (ValueError, TypeError):
                pass

        # Add genres as subjects
        if hasattr(final_metadata, 'final_genres') and final_metadata.final_genres:
            for genre in final_metadata.final_genres.all():
                _add_dc_element(metadata, "subject", genre.name)

        # Calibre-specific metadata for series support
        if final_metadata.final_series:
            _add_opf_meta(metadata, "calibre:series", final_metadata.final_series)

            if final_metadata.final_series_number:
                try:
                    series_num = float(final_metadata.final_series_number)
                    _add_opf_meta(metadata, "calibre:series_index", str(series_num))
                except (ValueError, TypeError):
                    pass

        # Additional metadata from ebook library manager
        _add_opf_meta(metadata, "ebook-manager:reviewed",
                      "true" if final_metadata.is_reviewed else "false")
        _add_opf_meta(metadata, "ebook-manager:confidence",
                      f"{final_metadata.overall_confidence:.2f}")
        _add_opf_meta(metadata, "ebook-manager:generated",
                      datetime.now().isoformat())

        # Manifest section (simplified - just reference the ebook file if provided)
        manifest = ET.SubElement(root, "{http://www.idpf.org/2007/opf}manifest")

        if ebook_filename:
            # Determine media type based on file extension
            file_ext = Path(ebook_filename).suffix.lower()
            media_type_map = {
                '.epub': 'application/epub+zip',
                '.pdf': 'application/pdf',
                '.mobi': 'application/x-mobipocket-ebook',
                '.azw': 'application/vnd.amazon.ebook',
                '.azw3': 'application/vnd.amazon.ebook',
                '.txt': 'text/plain'
            }
            media_type = media_type_map.get(file_ext, 'application/octet-stream')

            ET.SubElement(manifest, "{http://www.idpf.org/2007/opf}item",
                          attrib={
                              "id": "main-content",
                              "href": ebook_filename,
                              "media-type": media_type
                          })

        # Spine section (simplified)
        spine = ET.SubElement(root, "{http://www.idpf.org/2007/opf}spine")
        if ebook_filename:
            ET.SubElement(spine, "{http://www.idpf.org/2007/opf}itemref",
                          attrib={"idref": "main-content"})

        # Format XML with proper indentation
        ET.indent(root, space="  ")

        # Generate XML string with declaration
        xml_str = ET.tostring(root, encoding='utf-8', xml_declaration=True,
                              pretty_print=True).decode('utf-8')

        return xml_str

    except Exception as e:
        logger.error(f"Failed to generate OPF for book {final_metadata.book.id}: {e}")
        return None


def _add_dc_element(parent, name, value, attrib=None):
    """Add a Dublin Core element to the metadata section."""
    if value:  # Only add if value is not None or empty
        elem = ET.SubElement(parent, f"{{http://purl.org/dc/elements/1.1/}}{name}")
        elem.text = str(value).strip()
        if attrib:
            for key, val in attrib.items():
                elem.set(key, val)


def _add_opf_meta(parent, name, content):
    """Add an OPF meta element."""
    if content is not None:
        ET.SubElement(parent, "{http://www.idpf.org/2007/opf}meta",
                      attrib={"name": name, "content": str(content)})


def save_opf_file(final_metadata, opf_path, ebook_filename=None):
    """
    Save an OPF file for the given final metadata.

    Args:
        final_metadata: FinalMetadata instance
        opf_path: Path where to save the OPF file
        ebook_filename: Optional filename of the ebook (for manifest)

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        opf_content = generate_opf_from_final_metadata(final_metadata, ebook_filename)
        if opf_content:
            # Ensure directory exists
            Path(opf_path).parent.mkdir(parents=True, exist_ok=True)

            # Write OPF file
            with open(opf_path, 'w', encoding='utf-8') as f:
                f.write(opf_content)

            logger.info(f"Generated OPF file: {opf_path}")
            return True
        else:
            logger.warning(f"Failed to generate OPF content for book {final_metadata.book.id}")
            return False

    except Exception as e:
        logger.error(f"Failed to save OPF file {opf_path}: {e}")
        return False


def get_opf_filename(book_filename):
    """
    Generate an appropriate OPF filename based on the book filename.

    Args:
        book_filename: Filename of the ebook

    Returns:
        str: OPF filename (same base name with .opf extension)
    """
    return Path(book_filename).with_suffix('.opf').name
