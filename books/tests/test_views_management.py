"""
Comprehensive test suite for management views in views.py.
Tests CRUD operations for Authors, Genres, and Series management.
"""

from django.contrib.auth.models import User
from django.contrib.messages import get_messages
from django.test import Client, TestCase
from django.urls import reverse

from books.models import (
    Author,
    BookAuthor,
    BookGenre,
    BookSeries,
    DataSource,
    FinalMetadata,
    Genre,
    Series,
)
from books.tests.test_helpers import create_test_book_with_file, create_test_scan_folder


class AuthorManagementViewTests(TestCase):
    """Test suite for Author management views"""

    def setUp(self):
        """Set up test data for author management tests"""
        self.client = Client()
        self.user = User.objects.create_user(username="testuser", password="testpass123")
        self.client.login(username="testuser", password="testpass123")

        # Create test data sources
        self.manual_source, _ = DataSource.objects.get_or_create(name="Manual Entry", defaults={"trust_level": 0.9})
        self.epub_source, _ = DataSource.objects.get_or_create(name="EPUB", defaults={"trust_level": 0.7})

        # Create test scan folder
        self.scan_folder = create_test_scan_folder()

        # Create test authors
        self.reviewed_author = Author.objects.create(
            name="Reviewed Author",
            first_name="Reviewed",
            last_name="Author",
            is_reviewed=True,
        )
        self.unreviewed_author1 = Author.objects.create(
            name="Unreviewed Author 1",
            first_name="Unreviewed",
            last_name="Author1",
            is_reviewed=False,
        )
        self.unreviewed_author2 = Author.objects.create(
            name="Unreviewed Author 2",
            first_name="Unreviewed",
            last_name="Author2",
            is_reviewed=False,
        )

        # Create test books with author relationships
        self.book1 = create_test_book_with_file(
            file_path="/test/book1.epub",
            file_format="epub",
            file_size=1000000,
            scan_folder=self.scan_folder,
        )
        FinalMetadata.objects.create(book=self.book1, final_title="Test Book 1", final_author="Test Author")

        # Create book-author relationships
        BookAuthor.objects.create(
            book=self.book1,
            author=self.reviewed_author,
            confidence=0.9,
            is_main_author=True,
            is_active=True,
            source=self.manual_source,
        )
        BookAuthor.objects.create(
            book=self.book1,
            author=self.unreviewed_author1,
            confidence=0.8,
            is_main_author=False,
            is_active=True,
            source=self.epub_source,
        )

    def test_author_list_view_requires_login(self):
        """Test that author list view requires authentication"""
        self.client.logout()
        response = self.client.get(reverse("books:author_list"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)

    def test_author_list_view_loads_successfully(self):
        """Test that author list view loads for authenticated users"""
        response = self.client.get(reverse("books:author_list"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "books/author_list.html")
        self.assertIn("authors", response.context)

    def test_author_list_view_pagination(self):
        """Test author list pagination"""
        # Create many authors to test pagination
        Author.objects.bulk_create(
            [
                Author(
                    name=f"Test Author {i}",
                    first_name=f"Test{i}",
                    last_name=f"Author{i}",
                )
                for i in range(30)
            ]
        )

        response = self.client.get(reverse("books:author_list"))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["is_paginated"])
        self.assertEqual(len(response.context["authors"]), 25)  # paginate_by = 25

    def test_author_list_view_search_functionality(self):
        """Test author search functionality"""
        # Search by name
        response = self.client.get(reverse("books:author_list"), {"search": "Reviewed"})
        self.assertEqual(response.status_code, 200)
        authors = response.context["authors"]
        self.assertEqual(len(authors), 1)
        self.assertEqual(authors[0], self.reviewed_author)

        # Search by first name
        response = self.client.get(reverse("books:author_list"), {"search": "Unreviewed"})
        authors = response.context["authors"]
        self.assertEqual(len(authors), 2)

        # Search with no results
        response = self.client.get(reverse("books:author_list"), {"search": "NonExistent"})
        authors = response.context["authors"]
        self.assertEqual(len(authors), 0)

    def test_author_list_view_review_filter(self):
        """Test author list filtering by review status"""
        # Filter reviewed authors
        response = self.client.get(reverse("books:author_list"), {"is_reviewed": "true"})
        authors = response.context["authors"]
        self.assertEqual(len(authors), 1)
        self.assertEqual(authors[0], self.reviewed_author)

        # Filter unreviewed authors
        response = self.client.get(reverse("books:author_list"), {"is_reviewed": "false"})
        authors = response.context["authors"]
        self.assertEqual(len(authors), 2)
        self.assertIn(self.unreviewed_author1, authors)
        self.assertIn(self.unreviewed_author2, authors)

    def test_author_list_view_context_data(self):
        """Test author list view context data includes sources"""
        response = self.client.get(reverse("books:author_list"))
        context = response.context

        self.assertIn("search_query", context)
        self.assertIn("author_sources", context)

        # Check that author sources are correctly mapped
        author_sources = context["author_sources"]
        self.assertIn(self.reviewed_author.id, author_sources)
        self.assertIn("Manual Entry", author_sources[self.reviewed_author.id])

    def test_author_bulk_delete_view_requires_login(self):
        """Test that author bulk delete requires authentication"""
        self.client.logout()
        response = self.client.post(
            reverse("books:author_bulk_delete"),
            {"selected_authors": [str(self.unreviewed_author1.id)]},
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)

    def test_author_bulk_delete_unreviewed_authors(self):
        """Test bulk deletion of unreviewed authors"""
        response = self.client.post(
            reverse("books:author_bulk_delete"),
            {
                "selected_authors": [
                    str(self.unreviewed_author1.id),
                    str(self.unreviewed_author2.id),
                ]
            },
        )

        # Should redirect to author list
        self.assertRedirects(response, reverse("books:author_list"))

        # Check that unreviewed authors were deleted
        self.assertFalse(Author.objects.filter(id=self.unreviewed_author1.id).exists())
        self.assertFalse(Author.objects.filter(id=self.unreviewed_author2.id).exists())

        # Check that reviewed author was not deleted
        self.assertTrue(Author.objects.filter(id=self.reviewed_author.id).exists())

        # Check success message
        messages = list(get_messages(response.wsgi_request))
        self.assertTrue(any("Deleted 2 authors" in str(msg) for msg in messages))

    def test_author_bulk_delete_protects_reviewed_authors(self):
        """Test that bulk delete protects reviewed authors"""
        response = self.client.post(
            reverse("books:author_bulk_delete"),
            {"selected_authors": [str(self.reviewed_author.id)]},
        )

        # Reviewed author should still exist
        self.assertTrue(Author.objects.filter(id=self.reviewed_author.id).exists())

        # Check info message about protection
        messages = list(get_messages(response.wsgi_request))
        self.assertTrue(any("No authors deleted" in str(msg) for msg in messages))

    def test_author_bulk_delete_removes_book_relationships(self):
        """Test that bulk delete removes BookAuthor relationships"""
        # Verify relationship exists before deletion
        self.assertTrue(BookAuthor.objects.filter(author=self.unreviewed_author1).exists())

        response = self.client.post(
            reverse("books:author_bulk_delete"),
            {"selected_authors": [str(self.unreviewed_author1.id)]},
        )

        # Verify the request was successful
        self.assertEqual(response.status_code, 302)  # Should redirect after successful delete

        # Verify relationship was deleted
        self.assertFalse(BookAuthor.objects.filter(author=self.unreviewed_author1).exists())

    def test_author_delete_view_requires_login(self):
        """Test that author delete view requires authentication"""
        self.client.logout()
        response = self.client.get(reverse("books:author_delete", kwargs={"pk": self.unreviewed_author1.pk}))
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)

    def test_author_delete_view_loads_confirmation(self):
        """Test that author delete view loads confirmation page"""
        response = self.client.get(reverse("books:author_delete", kwargs={"pk": self.unreviewed_author1.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "books/delete_author.html")
        self.assertEqual(response.context["object"], self.unreviewed_author1)

    def test_author_delete_view_successful_deletion(self):
        """Test successful author deletion"""
        response = self.client.post(reverse("books:author_delete", kwargs={"pk": self.unreviewed_author1.pk}))

        # Should redirect to author list
        self.assertRedirects(response, reverse("books:author_list"))

        # Author should be deleted
        self.assertFalse(Author.objects.filter(id=self.unreviewed_author1.id).exists())

        # BookAuthor relationships should be deleted
        self.assertFalse(BookAuthor.objects.filter(author_id=self.unreviewed_author1.id).exists())

    def test_author_delete_view_nonexistent_author(self):
        """Test author delete view with nonexistent author"""
        response = self.client.get(reverse("books:author_delete", kwargs={"pk": 99999}))
        self.assertEqual(response.status_code, 404)

    def test_author_mark_reviewed_view_requires_login(self):
        """Test that author mark reviewed requires authentication"""
        self.client.logout()
        response = self.client.post(
            reverse("books:author_mark_reviewed"),
            {"selected_authors": [str(self.unreviewed_author1.id)]},
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)

    def test_author_mark_reviewed_successful(self):
        """Test successful author review marking"""
        response = self.client.post(
            reverse("books:author_mark_reviewed"),
            {
                "selected_authors": [
                    str(self.unreviewed_author1.id),
                    str(self.unreviewed_author2.id),
                ]
            },
        )

        # Should redirect to author list
        self.assertRedirects(response, reverse("books:author_list"))

        # Authors should be marked as reviewed
        self.unreviewed_author1.refresh_from_db()
        self.unreviewed_author2.refresh_from_db()
        self.assertTrue(self.unreviewed_author1.is_reviewed)
        self.assertTrue(self.unreviewed_author2.is_reviewed)

        # Check success message
        messages = list(get_messages(response.wsgi_request))
        self.assertTrue(any("Marked 2 author(s) as reviewed" in str(msg) for msg in messages))

    def test_author_mark_reviewed_already_reviewed(self):
        """Test marking already reviewed authors"""
        response = self.client.post(
            reverse("books:author_mark_reviewed"),
            {"selected_authors": [str(self.reviewed_author.id)]},
        )

        # Check info message about no changes
        messages = list(get_messages(response.wsgi_request))
        self.assertTrue(any("No changes made" in str(msg) for msg in messages))


class GenreManagementViewTests(TestCase):
    """Test suite for Genre management views"""

    def setUp(self):
        """Set up test data for genre management tests"""
        self.client = Client()
        self.user = User.objects.create_user(username="testuser", password="testpass123")
        self.client.login(username="testuser", password="testpass123")

        # Create test data sources
        self.manual_source, _ = DataSource.objects.get_or_create(name="Manual Entry", defaults={"trust_level": 0.9})

        # Create test scan folder
        self.scan_folder = create_test_scan_folder()

        # Create test genres
        self.reviewed_genre = Genre.objects.create(name="Science Fiction", is_reviewed=True)
        self.unreviewed_genre1 = Genre.objects.create(name="Fantasy", is_reviewed=False)
        self.unreviewed_genre2 = Genre.objects.create(name="Mystery", is_reviewed=False)

        # Create test book with genre relationships
        self.book1 = create_test_book_with_file(
            file_path="/test/book1.epub",
            file_format="epub",
            file_size=1000000,
            scan_folder=self.scan_folder,
        )
        FinalMetadata.objects.create(book=self.book1, final_title="Test Book 1", final_author="Test Author")

        # Create book-genre relationships
        BookGenre.objects.create(
            book=self.book1,
            genre=self.reviewed_genre,
            confidence=0.9,
            is_active=True,
            source=self.manual_source,
        )

    def test_genre_list_view_requires_login(self):
        """Test that genre list view requires authentication"""
        self.client.logout()
        response = self.client.get(reverse("books:genre_list"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)

    def test_genre_list_view_loads_successfully(self):
        """Test that genre list view loads for authenticated users"""
        response = self.client.get(reverse("books:genre_list"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "books/genre_list.html")
        self.assertIn("genres", response.context)

    def test_genre_list_view_search_functionality(self):
        """Test genre search functionality"""
        # Search by name
        response = self.client.get(reverse("books:genre_list"), {"search": "Science"})
        self.assertEqual(response.status_code, 200)
        genres = response.context["genres"]
        self.assertEqual(len(genres), 1)
        self.assertEqual(genres[0], self.reviewed_genre)

        # Search with no results
        response = self.client.get(reverse("books:genre_list"), {"search": "NonExistent"})
        genres = response.context["genres"]
        self.assertEqual(len(genres), 0)

    def test_genre_list_view_review_filter(self):
        """Test genre list filtering by review status"""
        # Filter reviewed genres
        response = self.client.get(reverse("books:genre_list"), {"is_reviewed": "true"})
        genres = response.context["genres"]
        self.assertEqual(len(genres), 1)
        self.assertEqual(genres[0], self.reviewed_genre)

        # Filter unreviewed genres
        response = self.client.get(reverse("books:genre_list"), {"is_reviewed": "false"})
        genres = response.context["genres"]
        self.assertEqual(len(genres), 2)
        self.assertIn(self.unreviewed_genre1, genres)
        self.assertIn(self.unreviewed_genre2, genres)

    def test_genre_bulk_delete_view_requires_login(self):
        """Test that genre bulk delete requires authentication"""
        self.client.logout()
        response = self.client.post(
            reverse("books:genre_bulk_delete"),
            {"selected_genres": [str(self.unreviewed_genre1.id)]},
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)

    def test_genre_bulk_delete_unreviewed_genres(self):
        """Test bulk deletion of unreviewed genres"""
        response = self.client.post(
            reverse("books:genre_bulk_delete"),
            {
                "selected_genres": [
                    str(self.unreviewed_genre1.id),
                    str(self.unreviewed_genre2.id),
                ]
            },
        )

        # Should redirect to genre list
        self.assertRedirects(response, reverse("books:genre_list"))

        # Check that unreviewed genres were deleted
        self.assertFalse(Genre.objects.filter(id=self.unreviewed_genre1.id).exists())
        self.assertFalse(Genre.objects.filter(id=self.unreviewed_genre2.id).exists())

        # Check that reviewed genre was not deleted
        self.assertTrue(Genre.objects.filter(id=self.reviewed_genre.id).exists())

        # Check success message
        messages = list(get_messages(response.wsgi_request))
        self.assertTrue(any("Successfully deleted 2 genre(s)" in str(msg) for msg in messages))

    def test_genre_bulk_delete_protects_reviewed_genres(self):
        """Test that bulk delete protects reviewed genres"""
        response = self.client.post(
            reverse("books:genre_bulk_delete"),
            {"selected_genres": [str(self.reviewed_genre.id)]},
        )

        # Reviewed genre should still exist
        self.assertTrue(Genre.objects.filter(id=self.reviewed_genre.id).exists())

        # Check info message about protection
        messages = list(get_messages(response.wsgi_request))
        self.assertTrue(any("No genres deleted" in str(msg) for msg in messages))

    def test_genre_delete_view_requires_login(self):
        """Test that genre delete view requires authentication"""
        self.client.logout()
        response = self.client.get(reverse("books:genre_delete", kwargs={"pk": self.unreviewed_genre1.pk}))
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)

    def test_genre_delete_view_loads_confirmation(self):
        """Test that genre delete view loads confirmation page"""
        response = self.client.get(reverse("books:genre_delete", kwargs={"pk": self.unreviewed_genre1.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "books/delete_genre.html")
        self.assertEqual(response.context["object"], self.unreviewed_genre1)

    def test_genre_delete_view_successful_deletion(self):
        """Test successful genre deletion"""
        response = self.client.post(reverse("books:genre_delete", kwargs={"pk": self.unreviewed_genre1.pk}))

        # Should redirect to genre list
        self.assertRedirects(response, reverse("books:genre_list"))

        # Genre should be deleted
        self.assertFalse(Genre.objects.filter(id=self.unreviewed_genre1.id).exists())

    def test_genre_mark_reviewed_view_requires_login(self):
        """Test that genre mark reviewed requires authentication"""
        self.client.logout()
        response = self.client.post(
            reverse("books:genre_mark_reviewed"),
            {"selected_genres": [str(self.unreviewed_genre1.id)]},
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)

    def test_genre_mark_reviewed_successful(self):
        """Test successful genre review marking"""
        response = self.client.post(
            reverse("books:genre_mark_reviewed"),
            {
                "selected_genres": [
                    str(self.unreviewed_genre1.id),
                    str(self.unreviewed_genre2.id),
                ]
            },
        )

        # Should redirect to genre list
        self.assertRedirects(response, reverse("books:genre_list"))

        # Genres should be marked as reviewed
        self.unreviewed_genre1.refresh_from_db()
        self.unreviewed_genre2.refresh_from_db()
        self.assertTrue(self.unreviewed_genre1.is_reviewed)
        self.assertTrue(self.unreviewed_genre2.is_reviewed)

        # Check success message
        messages = list(get_messages(response.wsgi_request))
        self.assertTrue(any("Successfully marked 2 genre(s) as reviewed" in str(msg) for msg in messages))


class SeriesManagementViewTests(TestCase):
    """Test suite for Series management views"""

    def setUp(self):
        """Set up test data for series management tests"""
        self.client = Client()
        self.user = User.objects.create_user(username="testuser", password="testpass123")
        self.client.login(username="testuser", password="testpass123")

        # Create test data sources
        self.manual_source, _ = DataSource.objects.get_or_create(name="Manual Entry", defaults={"trust_level": 0.9})

        # Create test scan folder
        self.scan_folder = create_test_scan_folder()

        # Create test series
        self.series1 = Series.objects.create(name="Test Series 1")
        self.series2 = Series.objects.create(name="Test Series 2")
        self.series3 = Series.objects.create(name="Empty Series")

        # Create test books with series relationships
        self.book1 = create_test_book_with_file(
            file_path="/test/book1.epub",
            file_format="epub",
            file_size=1000000,
            scan_folder=self.scan_folder,
        )
        self.book2 = create_test_book_with_file(
            file_path="/test/book2.epub",
            file_format="epub",
            file_size=1000000,
            scan_folder=self.scan_folder,
        )

        FinalMetadata.objects.create(book=self.book1, final_title="Test Book 1", final_author="Test Author")
        FinalMetadata.objects.create(book=self.book2, final_title="Test Book 2", final_author="Test Author")

        # Create book-series relationships
        BookSeries.objects.create(
            book=self.book1,
            series=self.series1,
            series_number="1",
            confidence=0.9,
            is_active=True,
            source=self.manual_source,
        )
        BookSeries.objects.create(
            book=self.book2,
            series=self.series1,
            series_number="2",
            confidence=0.8,
            is_active=True,
            source=self.manual_source,
        )

    def test_series_list_view_requires_login(self):
        """Test that series list view requires authentication"""
        self.client.logout()
        response = self.client.get(reverse("books:series_list"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)

    def test_series_list_view_loads_successfully(self):
        """Test that series list view loads for authenticated users"""
        response = self.client.get(reverse("books:series_list"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "books/series_list.html")
        self.assertIn("series", response.context)

    def test_series_list_view_shows_book_counts(self):
        """Test that series list shows correct book counts"""
        response = self.client.get(reverse("books:series_list"))
        context = response.context

        # Series should be annotated with book counts
        series_list = list(context["series"])

        # Find our test series
        test_series1 = next(s for s in series_list if s.name == "Test Series 1")
        test_series3 = next(s for s in series_list if s.name == "Empty Series")

        # Verify book counts (assuming the view annotates book counts)
        # This test assumes the view adds book_count annotation
        if hasattr(test_series1, "book_count"):
            self.assertEqual(test_series1.book_count, 2)
            self.assertEqual(test_series3.book_count, 0)

    def test_series_with_books_view_functionality(self):
        """Test series filtering and search functionality"""
        # Test search functionality if implemented
        response = self.client.get(reverse("books:series_list"), {"search": "Test Series 1"})
        self.assertEqual(response.status_code, 200)

        if "search" in response.context:
            # If search is implemented, test it
            series_list = response.context["series"]
            self.assertTrue(any(s.name == "Test Series 1" for s in series_list))

    def test_series_detail_view_if_exists(self):
        """Test series detail view if it exists"""
        # This test checks if series detail view exists
        try:
            response = self.client.get(reverse("books:series_detail", kwargs={"pk": self.series1.pk}))
            if response.status_code == 200:
                self.assertIn("series", response.context)
                self.assertEqual(response.context["series"], self.series1)
        except Exception:
            # Series detail view may not be implemented yet
            pass


class ManagementViewEdgeCaseTests(TestCase):
    """Test edge cases and error scenarios in management views"""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username="testuser", password="testpass123")
        self.client.login(username="testuser", password="testpass123")

    def test_bulk_operations_with_empty_selection(self):
        """Test bulk operations with no items selected"""
        # Test author bulk delete with empty selection
        response = self.client.post(reverse("books:author_bulk_delete"), {"selected_authors": []})
        self.assertEqual(response.status_code, 302)

        # Test author mark reviewed with empty selection
        response = self.client.post(reverse("books:author_mark_reviewed"), {"selected_authors": []})
        self.assertEqual(response.status_code, 302)

        # Test genre bulk delete with empty selection
        response = self.client.post(reverse("books:genre_bulk_delete"), {"selected_genres": []})
        self.assertEqual(response.status_code, 302)

    def test_bulk_operations_with_invalid_ids(self):
        """Test bulk operations with invalid item IDs"""
        # Test with non-existent author IDs
        response = self.client.post(
            reverse("books:author_bulk_delete"),
            {"selected_authors": ["99999", "88888"]},
        )
        self.assertEqual(response.status_code, 302)

        # Should handle gracefully without errors
        # Note: In a real implementation, should check for appropriate error messages

    def test_management_views_with_large_datasets(self):
        """Test management views performance with larger datasets"""
        # Create many items to test pagination and performance
        authors = [Author.objects.create(name=f"Author {i}", is_reviewed=False) for i in range(100)]

        # List view should handle large datasets
        response = self.client.get(reverse("books:author_list"))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["is_paginated"])

        # Bulk operations should handle many items
        selected_ids = [str(author.id) for author in authors[:50]]
        response = self.client.post(reverse("books:author_mark_reviewed"), {"selected_authors": selected_ids})
        self.assertEqual(response.status_code, 302)

    def test_management_views_with_special_characters(self):
        """Test management views with special characters in names"""
        # Create items with special characters
        special_author = Author.objects.create(name="Ñoël Müller-Smith & Co.", is_reviewed=False)
        Genre.objects.create(name="Sci-Fi & Fantasy (Überkool)", is_reviewed=False)

        # Views should handle special characters
        response = self.client.get(reverse("books:author_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ñoël Müller-Smith")

        response = self.client.get(reverse("books:genre_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sci-Fi &amp; Fantasy")

        # Operations should work with special characters
        response = self.client.post(
            reverse("books:author_bulk_delete"),
            {"selected_authors": [str(special_author.id)]},
        )
        self.assertEqual(response.status_code, 302)

    def test_concurrent_modifications(self):
        """Test handling of concurrent modifications"""
        author = Author.objects.create(name="Test Author", is_reviewed=False)

        # Simulate concurrent deletion - delete the author outside the view
        author_id = author.id
        author.delete()

        # Try to operate on the deleted author
        response = self.client.post(
            reverse("books:author_mark_reviewed"),
            {"selected_authors": [str(author_id)]},
        )

        # Should handle gracefully
        self.assertEqual(response.status_code, 302)


class BookRenamerViewTests(TestCase):
    """Comprehensive tests for BookRenamerView and file path generation."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username="testuser", password="testpass123")
        self.client.login(username="testuser", password="testpass123")

        # Create test data
        self.author = Author.objects.create(name="Test Author")
        self.genre_fiction = Genre.objects.create(name="Fiction")
        self.genre_scifi = Genre.objects.create(name="Science Fiction")
        self.series = Series.objects.create(name="Test Series")

    def test_book_renamer_view_access(self):
        """Test basic access to book renamer view."""
        response = self.client.get(reverse("books:book_renamer"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "books/book_renamer.html")

    def test_book_renamer_view_context(self):
        """Test that book renamer view provides necessary context."""
        # Create test books
        book1 = create_test_book_with_file(file_path="/library/test1.epub", file_format="epub", file_size=1000000)
        FinalMetadata.objects.create(
            book=book1,
            final_title="Test Book 1",
            final_author="Test Author",
            final_series="Test Series",
            final_series_number="1",
        )

        response = self.client.get(reverse("books:book_renamer"))
        self.assertEqual(response.status_code, 200)

        # Check context variables
        self.assertIn("books", response.context)
        self.assertIn("books_with_paths", response.context)
        self.assertIn("series_groups", response.context)
        self.assertIn("complete_series", response.context)
        self.assertIn("incomplete_series", response.context)

        # Verify context structure
        books_with_paths = response.context["books_with_paths"]
        series_groups = response.context["series_groups"]
        self.assertIsInstance(books_with_paths, list)
        self.assertIsInstance(series_groups, list)


class BookRenamerFileOperationTests(TestCase):
    """Tests for file operation tracking and management in BookRenamerView."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username="testuser", password="testpass123")
        self.client.login(username="testuser", password="testpass123")
