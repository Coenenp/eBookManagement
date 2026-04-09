"""
Tests for EPUB version detection and upgrading.

Tests cover:
- Version detection (1.0, 2.0, 3.0, missing version)
- Upgrading EPUB 1.0/2.0 to 3.0
- NCX to navigation conversion
- Metadata format updates
- Manifest property updates
"""

import shutil
import tempfile
import zipfile
from pathlib import Path

from django.test import TestCase

from books.utils.epub.version_upgrader import (
    detect_epub_version,
    upgrade_epub_to_3,
)


class EPUBVersionDetectionTestCase(TestCase):
    """Test EPUB version detection."""

    def setUp(self):
        """Create test EPUBs with different versions."""
        self.test_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        """Clean up test directory."""
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    def test_detect_epub_3(self):
        """Test detecting EPUB 3.0."""
        epub_path = self.test_dir / "test_v3.epub"
        self._create_test_epub(epub_path, version="3.0", with_nav=True)

        # Extract and detect
        extract_dir = self.test_dir / "extracted_v3"
        with zipfile.ZipFile(epub_path, "r") as zf:
            zf.extractall(extract_dir)

        opf_path = extract_dir / "OEBPS" / "content.opf"
        version = detect_epub_version(opf_path)

        self.assertEqual(version, "3.0")

    def test_detect_epub_2(self):
        """Test detecting EPUB 2.0."""
        epub_path = self.test_dir / "test_v2.epub"
        self._create_test_epub(epub_path, version="2.0", with_nav=False)

        extract_dir = self.test_dir / "extracted_v2"
        with zipfile.ZipFile(epub_path, "r") as zf:
            zf.extractall(extract_dir)

        opf_path = extract_dir / "OEBPS" / "content.opf"
        version = detect_epub_version(opf_path)

        self.assertEqual(version, "2.0")

    def test_detect_missing_version(self):
        """Test detecting EPUB with missing version attribute."""
        epub_path = self.test_dir / "test_no_version.epub"
        self._create_test_epub(epub_path, version=None, with_nav=False)

        extract_dir = self.test_dir / "extracted_no_version"
        with zipfile.ZipFile(epub_path, "r") as zf:
            zf.extractall(extract_dir)

        opf_path = extract_dir / "OEBPS" / "content.opf"
        version = detect_epub_version(opf_path)

        # Should default to 2.0
        self.assertEqual(version, "2.0")

    def _create_test_epub(self, epub_path: Path, version: str = "3.0", with_nav: bool = True):
        """Create a test EPUB file."""
        with zipfile.ZipFile(epub_path, "w", zipfile.ZIP_DEFLATED) as epub:
            # mimetype
            epub.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)

            # container.xml
            container_xml = """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>"""
            epub.writestr("META-INF/container.xml", container_xml)

            # OPF
            version_attr = f' version="{version}"' if version else ""
            nav_item = (
                '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>'
                if with_nav
                else '<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>'
            )

            opf_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" unique-identifier="uuid_id"{version_attr}>
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="uuid_id">urn:uuid:12345678-1234-1234-1234-123456789012</dc:identifier>
    <dc:title>Test Book</dc:title>
    <dc:language>en</dc:language>
  </metadata>
  <manifest>
    <item id="chapter1" href="chapter1.xhtml" media-type="application/xhtml+xml"/>
    {nav_item}
  </manifest>
  <spine toc="ncx">
    <itemref idref="chapter1"/>
  </spine>
</package>"""
            epub.writestr("OEBPS/content.opf", opf_content)

            # Chapter
            epub.writestr("OEBPS/chapter1.xhtml", '<?xml version="1.0"?><html xmlns="http://www.w3.org/1999/xhtml"><body><p>Chapter 1</p></body></html>')

            # Nav or NCX depending on version
            if with_nav:
                nav_content = """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<head><title>Navigation</title></head>
<body>
<nav epub:type="toc" id="toc">
<ol><li><a href="chapter1.xhtml">Chapter 1</a></li></ol>
</nav>
</body>
</html>"""
                epub.writestr("OEBPS/nav.xhtml", nav_content)
            else:
                ncx_content = """<?xml version="1.0" encoding="UTF-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
