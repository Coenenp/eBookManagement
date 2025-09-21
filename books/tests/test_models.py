"""
Test cases for Book models
"""
from django.test import TestCase
from books.models import (
    Book, FinalMetadata, ScanFolder, BookCover, DataSource,
    BookMetadata, Author, Publisher, Genre, Series,
    BookAuthor, BookTitle, BookSeries, BookGenre, BookPublisher
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
            file_path="/test/scan/folder/subfolder/book.epub",
            file_format="epub",
            file_size=1024000,
            scan_folder=self.scan_folder
        )

    def test_book_creation(self):
        """Test book creation"""
        self.assertEqual(self.book.file_path, "/test/scan/folder/subfolder/book.epub")
        self.assertEqual(self.book.file_format, "epub")
        self.assertEqual(self.book.file_size, 1024000)
        self.assertEqual(self.book.scan_folder, self.scan_folder)

    def test_book_filename_property(self):
        """Test book filename property"""
        self.assertEqual(self.book.filename, "book.epub")

    def test_book_str_representation(self):
        """Test book string representation"""
        self.assertEqual(str(self.book), "book.epub")

    def test_book_relative_path_property(self):
        """Test book relative path property"""
        # Now the file_path starts with scan_folder path
        self.assertEqual(self.book.relative_path, "subfolder")

    def test_book_final_metadata_property(self):
        """Test book final_metadata property when no metadata exists"""
        self.assertIsNone(self.book.final_metadata)

    def test_book_placeholder_str(self):
        """Test book string representation for placeholders"""
        placeholder_book = Book.objects.create(
            file_path="/test/placeholder.epub",
            file_format="placeholder",
            scan_folder=self.scan_folder,
            is_placeholder=True
        )
        self.assertIn("Placeholder:", str(placeholder_book))


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
            is_reviewed=True  # Set to True to prevent auto-update
        )

    def test_final_metadata_creation(self):
        """Test final metadata creation"""
        self.assertEqual(self.final_metadata.final_title, "Final Test Book")
        self.assertEqual(self.final_metadata.final_author, "Test Author")
        self.assertEqual(self.final_metadata.publication_year, 2023)
        self.assertTrue(self.final_metadata.is_reviewed)

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

    def test_calculate_overall_confidence(self):
        """Test overall confidence calculation"""
        self.final_metadata.final_title_confidence = 0.8
        self.final_metadata.final_author_confidence = 0.9
        self.final_metadata.final_series_confidence = 0.7
        self.final_metadata.final_cover_confidence = 0.6

        confidence = self.final_metadata.calculate_overall_confidence()
        self.assertGreater(confidence, 0)
        self.assertEqual(self.final_metadata.overall_confidence, confidence)

    def test_calculate_completeness_score(self):
        """Test completeness score calculation"""
        score = self.final_metadata.calculate_completeness_score()
        self.assertGreater(score, 0)
        self.assertEqual(self.final_metadata.completeness_score, score)

    def test_final_series_number_null_handling(self):
        """Test that final_series_number field handles NULL values correctly"""
        # Create a separate book for this test to avoid unique constraint conflicts
        book_null = Book.objects.create(
            file_path="/test/path/book_null.epub",
            file_format="epub",
            file_size=1024000,
            scan_folder=self.scan_folder
        )

        # Test with None value (should not raise IntegrityError)
        metadata_null = FinalMetadata.objects.create(
            book=book_null,
            final_title="Test Book Null",
            final_author="Test Author",
            final_series="Test Series",
            final_series_number=None,
            is_reviewed=True
        )
        self.assertIsNone(metadata_null.final_series_number)

        # Test with empty string
        metadata_empty = FinalMetadata.objects.create(
            book=Book.objects.create(
                file_path="/test/path/book2.epub",
                file_format="epub",
                file_size=1024000,
                scan_folder=self.scan_folder
            ),
            final_title="Test Book Empty",
            final_author="Test Author",
            final_series="Test Series",
            final_series_number="",
            is_reviewed=True
        )
        self.assertEqual(metadata_empty.final_series_number, "")

    def test_update_final_series_with_none_values(self):
        """Test update_final_series method handles None values correctly"""
        # Test updating from None to actual values
        self.final_metadata.final_series = None
        self.final_metadata.final_series_number = None
        self.final_metadata.save()

        try:
            # Method updates from book's series_info, so it should not crash
            self.final_metadata.update_final_series()
            self.final_metadata.save()
            self.final_metadata.refresh_from_db()
            # Should default to empty string when no series data exists
            self.assertEqual(self.final_metadata.final_series, '')
            self.assertEqual(self.final_metadata.final_series_number, '')
        except Exception as e:
            self.fail(f"update_final_series failed with None values: {e}")

        # Test that the method handles null database values without crashing
        self.final_metadata.final_series = None
        self.final_metadata.final_series_number = None
        self.final_metadata.save()
        try:
            self.final_metadata.update_final_series()
            # Should not crash even with null values in database
        except Exception as e:
            self.fail(f"update_final_series failed when database had None values: {e}")

    def test_final_metadata_null_series_number(self):
        """Test that FinalMetadata can handle null series numbers"""
        # Create a new book for this test
        book2 = Book.objects.create(
            file_path="/test/path/book2.epub",
            file_format="epub",
            file_size=1024000,
            scan_folder=self.scan_folder
        )

        # Test creating with null series number
        final_metadata = FinalMetadata.objects.create(
            book=book2,
            final_title="Test Book",
            final_author="Test Author",
            final_series="Test Series",
            final_series_number=None,  # Should not raise error
            is_reviewed=True
        )

        self.assertIsNone(final_metadata.final_series_number)
        final_metadata.refresh_from_db()
        self.assertIsNone(final_metadata.final_series_number)

    def test_final_metadata_empty_series_number(self):
        """Test that FinalMetadata can handle empty string series numbers"""
        # Create a new book for this test
        book3 = Book.objects.create(
            file_path="/test/path/book3.epub",
            file_format="epub",
            file_size=1024000,
            scan_folder=self.scan_folder
        )

        final_metadata = FinalMetadata.objects.create(
            book=book3,
            final_title="Test Book",
            final_author="Test Author",
            final_series="Test Series",
            final_series_number="",  # Empty string
            is_reviewed=True
        )

        self.assertEqual(final_metadata.final_series_number, "")
        final_metadata.refresh_from_db()
        self.assertEqual(final_metadata.final_series_number, "")

    def test_final_metadata_update_series_with_null(self):
        """Test updating final_series_number to None doesn't cause errors"""
        # Create a new book for this test
        book4 = Book.objects.create(
            file_path="/test/path/book4.epub",
            file_format="epub",
            file_size=1024000,
            scan_folder=self.scan_folder
        )

        final_metadata = FinalMetadata.objects.create(
            book=book4,
            final_title="Test Book",
            final_author="Test Author",
            final_series="Test Series",
            final_series_number="1",
            is_reviewed=True
        )

        # Update to None should work
        final_metadata.final_series_number = None
        final_metadata.save()
        final_metadata.refresh_from_db()
        self.assertIsNone(final_metadata.final_series_number)


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

        self.data_source, created = DataSource.objects.get_or_create(
            name=DataSource.FILENAME,
            defaults={'trust_level': 0.7}
        )

        self.book_cover = BookCover.objects.create(
            book=self.book,
            cover_path="/test/covers/book_cover.jpg",
            source=self.data_source,
            confidence=0.85,
            width=600,
            height=800
        )

    def test_book_cover_creation(self):
        """Test book cover creation"""
        self.assertEqual(self.book_cover.book, self.book)
        self.assertEqual(self.book_cover.cover_path, "/test/covers/book_cover.jpg")
        self.assertEqual(self.book_cover.source, self.data_source)
        self.assertEqual(self.book_cover.confidence, 0.85)
        self.assertEqual(self.book_cover.width, 600)
        self.assertEqual(self.book_cover.height, 800)

    def test_book_cover_str_representation(self):
        """Test book cover string representation"""
        expected = f"Cover for {self.book.filename} from {self.data_source} ({self.book_cover.confidence:.2f})"
        self.assertEqual(str(self.book_cover), expected)

    def test_book_cover_aspect_ratio_calculation(self):
        """Test automatic aspect ratio calculation"""
        self.assertIsNotNone(self.book_cover.aspect_ratio)
        self.assertEqual(self.book_cover.aspect_ratio, 600 / 800)

    def test_book_cover_high_resolution_detection(self):
        """Test high resolution detection"""
        self.assertTrue(self.book_cover.is_high_resolution)

    def test_book_cover_properties(self):
        """Test book cover properties"""
        self.assertTrue(self.book_cover.is_local_file)
        self.assertEqual(self.book_cover.resolution_str, "600x800")

    def test_book_cover_url_detection(self):
        """Test URL vs local file detection"""
        url_cover = BookCover.objects.create(
            book=self.book,
            cover_path="https://example.com/cover.jpg",
            source=self.data_source,
            confidence=0.7
        )
        self.assertFalse(url_cover.is_local_file)


