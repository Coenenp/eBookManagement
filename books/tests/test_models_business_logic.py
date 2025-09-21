"""
Enhanced tests for complex business logic in books.models module.

Focuses on edge cases, error recovery, metadata synchronization scenarios,
and complex validation patterns that require comprehensive coverage.
"""

from django.test import TestCase
from django.db import IntegrityError, transaction
from unittest.mock import patch

from books.models import (
    Book, FinalMetadata, DataSource, BookTitle, BookAuthor,
    BookSeries, BookPublisher, BookMetadata, Author, Publisher, Series,
    ScanFolder, ScanLog, ScanStatus
)


class FinalMetadataBusinessLogicTests(TestCase):
    """Test complex business logic scenarios in FinalMetadata model."""

    def setUp(self):
        """Set up test data for business logic tests."""
        self.scan_folder = ScanFolder.objects.create(
            path='/test/scan/folder',
            name='Test Scan Folder'
        )

        self.book = Book.objects.create(
            file_path='/test/path/book.epub',
            file_format='epub',
            file_size=1024000,
            scan_folder=self.scan_folder
        )

        # Create multiple data sources with different trust levels
        self.manual_source = DataSource.objects.create(
            name=DataSource.MANUAL,
            trust_level=1.0
        )

        self.openlibrary_source = DataSource.objects.create(
            name=DataSource.OPEN_LIBRARY,
            trust_level=0.95
        )

        self.filename_source = DataSource.objects.create(
            name=DataSource.FILENAME,
            trust_level=0.2
        )

    def test_metadata_sync_priority_resolution(self):
        """Test metadata synchronization with conflicting sources."""
        final_metadata = FinalMetadata.objects.create(book=self.book)

        # Create conflicting titles with different trust levels
        BookTitle.objects.create(
            book=self.book,
            title='Low Trust Title',
            source=self.filename_source,
            confidence=0.9,
            is_active=True
        )

        BookTitle.objects.create(
            book=self.book,
            title='High Trust Title',
            source=self.manual_source,
            confidence=0.7,
            is_active=True
        )

        final_metadata.update_final_title()

        # Should choose high trust source even with lower confidence
        self.assertEqual(final_metadata.final_title, 'High Trust Title')
        self.assertEqual(final_metadata.final_title_confidence, 0.7)

    def test_metadata_sync_with_inactive_sources(self):
        """Test that inactive metadata sources are properly ignored."""
        final_metadata = FinalMetadata.objects.create(book=self.book)

        # Create active and inactive titles
        BookTitle.objects.create(
            book=self.book,
            title='Active Title',
            source=self.filename_source,
            confidence=0.5,
            is_active=True
        )

        BookTitle.objects.create(
            book=self.book,
            title='Inactive High Trust Title',
            source=self.manual_source,
            confidence=0.9,
            is_active=False
        )

        final_metadata.update_final_title()

        # Should use active source even if it has lower trust
        self.assertEqual(final_metadata.final_title, 'Active Title')
        self.assertEqual(final_metadata.final_title_confidence, 0.5)

    def test_complex_author_synchronization(self):
        """Test complex author synchronization with multiple authors."""
        final_metadata = FinalMetadata.objects.create(book=self.book)

        # Create multiple authors with different roles
        author1 = Author.objects.create(name='Primary Author')
        author2 = Author.objects.create(name='Secondary Author')
        author3 = Author.objects.create(name='Editor')

        # Primary author with high trust
        BookAuthor.objects.create(
            book=self.book,
            author=author1,
            source=self.manual_source,
            confidence=0.9,
            is_active=True,
            is_main_author=True
        )

        # Secondary author (not main)
        BookAuthor.objects.create(
            book=self.book,
            author=author2,
            source=self.manual_source,
            confidence=0.8,
            is_active=True,
            is_main_author=False
        )

        # Another main author with lower trust (should be ignored)
        BookAuthor.objects.create(
            book=self.book,
            author=author3,
            source=self.filename_source,
            confidence=0.9,
            is_active=True,
            is_main_author=True
        )

        final_metadata.update_final_author()

        # Should choose the main author from highest trust source
        self.assertEqual(final_metadata.final_author, 'Primary Author')

    def test_series_sync_with_number_parsing(self):
        """Test series synchronization with complex series number formats."""
        final_metadata = FinalMetadata.objects.create(book=self.book)

        series = Series.objects.create(name='Test Series')

        # Test with decimal series number
        BookSeries.objects.create(
            book=self.book,
            series=series,
            series_number='1.5',
            source=self.manual_source,
            confidence=0.9,
            is_active=True
        )

        final_metadata.update_final_series()

        self.assertEqual(final_metadata.final_series, 'Test Series')
        self.assertEqual(final_metadata.final_series_number, '1.5')

    def test_dynamic_field_year_extraction_edge_cases(self):
        """Test publication year extraction with complex text patterns."""
        final_metadata = FinalMetadata.objects.create(book=self.book)

        test_cases = [
            ('Published in 2023 by Test Publisher', 2023),
            ('Copyright (c) 2019-2023', 2023),  # Should get the later year
            ('First published 1995, revised 2020', 2020),
            ('©2018', 2018),
            ('Date: 2022/01/15', 2022),
            ('No year information here', None),
            ('Published in the year nineteen ninety-five', None),  # Text numbers
            ('2025 future publication', 2025),
        ]

        for i, (field_value, expected_year) in enumerate(test_cases):
            with self.subTest(field_value=field_value):
                # Clear existing metadata
                BookMetadata.objects.filter(book=self.book).delete()

                BookMetadata.objects.create(
                    book=self.book,
                    field_name='publication_year',
                    field_value=field_value,
                    source=self.manual_source,
                    confidence=0.9,
                    is_active=True
                )

                final_metadata.update_dynamic_field('publication_year')
                self.assertEqual(final_metadata.publication_year, expected_year)

    def test_overall_confidence_calculation_complex(self):
        """Test overall confidence calculation with various metadata types."""
        final_metadata = FinalMetadata.objects.create(book=self.book)

        # Create metadata with different confidence levels
        author = Author.objects.create(name='Test Author')
        series = Series.objects.create(name='Test Series')
        publisher = Publisher.objects.create(name='Test Publisher')

        BookTitle.objects.create(
            book=self.book, title='Test Title', source=self.manual_source,
            confidence=0.9, is_active=True
        )

        BookAuthor.objects.create(
            book=self.book, author=author, source=self.openlibrary_source,
            confidence=0.8, is_active=True, is_main_author=True
        )

        BookSeries.objects.create(
            book=self.book, series=series, series_number='1',
            source=self.filename_source, confidence=0.3, is_active=True
        )

        BookPublisher.objects.create(
            book=self.book, publisher=publisher, source=self.manual_source,
            confidence=0.7, is_active=True
        )

        BookMetadata.objects.create(
            book=self.book, field_name='publication_year', field_value='2023',
            source=self.openlibrary_source, confidence=0.85, is_active=True
        )

        final_metadata.update_final_values()

        # Overall confidence should be weighted average
        # (0.9 + 0.8 + 0.3 + 0.7 + 0.85) / 5 = 0.71
        expected_confidence = 0.71
        self.assertAlmostEqual(final_metadata.overall_confidence, expected_confidence, places=2)

    def test_completeness_score_edge_cases(self):
        """Test completeness score calculation edge cases."""
        # Test with minimal data
        final_metadata = FinalMetadata.objects.create(
            book=self.book,
            final_title='Only Title'
        )

        score = final_metadata.calculate_completeness_score()
        # Only 1 field out of 8 core fields filled
        self.assertEqual(score, 1/8)

        # Test with all fields filled
        final_metadata.final_author = 'Author'
        final_metadata.final_series = 'Series'
        final_metadata.final_series_number = '1'
        final_metadata.final_publisher = 'Publisher'
        final_metadata.final_cover_path = '/path/to/cover.jpg'
        final_metadata.language = 'en'
        final_metadata.publication_year = 2023
        final_metadata.has_cover = True

        score = final_metadata.calculate_completeness_score()
        self.assertEqual(score, 1.0)  # All 8 fields filled

    @patch('books.models.logger')
    def test_save_error_recovery(self, mock_logger):
        """Test FinalMetadata save error recovery mechanisms."""
        final_metadata = FinalMetadata.objects.create(book=self.book)

        # Mock update_final_values to raise an exception
        with patch.object(final_metadata, 'update_final_values') as mock_update:
            mock_update.side_effect = Exception('Database error')

            # Save should complete even if update fails
            final_metadata.save()

            # Should log the error
            mock_logger.error.assert_called()

    def test_metadata_hash_generation_and_deduplication(self):
        """Test metadata hash generation prevents duplicates."""
        # Create identical metadata entries
        metadata1 = BookMetadata.objects.create(
            book=self.book,
            field_name='description',
            field_value='Identical description',
            source=self.manual_source,
            confidence=0.8
        )

        # Try to create duplicate (should have same hash)
        metadata2 = BookMetadata.objects.create(
            book=self.book,
            field_name='description',
            field_value='Identical description',
            source=self.manual_source,
            confidence=0.8
        )

        # Hashes should be identical
        self.assertEqual(metadata1.field_value_hash, metadata2.field_value_hash)

        # But they should still be separate objects
        self.assertNotEqual(metadata1.id, metadata2.id)

    def test_concurrent_metadata_updates(self):
        """Test handling of concurrent metadata updates."""
        final_metadata = FinalMetadata.objects.create(book=self.book)

        # Simulate concurrent updates by disabling auto-update
        final_metadata._manual_update = True

        # Update title separately
        BookTitle.objects.create(
            book=self.book,
            title='Concurrent Title',
            source=self.manual_source,
            confidence=0.9,
            is_active=True
        )

        # Update author separately
        author = Author.objects.create(name='Concurrent Author')
        BookAuthor.objects.create(
            book=self.book,
            author=author,
            source=self.manual_source,
            confidence=0.8,
            is_active=True,
            is_main_author=True
        )

        # Now trigger full update
        final_metadata._manual_update = False
        final_metadata.update_final_values()

        self.assertEqual(final_metadata.final_title, 'Concurrent Title')
        self.assertEqual(final_metadata.final_author, 'Concurrent Author')


