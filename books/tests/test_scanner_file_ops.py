"""
Test cases for Scanner File Operations
"""
from django.test import TestCase
from pathlib import Path
from books.scanner.file_ops import (
    get_file_format,
    find_cover_file,
    find_opf_file
)


class ScannerFileOpsTests(TestCase):
    """Test cases for scanner file operation functions"""

    def test_get_file_format_epub(self):
        """Test file format detection for EPUB"""
        result = get_file_format("book.epub")
        self.assertEqual(result, "epub")

    def test_get_file_format_epub_uppercase(self):
        """Test file format detection for uppercase EPUB"""
        result = get_file_format("book.EPUB")
        self.assertEqual(result, "epub")

    def test_get_file_format_mobi(self):
        """Test file format detection for MOBI"""
        result = get_file_format("book.mobi")
        self.assertEqual(result, "mobi")

    def test_get_file_format_pdf(self):
        """Test file format detection for PDF"""
        result = get_file_format("book.pdf")
        self.assertEqual(result, "pdf")

    def test_get_file_format_azw(self):
        """Test file format detection for AZW"""
        result = get_file_format("book.azw")
        self.assertEqual(result, "azw")

    def test_get_file_format_azw3(self):
        """Test file format detection for AZW3"""
        result = get_file_format("book.azw3")
        self.assertEqual(result, "azw3")

    def test_get_file_format_cbr(self):
        """Test file format detection for CBR"""
        result = get_file_format("comic.cbr")
        self.assertEqual(result, "cbr")

    def test_get_file_format_cbz(self):
        """Test file format detection for CBZ"""
        result = get_file_format("comic.cbz")
        self.assertEqual(result, "cbz")

    def test_get_file_format_unknown(self):
        """Test file format detection for unknown format"""
        result = get_file_format("document.txt")
        self.assertEqual(result, "unknown")

    def test_get_file_format_no_extension(self):
        """Test file format detection for file without extension"""
        result = get_file_format("book")
        self.assertEqual(result, "unknown")

    def test_get_file_format_path_object(self):
        """Test file format detection with Path object"""
        path = Path("book.epub")
        result = get_file_format(str(path))
        self.assertEqual(result, "epub")

    def test_find_cover_file_same_directory(self):
        """Test finding cover file in same directory as ebook"""
        ebook_path = "/books/author/book.epub"
        cover_files = [
            "/books/author/cover.jpg",
            "/books/other/cover.jpg",
            "/books/author/book_cover.png"
        ]

        result = find_cover_file(ebook_path, cover_files)
        self.assertEqual(result, "/books/author/cover.jpg")

    def test_find_cover_file_different_directory(self):
        """Test finding cover file when none in same directory"""
        ebook_path = "/books/author/book.epub"
        cover_files = [
            "/books/other/cover.jpg",
            "/different/path/cover.jpg"
        ]

        result = find_cover_file(ebook_path, cover_files)
        self.assertEqual(result, "")

    def test_find_cover_file_empty_list(self):
        """Test finding cover file with empty cover list"""
        ebook_path = "/books/author/book.epub"
        cover_files = []

        result = find_cover_file(ebook_path, cover_files)
        self.assertEqual(result, "")

    def test_find_cover_file_multiple_in_same_dir(self):
        """Test finding cover file with multiple covers in same directory"""
        ebook_path = "/books/author/book.epub"
        cover_files = [
            "/books/author/cover1.jpg",
            "/books/author/cover2.jpg",
            "/books/other/cover.jpg"
        ]

        # Should return first match in same directory
        result = find_cover_file(ebook_path, cover_files)
        self.assertEqual(result, "/books/author/cover1.jpg")

    def test_find_opf_file_same_directory(self):
        """Test finding OPF file in same directory as ebook"""
        ebook_path = "/books/author/book.epub"
        opf_files = [
            "/books/author/metadata.opf",
            "/books/other/metadata.opf",
            "/books/author/book.opf"
        ]

        result = find_opf_file(ebook_path, opf_files)
        self.assertEqual(result, "/books/author/metadata.opf")

    def test_find_opf_file_different_directory(self):
        """Test finding OPF file when none in same directory"""
        ebook_path = "/books/author/book.epub"
        opf_files = [
            "/books/other/metadata.opf",
            "/different/path/metadata.opf"
        ]

        result = find_opf_file(ebook_path, opf_files)
        self.assertEqual(result, "")

    def test_find_opf_file_empty_list(self):
        """Test finding OPF file with empty OPF list"""
        ebook_path = "/books/author/book.epub"
        opf_files = []

        result = find_opf_file(ebook_path, opf_files)
        self.assertEqual(result, "")

    def test_find_opf_file_multiple_in_same_dir(self):
        """Test finding OPF file with multiple OPF files in same directory"""
        ebook_path = "/books/author/book.epub"
        opf_files = [
            "/books/author/content.opf",
            "/books/author/metadata.opf",
            "/books/other/metadata.opf"
        ]

        # Should return first match in same directory
        result = find_opf_file(ebook_path, opf_files)
        self.assertEqual(result, "/books/author/content.opf")

    def test_find_cover_file_windows_paths(self):
        """Test finding cover file with Windows-style paths"""
        ebook_path = "C:\\Books\\Author\\book.epub"
        cover_files = [
            "C:\\Books\\Author\\cover.jpg",
            "C:\\Books\\Other\\cover.jpg"
        ]

        result = find_cover_file(ebook_path, cover_files)
        self.assertEqual(result, "C:\\Books\\Author\\cover.jpg")

    def test_find_opf_file_windows_paths(self):
        """Test finding OPF file with Windows-style paths"""
        ebook_path = "C:\\Books\\Author\\book.epub"
        opf_files = [
            "C:\\Books\\Author\\metadata.opf",
            "C:\\Books\\Other\\metadata.opf"
        ]

        result = find_opf_file(ebook_path, opf_files)
        self.assertEqual(result, "C:\\Books\\Author\\metadata.opf")

    def test_get_file_format_with_path(self):
        """Test file format detection with full path"""
        result = get_file_format("/full/path/to/book.epub")
        self.assertEqual(result, "epub")

    def test_get_file_format_case_sensitivity(self):
        """Test file format detection is case insensitive"""
        formats = ["book.EPUB", "book.Mobi", "book.PDF", "book.Azw3"]
        expected = ["epub", "mobi", "pdf", "azw3"]

        for file_path, expected_format in zip(formats, expected):
            with self.subTest(file_path=file_path):
                result = get_file_format(file_path)
                self.assertEqual(result, expected_format)
