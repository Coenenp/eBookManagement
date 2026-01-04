"""
Test OPF generation functionality
"""
import os
import tempfile

from django.test import TestCase

from books.models import FinalMetadata
from books.tests.test_helpers import create_test_book_with_file, create_test_scan_folder
from books.utils.opf_generator import generate_opf_from_final_metadata, get_opf_filename, save_opf_file


class OPFGenerationTests(TestCase):
    """Test OPF generation utilities"""

    def setUp(self):
        """Set up test data"""
        self.scan_folder = create_test_scan_folder(name="Test Scan Folder")

        self.book = create_test_book_with_file(
            file_path="/test/path/book.epub",
            file_format="epub",
            file_size=1024000,
            scan_folder=self.scan_folder
        )

        self.final_metadata = FinalMetadata.objects.create(
            book=self.book,
            final_title="Test Book Title",
            final_author="John Doe",
            final_series="Test Series",
            final_series_number="1",
            final_publisher="Test Publisher",
            description="A test book description",
            isbn="9781234567890",
            publication_year=2023,
            language="en",
            is_reviewed=True,
            overall_confidence=0.85
        )

    def test_generate_opf_from_final_metadata(self):
        """Test OPF XML generation from final metadata"""
        opf_content = generate_opf_from_final_metadata(self.final_metadata)

        self.assertIsNotNone(opf_content)
        self.assertIn('<?xml version', opf_content)
        self.assertIn('Test Book Title', opf_content)
        self.assertIn('John Doe', opf_content)
        self.assertIn('Test Series', opf_content)
        self.assertIn('Test Publisher', opf_content)
        self.assertIn('9781234567890', opf_content)
        self.assertIn('ebook-manager:reviewed', opf_content)

    def test_generate_opf_with_ebook_filename(self):
        """Test OPF generation with ebook filename reference"""
        opf_content = generate_opf_from_final_metadata(
            self.final_metadata,
            ebook_filename="test_book.epub"
        )

        self.assertIsNotNone(opf_content)
        self.assertIn('test_book.epub', opf_content)
        self.assertIn('application/epub+zip', opf_content)

    def test_save_opf_file(self):
        """Test saving OPF to file"""
        with tempfile.TemporaryDirectory() as temp_dir:
            opf_path = os.path.join(temp_dir, "test_book.opf")

            success = save_opf_file(self.final_metadata, opf_path, "test_book.epub")

            self.assertTrue(success)
            self.assertTrue(os.path.exists(opf_path))

            # Verify file content
            with open(opf_path, 'r', encoding='utf-8') as f:
                content = f.read()
                self.assertIn('Test Book Title', content)
                self.assertIn('John Doe', content)

    def test_get_opf_filename(self):
        """Test OPF filename generation"""
        self.assertEqual(get_opf_filename("book.epub"), "book.opf")
        self.assertEqual(get_opf_filename("my_book.pdf"), "my_book.opf")
        self.assertEqual(get_opf_filename("test.mobi"), "test.opf")

    def test_opf_generation_with_minimal_metadata(self):
        """Test OPF generation with minimal required metadata"""
        minimal_metadata = FinalMetadata.objects.create(
            book=create_test_book_with_file(
            file_path="/test/minimal.epub",
                file_format="epub",
                file_size=1000,
                scan_folder=self.scan_folder
        ),
            final_title="Minimal Book",
            is_reviewed=True,  # Prevent auto-update from overriding our test values
            overall_confidence=0.5
        )

        opf_content = generate_opf_from_final_metadata(minimal_metadata)

        self.assertIsNotNone(opf_content)
        self.assertIn('Minimal Book', opf_content)
        self.assertIn('Unknown Author', opf_content)  # Default author
        self.assertIn('ebook-manager:', opf_content)  # Should include our metadata

    def test_opf_generation_handles_series_number_types(self):
        """Test OPF generation handles different series number formats"""
        # Test with float series number
        self.final_metadata.final_series_number = "2.5"
        self.final_metadata.save()

        opf_content = generate_opf_from_final_metadata(self.final_metadata)
        self.assertIn('2.5', opf_content)

        # Test with invalid series number
        self.final_metadata.final_series_number = "invalid"
        self.final_metadata.save()

        opf_content = generate_opf_from_final_metadata(self.final_metadata)
        self.assertIsNotNone(opf_content)  # Should not crash

        # Test with None series number
        self.final_metadata.final_series_number = None
        self.final_metadata.save()

        opf_content = generate_opf_from_final_metadata(self.final_metadata)
        self.assertIsNotNone(opf_content)  # Should not crash

    def test_opf_namespaces_and_structure(self):
        """Test that OPF has correct namespaces and structure"""
        opf_content = generate_opf_from_final_metadata(self.final_metadata)

        # Check for required namespaces
        self.assertIn('xmlns:opf="http://www.idpf.org/2007/opf"', opf_content)
        self.assertIn('xmlns:dc="http://purl.org/dc/elements/1.1/"', opf_content)

        # Check for required sections
        self.assertIn('<opf:metadata>', opf_content)
        self.assertIn('<opf:manifest>', opf_content)
        self.assertIn('<opf:spine>', opf_content)

        # Check for Dublin Core elements
        self.assertIn('<dc:title>', opf_content)
        self.assertIn('<dc:creator', opf_content)
        self.assertIn('<dc:identifier', opf_content)
        self.assertIn('<dc:language>', opf_content)
