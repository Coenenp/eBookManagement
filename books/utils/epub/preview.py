"""
EPUB metadata preview utilities.

Simulates metadata embedding to show what changes would be made,
without actually modifying the EPUB file.
"""

import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from books.models import Book
from books.utils.epub.inspector import EPUBStructure, get_opf_path, inspect_epub
from books.utils.epub.metadata_embedder import (
    _embed_cover_image,
    _extract_epub,
    _normalize_opf,
    _update_opf_metadata,
)

logger = logging.getLogger(__name__)


@dataclass
class EPUBMetadataPreview:
    """Preview of EPUB metadata changes."""

    original_opf: str
    modified_opf: str
    original_structure: EPUBStructure
    files_to_add: List[str]  # New files that will be added (e.g., cover images)
    files_to_modify: List[str]  # Existing files that will be changed
    files_to_remove: List[str]  # Orphaned files that can be removed (if cleanup enabled)
    cover_path: Optional[str]  # Path to cover that will be embedded

    @property
    def has_changes(self) -> bool:
        """Check if there are any changes."""
        return self.original_opf != self.modified_opf or len(self.files_to_add) > 0 or len(self.files_to_modify) > 0


def preview_metadata_changes(epub_path: Path, book: Book, cover_path: Optional[Path] = None) -> EPUBMetadataPreview:
    """
    Preview what changes would be made to EPUB metadata without modifying the file.

    This function:
    1. Inspects the original EPUB structure
    2. Extracts to temporary directory
    3. Applies metadata changes (in temp dir)
    4. Captures before/after OPF content
    5. Identifies new/modified files
    6. Cleans up temp files

    Args:
        epub_path: Path to EPUB file
        book: Book model instance with metadata
        cover_path: Optional path to cover image to embed

    Returns:
        EPUBMetadataPreview with before/after comparison
    """
    try:
        logger.info(f"Previewing metadata changes for: {epub_path.name}")

        # Inspect original structure
        original_structure = inspect_epub(epub_path)
        original_opf = original_structure.opf_content or ""

        # Extract to temp directory for modification simulation
        with tempfile.TemporaryDirectory() as temp_dir:
            extract_dir = Path(temp_dir)

            # Extract EPUB
            _extract_epub(epub_path, extract_dir)

            # Find OPF file
            opf_path = get_opf_path(extract_dir)
            if not opf_path:
                logger.error("No OPF file found in EPUB")
                return EPUBMetadataPreview(
                    original_opf=original_opf,
                    modified_opf=original_opf,
                    original_structure=original_structure,
                    files_to_add=[],
                    files_to_modify=[],
                    files_to_remove=[],
                    cover_path=None,
                )

            # Track files before modification
            files_before = set(p.relative_to(extract_dir) for p in extract_dir.rglob("*") if p.is_file())

            # Apply metadata updates (same as actual embedding)
            _update_opf_metadata(opf_path, book)
            _normalize_opf(opf_path)

            # Embed cover if provided
            cover_embedded = None
            if cover_path and cover_path.exists():
                _embed_cover_image(extract_dir, opf_path, cover_path)
                cover_embedded = str(cover_path)

            # Detect orphaned images that could be removed
            files_to_remove = _detect_orphaned_images(extract_dir, opf_path)

            # Track files after modification
            files_after = set(p.relative_to(extract_dir) for p in extract_dir.rglob("*") if p.is_file())

            # Identify new files
            files_to_add = [str(f) for f in (files_after - files_before)]

            # OPF is always modified
            files_to_modify = [str(opf_path.relative_to(extract_dir))]

            # Read modified OPF content
            modified_opf = opf_path.read_text(encoding="utf-8")

            return EPUBMetadataPreview(
                original_opf=original_opf,
                modified_opf=modified_opf,
                original_structure=original_structure,
                files_to_add=files_to_add,
                files_to_modify=files_to_modify,
                files_to_remove=files_to_remove,
                cover_path=cover_embedded,
            )

    except Exception as e:
        logger.error(f"Failed to preview metadata changes: {e}", exc_info=True)
        # Return empty preview on error
        original_structure = inspect_epub(epub_path)
        return EPUBMetadataPreview(
            original_opf=original_structure.opf_content or "",
            modified_opf=original_structure.opf_content or "",
            original_structure=original_structure,
            files_to_add=[],
            files_to_modify=[],
            files_to_remove=[],
            cover_path=None,
        )


