"""Tests for the shared language text-slice extractor (PDF text layer / EPUB).

The slices must be disjoint, and a short book (a PDF with fewer than 6 pages,
or an EPUB with too little text for two non-overlapping ~3000-char windows)
yields a single slice that can never vote.
"""

from unittest.mock import MagicMock, patch

from django.test import TestCase

from books.scanner.extractors.text_slices import (
    EPUB_SLICE_CHARS,
    extract_text_slices,
)
from books.utils.language import detect_language_from_slices


def _pdf_with_pages(count, text_fn=None):
    """Return a mocked PdfReader with ``count`` pages each carrying text."""
    pages = []
    for i in range(count):
        page = MagicMock()
        page.extract_text.return_value = text_fn(i) if text_fn else f"page {i} text"
        pages.append(page)
    reader = MagicMock()
    reader.pages = pages
    return reader


def _epub_with_items(texts):
    """Return a mocked ebooklib book whose document items carry ``texts``."""
    items = []
    for text in texts:
        item = MagicMock()
        item.get_type.return_value = 9  # ITEM_DOCUMENT
        item.get_content.return_value = text.encode("utf-8")
        items.append(item)
    book = MagicMock()
    book.get_items.return_value = items
    return book


# A single repeated token gives long, deterministic non-whitespace text.
def _long_text(marker, nws_chars):
    word = marker + " "
    return (word * (nws_chars // len(marker) + 1))[: nws_chars * 2]


class ExtractTextSlicesTests(TestCase):
    def test_unsupported_format_returns_none(self):
        self.assertIsNone(extract_text_slices("/tmp/book.mobi"))
        self.assertIsNone(extract_text_slices("/tmp/book.txt"))

    @patch("PyPDF2.PdfReader")
    def test_pdf_front_and_middle_slices_are_disjoint(self, mock_reader):
        # 8-page PDF: front = pages 1-3 (indexes 0-2), middle starts at
        # max(page 4, centre) = max(4, 4) -> pages 4-6 (indexes 3-5).
        mock_reader.return_value = _pdf_with_pages(8)
        slices = extract_text_slices("/tmp/book.pdf")
        self.assertEqual(len(slices), 2)
        front, middle = slices
        self.assertIn("page 0 text", front)
        self.assertIn("page 2 text", front)
        self.assertNotIn("page 3 text", front)
        self.assertIn("page 3 text", middle)
        self.assertIn("page 5 text", middle)

    @patch("PyPDF2.PdfReader")
    def test_pdf_six_pages_middle_starts_at_page_four(self, mock_reader):
        # 6 pages: centre = 3, but page 4 is later, so middle = pages 4-6
        # (indexes 3-5) and is disjoint from front (indexes 0-2).
        mock_reader.return_value = _pdf_with_pages(6)
        slices = extract_text_slices("/tmp/book.pdf")
        self.assertEqual(len(slices), 2)
        front, middle = slices
        self.assertIn("page 2 text", front)
        self.assertNotIn("page 3 text", front)
        self.assertIn("page 3 text", middle)
        self.assertIn("page 5 text", middle)

    @patch("PyPDF2.PdfReader")
    def test_pdf_five_pages_single_slice_no_vote(self, mock_reader):
        mock_reader.return_value = _pdf_with_pages(5, lambda i: _long_text(f"p{i}", 400))
        slices = extract_text_slices("/tmp/book.pdf")
        self.assertEqual(len(slices), 1)
        self.assertIsNone(detect_language_from_slices(slices))

    @patch("PyPDF2.PdfReader")
    def test_pdf_four_pages_single_slice_no_vote(self, mock_reader):
        mock_reader.return_value = _pdf_with_pages(4, lambda i: _long_text(f"p{i}", 400))
        slices = extract_text_slices("/tmp/book.pdf")
        self.assertEqual(len(slices), 1)
        self.assertIsNone(detect_language_from_slices(slices))

    @patch("PyPDF2.PdfReader")
    def test_pdf_too_short_returns_empty(self, mock_reader):
        mock_reader.return_value = _pdf_with_pages(3)
        self.assertEqual(extract_text_slices("/tmp/book.pdf"), [""])

    @patch("PyPDF2.PdfReader")
    def test_pdf_read_error_returns_empty(self, mock_reader):
        mock_reader.side_effect = Exception("boom")
        self.assertEqual(extract_text_slices("/tmp/book.pdf"), [""])

    @patch("ebooklib.epub.read_epub")
    def test_epub_two_non_overlapping_windows(self, mock_read_epub):
        # Total far above 2*EPUB_SLICE_CHARS: front and middle windows differ.
        chapters = [_long_text(f"chap{i}", EPUB_SLICE_CHARS * 2) for i in range(10)]
        mock_read_epub.return_value = _epub_with_items(chapters)
        slices = extract_text_slices("/tmp/book.epub")
        self.assertEqual(len(slices), 2)
        front, middle = slices
        self.assertGreaterEqual(
            sum(1 for ch in front if not ch.isspace()), EPUB_SLICE_CHARS
        )
        self.assertGreaterEqual(
            sum(1 for ch in middle if not ch.isspace()), EPUB_SLICE_CHARS
        )
        self.assertIn("chap0", front)
        self.assertNotIn("chap9", front)
        self.assertNotIn("chap0", middle)
        self.assertIn("chap5", middle)

    @patch("ebooklib.epub.read_epub")
    def test_epub_one_file_short_no_vote(self, mock_read_epub):
        # A single short chapter below 2*EPUB_SLICE_CHARS -> one slice, no vote.
        mock_read_epub.return_value = _epub_with_items([_long_text("only", 800)])
        slices = extract_text_slices("/tmp/book.epub")
        self.assertEqual(len(slices), 1)
        self.assertIsNone(detect_language_from_slices(slices))

    @patch("ebooklib.epub.read_epub")
    def test_epub_three_chapters_short_no_vote(self, mock_read_epub):
        texts = [_long_text(f"c{i}", 900) for i in range(3)]
        mock_read_epub.return_value = _epub_with_items(texts)
        slices = extract_text_slices("/tmp/book.epub")
        self.assertEqual(len(slices), 1)
        self.assertIsNone(detect_language_from_slices(slices))

    @patch("ebooklib.epub.read_epub")
    def test_epub_windows_overlap_threshold_single_slice(self, mock_read_epub):
        # Just under 2*EPUB_SLICE_CHARS non-whitespace chars -> the two windows
        # would overlap, so only one slice is returned.
        total = 2 * EPUB_SLICE_CHARS - 1
        mock_read_epub.return_value = _epub_with_items([_long_text("x", total)])
        slices = extract_text_slices("/tmp/book.epub")
        self.assertEqual(len(slices), 1)

    @patch("ebooklib.epub.read_epub")
    def test_epub_no_documents_returns_empty(self, mock_read_epub):
        book = MagicMock()
        book.get_items.return_value = []
        mock_read_epub.return_value = book
        self.assertEqual(extract_text_slices("/tmp/book.epub"), [""])

    @patch("ebooklib.epub.read_epub")
    def test_epub_read_error_returns_empty(self, mock_read_epub):
        mock_read_epub.side_effect = Exception("boom")
        self.assertEqual(extract_text_slices("/tmp/book.epub"), [""])