class DataSourceModelTests(TestCase):
    """Test cases for DataSource model"""

    def setUp(self):
        """Set up test data"""
        self.data_source, created = DataSource.objects.get_or_create(
            name=DataSource.GOOGLE_BOOKS,
            defaults={'trust_level': 0.8}
        )

    def test_data_source_creation(self):
        """Test data source creation"""
        self.assertEqual(self.data_source.name, DataSource.GOOGLE_BOOKS)
        # Since we're using get_or_create, trust_level may come from DataSourceModelTests
        # or may be set from another test, so check the value is reasonable
        self.assertGreaterEqual(self.data_source.trust_level, 0.0)
        self.assertLessEqual(self.data_source.trust_level, 1.0)

    def test_data_source_str_representation(self):
        """Test data source string representation"""
        self.assertEqual(str(self.data_source), "Google Books")

    def test_data_source_choices(self):
        """Test that data source choices are valid"""
        filename_source, created = DataSource.objects.get_or_create(
            name=DataSource.FILENAME,
            defaults={'trust_level': 0.5}
        )
        self.assertEqual(filename_source.name, DataSource.FILENAME)


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

        self.data_source, created = DataSource.objects.get_or_create(
            name=DataSource.EPUB_INTERNAL,
            defaults={'trust_level': 0.9}
        )

        self.book_metadata = BookMetadata.objects.create(
            book=self.book,
            source=self.data_source,
            field_name="title",
            field_value="Test Book",
            confidence=0.85
        )

    def test_book_metadata_creation(self):
        """Test book metadata creation"""
        self.assertEqual(self.book_metadata.book, self.book)
        self.assertEqual(self.book_metadata.source, self.data_source)
        self.assertEqual(self.book_metadata.field_name, "title")
        self.assertEqual(self.book_metadata.field_value, "Test Book")
        self.assertEqual(self.book_metadata.confidence, 0.85)

    def test_book_metadata_str_representation(self):
        """Test book metadata string representation"""
        expected = "title: Test Book (EPUB)"
        self.assertEqual(str(self.book_metadata), expected)

    def test_book_metadata_is_active_default(self):
        """Test that metadata is active by default"""
        self.assertTrue(self.book_metadata.is_active)


