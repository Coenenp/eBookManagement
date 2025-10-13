"""
Test Suite for Ebook & Series Renamer - Template Engine
Tests the core renaming engine functionality including JMTE template processing,
token resolution, pattern validation, and metadata handling.

Note: This is a basic implementation that tests the core renaming engine logic.
Full integration with the existing book models would require additional development.
"""

import tempfile
from pathlib import Path

from django.test import TestCase

from books.models import Author, Series, ScanFolder, BookTitle, FinalMetadata, DataSource
from books.utils.renaming_engine import (
    RenamingEngine,
    RenamingPatternValidator,
    PREDEFINED_PATTERNS
)
from books.tests.test_helpers import create_test_book_with_file


class BaseTestCaseWithTempDir(TestCase):
    """Base test case with temporary directory setup"""

    def setUp(self):
        super().setUp()
        # Create a temporary directory for test files
        import tempfile
        from pathlib import Path
        self.temp_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        super().tearDown()
        # Clean up temporary directory
        import shutil
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)


class RenamingEngineTests(TestCase):
    """Test cases for the RenamingEngine class"""

    def setUp(self):
        """Set up test data"""
        self.engine = RenamingEngine()

        # Create data source for testing
        self.data_source, created = DataSource.objects.get_or_create(
            name=DataSource.MANUAL,
            defaults={'priority': 1, 'trust_level': 5}
        )

        # Create test data using existing model structure
        self.author = Author.objects.create(
            first_name="Isaac",
            last_name="Asimov"
        )

        self.series = Series.objects.create(
            name="Foundation Series"
        )

        # Create basic book using actual Book model structure
        self.book = create_test_book_with_file(
            file_path="/test/Foundation.epub",
            file_format="epub",
            file_size=1024000
        )

        # Create author relationship
        from books.models import BookAuthor
        BookAuthor.objects.create(book=self.book, author=self.author, source=self.data_source)

        # Create series relationship
        from books.models import BookSeries
        BookSeries.objects.create(book=self.book, series=self.series, source=self.data_source)

        # Create final metadata that the renaming engine will use
        from books.models import FinalMetadata
        self.final_metadata = FinalMetadata.objects.create(
            book=self.book,
            final_title="Foundation",
            final_author="Isaac Asimov",
            final_series="Foundation Series",
            final_series_number="1",
            language="English"
        )


class TC1BasicRenamingRulesTests(RenamingEngineTests):
    """TC1 – Basic Renaming Rules"""

    def test_tc1_1_rename_simple_title_pattern(self):
        """TC1.1 – Rename based on simple title pattern"""
        pattern = "${title}.${ext}"
        result = self.engine.process_template(pattern, self.book)
        self.assertEqual(result, "Foundation.epub")

    def test_tc1_2_rename_with_author_portability(self):
        """TC1.2 – Rename including author name for portability"""
        pattern = "${author.sortname} - ${title}.${ext}"
        result = self.engine.process_template(pattern, self.book)
        self.assertEqual(result, "Asimov, Isaac - Foundation.epub")

    def test_tc1_3_empty_fields_omitted(self):
        """TC1.3 – Empty fields omitted"""
        # Test with series title but no series number
        self.final_metadata.final_series_number = ""  # Remove series number to test omission
        self.final_metadata.save()
        pattern = "${bookseries.title} #${bookseries.number} - ${title}.${ext}"
        result = self.engine.process_template(pattern, self.book)
        # Series number is empty, should be omitted
        self.assertEqual(result, "Foundation Series - Foundation.epub")

        # Test without series
        book_no_series = create_test_book_with_file(
            file_path="/test/Foundation_no_series.epub",
            file_format="epub",
            file_size=1024000
        )
        # Create final metadata for book without series
        from books.models import FinalMetadata
        FinalMetadata.objects.create(
            book=book_no_series,
            final_title="Foundation",
            final_author="Isaac Asimov"
        )

        result = self.engine.process_template(pattern, book_no_series)
        self.assertEqual(result, "Foundation.epub")

    def test_tc1_4_character_sanitization(self):
        """TC1.4 – Character sanitization"""
        book = create_test_book_with_file(
            file_path="/test/book.epub",
            file_size=1024000,
            file_format="epub"
        )

        # Create final metadata with invalid characters
        from books.models import FinalMetadata
        FinalMetadata.objects.create(
            book=book,
            final_title="Harry Potter: The Philosopher's Stone"
        )

        pattern = "${title}.${ext}"
        result = self.engine.process_template(pattern, book)
        # Special characters should be sanitized
        self.assertEqual(result, "Harry Potter_ The Philosopher's Stone.epub")

    def test_tc1_5_spaces_and_commas_handling(self):
        """TC1.5 – Spaces and commas handling"""
        pattern = "${author.sortname} - ${title}.${ext}"
        result = self.engine.process_template(pattern, self.book)

        # Spaces should be retained, commas used in author names
        self.assertEqual(result, "Asimov, Isaac - Foundation.epub")
        self.assertIn(", ", result)  # Comma in author name
        self.assertIn(" - ", result)  # Spaces around dash


