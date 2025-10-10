"""Folder scanning operations for ebook discovery.

This module handles scanning directories for ebook files, extracting
metadata from various formats, and managing book creation processes.
"""
import os
import logging
import zipfile
import rarfile
import traceback
from pathlib import Path
from books.models import (
    Book, BookFile, DataSource, BookTitle,
    Series, BookSeries, ScanStatus,
    COMIC_FORMATS, EBOOK_FORMATS, AUDIOBOOK_FORMATS
)
from books.scanner.file_ops import get_file_format, find_cover_file, find_opf_file
from books.scanner.extractors import epub, mobi, pdf, opf, comic
from books.scanner.parsing import parse_path_metadata
from books.scanner.external import query_metadata_and_covers
from books.scanner.resolver import resolve_final_metadata
from books.scanner.logging_helpers import log_scan_error, update_scan_progress
from books.utils.author import attach_authors

logger = logging.getLogger("books.scanner")


def _get_initial_scan_source():
    """Get or create the 'Initial Scan' DataSource."""
    source, created = DataSource.objects.get_or_create(name=DataSource.INITIAL_SCAN)
    return source


def _get_book_file_path(book):
    """Helper function to get the file path from a book's primary file."""
    primary_file = book.primary_file
    return primary_file.file_path if primary_file else f"Book {book.id} (no file)"


def _get_or_create_book_by_path(file_path, scan_folder, file_format=None, file_size=None, content_type='ebook'):
    """
    Get or create a Book and BookFile by file path.

    This replaces the old Book.get_or_create_by_path method.
    Returns (book, created) tuple like the old method.
    """
    from django.db import transaction

    # Check if a BookFile with this path already exists
    existing_file = BookFile.objects.filter(file_path=file_path).first()
    if existing_file:
        return existing_file.book, False

    # Create new Book and BookFile
    with transaction.atomic():
        # Determine content type from file format if not specified
        if not file_format:
            file_format = get_file_format(file_path)

        if content_type == 'ebook':
            if file_format.lower() in ['cbr', 'cbz', 'cb7', 'cbt']:
                content_type = 'comic'
            elif file_format.lower() in ['mp3', 'm4a', 'm4b', 'aac', 'flac', 'ogg', 'wav']:
                content_type = 'audiobook'

        # Create the book
        book = Book.objects.create(
            content_type=content_type,
            scan_folder=scan_folder
        )

        # Create the book file
        BookFile.objects.create(
            book=book,
            file_path=file_path,
            file_format=file_format or get_file_format(file_path),
            file_size=file_size or (os.path.getsize(file_path) if os.path.exists(file_path) else None)
        )

        return book, True