class BookModelBusinessLogicTests(TestCase):
    """Test complex business logic in Book model."""

    def setUp(self):
        self.scan_folder = ScanFolder.objects.create(
            path='/test/scan/folder',
            name='Test Scan Folder'
        )

    def test_book_creation_with_validation_edge_cases(self):
        """Test book creation with edge case validations."""
        # Test with very long file path
        long_path = '/test/' + 'a' * 500 + '/book.epub'

        book = Book.objects.create(
            file_path=long_path,
            file_format='epub',
            file_size=1024,
            scan_folder=self.scan_folder
        )

        self.assertEqual(book.file_path, long_path)

    def test_book_file_size_validation(self):
        """Test book file size validation and edge cases."""
        # Test with zero file size
        book = Book.objects.create(
            file_path='/test/empty.epub',
            file_format='epub',
            file_size=0,
            scan_folder=self.scan_folder
        )

        self.assertEqual(book.file_size, 0)

        # Test with very large file size
        large_size = 10 * 1024 * 1024 * 1024  # 10GB
        book = Book.objects.create(
            file_path='/test/large.epub',
            file_format='epub',
            file_size=large_size,
            scan_folder=self.scan_folder
        )

        self.assertEqual(book.file_size, large_size)

    def test_book_format_validation(self):
        """Test book format validation with various formats."""
        formats = ['epub', 'pdf', 'mobi', 'azw3', 'cbr', 'cbz', 'txt']

        for fmt in formats:
            book = Book.objects.create(
                file_path=f'/test/book.{fmt}',
                file_format=fmt,
                file_size=1024,
                scan_folder=self.scan_folder
            )

            self.assertEqual(book.file_format, fmt)


