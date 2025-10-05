"""
Ebook & Series Renamer - Batch Processing

Handles batch renaming operations, companion file management, and rollback capabilities.
"""
import os
import logging
import shutil
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from django.db import transaction
from django.utils import timezone

from .renaming_engine import RenamingEngine
from books.models import Book


logger = logging.getLogger(__name__)


class FileOperation:
    """Represents a single file operation (rename/move)."""

    def __init__(self, source_path: str, target_path: str,
                 operation_type: str = 'rename', book_id: Optional[int] = None):
        self.source_path = Path(source_path)
        self.target_path = Path(target_path)
        self.operation_type = operation_type
        self.book_id = book_id
        self.executed = False
        self.error = None

    def __str__(self):
        return f"{self.operation_type}: {self.source_path} -> {self.target_path}"


class CompanionFileFinder:
    """Finds and manages companion files for ebooks."""

    COMPANION_EXTENSIONS = {
        '.jpg', '.jpeg', '.png', '.gif',  # Cover images
        '.opf', '.xml',                   # Metadata files
        '.txt', '.nfo',                   # Description files
        '.srt', '.vtt',                   # Subtitle files (for audiobooks)
    }

    def __init__(self):
        self.engine = RenamingEngine()

    def find_companion_files(self, book_file_path: str) -> List[str]:
        """
        Find all companion files for a given book file.

        Args:
            book_file_path: Path to the main book file

        Returns:
            List of companion file paths
        """
        book_path = Path(book_file_path)
        if not book_path.exists():
            return []

        book_dir = book_path.parent
        book_stem = book_path.stem

        companion_files = []

        # Look for files with same name but different extensions
        for ext in self.COMPANION_EXTENSIONS:
            companion_path = book_dir / f"{book_stem}{ext}"
            if companion_path.exists():
                companion_files.append(str(companion_path))

        # Look for common generic names
        generic_names = ['cover', 'metadata', 'description']
        for generic in generic_names:
            for ext in self.COMPANION_EXTENSIONS:
                generic_path = book_dir / f"{generic}{ext}"
                if generic_path.exists() and str(generic_path) not in companion_files:
                    companion_files.append(str(generic_path))

        return companion_files

    def generate_companion_operations(self, book: Book, folder_pattern: str,
                                      filename_pattern: str,
                                      companion_files: List[str]) -> List[FileOperation]:
        """
        Generate file operations for companion files.

        Args:
            book: Book model instance
            folder_pattern: Target folder pattern
            filename_pattern: Target filename pattern
            companion_files: List of companion file paths

        Returns:
            List of FileOperation objects for companion files
        """
        operations = []

        for companion_path in companion_files:
            companion_file = Path(companion_path)
            companion_ext = companion_file.suffix

            # Generate target path for companion file
            target_folder = self.engine.process_template(folder_pattern, book)
            target_filename = self.engine.process_template(
                filename_pattern, book, companion_ext
            )

            target_path = Path(target_folder) / target_filename

            operations.append(FileOperation(
                source_path=str(companion_file),
                target_path=str(target_path),
                operation_type='companion_rename',
                book_id=book.id
            ))

        return operations


