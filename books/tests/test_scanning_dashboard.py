"""
Tests for scanning dashboard functionality
"""

import os
import tempfile
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from books.models import ScanFolder, UserProfile
from books.tests.test_helpers import create_test_book_with_file


class ScanningDashboardTests(TestCase):
    """Test scanning dashboard view and functionality"""

    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass123")
        self.client = Client()

        # Create temporary directories for testing
        self.temp_dir1 = tempfile.mkdtemp()
        self.temp_dir2 = tempfile.mkdtemp()

        # Create test scan folders with books
        self.folder1 = ScanFolder.objects.create(name="Test Folder 1", path=self.temp_dir1, language="en", is_active=True)

        self.folder2 = ScanFolder.objects.create(name="Test Folder 2", path=self.temp_dir2, language="fr", is_active=True)

        # Create test books in folders
        self.book1 = create_test_book_with_file(file_path=os.path.join(self.temp_dir1, "book1.epub"), file_format="epub", file_size=1024, scan_folder=self.folder1)

        self.book2 = create_test_book_with_file(file_path=os.path.join(self.temp_dir1, "book2.epub"), file_format="epub", file_size=2048, scan_folder=self.folder1)

        self.book3 = create_test_book_with_file(file_path=os.path.join(self.temp_dir2, "book3.pdf"), file_format="pdf", file_size=3072, scan_folder=self.folder2)

    def tearDown(self):
        """Clean up temporary directories"""
        import shutil

        try:
            shutil.rmtree(self.temp_dir1)
            shutil.rmtree(self.temp_dir2)
        except (OSError, FileNotFoundError):
            pass  # Directories might not exist or already be deleted

    def test_scanning_dashboard_requires_login(self):
        """Test that scanning dashboard requires authentication"""
        response = self.client.get(reverse("books:scan_dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_scanning_dashboard_loads_successfully(self):
        """Test that scanning dashboard loads for authenticated users"""
        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("books:scan_dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Scanning Control Center")
        self.assertContains(response, "Quick Scan Actions")

    @patch("books.scanner.background.get_all_active_scans")
    @patch("books.scanner.rate_limiting.get_api_status")
    @patch("books.scanner.rate_limiting.check_api_health")
    def test_scanning_dashboard_context_data(self, mock_api_health, mock_api_status, mock_active_scans):
        """Test that scanning dashboard provides correct context data"""
        # Mock the scanner functions
        mock_active_scans.return_value = [{"job_id": "test-job-1", "status": "Running", "percentage": 50, "details": "Processing books..."}]

        mock_api_status.return_value = {"google_books": {"api_name": "Google Books", "rate_limits": {"limits": {"daily": 1000}, "current_counts": {"daily": 100}}}}

        mock_api_health.return_value = {"google_books": True}

        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("books:scan_dashboard"))

        # Check context data
        self.assertEqual(response.context["page_title"], "Scanning Dashboard")
        self.assertIn("active_scans", response.context)
        self.assertIn("api_status", response.context)
        self.assertIn("recent_folders", response.context)

    def test_scanning_dashboard_book_count_annotation(self):
        """Test that book counts are correctly annotated in scan folders"""
        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("books:scan_dashboard"))

        folders = response.context["recent_folders"]

        # Check that folders have book_count annotation
        folder1_data = next((f for f in folders if f.id == self.folder1.id), None)
        folder2_data = next((f for f in folders if f.id == self.folder2.id), None)

        self.assertIsNotNone(folder1_data)
        self.assertIsNotNone(folder2_data)

        self.assertEqual(folder1_data.book_count, 2)
        self.assertEqual(folder2_data.book_count, 1)

    def test_scanning_dashboard_displays_book_counts(self):
        """Test that book counts are displayed in the template"""
        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("books:scan_dashboard"))

        # Check that book counts appear in the HTML
        self.assertContains(response, "2</td>")  # folder1 has 2 books
        self.assertContains(response, "1</td>")  # folder2 has 1 book

        # Check folder names are displayed
        self.assertContains(response, "Test Folder 1")
        self.assertContains(response, "Test Folder 2")

    def test_scanning_dashboard_last_scanned_display(self):
        """Test that last scanned information is displayed correctly"""
        # Update one folder to have a last_scanned date
        import datetime

        from django.utils import timezone

        self.folder1.last_scanned = timezone.now() - datetime.timedelta(hours=2)
        self.folder1.save()

        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("books:scan_dashboard"))

        # Should show "X hours ago" for folder1 and "Never" for folder2
        self.assertContains(response, "hours ago")
        self.assertContains(response, "Never")

    def test_scanning_dashboard_rescan_dropdown_book_counts(self):
        """Test that rescan dropdown shows correct book counts"""
        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("books:scan_dashboard"))

        # Check that rescan dropdown options show book counts
        self.assertContains(response, "Test Folder 1 (2 books)")
        self.assertContains(response, "Test Folder 2 (1 book)")

    @patch("books.views.scanning.get_all_active_scans")
    def test_scanning_dashboard_active_scans_display(self, mock_active_scans):
        """Test that active scans are displayed correctly"""
        mock_active_scans.return_value = [{"job_id": "test-job-123", "status": "Running", "percentage": 75, "details": "Processing book 15 of 20"}]

        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("books:scan_dashboard"))

        self.assertContains(response, "test-job-123")
        self.assertContains(response, "Running")
        self.assertContains(response, "75%")
        self.assertContains(response, "Processing book 15 of 20")

    @patch("books.views.scanning.get_all_active_scans")
    def test_scanning_dashboard_no_active_scans(self, mock_active_scans):
        """Test dashboard with no active scans"""
        mock_active_scans.return_value = []

        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("books:scan_dashboard"))

        # Check that no active scans are displayed (container will be empty)
        self.assertNotContains(response, "scan-card")

    def test_scanning_dashboard_no_folders(self):
        """Test dashboard with no scan folders"""
        # Delete all folders
        ScanFolder.objects.all().delete()

        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("books:scan_dashboard"))

        self.assertContains(response, "No scan folders found")

    @patch("books.views.scanning.get_api_status")
    @patch("books.views.scanning.check_api_health")
    def test_scanning_dashboard_api_status_display(self, mock_api_health, mock_api_status):
        """Test that API status information is displayed correctly"""
        mock_api_status.return_value = {
            "google_books": {"api_name": "Google Books", "rate_limits": {"limits": {"daily": 1000, "hourly": 100}, "current_counts": {"daily": 250, "hourly": 15}}},
            "comic_vine": {"api_name": "Comic Vine", "rate_limits": {"limits": {"hourly": 200}, "current_counts": {"hourly": 45}}},
        }

        mock_api_health.return_value = {"google_books": True, "comic_vine": False}

        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("books:scan_dashboard"))

        # Check API names are displayed
        self.assertContains(response, "Google Books")
        self.assertContains(response, "Comic Vine")

        # Check rate limit information - mocked values are displayed
        self.assertContains(response, "250/1000")  # Google Books daily limit (from mock)
        self.assertContains(response, "15/100")  # Google Books hourly limit (from mock)
        self.assertContains(response, "45/200")  # Comic Vine hourly limit (from mock)


