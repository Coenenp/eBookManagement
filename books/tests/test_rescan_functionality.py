"""
Tests for the external metadata rescan functionality.
"""

import json
import tempfile
import shutil
import os
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from books.models import FinalMetadata, BookTitle, BookAuthor, Author, DataSource, ScanFolder
from books.tests.test_helpers import create_test_book_with_file, create_test_scan_folder


class RescanFunctionalityTestCase(TestCase):
    """Test cases for the external metadata rescan feature."""

    def setUp(self):
        """Set up test data."""
        self.client = Client()

        # Create and login a user for authentication
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.client.login(username='testuser', password='testpass123')

        # Create required scan folder with temporary directory
        self.temp_dir = tempfile.mkdtemp()
        self.scan_folder = ScanFolder.objects.create(
            name="Test Scan Folder",
            path=self.temp_dir,
            content_type="ebooks"
        )

        # Create a test book
        self.book = create_test_book_with_file(
            file_path=os.path.join(self.temp_dir, "book.epub"),
            file_format="epub",
            file_size=1024,
            scan_folder=self.scan_folder
        )

        # Create a data source
        self.source, created = DataSource.objects.get_or_create(
            name=DataSource.MANUAL,
            defaults={'trust_level': 0.8}
        )

        # Create some initial metadata
        BookTitle.objects.create(
            book=self.book,
            title="Test Book Title",
            source=self.source,
            confidence=0.8
        )

        author = Author.objects.create(name="Test Author")
        BookAuthor.objects.create(
            book=self.book,
            author=author,
            source=self.source,
            confidence=0.8
        )

        # Create final metadata
        FinalMetadata.objects.create(
            book=self.book,
            final_title="Test Book Title",
            final_author="Test Author",
            isbn="9780062498557",
            is_reviewed=True
        )

    def tearDown(self):
        """Clean up test data."""
        try:
            shutil.rmtree(self.temp_dir)
        except (OSError, FileNotFoundError):
            pass

    def test_rescan_endpoint_exists(self):
        """Test that the rescan endpoint is accessible."""
        url = reverse('books:rescan_external_metadata', kwargs={'book_id': self.book.id})

        # Test with valid JSON data
        data = {
            'sources': ['google', 'openlibrary'],
            'title_search': 'Test Book Title',
            'author_search': 'Test Author'
        }

        response = self.client.post(
            url,
            data=json.dumps(data),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 200)

        # Check response structure
        response_data = response.json()
        self.assertIn('success', response_data)
        self.assertIn('message', response_data)
        self.assertIn('search_terms', response_data)
        self.assertIn('sources_queried', response_data)

    def test_rescan_with_form_data(self):
        """Test rescan functionality with form data."""
        url = reverse('books:rescan_external_metadata', kwargs={'book_id': self.book.id})

        data = {
            'sources[]': ['google'],
            'clear_existing': 'false',
            'force_refresh': 'false',
            'title_override': 'Custom Title',
            'author_override': 'Custom Author'
        }

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)

        response_data = response.json()
        self.assertTrue(response_data['success'])

    def test_rescan_invalid_book(self):
        """Test rescan with non-existent book ID."""
        url = reverse('books:rescan_external_metadata', kwargs={'book_id': 999})

        data = {
            'sources': ['google'],
            'title_search': 'Test',
            'author_search': 'Test'
        }

        response = self.client.post(
            url,
            data=json.dumps(data),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 404)

    def test_search_term_extraction(self):
        """Test that search terms are properly extracted from final metadata."""
        url = reverse('books:rescan_external_metadata', kwargs={'book_id': self.book.id})

        data = {
            'sources': ['google'],
            # No search terms provided - should use final metadata
        }

        response = self.client.post(
            url,
            data=json.dumps(data),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 200)
        response_data = response.json()

        # Should use final metadata for search terms
        search_terms = response_data['search_terms']
        self.assertEqual(search_terms['title'], 'Test Book Title')
        self.assertEqual(search_terms['author'], 'Test Author')
        self.assertEqual(search_terms['isbn'], '9780062498557')

    def test_metadata_counts(self):
        """Test that before/after metadata counts are tracked."""
        url = reverse('books:rescan_external_metadata', kwargs={'book_id': self.book.id})

        data = {
            'sources': ['google'],
            'title_search': 'Test Title',
            'author_search': 'Test Author'
        }

        response = self.client.post(
            url,
            data=json.dumps(data),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 200)
        response_data = response.json()

        # Check that counts are present
        self.assertIn('before_counts', response_data)
        self.assertIn('after_counts', response_data)
        self.assertIn('added_counts', response_data)

        # Check count structure
        before_counts = response_data['before_counts']
        self.assertIn('titles', before_counts)
        self.assertIn('authors', before_counts)
        self.assertIn('genres', before_counts)
        self.assertIn('series', before_counts)
        self.assertIn('publishers', before_counts)
        self.assertIn('covers', before_counts)
        self.assertIn('metadata', before_counts)


class ExternalQueryFunctionTestCase(TestCase):
    """Test cases for the external query function."""

    def setUp(self):
        """Set up test data"""
        self.scan_folder = create_test_scan_folder(name="Test Scan Folder")

        self.book = create_test_book_with_file(
            file_path="/test/path/book.epub",
            file_format="epub",
            file_size=1024000,
            scan_folder=self.scan_folder
        )

    def test_query_metadata_and_covers_with_terms_function_exists(self):
        """Test that the query function exists and is callable."""
        from books.scanner.external import query_metadata_and_covers_with_terms

        # Should not raise an error
        result = query_metadata_and_covers_with_terms(
            book=self.book,
            search_title='Test Book',
            search_author='Test Author',
            search_isbn=''
        )

        # Result should be a tuple
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 2)  # (metadata_list, covers_list)
