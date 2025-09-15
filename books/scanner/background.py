"""Background scanning implementation using Django-RQ.

This module provides background job processing for long-running scanning operations:
- Book discovery and metadata extraction
- External API querying with rate limiting
- Progress tracking and status updates
- Error handling and retry logic
"""
import logging
import time
from typing import Dict, List
from django.core.cache import cache
from books.models import Book, ScanFolder
from books.scanner import folder as folder_scanner
from books.scanner.rate_limiting import get_api_status, check_api_health

logger = logging.getLogger("books.scanner")


class ScanProgress:
    """Track scanning progress and provide status updates."""

    def __init__(self, job_id: str):
        self.job_id = job_id
        self.cache_key = f"scan_progress_{job_id}"
        self.start_time = time.time()

    def update(self, current: int, total: int, status: str, details: str = ""):
        """Update scan progress."""
        progress_data = {
            'job_id': self.job_id,
            'current': current,
            'total': total,
            'percentage': int((current / total * 100)) if total > 0 else 0,
            'status': status,
            'details': details,
            'start_time': self.start_time,
            'current_time': time.time(),
            'elapsed_time': time.time() - self.start_time,
        }

        # Calculate ETA
        if current > 0 and total > current:
            time_per_item = progress_data['elapsed_time'] / current
            remaining_items = total - current
            eta_seconds = time_per_item * remaining_items
            progress_data['eta_seconds'] = eta_seconds
        else:
            progress_data['eta_seconds'] = None

        cache.set(self.cache_key, progress_data, timeout=3600)  # 1 hour
        logger.info(f"[SCAN PROGRESS] {status}: {current}/{total} ({progress_data['percentage']}%)")

    def complete(self, success: bool, message: str = "", error: str = ""):
        """Mark scan as complete."""
        final_data = {
            'job_id': self.job_id,
            'completed': True,
            'success': success,
            'message': message,
            'error': error,
            'start_time': self.start_time,
            'end_time': time.time(),
            'total_time': time.time() - self.start_time,
        }
        cache.set(self.cache_key, final_data, timeout=86400)  # 24 hours

    def get_status(self) -> Dict:
        """Get current progress status."""
        return cache.get(self.cache_key, {})


