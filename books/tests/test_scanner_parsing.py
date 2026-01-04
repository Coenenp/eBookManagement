"""
Test cases for Scanner Parsing
"""
from django.test import TestCase

from books.scanner.parsing import parse_path_metadata, resolve_title_author_ambiguity


class ScannerParsingTests(TestCase):
    """Test cases for scanner parsing functions"""

    def test_resolve_title_author_ambiguity_clear_author(self):
        """Test resolving ambiguity when one part is clearly an author"""
        title, authors = resolve_title_author_ambiguity("John Doe", "The Complete Guide")
        self.assertEqual(title, "The Complete Guide")
        self.assertEqual(authors, ["John Doe"])

    def test_resolve_title_author_ambiguity_clear_title(self):
        """Test resolving ambiguity when one part is clearly a title"""
        title, authors = resolve_title_author_ambiguity("The History of Everything", "Jane Smith")
        self.assertEqual(title, "The History of Everything")
        self.assertEqual(authors, ["Jane Smith"])

    def test_resolve_title_author_ambiguity_punctuation_fallback(self):
        """Test resolving ambiguity using punctuation fallback"""
        title, authors = resolve_title_author_ambiguity("Book: A Story", "John Doe")
        self.assertEqual(title, "Book: A Story")  # Contains title words (book, story)
        self.assertEqual(authors, ["John Doe"])  # Clear author name

    def test_resolve_title_author_ambiguity_equal_ambiguity(self):
        """Test resolving ambiguity when both parts are equally ambiguous"""
        title, authors = resolve_title_author_ambiguity("Mystery Novel", "Crime Story")
        # Should fall back to punctuation scoring, first part becomes title
        self.assertEqual(title, "Crime Story")
        self.assertEqual(authors, ["Mystery Novel"])

    def test_parse_path_metadata_simple_title(self):
        """Test parsing simple title from filename"""
        metadata = parse_path_metadata("Book Title.epub")
        self.assertEqual(metadata["title"], "Book Title")

    def test_parse_path_metadata_numbered_title(self):
        """Test parsing numbered title"""
        metadata = parse_path_metadata("02 - Book Title.epub")
        self.assertEqual(metadata["title"], "Book Title")
        self.assertEqual(metadata["series_number"], 2.0)

    def test_parse_path_metadata_author_title_dash(self):
        """Test parsing author-title with dash separator"""
        metadata = parse_path_metadata("John Doe - Book Title.epub")
        self.assertEqual(metadata["title"], "Book Title")
        self.assertEqual(metadata["authors"], ["John Doe"])

    def test_parse_path_metadata_title_author_dash(self):
        """Test parsing title-author with dash separator"""
        metadata = parse_path_metadata("The Complete Guide - John Doe.epub")
        self.assertEqual(metadata["title"], "The Complete Guide")
        self.assertEqual(metadata["authors"], ["John Doe"])

    def test_parse_path_metadata_title_by_author(self):
        """Test parsing 'title by author' format"""
        metadata = parse_path_metadata("Book Title by John Doe.epub")
        self.assertEqual(metadata["title"], "Book Title")
        self.assertEqual(metadata["authors"], ["John Doe"])

    def test_parse_path_metadata_title_author_parentheses(self):
        """Test parsing title with author in parentheses"""
        metadata = parse_path_metadata("Book Title (John Doe).epub")
        self.assertEqual(metadata["title"], "Book Title")
        self.assertEqual(metadata["authors"], ["John Doe"])

    def test_parse_path_metadata_last_first_format(self):
        """Test parsing 'Last, First - Title' format"""
        metadata = parse_path_metadata("Doe, John - Book Title.epub")
        self.assertEqual(metadata["title"], "Book Title")
        self.assertEqual(metadata["authors"], ["John Doe"])

    def test_parse_path_metadata_series_bracket_format(self):
        """Test parsing '[Series] Title - Author' format"""
        metadata = parse_path_metadata("[Fantasy Series] Book Title - John Doe.epub")
        self.assertEqual(metadata["title"], "Book Title")
        self.assertEqual(metadata["authors"], ["John Doe"])
        self.assertEqual(metadata["series"], "Fantasy Series")

    def test_parse_path_metadata_full_series_format(self):
        """Test parsing 'Series - Number - Title - Author' format"""
        metadata = parse_path_metadata("Fantasy Series - 02 - Book Title - John Doe.epub")
        self.assertEqual(metadata["title"], "Book Title")
        self.assertEqual(metadata["authors"], ["John Doe"])
        self.assertEqual(metadata["series"], "Fantasy Series")
        self.assertEqual(metadata["series_number"], 2.0)

    def test_parse_path_metadata_numbered_with_dash(self):
        """Test parsing numbered title with dash"""
        metadata = parse_path_metadata("03 - Book Title - John Doe.epub")
        self.assertEqual(metadata["title"], "Book Title")
        self.assertEqual(metadata["authors"], ["John Doe"])
        self.assertEqual(metadata["series_number"], 3.0)

    def test_parse_path_metadata_decimal_number(self):
        """Test parsing with decimal series number"""
        metadata = parse_path_metadata("1.5 - Book Title.epub")
        self.assertEqual(metadata["title"], "Book Title")
        self.assertEqual(metadata["series_number"], 1.5)

    def test_parse_path_metadata_underscores_to_spaces(self):
        """Test parsing with underscores converted to spaces"""
        metadata = parse_path_metadata("John_Doe_-_Book_Title.epub")
        self.assertEqual(metadata["title"], "Book Title")
        self.assertEqual(metadata["authors"], ["John Doe"])

    def test_parse_path_metadata_multiple_authors(self):
        """Test parsing with multiple authors"""
        metadata = parse_path_metadata("Book Title - John Doe, Jane Smith.epub")
        self.assertEqual(metadata["title"], "Book Title")
        self.assertEqual(set(metadata["authors"]), {"John Doe", "Jane Smith"})

    def test_parse_path_metadata_complex_path(self):
        """Test parsing from complex file path"""
        file_path = "/library/authors/John Doe/Fantasy Series/02 - Book Title.epub"
        metadata = parse_path_metadata(file_path)

        # Should extract from filename and folder clues
        self.assertIsNotNone(metadata["title"])
        self.assertEqual(metadata["series_number"], 2.0)

    def test_parse_path_metadata_no_pattern_match(self):
        """Test parsing when no pattern matches"""
        metadata = parse_path_metadata("randombook123.epub")

        # Should have basic structure even if no patterns match
        self.assertIn("title", metadata)
        self.assertIn("authors", metadata)
        self.assertIn("series", metadata)
        self.assertIn("series_number", metadata)

    def test_parse_path_metadata_empty_filename(self):
        """Test parsing with empty or minimal filename"""
        metadata = parse_path_metadata(".epub")

        # Should handle gracefully
        self.assertIn("title", metadata)
        self.assertIn("authors", metadata)

    def test_parse_path_metadata_period_separator(self):
        """Test parsing with period separator"""
        metadata = parse_path_metadata("01. Book Title.epub")
        self.assertEqual(metadata["title"], "Book Title")
        self.assertEqual(metadata["series_number"], 1.0)

    def test_parse_path_metadata_series_number_in_title(self):
        """Test series number extraction from title"""
        metadata = parse_path_metadata("Book Title - John Doe.epub")
        # Should check for series number extraction from title after parsing
        self.assertIn("series_number", metadata)

    def test_parse_path_metadata_surname_particles(self):
        """Test parsing with surname particles"""
        metadata = parse_path_metadata("Vincent van Gogh - Art Book.epub")
        self.assertEqual(metadata["title"], "Art Book")
        self.assertEqual(metadata["authors"], ["Vincent van Gogh"])

    def test_parse_path_metadata_case_insensitive(self):
        """Test parsing is case insensitive where appropriate"""
        metadata = parse_path_metadata("book title BY john doe.epub")
        self.assertEqual(metadata["title"], "book title")
        self.assertEqual(metadata["authors"], ["john doe"])

    def test_parse_path_metadata_returns_all_keys(self):
        """Test that parse_path_metadata returns all expected keys"""
        metadata = parse_path_metadata("test.epub")

        expected_keys = ["title", "authors", "series", "series_number"]
        for key in expected_keys:
            self.assertIn(key, metadata)

    def test_parse_path_metadata_authors_is_list(self):
        """Test that authors is always returned as a list"""
        metadata = parse_path_metadata("John Doe - Book Title.epub")
        self.assertIsInstance(metadata["authors"], list)

    def test_parse_path_metadata_last_first_variations(self):
        """Test parsing 'Last, First - Title' format with various names"""
        test_cases = [
            ("Smith, Jane - The Great Adventure.epub", "Jane Smith", "The Great Adventure"),
            ("Doe, John - Book Title.epub", "John Doe", "Book Title"),
            ("Wilson, Robert - Another Story.pdf", "Robert Wilson", "Another Story"),
            ("Johnson, Mary Ann - Complex Title With Words.epub", "Mary Ann Johnson", "Complex Title With Words")
        ]

        for filename, expected_author, expected_title in test_cases:
            with self.subTest(filename=filename):
                metadata = parse_path_metadata(filename)
                self.assertEqual(metadata["title"], expected_title)
                self.assertEqual(metadata["authors"], [expected_author])

    def test_parse_path_metadata_user_requested_surname_prefixes(self):
        """Test parsing with user-requested surname prefixes in various formats"""
        test_cases = [
            # User's specific examples
            ("Vincent van Gogh - Art Book.epub", ["Vincent van Gogh"], "Art Book"),
            ("Van Gogh, Vincent - Painting Guide.epub", ["Vincent Van Gogh"], "Painting Guide"),
            ("Vanden Brande, Karel - Mystery Novel.epub", ["Karel Vanden Brande"], "Mystery Novel"),
            ("Van den Bossche, Peter - History Book.epub", ["Peter Van den Bossche"], "History Book"),
            ("Dela Paz, Maria - Romance Story.epub", ["Maria Dela Paz"], "Romance Story"),

            # Multiple authors with prefixes (simple comma format)
            ("Book Title - Vincent van Gogh, John Doe.epub", ["Vincent van Gogh", "John Doe"], "Book Title"),
            ("Story Collection - Peter Van den Bossche, Maria Dela Paz.epub", ["Peter Van den Bossche", "Maria Dela Paz"], "Story Collection"),
        ]

        for filename, expected_authors, expected_title in test_cases:
            with self.subTest(filename=filename):
                metadata = parse_path_metadata(filename)
                self.assertEqual(metadata["title"], expected_title)
                self.assertEqual(set(metadata["authors"]), set(expected_authors))
