"""
Test configuration and utilities for Ebook & Series Renamer
Provides test discovery, configuration, and utility functions for the renaming test suite.
"""

import os
import sys
from pathlib import Path

# Add the project root to Python path for imports
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Test configuration
TEST_CONFIG = {
    'use_temp_media': True,
    'cleanup_after_tests': True,
    'mock_file_operations': True,
    'test_data_size_limit': 1024 * 1024,  # 1MB limit for test files
}


# Test utilities
class RenamingTestUtils:
    """Utility functions for renaming tests"""

    @staticmethod
    def create_test_file_structure(base_dir, structure):
        """
        Create a test file structure from a dictionary

        Args:
            base_dir: Base directory path
            structure: Dictionary defining file structure
                e.g., {'folder1': {'file1.txt': None, 'folder2': {'file2.txt': None}}}
        """
        base_path = Path(base_dir)

        for name, content in structure.items():
            path = base_path / name

            if content is None:
                # It's a file
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()
            elif isinstance(content, dict):
                # It's a directory
                path.mkdir(parents=True, exist_ok=True)
                RenamingTestUtils.create_test_file_structure(path, content)
            else:
                # It's a file with content
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(str(content))

    @staticmethod
    def assert_pattern_generates_valid_path(test_case, pattern, book, expected_parts=None):
        """
        Assert that a pattern generates a valid path

        Args:
            test_case: TestCase instance
            pattern: Pattern string to test
            book: Book object to process
            expected_parts: List of expected path components (optional)
        """
        from books.utils.renaming_engine import RenamingEngine

        engine = RenamingEngine()
        result = engine.process_pattern(pattern, book)

        # Basic validations
        test_case.assertIsInstance(result, str)
        test_case.assertGreater(len(result), 0)

        # Path should not contain invalid characters
        invalid_chars = ['<', '>', ':', '"', '|', '?', '*']
        for char in invalid_chars:
            test_case.assertNotIn(char, result)

        # Should not have double slashes or start/end with slash
        test_case.assertNotIn('//', result)
        test_case.assertFalse(result.startswith('/'))
        test_case.assertFalse(result.endswith('/'))

        # Check expected parts if provided
        if expected_parts:
            path_parts = Path(result).parts
            for expected_part in expected_parts:
                test_case.assertIn(expected_part, path_parts)

    @staticmethod
    def create_test_book_with_metadata(title, **kwargs):
        """
        Create a test book with specified metadata

        Args:
            title: Book title
            **kwargs: Additional book fields

        Returns:
            Book instance
        """
        from books.models import Book, Format, BookTitle

        # Get or create default format
        format_obj, _ = Format.objects.get_or_create(
            name="EPUB",
            defaults={'extension': '.epub'}
        )

        defaults = {
            'file_path': f'/test/{title}.epub',
            'file_size': 1024000,
            'format': format_obj,
        }
        defaults.update(kwargs)

        book = Book.objects.create(**defaults)
        
        # Create BookTitle relationship
        BookTitle.objects.create(book=book, title=title)
        
        return book

    @staticmethod
    def validate_companion_files(test_case, source_dir, target_dir, base_name):
        """
        Validate that companion files were moved correctly

        Args:
            test_case: TestCase instance
            source_dir: Source directory path
            target_dir: Target directory path
            base_name: Base filename without extension
        """
        companion_extensions = ['.jpg', '.jpeg', '.png', '.opf', '.nfo', '.json']

        for ext in companion_extensions:
            source_file = Path(source_dir) / f"{base_name}{ext}"
            target_file = Path(target_dir) / f"{base_name}{ext}"

            if source_file.exists():
                test_case.assertTrue(target_file.exists(), f"Companion file {base_name}{ext} not moved to target")