class ThemePreviewTests(TestCase):
    """Test theme preview functionality"""

    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass123")
        self.client = Client()

    def test_preview_theme_requires_login(self):
        """Test that theme preview requires authentication"""
        response = self.client.post(reverse("books:preview_theme"), {"theme": "darkly"})
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_preview_theme_requires_post(self):
        """Test that theme preview only accepts POST requests"""
        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("books:preview_theme"))
        self.assertEqual(response.status_code, 405)  # Method not allowed

    def test_preview_theme_success(self):
        """Test successful theme preview"""
        self.client.login(username="testuser", password="testpass123")
        response = self.client.post(reverse("books:preview_theme"), {"theme": "darkly"})

        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertTrue(data["success"])
        self.assertEqual(data["theme"], "darkly")
        self.assertIn("Theme preview set to darkly", data["message"])

    def test_preview_theme_missing_parameter(self):
        """Test theme preview with missing theme parameter"""
        self.client.login(username="testuser", password="testpass123")
        response = self.client.post(reverse("books:preview_theme"), {})

        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertFalse(data["success"])
        self.assertEqual(data["error"], "Theme parameter required")

    def test_preview_theme_invalid_theme(self):
        """Test theme preview with invalid theme"""
        self.client.login(username="testuser", password="testpass123")
        response = self.client.post(reverse("books:preview_theme"), {"theme": "invalid-theme"})

        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertFalse(data["success"])
        self.assertEqual(data["error"], "Invalid theme")

    def test_preview_theme_sets_session(self):
        """Test that theme preview sets session variable"""
        self.client.login(username="testuser", password="testpass123")
        response = self.client.post(reverse("books:preview_theme"), {"theme": "darkly"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.session["preview_theme"], "darkly")

    def test_clear_theme_preview_requires_login(self):
        """Test that clear theme preview requires authentication"""
        response = self.client.post(reverse("books:clear_theme_preview"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_clear_theme_preview_requires_post(self):
        """Test that clear theme preview only accepts POST requests"""
        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("books:clear_theme_preview"))
        self.assertEqual(response.status_code, 405)  # Method not allowed

    def test_clear_theme_preview_success(self):
        """Test successful theme preview clearing"""
        # Set up session with preview theme
        session = self.client.session
        session["preview_theme"] = "darkly"
        session.save()

        self.client.login(username="testuser", password="testpass123")
        response = self.client.post(reverse("books:clear_theme_preview"))

        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertTrue(data["success"])
        self.assertEqual(data["message"], "Preview cleared")

        # Check that session variable is cleared
        self.assertNotIn("preview_theme", self.client.session)

    def test_clear_theme_preview_returns_user_theme(self):
        """Test that clear theme preview returns user's actual theme"""
        # Create user profile with custom theme
        profile = UserProfile.get_or_create_for_user(self.user)
        profile.theme = "cosmo"
        profile.save()

        # Set preview theme in session
        session = self.client.session
        session["preview_theme"] = "darkly"
        session.save()

        self.client.login(username="testuser", password="testpass123")
        response = self.client.post(reverse("books:clear_theme_preview"))

        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertTrue(data["success"])
        self.assertEqual(data["theme"], "cosmo")

    def test_clear_theme_preview_no_session(self):
        """Test clear theme preview when no preview theme in session"""
        self.client.login(username="testuser", password="testpass123")
        response = self.client.post(reverse("books:clear_theme_preview"))

        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertTrue(data["success"])
        self.assertEqual(data["message"], "Preview cleared")


class ScanningDashboardIntegrationTests(TestCase):
    """Integration tests for scanning dashboard functionality"""

    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass123")
        self.client = Client()

    @patch("books.views.scanning.get_all_active_scans")
    @patch("books.views.scanning.get_api_status")
    @patch("books.views.scanning.check_api_health")
    def test_full_dashboard_functionality(self, mock_api_health, mock_api_status, mock_active_scans):
        """Test complete dashboard functionality with all components"""
        # Create temporary directories for testing
        temp_dir1 = tempfile.mkdtemp()
        temp_dir2 = tempfile.mkdtemp()

        try:
            # Create scan folders with varying book counts
            folder1 = ScanFolder.objects.create(name="Fiction", path=temp_dir1, language="en")

            folder2 = ScanFolder.objects.create(name="Non-Fiction", path=temp_dir2, language="en")

            # Create books
            for i in range(5):
                create_test_book_with_file(file_path=os.path.join(temp_dir1, f"book{i}.epub"), file_format="epub", file_size=1024 * (i + 1), scan_folder=folder1)

            for i in range(3):
                create_test_book_with_file(file_path=os.path.join(temp_dir2, f"book{i}.pdf"), file_format="pdf", file_size=2048 * (i + 1), scan_folder=folder2)

            # Mock scanner responses
            mock_active_scans.return_value = [{"job_id": "scan-fiction", "status": "Running", "percentage": 60, "details": "Processing fiction books..."}]

            mock_api_status.return_value = {"google_books": {"api_name": "Google Books", "rate_limits": {"limits": {"daily": 1000}, "current_counts": {"daily": 150}}}}

            mock_api_health.return_value = {"google_books": True}

            self.client.login(username="testuser", password="testpass123")
            response = self.client.get(reverse("books:scan_dashboard"))

            # Verify response
            self.assertEqual(response.status_code, 200)

            # Check folder display with correct book counts
            self.assertContains(response, "Fiction")
            self.assertContains(response, "Non-Fiction")

            # Check active scan display (job ID and progress from mock)
            self.assertContains(response, "scan-fiction")
            self.assertContains(response, "60%")

            # Check API status
            self.assertContains(response, "Google Books")

        finally:
            # Clean up temporary directories
            import shutil

            try:
                shutil.rmtree(temp_dir1)
                shutil.rmtree(temp_dir2)
            except (OSError, FileNotFoundError):
                pass
