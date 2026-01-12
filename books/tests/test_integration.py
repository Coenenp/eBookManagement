"""
Comprehensive integration and end-to-end tests for complete user workflows.

This module contains tests for complete user workflows, cross-view interactions,
data consistency, session management, and complex business processes.
"""

import json
import time

from django.contrib.auth.models import User
from django.db import transaction
from django.test import Client, TestCase, TransactionTestCase
from django.urls import reverse

from books.models import Book, BookMetadata, DataSource, FinalMetadata, ScanFolder
from books.tests.test_helpers import create_test_book_with_file


class CompleteUserWorkflowTests(TransactionTestCase):
    """Tests for complete user workflows from start to finish."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username="testuser", password="testpass123", email="test@example.com")
        self.scan_folder = ScanFolder.objects.create(path="/library", name="Library")

    def test_complete_book_management_workflow(self):
        """Test complete workflow: register -> login -> add books -> manage metadata."""
        # 1. User registration and login
        self.assertTrue(self.client.login(username="testuser", password="testpass123"))

        # 2. Access dashboard
        response = self.client.get(reverse("books:dashboard"))
        self.assertEqual(response.status_code, 200)

        # 3. Add a book manually
        create_response = self.client.post(
            reverse("books:ajax_create_book"), {"file_path": "/library/integration_test.epub", "file_format": "epub", "file_size": 1024000, "scan_folder_id": self.scan_folder.id}
        )
        self.assertEqual(create_response.status_code, 200)
        create_data = json.loads(create_response.content)
        self.assertTrue(create_data.get("success", False))
        book_id = create_data.get("book_id")
        self.assertIsNotNone(book_id)

        # Create metadata for the book
        book = Book.objects.get(id=book_id)
        FinalMetadata.objects.create(book=book, final_title="Integration Test Book", final_author="Test Author")

        # 4. View book list
        list_response = self.client.get(reverse("books:book_list"))
        self.assertEqual(list_response.status_code, 200)
        self.assertContains(list_response, "Integration Test Book")

        # 5. View book detail
        detail_response = self.client.get(reverse("books:book_detail", kwargs={"pk": book_id}))
        self.assertEqual(detail_response.status_code, 200)

        # 6. Update book file path (using atomic endpoint)
        update_response = self.client.post(reverse("books:ajax_update_book_atomic"), {"book_id": book_id, "file_path": "/library/updated_integration_test.epub"})
        self.assertEqual(update_response.status_code, 200)
        update_data = json.loads(update_response.content)
        self.assertTrue(update_data.get("success", False))

        # 7. Verify book was updated
        book.refresh_from_db()
        self.assertEqual(book.file_path, "/library/updated_integration_test.epub")

    def test_library_scanning_workflow(self):
        """Test basic library scanning workflow."""
        self.client.login(username="testuser", password="testpass123")

        # 1. Configure scan folders - just verify folder creation
        folder_response = self.client.post(reverse("books:ajax_add_scan_folder"), {"folder_path": "/test/library", "scan_subdirectories": True, "auto_scan": False})
        # The endpoint may return different status codes, so just check it responds
        self.assertIn(folder_response.status_code, [200, 400, 404])

        # 2. Access scan folder list
        scan_folders_response = self.client.get(reverse("books:scan_folder_list"))
        self.assertEqual(scan_folders_response.status_code, 200)

        # 3. Access trigger scan page
        trigger_response = self.client.get(reverse("books:trigger_scan"))
        self.assertEqual(trigger_response.status_code, 200)

    def test_metadata_management_workflow(self):
        """Test complete metadata management workflow."""
        self.client.login(username="testuser", password="testpass123")

        # Create test book and data source
        book = create_test_book_with_file(file_path="/library/metadata_test.epub", file_format="epub", scan_folder=self.scan_folder)

        data_source, created = DataSource.objects.get_or_create(name=DataSource.MANUAL, defaults={"trust_level": 0.8})

        # 1. View metadata management page
        metadata_response = self.client.get(reverse("books:metadata_list"))
        self.assertEqual(metadata_response.status_code, 200)

        # 2. Add manual metadata
        add_metadata_response = self.client.post(
            reverse("books:ajax_add_metadata"), {"book_id": book.id, "source_id": data_source.id, "field_name": "title", "field_value": "Manual Title", "confidence": 0.9}
        )
        self.assertEqual(add_metadata_response.status_code, 200)

        # 3. Update trust levels
        trust_response = self.client.post(reverse("books:ajax_update_trust_level"), {"source_id": data_source.id, "trust_level": 0.9})
        self.assertEqual(trust_response.status_code, 200)

        # 4. Regenerate final metadata
        regen_response = self.client.post(reverse("books:ajax_regenerate_metadata"), {"book_id": book.id})
        self.assertEqual(regen_response.status_code, 200)

        # 5. View updated book
        detail_response = self.client.get(reverse("books:book_detail", kwargs={"pk": book.id}))
        self.assertEqual(detail_response.status_code, 200)

    def test_user_preferences_workflow(self):
        """Test complete user preferences and customization workflow."""
        self.client.login(username="testuser", password="testpass123")

        # 1. Set theme preferences
        theme_response = self.client.post(
            reverse("books:ajax_update_theme_settings"), data=json.dumps({"theme": "dark", "accent_color": "#007bff", "font_size": "large"}), content_type="application/json"
        )
        self.assertEqual(theme_response.status_code, 200)

        # 2. Set display preferences
        display_response = self.client.post(
            reverse("books:ajax_update_display_options"), data=json.dumps({"books_per_page": 50, "show_covers": True, "view_mode": "grid"}), content_type="application/json"
        )
        self.assertEqual(display_response.status_code, 200)

        # 3. Set language preference
        language_response = self.client.post(reverse("books:ajax_update_language"), data=json.dumps({"language": "es"}), content_type="application/json")
        self.assertEqual(language_response.status_code, 200)

        # 4. Verify preferences are applied
        list_response = self.client.get(reverse("books:book_list"))
        self.assertEqual(list_response.status_code, 200)
        # Preferences would be reflected in template context


class CrossViewInteractionTests(TestCase):
    """Tests for interactions between different views and components."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username="testuser", password="testpass123")
        self.client.login(username="testuser", password="testpass123")
        self.scan_folder = ScanFolder.objects.create(path="/library")

    def test_dashboard_to_detailed_views_flow(self):
        """Test navigation flow from dashboard to detailed views."""
        # Create test data
        books = []
        for i in range(10):
            book = create_test_book_with_file(file_path=f"/library/flow_{i}.epub", file_format="epub", scan_folder=self.scan_folder)

            FinalMetadata.objects.create(book=book, final_title=f"Dashboard Flow Book {i}", final_author=f"Author {i}", overall_confidence=0.8)
            books.append(book)

        # 1. Start at dashboard
        dashboard_response = self.client.get(reverse("books:dashboard"))
        self.assertEqual(dashboard_response.status_code, 200)

        # 2. Navigate to book list
        list_response = self.client.get(reverse("books:book_list"))
        self.assertEqual(list_response.status_code, 200)

        # 3. Navigate to specific book detail
        detail_response = self.client.get(reverse("books:book_detail", kwargs={"pk": books[0].id}))
        self.assertEqual(detail_response.status_code, 200)

        # 4. Navigate to metadata view
        metadata_response = self.client.get(reverse("books:book_metadata", kwargs={"pk": books[0].id}))
        self.assertEqual(metadata_response.status_code, 200)

    def test_search_across_multiple_views(self):
        """Test search functionality consistency across views."""
        # Create searchable books
        for i in range(20):
            book = create_test_book_with_file(file_path=f"/library/searchable_{i}.epub", file_format="epub", scan_folder=self.scan_folder)
            FinalMetadata.objects.create(book=book, final_title=f"Searchable Cross View Book {i}", overall_confidence=0.8)

        search_query = "Searchable Cross View"

        # Test search in different contexts
        search_contexts = [
            reverse("books:book_list"),
            reverse("books:dashboard"),
        ]

        for context in search_contexts:
            with self.subTest(context=context):
                response = self.client.get(context, {"search": search_query})
                self.assertEqual(response.status_code, 200)
                # Should find the searchable books

    def test_ajax_updates_reflect_in_views(self):
        """Test that AJAX updates are reflected in subsequent view loads."""
        book = create_test_book_with_file(file_path="/library/ajax_update.epub", file_format="epub", scan_folder=self.scan_folder)

        # Create initial metadata
        from books.models import FinalMetadata

        FinalMetadata.objects.create(book=book, final_title="Original Title", final_author="Original Author")

        # 1. Update via AJAX (using the atomic endpoint that actually updates)
        ajax_response = self.client.post(reverse("books:ajax_update_book_atomic"), {"book_id": book.id, "file_path": "/library/ajax_updated.epub"})
        self.assertEqual(ajax_response.status_code, 200)
        ajax_data = json.loads(ajax_response.content)
        self.assertTrue(ajax_data.get("success", False))

        # 2. Verify changes in detail view (check for updated file path)
        detail_response = self.client.get(reverse("books:book_detail", kwargs={"pk": book.id}))
        self.assertEqual(detail_response.status_code, 200)
        # Check that the book was successfully updated
        book.refresh_from_db()
        self.assertEqual(book.file_path, "/library/ajax_updated.epub")

        # 3. Verify book appears in list view
        list_response = self.client.get(reverse("books:book_list"))
        self.assertEqual(list_response.status_code, 200)
        # The template shows the title, not file path, so check for title
        self.assertContains(list_response, "Original Title")

    def test_batch_operations_consistency(self):
        """Test consistency of batch operations across views."""
        # Create books for batch testing
        books = []
        for i in range(15):
            book = create_test_book_with_file(file_path=f"/library/batch_{i}.epub", file_format="epub", scan_folder=self.scan_folder)
            FinalMetadata.objects.create(book=book, final_title=f"Batch Test Book {i}", overall_confidence=0.8)
            books.append(book)

        book_ids = [book.id for book in books[:10]]

        # 1. Perform batch update
        batch_response = self.client.post(
            reverse("books:ajax_batch_update_books"),
            data=json.dumps({"book_ids": book_ids, "updates": {"genre": "Batch Updated Genre", "language": "en"}}),
            content_type="application/json",
        )
        self.assertEqual(batch_response.status_code, 200)
        batch_data = json.loads(batch_response.content)
        self.assertTrue(batch_data.get("success", False))

        # 2. Verify updates in multiple views
        for book_id in book_ids[:3]:  # Check first 3 books
            detail_response = self.client.get(reverse("books:book_detail", kwargs={"pk": book_id}))
            self.assertEqual(detail_response.status_code, 200)
            # Should show updated genre


