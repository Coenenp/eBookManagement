"""Shared text-slice extraction for language detection.

Extracts a front slice and a middle slice from the PDF text layer or from EPUB
chapters, for language detection. No OCR: pages/chapters with no text layer
yield no text, so image-only content contributes nothing. One extraction per
book per scan.
"""

from pathlib import Path


def extract_text_slices(file_path):
    """Return ``(front_slice, middle_slice)`` for a PDF or EPUB, else ``None``.

    PDF: the text layer of pages 1-3 (front) and of the 3 pages around the
    centre (middle). EPUB: the text of the first 3 document chapters (front)
    and of 3 chapters around the centre (middle).

    Unsupported formats return ``None``, so the caller falls back to embedded /
    folder language instead of flagging the book undetermined. A PDF or EPUB
    whose text layer is empty still returns a ``("", "")`` tuple, which fails
    the language vote gate (flag undetermined) without erroring.
    """
    path = Path(file_path)
    ext = path.suffix.lower()
    if ext == ".pdf":
        return _pdf_slices(path)
    if ext == ".epub":
        return _epub_slices(path)
    return None


def _pdf_slices(path):
    from PyPDF2 import PdfReader

    try:
        reader = PdfReader(str(path))
    except Exception:
        return "", ""
    total = len(reader.pages)
    if total < 4:
        return "", ""
    front = _pdf_pages_text(reader, 0, 3)
    mid_start = total // 2
    middle = _pdf_pages_text(reader, mid_start, min(mid_start + 3, total))
    return front, middle


def _pdf_pages_text(reader, start, end):
    parts = []
    for index in range(start, end):
        try:
            text = reader.pages[index].extract_text()
        except Exception:
            text = None
        if text:
            parts.append(text)
    return "\n".join(parts)


def _epub_slices(path):
    from ebooklib import epub

    from books.scanner.extractors.content_isbn import _extract_text_from_html

    try:
        book = epub.read_epub(str(path))
    except Exception:
        return "", ""
    items = [item for item in book.get_items() if item.get_type() == 9]  # ITEM_DOCUMENT
    if not items:
        return "", ""

    count = len(items)
    front_items = items[:3]
    mid_start = max(0, count // 2 - 1)
    middle_items = items[mid_start:mid_start + 3]

    front = _join_items(front_items, _extract_text_from_html)
    middle = _join_items(middle_items, _extract_text_from_html)
    return front, middle


def _join_items(items, extract):
    parts = []
    for item in items:
        try:
            content = item.get_content().decode("utf-8", errors="ignore")
            parts.append(extract(content))
        except Exception:
            continue
    return " ".join(part for part in parts if part)