class DataSourceBusinessLogicTests(TestCase):
    """Test DataSource model business logic."""

    def test_data_source_trust_level_validation(self):
        """Test data source trust level validation."""
        # Test valid trust levels
        valid_levels = [0.0, 0.5, 1.0, 0.99, 0.01]

        for level in valid_levels:
            source = DataSource.objects.create(
                name=f'Test Source {level}',
                trust_level=level
            )
            self.assertEqual(source.trust_level, level)

    def test_data_source_name_uniqueness(self):
        """Test data source name uniqueness constraint."""
        DataSource.objects.create(
            name='Unique Source',
            trust_level=0.8
        )

        # Creating another with same name should raise error
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                DataSource.objects.create(
                    name='Unique Source',
                    trust_level=0.9
                )

    def test_data_source_constants_coverage(self):
        """Test that all DataSource constants are properly defined."""
        required_constants = [
            'MANUAL', 'OPEN_LIBRARY', 'OPF_FILE', 'CONTENT_SCAN',
            'EPUB_INTERNAL', 'MOBI_INTERNAL', 'GOOGLE_BOOKS',
            'OPEN_LIBRARY_COVERS', 'PDF_INTERNAL', 'GOOGLE_BOOKS_COVERS',
            'ORIGINAL_SCAN', 'FILENAME', 'COMICVINE'
        ]

        for constant in required_constants:
            self.assertTrue(hasattr(DataSource, constant))
            self.assertIsInstance(getattr(DataSource, constant), str)


