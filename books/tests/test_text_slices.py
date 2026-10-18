"""Tests for the shared language text-slice extractor (PDF text layer / EPUB)."""

from unittest.mock import MagicMock, patch

from django.test import TestCase

from books.scanner.extractors.text_slices import extract_text_slices


class ExtractTextSlicesTests(TestCase):
    def test_unsupported_format_returns_none(self):
        self.assertIsNone(extract_text_slices("/tmp/book.mobi"))
        self.assertIsNone(extract_text_slices("/tmp/book.txt"))

    @patch("PyPDF2.PdfReader")
    def test_pdf_front_and_middle_slices(self, mock_reader):
        # 8-page PDF: front = pages 1-3 (indexes 0-2), middle = pages 5-7 (4-6).
        pages = []
        for i in range(8):
            page = MagicMock()
            page.extract_text.return_value = f"page {i} text"
            pages.append(page)
        mock_reader.return_value.pages = pages

        front, middle = extract_text_slices("/tmp/book.pdf")
        self.assertIn("page 0 text", front)
        self.assertIn("page 2 text", front)
        self.assertNotIn("page 3 text", front)
        self.assertIn("page 4 text", middle)
        self.assertIn("page 6 text", middle)

    @patch("PyPDF2.PdfReader")
    def test_pdf_too_short_returns_empty(self, mock_reader):
        mock_reader.return_value.pages = [MagicMock(), MagicMock(), MagicMock()]
        self.assertEqual(extract_text_slices("/tmp/book.pdf"), ("", ""))

    @patch("PyPDF2.PdfReader")
    def test_pdf_read_error_returns_empty(self, mock_reader):
        mock_reader.side_effect = Exception("boom")
        self.assertEqual(extract_text_slices("/tmp/book.pdf"), ("", ""))

    @patch("ebooklib.epub.read_epub")
    def test_epub_front_and_middle_slices(self, mock_read_epub):
        book = MagicMock()
        items = []
        for i in range(10):
            item = MagicMock()
            item.get_type.return_value = 9  # ITEM_DOCUMENT
            item.get_content.return_value = f"<p>chapter {i}</p>".encode("utf-8")
            items.append(item)
        book.get_items.return_value = items
        mock_read_epub.return_value = book

        front, middle = extract_text_slices("/tmp/book.epub")
        self.assertIn("chapter 0", front)
        self.assertIn("chapter 2", front)
        self.assertNotIn("chapter 3", front)
        # 10 items -> middle starts at 4 (10//2 - 1), covers 4-6.
        self.assertIn("chapter 4", middle)
        self.assertIn("chapter 6", middle)

    @patch("ebooklib.epub.read_epub")
    def test_epub_no_documents_returns_empty(self, mock_read_epub):
        book = MagicMock()
        book.get_items.return_value = []
        mock_read_epub.return_value = book
        self.assertEqual(extract_text_slices("/tmp/book.epub"), ("", ""))

    @patch("ebooklib.epub.read_epub")
    def test_epub_read_error_returns_empty(self, mock_read_epub):
        mock_read_epub.side_effect = Exception("boom")
        self.assertEqual(extract_text_slices("/tmp/book.epub"), ("", ""))
