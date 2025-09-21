"""
Comprehensive test suite for Dashboard view analytics functionality.
Tests all dashboard methods, statistics calculations, and chart data preparation.
"""

import json
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone

from books.models import (
    Book, Author, Series, Publisher, Genre, DataSource, ScanFolder, ScanLog,
    FinalMetadata, BookSeries
)
from books.views import DashboardView


class DashboardViewTests(TestCase):
    """Test suite for the main DashboardView class"""

    def setUp(self):
        """Set up test data for dashboard analytics"""
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.client.login(username='testuser', password='testpass123')

        # Create test data sources
        self.manual_source, _ = DataSource.objects.get_or_create(
            name='Manual Entry',
            defaults={'trust_level': 0.9}
        )
        self.epub_source, _ = DataSource.objects.get_or_create(
            name='EPUB',
            defaults={'trust_level': 0.7}
        )

        # Create test scan folder
        self.scan_folder = ScanFolder.objects.create(
            path='/test/books',
            is_active=True,
            last_scanned=timezone.now() - timedelta(days=2)
        )

        # Create test authors, series, publishers
        self.author1 = Author.objects.create(name='Test Author 1', is_reviewed=True)
        self.author2 = Author.objects.create(name='Test Author 2', is_reviewed=False)
        self.series1 = Series.objects.create(name='Test Series 1')
        self.series2 = Series.objects.create(name='Test Series 2')
        self.publisher1 = Publisher.objects.create(name='Test Publisher 1')
        self.genre1 = Genre.objects.create(name='Science Fiction', is_reviewed=True)
        self.genre2 = Genre.objects.create(name='Fantasy', is_reviewed=False)

        # Create test books with varying metadata completeness
        self.create_test_books()

    def create_test_books(self):
        """Create a variety of test books with different metadata levels"""
        # Book 1: Complete metadata, high confidence
        self.book1 = Book.objects.create(
            file_path='/test/book1.epub',
            file_format='epub',
            file_size=1000000,
            is_placeholder=False,
            scan_folder=self.scan_folder,
            first_scanned=timezone.now() - timedelta(days=5)
        )
        self.metadata1 = FinalMetadata.objects.create(
            book=self.book1,
            final_title='Complete Book',
            final_author='Test Author 1',
            final_series='Test Series 1',
            final_publisher='Test Publisher 1',
            isbn='9781234567890',
            publication_year='2023',
            language='English',
            description='A complete book with all metadata',
            has_cover=True,
            overall_confidence=0.9,
            completeness_score=1.0,
            is_reviewed=True,
            last_updated=timezone.now() - timedelta(days=1)
        )

        # Book 2: Partial metadata, medium confidence
        self.book2 = Book.objects.create(
            file_path='/test/book2.epub',
            file_format='epub',
            file_size=800000,
            is_placeholder=False,
            scan_folder=self.scan_folder,
            first_scanned=timezone.now() - timedelta(days=3)
        )
        self.metadata2 = FinalMetadata.objects.create(
            book=self.book2,
            final_title='Partial Book',
            final_author='Test Author 2',
            final_series='',
            final_publisher='',
            isbn='',
            publication_year='2022',
            language='English',
            description='',
            has_cover=False,
            overall_confidence=0.6,
            completeness_score=0.5,
            is_reviewed=False,
            last_updated=timezone.now() - timedelta(days=2)
        )

        # Book 3: Minimal metadata, low confidence
        self.book3 = Book.objects.create(
            file_path='/test/book3.pdf',
            file_format='pdf',
            file_size=500000,
            is_placeholder=False,
            scan_folder=self.scan_folder,
            first_scanned=timezone.now() - timedelta(days=1)
        )
        self.metadata3 = FinalMetadata.objects.create(
            book=self.book3,
            final_title='',
            final_author='',
            final_series='',
            final_publisher='',
            isbn='',
            publication_year='',
            language='',
            description='',
            has_cover=False,
            overall_confidence=0.2,
            completeness_score=0.1,
            is_reviewed=False,
            last_updated=timezone.now()
        )

        # Book 4: Comic book format
        self.book4 = Book.objects.create(
            file_path='/test/comic1.cbr',
            file_format='cbr',
            file_size=50000000,
            is_placeholder=False,
            scan_folder=self.scan_folder
        )
        self.metadata4 = FinalMetadata.objects.create(
            book=self.book4,
            final_title='Test Comic',
            final_author='Comic Author',
            final_series='Comic Series',
            has_cover=True,
            overall_confidence=0.7,
            completeness_score=0.6,
            is_reviewed=True
        )

        # Book 5: Placeholder book
        self.book5 = Book.objects.create(
            file_path='/test/placeholder.epub',
            file_format='epub',
            file_size=0,
            is_placeholder=True,
            scan_folder=self.scan_folder
        )

        # Book 6: Corrupted book
        self.book6 = Book.objects.create(
            file_path='/test/corrupted.epub',
            file_format='epub',
            file_size=1000,
            is_corrupted=True,
            scan_folder=self.scan_folder
        )

        # Book 7: Duplicate book
        self.book7 = Book.objects.create(
            file_path='/test/duplicate.epub',
            file_format='epub',
            file_size=1000000,
            is_duplicate=True,
            scan_folder=self.scan_folder
        )

        # Create book series relationships
        BookSeries.objects.create(
            book=self.book1,
            series=self.series1,
            series_number='1',
            is_active=True,
            source=self.manual_source
        )
        BookSeries.objects.create(
            book=self.book4,
            series=self.series2,
            series_number='',  # No series number
            is_active=True,
            source=self.epub_source
        )

        # Create scan logs for recent activity
        ScanLog.objects.create(
            scan_folder=self.scan_folder,
            timestamp=timezone.now() - timedelta(days=1),
            books_found=3,
            books_processed=3,
            errors_count=0
        )

    def test_dashboard_view_requires_login(self):
        """Test that dashboard view requires authentication"""
        self.client.logout()
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('login', response.url)

    def test_dashboard_view_loads_successfully(self):
        """Test that dashboard view loads for authenticated users"""
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Dashboard')
        self.assertTemplateUsed(response, 'books/dashboard.html')

    def test_get_context_data_basic_stats(self):
        """Test basic statistics in dashboard context"""
        view = DashboardView()
        view.request = MagicMock()
        context = view.get_context_data()

        # Test core metadata statistics
        self.assertEqual(context['total_books'], 4)  # Excludes placeholder
        self.assertEqual(context['books_with_metadata'], 3)  # Books with non-empty titles
        self.assertEqual(context['books_with_author'], 3)  # Books with authors
        self.assertEqual(context['books_with_cover'], 2)  # Books with covers
        self.assertEqual(context['books_with_isbn'], 1)  # Books with ISBN
        self.assertEqual(context['books_in_series'], 2)  # Books in series
        self.assertEqual(context['needs_review_count'], 2)  # Unreviewed books

    def test_get_context_data_confidence_stats(self):
        """Test confidence level statistics"""
        view = DashboardView()
        view.request = MagicMock()
        context = view.get_context_data()

        self.assertEqual(context['high_confidence_count'], 1)  # >= 0.8
        self.assertEqual(context['medium_confidence_count'], 2)  # 0.5-0.8
        self.assertEqual(context['low_confidence_count'], 1)  # < 0.5

        # Test average values
        self.assertAlmostEqual(float(context['avg_confidence']), 0.6, places=1)
        self.assertAlmostEqual(float(context['avg_completeness']), 0.55, places=1)

    def test_get_context_data_percentages(self):
        """Test percentage calculations"""
        view = DashboardView()
        view.request = MagicMock()
        context = view.get_context_data()

        # Test percentage calculations (4 total books)
        self.assertEqual(context['completion_percentage'], 75.0)  # 3/4 * 100
        self.assertEqual(context['author_percentage'], 75.0)  # 3/4 * 100
        self.assertEqual(context['cover_percentage'], 50.0)  # 2/4 * 100
        self.assertEqual(context['isbn_percentage'], 25.0)  # 1/4 * 100
        self.assertEqual(context['series_percentage'], 50.0)  # 2/4 * 100
        self.assertEqual(context['review_percentage'], 50.0)  # (4-2)/4 * 100

    def test_get_context_data_quality_scores(self):
        """Test quality score calculations"""
        view = DashboardView()
        view.request = MagicMock()
        context = view.get_context_data()

        # Quality scores should be percentages (0-100)
        self.assertAlmostEqual(context['overall_quality_score'], 60.0, places=1)
        self.assertAlmostEqual(context['completeness_score'], 55.0, places=1)

    def test_get_issue_statistics(self):
        """Test issue detection and counting"""
        view = DashboardView()
        issue_stats = view.get_issue_statistics()

        # Test metadata issues
        self.assertEqual(issue_stats['missing_titles'], 1)  # book3 has empty title
        self.assertEqual(issue_stats['missing_authors'], 1)  # book3 has empty author
        self.assertEqual(issue_stats['missing_covers'], 2)  # book2 and book3
        self.assertEqual(issue_stats['missing_isbn'], 3)  # book2, book3, book4
        self.assertEqual(issue_stats['low_confidence'], 1)  # book3 < 0.5
        self.assertEqual(issue_stats['incomplete_metadata'], 1)  # book3 < 0.5 completeness

        # Test file issues
        self.assertEqual(issue_stats['placeholder_books'], 1)  # book5
        self.assertEqual(issue_stats['duplicate_books'], 1)  # book7
        self.assertEqual(issue_stats['corrupted_books'], 1)  # book6

        # Test review status
        self.assertEqual(issue_stats['needs_review'], 2)  # book2, book3
        self.assertEqual(issue_stats['unreviewed_authors'], 1)  # author2
        self.assertEqual(issue_stats['unreviewed_genres'], 1)  # genre2

        # Test series issues
        self.assertEqual(issue_stats['series_without_numbers'], 1)  # book4 series

    def test_get_incomplete_series_count(self):
        """Test detection of incomplete series"""
        # Create a series with gaps in numbering
        series_with_gaps = Series.objects.create(name='Gapped Series')

        # Create books 1, 3, 5 (missing 2, 4)
        for i, num in enumerate(['1', '3', '5'], 1):
            book = Book.objects.create(
                file_path=f'/test/series{i}.epub',
                file_format='epub',
                file_size=1000000,
                scan_folder=self.scan_folder
            )
            FinalMetadata.objects.create(book=book)
            BookSeries.objects.create(
                book=book,
                series=series_with_gaps,
                series_number=num,
                is_active=True,
                source=self.epub_source
            )

        view = DashboardView()
        gaps_count = view.get_incomplete_series_count()
        self.assertEqual(gaps_count, 1)  # One series with gaps

    def test_get_content_type_statistics(self):
        """Test content type categorization"""
        view = DashboardView()
        content_stats = view.get_content_type_statistics()

        # Test format counts
        self.assertEqual(content_stats['ebook_count'], 2)  # epub + pdf
        self.assertEqual(content_stats['comic_count'], 1)  # cbr
        self.assertEqual(content_stats['audiobook_count'], 0)  # No audiobooks

        # Test entity counts
        self.assertEqual(content_stats['series_count'], 2)
        self.assertEqual(content_stats['series_with_books'], 2)  # Both series have books
        self.assertEqual(content_stats['author_count'], 2)
        self.assertEqual(content_stats['publisher_count'], 1)
        self.assertEqual(content_stats['genre_count'], 2)

    def test_get_recent_activity(self):
        """Test recent activity tracking"""
        view = DashboardView()
        recent_activity = view.get_recent_activity()

        # Test recent counts (within last 7 days)
        self.assertEqual(recent_activity['recently_added'], 4)  # All non-placeholder books
        self.assertEqual(recent_activity['recently_updated'], 1)  # Only metadata3 updated today
        self.assertEqual(recent_activity['recent_scans'], 1)  # One scan log
        self.assertEqual(recent_activity['recent_scan_folders'], 1)  # One folder scanned

    def test_prepare_chart_data(self):
        """Test chart data preparation for visualizations"""
        view = DashboardView()

        # Mock format stats
        format_stats = [
            {'file_format': 'epub', 'count': 2},
            {'file_format': 'pdf', 'count': 1},
            {'file_format': 'cbr', 'count': 1}
        ]

        # Mock metadata stats
        metadata_stats = {
            'books_with_metadata': 3,
            'books_with_author': 3,
            'books_with_cover': 2,
            'books_with_isbn': 1,
            'books_in_series': 2,
            'high_confidence_count': 1,
            'medium_confidence_count': 2,
            'low_confidence_count': 1
        }

        # Mock issue stats
        issue_stats = {
            'missing_covers': 2,
            'missing_authors': 1,
            'needs_review': 2,
            'low_confidence': 1,
            'missing_isbn': 3
        }

        chart_data = view.prepare_chart_data(format_stats, metadata_stats, issue_stats)

        # Test that chart data is properly structured
        self.assertIn('format_labels', chart_data)
        self.assertIn('format_data', chart_data)
        self.assertIn('completeness_labels', chart_data)
        self.assertIn('completeness_data', chart_data)
        self.assertIn('confidence_labels', chart_data)
        self.assertIn('confidence_data', chart_data)

        # Test format chart data
        self.assertEqual(chart_data['format_labels'], ['EPUB', 'PDF', 'CBR'])
        self.assertEqual(chart_data['format_data'], [2, 1, 1])

        # Test completeness chart data
        expected_completeness_labels = ['Title', 'Author', 'Cover', 'ISBN', 'Series']
        self.assertEqual(chart_data['completeness_labels'], expected_completeness_labels)
        self.assertEqual(chart_data['completeness_data'], [3, 3, 2, 1, 2])

        # Test confidence chart data
        expected_confidence_labels = ['High (80%+)', 'Medium (50-80%)', 'Low (<50%)']
        self.assertEqual(chart_data['confidence_labels'], expected_confidence_labels)
        self.assertEqual(chart_data['confidence_data'], [1, 2, 1])

    def test_dashboard_context_integration(self):
        """Test full dashboard context integration"""
        response = self.client.get(reverse('dashboard'))
        context = response.context

        # Verify all required context variables are present
        required_keys = [
            'total_books', 'books_with_metadata', 'books_with_author',
            'books_with_cover', 'books_with_isbn', 'books_in_series',
            'needs_review_count', 'issue_stats', 'format_stats',
            'recent_activity', 'chart_data', 'completion_percentage',
            'author_percentage', 'cover_percentage', 'isbn_percentage',
            'series_percentage', 'review_percentage', 'overall_quality_score',
            'completeness_score'
        ]

        for key in required_keys:
            self.assertIn(key, context, f"Missing context key: {key}")

        # Test that chart data is JSON serializable
        chart_data = context['chart_data']
        try:
            json.dumps(chart_data)
        except (TypeError, ValueError):
            self.fail("Chart data is not JSON serializable")

    def test_dashboard_with_empty_database(self):
        """Test dashboard behavior with no books"""
        # Clear all books
        Book.objects.all().delete()
        FinalMetadata.objects.all().delete()

        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)

        context = response.context
        self.assertEqual(context['total_books'], 0)
        self.assertEqual(context['completion_percentage'], 0.0)  # Should handle division by zero

    def test_dashboard_with_extreme_values(self):
        """Test dashboard with extreme confidence/completeness values"""
        # Create book with extreme values
        extreme_book = Book.objects.create(
            file_path='/test/extreme.epub',
            file_format='epub',
            file_size=999999999,
            scan_folder=self.scan_folder
        )
        FinalMetadata.objects.create(
            book=extreme_book,
            final_title='Extreme Book',
            overall_confidence=1.0,  # Maximum confidence
            completeness_score=0.0   # Minimum completeness
        )

        view = DashboardView()
        view.request = MagicMock()
        context = view.get_context_data()

        # Should handle extreme values gracefully
        self.assertGreaterEqual(context['overall_quality_score'], 0)
        self.assertLessEqual(context['overall_quality_score'], 100)
        self.assertGreaterEqual(context['completeness_score'], 0)
        self.assertLessEqual(context['completeness_score'], 100)

    @patch('books.views.timezone.now')
    def test_recent_activity_time_boundary(self, mock_now):
        """Test recent activity time boundary calculations"""
        # Set a fixed 'now' time
        fixed_now = timezone.make_aware(datetime(2023, 9, 20, 12, 0, 0))
        mock_now.return_value = fixed_now

        # Create a book exactly 7 days ago (should be included)
        Book.objects.create(
            file_path='/test/week_ago.epub',
            file_format='epub',
            file_size=1000000,
            scan_folder=self.scan_folder,
            first_scanned=fixed_now - timedelta(days=7)
        )

        # Create a book 8 days ago (should be excluded)
        Book.objects.create(
            file_path='/test/old.epub',
            file_format='epub',
            file_size=1000000,
            scan_folder=self.scan_folder,
            first_scanned=fixed_now - timedelta(days=8)
        )

        view = DashboardView()
        recent_activity = view.get_recent_activity()

        # The week_ago_book should be included, old_book should not
        # Plus our existing test books within the last 7 days
        self.assertGreaterEqual(recent_activity['recently_added'], 1)