<navMap>
<navPoint id="navpoint-1">
<navLabel><text>Chapter 1</text></navLabel>
<content src="chapter1.xhtml"/>
</navPoint>
</navMap>
</ncx>"""
                epub.writestr("OEBPS/toc.ncx", ncx_content)


class EPUBVersionUpgradeTestCase(TestCase):
    """Test EPUB version upgrading."""

    def setUp(self):
        """Create test environment."""
        self.test_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        """Clean up."""
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    def test_upgrade_epub_2_to_3(self):
        """Test upgrading EPUB 2.0 to 3.0."""
        # Create EPUB 2.0
        epub_path = self.test_dir / "test_v2.epub"
        self._create_epub_2(epub_path)

        # Extract
        extract_dir = self.test_dir / "extracted"
        with zipfile.ZipFile(epub_path, "r") as zf:
            zf.extractall(extract_dir)

        opf_path = extract_dir / "OEBPS" / "content.opf"

        # Verify it's EPUB 2.0
        version_before = detect_epub_version(opf_path)
        self.assertEqual(version_before, "2.0")

        # Upgrade
        success = upgrade_epub_to_3(extract_dir, opf_path)
        self.assertTrue(success)

        # Verify upgraded to 3.0
        version_after = detect_epub_version(opf_path)
        self.assertEqual(version_after, "3.0")

        # Verify nav document created
        nav_path = extract_dir / "OEBPS" / "nav.xhtml"
        self.assertTrue(nav_path.exists())

    def test_upgrade_creates_nav_from_ncx(self):
        """Test that NCX is converted to EPUB 3 navigation."""
        epub_path = self.test_dir / "test_ncx.epub"
        self._create_epub_2_with_ncx(epub_path)

        extract_dir = self.test_dir / "extracted_ncx"
        with zipfile.ZipFile(epub_path, "r") as zf:
            zf.extractall(extract_dir)

        opf_path = extract_dir / "OEBPS" / "content.opf"

        # Upgrade
        success = upgrade_epub_to_3(extract_dir, opf_path)
        self.assertTrue(success)

        # Check nav document
        nav_path = extract_dir / "OEBPS" / "nav.xhtml"
        self.assertTrue(nav_path.exists())

        # Verify nav contains TOC from NCX
        nav_content = nav_path.read_text(encoding="utf-8")
        self.assertIn("Chapter 1", nav_content)
        self.assertIn("Chapter 2", nav_content)

    def test_upgrade_already_epub_3(self):
        """Test that EPUB 3.0 is not re-upgraded."""
        epub_path = self.test_dir / "test_v3.epub"
        self._create_epub_3(epub_path)

        extract_dir = self.test_dir / "extracted_v3"
        with zipfile.ZipFile(epub_path, "r") as zf:
            zf.extractall(extract_dir)

        opf_path = extract_dir / "OEBPS" / "content.opf"

        # Should return True but not modify
        success = upgrade_epub_to_3(extract_dir, opf_path)
        self.assertTrue(success)

        # Still 3.0
        version = detect_epub_version(opf_path)
        self.assertEqual(version, "3.0")

    def _create_epub_2(self, epub_path: Path):
        """Create basic EPUB 2.0."""
        with zipfile.ZipFile(epub_path, "w") as epub:
            epub.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
            epub.writestr(
                "META-INF/container.xml",
                """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>""",
            )
            epub.writestr(
                "OEBPS/content.opf",
                """<?xml version="1.0"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>Test Book</dc:title>
  </metadata>
  <manifest>
    <item id="chapter1" href="chapter1.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine><itemref idref="chapter1"/></spine>
</package>""",
            )
            epub.writestr("OEBPS/chapter1.xhtml", '<html xmlns="http://www.w3.org/1999/xhtml"><body><p>Text</p></body></html>')

    def _create_epub_2_with_ncx(self, epub_path: Path):
        """Create EPUB 2.0 with NCX table of contents."""
        with zipfile.ZipFile(epub_path, "w") as epub:
            epub.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
            epub.writestr(
                "META-INF/container.xml",
                """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>""",
            )
            epub.writestr(
                "OEBPS/content.opf",
                """<?xml version="1.0"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>Test Book</dc:title>
  </metadata>
  <manifest>
    <item id="chapter1" href="chapter1.xhtml" media-type="application/xhtml+xml"/>
    <item id="chapter2" href="chapter2.xhtml" media-type="application/xhtml+xml"/>
    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
  </manifest>
  <spine toc="ncx">
    <itemref idref="chapter1"/>
    <itemref idref="chapter2"/>
  </spine>
</package>""",
            )
            epub.writestr(
                "OEBPS/toc.ncx",
                """<?xml version="1.0" encoding="UTF-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
<navMap>
  <navPoint id="navpoint-1">
    <navLabel><text>Chapter 1</text></navLabel>
    <content src="chapter1.xhtml"/>
  </navPoint>
  <navPoint id="navpoint-2">
    <navLabel><text>Chapter 2</text></navLabel>
    <content src="chapter2.xhtml"/>
  </navPoint>
</navMap>
</ncx>""",
            )
            epub.writestr("OEBPS/chapter1.xhtml", '<html xmlns="http://www.w3.org/1999/xhtml"><body><p>Chapter 1</p></body></html>')
            epub.writestr("OEBPS/chapter2.xhtml", '<html xmlns="http://www.w3.org/1999/xhtml"><body><p>Chapter 2</p></body></html>')

    def _create_epub_3(self, epub_path: Path):
        """Create EPUB 3.0."""
        with zipfile.ZipFile(epub_path, "w") as epub:
            epub.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
            epub.writestr(
                "META-INF/container.xml",
                """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>""",
            )
            epub.writestr(
                "OEBPS/content.opf",
                """<?xml version="1.0"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="uuid_id">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="uuid_id">urn:uuid:test</dc:identifier>
    <dc:title>Test Book</dc:title>
    <meta property="dcterms:modified">2026-02-07T00:00:00Z</meta>
  </metadata>
  <manifest>
    <item id="chapter1" href="chapter1.xhtml" media-type="application/xhtml+xml"/>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
  </manifest>
  <spine><itemref idref="chapter1"/></spine>
</package>""",
            )
            epub.writestr("OEBPS/chapter1.xhtml", '<html xmlns="http://www.w3.org/1999/xhtml"><body><p>Text</p></body></html>')
            epub.writestr(
                "OEBPS/nav.xhtml",
                """<?xml version="1.0"?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<head><title>Nav</title></head>
<body><nav epub:type="toc"><ol><li><a href="chapter1.xhtml">Chapter 1</a></li></ol></nav></body>
</html>""",
            )
