"""
Tests for OPF normalization in EPUB metadata embedding.
"""

import xml.etree.ElementTree as ET

from django.test import TestCase

from books.utils.epub.metadata_embedder import (
    _get_tag_name,
    _indent_xml,
    _remove_calibre_metadata,
    _reorder_metadata_elements,
)


class OPFNormalizationTestCase(TestCase):
    """Test OPF normalization functions."""

    def setUp(self):
        """Set up test namespaces."""
        self.namespaces = {
            "opf": "http://www.idpf.org/2007/opf",
            "dc": "http://purl.org/dc/elements/1.1/",
            "dcterms": "http://purl.org/dc/terms/",
            "calibre": "http://calibre.kovidgoyal.net/2009/metadata",
        }

        # Register namespaces
        for prefix, uri in self.namespaces.items():
            ET.register_namespace(prefix, uri)

    def _create_test_metadata(self, with_calibre=False):
        """Create a test metadata element."""
        metadata = ET.Element("{http://www.idpf.org/2007/opf}metadata")

        # Add Dublin Core elements in random order
        ET.SubElement(metadata, "{http://purl.org/dc/elements/1.1/}description").text = "Test description"
        ET.SubElement(metadata, "{http://purl.org/dc/elements/1.1/}title").text = "Test Title"
        ET.SubElement(metadata, "{http://purl.org/dc/elements/1.1/}language").text = "en"
        ET.SubElement(metadata, "{http://purl.org/dc/elements/1.1/}creator").text = "Test Author"
        ET.SubElement(metadata, "{http://purl.org/dc/elements/1.1/}identifier").text = "test-id-123"

        # Add meta elements
        ET.SubElement(
            metadata,
            "{http://www.idpf.org/2007/opf}meta",
            {"name": "cover", "content": "cover-image"},
        )

        # Add Calibre metadata if requested
        if with_calibre:
            ET.SubElement(
                metadata,
                "{http://www.idpf.org/2007/opf}meta",
                {"name": "calibre:timestamp", "content": "2024-01-01T00:00:00+00:00"},
            )
            ET.SubElement(
                metadata,
                "{http://www.idpf.org/2007/opf}meta",
                {"name": "calibre:user_metadata:#myseries", "content": "{}"},
            )
            ET.SubElement(metadata, "{http://calibre.kovidgoyal.net/2009/metadata}custom").text = "custom value"

        return metadata

    def test_remove_calibre_metadata(self):
        """Test that Calibre metadata is removed."""
        metadata = self._create_test_metadata(with_calibre=True)

        # Verify Calibre metadata exists
        calibre_elements = [elem for elem in metadata if "calibre" in elem.tag.lower() or "calibre" in elem.get("name", "").lower()]
        self.assertGreater(len(calibre_elements), 0, "Should have Calibre metadata before removal")

        # Remove Calibre metadata
        _remove_calibre_metadata(metadata, self.namespaces)

        # Verify Calibre metadata is gone
        calibre_elements = [elem for elem in metadata if "calibre" in elem.tag.lower() or "calibre" in elem.get("name", "").lower()]
        self.assertEqual(len(calibre_elements), 0, "Should not have Calibre metadata after removal")

        # Verify non-Calibre metadata remains
        title = metadata.find(".//dc:title", self.namespaces)
        self.assertIsNotNone(title)
        self.assertEqual(title.text, "Test Title")

    def test_reorder_metadata_elements(self):
        """Test that metadata elements are reordered consistently."""
        metadata = self._create_test_metadata()

        # Original order: description, title, language, creator, identifier, meta
        original_order = [self._get_simple_tag(elem) for elem in metadata]
        self.assertEqual(
            original_order,
            ["dc:description", "dc:title", "dc:language", "dc:creator", "dc:identifier", "opf:meta"],
        )

        # Reorder elements
        _reorder_metadata_elements(metadata, self.namespaces)

        # Expected order: identifier, title, creator, language, description, meta
        expected_order = [
            "dc:identifier",
            "dc:title",
            "dc:creator",
            "dc:language",
            "dc:description",
            "opf:meta",
        ]
        new_order = [self._get_simple_tag(elem) for elem in metadata]
        self.assertEqual(new_order, expected_order)

    def _get_simple_tag(self, elem):
        """Get simplified tag name for testing."""
        return _get_tag_name(elem, self.namespaces)

    def test_get_tag_name(self):
        """Test tag name extraction."""
        # Create test elements
        title = ET.Element("{http://purl.org/dc/elements/1.1/}title")
        meta = ET.Element("{http://www.idpf.org/2007/opf}meta")

        # Test tag name extraction
        self.assertEqual(_get_tag_name(title, self.namespaces), "dc:title")
        self.assertEqual(_get_tag_name(meta, self.namespaces), "opf:meta")

    def test_indent_xml(self):
        """Test XML indentation."""
        # Create a simple XML structure
        root = ET.Element("root")
        ET.SubElement(root, "child1")
        child2 = ET.SubElement(root, "child2")
        grandchild = ET.SubElement(child2, "grandchild")
        grandchild.text = "text"

        # Apply indentation
        _indent_xml(root)

        # Convert to string to check formatting
        xml_str = ET.tostring(root, encoding="unicode")

        # Check that newlines and indentation are present
        self.assertIn("\n", xml_str, "Should have newlines")
        self.assertIn("  ", xml_str, "Should have indentation")

        # Check structure
        lines = xml_str.split("\n")
        self.assertGreater(len(lines), 1, "Should be multi-line")

    def test_reorder_preserves_content(self):
        """Test that reordering preserves all element content."""
        metadata = self._create_test_metadata()

        # Count elements before
        original_count = len(list(metadata))
        original_titles = [elem.text for elem in metadata.findall(".//dc:title", self.namespaces)]

        # Reorder
        _reorder_metadata_elements(metadata, self.namespaces)

        # Count elements after
        new_count = len(list(metadata))
        new_titles = [elem.text for elem in metadata.findall(".//dc:title", self.namespaces)]

        # Verify no elements lost
        self.assertEqual(original_count, new_count)
        self.assertEqual(original_titles, new_titles)

    def test_reorder_handles_multiple_same_tags(self):
        """Test that reordering handles multiple elements with the same tag."""
        metadata = self._create_test_metadata()

        # Add multiple creators
        ET.SubElement(metadata, "{http://purl.org/dc/elements/1.1/}creator").text = "Second Author"
        ET.SubElement(metadata, "{http://purl.org/dc/elements/1.1/}creator").text = "Third Author"

        # Reorder
        _reorder_metadata_elements(metadata, self.namespaces)

        # Verify all creators are present and in order
        creators = metadata.findall(".//dc:creator", self.namespaces)
        self.assertEqual(len(creators), 3)

        # Verify creators appear before other elements (except identifier and title)
        creator_indices = [i for i, elem in enumerate(metadata) if _get_tag_name(elem, self.namespaces) == "dc:creator"]
        language_index = next(i for i, elem in enumerate(metadata) if _get_tag_name(elem, self.namespaces) == "dc:language")

        # All creators should appear before language
        for idx in creator_indices:
            self.assertLess(idx, language_index, "Creators should appear before language")

    def test_normalization_consistency(self):
        """Test that normalizing the same content twice produces identical results."""
        metadata1 = self._create_test_metadata(with_calibre=True)
        metadata2 = self._create_test_metadata(with_calibre=True)

        # Apply normalization to both
        _remove_calibre_metadata(metadata1, self.namespaces)
        _reorder_metadata_elements(metadata1, self.namespaces)
        _indent_xml(metadata1)

        _remove_calibre_metadata(metadata2, self.namespaces)
        _reorder_metadata_elements(metadata2, self.namespaces)
        _indent_xml(metadata2)

        # Convert both to strings
        xml1 = ET.tostring(metadata1, encoding="unicode")
        xml2 = ET.tostring(metadata2, encoding="unicode")

        # Should be identical
        self.assertEqual(xml1, xml2, "Normalized metadata should be identical")