class DashboardViewEdgeCaseTests(TestCase):
    """Test edge cases and error handling for dashboard views"""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.client.login(username='testuser', password='testpass123')

    def test_dashboard_with_malformed_series_numbers(self):
        """Test dashboard handles malformed series numbers gracefully"""
        scan_folder = ScanFolder.objects.create(
            path='/test', is_active=True
        )

        series = Series.objects.create(name='Malformed Series')

        # Create books with invalid series numbers
        for i, invalid_number in enumerate(['abc', 'N/A', '', None]):
            book = Book.objects.create(
                file_path=f'/test/book{i}.epub',
                file_format='epub',
                file_size=1000000,
                scan_folder=scan_folder
            )
            FinalMetadata.objects.create(book=book)
            BookSeries.objects.create(
                book=book,
                series=series,
                series_number=invalid_number,
                is_active=True,
                source=DataSource.objects.create(name='Test')
            )

        view = DashboardView()
        # Should not raise an exception
        gaps_count = view.get_incomplete_series_count()
        self.assertIsInstance(gaps_count, int)

    def test_dashboard_performance_with_large_dataset(self):
        """Test dashboard performance considerations with larger dataset"""
        scan_folder = ScanFolder.objects.create(
            path='/test', is_active=True
        )

        # Create a moderate number of books to test query efficiency
        books = []
        for i in range(100):
            book = Book.objects.create(
                file_path=f'/test/book{i}.epub',
                file_format='epub',
                file_size=1000000,
                scan_folder=scan_folder
            )
            books.append(book)

        # Bulk create metadata
        metadata_objects = [
            FinalMetadata(
                book=book,
                final_title=f'Book {i}',
                overall_confidence=0.5 + (i % 5) * 0.1,
                completeness_score=0.3 + (i % 7) * 0.1
            )
            for i, book in enumerate(books)
        ]
        FinalMetadata.objects.bulk_create(metadata_objects)

        # Dashboard should load without timeout
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)

    def test_dashboard_with_null_values(self):
        """Test dashboard handles null values in database"""
        scan_folder = ScanFolder.objects.create(
            path='/test', is_active=True
        )

        book = Book.objects.create(
            file_path='/test/null_book.epub',
            file_format='epub',
            file_size=1000000,
            scan_folder=scan_folder
        )

        # Create metadata with null values
        FinalMetadata.objects.create(
            book=book,
            final_title=None,
            final_author=None,
            isbn=None,
            publication_year=None,
            language=None,
            description=None,
            overall_confidence=None,
            completeness_score=None
        )

        view = DashboardView()
        view.request = MagicMock()
        context = view.get_context_data()

        # Should handle null values gracefully
        self.assertIsNotNone(context['avg_confidence'])
        self.assertIsNotNone(context['avg_completeness'])
        self.assertIsInstance(context['overall_quality_score'], (int, float))
        self.assertIsInstance(context['completeness_score'], (int, float))
