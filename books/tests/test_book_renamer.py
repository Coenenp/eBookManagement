"""
Test cases for Book Renamer functionality
"""

import json
import os
import shutil
import tempfile
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from books.models import FileOperation, FinalMetadata
from books.tests.test_helpers import create_test_book_with_file, create_test_scan_folder


class BookRenamerViewTests(TestCase):
    """Test cases for Book Renamer View"""

    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass123")
        self.client = Client()
        self.client.force_login(self.user)

        # Create temporary directory for scan folder
        self.temp_dir = tempfile.mkdtemp()
        self.scan_folder = create_test_scan_folder(self.temp_dir, "Test Scan Folder")

        # Create test book with new architecture
        self.book = create_test_book_with_file(
            file_path=os.path.join(self.temp_dir, "book.epub"), file_format="epub", file_size=1024000, scan_folder=self.scan_folder, title="Test Book"
        )

        # Create final metadata with series information
        self.final_metadata = FinalMetadata.objects.create(
            book=self.book, final_title="Test Book", final_author="Test Author", final_series="Test Series", final_series_number="1", is_reviewed=True  # Test string series number
        )

    def tearDown(self):
        """Clean up temporary directory"""
        if hasattr(self, "temp_dir") and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_book_renamer_view_loads(self):
        """Test that book renamer view loads successfully"""
        response = self.client.get(reverse("books:book_renamer"))
        self.assertEqual(response.status_code, 200)

    def test_book_renamer_context_data(self):
        """Test context data includes necessary information"""
        response = self.client.get(reverse("books:book_renamer"))
        self.assertEqual(response.status_code, 200)

        # Check context variables - the view provides books_with_previews, not books_with_paths
        self.assertIn("books_with_previews", response.context)
        self.assertIn("predefined_patterns", response.context)
        self.assertIn("available_tokens", response.context)

    def test_series_analysis_with_null_series_number(self):
        """Test series analysis handles null series numbers correctly"""
        # Create book with null series number
        book_null = create_test_book_with_file(
            file_path=os.path.join(self.temp_dir, "book_null.epub"), file_format="epub", file_size=1024000, scan_folder=self.scan_folder, title="Test Book Null"
        )

        FinalMetadata.objects.create(
            book=book_null, final_title="Test Book Null", final_author="Test Author", final_series="Test Series", final_series_number=None, is_reviewed=True  # NULL value
        )

        response = self.client.get(reverse("books:book_renamer"))
        self.assertEqual(response.status_code, 200)

    def test_series_analysis_with_empty_series_number(self):
        """Test series analysis handles empty string series numbers correctly"""
        # Create book with empty series number
        book_empty = create_test_book_with_file(
            file_path=os.path.join(self.temp_dir, "book_empty.epub"), file_format="epub", file_size=1024000, scan_folder=self.scan_folder, title="Test Book Empty"
        )

        FinalMetadata.objects.create(
            book=book_empty, final_title="Test Book Empty", final_author="Test Author", final_series="Test Series", final_series_number="", is_reviewed=True  # Empty string
        )

        response = self.client.get(reverse("books:book_renamer"))
        self.assertEqual(response.status_code, 200)

    def test_new_file_path_generation(self):
        """Test that new file paths are generated correctly"""
        response = self.client.get(reverse("books:book_renamer"))
        self.assertEqual(response.status_code, 200)

        books_with_previews = response.context["books_with_previews"]
        self.assertTrue(len(books_with_previews) > 0)

        book_data = books_with_previews[0]
        self.assertIn("new_path", book_data)
        self.assertIn("current_path", book_data)
        self.assertNotEqual(book_data["new_path"], book_data["current_path"])

    def test_warnings_generation(self):
        """Test that warnings are generated for problematic books"""
        # Create book with missing author
        book_missing_author = create_test_book_with_file(
            file_path=os.path.join(self.temp_dir, "missing_author.epub"), file_format="epub", file_size=1024000, scan_folder=self.scan_folder, title="Test Book Missing Author"
        )

        FinalMetadata.objects.create(book=book_missing_author, final_title="Test Book Missing Author", final_author="", is_reviewed=True)  # Missing author

        response = self.client.get(reverse("books:book_renamer"))
        self.assertEqual(response.status_code, 200)

        books_with_previews = response.context["books_with_previews"]

        # Find the book with missing author
        missing_author_book = None
        for book_data in books_with_previews:
            if book_data["book"].id == book_missing_author.id:
                missing_author_book = book_data
                break

        self.assertIsNotNone(missing_author_book)
        self.assertTrue(len(missing_author_book["warnings"]) > 0)


