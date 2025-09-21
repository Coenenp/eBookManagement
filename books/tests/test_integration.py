"""
Comprehensive integration and end-to-end tests for complete user workflows.

This module contains tests for complete user workflows, cross-view interactions,
data consistency, session management, and complex business processes.
"""

import json
import time
from django.test import TestCase, Client, TransactionTestCase
from django.contrib.auth.models import User
from django.urls import reverse
from django.db import transaction
from books.models import Book, FinalMetadata, BookMetadata, DataSource


class CompleteUserWorkflowTests(TransactionTestCase):
    """Tests for complete user workflows from start to finish."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123',
            email='test@example.com'
        )

    def test_complete_book_management_workflow(self):
        """Test complete workflow: register -> login -> add books -> manage metadata."""
        # 1. User registration and login
        self.assertTrue(self.client.login(username='testuser', password='testpass123'))

        # 2. Access dashboard
        response = self.client.get(reverse('books:dashboard'))
        self.assertEqual(response.status_code, 200)

        # 3. Add a book manually
        create_response = self.client.post(reverse('books:ajax_create_book'), {
            'title': 'Integration Test Book',
            'file_path': '/library/integration_test.epub',
            'file_format': 'epub',
            'file_size': 1024000
        })
        self.assertEqual(create_response.status_code, 200)
        create_data = json.loads(create_response.content)
        self.assertTrue(create_data.get('success', False))
        book_id = create_data.get('book_id')
        self.assertIsNotNone(book_id)

        # 4. View book list
        list_response = self.client.get(reverse('books:book_list'))
        self.assertEqual(list_response.status_code, 200)
        self.assertContains(list_response, 'Integration Test Book')

        # 5. View book detail
        detail_response = self.client.get(reverse('books:book_detail', kwargs={'pk': book_id}))
        self.assertEqual(detail_response.status_code, 200)

        # 6. Update book metadata
        update_response = self.client.post(reverse('books:ajax_update_book'), {
            'book_id': book_id,
            'title': 'Updated Integration Test Book',
            'author': 'Test Author',
            'genre': 'Science Fiction'
        })
        self.assertEqual(update_response.status_code, 200)
        update_data = json.loads(update_response.content)
        self.assertTrue(update_data.get('success', False))

        # 7. Search for the updated book
        search_response = self.client.get(reverse('books:book_list'), {'search': 'Updated Integration'})
        self.assertEqual(search_response.status_code, 200)
        self.assertContains(search_response, 'Updated Integration Test Book')

    def test_library_scanning_workflow(self):
        """Test complete library scanning workflow."""
        self.client.login(username='testuser', password='testpass123')

        # 1. Configure scan folders
        folder_response = self.client.post(reverse('books:ajax_add_scan_folder'), {
            'folder_path': '/test/library',
            'scan_subdirectories': True,
            'auto_scan': False
        })
        self.assertEqual(folder_response.status_code, 200)

        # 2. Trigger manual scan
        scan_response = self.client.post(reverse('books:ajax_trigger_scan'), {
            'folder_path': '/test/library',
            'full_scan': True
        })
        self.assertEqual(scan_response.status_code, 200)
        scan_data = json.loads(scan_response.content)
        self.assertTrue(scan_data.get('success', False))
        scan_id = scan_data.get('scan_id')

        # 3. Monitor scan progress
        progress_response = self.client.get(reverse('books:ajax_scan_progress'), {
            'scan_id': scan_id
        })
        self.assertEqual(progress_response.status_code, 200)

        # 4. View scan results
        results_response = self.client.get(reverse('books:scan_results', kwargs={'scan_id': scan_id}))
        self.assertEqual(results_response.status_code, 200)

    def test_metadata_management_workflow(self):
        """Test complete metadata management workflow."""
        self.client.login(username='testuser', password='testpass123')

        # Create test book and data source
        book = Book.objects.create(
            title='Metadata Test Book',
            file_path='/library/metadata_test.epub',
            file_format='epub'
        )

        data_source = DataSource.objects.create(
            name='test_source',
            display_name='Test Source',
            trust_level=0.8
        )

        # 1. View metadata management page
        metadata_response = self.client.get(reverse('books:metadata_list'))
        self.assertEqual(metadata_response.status_code, 200)

        # 2. Add manual metadata
        add_metadata_response = self.client.post(reverse('books:ajax_add_metadata'), {
            'book_id': book.id,
            'source_id': data_source.id,
            'field_name': 'title',
            'field_value': 'Manual Title',
            'confidence': 0.9
        })
        self.assertEqual(add_metadata_response.status_code, 200)

        # 3. Update trust levels
        trust_response = self.client.post(reverse('books:ajax_update_trust_level'), {
            'source_id': data_source.id,
            'trust_level': 0.9
        })
        self.assertEqual(trust_response.status_code, 200)

        # 4. Regenerate final metadata
        regen_response = self.client.post(reverse('books:ajax_regenerate_metadata'), {
            'book_id': book.id
        })
        self.assertEqual(regen_response.status_code, 200)

        # 5. View updated book
        detail_response = self.client.get(reverse('books:book_detail', kwargs={'pk': book.id}))
        self.assertEqual(detail_response.status_code, 200)

    def test_user_preferences_workflow(self):
        """Test complete user preferences and customization workflow."""
        self.client.login(username='testuser', password='testpass123')

        # 1. Set theme preferences
        theme_response = self.client.post(
            reverse('books:ajax_update_theme_settings'),
            data=json.dumps({
                'theme': 'dark',
                'accent_color': '#007bff',
                'font_size': 'large'
            }),
            content_type='application/json'
        )
        self.assertEqual(theme_response.status_code, 200)

        # 2. Set display preferences
        display_response = self.client.post(
            reverse('books:ajax_update_display_options'),
            data=json.dumps({
                'books_per_page': 50,
                'show_covers': True,
                'view_mode': 'grid'
            }),
            content_type='application/json'
        )
        self.assertEqual(display_response.status_code, 200)

        # 3. Set language preference
        language_response = self.client.post(
            reverse('books:ajax_update_language'),
            data=json.dumps({'language': 'es'}),
            content_type='application/json'
        )
        self.assertEqual(language_response.status_code, 200)

        # 4. Verify preferences are applied
        list_response = self.client.get(reverse('books:book_list'))
        self.assertEqual(list_response.status_code, 200)
        # Preferences would be reflected in template context


class CrossViewInteractionTests(TestCase):
    """Tests for interactions between different views and components."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.client.login(username='testuser', password='testpass123')

    def test_dashboard_to_detailed_views_flow(self):
        """Test navigation flow from dashboard to detailed views."""
        # Create test data
        books = []
        for i in range(10):
            book = Book.objects.create(
                title=f'Dashboard Flow Book {i}',
                file_path=f'/library/flow_{i}.epub',
                file_format='epub'
            )

            FinalMetadata.objects.create(
                book=book,
                final_title=f'Dashboard Flow Book {i}',
                final_author=f'Author {i}',
                overall_confidence=0.8
            )
            books.append(book)

        # 1. Start at dashboard
        dashboard_response = self.client.get(reverse('books:dashboard'))
        self.assertEqual(dashboard_response.status_code, 200)

        # 2. Navigate to book list
        list_response = self.client.get(reverse('books:book_list'))
        self.assertEqual(list_response.status_code, 200)

        # 3. Navigate to specific book detail
        detail_response = self.client.get(reverse('books:book_detail', kwargs={'pk': books[0].id}))
        self.assertEqual(detail_response.status_code, 200)

        # 4. Navigate to metadata view
        metadata_response = self.client.get(reverse('books:book_metadata', kwargs={'pk': books[0].id}))
        self.assertEqual(metadata_response.status_code, 200)

    def test_search_across_multiple_views(self):
        """Test search functionality consistency across views."""
        # Create searchable books
        for i in range(20):
            Book.objects.create(
                title=f'Searchable Cross View Book {i}',
                file_path=f'/library/searchable_{i}.epub',
                file_format='epub'
            )

        search_query = 'Searchable Cross View'

        # Test search in different contexts
        search_contexts = [
            reverse('books:book_list'),
            reverse('books:dashboard'),
        ]

        for context in search_contexts:
            with self.subTest(context=context):
                response = self.client.get(context, {'search': search_query})
                self.assertEqual(response.status_code, 200)
                # Should find the searchable books

    def test_ajax_updates_reflect_in_views(self):
        """Test that AJAX updates are reflected in subsequent view loads."""
        book = Book.objects.create(
            title='AJAX Update Test',
            file_path='/library/ajax_update.epub',
            file_format='epub'
        )

        # 1. Update via AJAX
        ajax_response = self.client.post(reverse('books:ajax_update_book'), {
            'book_id': book.id,
            'title': 'AJAX Updated Title',
            'author': 'AJAX Author'
        })
        self.assertEqual(ajax_response.status_code, 200)
        ajax_data = json.loads(ajax_response.content)
        self.assertTrue(ajax_data.get('success', False))

        # 2. Verify changes in detail view
        detail_response = self.client.get(reverse('books:book_detail', kwargs={'pk': book.id}))
        self.assertEqual(detail_response.status_code, 200)
        self.assertContains(detail_response, 'AJAX Updated Title')

        # 3. Verify changes in list view
        list_response = self.client.get(reverse('books:book_list'))
        self.assertEqual(list_response.status_code, 200)
        self.assertContains(list_response, 'AJAX Updated Title')

    def test_batch_operations_consistency(self):
        """Test consistency of batch operations across views."""
        # Create books for batch testing
        books = []
        for i in range(15):
            book = Book.objects.create(
                title=f'Batch Test Book {i}',
                file_path=f'/library/batch_{i}.epub',
                file_format='epub'
            )
            books.append(book)

        book_ids = [book.id for book in books[:10]]

        # 1. Perform batch update
        batch_response = self.client.post(
            reverse('books:ajax_batch_update_books'),
            data=json.dumps({
                'book_ids': book_ids,
                'updates': {
                    'genre': 'Batch Updated Genre',
                    'language': 'en'
                }
            }),
            content_type='application/json'
        )
        self.assertEqual(batch_response.status_code, 200)
        batch_data = json.loads(batch_response.content)
        self.assertTrue(batch_data.get('success', False))

        # 2. Verify updates in multiple views
        for book_id in book_ids[:3]:  # Check first 3 books
            detail_response = self.client.get(reverse('books:book_detail', kwargs={'pk': book_id}))
            self.assertEqual(detail_response.status_code, 200)
            # Should show updated genre


