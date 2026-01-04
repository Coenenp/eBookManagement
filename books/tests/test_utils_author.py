"""
Test cases for Author utilities
"""
from django.test import TestCase

from books.models import Author, BookAuthor, DataSource
from books.tests.test_helpers import create_test_book_with_file, create_test_scan_folder
from books.utils.author import attach_authors, split_author_parts


class AuthorUtilsTests(TestCase):
    """Test cases for Author utility functions"""

    def setUp(self):
        """Set up test data"""
        self.scan_folder = create_test_scan_folder(name="Test Scan Folder")

        self.book = create_test_book_with_file(
            file_path="/test/scan/folder/book.epub",
            file_format="epub",
            file_size=1024000,
            scan_folder=self.scan_folder
        )

        self.source = DataSource.objects.get_or_create(
            name="test_source",
            defaults={"trust_level": 0.8}
        )[0]

    def test_split_author_parts_first_last_format(self):
        """Test splitting author name in 'First Last' format"""
        first, last = split_author_parts("John Doe")
        self.assertEqual(first, "John")
        self.assertEqual(last, "Doe")

    def test_split_author_parts_last_first_format(self):
        """Test splitting author name in 'Last, First' format"""
        first, last = split_author_parts("Doe, John")
        self.assertEqual(first, "John")
        self.assertEqual(last, "Doe")

    def test_split_author_parts_multiple_first_names(self):
        """Test splitting author name with multiple first names"""
        first, last = split_author_parts("John Michael Doe")
        self.assertEqual(first, "John Michael")
        self.assertEqual(last, "Doe")

    def test_split_author_parts_comma_multiple_names(self):
        """Test splitting author name with comma and multiple names"""
        first, last = split_author_parts("Doe, John Michael")
        self.assertEqual(first, "John Michael")
        self.assertEqual(last, "Doe")

    def test_split_author_parts_single_name(self):
        """Test splitting single name"""
        first, last = split_author_parts("Cher")
        self.assertEqual(first, "Cher")
        self.assertEqual(last, "")

    def test_split_author_parts_empty_string(self):
        """Test splitting empty string"""
        first, last = split_author_parts("")
        self.assertEqual(first, "")
        self.assertEqual(last, "")

    def test_split_author_parts_whitespace_handling(self):
        """Test splitting with extra whitespace"""
        first, last = split_author_parts("  John   Doe  ")
        self.assertEqual(first, "John")
        self.assertEqual(last, "Doe")

    def test_attach_authors_single_author(self):
        """Test attaching single author to book"""
        raw_names = ["John Doe"]
        attach_authors(self.book, raw_names, self.source, confidence=0.9)

        # Check author was created
        author = Author.objects.get(first_name="John", last_name="Doe")
        self.assertEqual(author.name, "John Doe")

        # Check BookAuthor relationship
        book_author = BookAuthor.objects.get(book=self.book, author=author)
        self.assertEqual(book_author.confidence, 0.9)
        self.assertTrue(book_author.is_main_author)
        self.assertEqual(book_author.source, self.source)

    def test_attach_authors_multiple_authors(self):
        """Test attaching multiple authors to book"""
        raw_names = ["John Doe", "Jane Smith", "Bob Wilson"]
        attach_authors(self.book, raw_names, self.source, confidence=0.8)

        # Check all authors were created
        authors = Author.objects.filter(
            name__in=["John Doe", "Jane Smith", "Bob Wilson"]
        )
        self.assertEqual(authors.count(), 3)

        # Check BookAuthor relationships
        book_authors = BookAuthor.objects.filter(book=self.book)
        self.assertEqual(book_authors.count(), 3)

        # Check main author designation
        main_authors = book_authors.filter(is_main_author=True)
        self.assertEqual(main_authors.count(), 1)
        self.assertEqual(main_authors.first().author.name, "John Doe")

    def test_attach_authors_limit_to_three(self):
        """Test that only first three authors are attached"""
        raw_names = ["Author One", "Author Two", "Author Three", "Author Four", "Author Five"]
        attach_authors(self.book, raw_names, self.source, confidence=0.8)

        # Should only create 3 authors
        book_authors = BookAuthor.objects.filter(book=self.book)
        self.assertEqual(book_authors.count(), 3)

        # Check the correct authors were created
        author_names = [ba.author.name for ba in book_authors]
        expected_names = ["Author One", "Author Two", "Author Three"]
        self.assertEqual(sorted(author_names), sorted(expected_names))

    def test_attach_authors_existing_author_reuse(self):
        """Test that existing authors are reused"""
        # Create an existing author
        existing_author = Author.objects.create(
            name="John Doe",
            first_name="John",
            last_name="Doe"
        )
        existing_id = existing_author.id

        raw_names = ["John Doe"]
        attach_authors(self.book, raw_names, self.source, confidence=0.8)

        # Should reuse existing author, not create new one
        authors = Author.objects.filter(name="John Doe")
        self.assertEqual(authors.count(), 1)
        self.assertEqual(authors.first().id, existing_id)

    def test_attach_authors_normalized_name_matching(self):
        """Test author matching by normalized name"""
        # Create author with different formatting
        Author.objects.create(
            name="J. R. R. Tolkien",
            first_name="John Ronald Reuel",
            last_name="Tolkien"
        )

        # Try to attach similar but differently formatted name
        raw_names = ["John Ronald Reuel Tolkien"]
        attach_authors(self.book, raw_names, self.source, confidence=0.8)

        # Should match existing author by normalized name
        authors = Author.objects.filter(last_name="Tolkien")
        self.assertEqual(authors.count(), 1)

    def test_attach_authors_case_insensitive_matching(self):
        """Test case insensitive author matching"""
        # Create author
        Author.objects.create(
            name="john doe",
            first_name="john",
            last_name="doe"
        )

        # Try to attach with different case
        raw_names = ["John Doe"]
        attach_authors(self.book, raw_names, self.source, confidence=0.8)

        # Should match existing author
        authors = Author.objects.filter(first_name__iexact="john", last_name__iexact="doe")
        self.assertEqual(authors.count(), 1)

    def test_attach_authors_empty_list(self):
        """Test attaching empty author list"""
        raw_names = []
        attach_authors(self.book, raw_names, self.source, confidence=0.8)

        # Should not create any authors
        book_authors = BookAuthor.objects.filter(book=self.book)
        self.assertEqual(book_authors.count(), 0)

    def test_attach_authors_whitespace_stripping(self):
        """Test that whitespace is properly stripped from author names"""
        raw_names = ["  John Doe  ", " Jane Smith "]
        attach_authors(self.book, raw_names, self.source, confidence=0.8)

        # Check authors were created with stripped names via BookAuthor relationships
        authors = Author.objects.filter(book_relationships__book=self.book)
        author_names = [author.name for author in authors]
        self.assertIn("John Doe", author_names)
        self.assertIn("Jane Smith", author_names)

    def test_attach_authors_duplicate_in_list(self):
        """Test handling duplicate authors in the same list"""
        raw_names = ["John Doe", "John Doe", "Jane Smith"]
        attach_authors(self.book, raw_names, self.source, confidence=0.8)

        # Should have created relationships for all entries (even duplicates)
        # but with unique authors
        authors = Author.objects.filter(book_relationships__book=self.book)
        self.assertEqual(authors.count(), 2)  # John Doe and Jane Smith
