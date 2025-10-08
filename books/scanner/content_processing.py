"""
Content-type specific scanner processing
Integrates file grouping algorithms with the scanner to create Comics and Audiobooks
"""

import logging
import os
from pathlib import Path
from typing import List

from books.models import (
    ScanFolder,
    Comic, ComicIssue, Audiobook, AudiobookFile,
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
    """Process comic files by grouping them into series"""

    # Group files by series
    comic_grouper = ComicFileGrouper()
    comic_groups = comic_grouper.group_files(file_paths)

    logger.info(f"Found {len(comic_groups)} comic series in {len(file_paths)} files")

    for series_name, issue_files in comic_groups.items():
        logger.info(f"Processing comic series: {series_name} ({len(issue_files)} issues)")

        # Get or create the Comic (series)
        comic, created = Comic.objects.get_or_create(
            title=series_name,
            scan_folder=scan_folder,
            defaults={
                'description': f'Comic series: {series_name}',
                'issue_count': len(issue_files)
            }
        )

        if created:
            logger.info(f"Created new comic series: {series_name}")
        else:
            # Update issue count if we found more issues
            comic.issue_count = max(comic.issue_count, len(issue_files))
            comic.save()
            logger.info(f"Updated comic series: {series_name}")

        # Process each issue file
        for issue_file in issue_files:
            _process_comic_issue(issue_file, comic, comic_grouper, cover_files, opf_files, rescan)


def _process_comic_issue(file_path: str, comic: Comic, comic_grouper: ComicFileGrouper,
                         cover_files: List[str], opf_files: List[str], rescan: bool):
    """Process a single comic issue file"""

    # Extract issue information
    issue_info = comic_grouper.extract_issue_info(file_path, comic.title)

    # Get or create the ComicIssue
    issue, created = ComicIssue.objects.get_or_create(
        comic=comic,
        file_path=file_path,
        defaults={
            'issue_number': issue_info.get('issue_number', '1'),
            'volume': issue_info.get('volume', 1),
            'publication_year': issue_info.get('year'),
            'file_format': get_file_format(file_path),
            'file_size': os.path.getsize(file_path),
        }
    )

    if created:
        logger.info(f"Created comic issue: {comic.title} #{issue_info.get('issue_number', '1')}")
    elif rescan:
        # Update file info on rescan
        issue.file_size = os.path.getsize(file_path)
        issue.file_format = get_file_format(file_path)
        issue.save()
        logger.info(f"Updated comic issue: {comic.title} #{issue_info.get('issue_number', '1')}")

    # Find associated cover file
    from books.scanner.file_ops import find_cover_file
    cover_path = find_cover_file(file_path, cover_files)
    if cover_path:
        issue.cover_path = cover_path
        issue.save()


def _process_audiobook_files(file_paths: List[str], scan_folder: ScanFolder,
                             cover_files: List[str], opf_files: List[str], rescan: bool):
    """Process audiobook files by grouping them into audiobooks"""

    # Group files by audiobook
    audiobook_grouper = AudiobookFileGrouper()
    audiobook_groups = audiobook_grouper.group_files(file_paths)

    logger.info(f"Found {len(audiobook_groups)} audiobooks in {len(file_paths)} files")

    for book_key, audio_files in audiobook_groups.items():
        logger.info(f"Processing audiobook: {book_key} ({len(audio_files)} files)")

        # Get or create the Audiobook
        audiobook, created = Audiobook.objects.get_or_create(
            title=book_key,
            scan_folder=scan_folder,
            defaults={
                'total_duration_seconds': 0,  # Will be calculated later
                'total_size_bytes': 0  # Will be calculated later
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
            duration, size = _process_audiobook_file(audio_file, audiobook, audiobook_grouper, cover_files, opf_files, rescan)
            total_duration += duration or 0
            total_size += size or 0

        # Update totals
        audiobook.total_duration_seconds = total_duration
        audiobook.total_size_bytes = total_size
        audiobook.save()
        logger.info(f"Updated audiobook totals: {total_duration}s, {total_size} bytes")


def _process_audiobook_file(file_path: str, audiobook: Audiobook, audiobook_grouper: AudiobookFileGrouper,
                            cover_files: List[str], opf_files: List[str], rescan: bool) -> tuple:
    """Process a single audiobook file, returns (duration_seconds, file_size_bytes)"""

    # Extract file information
    file_info = audiobook_grouper.extract_file_info(file_path, audiobook.title)

    # Get or create the AudiobookFile
    audiobook_file, created = AudiobookFile.objects.get_or_create(
        audiobook=audiobook,
        file_path=file_path,
        defaults={
            'chapter_number': file_info.get('chapter_number'),
            'track_number': file_info.get('track_number'),
            'chapter_title': file_info.get('chapter_title') or f'Chapter {file_info.get("chapter_number", "")}',

            'file_format': get_file_format(file_path),
            'file_size': os.path.getsize(file_path),
            'duration_seconds': 0  # Will be extracted from file metadata
        }
    )

    if created:
        logger.info(f"Created audiobook file: {audiobook.title} - Chapter {file_info.get('chapter_number', 'Unknown')}")
    elif rescan:
        # Update file info on rescan
        audiobook_file.file_size = os.path.getsize(file_path)
        audiobook_file.file_format = get_file_format(file_path)
        audiobook_file.save()
        logger.info(f"Updated audiobook file: {audiobook.title} - Chapter {file_info.get('chapter_number', 'Unknown')}")

    # Try to extract duration from audio metadata
    try:
        duration = _extract_audio_duration(file_path)
        if duration:
            audiobook_file.duration_seconds = duration
            audiobook_file.save()
    except Exception as e:
        logger.warning(f"Could not extract duration from {file_path}: {e}")

    return audiobook_file.duration_seconds or 0, audiobook_file.file_size or 0


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