def scan_directory(directory, scan_folder, rescan=False, ebook_extensions=None, cover_extensions=None, scan_status=None, resume_from=None):
    if not scan_status:
        scan_status, _ = ScanStatus.objects.get_or_create(id=1)

    # Use content-type specific extensions if none provided
    if ebook_extensions is None:
        ebook_extensions = scan_folder.get_extensions()

    scan_status.message = "Counting files..."
    scan_status.save()

    ebook_files, cover_files, opf_files = _collect_files(directory, ebook_extensions, cover_extensions)

    # Handle resume logic
    if resume_from:
        logger.info(f"Attempting to resume from: {resume_from}")

        # First, check for books that exist but need metadata completion
        incomplete_books = _find_incomplete_metadata_books(directory, scan_folder)

        if incomplete_books:
            logger.info(f"Found {len(incomplete_books)} books needing metadata completion")
            _complete_metadata_for_books(incomplete_books, scan_status)

        # Then handle file-based resume
        try:
            # Find the index of the file we should resume from
            resume_index = 0
            for i, file_path in enumerate(ebook_files):
                if file_path == resume_from:
                    # Start from the next file after the last processed one
                    resume_index = i + 1
                    break

            if resume_index > 0:
                logger.info(f"Resuming file processing from file #{resume_index + 1} out of {len(ebook_files)}")
                ebook_files = ebook_files[resume_index:]
            else:
                logger.info("Resume file not found in current directory, starting from beginning")
        except Exception as e:
            logger.warning(f"Error processing resume point: {e}. Starting from beginning.")

    # Use existing total_files from scan_status (set by scanner_engine)
    total_files = scan_status.total_files or len(ebook_files)
    logger.info(f"Processing {len(ebook_files)} files in {directory}")

    # Phase 1 Enhancement: Use content-type specific processing if enabled
    try:
        from books.scanner.content_processing import process_files_by_type

        # Check if this folder should use content-type specific processing
        if scan_folder.content_type in ['comics', 'audiobooks'] or _should_use_content_type_processing(ebook_files):
            logger.info(f"Using content-type specific processing for {scan_folder.content_type}")
            process_files_by_type(ebook_files, scan_folder, cover_files, opf_files, rescan)

            # Update progress for all files at once
            scan_status.processed_files += len(ebook_files)
            if ebook_files:
                scan_status.last_processed_file = ebook_files[-1]
            update_scan_progress(scan_status, scan_status.processed_files, total_files, "Content-type processing complete")
        else:
            # Use original individual file processing for ebooks
            _process_files_individually(ebook_files, scan_folder, cover_files, opf_files, rescan, scan_status, total_files)

    except ImportError:
        logger.info("Content-type processing not available, using standard processing")
        _process_files_individually(ebook_files, scan_folder, cover_files, opf_files, rescan, scan_status, total_files)

    # Handle orphaned files at the end
    _handle_orphans(directory, cover_files, opf_files, ebook_files, scan_folder)


def _should_use_content_type_processing(ebook_files):
    """Determine if content-type specific processing should be used based on file types"""
    if not ebook_files:
        return False

    # Count file types
    comic_count = sum(1 for f in ebook_files if any(f.lower().endswith(f'.{ext}') for ext in COMIC_FORMATS))
    audio_count = sum(1 for f in ebook_files if any(f.lower().endswith(f'.{ext}') for ext in AUDIOBOOK_FORMATS))

    # Use content-type specific processing if majority are comics or audiobooks
    total_files = len(ebook_files)
    return (comic_count > total_files * 0.5) or (audio_count > total_files * 0.5)


def _process_files_individually(ebook_files, scan_folder, cover_files, opf_files, rescan, scan_status, total_files):
    """Process files using the original individual approach"""
    for i, ebook_path in enumerate(ebook_files, 1):
        try:
            _process_book(ebook_path, scan_folder, cover_files, opf_files, rescan)

            # Update global progress tracking
            scan_status.processed_files += 1
            scan_status.last_processed_file = ebook_path

        except Exception as e:
            logger.error(f"[PROCESS_BOOK ERROR] {ebook_path}: {str(e)}")
            traceback.print_exc()
            log_scan_error(f"Failed to process: {str(e)}", ebook_path, scan_folder)

            # Still update progress even on error
            scan_status.processed_files += 1

        update_scan_progress(scan_status, scan_status.processed_files, total_files, Path(ebook_path).name)


def _find_incomplete_metadata_books(directory, scan_folder):
    """Find books in the directory that exist in DB but have incomplete metadata."""
    from books.models import Book, FinalMetadata

    # Get all books in this scan folder that don't have complete metadata
    incomplete_books = Book.objects.filter(
        scan_folder=scan_folder,
        file_path__startswith=directory
    ).exclude(
        # Exclude books that have FinalMetadata (considered complete)
        id__in=FinalMetadata.objects.values_list('book_id', flat=True)
    ).exclude(
        # Exclude corrupted books
        is_corrupted=True
    )

    logger.info(f"Found {incomplete_books.count()} books needing metadata completion in {directory}")
    return list(incomplete_books)


