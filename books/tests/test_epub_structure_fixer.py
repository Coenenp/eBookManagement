"""
Tests for EPUB structure validation and repair.
"""

import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

from django.test import TestCase

from books.utils.epub.structure_fixer import (
    EPUBValidationIssues,
    repair_epub_structure,
    validate_epub_structure,
)


class EPUBStructureFixerTestCase(TestCase):
    """Test EPUB structure validation and repair."""

    def setUp(self):
        """Set up test directory with sample EPUB structure."""
        self.test_dir = Path(tempfile.mkdtemp())

        # Create basic EPUB structure
        self.opf_dir = self.test_dir / "OEBPS"
        self.opf_dir.mkdir()

        self.opf_path = self.opf_dir / "content.opf"

    def tearDown(self):
        """Clean up test files."""
        import shutil

        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    def _create_opf_with_missing_files(self):
        """Create OPF that references non-existent files."""
        opf_content = """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>Test Book</dc:title>
  </metadata>
  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
    <item id="chapter1" href="chapter1.xhtml" media-type="application/xhtml+xml"/>
    <item id="missing" href="missing.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine>
    <itemref idref="chapter1"/>
    <itemref idref="missing"/>
  </spine>
</package>"""

        self.opf_path.write_text(opf_content, encoding="utf-8")

        # Create existing files
        (self.opf_dir / "nav.xhtml").write_text("<html></html>", encoding="utf-8")
        (self.opf_dir / "chapter1.xhtml").write_text("<html></html>", encoding="utf-8")
        # missing.xhtml intentionally not created

    def _create_opf_without_nav(self):
        """Create OPF without navigation document."""
        opf_content = """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>Test Book</dc:title>
  </metadata>
  <manifest>
    <item id="chapter1" href="chapter1.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine>
    <itemref idref="chapter1"/>
  </spine>
</package>"""

        self.opf_path.write_text(opf_content, encoding="utf-8")
        (self.opf_dir / "chapter1.xhtml").write_text("<html></html>", encoding="utf-8")

    def _create_valid_opf(self):
        """Create valid OPF with all files present."""
        opf_content = """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>Test Book</dc:title>
  </metadata>
  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
    <item id="chapter1" href="chapter1.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine>
    <itemref idref="chapter1"/>
  </spine>
</package>"""

        self.opf_path.write_text(opf_content, encoding="utf-8")
        (self.opf_dir / "nav.xhtml").write_text("<html></html>", encoding="utf-8")
        (self.opf_dir / "chapter1.xhtml").write_text("<html></html>", encoding="utf-8")

    def test_validation_detects_missing_files(self):
        """Test that validation detects missing files."""
        self._create_opf_with_missing_files()

        issues = validate_epub_structure(self.test_dir, self.opf_path)

        self.assertTrue(issues.has_issues())
        self.assertEqual(len(issues.missing_files), 1)
        self.assertEqual(issues.missing_files[0]["id"], "missing")

    def test_validation_detects_missing_nav(self):
        """Test that validation detects missing navigation."""
        self._create_opf_without_nav()

        issues = validate_epub_structure(self.test_dir, self.opf_path)

        self.assertTrue(issues.has_issues())
        self.assertGreater(len(issues.nav_issues), 0)
        self.assertIn("nav document", issues.nav_issues[0].lower())

    def test_validation_passes_for_valid_epub(self):
        """Test that validation passes for valid EPUB."""
        self._create_valid_opf()

        issues = validate_epub_structure(self.test_dir, self.opf_path)

        self.assertFalse(issues.has_issues())

    def test_repair_removes_missing_files(self):
        """Test that repair removes broken file references."""
        self._create_opf_with_missing_files()

        issues = validate_epub_structure(self.test_dir, self.opf_path)
        fixes = repair_epub_structure(self.test_dir, self.opf_path, issues)

        self.assertGreater(len(fixes), 0)
        self.assertTrue(any("broken references" in fix for fix in fixes))

        # Verify missing file removed from manifest
        tree = ET.parse(self.opf_path)
        root = tree.getroot()
        ns = {"opf": "http://www.idpf.org/2007/opf"}

        manifest = root.find(".//opf:manifest", ns)
        items = manifest.findall(".//opf:item", ns)
        item_ids = [item.get("id") for item in items]

        self.assertNotIn("missing", item_ids)

    def test_repair_generates_nav(self):
        """Test that repair generates missing navigation."""
        self._create_opf_without_nav()

        issues = validate_epub_structure(self.test_dir, self.opf_path)
        fixes = repair_epub_structure(self.test_dir, self.opf_path, issues)

        self.assertGreater(len(fixes), 0)
        self.assertTrue(any("navigation" in fix.lower() for fix in fixes))

        # Verify nav file created
        nav_path = self.opf_dir / "nav.xhtml"
        self.assertTrue(nav_path.exists())

        # Verify nav added to manifest
        tree = ET.parse(self.opf_path)
        root = tree.getroot()
        ns = {"opf": "http://www.idpf.org/2007/opf"}

        manifest = root.find(".//opf:manifest", ns)
        nav_item = manifest.find(".//opf:item[@id='nav']", ns)
        self.assertIsNotNone(nav_item)
        self.assertEqual(nav_item.get("properties"), "nav")

    def test_issues_summary(self):
        """Test EPUBValidationIssues summary."""
        issues = EPUBValidationIssues()

        self.assertEqual(issues.summary(), "No issues")

        issues.missing_files.append({"id": "test", "href": "test.html", "type": "missing"})
        issues.nav_issues.append("Missing nav")

        summary = issues.summary()
        self.assertIn("1 missing files", summary)
        self.assertIn("1 nav issues", summary)

    def test_no_repair_for_valid_epub(self):
        """Test that no repairs are made for valid EPUB."""
        self._create_valid_opf()

        issues = validate_epub_structure(self.test_dir, self.opf_path)
        fixes = repair_epub_structure(self.test_dir, self.opf_path, issues)

        self.assertEqual(len(fixes), 0)
