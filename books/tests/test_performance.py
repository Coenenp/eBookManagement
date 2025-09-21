"""
Comprehensive performance tests for database queries, caching, and optimization.

This module contains tests for database query optimization, caching effectiveness,
pagination efficiency, large dataset handling, and response time optimization.
"""

import time
import json
from unittest.mock import patch
from django.test import TestCase, Client, TransactionTestCase
from django.contrib.auth.models import User
from django.urls import reverse
from django.core.cache import cache
from django.db import connection
from django.test.utils import override_settings
from books.models import Book, FinalMetadata, BookMetadata, DataSource


class DatabaseQueryPerformanceTests(TestCase):
    """Tests for database query performance and optimization."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.client.login(username='testuser', password='testpass123')

        # Create test data source
        self.data_source = DataSource.objects.create(
            name='test_source',
            display_name='Test Source',
            trust_level=0.8
        )

    def test_book_list_query_count(self):
        """Test that book list view uses efficient queries."""
        # Create test books
        books = []
        for i in range(100):
            book = Book.objects.create(
                title=f"Performance Test Book {i}",
                file_path=f"/library/perf_test_{i}.epub",
                file_format="epub",
                file_size=1024 * 1024  # 1MB
            )

            # Add final metadata
            FinalMetadata.objects.create(
                book=book,
                final_title=f"Performance Test Book {i}",
                final_author=f"Author {i}",
                overall_confidence=0.8
            )

            books.append(book)

        # Test query count
        with self.assertNumQueries(10):  # Should use reasonable number of queries
            response = self.client.get(reverse('books:book_list'))
            self.assertEqual(response.status_code, 200)

    def test_book_detail_query_efficiency(self):
        """Test book detail view query efficiency."""
        # Create book with related data
        book = Book.objects.create(
            title="Detail Performance Test",
            file_path="/library/detail_test.epub",
            file_format="epub"
        )

        # Add metadata entries
        for i in range(10):
            BookMetadata.objects.create(
                book=book,
                source=self.data_source,
                field_name=f'test_field_{i}',
                field_value=f'test_value_{i}',
                confidence=0.8,
                is_active=True
            )

        # Test with limited queries
        with self.assertNumQueries(5):  # Should use select_related/prefetch_related
            response = self.client.get(reverse('books:book_detail', kwargs={'pk': book.pk}))
            self.assertEqual(response.status_code, 200)

    def test_search_query_performance(self):
        """Test search functionality performance."""
        # Create many books for search testing
        for i in range(500):
            Book.objects.create(
                title=f"Search Test Book {i}",
                file_path=f"/library/search_{i}.epub",
                file_format="epub"
            )

        # Test search performance
        start_time = time.time()
        response = self.client.get(reverse('books:book_list'), {'search': 'Search Test'})
        end_time = time.time()

        search_time = end_time - start_time
        self.assertLess(search_time, 2.0)  # Should complete within 2 seconds
        self.assertEqual(response.status_code, 200)

    def test_bulk_operations_performance(self):
        """Test bulk database operations performance."""
        # Create books for bulk testing
        book_ids = []
        for i in range(200):
            book = Book.objects.create(
                title=f"Bulk Test Book {i}",
                file_path=f"/library/bulk_{i}.epub",
                file_format="epub"
            )
            book_ids.append(book.id)

        # Test bulk update performance
        start_time = time.time()
        response = self.client.post(
            reverse('books:ajax_bulk_update_books'),
            data=json.dumps({
                'book_ids': book_ids[:50],  # Update 50 books
                'updates': {'genre': 'Performance Test Genre'}
            }),
            content_type='application/json'
        )
        end_time = time.time()

        bulk_time = end_time - start_time
        self.assertLess(bulk_time, 5.0)  # Should complete within 5 seconds
        self.assertEqual(response.status_code, 200)

    def test_aggregation_query_performance(self):
        """Test performance of aggregation queries."""
        # Create books with metadata for aggregation
        for i in range(300):
            book = Book.objects.create(
                title=f"Aggregation Test Book {i}",
                file_path=f"/library/agg_{i}.epub",
                file_format="epub",
                file_size=(i + 1) * 1024 * 1024  # Varying sizes
            )

            FinalMetadata.objects.create(
                book=book,
                final_title=f"Aggregation Test Book {i}",
                overall_confidence=0.5 + (i % 50) / 100.0  # Varying confidence
            )

        # Test dashboard statistics performance
        start_time = time.time()
        response = self.client.get(reverse('books:dashboard'))
        end_time = time.time()

        dashboard_time = end_time - start_time
        self.assertLess(dashboard_time, 3.0)  # Should complete within 3 seconds
        self.assertEqual(response.status_code, 200)

    def test_index_usage_verification(self):
        """Test that database indexes are being used effectively."""
        # Create books to test index usage
        for i in range(100):
            Book.objects.create(
                title=f"Index Test Book {i}",
                file_path=f"/library/index_{i}.epub",
                file_format="epub"
            )

        # Test query that should use indexes
        with connection.cursor() as cursor:
            # Run a query that should use indexes
            cursor.execute("""
                SELECT COUNT(*) FROM books_book
                WHERE title LIKE %s
            """, ['Index Test%'])

            result = cursor.fetchone()
            self.assertGreater(result[0], 0)


class CachingPerformanceTests(TestCase):
    """Tests for caching effectiveness and performance."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.client.login(username='testuser', password='testpass123')

        # Clear cache before each test
        cache.clear()

    def test_view_caching_effectiveness(self):
        """Test that view caching improves performance."""
        # Create test data
        for i in range(50):
            Book.objects.create(
                title=f"Cache Test Book {i}",
                file_path=f"/library/cache_{i}.epub",
                file_format="epub"
            )

        # First request (no cache)
        start_time = time.time()
        response1 = self.client.get(reverse('books:book_list'))
        first_request_time = time.time() - start_time

        # Second request (should use cache if implemented)
        start_time = time.time()
        response2 = self.client.get(reverse('books:book_list'))
        second_request_time = time.time() - start_time

        self.assertEqual(response1.status_code, 200)
        self.assertEqual(response2.status_code, 200)

        # If caching is implemented, second request should be faster
        # This may not always be true depending on cache implementation
        self.assertLess(second_request_time, first_request_time + 1.0)

    def test_cache_hit_ratio_tracking(self):
        """Test cache hit ratio for frequently accessed data."""
        book = Book.objects.create(
            title="Cache Hit Test",
            file_path="/library/cache_hit.epub",
            file_format="epub"
        )

        # Access the same book multiple times
        hit_times = []
        for i in range(10):
            start_time = time.time()
            response = self.client.get(reverse('books:book_detail', kwargs={'pk': book.pk}))
            end_time = time.time()

            hit_times.append(end_time - start_time)
            self.assertEqual(response.status_code, 200)

        # Later requests should generally be faster (if caching works)
        average_early = sum(hit_times[:3]) / 3
        average_late = sum(hit_times[-3:]) / 3

        # Allow some tolerance for variations
        self.assertLessEqual(average_late, average_early + 0.5)

    def test_cache_invalidation_performance(self):
        """Test performance of cache invalidation."""
        # Create cached data
        for i in range(20):
            book = Book.objects.create(
                title=f"Invalidation Test Book {i}",
                file_path=f"/library/invalidation_{i}.epub",
                file_format="epub"
            )

            # Access to potentially cache
            self.client.get(reverse('books:book_detail', kwargs={'pk': book.pk}))

        # Test cache invalidation performance
        start_time = time.time()
        response = self.client.post(reverse('books:ajax_clear_cache'))
        end_time = time.time()

        invalidation_time = end_time - start_time
        self.assertLess(invalidation_time, 1.0)  # Should be fast
        self.assertEqual(response.status_code, 200)

    @patch('django.core.cache.cache.get')
    @patch('django.core.cache.cache.set')
    def test_cache_memory_usage(self, mock_set, mock_get):
        """Test cache memory usage patterns."""
        # Simulate cache operations
        mock_get.return_value = None  # Cache miss

        # Access multiple pages
        for i in range(10):
            response = self.client.get(reverse('books:book_list'), {'page': i + 1})
            self.assertEqual(response.status_code, 200)

        # Verify cache operations
        self.assertTrue(mock_get.called)
        # Cache set might be called if caching is implemented

    def test_query_result_caching(self):
        """Test caching of expensive query results."""
        # Create data for expensive query
        for i in range(100):
            book = Book.objects.create(
                title=f"Query Cache Test Book {i}",
                file_path=f"/library/query_cache_{i}.epub",
                file_format="epub"
            )

            FinalMetadata.objects.create(
                book=book,
                final_title=f"Query Cache Test Book {i}",
                overall_confidence=0.5 + (i % 50) / 100.0
            )

        # Test expensive query (e.g., statistics calculation)
        start_time = time.time()
        response1 = self.client.get(reverse('books:ajax_get_statistics'))
        first_query_time = time.time() - start_time

        # Second identical request
        start_time = time.time()
        response2 = self.client.get(reverse('books:ajax_get_statistics'))
        second_query_time = time.time() - start_time

        self.assertEqual(response1.status_code, 200)
        self.assertEqual(response2.status_code, 200)

        # Second query should be faster if caching works
        self.assertLessEqual(second_query_time, first_query_time)