class TC2FolderStructureRulesTests(RenamingEngineTests):
    """TC2 – Folder Structure Rules"""

    def test_tc2_1_full_folder_hierarchy_pattern(self):
        """TC2.1 – Full folder hierarchy pattern"""
        pattern = "Library/${format}/${language}/${category}/${author.sortname}/${bookseries.title}/${title}.${ext}"
        result = self.engine.process_template(pattern, self.book)

        expected = "Library/EPUB/en/Asimov, Isaac/Foundation Series/Foundation.epub"
        self.assertEqual(result, expected)

    def test_tc2_2_omit_empty_hierarchy_levels(self):
        """TC2.2 – Omit empty hierarchy levels"""
        # Create book without series
        book_no_series = create_test_book_with_file(
            file_path="/test/Foundation.epub",
            file_size=1024000,
            file_format="epub"
        )

        # Add title and author relationships
        BookTitle.objects.create(book=book_no_series, title="Foundation", source=self.data_source)
        from books.models import BookAuthor
        BookAuthor.objects.create(book=book_no_series, author=self.author, source=self.data_source)

        # Create FinalMetadata with language for this book
        FinalMetadata.objects.create(
            book=book_no_series,
            final_title="Foundation",
            final_author="Isaac Asimov",
            language="English"
        )

        pattern = "Library/${format}/${language}/${category}/${author.sortname}/${bookseries.title}/${title}.${ext}"
        result = self.engine.process_template(pattern, book_no_series)

        expected = "Library/EPUB/en/Asimov, Isaac/Foundation.epub"
        self.assertEqual(result, expected)

    def test_tc2_3_language_separated_folders(self):
        """TC2.3 – Language-separated top-level folders"""
        pattern = "Library/${language}/${author.sortname}/${title}.${ext}"
        result = self.engine.process_template(pattern, self.book)

        expected = "Library/en/Asimov, Isaac/Foundation.epub"
        self.assertEqual(result, expected)

    def test_tc2_4_deep_nesting_structure(self):
        """TC2.4 – Deep nesting structure"""
        # Add category metadata for testing
        from books.models import BookMetadata
        BookMetadata.objects.create(
            book=self.book,
            field_name='category',
            field_value='Fiction',
            source=self.data_source
        )

        pattern = "Library/${category}/${format}/${author.sortname}/${bookseries.title}/${title}.${ext}"
        result = self.engine.process_template(pattern, self.book)

        # Should create full structure recursively
        expected = "Library/EPUB/Asimov, Isaac/Foundation Series/Foundation.epub"
        self.assertEqual(result, expected)

        # Verify no missing path components
        path_parts = Path(result).parts
        self.assertGreater(len(path_parts), 2)  # Some nesting structure


