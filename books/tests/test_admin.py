"""
Tests for Django admin interface functionality.

This module tests the admin interface for all book-related models,
including superuser creation, admin views, and admin functionality.
"""
import os
import shutil
import tempfile

from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import User
from django.test import Client, TestCase

from books.admin import BookAdmin, BookAuthorAdmin
from books.models import Author, Book, BookAuthor, BookTitle, DataSource, Genre, Publisher, ScanFolder, Series
from books.tests.test_helpers import create_test_book_with_file


class AdminSetupTestCase(TestCase):
    """Test superuser creation and admin access."""

    def setUp(self):
        """Set up test client and create superuser."""
        self.client = Client()
        self.superuser = User.objects.create_superuser(
            username='admin',
            email='admin@test.com',
            password='testpass123'
        )

    def test_superuser_creation(self):
        """Test that superuser is created correctly."""
        self.assertTrue(self.superuser.is_superuser)
        self.assertTrue(self.superuser.is_staff)
        self.assertEqual(self.superuser.username, 'admin')
        self.assertEqual(self.superuser.email, 'admin@test.com')

    def test_admin_login(self):
        """Test that superuser can log into admin."""
        login_successful = self.client.login(username='admin', password='testpass123')
        self.assertTrue(login_successful)

    def test_admin_index_access(self):
        """Test that superuser can access admin index."""
        self.client.login(username='admin', password='testpass123')
        response = self.client.get('/admin/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Django administration')

    def test_admin_logout(self):
        """Test admin logout functionality."""
        self.client.login(username='admin', password='testpass123')
        # Use POST request for logout (Django requires POST for logout)
        response = self.client.post('/admin/logout/')
        self.assertEqual(response.status_code, 200)


