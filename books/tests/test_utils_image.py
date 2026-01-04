"""
Test cases for Image utilities
"""
import os
import tempfile
from unittest.mock import MagicMock, mock_open, patch

from django.test import TestCase, override_settings

# Removed unused imports
from books.tests.test_helpers import create_test_book_with_file, create_test_scan_folder
from books.utils.image_utils import download_and_store_cover, encode_cover_to_base64


class ImageUtilsTests(TestCase):
    """Test cases for Image utility functions"""

    def setUp(self):
        """Set up test data"""
        self.scan_folder = create_test_scan_folder(name="Test Scan Folder")

        self.book = create_test_book_with_file(
            file_path="/test/scan/folder/book.epub",
            file_format="epub",
            file_size=1024000,
            opf_path="",  # Set empty string for opf_path field
            scan_folder=self.scan_folder
        )

    @patch('books.utils.image_utils.requests.get')
    @patch('builtins.open', new_callable=mock_open)
    @override_settings(MEDIA_ROOT='/test/media', MEDIA_URL='/media/')
    def test_download_and_store_cover_success(self, mock_file, mock_get):
        """Test successful cover download and storage"""
        # Mock the cover candidate
        candidate = MagicMock()
        candidate.image_url = "http://example.com/cover.jpg"
        candidate.book = self.book

        # Mock the HTTP response
        mock_response = MagicMock()
        mock_response.content = b"fake image data"
        mock_get.return_value = mock_response

        result = download_and_store_cover(candidate)

        # Verify the request was made
        mock_get.assert_called_once_with("http://example.com/cover.jpg", timeout=10)
        mock_response.raise_for_status.assert_called_once()

        # Verify file was written (the exact path will depend on actual os.path.join behavior)
        self.assertTrue(mock_file.called)
        mock_file().write.assert_called_once_with(b"fake image data")

        # Verify return value contains the expected URL pattern (handle path separators)
        self.assertTrue(result.startswith('/media/covers'), f"Result '{result}' does not start with '/media/covers'")
        self.assertTrue(result.endswith('_cover.jpg'), f"Result '{result}' does not end with '_cover.jpg'")
        self.assertIn('covers', result)  # Ensure covers directory is in path

    @patch('books.utils.image_utils.requests.get')
    def test_download_and_store_cover_http_error(self, mock_get):
        """Test cover download with HTTP error"""
        candidate = MagicMock()
        candidate.image_url = "http://example.com/cover.jpg"
        candidate.book = self.book

        # Mock HTTP error
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = Exception("HTTP Error")
        mock_get.return_value = mock_response

        with self.assertRaises(Exception):
            download_and_store_cover(candidate)

    @patch('books.utils.image_utils.requests.get')
    def test_download_and_store_cover_timeout(self, mock_get):
        """Test cover download with timeout"""
        candidate = MagicMock()
        candidate.image_url = "http://example.com/cover.jpg"
        candidate.book = self.book

        # Mock timeout
        mock_get.side_effect = Exception("Timeout")

        with self.assertRaises(Exception):
            download_and_store_cover(candidate)

        # Verify timeout parameter was used
        mock_get.assert_called_once_with("http://example.com/cover.jpg", timeout=10)

    def test_encode_cover_to_base64_success(self):
        """Test successful base64 encoding of cover image"""
        # Create a temporary file with fake image data
        with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
            test_data = b"fake image data"
            tmp_file.write(test_data)
            tmp_path = tmp_file.name

        try:
            result = encode_cover_to_base64(tmp_path)

            # Verify the result format
            self.assertTrue(result.startswith("data:image/jpeg;base64,"))

            # Verify the encoded content
            import base64
            expected_b64 = base64.b64encode(test_data).decode('utf-8')
            expected_result = f"data:image/jpeg;base64,{expected_b64}"
            self.assertEqual(result, expected_result)

        finally:
            # Clean up temporary file
            os.unlink(tmp_path)

    def test_encode_cover_to_base64_file_not_found(self):
        """Test base64 encoding with non-existent file"""
        result = encode_cover_to_base64("/nonexistent/path.jpg")
        self.assertEqual(result, "")

    def test_encode_cover_to_base64_empty_path(self):
        """Test base64 encoding with empty path"""
        result = encode_cover_to_base64("")
        self.assertEqual(result, "")

    def test_encode_cover_to_base64_none_path(self):
        """Test base64 encoding with None path"""
        result = encode_cover_to_base64(None)
        self.assertEqual(result, "")

    @patch('builtins.open', side_effect=PermissionError("Permission denied"))
    @patch('os.path.isfile', return_value=True)
    def test_encode_cover_to_base64_permission_error(self, mock_isfile, mock_open):
        """Test base64 encoding with permission error"""
        result = encode_cover_to_base64("/test/path.jpg")
        self.assertEqual(result, "")

    @patch('builtins.open', side_effect=IOError("IO Error"))
    @patch('os.path.isfile', return_value=True)
    def test_encode_cover_to_base64_io_error(self, mock_isfile, mock_open):
        """Test base64 encoding with IO error"""
        result = encode_cover_to_base64("/test/path.jpg")
        self.assertEqual(result, "")

    def test_encode_cover_to_base64_empty_file(self):
        """Test base64 encoding with empty file"""
        # Create a temporary empty file
        with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
            tmp_path = tmp_file.name

        try:
            result = encode_cover_to_base64(tmp_path)

            # Should return valid base64 data URL even for empty file
            self.assertTrue(result.startswith("data:image/jpeg;base64,"))

            # Verify empty content
            import base64
            expected_b64 = base64.b64encode(b"").decode('utf-8')
            expected_result = f"data:image/jpeg;base64,{expected_b64}"
            self.assertEqual(result, expected_result)

        finally:
            # Clean up temporary file
            os.unlink(tmp_path)

    @patch('books.utils.image_utils.slugify')
    @patch('books.utils.image_utils.requests.get')
    @patch('builtins.open', new_callable=mock_open)
    @override_settings(MEDIA_ROOT='/test/media', MEDIA_URL='/media/')
    def test_download_and_store_cover_filename_slugification(self, mock_file, mock_get, mock_slugify):
        """Test that filename is properly slugified"""
        candidate = MagicMock()
        candidate.image_url = "http://example.com/cover.jpg"
        candidate.book = self.book

        # Mock slugify
        mock_slugify.return_value = "test-book-epub"

        # Mock successful response
        mock_response = MagicMock()
        mock_response.content = b"fake image data"
        mock_get.return_value = mock_response

        download_and_store_cover(candidate)

        # Verify slugify was called with book filename from primary file
        expected_filename = self.book.primary_file.filename if self.book.primary_file else f"book_{self.book.id}"
        mock_slugify.assert_called_once_with(expected_filename)
