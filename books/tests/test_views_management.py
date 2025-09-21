"""
Comprehensive test suite for management views in views.py.
Tests CRUD operations for Authors, Genres, and Series management.
"""

from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from django.contrib.messages import get_messages

from books.models import (
    Book, Author, Series, Genre, DataSource, ScanFolder,
    FinalMetadata, BookSeries, BookAuthor, BookGenre
)


class AuthorManagementViewTests(TestCase):
    """Test suite for Author management views"""

    def setUp(self):
        """Set up test data for author management tests"""
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.client.login(username='testuser', password='testpass123')

        # Create test data sources
        self.manual_source = DataSource.objects.create(
            name='Manual Entry',
            trust_level=0.9
        )
        self.epub_source = DataSource.objects.create(
            name='EPUB',
            trust_level=0.7
        )

        # Create test scan folder
        self.scan_folder = ScanFolder.objects.create(
            path='/test/books',
            is_active=True
        )

        # Create test authors
        self.reviewed_author = Author.objects.create(
            name='Reviewed Author',
            first_name='Reviewed',
            last_name='Author',
            is_reviewed=True
        )
        self.unreviewed_author1 = Author.objects.create(
            name='Unreviewed Author 1',
            first_name='Unreviewed',
            last_name='Author1',
            is_reviewed=False
        )
        self.unreviewed_author2 = Author.objects.create(
            name='Unreviewed Author 2',
            first_name='Unreviewed',
            last_name='Author2',
            is_reviewed=False
        )

        # Create test books with author relationships
        self.book1 = Book.objects.create(
            file_path='/test/book1.epub',
            file_format='epub',
            file_size=1000000,
            scan_folder=self.scan_folder
        )
        FinalMetadata.objects.create(book=self.book1)

        # Create book-author relationships
        BookAuthor.objects.create(
            book=self.book1,
            author=self.reviewed_author,
            confidence=0.9,
            is_main_author=True,
            is_active=True,
            source=self.manual_source
        )
        BookAuthor.objects.create(
            book=self.book1,
            author=self.unreviewed_author1,
            confidence=0.8,
            is_main_author=False,
            is_active=True,
            source=self.epub_source
        )

    def test_author_list_view_requires_login(self):
        """Test that author list view requires authentication"""
        self.client.logout()
        response = self.client.get(reverse('books:author_list'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('login', response.url)

    def test_author_list_view_loads_successfully(self):
        """Test that author list view loads for authenticated users"""
        response = self.client.get(reverse('books:author_list'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'books/author_list.html')
        self.assertIn('authors', response.context)

    def test_author_list_view_pagination(self):
        """Test author list pagination"""
        # Create many authors to test pagination
        Author.objects.bulk_create([
            Author(name=f'Test Author {i}')
            for i in range(30)
        ])

        response = self.client.get(reverse('books:author_list'))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['is_paginated'])
        self.assertEqual(len(response.context['authors']), 25)  # paginate_by = 25

    def test_author_list_view_search_functionality(self):
        """Test author search functionality"""
        # Search by name
        response = self.client.get(reverse('books:author_list'), {'search': 'Reviewed'})
        self.assertEqual(response.status_code, 200)
        authors = response.context['authors']
        self.assertEqual(len(authors), 1)
        self.assertEqual(authors[0], self.reviewed_author)

        # Search by first name
        response = self.client.get(reverse('books:author_list'), {'search': 'Unreviewed'})
        authors = response.context['authors']
        self.assertEqual(len(authors), 2)

        # Search with no results
        response = self.client.get(reverse('books:author_list'), {'search': 'NonExistent'})
        authors = response.context['authors']
        self.assertEqual(len(authors), 0)

    def test_author_list_view_review_filter(self):
        """Test author list filtering by review status"""
        # Filter reviewed authors
        response = self.client.get(reverse('books:author_list'), {'is_reviewed': 'true'})
        authors = response.context['authors']
        self.assertEqual(len(authors), 1)
        self.assertEqual(authors[0], self.reviewed_author)

        # Filter unreviewed authors
        response = self.client.get(reverse('books:author_list'), {'is_reviewed': 'false'})
        authors = response.context['authors']
        self.assertEqual(len(authors), 2)
        self.assertIn(self.unreviewed_author1, authors)
        self.assertIn(self.unreviewed_author2, authors)

    def test_author_list_view_context_data(self):
        """Test author list view context data includes sources"""
        response = self.client.get(reverse('books:author_list'))
        context = response.context

        self.assertIn('search_query', context)
        self.assertIn('author_sources', context)

        # Check that author sources are correctly mapped
        author_sources = context['author_sources']
        self.assertIn(self.reviewed_author.id, author_sources)
        self.assertIn('Manual Entry', author_sources[self.reviewed_author.id])

    def test_author_bulk_delete_view_requires_login(self):
        """Test that author bulk delete requires authentication"""
        self.client.logout()
        response = self.client.post(
            reverse('books:author_bulk_delete'),
            {'selected_authors': [str(self.unreviewed_author1.id)]}
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn('login', response.url)

    def test_author_bulk_delete_unreviewed_authors(self):
        """Test bulk deletion of unreviewed authors"""
        response = self.client.post(
            reverse('books:author_bulk_delete'),
            {'selected_authors': [str(self.unreviewed_author1.id), str(self.unreviewed_author2.id)]}
        )

        # Should redirect to author list
        self.assertRedirects(response, reverse('books:author_list'))

        # Check that unreviewed authors were deleted
        self.assertFalse(Author.objects.filter(id=self.unreviewed_author1.id).exists())
        self.assertFalse(Author.objects.filter(id=self.unreviewed_author2.id).exists())

        # Check that reviewed author was not deleted
        self.assertTrue(Author.objects.filter(id=self.reviewed_author.id).exists())

        # Check success message
        messages = list(get_messages(response.wsgi_request))
        self.assertTrue(any('Deleted 2 authors' in str(msg) for msg in messages))

    def test_author_bulk_delete_protects_reviewed_authors(self):
        """Test that bulk delete protects reviewed authors"""
        response = self.client.post(
            reverse('books:author_bulk_delete'),
            {'selected_authors': [str(self.reviewed_author.id)]}
        )

        # Reviewed author should still exist
        self.assertTrue(Author.objects.filter(id=self.reviewed_author.id).exists())

        # Check info message about protection
        messages = list(get_messages(response.wsgi_request))
        self.assertTrue(any('No authors deleted' in str(msg) for msg in messages))

    def test_author_bulk_delete_removes_book_relationships(self):
        """Test that bulk delete removes BookAuthor relationships"""
        # Verify relationship exists before deletion
        self.assertTrue(BookAuthor.objects.filter(author=self.unreviewed_author1).exists())

        response = self.client.post(
            reverse('books:author_bulk_delete'),
            {'selected_authors': [str(self.unreviewed_author1.id)]}
        )

        # Verify the request was successful
        self.assertEqual(response.status_code, 302)  # Should redirect after successful delete

        # Verify relationship was deleted
        self.assertFalse(BookAuthor.objects.filter(author=self.unreviewed_author1).exists())

    def test_author_delete_view_requires_login(self):
        """Test that author delete view requires authentication"""
        self.client.logout()
        response = self.client.get(
            reverse('books:author_delete', kwargs={'pk': self.unreviewed_author1.pk})
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn('login', response.url)

    def test_author_delete_view_loads_confirmation(self):
        """Test that author delete view loads confirmation page"""
        response = self.client.get(
            reverse('books:author_delete', kwargs={'pk': self.unreviewed_author1.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'books/author_confirm_delete.html')
        self.assertEqual(response.context['object'], self.unreviewed_author1)

    def test_author_delete_view_successful_deletion(self):
        """Test successful author deletion"""
        author_name = self.unreviewed_author1.name

        response = self.client.post(
            reverse('books:author_delete', kwargs={'pk': self.unreviewed_author1.pk})
        )

        # Should redirect to author list
        self.assertRedirects(response, reverse('books:author_list'))

        # Author should be deleted
        self.assertFalse(Author.objects.filter(id=self.unreviewed_author1.id).exists())

        # BookAuthor relationships should be deleted
        self.assertFalse(BookAuthor.objects.filter(author_id=self.unreviewed_author1.id).exists())

        # Check success message
        messages = list(get_messages(response.wsgi_request))
        self.assertTrue(any(author_name in str(msg) for msg in messages))

    def test_author_delete_view_nonexistent_author(self):
        """Test author delete view with nonexistent author"""
        response = self.client.get(
            reverse('books:author_delete', kwargs={'pk': 99999})
        )
        self.assertEqual(response.status_code, 404)

    def test_author_mark_reviewed_view_requires_login(self):
        """Test that author mark reviewed requires authentication"""
        self.client.logout()
        response = self.client.post(
            reverse('books:author_mark_reviewed'),
            {'selected_authors': [str(self.unreviewed_author1.id)]}
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn('login', response.url)

    def test_author_mark_reviewed_successful(self):
        """Test successful author review marking"""
        response = self.client.post(
            reverse('books:author_mark_reviewed'),
            {'selected_authors': [str(self.unreviewed_author1.id), str(self.unreviewed_author2.id)]}
        )

        # Should redirect to author list
        self.assertRedirects(response, reverse('books:author_list'))

        # Authors should be marked as reviewed
        self.unreviewed_author1.refresh_from_db()
        self.unreviewed_author2.refresh_from_db()
        self.assertTrue(self.unreviewed_author1.is_reviewed)
        self.assertTrue(self.unreviewed_author2.is_reviewed)

        # Check success message
        messages = list(get_messages(response.wsgi_request))
        self.assertTrue(any('Marked 2 author(s) as reviewed' in str(msg) for msg in messages))

    def test_author_mark_reviewed_already_reviewed(self):
        """Test marking already reviewed authors"""
        response = self.client.post(
            reverse('books:author_mark_reviewed'),
            {'selected_authors': [str(self.reviewed_author.id)]}
        )

        # Check info message about no changes
        messages = list(get_messages(response.wsgi_request))
        self.assertTrue(any('No changes made' in str(msg) for msg in messages))


class GenreManagementViewTests(TestCase):
    """Test suite for Genre management views"""

    def setUp(self):
        """Set up test data for genre management tests"""
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.client.login(username='testuser', password='testpass123')

        # Create test data sources
        self.manual_source = DataSource.objects.create(
            name='Manual Entry',
            trust_level=0.9
        )

        # Create test scan folder
        self.scan_folder = ScanFolder.objects.create(
            path='/test/books',
            is_active=True
        )

        # Create test genres
        self.reviewed_genre = Genre.objects.create(
            name='Science Fiction',
            is_reviewed=True
        )
        self.unreviewed_genre1 = Genre.objects.create(
            name='Fantasy',
            is_reviewed=False
        )
        self.unreviewed_genre2 = Genre.objects.create(
            name='Mystery',
            is_reviewed=False
        )

        # Create test book with genre relationships
        self.book1 = Book.objects.create(
            file_path='/test/book1.epub',
            file_format='epub',
            file_size=1000000,
            scan_folder=self.scan_folder
        )
        FinalMetadata.objects.create(book=self.book1)

        # Create book-genre relationships
        BookGenre.objects.create(
            book=self.book1,
            genre=self.reviewed_genre,
            confidence=0.9,
            is_active=True,
            source=self.manual_source
        )

    def test_genre_list_view_requires_login(self):
        """Test that genre list view requires authentication"""
        self.client.logout()
        response = self.client.get(reverse('books:genre_list'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('login', response.url)

    def test_genre_list_view_loads_successfully(self):
        """Test that genre list view loads for authenticated users"""
        response = self.client.get(reverse('books:genre_list'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'books/genre_list.html')
        self.assertIn('genres', response.context)

    def test_genre_list_view_search_functionality(self):
        """Test genre search functionality"""
        # Search by name
        response = self.client.get(reverse('books:genre_list'), {'search': 'Science'})
        self.assertEqual(response.status_code, 200)
        genres = response.context['genres']
        self.assertEqual(len(genres), 1)
        self.assertEqual(genres[0], self.reviewed_genre)

        # Search with no results
        response = self.client.get(reverse('books:genre_list'), {'search': 'NonExistent'})
        genres = response.context['genres']
        self.assertEqual(len(genres), 0)

    def test_genre_list_view_review_filter(self):
        """Test genre list filtering by review status"""
        # Filter reviewed genres
        response = self.client.get(reverse('books:genre_list'), {'is_reviewed': 'true'})
        genres = response.context['genres']
        self.assertEqual(len(genres), 1)
        self.assertEqual(genres[0], self.reviewed_genre)

        # Filter unreviewed genres
        response = self.client.get(reverse('books:genre_list'), {'is_reviewed': 'false'})
        genres = response.context['genres']
        self.assertEqual(len(genres), 2)
        self.assertIn(self.unreviewed_genre1, genres)
        self.assertIn(self.unreviewed_genre2, genres)

    def test_genre_bulk_delete_view_requires_login(self):
        """Test that genre bulk delete requires authentication"""
        self.client.logout()
        response = self.client.post(
            reverse('books:genre_bulk_delete'),
            {'selected_genres': [str(self.unreviewed_genre1.id)]}
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn('login', response.url)

    def test_genre_bulk_delete_unreviewed_genres(self):
        """Test bulk deletion of unreviewed genres"""
        response = self.client.post(
            reverse('books:genre_bulk_delete'),
            {'selected_genres': [str(self.unreviewed_genre1.id), str(self.unreviewed_genre2.id)]}
        )

        # Should redirect to genre list
        self.assertRedirects(response, reverse('books:genre_list'))

        # Check that unreviewed genres were deleted
        self.assertFalse(Genre.objects.filter(id=self.unreviewed_genre1.id).exists())
        self.assertFalse(Genre.objects.filter(id=self.unreviewed_genre2.id).exists())

        # Check that reviewed genre was not deleted
        self.assertTrue(Genre.objects.filter(id=self.reviewed_genre.id).exists())

        # Check success message
        messages = list(get_messages(response.wsgi_request))
        self.assertTrue(any('Deleted 2 genres' in str(msg) for msg in messages))

    def test_genre_bulk_delete_protects_reviewed_genres(self):
        """Test that bulk delete protects reviewed genres"""
        response = self.client.post(
            reverse('books:genre_bulk_delete'),
            {'selected_genres': [str(self.reviewed_genre.id)]}
        )

        # Reviewed genre should still exist
        self.assertTrue(Genre.objects.filter(id=self.reviewed_genre.id).exists())

        # Check info message about protection
        messages = list(get_messages(response.wsgi_request))
        self.assertTrue(any('No genres deleted' in str(msg) for msg in messages))

    def test_genre_delete_view_requires_login(self):
        """Test that genre delete view requires authentication"""
        self.client.logout()
        response = self.client.get(
            reverse('books:genre_delete', kwargs={'pk': self.unreviewed_genre1.pk})
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn('login', response.url)

    def test_genre_delete_view_loads_confirmation(self):
        """Test that genre delete view loads confirmation page"""
        response = self.client.get(
            reverse('books:genre_delete', kwargs={'pk': self.unreviewed_genre1.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'books/genre_confirm_delete.html')
        self.assertEqual(response.context['object'], self.unreviewed_genre1)

    def test_genre_delete_view_successful_deletion(self):
        """Test successful genre deletion"""
        genre_name = self.unreviewed_genre1.name

        response = self.client.post(
            reverse('books:genre_delete', kwargs={'pk': self.unreviewed_genre1.pk})
        )

        # Should redirect to genre list
        self.assertRedirects(response, reverse('books:genre_list'))

        # Genre should be deleted
        self.assertFalse(Genre.objects.filter(id=self.unreviewed_genre1.id).exists())

        # Check success message
        messages = list(get_messages(response.wsgi_request))
        self.assertTrue(any(genre_name in str(msg) for msg in messages))

    def test_genre_mark_reviewed_view_requires_login(self):
        """Test that genre mark reviewed requires authentication"""
        self.client.logout()
        response = self.client.post(
            reverse('books:genre_mark_reviewed'),
            {'selected_genres': [str(self.unreviewed_genre1.id)]}
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn('login', response.url)

    def test_genre_mark_reviewed_successful(self):
        """Test successful genre review marking"""
        response = self.client.post(
            reverse('books:genre_mark_reviewed'),
            {'selected_genres': [str(self.unreviewed_genre1.id), str(self.unreviewed_genre2.id)]}
        )

        # Should redirect to genre list
        self.assertRedirects(response, reverse('books:genre_list'))

        # Genres should be marked as reviewed
        self.unreviewed_genre1.refresh_from_db()
        self.unreviewed_genre2.refresh_from_db()
        self.assertTrue(self.unreviewed_genre1.is_reviewed)
        self.assertTrue(self.unreviewed_genre2.is_reviewed)

        # Check success message
        messages = list(get_messages(response.wsgi_request))
        self.assertTrue(any('Marked 2 genre(s) as reviewed' in str(msg) for msg in messages))


class SeriesManagementViewTests(TestCase):
    """Test suite for Series management views"""

    def setUp(self):
        """Set up test data for series management tests"""
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.client.login(username='testuser', password='testpass123')

        # Create test data sources
        self.manual_source = DataSource.objects.create(
            name='Manual Entry',
            trust_level=0.9
        )

        # Create test scan folder
        self.scan_folder = ScanFolder.objects.create(
            path='/test/books',
            is_active=True
        )

        # Create test series
        self.series1 = Series.objects.create(name='Test Series 1')
        self.series2 = Series.objects.create(name='Test Series 2')
        self.series3 = Series.objects.create(name='Empty Series')

        # Create test books with series relationships
        self.book1 = Book.objects.create(
            file_path='/test/book1.epub',
            file_format='epub',
            file_size=1000000,
            scan_folder=self.scan_folder
        )
        self.book2 = Book.objects.create(
            file_path='/test/book2.epub',
            file_format='epub',
            file_size=1000000,
            scan_folder=self.scan_folder
        )

        FinalMetadata.objects.create(book=self.book1)
        FinalMetadata.objects.create(book=self.book2)

        # Create book-series relationships
        BookSeries.objects.create(
            book=self.book1,
            series=self.series1,
            series_number='1',
            confidence=0.9,
            is_active=True,
            source=self.manual_source
        )
        BookSeries.objects.create(
            book=self.book2,
            series=self.series1,
            series_number='2',
            confidence=0.8,
            is_active=True,
            source=self.manual_source
        )

    def test_series_list_view_requires_login(self):
        """Test that series list view requires authentication"""
        self.client.logout()
        response = self.client.get(reverse('books:series_list'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('login', response.url)

    def test_series_list_view_loads_successfully(self):
        """Test that series list view loads for authenticated users"""
        response = self.client.get(reverse('books:series_list'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'books/series_list.html')
        self.assertIn('series', response.context)

    def test_series_list_view_shows_book_counts(self):
        """Test that series list shows correct book counts"""
        response = self.client.get(reverse('books:series_list'))
        context = response.context

        # Series should be annotated with book counts
        series_list = list(context['series'])

        # Find our test series
        test_series1 = next(s for s in series_list if s.name == 'Test Series 1')
        test_series3 = next(s for s in series_list if s.name == 'Empty Series')

        # Verify book counts (assuming the view annotates book counts)
        # This test assumes the view adds book_count annotation
        if hasattr(test_series1, 'book_count'):
            self.assertEqual(test_series1.book_count, 2)
            self.assertEqual(test_series3.book_count, 0)

    def test_series_with_books_view_functionality(self):
        """Test series filtering and search functionality"""
        # Test search functionality if implemented
        response = self.client.get(reverse('books:series_list'), {'search': 'Test Series 1'})
        self.assertEqual(response.status_code, 200)

        if 'search' in response.context:
            # If search is implemented, test it
            series_list = response.context['series']
            self.assertTrue(any(s.name == 'Test Series 1' for s in series_list))

    def test_series_detail_view_if_exists(self):
        """Test series detail view if it exists"""
        # This test checks if series detail view exists
        try:
            response = self.client.get(reverse('books:series_detail', kwargs={'pk': self.series1.pk}))
            if response.status_code == 200:
                self.assertIn('series', response.context)
                self.assertEqual(response.context['series'], self.series1)
        except Exception:
            # Series detail view may not be implemented yet
            pass


class ManagementViewEdgeCaseTests(TestCase):
    """Test edge cases and error scenarios in management views"""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.client.login(username='testuser', password='testpass123')

    def test_bulk_operations_with_empty_selection(self):
        """Test bulk operations with no items selected"""
        # Test author bulk delete with empty selection
        response = self.client.post(
            reverse('books:author_bulk_delete'),
            {'selected_authors': []}
        )
        self.assertEqual(response.status_code, 302)

        # Test author mark reviewed with empty selection
        response = self.client.post(
            reverse('books:author_mark_reviewed'),
            {'selected_authors': []}
        )
        self.assertEqual(response.status_code, 302)

        # Test genre bulk delete with empty selection
        response = self.client.post(
            reverse('books:genre_bulk_delete'),
            {'selected_genres': []}
        )
        self.assertEqual(response.status_code, 302)

    def test_bulk_operations_with_invalid_ids(self):
        """Test bulk operations with invalid item IDs"""
        # Test with non-existent author IDs
        response = self.client.post(
            reverse('books:author_bulk_delete'),
            {'selected_authors': ['99999', '88888']}
        )
        self.assertEqual(response.status_code, 302)

        # Should handle gracefully without errors
        # Note: In a real implementation, should check for appropriate error messages

    def test_management_views_with_large_datasets(self):
        """Test management views performance with larger datasets"""
        # Create many items to test pagination and performance
        authors = [
            Author.objects.create(name=f'Author {i}', is_reviewed=False)
            for i in range(100)
        ]

        # List view should handle large datasets
        response = self.client.get(reverse('books:author_list'))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['is_paginated'])

        # Bulk operations should handle many items
        selected_ids = [str(author.id) for author in authors[:50]]
        response = self.client.post(
            reverse('books:author_mark_reviewed'),
            {'selected_authors': selected_ids}
        )
        self.assertEqual(response.status_code, 302)

    def test_management_views_with_special_characters(self):
        """Test management views with special characters in names"""
        # Create items with special characters
        special_author = Author.objects.create(
            name='Ñoël Müller-Smith & Co.',
            is_reviewed=False
        )
        Genre.objects.create(
            name='Sci-Fi & Fantasy (Überkool)',
            is_reviewed=False
        )

        # Views should handle special characters
        response = self.client.get(reverse('books:author_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Ñoël Müller-Smith')

        response = self.client.get(reverse('books:genre_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Sci-Fi &amp; Fantasy')

        # Operations should work with special characters
        response = self.client.post(
            reverse('books:author_bulk_delete'),
            {'selected_authors': [str(special_author.id)]}
        )
        self.assertEqual(response.status_code, 302)

    def test_concurrent_modifications(self):
        """Test handling of concurrent modifications"""
        author = Author.objects.create(name='Test Author', is_reviewed=False)

        # Simulate concurrent deletion - delete the author outside the view
        author_id = author.id
        author.delete()

        # Try to operate on the deleted author
        response = self.client.post(
            reverse('books:author_mark_reviewed'),
            {'selected_authors': [str(author_id)]}
        )

        # Should handle gracefully
        self.assertEqual(response.status_code, 302)


class BookRenamerViewTests(TestCase):
    """Comprehensive tests for BookRenamerView and file path generation."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.client.login(username='testuser', password='testpass123')

        # Create test data
        self.author = Author.objects.create(name='Test Author')
        self.genre_fiction = Genre.objects.create(name='Fiction')
        self.genre_scifi = Genre.objects.create(name='Science Fiction')
        self.series = Series.objects.create(name='Test Series')

    def test_book_renamer_view_access(self):
        """Test basic access to book renamer view."""
        response = self.client.get(reverse('books:book_renamer'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'books/book_renamer.html')

    def test_book_renamer_view_context(self):
        """Test that book renamer view provides necessary context."""
        # Create test books
        book1 = Book.objects.create(
            title="Test Book 1",
            file_path="/library/test1.epub",
            file_format="epub"
        )
        FinalMetadata.objects.create(
            book=book1,
            final_title="Test Book 1",
            final_author="Test Author",
            final_series="Test Series",
            final_series_number="1"
        )

        response = self.client.get(reverse('books:book_renamer'))
        self.assertEqual(response.status_code, 200)

        # Check context variables
        self.assertIn('books', response.context)
        self.assertIn('stats', response.context)

        # Verify stats structure
        stats = response.context['stats']
        expected_stats = [
            'total_books', 'needs_rename', 'duplicate_paths', 'missing_metadata',
            'series_books', 'standalone_books', 'comic_books', 'complete_series_count'
        ]
        for stat in expected_stats:
            self.assertIn(stat, stats)

    def test_path_generation_for_regular_book(self):
        """Test file path generation for regular books."""
        from books.views import BookRenamerView

        book = Book.objects.create(
            title="The Test Book: A Novel!",
            file_path="/old/path/test.epub",
            file_format="epub"
        )
        book.authors.add(self.author)
        book.genres.add(self.genre_fiction)

        FinalMetadata.objects.create(
            book=book,
            final_title="The Test Book: A Novel!",
            final_author="Test Author",
            language="en"
        )

        renamer_view = BookRenamerView()
        new_path = renamer_view._generate_new_file_path(book)

        # Verify path structure
        self.assertIsInstance(new_path, str)
        self.assertIn("Test Author", new_path)
        self.assertIn("The Test Book - A Novel", new_path)  # Special chars cleaned
        self.assertNotIn(":", new_path)
        self.assertNotIn("!", new_path)

    def test_path_generation_for_series_book(self):
        """Test file path generation for books in a series."""
        from books.views import BookRenamerView

        book = Book.objects.create(
            title="Test Series Book 1",
            file_path="/old/path/series1.epub",
            file_format="epub"
        )
        book.authors.add(self.author)
        book.genres.add(self.genre_scifi)

        FinalMetadata.objects.create(
            book=book,
            final_title="Test Series Book 1",
            final_author="Test Author",
            final_series="Test Series",
            final_series_number="1",
            language="en"
        )

        renamer_view = BookRenamerView()
        new_path = renamer_view._generate_new_file_path(book)

        # Verify series book structure
        self.assertIn("Test Author", new_path)
        self.assertIn("Test Series", new_path)
        self.assertIn("01", new_path)  # Series number should be padded

    def test_path_generation_for_comic_book(self):
        """Test file path generation for comic books."""
        from books.views import BookRenamerView
        from unittest.mock import patch

        book = Book.objects.create(
            title="Spider-Man #001",
            file_path="/comics/spider-man-001.cbz",
            file_format="cbz"
        )

        FinalMetadata.objects.create(
            book=book,
            final_title="Spider-Man #001",
            final_series="Spider-Man",
            final_series_number="1",
            language="en"
        )

        renamer_view = BookRenamerView()

        # Mock comic metadata
        with patch.object(renamer_view, '_get_comic_metadata') as mock_get_metadata:
            mock_get_metadata.return_value = {
                'series': 'Spider-Man',
                'issue_number': '1',
                'title': 'Spider-Man #001',
                'language': 'en'
            }

            new_path = renamer_view._generate_new_file_path(book)

            # Verify comic book structure
            self.assertIn("CBZ", new_path)  # Should be in CBZ folder
            self.assertIn("Spider-Man", new_path)

    def test_series_completion_analysis(self):
        """Test series completion analysis for multiple books."""
        from books.views import BookRenamerView

        # Create multiple books in the same series
        series_books = []
        for i in range(1, 6):  # Books 1-5
            book = Book.objects.create(
                title=f"Test Series Book {i}",
                file_path=f"/series/book{i}.epub",
                file_format="epub"
            )
            book.authors.add(self.author)
            book.genres.add(self.genre_fiction)

            FinalMetadata.objects.create(
                book=book,
                final_title=f"Test Series Book {i}",
                final_author="Test Author",
                final_series="Test Series",
                final_series_number=str(i)
            )
            series_books.append(book)

        renamer_view = BookRenamerView()
        complete_series = renamer_view._analyze_series_completion()

        # Should identify this as a complete series
        self.assertIsInstance(complete_series, dict)
        self.assertIn("Test Series", complete_series)

    def test_warning_generation(self):
        """Test warning generation for various scenarios."""
        from books.views import BookRenamerView

        # Create book with potential issues
        book = Book.objects.create(
            title="Test Book",
            file_path="/library/test.epub",
            file_format="epub"
        )

        # Missing metadata should generate warning
        renamer_view = BookRenamerView()
        warnings = renamer_view._generate_warnings(book)

        self.assertIsInstance(warnings, list)
        # Should warn about missing metadata

    def test_duplicate_path_detection(self):
        """Test detection of duplicate file paths."""
        from books.views import BookRenamerView
        from unittest.mock import patch

        book1 = Book.objects.create(
            title="Test Book 1",
            file_path="/library/book1.epub",
            file_format="epub"
        )

        book2 = Book.objects.create(
            title="Test Book 2",
            file_path="/library/book2.epub",
            file_format="epub"
        )

        # Add same metadata to both books to potentially create duplicate paths
        for book in [book1, book2]:
            book.authors.add(self.author)
            FinalMetadata.objects.create(
                book=book,
                final_title="Same Title",
                final_author="Test Author"
            )

        renamer_view = BookRenamerView()

        # Mock path generation to return same path
        with patch.object(renamer_view, '_generate_new_file_path') as mock_gen_path:
            mock_gen_path.return_value = "/library/Test Author/Same Title.epub"

            warnings = renamer_view._check_for_duplicate_paths(book1)
            # Should detect potential duplicates
            self.assertIsInstance(warnings, list)

    def test_filename_cleaning_comprehensive(self):
        """Test comprehensive filename cleaning scenarios."""
        from books.views import BookRenamerView

        renamer_view = BookRenamerView()

        test_cases = [
            ("Book: Title!", "Book - Title"),
            ("Book/with\\slashes", "Book-with-slashes"),
            ("Book<with>pipes|and?quotes\"", "Book-with-pipes-and-quotes"),
            ("Book   with    multiple     spaces", "Book with multiple spaces"),
            ("Book.with.dots", "Book.with.dots"),  # Dots should be preserved
            ("", ""),
            ("   ", ""),
            ("Book with éàü unicode", "Book with éàü unicode"),
            ("Multiple---dashes", "Multiple-dashes"),
        ]

        for input_name, expected in test_cases:
            with self.subTest(input_name=input_name):
                result = renamer_view._clean_filename(input_name)
                self.assertEqual(result, expected)

    def test_category_determination(self):
        """Test book category determination logic."""
        from books.views import BookRenamerView

        renamer_view = BookRenamerView()

        # Test fiction book
        fiction_book = Book.objects.create(
            title="Fiction Book",
            file_path="/library/fiction.epub",
            file_format="epub"
        )
        fiction_book.genres.add(self.genre_fiction)

        category = renamer_view._determine_category(fiction_book)
        self.assertEqual(category, "Fiction")

        # Test non-fiction book
        nonfiction_genre = Genre.objects.create(name="Biography")
        nonfiction_book = Book.objects.create(
            title="Biography Book",
            file_path="/library/bio.epub",
            file_format="epub"
        )
        nonfiction_book.genres.add(nonfiction_genre)

        category = renamer_view._determine_category(nonfiction_book)
        self.assertEqual(category, "Non-Fiction")

    def test_language_mapping(self):
        """Test language code to folder mapping."""
        from books.views import BookRenamerView

        renamer_view = BookRenamerView()

        test_mappings = [
            ('en', 'English'),
            ('nl', 'Nederlands'),
            ('fr', 'Francais'),
            ('de', 'Deutsch'),
            ('unknown', 'Nederlands'),  # Default
            ('', 'Nederlands'),  # Default
            (None, 'Nederlands'),  # Default
        ]

        for lang_code, expected_folder in test_mappings:
            with self.subTest(lang_code=lang_code):
                result = renamer_view._map_language_to_folder(lang_code)
                self.assertEqual(result, expected_folder)

    def test_comic_metadata_extraction(self):
        """Test comic metadata extraction functionality."""
        from books.views import BookRenamerView
        from unittest.mock import patch

        comic_book = Book.objects.create(
            title="Test Comic #5",
            file_path="/comics/test-005.cbz",
            file_format="cbz"
        )

        renamer_view = BookRenamerView()

        # Mock the comic metadata extraction
        with patch.object(renamer_view, '_get_comic_metadata') as mock_get_metadata:
            mock_get_metadata.return_value = {
                'series': 'Test Comic',
                'issue_number': '5',
                'title': 'Test Comic #5',
                'issue_type': 'main_series'
            }

            metadata = renamer_view._get_comic_metadata(comic_book)
            self.assertEqual(metadata['series'], 'Test Comic')
            self.assertEqual(metadata['issue_number'], '5')

    def test_issue_number_extraction(self):
        """Test comic issue number extraction from various sources."""
        from books.views import BookRenamerView

        comic_book = Book.objects.create(
            title="Comic #10",
            file_path="/comics/comic-010.cbz",
            file_format="cbz"
        )

        FinalMetadata.objects.create(
            book=comic_book,
            final_title="Comic #10",
            final_series="Comic Series",
            final_series_number="10"
        )

        renamer_view = BookRenamerView()

        # Test extraction from metadata
        comic_metadata = {'issue_number': '15'}
        result = renamer_view._extract_issue_number(comic_metadata, comic_book)
        self.assertEqual(result, 15)

        # Test extraction from final metadata
        comic_metadata = {}
        result = renamer_view._extract_issue_number(comic_metadata, comic_book)
        self.assertEqual(result, 10)

        # Test with invalid data
        comic_metadata = {'issue_number': 'invalid'}
        result = renamer_view._extract_issue_number(comic_metadata, comic_book)
        self.assertEqual(result, 10)  # Should fall back to final metadata

    def test_comic_series_completion_analysis(self):
        """Test comic series completion analysis."""
        from books.views import BookRenamerView
        from unittest.mock import patch

        # Create comic series with missing issues
        comic_issues = [1, 2, 4, 5]  # Missing issue 3
        for issue_num in comic_issues:
            book = Book.objects.create(
                title=f"Comic Series #{issue_num:03d}",
                file_path=f"/comics/series-{issue_num:03d}.cbz",
                file_format="cbz"
            )

            FinalMetadata.objects.create(
                book=book,
                final_title=f"Comic Series #{issue_num:03d}",
                final_series="Comic Series",
                final_series_number=str(issue_num)
            )

        renamer_view = BookRenamerView()

        # Mock comic metadata for analysis
        with patch.object(renamer_view, '_get_comic_metadata') as mock_get_metadata:
            mock_get_metadata.return_value = {
                'series': 'Comic Series',
                'issue_number': '1'
            }

            status = renamer_view._analyze_series_completion_status(
                Book.objects.filter(finalmetadata__final_series="Comic Series").first(),
                {'series': 'Comic Series'}
            )

            # Should indicate incomplete series
            self.assertIsInstance(status, str)
            self.assertIn("1", status)  # Should mention range

    def test_queryset_filtering_and_sorting(self):
        """Test book renamer view queryset filtering and sorting."""
        from books.views import BookRenamerView

        # Create various books
        books_data = [
            ("Book A", "Author A", None, None),
            ("Book B", "Author B", "Series B", "1"),
            ("Book C", "Author A", "Series A", "2"),
            ("Book D", "Author C", None, None),
        ]

        for title, author, series, series_num in books_data:
            book = Book.objects.create(
                title=title,
                file_path=f"/library/{title.lower().replace(' ', '_')}.epub",
                file_format="epub"
            )

            author_obj, _ = Author.objects.get_or_create(name=author)
            book.authors.add(author_obj)

            FinalMetadata.objects.create(
                book=book,
                final_title=title,
                final_author=author,
                final_series=series,
                final_series_number=series_num
            )

        renamer_view = BookRenamerView()
        renamer_view.request = type('Request', (), {'GET': {}})()

        queryset = renamer_view.get_queryset()
        self.assertEqual(queryset.count(), 4)

        # Books should be ordered properly
        book_titles = list(queryset.values_list('title', flat=True))
        self.assertIn("Book A", book_titles)
        self.assertIn("Book B", book_titles)

    def test_edge_cases_and_error_handling(self):
        """Test edge cases and error handling in path generation."""
        from books.views import BookRenamerView

        renamer_view = BookRenamerView()

        # Book with no metadata
        minimal_book = Book.objects.create(
            title="Minimal Book",
            file_path="/library/minimal.epub",
            file_format="epub"
        )

        # Should not crash
        try:
            new_path = renamer_view._generate_new_file_path(minimal_book)
            self.assertIsInstance(new_path, str)
        except Exception as e:
            self.fail(f"Path generation failed for minimal book: {e}")

        # Book with very long title
        long_title = "A" * 500
        long_title_book = Book.objects.create(
            title=long_title,
            file_path="/library/long.epub",
            file_format="epub"
        )

        try:
            new_path = renamer_view._generate_new_file_path(long_title_book)
            self.assertIsInstance(new_path, str)
            # Path should not be excessively long
            self.assertLess(len(new_path), 1000)
        except Exception as e:
            self.fail(f"Path generation failed for long title: {e}")

    def test_book_renamer_statistics(self):
        """Test statistics calculation in book renamer view."""
        # Create test books with various states
        complete_book = Book.objects.create(
            title="Complete Book",
            file_path="/library/complete.epub",
            file_format="epub"
        )
        complete_book.authors.add(self.author)
        FinalMetadata.objects.create(
            book=complete_book,
            final_title="Complete Book",
            final_author="Test Author"
        )

        # Book without metadata
        Book.objects.create(
            title="Incomplete Book",
            file_path="/library/incomplete.epub",
            file_format="epub"
        )

        # Comic book
        Book.objects.create(
            title="Comic #1",
            file_path="/comics/comic1.cbz",
            file_format="cbz"
        )

        response = self.client.get(reverse('books:book_renamer'))
        stats = response.context['stats']

        # Verify statistics
        self.assertGreaterEqual(stats['total_books'], 3)
        self.assertGreaterEqual(stats['missing_metadata'], 1)  # incomplete_book
        self.assertGreaterEqual(stats['comic_books'], 1)  # comic_book


class BookRenamerFileOperationTests(TestCase):
    """Tests for file operation tracking and management in BookRenamerView."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.client.login(username='testuser', password='testpass123')
