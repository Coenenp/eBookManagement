"""Background scanning implementation using Django-RQ.

This module provides background job processing for long-running scanning operations:
- Book discovery and metadata extraction
- External API querying with rate limiting and intelligent degradation
- Progress tracking and status updates
- Error handling and retry logic
- Resumable scan sessions
"""

import logging
import time
from typing import Dict, List, Optional

from django.core.cache import cache

from books.models import Book, ScanFolder, ScanSession
from books.scanner import folder as folder_scanner
from books.scanner.intelligent import IntelligentAPIScanner

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
            "job_id": self.job_id,
            "current": current,
            "total": total,
            "percentage": int((current / total * 100)) if total > 0 else 0,
            "status": status,
            "details": details,
            "start_time": self.start_time,
            "current_time": time.time(),
            "elapsed_time": time.time() - self.start_time,
        }

        # Calculate ETA
        if current > 0 and total > current:
            time_per_item = progress_data["elapsed_time"] / current
            remaining_items = total - current
            eta_seconds = time_per_item * remaining_items
            progress_data["eta_seconds"] = eta_seconds
        else:
            progress_data["eta_seconds"] = None

        cache.set(self.cache_key, progress_data, timeout=3600)  # 1 hour
        logger.info(
            f"[SCAN PROGRESS] {status}: {current}/{total} ({progress_data['percentage']}%)"
        )

    def complete(self, success: bool, message: str = "", error: str = ""):
        """Mark scan as complete and remove from active scans."""
        final_data = {
            "job_id": self.job_id,
            "completed": True,
            "success": success,
            "message": message,
            "error": error,
            "start_time": self.start_time,
            "end_time": time.time(),
            "total_time": time.time() - self.start_time,
        }
        cache.set(self.cache_key, final_data, timeout=86400)  # 24 hours

        # Remove from active scans list
        job_ids = cache.get("active_scan_job_ids", [])
        if self.job_id in job_ids:
            job_ids.remove(self.job_id)
            cache.set("active_scan_job_ids", job_ids, timeout=3600)

    def get_status(self) -> Dict:
        """Get current progress status."""
        return cache.get(self.cache_key, {})