class ScanLogBusinessLogicTests(TestCase):
    """Test ScanLog model business logic."""

    def setUp(self):
        self.scan_folder = ScanFolder.objects.create(
            path='/test/scan/folder',
            name='Test Scan Folder'
        )

    def test_scan_log_level_validation(self):
        """Test scan log level validation."""
        valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']

        for level in valid_levels:
            log = ScanLog.objects.create(
                level=level,
                message=f'Test {level} message',
                scan_folder=self.scan_folder
            )
            self.assertEqual(log.level, level)

    def test_scan_log_long_message_handling(self):
        """Test scan log with very long messages."""
        very_long_message = 'X' * 10000  # 10KB message

        log = ScanLog.objects.create(
            level='INFO',
            message=very_long_message,
            scan_folder=self.scan_folder
        )

        self.assertEqual(log.message, very_long_message)

    def test_scan_log_with_null_file_path(self):
        """Test scan log creation with null file path."""
        log = ScanLog.objects.create(
            level='INFO',
            message='General scan message',
            scan_folder=self.scan_folder,
            file_path=None
        )

        self.assertIsNone(log.file_path)

    def test_scan_log_ordering(self):
        """Test scan log default ordering by timestamp."""
        log1 = ScanLog.objects.create(
            level='INFO',
            message='First message',
            scan_folder=self.scan_folder
        )

        log2 = ScanLog.objects.create(
            level='ERROR',
            message='Second message',
            scan_folder=self.scan_folder
        )

        logs = list(ScanLog.objects.all())
        # Should be ordered by most recent first
        self.assertEqual(logs[0], log2)
        self.assertEqual(logs[1], log1)


