"""
Test cases for Book views
"""
from unittest.mock import patch, Mock
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone

from books.models import (
    Book, FinalMetadata, ScanFolder
)


class BookListViewTests(TestCase):
    """Test cases for book list view"""

    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.client = Client()
        self.client.force_login(self.user)

        self.scan_folder = ScanFolder.objects.create(
            path="/test/scan/folder",
            name="Test Scan Folder"
        )

        # Create test books
        for i in range(5):
            book = Book.objects.create(
                file_path=f"/test/path/book_{i+1}.epub",
                file_format="epub",
                file_size=1024000 + (i * 100000),
                scan_folder=self.scan_folder,
            )

            FinalMetadata.objects.create(
                book=book,
                final_title=f"Test Book {i+1}",
                final_author=f"Test Author {i+1}",
                is_reviewed=True  # Set all to reviewed to avoid auto-update issues
            )

    def test_book_list_view_loads(self):
        """Test that book list view loads successfully"""
        response = self.client.get(reverse('books:book_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test Book 1")

    def test_book_list_view_unauthenticated(self):
        """Test book list view access by unauthenticated user"""
        self.client.logout()
        response = self.client.get(reverse('books:book_list'))
        # Should redirect to login or return 403
        self.assertIn(response.status_code, [302, 401, 403])

    def test_book_list_pagination(self):
        """Test book list pagination"""
        response = self.client.get(reverse('books:book_list'))
        self.assertEqual(response.status_code, 200)

        # Check that pagination context exists
        self.assertIn('is_paginated', response.context)
        self.assertIn('page_obj', response.context)

    def test_book_list_filtering_by_review_status(self):
        """Test filtering books by review status"""
        # Test reviewed filter
        response = self.client.get(reverse('books:book_list') + '?needs_review=false')
        self.assertEqual(response.status_code, 200)

        # Should only show reviewed books
        books = response.context['books'] if 'books' in response.context else response.context['page_obj']
        for book in books:
            self.assertTrue(book.finalmetadata.is_reviewed)


class BookDetailViewTests(TestCase):
    """Test cases for book detail view"""

    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.client = Client()
        self.client.force_login(self.user)

        self.scan_folder = ScanFolder.objects.create(
            path="/test/scan/folder",
            name="Test Scan Folder"
        )

        self.book = Book.objects.create(

            file_path="/test/path/book.epub",
            file_format="epub",
            file_size=1024000,

            scan_folder=self.scan_folder,
            last_scanned=timezone.now()
        )

        self.final_metadata = FinalMetadata.objects.create(
            book=self.book,
            final_title="Test Book",
            final_author="Test Author",
            final_series="Test Series",
            is_reviewed=True  # Mark as reviewed to prevent auto-update
        )

    def test_book_detail_view_loads(self):
        """Test that book detail view loads successfully"""
        response = self.client.get(
            reverse('books:book_detail', kwargs={'pk': self.book.id})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test Book")

    def test_book_detail_view_context(self):
        """Test book detail view context variables"""
        response = self.client.get(
            reverse('books:book_detail', kwargs={'pk': self.book.id})
        )
        self.assertEqual(response.status_code, 200)

        # Check required context variables
        self.assertIn('book', response.context)
        self.assertIn('final_metadata', response.context)
        self.assertEqual(response.context['book'], self.book)

    def test_book_detail_navigation_context(self):
        """Test navigation context in book detail view"""
        # Create additional books for navigation testing
        Book.objects.create(

            file_path="/test/path/book2.epub",
            file_format="epub",
            file_size=1024000,

            scan_folder=self.scan_folder
        )

        response = self.client.get(
            reverse('books:book_detail', kwargs={'pk': self.book.id})
        )
        self.assertEqual(response.status_code, 200)

        # Check navigation context
        self.assertIn('prev_book_id', response.context)
        self.assertIn('next_book_id', response.context)
        self.assertIn('next_needsreview_id', response.context)

    def test_book_detail_nonexistent_book(self):
        """Test book detail view with nonexistent book"""
        response = self.client.get(
            reverse('books:book_detail', kwargs={'pk': 99999})
        )
        self.assertEqual(response.status_code, 404)


class BookSearchViewTests(TestCase):
    """Test cases for book search functionality"""

    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.client = Client()
        self.client.force_login(self.user)

        self.scan_folder = ScanFolder.objects.create(
            path="/test/scan/folder",
            name="Test Scan Folder"
        )

        # Create books with different titles
        book1 = Book.objects.create(

            file_path="/test/path/python.epub",
            file_format="epub",
            file_size=1024000,

            scan_folder=self.scan_folder
        )

        book2 = Book.objects.create(

            file_path="/test/path/django.epub",
            file_format="epub",
            file_size=1024000,

            scan_folder=self.scan_folder
        )

        FinalMetadata.objects.create(
            book=book1,
            final_title="Python Programming",
            final_author="Python Author",
            is_reviewed=True
        )

        FinalMetadata.objects.create(
            book=book2,
            final_title="Django Web Framework",
            final_author="Django Author",
            is_reviewed=True
        )

    def test_book_search_by_title(self):
        """Test searching books by title"""
        response = self.client.get(reverse('books:book_list') + '?search_query=Python')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Python Programming")
        self.assertNotContains(response, "Django Web Framework")

    def test_book_search_by_author(self):
        """Test searching books by author"""
        response = self.client.get(reverse('books:book_list') + '?search_query=Django Author')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Django Web Framework")
        self.assertNotContains(response, "Python Programming")

    def test_empty_search_query(self):
        """Test empty search query returns all books"""
        response = self.client.get(reverse('books:book_list') + '?search_query=')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Python Programming")
        self.assertContains(response, "Django Web Framework")


class TriggerScanViewTests(TestCase):
    """Test cases for the TriggerScanView."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.client = Client()
        self.client.force_login(self.user)

        from books.models import ScanFolder
        self.scan_folder = ScanFolder.objects.create(
            path="/test/folder",
            is_active=True
        )

    def test_trigger_scan_view_requires_login(self):
        """Test that trigger scan view requires authentication."""
        self.client.logout()
        response = self.client.get(reverse('books:trigger_scan'))
        self.assertIn(response.status_code, [302, 401, 403])

    def test_trigger_scan_view_get(self):
        """Test GET request to trigger scan view."""
        response = self.client.get(reverse('books:trigger_scan'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Trigger Scan")

    def test_trigger_scan_view_no_active_folders(self):
        """Test scan trigger with no active folders."""
        self.scan_folder.is_active = False
        self.scan_folder.save()

        with patch('subprocess.Popen') as mock_popen, \
             patch('books.views.settings') as mock_settings:
            mock_settings.BASE_DIR = "/project"
            mock_popen.return_value = Mock()

            response = self.client.post(reverse('books:trigger_scan'), {
                'scan_mode': 'normal'
            })

            self.assertEqual(response.status_code, 302)


class ViewFilteringTests(TestCase):
    """Test filtering functionality across views."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.client = Client()
        self.client.force_login(self.user)

        from books.models import DataSource
        self.filename_source = DataSource.objects.create(
            name=DataSource.FILENAME,
            trust_level=0.2
        )

        self.scan_folder = ScanFolder.objects.create(
            path="/test/folder",
            is_active=True
        )

    def test_book_list_confidence_filtering(self):
        """Test filtering by confidence level."""
        # Create book with high confidence
        book_high = Book.objects.create(
            file_path="/test/folder/high.epub",
            file_format="epub",
            file_size=1000,
            scan_folder=self.scan_folder
        )

        FinalMetadata.objects.create(
            book=book_high,
            final_title="High Confidence Book",
            final_title_confidence=0.9,  # 0.9 * 0.3 = 0.27
            final_author_confidence=0.9,  # 0.9 * 0.3 = 0.27
            final_series_confidence=0.9,  # 0.9 * 0.15 = 0.135
            final_cover_confidence=0.9,   # 0.9 * 0.25 = 0.225
            # Total: 0.27 + 0.27 + 0.135 + 0.225 = 0.9
            overall_confidence=0.9,
            is_reviewed=True
        )

        # Create book with low confidence
        book_low = Book.objects.create(
            file_path="/test/folder/low.epub",
            file_format="epub",
            file_size=1000,
            scan_folder=self.scan_folder
        )

        FinalMetadata.objects.create(
            book=book_low,
            final_title="Low Confidence Book",
            final_title_confidence=0.3,  # Set individual confidence scores
            final_author_confidence=0.3,
            overall_confidence=0.3,
            is_reviewed=True
        )

        # Test high confidence filter
        response = self.client.get(reverse('books:book_list'), {'confidence': 'high'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "High Confidence Book")
        self.assertNotContains(response, "Low Confidence Book")

        # Test low confidence filter
        response = self.client.get(reverse('books:book_list'), {'confidence': 'low'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Low Confidence Book")
        self.assertNotContains(response, "High Confidence Book")

    def test_book_list_format_filtering(self):
        """Test filtering by file format."""
        # Create EPUB book
        book_epub = Book.objects.create(
            file_path="/test/folder/book.epub",
            file_format="epub",
            file_size=1000,
            scan_folder=self.scan_folder
        )

        # Create PDF book
        book_pdf = Book.objects.create(
            file_path="/test/folder/book.pdf",
            file_format="pdf",
            file_size=2000,
            scan_folder=self.scan_folder
        )

        # Test EPUB filter
        response = self.client.get(reverse('books:book_list'), {'file_format': 'epub'})
        self.assertEqual(response.status_code, 200)
        # Verify EPUB book is in results
        books = response.context['books'] if 'books' in response.context else response.context['page_obj']
        book_ids = [book.id for book in books]
        self.assertIn(book_epub.id, book_ids)
        self.assertNotIn(book_pdf.id, book_ids)

        # Test PDF filter
        response = self.client.get(reverse('books:book_list'), {'file_format': 'pdf'})
        self.assertEqual(response.status_code, 200)
        # Verify PDF book is in results
        books = response.context['books'] if 'books' in response.context else response.context['page_obj']
        book_ids = [book.id for book in books]
        self.assertIn(book_pdf.id, book_ids)
        self.assertNotIn(book_epub.id, book_ids)

    def test_book_list_missing_metadata_filter(self):
        """Test filtering by missing metadata."""
        # Create book without FinalMetadata
        book_missing = Book.objects.create(
            file_path="/test/folder/missing.epub",
            file_format="epub",
            file_size=1000,
            scan_folder=self.scan_folder
        )

        # Create book with FinalMetadata
        book_complete = Book.objects.create(
            file_path="/test/folder/complete.epub",
            file_format="epub",
            file_size=1000,
            scan_folder=self.scan_folder
        )

        FinalMetadata.objects.create(
            book=book_complete,
            final_title="Complete Book",
            is_reviewed=True
        )

        # Test missing metadata filter
        response = self.client.get(reverse('books:book_list'), {'missing': 'metadata'})
        self.assertEqual(response.status_code, 200)
        # Verify that book without metadata is in results
        books = response.context['books'] if 'books' in response.context else response.context['page_obj']
        book_ids = [book.id for book in books]
        self.assertIn(book_missing.id, book_ids)
        self.assertNotIn(book_complete.id, book_ids)

    def test_book_list_corrupted_filter(self):
        """Test filtering by corrupted status."""
        # Create corrupted book
        book_corrupted = Book.objects.create(
            file_path="/test/folder/corrupted.epub",
            file_format="epub",
            file_size=1000,
            scan_folder=self.scan_folder,
            is_corrupted=True
        )

        # Test corrupted filter
        response = self.client.get(reverse('books:book_list'), {'review_type': 'corrupted'})
        self.assertEqual(response.status_code, 200)
        # Verify that corrupted book is in results
        books = response.context['books'] if 'books' in response.context else response.context['page_obj']
        book_ids = [book.id for book in books]
        self.assertIn(book_corrupted.id, book_ids)

    def test_book_list_datasource_filter(self):
        """Test filtering by data source."""
        from books.models import DataSource, BookTitle, BookAuthor, Author

        # Create different data sources
        epub_source, _ = DataSource.objects.get_or_create(
            name=DataSource.EPUB_INTERNAL,
            defaults={'trust_level': 0.8}
        )

        filename_source, _ = DataSource.objects.get_or_create(
            name=DataSource.FILENAME,
            defaults={'trust_level': 0.3}
        )

        # Create authors
        epub_author = Author.objects.create(name="EPUB Author")
        filename_author = Author.objects.create(name="Filename Author")

        # Create books
        book1 = Book.objects.create(
            file_path="/test/folder/book1.epub",
            file_format="epub",
            file_size=1000,
            scan_folder=self.scan_folder
        )

        book2 = Book.objects.create(
            file_path="/test/folder/book2.epub",
            file_format="epub",
            file_size=1000,
            scan_folder=self.scan_folder
        )

        # Create metadata with different sources
        BookTitle.objects.create(
            book=book1,
            title="Book with EPUB metadata",
            source=epub_source,
            confidence=0.8
        )

        BookTitle.objects.create(
            book=book2,
            title="Book with filename metadata",
            source=filename_source,
            confidence=0.3
        )

        BookAuthor.objects.create(
            book=book1,
            author=epub_author,
            source=epub_source,
            confidence=0.8
        )

        BookAuthor.objects.create(
            book=book2,
            author=filename_author,
            source=filename_source,
            confidence=0.3
        )

        # Test filtering by EPUB metadata source
        response = self.client.get(reverse('books:book_list'), {'datasource': str(epub_source.id)})
        self.assertEqual(response.status_code, 200)
        books = response.context['books'] if 'books' in response.context else response.context['page_obj']
        book_ids = [book.id for book in books]
        self.assertIn(book1.id, book_ids)
        self.assertNotIn(book2.id, book_ids)

        # Test filtering by filename source
        response = self.client.get(reverse('books:book_list'), {'datasource': str(filename_source.id)})
        self.assertEqual(response.status_code, 200)
        books = response.context['books'] if 'books' in response.context else response.context['page_obj']
        book_ids = [book.id for book in books]
        self.assertIn(book2.id, book_ids)
        self.assertNotIn(book1.id, book_ids)

    def test_book_list_scan_folder_filter(self):
        """Test filtering by scan folder."""
        # Create additional scan folder
        scan_folder2 = ScanFolder.objects.create(
            path="/test/folder2",
            name="Test Folder 2",
            is_active=True
        )

        # Create books in different scan folders
        book1 = Book.objects.create(
            file_path="/test/folder/book1.epub",
            file_format="epub",
            file_size=1000,
            scan_folder=self.scan_folder
        )

        book2 = Book.objects.create(
            file_path="/test/folder2/book2.epub",
            file_format="epub",
            file_size=1000,
            scan_folder=scan_folder2
        )

        # Test filtering by first scan folder
        response = self.client.get(reverse('books:book_list'), {'scan_folder': str(self.scan_folder.id)})
        self.assertEqual(response.status_code, 200)
        books = response.context['books'] if 'books' in response.context else response.context['page_obj']
        book_ids = [book.id for book in books]
        self.assertIn(book1.id, book_ids)
        self.assertNotIn(book2.id, book_ids)

        # Test filtering by second scan folder
        response = self.client.get(reverse('books:book_list'), {'scan_folder': str(scan_folder2.id)})
        self.assertEqual(response.status_code, 200)
        books = response.context['books'] if 'books' in response.context else response.context['page_obj']
        book_ids = [book.id for book in books]
        self.assertIn(book2.id, book_ids)
        self.assertNotIn(book1.id, book_ids)

    def test_book_list_combined_filters(self):
        """Test combining datasource and scan folder filters."""
        from books.models import DataSource, BookTitle

        # Create second scan folder
        scan_folder2 = ScanFolder.objects.create(
            path="/test/folder2",
            name="Test Folder 2",
            is_active=True
        )

        # Create data source
        epub_source, _ = DataSource.objects.get_or_create(
            name=DataSource.EPUB_INTERNAL,
            defaults={'trust_level': 0.8}
        )

        # Create books
        book1 = Book.objects.create(
            file_path="/test/folder/book1.epub",
            file_format="epub",
            file_size=1000,
            scan_folder=self.scan_folder
        )

        book2 = Book.objects.create(
            file_path="/test/folder2/book2.epub",
            file_format="epub",
            file_size=1000,
            scan_folder=scan_folder2
        )

        # Both books have same data source
        BookTitle.objects.create(
            book=book1,
            title="Book 1",
            source=epub_source,
            confidence=0.8
        )

        BookTitle.objects.create(
            book=book2,
            title="Book 2",
            source=epub_source,
            confidence=0.8
        )

        # Test combined filters - should only return book1
        response = self.client.get(reverse('books:book_list'), {
            'datasource': str(epub_source.id),
            'scan_folder': str(self.scan_folder.id)
        })
        self.assertEqual(response.status_code, 200)
        books = response.context['books'] if 'books' in response.context else response.context['page_obj']
        book_ids = [book.id for book in books]
        self.assertIn(book1.id, book_ids)
        self.assertNotIn(book2.id, book_ids)


class ViewEdgeCaseTests(TestCase):
    """Test edge cases and potential issues in views."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.client = Client()
        self.client.force_login(self.user)

    def test_search_with_special_characters(self):
        """Test search with special characters."""
        response = self.client.get(reverse('books:book_list'), {
            'search_query': '<script>alert("xss")</script>'
        })
        self.assertEqual(response.status_code, 200)
        # Should be safely handled

    def test_search_with_unicode_characters(self):
        """Test search with unicode characters."""
        response = self.client.get(reverse('books:book_list'), {
            'search_query': 'Café Français 中文 العربية'
        })
        self.assertEqual(response.status_code, 200)

    def test_view_with_very_long_search_query(self):
        """Test search with extremely long query."""
        long_query = 'a' * 1000
        response = self.client.get(reverse('books:book_list'), {
            'search_query': long_query
        })
        self.assertEqual(response.status_code, 200)

    def test_book_list_with_empty_database(self):
        """Test book list view with no books."""
        response = self.client.get(reverse('books:book_list'))
        self.assertEqual(response.status_code, 200)
        # Should handle empty state gracefully

    def test_view_with_malformed_parameters(self):
        """Test views with malformed URL parameters."""
        # Test with non-integer book ID
        response = self.client.get('/books/detail/abc/')
        self.assertEqual(response.status_code, 404)

    def test_book_list_sorting_edge_cases(self):
        """Test sorting with edge cases."""
        # Test with invalid sort field
        response = self.client.get(reverse('books:book_list'), {'sort': 'invalid_field'})
        self.assertEqual(response.status_code, 200)
        # Should fall back to default sorting

    def test_empty_filter_values(self):
        """Test behavior with empty filter values."""
        response = self.client.get(reverse('books:book_list'), {
            'file_format': '',
            'language': '',
            'search_query': ''
        })
        self.assertEqual(response.status_code, 200)


class BookRenamerIntegrationTests(TestCase):
    """Integration tests for book renamer functionality"""

    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.client = Client()
        self.client.force_login(self.user)

        self.scan_folder = ScanFolder.objects.create(
            path="/test/scan/folder",
            name="Test Scan Folder"
        )

        self.book = Book.objects.create(
            file_path="/test/scan/folder/book.epub",
            file_format="epub",
            file_size=1024000,
            scan_folder=self.scan_folder,
        )

        self.final_metadata = FinalMetadata.objects.create(
            book=self.book,
            final_title="Test Book",
            final_author="Test Author",
            final_series="Test Series",
            final_series_number="1",
            is_reviewed=True
        )

    def test_book_renamer_view_integration(self):
        """Test that book renamer view works with actual data"""
        response = self.client.get(reverse('books:book_renamer'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test Book")

    def test_book_renamer_with_null_series_number(self):
        """Test book renamer handles books with null series numbers"""
        # Create book with null series number
        book_null = Book.objects.create(
            file_path="/test/scan/folder/book_null.epub",
            file_format="epub",
            file_size=1024000,
            scan_folder=self.scan_folder,
        )

        FinalMetadata.objects.create(
            book=book_null,
            final_title="Test Book Null",
            final_author="Test Author",
            final_series="Test Series",
            final_series_number=None,
            is_reviewed=True
        )

        response = self.client.get(reverse('books:book_renamer'))
        self.assertEqual(response.status_code, 200)
        # Should not crash and should include both books
        self.assertContains(response, "Test Book")
        self.assertContains(response, "Test Book Null")


class BookDetailNavigationTestCase(TestCase):
    """Test the prev/next navigation buttons in book detail view."""

    def setUp(self):
        """Set up test data."""
        self.client = Client()
        self.user = User.objects.create_user(username='testuser', password='testpass')

        # Create a scan folder
        self.scan_folder = ScanFolder.objects.create(
            name='Test Folder',
            path='/test/path',
            language='en'
        )

        # Create test books with proper Book model fields
        # Create books first
        self.book1 = Book.objects.create(
            id=1,
            file_path='/test/book1.epub',
            file_format='epub',
            scan_folder=self.scan_folder
        )

        self.book2 = Book.objects.create(
            id=2,
            file_path='/test/book2.epub',
            file_format='epub',
            scan_folder=self.scan_folder
        )

        self.book3 = Book.objects.create(
            id=3,
            file_path='/test/book3.epub',
            file_format='epub',
            scan_folder=self.scan_folder
        )

        # Now create FinalMetadata with manual update flag to prevent auto-overwriting
        # We need to manually handle the metadata creation to avoid the auto-update
        from books.models import FinalMetadata

        # For book1
        metadata1 = FinalMetadata.objects.filter(book=self.book1).first()
        if not metadata1:
            metadata1 = FinalMetadata(book=self.book1)
        metadata1.final_title = 'Book One'
        metadata1.final_author = 'Author One'
        metadata1.final_series = 'Series A'
        metadata1.final_series_number = '1'
        metadata1.is_reviewed = True
        metadata1._manual_update = True
        metadata1.save()
        self.metadata1 = metadata1

        # For book2
        metadata2 = FinalMetadata.objects.filter(book=self.book2).first()
        if not metadata2:
            metadata2 = FinalMetadata(book=self.book2)
        metadata2.final_title = 'Book Two'
        metadata2.final_author = 'Author One'
        metadata2.final_series = 'Series A'
        metadata2.final_series_number = '2'
        metadata2.is_reviewed = False
        metadata2._manual_update = True
        metadata2.save()
        self.metadata2 = metadata2

        # For book3
        metadata3 = FinalMetadata.objects.filter(book=self.book3).first()
        if not metadata3:
            metadata3 = FinalMetadata(book=self.book3)
        metadata3.final_title = 'Book Three'
        metadata3.final_author = 'Author Two'
        metadata3.final_series = 'Series B'
        metadata3.final_series_number = '1'
        metadata3.is_reviewed = False
        metadata3._manual_update = True
        metadata3.save()
        self.metadata3 = metadata3

    def test_basic_navigation_context(self):
        """Test that basic prev/next navigation context is provided."""
        self.client.login(username='testuser', password='testpass')

        # Test book2 (middle book) - should have both prev and next
        response = self.client.get(reverse('books:book_detail', kwargs={'pk': 2}))
        self.assertEqual(response.status_code, 200)

        context = response.context
        self.assertIsNotNone(context['prev_book'])
        self.assertIsNotNone(context['next_book'])
        self.assertEqual(context['prev_book'].id, 1)
        self.assertEqual(context['next_book'].id, 3)
        self.assertEqual(context['prev_book_id'], 1)
        self.assertEqual(context['next_book_id'], 3)

    def test_first_book_navigation(self):
        """Test navigation context for the first book."""
        self.client.login(username='testuser', password='testpass')

        response = self.client.get(reverse('books:book_detail', kwargs={'pk': 1}))
        self.assertEqual(response.status_code, 200)

        context = response.context
        self.assertIsNone(context['prev_book'])
        self.assertIsNotNone(context['next_book'])
        self.assertIsNone(context['prev_book_id'])
        self.assertEqual(context['next_book_id'], 2)

    def test_last_book_navigation(self):
        """Test navigation context for the last book."""
        self.client.login(username='testuser', password='testpass')

        response = self.client.get(reverse('books:book_detail', kwargs={'pk': 3}))
        self.assertEqual(response.status_code, 200)

        context = response.context
        self.assertIsNotNone(context['prev_book'])
        self.assertIsNone(context['next_book'])
        self.assertEqual(context['prev_book_id'], 2)
        self.assertIsNone(context['next_book_id'])

    def test_same_author_navigation(self):
        """Test navigation by same author."""
        self.client.login(username='testuser', password='testpass')

        # Test book1 - should have next author book (book2)
        response = self.client.get(reverse('books:book_detail', kwargs={'pk': 1}))
        context = response.context

        self.assertIsNone(context.get('prev_same_author'))
        self.assertIsNotNone(context.get('next_same_author'))
        self.assertEqual(context['next_same_author'].id, 2)

        # Test book2 - should have prev author book (book1)
        response = self.client.get(reverse('books:book_detail', kwargs={'pk': 2}))
        context = response.context

        self.assertIsNotNone(context.get('prev_same_author'))
        self.assertIsNone(context.get('next_same_author'))
        self.assertEqual(context['prev_same_author'].id, 1)

    def test_same_series_navigation(self):
        """Test navigation by same series."""
        self.client.login(username='testuser', password='testpass')

        # Test book1 - should have next series book (book2)
        response = self.client.get(reverse('books:book_detail', kwargs={'pk': 1}))
        context = response.context

        self.assertIsNone(context.get('prev_same_series'))
        self.assertIsNotNone(context.get('next_same_series'))
        self.assertEqual(context['next_same_series'].id, 2)

        # Test book2 - should have prev series book (book1)
        response = self.client.get(reverse('books:book_detail', kwargs={'pk': 2}))
        context = response.context

        self.assertIsNotNone(context.get('prev_same_series'))
        self.assertIsNone(context.get('next_same_series'))
        self.assertEqual(context['prev_same_series'].id, 1)

    def test_review_status_navigation(self):
        """Test navigation by review status."""
        self.client.login(username='testuser', password='testpass')

        # Test book1 (reviewed) - should have next unreviewed (book2)
        response = self.client.get(reverse('books:book_detail', kwargs={'pk': 1}))
        context = response.context

        self.assertIsNotNone(context.get('next_unreviewed'))
        self.assertEqual(context['next_unreviewed'].id, 2)

        # Test book2 (unreviewed) - should have next reviewed book (none in this case)
        response = self.client.get(reverse('books:book_detail', kwargs={'pk': 2}))
        context = response.context

        self.assertIsNotNone(context.get('prev_reviewed'))
        self.assertEqual(context['prev_reviewed'].id, 1)

    def test_needs_review_navigation(self):
        """Test navigation for books that need review."""
        self.client.login(username='testuser', password='testpass')

        # Test that unreviewed books show up in needs review navigation
        response = self.client.get(reverse('books:book_detail', kwargs={'pk': 1}))
        context = response.context

        # Book1 (reviewed) should have next needs review (book2)
        self.assertIsNotNone(context.get('next_needs_review'))
        self.assertEqual(context['next_needs_review'].id, 2)

        # Test book2 - should have next needs review (book3)
        response = self.client.get(reverse('books:book_detail', kwargs={'pk': 2}))
        context = response.context

        self.assertIsNotNone(context.get('next_needs_review'))
        self.assertEqual(context['next_needs_review'].id, 3)

    def test_navigation_buttons_in_template(self):
        """Test that navigation buttons appear correctly in the template."""
        self.client.login(username='testuser', password='testpass')

        response = self.client.get(reverse('books:book_detail', kwargs={'pk': 2}))
        self.assertEqual(response.status_code, 200)

        content = response.content.decode('utf-8')

        # Check for prev button
        self.assertIn('href="/book/1/"', content)
        self.assertIn('Previous Book', content)

        # Check for next button
        self.assertIn('href="/book/3/"', content)
        self.assertIn('Next Book', content)

        # Check for author navigation
        self.assertIn('Previous by Author One', content)

        # Check for series navigation
        self.assertIn('Series A', content)

    def test_navigation_with_placeholder_books(self):
        """Test that placeholder books are excluded from navigation."""
        # Create a placeholder book
        Book.objects.create(
            id=10,
            file_path='/test/placeholder.epub',
            file_format='placeholder',
            scan_folder=self.scan_folder,
            is_placeholder=True
        )

        self.client.login(username='testuser', password='testpass')

        # Test that placeholder book doesn't appear in navigation
        response = self.client.get(reverse('books:book_detail', kwargs={'pk': 3}))
        context = response.context

        # Next book should be None, not the placeholder
        self.assertIsNone(context['next_book'])
        self.assertIsNone(context['next_book_id'])

    def test_navigation_urls_work(self):
        """Test that navigation URLs actually work and return 200."""
        self.client.login(username='testuser', password='testpass')

        # Test basic navigation URLs
        response = self.client.get(reverse('books:book_detail', kwargs={'pk': 1}))
        self.assertEqual(response.status_code, 200)

        response = self.client.get(reverse('books:book_detail', kwargs={'pk': 2}))
        self.assertEqual(response.status_code, 200)

        response = self.client.get(reverse('books:book_detail', kwargs={'pk': 3}))
        self.assertEqual(response.status_code, 200)

    def test_navigation_with_missing_final_metadata(self):
        """Test navigation works even when final metadata is missing."""
        # Create a book without final metadata
        Book.objects.create(
            id=4,
            file_path='/test/book4.epub',
            file_format='epub',
            scan_folder=self.scan_folder
        )

        self.client.login(username='testuser', password='testpass')

        response = self.client.get(reverse('books:book_detail', kwargs={'pk': 4}))
        self.assertEqual(response.status_code, 200)

        context = response.context
        # Should still have basic navigation
        self.assertIsNotNone(context['prev_book'])
        self.assertEqual(context['prev_book'].id, 3)

        # But no author/series navigation since no final metadata
        self.assertIsNone(context.get('prev_same_author'))
        self.assertIsNone(context.get('next_same_author'))


class BookDetailNavigationIntegrationTestCase(TestCase):
    """Integration tests for the complete navigation flow."""

    def setUp(self):
        """Set up test data for integration tests."""
        self.client = Client()
        self.user = User.objects.create_user(username='testuser', password='testpass')

        # Create scan folder
        self.scan_folder = ScanFolder.objects.create(
            path='/test/path',
            language='en'
        )

        # Create multiple books for comprehensive testing
        self.books = []
        for i in range(1, 6):  # Create books 1-5
            book = Book.objects.create(
                id=i,
                file_path=f'/test/book{i}.epub',
                file_format='epub',
                scan_folder=self.scan_folder
            )
            self.books.append(book)

            # Create final metadata
            FinalMetadata.objects.create(
                book=book,
                final_title=f'Book {i}',
                final_author='Test Author',
                is_reviewed=(i % 2 == 0)  # Even numbered books are reviewed
            )

    def test_navigation_chain(self):
        """Test that you can navigate through a chain of books."""
        self.client.login(username='testuser', password='testpass')

        # Start at book 1
        current_id = 1
        visited_books = [current_id]

        # Navigate forward through all books
        while current_id < 5:
            response = self.client.get(reverse('books:book_detail', kwargs={'pk': current_id}))
            self.assertEqual(response.status_code, 200)

            next_book_id = response.context.get('next_book_id')
            if next_book_id:
                current_id = next_book_id
                visited_books.append(current_id)
            else:
                break

        # Should have visited all books
        self.assertEqual(visited_books, [1, 2, 3, 4, 5])

        # Navigate backward
        visited_backward = [current_id]
        while current_id > 1:
            response = self.client.get(reverse('books:book_detail', kwargs={'pk': current_id}))
            self.assertEqual(response.status_code, 200)

            prev_book_id = response.context.get('prev_book_id')
            if prev_book_id:
                current_id = prev_book_id
                visited_backward.append(current_id)
            else:
                break

        # Should have visited all books in reverse
        self.assertEqual(visited_backward, [5, 4, 3, 2, 1])

    def test_review_status_navigation_flow(self):
        """Test navigating through books by review status."""
        self.client.login(username='testuser', password='testpass')

        # Start at book 1 (unreviewed)
        response = self.client.get(reverse('books:book_detail', kwargs={'pk': 1}))
        self.assertEqual(response.status_code, 200)

        # Should have next unreviewed book
        next_unreviewed = response.context.get('next_unreviewed')
        self.assertIsNotNone(next_unreviewed)
        self.assertEqual(next_unreviewed.id, 3)  # Book 3 is unreviewed

        # Navigate to book 3
        response = self.client.get(reverse('books:book_detail', kwargs={'pk': 3}))
        self.assertEqual(response.status_code, 200)

        # Should have next unreviewed book
        next_unreviewed = response.context.get('next_unreviewed')
        self.assertIsNotNone(next_unreviewed)
        self.assertEqual(next_unreviewed.id, 5)  # Book 5 is unreviewed
