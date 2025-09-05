import logging
import os
import json
from django.utils import timezone

from books.models import ScanStatus, ScanFolder
from books.scanner.folder import scan_directory

logger = logging.getLogger("books.scanner")


class EbookScanner:
    def __init__(self, rescan=False, resume=False):
        self.rescan = rescan
        self.resume = resume
        self.cover_extensions = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}
        self.ebook_extensions = {".epub", ".mobi", ".pdf", "azw", ".azw3", ".cbr", ".cbz"}

    def run(self, folder_path=None):
        # Handle resume mode
        if self.resume:
            return self._resume_scan(folder_path)

        # Get the latest scan status or create one
        status = ScanStatus.objects.order_by('-started').first()
        if not status or status.status in ['Completed', 'Failed']:
            status = ScanStatus.objects.create(
                status="Running",
                progress=0,
                message="Initializing scan..."
            )
        else:
            status.status = "Running"
            status.progress = 0
            status.message = "Initializing scan..."
            status.save()

        folders_to_scan = []

        if folder_path:
            folder_path = os.path.abspath(folder_path)
            if os.path.isdir(folder_path) and os.access(folder_path, os.R_OK):
                folders_to_scan = [folder_path]
            else:
                logger.error(f"Can't access folder: {folder_path}")
                status.status = "Failed"
                status.message = f"Can't access folder: {folder_path}"
                status.save()
                return
        else:
            active_folders = ScanFolder.objects.filter(is_active=True)
            folders_to_scan = [
                os.path.abspath(folder.path)
                for folder in active_folders
                if os.path.isdir(folder.path) and os.access(folder.path, os.R_OK)
            ]

        # Store scan configuration for potential resume
        status.scan_folders = json.dumps(folders_to_scan)
        status.save()

        # Track if any failures occurred
        has_failures = False
        failure_messages = []

        total = len(folders_to_scan)
        for idx, path in enumerate(folders_to_scan, start=1):
            status.message = f"Scanning: {path}"
            status.progress = int((idx - 1) / total * 100)
            status.save()

            scan_folder_obj, _ = ScanFolder.objects.get_or_create(
                path=path, defaults={"is_active": True}
            )
            logger.info(f"Starting scan of folder: {path}")
            scan_folder_obj.last_scanned = timezone.now()
            scan_folder_obj.save()

            try:
                scan_directory(
                    directory=path,
                    scan_folder=scan_folder_obj,
                    rescan=self.rescan,
                    ebook_extensions=self.ebook_extensions,
                    cover_extensions=self.cover_extensions,
                    scan_status=status,  # Pass status for progress tracking
                )
                logger.info(f"Completed scan of folder: {path}")
            except Exception as e:
                logger.error(f"Error scanning folder {path}: {e}")
                has_failures = True
                failure_messages.append(f"Error scanning folder {path}: {e}")

        # Set final status based on whether there were failures
        if has_failures:
            status.status = "Failed"
            status.message = "; ".join(failure_messages)
        else:
            status.status = "Completed"
            status.progress = 100
            status.message = "Scan complete."

        status.save()
        logger.info("All folder scans completed.")

    def _resume_scan(self, folder_path=None):
        """Resume an interrupted scan from where it left off"""
        # Find the most recent interrupted scan
        status = ScanStatus.objects.filter(status='Running').order_by('-started').first()

        if not status:
            logger.info("No interrupted scan found. Starting new scan.")
            # Start a new scan instead
            self.resume = False
            return self.run(folder_path)

        logger.info(f"Resuming scan from: {status.last_processed_file or 'beginning'}")

        # Get folders to scan (either from resume or from parameters)
        if status.scan_folders:
            try:
                folders_to_scan = json.loads(status.scan_folders)
            except json.JSONDecodeError:
                logger.error("Could not parse saved scan folders. Starting new scan.")
                self.resume = False
                return self.run(folder_path)
        else:
            # Fall back to current configuration
            if folder_path:
                folders_to_scan = [os.path.abspath(folder_path)]
            else:
                active_folders = ScanFolder.objects.filter(is_active=True)
                folders_to_scan = [
                    os.path.abspath(folder.path)
                    for folder in active_folders
                    if os.path.isdir(folder.path) and os.access(folder.path, os.R_OK)
                ]

        status.message = "Resuming interrupted scan..."
        status.save()

        # First, handle metadata completion for books that exist but have incomplete metadata
        self._handle_metadata_completion(status, folders_to_scan)

        total = len(folders_to_scan)
        for idx, path in enumerate(folders_to_scan, start=1):
            status.message = f"Resuming scan: {path}"
            status.progress = int((idx - 1) / total * 100)
            status.save()

            scan_folder_obj, _ = ScanFolder.objects.get_or_create(
                path=path, defaults={"is_active": True}
            )
            logger.info(f"Resuming scan of folder: {path}")

            try:
                scan_directory(
                    directory=path,
                    scan_folder=scan_folder_obj,
                    rescan=self.rescan,
                    ebook_extensions=self.ebook_extensions,
                    cover_extensions=self.cover_extensions,
                    scan_status=status,
                    resume_from=status.last_processed_file,  # Resume from last processed file
                )
                logger.info(f"Completed scan of folder: {path}")
            except Exception as e:
                logger.error(f"Error scanning folder {path}: {e}")
                status.status = "Failed"
                status.message = f"Error in scan: {e}"
                status.save()
                return

        status.status = "Completed"
        status.progress = 100
        status.message = "Scan complete."
        status.last_processed_file = None  # Clear resume marker
        status.save()
        logger.info("All folder scans completed.")

    def _handle_metadata_completion(self, status, folders_to_scan):
        """Handle completion of metadata for books that exist but have incomplete metadata."""
        from books.models import Book, FinalMetadata, ScanFolder

        # Find all incomplete books across all scan folders being processed
        all_incomplete_books = []

        for folder_path in folders_to_scan:
            try:
                # Get or create the scan folder object
                scan_folder, _ = ScanFolder.objects.get_or_create(
                    path=folder_path, defaults={"is_active": True}
                )

                # Get books in this folder that don't have complete metadata
                incomplete_books = Book.objects.filter(
                    scan_folder=scan_folder,
                    file_path__startswith=folder_path
                ).exclude(
                    # Exclude books that have FinalMetadata (considered complete)
                    id__in=FinalMetadata.objects.values_list('book_id', flat=True)
                ).exclude(
                    # Exclude corrupted books
                    is_corrupted=True
                )

                all_incomplete_books.extend(list(incomplete_books))
                logger.info(f"Found {incomplete_books.count()} incomplete books in {folder_path}")

            except Exception as e:
                logger.error(f"Error checking incomplete books in {folder_path}: {e}")

        if all_incomplete_books:
            logger.info(f"Found {len(all_incomplete_books)} total books needing metadata completion")

            # Complete metadata for these books
            for i, book in enumerate(all_incomplete_books, 1):
                try:
                    logger.info(f"[METADATA COMPLETION] Processing book {book.id}: {book.file_path}")

                    # Update status to show what we're doing
                    status.message = f"Completing metadata for book {book.id} ({i}/{len(all_incomplete_books)})"
                    status.save()

                    # Import the required functions
                    from books.scanner.folder import query_metadata_and_covers, resolve_final_metadata

                    # Skip the file creation part, book already exists
                    # Go straight to metadata collection steps
                    logger.info(f"[METADATA and COVER CANDIDATES QUERY] Path: {book.file_path}")
                    query_metadata_and_covers(book)

                    try:
                        logger.info(f"[FINAL METADATA RESOLVE] Path: {book.file_path}")
                        resolve_final_metadata(book)
                        logger.info(f"Completed metadata for book {book.id}")
                    except Exception as e:
                        logger.error(f"Final metadata resolution failed for {book.file_path}: {str(e)}")

                except Exception as e:
                    logger.error(f"[METADATA COMPLETION ERROR] Book {book.id}: {str(e)}")
                    import traceback
                    traceback.print_exc()

                if i % 10 == 0:  # Log every 10 books
                    logger.info(f"Completed metadata for {i}/{len(all_incomplete_books)} books")
        else:
            logger.info("No incomplete metadata books found")