def generate_preview_summary(preview: EPUBMetadataPreview) -> dict:
    """
    Generate human-readable summary of preview changes.

    Args:
        preview: EPUBMetadataPreview instance

    Returns:
        Dictionary with summary information
    """
    summary = {
        "has_changes": preview.has_changes,
        "opf_modified": preview.original_opf != preview.modified_opf,
        "cover_added": preview.cover_path is not None,
        "files_added_count": len(preview.files_to_add),
        "files_modified_count": len(preview.files_to_modify),
        "orphaned_images_count": len(preview.files_to_remove),
        "files_to_add": preview.files_to_add,
        "files_to_modify": preview.files_to_modify,
        "files_to_remove": preview.files_to_remove,
    }

    # Extract specific OPF changes
    if summary["opf_modified"]:
        summary["opf_changes"] = _summarize_opf_changes(preview.original_opf, preview.modified_opf)

    return summary


def _summarize_opf_changes(original: str, modified: str) -> dict:
    """
    Summarize specific OPF metadata changes.

    Args:
        original: Original OPF content
        modified: Modified OPF content

    Returns:
        Dictionary describing changes
    """
    import xml.etree.ElementTree as ET

    changes = {
        "title_changed": False,
        "author_changed": False,
        "publisher_changed": False,
        "description_changed": False,
        "cover_changed": False,
        "calibre_removed": False,
    }

    try:
        # Parse both OPFs
        original_root = ET.fromstring(original)
        modified_root = ET.fromstring(modified)

        namespaces = {"opf": "http://www.idpf.org/2007/opf", "dc": "http://purl.org/dc/elements/1.1/"}

        # Check title
        orig_title = original_root.findtext(".//dc:title", default="", namespaces=namespaces)
        mod_title = modified_root.findtext(".//dc:title", default="", namespaces=namespaces)
        changes["title_changed"] = orig_title != mod_title

        # Check author
        orig_author = original_root.findtext(".//dc:creator", default="", namespaces=namespaces)
        mod_author = modified_root.findtext(".//dc:creator", default="", namespaces=namespaces)
        changes["author_changed"] = orig_author != mod_author

        # Check publisher
        orig_pub = original_root.findtext(".//dc:publisher", default="", namespaces=namespaces)
        mod_pub = modified_root.findtext(".//dc:publisher", default="", namespaces=namespaces)
        changes["publisher_changed"] = orig_pub != mod_pub

        # Check description
        orig_desc = original_root.findtext(".//dc:description", default="", namespaces=namespaces)
        mod_desc = modified_root.findtext(".//dc:description", default="", namespaces=namespaces)
        changes["description_changed"] = orig_desc != mod_desc

        # Check cover meta
        orig_cover = original_root.find('.//opf:meta[@name="cover"]', namespaces)
        mod_cover = modified_root.find('.//opf:meta[@name="cover"]', namespaces)
        changes["cover_changed"] = (orig_cover is None) != (mod_cover is None)

        # Check for Calibre removal
        orig_calibre = "calibre" in original.lower()
        mod_calibre = "calibre" in modified.lower()
        changes["calibre_removed"] = orig_calibre and not mod_calibre

    except Exception as e:
        logger.warning(f"Failed to parse OPF for change summary: {e}")

    return changes


def _detect_orphaned_images(extract_dir: Path, opf_path: Path) -> List[str]:
    """
    Detect image files that are not referenced in the OPF manifest.

    This is a non-destructive preview version of _remove_orphaned_images.

    Args:
        extract_dir: Extracted EPUB directory
        opf_path: Path to OPF file

    Returns:
        List of relative paths to orphaned images
    """
    import xml.etree.ElementTree as ET

    try:
        # Parse OPF to get referenced files
        tree = ET.parse(opf_path)
        root = tree.getroot()
        namespaces = {"opf": "http://www.idpf.org/2007/opf"}

        # Get all manifest items
        manifest = root.find(".//opf:manifest", namespaces)
        if manifest is None:
            return []

        # Collect all referenced hrefs (normalized to absolute paths)
        opf_dir = opf_path.parent
        referenced_files = set()

        for item in manifest.findall(".//opf:item", namespaces):
            href = item.get("href")
            if href:
                # Resolve relative path to absolute
                file_path = (opf_dir / href).resolve()
                referenced_files.add(file_path)

        # Find all image files in EPUB
        image_extensions = {".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp"}
        all_images = []

        for ext in image_extensions:
            all_images.extend(extract_dir.rglob(f"*{ext}"))
            all_images.extend(extract_dir.rglob(f"*{ext.upper()}"))

        # Identify orphaned images
        orphaned = []
        for image_path in all_images:
            resolved_path = image_path.resolve()

            if resolved_path not in referenced_files:
                # Convert to relative path for display
                rel_path = str(image_path.relative_to(extract_dir))
                orphaned.append(rel_path)

        return orphaned

    except Exception as e:
        logger.error(f"Error detecting orphaned images: {e}", exc_info=True)
        return []
