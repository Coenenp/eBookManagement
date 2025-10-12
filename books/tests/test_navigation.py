"""
Test cases for book detail view navigation functionality.
"""
import tempfile
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from books.models import FinalMetadata, ScanFolder
from books.tests.test_helpers import create_test_book_with_file


class BookDetailNavigationTestCase(TestCase):
    """Test the prev/next navigation buttons in book detail view."""

    def setUp(self):
        """Set up test data."""
        self.client = Client()
        self.user = User.objects.create_user(username='testuser', password='testpass')

        # Create a scan folder
        self.scan_folder = ScanFolder.objects.create(
            name='Test Folder',
            path=tempfile.mkdtemp(),
            language='en'
        )

        # Create test books with proper Book model fields
        # Create books first
        self.book1 = create_test_book_with_file(
            file_path='/test/book1.epub',
            file_format='epub',
            scan_folder=self.scan_folder
        )

        self.book2 = create_test_book_with_file(
            file_path='/test/book2.epub',
            file_format='epub',
            scan_folder=self.scan_folder
        )

        self.book3 = create_test_book_with_file(
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
        create_test_book_with_file(
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
        create_test_book_with_file(
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
            path=tempfile.mkdtemp(),
            language='en'
        )

        # Create multiple books for comprehensive testing
        self.books = []
        for i in range(1, 6):  # Create books 1-5
            book = create_test_book_with_file(
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