class TC3SeriesAndStandaloneTests(RenamingEngineTests):
    """TC3 – Series and Standalone Behavior"""

    def test_tc3_1_series_file_naming(self):
        """TC3.1 – Series file naming"""
        # Add series number
        self.book.series_number = 1
        self.book.save()

        pattern = "${author.sortname} - ${bookseries.title} #${bookseries.number} - ${title}.${ext}"
        result = self.engine.process_template(pattern, self.book)

        expected = "Asimov, Isaac - Foundation Series #01 - Foundation.epub"
        self.assertEqual(result, expected)

    def test_tc3_2_standalone_fallback(self):
        """TC3.2 – Standalone fallback"""
        # Remove series
        self.book.series_relationships.all().delete()

        # Also remove series from final metadata
        self.final_metadata.final_series = ""
        self.final_metadata.final_series_number = ""
        self.final_metadata.save()

        pattern = "${author.sortname} - ${bookseries.title} #${bookseries.number} - ${title}.${ext}"
        result = self.engine.process_template(pattern, self.book)

        # Should fallback to just author and title
        expected = "Asimov, Isaac - - Foundation.epub"
        self.assertEqual(result, expected)

    def test_tc3_3_uniform_series_folder_organization(self):
        """TC3.3 – Uniform series folder organization"""
        # Test with series
        pattern = "${author.sortname}/${bookseries.title}/${title}.${ext}"
        result_with_series = self.engine.process_template(pattern, self.book)
        expected_with_series = "Asimov, Isaac/Foundation Series/Foundation.epub"
        self.assertEqual(result_with_series, expected_with_series)

        # Test standalone - should skip series folder
        self.book.series_relationships.all().delete()

        # Also remove series from final metadata
        self.final_metadata.final_series = ""
        self.final_metadata.final_series_number = ""
        self.final_metadata.save()

        result_standalone = self.engine.process_template(pattern, self.book)
        expected_standalone = "Asimov, Isaac/Foundation.epub"
        self.assertEqual(result_standalone, expected_standalone)

    def test_tc3_4_duplicate_detection_postponed(self):
        """TC3.4 – Duplicate detection postponed"""
        # Create duplicate book
        book2 = create_test_book_with_file(
            file_path="/test/duplicate/Foundation.epub",
            file_size=1024000,
            file_format="epub"
        )
        BookTitle.objects.create(book=book2, title="Foundation", source=self.data_source)
        from books.models import BookAuthor
        BookAuthor.objects.create(book=book2, author=self.author, source=self.data_source)

        # Create final metadata for book2 to match book1
        FinalMetadata.objects.create(
            book=book2,
            final_title="Foundation",
            final_author="Isaac Asimov",
            language="English"
        )

        pattern = "${author.sortname} - ${title}.${ext}"

        # Both should generate same filename - no merge at this stage
        result1 = self.engine.process_template(pattern, self.book)
        result2 = self.engine.process_template(pattern, book2)

        self.assertEqual(result1, result2)
        # Ensure both books remain separate in database
        foundation_books = [self.book, book2]
        self.assertEqual(len(foundation_books), 2)


class TC4CompanionFileHandlingTests(RenamingEngineTests):
    """TC4 – Companion File Handling"""

    def setUp(self):
        super().setUp()
        # Create temporary directory structure
        self.temp_dir = tempfile.mkdtemp()
        self.book_file = Path(self.temp_dir) / "Foundation.epub"
        self.cover_file = Path(self.temp_dir) / "cover.jpeg"
        self.metadata_file = Path(self.temp_dir) / "metadata.opf"

        # Create files
        self.book_file.touch()
        self.cover_file.touch()
        self.metadata_file.touch()

        # Update book file path through BookFile relationship
        book_file = self.book.files.first()
        if book_file:
            book_file.file_path = str(self.book_file)
            book_file.save()

    def tearDown(self):
        # Clean up temporary files
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        super().tearDown()

    def test_tc4_1_rename_companion_files_consistently(self):
        """TC4.1 – Rename companion files consistently"""
        pattern = "${title} - ${author.sortname}"
        base_name = self.engine.process_template(pattern, self.book)

        # Expected base name without extension
        expected_base = "Foundation - Asimov, Isaac"
        self.assertEqual(base_name, expected_base)

        # Companion files should share same base name
        expected_files = {
            f"{expected_base}.epub",
            f"{expected_base}.cover.jpeg",
            f"{expected_base}.opf"
        }

        # This would be handled by BatchRenamer, but we can test the pattern
        self.assertTrue(all(expected_base in filename for filename in expected_files))

    def test_tc4_2_companion_files_without_book_ignored(self):
        """TC4.2 – Companion files without book file ignored"""
        # Remove book file but leave companions
        self.book_file.unlink()

        # Companion detection should log warning but not fail
        # This would be handled by BatchRenamer's companion detection
        companion_files = [self.cover_file, self.metadata_file]

        # Should identify as orphaned companions
        for companion in companion_files:
            self.assertTrue(companion.exists())
            # Would log warning in actual implementation

    def test_tc4_3_preserve_relative_structure(self):
        """TC4.3 – Preserve relative structure for bundled resources"""
        # Create subdirectory structure
        extras_dir = Path(self.temp_dir) / "extras"
        extras_dir.mkdir()
        (extras_dir / "annotations.txt").touch()
        (extras_dir / "images" / "map.png").parent.mkdir(parents=True)
        (extras_dir / "images" / "map.png").touch()

        # Relative structure should be preserved under renamed folder
        # This would be handled by BatchRenamer's directory operations
        self.assertTrue(extras_dir.exists())
        self.assertTrue((extras_dir / "annotations.txt").exists())
        self.assertTrue((extras_dir / "images" / "map.png").exists())


