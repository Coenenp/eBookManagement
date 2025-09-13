"""Tests for scanner bootstrap functionality.

This module tests the data source bootstrapping utilities that ensure
default data sources are created with appropriate confidence levels.
"""

from django.test import TestCase

from books.models import DataSource
from books.scanner.bootstrap import ensure_data_sources


class BootstrapTests(TestCase):
    """Test cases for bootstrap functionality."""

    def test_ensure_data_sources_creates_all_sources(self):
        """Test that ensure_data_sources creates all expected data sources."""
        # Verify no sources exist initially
        self.assertEqual(DataSource.objects.count(), 0)

        # Run bootstrap
        ensure_data_sources()

        # Check that all expected sources were created
        expected_sources = [
            (DataSource.MANUAL, 1.0),
            (DataSource.OPEN_LIBRARY, 0.95),
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
