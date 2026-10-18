"""Shared text-slice extraction for language detection.

Extracts disjoint text slices from a PDF text layer or from EPUB chapters, for
language detection. No OCR: pages/chapters with no text layer yield no text, so
image-only content contributes nothing.

Slices are disjoint so the same characters can never vote twice:

- PDF: the front slice is pages 1-3. The middle slice starts at the later of
  page 4 and the centre page (``max(4, page_count // 2)``) and spans three
  pages. A PDF with fewer than 6 pages yields a single slice (no middle), so it
  can never reach the two-slice vote threshold.
- EPUB: the concatenated text of every document chapter is split into two
  non-overlapping windows of about ``EPUB_SLICE_CHARS`` non-whitespace
  characters, one at the start and one at the midpoint. When the two windows
  would overlap (fewer than ``2 * EPUB_SLICE_CHARS`` non-whitespace characters
  in total) only the start window is returned, so the book can never vote.
"""

import logging
from pathlib import Path

logger = logging.getLogger("books.scanner")

# Non-whitespace characters per EPUB window ("about 3000").
EPUB_SLICE_CHARS = 3000


def extract_text_slices(file_path):
    """Return a list of disjoint text slices for a PDF or EPUB, else ``None``.

    Unsupported formats return ``None``, so the caller falls back to embedded /
    folder language instead of flagging the book undetermined. A PDF or EPUB
    whose text layer is empty returns ``[""]``. A short book (a PDF with fewer
    than 6 pages, or an EPUB with too little text for two disjoint windows)
    returns a single slice, which fails the two-slice vote gate without
    erroring.
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
    except Exception as e:
        logger.warning("PDF text-slice open failed (%s): %s", type(e).__name__, e)
        return [""]
    total = len(reader.pages)
    if total < 4:
        return [""]
    front = _pdf_pages_text(reader, 0, 3)
    if total < 6:
        # Fewer than 6 pages: front slice only, no middle, so no vote.
        return [front]
    # Middle starts at the later of page 4 and the centre (1-indexed), so it is
    # always disjoint from the front slice (pages 1-3).
    mid_start_page = max(4, total // 2)
    middle = _pdf_pages_text(
        reader, mid_start_page - 1, min(mid_start_page + 2, total)
    )
    return [front, middle]


def _pdf_pages_text(reader, start, end):
    parts = []
    for index in range(start, end):
        try:
            text = reader.pages[index].extract_text()
        except Exception as e:
            logger.warning(
                "PDF page %d text extraction failed (%s): %s",
                index,
                type(e).__name__,
                e,
            )
            text = None
        if text:
            parts.append(text)
    return "\n".join(parts)


def _epub_slices(path):
    from ebooklib import epub

    from books.scanner.extractors.content_isbn import _extract_text_from_html

    try:
        book = epub.read_epub(str(path))
    except Exception as e:
        logger.warning("EPUB text-slice open failed (%s): %s", type(e).__name__, e)
        return [""]
    items = [item for item in book.get_items() if item.get_type() == 9]  # ITEM_DOCUMENT
    if not items:
        return [""]

    full = _join_items(items, _extract_text_from_html)
    total_nws = sum(1 for ch in full if not ch.isspace())
    if total_nws < 2 * EPUB_SLICE_CHARS:
        # The two windows would overlap -> a single slice, which cannot vote.
        return [_nws_window(full, 0, EPUB_SLICE_CHARS)]
    front = _nws_window(full, 0, EPUB_SLICE_CHARS)
    middle = _nws_window(full, total_nws // 2, EPUB_SLICE_CHARS)
    return [front, middle]


def _nws_window(text, start, count):
    """Return a substring covering ``count`` non-whitespace chars of ``text``,
    beginning from the ``start``-th non-whitespace character."""
    out = []
    seen = 0
    gathered = 0
    for ch in text:
        if not ch.isspace():
            seen += 1
            if seen > start:
                if gathered >= count:
                    break
                out.append(ch)
                gathered += 1
        elif seen > start and gathered < count:
            out.append(ch)
    return "".join(out)


def _join_items(items, extract):
    parts = []
    for item in items:
        try:
            content = item.get_content().decode("utf-8", errors="ignore")
            parts.append(extract(content))
        except Exception as e:
            logger.warning(
                "EPUB item text extraction failed (%s): %s", type(e).__name__, e
            )
            continue
    return " ".join(part for part in parts if part)