class AdminModelAccessTestCase(TestCase):
    """Test admin access to all models."""

    def setUp(self):
        """Set up test data and superuser."""
        self.client = Client()
        self.superuser = User.objects.create_superuser(
            username='admin',
            email='admin@test.com',
            password='testpass123'
        )
        self.client.login(username='admin', password='testpass123')

        # Create temporary directory for testing
        self.temp_dir = tempfile.mkdtemp()

        # Create test data
        self.scan_folder = ScanFolder.objects.create(
            name="Test Folder",
            path=self.temp_dir,
            language="en"
        )

        self.book = create_test_book_with_file(
            file_path="/test/book.epub",
            file_format="epub",
            file_size=1024,
            scan_folder=self.scan_folder,
            content_type='ebook',
            title="Test Book"
        )

        self.author = Author.objects.create(
            first_name="John",
            last_name="Doe"
        )

        self.genre = Genre.objects.create(name="Fiction")
        self.series = Series.objects.create(name="Test Series")
        self.publisher = Publisher.objects.create(name="Test Publisher")
        self.data_source = DataSource.objects.create(
            name="Test Source",
            trust_level=0.8
        )

    def tearDown(self):
        """Clean up temporary directory."""
        if hasattr(self, 'temp_dir') and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_book_admin_access(self):
        """Test access to Book admin."""
        response = self.client.get('/admin/books/book/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Test Book')

    def test_author_admin_access(self):
        """Test access to Author admin."""
        response = self.client.get('/admin/books/author/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'John')

    def test_scanfolder_admin_access(self):
        """Test access to ScanFolder admin."""
        response = self.client.get('/admin/books/scanfolder/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Test Folder')

    def test_genre_admin_access(self):
        """Test access to Genre admin."""
        response = self.client.get('/admin/books/genre/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Fiction')

    def test_series_admin_access(self):
        """Test access to Series admin."""
        response = self.client.get('/admin/books/series/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Test Series')

    def test_publisher_admin_access(self):
        """Test access to Publisher admin."""
        response = self.client.get('/admin/books/publisher/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Test Publisher')

    def test_datasource_admin_access(self):
        """Test access to DataSource admin."""
        response = self.client.get('/admin/books/datasource/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Test Source')


class AdminModelDetailTestCase(TestCase):
    """Test admin detail views and forms."""

    def setUp(self):
        """Set up test data and superuser."""
        self.client = Client()
        self.superuser = User.objects.create_superuser(
            username='admin',
            email='admin@test.com',
            password='testpass123'
        )
        self.client.login(username='admin', password='testpass123')

        # Create temporary directory for testing
        self.temp_dir = tempfile.mkdtemp()

        self.scan_folder = ScanFolder.objects.create(
            name="Test Folder",
            path=self.temp_dir,
            language="en"
        )

        self.book = create_test_book_with_file(
            file_path="/test/book.epub",
            file_format="epub",
            file_size=1024,
            scan_folder=self.scan_folder,
            content_type='ebook',
            title="Test Book Admin Detail"
        )

    def tearDown(self):
        """Clean up temporary directory."""
        if hasattr(self, 'temp_dir') and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_book_detail_admin(self):
        """Test Book detail view in admin."""
        response = self.client.get(f'/admin/books/book/{self.book.id}/change/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'book.epub')
        self.assertContains(response, 'File Information')

    def test_book_add_admin(self):
        """Test Book add view in admin."""
        response = self.client.get('/admin/books/book/add/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'file_path')

    def test_scanfolder_detail_admin(self):
        """Test ScanFolder detail view in admin."""
        response = self.client.get(f'/admin/books/scanfolder/{self.scan_folder.id}/change/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Test Folder')


class AdminInlineTestCase(TestCase):
    """Test admin inline functionality."""

    def setUp(self):
        """Set up test data and superuser."""
        self.client = Client()
        self.superuser = User.objects.create_superuser(
            username='admin',
            email='admin@test.com',
            password='testpass123'
        )
        self.client.login(username='admin', password='testpass123')

        # Create temporary directory for testing
        self.temp_dir = tempfile.mkdtemp()

        self.scan_folder = ScanFolder.objects.create(
            name="Test Folder",
            path=self.temp_dir,
            language="en"
        )

        self.book = create_test_book_with_file(
            file_path="/test/book.epub",
            file_format="epub",
            file_size=1024,
            scan_folder=self.scan_folder,
            content_type='ebook',
            title="Test Book Inline"
        )

        self.author = Author.objects.create(
            first_name="John",
            last_name="Doe"
        )

        self.data_source = DataSource.objects.create(
            name="Test Source",
            trust_level=0.8
        )

        # Create related objects
        self.book_title = BookTitle.objects.create(
            book=self.book,
            title="Test Book",
            source=self.data_source,
            confidence=0.9
        )

        self.book_author = BookAuthor.objects.create(
            book=self.book,
            author=self.author,
            source=self.data_source,
            confidence=0.8
        )

    def tearDown(self):
        """Clean up temporary directory."""
        if hasattr(self, 'temp_dir') and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_book_inlines_display(self):
        """Test that book inlines display correctly."""
        response = self.client.get(f'/admin/books/book/{self.book.id}/change/')
        self.assertEqual(response.status_code, 200)

        # Check for inline sections (Django admin uses plural, spaced names)
        self.assertContains(response, 'Book titles')
        self.assertContains(response, 'Book authors')
        self.assertContains(response, 'Test Book')
        self.assertContains(response, 'John')


class AdminFilteringTestCase(TestCase):
    """Test admin filtering and search functionality."""

    def setUp(self):
        """Set up test data and superuser."""
        self.client = Client()
        self.superuser = User.objects.create_superuser(
            username='admin',
            email='admin@test.com',
            password='testpass123'
        )
        self.client.login(username='admin', password='testpass123')

        # Create temporary directory for testing
        self.temp_dir = tempfile.mkdtemp()

        self.scan_folder = ScanFolder.objects.create(
            name="Test Folder",
            path=self.temp_dir,
            language="en"
        )

        # Create multiple books with different formats
        self.book1 = create_test_book_with_file(
            file_path="/test/book1.epub",
            file_format="epub",
            file_size=1024,
            scan_folder=self.scan_folder,
            content_type='ebook',
            title="Book 1"
        )

        self.book2 = create_test_book_with_file(
            file_path="/test/book2.pdf",
            file_format="pdf",
            file_size=2048,
            scan_folder=self.scan_folder,
            content_type='ebook',
            title="Book 2"
        )

    def test_book_format_filtering(self):
        """Test filtering books by format."""
        response = self.client.get('/admin/books/book/?files__file_format=epub')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Book 1')
        self.assertNotContains(response, 'Book 2')

    def test_book_search(self):
        """Test searching books."""
        response = self.client.get('/admin/books/book/?q=Book 1')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Book 1')

    def tearDown(self):
        """Clean up temporary directory."""
        if hasattr(self, 'temp_dir') and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)


class AdminFunctionalityTestCase(TestCase):
    """Test admin-specific functionality like readonly fields."""

    def setUp(self):
        """Set up test data and superuser."""
        self.client = Client()
        self.superuser = User.objects.create_superuser(
            username='admin',
            email='admin@test.com',
            password='testpass123'
        )
        self.client.login(username='admin', password='testpass123')

        # Create temporary directory for testing
        self.temp_dir = tempfile.mkdtemp()

        self.scan_folder = ScanFolder.objects.create(
            name="Test Folder",
            path=self.temp_dir,
            language="en"
        )

        self.book = create_test_book_with_file(
            file_path="/test/book.epub",
            file_format="epub",
            file_size=1048576,  # 1MB
            scan_folder=self.scan_folder,
            content_type="ebook",
            title="Test Book"
        )

    def test_book_readonly_fields(self):
        """Test that readonly fields are displayed correctly."""
        response = self.client.get(f'/admin/books/book/{self.book.id}/change/')
        self.assertEqual(response.status_code, 200)

        # Check for readonly field displays
        self.assertContains(response, 'book.epub')  # filename should be readonly
        self.assertContains(response, '1.00 MB')    # file_size_mb should be calculated

    def test_datasource_admin_display(self):
        """Test DataSource admin display."""
        _ = DataSource.objects.create(
            name="Test Source",
            trust_level=0.85
        )

        response = self.client.get('/admin/books/datasource/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Test Source')
        self.assertContains(response, '0.85')

    def tearDown(self):
        """Clean up temporary directory."""
        if hasattr(self, 'temp_dir') and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)


class AdminPermissionTestCase(TestCase):
    """Test admin permissions and access control."""

    def setUp(self):
        """Set up test users with different permissions."""
        self.client = Client()

        # Create superuser
        self.superuser = User.objects.create_superuser(
            username='admin',
            email='admin@test.com',
            password='testpass123'
        )

        # Create regular user
        self.regular_user = User.objects.create_user(
            username='user',
            email='user@test.com',
            password='testpass123'
        )

        # Create staff user (but not superuser)
        self.staff_user = User.objects.create_user(
            username='staff',
            email='staff@test.com',
            password='testpass123',
            is_staff=True
        )

    def test_superuser_admin_access(self):
        """Test that superuser can access admin."""
        self.client.login(username='admin', password='testpass123')
        response = self.client.get('/admin/')
        self.assertEqual(response.status_code, 200)

    def test_regular_user_admin_denied(self):
        """Test that regular user cannot access admin."""
        self.client.login(username='user', password='testpass123')
        response = self.client.get('/admin/')
        self.assertEqual(response.status_code, 302)  # Redirect to login

    def test_staff_user_admin_access(self):
        """Test that staff user can access admin but with limited permissions."""
        self.client.login(username='staff', password='testpass123')
        response = self.client.get('/admin/')
        self.assertEqual(response.status_code, 200)


class AdminCustomMethodTestCase(TestCase):
    """Test custom admin methods and display functions."""

    def setUp(self):
        """Set up test data and admin instances."""
        self.site = AdminSite()

        # Create test data
        # Create temporary directory for testing
        self.temp_dir = tempfile.mkdtemp()

        self.scan_folder = ScanFolder.objects.create(
            name="Test Folder",
            path=self.temp_dir,
            language="en"
        )

        self.book = create_test_book_with_file(
            file_path="/test/book.epub",
            file_format="epub",
            file_size=1048576,  # 1MB
            scan_folder=self.scan_folder,
            content_type="ebook",
            title="Test Book"
        )

        self.author = Author.objects.create(
            name="John Doe",
            first_name="John",
            last_name="Doe"
        )

        self.data_source = DataSource.objects.create(
            name="Test Source",
            trust_level=0.8
        )

        self.book_author = BookAuthor.objects.create(
            book=self.book,
            author=self.author,
            source=self.data_source,
            confidence=0.9
        )

        # Create admin instances
        self.book_admin = BookAdmin(Book, self.site)
        self.book_author_admin = BookAuthorAdmin(BookAuthor, self.site)

    def test_book_admin_file_size_mb(self):
        """Test BookAdmin file_size_mb custom method."""
        result = self.book_admin.file_size_mb(self.book)
        self.assertEqual(result, "1.00 MB")

    def test_book_admin_file_size_mb_unknown(self):
        """Test BookAdmin file_size_mb with no file size."""
        book_no_size = create_test_book_with_file(
            file_path="/test/unknown.epub",
            file_format="epub",
            scan_folder=self.scan_folder,
            content_type="ebook",
            title="Unknown Size Book"
        )
        result = self.book_admin.file_size_mb(book_no_size)
        self.assertEqual(result, "Unknown")

    def test_book_author_admin_methods(self):
        """Test BookAuthorAdmin custom display methods."""
        full_name = self.book_author_admin.author_full_name(self.book_author)
        first_name = self.book_author_admin.author_first_name(self.book_author)
        last_name = self.book_author_admin.author_last_name(self.book_author)

        self.assertEqual(full_name, "John Doe")
        self.assertEqual(first_name, "John")
        self.assertEqual(last_name, "Doe")

    def tearDown(self):
        """Clean up temporary directory."""
        if hasattr(self, 'temp_dir') and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)


