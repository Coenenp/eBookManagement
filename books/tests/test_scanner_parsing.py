"""
Test cases for Scanner Parsing
"""

from django.test import TestCase

from books.scanner.parsing import parse_comic_metadata, parse_path_metadata, resolve_title_author_ambiguity


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
            ("Johnson, Mary Ann - Complex Title With Words.epub", "Mary Ann Johnson", "Complex Title With Words"),
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


class FilenameYearAndHyphenatedForenameTests(TestCase):
    """Trailing-year stripping, hyphenated forenames, and volume-vs-year rules."""

    def test_parse_path_metadata_strips_trailing_year(self):
        metadata = parse_path_metadata("Klein, Naomi - Why the DNC Must Hold a Climate Debate (2019).epub")
        self.assertEqual(metadata["title"], "Why the DNC Must Hold a Climate Debate")
        self.assertEqual(metadata["authors"], ["Naomi Klein"])
        self.assertEqual(metadata["publication_year"], 2019)

    def test_parse_path_metadata_strips_year_after_event_text(self):
        metadata = parse_path_metadata("Klein, Naomi - Baghdad Year Zero (Dalton Camp Lecture, 2004).epub")
        self.assertEqual(metadata["title"], "Baghdad Year Zero")
        self.assertEqual(metadata["authors"], ["Naomi Klein"])
        self.assertEqual(metadata["publication_year"], 2004)

    def test_parse_path_metadata_strips_year_after_publisher_text(self):
        metadata = parse_path_metadata("Schwarz-Bart, André - Last of the Just (Atheneum, 1960).epub")
        self.assertEqual(metadata["title"], "Last of the Just")
        self.assertEqual(metadata["authors"], ["André Schwarz-Bart"])
        self.assertEqual(metadata["publication_year"], 1960)

    def test_parse_path_metadata_hyphenated_forename(self):
        metadata = parse_path_metadata("Sartre, Jean-Paul - Being and Nothingness (1943).epub")
        self.assertEqual(metadata["title"], "Being and Nothingness")
        self.assertEqual(metadata["authors"], ["Jean-Paul Sartre"])
        self.assertEqual(metadata["publication_year"], 1943)

    def test_parse_comic_metadata_strips_trailing_year(self):
        metadata = parse_comic_metadata("Largo Winch 03 - H - Dutch Connection (2008).cbz")
        self.assertEqual(metadata["title"], "H - Dutch Connection")
        self.assertEqual(metadata["series"], "Largo Winch")
        self.assertEqual(metadata["series_number"], 3.0)
        self.assertEqual(metadata["publication_year"], 2008)

    def test_parse_path_metadata_keeps_non_year_parenthetical(self):
        metadata = parse_path_metadata("1984 (Nineteen Eighty-Four).epub")
        self.assertEqual(metadata["title"], "1984 (Nineteen Eighty-Four)")
        self.assertIsNone(metadata["publication_year"])

    def test_parse_path_metadata_keeps_volume_parenthetical(self):
        metadata = parse_path_metadata("Book Title (Volume 2).epub")
        self.assertEqual(metadata["title"], "Book Title (Volume 2)")
        self.assertIsNone(metadata["publication_year"])

    def test_parse_path_metadata_numeric_parenthetical_is_not_an_author(self):
        # A parenthetical made only of digits is never an author; it stays
        # part of the title. 1399 is below the 1400-2099 year range, so it is
        # also not stripped as a publication year.
        metadata = parse_path_metadata("Book Title (1399).epub")
        self.assertEqual(metadata["title"], "Book Title (1399)")
        self.assertEqual(metadata["authors"], [])
        self.assertIsNone(metadata["publication_year"])

    def test_parse_path_metadata_pre_1400_year_parenthetical_is_not_an_author(self):
        metadata = parse_path_metadata("Chronicle (1066).epub")
        self.assertEqual(metadata["title"], "Chronicle (1066)")
        self.assertEqual(metadata["authors"], [])
        self.assertIsNone(metadata["publication_year"])

    def test_parse_path_metadata_post_2099_year_parenthetical_is_not_an_author(self):
        metadata = parse_path_metadata("Book Title (2100).epub")
        self.assertEqual(metadata["title"], "Book Title (2100)")
        self.assertEqual(metadata["authors"], [])
        self.assertIsNone(metadata["publication_year"])

    def test_parse_path_metadata_year_only_title_is_not_stripped(self):
        metadata = parse_path_metadata("1984.epub")
        self.assertEqual(metadata["title"], "1984")
        self.assertIsNone(metadata["publication_year"])

    def test_parse_path_metadata_four_digit_never_series_volume(self):
        # A four-digit year must never become a series volume, even after an author.
        metadata = parse_path_metadata("Orwell, George - 1984.epub")
        self.assertEqual(metadata["title"], "1984")
        self.assertEqual(metadata["authors"], ["George Orwell"])
        self.assertIsNone(metadata["series_number"])
        self.assertIsNone(metadata["publication_year"])

    def test_parse_path_metadata_returns_publication_year_key(self):
        metadata = parse_path_metadata("Book Title.epub")
        self.assertIn("publication_year", metadata)
        self.assertIsNone(metadata["publication_year"])

    def test_parse_path_metadata_strips_pre_1900_year(self):
        # Year range is 1400-2099, so a 17th-century year must also strip.
        metadata = parse_path_metadata("Cervantes, Miguel de - Don Quijote (1605).epub")
        self.assertEqual(metadata["title"], "Don Quijote")
        self.assertEqual(metadata["authors"], ["Miguel de Cervantes"])
        self.assertEqual(metadata["publication_year"], 1605)

    def test_parse_path_metadata_strips_year_lower_bound(self):
        # Lower bound of the extended range (1400) must strip.
        metadata = parse_path_metadata("Author, Jane - Early Work (1400).epub")
        self.assertEqual(metadata["title"], "Early Work")
        self.assertEqual(metadata["authors"], ["Jane Author"])
        self.assertEqual(metadata["publication_year"], 1400)