class ScanStatusBusinessLogicTests(TestCase):
    """Test ScanStatus model business logic."""

    def test_scan_status_progression(self):
        """Test scan status progression through different states."""
        statuses = ['Idle', 'Starting', 'Running', 'Completed', 'Failed']

        status_obj = ScanStatus.objects.create(status='Idle')

        for status in statuses:
            status_obj.status = status
            status_obj.save()
            status_obj.refresh_from_db()
            self.assertEqual(status_obj.status, status)

    def test_scan_status_with_progress_tracking(self):
        """Test scan status with progress information."""
        status = ScanStatus.objects.create(
            status='Running',
            current_file='/test/book.epub',
            total_files=100,
            processed_files=50
        )

        self.assertEqual(status.current_file, '/test/book.epub')
        self.assertEqual(status.total_files, 100)
        self.assertEqual(status.processed_files, 50)

    def test_scan_status_completion_tracking(self):
        """Test scan status completion percentage calculation."""
        status = ScanStatus.objects.create(
            status='Running',
            total_files=200,
            processed_files=150
        )

        # If the model has a completion percentage method
        if hasattr(status, 'completion_percentage'):
            expected_percentage = (150 / 200) * 100
            self.assertEqual(status.completion_percentage(), expected_percentage)


class MetadataValidationBusinessLogicTests(TestCase):
    """Test metadata validation business logic."""

    def setUp(self):
        self.scan_folder = ScanFolder.objects.create(
            path='/test/scan/folder',
            name='Test Scan Folder'
        )

        self.book = Book.objects.create(
            file_path='/test/path/book.epub',
            file_format='epub',
            file_size=1024000,
            scan_folder=self.scan_folder
        )

        self.data_source = DataSource.objects.create(
            name=DataSource.MANUAL,
            trust_level=1.0
        )

    def test_book_title_validation_edge_cases(self):
        """Test BookTitle validation with edge cases."""
        # Test with very long title
        long_title = 'A' * 1000

        title = BookTitle.objects.create(
            book=self.book,
            title=long_title,
            source=self.data_source,
            confidence=0.8
        )

        self.assertEqual(title.title, long_title)

    def test_book_author_confidence_validation(self):
        """Test BookAuthor confidence validation."""
        author = Author.objects.create(name='Test Author')

        # Test with boundary confidence values
        for confidence in [0.0, 0.5, 1.0]:
            book_author = BookAuthor.objects.create(
                book=self.book,
                author=author,
                source=self.data_source,
                confidence=confidence,
                is_main_author=True
            )
            self.assertEqual(book_author.confidence, confidence)

    def test_book_metadata_field_value_hash_uniqueness(self):
        """Test BookMetadata field value hash uniqueness within book."""
        # Create metadata with same field value
        field_value = 'Same description text'

        metadata1 = BookMetadata.objects.create(
            book=self.book,
            field_name='description',
            field_value=field_value,
            source=self.data_source,
            confidence=0.8
        )

        metadata2 = BookMetadata.objects.create(
            book=self.book,
            field_name='description',
            field_value=field_value,
            source=self.data_source,
            confidence=0.9  # Different confidence
        )

        # Should have same hash despite different confidence
        self.assertEqual(metadata1.field_value_hash, metadata2.field_value_hash)

    def test_complex_metadata_relationships(self):
        """Test complex metadata relationship scenarios."""
        # Create a book with full metadata hierarchy
        author = Author.objects.create(name='Complex Author')
        series = Series.objects.create(name='Complex Series')
        publisher = Publisher.objects.create(name='Complex Publisher')

        # Create all metadata types
        BookTitle.objects.create(
            book=self.book, title='Complex Title',
            source=self.data_source, confidence=0.9
        )

        BookAuthor.objects.create(
            book=self.book, author=author,
            source=self.data_source, confidence=0.8,
            is_main_author=True
        )

        BookSeries.objects.create(
            book=self.book, series=series, series_number='1',
            source=self.data_source, confidence=0.7
        )

        BookPublisher.objects.create(
            book=self.book, publisher=publisher,
            source=self.data_source, confidence=0.6
        )

        BookMetadata.objects.create(
            book=self.book, field_name='publication_year',
            field_value='2023', source=self.data_source,
            confidence=0.9
        )

        # Verify all relationships exist
        self.assertEqual(self.book.booktitle_set.count(), 1)
        self.assertEqual(self.book.bookauthor_set.count(), 1)
        self.assertEqual(self.book.bookseries_set.count(), 1)
        self.assertEqual(self.book.bookpublisher_set.count(), 1)
        self.assertEqual(self.book.bookmetadata_set.count(), 1)

    def test_metadata_activation_deactivation_cycles(self):
        """Test metadata activation/deactivation business logic."""
        title = BookTitle.objects.create(
            book=self.book,
            title='Active Title',
            source=self.data_source,
            confidence=0.9,
            is_active=True
        )

        # Create FinalMetadata to test sync
        final_metadata = FinalMetadata.objects.create(book=self.book)
        final_metadata.update_final_title()

        self.assertEqual(final_metadata.final_title, 'Active Title')

        # Deactivate title
        title.is_active = False
        title.save()

        # Should trigger sync and clear final title
        final_metadata.refresh_from_db()
        final_metadata.update_final_title()

        self.assertEqual(final_metadata.final_title, '')