def _complete_metadata_for_books(books, scan_status):
    """Complete metadata collection for existing books."""
    total_incomplete = len(books)

    for i, book in enumerate(books, 1):
        try:
            logger.info(f"[METADATA COMPLETION] Processing book {book.id}: {book.primary_file.file_path if book.primary_file else 'No file'}")

            # Skip the file creation part, book already exists
            # Go straight to metadata collection steps

            logger.info(f"[METADATA and COVER CANDIDATES QUERY] Path: {book.primary_file.file_path if book.primary_file else 'No file'}")
            query_metadata_and_covers(book)

            try:
                logger.info(f"[FINAL METADATA RESOLVE] Path: {book.primary_file.file_path if book.primary_file else 'No file'}")
                resolve_final_metadata(book)
                logger.info(f"Completed metadata for book {book.id}")
            except Exception as e:
                logger.error(f"Final metadata resolution failed for {book.primary_file.file_path if book.primary_file else 'No file'}: {str(e)}")

        except Exception as e:
            logger.error(f"[METADATA COMPLETION ERROR] Book {book.id}: {str(e)}")
            traceback.print_exc()

        # Update progress
        scan_status.message = f"Completing metadata for book {book.id} ({i}/{total_incomplete})"
        scan_status.save()

        if i % 10 == 0:  # Log every 10 books
            logger.info(f"Completed metadata for {i}/{total_incomplete} books")


def discover_books_in_folder(directory, ebook_extensions=None, cover_extensions=None):
    """
    Discover all ebook files in a directory.

    Args:
        directory: Path to scan
        ebook_extensions: List of ebook extensions to look for (defaults to all supported formats)
        cover_extensions: List of cover file extensions

    Returns:
        List of ebook file paths found
    """
    if ebook_extensions is None:
        # Include all supported formats: ebooks, comics, and audiobooks
        # Use set union to avoid duplicates (PDF appears in both ebooks and comics)
        all_formats = set(
            [f'.{fmt}' for fmt in EBOOK_FORMATS] +
            [f'.{fmt}' for fmt in COMIC_FORMATS] +
            [f'.{fmt}' for fmt in AUDIOBOOK_FORMATS]
        )
        ebook_extensions = sorted(list(all_formats))  # Sort for consistent output

    if cover_extensions is None:
        cover_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']

    logger.info(f"[DISCOVER] Scanning directory: {directory}")
    logger.info(f"[DISCOVER] Looking for extensions: {ebook_extensions}")

    ebook_files, cover_files, opf_files = _collect_files(directory, ebook_extensions, cover_extensions)

    logger.info(f"[DISCOVER] Found {len(ebook_files)} ebook files")
    logger.info(f"[DISCOVER] Found {len(cover_files)} cover files")
    logger.info(f"[DISCOVER] Found {len(opf_files)} OPF files")

    return ebook_files


def _collect_files(directory, ebook_exts, cover_exts):
    ebook_files, cover_files, opf_files = [], [], []
    for root, dirs, files in os.walk(directory):
        for file in files:
            file_path = os.path.join(root, file)
            ext = Path(file).suffix.lower()
            if ebook_exts and ext in ebook_exts:
                ebook_files.append(file_path)
            elif cover_exts and ext in cover_exts and "cover" in file.lower():
                cover_files.append(file_path)
            elif ext == ".opf":
                opf_files.append(file_path)
    return ebook_files, cover_files, opf_files