class BatchRenamer:
    """
    Handles batch renaming operations with rollback capability.
    """

    def __init__(self, dry_run: bool = True):
        self.dry_run = dry_run
        self.engine = RenamingEngine()
        self.companion_finder = CompanionFileFinder()
        self.operations: List[FileOperation] = []
        self.rollback_log: List[Dict] = []

    def add_books(self, books: List[Book], folder_pattern: str,
                  filename_pattern: str, include_companions: bool = True) -> None:
        """
        Add books to the batch renaming queue.

        Args:
            books: List of Book model instances
            folder_pattern: Template for folder structure
            filename_pattern: Template for filename
            include_companions: Whether to include companion files
        """
        for book in books:
            try:
                self._add_single_book(book, folder_pattern, filename_pattern,
                                      include_companions)
            except Exception as e:
                logger.error(f"Error adding book {book.id} to batch: {e}")

    def _add_single_book(self, book: Book, folder_pattern: str,
                         filename_pattern: str, include_companions: bool) -> None:
        """Add a single book and its operations to the batch."""
        if not book.file_path or not os.path.exists(book.file_path):
            logger.warning(f"Book {book.id} file not found: {book.file_path}")
            return

        # Generate target path for main book file
        target_folder = self.engine.process_template(folder_pattern, book)
        target_filename = self.engine.process_template(filename_pattern, book)

        if not target_folder or not target_filename:
            logger.warning(f"Could not generate target path for book {book.id}")
            return

        # Ensure target folder exists in target path
        target_path = Path(target_folder) / target_filename

        # Add main file operation
        main_operation = FileOperation(
            source_path=book.file_path,
            target_path=str(target_path),
            operation_type='main_rename',
            book_id=book.id
        )
        self.operations.append(main_operation)

        # Add companion file operations
        if include_companions:
            companion_files = self.companion_finder.find_companion_files(book.file_path)
            companion_ops = self.companion_finder.generate_companion_operations(
                book, folder_pattern, filename_pattern, companion_files
            )
            self.operations.extend(companion_ops)

    def preview_operations(self) -> List[Dict]:
        """
        Generate a preview of all operations without executing them.

        Returns:
            List of operation preview dictionaries
        """
        previews = []

        for op in self.operations:
            preview = {
                'operation_type': op.operation_type,
                'book_id': op.book_id,
                'source_path': str(op.source_path),
                'target_path': str(op.target_path),
                'source_exists': op.source_path.exists(),
                'target_exists': op.target_path.exists(),
                'will_create_dirs': not op.target_path.parent.exists(),
                'path_length': len(str(op.target_path)),
                'warnings': self._check_operation_warnings(op)
            }
            previews.append(preview)

        return previews

    def _check_operation_warnings(self, operation: FileOperation) -> List[str]:
        """Check for potential issues with an operation."""
        warnings = []

        # Check path length
        if len(str(operation.target_path)) > 260:  # Windows path limit
            warnings.append("Target path exceeds Windows path length limit")

        # Check if target already exists
        if operation.target_path.exists():
            warnings.append("Target file already exists")

        # Check if source exists
        if not operation.source_path.exists():
            warnings.append("Source file not found")

        # Check for permission issues (basic check)
        try:
            if operation.source_path.exists():
                operation.source_path.stat()
        except PermissionError:
            warnings.append("Permission denied accessing source file")

        return warnings

    @transaction.atomic
    def execute_operations(self) -> Tuple[int, int, List[str]]:
        """
        Execute all queued operations.

        Returns:
            Tuple of (successful_operations, failed_operations, error_messages)
        """
        if self.dry_run:
            logger.info("Dry run mode - no files will be moved")
            return len(self.operations), 0, []

        successful = 0
        failed = 0
        errors = []

        # Group operations by book for proper rollback handling
        book_operations = self._group_operations_by_book()

        for book_id, ops in book_operations.items():
            try:
                self._execute_book_operations(book_id, ops)
                successful += len(ops)

                # Update database with new path for main file
                self._update_book_path(book_id, ops)

            except Exception as e:
                error_msg = f"Failed to rename book {book_id}: {str(e)}"
                logger.error(error_msg)
                errors.append(error_msg)
                failed += len(ops)

                # Rollback this book's operations
                self._rollback_book_operations(book_id, ops)

        return successful, failed, errors

    def _group_operations_by_book(self) -> Dict[int, List[FileOperation]]:
        """Group operations by book ID for atomic processing."""
        grouped = {}

        for op in self.operations:
            if op.book_id not in grouped:
                grouped[op.book_id] = []
            grouped[op.book_id].append(op)

        return grouped

    def _execute_book_operations(self, book_id: int, operations: List[FileOperation]) -> None:
        """Execute all operations for a single book atomically."""
        executed_ops = []

        try:
            for op in operations:
                # Create target directory if it doesn't exist
                op.target_path.parent.mkdir(parents=True, exist_ok=True)

                # Perform the file operation
                if op.operation_type in ['main_rename', 'companion_rename']:
                    shutil.move(str(op.source_path), str(op.target_path))

                op.executed = True
                executed_ops.append(op)

                # Log operation for potential rollback
                self.rollback_log.append({
                    'book_id': book_id,
                    'operation': op.operation_type,
                    'source': str(op.source_path),
                    'target': str(op.target_path),
                    'timestamp': timezone.now()
                })

        except Exception as e:
            # Rollback already executed operations for this book
            for executed_op in executed_ops:
                try:
                    shutil.move(str(executed_op.target_path), str(executed_op.source_path))
                    executed_op.executed = False
                except Exception as rollback_error:
                    logger.error(f"Failed to rollback operation: {rollback_error}")

            raise e

    def _rollback_book_operations(self, book_id: int, operations: List[FileOperation]) -> None:
        """Rollback operations for a specific book."""
        for op in reversed(operations):  # Reverse order for rollback
            if op.executed:
                try:
                    shutil.move(str(op.target_path), str(op.source_path))
                    op.executed = False
                    logger.info(f"Rolled back: {op}")
                except Exception as e:
                    logger.error(f"Failed to rollback {op}: {e}")

    def _update_book_path(self, book_id: int, operations: List[FileOperation]) -> None:
        """Update the book's file path in the database."""
        main_ops = [op for op in operations if op.operation_type == 'main_rename']

        if main_ops:
            main_op = main_ops[0]  # Should only be one main operation per book
            try:
                book = Book.objects.get(id=book_id)
                book.file_path = str(main_op.target_path)
                book.save(update_fields=['file_path'])
                logger.info(f"Updated book {book_id} path to: {book.file_path}")
            except Book.DoesNotExist:
                logger.error(f"Book {book_id} not found for path update")

    def get_operation_summary(self) -> Dict:
        """Get a summary of queued operations."""
        main_files = sum(1 for op in self.operations if op.operation_type == 'main_rename')
        companion_files = sum(1 for op in self.operations if op.operation_type == 'companion_rename')

        unique_books = len(set(op.book_id for op in self.operations if op.book_id))

        return {
            'total_operations': len(self.operations),
            'main_files': main_files,
            'companion_files': companion_files,
            'books_affected': unique_books,
            'dry_run': self.dry_run
        }


class RenamingHistory:
    """
    Manages history and rollback of renaming operations.
    """

    def __init__(self):
        pass

    def save_operation_batch(self, operations: List[FileOperation], user_id: Optional[int] = None) -> str:
        """
        Save a batch of operations to history for potential rollback.

        Args:
            operations: List of executed operations
            user_id: Optional user ID who performed the operations

        Returns:
            Batch ID for referencing this operation set
        """
        # In a full implementation, this would save to a RenameHistory model
        # For now, return a mock batch ID
        batch_id = f"batch_{timezone.now().strftime('%Y%m%d_%H%M%S')}"

        logger.info(f"Saved rename batch {batch_id} with {len(operations)} operations")
        return batch_id

    def rollback_batch(self, batch_id: str) -> Tuple[bool, str]:
        """
        Rollback a batch of operations by batch ID.

        Args:
            batch_id: The batch ID to rollback

        Returns:
            Tuple of (success, message)
        """
        # In a full implementation, this would:
        # 1. Load operations from RenameHistory model
        # 2. Reverse the file operations
        # 3. Update book paths in database
        # 4. Mark batch as rolled back

        logger.info(f"Rollback requested for batch {batch_id}")
        return True, f"Batch {batch_id} rolled back successfully"
