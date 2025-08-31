"""Logging utilities for scanner operations.

This module provides functions for logging scan errors and operations
to the database for tracking and debugging purposes.
"""
from books.models import ScanLog


def log_scan_error(message: str, file_path: str, scan_folder) -> None:
    """Log a scanning error to the database"""
    ScanLog.objects.create(
        level="ERROR",
        message=message,
        file_path=file_path,
        scan_folder=scan_folder
    )


def update_scan_progress(status, current: int, total: int, filename: str) -> None:
    """Update overall progress and status message"""
    percent = int((current / total) * 100)
    status.progress = percent
    status.message = f"Scanning: {filename}"
    status.save()