class BackgroundScanner:
    """Background scanner for processing books with intelligent API management."""

    def __init__(self, job_id: str):
        self.job_id = job_id
        self.progress = ScanProgress(job_id)
        self.intelligent_scanner: Optional[IntelligentAPIScanner] = None
        self.scan_session: Optional[ScanSession] = None
        self.api_mode = "adaptive"  # 'full', 'partial', 'internal_only', 'adaptive'

    def report_progress(self, current: int, total: int, message: str = ""):
        """Report progress during scanning."""
        self.progress.update(current, total, "Processing", message)

    def scan_folder(
        self,
        folder_path: str,
        language: str = None,
        enable_external_apis: bool = True,
        content_type: str = None,
    ) -> Dict:
        """Scan a folder for books with intelligent API management."""
        try:
            logger.info(f"[BACKGROUND SCAN] Starting intelligent scan of {folder_path}")

            # Initialize intelligent scanner if APIs are enabled
            if enable_external_apis:
                self.intelligent_scanner = IntelligentAPIScanner()
                self.scan_session = self.intelligent_scanner.session

                # Get API availability recommendations
                recommendations = (
                    self.intelligent_scanner.get_scanning_recommendations()
                )
                logger.info(f"[BACKGROUND SCAN] API recommendations: {recommendations}")

                # Adjust scanning mode based on API availability
                if not recommendations["available_apis"]:
                    logger.warning(
                        "[BACKGROUND SCAN] No APIs available, switching to internal-only mode"
                    )
                    self.api_mode = "internal_only"
                    enable_external_apis = False
                elif len(recommendations["available_apis"]) < len(
                    recommendations["api_status"]
                ):
                    logger.info(
                        f"[BACKGROUND SCAN] Partial API availability: {recommendations['available_apis']}"
                    )
                    self.api_mode = "partial"
                else:
                    self.api_mode = "full"
            else:
                self.api_mode = "internal_only"

            self.progress.update(
                0,
                100,
                "Initializing",
                f"Scanning folder: {folder_path} (Mode: {self.api_mode})",
            )

            # Get or create scan folder
            scan_folder = ScanFolder.objects.filter(path=folder_path).first()
            if not scan_folder:
                scan_folder = ScanFolder.objects.create(
                    path=folder_path,
                    language=language or "en",
                    content_type=content_type or "mixed",
                    name=folder_path.split("/")[-1] or folder_path.split("\\")[-1],
                )
            else:
                # Update content_type if provided
                if content_type:
                    scan_folder.content_type = content_type
                    scan_folder.save()

            # Use proper folder scanning with content-type support
            self.progress.update(
                10, 100, "Scanning folder", "Processing files by content type..."
            )

            try:
                # Use the folder scanner directly which supports content-type processing
                folder_scanner.scan_directory(
                    directory=folder_path,
                    scan_folder=scan_folder,
                    rescan=False,  # This is a new scan, not a rescan
                )

                # Count processed books for the progress report
                processed_count = Book.objects.filter(scan_folder=scan_folder).count()

                # If content-type specific processing was used, count those objects too
                if scan_folder.content_type == "audiobooks":
                    from books.models import Audiobook

                    audiobook_count = Audiobook.objects.filter(
                        scan_folder=scan_folder
                    ).count()
                    logger.info(
                        f"[BACKGROUND SCAN] Created {audiobook_count} audiobook objects"
                    )

                elif scan_folder.content_type == "comics":
                    from books.models import Comic

                    comic_count = Comic.objects.filter(scan_folder=scan_folder).count()
                    logger.info(
                        f"[BACKGROUND SCAN] Created {comic_count} comic objects"
                    )

                error_count = 0  # folder_scanner handles errors internally

            except Exception as e:
                logger.error(f"[BACKGROUND SCAN] Error during folder scan: {e}")
                processed_count = 0
                error_count = 1

            # Complete the intelligent scan session
            if self.intelligent_scanner:
                self.intelligent_scanner.complete_session()

            # Finalize
            self.progress.update(95, 100, "Finalizing", "Cleaning up...")

            success_message = f"Processed {processed_count} books"
            if error_count > 0:
                success_message += f" ({error_count} errors)"

            self.progress.complete(
                True,
                success_message,
                f"{error_count} errors occurred" if error_count > 0 else "",
            )

            result = {
                "success": True,
                "books_processed": processed_count,
                "errors": error_count,
                "message": success_message,
            }

            # Add intelligent API information to result
            if self.intelligent_scanner:
                recommendations = (
                    self.intelligent_scanner.get_scanning_recommendations()
                )
                result.update(
                    {
                        "api_mode": self.api_mode,
                        "available_apis": recommendations["available_apis"],
                        "session_id": self.intelligent_scanner.session_id,
                        "books_needing_retry": (
                            len(self.scan_session.resume_queue)
                            if self.scan_session
                            else 0
                        ),
                    }
                )

            return result

        except Exception as e:
            logger.error(f"[BACKGROUND SCAN] Fatal error: {e}")
            if self.intelligent_scanner:
                self.intelligent_scanner.complete_session()
            self.progress.complete(False, "", str(e))
            return {"success": False, "error": str(e)}

    def _process_single_book(
        self, book_path: str, scan_folder: ScanFolder, enable_external_apis: bool
    ) -> bool:
        """Process a single book file with intelligent API management."""
        try:
            # Create book record
            book = folder_scanner.create_book_from_file(book_path, scan_folder)
            if not book:
                return False

            # Extract internal metadata
            folder_scanner.extract_internal_metadata(book)

            # Use intelligent API scanner if enabled
            if (
                enable_external_apis
                and self.intelligent_scanner
                and self.api_mode != "internal_only"
            ):
                try:
                    # Use intelligent scanner for graceful degradation
                    api_result = self.intelligent_scanner.scan_book_with_intelligence(
                        book, force_all_apis=(self.api_mode == "full")
                    )

                    # Log API usage details
                    if api_result["apis_succeeded"]:
                        logger.info(
                            f"[INTELLIGENT API] Book {book.id}: Success with {api_result['apis_succeeded']}"
                        )
                    if api_result["apis_failed"]:
                        logger.warning(
                            f"[INTELLIGENT API] Book {book.id}: Failed with {api_result['apis_failed']}"
                        )

                except Exception as api_error:
                    logger.warning(
                        f"[INTELLIGENT API] API error for book {book.id}: {api_error}"
                    )
                    # Continue without failing - graceful degradation
                    logger.info(
                        f"[BACKGROUND SCAN] Continuing without APIs for book {book.id}"
                    )

            # Sync final metadata if available
            if hasattr(book, "finalmetadata"):
                book.finalmetadata.sync_from_sources()

            return True

        except Exception as e:
            logger.error(f"[BACKGROUND SCAN] Error processing {book_path}: {e}")
            return False

    def rescan_existing_books(
        self, book_ids: List[int], enable_external_apis: bool = True
    ) -> Dict:
        """Rescan existing books for updated metadata."""
        try:
            total_books = len(book_ids)
            logger.info(f"[BACKGROUND RESCAN] Starting rescan of {total_books} books")

            self.progress.update(
                0, 100, "Initializing", f"Rescanning {total_books} books"
            )

            processed_count = 0
            error_count = 0

            for i, book_id in enumerate(book_ids):
                try:
                    current_progress = int(
                        (i / total_books) * 90
                    )  # 0-90% for processing

                    book = Book.objects.get(id=book_id)
                    self.progress.update(
                        current_progress,
                        100,
                        "Rescanning books",
                        f"Rescanning: {book.finalmetadata.final_title if hasattr(book, 'finalmetadata') else 'Unknown'}",
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
                    logger.error(
                        f"[BACKGROUND RESCAN] Error rescanning book {book_id}: {e}"
                    )
                    error_count += 1

            # Finalize
            self.progress.update(95, 100, "Finalizing", "Updating final metadata...")

            success_message = f"Rescanned {processed_count} books"
            if error_count > 0:
                success_message += f" ({error_count} errors)"

            self.progress.complete(
                True,
                success_message,
                f"{error_count} errors occurred" if error_count > 0 else "",
            )

            return {
                "success": True,
                "books_processed": processed_count,
                "errors": error_count,
                "message": success_message,
            }

        except Exception as e:
            logger.error(f"[BACKGROUND RESCAN] Fatal error: {e}")
            self.progress.complete(False, "", str(e))
            return {"success": False, "error": str(e)}


# Background job functions for Django-RQ
def background_scan_folder(
    job_id: str,
    folder_path: str,
    language: str = None,
    enable_external_apis: bool = True,
    content_type: str = None,
):
    """Background job for scanning a folder."""
    import inspect

    # Log the function call with all arguments
    frame = inspect.currentframe()
    args, _, _, values = inspect.getargvalues(frame)
    logger.info("[FUNCTION CALL] background_scan_folder called with:")
    for arg in args:
        logger.info(f"  {arg} = {values[arg]}")

    # Also log the original arguments if this was called via *args
    all_args = inspect.getfullargspec(background_scan_folder)
    logger.info(f"[FUNCTION SIGNATURE] Expected: {all_args}")

    scanner = BackgroundScanner(job_id)
    return scanner.scan_folder(
        folder_path, language, enable_external_apis, content_type
    )


def background_rescan_books(
    job_id: str, book_ids: List[int], enable_external_apis: bool = True
):
    """Background job for rescanning existing books."""
    scanner = BackgroundScanner(job_id)
    return scanner.rescan_existing_books(book_ids, enable_external_apis)


def get_scan_progress(job_id: str) -> Dict:
    """Get the progress of a background scan job."""
    progress = ScanProgress(job_id)
    return progress.get_status()


def add_active_scan(job_id: str):
    """Add a job ID to the active scans list."""
    job_ids = cache.get("active_scan_job_ids", [])
    if job_id not in job_ids:
        job_ids.append(job_id)
        cache.set("active_scan_job_ids", job_ids, timeout=3600)


def scan_folder_in_background(
    folder_id: int,
    folder_path: str,
    folder_name: str,
    content_type: str,
    language: str,
    enable_external_apis: bool = True,
):
    """Trigger a background scan for a specific scan folder."""
    import threading
    import uuid

    # Generate unique job ID
    job_id = str(uuid.uuid4())

    # Add to active scans
    add_active_scan(job_id)

    # Log function parameters for debugging
    logger.info(
        f"[DEBUG] scan_folder_in_background received: folder_id={folder_id}, folder_path={folder_path}, folder_name={folder_name}, content_type={content_type}, language={language}, enable_external_apis={enable_external_apis}"
    )
    logger.info(
        f"[DEBUG] Calling background_scan_folder with args: job_id={job_id}, folder_path={folder_path}, language={language}, enable_external_apis={enable_external_apis}, content_type={content_type}"
    )

    # Start background scan thread
    thread = threading.Thread(
        target=background_scan_folder,
        args=(job_id, folder_path, language, enable_external_apis, content_type),
        daemon=True,
        name="background_scan_folder",
    )

    logger.info(f"[THREAD START] Creating background thread for job {job_id}")

    try:
        thread.start()
        logger.info(
            f"[THREAD STARTED] Background thread started for job {job_id}, thread: {thread.name}"
        )
    except Exception as e:
        logger.error(f"[THREAD ERROR] Failed to start thread: {e}")
        raise

    return job_id

    logger.info(
        f"Started background scan for folder '{folder_name}' (ID: {folder_id}, Job ID: {job_id})"
    )
    return job_id


def get_all_active_scans() -> List[Dict]:
    """Get all currently active scan jobs."""
    job_ids = cache.get("active_scan_job_ids", [])
    active_scans = []

    for job_id in job_ids:
        progress_data = cache.get(f"scan_progress_{job_id}")
        if progress_data and not progress_data.get("completed", False):
            active_scans.append(progress_data)

    return active_scans


def cancel_scan(job_id: str) -> bool:
    """Cancel a background scan job."""
    # This would need to be implemented with a proper job queue
    # For now, just clear the progress
    cache_key = f"scan_progress_{job_id}"
    cache.delete(cache_key)
    return True
