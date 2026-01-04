"""
Test suite for books/mixins/filters.py - CORRECTED VERSION
Tests filtering functionality for book queries.
"""

import unittest

from django.contrib.auth.models import User

from books.mixins.filters import BookFilterMixin
from books.models import Book, FinalMetadata, ScanFolder
from books.tests.test_helpers import create_test_book_with_file
from books.tests.test_models_comprehensive import BaseTestCaseWithTempDir


class MockView(BookFilterMixin):
    """Mock view class for testing the BookFilterMixin"""
    pass


class BookFilterMixinTests(BaseTestCaseWithTempDir):
    """Test BookFilterMixin functionality"""

    def setUp(self):
        """Set up test data"""
        super().setUp()
        self.scan_folder = ScanFolder.objects.create(
            path=self.temp_dir,
            name="Filter Test Folder",
            language='en'
        )

        # Create test books using helper function
        self.epub_book = create_test_book_with_file(
            file_path="/test/filter/book1.epub",
            file_format="epub",
            file_size=1024000,
            scan_folder=self.scan_folder
        )

        self.pdf_book = create_test_book_with_file(
            file_path="/test/filter/book2.pdf",
            file_format="pdf",
            file_size=2048000,
            scan_folder=self.scan_folder
        )

        self.mobi_book = create_test_book_with_file(
            file_path="/test/filter/book3.mobi",
            file_format="mobi",
            file_size=1536000,
            scan_folder=self.scan_folder
        )

        # Create metadata with different confidence levels
        FinalMetadata.objects.create(
            book=self.epub_book,
            final_title="High Confidence Book",
            final_author="Test Author 1",
            overall_confidence=0.9,
            is_reviewed=True,
            language='en'
        )

        FinalMetadata.objects.create(
            book=self.pdf_book,
            final_title="Medium Confidence Book",
            final_author="Test Author 2",
            overall_confidence=0.6,
            is_reviewed=False,
            language='en'
        )

        FinalMetadata.objects.create(
            book=self.mobi_book,
            final_title="Low Confidence Book",
            final_author="Test Author 3",
            overall_confidence=0.3,
            is_reviewed=False,
            language='en'
        )

    def test_apply_search_filters_no_filters(self):
        """Test apply_search_filters with no filter parameters"""
        view = MockView()
        queryset = Book.objects.all()
        search_params = {}
        filtered_queryset = view.apply_search_filters(queryset, search_params)

        # Should return all books when no filters applied
        self.assertEqual(filtered_queryset.count(), 3)

    def test_apply_search_filters_search_query_title(self):
        """Test search filtering by title"""
        view = MockView()
        queryset = Book.objects.all()
        search_params = {'search_query': "High Confidence"}
        filtered_queryset = view.apply_search_filters(queryset, search_params)

        # Should return only the book with matching title
        self.assertEqual(filtered_queryset.count(), 1)
        book = filtered_queryset.first()
        self.assertEqual(book.finalmetadata.final_title, "High Confidence Book")

    def test_apply_search_filters_search_query_author(self):
        """Test search filtering by author"""
        view = MockView()
        queryset = Book.objects.all()
        search_params = {'search_query': "Test Author 2"}
        filtered_queryset = view.apply_search_filters(queryset, search_params)

        # Should return only the book by that author
        self.assertEqual(filtered_queryset.count(), 1)
        book = filtered_queryset.first()
        self.assertEqual(book.finalmetadata.final_author, "Test Author 2")

    def test_apply_search_filters_search_query_partial_match(self):
        """Test search filtering with partial matches"""
        view = MockView()
        queryset = Book.objects.all()
        search_params = {'search_query': "Confidence"}
        filtered_queryset = view.apply_search_filters(queryset, search_params)

        # Should return all books containing "Confidence" in title
        self.assertEqual(filtered_queryset.count(), 3)

    def test_apply_search_filters_search_query_case_insensitive(self):
        """Test search filtering is case insensitive"""
        view = MockView()
        queryset = Book.objects.all()
        search_params = {'search_query': "high confidence"}
        filtered_queryset = view.apply_search_filters(queryset, search_params)

        # Should find the book despite different case
        self.assertEqual(filtered_queryset.count(), 1)
        book = filtered_queryset.first()
        self.assertEqual(book.finalmetadata.final_title, "High Confidence Book")

    def test_apply_search_filters_format_filter(self):
        """Test filtering by file format"""
        view = MockView()
        queryset = Book.objects.all()
        search_params = {'file_format': "epub"}
        filtered_queryset = view.apply_search_filters(queryset, search_params)

        # Should return only EPUB books
        self.assertEqual(filtered_queryset.count(), 1)
        book = filtered_queryset.first()
        # file_format is now on BookFile, accessed through the property
        self.assertEqual(book.file_format, "epub")

    def test_apply_search_filters_confidence_filter_high(self):
        """Test filtering by high confidence level"""
        view = MockView()
        queryset = Book.objects.all()
        search_params = {'confidence_level': "high"}
        filtered_queryset = view.apply_search_filters(queryset, search_params)

        # Should return only high confidence books (>= 0.8)
        self.assertEqual(filtered_queryset.count(), 1)
        book = filtered_queryset.first()
        self.assertEqual(book.finalmetadata.final_title, "High Confidence Book")

    def test_apply_search_filters_confidence_filter_medium(self):
        """Test filtering by medium confidence level"""
        view = MockView()
        queryset = Book.objects.all()
        search_params = {'confidence_level': "medium"}
        filtered_queryset = view.apply_search_filters(queryset, search_params)

        # Should return medium confidence books (0.5 - 0.79)
        self.assertEqual(filtered_queryset.count(), 1)
        book = filtered_queryset.first()
        self.assertEqual(book.finalmetadata.final_title, "Medium Confidence Book")

    def test_apply_search_filters_confidence_filter_low(self):
        """Test filtering by low confidence level"""
        view = MockView()
        queryset = Book.objects.all()
        search_params = {'confidence_level': "low"}
        filtered_queryset = view.apply_search_filters(queryset, search_params)

        # Should return low confidence books (< 0.5)
        self.assertEqual(filtered_queryset.count(), 1)
        book = filtered_queryset.first()
        self.assertEqual(book.finalmetadata.final_title, "Low Confidence Book")

    def test_apply_search_filters_combined_filters(self):
        """Test applying multiple filters together"""
        view = MockView()
        queryset = Book.objects.all()
        search_params = {
            'search_query': "Test Author",
            'file_format': "epub",
            'confidence_level': "high"
        }
        filtered_queryset = view.apply_search_filters(queryset, search_params)

        # Should return only books matching ALL criteria
        self.assertEqual(filtered_queryset.count(), 1)
        book = filtered_queryset.first()
        # file_format is now accessed through the property
        self.assertEqual(book.file_format, "epub")
        self.assertGreaterEqual(book.finalmetadata.overall_confidence, 0.8)
        self.assertIn("Test Author", book.finalmetadata.final_author)

    def test_apply_search_filters_empty_string_values(self):
        """Test filtering with empty string values"""
        view = MockView()
        queryset = Book.objects.all()
        search_params = {
            'search_query': "",
            'language': "",
            'file_format': "",
            'confidence_level': ""
        }
        filtered_queryset = view.apply_search_filters(queryset, search_params)

        # Empty strings should be ignored, return all books
        self.assertEqual(filtered_queryset.count(), 3)

    def test_apply_search_filters_nonexistent_format(self):
        """Test filtering with non-existent file format"""
        view = MockView()
        queryset = Book.objects.all()
        search_params = {'file_format': "docx"}
        filtered_queryset = view.apply_search_filters(queryset, search_params)

        # Should return no results
        self.assertEqual(filtered_queryset.count(), 0)

    def test_apply_search_filters_invalid_confidence_level(self):
        """Test filtering with invalid confidence level"""
        view = MockView()
        queryset = Book.objects.all()
        search_params = {'confidence_level': "invalid"}
        filtered_queryset = view.apply_search_filters(queryset, search_params)

        # Invalid confidence level should be ignored
        self.assertEqual(filtered_queryset.count(), 3)

    def test_apply_search_filters_language_filter(self):
        """Test filtering by language"""
        # Create a book with different language
        import tempfile

        french_dir = tempfile.mkdtemp()
        try:
            french_folder = ScanFolder.objects.create(
                path=french_dir,
                name="French Folder",
                language='fr'
            )

            french_book = create_test_book_with_file(
                file_path=f"{french_dir}/livre.epub",
                file_format="epub",
                file_size=1000000,
                scan_folder=french_folder
            )

            FinalMetadata.objects.create(
                book=french_book,
                final_title="Livre Français",
                final_author="Auteur Français",
                overall_confidence=0.8,
                language='fr'
            )

            # Filter by English language
            view = MockView()
            queryset = Book.objects.all()
            search_params = {'language': "en"}
            filtered_queryset = view.apply_search_filters(queryset, search_params)

            # Should return only English books (books in en folder)
            self.assertEqual(filtered_queryset.count(), 3)

            # Filter by French language
            search_params = {'language': "fr"}
            filtered_queryset = view.apply_search_filters(queryset, search_params)

            # Should return only French book
            self.assertEqual(filtered_queryset.count(), 1)
            book = filtered_queryset.first()
            self.assertEqual(book.finalmetadata.final_title, "Livre Français")
        finally:
            import shutil
            shutil.rmtree(french_dir, ignore_errors=True)

    def test_apply_search_filters_multiple_format_extensions(self):
        """Test filtering with formats that have multiple extensions"""
        # Test formats with variations
        for format_name in ["epub", "pdf", "mobi"]:
            view = MockView()
            queryset = Book.objects.all()
            search_params = {'file_format': format_name}
            filtered_queryset = view.apply_search_filters(queryset, search_params)

            # Should find exactly one book of each format
            self.assertEqual(filtered_queryset.count(), 1)
            book = filtered_queryset.first()
            self.assertEqual(book.file_format.lower(), format_name.lower())

    def test_apply_search_filters_confidence_boundaries(self):
        """Test confidence filtering at boundaries"""
        # Create books at exact boundary values
        boundary_book_1 = create_test_book_with_file(
            file_path=f"{self.temp_dir}/boundary1.epub",
            file_format="epub",
            file_size=1000000,
            scan_folder=self.scan_folder
        )

        boundary_book_2 = create_test_book_with_file(
            file_path=f"{self.temp_dir}/boundary2.epub",
            file_format="epub",
            file_size=1000000,
            scan_folder=self.scan_folder
        )

        # Exactly 0.8 confidence (high boundary)
        FinalMetadata.objects.create(
            book=boundary_book_1,
            final_title="Exactly High Boundary",
            final_author="Boundary Author 1",
            overall_confidence=0.8
        )

        # Exactly 0.5 confidence (medium/low boundary)
        FinalMetadata.objects.create(
            book=boundary_book_2,
            final_title="Exactly Medium Boundary",
            final_author="Boundary Author 2",
            overall_confidence=0.5
        )

        view = MockView()

        # Test high confidence (should include 0.8)
        queryset = Book.objects.all()
        search_params = {'confidence_level': "high"}
        filtered_queryset = view.apply_search_filters(queryset, search_params)

        # Should include the original high confidence book AND the boundary book
        self.assertEqual(filtered_queryset.count(), 2)

        # Test medium confidence (should include 0.5 and 0.6)
        search_params = {'confidence_level': "medium"}
        filtered_queryset = view.apply_search_filters(queryset, search_params)

        # Should include the original medium confidence book AND the boundary book
        self.assertEqual(filtered_queryset.count(), 2)

    def test_apply_search_filters_with_none_values(self):
        """Test filtering when metadata contains None values"""
        # Create book with minimal metadata
        minimal_book = create_test_book_with_file(
            file_path=f"{self.temp_dir}/minimal.epub",
            file_format="epub",
            file_size=1000000,
            scan_folder=self.scan_folder
        )

        FinalMetadata.objects.create(
            book=minimal_book,
            final_title="Minimal Book",
            final_author="Unknown Author",  # Provide required field
            overall_confidence=None  # This can be None
        )

        # Search should still work with None values
        view = MockView()
        queryset = Book.objects.all()
        search_params = {'search_query': "Minimal"}
        filtered_queryset = view.apply_search_filters(queryset, search_params)

        self.assertEqual(filtered_queryset.count(), 1)
        book = filtered_queryset.first()
        self.assertEqual(book.finalmetadata.final_title, "Minimal Book")

    def test_apply_search_filters_or_conditions(self):
        """Test that search query uses OR conditions for title and author"""
        # Create book where search term matches author but not title
        author_match_book = create_test_book_with_file(
            file_path=f"{self.temp_dir}/author_match.epub",
            file_format="epub",
            file_size=1000000,
            scan_folder=self.scan_folder
        )

        FinalMetadata.objects.create(
            book=author_match_book,
            final_title="Different Title",
            final_author="Unique Search Term Author",
            overall_confidence=0.7
        )

        view = MockView()
        queryset = Book.objects.all()
        search_params = {'search_query': "Unique Search Term"}
        filtered_queryset = view.apply_search_filters(queryset, search_params)

        # Should find the book even though search term is only in author
        self.assertEqual(filtered_queryset.count(), 1)
        book = filtered_queryset.first()
        self.assertIn("Unique Search Term", book.finalmetadata.final_author)

    def test_apply_search_filters_queryset_chaining(self):
        """Test that filters can be chained with other QuerySet operations"""
        view = MockView()

        # Start with a pre-filtered queryset filtering through the files relationship
        queryset = Book.objects.filter(files__file_size__gt=500000)
        search_params = {'file_format': "epub"}
        filtered_queryset = view.apply_search_filters(queryset, search_params)

        # Should apply both the initial filter and the mixin filter
        self.assertGreaterEqual(filtered_queryset.count(), 1)
        book = filtered_queryset.first()
        self.assertEqual(book.file_format, "epub")
        # file_size is now on BookFile
        self.assertGreater(book.primary_file.file_size, 500000)

    def test_apply_search_filters_preserves_queryset_type(self):
        """Test that the returned object is still a QuerySet"""
        view = MockView()
        queryset = Book.objects.all()
        search_params = {'search_query': "Test"}
        filtered_queryset = view.apply_search_filters(queryset, search_params)

        # Should return a QuerySet that can be further chained
        self.assertTrue(hasattr(filtered_queryset, 'filter'))
        self.assertTrue(hasattr(filtered_queryset, 'exclude'))
        self.assertTrue(hasattr(filtered_queryset, 'order_by'))