class AuthorModelTests(TestCase):
    """Test cases for Author model"""

    def setUp(self):
        """Set up test data"""
        self.author = Author.objects.create(
            name="Test Author"
        )

    def test_author_creation(self):
        """Test author creation"""
        self.assertEqual(self.author.name, "Test Author")
        # The model should automatically set name_normalized
        self.assertTrue(hasattr(self.author, 'name_normalized'))
        self.assertIsNotNone(self.author.name_normalized)

    def test_author_str_representation(self):
        """Test author string representation"""
        self.assertEqual(str(self.author), "Test Author")

    def test_author_name_parsing(self):
        """Test automatic first/last name parsing"""
        complex_author = Author.objects.create(name="John van der Berg")
        complex_author.refresh_from_db()
        # The save method should parse the name
        self.assertIsNotNone(complex_author.first_name)
        self.assertIsNotNone(complex_author.last_name)

    def test_author_comma_separated_name(self):
        """Test comma-separated name parsing"""
        author = Author.objects.create(name="Smith, John")
        author.refresh_from_db()
        self.assertEqual(author.last_name, "Smith")
        self.assertEqual(author.first_name, "John")


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
        self.assertEqual(str(self.scan_folder), "Test Scan Folder (Ebooks)")

    def test_scan_folder_default_language(self):
        """Test default language setting"""
        self.assertEqual(self.scan_folder.language, 'en')

    def test_scan_folder_created_at(self):
        """Test that created_at is set automatically"""
        self.assertIsNotNone(self.scan_folder.created_at)


