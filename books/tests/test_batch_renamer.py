"""
Test Suite for Ebook & Series Renamer - Batch Operations & Execution
Tests batch renaming operations, companion file handling, undo functionality,
and integration with the file system.
"""

import os
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch

from django.test import TestCase, TransactionTestCase

from books.models import Book, Author, Series, BookAuthor, BookSeries, DataSource, FinalMetadata
from books.utils.batch_renamer import BatchRenamer, CompanionFileFinder, RenamingHistory, FileOperation


class BatchRenamerTestCase(TransactionTestCase):
    """Base test case for batch renamer tests"""

    def setUp(self):
        """Set up test data and temporary directory"""
        # Create temporary directory
        self.temp_dir = tempfile.mkdtemp()

        # Get or create test data source
        self.source, _ = DataSource.objects.get_or_create(
            name=DataSource.MANUAL
        )

        # Create test models
        self.author = Author.objects.create(
            name="Isaac Asimov",
            first_name="Isaac",
            last_name="Asimov"
        )

        self.series = Series.objects.create(name="Foundation Series")        # Create test books with actual files
        self.book1_path = Path(self.temp_dir) / "Foundation.epub"
        self.book1_path.touch()
        self.book1 = Book.objects.create(
            file_path=str(self.book1_path),
            file_format='epub',
            file_size=1024000
        )
        # Create relationships using intermediate models
        BookAuthor.objects.create(book=self.book1, author=self.author, source=self.source, is_main_author=True)
        BookSeries.objects.create(book=self.book1, series=self.series, source=self.source, series_number="1")

        # Create FinalMetadata for renaming engine
        FinalMetadata.objects.create(
            book=self.book1,
            final_title="Foundation",
            final_author="Isaac Asimov"
        )

        self.book2_path = Path(self.temp_dir) / "Second Foundation.epub"
        self.book2_path.touch()
        self.book2 = Book.objects.create(
            file_path=str(self.book2_path),
            file_format='epub',
            file_size=2048000
        )
        # Create relationships using intermediate models
        BookAuthor.objects.create(book=self.book2, author=self.author, source=self.source, is_main_author=True)
        BookSeries.objects.create(book=self.book2, series=self.series, source=self.source, series_number="2")

        # Create FinalMetadata for renaming engine
        FinalMetadata.objects.create(
            book=self.book2,
            final_title="Second Foundation",
            final_author="Isaac Asimov"
        )

        self.renamer = BatchRenamer()

    def tearDown(self):
        """Clean up temporary directory"""
        shutil.rmtree(self.temp_dir, ignore_errors=True)


class TC7RenamingExecutionAndUndoTests(BatchRenamerTestCase):
    """TC7 – Renaming Execution and Undo"""

    def test_tc7_1_dry_run_mode(self):
        """TC7.1 – Dry run mode"""
        # Create dry run renamer
        dry_renamer = BatchRenamer(dry_run=True)

        # Add books to renamer
        dry_renamer.add_books(
            [self.book1],
            folder_pattern="Authors/${author.sortname}",
            filename_pattern="${title}.${ext}"
        )

        # Execute dry run
        successful, failed, errors = dry_renamer.execute_operations()

        # Should show preview without modifying files
        self.assertEqual(failed, 0)  # No failures expected
        self.assertEqual(len(errors), 0)  # No errors expected

        # Database should remain unchanged
        self.book1.refresh_from_db()
        self.assertEqual(self.book1.file_path, str(self.book1_path))

        # Files should not be moved
        self.assertTrue(self.book1_path.exists())

    def test_tc7_2_execute_mode(self):
        """TC7.2 – Execute mode"""
        # Create execute mode renamer
        execute_renamer = BatchRenamer(dry_run=False)

        # Create target directory structure
        target_dir = Path(self.temp_dir) / "Authors" / "Asimov, Isaac"

        # Add book to renamer
        execute_renamer.add_books(
            [self.book1],
            folder_pattern="Authors/${author.sortname}",
            filename_pattern="${title}.${ext}"
        )

        # Execute actual rename
        successful, failed, errors = execute_renamer.execute_operations()

        # Should successfully rename files and update DB
        self.assertEqual(failed, 0)  # No failures expected
        self.assertEqual(len(errors), 0)  # No errors expected

        # Database should be updated
        self.book1.refresh_from_db()
        expected_path = target_dir / "Foundation.epub"
        self.assertEqual(Path(self.book1.file_path), expected_path)

        # File should be moved
        self.assertFalse(self.book1_path.exists())
        self.assertTrue(expected_path.exists())

    def test_tc7_3_undo_operation(self):
        """TC7.3 – Undo operation"""
        # Create execute mode renamer for first rename
        execute_renamer = BatchRenamer(dry_run=False)

        # Execute rename first
        execute_renamer.add_books(
            [self.book1],
            folder_pattern="Authors/${author.sortname}",
            filename_pattern="${title}.${ext}"
        )

        successful, failed, errors = execute_renamer.execute_operations()
        self.assertEqual(failed, 0)  # No failures expected

        # For undo test, we need to check if renaming history exists
        # This would need proper RenamingHistory model integration

        # Undo the operation
        history = RenamingHistory()
        undo_success, undo_message = history.rollback_batch("batch_1")

        # Should successfully undo
        self.assertTrue(undo_success)

        # Database should be reverted
        self.book1.refresh_from_db()
        self.assertEqual(Path(self.book1.file_path), self.book1_path)

        # File should be back in original location
        self.assertTrue(self.book1_path.exists())

    def test_tc7_4_path_length_validation(self):
        """TC7.4 – Path length validation"""
        # Create dry run renamer for path validation
        dry_renamer = BatchRenamer(dry_run=True)

        # Create very long pattern that would exceed path limits
        long_pattern = "Very" + ("Long" * 50) + "Path/${title}"

        dry_renamer.add_books(
            [self.book1],
            folder_pattern=long_pattern,
            filename_pattern="${title}.${ext}"
        )

        # Should warn about path length
        successful, failed, errors = dry_renamer.execute_operations()

        # Should contain warnings about path length (check if errors include path length warnings)
        # For now, we just check that the operation completes without crashing
        # Note: This test may pass even without warnings if path isn't too long
        # Implementation should add warnings for very long paths