class AdminBulkActionsTestCase(TestCase):
    """Test admin bulk actions functionality."""

    def setUp(self):
        """Set up test data and superuser."""
        self.client = Client()
        self.superuser = User.objects.create_superuser(
            username='admin',
            email='admin@test.com',
            password='testpass123'
        )
        self.client.login(username='admin', password='testpass123')

        # Create temporary directory for testing
        self.temp_dir = tempfile.mkdtemp()

        self.scan_folder = ScanFolder.objects.create(
            name="Test Folder",
            path=self.temp_dir,
            language="en"
        )

        # Create multiple books for bulk testing
        self.books = []
        for i in range(3):
            book = create_test_book_with_file(
                file_path=f"/test/book{i}.epub",
                file_format="epub",
                file_size=1024,
                scan_folder=self.scan_folder,
                content_type="ebook",
                title=f"Test Book {i}"
            )
            self.books.append(book)

    def test_admin_bulk_delete_available(self):
        """Test that bulk delete action is available in admin."""
        response = self.client.get('/admin/books/book/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'action-select')  # Bulk action checkboxes
        self.assertContains(response, 'Delete selected')

    def tearDown(self):
        """Clean up temporary directory."""
        if hasattr(self, 'temp_dir') and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)


class AdminIntegrationTestCase(TestCase):
    """Integration tests for admin functionality."""

    def setUp(self):
        """Set up comprehensive test environment."""
        self.client = Client()
        self.superuser = User.objects.create_superuser(
            username='admin',
            email='admin@test.com',
            password='testpass123'
        )
        self.client.login(username='admin', password='testpass123')

        # Create temporary directory for testing
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up temporary directory."""
        if hasattr(self, 'temp_dir') and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_full_admin_workflow(self):
        """Test a complete admin workflow."""
        # 1. Access admin index
        response = self.client.get('/admin/')
        self.assertEqual(response.status_code, 200)

        # 2. Create a scan folder
        response = self.client.post('/admin/books/scanfolder/add/', {
            'name': 'Integration Test Folder',
            'path': self.temp_dir,
            'content_type': 'ebooks',
            'language': 'en',
            'is_active': True
        })
        self.assertEqual(response.status_code, 302)  # Redirect after successful creation

        # 3. Verify scan folder was created
        scan_folder = ScanFolder.objects.get(name='Integration Test Folder')
        self.assertEqual(scan_folder.path, self.temp_dir)

        # 4. Create a book through the model (testing admin functionality separately)
        book = create_test_book_with_file(
            file_path='/integration/test/book.epub',
            file_format='epub',
            file_size=1024,
            scan_folder=scan_folder,
            is_placeholder=False,
            is_duplicate=False,
            is_corrupted=False,
            content_type="ebook",
            title="Integration Test Book"
        )

        # 5. Verify book was created
        first_file = book.files.first()
        self.assertEqual(first_file.file_format, 'epub')
        self.assertEqual(book.scan_folder, scan_folder)

        # 6. Test admin view access for the created book
        response = self.client.get(f'/admin/books/book/{book.id}/change/')
        self.assertEqual(response.status_code, 200)

    def test_admin_model_relationships(self):
        """Test admin handling of model relationships."""
        # Create base objects
        # Create another temporary directory for this specific test
        temp_rel_dir = tempfile.mkdtemp()

        scan_folder = ScanFolder.objects.create(
            name="Relationship Test",
            path=temp_rel_dir,
            language="en"
        )

        book = create_test_book_with_file(
            file_path="/test/relationships/book.epub",
            file_format="epub",
            file_size=1024,
            scan_folder=scan_folder,
            content_type="ebook",
            title="Relationship Test Book"
        )

        # Test that admin shows relationships correctly
        response = self.client.get(f'/admin/books/book/{book.id}/change/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Relationship Test')  # Should show related scan folder

        # Clean up the temporary directory created for this test
        if os.path.exists(temp_rel_dir):
            shutil.rmtree(temp_rel_dir)