class PublisherModelTests(TestCase):
    """Test cases for Publisher model"""

    def setUp(self):
        """Set up test data"""
        self.publisher = Publisher.objects.create(
            name="Test Publisher"
        )

    def test_publisher_creation(self):
        """Test publisher creation"""
        self.assertEqual(self.publisher.name, "Test Publisher")
        self.assertFalse(self.publisher.is_reviewed)

    def test_publisher_str_representation(self):
        """Test publisher string representation"""
        self.assertEqual(str(self.publisher), "Test Publisher")


class GenreModelTests(TestCase):
    """Test cases for Genre model"""

    def setUp(self):
        """Set up test data"""
        self.genre = Genre.objects.create(
            name="Science Fiction"
        )

    def test_genre_creation(self):
        """Test genre creation"""
        self.assertEqual(self.genre.name, "Science Fiction")

    def test_genre_str_representation(self):
        """Test genre string representation"""
        self.assertEqual(str(self.genre), "Science Fiction")


class SeriesModelTests(TestCase):
    """Test cases for Series model"""

    def setUp(self):
        """Set up test data"""
        self.series = Series.objects.create(
            name="Test Series"
        )

    def test_series_creation(self):
        """Test series creation"""
        self.assertEqual(self.series.name, "Test Series")

    def test_series_str_representation(self):
        """Test series string representation"""
        self.assertEqual(str(self.series), "Test Series")


class RelationshipModelTests(TestCase):
    """Test cases for relationship models (BookAuthor, BookTitle, etc.)"""

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

        self.author = Author.objects.create(name="Test Author")
        self.publisher = Publisher.objects.create(name="Test Publisher")
        self.genre = Genre.objects.create(name="Fiction")
        self.series = Series.objects.create(name="Test Series")

        self.data_source, created = DataSource.objects.get_or_create(
            name=DataSource.MANUAL,
            defaults={'trust_level': 1.0}
        )

    def test_book_author_creation(self):
        """Test BookAuthor relationship creation"""
        book_author = BookAuthor.objects.create(
            book=self.book,
            author=self.author,
            source=self.data_source,
            confidence=0.9,
            is_main_author=True
        )
        self.assertEqual(book_author.book, self.book)
        self.assertEqual(book_author.author, self.author)
        self.assertTrue(book_author.is_main_author)

    def test_book_title_creation(self):
        """Test BookTitle creation"""
        book_title = BookTitle.objects.create(
            book=self.book,
            title="Test Book Title",
            source=self.data_source,
            confidence=0.8
        )
        self.assertEqual(book_title.title, "Test Book Title")
        self.assertEqual(str(book_title), "Test Book Title (Manual Entry)")

    def test_book_publisher_creation(self):
        """Test BookPublisher relationship creation"""
        book_publisher = BookPublisher.objects.create(
            book=self.book,
            publisher=self.publisher,
            source=self.data_source,
            confidence=0.7
        )
        self.assertEqual(book_publisher.publisher, self.publisher)

    def test_book_genre_creation(self):
        """Test BookGenre relationship creation"""
        book_genre = BookGenre.objects.create(
            book=self.book,
            genre=self.genre,
            source=self.data_source,
            confidence=0.8
        )
        self.assertEqual(book_genre.genre, self.genre)

    def test_book_series_creation(self):
        """Test BookSeries relationship creation"""
        book_series = BookSeries.objects.create(
            book=self.book,
            series=self.series,
            series_number="1",
            source=self.data_source,
            confidence=0.9
        )
        self.assertEqual(book_series.series, self.series)
        self.assertEqual(book_series.series_number, "1")