class BookRenamerFileDetailsViewTests(TestCase):
    """Test cases for BookRenamerFileDetailsView"""

    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass123")
        self.client = Client()
        self.client.force_login(self.user)

        # Create temporary directory for testing
        self.temp_dir = tempfile.mkdtemp()
        self.scan_folder = create_test_scan_folder(self.temp_dir, "Test Scan Folder")

        # Create test files
        self.test_book_path = os.path.join(self.temp_dir, "test_book.epub")
        self.test_opf_path = os.path.join(self.temp_dir, "test_book.opf")
        self.test_cover_path = os.path.join(self.temp_dir, "test_book.jpg")
        self.test_txt_path = os.path.join(self.temp_dir, "test_book.txt")

        # Create actual files
        for path in [self.test_book_path, self.test_opf_path, self.test_cover_path, self.test_txt_path]:
            with open(path, "w") as f:
                f.write("test content")

        from books.tests.test_helpers import create_test_book_with_file

        self.book = create_test_book_with_file(file_path=self.test_book_path, file_format="epub", file_size=1024000, scan_folder=self.scan_folder, content_type="ebook")

        self.final_metadata = FinalMetadata.objects.create(book=self.book, final_title="Test Book", final_author="Test Author", is_reviewed=True)

    def tearDown(self):
        """Clean up test files"""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_file_details_view_requires_login(self):
        """Test that file details view requires authentication"""
        self.client.logout()
        response = self.client.post(reverse("books:book_renamer_file_details"), {"book_id": self.book.id})
        self.assertIn(response.status_code, [302, 401, 403])

    def test_file_details_view_missing_book_id(self):
        """Test file details view with missing book ID"""
        response = self.client.post(reverse("books:book_renamer_file_details"))
        self.assertEqual(response.status_code, 400)

    def test_file_details_view_nonexistent_book(self):
        """Test file details view with nonexistent book"""
        response = self.client.post(reverse("books:book_renamer_file_details"), {"book_id": 99999})
        # Accept either 404 or 500, both are reasonable for non-existent book
        self.assertIn(response.status_code, [404, 500])

    def test_file_details_view_success(self):
        """Test successful file details retrieval"""
        response = self.client.post(reverse("books:book_renamer_file_details"), {"book_id": self.book.id})
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertTrue(data["success"])
        self.assertIn("current_path", data)
        self.assertIn("new_path", data)
        self.assertIn("automatic_files", data)
        self.assertIn("optional_files", data)
        self.assertIn("book_info", data)

    def test_file_details_automatic_files_detection(self):
        """Test automatic files are correctly detected and categorized"""
        response = self.client.post(reverse("books:book_renamer_file_details"), {"book_id": self.book.id})
        self.assertEqual(response.status_code, 200)

        data = response.json()
        automatic_files = data["automatic_files"]

        # Should detect .opf and .jpg files as automatic
        opf_found = any(f["type"] == "opf" for f in automatic_files)
        jpg_found = any(f["type"] == "jpg" for f in automatic_files)

        self.assertTrue(opf_found)
        self.assertTrue(jpg_found)

    def test_file_details_optional_files_detection(self):
        """Test optional files are correctly detected and categorized"""
        response = self.client.post(reverse("books:book_renamer_file_details"), {"book_id": self.book.id})
        self.assertEqual(response.status_code, 200)

        data = response.json()
        optional_files = data["optional_files"]

        # Should detect .txt file as optional
        txt_found = any(f["type"] == "txt" for f in optional_files)
        self.assertTrue(txt_found)

    def test_file_details_file_information(self):
        """Test that file information includes all necessary details"""
        response = self.client.post(reverse("books:book_renamer_file_details"), {"book_id": self.book.id})
        self.assertEqual(response.status_code, 200)

        data = response.json()
        all_files = data["automatic_files"] + data["optional_files"]

        for file_info in all_files:
            self.assertIn("original", file_info)
            self.assertIn("original_name", file_info)
            self.assertIn("new", file_info)
            self.assertIn("new_name", file_info)
            self.assertIn("type", file_info)
            self.assertIn("extension", file_info)
            self.assertIn("size", file_info)
            self.assertIn("size_formatted", file_info)
            self.assertIn("description", file_info)

    def test_file_details_missing_file(self):
        """Test file details view when original file doesn't exist"""
        # Create book with non-existent file
        missing_book = create_test_book_with_file(
            file_path="/nonexistent/path/book.epub", file_format="epub", file_size=1024000, scan_folder=self.scan_folder, title="Missing Book"
        )

        FinalMetadata.objects.create(book=missing_book, final_title="Missing Book", final_author="Test Author", is_reviewed=True)

        response = self.client.post(reverse("books:book_renamer_file_details"), {"book_id": missing_book.id})
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertIn("error", data)