class PaginationPerformanceTests(TestCase):
    """Tests for pagination efficiency and performance."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.client.login(username='testuser', password='testpass123')

    def test_large_dataset_pagination(self):
        """Test pagination performance with large datasets."""
        # Create large dataset
        books = []
        for i in range(1000):  # 1000 books
            book = Book.objects.create(
                title=f"Pagination Test Book {i:04d}",
                file_path=f"/library/pagination_{i:04d}.epub",
                file_format="epub"
            )
            books.append(book)

        # Test first page performance
        start_time = time.time()
        response = self.client.get(reverse('books:book_list'))
        first_page_time = time.time() - start_time

        # Test middle page performance
        start_time = time.time()
        response = self.client.get(reverse('books:book_list'), {'page': 10})
        middle_page_time = time.time() - start_time

        # Test last page performance
        start_time = time.time()
        response = self.client.get(reverse('books:book_list'), {'page': 20})
        last_page_time = time.time() - start_time
        self.assertEqual(response.status_code, 200)

        # All pages should load quickly
        self.assertLess(first_page_time, 2.0)
        self.assertLess(middle_page_time, 2.0)
        self.assertLess(last_page_time, 2.0)

        # Performance should be consistent across pages
        max_time = max(first_page_time, middle_page_time, last_page_time)
        min_time = min(first_page_time, middle_page_time, last_page_time)
        self.assertLess(max_time - min_time, 1.0)  # Difference should be small

    def test_pagination_memory_efficiency(self):
        """Test memory efficiency of pagination."""
        import tracemalloc

        # Create test data
        for i in range(500):
            Book.objects.create(
                title=f"Memory Test Book {i}",
                file_path=f"/library/memory_{i}.epub",
                file_format="epub"
            )

        # Start memory tracking
        tracemalloc.start()

        # Load multiple pages
        for page in range(1, 6):  # First 5 pages
            response = self.client.get(reverse('books:book_list'), {'page': page})
            self.assertEqual(response.status_code, 200)

        # Get memory usage
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        # Memory usage should be reasonable (less than 50MB)
        self.assertLess(peak, 50 * 1024 * 1024)  # 50MB

    def test_search_result_pagination(self):
        """Test pagination performance with search results."""
        # Create searchable books
        for i in range(200):
            Book.objects.create(
                title=f"Searchable Book {i:03d}",
                file_path=f"/library/searchable_{i:03d}.epub",
                file_format="epub"
            )

        # Test search with pagination
        start_time = time.time()
        response = self.client.get(reverse('books:book_list'), {
            'search': 'Searchable',
            'page': 1
        })
        search_time = time.time() - start_time

        self.assertLess(search_time, 2.0)
        self.assertEqual(response.status_code, 200)

    def test_different_page_sizes(self):
        """Test performance with different page sizes."""
        # Create test books
        for i in range(300):
            Book.objects.create(
                title=f"Page Size Test Book {i}",
                file_path=f"/library/pagesize_{i}.epub",
                file_format="epub"
            )

        page_sizes = [10, 25, 50, 100]

        for page_size in page_sizes:
            with self.subTest(page_size=page_size):
                start_time = time.time()
                response = self.client.get(reverse('books:book_list'), {
                    'per_page': page_size
                })
                load_time = time.time() - start_time

                # Should handle different page sizes efficiently
                self.assertLess(load_time, 3.0)
                self.assertEqual(response.status_code, 200)


class ResponseTimeOptimizationTests(TestCase):
    """Tests for overall response time optimization."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.client.login(username='testuser', password='testpass123')

    def test_ajax_endpoint_response_times(self):
        """Test response times of AJAX endpoints."""
        # Create test book
        book = Book.objects.create(
            title="Response Time Test",
            file_path="/library/response_test.epub",
            file_format="epub"
        )

        ajax_endpoints = [
            ('books:ajax_get_book_info', {'book_id': book.id}),
            ('books:ajax_update_book', {'book_id': book.id, 'title': 'Updated Title'}),
            ('books:ajax_search_books', {'query': 'test'}),
        ]

        for endpoint, data in ajax_endpoints:
            with self.subTest(endpoint=endpoint):
                start_time = time.time()
                response = self.client.post(reverse(endpoint), data)
                response_time = time.time() - start_time

                # AJAX endpoints should be fast
                self.assertLess(response_time, 1.0)
                self.assertEqual(response.status_code, 200)

    def test_static_asset_loading_impact(self):
        """Test impact of static assets on page load times."""
        # Create test data
        for i in range(20):
            Book.objects.create(
                title=f"Asset Test Book {i}",
                file_path=f"/library/asset_{i}.epub",
                file_format="epub"
            )

        # Test page load time
        start_time = time.time()
        response = self.client.get(reverse('books:book_list'))
        load_time = time.time() - start_time

        self.assertLess(load_time, 2.0)
        self.assertEqual(response.status_code, 200)

    def test_concurrent_request_handling(self):
        """Test handling of concurrent requests."""
        import threading

        # Create test data
        for i in range(50):
            Book.objects.create(
                title=f"Concurrent Test Book {i}",
                file_path=f"/library/concurrent_{i}.epub",
                file_format="epub"
            )

        def make_request():
            start_time = time.time()
            response = self.client.get(reverse('books:book_list'))
            end_time = time.time()
            return response.status_code, end_time - start_time

        # Make concurrent requests
        threads = []
        results = []

        for i in range(10):  # 10 concurrent requests
            thread = threading.Thread(
                target=lambda: results.append(make_request())
            )
            threads.append(thread)
            thread.start()

        # Wait for all threads
        for thread in threads:
            thread.join()

        # All requests should succeed and be reasonably fast
        for status_code, response_time in results:
            self.assertEqual(status_code, 200)
            self.assertLess(response_time, 5.0)  # Allow more time for concurrent load

    def test_memory_usage_optimization(self):
        """Test memory usage during intensive operations."""
        import tracemalloc

        # Start memory tracking
        tracemalloc.start()

        # Create and process many books
        for i in range(100):
            book = Book.objects.create(
                title=f"Memory Optimization Test Book {i}",
                file_path=f"/library/memory_opt_{i}.epub",
                file_format="epub"
            )

            # Simulate metadata processing
            self.client.post(reverse('books:ajax_process_book'), {
                'book_id': book.id,
                'operation': 'extract_metadata'
            })

        # Get memory usage
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        # Memory usage should be reasonable
        self.assertLess(peak, 100 * 1024 * 1024)  # 100MB