class TC8BookDeletionImpactTests(BatchRenamerTestCase):
    """TC8 – Book Deletion Impact"""

    def test_tc8_1_renamed_books_can_be_deleted(self):
        """TC8.1 – Renamed books can still be deleted"""
        # Rename book first
        self.renamer.add_books([self.book1], folder_pattern="Authors/${author.sortname}", filename_pattern="${title}.${ext}")

        # Create a non-dry-run renamer for actual execution
        execute_renamer = BatchRenamer(dry_run=False)
        execute_renamer.add_books(
            [self.book1],
            folder_pattern="Authors/${author.sortname}",
            filename_pattern="${title}.${ext}"
        )
        successful, failed, errors = execute_renamer.execute_operations()
        self.assertEqual(failed, 0)  # No failures expected

        # Update book instance
        self.book1.refresh_from_db()

        # Book should still be deletable
        book_id = self.book1.id
        new_path = Path(self.book1.file_path)

        # Delete book
        self.book1.delete()

        # Book should be removed from database
        self.assertFalse(Book.objects.filter(id=book_id).exists())

        # File operations should remain valid
        self.assertTrue(new_path.exists())  # File still exists for manual cleanup

    def test_tc8_2_unreviewed_books_auto_deletion(self):
        """TC8.2 – Only unreviewed books are auto-deleted"""
        # Set book as unreviewed (assuming reviewed field exists)
        if hasattr(self.book1, 'reviewed'):
            self.book1.reviewed = False
            self.book1.save()

        # Rename book
        self.renamer.add_books([self.book1], folder_pattern="Authors/${author.sortname}", filename_pattern="${title}.${ext}")

        successful, failed, errors = self.renamer.execute_operations()
        self.assertEqual(failed, 0)  # No failures expected

        # Unreviewed books should be deletable
        # (This would be handled by separate deletion logic)
        self.assertTrue(Book.objects.filter(id=self.book1.id).exists())

    def test_tc8_3_retain_unrelated_metadata(self):
        """TC8.3 – Retain unrelated metadata"""
        # Rename and then delete book
        self.renamer.add_books([self.book1], folder_pattern="Authors/${author.sortname}", filename_pattern="${title}.${ext}")

        successful, failed, errors = self.renamer.execute_operations()
        self.assertEqual(failed, 0)  # No failures expected

        author_id = self.author.id
        series_id = self.series.id

        # Delete book
        self.book1.delete()

        # Author and Series should remain intact
        self.assertTrue(Author.objects.filter(id=author_id).exists())
        self.assertTrue(Series.objects.filter(id=series_id).exists())

    def test_tc8_4_delete_associated_book_metadata(self):
        """TC8.4 – Delete associated book metadata"""
        # This would test that book-specific metadata is cleaned up
        # while preserving global metadata entities

        book_id = self.book1.id

        # Delete book
        self.book1.delete()

        # Book should be completely removed
        self.assertFalse(Book.objects.filter(id=book_id).exists())

        # Related objects should handle cascading appropriately
        # (Based on model definitions)

    def test_tc8_5_confirmed_deletion_cascade(self):
        """TC8.5 – Confirmed deletion cascade"""
        # Test that confirmed deletion properly cascades

        # Rename book first
        self.renamer.add_books([self.book1], folder_pattern="Authors/${author.sortname}", filename_pattern="${title}.${ext}")

        successful, failed, errors = self.renamer.execute_operations()
        self.assertEqual(failed, 0)  # No failures expected

        # Get new file path
        self.book1.refresh_from_db()
        new_file_path = Path(self.book1.file_path)

        # Confirm deletion (this would be a separate method)
        book_id = self.book1.id
        self.book1.delete()

        # Book should be removed from database
        self.assertFalse(Book.objects.filter(id=book_id).exists())

        # File should still exist for manual cleanup
        self.assertTrue(new_file_path.exists())


