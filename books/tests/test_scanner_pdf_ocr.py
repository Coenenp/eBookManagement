"""Tests for the PDF OCR fallback used on image-based (scanned) PDFs."""

from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from books.scanner.extractors import pdf_ocr


class PdfOcrModuleTests(SimpleTestCase):
    """Unit tests for pdf_ocr helper functions."""

    def test_contiguous_runs(self):
        self.assertEqual(
            list(pdf_ocr._contiguous_runs([0, 1, 2, 5, 6, 9])),
            [(0, 2), (5, 6), (9, 9)],
        )
        self.assertEqual(list(pdf_ocr._contiguous_runs([3])), [(3, 3)])
        self.assertEqual(list(pdf_ocr._contiguous_runs([])), [])

    def test_ocr_available_disabled_without_deps(self):
        with patch.object(pdf_ocr, "HAS_PDF2IMAGE", False), patch.object(pdf_ocr, "HAS_PYTESSERACT", False):
            self.assertFalse(pdf_ocr.ocr_available())

    def test_ocr_pages_returns_empty_when_unavailable(self):
        with patch.object(pdf_ocr, "ocr_available", return_value=False):
            self.assertEqual(pdf_ocr.ocr_pages("test.pdf", [0]), {})

    def test_ocr_pages_runs_tesseract(self):
        with (
            patch.object(pdf_ocr, "ocr_available", return_value=True),
            patch.object(pdf_ocr, "convert_from_path") as mock_convert,
            patch.object(pdf_ocr, "pytesseract") as mock_pytesseract,
        ):
            mock_image = MagicMock()
            mock_convert.return_value = [mock_image]
            mock_pytesseract.image_to_string.return_value = "ISBN 9780134685991"

            result = pdf_ocr.ocr_pages("test.pdf", [0, 1, 2, 5], dpi=150)

            # Two contiguous runs: pages 0-2 and page 5.
            self.assertEqual(mock_convert.call_count, 2)
            self.assertEqual(result[0], "ISBN 9780134685991")
            self.assertIn(5, result)

    def test_ocr_pages_handles_rasterize_error(self):
        with (
            patch.object(pdf_ocr, "ocr_available", return_value=True),
            patch.object(pdf_ocr, "convert_from_path", side_effect=Exception("poppler missing")),
        ):
            self.assertEqual(pdf_ocr.ocr_pages("test.pdf", [0]), {})

    def test_ocr_pages_handles_tesseract_error(self):
        with (
            patch.object(pdf_ocr, "ocr_available", return_value=True),
            patch.object(pdf_ocr, "convert_from_path") as mock_convert,
            patch.object(pdf_ocr, "pytesseract") as mock_pytesseract,
        ):
            mock_image = MagicMock()
            mock_convert.return_value = [mock_image]
            mock_pytesseract.image_to_string.side_effect = Exception("tesseract not found")

            result = pdf_ocr.ocr_pages("test.pdf", [0], dpi=150)

            self.assertEqual(result, {0: ""})
