"""
EPUB Structure Fixer

Provides validation and repair functionality for EPUB files:
- Validates OPF structure
- Removes broken references
- Generates navigation documents
- Fixes spine issues
"""

import logging
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List

logger = logging.getLogger(__name__)


class EPUBValidationIssues:
    """Track structural validation issues."""

    def __init__(self):
        self.missing_files: List[Dict] = []
        self.broken_refs: List[str] = []
        self.nav_issues: List[str] = []
        self.spine_issues: List[str] = []

    def has_issues(self) -> bool:
        """Check if any issues were found."""
        return bool(self.missing_files or self.broken_refs or self.nav_issues or self.spine_issues)

    def summary(self) -> str:
        """Get summary of all issues."""
        parts = []
        if self.missing_files:
            parts.append(f"{len(self.missing_files)} missing files")
        if self.broken_refs:
            parts.append(f"{len(self.broken_refs)} broken references")
        if self.nav_issues:
            parts.append(f"{len(self.nav_issues)} nav issues")
        if self.spine_issues:
            parts.append(f"{len(self.spine_issues)} spine issues")
        return ", ".join(parts) if parts else "No issues"


def validate_epub_structure(extract_dir: Path, opf_path: Path) -> EPUBValidationIssues:
    """
    Validate EPUB structure after metadata embedding.

    Checks:
    - Missing files referenced in manifest
    - Broken references
    - Navigation document existence
    - Spine integrity

    Args:
        extract_dir: Directory with extracted EPUB contents
        opf_path: Path to OPF file

    Returns:
        EPUBValidationIssues object with detected issues
    """
    issues = EPUBValidationIssues()

    try:
        # Parse OPF
        tree = ET.parse(opf_path)
        root = tree.getroot()

        # Define namespace
        ns = {"opf": "http://www.idpf.org/2007/opf"}

        # Get manifest
        manifest = root.find(".//opf:manifest", ns)
        if manifest is None:
            issues.nav_issues.append("No manifest element found")
            return issues

        opf_dir = opf_path.parent

        # Check for missing files
        for item in manifest.findall(".//opf:item", ns):
            item_id = item.get("id")
            href = item.get("href")

            if href:
                # Resolve path relative to OPF
                file_path = (opf_dir / href).resolve()

                if not file_path.exists():
                    issues.missing_files.append({"id": item_id, "href": href, "type": "missing"})

        # Check nav document
        nav_item = manifest.find(".//opf:item[@properties='nav']", ns)
        if nav_item is None:
            issues.nav_issues.append("Missing nav document reference in manifest")
        else:
            nav_href = nav_item.get("href")
            if nav_href:
                nav_path = (opf_dir / nav_href).resolve()
                if not nav_path.exists():
                    issues.nav_issues.append(f"Nav file not found: {nav_href}")

        # Check spine
        spine = root.find(".//opf:spine", ns)
        if spine is None or len(spine) == 0:
            issues.spine_issues.append("Empty or missing spine")
        else:
            # Build manifest ID set
            manifest_ids = {item.get("id") for item in manifest.findall(".//opf:item", ns)}

            # Check spine references
            for itemref in spine.findall(".//opf:itemref", ns):
                idref = itemref.get("idref")
                if idref and idref not in manifest_ids:
                    issues.spine_issues.append(f"Spine references missing manifest item: {idref}")

        logger.debug(f"Validation complete: {issues.summary()}")

    except Exception as e:
        logger.error(f"Error validating EPUB structure: {e}", exc_info=True)
        issues.broken_refs.append(f"Validation error: {str(e)}")

    return issues


def repair_epub_structure(extract_dir: Path, opf_path: Path, issues: EPUBValidationIssues) -> List[str]:
    """
    Repair detected EPUB structure issues.

    Applies fixes:
    - Removes broken file references from manifest
    - Generates missing navigation document
    - Cleans up spine references

    Args:
        extract_dir: Directory with extracted EPUB contents
        opf_path: Path to OPF file
        issues: Detected issues from validation

    Returns:
        List of fixes applied
    """
    fixes = []

    if not issues.has_issues():
        return fixes

    try:
        # Parse OPF
        tree = ET.parse(opf_path)
        root = tree.getroot()

        # Define namespace
        ns = {"opf": "http://www.idpf.org/2007/opf"}
        ET.register_namespace("opf", "http://www.idpf.org/2007/opf")
        ET.register_namespace("dc", "http://purl.org/dc/elements/1.1/")

        modified = False

        # Fix missing files by removing from manifest
        if issues.missing_files:
            manifest = root.find(".//opf:manifest", ns)
            if manifest is not None:
                missing_ids = {mf["id"] for mf in issues.missing_files}

                for item in list(manifest.findall(".//opf:item", ns)):
                    item_id = item.get("id")
                    if item_id in missing_ids:
                        manifest.remove(item)
                        modified = True

                # Also remove from spine
                spine = root.find(".//opf:spine", ns)
                if spine is not None:
                    for itemref in list(spine.findall(".//opf:itemref", ns)):
                        idref = itemref.get("idref")
                        if idref in missing_ids:
                            spine.remove(itemref)

                fixes.append(f"Removed {len(issues.missing_files)} broken references")

        # Generate nav if missing
        if issues.nav_issues and "Missing nav document" in issues.nav_issues[0]:
            nav_generated = _generate_navigation_document(extract_dir, opf_path, root, ns)
            if nav_generated:
                fixes.append("Generated navigation document")
                modified = True

        # Save updated OPF if modified
        if modified:
            tree.write(opf_path, encoding="utf-8", xml_declaration=True)
            logger.debug(f"Applied fixes: {', '.join(fixes)}")

    except Exception as e:
        logger.error(f"Error repairing EPUB structure: {e}", exc_info=True)

    return fixes


def _generate_navigation_document(extract_dir: Path, opf_path: Path, root, ns: Dict[str, str]) -> bool:
    """Generate basic navigation document from spine."""
    try:
        opf_dir = opf_path.parent

        # Build manifest dict
        manifest = root.find(".//opf:manifest", ns)
        manifest_dict = {}
        if manifest is not None:
            for item in manifest.findall(".//opf:item", ns):
                item_id = item.get("id")
                if item_id:
                    manifest_dict[item_id] = {"href": item.get("href"), "media-type": item.get("media-type")}

        # Get spine items
        spine = root.find(".//opf:spine", ns)
        spine_items = []
        if spine is not None:
            for itemref in spine.findall(".//opf:itemref", ns):
                idref = itemref.get("idref")
                if idref and idref in manifest_dict:
                    spine_items.append(manifest_dict[idref])

        if not spine_items:
            return False

        # Generate nav.xhtml
        nav_content = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<head>
<title>Navigation</title>
</head>
<body>
<nav epub:type="toc" id="toc">
<h1>Table of Contents</h1>
<ol>
"""

        for i, item in enumerate(spine_items, 1):
            href = item["href"]
            nav_content += f'  <li><a href="{href}">Chapter {i}</a></li>\n'

        nav_content += """</ol>
</nav>
</body>
</html>"""

        # Save nav file
        nav_path = opf_dir / "nav.xhtml"
        nav_path.write_text(nav_content, encoding="utf-8")

        # Add to manifest
        if manifest is not None:
            nav_item = ET.SubElement(manifest, "{http://www.idpf.org/2007/opf}item")
            nav_item.set("id", "nav")
            nav_item.set("href", "nav.xhtml")
            nav_item.set("media-type", "application/xhtml+xml")
            nav_item.set("properties", "nav")

        return True

    except Exception as e:
        logger.error(f"Error generating navigation: {e}", exc_info=True)
        return False
