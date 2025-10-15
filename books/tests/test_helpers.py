"""
Helper functions for updating tests to work with the new unified Book/BookFile architecture.

This module provides utilities to help convert old test code to work with the new model structure.
"""

from books.models import Book, BookFile, BookTitle, DataSource, ScanFolder


def create_test_book_with_file(file_path, file_format=None, file_size=None, scan_folder=None,
                               content_type='ebook', title=..., opf_path=None, **book_kwargs):
    """
    Create a Book and associated BookFile using the new architecture.

    This replaces the old pattern:
        Book.objects.create(file_path='...', file_format='...', ...)

    With the new pattern:
        book = Book.objects.create(content_type='...', scan_folder=...)
        BookFile.objects.create(book=book, file_path='...', file_format='...', ...)
    """
    import os

    # Extract format from file path if not provided
    if file_format is None and file_path:
        file_format = os.path.splitext(file_path)[1].lower().lstrip('.')

    # Create title from filename if not provided
    if title is ... and file_path:
        title = os.path.splitext(os.path.basename(file_path))[0]
    elif title is ...:
        title = None

    # Create the book
    book_data = {
        'content_type': content_type,
        'scan_folder': scan_folder,
        **book_kwargs
    }
    book = Book.objects.create(**book_data)

    # Create the title record
    if title:
        data_source, _ = DataSource.objects.get_or_create(
            name='test_source',
            defaults={'trust_level': 0.8}
        )
        BookTitle.objects.create(
            book=book,
            title=title,
            source=data_source,
            confidence=0.8,
            is_active=True
        )

    # Create the file record
    if file_path:
        book_file_data = {
            'book': book,
            'file_path': file_path,
            'file_format': file_format or 'unknown',
            'file_size': file_size
        }

        # Add optional BookFile fields
        if opf_path:
            book_file_data['opf_path'] = opf_path

        BookFile.objects.create(**book_file_data)

    return book


def create_test_scan_folder(temp_dir=None, name="Test Scan Folder", content_type='ebooks', auto_cleanup=True):
    """
    Create a ScanFolder for testing with a valid temporary directory path.

    This replaces the old pattern:
        ScanFolder.objects.create(path="/test/scan/folder", ...)

    With:
        ScanFolder.objects.create(path=actual_temp_dir, ...)

    If temp_dir is None, creates a new temporary directory.
    """
    import tempfile

    if temp_dir is None:
        temp_dir = tempfile.mkdtemp()
        # For automatic cleanup, you should add cleanup in your test tearDown
        # or use addCleanup(shutil.rmtree, temp_dir, ignore_errors=True)

    return ScanFolder.objects.create(
        path=temp_dir,
        name=name,
        content_type=content_type,
        is_active=True
    )


def migrate_book_creation_call(old_call_text):
    """
    Helper to convert old Book.objects.create() calls to new architecture.

    Example:
        Book.objects.create(
            file_path="/test/book.epub",
            file_format="epub",
            file_size=1000,
            scan_folder=folder
        )

    Becomes:
        create_test_book_with_file(
            file_path="/test/book.epub",
            file_format="epub",
            file_size=1000,
            scan_folder=folder
        )
    """
    # This is a reference function showing the pattern
    # In practice, manual updates are needed for each test file
    pass


# Usage examples:
"""
# OLD CODE:
self.book1 = Book.objects.create(
    file_path="/test/ebooks/book1.epub",
    file_format="epub",
    file_size=1000000,
    scan_folder=self.ebooks_folder
)

# NEW CODE:
self.book1 = create_test_book_with_file(
    file_path="/test/ebooks/book1.epub",
    file_format="epub",
    file_size=1000000,
    scan_folder=self.ebooks_folder,
    content_type='ebook'
)
"""
