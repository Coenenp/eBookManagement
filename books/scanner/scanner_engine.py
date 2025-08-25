import logging
import os
from django.utils import timezone

from books.models import ScanStatus, ScanFolder
from books.scanner.folder import scan_directory

logger = logging.getLogger("books.scanner")


class EbookScanner:
    def __init__(self, rescan=False):
        self.rescan = rescan
        self.cover_extensions = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}
        self.ebook_extensions = {".epub", ".mobi", ".pdf", "azw", ".azw3", ".cbr", ".cbz"}

    def run(self, folder_path=None):
        # Initialize scan status
        status, _ = ScanStatus.objects.get_or_create(id=1)
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
                )
                logger.info(f"Completed scan of folder: {path}")
            except Exception as e:
                logger.error(f"Error scanning folder {path}: {e}")
                status.status = "Failed"
                status.message = f"Error in scan: {e}"
                status.save()

        status.status = "Completed"
        status.progress = 100
        status.message = "Scan complete."
        status.save()
        logger.info("All folder scans completed.")
