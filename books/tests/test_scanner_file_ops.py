"""
Test cases for Scanner File Operations
"""

from pathlib import Path

from django.test import TestCase

from books.scanner.file_ops import find_cover_file, find_opf_file, get_file_format


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
        cover_files = ["/books/author/cover.jpg", "/books/other/cover.jpg", "/books/author/book_cover.png"]

        result = find_cover_file(ebook_path, cover_files)
        self.assertEqual(result, "/books/author/cover.jpg")

    def test_find_cover_file_different_directory(self):
        """Test finding cover file when none in same directory"""
        ebook_path = "/books/author/book.epub"
        cover_files = ["/books/other/cover.jpg", "/different/path/cover.jpg"]

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
        cover_files = ["/books/author/cover1.jpg", "/books/author/cover2.jpg", "/books/other/cover.jpg"]

        # Should return first match in same directory
        result = find_cover_file(ebook_path, cover_files)
        self.assertEqual(result, "/books/author/cover1.jpg")

    def test_find_opf_file_same_directory(self):
        """Test that a same-directory OPF whose stem matches the ebook wins."""
        ebook_path = "/books/author/book.epub"
        opf_files = ["/books/author/metadata.opf", "/books/other/metadata.opf", "/books/author/book.opf"]

        result = find_opf_file(ebook_path, opf_files)
        self.assertEqual(result, "/books/author/book.opf")

    def test_find_opf_file_different_directory(self):
        """Test finding OPF file when none in same directory"""
        ebook_path = "/books/author/book.epub"
        opf_files = ["/books/other/metadata.opf", "/different/path/metadata.opf"]

        result = find_opf_file(ebook_path, opf_files)
        self.assertEqual(result, "")

    def test_find_opf_file_empty_list(self):
        """Test finding OPF file with empty OPF list"""
        ebook_path = "/books/author/book.epub"
        opf_files = []

        result = find_opf_file(ebook_path, opf_files)
        self.assertEqual(result, "")

    def test_find_opf_file_multiple_in_same_dir(self):
        """Test that OPFs without a matching stem or a single-ebook metadata.opf are not matched."""
        ebook_path = "/books/author/book.epub"
        opf_files = ["/books/author/content.opf", "/books/author/metadata.opf", "/books/other/metadata.opf"]

        result = find_opf_file(ebook_path, opf_files)
        self.assertEqual(result, "")

    def test_find_cover_file_windows_paths(self):
        """Test finding cover file with Windows-style paths"""
        ebook_path = "C:\\Books\\Author\\book.epub"
        cover_files = ["C:\\Books\\Author\\cover.jpg", "C:\\Books\\Other\\cover.jpg"]

        result = find_cover_file(ebook_path, cover_files)
        self.assertEqual(result, "C:\\Books\\Author\\cover.jpg")

    def test_find_opf_file_windows_paths(self):
        """Test finding OPF file with Windows-style paths"""
        ebook_path = "C:\\Books\\Author\\book.epub"
        opf_files = ["C:\\Books\\Author\\metadata.opf", "C:\\Books\\Other\\metadata.opf"]

        result = find_opf_file(ebook_path, opf_files, ebook_files=[ebook_path])
        self.assertEqual(result, "C:\\Books\\Author\\metadata.opf")

    def test_find_opf_file_no_stem_match_multiple_ebooks(self):
        """A folder with several ebooks and one unmatched OPF: no book matches it."""
        a = "/books/author/a.epub"
        b = "/books/author/b.epub"
        c = "/books/author/c.epub"
        opf_files = ["/books/author/x.opf"]
        ebook_files = [a, b, c]
        for ebook in ebook_files:
            self.assertEqual(find_opf_file(ebook, opf_files, ebook_files), "")

    def test_find_opf_file_stem_match_wins_regardless_of_order(self):
        """a.epub matches a.opf even when other.opf is listed first."""
        ebook_path = "/books/author/a.epub"
        opf_files = ["/books/author/other.opf", "/books/author/a.opf"]
        result = find_opf_file(ebook_path, opf_files)
        self.assertEqual(result, "/books/author/a.opf")

    def test_find_opf_file_metadata_opf_single_ebook(self):
        """A folder with one ebook and metadata.opf matches metadata.opf."""
        ebook_path = "/books/author/a.epub"
        opf_files = ["/books/author/metadata.opf"]
        result = find_opf_file(ebook_path, opf_files, ebook_files=[ebook_path])
        self.assertEqual(result, "/books/author/metadata.opf")

    def test_find_opf_file_metadata_opf_two_ebooks_does_not_match(self):
        """metadata.opf is not matched when the folder holds two ebooks."""
        a = "/books/author/a.epub"
        b = "/books/author/b.epub"
        opf_files = ["/books/author/metadata.opf"]
        for ebook in (a, b):
            self.assertEqual(find_opf_file(ebook, opf_files, ebook_files=[a, b]), "")

    def test_find_opf_file_stem_match_case_insensitive(self):
        """A.OPF matches a.epub regardless of case."""
        ebook_path = "/books/author/a.epub"
        opf_files = ["/books/author/other.opf", "/books/author/A.OPF"]
        result = find_opf_file(ebook_path, opf_files)
        self.assertEqual(result, "/books/author/A.OPF")

    def test_find_opf_file_multiple_stem_matches_is_ambiguous(self):
        """More than one OPF matching the stem (case-insensitive) is ambiguous."""
        ebook_path = "/books/author/a.epub"
        opf_files = ["/books/author/a.opf", "/books/author/A.OPF"]
        result = find_opf_file(ebook_path, opf_files)
        self.assertEqual(result, "")

    def test_find_opf_file_unrelated_stray_single_ebook(self):
        """A folder with one ebook and an unrelated stray.opf gets an empty string."""
        ebook_path = "/books/author/a.epub"
        opf_files = ["/books/author/stray.opf"]
        result = find_opf_file(ebook_path, opf_files, ebook_files=[ebook_path])
        self.assertEqual(result, "")

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