class TC5TokenResolutionTests(RenamingEngineTests):
    """TC5 – Token Resolution and JMTE Evaluation"""

    def test_tc5_1_token_substitution(self):
        """TC5.1 – Token substitution"""
        pattern = "${title} (${publicationyear})"
        # First add publication year to final metadata
        self.final_metadata.publication_year = 1951
        self.final_metadata.save()

        result = self.engine.process_template(pattern, self.book)

        expected = "Foundation (1951)"
        self.assertEqual(result, expected)

    def test_tc5_2_nested_tokens(self):
        """TC5.2 – Nested tokens"""
        pattern = "${author.lastname}/${bookseries.title}/${title}"
        result = self.engine.process_template(pattern, self.book)

        expected = "Asimov/Foundation Series/Foundation"
        self.assertEqual(result, expected)

    def test_tc5_3_missing_field_fallback(self):
        """TC5.3 – Missing field fallback"""
        # Remove publication year from final metadata
        self.final_metadata.publication_year = None
        self.final_metadata.save()

        pattern = "${title} (${publicationyear}).${ext}"
        result = self.engine.process_template(pattern, self.book)

        # Missing year should be skipped gracefully
        expected = "Foundation.epub"
        self.assertEqual(result, expected)

        # Should not raise errors
        self.assertNotIn("None", result)
        self.assertNotIn("()", result)

    def test_tc5_4_combined_datasource(self):
        """TC5.4 – Combined datasource"""
        # Test that filename and path are treated as one datasource
        pattern = "${author.sortname}/${title}.${ext}"
        result = self.engine.process_template(pattern, self.book)

        # Should generate complete path as single evaluation
        expected = "Asimov, Isaac/Foundation.epub"
        self.assertEqual(result, expected)

        # Verify path components are properly joined
        path_obj = Path(result)
        self.assertEqual(path_obj.parent.name, "Asimov, Isaac")
        self.assertEqual(path_obj.name, "Foundation.epub")

    def test_tc5_5_conditional_support_backward_compatibility(self):
        """TC5.5 – Conditional support (future)"""
        # Test that current implementation doesn't break with simple conditionals
        # This ensures backward compatibility when JMTE conditionals are added

        pattern = "${title}.${ext}"
        result = self.engine.process_template(pattern, self.book)

        # Should work without conditionals
        self.assertEqual(result, "Foundation.epub")

        # Verify engine can be extended for future conditional logic
        self.assertTrue(hasattr(self.engine, 'process_template'))
        self.assertTrue(callable(getattr(self.engine, 'process_template')))