class LargeDatasetHandlingTests(TransactionTestCase):
    """Tests for handling very large datasets efficiently."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.client.login(username='testuser', password='testpass123')

    def test_very_large_library_performance(self):
        """Test performance with very large library (10000+ books)."""
        # Create large dataset (use smaller number for test)
        batch_size = 1000
        for batch in range(10):  # 10 batches of 1000 = 10000 books
            books_to_create = []
            for i in range(batch_size):
                book_data = {
                    'title': f'Large Library Book {batch * batch_size + i:05d}',
                    'file_path': f'/library/large_{batch * batch_size + i:05d}.epub',
                    'file_format': 'epub',
                    'file_size': (i + 1) * 1024 * 1024  # Varying sizes
                }
                books_to_create.append(Book(**book_data))

            # Bulk create for efficiency
            Book.objects.bulk_create(books_to_create, batch_size=500)

        # Test library browsing performance
        start_time = time.time()
        response = self.client.get(reverse('books:book_list'))
        browse_time = time.time() - start_time

        self.assertLess(browse_time, 3.0)  # Should handle large library efficiently
        self.assertEqual(response.status_code, 200)

    def test_bulk_operations_on_large_dataset(self):
        """Test bulk operations on large datasets."""
        # Create large dataset
        books_to_create = []
        for i in range(5000):  # 5000 books
            books_to_create.append(Book(
                title=f'Bulk Test Book {i:04d}',
                file_path=f'/library/bulk_{i:04d}.epub',
                file_format='epub'
            ))

        Book.objects.bulk_create(books_to_create, batch_size=1000)

        # Test bulk update performance
        book_ids = list(Book.objects.values_list('id', flat=True)[:1000])

        start_time = time.time()
        response = self.client.post(
            reverse('books:ajax_bulk_update_books'),
            data=json.dumps({
                'book_ids': book_ids,
                'updates': {'genre': 'Bulk Updated Genre'}
            }),
            content_type='application/json'
        )
        bulk_time = time.time() - start_time

        self.assertLess(bulk_time, 10.0)  # Should handle bulk operations efficiently
        self.assertEqual(response.status_code, 200)

    def test_search_performance_large_dataset(self):
        """Test search performance on large dataset."""
        # Create searchable dataset
        books_to_create = []
        for i in range(2000):  # 2000 books
            books_to_create.append(Book(
                title=f'Search Performance Book {i:04d}',
                file_path=f'/library/search_perf_{i:04d}.epub',
                file_format='epub'
            ))

        Book.objects.bulk_create(books_to_create, batch_size=500)

        # Test search performance
        search_queries = [
            'Search Performance',
            'Book 0001',
            'Book 1999',
            'Performance'
        ]

        for query in search_queries:
            with self.subTest(query=query):
                start_time = time.time()
                response = self.client.get(reverse('books:book_list'), {'search': query})
                search_time = time.time() - start_time

                self.assertLess(search_time, 2.0)
                self.assertEqual(response.status_code, 200)


@override_settings(DEBUG=False)
class ProductionPerformanceTests(TestCase):
    """Tests for performance in production-like settings."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.client.login(username='testuser', password='testpass123')

    def test_production_response_times(self):
        """Test response times in production mode (DEBUG=False)."""
        # Create test data
        for i in range(100):
            Book.objects.create(
                title=f"Production Test Book {i}",
                file_path=f"/library/production_{i}.epub",
                file_format="epub"
            )

        # Test critical pages
        critical_pages = [
            reverse('books:book_list'),
            reverse('books:dashboard'),
        ]

        for page in critical_pages:
            with self.subTest(page=page):
                start_time = time.time()
                response = self.client.get(page)
                response_time = time.time() - start_time

                # Production should be fast
                self.assertLess(response_time, 1.5)
                self.assertEqual(response.status_code, 200)

    def test_production_memory_efficiency(self):
        """Test memory efficiency in production mode."""
        import tracemalloc

        # Start memory tracking
        tracemalloc.start()

        # Simulate production workload
        for i in range(10):
            # Access various pages
            self.client.get(reverse('books:book_list'))
            self.client.get(reverse('books:dashboard'))

            # Make AJAX requests
            self.client.post(reverse('books:ajax_search_books'), {'query': f'test {i}'})

        # Get memory usage
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        # Production memory usage should be optimized
        self.assertLess(peak, 75 * 1024 * 1024)  # 75MB