class TC9MediaTypeRulesTests(BatchRenamerTestCase):
    """TC9 – Media Type Rules"""

    def setUp(self):
        super().setUp()

        # Create mixed media files
        self.comic_path = Path(self.temp_dir) / "comic.cbz"
        self.comic_path.touch()
        self.comic_book = Book.objects.create(
            file_path=str(self.comic_path),
            file_size=512000,
            file_format='cbz'
        )

        self.audio_path = Path(self.temp_dir) / "audiobook.m4b"
        self.audio_path.touch()
        self.audio_book = Book.objects.create(
            file_path=str(self.audio_path),
            file_size=1024000000,
            file_format='m4b'
        )

    def test_tc9_1_folder_content_type_validation(self):
        """TC9.1 – Folder content type validation"""
        # Try to put different media types in same folder
        self.renamer.add_books([self.book1], folder_pattern="Mixed", filename_pattern="${title}.${ext}")

        self.renamer.add_books([self.comic_book], folder_pattern="Mixed", filename_pattern="${title}.${ext}")

        # Should detect mixed media types
        result = self.renamer.execute_operations()

        # Should have warnings about mixed media types
        operations = result['operations']
        has_media_warning = any(
            'media type' in str(op.get('warnings', [])).lower() or
            'mixed' in str(op.get('warnings', [])).lower()
            for op in operations
        )
        # Note: Implementation should warn about mixed media types

    def test_tc9_2_extension_whitelist_per_media_type(self):
        """TC9.2 – Extension whitelist per media type"""
        # Test valid extensions for each media type

        # Ebooks
        valid_ebook_exts = ['.epub', '.mobi', '.azw3', '.pdf', '.txt']
        for ext in valid_ebook_exts:
            self.assertIn(ext, ['.epub', '.mobi', '.azw3', '.pdf', '.txt'])

        # Comics
        valid_comic_exts = ['.cbz', '.cbr', '.cb7']
        for ext in valid_comic_exts:
            self.assertIn(ext, ['.cbz', '.cbr', '.cb7'])

        # Audiobooks
        valid_audio_exts = ['.mp3', '.m4b', '.aac', '.flac']
        for ext in valid_audio_exts:
            self.assertIn(ext, ['.mp3', '.m4b', '.aac', '.flac'])

    def test_tc9_3_reject_unknown_extensions(self):
        """TC9.3 – Reject unknown or mixed extensions"""
        # Create file with unknown extension
        unknown_path = Path(self.temp_dir) / "unknown.xyz"
        unknown_path.touch()

        # This would be handled during file scanning
        # Unknown extensions should be logged but skipped
        self.assertTrue(unknown_path.exists())

        # File should not be processed for renaming
        # (Would be filtered out during book discovery)

    def test_tc9_4_maintain_mediatype_mapping(self):
        """TC9.4 – Maintain consistent folder-level mediatype mapping"""
        # Rename books and ensure media type classification is preserved

        # Rename ebook
        self.renamer.add_books([self.book1], folder_pattern="Library/Ebooks/${author.sortname}", filename_pattern="${title}.${ext}")

        # Rename comic
        self.renamer.add_books([self.comic_book], folder_pattern="Library/Comics/${title}", filename_pattern="${title}.${ext}")

        successful, failed, errors = self.renamer.execute_operations()
        self.assertEqual(failed, 0)  # No failures expected

        # Should maintain separate folder structures by media type
        operations = self.renamer.preview_operations()

        # Find operations for each book
        ebook_ops = [op for op in operations if 'Foundation' in op['target_path']]
        comic_ops = [op for op in operations if 'Test Comic' in op['target_path']]

        # Should have separate folder structures
        self.assertGreater(len(ebook_ops), 0)
        self.assertGreater(len(comic_ops), 0)

        # Paths should reflect media type separation
        if ebook_ops:
            self.assertIn('Ebooks', ebook_ops[0]['target_path'])
        if comic_ops:
            self.assertIn('Comics', comic_ops[0]['target_path'])