def _process_book(file_path, scan_folder, cover_files, opf_files, rescan=False):
    book, created = _get_or_create_book_by_path(
        file_path=file_path,
        scan_folder=scan_folder,
        file_format=get_file_format(file_path),
        file_size=os.path.getsize(file_path) if os.path.exists(file_path) else None
    )
    if not created and not rescan:
        return

    # Update the BookFile with cover and OPF paths
    primary_file = book.primary_file
    if primary_file:
        primary_file.cover_path = find_cover_file(file_path, cover_files) or ''
        primary_file.opf_path = find_opf_file(file_path, opf_files) or ''
        primary_file.save()

    logger.info(f"[FILENAME PARSE] Path: {file_path}")
    _extract_filename_metadata(book)

    try:
        _extract_internal_metadata(book)
    except Exception as e:
        logger.warning(f"Internal metadata extraction failed: {str(e)}")
        book.is_corrupted = True
        book.save()

    logger.info(f"[INTERNAL METADATA PARSE] Path: {book.primary_file.file_path if book.primary_file else 'No file'}")
    _extract_internal_metadata(book)

    # Skip ISBN scanning for comic books (comics don't typically have ISBNs)
    is_comic = book.primary_file.file_format.lower() in COMIC_FORMATS if book.primary_file else False

    if not is_comic:
        logger.info(f"[CONTENT ISBN SCAN] Path: {book.primary_file.file_path if book.primary_file else 'No file'}")
        try:
            from books.scanner.extractors.content_isbn import save_content_isbns
            save_content_isbns(book)
        except Exception as e:
            logger.warning(f"Content ISBN extraction failed: {str(e)}")

    logger.info(f"[OPF PARSE] Path: {book.primary_file.file_path if book.primary_file else 'No file'}")
    if book.primary_file and book.primary_file.opf_path:
        try:
            opf.extract(book)
        except Exception as e:
            logger.warning(f"OPF file reading failed: {str(e)}")
            book.is_corrupted = True
            book.save()

    # Skip external metadata queries for comic books
    if not is_comic:
        logger.info(f"[METADATA and COVER CANDIDATES QUERY] Path: {book.primary_file.file_path if book.primary_file else 'No file'}")
        query_metadata_and_covers(book)
    else:
        logger.info(f"[SKIPPING EXTERNAL QUERIES] Comic book detected: {book.primary_file.file_path if book.primary_file else 'No file'}")

    try:
        logger.info(f"[FINAL METADATA RESOLVE] Path: {book.primary_file.file_path if book.primary_file else 'No file'}")
        resolve_final_metadata(book)
    except Exception as e:
        logger.error(f"Final metadata resolution failed for {book.primary_file.file_path if book.primary_file else 'No file'}: {str(e)}")
        # Optionally create a minimal FinalMetadata record here
        # final_metadata, created = FinalMetadata.objects.get_or_create(book=book)
        #   if created:
        #       final_metadata.save()

    logger.info(f"Processed: {Path(file_path).name}")


def _extract_filename_metadata(book):
    source = _get_initial_scan_source()

    # Use comic-specific parsing for comic books
    is_comic = book.primary_file.file_format.lower() in COMIC_FORMATS if book.primary_file else False
    if is_comic:
        from books.scanner.parsing import parse_comic_metadata
        parsed = parse_comic_metadata(book.primary_file.file_path)
    else:
        parsed = parse_path_metadata(book.primary_file.file_path if book.primary_file else '')

    # 🎯 Debug output for filename parsing
    logger.info(f"[FILENAME PARSE] Parsed title: {parsed.get('title')}")
    logger.info(f"[FILENAME PARSE] Parsed authors: {parsed.get('authors')}")
    logger.info(f"[FILENAME PARSE] Parsed series: {parsed.get('series')} (#{parsed.get('series_number')})")

    if parsed.get("title"):
        BookTitle.objects.get_or_create(
            book=book,
            title=parsed["title"],
            source=source,
            defaults={"confidence": source.trust_level}
        )

    raw_names = parsed.get("authors", [])[:3]
    attach_authors(book, raw_names, source, confidence=source.trust_level)

    if parsed.get("series"):
        series_obj, _ = Series.objects.get_or_create(name=parsed["series"])
        obj, created = BookSeries.objects.get_or_create(
            book=book,
            series=series_obj,
            source=source,
            defaults={
                "series_number": parsed.get("series_number", ""),
                "confidence": 0.5
            }
        )
        if not created and not obj.series_number and parsed.get("series_number"):
            obj.series_number = parsed["series_number"]
            obj.save()


