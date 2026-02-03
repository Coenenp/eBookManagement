"""
Cover extraction from various book file formats.

This module provides extractors for:
- EPUB files (internal cover images)
- PDF files (first page as cover)
- Comic archives (CBZ/CBR - first image)
- MOBI files (internal cover)
"""

import logging
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Optional, Tuple

from PIL import Image

logger = logging.getLogger(__name__)

# Optional dependencies for enhanced functionality
# These are imported within try-except blocks to allow graceful degradation
try:
    from pdf2image import convert_from_path

    HAS_PDF2IMAGE = True
except ImportError:
    HAS_PDF2IMAGE = False

try:
    from PyPDF2 import PdfReader

    HAS_PYPDF2 = True
except ImportError:
    HAS_PYPDF2 = False

try:
    import rarfile

    HAS_RARFILE = True
except ImportError:
    HAS_RARFILE = False


class CoverExtractionError(Exception):
    """Raised when cover extraction fails."""

    pass


class EPUBCoverExtractor:
    """Extract cover images from EPUB files."""

    # Common cover image paths in EPUBs
    COMMON_COVER_PATHS = [
        "cover.jpg",
        "cover.jpeg",
        "cover.png",
        "Cover.jpg",
        "Cover.jpeg",
        "Cover.png",
        "OEBPS/cover.jpg",
        "OEBPS/cover.jpeg",
        "OEBPS/cover.png",
        "OEBPS/images/cover.jpg",
        "OEBPS/images/cover.jpeg",
        "OEBPS/images/cover.png",
        "Images/cover.jpg",
        "Images/cover.jpeg",
        "Images/cover.png",
        "images/cover.jpg",
        "images/cover.jpeg",
        "images/cover.png",
    ]

    @classmethod
    def find_cover_in_opf(cls, epub_path: str) -> Optional[str]:
        """
        Parse OPF file to find cover image reference.

        Args:
            epub_path: Path to EPUB file

        Returns:
            Internal path to cover image, or None if not found
        """
        try:
            with zipfile.ZipFile(epub_path, "r") as zf:
                # Find the OPF file
                opf_path = None
                for name in zf.namelist():
                    if name.endswith(".opf"):
                        opf_path = name
                        break

                if not opf_path:
                    return None

                # Read and parse OPF
                opf_content = zf.read(opf_path).decode("utf-8", errors="ignore")

                # Look for cover metadata
                # Format: <meta name="cover" content="cover-image-id"/>
                import re

                cover_id_match = re.search(r'<meta\s+name=["\']cover["\']\s+content=["\']([^"\']+)["\']', opf_content)

                if cover_id_match:
                    cover_id = cover_id_match.group(1)

                    # Find the item with this ID
                    item_match = re.search(rf'<item\s+[^>]*id=["\']({cover_id})["\'][^>]*href=["\']([^"\']+)["\']', opf_content)
                    if not item_match:
                        # Try reversed attribute order
                        item_match = re.search(rf'<item\s+[^>]*href=["\']([^"\']+)["\'][^>]*id=["\']({cover_id})["\']', opf_content)
                        if item_match:
                            href = item_match.group(1)
                        else:
                            return None
                    else:
                        href = item_match.group(2)

                    # Convert relative path to absolute within EPUB
                    opf_dir = str(Path(opf_path).parent)
                    if opf_dir == ".":
                        return href
                    return str(Path(opf_dir) / href)

                return None

        except Exception as e:
            logger.warning(f"Error parsing OPF for cover in {epub_path}: {e}")
            return None

    @classmethod
    def extract_cover(cls, epub_path: str) -> Tuple[Optional[bytes], Optional[str]]:
        """
        Extract cover image from EPUB file.

        Args:
            epub_path: Path to EPUB file

        Returns:
            Tuple of (cover_data: bytes, internal_path: str) or (None, None) if not found

        Raises:
            CoverExtractionError: If EPUB is invalid or cannot be read
        """
        try:
            with zipfile.ZipFile(epub_path, "r") as zf:
                # Strategy 1: Check OPF metadata
                cover_path = cls.find_cover_in_opf(epub_path)
                if cover_path:
                    try:
                        cover_data = zf.read(cover_path)
                        logger.info(f"Extracted cover from OPF metadata: {cover_path}")
                        return cover_data, cover_path
                    except KeyError:
                        logger.warning(f"OPF references non-existent cover: {cover_path}")

                # Strategy 2: Check common cover paths
                for common_path in cls.COMMON_COVER_PATHS:
                    try:
                        cover_data = zf.read(common_path)
                        logger.info(f"Extracted cover from common path: {common_path}")
                        return cover_data, common_path
                    except KeyError:
                        continue

                # Strategy 3: Find first image file
                image_extensions = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
                for name in sorted(zf.namelist()):
                    if Path(name).suffix.lower() in image_extensions:
                        # Skip thumbnails
                        if "thumb" in name.lower() or "thumbnail" in name.lower():
                            continue

                        cover_data = zf.read(name)
                        logger.info(f"Extracted first image as cover: {name}")
                        return cover_data, name

                logger.warning(f"No cover image found in EPUB: {epub_path}")
                return None, None

        except zipfile.BadZipFile:
            raise CoverExtractionError(f"Invalid EPUB file: {epub_path}")
        except Exception as e:
            raise CoverExtractionError(f"Failed to extract cover from EPUB: {e}")

    @classmethod
    def list_images(cls, epub_path: str) -> list[str]:
        """
        List all image files in an EPUB.

        Args:
            epub_path: Path to EPUB file

        Returns:
            List of internal image paths
        """
        try:
            with zipfile.ZipFile(epub_path, "r") as zf:
                image_extensions = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
                return [name for name in zf.namelist() if Path(name).suffix.lower() in image_extensions]
        except Exception as e:
            logger.error(f"Failed to list images in EPUB {epub_path}: {e}")
            return []

    @classmethod
    def list_all_covers(cls, epub_path: str) -> list[dict]:
        """
        Extract all images from EPUB with full metadata.

        Args:
            epub_path: Path to EPUB file

        Returns:
            List of dicts with keys:
                - internal_path: Path inside EPUB
                - image_data: Raw image bytes
                - width: Image width in pixels
                - height: Image height in pixels
                - file_size: Size in bytes
                - format: Image format (JPEG, PNG, etc.)
                - is_opf_cover: True if this is the OPF-designated cover
                - position: 0-based index in sorted image list
        """
        covers = []

        try:
            with zipfile.ZipFile(epub_path, "r") as zf:
                # Find OPF-designated cover
                opf_cover_path = cls.find_cover_in_opf(epub_path)

                # Get all image files
                image_extensions = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
                image_files = [
                    name
                    for name in sorted(zf.namelist())
                    if Path(name).suffix.lower() in image_extensions and not name.startswith("__MACOSX") and not Path(name).name.startswith(".")
                ]

                # Extract metadata for each image
                for position, internal_path in enumerate(image_files):
                    try:
                        # Read image data
                        image_data = zf.read(internal_path)
                        file_size = len(image_data)

                        # Get dimensions and format using PIL
                        try:
                            img = Image.open(BytesIO(image_data))
                            width, height = img.size
                            img_format = img.format or "UNKNOWN"
                        except Exception as e:
                            logger.warning(f"Could not read image {internal_path}: {e}")
                            width = height = 0
                            img_format = "UNKNOWN"

                        # Check if this is the OPF cover
                        is_opf_cover = internal_path == opf_cover_path

                        covers.append(
                            {
                                "internal_path": internal_path,
                                "image_data": image_data,
                                "width": width,
                                "height": height,
                                "file_size": file_size,
                                "format": img_format,
                                "is_opf_cover": is_opf_cover,
                                "position": position,
                            }
                        )

                    except Exception as e:
                        logger.warning(f"Failed to extract metadata for {internal_path}: {e}")
                        continue

                logger.info(f"Found {len(covers)} images in EPUB: {epub_path}")
                return covers

        except Exception as e:
            logger.error(f"Failed to list all covers in EPUB {epub_path}: {e}")
            return []