class BookRenamerExecuteViewTests(TestCase):
    """Test cases for BookRenamerExecuteView"""

    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass123")
        self.client = Client()
        self.client.force_login(self.user)

        # Create temporary directory for testing
        self.temp_dir = tempfile.mkdtemp()
        self.scan_folder = create_test_scan_folder(self.temp_dir, "Test Scan Folder")

        # Create test files
        self.test_book_path = os.path.join(self.temp_dir, "test_book.epub")
        self.test_opf_path = os.path.join(self.temp_dir, "test_book.opf")
        self.test_cover_path = os.path.join(self.temp_dir, "test_book.jpg")
        self.test_txt_path = os.path.join(self.temp_dir, "test_book.txt")

        # Create actual files
        for path in [self.test_book_path, self.test_opf_path, self.test_cover_path, self.test_txt_path]:
            with open(path, "w") as f:
                f.write("test content")

        self.book = create_test_book_with_file(file_path=self.test_book_path, file_format="epub", file_size=1024000, scan_folder=self.scan_folder, title="Test Book")

        self.final_metadata = FinalMetadata.objects.create(book=self.book, final_title="Test Book", final_author="Test Author", is_reviewed=True)

    def tearDown(self):
        """Clean up test files"""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_execute_view_requires_login(self):
        """Test that execute view requires authentication"""
        self.client.logout()
        response = self.client.post(reverse("books:book_renamer_execute"), {"selected_books": [self.book.id]})
        self.assertIn(response.status_code, [302, 401, 403])

    def test_execute_view_no_books_selected(self):
        """Test execute view with no books selected"""
        response = self.client.post(reverse("books:book_renamer_execute"))
        self.assertEqual(response.status_code, 400)

    @patch("books.views.BookRenamerExecuteView._rename_book_files")
    def test_execute_view_success(self, mock_rename):
        """Test successful execution of book renaming"""
        mock_rename.return_value = {
            "new_path": "/new/path/book.epub",
            "new_cover_path": "/new/path/book.jpg",
            "new_opf_path": "/new/path/book.opf",
            "additional_files": [],
            "automatic_files": [],
            "optional_files": [],
        }

        response = self.client.post(reverse("books:book_renamer_execute"), {"selected_books": [self.book.id]})
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertEqual(data["total"], 1)
        self.assertTrue(len(data["success"]) > 0 or len(data["warnings"]) > 0)

    def test_execute_view_with_file_actions(self):
        """Test execute view with file actions for optional files"""
        file_actions = [{"index": 0, "action": "rename"}, {"index": 1, "action": "delete"}, {"index": 2, "action": "skip"}]

        with patch("books.views.BookRenamerExecuteView._rename_book_files") as mock_rename:
            mock_rename.return_value = {"new_path": "/new/path/book.epub", "additional_files": []}

            response = self.client.post(reverse("books:book_renamer_execute"), {"selected_books": [self.book.id], "file_actions": json.dumps(file_actions)})
            self.assertEqual(response.status_code, 200)

            # Verify file actions were passed to rename function
            mock_rename.assert_called()
            call_args = mock_rename.call_args
            self.assertEqual(call_args[0][2], file_actions)  # Third argument should be file_actions

    def test_execute_view_creates_file_operation(self):
        """Test that file operations are created for tracking"""
        with patch("books.views.BookRenamerExecuteView._rename_book_files") as mock_rename:
            mock_rename.return_value = {"new_path": "/new/path/book.epub", "additional_files": []}

            response = self.client.post(reverse("books:book_renamer_execute"), {"selected_books": [self.book.id]})
            self.assertEqual(response.status_code, 200)

            # Check that FileOperation was created
            file_ops = FileOperation.objects.filter(book=self.book)
            self.assertTrue(file_ops.exists())

            file_op = file_ops.first()
            self.assertEqual(file_op.operation_type, "rename")
            self.assertEqual(file_op.user, self.user)

    @patch("books.views.BookRenamerExecuteView._rename_book_files")
    def test_execute_view_handles_errors(self, mock_rename):
        """Test execute view handles errors gracefully"""
        mock_rename.side_effect = Exception("Test error")

        response = self.client.post(reverse("books:book_renamer_execute"), {"selected_books": [self.book.id]})
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertEqual(data["total"], 1)
        self.assertTrue(len(data["errors"]) > 0)

    def test_get_file_action_method(self):
        """Test _get_file_action method works correctly"""
        from books.views import BookRenamerExecuteView

        view = BookRenamerExecuteView()

        file_actions = [{"index": 0, "action": "rename"}, {"index": 1, "action": "delete"}, {"index": 2, "action": "skip"}]

        # Test existing actions
        self.assertEqual(view._get_file_action(0, file_actions), "rename")
        self.assertEqual(view._get_file_action(1, file_actions), "delete")
        self.assertEqual(view._get_file_action(2, file_actions), "skip")

        # Test non-existent index (should default to 'rename')
        self.assertEqual(view._get_file_action(99, file_actions), "rename")

        # Test empty file_actions (should default to 'rename')
        self.assertEqual(view._get_file_action(0, []), "rename")
        self.assertEqual(view._get_file_action(0, None), "rename")