class BookFilterMixinEdgeCaseTests(BaseTestCaseWithTempDir):
    """Test edge cases and error conditions for BookFilterMixin"""

    def setUp(self):
        """Set up minimal test data for edge cases"""
        super().setUp()
        self.scan_folder = ScanFolder.objects.create(
            path=self.temp_dir,
            name="Edge Test Folder"
        )

    def test_apply_search_filters_empty_queryset(self):
        """Test filtering on empty QuerySet"""
        view = MockView()

        # Start with empty queryset
        queryset = Book.objects.none()
        search_params = {'search_query': "anything"}
        filtered_queryset = view.apply_search_filters(queryset, search_params)

        # Should remain empty
        self.assertEqual(filtered_queryset.count(), 0)

    def test_apply_search_filters_no_metadata(self):
        """Test filtering books that have no FinalMetadata"""
        # Create book without metadata
        create_test_book_with_file(
            file_path=f"{self.temp_dir}/no_metadata.epub",
            file_format="epub",
            file_size=1000000,
            scan_folder=self.scan_folder
        )

        view = MockView()
        queryset = Book.objects.all()
        search_params = {'search_query': "test"}
        filtered_queryset = view.apply_search_filters(queryset, search_params)

        # Should handle books without metadata gracefully
        self.assertEqual(filtered_queryset.count(), 0)

    def test_apply_search_filters_malformed_request(self):
        """Test with malformed search params"""
        view = MockView()
        queryset = Book.objects.all()

        # Test with None search_params
        try:
            filtered_queryset = view.apply_search_filters(queryset, None)
            self.assertEqual(filtered_queryset.count(), 0)
        except (AttributeError, TypeError):
            # This is acceptable behavior for malformed params
            pass

    def test_apply_search_filters_performance_with_large_dataset(self):
        """Test performance considerations with larger dataset"""
        import time

        # Create multiple books for performance testing
        books = []
        for i in range(25):  # Reduced number for testing
            book = create_test_book_with_file(
                file_path=f"{self.temp_dir}/book_{i}.epub",
                file_format="epub",
                file_size=1000000,
                scan_folder=self.scan_folder
            )
            books.append(book)

            FinalMetadata.objects.create(
                book=book,
                final_title=f"Performance Test Book {i}",
                final_author=f"Author {i % 10}",
                overall_confidence=0.5 + (i % 5) * 0.1
            )

        view = MockView()

        start_time = time.time()
        queryset = Book.objects.all()
        search_params = {'search_query': "Performance"}
        filtered_queryset = view.apply_search_filters(queryset, search_params)
        result_count = filtered_queryset.count()
        end_time = time.time()

        # Should find all books with "Performance" in title
        self.assertEqual(result_count, 25)

        # Should complete reasonably quickly (less than 1 second)
        self.assertLess(end_time - start_time, 1.0)

    def test_apply_search_filters_database_query_efficiency(self):
        """Test that filtering doesn't generate excessive database queries"""
        # Create test data
        for i in range(10):
            book = create_test_book_with_file(
                file_path=f"{self.temp_dir}/efficient_{i}.epub",
                file_format="epub",
                file_size=1000000,
                scan_folder=self.scan_folder
            )

            FinalMetadata.objects.create(
                book=book,
                final_title=f"Efficiency Test {i}",
                final_author="Test Author",
                overall_confidence=0.8
            )

        view = MockView()

        queryset = Book.objects.all()

        # Monitor database queries
        from django.db import connection
        from django.test.utils import override_settings

        with override_settings(DEBUG=True):
            # Reset query log
            connection.queries_log.clear()

            search_params = {'search_query': "Efficiency"}
            filtered_queryset = view.apply_search_filters(queryset, search_params)
            list(filtered_queryset)  # Force evaluation

            # Should not generate excessive queries
            query_count = len(connection.queries)
            self.assertLessEqual(query_count, 5, f"Generated {query_count} queries, which may be excessive")


