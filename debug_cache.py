#!/usr/bin/env python
"""Debug script to check cache contents"""

import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ebook_manager.settings")
django.setup()

from django.core.cache import cache

print("=" * 60)
print("CACHE DEBUG")
print("=" * 60)

# Check active scan job IDs
job_ids = cache.get("active_scan_job_ids", [])
print(f"\nActive job IDs: {job_ids}")
print(f"Number of active jobs: {len(job_ids)}")

# Check progress for each job
if job_ids:
    print("\n" + "-" * 60)
    print("PROGRESS DATA FOR EACH JOB:")
    print("-" * 60)
    for job_id in job_ids:
        progress_key = f"scan_progress_{job_id}"
        progress_data = cache.get(progress_key)
        print(f"\nJob ID: {job_id}")
        if progress_data:
            for key, value in progress_data.items():
                print(f"  {key}: {value}")
        else:
            print("  NO PROGRESS DATA FOUND")
else:
    print("\nNo active jobs in cache")

print("\n" + "=" * 60)