class FinalMetadataSeriesNumberTests(TestCase):
    """Test cases for final_series_number null handling"""

    def setUp(self):
        """Set up test data"""
        # Create temporary directory for testing
        self.temp_dir = tempfile.mkdtemp()
        self.scan_folder = create_test_scan_folder(self.temp_dir, "Test Scan Folder")

        self.book = create_test_book_with_file(
            file_path=os.path.join(self.temp_dir, "book.epub"), file_format="epub", file_size=1024000, scan_folder=self.scan_folder, title="Test Book"
        )

    def tearDown(self):
        """Clean up temporary directory"""
        if hasattr(self, "temp_dir") and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_final_series_number_can_be_null(self):
        """Test that final_series_number field can be null"""
        final_metadata = FinalMetadata.objects.create(
            book=self.book,
            final_title="Test Book",
            final_author="Test Author",
            final_series="Test Series",
            final_series_number=None,  # Should not raise IntegrityError
            is_reviewed=True,
        )

        self.assertIsNone(final_metadata.final_series_number)
        final_metadata.refresh_from_db()
        self.assertIsNone(final_metadata.final_series_number)

    def test_final_series_number_can_be_empty_string(self):
        """Test that final_series_number field can be empty string"""
        final_metadata = FinalMetadata.objects.create(
            book=self.book, final_title="Test Book", final_author="Test Author", final_series="Test Series", final_series_number="", is_reviewed=True  # Empty string
        )

        self.assertEqual(final_metadata.final_series_number, "")
        final_metadata.refresh_from_db()
        self.assertEqual(final_metadata.final_series_number, "")

    def test_final_series_number_with_valid_string(self):
        """Test that final_series_number field works with valid strings"""
        final_metadata = FinalMetadata.objects.create(
            book=self.book, final_title="Test Book", final_author="Test Author", final_series="Test Series", final_series_number="1.5", is_reviewed=True  # Valid series number
        )

        self.assertEqual(final_metadata.final_series_number, "1.5")

    def test_series_analysis_with_null_series_number(self):
        """Test that series analysis methods handle None values correctly"""
        final_metadata = FinalMetadata.objects.create(
            book=self.book, final_title="Test Book", final_author="Test Author", final_series="Test Series", final_series_number=None, is_reviewed=True
        )

        # Verify the metadata was created with null series number
        self.assertIsNone(final_metadata.final_series_number)

        # Test that this doesn't cause errors in series analysis
        from books.views import BookRenamerView

        view = BookRenamerView()

        try:
            series_analysis = view._analyze_series_completion()
            # Should not raise an exception
            self.assertIsInstance(series_analysis, dict)
        except Exception as e:
            self.fail(f"Series analysis failed with None series number: {e}")

    def test_update_final_series_method_handles_none(self):
        """Test that update_final_series method handles None values correctly"""
        final_metadata = FinalMetadata.objects.create(
            book=self.book, final_title="Test Book", final_author="Test Author", final_series=None, final_series_number=None, is_reviewed=True
        )

        # This should not raise an error
        try:
            final_metadata.update_final_series()
            final_metadata.save()  # Save changes to database
            final_metadata.refresh_from_db()
            # Should default to empty string when no series data exists
            self.assertEqual(final_metadata.final_series, "")
            self.assertEqual(final_metadata.final_series_number, "")
        except Exception as e:
            self.fail(f"update_final_series failed with None values: {e}")


