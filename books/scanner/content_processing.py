"""
Content-type specific scanner processing
Integrates file grouping algorithms with the scanner to create Comics and Audiobooks
"""

import logging
import os
from pathlib import Path
from typing import List

from books.models import (
    ScanFolder, Book, BookFile,
    COMIC_FORMATS, EBOOK_FORMATS, AUDIOBOOK_FORMATS
)
from books.scanner.grouping import ComicFileGrouper, AudiobookFileGrouper
from books.scanner.file_ops import get_file_format

logger = logging.getLogger("books.scanner")


def process_files_by_content_type(file_paths: List[str], scan_folder: ScanFolder,
                                  cover_files: List[str], opf_files: List[str],
                                  rescan: bool = False):
    """
    Process files using content-type specific logic
    This is the new Phase 1 processing function
    """
    content_type = scan_folder.content_type

    logger.info(f"Processing {len(file_paths)} files as {content_type}")

    if content_type == 'comics':
        _process_comic_files(file_paths, scan_folder, cover_files, opf_files, rescan)
    elif content_type == 'audiobooks':
        _process_audiobook_files(file_paths, scan_folder, cover_files, opf_files, rescan)
    else:
        # For ebooks, process individually (existing behavior)
        for file_path in file_paths:
            _process_individual_ebook(file_path, scan_folder, cover_files, opf_files, rescan)


def _process_comic_files(file_paths: List[str], scan_folder: ScanFolder,
                         cover_files: List[str], opf_files: List[str], rescan: bool):
    """Process comic files by grouping them into issues"""

    # Group files by series
    comic_grouper = ComicFileGrouper()
    comic_groups = comic_grouper.group_files(file_paths)

    logger.info(f"Found {len(comic_groups)} comic series in {len(file_paths)} files")

    for series_name, issue_files in comic_groups.items():
        logger.info(f"Processing comic series: {series_name} ({len(issue_files)} issues)")

        # Process each issue file as a separate Book (content_type='comic')
        for issue_file in issue_files:
            _process_comic_issue(issue_file, series_name, comic_grouper, cover_files, opf_files, rescan, scan_folder)


def _process_comic_issue(file_path: str, series_name: str, comic_grouper: ComicFileGrouper,
                         cover_files: List[str], opf_files: List[str], rescan: bool, scan_folder: ScanFolder):
    """Process a single comic issue file using unified Book + BookFile architecture"""

    # Extract issue information
    issue_info = comic_grouper.extract_issue_info(file_path, series_name)

    # Create issue title (series name + issue number)
    issue_number = issue_info.get('issue_number', '1')
    issue_title = f"{series_name} #{issue_number}"

    # Get or create the Book (comic issue)
    book, created = Book.get_or_create_by_title(
        title=issue_title,
        content_type='comic',
        defaults={
            'scan_folder': scan_folder,
        }
    )

    if created:
        logger.info(f"Created comic issue: {issue_title}")
    else:
        logger.info(f"Found existing comic issue: {issue_title}")

    # Get or create the BookFile
    book_file, file_created = BookFile.objects.get_or_create(
        book=book,
        file_path=file_path,
        defaults={
            'file_format': get_file_format(file_path),
            'file_size': os.path.getsize(file_path),
        }
    )

    if file_created:
        logger.info(f"Created BookFile for: {issue_title}")
    elif rescan:
        # Update file info on rescan
        book_file.file_size = os.path.getsize(file_path)
        book_file.file_format = get_file_format(file_path)
        book_file.save()
        logger.info(f"Updated BookFile for: {issue_title}")

    # Store comic-specific metadata
    _store_comic_metadata(book, issue_info)

    # Find associated cover file
    from books.scanner.file_ops import find_cover_file
    cover_path = find_cover_file(file_path, cover_files)
    if cover_path:
        book_file.cover_path = cover_path
        book_file.save()


def _store_comic_metadata(book: Book, issue_info: dict):
    """Store comic-specific metadata using the BookMetadata system"""
    from books.models import BookMetadata, STANDARD_METADATA_FIELDS

    # Store issue number
    if issue_info.get('issue_number'):
        BookMetadata.objects.update_or_create(
            book=book,
            field_name=STANDARD_METADATA_FIELDS['issue_number'],
            defaults={
                'field_value': str(issue_info['issue_number']),
                'source': 'file_scanner',
                'confidence': 0.8
            }
        )

    # Store volume
    if issue_info.get('volume'):
        BookMetadata.objects.update_or_create(
            book=book,
            field_name=STANDARD_METADATA_FIELDS['volume'],
            defaults={
                'field_value': str(issue_info['volume']),
                'source': 'file_scanner',
                'confidence': 0.8
            }
        )

    # Store year
    if issue_info.get('year'):
        BookMetadata.objects.update_or_create(
            book=book,
            field_name=STANDARD_METADATA_FIELDS['publication_year'],
            defaults={
                'field_value': str(issue_info['year']),
                'source': 'file_scanner',
                'confidence': 0.8
            }
        )


