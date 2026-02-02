"""
EPUB structure inspection utilities.

Provides tools to examine EPUB internal structure without modification.
Used for previewing changes before metadata embedding.
"""

import logging
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class EPUBFile:
    """Represents a file within an EPUB."""

    path: str
    size: int
    file_type: str  # 'opf', 'xhtml', 'image', 'css', 'font', 'other'

    @property
    def name(self) -> str:
        """Get filename from path."""
        return Path(self.path).name

    @property
    def extension(self) -> str:
        """Get file extension."""
        return Path(self.path).suffix.lower()


@dataclass
class EPUBStructure:
    """Represents the complete structure of an EPUB."""

    opf_path: Optional[str]
    opf_content: Optional[str]
    files: List[EPUBFile]
    total_size: int

    def get_files_by_type(self, file_type: str) -> List[EPUBFile]:
        """Get all files of a specific type."""
        return [f for f in self.files if f.file_type == file_type]

    @property
    def images(self) -> List[EPUBFile]:
        """Get all image files."""
        return self.get_files_by_type("image")

    @property
    def xhtml_files(self) -> List[EPUBFile]:
        """Get all XHTML files."""
        return self.get_files_by_type("xhtml")

    @property
    def css_files(self) -> List[EPUBFile]:
        """Get all CSS files."""
        return self.get_files_by_type("css")


def inspect_epub(epub_path: Path) -> EPUBStructure:
    """
    Inspect EPUB structure without extraction.

    Reads the EPUB zip file and catalogs all internal files,
    identifying file types and extracting OPF content.

    Args:
        epub_path: Path to EPUB file

    Returns:
        EPUBStructure with complete file catalog
    """
    files = []
    opf_path = None
    opf_content = None
    total_size = 0

    try:
        with zipfile.ZipFile(epub_path, "r") as epub_zip:
            for zip_info in epub_zip.filelist:
                if zip_info.is_dir():
                    continue

                file_path = zip_info.filename
                file_size = zip_info.file_size
                total_size += file_size

                # Determine file type
                file_type = _classify_file(file_path)

                files.append(EPUBFile(path=file_path, size=file_size, file_type=file_type))

                # Extract OPF content
                if file_type == "opf":
                    opf_path = file_path
                    opf_content = epub_zip.read(file_path).decode("utf-8", errors="ignore")

        return EPUBStructure(opf_path=opf_path, opf_content=opf_content, files=files, total_size=total_size)

    except Exception as e:
        logger.error(f"Failed to inspect EPUB: {e}", exc_info=True)
        raise


def extract_epub_for_preview(epub_path: Path) -> Path:
    """
    Extract EPUB to temporary directory for detailed inspection.

    Args:
        epub_path: Path to EPUB file

    Returns:
        Path to extraction directory (caller should clean up)
    """
    temp_dir = tempfile.mkdtemp(prefix="epub_preview_")
    extract_dir = Path(temp_dir)

    try:
        with zipfile.ZipFile(epub_path, "r") as epub_zip:
            epub_zip.extractall(extract_dir)

        return extract_dir

    except Exception as e:
        logger.error(f"Failed to extract EPUB for preview: {e}", exc_info=True)
        # Clean up on failure
        import shutil

        shutil.rmtree(extract_dir, ignore_errors=True)
        raise


def get_opf_path(extract_dir: Path) -> Optional[Path]:
    """
    Find OPF file in extracted EPUB.

    Args:
        extract_dir: Path to extracted EPUB directory

    Returns:
        Path to OPF file or None
    """
    for opf_file in extract_dir.rglob("*.opf"):
        return opf_file
    return None


def read_opf_content(opf_path: Path) -> str:
    """
    Read OPF file content.

    Args:
        opf_path: Path to OPF file

    Returns:
        OPF content as string
    """
    return opf_path.read_text(encoding="utf-8")


def _classify_file(file_path: str) -> str:
    """
    Classify file by type based on extension and path.

    Args:
        file_path: File path within EPUB

    Returns:
        File type: 'opf', 'xhtml', 'image', 'css', 'font', 'other'
    """
    path = Path(file_path)
    ext = path.suffix.lower()

    # OPF file
    if ext == ".opf":
        return "opf"

    # XHTML/HTML files
    if ext in {".xhtml", ".html", ".htm", ".xml"}:
        # NCX and container.xml are not content files
        if path.name in {"toc.ncx", "container.xml"}:
            return "other"
        return "xhtml"

    # Images
    if ext in {".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp"}:
        return "image"

    # CSS
    if ext == ".css":
        return "css"

    # Fonts
    if ext in {".ttf", ".otf", ".woff", ".woff2"}:
        return "font"

    return "other"


def get_file_tree(structure: EPUBStructure) -> Dict:
    """
    Build hierarchical tree structure from flat file list.

    Args:
        structure: EPUB structure

    Returns:
        Nested dictionary representing file tree
    """
    tree = {}

    for epub_file in structure.files:
        parts = epub_file.path.split("/")
        current = tree

        for i, part in enumerate(parts):
            if i == len(parts) - 1:
                # Leaf node (file)
                current[part] = {"type": "file", "file_type": epub_file.file_type, "size": epub_file.size, "path": epub_file.path}
            else:
                # Directory node
                if part not in current:
                    current[part] = {"type": "directory", "children": {}}
                elif current[part].get("type") != "directory":
                    # Convert to directory if needed
                    current[part] = {"type": "directory", "children": {}}
                current = current[part]["children"]

    return tree
