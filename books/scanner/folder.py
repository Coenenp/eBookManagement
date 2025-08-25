import os
import logging
import zipfile
import rarfile
import traceback
from pathlib import Path
from books.models import (
    Book, DataSource, BookTitle,
    Series, BookSeries, ScanStatus
)
from books.scanner.file_ops import get_file_format, find_cover_file, find_opf_file
from books.scanner.extractors import epub, mobi, pdf, opf
from books.scanner.parsing import parse_path_metadata
from books.scanner.external import query_metadata_and_covers
from books.scanner.resolver import resolve_final_metadata
from books.scanner.logging_helpers import log_scan_error, update_scan_progress
from books.utils.author import attach_authors

logger = logging.getLogger("books.scanner")


def scan_directory(directory, scan_folder, rescan=False, ebook_extensions=None, cover_extensions=None):
    status, _ = ScanStatus.objects.get_or_create(id=1)
    status.message = "Counting files..."
    status.save()

    ebook_files, cover_files, opf_files = _collect_files(directory, ebook_extensions, cover_extensions)
    total_files = len(ebook_files)

    for i, ebook_path in enumerate(ebook_files, 1):
        try:
            _process_book(ebook_path, scan_folder, cover_files, opf_files, rescan)
        except Exception as e:
            logger.error(f"[PROCESS_BOOK ERROR] {ebook_path}: {str(e)}")
            traceback.print_exc()
            log_scan_error(f"Failed to process: {str(e)}", ebook_path, scan_folder)

        update_scan_progress(status, i, total_files, Path(ebook_path).name)

    _handle_orphans(directory, cover_files, opf_files, ebook_files, scan_folder)


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
    book, created = Book.objects.get_or_create(
        file_path=file_path,
        defaults={
            "file_format": get_file_format(file_path),
            "file_size": os.path.getsize(file_path),
            "scan_folder": scan_folder,
        }
    )
    if not created and not rescan:
        return

    book.cover_path = find_cover_file(file_path, cover_files)
    book.opf_path = find_opf_file(file_path, opf_files)
    book.save()

    logger.info(f"[FILENAME PARSE] Path: {book.file_path}")
    _extract_filename_metadata(book)

    try:
        _extract_internal_metadata(book)
    except Exception as e:
        logger.warning(f"Internal metadata extraction failed: {str(e)}")
        book.is_corrupted = True
        book.save()

    logger.info(f"[INTERNAL METADATA PARSE] Path: {book.file_path}")
    _extract_internal_metadata(book)

    logger.info(f"[OPF PARSE] Path: {book.file_path}")
    if book.opf_path:
        try:
            opf.extract(book)
        except Exception as e:
            logger.warning(f"OPF file reading failed: {str(e)}")
            book.is_corrupted = True
            book.save()

    logger.info(f"[METADATA and COVER CANDIDATES QUERY] Path: {book.file_path}")
    query_metadata_and_covers(book)

    try:
        logger.info(f"[FINAL METADATA RESOLVE] Path: {book.file_path}")
        resolve_final_metadata(book)
    except Exception as e:
        logger.error(f"Final metadata resolution failed for {book.file_path}: {str(e)}")
        # Optionally create a minimal FinalMetadata record here
        # final_metadata, created = FinalMetadata.objects.get_or_create(book=book)
        #   if created:
        #       final_metadata.save()


    logger.info(f"Processed: {Path(file_path).name}")


def _extract_filename_metadata(book):
    source = DataSource.objects.get(name=DataSource.FILENAME)
    parsed = parse_path_metadata(book.file_path)

    # 🎯 Debug output for filename parsing
    logger.info(f"[FILENAME PARSE] Parsed title: {parsed.get('title')}")
    logger.info(f"[FILENAME PARSE] Parsed authors: {parsed.get('authors')}")
    logger.info(f"[FILENAME PARSE] Parsed series: {parsed.get('series')} (#{parsed.get('series_number')})")

    if parsed.get("title"):
        BookTitle.objects.get_or_create(
            book=book,
            title=parsed["title"],
            source=source,
            defaults={"confidence": 0.6}
        )

    raw_names = parsed.get("authors", [])[:3]
    attach_authors(book, raw_names, source, confidence=0.5)

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
    fmt = book.file_format.lower()
    extractor = None

    try:
        if fmt == "epub":
            if not zipfile.is_zipfile(book.file_path):
                raise ValueError("EPUB file is not a valid ZIP archive.")
            extractor = epub.extract

        elif fmt == "pdf":
            extractor = pdf.extract

        elif fmt in ["mobi", "azw", "azw3"]:
            extractor = mobi.extract

        elif fmt == "cbr":
            if not rarfile.is_rarfile(book.file_path):
                raise ValueError("CBR file is not a valid RAR archive.")
            with rarfile.RarFile(book.file_path) as rf:
                rf.testrar()

        elif fmt == "cbz":
            if not zipfile.is_zipfile(book.file_path):
                raise ValueError("CBZ file is not a valid ZIP archive.")
            # extractor = cbz.extract

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
        book, created = Book.objects.get_or_create(
            file_path=file_path,
            defaults={
                "file_format": "placeholder",
                "scan_folder": scan_folder,
                "is_placeholder": True
            }
        )
        if created:
            book.opf_path = file_path
            book.save()

            opf.extract(book)
            resolve_final_metadata(book)

            logger.info(f"Created placeholder for orphan OPF file: {file_path}")
    except Exception as e:
        logger.error(f"Error creating placeholder for {file_path}: {e}")