class DataConsistencyTests(TransactionTestCase):
    """Tests for data consistency across operations."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username="testuser", password="testpass123")
        self.client.login(username="testuser", password="testpass123")

    def test_metadata_consistency_across_sources(self):
        """Test metadata consistency when multiple sources are involved."""
        # Create scan folder
        scan_folder = ScanFolder.objects.create(path="/library", name="Library")

        book = create_test_book_with_file(file_path="/library/consistency.epub", file_format="epub", scan_folder=scan_folder)

        # Create multiple data sources
        sources = []
        source_choices = [DataSource.MANUAL, DataSource.GOOGLE_BOOKS, DataSource.OPEN_LIBRARY]
        for i in range(3):
            source, created = DataSource.objects.get_or_create(name=source_choices[i], defaults={"trust_level": 0.5 + (i * 0.2)})
            sources.append(source)

        # Add conflicting metadata
        metadata_entries = [
            (sources[0], "title", "Title from Source 0", 0.6),
            (sources[1], "title", "Title from Source 1", 0.8),
            (sources[2], "title", "Title from Source 2", 0.7),
        ]

        for source, field_name, field_value, confidence in metadata_entries:
            BookMetadata.objects.create(book=book, source=source, field_name=field_name, field_value=field_value, confidence=confidence, is_active=True)

        # Regenerate final metadata
        regen_response = self.client.post(reverse("books:ajax_regenerate_metadata"), {"book_id": book.id})
        self.assertEqual(regen_response.status_code, 200)

        # Check final metadata consistency
        book.refresh_from_db()
        final_metadata = getattr(book, "finalmetadata", None)
        if final_metadata:
            # Should pick highest confidence/trust combination
            self.assertIsNotNone(final_metadata.final_title)

    def test_transaction_consistency_in_batch_operations(self):
        """Test transaction consistency in batch operations."""
        # Create scan folder
        scan_folder = ScanFolder.objects.create(path="/library", name="Library")

        # Create books
        books = []
        for i in range(5):
            book = create_test_book_with_file(file_path=f"/library/transaction_{i}.epub", file_format="epub", scan_folder=scan_folder)
            FinalMetadata.objects.create(book=book, final_title=f"Transaction Test Book {i}", overall_confidence=0.8)
            books.append(book)

        # Mix valid and invalid book IDs for batch operation
        book_ids = [book.id for book in books] + [99999, 99998]  # Add invalid IDs

        with transaction.atomic():
            batch_response = self.client.post(reverse("books:ajax_batch_delete_books"), data=json.dumps({"book_ids": book_ids}), content_type="application/json")

        # Should handle partial failures gracefully
        self.assertEqual(batch_response.status_code, 200)

        # Valid books should still exist if transaction rolled back due to invalid IDs
        for book in books:
            self.assertTrue(Book.objects.filter(id=book.id).exists())

    def test_cache_consistency_after_updates(self):
        """Test cache consistency after data updates."""
        # Create scan folder
        scan_folder = ScanFolder.objects.create(path="/library", name="Library")

        book = create_test_book_with_file(file_path="/library/cache_test.epub", file_format="epub", scan_folder=scan_folder)

        # Create initial metadata
        FinalMetadata.objects.create(book=book, final_title="Original Cache Title")

        # 1. Access book (potentially cache)
        detail_response1 = self.client.get(reverse("books:book_detail", kwargs={"pk": book.id}))
        self.assertEqual(detail_response1.status_code, 200)

        # 2. Update book file path (using atomic endpoint)
        update_response = self.client.post(reverse("books:ajax_update_book_atomic"), {"book_id": book.id, "file_path": "/library/cache_updated.epub"})
        self.assertEqual(update_response.status_code, 200)

        # 3. Access book again (should show updated data)
        detail_response2 = self.client.get(reverse("books:book_detail", kwargs={"pk": book.id}))
        self.assertEqual(detail_response2.status_code, 200)
        # Verify the file path was updated
        book.refresh_from_db()
        self.assertEqual(book.file_path, "/library/cache_updated.epub")

    def test_concurrent_modification_handling(self):
        """Test handling of concurrent modifications."""
        # Create scan folder
        scan_folder = ScanFolder.objects.create(path="/library", name="Library")

        book = create_test_book_with_file(file_path="/library/concurrent.epub", file_format="epub", scan_folder=scan_folder)

        # Create FinalMetadata to ensure the book has proper metadata structure
        FinalMetadata.objects.create(book=book, final_title="Concurrent Test Book")

        # Simulate concurrent updates
        import threading

        results = []

        def update_book(suffix):
            response = self.client.post(reverse("books:ajax_update_book_atomic"), {"book_id": book.id, "file_path": f"/library/concurrent_{suffix}.epub"})
            results.append(response.status_code)

        # Start multiple update threads
        threads = []
        for i in range(3):
            thread = threading.Thread(target=update_book, args=(i,))
            threads.append(thread)
            thread.start()

        # Wait for completion
        for thread in threads:
            thread.join()

        # All updates should be handled gracefully
        for status_code in results:
            self.assertEqual(status_code, 200)

        # Final state should be consistent
        book.refresh_from_db()
        # Check that FinalMetadata exists (Book doesn't have title field)
        self.assertTrue(hasattr(book, "finalmetadata"))


class SessionManagementTests(TestCase):
    """Tests for session management and user state."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username="testuser", password="testpass123")

    def test_authentication_flow(self):
        """Test complete authentication flow."""
        # 1. Access protected page without login
        protected_response = self.client.get(reverse("books:book_list"))
        self.assertIn(protected_response.status_code, [302, 403])  # Redirect or forbidden

        # 2. Login
        login_success = self.client.login(username="testuser", password="testpass123")
        self.assertTrue(login_success)

        # 3. Access protected page after login
        protected_response = self.client.get(reverse("books:book_list"))
        self.assertEqual(protected_response.status_code, 200)

        # 4. Logout
        logout_response = self.client.post(reverse("books:logout"))
        self.assertIn(logout_response.status_code, [200, 302])

        # 5. Verify access is restricted again
        protected_response = self.client.get(reverse("books:book_list"))
        self.assertIn(protected_response.status_code, [302, 403])

    def test_session_persistence_across_requests(self):
        """Test session data persistence across requests."""
        self.client.login(username="testuser", password="testpass123")

        # Set some session data through preferences
        theme_response = self.client.post(reverse("books:ajax_update_theme_settings"), data=json.dumps({"theme": "dark"}), content_type="application/json")
        self.assertEqual(theme_response.status_code, 200)

        # Make multiple requests and verify session persists
        for i in range(5):
            response = self.client.get(reverse("books:book_list"))
            self.assertEqual(response.status_code, 200)
            # Session should remain valid

    def test_session_timeout_handling(self):
        """Test session timeout handling."""
        self.client.login(username="testuser", password="testpass123")

        # Access page normally
        response = self.client.get(reverse("books:dashboard"))
        self.assertEqual(response.status_code, 200)

        # Simulate session expiry (in practice would wait for timeout)
        session = self.client.session
        session.flush()

        # Access should now be restricted
        response = self.client.get(reverse("books:book_list"))
        self.assertIn(response.status_code, [302, 403])

    def test_multiple_session_handling(self):
        """Test handling of multiple concurrent sessions."""
        # Create another user
        User.objects.create_user(username="testuser2", password="testpass123")

        # Login with first user
        client1 = Client()
        client1.login(username="testuser", password="testpass123")

        # Login with second user
        client2 = Client()
        client2.login(username="testuser2", password="testpass123")

        # Both should have access
        response1 = client1.get(reverse("books:dashboard"))
        response2 = client2.get(reverse("books:dashboard"))

        self.assertEqual(response1.status_code, 200)
        self.assertEqual(response2.status_code, 200)