# Test data generators
class TestDataGenerator:
    """Generate test data for comprehensive testing"""

    @staticmethod
    def generate_test_books(count=10):
        """Generate a collection of test books with various metadata combinations"""
        from books.models import Book, Author, Series, Format, Language, Category

        # Ensure required objects exist
        format_obj, _ = Format.objects.get_or_create(
            name="EPUB", defaults={'extension': '.epub'}
        )

        language_obj, _ = Language.objects.get_or_create(
            name="English", defaults={'code': 'en'}
        )

        category_obj, _ = Category.objects.get_or_create(
            name="Fiction"
        )

        authors = []
        for i in range(5):
            author, _ = Author.objects.get_or_create(
                name=f"Test Author {i}",
                defaults={'sort_name': f"Author {i}, Test"}
            )
            authors.append(author)

        series = []
        for i in range(3):
            series_obj, _ = Series.objects.get_or_create(
                name=f"Test Series {i}"
            )
            series.append(series_obj)

        books = []
        for i in range(count):
            book = Book.objects.create(
                title=f"Test Book {i}",
                file_path=f"/test/book_{i}.epub",
                file_size=1024000 + (i * 1000),
                format=format_obj,
                language=language_obj,
                category=category_obj,
                publication_year=2000 + i
            )

            # Add random authors and series
            book.authors.add(authors[i % len(authors)])
            if i % 3 == 0:  # Some books have series
                book.series.add(series[i % len(series)])
                book.series_number = (i // 3) + 1
                book.save()

            books.append(book)

        return books

    @staticmethod
    def generate_companion_files(book_path):
        """Generate typical companion files for a book"""
        book_file = Path(book_path)
        base_name = book_file.stem
        base_dir = book_file.parent

        companions = []

        # Cover files
        for ext in ['.jpg', '.jpeg', '.png']:
            cover_file = base_dir / f"{base_name}{ext}"
            cover_file.touch()
            companions.append(cover_file)

        # Metadata files
        for ext in ['.opf', '.nfo']:
            meta_file = base_dir / f"{base_name}{ext}"
            meta_file.touch()
            companions.append(meta_file)

        # Generic files
        (base_dir / "cover.jpg").touch()
        (base_dir / "metadata.opf").touch()
        companions.extend([
            base_dir / "cover.jpg",
            base_dir / "metadata.opf"
        ])

        return companions


# Pattern test cases
PATTERN_TEST_CASES = [
    # Basic patterns
    {
        'name': 'simple_title',
        'pattern': '${title}.${ext}',
        'expected_tokens': ['title', 'ext'],
        'should_work_with_minimal': True
    },

    {
        'name': 'author_title',
        'pattern': '${author_sort} - ${title}.${ext}',
        'expected_tokens': ['author_sort', 'title', 'ext'],
        'should_work_with_minimal': False  # Requires author
    },

    {
        'name': 'series_pattern',
        'pattern': '${series_name} #${series_number} - ${title}.${ext}',
        'expected_tokens': ['series_name', 'series_number', 'title', 'ext'],
        'should_work_with_minimal': True  # Should gracefully omit series
    },

    # Folder patterns
    {
        'name': 'library_structure',
        'pattern': 'Library/${format}/${language}/${author_sort}/${title}.${ext}',
        'expected_tokens': ['format', 'language', 'author_sort', 'title', 'ext'],
        'should_work_with_minimal': False
    },

    # Complex patterns
    {
        'name': 'full_metadata',
        'pattern': '${category}/${language}/${author_sort}/${series_name}/${title} (${year}).${ext}',
        'expected_tokens': ['category', 'language', 'author_sort', 'series_name', 'title', 'year', 'ext'],
        'should_work_with_minimal': True
    }
]

# Test scenarios for different book types
BOOK_TEST_SCENARIOS = [
    {
        'name': 'complete_metadata',
        'has_author': True,
        'has_series': True,
        'has_year': True,
        'has_category': True,
        'has_language': True,
        'description': 'Book with complete metadata'
    },

    {
        'name': 'minimal_metadata',
        'has_author': False,
        'has_series': False,
        'has_year': False,
        'has_category': False,
        'has_language': False,
        'description': 'Book with only title and format'
    },

    {
        'name': 'partial_metadata',
        'has_author': True,
        'has_series': False,
        'has_year': True,
        'has_category': False,
        'has_language': True,
        'description': 'Book with partial metadata'
    },

    {
        'name': 'series_book',
        'has_author': True,
        'has_series': True,
        'has_year': True,
        'has_category': True,
        'has_language': True,
        'series_number': 5,
        'description': 'Book that is part of a numbered series'
    }
]


def discover_renaming_tests():
    """Discover all renaming-related test modules"""
    test_modules = [
        'books.tests.test_renaming_engine',
        'books.tests.test_batch_renamer',
        'books.tests.test_renaming_views',
        'books.tests.test_renaming_comprehensive'
    ]

    return test_modules


def run_renaming_test_suite():
    """Run the complete renaming test suite"""
    import django
    from django.conf import settings
    from django.test.utils import get_runner

    # Configure Django settings if not already configured
    if not settings.configured:
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ebook_manager.settings')
        django.setup()

    # Get test runner
    TestRunner = get_runner(settings)
    test_runner = TestRunner(verbosity=2, interactive=False)

    # Discover and run tests
    test_modules = discover_renaming_tests()
    failures = test_runner.run_tests(test_modules)

    return failures == 0  # True if all tests passed


if __name__ == '__main__':
    """Run tests when executed directly"""
    success = run_renaming_test_suite()
    sys.exit(0 if success else 1)
