"""
Test cases for active scans functionality
"""

from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase

from books.scanner.background import ScanProgress, add_active_scan, get_all_active_scans


class ActiveScansTests(TestCase):
    """Test cases for active scans tracking functionality"""

    def setUp(self):
        """Set up test data"""
        # Clear any existing active scans
        cache.delete('active_scan_job_ids')

    def tearDown(self):
        """Clean up after tests"""
        cache.delete('active_scan_job_ids')
        # Clean up any progress data from tests
        job_ids = ["test-job-123", "test-job-456", "job-1", "job-2", "job-3", "duplicate-job", "timeout-test-job"]
        for job_id in job_ids:
            cache.delete(f"scan_progress_{job_id}")

    def test_empty_active_scans_initially(self):
        """Test that initially there are no active scans"""
        active_scans = get_all_active_scans()
        self.assertEqual(len(active_scans), 0)

    def test_add_active_scan(self):
        """Test adding a job ID to active scans"""
        test_job_id = "test-job-123"

        # Add the job ID
        add_active_scan(test_job_id)

        # Check if it appears in cache
        job_ids = cache.get('active_scan_job_ids', [])
        self.assertIn(test_job_id, job_ids)

    def test_get_active_scans_with_job(self):
        """Test getting active scans after adding a job"""
        test_job_id = "test-job-456"

        # Add the job ID
        add_active_scan(test_job_id)

        # Create progress data for the job (this is what get_all_active_scans() actually looks for)
        progress = ScanProgress(test_job_id)
        progress.update(0, 100, "Starting", "Test scan in progress")

        # Get active scans
        active_scans = get_all_active_scans()
        self.assertEqual(len(active_scans), 1)
        self.assertEqual(active_scans[0]['job_id'], test_job_id)
        self.assertEqual(active_scans[0]['status'], "Starting")

    def test_multiple_active_scans(self):
        """Test handling multiple active scans"""
        job_ids = ["job-1", "job-2", "job-3"]

        # Add multiple jobs and create progress data for each
        for i, job_id in enumerate(job_ids):
            add_active_scan(job_id)
            progress = ScanProgress(job_id)
            progress.update(i * 10, 100, f"Processing {i+1}", f"Test scan {i+1} in progress")

        # Check all are tracked in cache
        cached_ids = cache.get('active_scan_job_ids', [])
        for job_id in job_ids:
            self.assertIn(job_id, cached_ids)

        # Get active scans
        active_scans = get_all_active_scans()
        self.assertEqual(len(active_scans), 3)

        # Verify each scan has correct data
        returned_job_ids = [scan['job_id'] for scan in active_scans]
        for job_id in job_ids:
            self.assertIn(job_id, returned_job_ids)

    def test_duplicate_job_ids_not_added(self):
        """Test that duplicate job IDs are not added twice"""
        test_job_id = "duplicate-job"

        # Add the same job ID twice
        add_active_scan(test_job_id)
        add_active_scan(test_job_id)

        # Should only appear once in cache
        job_ids = cache.get('active_scan_job_ids', [])
        self.assertEqual(job_ids.count(test_job_id), 1)

    def test_cache_timeout_handling(self):
        """Test that cache timeout is properly set"""
        test_job_id = "timeout-test-job"

        with patch('django.core.cache.cache.set') as mock_set:
            add_active_scan(test_job_id)

            # Verify cache.set was called with timeout
            mock_set.assert_called()
            args, kwargs = mock_set.call_args
            self.assertIn('timeout', kwargs)
            self.assertEqual(kwargs['timeout'], 3600)  # 1 hour timeout

    def test_completed_scans_filtered_out(self):
        """Test that completed scans are not returned as active"""
        active_job_id = "active-scan"
        completed_job_id = "completed-scan"

        # Add both jobs
        add_active_scan(active_job_id)
        add_active_scan(completed_job_id)

        # Create progress for active job
        active_progress = ScanProgress(active_job_id)
        active_progress.update(50, 100, "Processing", "Active scan in progress")

        # Create completed progress for second job
        completed_progress = ScanProgress(completed_job_id)
        completed_progress.complete(True, "Scan completed successfully")

        # Get active scans - should only return the active one
        active_scans = get_all_active_scans()
        self.assertEqual(len(active_scans), 1)
        self.assertEqual(active_scans[0]['job_id'], active_job_id)

        # Verify the completed scan is not included
        returned_job_ids = [scan['job_id'] for scan in active_scans]
        self.assertNotIn(completed_job_id, returned_job_ids)