def _process_audiobook_files(file_paths: List[str], scan_folder: ScanFolder,
                             cover_files: List[str], opf_files: List[str], rescan: bool):
    """Process audiobook files by grouping them into audiobooks using unified Book + BookFile architecture"""

    # Group files by audiobook
    audiobook_grouper = AudiobookFileGrouper()
    audiobook_groups = audiobook_grouper.group_files(file_paths)

    logger.info(f"Found {len(audiobook_groups)} audiobooks in {len(file_paths)} files")

    for book_key, audio_files in audiobook_groups.items():
        logger.info(f"Processing audiobook: {book_key} ({len(audio_files)} files)")

        # Get or create the Book (audiobook)
        book, created = Book.get_or_create_by_title(
            title=book_key,
            content_type='audiobook',
            defaults={
                'scan_folder': scan_folder,
            }
        )

        if created:
            logger.info(f"Created new audiobook: {book_key}")
        else:
            logger.info(f"Found existing audiobook: {book_key}")

        # Process each audio file
        total_duration = 0
        total_size = 0
        for audio_file in audio_files:
            duration, size = _process_audiobook_file(audio_file, book, audiobook_grouper, cover_files, opf_files, rescan)
            total_duration += duration or 0
            total_size += size or 0

        # Store total duration and size as metadata
        _store_audiobook_totals(book, total_duration, total_size)
        logger.info(f"Updated audiobook totals: {total_duration}s, {total_size} bytes")

        # Query external metadata for this audiobook (once per audiobook, not per file)
        if created or rescan:  # Only query for new audiobooks or during rescan
            _query_audiobook_external_metadata(book)


def _process_audiobook_file(file_path: str, book: Book, audiobook_grouper: AudiobookFileGrouper,
                            cover_files: List[str], opf_files: List[str], rescan: bool) -> tuple:
    """Process a single audiobook file using unified BookFile architecture, returns (duration_seconds, file_size_bytes)"""

    # Extract file information
    file_info = audiobook_grouper.extract_file_info(file_path, book.title)

    # Get or create the BookFile
    book_file, created = BookFile.objects.get_or_create(
        book=book,
        file_path=file_path,
        defaults={
            'file_format': get_file_format(file_path),
            'file_size': os.path.getsize(file_path),
            'chapter_number': file_info.get('chapter_number'),
            'track_number': file_info.get('track_number'),
            'chapter_title': file_info.get('chapter_title') or f'Chapter {file_info.get("chapter_number", "")}',
            'duration_seconds': 0  # Will be extracted from file metadata
        }
    )

    if created:
        logger.info(f"Created audiobook file: {book.title} - Chapter {file_info.get('chapter_number', 'Unknown')}")
    elif rescan:
        # Update file info on rescan
        book_file.file_size = os.path.getsize(file_path)
        book_file.file_format = get_file_format(file_path)
        book_file.save()
        logger.info(f"Updated audiobook file: {book.title} - Chapter {file_info.get('chapter_number', 'Unknown')}")

    # Try to extract duration from audio metadata
    try:
        duration = _extract_audio_duration(file_path)
        if duration:
            book_file.duration_seconds = duration
            book_file.save()
    except Exception as e:
        logger.warning(f"Could not extract duration from {file_path}: {e}")

    return book_file.duration_seconds or 0, book_file.file_size or 0


def _store_audiobook_totals(book: Book, total_duration: int, total_size: int):
    """Store audiobook total duration and size as metadata"""
    from books.models import BookMetadata

    # Store total duration
    BookMetadata.objects.update_or_create(
        book=book,
        field_name='total_duration_seconds',
        defaults={
            'field_value': str(total_duration),
            'source': 'file_scanner',
            'confidence': 0.9
        }
    )

    # Store total size
    BookMetadata.objects.update_or_create(
        book=book,
        field_name='total_size_bytes',
        defaults={
            'field_value': str(total_size),
            'source': 'file_scanner',
            'confidence': 0.9
        }
    )


def _extract_audio_duration(file_path: str) -> int:
    """Extract duration from audio file metadata (in seconds)"""
    try:
        # Try using mutagen for audio metadata
        from mutagen import File
        audio_file = File(file_path)
        if audio_file and hasattr(audio_file, 'info'):
            return int(audio_file.info.length)
    except ImportError:
        logger.warning("Mutagen not available for audio duration extraction")
    except Exception as e:
        logger.warning(f"Error extracting duration from {file_path}: {e}")

    return 0


def _process_individual_ebook(file_path: str, scan_folder: ScanFolder,
                              cover_files: List[str], opf_files: List[str], rescan: bool):
    """Process individual ebook file (existing behavior for ebooks)"""
    # Import the original processing function
    from books.scanner.folder import _process_book

    # Use the existing book processing logic for ebooks
    _process_book(file_path, scan_folder, cover_files, opf_files, rescan)