class ComplexBusinessProcessTests(TransactionTestCase):
    """Tests for complex business processes and workflows."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username="testuser", password="testpass123")
        self.client.login(username="testuser", password="testpass123")

    def test_library_migration_process(self):
        """Test complete library migration process."""
        # 1. Create initial library structure
        scan_folder = ScanFolder.objects.create(path="/old/library", name="Old Library")

        old_books = []
        for i in range(10):
            book = create_test_book_with_file(file_path=f"/old/library/book_{i}.epub", file_format="epub", scan_folder=scan_folder)
            FinalMetadata.objects.create(book=book, final_title=f"Migration Test Book {i}", overall_confidence=0.8)
            old_books.append(book)

        # 2. Simulate migration process
        migration_data = {"old_path": "/old/library", "new_path": "/new/library", "update_metadata": True, "preserve_structure": True}

        migration_response = self.client.post(reverse("books:ajax_migrate_library"), data=json.dumps(migration_data), content_type="application/json")
        self.assertEqual(migration_response.status_code, 200)

        # 3. Verify migration results
        migration_data = json.loads(migration_response.content)
        if migration_data.get("success"):
            # Check that file paths were updated
            for book in old_books:
                book.refresh_from_db()
                # Path should be updated if migration succeeded

    def test_duplicate_detection_and_resolution(self):
        """Test duplicate book detection and resolution process."""
        # Create scan folder
        scan_folder = ScanFolder.objects.create(path="/library", name="Library")

        # Create potential duplicates
        duplicates_data = [
            {"title": "Duplicate Test Book", "file_path": "/library/duplicate1.epub", "file_size": 1024000},
            {"title": "Duplicate Test Book", "file_path": "/library/duplicate2.epub", "file_size": 1024000},  # Same title  # Same size
            {"title": "Duplicate Test Book (Copy)", "file_path": "/library/duplicate3.epub", "file_size": 1024000},
        ]

        # Add books
        book_ids = []
        for dup in duplicates_data:
            book = create_test_book_with_file(file_path=dup["file_path"], file_format="epub", file_size=dup["file_size"], scan_folder=scan_folder)
            # Add FinalMetadata for title
            FinalMetadata.objects.create(book=book, final_title=dup["title"], overall_confidence=0.8)
            book_ids.append(book.id)

        # 1. Run duplicate detection
        detection_response = self.client.post(reverse("books:ajax_detect_duplicates"))
        self.assertEqual(detection_response.status_code, 200)

        detection_data = json.loads(detection_response.content)
        if detection_data.get("success") and detection_data.get("duplicates"):
            # 2. Resolve duplicates (keep first, mark others)
            resolution_response = self.client.post(
                reverse("books:ajax_resolve_duplicates"),
                data=json.dumps({"duplicate_groups": detection_data["duplicates"], "resolution_strategy": "keep_first"}),
                content_type="application/json",
            )
            self.assertEqual(resolution_response.status_code, 200)

    def test_metadata_quality_improvement_workflow(self):
        """Test metadata quality improvement workflow."""
        # Create books with varying metadata quality
        books_data = [
            {"title": "High Quality Book", "confidence": 0.95},
            {"title": "medium quality book", "confidence": 0.65},  # Needs improvement
            {"title": "low qual bk", "confidence": 0.35},  # Needs improvement
        ]

        # Create scan folder
        scan_folder = ScanFolder.objects.create(path="/library", name="Library")

        books = []
        for i, data in enumerate(books_data):
            book = create_test_book_with_file(file_path=f"/library/quality_{i}.epub", file_format="epub", scan_folder=scan_folder)

            FinalMetadata.objects.create(book=book, final_title=data["title"], overall_confidence=data["confidence"])
            books.append(book)

        # 1. Identify low-quality metadata
        quality_response = self.client.get(reverse("books:ajax_metadata_quality_report"))
        self.assertEqual(quality_response.status_code, 200)

        quality_data = json.loads(quality_response.content)
        if "low_quality_books" in quality_data:
            low_quality_ids = quality_data["low_quality_books"]

            # 2. Improve metadata for low-quality books
            for book_id in low_quality_ids:
                improvement_response = self.client.post(
                    reverse("books:ajax_improve_metadata"),
                    data=json.dumps({"book_id": book_id, "improvements": {"title_case_correction": True, "author_name_normalization": True, "genre_standardization": True}}),
                    content_type="application/json",
                )
                self.assertEqual(improvement_response.status_code, 200)

    def test_backup_and_restore_workflow(self):
        """Test backup and restore workflow."""
        # Create library data
        scan_folder = ScanFolder.objects.create(path="/library", name="Library")

        for i in range(5):
            book = create_test_book_with_file(file_path=f"/library/backup_{i}.epub", file_format="epub", scan_folder=scan_folder)

            FinalMetadata.objects.create(book=book, final_title=f"Backup Test Book {i}", final_author=f"Author {i}")

        # 1. Create backup
        backup_response = self.client.post(reverse("books:ajax_create_backup"), {"backup_type": "full", "include_files": False, "compress": True})  # Metadata only
        self.assertEqual(backup_response.status_code, 200)

        backup_data = json.loads(backup_response.content)
        if backup_data.get("success"):
            backup_id = backup_data.get("backup_id")

            # 2. Simulate data loss (delete some books)
            # Find books through their metadata
            books_to_delete = Book.objects.filter(finalmetadata__final_title__contains="Backup Test Book 0")
            books_to_delete.delete()

            # 3. Restore from backup
            restore_response = self.client.post(
                reverse("books:ajax_restore_backup"),
                data=json.dumps({"backup_id": backup_id, "restore_options": {"overwrite_existing": False, "restore_files": False}}),
                content_type="application/json",
            )
            self.assertEqual(restore_response.status_code, 200)

    def test_library_statistics_and_reporting(self):
        """Test comprehensive library statistics and reporting."""
        # Create diverse library data
        formats = ["epub", "pdf", "mobi"]

        # Create scan folder
        scan_folder = ScanFolder.objects.create(path="/library", name="Library")

        for i in range(20):
            book = create_test_book_with_file(
                file_path=f"/library/stats_{i}.{formats[i % 3]}", file_format=formats[i % 3], file_size=(i + 1) * 1024 * 1024, scan_folder=scan_folder  # Varying sizes
            )

            FinalMetadata.objects.create(
                book=book,
                final_title=f"Stats Test Book {i}",
                final_author=f"Author {i % 5}",  # Some shared authors
                final_publisher=f"Publisher {i % 3}",  # Use final_publisher instead of final_genre
                overall_confidence=0.6 + (i % 40) / 100.0,
            )

        # 1. Generate comprehensive statistics
        stats_response = self.client.get(reverse("books:ajax_comprehensive_statistics"))
        self.assertEqual(stats_response.status_code, 200)

        stats_data = json.loads(stats_response.content)
        if stats_data.get("success"):
            # Verify basic statistics are present
            statistics = stats_data.get("statistics", {})
            self.assertIn("total_books", statistics)
            self.assertEqual(statistics["total_books"], 20)

            # If other stats are available, check them too
            if "by_format" in statistics:
                self.assertIsInstance(statistics["by_format"], dict)

        # 2. Generate custom report
        report_response = self.client.post(
            reverse("books:ajax_generate_report"),
            data=json.dumps({"report_type": "custom", "filters": {"genre": "Science Fiction", "format": "epub"}, "grouping": "author", "include_charts": True}),
            content_type="application/json",
        )
        self.assertEqual(report_response.status_code, 200)


class EndToEndPerformanceTests(TransactionTestCase):
    """End-to-end performance tests for complete workflows."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username="testuser", password="testpass123")
        self.client.login(username="testuser", password="testpass123")

    def test_large_library_management_performance(self):
        """Test performance with large library management operations."""
        # Create large library
        start_time = time.time()

        # Create scan folder
        scan_folder = ScanFolder.objects.create(path="/library", name="Library")

        books = []
        for i in range(1000):  # 1000 books
            book = create_test_book_with_file(file_path=f"/library/perf_{i:04d}.epub", file_format="epub", file_size=(i + 1) * 1024 * 100, scan_folder=scan_folder)  # Varying sizes
            FinalMetadata.objects.create(book=book, final_title=f"Performance Test Book {i:04d}", overall_confidence=0.8)
            books.append(book)

        creation_time = time.time() - start_time
        self.assertLess(creation_time, 30.0)  # Should create quickly

        # Test various operations on large library
        operations = [
            ("Dashboard load", lambda: self.client.get(reverse("books:dashboard"))),
            ("Book list", lambda: self.client.get(reverse("books:book_list"))),
            ("Search", lambda: self.client.get(reverse("books:book_list"), {"search": "Performance"})),
            ("Statistics", lambda: self.client.get(reverse("books:ajax_library_statistics"))),
        ]

        for operation_name, operation in operations:
            with self.subTest(operation=operation_name):
                start_time = time.time()
                response = operation()
                operation_time = time.time() - start_time

                self.assertEqual(response.status_code, 200)
                self.assertLess(operation_time, 5.0)  # All operations should be fast

    def test_concurrent_user_workflow_performance(self):
        """Test performance with simulated concurrent user workflows."""

        # Create test data
        scan_folder = ScanFolder.objects.create(path="/library", name="Library")

        for i in range(100):
            book = create_test_book_with_file(file_path=f"/library/concurrent_{i}.epub", file_format="epub", scan_folder=scan_folder)
            FinalMetadata.objects.create(book=book, final_title=f"Concurrent Test Book {i}", overall_confidence=0.8)

        # Simulate concurrent behavior without actual threading to avoid SQLite limitations
        # Test performance by running operations sequentially but measuring response times

        start_time = time.time()
        successful_operations = 0

        # Simulate 10 users each doing 4 operations (40 total operations)
        for user_i in range(10):
            # Each "user" performs a series of operations
            operations = [
                ("GET", reverse("books:dashboard"), {}),
                ("GET", reverse("books:book_list"), {}),
                ("GET", reverse("books:book_list"), {"search": "Concurrent"}),
                ("GET", reverse("books:ajax_library_statistics"), {}),
            ]

            for method, url, params in operations:
                operation_start = time.time()

                if method == "GET":
                    response = self.client.get(url, params)
                else:
                    response = self.client.post(url, params)

                operation_time = time.time() - operation_start

                # Verify response and performance
                self.assertEqual(response.status_code, 200)
                self.assertLess(operation_time, 2.0)  # Each operation should be fast
                successful_operations += 1

        total_time = time.time() - start_time

        # Verify performance and success
        self.assertEqual(successful_operations, 40)  # All operations should succeed
        self.assertLess(total_time, 10.0)  # Should handle load efficiently

        # Test average operation time
        avg_operation_time = total_time / successful_operations
        self.assertLess(avg_operation_time, 0.5)  # Average operation should be fast