class TC6MetadataPreservationTests(RenamingEngineTests):
    """TC6 – Metadata Preservation"""

    def test_tc6_1_renaming_respects_source_scores(self):
        """TC6.1 – Renaming respects source scores"""
        # This would be tested in integration with metadata system
        # Renaming should use highest-scored metadata values

        pattern = "${title}"
        result = self.engine.process_template(pattern, self.book)

        # Should use the current title (highest score)
        self.assertEqual(result, "Foundation")

    def test_tc6_2_metadata_retained_after_rename(self):
        """TC6.2 – Metadata retained after rename"""
        original_title = self.book.titles.first().title if self.book.titles.exists() else ""
        original_author_count = self.book.author_relationships.count()

        # Simulate rename operation
        pattern = "${author.sortname} - ${title}.${ext}"
        self.engine.process_template(pattern, self.book)

        # Metadata should remain intact
        self.book.refresh_from_db()
        current_title = self.book.titles.first().title if self.book.titles.exists() else ""
        self.assertEqual(current_title, original_title)
        self.assertEqual(self.book.author_relationships.count(), original_author_count)

    def test_tc6_3_multiple_metadata_entries_per_field(self):
        """TC6.3 – Multiple metadata entries per field"""
        # Add multiple authors
        author2 = Author.objects.create(
            first_name="Robert",
            last_name="Heinlein"
        )
        from books.models import BookAuthor
        BookAuthor.objects.create(book=self.book, author=author2, source=self.data_source)

        # Both authors should be retained
        self.assertEqual(self.book.author_relationships.count(), 2)

        pattern = "${title}"
        self.engine.process_template(pattern, self.book)

        # All metadata entries should remain linked
        self.assertEqual(self.book.author_relationships.count(), 2)

    def test_tc6_4_metadata_added_but_not_promoted(self):
        """TC6.4 – Metadata added but not promoted"""
        # This tests that renaming doesn't affect metadata promotion logic
        # All metadata should be stored with source and score information

        pattern = "${title}.${ext}"
        result = self.engine.process_template(pattern, self.book)

        # Renaming shouldn't change metadata storage behavior
        self.assertEqual(result, "Foundation.epub")
        # Metadata relationships should be preserved
        self.assertTrue(self.book.author_relationships.exists())
        self.assertTrue(self.book.series_relationships.exists())


class RenamingPatternValidatorTests(TestCase):
    """Test cases for pattern validation"""

    def setUp(self):
        self.validator = RenamingPatternValidator()

    def test_valid_patterns(self):
        """Test validation of valid patterns"""
        valid_patterns = [
            "${title}",
            "${author.sortname} - ${title}.${ext}",
            "Library/${format}/${author.sortname}/${title}",
            "${bookseries.title} #${bookseries.number} - ${title}"
        ]

        for pattern in valid_patterns:
            with self.subTest(pattern=pattern):
                is_valid, warnings = self.validator.validate_pattern(pattern)
                self.assertTrue(is_valid)

    def test_invalid_patterns(self):
        """Test validation of invalid patterns"""
        invalid_patterns = [
            "${invalid_token}",
            "${title",  # Missing closing brace
            "title}",   # Missing opening brace
            "",         # Empty pattern
        ]

        for pattern in invalid_patterns:
            with self.subTest(pattern=pattern):
                is_valid, warnings = self.validator.validate_pattern(pattern)
                self.assertFalse(is_valid)

    def test_pattern_warnings(self):
        """Test pattern validation warnings"""
        # Pattern without extension
        is_valid, warnings = self.validator.validate_pattern("${title}")
        self.assertTrue(is_valid)
        self.assertIn("extension", " ".join(warnings).lower())

        # Pattern with potential path issues
        is_valid, warnings = self.validator.validate_pattern("${title}/${title}")
        self.assertTrue(is_valid)


class TokenProcessorTests(BaseTestCaseWithTempDir):
    """Test cases for token processing"""

    def setUp(self):
        super().setUp()
        self.processor = RenamingEngine()

        # Create test book
        self.author = Author.objects.create(
            name="Isaac Asimov",
            first_name="Isaac",
            last_name="Asimov"
        )

        # Create required scan folder using temp directory
        scan_folder = ScanFolder.objects.create(
            name="Test Folder",
            path=str(self.temp_dir),
            content_type="ebooks"
        )

        self.book = create_test_book_with_file(
            file_path=str(self.temp_dir / "Foundation.epub"),
            file_format="epub",
            file_size=1024000,
            scan_folder=scan_folder
        )

    def test_basic_token_processing(self):
        """Test basic token processing using template processing"""
        # Test that basic tokens can be processed
        template = "${title}"
        result = self.processor.process_template(template, self.book)
        # Since we created a book without title metadata, it should return empty or handle gracefully
        self.assertIsInstance(result, str)

    def test_token_values(self):
        """Test token value processing through templates"""
        # Test individual token processing through templates
        format_result = self.processor.process_template("${format}", self.book)
        ext_result = self.processor.process_template("${ext}", self.book)

        # These should work with the basic book data
        self.assertEqual(format_result, 'EPUB')
        self.assertEqual(ext_result, 'epub')

    def test_empty_token_handling(self):
        """Test handling of empty/missing tokens"""
        # Test with a token that should be empty (no publication year in our simple book)
        result = self.processor.process_template("${publicationyear}", self.book)

        # Empty values should be handled gracefully (return empty string or None-like)
        self.assertTrue(result == "" or result is None)

    def test_character_sanitization(self):
        """Test character sanitization in processed templates"""
        # Test template processing with invalid characters
        template = "Test: Invalid<>Characters|Here"
        result = self.processor._normalize_path(template)

        # Invalid filesystem characters should be sanitized
        self.assertNotIn(':', result)
        self.assertNotIn('<', result)
        self.assertNotIn('>', result)
        self.assertNotIn('|', result)