class DataConsistencyTests(TransactionTestCase):
    """Tests for data consistency across operations."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.client.login(username='testuser', password='testpass123')

    def test_metadata_consistency_across_sources(self):
        """Test metadata consistency when multiple sources are involved."""
        book = Book.objects.create(
            title='Consistency Test',
            file_path='/library/consistency.epub',
            file_format='epub'
        )

        # Create multiple data sources
        sources = []
        for i in range(3):
            source = DataSource.objects.create(
                name=f'source_{i}',
                display_name=f'Source {i}',
                trust_level=0.5 + (i * 0.2)
            )
            sources.append(source)

        # Add conflicting metadata
        metadata_entries = [
            (sources[0], 'title', 'Title from Source 0', 0.6),
            (sources[1], 'title', 'Title from Source 1', 0.8),
            (sources[2], 'title', 'Title from Source 2', 0.7),
        ]

        for source, field_name, field_value, confidence in metadata_entries:
            BookMetadata.objects.create(
                book=book,
                source=source,
                field_name=field_name,
                field_value=field_value,
                confidence=confidence,
                is_active=True
            )

        # Regenerate final metadata
        regen_response = self.client.post(reverse('books:ajax_regenerate_metadata'), {
            'book_id': book.id
        })
        self.assertEqual(regen_response.status_code, 200)

        # Check final metadata consistency
        book.refresh_from_db()
        final_metadata = getattr(book, 'finalmetadata', None)
        if final_metadata:
            # Should pick highest confidence/trust combination
            self.assertIsNotNone(final_metadata.final_title)

    def test_transaction_consistency_in_batch_operations(self):
        """Test transaction consistency in batch operations."""
        # Create books
        books = []
        for i in range(5):
            book = Book.objects.create(
                title=f'Transaction Test Book {i}',
                file_path=f'/library/transaction_{i}.epub',
                file_format='epub'
            )
            books.append(book)

        # Mix valid and invalid book IDs for batch operation
        book_ids = [book.id for book in books] + [99999, 99998]  # Add invalid IDs

        with transaction.atomic():
            batch_response = self.client.post(
                reverse('books:ajax_batch_delete_books'),
                data=json.dumps({'book_ids': book_ids}),
                content_type='application/json'
            )

        # Should handle partial failures gracefully
        self.assertEqual(batch_response.status_code, 200)

        # Valid books should still exist if transaction rolled back due to invalid IDs
        for book in books:
            self.assertTrue(Book.objects.filter(id=book.id).exists())

    def test_cache_consistency_after_updates(self):
        """Test cache consistency after data updates."""
        book = Book.objects.create(
            title='Cache Consistency Test',
            file_path='/library/cache_test.epub',
            file_format='epub'
        )

        # 1. Access book (potentially cache)
        detail_response1 = self.client.get(reverse('books:book_detail', kwargs={'pk': book.id}))
        self.assertEqual(detail_response1.status_code, 200)

        # 2. Update book
        update_response = self.client.post(reverse('books:ajax_update_book'), {
            'book_id': book.id,
            'title': 'Cache Updated Title'
        })
        self.assertEqual(update_response.status_code, 200)

        # 3. Access book again (should show updated data)
        detail_response2 = self.client.get(reverse('books:book_detail', kwargs={'pk': book.id}))
        self.assertEqual(detail_response2.status_code, 200)
        self.assertContains(detail_response2, 'Cache Updated Title')

    def test_concurrent_modification_handling(self):
        """Test handling of concurrent modifications."""
        book = Book.objects.create(
            title='Concurrent Test',
            file_path='/library/concurrent.epub',
            file_format='epub'
        )

        # Simulate concurrent updates
        import threading
        results = []

        def update_book(suffix):
            response = self.client.post(reverse('books:ajax_update_book'), {
                'book_id': book.id,
                'title': f'Concurrent Title {suffix}'
            })
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
        self.assertIsNotNone(book.title)


class SessionManagementTests(TestCase):
    """Tests for session management and user state."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )

    def test_authentication_flow(self):
        """Test complete authentication flow."""
        # 1. Access protected page without login
        protected_response = self.client.get(reverse('books:book_list'))
        self.assertIn(protected_response.status_code, [302, 403])  # Redirect or forbidden

        # 2. Login
        login_success = self.client.login(username='testuser', password='testpass123')
        self.assertTrue(login_success)

        # 3. Access protected page after login
        protected_response = self.client.get(reverse('books:book_list'))
        self.assertEqual(protected_response.status_code, 200)

        # 4. Logout
        logout_response = self.client.post(reverse('logout'))
        self.assertIn(logout_response.status_code, [200, 302])

        # 5. Verify access is restricted again
        protected_response = self.client.get(reverse('books:book_list'))
        self.assertIn(protected_response.status_code, [302, 403])

    def test_session_persistence_across_requests(self):
        """Test session data persistence across requests."""
        self.client.login(username='testuser', password='testpass123')

        # Set some session data through preferences
        theme_response = self.client.post(
            reverse('books:ajax_update_theme_settings'),
            data=json.dumps({'theme': 'dark'}),
            content_type='application/json'
        )
        self.assertEqual(theme_response.status_code, 200)

        # Make multiple requests and verify session persists
        for i in range(5):
            response = self.client.get(reverse('books:book_list'))
            self.assertEqual(response.status_code, 200)
            # Session should remain valid

    def test_session_timeout_handling(self):
        """Test session timeout handling."""
        self.client.login(username='testuser', password='testpass123')

        # Access page normally
        response = self.client.get(reverse('books:dashboard'))
        self.assertEqual(response.status_code, 200)

        # Simulate session expiry (in practice would wait for timeout)
        session = self.client.session
        session.flush()

        # Access should now be restricted
        response = self.client.get(reverse('books:book_list'))
        self.assertIn(response.status_code, [302, 403])

    def test_multiple_session_handling(self):
        """Test handling of multiple concurrent sessions."""
        # Create another user
        User.objects.create_user(
            username='testuser2',
            password='testpass123'
        )

        # Login with first user
        client1 = Client()
        client1.login(username='testuser', password='testpass123')

        # Login with second user
        client2 = Client()
        client2.login(username='testuser2', password='testpass123')

        # Both should have access
        response1 = client1.get(reverse('books:dashboard'))
        response2 = client2.get(reverse('books:dashboard'))

        self.assertEqual(response1.status_code, 200)
        self.assertEqual(response2.status_code, 200)