class PDFCoverExtractor:
    """Extract first page from PDF as cover image."""

    @classmethod
    def extract_cover(cls, pdf_path: str, dpi: int = 150) -> Optional[bytes]:
        """
        Extract first page of PDF as JPG image.

        Args:
            pdf_path: Path to PDF file
            dpi: Resolution for rendering (default: 150)

        Returns:
            JPG image data as bytes, or None if extraction fails

        Raises:
            CoverExtractionError: If PDF is invalid or cannot be read
        """
        try:
            # Try using pdf2image first (requires poppler)
            if HAS_PDF2IMAGE:
                images = convert_from_path(pdf_path, dpi=dpi, first_page=1, last_page=1)

                if images:
                    # Convert to JPG
                    img_bytes = BytesIO()
                    images[0].save(img_bytes, format="JPEG", quality=85)
                    logger.info(f"Extracted PDF first page using pdf2image: {pdf_path}")
                    return img_bytes.getvalue()
            else:
                logger.debug("pdf2image not available, trying PyPDF2")

            # Fallback to PyPDF2 (lower quality, but no external dependencies)
            if HAS_PYPDF2:

                reader = PdfReader(pdf_path)
                if not reader.pages:
                    logger.warning(f"PDF has no pages: {pdf_path}")
                    return None

                # Try to extract images from first page
                page = reader.pages[0]
                if "/XObject" in page["/Resources"]:
                    xobjects = page["/Resources"]["/XObject"].get_object()

                    for obj_name in xobjects:
                        obj = xobjects[obj_name]

                        if obj["/Subtype"] == "/Image":
                            # Extract image data
                            data = obj.get_data()

                            # Try to load with PIL and convert to JPG
                            try:
                                img = Image.open(BytesIO(data))
                                img_bytes = BytesIO()
                                img.convert("RGB").save(img_bytes, format="JPEG", quality=85)
                                logger.info(f"Extracted PDF image using PyPDF2: {pdf_path}")
                                return img_bytes.getvalue()
                            except Exception as e:
                                logger.warning(f"Failed to process extracted image: {e}")
                                continue
            else:
                logger.warning("PyPDF2 not available, PDF cover extraction not supported")

            logger.warning(f"No cover extracted from PDF: {pdf_path}")
            return None

        except Exception as e:
            raise CoverExtractionError(f"Failed to extract cover from PDF: {e}")


