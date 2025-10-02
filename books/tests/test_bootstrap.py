"""Tests for scanner bootstrap functionality."""
from django.test import TestCase
from books.models import DataSource
from books.scanner.bootstrap import ensure_data_sources


class BootstrapTests(TestCase):
    """Test cases for bootstrap functionality."""

    def test_ensure_data_sources_creates_all_sources(self):
        """Test that ensure_data_sources creates all expected data sources."""
        ensure_data_sources()
        expected_sources = [
            (DataSource.MANUAL, 1.0), (DataSource.OPEN_LIBRARY, 0.95),
            (DataSource.COMICVINE, 0.9), (DataSource.OPF_FILE, 0.9),
            (DataSource.CONTENT_SCAN, 0.85), (DataSource.EPUB_INTERNAL, 0.8),
            (DataSource.MOBI_INTERNAL, 0.75), (DataSource.GOOGLE_BOOKS, 0.7),
            (DataSource.OPEN_LIBRARY_COVERS, 0.65), (DataSource.PDF_INTERNAL, 0.6),
            (DataSource.GOOGLE_BOOKS_COVERS, 0.55), (DataSource.INITIAL_SCAN, 0.2),
        ]
        self.assertEqual(DataSource.objects.count(), len(expected_sources))
        for name, expected_trust in expected_sources:
            source = DataSource.objects.get(name=name)
            self.assertEqual(source.trust_level, expected_trust)

    def test_ensure_data_sources_idempotent(self):
        """Test that ensure_data_sources can be called multiple times safely."""
        ensure_data_sources()
        initial_count = DataSource.objects.count()
        ensure_data_sources()
        self.assertEqual(DataSource.objects.count(), initial_count)

    def test_trust_level_hierarchy(self):
        """Test that trust levels follow the expected hierarchy."""
        ensure_data_sources()
        sources = DataSource.objects.order_by('-trust_level')
        expected_order = [
            DataSource.MANUAL, DataSource.OPEN_LIBRARY, DataSource.COMICVINE,
            DataSource.OPF_FILE, DataSource.CONTENT_SCAN, DataSource.EPUB_INTERNAL,
            DataSource.MOBI_INTERNAL, DataSource.GOOGLE_BOOKS, DataSource.OPEN_LIBRARY_COVERS,
            DataSource.PDF_INTERNAL, DataSource.GOOGLE_BOOKS_COVERS, DataSource.INITIAL_SCAN,
        ]
        actual_order = [source.name for source in sources]
        self.assertEqual(actual_order, expected_order)

    def test_trust_level_values(self):
        """Test specific trust level values for critical sources."""
        ensure_data_sources()
        self.assertEqual(DataSource.objects.get(name=DataSource.MANUAL).trust_level, 1.0)
        self.assertEqual(DataSource.objects.get(name=DataSource.OPEN_LIBRARY).trust_level, 0.95)
        self.assertEqual(DataSource.objects.get(name=DataSource.OPF_FILE).trust_level, 0.9)
        self.assertEqual(DataSource.objects.get(name=DataSource.EPUB_INTERNAL).trust_level, 0.8)
        self.assertEqual(DataSource.objects.get(name=DataSource.INITIAL_SCAN).trust_level, 0.2)

    def test_cover_source_trust_levels(self):
        """Test that cover sources have appropriate trust levels."""
        ensure_data_sources()
        ol_covers = DataSource.objects.get(name=DataSource.OPEN_LIBRARY_COVERS)
        gb_covers = DataSource.objects.get(name=DataSource.GOOGLE_BOOKS_COVERS)
        self.assertGreater(ol_covers.trust_level, gb_covers.trust_level)
        self.assertEqual(ol_covers.trust_level, 0.65)
        self.assertEqual(gb_covers.trust_level, 0.55)

    def test_external_api_trust_levels(self):
        """Test trust levels for external API sources."""
        ensure_data_sources()
        open_library = DataSource.objects.get(name=DataSource.OPEN_LIBRARY)
        google_books = DataSource.objects.get(name=DataSource.GOOGLE_BOOKS)
        self.assertGreater(open_library.trust_level, google_books.trust_level)

    def test_file_format_trust_hierarchy(self):
        """Test that file format sources have appropriate trust hierarchy."""
        ensure_data_sources()
        epub = DataSource.objects.get(name=DataSource.EPUB_INTERNAL)
        mobi = DataSource.objects.get(name=DataSource.MOBI_INTERNAL)
        pdf = DataSource.objects.get(name=DataSource.PDF_INTERNAL)
        self.assertGreater(epub.trust_level, mobi.trust_level)
        self.assertGreater(mobi.trust_level, pdf.trust_level)

    def test_ensure_data_sources_with_existing_source(self):
        """Test that existing sources are not modified."""
        custom_source, _ = DataSource.objects.get_or_create(
            name=DataSource.MANUAL, defaults={'trust_level': 0.5}
        )
        if custom_source.trust_level != 0.5:
            custom_source.trust_level = 0.5
            custom_source.save()
        ensure_data_sources()
        custom_source.refresh_from_db()
        self.assertEqual(custom_source.trust_level, 0.5)

    def test_data_source_constants_exist(self):
        """Test that all expected DataSource constants exist."""
        constants = [
            'MANUAL', 'OPEN_LIBRARY', 'OPF_FILE', 'CONTENT_SCAN',
            'EPUB_INTERNAL', 'MOBI_INTERNAL', 'GOOGLE_BOOKS',
            'OPEN_LIBRARY_COVERS', 'PDF_INTERNAL', 'GOOGLE_BOOKS_COVERS',
            'COMICVINE', 'INITIAL_SCAN',
        ]
        for constant in constants:
            self.assertTrue(hasattr(DataSource, constant))
            self.assertIsInstance(getattr(DataSource, constant), str)