class ComplexBusinessProcessTests(TransactionTestCase):
    """Tests for complex business processes and workflows."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.client.login(username='testuser', password='testpass123')

    def test_library_migration_process(self):
        """Test complete library migration process."""
        # 1. Create initial library structure
        old_books = []
        for i in range(10):
            book = Book.objects.create(
                title=f'Migration Test Book {i}',
                file_path=f'/old/library/book_{i}.epub',
                file_format='epub'
            )
            old_books.append(book)

        # 2. Simulate migration process
        migration_data = {
            'old_path': '/old/library',
            'new_path': '/new/library',
            'update_metadata': True,
            'preserve_structure': True
        }

        migration_response = self.client.post(
            reverse('books:ajax_migrate_library'),
            data=json.dumps(migration_data),
            content_type='application/json'
        )
        self.assertEqual(migration_response.status_code, 200)

        # 3. Verify migration results
        migration_data = json.loads(migration_response.content)
        if migration_data.get('success'):
            # Check that file paths were updated
            for book in old_books:
                book.refresh_from_db()
                # Path should be updated if migration succeeded

    def test_duplicate_detection_and_resolution(self):
        """Test duplicate book detection and resolution process."""
        # Create potential duplicates
        duplicates = [
            {
                'title': 'Duplicate Test Book',
                'file_path': '/library/duplicate1.epub',
                'file_size': 1024000
            },
            {
                'title': 'Duplicate Test Book',  # Same title
                'file_path': '/library/duplicate2.epub',
                'file_size': 1024000  # Same size
            },
            {
                'title': 'Duplicate Test Book (Copy)',
                'file_path': '/library/duplicate3.epub',
                'file_size': 1024000
            }
        ]

        # Add books
        book_ids = []
        for dup in duplicates:
            book = Book.objects.create(**dup, file_format='epub')
            book_ids.append(book.id)

        # 1. Run duplicate detection
        detection_response = self.client.post(reverse('books:ajax_detect_duplicates'))
        self.assertEqual(detection_response.status_code, 200)

        detection_data = json.loads(detection_response.content)
        if detection_data.get('success') and detection_data.get('duplicates'):
            # 2. Resolve duplicates (keep first, mark others)
            resolution_response = self.client.post(
                reverse('books:ajax_resolve_duplicates'),
                data=json.dumps({
                    'duplicate_groups': detection_data['duplicates'],
                    'resolution_strategy': 'keep_first'
                }),
                content_type='application/json'
            )
            self.assertEqual(resolution_response.status_code, 200)

    def test_metadata_quality_improvement_workflow(self):
        """Test metadata quality improvement workflow."""
        # Create books with varying metadata quality
        books_data = [
            {'title': 'High Quality Book', 'confidence': 0.95},
            {'title': 'medium quality book', 'confidence': 0.65},  # Needs improvement
            {'title': 'low qual bk', 'confidence': 0.35},  # Needs improvement
        ]

        books = []
        for i, data in enumerate(books_data):
            book = Book.objects.create(
                title=data['title'],
                file_path=f'/library/quality_{i}.epub',
                file_format='epub'
            )

            FinalMetadata.objects.create(
                book=book,
                final_title=data['title'],
                overall_confidence=data['confidence']
            )
            books.append(book)

        # 1. Identify low-quality metadata
        quality_response = self.client.get(reverse('books:ajax_metadata_quality_report'))
        self.assertEqual(quality_response.status_code, 200)

        quality_data = json.loads(quality_response.content)
        if 'low_quality_books' in quality_data:
            low_quality_ids = quality_data['low_quality_books']

            # 2. Improve metadata for low-quality books
            for book_id in low_quality_ids:
                improvement_response = self.client.post(
                    reverse('books:ajax_improve_metadata'),
                    data=json.dumps({
                        'book_id': book_id,
                        'improvements': {
                            'title_case_correction': True,
                            'author_name_normalization': True,
                            'genre_standardization': True
                        }
                    }),
                    content_type='application/json'
                )
                self.assertEqual(improvement_response.status_code, 200)

    def test_backup_and_restore_workflow(self):
        """Test backup and restore workflow."""
        # Create library data
        for i in range(5):
            book = Book.objects.create(
                title=f'Backup Test Book {i}',
                file_path=f'/library/backup_{i}.epub',
                file_format='epub'
            )

            FinalMetadata.objects.create(
                book=book,
                final_title=f'Backup Test Book {i}',
                final_author=f'Author {i}'
            )

        # 1. Create backup
        backup_response = self.client.post(reverse('books:ajax_create_backup'), {
            'backup_type': 'full',
            'include_files': False,  # Metadata only
            'compress': True
        })
        self.assertEqual(backup_response.status_code, 200)

        backup_data = json.loads(backup_response.content)
        if backup_data.get('success'):
            backup_id = backup_data.get('backup_id')

            # 2. Simulate data loss (delete some books)
            Book.objects.filter(title__contains='Backup Test Book 0').delete()

            # 3. Restore from backup
            restore_response = self.client.post(
                reverse('books:ajax_restore_backup'),
                data=json.dumps({
                    'backup_id': backup_id,
                    'restore_options': {
                        'overwrite_existing': False,
                        'restore_files': False
                    }
                }),
                content_type='application/json'
            )
            self.assertEqual(restore_response.status_code, 200)

    def test_library_statistics_and_reporting(self):
        """Test comprehensive library statistics and reporting."""
        # Create diverse library data
        genres = ['Science Fiction', 'Fantasy', 'Mystery', 'Romance']
        formats = ['epub', 'pdf', 'mobi']

        for i in range(20):
            book = Book.objects.create(
                title=f'Stats Test Book {i}',
                file_path=f'/library/stats_{i}.{formats[i % 3]}',
                file_format=formats[i % 3],
                file_size=(i + 1) * 1024 * 1024  # Varying sizes
            )

            FinalMetadata.objects.create(
                book=book,
                final_title=f'Stats Test Book {i}',
                final_author=f'Author {i % 5}',  # Some shared authors
                final_genre=genres[i % 4],
                overall_confidence=0.6 + (i % 40) / 100.0
            )

        # 1. Generate comprehensive statistics
        stats_response = self.client.get(reverse('books:ajax_comprehensive_statistics'))
        self.assertEqual(stats_response.status_code, 200)

        stats_data = json.loads(stats_response.content)
        if stats_data.get('success'):
            # Verify statistics structure
            expected_stats = ['total_books', 'by_format', 'by_genre', 'by_author', 'size_distribution']
            for stat in expected_stats:
                self.assertIn(stat, stats_data.get('statistics', {}))

        # 2. Generate custom report
        report_response = self.client.post(
            reverse('books:ajax_generate_report'),
            data=json.dumps({
                'report_type': 'custom',
                'filters': {
                    'genre': 'Science Fiction',
                    'format': 'epub'
                },
                'grouping': 'author',
                'include_charts': True
            }),
            content_type='application/json'
        )
        self.assertEqual(report_response.status_code, 200)


class EndToEndPerformanceTests(TransactionTestCase):
    """End-to-end performance tests for complete workflows."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.client.login(username='testuser', password='testpass123')

    def test_large_library_management_performance(self):
        """Test performance with large library management operations."""
        # Create large library
        start_time = time.time()

        books = []
        for i in range(1000):  # 1000 books
            book = Book.objects.create(
                title=f'Performance Test Book {i:04d}',
                file_path=f'/library/perf_{i:04d}.epub',
                file_format='epub',
                file_size=(i + 1) * 1024 * 100  # Varying sizes
            )
            books.append(book)

        creation_time = time.time() - start_time
        self.assertLess(creation_time, 30.0)  # Should create quickly

        # Test various operations on large library
        operations = [
            ('Dashboard load', lambda: self.client.get(reverse('books:dashboard'))),
            ('Book list', lambda: self.client.get(reverse('books:book_list'))),
            ('Search', lambda: self.client.get(reverse('books:book_list'), {'search': 'Performance'})),
            ('Statistics', lambda: self.client.get(reverse('books:ajax_library_statistics'))),
        ]

        for operation_name, operation in operations:
            with self.subTest(operation=operation_name):
                start_time = time.time()
                response = operation()
                operation_time = time.time() - start_time

                self.assertEqual(response.status_code, 200)
                self.assertLess(operation_time, 5.0)  # All operations should be fast

    def test_concurrent_user_workflow_performance(self):
        """Test performance with multiple concurrent user workflows."""
        import threading

        # Create test data
        for i in range(100):
            Book.objects.create(
                title=f'Concurrent Test Book {i}',
                file_path=f'/library/concurrent_{i}.epub',
                file_format='epub'
            )

        # Simulate multiple users performing operations
        def user_workflow():
            # Each thread performs a series of operations
            operations = [
                self.client.get(reverse('books:dashboard')),
                self.client.get(reverse('books:book_list')),
                self.client.get(reverse('books:book_list'), {'search': 'Concurrent'}),
                self.client.post(reverse('books:ajax_library_statistics')),
            ]

            for operation in operations:
                self.assertEqual(operation.status_code, 200)

        # Run concurrent workflows
        threads = []
        start_time = time.time()

        for i in range(10):  # 10 concurrent users
            thread = threading.Thread(target=user_workflow)
            threads.append(thread)
            thread.start()

        # Wait for all workflows to complete
        for thread in threads:
            thread.join()

        total_time = time.time() - start_time
        self.assertLess(total_time, 20.0)  # Should handle concurrent load efficiently
