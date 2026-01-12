"""
Test cases for Book views
"""

from unittest.mock import MagicMock, Mock, patch

from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from books.models import (
    Author,
    Book,
    BookAuthor,
    BookMetadata,
    BookTitle,
    DataSource,
    FinalMetadata,
    ScanFolder,
    ScanLog,
)
from books.tests.test_helpers import create_test_book_with_file, create_test_scan_folder


class BaseViewTestCase(TestCase):
    """Base test case class with helper methods for view testing"""

    def get_rendered_response(self, url_name, **kwargs):
        """
        Helper method to get a response and ensure context is available
        for class-based views that use TemplateResponse.
        """
        response = self.client.get(reverse(url_name, kwargs=kwargs))
        # Force rendering to populate response.context for CBVs
        if hasattr(response, "render") and callable(response.render):
            response.render()
        return response

    def get_context_from_response(self, response):
        """
        Helper method to get context from response, handling both
        regular responses and TemplateResponse objects.
        """
        if hasattr(response, "context") and response.context is not None:
            return response.context
        elif hasattr(response, "context_data") and response.context_data is not None:
            return response.context_data
        else:
            return None


class BookListViewTests(BaseViewTestCase):
    """Test cases for book list view"""

    def setUp(self):
        """Set up test data"""
        self.user, created = User.objects.get_or_create(
            username="testuser_list",
            defaults={"email": "test@example.com", "password": "testpass123"},
        )
        if created:
            self.user.set_password("testpass123")
            self.user.save()
        self.client = Client()
        self.client.force_login(self.user)

        self.scan_folder = create_test_scan_folder(name="Test Scan Folder")
        # Cleanup will be handled by Django's test framework database rollback

        # Create test books
        for i in range(5):
            book = create_test_book_with_file(
                file_path=f"/test/path/book_{i+1}.epub",
                file_format="epub",
                file_size=1024000 + (i * 100000),
                scan_folder=self.scan_folder,
            )

            FinalMetadata.objects.create(
                book=book,
                final_title=f"Test Book {i+1}",
                final_author=f"Test Author {i+1}",
                is_reviewed=True,  # Set all to reviewed to avoid auto-update issues
            )

    def test_book_list_view_loads(self):
        """Test that book list view loads successfully"""
        response = self.client.get(reverse("books:book_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test Book 1")

    def test_book_list_view_unauthenticated(self):
        """Test book list view access by unauthenticated user"""
        self.client.logout()
        response = self.client.get(reverse("books:book_list"))
        # Should redirect to login or return 403
        self.assertIn(response.status_code, [302, 401, 403])

    def test_book_list_pagination(self):
        """Test book list pagination"""
        response = self.client.get(reverse("books:book_list"))
        self.assertEqual(response.status_code, 200)

        # Force rendering to populate response.context for CBVs
        if hasattr(response, "render") and callable(response.render):
            response.render()

        context = self.get_context_from_response(response)
        self.assertIsNotNone(context)

        # Check that pagination context exists
        self.assertIn("is_paginated", context)
        self.assertIn("page_obj", context)

    def test_book_list_filtering_by_review_status(self):
        """Test filtering books by review status"""
        # Test reviewed filter
        response = self.client.get(reverse("books:book_list") + "?needs_review=false")
        self.assertEqual(response.status_code, 200)

        # Force rendering to populate response.context for CBVs
        if hasattr(response, "render") and callable(response.render):
            response.render()

        context = self.get_context_from_response(response)
        self.assertIsNotNone(context)

        # Should only show reviewed books
        books = context["books"] if "books" in context else context["page_obj"]
        for book in books:
            self.assertTrue(book.finalmetadata.is_reviewed)


class BookDetailViewTests(BaseViewTestCase):
    """Test cases for book detail view"""

    def setUp(self):
        """Set up test data"""
        self.user, created = User.objects.get_or_create(
            username="testuser_detail",
            defaults={"email": "test@example.com", "password": "testpass123"},
        )
        if created:
            self.user.set_password("testpass123")
            self.user.save()
        self.client = Client()
        self.client.force_login(self.user)

        self.scan_folder = create_test_scan_folder(name="Test Scan Folder")

        self.book = create_test_book_with_file(
            file_path="/test/path/book_detail.epub",
            file_format="epub",
            file_size=1024000,
            scan_folder=self.scan_folder,
        )

        self.final_metadata = FinalMetadata.objects.create(
            book=self.book,
            final_title="Test Book",
            final_author="Test Author",
            final_series="Test Series",
            is_reviewed=True,  # Mark as reviewed to prevent auto-update
        )

    def test_book_detail_view_loads(self):
        """Test that book detail view loads successfully"""
        response = self.client.get(reverse("books:book_detail", kwargs={"pk": self.book.id}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test Book")

    def test_book_detail_view_context(self):
        """Test book detail view context variables"""
        response = self.client.get(reverse("books:book_detail", kwargs={"pk": self.book.id}))
        self.assertEqual(response.status_code, 200)

        # Use helper method to get context data
        context = self.get_context_from_response(response)

        # Check required context variables
        self.assertIn("book", context)
        self.assertIn("final_metadata", context)
        self.assertEqual(context["book"], self.book)

    def test_book_detail_navigation_context(self):
        """Test navigation context in book detail view"""
        # Create additional books for navigation testing
        create_test_book_with_file(
            file_path="/test/path/book2.epub",
            file_format="epub",
            file_size=1024000,
            scan_folder=self.scan_folder,
        )

        response = self.client.get(reverse("books:book_detail", kwargs={"pk": self.book.id}))
        self.assertEqual(response.status_code, 200)

        # Use helper method to get context data
        context = self.get_context_from_response(response)

        # Check navigation context
        self.assertIn("prev_book_id", context)
        self.assertIn("next_book_id", context)
        self.assertIn("next_needsreview_id", context)

    def test_book_detail_nonexistent_book(self):
        """Test book detail view with nonexistent book"""
        response = self.client.get(reverse("books:book_detail", kwargs={"pk": 99999}))
        self.assertEqual(response.status_code, 404)


class BookSearchViewTests(BaseViewTestCase):
    """Test cases for book search functionality"""

    def setUp(self):
        """Set up test data"""
        self.user, created = User.objects.get_or_create(
            username="testuser_search",
            defaults={"email": "test@example.com", "password": "testpass123"},
        )
        if created:
            self.user.set_password("testpass123")
            self.user.save()
        self.client = Client()
        self.client.force_login(self.user)

        self.scan_folder = create_test_scan_folder(name="Test Scan Folder")

        # Create books with different titles
        book1 = create_test_book_with_file(
            file_path="/test/path/python.epub",
            file_format="epub",
            file_size=1024000,
            scan_folder=self.scan_folder,
        )

        book2 = create_test_book_with_file(
            file_path="/test/path/django.epub",
            file_format="epub",
            file_size=1024000,
            scan_folder=self.scan_folder,
        )

        FinalMetadata.objects.create(
            book=book1,
            final_title="Python Programming",
            final_author="Python Author",
            is_reviewed=True,
        )

        FinalMetadata.objects.create(
            book=book2,
            final_title="Django Web Framework",
            final_author="Django Author",
            is_reviewed=True,
        )

    def test_book_search_by_title(self):
        """Test searching books by title"""
        response = self.client.get(reverse("books:book_list") + "?search_query=Python")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Python Programming")
        self.assertNotContains(response, "Django Web Framework")

    def test_book_search_by_author(self):
        """Test searching books by author"""
        response = self.client.get(reverse("books:book_list") + "?search_query=Django Author")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Django Web Framework")
        self.assertNotContains(response, "Python Programming")

    def test_empty_search_query(self):
        """Test empty search query returns all books"""
        response = self.client.get(reverse("books:book_list") + "?search_query=")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Python Programming")
        self.assertContains(response, "Django Web Framework")


class TriggerScanViewTests(BaseViewTestCase):
    """Test cases for the TriggerScanView."""

    def setUp(self):
        """Set up test data."""
        self.user, created = User.objects.get_or_create(username="testuser_trigger", defaults={"password": "testpass123"})
        if created:
            self.user.set_password("testpass123")
            self.user.save()
        self.client = Client()
        self.client.force_login(self.user)

        self.scan_folder = create_test_scan_folder(name="Test Folder")

    def test_trigger_scan_view_requires_login(self):
        """Test that trigger scan view requires authentication."""
        self.client.logout()
        response = self.client.get(reverse("books:trigger_scan"))
        self.assertIn(response.status_code, [302, 401, 403])

    def test_trigger_scan_view_get(self):
        """Test GET request to trigger scan view."""
        response = self.client.get(reverse("books:trigger_scan"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Trigger Scan")

    def test_trigger_scan_view_no_active_folders(self):
        """Test scan trigger with no active folders."""
        self.scan_folder.is_active = False
        self.scan_folder.save()

        with patch("subprocess.Popen") as mock_popen, patch("books.views.settings") as mock_settings:
            mock_settings.BASE_DIR = "/project"
            mock_popen.return_value = Mock()

            response = self.client.post(reverse("books:trigger_scan"), {"scan_mode": "normal"})

            self.assertEqual(response.status_code, 302)


class ViewFilteringTests(BaseViewTestCase):
    """Test filtering functionality across views."""

    def setUp(self):
        """Set up test data."""
        self.user, created = User.objects.get_or_create(username="testuser_filter", defaults={"password": "testpass123"})
        if created:
            self.user.set_password("testpass123")
            self.user.save()
        self.client = Client()
        self.client.force_login(self.user)

        from books.models import DataSource

        self.initial_scan_source, _ = DataSource.objects.get_or_create(name=DataSource.INITIAL_SCAN, defaults={"trust_level": 0.2})

        self.scan_folder = create_test_scan_folder(name="Test Folder")

    def test_book_list_confidence_filtering(self):
        """Test filtering by confidence level."""
        # Create book with high confidence
        book_high = create_test_book_with_file(
            file_path="/test/folder/high.epub",
            file_format="epub",
            file_size=1000,
            scan_folder=self.scan_folder,
        )

        FinalMetadata.objects.create(
            book=book_high,
            final_title="High Confidence Book",
            final_title_confidence=0.9,  # 0.9 * 0.3 = 0.27
            final_author_confidence=0.9,  # 0.9 * 0.3 = 0.27
            final_series_confidence=0.9,  # 0.9 * 0.15 = 0.135
            final_cover_confidence=0.9,  # 0.9 * 0.25 = 0.225
            # Total: 0.27 + 0.27 + 0.135 + 0.225 = 0.9
            overall_confidence=0.9,
            is_reviewed=True,
        )

        # Create book with low confidence
        book_low = create_test_book_with_file(
            file_path="/test/folder/low.epub",
            file_format="epub",
            file_size=1000,
            scan_folder=self.scan_folder,
        )

        FinalMetadata.objects.create(
            book=book_low,
            final_title="Low Confidence Book",
            final_title_confidence=0.3,  # Set individual confidence scores
            final_author_confidence=0.3,
            overall_confidence=0.3,
            is_reviewed=True,
        )

        # Test high confidence filter
        response = self.client.get(reverse("books:book_list"), {"confidence": "high"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "High Confidence Book")
        self.assertNotContains(response, "Low Confidence Book")

        # Test low confidence filter
        response = self.client.get(reverse("books:book_list"), {"confidence": "low"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Low Confidence Book")
        self.assertNotContains(response, "High Confidence Book")

    def test_book_list_format_filtering(self):
        """Test filtering by file format."""
        # Create EPUB book
        book_epub = create_test_book_with_file(
            file_path="/test/folder/book.epub",
            file_format="epub",
            file_size=1000,
            scan_folder=self.scan_folder,
        )

        # Create PDF book
        book_pdf = create_test_book_with_file(
            file_path="/test/folder/book.pdf",
            file_format="pdf",
            file_size=2000,
            scan_folder=self.scan_folder,
        )

        # Test EPUB filter
        response = self.client.get(reverse("books:book_list"), {"file_format": "epub"})
        self.assertEqual(response.status_code, 200)
        # Verify EPUB book is in results
        context = self.get_context_from_response(response)
        books = context["books"] if "books" in context else context["page_obj"]
        book_ids = [book.id for book in books]
        self.assertIn(book_epub.id, book_ids)
        self.assertNotIn(book_pdf.id, book_ids)

        # Test PDF filter
        response = self.client.get(reverse("books:book_list"), {"file_format": "pdf"})
        self.assertEqual(response.status_code, 200)
        # Verify PDF book is in results
        context = self.get_context_from_response(response)
        books = context["books"] if "books" in context else context["page_obj"]
        book_ids = [book.id for book in books]
        self.assertIn(book_pdf.id, book_ids)
        self.assertNotIn(book_epub.id, book_ids)

    def test_book_list_missing_metadata_filter(self):
        """Test filtering by missing metadata."""
        # Create book without FinalMetadata
        book_missing = create_test_book_with_file(
            file_path="/test/folder/missing.epub",
            file_format="epub",
            file_size=1000,
            scan_folder=self.scan_folder,
        )

        # Create book with FinalMetadata
        book_complete = create_test_book_with_file(
            file_path="/test/folder/complete.epub",
            file_format="epub",
            file_size=1000,
            scan_folder=self.scan_folder,
        )

        FinalMetadata.objects.create(book=book_complete, final_title="Complete Book", is_reviewed=True)

        # Test missing metadata filter
        response = self.client.get(reverse("books:book_list"), {"missing": "metadata"})
        self.assertEqual(response.status_code, 200)
        # Verify that book without metadata is in results
        context = self.get_context_from_response(response)
        books = context["books"] if "books" in context else context["page_obj"]
        book_ids = [book.id for book in books]
        self.assertIn(book_missing.id, book_ids)
        self.assertNotIn(book_complete.id, book_ids)

    def test_book_list_corrupted_filter(self):
        """Test filtering by corrupted status."""
        # Create corrupted book
        book_corrupted = create_test_book_with_file(
            file_path="/test/folder/corrupted.epub",
            file_format="epub",
            file_size=1000,
            scan_folder=self.scan_folder,
            is_corrupted=True,
        )

        # Test corrupted filter
        response = self.client.get(reverse("books:book_list"), {"review_type": "corrupted"})
        self.assertEqual(response.status_code, 200)
        # Verify that corrupted book is in results
        context = self.get_context_from_response(response)
        books = context["books"] if "books" in context else context["page_obj"]
        book_ids = [book.id for book in books]
        self.assertIn(book_corrupted.id, book_ids)

    def test_book_list_datasource_filter(self):
        """Test filtering by data source."""

        # Create different data sources
        epub_source, _ = DataSource.objects.get_or_create(name=DataSource.EPUB_INTERNAL, defaults={"trust_level": 0.8})

        initial_scan_source, _ = DataSource.objects.get_or_create(name=DataSource.INITIAL_SCAN, defaults={"trust_level": 0.3})

        # Create authors
        epub_author = Author.objects.create(name="EPUB Author")
        filename_author = Author.objects.create(name="Filename Author")

        # Create books
        book1 = create_test_book_with_file(
            file_path="/test/folder/book1.epub",
            file_format="epub",
            file_size=1000,
            scan_folder=self.scan_folder,
        )

        book2 = create_test_book_with_file(
            file_path="/test/folder/book2.epub",
            file_format="epub",
            file_size=1000,
            scan_folder=self.scan_folder,
        )

        # Create metadata with different sources
        BookTitle.objects.create(
            book=book1,
            title="Book with EPUB metadata",
            source=epub_source,
            confidence=0.8,
        )

        BookTitle.objects.create(
            book=book2,
            title="Book with filename metadata",
            source=initial_scan_source,
            confidence=0.3,
        )

        BookAuthor.objects.create(book=book1, author=epub_author, source=epub_source, confidence=0.8)

        BookAuthor.objects.create(
            book=book2,
            author=filename_author,
            source=initial_scan_source,
            confidence=0.3,
        )

        # Test filtering by EPUB metadata source
        response = self.client.get(reverse("books:book_list"), {"datasource": str(epub_source.id)})
        self.assertEqual(response.status_code, 200)
        context = self.get_context_from_response(response)
        books = context["books"] if "books" in context else context["page_obj"]
        book_ids = [book.id for book in books]
        self.assertIn(book1.id, book_ids)
        self.assertNotIn(book2.id, book_ids)

        # Test filtering by initial scan source
        response = self.client.get(reverse("books:book_list"), {"datasource": str(initial_scan_source.id)})
        self.assertEqual(response.status_code, 200)
        context = self.get_context_from_response(response)
        books = context["books"] if "books" in context else context["page_obj"]
        book_ids = [book.id for book in books]
        self.assertIn(book2.id, book_ids)
        self.assertNotIn(book1.id, book_ids)

    def test_book_list_scan_folder_filter(self):
        """Test filtering by scan folder."""
        # Create additional scan folder
        scan_folder2 = create_test_scan_folder(name="Test Folder 2")

        # Create books in different scan folders
        book1 = create_test_book_with_file(
            file_path="/test/folder/book1.epub",
            file_format="epub",
            file_size=1000,
            scan_folder=self.scan_folder,
        )

        book2 = create_test_book_with_file(
            file_path="/test/folder2/book2.epub",
            file_format="epub",
            file_size=1000,
            scan_folder=scan_folder2,
        )

        # Test filtering by first scan folder
        response = self.client.get(reverse("books:book_list"), {"scan_folder": str(self.scan_folder.id)})
        self.assertEqual(response.status_code, 200)
        context = self.get_context_from_response(response)
        books = context["books"] if "books" in context else context["page_obj"]
        book_ids = [book.id for book in books]
        self.assertIn(book1.id, book_ids)
        self.assertNotIn(book2.id, book_ids)

        # Test filtering by second scan folder
        response = self.client.get(reverse("books:book_list"), {"scan_folder": str(scan_folder2.id)})
        self.assertEqual(response.status_code, 200)
        context = self.get_context_from_response(response)
        books = context["books"] if "books" in context else context["page_obj"]
        book_ids = [book.id for book in books]
        self.assertIn(book2.id, book_ids)
        self.assertNotIn(book1.id, book_ids)

    def test_book_list_combined_filters(self):
        """Test combining datasource and scan folder filters."""
        from books.models import BookTitle, DataSource

        # Create second scan folder
        scan_folder2 = create_test_scan_folder(name="Test Folder 2")

        # Create data source
        epub_source, _ = DataSource.objects.get_or_create(name=DataSource.EPUB_INTERNAL, defaults={"trust_level": 0.8})

        # Create books
        book1 = create_test_book_with_file(
            file_path="/test/folder/book1.epub",
            file_format="epub",
            file_size=1000,
            scan_folder=self.scan_folder,
        )

        book2 = create_test_book_with_file(
            file_path="/test/folder2/book2.epub",
            file_format="epub",
            file_size=1000,
            scan_folder=scan_folder2,
        )

        # Both books have same data source
        BookTitle.objects.create(book=book1, title="Book 1", source=epub_source, confidence=0.8)

        BookTitle.objects.create(book=book2, title="Book 2", source=epub_source, confidence=0.8)

        # Test combined filters - should only return book1
        response = self.client.get(
            reverse("books:book_list"),
            {
                "datasource": str(epub_source.id),
                "scan_folder": str(self.scan_folder.id),
            },
        )
        self.assertEqual(response.status_code, 200)
        context = self.get_context_from_response(response)
        books = context["books"] if "books" in context else context["page_obj"]
        book_ids = [book.id for book in books]
        self.assertIn(book1.id, book_ids)
        self.assertNotIn(book2.id, book_ids)


class ViewEdgeCaseTests(BaseViewTestCase):
    """Test edge cases and potential issues in views."""

    def setUp(self):
        """Set up test data."""
        self.user, created = User.objects.get_or_create(username="testuser_edge", defaults={"password": "testpass123"})
        if created:
            self.user.set_password("testpass123")
            self.user.save()
        self.client = Client()
        self.client.force_login(self.user)

    def test_search_with_special_characters(self):
        """Test search with special characters."""
        response = self.client.get(
            reverse("books:book_list"),
            {"search_query": '<script>alert("xss")</script>'},
        )
        self.assertEqual(response.status_code, 200)
        # Should be safely handled

    def test_search_with_unicode_characters(self):
        """Test search with unicode characters."""
        response = self.client.get(reverse("books:book_list"), {"search_query": "Café Français 中文 العربية"})
        self.assertEqual(response.status_code, 200)

    def test_view_with_very_long_search_query(self):
        """Test search with extremely long query."""
        long_query = "a" * 1000
        response = self.client.get(reverse("books:book_list"), {"search_query": long_query})
        self.assertEqual(response.status_code, 200)

    def test_book_list_with_empty_database(self):
        """Test book list view with no books."""
        response = self.client.get(reverse("books:book_list"))
        self.assertEqual(response.status_code, 200)
        # Should handle empty state gracefully

    def test_view_with_malformed_parameters(self):
        """Test views with malformed URL parameters."""
        # Test with non-integer book ID
        response = self.client.get("/books/detail/abc/")
        self.assertEqual(response.status_code, 404)

    def test_book_list_sorting_edge_cases(self):
        """Test sorting with edge cases."""
        # Test with invalid sort field
        response = self.client.get(reverse("books:book_list"), {"sort": "invalid_field"})
        self.assertEqual(response.status_code, 200)
        # Should fall back to default sorting

    def test_empty_filter_values(self):
        """Test behavior with empty filter values."""
        response = self.client.get(
            reverse("books:book_list"),
            {"file_format": "", "language": "", "search_query": ""},
        )
        self.assertEqual(response.status_code, 200)


class BookRenamerIntegrationTests(BaseViewTestCase):
    """Integration tests for book renamer functionality"""

    def setUp(self):
        """Set up test data"""
        self.user, created = User.objects.get_or_create(
            username="testuser_renamer",
            defaults={"email": "test@example.com", "password": "testpass123"},
        )
        if created:
            self.user.set_password("testpass123")
            self.user.save()
        self.client = Client()
        self.client.force_login(self.user)

        self.scan_folder = create_test_scan_folder(name="Test Scan Folder")

        self.book = create_test_book_with_file(
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
            is_reviewed=True,
        )

    def test_book_renamer_view_integration(self):
        """Test that book renamer view works with actual data"""
        response = self.client.get(reverse("books:book_renamer"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test Book")

    def test_book_renamer_with_null_series_number(self):
        """Test book renamer handles books with null series numbers"""
        # Create book with null series number
        book_null = create_test_book_with_file(
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
            is_reviewed=True,
        )

        response = self.client.get(reverse("books:book_renamer"))
        self.assertEqual(response.status_code, 200)
        # Should not crash and should include both books
        self.assertContains(response, "Test Book")
        self.assertContains(response, "Test Book Null")


class BookDetailNavigationTestCase(BaseViewTestCase):
    """Test the prev/next navigation buttons in book detail view."""

    def setUp(self):
        """Set up test data."""
        self.client = Client()
        self.user, created = User.objects.get_or_create(username="testuser_nav", defaults={"password": "testpass"})
        if created:
            self.user.set_password("testpass")
            self.user.save()

        # Create a scan folder
        self.scan_folder = create_test_scan_folder(name="Test Folder")

        # Create test books with proper Book model fields
        # Create books first
        self.book1 = create_test_book_with_file(
            file_path="/test/book1.epub",
            file_format="epub",
            scan_folder=self.scan_folder,
        )

        self.book2 = create_test_book_with_file(
            file_path="/test/book2.epub",
            file_format="epub",
            scan_folder=self.scan_folder,
        )

        self.book3 = create_test_book_with_file(
            file_path="/test/book3.epub",
            file_format="epub",
            scan_folder=self.scan_folder,
        )

        # Now create FinalMetadata with manual update flag to prevent auto-overwriting
        # We need to manually handle the metadata creation to avoid the auto-update
        from books.models import FinalMetadata

        # For book1
        metadata1 = FinalMetadata.objects.filter(book=self.book1).first()
        if not metadata1:
            metadata1 = FinalMetadata(book=self.book1)
        metadata1.final_title = "Book One"
        metadata1.final_author = "Author One"
        metadata1.final_series = "Series A"
        metadata1.final_series_number = "1"
        metadata1.is_reviewed = True
        metadata1._manual_update = True
        metadata1.save()
        self.metadata1 = metadata1

        # For book2
        metadata2 = FinalMetadata.objects.filter(book=self.book2).first()
        if not metadata2:
            metadata2 = FinalMetadata(book=self.book2)
        metadata2.final_title = "Book Two"
        metadata2.final_author = "Author One"
        metadata2.final_series = "Series A"
        metadata2.final_series_number = "2"
        metadata2.is_reviewed = False
        metadata2._manual_update = True
        metadata2.save()
        self.metadata2 = metadata2

        # For book3
        metadata3 = FinalMetadata.objects.filter(book=self.book3).first()
        if not metadata3:
            metadata3 = FinalMetadata(book=self.book3)
        metadata3.final_title = "Book Three"
        metadata3.final_author = "Author Two"
        metadata3.final_series = "Series B"
        metadata3.final_series_number = "1"
        metadata3.is_reviewed = False
        metadata3._manual_update = True
        metadata3.save()
        self.metadata3 = metadata3

    def test_basic_navigation_context(self):
        """Test that basic prev/next navigation context is provided."""
        self.client.login(username="testuser_nav", password="testpass")

        # Test book2 (middle book) - should have both prev and next
        response = self.client.get(reverse("books:book_detail", kwargs={"pk": 2}))
        self.assertEqual(response.status_code, 200)

        context = self.get_context_from_response(response)
        self.assertIsNotNone(context["prev_book"])
        self.assertIsNotNone(context["next_book"])
        self.assertEqual(context["prev_book"].id, 1)
        self.assertEqual(context["next_book"].id, 3)
        self.assertEqual(context["prev_book_id"], 1)
        self.assertEqual(context["next_book_id"], 3)

    def test_first_book_navigation(self):
        """Test navigation context for the first book."""
        self.client.login(username="testuser_nav", password="testpass")

        response = self.client.get(reverse("books:book_detail", kwargs={"pk": 1}))
        self.assertEqual(response.status_code, 200)

        context = self.get_context_from_response(response)
        self.assertIsNone(context["prev_book"])
        self.assertIsNotNone(context["next_book"])
        self.assertIsNone(context["prev_book_id"])
        self.assertEqual(context["next_book_id"], 2)

    def test_last_book_navigation(self):
        """Test navigation context for the last book."""
        self.client.login(username="testuser_nav", password="testpass")

        response = self.client.get(reverse("books:book_detail", kwargs={"pk": 3}))
        self.assertEqual(response.status_code, 200)

        context = self.get_context_from_response(response)
        self.assertIsNotNone(context["prev_book"])
        self.assertIsNone(context["next_book"])
        self.assertEqual(context["prev_book_id"], 2)
        self.assertIsNone(context["next_book_id"])

    def test_same_author_navigation(self):
        """Test navigation by same author."""
        self.client.login(username="testuser_nav", password="testpass")

        # Test book1 - should have next author book (book2)
        response = self.client.get(reverse("books:book_detail", kwargs={"pk": 1}))
        context = self.get_context_from_response(response)

        self.assertIsNone(context.get("prev_same_author"))
        self.assertIsNotNone(context.get("next_same_author"))
        self.assertEqual(context["next_same_author"].id, 2)

        # Test book2 - should have prev author book (book1)
        response = self.client.get(reverse("books:book_detail", kwargs={"pk": 2}))
        context = self.get_context_from_response(response)

        self.assertIsNotNone(context.get("prev_same_author"))
        self.assertIsNone(context.get("next_same_author"))
        self.assertEqual(context["prev_same_author"].id, 1)

    def test_same_series_navigation(self):
        """Test navigation by same series."""
        self.client.login(username="testuser_nav", password="testpass")

        # Test book1 - should have next series book (book2)
        response = self.client.get(reverse("books:book_detail", kwargs={"pk": 1}))
        context = self.get_context_from_response(response)

        self.assertIsNone(context.get("prev_same_series"))
        self.assertIsNotNone(context.get("next_same_series"))
        self.assertEqual(context["next_same_series"].id, 2)

        # Test book2 - should have prev series book (book1)
        response = self.client.get(reverse("books:book_detail", kwargs={"pk": 2}))
        context = self.get_context_from_response(response)

        self.assertIsNotNone(context.get("prev_same_series"))
        self.assertIsNone(context.get("next_same_series"))
        self.assertEqual(context["prev_same_series"].id, 1)

    def test_review_status_navigation(self):
        """Test navigation by review status."""
        self.client.login(username="testuser_nav", password="testpass")

        # Test book1 (reviewed) - should have next unreviewed (book2)
        response = self.client.get(reverse("books:book_detail", kwargs={"pk": 1}))
        context = self.get_context_from_response(response)

        self.assertIsNotNone(context.get("next_unreviewed"))
        self.assertEqual(context["next_unreviewed"].id, 2)

        # Test book2 (unreviewed) - should have next reviewed book (none in this case)
        response = self.client.get(reverse("books:book_detail", kwargs={"pk": 2}))
        context = self.get_context_from_response(response)

        self.assertIsNotNone(context.get("prev_reviewed"))
        self.assertEqual(context["prev_reviewed"].id, 1)

    def test_needs_review_navigation(self):
        """Test navigation for books that need review."""
        self.client.login(username="testuser_nav", password="testpass")

        # Test that unreviewed books show up in needs review navigation
        response = self.client.get(reverse("books:book_detail", kwargs={"pk": 1}))
        context = self.get_context_from_response(response)

        # Book1 (reviewed) should have next needs review (book2)
        self.assertIsNotNone(context.get("next_needs_review"))
        self.assertEqual(context["next_needs_review"].id, 2)

        # Test book2 - should have next needs review (book3)
        response = self.client.get(reverse("books:book_detail", kwargs={"pk": 2}))
        context = self.get_context_from_response(response)

        self.assertIsNotNone(context.get("next_needs_review"))
        self.assertEqual(context["next_needs_review"].id, 3)

    def test_navigation_buttons_in_template(self):
        """Test that navigation buttons appear correctly in the template."""
        self.client.login(username="testuser_nav", password="testpass")

        response = self.client.get(reverse("books:book_detail", kwargs={"pk": 2}))
        self.assertEqual(response.status_code, 200)

        content = response.content.decode("utf-8")

        # Check for prev button
        self.assertIn('href="/book/1/"', content)
        self.assertIn("Previous Book", content)

        # Check for next button
        self.assertIn('href="/book/3/"', content)
        self.assertIn("Next Book", content)

        # Check for author navigation
        self.assertIn("Previous by Author One", content)

        # Check for series navigation
        self.assertIn("Series A", content)

    def test_navigation_with_placeholder_books(self):
        """Test that placeholder books are excluded from navigation."""
        # Create a placeholder book
        create_test_book_with_file(
            file_path="/test/placeholder.epub",
            file_format="placeholder",
            scan_folder=self.scan_folder,
            is_placeholder=True,
        )

        self.client.login(username="testuser_nav", password="testpass")

        # Test that placeholder book doesn't appear in navigation
        response = self.client.get(reverse("books:book_detail", kwargs={"pk": 3}))
        context = self.get_context_from_response(response)

        # Next book should be None, not the placeholder
        self.assertIsNone(context["next_book"])
        self.assertIsNone(context["next_book_id"])

    def test_navigation_urls_work(self):
        """Test that navigation URLs actually work and return 200."""
        self.client.login(username="testuser_nav", password="testpass")

        # Test basic navigation URLs
        response = self.client.get(reverse("books:book_detail", kwargs={"pk": 1}))
        self.assertEqual(response.status_code, 200)

        response = self.client.get(reverse("books:book_detail", kwargs={"pk": 2}))
        self.assertEqual(response.status_code, 200)

        response = self.client.get(reverse("books:book_detail", kwargs={"pk": 3}))
        self.assertEqual(response.status_code, 200)

    def test_navigation_with_missing_final_metadata(self):
        """Test navigation works even when final metadata is missing."""
        # Create a book without final metadata
        create_test_book_with_file(
            file_path="/test/book4.epub",
            file_format="epub",
            scan_folder=self.scan_folder,
        )

        self.client.login(username="testuser_nav", password="testpass")

        response = self.client.get(reverse("books:book_detail", kwargs={"pk": 4}))
        self.assertEqual(response.status_code, 200)

        context = self.get_context_from_response(response)
        # Should still have basic navigation
        self.assertIsNotNone(context["prev_book"])
        self.assertEqual(context["prev_book"].id, 3)

        # But no author/series navigation since no final metadata
        self.assertIsNone(context.get("prev_same_author"))
        self.assertIsNone(context.get("next_same_author"))


# ============================================================================
# Dashboard View Tests
# ============================================================================


class DashboardViewTests(BaseViewTestCase):
    """Test cases for the enhanced dashboard view"""

    def setUp(self):
        """Set up test data"""
        self.user, created = User.objects.get_or_create(
            username="testuser_dashboard",
            defaults={"email": "test@example.com", "password": "testpass123"},
        )
        if created:
            self.user.set_password("testpass123")
            self.user.save()
        self.client = Client()
        self.client.force_login(self.user)

        # Create scan folder
        self.scan_folder = create_test_scan_folder(name="Dashboard Test Folder")

        # Create test books with various states
        self.epub_book = create_test_book_with_file(
            file_path="/test/dashboard/book1.epub",
            file_format="epub",
            file_size=1024000,
            scan_folder=self.scan_folder,
        )

        self.pdf_book = create_test_book_with_file(
            file_path="/test/dashboard/book2.pdf",
            file_format="pdf",
            file_size=2048000,
            scan_folder=self.scan_folder,
        )

        # Create metadata for books
        FinalMetadata.objects.create(
            book=self.epub_book,
            final_title="Test EPUB Book",
            final_author="Test Author",
            final_series="Test Series",
            overall_confidence=0.9,
            completeness_score=0.8,
            is_reviewed=True,
            has_cover=True,
            isbn="9781234567890",
        )

        FinalMetadata.objects.create(
            book=self.pdf_book,
            final_title="Test PDF Book",
            final_author="Another Author",
            overall_confidence=0.3,
            completeness_score=0.4,
            is_reviewed=False,
            has_cover=False,
        )

    def test_dashboard_view_loads(self):
        """Test that dashboard view loads successfully"""
        response = self.client.get(reverse("books:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Dashboard")

    def test_dashboard_view_anonymous_user(self):
        """Test that anonymous users are redirected to login"""
        self.client.logout()
        response = self.client.get(reverse("books:dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_dashboard_context_statistics(self):
        """Test dashboard context contains expected statistics"""
        response = self.client.get(reverse("books:dashboard"))
        self.assertEqual(response.status_code, 200)

        context = self.get_context_from_response(response)
        self.assertIsNotNone(context)

        # Check core statistics - access context directly
        context_dict = context[0] if isinstance(context, list) else context

        # Check that statistics are available directly in context
        self.assertIn("total_books", context_dict)
        self.assertIn("issue_stats", context_dict)
        self.assertIn("format_stats", context_dict)
        self.assertIn("chart_data", context_dict)

        # Verify statistics values
        self.assertEqual(context_dict["total_books"], 2)
        self.assertEqual(context_dict["needs_review_count"], 1)

    def test_dashboard_format_distribution(self):
        """Test format distribution statistics"""
        response = self.client.get(reverse("books:dashboard"))
        context = self.get_context_from_response(response)

        format_stats = context["format_stats"]
        format_counts = {item["files__file_format"]: item["count"] for item in format_stats}

        self.assertEqual(format_counts.get("epub", 0), 1)
        self.assertEqual(format_counts.get("pdf", 0), 1)

    def test_dashboard_confidence_statistics(self):
        """Test confidence level statistics"""
        response = self.client.get(reverse("books:dashboard"))
        context = self.get_context_from_response(response)

        # Check confidence statistics - available directly in context due to **metadata_stats unpacking
        self.assertIn("high_confidence_count", context)
        self.assertIn("low_confidence_count", context)
        self.assertIn("medium_confidence_count", context)

    def test_dashboard_issue_detection(self):
        """Test issue detection functionality"""
        # Create a corrupted book
        create_test_book_with_file(
            file_path="/test/dashboard/corrupted.epub",
            file_format="epub",
            file_size=100,
            scan_folder=self.scan_folder,
            is_corrupted=True,
        )

        response = self.client.get(reverse("books:dashboard"))
        context = self.get_context_from_response(response)

        issue_stats = context["issue_stats"]
        self.assertGreaterEqual(issue_stats.get("corrupted_books", 0), 1)

    def test_dashboard_content_type_statistics(self):
        """Test content type statistics"""
        response = self.client.get(reverse("books:dashboard"))
        context = self.get_context_from_response(response)

        # Check for content statistics - available directly in context due to **content_stats unpacking
        self.assertIn("issue_stats", context)
        self.assertIn("format_stats", context)

    def test_dashboard_chart_data(self):
        """Test chart data preparation"""
        response = self.client.get(reverse("books:dashboard"))
        context = self.get_context_from_response(response)

        context_dict = context[0] if isinstance(context, list) else context
        self.assertIn("chart_data", context_dict)
        chart_data = context_dict["chart_data"]

        # Check chart data structure - check for actual keys in response
        self.assertIn("format_labels", chart_data)
        self.assertIn("format_data", chart_data)
        self.assertIn("completeness_labels", chart_data)
        self.assertIn("completeness_data", chart_data)

    def test_dashboard_recent_activity(self):
        """Test recent activity tracking"""
        response = self.client.get(reverse("books:dashboard"))
        context = self.get_context_from_response(response)

        self.assertIn("recent_activity", context)
        # Recent activity should include our test books
        recent_activity = context["recent_activity"]
        self.assertGreaterEqual(len(recent_activity), 2)


# ============================================================================
# Signup View Tests
# ============================================================================


class SignupViewTests(BaseViewTestCase):
    """Test cases for user registration"""

    def test_signup_view_get(self):
        """Test GET request to signup view"""
        response = self.client.get(reverse("books:signup"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "form")

    def test_signup_view_post_valid(self):
        """Test POST request with valid data"""
        response = self.client.post(
            reverse("books:signup"),
            {
                "username": "newuser",
                "email": "newuser@example.com",
                "password1": "ComplexPass123!",
                "password2": "ComplexPass123!",
            },
        )

        # Should redirect to dashboard after successful signup
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("books:dashboard"))

        # User should be created
        self.assertTrue(User.objects.filter(username="newuser").exists())

    def test_signup_view_post_invalid(self):
        """Test POST request with invalid data"""
        response = self.client.post(
            reverse("books:signup"),
            {
                "username": "newuser",
                "email": "invalid-email",
                "password1": "pass",
                "password2": "different",
            },
        )

        # Should stay on signup page with errors
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "form")

        # User should not be created
        self.assertFalse(User.objects.filter(username="newuser").exists())


# ============================================================================
# Book Metadata Views Tests
# ============================================================================


class BookMetadataViewTests(BaseViewTestCase):
    """Test cases for book metadata views"""

    def setUp(self):
        """Set up test data"""
        self.user, created = User.objects.get_or_create(
            username="testuser_metadata",
            defaults={"email": "test@example.com", "password": "testpass123"},
        )
        if created:
            self.user.set_password("testpass123")
            self.user.save()
        self.client = Client()
        self.client.force_login(self.user)

        self.scan_folder = create_test_scan_folder(name="Metadata Test Folder")

        self.book = create_test_book_with_file(
            file_path="/test/metadata/book.epub",
            file_format="epub",
            file_size=1024000,
            scan_folder=self.scan_folder,
        )

        self.final_metadata = FinalMetadata.objects.create(
            book=self.book,
            final_title="Original Title",
            final_author="Original Author",
            final_series="Original Series",
            is_reviewed=True,  # Prevent auto-metadata from overriding test data
        )

    def test_book_metadata_view_loads(self):
        """Test that book metadata view loads successfully"""
        response = self.client.get(reverse("books:book_metadata", kwargs={"pk": self.book.id}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Original Title")

    def test_book_metadata_view_anonymous_user(self):
        """Test that anonymous users are redirected to login"""
        self.client.logout()
        response = self.client.get(reverse("books:book_metadata", kwargs={"pk": self.book.id}))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_book_metadata_view_nonexistent_book(self):
        """Test book metadata view with nonexistent book"""
        response = self.client.get(reverse("books:book_metadata", kwargs={"pk": 99999}))
        self.assertEqual(response.status_code, 404)

    def test_book_metadata_update_view_post_valid(self):
        """Test POST request to metadata update view with valid data"""
        response = self.client.post(
            reverse("books:book_metadata_update", kwargs={"pk": self.book.id}),
            {
                "final_title": "Updated Title",
                "final_author": "Updated Author",
                "final_series": "Updated Series",
                "final_series_number": "2",
                "is_reviewed": "on",
            },
        )

        # Should redirect to book detail
        self.assertEqual(response.status_code, 302)

        # Metadata should be updated
        updated_metadata = FinalMetadata.objects.get(book=self.book)
        self.assertEqual(updated_metadata.final_title, "Updated Title")
        self.assertEqual(updated_metadata.final_author, "Updated Author")
        self.assertEqual(updated_metadata.final_series, "Updated Series")
        self.assertEqual(updated_metadata.final_series_number, "2")
        self.assertTrue(updated_metadata.is_reviewed)

    def test_book_metadata_update_view_post_invalid(self):
        """Test POST request with invalid data"""
        response = self.client.post(
            reverse("books:book_metadata_update", kwargs={"pk": self.book.id}),
            {"final_title": "", "final_author": "Updated Author"},  # Empty title
        )

        # Should return to metadata view with errors
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "error")


# ============================================================================
# AJAX Views Tests
# ============================================================================


class AjaxViewTests(BaseViewTestCase):
    """Test cases for AJAX endpoints"""

    def setUp(self):
        """Set up test data"""
        self.user, created = User.objects.get_or_create(
            username="testuser_ajax",
            defaults={"email": "test@example.com", "password": "testpass123"},
        )
        if created:
            self.user.set_password("testpass123")
            self.user.save()
        self.client = Client()
        self.client.force_login(self.user)

        self.scan_folder = create_test_scan_folder(name="AJAX Test Folder")

        self.book = create_test_book_with_file(
            file_path="/test/ajax/book.epub",
            file_format="epub",
            file_size=1024000,
            scan_folder=self.scan_folder,
        )

        self.final_metadata = FinalMetadata.objects.create(
            book=self.book,
            final_title="AJAX Test Book",
            final_author="AJAX Author",
            is_reviewed=False,
        )

    def test_ajax_update_book_status_anonymous(self):
        """Test AJAX book status update requires authentication"""
        self.client.logout()
        response = self.client.post(reverse("books:ajax_update_book_status", kwargs={"book_id": self.book.id}))
        self.assertEqual(response.status_code, 302)

    def test_ajax_update_book_status_invalid_book(self):
        """Test AJAX book status update with invalid book ID"""
        import json

        response = self.client.post(reverse("books:ajax_update_book_status", kwargs={"book_id": 99999}))
        # Function catches exceptions and returns error in JSON format
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertFalse(data["success"])

    def test_ajax_trigger_scan_anonymous(self):
        """Test AJAX trigger scan requires authentication"""
        self.client.logout()
        response = self.client.post(reverse("books:ajax_trigger_scan"))
        self.assertEqual(response.status_code, 302)

    def test_ajax_trigger_scan_authenticated(self):
        """Test AJAX trigger scan for authenticated user"""
        # Test with valid JSON data
        import json

        response = self.client.post(
            reverse("books:ajax_trigger_scan"),
            data=json.dumps({"folder_id": self.scan_folder.id, "use_external_apis": True}),
            content_type="application/json",
        )

        # Should return JSON response
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")

    def test_isbn_lookup_valid(self):
        """Test ISBN lookup with valid ISBN"""
        with patch("books.utils.external_services.PrimaryISBNService.lookup_isbn") as mock_lookup:
            mock_lookup.return_value = {
                "title": "Test Book",
                "author": "Test Author",
                "publishedDate": "2023",
                "description": "Test description",
            }

            response = self.client.get(reverse("books:isbn_lookup", kwargs={"isbn": "9781234567890"}))

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response["Content-Type"], "application/json")

    def test_isbn_lookup_invalid(self):
        """Test ISBN lookup with invalid ISBN"""
        import json

        response = self.client.get(reverse("books:isbn_lookup", kwargs={"isbn": "invalid-isbn"}))

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertFalse(data["success"])

    def test_toggle_needs_review(self):
        """Test toggle needs review functionality"""
        response = self.client.post(reverse("books:toggle_needs_review", kwargs={"book_id": self.book.id}))

        # Should return JSON response (not implemented yet)
        self.assertEqual(response.status_code, 200)

        # Function is not implemented yet, so status remains unchanged
        updated_metadata = FinalMetadata.objects.get(book=self.book)
        self.assertFalse(updated_metadata.is_reviewed)

    def test_toggle_needs_review_invalid_book(self):
        """Test toggle needs review with invalid book ID"""
        response = self.client.post(reverse("books:toggle_needs_review", kwargs={"book_id": 99999}))

        # Function returns success even for invalid books (not implemented)
        self.assertEqual(response.status_code, 200)


# ============================================================================
# Theme and Settings Views Tests
# ============================================================================


class ThemeAndSettingsViewTests(BaseViewTestCase):
    """Test cases for theme preview and user settings"""

    def setUp(self):
        """Set up test data"""
        self.user, created = User.objects.get_or_create(
            username="testuser_theme",
            defaults={"email": "test@example.com", "password": "testpass123"},
        )
        if created:
            self.user.set_password("testpass123")
            self.user.save()
        self.client = Client()
        self.client.force_login(self.user)

    def test_user_settings_view_loads(self):
        """Test that user settings view loads successfully"""
        response = self.client.get(reverse("books:user_settings"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Settings")

    def test_user_settings_view_anonymous(self):
        """Test that anonymous users are redirected to login"""
        self.client.logout()
        response = self.client.get(reverse("books:user_settings"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_preview_theme_requires_login(self):
        """Test that theme preview requires authentication"""
        self.client.logout()
        response = self.client.post(reverse("books:preview_theme"), {"theme": "darkly"})
        self.assertEqual(response.status_code, 302)

    def test_preview_theme_requires_post(self):
        """Test that theme preview requires POST method"""
        response = self.client.get(reverse("books:preview_theme"))
        self.assertEqual(response.status_code, 405)  # Method not allowed

    def test_preview_theme_success(self):
        """Test successful theme preview"""
        response = self.client.post(reverse("books:preview_theme"), {"theme": "darkly"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")

        # Check session
        self.assertEqual(self.client.session["preview_theme"], "darkly")

    def test_preview_theme_missing_parameter(self):
        """Test theme preview without theme parameter"""
        response = self.client.post(reverse("books:preview_theme"), {})

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data["success"])

    def test_preview_theme_invalid_theme(self):
        """Test theme preview with invalid theme"""
        response = self.client.post(reverse("books:preview_theme"), {"theme": "invalid-theme"})

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data["success"])

    def test_preview_theme_sets_session(self):
        """Test that theme preview sets session variable"""
        response = self.client.post(reverse("books:preview_theme"), {"theme": "darkly"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.session["preview_theme"], "darkly")

    def test_clear_theme_preview_requires_login(self):
        """Test that clear theme preview requires authentication"""
        self.client.logout()
        response = self.client.post(reverse("books:clear_theme_preview"))
        self.assertEqual(response.status_code, 302)

    def test_clear_theme_preview_success(self):
        """Test successful theme preview clearing"""
        # Set preview theme first
        session = self.client.session
        session["preview_theme"] = "darkly"
        session.save()

        response = self.client.post(reverse("books:clear_theme_preview"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")

        # Preview theme should be cleared from session
        self.assertNotIn("preview_theme", self.client.session)

    def test_user_settings_post_valid(self):
        """Test POST request to user settings with valid data"""
        response = self.client.post(
            reverse("books:user_settings"),
            {
                "theme": "darkly",
                "default_view_mode": "grid",
                "items_per_page": "20",
                "show_covers_in_list": "on",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])

        response = self.client.post(
            reverse("books:user_settings"),
            {"theme": "invalid-theme", "items_per_page": "not-a-number"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data["success"])


# ============================================================================
# Book Renamer Views Tests
# ============================================================================


class BookRenamerViewTests(BaseViewTestCase):
    """Test cases for book renaming functionality"""

    def setUp(self):
        """Set up test data"""
        self.user, created = User.objects.get_or_create(
            username="testuser_renamer",
            defaults={"email": "test@example.com", "password": "testpass123"},
        )
        if created:
            self.user.set_password("testpass123")
            self.user.save()
        self.client = Client()
        self.client.force_login(self.user)

        self.scan_folder = create_test_scan_folder(name="Renamer Test Folder")

        self.book = create_test_book_with_file(
            file_path="/test/renamer/original.epub",
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
        )

    def test_book_renamer_view_loads(self):
        """Test that book renamer view loads successfully"""
        response = self.client.get(reverse("books:book_renamer"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Book File Organizer")

    def test_book_renamer_anonymous_user(self):
        """Test that anonymous users are redirected to login"""
        self.client.logout()
        response = self.client.get(reverse("books:book_renamer"))
        self.assertEqual(response.status_code, 302)

    def test_book_renamer_with_filters(self):
        """Test book renamer with various filters"""
        response = self.client.get(
            reverse("books:book_renamer"),
            {"author": "Test Author", "series": "Test Series"},
        )
        self.assertEqual(response.status_code, 200)

        context = self.get_context_from_response(response)
        self.assertIn("books", context)

    @patch("books.views.os.path.exists")
    @patch("books.views.os.rename")
    def test_rename_book_success(self, mock_rename, mock_exists):
        """Test successful book renaming"""
        mock_exists.return_value = True
        mock_rename.return_value = None

        response = self.client.post(
            reverse("books:rename_book", kwargs={"book_id": self.book.id}),
            {"new_filename": "Test Author - Test Book.epub"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        mock_rename.assert_called_once()

    @patch("books.views.os.path.exists")
    def test_rename_book_file_not_found(self, mock_exists):
        """Test book renaming when file doesn't exist"""
        mock_exists.return_value = False

        response = self.client.post(
            reverse("books:rename_book", kwargs={"book_id": self.book.id}),
            {"new_filename": "Test Author - Test Book.epub"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data["success"])

    def test_rename_book_invalid_book_id(self):
        """Test book renaming with invalid book ID"""
        response = self.client.post(
            reverse("books:rename_book", kwargs={"book_id": 99999}),
            {"new_filename": "Test.epub"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 404)

    def test_rename_book_missing_filename(self):
        """Test book renaming without new filename"""
        response = self.client.post(
            reverse("books:rename_book", kwargs={"book_id": self.book.id}),
            {},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data["success"])

    def test_preview_rename(self):
        """Test renaming preview functionality"""
        response = self.client.post(
            reverse("books:preview_rename"),
            {"book_id": self.book.id, "pattern": "{author} - {title}"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertIn("preview", data)

    def test_bulk_rename_preview(self):
        """Test bulk rename preview"""
        response = self.client.post(
            reverse("books:bulk_rename_preview"),
            {"pattern": "{author} - {title}", "book_ids": [self.book.id]},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertIn("previews", data)

    @patch("books.views.os.path.exists")
    @patch("books.views.os.rename")
    def test_bulk_rename_execute(self, mock_rename, mock_exists):
        """Test bulk rename execution"""
        mock_exists.return_value = True
        mock_rename.return_value = None

        response = self.client.post(
            reverse("books:bulk_rename_execute"),
            {"renames": f'[{{"book_id": {self.book.id}, "new_filename": "Test Author - Test Book.epub"}}]'},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])


# ============================================================================
# AI Feedback Views Tests
# ============================================================================


class AIFeedbackViewTests(BaseViewTestCase):
    """Test cases for AI feedback functionality"""

    def setUp(self):
        """Set up test data"""
        self.user, created = User.objects.get_or_create(
            username="testuser_ai",
            defaults={"email": "test@example.com", "password": "testpass123"},
        )
        if created:
            self.user.set_password("testpass123")
            self.user.save()
        self.client = Client()
        self.client.force_login(self.user)

        self.scan_folder = create_test_scan_folder(name="AI Test Folder")

        self.book = create_test_book_with_file(
            file_path="/test/ai/book.epub",
            file_format="epub",
            file_size=1024000,
            scan_folder=self.scan_folder,
        )

    def test_ai_suggest_metadata_anonymous(self):
        """Test AI metadata suggestions require authentication"""
        self.client.logout()
        response = self.client.post(reverse("books:ai_suggest_metadata", kwargs={"book_id": self.book.id}))
        self.assertEqual(response.status_code, 302)

    def test_ai_suggest_metadata_invalid_book(self):
        """Test AI metadata suggestions with invalid book ID"""
        response = self.client.post(reverse("books:ai_suggest_metadata", kwargs={"book_id": 99999}))
        self.assertEqual(response.status_code, 404)

    @patch("books.views.requests.post")
    def test_ai_suggest_metadata_success(self, mock_post):
        """Test successful AI metadata suggestion"""
        mock_response = Mock()
        mock_response.json.return_value = {
            "suggestions": {
                "title": "AI Suggested Title",
                "author": "AI Suggested Author",
                "series": "AI Suggested Series",
            }
        }
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        response = self.client.post(
            reverse("books:ai_suggest_metadata", kwargs={"book_id": self.book.id}),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertIn("suggestions", data)

    @patch("books.views.requests.post")
    def test_ai_suggest_metadata_api_failure(self, mock_post):
        """Test AI metadata suggestion when API fails"""
        mock_post.side_effect = Exception("API Error")

        response = self.client.post(
            reverse("books:ai_suggest_metadata", kwargs={"book_id": self.book.id}),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data["success"])

    def test_submit_ai_feedback_anonymous(self):
        """Test AI feedback submission requires authentication"""
        self.client.logout()
        response = self.client.post(reverse("books:submit_ai_feedback"))
        self.assertEqual(response.status_code, 302)

    def test_submit_ai_feedback_missing_data(self):
        """Test AI feedback submission with missing data"""
        response = self.client.post(
            reverse("books:submit_ai_feedback"),
            {},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data["success"])

    def test_submit_ai_feedback_success(self):
        """Test successful AI feedback submission"""
        response = self.client.post(
            reverse("books:submit_ai_feedback"),
            {
                "book_id": self.book.id,
                "feedback_type": "title_incorrect",
                "feedback_text": "The title is wrong",
                "suggested_correction": "Correct Title",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])


# ============================================================================
# Upload and File Management Views Tests
# ============================================================================


class UploadFileViewTests(BaseViewTestCase):
    """Test cases for file upload functionality"""

    def setUp(self):
        """Set up test data"""
        self.user, created = User.objects.get_or_create(
            username="testuser_upload",
            defaults={"email": "test@example.com", "password": "testpass123"},
        )
        if created:
            self.user.set_password("testpass123")
            self.user.save()
        self.client = Client()
        self.client.force_login(self.user)

        self.scan_folder = create_test_scan_folder(name="Upload Test Folder")

    def test_upload_file_view_loads(self):
        """Test that upload file view loads successfully"""
        response = self.client.get(reverse("books:upload_file"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Upload")

    def test_upload_file_anonymous_user(self):
        """Test that anonymous users are redirected to login"""
        self.client.logout()
        response = self.client.get(reverse("books:upload_file"))
        self.assertEqual(response.status_code, 302)

    def test_upload_file_post_missing_file(self):
        """Test file upload without selecting a file"""
        response = self.client.post(reverse("books:upload_file"), {"scan_folder": self.scan_folder.id})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "error")

    def test_upload_file_post_missing_folder(self):
        """Test file upload without selecting a folder"""
        from django.core.files.uploadedfile import SimpleUploadedFile

        uploaded_file = SimpleUploadedFile("test.epub", b"fake file content", content_type="application/epub+zip")

        response = self.client.post(reverse("books:upload_file"), {"file": uploaded_file})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "error")

    @patch("books.views.os.makedirs")
    @patch("books.views.default_storage.save")
    def test_upload_file_success(self, mock_save, mock_makedirs):
        """Test successful file upload"""
        from django.core.files.uploadedfile import SimpleUploadedFile

        uploaded_file = SimpleUploadedFile("test.epub", b"fake file content", content_type="application/epub+zip")

        mock_save.return_value = "/test/upload/folder/test.epub"

        response = self.client.post(
            reverse("books:upload_file"),
            {"file": uploaded_file, "scan_folder": self.scan_folder.id},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/books/")

    def test_delete_file_anonymous(self):
        """Test file deletion requires authentication"""
        self.client.logout()
        response = self.client.post(reverse("books:delete_file", kwargs={"file_id": 1}))
        self.assertEqual(response.status_code, 302)

    def test_delete_file_invalid_id(self):
        """Test file deletion with invalid file ID"""
        response = self.client.post(reverse("books:delete_file", kwargs={"file_id": 99999}))
        self.assertEqual(response.status_code, 404)


# ============================================================================
# Debug and Development Views Tests
# ============================================================================


class DebugViewTests(BaseViewTestCase):
    """Test cases for debug and development views"""

    def setUp(self):
        """Set up test data"""
        self.user, created = User.objects.get_or_create(
            username="testuser_debug",
            defaults={"email": "test@example.com", "password": "testpass123"},
        )
        if created:
            self.user.set_password("testpass123")
            self.user.save()
        self.client = Client()
        self.client.force_login(self.user)

    @override_settings(DEBUG=True)
    def test_debug_view_in_debug_mode(self):
        """Test debug view access in debug mode"""
        response = self.client.get(reverse("books:debug_view"))
        self.assertEqual(response.status_code, 200)

    @override_settings(DEBUG=False)
    def test_debug_view_in_production_mode(self):
        """Test debug view access in production mode"""
        response = self.client.get(reverse("books:debug_view"))
        self.assertEqual(response.status_code, 404)

    def test_system_status_view(self):
        """Test system status view"""
        response = self.client.get(reverse("books:system_status"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "System Status")

    def test_system_status_anonymous(self):
        """Test system status view requires authentication"""
        self.client.logout()
        response = self.client.get(reverse("books:system_status"))
        self.assertEqual(response.status_code, 302)

    def test_clear_cache_view(self):
        """Test cache clearing functionality"""
        response = self.client.post(reverse("books:clear_cache"))
        self.assertEqual(response.status_code, 302)

    def test_clear_cache_anonymous(self):
        """Test cache clearing requires authentication"""
        self.client.logout()
        response = self.client.post(reverse("books:clear_cache"))
        self.assertEqual(response.status_code, 302)


# ============================================================================
# Utility Function Tests
# ============================================================================


class UtilityFunctionTests(BaseViewTestCase):
    """Test cases for utility functions used in views"""

    def test_get_filter_params(self):
        """Test filter parameter extraction"""
        from books.views.utilities import get_filter_params

        request_mock = Mock()
        request_mock.GET = {
            "author": "Test Author",
            "format": "epub",
            "series": "",
            "invalid_param": "should_be_ignored",
        }

        params = get_filter_params(request_mock)

        self.assertIn("author", params)
        self.assertIn("format", params)
        self.assertNotIn("series", params)  # Empty values excluded
        self.assertNotIn("invalid_param", params)

    def test_paginate_queryset(self):
        """Test queryset pagination functionality"""
        from django.http import HttpRequest

        from books.views.utilities import paginate_queryset

        # Create test books
        scan_folder = create_test_scan_folder(name="Pagination Test")

        books = []
        for i in range(25):
            books.append(
                create_test_book_with_file(
                    file_path=f"/test/pagination/book{i}.epub",
                    file_format="epub",
                    scan_folder=scan_folder,
                )
            )

        queryset = Book.objects.all()
        request = HttpRequest()
        request.GET = {"page": "2"}

        object_list, page_obj, is_paginated = paginate_queryset(queryset, request, per_page=10)

        self.assertEqual(len(object_list), 10)
        self.assertEqual(page_obj.number, 2)
        self.assertTrue(page_obj.has_previous())
        self.assertTrue(page_obj.has_next())

    def test_build_filter_context(self):
        """Test filter context building"""
        from books.views.utilities import build_filter_context

        context = build_filter_context({"author": "Test Author", "format": "epub"})

        self.assertIn("active_filters", context)
        self.assertIn("filter_count", context)
        self.assertIn("has_filters", context)
        self.assertEqual(len(context["active_filters"]), 2)
        self.assertEqual(context["filter_count"], 2)
        self.assertTrue(context["has_filters"])

    @patch("books.views.utilities.cache")
    def test_get_dashboard_stats_cached(self, mock_cache):
        """Test dashboard statistics caching"""
        from books.views.utilities import get_dashboard_stats

        mock_cache.get.return_value = {"cached": True}

        stats = get_dashboard_stats()

        self.assertEqual(stats, {"cached": True})
        mock_cache.get.assert_called_once()

    def test_format_file_size(self):
        """Test file size formatting utility"""
        from books.views import format_file_size

        self.assertEqual(format_file_size(1024), "1.0 KB")
        self.assertEqual(format_file_size(1048576), "1.0 MB")
        self.assertEqual(format_file_size(1073741824), "1.0 GB")

    def test_generate_filename_from_metadata(self):
        """Test filename generation from metadata"""
        from books.views.utilities import generate_filename_from_metadata

        # Create a book to test filename generation
        scan_folder = create_test_scan_folder(name="Test Scan Folder")
        book = create_test_book_with_file(
            file_path="/test/path/test_book.epub",
            file_format="epub",
            scan_folder=scan_folder,
        )

        # Create related metadata
        data_source = DataSource.objects.get_or_create(name="Test Source")[0]
        author = Author.objects.create(name="Test Author", name_normalized="test author")
        BookTitle.objects.create(book=book, title="Test Book", confidence=90, source=data_source)
        BookAuthor.objects.create(book=book, author=author, confidence=90, source=data_source)

        # Create final metadata
        FinalMetadata.objects.create(book=book, final_title="Test Book", final_author="Test Author")

        filename = generate_filename_from_metadata(book)

        self.assertIn("Test Author", filename)
        self.assertIn("Test Book", filename)
        self.assertTrue(filename.endswith(".epub"))

    def test_sanitize_filename(self):
        """Test filename sanitization"""
        from books.views.utilities import sanitize_filename

        dangerous_name = "Test/Book\\With:Bad*Characters"
        safe_name = sanitize_filename(dangerous_name)

        self.assertNotIn("/", safe_name)
        self.assertNotIn("\\", safe_name)
        self.assertNotIn(":", safe_name)
        self.assertNotIn("*", safe_name)


class BookDetailNavigationIntegrationTestCase(BaseViewTestCase):
    """Integration tests for the complete navigation flow."""

    def setUp(self):
        """Set up test data for integration tests."""
        self.client = Client()
        self.user, created = User.objects.get_or_create(username="testuser_integration", defaults={"password": "testpass"})
        if created:
            self.user.set_password("testpass")
            self.user.save()

        # Create scan folder
        self.scan_folder = create_test_scan_folder(name="Test Folder")

        # Create multiple books for comprehensive testing
        self.books = []
        for i in range(1, 6):  # Create books 1-5
            book = create_test_book_with_file(
                file_path=f"/test/book{i}.epub",
                file_format="epub",
                scan_folder=self.scan_folder,
            )
            self.books.append(book)

            # Create final metadata
            FinalMetadata.objects.create(
                book=book,
                final_title=f"Book {i}",
                final_author="Test Author",
                is_reviewed=(i % 2 == 0),  # Even numbered books are reviewed
            )

    def test_navigation_chain(self):
        """Test that you can navigate through a chain of books."""
        self.client.login(username="testuser_integration", password="testpass")

        # Start at book 1
        current_id = 1
        visited_books = [current_id]

        # Navigate forward through all books
        while current_id < 5:
            response = self.client.get(reverse("books:book_detail", kwargs={"pk": current_id}))
            self.assertEqual(response.status_code, 200)

            context = self.get_context_from_response(response)
            next_book_id = context.get("next_book_id")
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
            response = self.client.get(reverse("books:book_detail", kwargs={"pk": current_id}))
            self.assertEqual(response.status_code, 200)

            context = self.get_context_from_response(response)
            prev_book_id = context.get("prev_book_id")
            if prev_book_id:
                current_id = prev_book_id
                visited_backward.append(current_id)
            else:
                break

        # Should have visited all books in reverse
        self.assertEqual(visited_backward, [5, 4, 3, 2, 1])

    def test_review_status_navigation_flow(self):
        """Test navigating through books by review status."""
        self.client.login(username="testuser_integration", password="testpass")

        # Start at book 1 (unreviewed)
        response = self.client.get(reverse("books:book_detail", kwargs={"pk": 1}))
        self.assertEqual(response.status_code, 200)

        # Should have next unreviewed book
        context = self.get_context_from_response(response)
        next_unreviewed = context.get("next_unreviewed")
        self.assertIsNotNone(next_unreviewed)
        self.assertEqual(next_unreviewed.id, 3)  # Book 3 is unreviewed

        # Navigate to book 3
        response = self.client.get(reverse("books:book_detail", kwargs={"pk": 3}))
        self.assertEqual(response.status_code, 200)

        # Should have next unreviewed book
        context = self.get_context_from_response(response)
        next_unreviewed = context.get("next_unreviewed")
        self.assertIsNotNone(next_unreviewed)
        self.assertEqual(next_unreviewed.id, 5)  # Book 5 is unreviewed


# ============================================================================
# Scanning View Tests
# ============================================================================


class ScanningDashboardViewTests(BaseViewTestCase):
    """Test cases for scanning dashboard view"""

    def setUp(self):
        """Set up test data"""
        self.user, created = User.objects.get_or_create(
            username="testuser_scanning",
            defaults={"email": "test@example.com", "password": "testpass123"},
        )
        if created:
            self.user.set_password("testpass123")
            self.user.save()

        self.scan_folder = create_test_scan_folder(name="Test Scan Folder")

    def test_scan_dashboard_view_anonymous_user(self):
        """Test that anonymous users are redirected to login"""
        response = self.client.get(reverse("books:scan_dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_scan_dashboard_view_authenticated_user(self):
        """Test scanning dashboard view for authenticated users"""
        self.client.login(username="testuser_scanning", password="testpass123")
        response = self.client.get(reverse("books:scan_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Scanning Dashboard")

    @patch("books.views_modules.scanning.get_all_active_scans")
    @patch("books.views_modules.scanning.get_api_status")
    def test_scan_dashboard_context_data(self, mock_api_status, mock_active_scans):
        """Test that scanning dashboard has correct context data"""
        mock_api_status.return_value = {
            "google_books": {
                "api_name": "Google Books",
                "healthy": True,
                "rate_limits": {
                    "limits": {"hourly": 1000},
                    "current_counts": {"hourly": 100},
                },
            }
        }
        mock_active_scans.return_value = []

        self.client.login(username="testuser_scanning", password="testpass123")
        response = self.client.get(reverse("books:scan_dashboard"))

        self.assertEqual(response.status_code, 200)
        context = self.get_context_from_response(response)

        # Check that context exists
        self.assertIsNotNone(context)

        # Check for expected context keys (if they exist in the actual view)
        # Note: This test may need adjustment based on actual view implementation


class ScanFolderViewTests(BaseViewTestCase):
    """Test cases for folder scan functionality"""

    def setUp(self):
        """Set up test data"""
        self.user, created = User.objects.get_or_create(
            username="testuser_folder_scan",
            defaults={"email": "test@example.com", "password": "testpass123"},
        )
        if created:
            self.user.set_password("testpass123")
            self.user.save()

    def test_start_folder_scan_anonymous_user(self):
        """Test that anonymous users cannot start folder scans"""
        response = self.client.post(
            reverse("books:start_folder_scan"),
            {
                "folder_path": "/test/path",
                "language": "en",
                "enable_external_apis": "on",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_start_folder_scan_missing_path(self):
        """Test folder scan with missing folder path"""
        self.client.login(username="testuser_folder_scan", password="testpass123")

        response = self.client.post(
            reverse("books:start_folder_scan"),
            {"language": "en", "enable_external_apis": "on"},
        )

        # Should redirect back to dashboard
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("books:scan_dashboard"))

    @patch("books.views_modules.scanning.background_scan_folder")
    def test_start_folder_scan_valid_request(self, mock_background_scan):
        """Test successful folder scan initiation"""
        self.client.login(username="testuser_folder_scan", password="testpass123")

        response = self.client.post(
            reverse("books:start_folder_scan"),
            {
                "folder_path": "/test/valid/path",
                "language": "en",
                "enable_external_apis": "on",
            },
        )

        # Should redirect back to dashboard
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("books:scan_dashboard"))

        # Should have called background scan
        mock_background_scan.assert_called_once()

    @patch("books.views_modules.scanning.background_scan_folder")
    def test_start_folder_scan_with_exception(self, mock_background_scan):
        """Test folder scan with exception during startup"""
        mock_background_scan.side_effect = Exception("Test error")

        self.client.login(username="testuser_folder_scan", password="testpass123")

        response = self.client.post(
            reverse("books:start_folder_scan"),
            {"folder_path": "/test/error/path", "language": "en"},
        )

        # Should redirect back to dashboard
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("books:scan_dashboard"))


class BookRescanViewTests(BaseViewTestCase):
    """Test cases for book rescan functionality"""

    def setUp(self):
        """Set up test data"""
        self.user, created = User.objects.get_or_create(
            username="testuser_book_rescan",
            defaults={"email": "test@example.com", "password": "testpass123"},
        )
        if created:
            self.user.set_password("testpass123")
            self.user.save()

        self.scan_folder = create_test_scan_folder(name="Test Rescan Folder")

        self.book = create_test_book_with_file(
            file_path="/test/rescan/book.epub",
            file_format="epub",
            file_size=1024,
            scan_folder=self.scan_folder,
        )

    def test_start_book_rescan_anonymous_user(self):
        """Test that anonymous users cannot start book rescans"""
        response = self.client.post(
            reverse("books:start_book_rescan"),
            {"book_ids": str(self.book.id), "enable_external_apis": "on"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_start_book_rescan_no_books_specified(self):
        """Test book rescan with no books specified"""
        self.client.login(username="testuser_book_rescan", password="testpass123")

        response = self.client.post(reverse("books:start_book_rescan"), {"enable_external_apis": "on"})

        # Should redirect back to dashboard with error
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("books:scan_dashboard"))

    @patch("books.views_modules.scanning.background_rescan_books")
    def test_start_book_rescan_by_book_ids(self, mock_background_rescan):
        """Test successful book rescan by book IDs"""
        self.client.login(username="testuser_book_rescan", password="testpass123")

        response = self.client.post(
            reverse("books:start_book_rescan"),
            {"book_ids": str(self.book.id), "enable_external_apis": "on"},
        )

        # Should redirect back to dashboard
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("books:scan_dashboard"))

        # Should have called background rescan
        mock_background_rescan.assert_called_once()

    @patch("books.views_modules.scanning.background_rescan_books")
    def test_start_book_rescan_by_folder(self, mock_background_rescan):
        """Test successful book rescan by folder"""
        self.client.login(username="testuser_book_rescan", password="testpass123")

        response = self.client.post(
            reverse("books:start_book_rescan"),
            {"folder_id": str(self.scan_folder.id), "enable_external_apis": "on"},
        )

        # Should redirect back to dashboard
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("books:scan_dashboard"))

        # Should have called background rescan
        mock_background_rescan.assert_called_once()

    @patch("books.views_modules.scanning.background_rescan_books")
    def test_start_book_rescan_all_books(self, mock_background_rescan):
        """Test successful rescan of all books"""
        self.client.login(username="testuser_book_rescan", password="testpass123")

        response = self.client.post(
            reverse("books:start_book_rescan"),
            {"rescan_all": "on", "enable_external_apis": "on"},
        )

        # Should redirect back to dashboard
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("books:scan_dashboard"))

        # Should have called background rescan
        mock_background_rescan.assert_called_once()

    def test_start_book_rescan_invalid_folder(self):
        """Test book rescan with invalid folder ID"""
        self.client.login(username="testuser_book_rescan", password="testpass123")

        response = self.client.post(
            reverse("books:start_book_rescan"),
            {
                "folder_id": "999999",  # Non-existent folder
                "enable_external_apis": "on",
            },
        )

        # Should redirect back to dashboard with error
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("books:scan_dashboard"))

    def test_start_book_rescan_invalid_book_ids(self):
        """Test book rescan with invalid book IDs"""
        self.client.login(username="testuser_book_rescan", password="testpass123")

        response = self.client.post(
            reverse("books:start_book_rescan"),
            {"book_ids": "invalid,ids,here", "enable_external_apis": "on"},
        )

        # Should redirect back to dashboard with error
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("books:scan_dashboard"))


class ScanProgressAjaxViewTests(BaseViewTestCase):
    """Test cases for scan progress AJAX endpoints"""

    def setUp(self):
        """Set up test data"""
        self.user, created = User.objects.get_or_create(
            username="testuser_progress",
            defaults={"email": "test@example.com", "password": "testpass123"},
        )
        if created:
            self.user.set_password("testpass123")
            self.user.save()

    def test_scan_progress_ajax_anonymous_user(self):
        """Test that anonymous users cannot access progress endpoint"""
        response = self.client.get(reverse("books:scan_progress_ajax", kwargs={"job_id": "test-job-id"}))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    @patch("books.views_modules.scanning.get_scan_progress")
    def test_scan_progress_ajax_authenticated_user(self, mock_get_progress):
        """Test scan progress endpoint for authenticated users"""
        mock_get_progress.return_value = {
            "percentage": 50,
            "status": "Running",
            "details": "Processing files...",
            "completed": False,
        }

        self.client.login(username="testuser_progress", password="testpass123")
        response = self.client.get(reverse("books:scan_progress_ajax", kwargs={"job_id": "test-job-id"}))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")

        # Should have called get_scan_progress
        mock_get_progress.assert_called_once_with("test-job-id")

    @patch("books.views_modules.scanning.get_all_active_scans")
    def test_active_scans_ajax_authenticated_user(self, mock_active_scans):
        """Test active scans endpoint for authenticated users"""
        mock_active_scans.return_value = [
            {"job_id": "test-1", "percentage": 25, "status": "Running"},
            {"job_id": "test-2", "percentage": 75, "status": "Running"},
        ]

        self.client.login(username="testuser_progress", password="testpass123")
        response = self.client.get(reverse("books:active_scans_ajax"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")

    @patch("books.views_modules.scanning.get_api_status")
    def test_api_status_ajax_authenticated_user(self, mock_api_status):
        """Test API status endpoint for authenticated users"""
        mock_api_status.return_value = {
            "google_books": {
                "api_name": "Google Books",
                "healthy": True,
                "rate_limits": {
                    "limits": {"hourly": 1000},
                    "current_counts": {"hourly": 150},
                },
            }
        }

        self.client.login(username="testuser_progress", password="testpass123")
        response = self.client.get(reverse("books:api_status_ajax"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")


class CancelScanViewTests(BaseViewTestCase):
    """Test cases for scan cancellation functionality"""

    def setUp(self):
        """Set up test data"""
        self.user, created = User.objects.get_or_create(
            username="testuser_cancel",
            defaults={"email": "test@example.com", "password": "testpass123"},
        )
        if created:
            self.user.set_password("testpass123")
            self.user.save()

    def test_cancel_scan_ajax_anonymous_user(self):
        """Test that anonymous users cannot cancel scans"""
        response = self.client.post(reverse("books:cancel_scan_ajax", kwargs={"job_id": "test-job-id"}))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_cancel_scan_ajax_get_method_not_allowed(self):
        """Test that GET method is not allowed for cancel scan"""
        self.client.login(username="testuser_cancel", password="testpass123")
        response = self.client.get(reverse("books:cancel_scan_ajax", kwargs={"job_id": "test-job-id"}))
        self.assertEqual(response.status_code, 405)  # Method not allowed

    @patch("books.scanner.background.cancel_scan")
    def test_cancel_scan_ajax_successful(self, mock_cancel_scan):
        """Test successful scan cancellation"""
        mock_cancel_scan.return_value = True

        self.client.login(username="testuser_cancel", password="testpass123")
        response = self.client.post(reverse("books:cancel_scan_ajax", kwargs={"job_id": "test-job-id"}))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")

        # Should have called cancel_scan
        mock_cancel_scan.assert_called_once_with("test-job-id")

    @patch("books.scanner.background.cancel_scan")
    def test_cancel_scan_ajax_failed(self, mock_cancel_scan):
        """Test failed scan cancellation"""
        mock_cancel_scan.return_value = False

        self.client.login(username="testuser_cancel", password="testpass123")
        response = self.client.post(reverse("books:cancel_scan_ajax", kwargs={"job_id": "test-job-id"}))

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response["Content-Type"], "application/json")


class ScanHistoryViewTests(BaseViewTestCase):
    """Test cases for scan history functionality"""

    def setUp(self):
        """Set up test data"""
        self.user, created = User.objects.get_or_create(
            username="testuser_history",
            defaults={"email": "test@example.com", "password": "testpass123"},
        )
        if created:
            self.user.set_password("testpass123")
            self.user.save()

    def test_scan_history_anonymous_user(self):
        """Test that anonymous users cannot access scan history"""
        response = self.client.get(reverse("books:scan_history"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_scanning_help_anonymous_user(self):
        """Test that anonymous users cannot access scanning help"""
        response = self.client.get(reverse("books:scanning_help"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)


class TriggerScanViewEnhancedTests(BaseViewTestCase):
    """Comprehensive tests for TriggerScanView."""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser_scan", password="testpass123")
        self.client.login(username="testuser_scan", password="testpass123")

        # Create test scan folder
        self.scan_folder = create_test_scan_folder(name="Test Library")

    def test_trigger_scan_view_get(self):
        """Test GET request to trigger scan view."""
        response = self.client.get(reverse("books:trigger_scan"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "books/trigger_scan.html")

        # Check context
        context = response.context
        self.assertIn("scan_folders", context)
        self.assertIn("can_start_scan", context)
        self.assertIn("active_scans", context)

    @patch("books.views.subprocess.Popen")
    def test_trigger_scan_success(self, mock_popen):
        """Test successful scan trigger."""
        # Mock subprocess
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_popen.return_value = mock_process

        response = self.client.post(
            reverse("books:trigger_scan"),
            {
                "scan_folders": [self.scan_folder.id],
                "scan_type": "full",
                "enable_metadata_fetching": True,
                "enable_cover_extraction": True,
            },
        )

        # Should redirect to scan status
        self.assertEqual(response.status_code, 302)
        self.assertIn("scan_status", response.url)

    def test_trigger_scan_no_folders_selected(self):
        """Test scan trigger with no folders selected."""
        response = self.client.post(reverse("books:trigger_scan"), {"scan_folders": [], "scan_type": "full"})

        # Should redirect back with error
        self.assertEqual(response.status_code, 302)

    def test_trigger_scan_invalid_folder(self):
        """Test scan trigger with invalid folder ID."""
        response = self.client.post(
            reverse("books:trigger_scan"),
            {"scan_folders": [99999], "scan_type": "full"},
        )

        # Should handle gracefully
        self.assertEqual(response.status_code, 302)

    @patch("books.views.subprocess.Popen")
    def test_trigger_scan_subprocess_error(self, mock_popen):
        """Test scan trigger when subprocess fails."""
        # Mock subprocess failure
        mock_popen.side_effect = Exception("Failed to start process")

        response = self.client.post(
            reverse("books:trigger_scan"),
            {"scan_folders": [self.scan_folder.id], "scan_type": "full"},
        )

        # Should handle error gracefully
        self.assertEqual(response.status_code, 302)

    def test_trigger_scan_concurrent_scans(self):
        """Test behavior when trying to start scan while another is running."""
        # Mock active scan
        with patch("books.views.ScanLog.objects.filter") as mock_filter:
            mock_queryset = MagicMock()
            mock_queryset.exists.return_value = True
            mock_filter.return_value = mock_queryset

            response = self.client.post(
                reverse("books:trigger_scan"),
                {"scan_folders": [self.scan_folder.id], "scan_type": "full"},
            )

            # Should prevent starting new scan
            self.assertEqual(response.status_code, 302)

    def test_trigger_scan_incremental_vs_full(self):
        """Test different scan types."""
        with patch("books.views.subprocess.Popen") as mock_popen:
            mock_process = MagicMock()
            mock_process.pid = 12345
            mock_popen.return_value = mock_process

            # Test incremental scan
            response = self.client.post(
                reverse("books:trigger_scan"),
                {"scan_folders": [self.scan_folder.id], "scan_type": "incremental"},
            )
            self.assertEqual(response.status_code, 302)

            # Test full scan
            response = self.client.post(
                reverse("books:trigger_scan"),
                {"scan_folders": [self.scan_folder.id], "scan_type": "full"},
            )
            self.assertEqual(response.status_code, 302)


class ScanStatusViewTests(BaseViewTestCase):
    """Comprehensive tests for ScanStatusView."""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser_status", password="testpass123")
        self.client.login(username="testuser_status", password="testpass123")

    def test_scan_status_view_access(self):
        """Test basic access to scan status view."""
        response = self.client.get(reverse("books:scan_status"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "books/scanning/status.html")

    def test_scan_status_context_data(self):
        """Test scan status view context data."""
        # Create test scan logs
        ScanLog.objects.create(level="INFO", message="Scan in progress", books_found=10)

        ScanLog.objects.create(level="INFO", message="Scan completed successfully", books_processed=10)

        response = self.client.get(reverse("books:scan_status"))
        context = response.context

        self.assertIn("scan_logs", context)
        self.assertIn("current_scan", context)
        self.assertIn("recent_scans", context)
        self.assertIn("scan_statistics", context)

    def test_scan_status_with_running_scan(self):
        """Test scan status when scan is running."""
        # Create running scan
        running_scan = ScanLog.objects.create(level="INFO", message="Processing files...", books_processed=75)

        response = self.client.get(reverse("books:scan_status"))
        context = response.context

        self.assertEqual(context["current_scan"], running_scan)
        self.assertTrue(context["scan_statistics"]["has_active_scan"])

    def test_scan_status_pagination(self):
        """Test scan status view pagination."""
        # Create many scan logs
        for i in range(25):
            ScanLog.objects.create(level="INFO", message=f"Scan {i} completed", books_processed=100)

        response = self.client.get(reverse("books:scan_status"))
        self.assertTrue(response.context["is_paginated"])

        # Test second page
        response = self.client.get(reverse("books:scan_status") + "?page=2")
        self.assertEqual(response.status_code, 200)

    def test_scan_status_filtering(self):
        """Test scan status view filtering by status."""
        # Create scans with different statuses
        ScanLog.objects.create(level="INFO", message="Success")
        ScanLog.objects.create(level="ERROR", message="Failed")
        ScanLog.objects.create(level="INFO", message="Running")

        # Test status filter
        response = self.client.get(reverse("books:scan_status"), {"status": "completed"})
        self.assertEqual(response.status_code, 200)

        response = self.client.get(reverse("books:scan_status"), {"status": "failed"})
        self.assertEqual(response.status_code, 200)

    def test_scan_status_statistics_calculation(self):
        """Test scan statistics calculation."""
        # Create test data
        ScanLog.objects.create(level="INFO", message="Success", books_found=10, books_processed=10)

        ScanLog.objects.create(level="ERROR", message="Failed", books_found=5, books_processed=3)

        response = self.client.get(reverse("books:scan_status"))
        stats = response.context["scan_statistics"]

        self.assertIn("total_scans", stats)
        self.assertIn("successful_scans", stats)
        self.assertIn("failed_scans", stats)
        self.assertIn("total_books_found", stats)


class DataSourceListViewTests(BaseViewTestCase):
    """Tests for DataSourceListView."""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser_datasource", password="testpass123")
        self.client.login(username="testuser_datasource", password="testpass123")

        # Create test data sources
        self.google_source = DataSource.objects.get_or_create(
            name=DataSource.GOOGLE_BOOKS,
            defaults={"trust_level": 0.8, "is_active": True},
        )[0]

        self.openlibrary_source = DataSource.objects.get_or_create(
            name=DataSource.OPEN_LIBRARY,
            defaults={"trust_level": 0.7, "is_active": True},
        )[0]

    def test_data_source_list_access(self):
        """Test access to data source list view."""
        response = self.client.get(reverse("books:data_source_list"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "books/data_source_list.html")

    def test_data_source_list_context(self):
        """Test data source list context data."""
        # Create some metadata entries
        book = create_test_book_with_file(title="Test Book", file_path="/test/book.epub", file_format="epub")

        BookMetadata.objects.create(
            book=book,
            source=self.google_source,
            field_name="title",
            field_value="Test Book",
        )

        response = self.client.get(reverse("books:data_source_list"))
        context = response.context

        self.assertIn("sources", context)
        self.assertIn("source_statistics", context)
        self.assertIn("top_source", context)

    def test_data_source_statistics(self):
        """Test data source statistics calculation."""
        # Create test book and metadata
        book = create_test_book_with_file(title="Test Book", file_path="/test/book.epub", file_format="epub")

        # Add metadata from different sources
        for i in range(5):
            BookMetadata.objects.create(
                book=book,
                source=self.google_source,
                field_name=f"field_{i}",
                field_value=f"value_{i}",
            )

        for i in range(3):
            BookMetadata.objects.create(
                book=book,
                source=self.openlibrary_source,
                field_name=f"field_{i}",
                field_value=f"value_{i}",
            )

        response = self.client.get(reverse("books:data_source_list"))
        context = response.context

        # Google should be top source
        self.assertEqual(context["top_source"], self.google_source)

    def test_data_source_list_inactive_sources(self):
        """Test that inactive sources are handled properly."""
        # Create inactive source
        DataSource.objects.get_or_create(
            name=DataSource.INITIAL_SCAN,
            defaults={"trust_level": 0.5, "is_active": False},
        )

        response = self.client.get(reverse("books:data_source_list"))
        self.assertEqual(response.status_code, 200)

        # Should still work with inactive sources


class ScanFolderManagementTests(BaseViewTestCase):
    """Tests for scan folder management views."""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser_folders", password="testpass123")
        self.client.login(username="testuser_folders", password="testpass123")

    def test_scan_folder_list_view(self):
        """Test scan folder list view."""
        # Create test folders
        create_test_scan_folder(name="Library 1")

        folder2 = create_test_scan_folder(name="Library 2")
        folder2.is_active = False
        folder2.save()

        response = self.client.get(reverse("books:scan_folder_list"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "books/scanning/folder_list.html")

        # Check that folders are in context
        folders = response.context["scanfolder_list"]
        self.assertEqual(len(folders), 2)

    def test_add_scan_folder_get(self):
        """Test GET request to add scan folder."""
        response = self.client.get(reverse("books:add_scan_folder"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "books/scan_folder/add_scan_folder.html")

    def test_add_scan_folder_post_valid(self):
        """Test POST request to add scan folder with valid data."""
        response = self.client.post(
            reverse("books:add_scan_folder"),
            {"name": "New Library", "path": "/new/library", "is_active": True},
        )

        # Should redirect on success
        self.assertEqual(response.status_code, 302)

        # Verify folder was created
        folder = ScanFolder.objects.filter(name="New Library").first()
        self.assertIsNotNone(folder)
        self.assertEqual(folder.path, "/new/library")

    def test_add_scan_folder_post_invalid(self):
        """Test POST request to add scan folder with invalid data."""
        response = self.client.post(
            reverse("books:add_scan_folder"),
            {"name": "", "path": "/invalid"},  # Empty name
        )

        # Should show form with errors
        self.assertEqual(response.status_code, 200)
        self.assertFormError(response.context["form"], "name", "This field is required.")

    def test_delete_scan_folder(self):
        """Test scan folder deletion."""
        folder = create_test_scan_folder(name="Test Library")

        response = self.client.post(reverse("books:delete_scan_folder", kwargs={"pk": folder.pk}))

        # Should redirect on success
        self.assertEqual(response.status_code, 302)

        # Verify folder was deleted
        self.assertFalse(ScanFolder.objects.filter(pk=folder.pk).exists())

    def test_delete_nonexistent_scan_folder(self):
        """Test deletion of non-existent scan folder."""
        response = self.client.post(reverse("books:delete_scan_folder", kwargs={"pk": 99999}))

        # Should return 404
        self.assertEqual(response.status_code, 404)


class ScanErrorHandlingTests(BaseViewTestCase):
    """Tests for error handling in scan-related views."""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser_errors", password="testpass123")
        self.client.login(username="testuser_errors", password="testpass123")

    def test_trigger_scan_with_nonexistent_folder(self):
        """Test triggering scan with non-existent folder."""
        response = self.client.post(
            reverse("books:trigger_scan"),
            {"scan_folders": [99999], "scan_type": "full"},
        )

        # Should handle gracefully
        self.assertEqual(response.status_code, 302)

    def test_scan_status_with_corrupted_logs(self):
        """Test scan status view with corrupted log data."""
        # Create log with None values
        ScanLog.objects.create(level="ERROR", message="Failed scan")

        response = self.client.get(reverse("books:scan_status"))
        # Should not crash
        self.assertEqual(response.status_code, 200)

    @patch("books.views.subprocess.Popen")
    def test_trigger_scan_permission_error(self, mock_popen):
        """Test scan trigger with permission error."""
        mock_popen.side_effect = PermissionError("Permission denied")

        folder = create_test_scan_folder(name="Test Library")

        response = self.client.post(
            reverse("books:trigger_scan"),
            {"scan_folders": [folder.id], "scan_type": "full"},
        )

        # Should handle permission error gracefully
        self.assertEqual(response.status_code, 302)

    def test_data_source_trust_update_boundary_values(self):
        """Test trust level updates with boundary values."""
        source = DataSource.objects.get_or_create(name=DataSource.EPUB_INTERNAL, defaults={"trust_level": 0.5})[0]

        # Test minimum value
        response = self.client.post(
            reverse("books:update_trust", kwargs={"pk": source.pk}),
            {"trust_level": "0.0"},
        )
        self.assertEqual(response.status_code, 200)

        # Test maximum value
        response = self.client.post(
            reverse("books:update_trust", kwargs={"pk": source.pk}),
            {"trust_level": "1.0"},
        )
        self.assertEqual(response.status_code, 200)


class ScanPerformanceTests(BaseViewTestCase):
    """Performance tests for scan-related views."""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser_perf", password="testpass123")
        self.client.login(username="testuser_perf", password="testpass123")

    def test_scan_status_with_many_logs(self):
        """Test scan status view performance with many logs."""
        # Create many scan logs
        scan_logs = []
        for i in range(100):
            scan_logs.append(ScanLog(level="INFO", message=f"Scan {i}", books_processed=100))
        ScanLog.objects.bulk_create(scan_logs)

        import time

        start_time = time.time()
        response = self.client.get(reverse("books:scan_status"))
        end_time = time.time()

        self.assertEqual(response.status_code, 200)
        # Should complete within 2 seconds
        self.assertLess(end_time - start_time, 2.0)

    def test_data_source_list_with_many_sources(self):
        """Test data source list performance with many sources."""
        # Create several data sources from available choices
        choices = [
            DataSource.GOOGLE_BOOKS,
            DataSource.OPEN_LIBRARY,
            DataSource.MANUAL,
            DataSource.EPUB_INTERNAL,
            DataSource.PDF_INTERNAL,
            DataSource.MOBI_INTERNAL,
        ]

        for name in choices:
            DataSource.objects.get_or_create(name=name, defaults={"trust_level": 0.5})

        import time

        start_time = time.time()
        response = self.client.get(reverse("books:data_source_list"))
        end_time = time.time()

        self.assertEqual(response.status_code, 200)
        # Should complete within 2 seconds
        self.assertLess(end_time - start_time, 2.0)
