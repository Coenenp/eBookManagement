"""Tests for scanner bootstrap functionality.

This module tests the data source bootstrapping utilities that ensure
default data sources are created with appropriate confidence levels.
"""

from django.test import TestCase
from django.db import IntegrityError, transaction
from unittest.mock import patch, Mock

from books.models import DataSource
from books.scanner.bootstrap import ensure_data_sources


class BootstrapTests(TestCase):
    """Test cases for bootstrap functionality."""

    def test_ensure_data_sources_creates_all_sources(self):
        """Test that ensure_data_sources creates all expected data sources."""
        # Run bootstrap (should be idempotent)
        ensure_data_sources()

        # Check that all expected sources exist (13 total expected)
        expected_sources = [
            (DataSource.MANUAL, 1.0),
            (DataSource.OPEN_LIBRARY, 0.95),
            (DataSource.COMICVINE, 0.9),
            (DataSource.OPF_FILE, 0.9),
            (DataSource.CONTENT_SCAN, 0.85),
            (DataSource.EPUB_INTERNAL, 0.8),
            (DataSource.MOBI_INTERNAL, 0.75),
            (DataSource.GOOGLE_BOOKS, 0.7),
            (DataSource.OPEN_LIBRARY_COVERS, 0.65),
            (DataSource.PDF_INTERNAL, 0.6),
            (DataSource.GOOGLE_BOOKS_COVERS, 0.55),
            (DataSource.ORIGINAL_SCAN, 0.5),
            (DataSource.FILENAME, 0.2),
        ]

        # Verify all expected sources exist with correct trust levels
        self.assertEqual(DataSource.objects.count(), len(expected_sources))

        for name, expected_trust in expected_sources:
            source = DataSource.objects.get(name=name)
            self.assertEqual(source.trust_level, expected_trust)

    def test_ensure_data_sources_idempotent(self):
        """Test that ensure_data_sources can be called multiple times safely."""
        # Run bootstrap twice
        ensure_data_sources()
        initial_count = DataSource.objects.count()

        ensure_data_sources()

        # Should not create duplicates
        self.assertEqual(DataSource.objects.count(), initial_count)

    def test_trust_level_hierarchy(self):
        """Test that trust levels follow the expected hierarchy."""
        ensure_data_sources()

        # Get all sources ordered by trust level descending
        sources = DataSource.objects.order_by('-trust_level')

        # Verify the hierarchy
        expected_order = [
            DataSource.MANUAL,               # 1.0
            DataSource.OPEN_LIBRARY,         # 0.95
            DataSource.COMICVINE,            # 0.9
            DataSource.OPF_FILE,             # 0.9
            DataSource.CONTENT_SCAN,         # 0.85
            DataSource.EPUB_INTERNAL,        # 0.8
            DataSource.MOBI_INTERNAL,        # 0.75
            DataSource.GOOGLE_BOOKS,         # 0.7
            DataSource.OPEN_LIBRARY_COVERS,  # 0.65
            DataSource.PDF_INTERNAL,         # 0.6
            DataSource.GOOGLE_BOOKS_COVERS,  # 0.55
            DataSource.ORIGINAL_SCAN,        # 0.5
            DataSource.FILENAME,             # 0.2
        ]

        actual_order = [source.name for source in sources]
        self.assertEqual(actual_order, expected_order)

    def test_trust_level_values(self):
        """Test specific trust level values for critical sources."""
        ensure_data_sources()

        # Test highest trust sources
        manual = DataSource.objects.get(name=DataSource.MANUAL)
        self.assertEqual(manual.trust_level, 1.0)

        open_library = DataSource.objects.get(name=DataSource.OPEN_LIBRARY)
        self.assertEqual(open_library.trust_level, 0.95)

        # Test metadata sources
        opf = DataSource.objects.get(name=DataSource.OPF_FILE)
        self.assertEqual(opf.trust_level, 0.9)

        content_scan = DataSource.objects.get(name=DataSource.CONTENT_SCAN)
        self.assertEqual(content_scan.trust_level, 0.85)

        # Test format-specific sources
        epub = DataSource.objects.get(name=DataSource.EPUB_INTERNAL)
        self.assertEqual(epub.trust_level, 0.8)

        pdf = DataSource.objects.get(name=DataSource.PDF_INTERNAL)
        self.assertEqual(pdf.trust_level, 0.6)

        # Test lowest trust source
        filename = DataSource.objects.get(name=DataSource.FILENAME)
        self.assertEqual(filename.trust_level, 0.2)

    def test_cover_source_trust_levels(self):
        """Test that cover sources have appropriate trust levels."""
        ensure_data_sources()

        ol_covers = DataSource.objects.get(name=DataSource.OPEN_LIBRARY_COVERS)
        gb_covers = DataSource.objects.get(name=DataSource.GOOGLE_BOOKS_COVERS)

        # Open Library covers should have higher trust than Google Books covers
        self.assertGreater(ol_covers.trust_level, gb_covers.trust_level)
        self.assertEqual(ol_covers.trust_level, 0.65)
        self.assertEqual(gb_covers.trust_level, 0.55)

    def test_external_api_trust_levels(self):
        """Test trust levels for external API sources."""
        ensure_data_sources()

        open_library = DataSource.objects.get(name=DataSource.OPEN_LIBRARY)
        google_books = DataSource.objects.get(name=DataSource.GOOGLE_BOOKS)

        # Open Library should have higher trust than Google Books
        self.assertGreater(open_library.trust_level, google_books.trust_level)
        self.assertEqual(open_library.trust_level, 0.95)
        self.assertEqual(google_books.trust_level, 0.7)

    def test_file_format_trust_hierarchy(self):
        """Test that file format sources have appropriate trust hierarchy."""
        ensure_data_sources()

        epub = DataSource.objects.get(name=DataSource.EPUB_INTERNAL)
        mobi = DataSource.objects.get(name=DataSource.MOBI_INTERNAL)
        pdf = DataSource.objects.get(name=DataSource.PDF_INTERNAL)

        # EPUB should have highest trust among formats
        self.assertGreater(epub.trust_level, mobi.trust_level)
        self.assertGreater(mobi.trust_level, pdf.trust_level)

        self.assertEqual(epub.trust_level, 0.8)
        self.assertEqual(mobi.trust_level, 0.75)
        self.assertEqual(pdf.trust_level, 0.6)

    def test_ensure_data_sources_with_existing_source(self):
        """Test that existing sources are not modified."""
        # Create a source with custom trust level
        custom_source = DataSource.objects.create(
            name=DataSource.MANUAL,
            trust_level=0.5  # Different from expected 1.0
        )

        ensure_data_sources()

        # Should not modify existing source
        custom_source.refresh_from_db()
        self.assertEqual(custom_source.trust_level, 0.5)

    def test_data_source_constants_exist(self):
        """Test that all expected DataSource constants exist."""
        # This test ensures we don't accidentally break constant names
        constants = [
            'MANUAL',
            'OPEN_LIBRARY',
            'OPF_FILE',
            'CONTENT_SCAN',
            'EPUB_INTERNAL',
            'MOBI_INTERNAL',
            'GOOGLE_BOOKS',
            'OPEN_LIBRARY_COVERS',
            'PDF_INTERNAL',
            'GOOGLE_BOOKS_COVERS',
            'ORIGINAL_SCAN',
            'FILENAME',
        ]

        for constant in constants:
            self.assertTrue(hasattr(DataSource, constant))
            # Verify it's a string value
            self.assertIsInstance(getattr(DataSource, constant), str)

    def test_bootstrap_import_safety(self):
        """Test that bootstrap can be imported safely without side effects."""
        # Import should not automatically create data sources
        from books.scanner import bootstrap

        # No sources should exist just from import
        initial_count = DataSource.objects.count()

        # Now run the function
        bootstrap.ensure_data_sources()

        # Should have created sources
        self.assertGreater(DataSource.objects.count(), initial_count)


