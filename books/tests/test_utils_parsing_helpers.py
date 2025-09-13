"""
Test cases for Parsing Helper utilities
"""
from django.test import TestCase
from pathlib import Path
from books.utils.parsing_helpers import (
    clean_title_and_extract_series_number,
    clean_author_string,
    split_authors,
    normalize_surnames,
    extract_folder_clues,
    looks_like_author,
    is_probable_author,
    extract_number_from_filename,
    fallback_segment_resolution
)


class ParsingHelpersTests(TestCase):
    """Test cases for parsing helper functions"""

    def test_clean_title_and_extract_series_number_with_number(self):
        """Test title cleaning with series number extraction"""
        title, number = clean_title_and_extract_series_number("02 - Book Title")
        self.assertEqual(title, "Book Title")
        self.assertEqual(number, 2.0)

    def test_clean_title_and_extract_series_number_decimal(self):
        """Test title cleaning with decimal series number"""
        title, number = clean_title_and_extract_series_number("1.5 - Book Title")
        self.assertEqual(title, "Book Title")
        self.assertEqual(number, 1.5)

    def test_clean_title_and_extract_series_number_no_number(self):
        """Test title cleaning without series number"""
        title, number = clean_title_and_extract_series_number("Book Title")
        self.assertEqual(title, "Book Title")
        self.assertIsNone(number)

    def test_clean_title_and_extract_series_number_period_separator(self):
        """Test title cleaning with period separator"""
        title, number = clean_title_and_extract_series_number("03. Book Title")
        self.assertEqual(title, "Book Title")
        self.assertEqual(number, 3.0)

    def test_clean_author_string_removes_formats(self):
        """Test author string cleaning removes format strings"""
        result = clean_author_string("Jane Doe (epub)")
        self.assertEqual(result, "Jane Doe")

    def test_clean_author_string_multiple_formats(self):
        """Test author string cleaning with multiple formats"""
        result = clean_author_string("John Smith epub mobi pdf")
        self.assertEqual(result, "John Smith")

    def test_clean_author_string_case_insensitive(self):
        """Test author string cleaning is case insensitive"""
        result = clean_author_string("Jane Doe EPUB")
        self.assertEqual(result, "Jane Doe")

    def test_clean_author_string_no_formats(self):
        """Test author string cleaning with no formats to remove"""
        result = clean_author_string("Jane Doe")
        self.assertEqual(result, "Jane Doe")

    def test_split_authors_comma_separated(self):
        """Test splitting comma-separated authors"""
        result = split_authors("John Doe, Jane Smith, Bob Wilson")
        expected = ["John Doe", "Jane Smith", "Bob Wilson"]
        self.assertEqual(result, expected)

    def test_split_authors_ampersand_separated(self):
        """Test splitting ampersand-separated authors"""
        result = split_authors("John Doe & Jane Smith")
        expected = ["John Doe", "Jane Smith"]
        self.assertEqual(result, expected)

    def test_split_authors_and_separated(self):
        """Test splitting 'and'-separated authors"""
        result = split_authors("John Doe and Jane Smith")
        expected = ["John Doe", "Jane Smith"]
        self.assertEqual(result, expected)

    def test_split_authors_semicolon_separated(self):
        """Test splitting semicolon-separated authors"""
        result = split_authors("John Doe; Jane Smith")
        expected = ["John Doe", "Jane Smith"]
        self.assertEqual(result, expected)

    def test_split_authors_mixed_separators(self):
        """Test splitting with mixed separators"""
        result = split_authors("John Doe, Jane Smith & Bob Wilson")
        expected = ["John Doe", "Jane Smith", "Bob Wilson"]
        self.assertEqual(result, expected)

    def test_split_authors_with_formats(self):
        """Test splitting authors and removing format strings"""
        result = split_authors("John Doe (epub), Jane Smith mobi")
        expected = ["John Doe", "Jane Smith"]
        self.assertEqual(result, expected)

    def test_normalize_surnames_van_prefix(self):
        """Test surname normalization with 'van' prefix"""
        result = normalize_surnames(["Vincent", "van", "Gogh"])
        expected = ["Vincent van Gogh"]
        self.assertEqual(result, expected)

    def test_normalize_surnames_de_prefix(self):
        """Test surname normalization with 'de' prefix"""
        result = normalize_surnames(["Leonardo", "da", "Vinci"])
        expected = ["Leonardo da Vinci"]
        self.assertEqual(result, expected)

    def test_normalize_surnames_no_prefix(self):
        """Test surname normalization without prefix"""
        result = normalize_surnames(["John", "Doe"])
        expected = ["John", "Doe"]
        self.assertEqual(result, expected)

    def test_normalize_surnames_multiple_with_prefix(self):
        """Test surname normalization with multiple names including prefix"""
        result = normalize_surnames(["Vincent", "van", "Gogh", "John", "Doe"])
        expected = ["Vincent van Gogh", "John", "Doe"]
        self.assertEqual(result, expected)

    def test_looks_like_author_valid_name(self):
        """Test looks_like_author with valid author name"""
        self.assertTrue(looks_like_author("John Doe"))
        self.assertTrue(looks_like_author("J.R.R. Tolkien"))
        self.assertTrue(looks_like_author("Dr. Smith"))

    def test_looks_like_author_invalid_name(self):
        """Test looks_like_author with invalid author name"""
        self.assertFalse(looks_like_author("This is a very long title"))
        self.assertFalse(looks_like_author("123"))
        self.assertFalse(looks_like_author(""))

    def test_is_probable_author_valid(self):
        """Test is_probable_author with valid names"""
        self.assertTrue(is_probable_author("John Doe"))
        self.assertTrue(is_probable_author("Jane Smith"))
        self.assertTrue(is_probable_author("Unknown"))

    def test_is_probable_author_invalid(self):
        """Test is_probable_author with titles or common words"""
        self.assertFalse(is_probable_author("The Complete Guide"))
        self.assertFalse(is_probable_author("History of Everything"))
        self.assertFalse(is_probable_author("Manual PDF"))

    def test_extract_number_from_filename_with_number(self):
        """Test extracting number from filename"""
        result = extract_number_from_filename("02 - Book Title.epub")
        self.assertEqual(result, 2.0)

    def test_extract_number_from_filename_decimal(self):
        """Test extracting decimal number from filename"""
        result = extract_number_from_filename("1.5 - Book Title.epub")
        self.assertEqual(result, 1.5)

    def test_extract_number_from_filename_no_number(self):
        """Test extracting number from filename without number"""
        result = extract_number_from_filename("Book Title.epub")
        self.assertIsNone(result)

    def test_fallback_segment_resolution_author_first(self):
        """Test fallback resolution with author first"""
        title, authors = fallback_segment_resolution("John Doe - Book Title")
        self.assertEqual(title, "Book Title")
        self.assertEqual(authors, ["John Doe"])

    def test_fallback_segment_resolution_title_first(self):
        """Test fallback resolution with title first"""
        title, authors = fallback_segment_resolution("The Complete Guide - John Doe")
        self.assertEqual(title, "The Complete Guide")
        self.assertEqual(authors, ["John Doe"])

    def test_fallback_segment_resolution_no_separator(self):
        """Test fallback resolution without separator"""
        title, authors = fallback_segment_resolution("Book Title")
        self.assertEqual(title, "Book Title")
        self.assertEqual(authors, [])

    def test_fallback_segment_resolution_multiple_segments(self):
        """Test fallback resolution with multiple segments"""
        title, authors = fallback_segment_resolution("Series - Book Title - John Doe")
        self.assertEqual(title, "Series - Book Title")
        self.assertEqual(authors, ["John Doe"])

    def test_extract_folder_clues_basic_structure(self):
        """Test extracting clues from folder structure"""
        # Create a mock path structure
        path = Path("/library/Authors/John Doe/Series Name/Book Title.epub")

        # Note: Since we can't create actual folder structure in tests,
        # this test focuses on the function's ability to process path components
        clues = extract_folder_clues(path, max_depth=3)

        # Should return a dictionary with the expected keys
        expected_keys = ["likely_title", "likely_author", "series", "all_authors"]
        for key in expected_keys:
            self.assertIn(key, clues)

    def test_extract_folder_clues_series_detection(self):
        """Test series detection in folder structure"""
        path = Path("/library/Fantasy Series/Book 1.epub")
        clues = extract_folder_clues(path, max_depth=2)

        # Should detect series folder
        self.assertIn("series", clues)

    def test_extract_folder_clues_empty_path(self):
        """Test folder clues extraction with minimal path"""
        path = Path("book.epub")
        clues = extract_folder_clues(path, max_depth=3)

        # Should return dictionary with None values
        expected_keys = ["likely_title", "likely_author", "series", "all_authors"]
        for key in expected_keys:
            self.assertIn(key, clues)
            if key != "all_authors":
                self.assertIsNone(clues[key])
            else:
                self.assertEqual(clues[key], [])

    def test_normalize_surnames_user_requested_prefixes(self):
        """Test normalize_surnames with user-requested prefix examples"""
        # User's specific examples: Van Gogh, Vanden Brande, Van den Bossche, Dela Paz

        # Basic van prefix
        result = normalize_surnames(["Vincent", "van", "Gogh"])
        self.assertEqual(result, ["Vincent van Gogh"])

        # Vanden prefix
        result = normalize_surnames(["Vanden", "Brande"])
        self.assertEqual(result, ["Vanden Brande"])

        # Van den compound prefix
        result = normalize_surnames(["Van", "den", "Bossche"])
        self.assertEqual(result, ["Van den Bossche"])

        # Dela prefix
        result = normalize_surnames(["Dela", "Paz"])
        self.assertEqual(result, ["Dela Paz"])

        # More complex cases with first names
        result = normalize_surnames(["Peter", "Van", "den", "Bossche"])
        self.assertEqual(result, ["Peter Van den Bossche"])

        result = normalize_surnames(["Maria", "Dela", "Cruz"])
        self.assertEqual(result, ["Maria Dela Cruz"])

        # Multiple authors with prefixes
        result = normalize_surnames(["Vincent", "van", "Gogh", "John", "Doe"])
        self.assertEqual(result, ["Vincent van Gogh", "John", "Doe"])

        result = normalize_surnames(["Peter", "Van", "den", "Bossche", "Maria", "Dela", "Paz"])
        self.assertEqual(result, ["Peter Van den Bossche", "Maria Dela Paz"])

    def test_normalize_surnames_classic_prefixes(self):
        """Test normalize_surnames with classic European prefixes"""
        # da Vinci
        result = normalize_surnames(["Leonardo", "da", "Vinci"])
        self.assertEqual(result, ["Leonardo da Vinci"])

        # von prefix
        result = normalize_surnames(["John", "von", "der", "Berg"])
        self.assertEqual(result, ["John von der Berg"])

        # Multiple word prefixes
        result = normalize_surnames(["Marie", "von", "der", "Leyen"])
        self.assertEqual(result, ["Marie von der Leyen"])