class ErrorRecoveryBusinessLogicTests(TestCase):
    """Test error recovery and resilience in business logic."""

    def setUp(self):
        self.scan_folder = ScanFolder.objects.create(
            path='/test/scan/folder',
            name='Test Scan Folder'
        )

        self.book = Book.objects.create(
            file_path='/test/path/book.epub',
            file_format='epub',
            file_size=1024000,
            scan_folder=self.scan_folder
        )

    @patch('books.models.logger')
    def test_final_metadata_partial_update_recovery(self, mock_logger):
        """Test FinalMetadata recovery from partial update failures."""
        final_metadata = FinalMetadata.objects.create(book=self.book)

        # Mock one update method to fail
        with patch.object(final_metadata, 'update_final_title') as mock_title:
            mock_title.side_effect = Exception('Title update failed')

            with patch.object(final_metadata, 'update_final_author') as mock_author:
                # This should succeed
                mock_author.return_value = None

                # Should handle partial failure gracefully
                try:
                    final_metadata.update_final_values()
                except Exception as e:
                    # Should not propagate the exception
                    self.fail(f"update_final_values should handle errors gracefully: {e}")

    @patch('books.models.logger')
    def test_database_constraint_violation_handling(self, mock_logger):
        """Test handling of database constraint violations."""
        DataSource.objects.create(
            name=DataSource.MANUAL,
            trust_level=1.0
        )

        # Test duplicate data source creation
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                DataSource.objects.create(
                    name=DataSource.MANUAL,  # Duplicate name
                    trust_level=0.8
                )

    def test_cascade_deletion_behavior(self):
        """Test cascade deletion behavior in related models."""
        data_source = DataSource.objects.create(
            name=DataSource.MANUAL,
            trust_level=1.0
        )

        # Create metadata that depends on the book
        BookTitle.objects.create(
            book=self.book,
            title='Test Title',
            source=data_source,
            confidence=0.9
        )

        FinalMetadata.objects.create(book=self.book)

        # Delete the book
        book_id = self.book.id
        self.book.delete()

        # Related metadata should be deleted
        self.assertEqual(BookTitle.objects.filter(book_id=book_id).count(), 0)
        self.assertEqual(FinalMetadata.objects.filter(book_id=book_id).count(), 0)

    def test_orphaned_metadata_cleanup(self):
        """Test cleanup of orphaned metadata records."""
        data_source = DataSource.objects.create(
            name=DataSource.MANUAL,
            trust_level=1.0
        )

        # Create author and metadata
        author = Author.objects.create(name='Test Author')
        book_author = BookAuthor.objects.create(
            book=self.book,
            author=author,
            source=data_source,
            confidence=0.8
        )

        # Delete the author
        author.delete()

        # BookAuthor should be deleted due to cascade
        self.assertEqual(BookAuthor.objects.filter(id=book_author.id).count(), 0)
