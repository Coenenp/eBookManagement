#!/usr/bin/env python
"""
Test scanning with real delays to verify progress tracking
"""

import os
import tempfile
import django
from pathlib import Path
import threading
import time

from books.scanner.background import background_scan_folder, add_active_scan, get_all_active_scans
import uuid

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ebook_manager.settings')
django.setup()


print("=== Testing Real Scan Progress Tracking ===")

# Create a temporary directory with test files
with tempfile.TemporaryDirectory() as temp_dir:
    print(f"Creating test files in: {temp_dir}")

    # Create some test ebook files
    test_files = [
        "test_book1.epub",
        "test_book2.mobi",
        "test_book3.pdf",
        "standalone.opf"
    ]

    for filename in test_files:
        file_path = Path(temp_dir) / filename
        file_path.write_text("test content")
        print(f"  Created: {filename}")

    print("\n=== Starting Background Scan ===")

    # Generate job ID and add to active scans
    job_id = str(uuid.uuid4())
    print(f"Job ID: {job_id}")

    # Add to active scans first
    add_active_scan(job_id)
    print("Added to active scans list")

    # Start background scan in a thread
    def run_scan():
        print("Starting background scan thread...")
        try:
            result = background_scan_folder(
                job_id=job_id,
                folder_path=temp_dir,
                language='en',
                enable_external_apis=False,  # Disable for faster testing
                content_type='mixed'
            )
            print(f"Scan completed with result: {result}")
        except Exception as e:
            print(f"Scan failed with error: {e}")

    # Start the scan in a background thread
    scan_thread = threading.Thread(target=run_scan, daemon=True)
    scan_thread.start()

    # Monitor active scans for 30 seconds
    print("\n=== Monitoring Active Scans ===")
    for i in range(30):
        active_scans = get_all_active_scans()
        print(f"Time {i+1}s: {len(active_scans)} active scans")

        for j, scan in enumerate(active_scans):
            status = scan.get('status', 'Unknown')
            percentage = scan.get('percentage', 0)
            current = scan.get('current', 0)
            total = scan.get('total', 0)
            print(f"  Scan {j+1}: {status} - {current}/{total} ({percentage}%)")

        if not active_scans:
            print("  No active scans detected")

        time.sleep(1)

        # Break if scan thread finished
        if not scan_thread.is_alive():
            print("  Scan thread completed")
            break

    # Final check
    print("\n=== Final Status ===")
    active_scans = get_all_active_scans()
    print(f"Final active scans: {len(active_scans)}")

print("=== Test Complete ===")
