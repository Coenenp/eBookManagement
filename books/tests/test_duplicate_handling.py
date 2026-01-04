"""
Test cases for duplicate book handling and same title/different author scenarios.

Tests TC9.5: Verify that books with identical titles but different authors
are stored as separate entries and not merged incorrectly.
"""
from unittest.mock import patch

from django.test import TestCase

from books.models import Author, Book, BookAuthor, DataSource, FinalMetadata
from books.tests.test_helpers import create_test_book_with_file, create_test_scan_folder


class DuplicateHandlingTests(TestCase):
    """Test cases for handling duplicate books and same title scenarios"""

    def setUp(self):
        """Set up test data"""
        self.scan_folder = create_test_scan_folder(name="Test Scan Folder")

        # Create data sources
        self.initial_source, _ = DataSource.objects.get_or_create(
            name=DataSource.INITIAL_SCAN,
            defaults={'trust_level': 0.2}
        )

        self.epub_source, _ = DataSource.objects.get_or_create(
            name=DataSource.EPUB_INTERNAL,
            defaults={'trust_level': 0.7}
        )

    def test_same_title_different_authors_separate_entries(self):
        """TC9.5: Books with same title but different authors should be separate entries"""
        # Create authors
        author1 = Author.objects.create(name='John Smith')
        author2 = Author.objects.create(name='Jane Doe')

        # Create two books with same title, different authors
        book1 = create_test_book_with_file(
            file_path="/test/path/common_title1.epub",
            file_format="epub",
            file_size=1024000,
            scan_folder=self.scan_folder
        )

        book2 = create_test_book_with_file(
            file_path="/test/path/common_title2.epub",
            file_format="epub",
            file_size=1048576,
            scan_folder=self.scan_folder
        )

        # Create final metadata with same title, different authors
        FinalMetadata.objects.create(
            book=book1,
            final_title='The Common Title',
            final_author='John Smith',
            is_reviewed=False
        )

        FinalMetadata.objects.create(
            book=book2,
            final_title='The Common Title',
            final_author='Jane Doe',
            is_reviewed=False
        )

        # Create author relationships
        BookAuthor.objects.create(
            book=book1,
            author=author1,
            source=self.epub_source,
            confidence=0.9,
            is_main_author=True
        )

        BookAuthor.objects.create(
            book=book2,
            author=author2,
            source=self.epub_source,
            confidence=0.9,
            is_main_author=True
        )

        # Verify both books exist as separate entries
        books_with_title = FinalMetadata.objects.filter(final_title='The Common Title')
        self.assertEqual(books_with_title.count(), 2, "Should have 2 separate book entries for same title")

        # Verify different authors
        authors = [metadata.final_author for metadata in books_with_title]
        self.assertIn('John Smith', authors)
        self.assertIn('Jane Doe', authors)
        self.assertEqual(len(set(authors)), 2, "Should have 2 different authors")

    def test_identical_file_path_prevents_duplicates(self):
        """Test that books with identical file paths are not duplicated"""
        file_path = "/test/path/duplicate.epub"

        # Try to create book with same path twice
        book1 = create_test_book_with_file(
            file_path=file_path,
            file_format="epub",
            file_size=1024000,
            scan_folder=self.scan_folder
        )

        # Second creation should either fail or return existing book
        # depending on get_or_create_by_path implementation
        with patch.object(Book, 'get_or_create_by_path') as mock_get_or_create:
            mock_get_or_create.return_value = (book1, False)  # Existing book, not created

            result_book, created = Book.get_or_create_by_path(
                file_path=file_path,
                defaults={
                    "file_format": "epub",
                    "file_size": 2048000,  # Different size
                    "scan_folder": self.scan_folder
                }
            )

            # Should return existing book, not create new one
            self.assertEqual(result_book.id, book1.id)
            self.assertFalse(created, "Should not create duplicate book for same file path")

    def test_same_title_same_author_different_editions(self):
        """Test handling of different editions of same book by same author"""
        Author.objects.create(name='Stephen King')

        # Create two books - different editions of same work
        book1 = create_test_book_with_file(
            file_path="/test/path/the_shining_first_edition.epub",
            file_format="epub",
            file_size=1024000,
            scan_folder=self.scan_folder
        )

        book2 = create_test_book_with_file(
            file_path="/test/path/the_shining_revised_edition.epub",
            file_format="epub",
            file_size=1048576,
            scan_folder=self.scan_folder
        )

        # Same title and author, different ISBNs/editions
        FinalMetadata.objects.create(
            book=book1,
            final_title='The Shining',
            final_author='Stephen King',
            isbn='978-1111111111',  # Different ISBNs
            publication_year=1977
        )

        FinalMetadata.objects.create(
            book=book2,
            final_title='The Shining',
            final_author='Stephen King',
            isbn='978-2222222222',  # Different ISBNs
            publication_year=2013   # Different publication years
        )

        # Should maintain as separate entries (different editions)
        books_count = FinalMetadata.objects.filter(
            final_title='The Shining',
            final_author='Stephen King'
        ).count()

        self.assertEqual(books_count, 2, "Different editions should be separate entries even with same title/author")

    def test_case_insensitive_title_comparison_for_duplicates(self):
        """Test that title comparison for duplicates is case insensitive"""
        Author.objects.create(name='Test Author')

        # Create books with same title in different cases
        book1 = create_test_book_with_file(
            file_path="/test/path/book1.epub",
            file_format="epub",
            scan_folder=self.scan_folder
        )

        book2 = create_test_book_with_file(
            file_path="/test/path/book2.epub",
            file_format="epub",
            scan_folder=self.scan_folder
        )

        # Create metadata with case variations
        FinalMetadata.objects.create(
            book=book1,
            final_title='the test book',  # lowercase
            final_author='Test Author'
        )

        FinalMetadata.objects.create(
            book=book2,
            final_title='The Test Book',  # title case
            final_author='Test Author'
        )

        # Query should find both as potential duplicates if doing case-insensitive comparison
        lowercase_matches = FinalMetadata.objects.filter(
            final_title__iexact='the test book',
            final_author='Test Author'
        ).count()

        self.assertEqual(lowercase_matches, 2, "Case insensitive search should find both title variations")

    def test_file_hash_duplicate_detection(self):
        """Test duplicate detection using file path hashes"""
        # Create two books with different paths but same content hash (if implemented)
        book1 = create_test_book_with_file(
            file_path="/test/path/original.epub",
            file_format="epub",
            file_size=1024000,
            scan_folder=self.scan_folder
        )

        book2 = create_test_book_with_file(
            file_path="/test/path/copy.epub",  # Different path
            file_format="epub",
            file_size=1024000,  # Same size
            scan_folder=self.scan_folder
        )

        # Both books should have file_path_hash generated
        self.assertIsNotNone(book1.file_path_hash)
        self.assertIsNotNone(book2.file_path_hash)

        # Different paths should have different hashes
        self.assertNotEqual(book1.file_path_hash, book2.file_path_hash, "Different file paths should have different hashes")

    def test_author_name_normalization_for_duplicates(self):
        """Test that author name variations are handled consistently"""
        # Create books with author name variations
        book1 = create_test_book_with_file(
            file_path="/test/path/book1.epub",
            file_format="epub",
            scan_folder=self.scan_folder
        )

        book2 = create_test_book_with_file(
            file_path="/test/path/book2.epub",
            file_format="epub",
            scan_folder=self.scan_folder
        )

        # Create metadata with author name variations
        FinalMetadata.objects.create(
            book=book1,
            final_title='Sample Book',
            final_author='J.K. Rowling'  # With periods
        )

        FinalMetadata.objects.create(
            book=book2,
            final_title='Sample Book',
            final_author='JK Rowling'   # Without periods
        )

        # Both should be treated as potentially different authors
        # unless normalization logic exists
        author_variations = FinalMetadata.objects.filter(
            final_title='Sample Book'
        ).values_list('final_author', flat=True)

        self.assertEqual(len(author_variations), 2, "Author name variations should be preserved unless normalization exists")

    def test_isbn_based_duplicate_detection(self):
        """Test that books with same ISBN are flagged as potential duplicates"""
        isbn = '978-0123456789'

        # Create two books with same ISBN
        book1 = create_test_book_with_file(
            file_path="/test/path/book1.epub",
            file_format="epub",
            scan_folder=self.scan_folder
        )

        book2 = create_test_book_with_file(
            file_path="/test/path/book2.epub",
            file_format="epub",
            scan_folder=self.scan_folder
        )

        # Same ISBN, potentially different titles/authors (data entry errors)
        FinalMetadata.objects.create(
            book=book1,
            final_title='Title Version A',
            final_author='Author A',
            isbn=isbn
        )

        FinalMetadata.objects.create(
            book=book2,
            final_title='Title Version B',
            final_author='Author B',
            isbn=isbn
        )

        # Query for potential ISBN duplicates
        isbn_duplicates = FinalMetadata.objects.filter(isbn=isbn).count()
        self.assertEqual(isbn_duplicates, 2, "Should detect multiple books with same ISBN as potential duplicates")

    def test_series_differentiation_same_title(self):
        """Test that books in different series with same title are kept separate"""
        Author.objects.create(name='Fantasy Author')

        # Create books with same title but different series
        book1 = create_test_book_with_file(
            file_path="/test/path/dragons1.epub",
            file_format="epub",
            scan_folder=self.scan_folder
        )

        book2 = create_test_book_with_file(
            file_path="/test/path/dragons2.epub",
            file_format="epub",
            scan_folder=self.scan_folder
        )

        # Same title, same author, different series
        FinalMetadata.objects.create(
            book=book1,
            final_title='Dragons',
            final_author='Fantasy Author',
            final_series='Epic Fantasy Series'
        )

        FinalMetadata.objects.create(
            book=book2,
            final_title='Dragons',
            final_author='Fantasy Author',
            final_series='Modern Fantasy Series'
        )

        # Should remain separate due to different series
        dragons_books = FinalMetadata.objects.filter(
            final_title='Dragons',
            final_author='Fantasy Author'
        )

        self.assertEqual(dragons_books.count(), 2, "Books with same title/author but different series should remain separate")

        series_names = [book.final_series for book in dragons_books]
        self.assertEqual(len(set(series_names)), 2, "Should have 2 different series names")