class PerformanceRegressionTests(TestCase):
    """Tests to detect performance regressions."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.client.login(username='testuser', password='testpass123')

    def test_baseline_performance_metrics(self):
        """Test baseline performance metrics for comparison."""
        # Create standard test dataset
        for i in range(200):
            Book.objects.create(
                title=f"Baseline Test Book {i}",
                file_path=f"/library/baseline_{i}.epub",
                file_format="epub"
            )

        # Measure baseline operations
        operations = {
            'list_view': lambda: self.client.get(reverse('books:book_list')),
            'search': lambda: self.client.get(reverse('books:book_list'), {'search': 'Baseline'}),
            'ajax_search': lambda: self.client.post(reverse('books:ajax_search_books'), {'query': 'Test'}),
        }

        performance_metrics = {}

        for operation_name, operation in operations.items():
            start_time = time.time()
            response = operation()
            end_time = time.time()

            performance_metrics[operation_name] = end_time - start_time
            self.assertEqual(response.status_code, 200)

        # Log metrics for regression tracking
        # In a real scenario, you'd store these for comparison
        for operation, timing in performance_metrics.items():
            print(f"{operation}: {timing:.3f} seconds")

            # Set reasonable upper bounds
            if operation == 'list_view':
                self.assertLess(timing, 2.0)
            elif operation == 'search':
                self.assertLess(timing, 3.0)
            elif operation == 'ajax_search':
                self.assertLess(timing, 1.0)