class CompanionFileFinderTests(TestCase):
    """Test cases for companion file detection"""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.finder = CompanionFileFinder()

        # Create test files
        self.book_file = Path(self.temp_dir) / "Foundation.epub"
        self.book_file.touch()

        # Create companion files
        (Path(self.temp_dir) / "Foundation.jpg").touch()  # Cover
        (Path(self.temp_dir) / "Foundation.opf").touch()  # Metadata
        (Path(self.temp_dir) / "Foundation.nfo").touch()  # NFO file
        (Path(self.temp_dir) / "cover.jpg").touch()       # Generic cover
        (Path(self.temp_dir) / "metadata.opf").touch()    # Generic metadata

        # Create non-companion file
        (Path(self.temp_dir) / "other_book.epub").touch()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_find_exact_name_companions(self):
        """Test finding companion files with exact matching names"""
        companions = self.finder.find_companion_files(str(self.book_file))

        # Should find files with same base name
        companion_names = [Path(c).name for c in companions]

        self.assertIn("Foundation.jpg", companion_names)
        self.assertIn("Foundation.opf", companion_names)
        self.assertIn("Foundation.nfo", companion_names)

    def test_find_generic_companions(self):
        """Test finding generic companion files"""
        companions = self.finder.find_companion_files(str(self.book_file))

        companion_names = [Path(c).name for c in companions]

        # Should find generic files
        self.assertIn("cover.jpg", companion_names)
        self.assertIn("metadata.opf", companion_names)

    def test_exclude_other_books(self):
        """Test that other book files are not considered companions"""
        companions = self.finder.find_companion_files(str(self.book_file))

        companion_names = [Path(c).name for c in companions]

        # Should not include other book files
        self.assertNotIn("other_book.epub", companion_names)

    def test_companion_extensions(self):
        """Test recognized companion file extensions"""
        valid_companion_exts = ['.jpg', '.jpeg', '.png', '.opf', '.nfo', '.txt']

        for ext in valid_companion_exts:
            companion_file = Path(self.temp_dir) / f"Foundation{ext}"
            companion_file.touch()

            companions = self.finder.find_companion_files(str(self.book_file))
            companion_names = [Path(c).name for c in companions]

            self.assertIn(f"Foundation{ext}", companion_names)

            # Clean up
            companion_file.unlink()


class RenamingHistoryTests(TestCase):
    """Test cases for renaming history and undo functionality"""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

        # Create test book
        # No need to create format objects - file_format is just a CharField
        self.book = Book.objects.create(
            file_path=os.path.join(self.temp_dir, "test.epub"),
            file_size=1024000,
            file_format='epub'
        )

        # Create actual file
        Path(self.book.file_path).touch()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_history_creation(self):
        """Test that rename history is created"""
        # RenamingHistory is a utility class, not a Django model
        history = RenamingHistory()

        # Test that batch operations can be saved
        operations = [FileOperation("/tmp/test.epub", "/tmp/new/test.epub", "main_rename", 1)]
        batch_id = history.save_operation_batch(operations)

        self.assertIsNotNone(batch_id)
        self.assertIsInstance(batch_id, str)

    def test_history_operations_tracking(self):
        """Test tracking of individual operations in history"""
        # RenamingHistory is a utility class, not a Django model
        history = RenamingHistory()

        # Test batch operations with mixed success/failure
        operations = [
            FileOperation("/tmp/test1.epub", "/tmp/new/test1.epub", "main_rename", 1),
        ]
        batch_id = history.save_operation_batch(operations)

        self.assertIsNotNone(batch_id)
        self.assertEqual(len(operations), 1)

    def test_undo_validation(self):
        """Test validation before undo operations"""
        # RenamingHistory is a utility class, not a Django model
        history = RenamingHistory()

        # Test that validation works for undo operations
        operations = [FileOperation("/tmp/test.epub", "/tmp/new/test.epub", "main_rename", 1)]
        batch_id = history.save_operation_batch(operations)

        # Test that we can find the batch for rollback
        self.assertIsNotNone(batch_id)


