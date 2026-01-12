"""
Test cases for content-type-specific file filtering in scan folders.

Tests TC1.1-TC1.3: Verify that scan folders only process files
appropriate for their designated content type.
"""

import os
import tempfile
from unittest.mock import patch

from django.test import TestCase

from books.models import DataSource, ScanFolder
from books.scanner.folder import scan_directory


class ContentTypeFilteringTests(TestCase):
    """Test cases for content-type-specific file filtering"""

    @classmethod
    def setUpTestData(cls):
        """Set up test data sources"""
        DataSource.objects.get_or_create(name=DataSource.INITIAL_SCAN, defaults={"trust_level": 0.2})

    def setUp(self):
        """Set up test scan folders"""
        import tempfile

        # Create temporary directories for scan folders
        self.temp_dirs = []

        # Create ebook temp directory
        ebook_temp = tempfile.mkdtemp(prefix="test_ebooks_")
        self.temp_dirs.append(ebook_temp)
        self.ebooks_folder = ScanFolder.objects.create(name="Ebooks Test Folder", path=ebook_temp, content_type="ebooks")

        # Create comic temp directory
        comic_temp = tempfile.mkdtemp(prefix="test_comics_")
        self.temp_dirs.append(comic_temp)
        self.comics_folder = ScanFolder.objects.create(name="Comics Test Folder", path=comic_temp, content_type="comics")

        # Create audiobook temp directory
        audiobook_temp = tempfile.mkdtemp(prefix="test_audiobooks_")
        self.temp_dirs.append(audiobook_temp)
        self.audiobooks_folder = ScanFolder.objects.create(name="Audiobooks Test Folder", path=audiobook_temp, content_type="audiobooks")

    def tearDown(self):
        """Clean up temporary directories"""
        import shutil

        for temp_dir in getattr(self, "temp_dirs", []):
            try:
                shutil.rmtree(temp_dir)
            except (OSError, FileNotFoundError):
                pass  # Directory already cleaned up

    def test_ebooks_folder_filters_file_formats(self):
        """TC1.1: Ebooks folder should only count ebook formats"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create test files of different formats
            test_files = {
                "book1.epub": "ebook",
                "book2.pdf": "ebook",
                "book3.mobi": "ebook",
                "book4.azw3": "ebook",
                "comic1.cbz": "comic",
                "comic2.cbr": "comic",
                "audio1.mp3": "audiobook",
                "audio2.m4a": "audiobook",
            }

            for filename in test_files:
                filepath = os.path.join(temp_dir, filename)
                with open(filepath, "w") as f:
                    f.write("test content")

            # Update folder path to temp directory
            self.ebooks_folder.path = temp_dir
            self.ebooks_folder.save()

            # Clear any cached file counts before testing
            from django.core.cache import cache

            cache.clear()

            # Count files - should only include ebook formats
            file_count = self.ebooks_folder.count_files_on_disk()

            # Should count: book1.epub, book2.pdf, book3.mobi, book4.azw3 = 4 files
            # Should exclude: comic files and audio files
            self.assertEqual(file_count, 4, "Ebooks folder should only count ebook format files")

    def test_comics_folder_filters_file_formats(self):
        """TC1.2: Comics folder should only count comic formats"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create test files of different formats
            test_files = {
                "book1.epub": "ebook",
                "book2.pdf": "ebook_or_comic",  # PDF can be comic too
                "comic1.cbz": "comic",
                "comic2.cbr": "comic",
                "comic3.cb7": "comic",
                "audio1.mp3": "audiobook",
                "audio2.m4a": "audiobook",
            }

            for filename in test_files:
                filepath = os.path.join(temp_dir, filename)
                with open(filepath, "w") as f:
                    f.write("test content")

            # Update folder path to temp directory
            self.comics_folder.path = temp_dir
            self.comics_folder.save()

            # Count files - should only include comic formats
            file_count = self.comics_folder.count_files_on_disk()

            # Should count: comic1.cbz, comic2.cbr, comic3.cb7, book2.pdf = 4 files
            # Should exclude: epub, mobi, audio files
            self.assertEqual(file_count, 4, "Comics folder should only count comic format files (including PDFs)")

    def test_audiobooks_folder_filters_file_formats(self):
        """TC1.3: Audiobooks folder should only count audiobook formats"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create test files of different formats
            test_files = {
                "book1.epub": "ebook",
                "book2.pdf": "ebook",
                "comic1.cbz": "comic",
                "audio1.mp3": "audiobook",
                "audio2.m4a": "audiobook",
                "audio3.m4b": "audiobook",
                "audio4.flac": "audiobook",
                "audio5.ogg": "audiobook",
            }

            for filename in test_files:
                filepath = os.path.join(temp_dir, filename)
                with open(filepath, "w") as f:
                    f.write("test content")

            # Update folder path to temp directory
            self.audiobooks_folder.path = temp_dir
            self.audiobooks_folder.save()

            # Count files - should only include audiobook formats
            file_count = self.audiobooks_folder.count_files_on_disk()

            # Should count: audio1.mp3, audio2.m4a, audio3.m4b, audio4.flac, audio5.ogg = 5 files
            # Should exclude: epub, pdf, comic files
            self.assertEqual(file_count, 5, "Audiobooks folder should only count audiobook format files")

    def test_recursive_filtering_maintains_content_type(self):
        """Test that recursive scanning respects content type in subdirectories"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create nested directory structure
            subdir = os.path.join(temp_dir, "subdir")
            os.makedirs(subdir)

            # Create files in both root and subdirectory
            test_files = {"book1.epub": temp_dir, "comic1.cbz": temp_dir, "audio1.mp3": temp_dir, "book2.mobi": subdir, "comic2.cbr": subdir, "audio2.m4a": subdir}

            for filename, directory in test_files.items():
                filepath = os.path.join(directory, filename)
                with open(filepath, "w") as f:
                    f.write("test content")

            # Test ebooks folder recursive filtering
            self.ebooks_folder.path = temp_dir
            self.ebooks_folder.save()

            # Clear any cached file counts before testing
            from django.core.cache import cache

            cache.clear()

            file_count = self.ebooks_folder.count_files_on_disk()

            # Should count: book1.epub, book2.mobi = 2 files (recursive)
            # Should exclude: all comic and audio files even in subdirs
            self.assertEqual(file_count, 2, "Recursive scanning should maintain content type filtering")

    @patch("books.scanner.folder.get_file_format")
    def test_scanner_respects_content_type_during_processing(self, mock_get_format):
        """Test that the actual scanner respects content type when processing files"""

        # Mock file format detection
        def mock_format_detector(file_path):
            if file_path.endswith(".epub"):
                return "epub"
            elif file_path.endswith(".cbz"):
                return "cbz"
            elif file_path.endswith(".mp3"):
                return "mp3"
            return "unknown"

        mock_get_format.side_effect = mock_format_detector

        with tempfile.TemporaryDirectory() as temp_dir:
            # Create ebook files of different formats
            test_files = ["book.epub", "comic.cbz", "audio.mp3"]
            for filename in test_files:
                filepath = os.path.join(temp_dir, filename)
                with open(filepath, "w") as f:
                    f.write("test content")

            # Test with ebooks folder - should only process .epub
            with patch("books.scanner.folder._process_book") as mock_process:
                with patch("books.scanner.folder.discover_books_in_folder") as mock_discover:
                    # Mock discover to return all files
                    mock_discover.return_value = [os.path.join(temp_dir, "book.epub"), os.path.join(temp_dir, "comic.cbz"), os.path.join(temp_dir, "audio.mp3")]

                    # Should filter out non-ebook files before processing
                    # This test verifies the scanning logic honors content_type
                    scan_directory(temp_dir, self.ebooks_folder)

                    # Verify only ebook files were processed
                    processed_files = [call[0][0] for call in mock_process.call_args_list]
                    epub_files = [f for f in processed_files if f.endswith(".epub")]
                    non_epub_files = [f for f in processed_files if not f.endswith(".epub")]

                    self.assertTrue(len(epub_files) > 0, "Should process EPUB files")
                    self.assertEqual(len(non_epub_files), 0, "Should not process non-EPUB files in ebooks folder")

    def test_ebooks_folder_processes_all_ebook_formats(self):
        """Test that ebooks folders process all supported ebook formats"""
        with tempfile.TemporaryDirectory() as temp_dir:
            ebooks_folder = ScanFolder.objects.create(name="Ebooks Folder", path=temp_dir, content_type="ebooks")  # Processes all ebook formats

            # Create files of different ebook formats
            ebook_files = ["book.epub", "book.pdf", "book.mobi", "book.azw3"]
            for filename in ebook_files:
                filepath = os.path.join(temp_dir, filename)
                with open(filepath, "w") as f:
                    f.write("test content")

            file_count = ebooks_folder.count_files_on_disk()

            # Should count all ebook format files
            self.assertEqual(file_count, 4, "Ebooks folder should process all ebook formats")

    def test_case_insensitive_file_extension_filtering(self):
        """Test that file extension filtering is case insensitive"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create files with different case extensions
            test_files = ["book.EPUB", "book.Pdf", "book.cbZ", "audio.MP3"]
            for filename in test_files:
                filepath = os.path.join(temp_dir, filename)
                with open(filepath, "w") as f:
                    f.write("test content")

            # Test ebooks folder with mixed case
            self.ebooks_folder.path = temp_dir
            self.ebooks_folder.save()

            file_count = self.ebooks_folder.count_files_on_disk()

            # Should count: book.EPUB, book.Pdf = 2 files (case insensitive)
            self.assertEqual(file_count, 2, "File filtering should be case insensitive")
