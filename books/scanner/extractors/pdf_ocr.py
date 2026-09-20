"""PDF OCR utilities for image-based (scanned) PDFs.

Some PDFs have no embedded text layer (typical of scanned or facsimile
documents), which means PyPDF2 cannot extract any searchable text from them.
This module provides a Tesseract-based OCR fallback: it rasterizes PDF pages
with ``pdf2image`` (which requires Poppler) and recognizes the text with
``pytesseract`` (which requires the Tesseract binary).

Both dependencies are optional. If either is missing, or if OCR is disabled
via settings, :func:`ocr_available` returns ``False`` and callers fall back to
the existing embedded-text extraction only.
"""

import logging

logger = logging.getLogger("books.scanner")

try:
    from pdf2image import convert_from_path

    HAS_PDF2IMAGE = True
except ImportError:  # pragma: no cover - depends on the deployment environment
    convert_from_path = None
    HAS_PDF2IMAGE = False

try:
    import pytesseract

    HAS_PYTESSERACT = True
except ImportError:  # pragma: no cover - depends on the deployment environment
    pytesseract = None
    HAS_PYTESSERACT = False


def _configure_tesseract():
    """Point pytesseract at a custom Tesseract binary when configured."""
    if not HAS_PYTESSERACT:
        return
    try:
        from django.conf import settings

        cmd = getattr(settings, "TESSERACT_CMD", None)
        if cmd:
            pytesseract.pytesseract.tesseract_cmd = cmd
    except Exception:  # pragma: no cover - settings access is best-effort
        pass


def _ocr_enabled():
    """Read the PDF_OCR_ENABLED setting (default: enabled)."""
    try:
        from django.conf import settings

        return bool(getattr(settings, "PDF_OCR_ENABLED", True))
    except Exception:  # pragma: no cover - settings access is best-effort
        return True


def _ocr_dpi():
    """Read the PDF_OCR_DPI setting (default: 300)."""
    try:
        from django.conf import settings

        return int(getattr(settings, "PDF_OCR_DPI", 300))
    except Exception:  # pragma: no cover - settings access is best-effort
        return 300


def ocr_available():
    """Return ``True`` when Tesseract OCR can actually be performed."""
    if not (HAS_PDF2IMAGE and HAS_PYTESSERACT):
        return False
    return _ocr_enabled()


def _contiguous_runs(indexes):
    """Yield ``(start, end)`` inclusive contiguous runs for sorted indexes."""
    if not indexes:
        return

    start = prev = indexes[0]
    for index in indexes[1:]:
        if index == prev + 1:
            prev = index
        else:
            yield start, prev
            start = prev = index
    yield start, prev


def ocr_pages(pdf_path, page_indexes, dpi=None):
    """OCR specific PDF pages using Tesseract.

    Args:
        pdf_path: Path to the PDF file.
        page_indexes: Iterable of 0-based page indexes to OCR.
        dpi: Render resolution. Defaults to ``settings.PDF_OCR_DPI``.

    Returns:
        dict mapping 0-based page index to the recognized text. Pages that
        fail to rasterize or recognize are omitted (or mapped to ``""``).
    """
    if not ocr_available():
        return {}

    indexes = sorted({int(index) for index in page_indexes if index is not None})
    if not indexes:
        return {}

    _configure_tesseract()

    if dpi is None:
        dpi = _ocr_dpi()

    results = {}
    try:
        for start, end in _contiguous_runs(indexes):
            # pdf2image uses 1-based page numbers.
            images = convert_from_path(pdf_path, dpi=dpi, first_page=start + 1, last_page=end + 1)
            for offset, image in enumerate(images):
                page_number = start + offset
                try:
                    results[page_number] = pytesseract.image_to_string(image, lang='eng+nld+fra+deu') or ""
                except Exception as exc:
                    logger.warning(f"Tesseract OCR failed for page {page_number} of {pdf_path}: {exc}")
                    results[page_number] = ""
    except Exception as exc:
        logger.warning(f"PDF rasterization failed for OCR on {pdf_path}: {exc}")

    return results