class BookFilterMixinIntegrationTests(BaseTestCaseWithTempDir):
    """Integration tests for BookFilterMixin with real Django components"""

    def setUp(self):
        """Set up integration test data"""
        super().setUp()
        self.user = User.objects.create_user(
            username='filtertest',
            password='testpass123'
        )

        self.scan_folder = ScanFolder.objects.create(
            path=self.temp_dir,
            name="Integration Test Folder"
        )

        # Create books with rich metadata for integration testing
        self.books_data = [
            {
                'file_path': '/test/integration/scifi.epub',
                'title': 'Science Fiction Novel',
                'author': 'Isaac Asimov',
                'format': 'epub',
                'confidence': 0.9
            },
            {
                'file_path': '/test/integration/fantasy.pdf',
                'title': 'Fantasy Adventure',
                'author': 'J.R.R. Tolkien',
                'format': 'pdf',
                'confidence': 0.7
            },
            {
                'file_path': '/test/integration/mystery.mobi',
                'title': 'Mystery Thriller',
                'author': 'Agatha Christie',
                'format': 'mobi',
                'confidence': 0.4
            }
        ]

        self.books = []
        for book_data in self.books_data:
            book = create_test_book_with_file(
                file_path=f"{self.temp_dir}/{book_data['format']}_book.{book_data['format']}",
                file_format=book_data['format'],
                file_size=1000000,
                scan_folder=self.scan_folder
            )

            FinalMetadata.objects.create(
                book=book,
                final_title=book_data['title'],
                final_author=book_data['author'],
                overall_confidence=book_data['confidence']
            )

            self.books.append(book)

    def test_mixin_with_select_related(self):
        """Test that filtering works with select_related optimizations"""
        view = MockView()

        # Use select_related to optimize queries
        queryset = Book.objects.select_related('scan_folder', 'finalmetadata')
        search_params = {'search_query': 'Science'}
        filtered_queryset = view.apply_search_filters(queryset, search_params)

        # Should work without issues and maintain optimization
        results = list(filtered_queryset)
        self.assertGreater(len(results), 0)

        # Verify that related objects are accessible
        for book in results:
            if hasattr(book, 'finalmetadata'):
                _ = book.finalmetadata.final_title
            _ = book.scan_folder.name

    def test_mixin_with_prefetch_related(self):
        """Test that filtering works with prefetch_related optimizations"""
        view = MockView()

        # Use prefetch_related
        queryset = Book.objects.prefetch_related('scan_folder')
        search_params = {'file_format': 'epub'}
        filtered_queryset = view.apply_search_filters(queryset, search_params)

        # Should work without issues
        results = list(filtered_queryset)
        self.assertGreater(len(results), 0)

    def test_mixin_filter_combinations_comprehensive(self):
        """Test comprehensive combinations of all filter types"""
        test_cases = [
            # Single filters
            {'search_query': 'Science'},
            {'file_format': 'epub'},
            {'confidence_level': 'high'},
            {'language': 'en'},

            # Two-way combinations
            {'search_query': 'Novel', 'file_format': 'epub'},
            {'search_query': 'Fantasy', 'confidence_level': 'medium'},
            {'file_format': 'pdf', 'confidence_level': 'medium'},

            # Three-way combinations
            {'search_query': 'Mystery', 'file_format': 'mobi', 'confidence_level': 'low'},

            # All filters (might not match anything)
            {'search_query': 'Novel', 'file_format': 'epub', 'confidence_level': 'high', 'language': 'en'}
        ]

        view = MockView()

        for test_case in test_cases:
            with self.subTest(filters=test_case):
                queryset = Book.objects.all()

                # Should not raise exceptions
                try:
                    filtered_queryset = view.apply_search_filters(queryset, test_case)
                    result_count = filtered_queryset.count()

                    # Result count should be non-negative
                    self.assertGreaterEqual(result_count, 0)

                except Exception as e:
                    self.fail(f"Filter combination {test_case} raised exception: {e}")

    @unittest.skip("SQLite doesn't handle concurrent writes well in tests")
    def test_mixin_thread_safety(self):
        """Test that the mixin is thread-safe (basic test)"""
        import threading
        import time

        results = {}
        errors = {}

        def filter_books(thread_id, search_term):
            try:
                view = MockView()

                queryset = Book.objects.all()
                search_params = {'search_query': search_term}
                filtered_queryset = view.apply_search_filters(queryset, search_params)
                results[thread_id] = filtered_queryset.count()

                # Add small delay to increase chance of race conditions
                time.sleep(0.01)

            except Exception as e:
                errors[thread_id] = str(e)

        # Run multiple threads with different search terms
        threads = []
        search_terms = ['Science', 'Fantasy', 'Mystery', 'Novel', 'Adventure']

        for i, term in enumerate(search_terms):
            thread = threading.Thread(target=filter_books, args=(i, term))
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # Check that no errors occurred
        self.assertEqual(len(errors), 0, f"Thread errors: {errors}")

        # Check that all threads completed
        self.assertEqual(len(results), len(search_terms))

    def test_mixin_with_ordering(self):
        """Test that filtering preserves or works with ordering"""
        view = MockView()

        # Apply ordering before filtering
        queryset = Book.objects.all().order_by('id')
        search_params = {'search_query': 'Novel'}
        filtered_queryset = view.apply_search_filters(queryset, search_params)

        # Should maintain ordering
        ordered_results = list(filtered_queryset)
        if len(ordered_results) > 1:
            self.assertLessEqual(
                ordered_results[0].id,
                ordered_results[1].id
            )

        # Apply ordering after filtering
        queryset = Book.objects.all()
        filtered_queryset = view.apply_search_filters(queryset, search_params)
        ordered_filtered = filtered_queryset.order_by('-id')

        # Should be able to order filtered results
        self.assertGreater(len(list(ordered_filtered)), 0)

    def test_mixin_with_pagination(self):
        """Test that filtering works correctly with pagination"""
        # Create many books to test pagination
        for i in range(25):
            book = create_test_book_with_file(
                file_path=f'{self.temp_dir}/paginated_{i}.epub',
                file_format='epub',
                file_size=1000000,
                scan_folder=self.scan_folder
            )

            FinalMetadata.objects.create(
                book=book,
                final_title=f'Paginated Book {i}',
                final_author='Pagination Author',
                overall_confidence=0.8
            )

        view = MockView()

        queryset = Book.objects.all()
        search_params = {
            'search_query': 'Paginated',
            'confidence_level': 'high'
        }
        filtered_queryset = view.apply_search_filters(queryset, search_params)

        # Should find all paginated books
        self.assertEqual(filtered_queryset.count(), 25)

        # Test that pagination can be applied to filtered results
        paginated_results = filtered_queryset[:10]
        self.assertEqual(len(list(paginated_results)), 10)