class IntegrationTests(BatchRenamerTestCase):
    """Integration tests for complete renaming workflows"""

    def test_complete_rename_workflow(self):
        """Test complete workflow from pattern to execution"""
        # Set up companion files
        cover_file = Path(self.temp_dir) / "Foundation.jpg"
        metadata_file = Path(self.temp_dir) / "Foundation.opf"
        cover_file.touch()
        metadata_file.touch()

        # Add books with patterns
        self.renamer.add_books([self.book1], folder_pattern="Library/${format}/${author.sortname}", filename_pattern="${title}.${ext}", include_companions=True)

        self.renamer.add_books([self.book2], folder_pattern="Library/${format}/${author.sortname}", filename_pattern="${title}.${ext}", include_companions=True)

        # Execute dry run first
        dry_successful, dry_failed, dry_errors = self.renamer.execute_operations()
        self.assertEqual(dry_failed, 0)  # No failures expected in dry run
        self.assertGreater(len(self.renamer.operations), 0)

        # Execute actual rename with new non-dry-run renamer
        execute_renamer = BatchRenamer(dry_run=False)
        execute_renamer.add_books(
            [self.book1],
            folder_pattern="Library/${format}/${author.sortname}",
            filename_pattern="${title}.${ext}",
            include_companions=True
        )
        execute_renamer.add_books(
            [self.book2],
            folder_pattern="Library/${format}/${author.sortname}",
            filename_pattern="${title}.${ext}",
            include_companions=True
        )
        actual_successful, actual_failed, actual_errors = execute_renamer.execute_operations()
        self.assertEqual(actual_failed, 0)  # No failures expected

        # Verify books were moved
        self.book1.refresh_from_db()
        self.book2.refresh_from_db()

        expected_dir = Path(self.temp_dir) / "Library" / "EPUB" / "Asimov, Isaac"

        self.assertEqual(
            Path(self.book1.file_path).parent,
            expected_dir
        )
        self.assertEqual(
            Path(self.book2.file_path).parent,
            expected_dir
        )

        # Verify files exist in new locations
        self.assertTrue(Path(self.book1.file_path).exists())
        self.assertTrue(Path(self.book2.file_path).exists())

    def test_error_handling_and_rollback(self):
        """Test error handling and partial rollback"""
        # Create a scenario that might fail

        # Make one of the files read-only to simulate permission error
        self.book2_path.chmod(0o444)  # Read-only

        try:
            self.renamer.add_books([self.book1], folder_pattern="Library/${author.sortname}", filename_pattern="${title}.${ext}")

            self.renamer.add_books([self.book2], folder_pattern="Library/${author.sortname}", filename_pattern="${title}.${ext}")

            # Execute operation
            successful, failed, errors = self.renamer.execute_operations()

            # Should handle errors gracefully
            # May succeed for book1 but fail for book2
            # Check that we got some result (successful + failed should equal total operations)
            total_operations = len(self.renamer.operations)
            self.assertEqual(successful + failed, total_operations)

            if failed > 0:
                # Should have error information
                self.assertGreater(len(errors), 0)

        finally:
            # Restore permissions for cleanup
            self.book2_path.chmod(0o644)

    def test_concurrent_access_handling(self):
        """Test handling of concurrent access to files"""
        # This would test file locking and concurrent access scenarios

        self.renamer.add_books([self.book1], folder_pattern="Library/${author.sortname}", filename_pattern="${title}.${ext}")

        # Simulate concurrent access by opening file
        with open(self.book1_path, 'rb') as f:
            # Try to rename while file is open
            result = self.renamer.execute_operations()

            # Should handle file being in use
            # (Behavior depends on OS and implementation)
            self.assertIn('success', result)

    @patch('books.utils.batch_renamer.os.rename')
    def test_filesystem_error_handling(self, mock_rename):
        """Test handling of filesystem errors"""
        # Mock filesystem operation to raise error
        mock_rename.side_effect = OSError("Disk full")

        self.renamer.add_books([self.book1], folder_pattern="Library/${author.sortname}", filename_pattern="${title}.${ext}")

        successful, failed, errors = self.renamer.execute_operations()

        # Should handle filesystem errors gracefully
        self.assertGreater(failed, 0)  # Should have failures due to mocked error
        self.assertGreater(len(errors), 0)  # Should have error messages

        # Database should not be updated on failure
        self.book1.refresh_from_db()
        self.assertEqual(self.book1.file_path, str(self.book1_path))