def detect_content_type_from_files(file_paths: List[str]) -> str:
    """
    Auto-detect content type based on file extensions
    This can be used when scan folder content_type is not set
    """
    if not file_paths:
        return 'ebooks'  # default

    comic_count = 0
    audio_count = 0
    ebook_count = 0

    for file_path in file_paths:
        ext = Path(file_path).suffix.lower().lstrip('.')

        if ext in COMIC_FORMATS:
            comic_count += 1
        elif ext in AUDIOBOOK_FORMATS:
            audio_count += 1
        elif ext in EBOOK_FORMATS:
            ebook_count += 1

    # Determine majority content type
    if comic_count > audio_count and comic_count > ebook_count:
        return 'comics'
    elif audio_count > comic_count and audio_count > ebook_count:
        return 'audiobooks'
    else:
        return 'ebooks'


# Integration hook for the existing scanner
def process_files_by_type(file_paths: List[str], scan_folder: ScanFolder,
                          cover_files: List[str], opf_files: List[str], rescan: bool = False):
    """
    Content-type specific file processing that routes to appropriate processors
    This function can replace the file processing loop in scan_directory
    """

    # Check if scan_folder has a specific content_type set
    if scan_folder.content_type and scan_folder.content_type != 'ebooks':
        # Use content-type specific processing
        process_files_by_content_type(file_paths, scan_folder, cover_files, opf_files, rescan)
    else:
        # Auto-detect or fall back to individual processing
        detected_type = detect_content_type_from_files(file_paths)

        if detected_type == 'comics':
            logger.info(f"Auto-detected comics in folder {scan_folder.path}")
            _process_comic_files(file_paths, scan_folder, cover_files, opf_files, rescan)
        elif detected_type == 'audiobooks':
            logger.info(f"Auto-detected audiobooks in folder {scan_folder.path}")
            _process_audiobook_files(file_paths, scan_folder, cover_files, opf_files, rescan)
        else:
            # Process as individual ebooks
            for file_path in file_paths:
                _process_individual_ebook(file_path, scan_folder, cover_files, opf_files, rescan)


def _query_audiobook_external_metadata(book):
    """Query external metadata for an audiobook using its title and author"""
    try:
        # Skip if no title available
        if not book.title or book.title.strip() == "":
            logger.info(f"[AUDIOBOOK EXTERNAL] Skipping external query - no title: {book.id}")
            return

        # Get author from book metadata if available
        author = None
        try:
            author_relation = book.bookauthor.filter(is_active=True).first()
            if author_relation:
                author = author_relation.author.name
        except Exception:
            author = None

        # Create a cache key to prevent duplicate queries for the same audiobook
        from books.utils.cache_key import make_cache_key
        cache_key = f"audiobook_external_metadata:{make_cache_key(book.title, author or 'unknown')}"

        from django.core.cache import cache
        if cache.get(cache_key):
            logger.info(f"[AUDIOBOOK EXTERNAL] Cache hit for: {book.title}")
            return

        logger.info(f"[AUDIOBOOK EXTERNAL] Querying external metadata for: {book.title} by {author or 'unknown'}")

        # Query external APIs using the book's title and author
        from books.scanner.external import query_metadata_and_covers_with_terms

        # Get ISBN from book metadata if available
        isbn = None
        try:
            isbn_metadata = book.bookmetadata.filter(field_name='isbn', is_active=True).first()
            if isbn_metadata:
                isbn = isbn_metadata.field_value
        except Exception:
            isbn = None

        query_metadata_and_covers_with_terms(
            book,
            search_title=book.title,
            search_author=author,
            search_isbn=isbn
        )

        logger.info(f"[AUDIOBOOK EXTERNAL] Completed external metadata query for: {book.title}")

        # Cache that we've processed this audiobook to prevent duplicates
        cache.set(cache_key, True, timeout=3600 * 24)  # Cache for 24 hours

    except Exception as e:
        logger.error(f"[AUDIOBOOK EXTERNAL ERROR] Failed for book {book.id}: {e}")
        import traceback
        traceback.print_exc()


# Test function
def test_content_processing():
    """Test the content-type processing with sample data"""
    import os
    import django

    # Setup Django
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ebook_manager.settings')
    django.setup()

    # Create test files
    test_comic_files = [
        "/test/comics/Batman #001.cbr",
        "/test/comics/Batman #002.cbr",
        "/test/comics/Spider-Man Vol 1 #001.cbz"
    ]

    test_audio_files = [
        "/test/audiobooks/Book Title/Chapter 01.mp3",
        "/test/audiobooks/Book Title/Chapter 02.mp3"
    ]

    # Test content type detection
    comic_type = detect_content_type_from_files(test_comic_files)
    audio_type = detect_content_type_from_files(test_audio_files)

    print(f"Detected comic type: {comic_type}")
    print(f"Detected audio type: {audio_type}")


if __name__ == "__main__":
    test_content_processing()