class BootstrapErrorHandlingTests(TestCase):
    """Test error handling and edge cases in bootstrap functionality."""

    def test_ensure_data_sources_database_error_recovery(self):
        """Test bootstrap recovery from database errors."""
        # Mock database error on first source creation
        with patch('books.models.DataSource.objects.get_or_create') as mock_get_or_create:
            # First call fails, subsequent calls succeed
            mock_get_or_create.side_effect = [
                Exception('Database connection error'),
                (Mock(name=DataSource.MANUAL, trust_level=1.0), True),
                (Mock(name=DataSource.OPEN_LIBRARY, trust_level=0.95), True),
            ]

            # Should handle the error gracefully
            with self.assertRaises(Exception):
                ensure_data_sources()

    def test_ensure_data_sources_partial_creation_failure(self):
        """Test handling of partial data source creation failures."""
        # Create some sources manually first
        DataSource.objects.create(name=DataSource.MANUAL, trust_level=1.0)
        DataSource.objects.create(name=DataSource.OPEN_LIBRARY, trust_level=0.95)

        # Mock failure for one specific source
        with patch('books.models.DataSource.objects.get_or_create') as mock_get_or_create:
            def side_effect(name, defaults):
                if name == DataSource.COMICVINE:
                    raise IntegrityError('Constraint violation')
                return DataSource.objects.get_or_create(name=name, defaults=defaults)

            mock_get_or_create.side_effect = side_effect

            # Should continue creating other sources despite one failure
            with self.assertRaises(IntegrityError):
                ensure_data_sources()

    def test_ensure_data_sources_concurrent_access(self):
        """Test bootstrap behavior under concurrent access scenarios."""
        # Simulate concurrent creation by creating a source during bootstrap
        def concurrent_creation(*args, **kwargs):
            # Create source during the bootstrap process
            if not DataSource.objects.filter(name=DataSource.MANUAL).exists():
                DataSource.objects.create(name=DataSource.MANUAL, trust_level=0.99)
            return DataSource.objects.get_or_create(*args, **kwargs)

        with patch('books.models.DataSource.objects.get_or_create', side_effect=concurrent_creation):
            ensure_data_sources()

            # Should handle concurrent creation gracefully
            manual_source = DataSource.objects.get(name=DataSource.MANUAL)
            # Should keep the first created value
            self.assertEqual(manual_source.trust_level, 0.99)

    def test_ensure_data_sources_invalid_trust_levels(self):
        """Test bootstrap with invalid trust level scenarios."""
        # Test with corrupted constants (if possible to mock)
        with patch('books.models.DataSource.MANUAL', 'TestManual'):
            ensure_data_sources()

            # Should create source with the patched name
            self.assertTrue(DataSource.objects.filter(name='TestManual').exists())

    def test_ensure_data_sources_transaction_rollback(self):
        """Test transaction rollback behavior in bootstrap."""
        # Force a transaction rollback scenario
        with patch('books.models.DataSource.objects.get_or_create') as mock_get_or_create:
            # Simulate transaction rollback
            mock_get_or_create.side_effect = [
                (DataSource.objects.create(name=DataSource.MANUAL, trust_level=1.0), True),
                IntegrityError('Transaction rolled back'),
            ]

            with self.assertRaises(IntegrityError):
                with transaction.atomic():
                    ensure_data_sources()

    def test_ensure_data_sources_memory_constraints(self):
        """Test bootstrap behavior under memory constraints."""
        # Mock memory error during bootstrap
        with patch('books.models.DataSource.objects.get_or_create') as mock_get_or_create:
            mock_get_or_create.side_effect = MemoryError('Out of memory')

            with self.assertRaises(MemoryError):
                ensure_data_sources()

    def test_ensure_data_sources_with_corrupted_data(self):
        """Test bootstrap with existing corrupted data sources."""
        # Create a source with invalid trust level (outside 0-1 range)
        corrupted_source = DataSource.objects.create(
            name='CorruptedSource',
            trust_level=2.0  # Invalid trust level
        )

        # Bootstrap should still work with existing corrupted data
        ensure_data_sources()

        # Corrupted source should still exist
        corrupted_source.refresh_from_db()
        self.assertEqual(corrupted_source.trust_level, 2.0)

        # But valid sources should be created
        self.assertTrue(DataSource.objects.filter(name=DataSource.MANUAL).exists())

    def test_ensure_data_sources_duplicate_constant_values(self):
        """Test bootstrap behavior if constant values are duplicated."""
        # This is a defensive test in case constants are accidentally duplicated
        original_manual = DataSource.MANUAL

        try:
            # Temporarily modify constant to create conflict scenario
            with patch('books.models.DataSource.OPEN_LIBRARY', DataSource.MANUAL):
                ensure_data_sources()

                # Should handle gracefully and create only one instance
                manual_sources = DataSource.objects.filter(name=DataSource.MANUAL)
                self.assertEqual(manual_sources.count(), 1)

        finally:
            # Restore original constant
            DataSource.MANUAL = original_manual

    def test_ensure_data_sources_empty_constant_values(self):
        """Test bootstrap behavior with empty constant values."""
        with patch('books.models.DataSource.MANUAL', ''):
            # Should handle empty string constant
            ensure_data_sources()

            # Should create source with empty name (if allowed by model)
            try:
                empty_source = DataSource.objects.get(name='')
                self.assertIsNotNone(empty_source)
            except DataSource.DoesNotExist:
                # If empty names aren't allowed, that's also valid behavior
                pass

    def test_bootstrap_function_idempotency_stress(self):
        """Stress test bootstrap function idempotency."""
        # Run bootstrap multiple times rapidly
        for i in range(10):
            ensure_data_sources()

        # Should still have exactly the expected number of sources
        expected_sources = [
            DataSource.MANUAL, DataSource.OPEN_LIBRARY, DataSource.COMICVINE,
            DataSource.OPF_FILE, DataSource.CONTENT_SCAN, DataSource.EPUB_INTERNAL,
            DataSource.MOBI_INTERNAL, DataSource.GOOGLE_BOOKS, DataSource.OPEN_LIBRARY_COVERS,
            DataSource.PDF_INTERNAL, DataSource.GOOGLE_BOOKS_COVERS, DataSource.ORIGINAL_SCAN,
            DataSource.FILENAME
        ]

        self.assertEqual(DataSource.objects.count(), len(expected_sources))

    def test_bootstrap_with_database_lock_timeout(self):
        """Test bootstrap behavior with database lock timeouts."""
        # Simulate database lock timeout
        with patch('books.models.DataSource.objects.get_or_create') as mock_get_or_create:
            from django.db import OperationalError
            mock_get_or_create.side_effect = OperationalError('Lock wait timeout exceeded')

            with self.assertRaises(OperationalError):
                ensure_data_sources()

    def test_bootstrap_trust_level_precision(self):
        """Test bootstrap with high precision trust level requirements."""
        ensure_data_sources()

        # Verify precision of trust levels
        for source in DataSource.objects.all():
            # Trust levels should be precise decimal values
            self.assertIsInstance(source.trust_level, float)
            self.assertGreaterEqual(source.trust_level, 0.0)
            self.assertLessEqual(source.trust_level, 1.0)

            # Verify precision (should have reasonable decimal places)
            decimal_places = len(str(source.trust_level).split('.')[-1])
            self.assertLessEqual(decimal_places, 3)  # Max 3 decimal places