class ArchiveCoverExtractor:
    """Extract first image from comic archives (CBZ/CBR)."""

    @classmethod
    def extract_cover(cls, archive_path: str) -> Tuple[Optional[bytes], Optional[str]]:
        """
        Extract first image from comic archive.

        Args:
            archive_path: Path to CBZ or CBR file

        Returns:
            Tuple of (cover_data: bytes, internal_path: str) or (None, None) if not found

        Raises:
            CoverExtractionError: If archive is invalid or cannot be read
        """
        archive_path_obj = Path(archive_path)
        extension = archive_path_obj.suffix.lower()

        try:
            if extension == ".cbz":
                return cls._extract_from_zip(archive_path)
            elif extension == ".cbr":
                return cls._extract_from_rar(archive_path)
            else:
                raise CoverExtractionError(f"Unsupported archive format: {extension}")

        except Exception as e:
            raise CoverExtractionError(f"Failed to extract cover from archive: {e}")

    @classmethod
    def _extract_from_zip(cls, cbz_path: str) -> Tuple[Optional[bytes], Optional[str]]:
        """Extract first image from CBZ (ZIP) archive."""
        try:
            with zipfile.ZipFile(cbz_path, "r") as zf:
                image_extensions = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
                image_files = [
                    name
                    for name in sorted(zf.namelist())
                    if Path(name).suffix.lower() in image_extensions
                    and not name.startswith("__MACOSX")  # Skip macOS metadata
                    and not Path(name).name.startswith(".")  # Skip hidden files
                ]

                if image_files:
                    first_image = image_files[0]
                    cover_data = zf.read(first_image)
                    logger.info(f"Extracted CBZ cover: {first_image}")
                    return cover_data, first_image

                logger.warning(f"No images found in CBZ: {cbz_path}")
                return None, None

        except zipfile.BadZipFile:
            raise CoverExtractionError(f"Invalid CBZ file: {cbz_path}")

    @classmethod
    def _extract_from_rar(cls, cbr_path: str) -> Tuple[Optional[bytes], Optional[str]]:
        """Extract first image from CBR (RAR) archive."""
        if not HAS_RARFILE:
            raise CoverExtractionError("rarfile library not available for CBR extraction")

        try:
            with rarfile.RarFile(cbr_path, "r") as rf:
                image_extensions = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
                image_files = [name for name in sorted(rf.namelist()) if Path(name).suffix.lower() in image_extensions and not Path(name).name.startswith(".")]  # Skip hidden files

                if image_files:
                    first_image = image_files[0]
                    cover_data = rf.read(first_image)
                    logger.info(f"Extracted CBR cover: {first_image}")
                    return cover_data, first_image

                logger.warning(f"No images found in CBR: {cbr_path}")
                return None, None

        except rarfile.BadRarFile:
            raise CoverExtractionError(f"Invalid CBR file: {cbr_path}")
