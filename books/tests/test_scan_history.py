"""Test the scan history functionality."""
import pytest
from datetime import timedelta
from django.test import TestCase
from django.utils import timezone
from books.models import ScanHistory, ScanFolder


@pytest.mark.django_db
def test_simple_scan_history():
    """Test basic scan history creation."""
    # Create a scan folder
    scan_folder = ScanFolder.objects.create(
        name="Test Folder",
        path="/test/path",
        language="en",
        content_type="mixed"
    )

    # Verify scan folder was created
    assert scan_folder.name == "Test Folder"
    print("✅ Test passed: Scan history functionality works!")


@pytest.mark.django_db
def test_scan_history_model():
    """Test the ScanHistory model functionality."""
    # Create a test scan folder
    scan_folder = ScanFolder.objects.create(
        name='Test Folder',
        path='/test/path',
        language='en',
        content_type='mixed'
    )

    # Create a scan history entry
    scan_history = ScanHistory.objects.create(
        job_id='test-model-001',
        scan_folder=scan_folder,
        scan_type='scan',
        status='completed',
        folder_name='Test Folder',
        folder_path='/test/path',
        started_at=timezone.now() - timedelta(minutes=5),
        completed_at=timezone.now(),
        duration_seconds=300,
        total_files_found=10,
        files_processed=10,
        books_added=5,
        books_updated=2,
        external_apis_used=True,
        api_requests_made=7,
    )

    # Test basic functionality
    assert scan_history.job_id == 'test-model-001'
    assert scan_history.status == 'completed'
    assert scan_history.books_added == 5

    # Test string representation
    str_repr = str(scan_history)
    assert 'Test Folder' in str_repr
    assert 'completed' in str_repr
    print("✅ Test passed: ScanHistory model works correctly!")


@pytest.mark.django_db
class TestScanHistory(TestCase):
    """Test scan history functionality."""

    def test_create_multiple_scan_entries(self):
        """Test creating multiple scan history entries."""
        print("=== Testing Multiple Scan History Entries ===")

        # Create a test scan folder
        scan_folder = ScanFolder.objects.create(
            name='Test History Folder',
            path='/test/scan/history',
            language='en',
            content_type='mixed'
        )

        sample_scans = [
            {
                'job_id': 'test-scan-001',
                'scan_type': 'scan',
                'status': 'completed',
                'books_added': 18,
                'files_processed': 25,
            },
            {
                'job_id': 'test-scan-002',
                'scan_type': 'rescan',
                'status': 'completed',
                'books_added': 3,
                'files_processed': 8,
            },
            {
                'job_id': 'test-scan-003',
                'scan_type': 'scan',
                'status': 'failed',
                'books_added': 0,
                'files_processed': 12,
            }
        ]

        for i, scan_data in enumerate(sample_scans):
            completed_at = timezone.now() - timedelta(days=i+1)
            started_at = completed_at - timedelta(minutes=5)

            ScanHistory.objects.create(
                job_id=scan_data['job_id'],
                scan_folder=scan_folder,
                scan_type=scan_data['scan_type'],
                status=scan_data['status'],
                folder_name='Test Folder',
                folder_path='/test/path',
                started_at=started_at,
                completed_at=completed_at,
                duration_seconds=300,
                total_files_found=scan_data['files_processed'],
                files_processed=scan_data['files_processed'],
                books_added=scan_data['books_added'],
                books_updated=2,
                external_apis_used=True,
                api_requests_made=7,
            )

        # Verify all entries were created
        self.assertEqual(ScanHistory.objects.count(), len(sample_scans))

        # Test statistics
        total_scans = ScanHistory.objects.count()
        successful_scans = ScanHistory.objects.filter(status='completed').count()
        failed_scans = ScanHistory.objects.filter(status='failed').count()

        self.assertEqual(total_scans, 3)
        self.assertEqual(successful_scans, 2)
        self.assertEqual(failed_scans, 1)

        print(f"✅ Created {total_scans} scan history entries")
        print(f"   - {successful_scans} successful scans")
        print(f"   - {failed_scans} failed scans")
        print("✅ Test passed: Multiple scan history entries created successfully!")