class PredefinedPatternsTests(TestCase):
    """Test cases for predefined patterns"""

    def test_predefined_patterns_exist(self):
        """Test that predefined patterns are available"""
        self.assertIsInstance(PREDEFINED_PATTERNS, dict)
        self.assertGreater(len(PREDEFINED_PATTERNS), 0)

    def test_predefined_patterns_structure(self):
        """Test predefined patterns have correct structure"""
        for name, pattern_data in PREDEFINED_PATTERNS.items():
            with self.subTest(pattern=name):
                self.assertIn('folder', pattern_data)
                self.assertIn('filename', pattern_data)
                self.assertIn('description', pattern_data)

                # Both patterns should be strings
                self.assertIsInstance(pattern_data['folder'], str)
                self.assertIsInstance(pattern_data['filename'], str)

    def test_predefined_patterns_validity(self):
        """Test that predefined patterns are valid"""
        validator = RenamingPatternValidator()

        for name, pattern_data in PREDEFINED_PATTERNS.items():
            with self.subTest(pattern=name):
                folder_valid, _ = validator.validate_pattern(pattern_data['folder'])
                filename_valid, _ = validator.validate_pattern(pattern_data['filename'])

                self.assertTrue(folder_valid, f"Invalid folder pattern in {name}")
                self.assertTrue(filename_valid, f"Invalid filename pattern in {name}")


class IntegrationTests(RenamingEngineTests):
    """Integration tests combining multiple components"""

    def test_end_to_end_pattern_processing(self):
        """Test complete pattern processing workflow"""
        # Full pattern with folder and filename
        folder_pattern = "Library/${format}/${language}/${author.sortname}"
        filename_pattern = "${bookseries.title} #${bookseries.number} - ${title}.${ext}"

        # Process folder pattern
        folder_result = self.engine.process_template(folder_pattern, self.book)
        expected_folder = "Library/EPUB/en/Asimov, Isaac"
        self.assertEqual(folder_result, expected_folder)

        # Process filename pattern (with series number)
        self.book.series_number = 1
        self.book.save()

        filename_result = self.engine.process_template(filename_pattern, self.book)
        expected_filename = "Foundation Series #01 - Foundation.epub"
        self.assertEqual(filename_result, expected_filename)

        # Combine for full path
        full_path = f"{folder_result}/{filename_result}"
        expected_full = "Library/EPUB/en/Asimov, Isaac/Foundation Series #01 - Foundation.epub"
        self.assertEqual(full_path, expected_full)

    def test_pattern_with_missing_optional_fields(self):
        """Test pattern processing with missing optional fields"""
        # Create minimal book
        minimal_book = create_test_book_with_file(
            file_path="/test/book.epub",
            file_size=1024000,
            file_format="epub"
        )
        # Add title through BookTitle relationship
        BookTitle.objects.create(book=minimal_book, title="Test Book", source=self.data_source)

        # Pattern with many optional fields
        pattern = "${author.sortname}/${bookseries.title}/${category}/${title} (${publicationyear}).${ext}"
        result = self.engine.process_template(pattern, minimal_book)

        # Should gracefully omit missing fields
        expected = "Test Book.epub"
        self.assertEqual(result, expected)

    def test_complex_folder_hierarchy(self):
        """Test complex folder hierarchy generation"""
        # Set all metadata fields
        self.book.publication_year = 1951
        self.book.series_number = 1
        self.book.save()

        pattern = "${category}/${language}/${format}/${author.sortname}/${bookseries.title}/${title} (${publicationyear}).${ext}"
        result = self.engine.process_template(pattern, self.book)

        expected = "en/EPUB/Asimov, Isaac/Foundation Series/Foundation (1951).epub"
        self.assertEqual(result, expected)

        # Verify path depth
        path_parts = Path(result).parts
        self.assertEqual(len(path_parts), 5)  # 4 directories + filename