class DashSeparatorWhitespaceTests(TestCase):
    """A dash is a title/author separator only when surrounded by whitespace.

    This is a deliberate behaviour change from master: master split
    "Tolkien-The Hobbit" and "Tolkien -The Hobbit" on the bare dash into
    title/author; this branch keeps them whole (no author) because the dash is
    not surrounded by whitespace on both sides.
    """

    def test_dash_without_surrounding_whitespace_is_not_a_separator(self):
        # Deliberate change from master (which split this on the bare dash into
        # title "The Hobbit" / author "Tolkien"): no whitespace around the dash,
        # so the branch keeps the name whole.
        metadata = parse_path_metadata("Tolkien-The Hobbit.epub")
        self.assertEqual(metadata["title"], "Tolkien-The Hobbit")
        self.assertEqual(metadata["authors"], [])

    def test_dash_with_trailing_whitespace_only_is_not_a_separator(self):
        # Deliberate change from master (which split this on the dash into title
        # "The Hobbit" / author "Tolkien"): whitespace only before the dash, so
        # the branch keeps the name whole.
        metadata = parse_path_metadata("Tolkien -The Hobbit.epub")
        self.assertEqual(metadata["title"], "Tolkien -The Hobbit")
        self.assertEqual(metadata["authors"], [])

    def test_person_like_author_in_parentheses_is_extracted(self):
        metadata = parse_path_metadata("The Hobbit (Tolkien).epub")
        self.assertEqual(metadata["title"], "The Hobbit")
        self.assertEqual(metadata["authors"], ["Tolkien"])

    def test_dash_with_surrounding_whitespace_is_a_separator(self):
        metadata = parse_path_metadata("Tolkien - The Hobbit.epub")
        self.assertEqual(metadata["title"], "The Hobbit")
        self.assertEqual(metadata["authors"], ["Tolkien"])

    def test_by_separator_still_works(self):
        metadata = parse_path_metadata("The Hobbit by Tolkien.epub")
        self.assertEqual(metadata["title"], "The Hobbit")
        self.assertEqual(metadata["authors"], ["Tolkien"])