class BackgroundScanner:
    """Background scanner for processing books with rate limiting."""

    def __init__(self, job_id: str):
        self.job_id = job_id
        self.progress = ScanProgress(job_id)

    def scan_folder(self, folder_path: str, language: str = None, enable_external_apis: bool = True) -> Dict:
        """Scan a folder for books in the background."""
        try:
            logger.info(f"[BACKGROUND SCAN] Starting scan of {folder_path}")
            self.progress.update(0, 100, "Initializing", f"Scanning folder: {folder_path}")

            # Get or create scan folder
            scan_folder = ScanFolder.objects.filter(path=folder_path).first()
            if not scan_folder:
                scan_folder = ScanFolder.objects.create(
                    path=folder_path,
                    language=language or 'en',
                    name=folder_path.split('/')[-1] or folder_path.split('\\')[-1]
                )

            # Discover books
            self.progress.update(10, 100, "Discovering files", "Finding book files...")
            discovered_books = folder_scanner.discover_books_in_folder(folder_path)

            if not discovered_books:
                self.progress.complete(True, "No books found in folder")
                return {'success': True, 'message': 'No books found', 'books_processed': 0}

            total_books = len(discovered_books)
            logger.info(f"[BACKGROUND SCAN] Found {total_books} books to process")

            # Process each book
            processed_count = 0
            error_count = 0

            for i, book_path in enumerate(discovered_books):
                try:
                    current_progress = 20 + int((i / total_books) * 70)  # 20-90% for processing

                    self.progress.update(
                        current_progress, 100,
                        "Processing books",
                        f"Processing: {book_path.split('/')[-1] or book_path.split('\\')[-1]}"
                    )

                    # Check if book already exists
                    existing_book = Book.objects.filter(file_path=book_path).first()
                    if existing_book:
                        logger.debug(f"[BACKGROUND SCAN] Book already exists: {book_path}")
                        processed_count += 1
                        continue

                    # Process the book
                    success = self._process_single_book(book_path, scan_folder, enable_external_apis)

                    if success:
                        processed_count += 1
                    else:
                        error_count += 1

                    # Add delay to prevent overwhelming the system
                    time.sleep(0.1)

                except Exception as e:
                    logger.error(f"[BACKGROUND SCAN] Error processing {book_path}: {e}")
                    error_count += 1

            # Finalize
            self.progress.update(95, 100, "Finalizing", "Cleaning up...")

            success_message = f"Processed {processed_count} books"
            if error_count > 0:
                success_message += f" ({error_count} errors)"

            self.progress.complete(
                True,
                success_message,
                f"{error_count} errors occurred" if error_count > 0 else ""
            )

            return {
                'success': True,
                'books_processed': processed_count,
                'errors': error_count,
                'message': success_message
            }

        except Exception as e:
            logger.error(f"[BACKGROUND SCAN] Fatal error: {e}")
            self.progress.complete(False, "", str(e))
            return {'success': False, 'error': str(e)}

    def _process_single_book(self, book_path: str, scan_folder: ScanFolder, enable_external_apis: bool) -> bool:
        """Process a single book file."""
        try:
            # Check API health before processing
            if enable_external_apis:
                api_health = check_api_health()
                if not any(api_health.values()):
                    logger.warning("[BACKGROUND SCAN] All APIs are down, disabling external API calls")
                    enable_external_apis = False

            # Create book record
            book = folder_scanner.create_book_from_file(book_path, scan_folder)
            if not book:
                return False

            # Extract internal metadata
            folder_scanner.extract_internal_metadata(book)

            # Query external APIs if enabled and APIs are healthy
            if enable_external_apis:
                try:
                    # Add delay based on API status
                    api_status = get_api_status()
                    max_delay = max([
                        status.get('rate_limits', {}).get('current_counts', {}).get('minute', 0)
                        for status in api_status.values()
                    ])

                    # Add extra delay if APIs are being hit hard
                    if max_delay > 30:  # If any API has made 30+ requests this minute
                        time.sleep(2)

                    folder_scanner.query_external_metadata(book)

                except Exception as e:
                    logger.warning(f"[BACKGROUND SCAN] External API error for {book_path}: {e}")

            return True

        except Exception as e:
            logger.error(f"[BACKGROUND SCAN] Error processing {book_path}: {e}")
            return False

    def rescan_existing_books(self, book_ids: List[int], enable_external_apis: bool = True) -> Dict:
        """Rescan existing books for updated metadata."""
        try:
            total_books = len(book_ids)
            logger.info(f"[BACKGROUND RESCAN] Starting rescan of {total_books} books")

            self.progress.update(0, 100, "Initializing", f"Rescanning {total_books} books")

            processed_count = 0
            error_count = 0

            for i, book_id in enumerate(book_ids):
                try:
                    current_progress = int((i / total_books) * 90)  # 0-90% for processing

                    book = Book.objects.get(id=book_id)
                    self.progress.update(
                        current_progress, 100,
                        "Rescanning books",
                        f"Rescanning: {book.finalmetadata.final_title if hasattr(book, 'finalmetadata') else 'Unknown'}"
                    )

                    # Re-extract internal metadata
                    folder_scanner.extract_internal_metadata(book)

                    # Re-query external APIs
                    if enable_external_apis:
                        folder_scanner.query_external_metadata(book)

                    processed_count += 1

                    # Add delay
                    time.sleep(0.5)  # Longer delay for rescanning to be gentler on APIs

                except Book.DoesNotExist:
                    logger.warning(f"[BACKGROUND RESCAN] Book {book_id} not found")
                    error_count += 1
                except Exception as e:
                    logger.error(f"[BACKGROUND RESCAN] Error rescanning book {book_id}: {e}")
                    error_count += 1

            # Finalize
            self.progress.update(95, 100, "Finalizing", "Updating final metadata...")

            success_message = f"Rescanned {processed_count} books"
            if error_count > 0:
                success_message += f" ({error_count} errors)"

            self.progress.complete(
                True,
                success_message,
                f"{error_count} errors occurred" if error_count > 0 else ""
            )

            return {
                'success': True,
                'books_processed': processed_count,
                'errors': error_count,
                'message': success_message
            }

        except Exception as e:
            logger.error(f"[BACKGROUND RESCAN] Fatal error: {e}")
            self.progress.complete(False, "", str(e))
            return {'success': False, 'error': str(e)}


# Background job functions for Django-RQ
def background_scan_folder(job_id: str, folder_path: str, language: str = None, enable_external_apis: bool = True):
    """Background job for scanning a folder."""
    scanner = BackgroundScanner(job_id)
    return scanner.scan_folder(folder_path, language, enable_external_apis)


def background_rescan_books(job_id: str, book_ids: List[int], enable_external_apis: bool = True):
    """Background job for rescanning existing books."""
    scanner = BackgroundScanner(job_id)
    return scanner.rescan_existing_books(book_ids, enable_external_apis)


def get_scan_progress(job_id: str) -> Dict:
    """Get the progress of a background scan job."""
    progress = ScanProgress(job_id)
    return progress.get_status()


def get_all_active_scans() -> List[Dict]:
    """Get all currently active scan jobs."""
    # This would need to be implemented with a proper job queue
    # For now, return empty list
    return []


def cancel_scan(job_id: str) -> bool:
    """Cancel a background scan job."""
    # This would need to be implemented with a proper job queue
    # For now, just clear the progress
    cache_key = f"scan_progress_{job_id}"
    cache.delete(cache_key)
    return True