class FileHandlingEdgeCaseTests(TestCase):
    """Test edge cases in file handling functionality"""

    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass123")
        self.client = Client()
        self.client.force_login(self.user)

        # Create temporary directory for testing
        self.temp_dir = tempfile.mkdtemp()
        self.scan_folder = create_test_scan_folder(self.temp_dir, "Test Scan Folder")

    def tearDown(self):
        """Clean up temporary directory"""
        if hasattr(self, "temp_dir") and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_file_description_method(self):
        """Test _get_file_description method returns appropriate descriptions"""
        from books.views import BookRenamerExecuteView

        view = BookRenamerExecuteView()

        # Test known extensions
        self.assertEqual(view._get_file_description(".opf", "/path/book.opf"), "eBook metadata file (OPF)")
        self.assertEqual(view._get_file_description(".jpg", "/path/book.jpg"), "Book cover image (JPEG)")
        self.assertEqual(view._get_file_description(".txt", "/path/book.txt"), "Text file (may contain author info, synopsis, etc.)")

        # Test unknown extension
        description = view._get_file_description(".xyz", "/path/book.xyz")
        self.assertEqual(description, "XYZ file")

    def test_file_size_formatting(self):
        """Test _format_file_size method formats sizes correctly"""
        from books.views import BookRenamerFileDetailsView

        view = BookRenamerFileDetailsView()

        # Test various file sizes
        self.assertEqual(view._format_file_size(500), "500.0 B")
        self.assertEqual(view._format_file_size(1536), "1.5 KB")  # 1.5 * 1024
        self.assertEqual(view._format_file_size(1572864), "1.5 MB")  # 1.5 * 1024 * 1024
        self.assertEqual(view._format_file_size(1610612736), "1.5 GB")  # 1.5 * 1024^3

    def test_file_actions_json_parsing(self):
        """Test that malformed JSON in file_actions is handled gracefully"""
        book = create_test_book_with_file(
            file_path=os.path.join(self.temp_dir, "book.epub"), file_format="epub", file_size=1024000, scan_folder=self.scan_folder, title="Test Book"
        )

        FinalMetadata.objects.create(book=book, final_title="Test Book", final_author="Test Author", is_reviewed=True)

        with patch("books.views.BookRenamerExecuteView._rename_book_files") as mock_rename:
            mock_rename.return_value = {"new_path": "/new/path/book.epub", "additional_files": []}

            # Test with malformed JSON
            response = self.client.post(reverse("books:book_renamer_execute"), {"selected_books": [book.id], "file_actions": "invalid json"})
            self.assertEqual(response.status_code, 200)

            # Should fall back to empty list
            call_args = mock_rename.call_args
            self.assertEqual(call_args[0][2], [])  # file_actions should be empty list

    def test_book_with_no_final_metadata(self):
        """Test handling of books without final metadata"""
        from books.tests.test_helpers import create_test_book_with_file

        book_no_metadata = create_test_book_with_file(file_path="/test/path/book.epub", file_format="epub", file_size=1024000, scan_folder=self.scan_folder, content_type="ebook")

        # Book renamer should filter out books without reviewed metadata
        response = self.client.get(reverse("books:book_renamer"))
        self.assertEqual(response.status_code, 200)

        books_with_previews = response.context["books_with_previews"]
        book_ids = [b["book"].id for b in books_with_previews]
        self.assertNotIn(book_no_metadata.id, book_ids)