def _extract_internal_metadata(book):
    fmt = book.primary_file.file_format.lower() if book.primary_file else ""
    extractor = None

    try:
        if fmt == "epub":
            if not zipfile.is_zipfile(book.primary_file.file_path):
                raise ValueError("EPUB file is not a valid ZIP archive.")
            extractor = epub.extract

        elif fmt == "pdf":
            extractor = pdf.extract

        elif fmt in ["mobi", "azw", "azw3"]:
            extractor = mobi.extract

        elif fmt == "cbr":
            if not rarfile.is_rarfile(book.primary_file.file_path):
                raise ValueError("CBR file is not a valid RAR archive.")
            extractor = comic.extract_cbr

        elif fmt == "cbz":
            if not zipfile.is_zipfile(book.primary_file.file_path):
                raise ValueError("CBZ file is not a valid ZIP archive.")
            extractor = comic.extract_cbz

        elif fmt in ["cb7", "cbt"]:
            # CB7 (7-Zip) and CBT (TAR) comic formats are not yet supported
            logger.info(f"[SKIPPED] Comic format {fmt.upper()} not yet supported for metadata extraction: {book.file_path}")
            return

        else:
            logger.info(f"[SKIPPED] No extractor available for format: {fmt}")
            return

        if extractor:
            result = extractor(book)
            if not result:
                logger.warning(f"[WARNING] No metadata extracted from {book.file_path}")

    except Exception as e:
        logger.warning(f"[CORRUPT FILE DETECTED] {fmt.upper()} extract failed for {book.file_path}: {e}")
        book.is_corrupted = True
        book.save()


def _handle_orphans(directory, cover_files, opf_files, ebook_files, scan_folder):
    ebook_dirs = {os.path.dirname(f) for f in ebook_files}

    for opf_file in opf_files:
        opf_dir = os.path.dirname(opf_file)
        if opf_dir not in ebook_dirs:
            _create_placeholder_book(opf_file, scan_folder)


def _create_placeholder_book(file_path, scan_folder):
    try:
        book, created = _get_or_create_book_by_path(
            file_path=file_path,
            scan_folder=scan_folder,
            file_format="placeholder"
        )
        if created:
            book.is_placeholder = True
            book.save()

            # Set OPF path on the BookFile
            primary_file = book.primary_file
            if primary_file:
                primary_file.opf_path = file_path
                primary_file.save()

            opf.extract(book)
            resolve_final_metadata(book)

            logger.info(f"Created placeholder for orphan OPF file: {file_path}")
    except Exception as e:
        logger.error(f"Error creating placeholder for {file_path}: {e}")


def create_book_from_file(file_path, scan_folder):
    """
    Create a book record from a file path.

    Args:
        file_path: Path to the ebook file
        scan_folder: ScanFolder object

    Returns:
        Book object or None if creation failed
    """
    try:
        book, created = _get_or_create_book_by_path(
            file_path=file_path,
            scan_folder=scan_folder,
            file_format=get_file_format(file_path),
            file_size=os.path.getsize(file_path) if os.path.exists(file_path) else None
        )

        if created:
            logger.info(f"[CREATE BOOK] Created new book record: {file_path}")
            # Extract filename metadata
            _extract_filename_metadata(book)
        else:
            logger.debug(f"[CREATE BOOK] Book already exists: {file_path}")

        return book

    except Exception as e:
        logger.error(f"[CREATE BOOK ERROR] Failed to create book from {file_path}: {e}")
        return None


def extract_internal_metadata(book):
    """
    Extract internal metadata from a book file.

    Args:
        book: Book object

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        logger.info(f"[INTERNAL METADATA] Processing: {book.file_path}")
        _extract_internal_metadata(book)
        return True
    except Exception as e:
        logger.error(f"[INTERNAL METADATA ERROR] Failed for {book.file_path}: {e}")
        book.is_corrupted = True
        book.save()
        return False


def query_external_metadata(book):
    """
    Query external APIs for book metadata and covers.

    Args:
        book: Book object

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Skip external queries for comic books
        is_comic = book.file_format.lower() in COMIC_FORMATS
        if is_comic:
            logger.info(f"[EXTERNAL METADATA] Skipping external queries for comic: {book.file_path}")
            return True

        logger.info(f"[EXTERNAL METADATA] Querying external APIs: {book.file_path}")
        query_metadata_and_covers(book)

        # Resolve final metadata
        resolve_final_metadata(book)

        return True
    except Exception as e:
        logger.error(f"[EXTERNAL METADATA ERROR] Failed for {book.file_path}: {e}")
        return False
