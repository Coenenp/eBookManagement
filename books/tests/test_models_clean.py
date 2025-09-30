"""
Test cases for Book models
"""
from django.test import TestCase
from books.models import (
    Book, FinalMetadata, ScanFolder, BookCover, DataSource,
    BookMetadata, Author
)


class BookModelTests(TestCase):
    """Test cases for Book model"""

    def setUp(self):
        """Set up test data"""
        self.scan_folder = ScanFolder.objects.create(
            path="/test/scan/folder",
            name="Test Scan Folder"
        )

        self.book = Book.objects.create(
            file_path="/test/path/book.epub",
            file_format="epub",
            file_size=1024000,
            scan_folder=self.scan_folder
        )

    def test_book_creation(self):
        """Test book creation"""
        self.assertEqual(self.book.file_path, "/test/path/book.epub")
        self.assertEqual(self.book.file_format, "epub")
        self.assertEqual(self.book.file_size, 1024000)
        self.assertEqual(self.book.scan_folder, self.scan_folder)

    def test_book_filename_property(self):
        """Test book filename property"""
        self.assertEqual(self.book.filename, "book.epub")

    def test_book_str_representation(self):
        """Test book string representation"""
        self.assertEqual(str(self.book), "book.epub")


class FinalMetadataModelTests(TestCase):
    """Test cases for FinalMetadata model"""

    def setUp(self):
        """Set up test data"""
        self.scan_folder = ScanFolder.objects.create(
            path="/test/scan/folder",
            name="Test Scan Folder"
        )

        self.book = Book.objects.create(
            file_path="/test/path/book.epub",
            file_format="epub",
            file_size=1024000,
            scan_folder=self.scan_folder
        )

        self.final_metadata = FinalMetadata.objects.create(
            book=self.book,
            final_title="Final Test Book",
            final_author="Test Author",
            final_series="Test Series",
            final_publisher="Test Publisher",
            publication_year=2023,
            isbn="978-0123456789",
            language="en",
            description="Test description",
            is_reviewed=False
        )

    def test_final_metadata_creation(self):
        """Test final metadata creation"""
        self.assertEqual(self.final_metadata.final_title, "Final Test Book")
        self.assertEqual(self.final_metadata.final_author, "Test Author")
        self.assertEqual(self.final_metadata.publication_year, 2023)
        self.assertFalse(self.final_metadata.is_reviewed)

    def test_final_metadata_str_representation(self):
        """Test final metadata string representation"""
        expected = "Final Test Book by Test Author"
        self.assertEqual(str(self.final_metadata), expected)

    def test_manual_update_flag(self):
        """Test manual update flag functionality"""
        # Manual updates should be preserved
        self.final_metadata._manual_update = True
        self.final_metadata.final_title = "Manually Updated Title"
        self.final_metadata.save()

        self.final_metadata.refresh_from_db()
        self.assertEqual(self.final_metadata.final_title, "Manually Updated Title")


class BookCoverModelTests(TestCase):
    """Test cases for BookCover model"""

    def setUp(self):
        """Set up test data"""
        self.scan_folder = ScanFolder.objects.create(
            path="/test/scan/folder",
            name="Test Scan Folder"
        )

        self.book = Book.objects.create(
            file_path="/test/path/book.epub",
            file_format="epub",
            file_size=1024000,
            scan_folder=self.scan_folder
        )

        # Get or create DataSource for BookCover
        self.data_source, _ = DataSource.objects.get_or_create(
            name=DataSource.MANUAL,
            defaults={'trust_level': 0.9}
        )

        self.book_cover = BookCover.objects.create(
            book=self.book,
            cover_path="/test/covers/book_cover.jpg",
            source=self.data_source,
            confidence=0.9,
            width=400,
            height=600
        )

    def test_book_cover_creation(self):
        """Test book cover creation"""
        self.assertEqual(self.book_cover.book, self.book)
        self.assertEqual(self.book_cover.cover_path, "/test/covers/book_cover.jpg")
        self.assertEqual(self.book_cover.height, 600)
        self.assertEqual(self.book_cover.width, 400)
        self.assertEqual(self.book_cover.source, self.data_source)

    def test_book_cover_str_representation(self):
        """Test book cover string representation"""
        expected = f"Cover for {self.book.filename}"
        self.assertEqual(str(self.book_cover), expected)


class DataSourceModelTests(TestCase):
    """Test cases for DataSource model"""

    def setUp(self):
        """Set up test data"""
        self.data_source = DataSource.objects.create(
            name="Test Source",
            priority=1,
            is_active=True
        )

    def test_data_source_creation(self):
        """Test data source creation"""
        self.assertEqual(self.data_source.name, "Test Source")
        self.assertEqual(self.data_source.priority, 1)
        self.assertTrue(self.data_source.is_active)

    def test_data_source_str_representation(self):
        """Test data source string representation"""
        self.assertEqual(str(self.data_source), "Test Source")


class BookMetadataModelTests(TestCase):
    """Test cases for BookMetadata model"""

    def setUp(self):
        """Set up test data"""
        self.scan_folder = ScanFolder.objects.create(
            path="/test/scan/folder",
            name="Test Scan Folder"
        )

        self.book = Book.objects.create(
            file_path="/test/path/book.epub",
            file_format="epub",
            file_size=1024000,
            scan_folder=self.scan_folder
        )

        self.data_source = DataSource.objects.create(
            name="Test Source",
            priority=1,
            is_active=True
        )

        self.book_metadata = BookMetadata.objects.create(
            book=self.book,
            source=self.data_source,
            title="Test Book",
            author="Test Author",
            confidence_score=85.0,
            is_primary=True
        )

    def test_book_metadata_creation(self):
        """Test book metadata creation"""
        self.assertEqual(self.book_metadata.book, self.book)
        self.assertEqual(self.book_metadata.source, self.data_source)
        self.assertEqual(self.book_metadata.title, "Test Book")
        self.assertEqual(self.book_metadata.author, "Test Author")
        self.assertEqual(self.book_metadata.confidence_score, 85.0)
        self.assertTrue(self.book_metadata.is_primary)

    def test_book_metadata_str_representation(self):
        """Test book metadata string representation"""
        expected = "Test Book by Test Author (Test Source)"
        self.assertEqual(str(self.book_metadata), expected)


class AuthorModelTests(TestCase):
    """Test cases for Author model"""

    def setUp(self):
        """Set up test data"""
        self.author = Author.objects.create(
            name="Test Author",
            normalized_name="test_author"
        )

    def test_author_creation(self):
        """Test author creation"""
        self.assertEqual(self.author.name, "Test Author")
        self.assertEqual(self.author.normalized_name, "test_author")

    def test_author_str_representation(self):
        """Test author string representation"""
        self.assertEqual(str(self.author), "Test Author")


class ScanFolderModelTests(TestCase):
    """Test cases for ScanFolder model"""

    def setUp(self):
        """Set up test data"""
        self.scan_folder = ScanFolder.objects.create(
            path="/test/scan/folder",
            name="Test Scan Folder",
            is_active=True
        )

    def test_scan_folder_creation(self):
        """Test scan folder creation"""
        self.assertEqual(self.scan_folder.path, "/test/scan/folder")
        self.assertEqual(self.scan_folder.name, "Test Scan Folder")
        self.assertTrue(self.scan_folder.is_active)

    def test_scan_folder_str_representation(self):
        """Test scan folder string representation"""
        self.assertEqual(str(self.scan_folder), "Test Scan Folder")
