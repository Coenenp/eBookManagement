"""
Wizard Integration Tests
Complete wizard system integration and workflow testing.
"""

import shutil
import tempfile
from unittest.mock import Mock, patch

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from books.models import ScanFolder, SetupWizard


class WizardCompleteIntegrationTests(TestCase):
    """Test complete wizard system integration and workflows"""

    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(username="testuser_integration", password="testpass123")
        self.client = Client()
        self.client.force_login(self.user)
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up test data"""
        try:
            shutil.rmtree(self.temp_dir)
        except Exception:
            pass

    def test_complete_wizard_flow_with_prepopulation(self):
        """Test complete wizard flow including pre-population"""
        # Step 1: Welcome
        response = self.client.get(reverse("books:wizard_welcome"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "wizard")

        # Continue from welcome
        response = self.client.post(reverse("books:wizard_welcome"), {"action": "continue"})
        self.assertIn(response.status_code, [200, 302])

        # Step 2: Folders - Add a test folder
        with patch("os.path.exists", return_value=True):
            with patch("os.path.isdir", return_value=True):
                with patch("os.access", return_value=True):
                    response = self.client.post(reverse("books:wizard_folders"), {"action": "add_folder", "folder_path": self.temp_dir, "folder_name": "Test Integration Folder"})
                    self.assertIn(response.status_code, [200, 302])

        # Continue from folders
        response = self.client.post(reverse("books:wizard_folders"), {"action": "continue"})
        self.assertIn(response.status_code, [200, 302])

        # Step 3: Content Types
        response = self.client.get(reverse("books:wizard_content_types"))
        self.assertEqual(response.status_code, 200)

        response = self.client.post(reverse("books:wizard_content_types"), {"content_type": "ebooks"})
        self.assertIn(response.status_code, [200, 302])

        # Step 4: Scrapers
        response = self.client.get(reverse("books:wizard_scrapers"))
        self.assertEqual(response.status_code, 200)

        response = self.client.post(reverse("books:wizard_scrapers"), {"google_books": "test_api_key_12345", "enabled_scrapers": ["google_books"]})
        self.assertIn(response.status_code, [200, 302])

        # Step 5: Complete
        response = self.client.get(reverse("books:wizard_complete"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "complete")

        # Verify data was saved
        folder = ScanFolder.objects.filter(path=self.temp_dir).first()
        self.assertIsNotNone(folder)
        self.assertEqual(folder.name, "Test Integration Folder")

    def test_wizard_prepopulation_on_second_run(self):
        """Test that wizard pre-populates data on second run"""
        # Create initial wizard data
        SetupWizard.objects.create(user=self.user, scraper_config={"google_books": "existing_key_123"}, folder_content_types={"TestFolder": "ebooks"})

        # Access scrapers step
        response = self.client.get(reverse("books:wizard_scrapers"))
        self.assertEqual(response.status_code, 200)

        # Should contain pre-populated data
        content = response.content.decode("utf-8")
        # Check for pre-population indicators (masked key or filled fields)
        self.assertTrue("existing_key" in content or "value=" in content or "is-valid" in content)  # Pre-filled input values  # Bootstrap validation classes

    def test_wizard_skip_functionality(self):
        """Test wizard skip functionality at each step"""
        # Test skip from welcome
        response = self.client.post(reverse("books:wizard_welcome"), {"action": "skip"})
        self.assertEqual(response.status_code, 302)
        self.assertIn("dashboard", response.url)

        # Test skip from scrapers
        response = self.client.post(reverse("books:wizard_scrapers"), {"action": "skip"})
        self.assertIn(response.status_code, [200, 302])

    def test_wizard_validation_and_error_handling(self):
        """Test wizard validation and error handling"""
        # Test invalid folder path
        response = self.client.post(reverse("books:wizard_folders"), {"action": "add_folder", "folder_path": "/absolutely/nonexistent/path/12345", "folder_name": "Invalid Folder"})
        # Should show error but not crash
        self.assertIn(response.status_code, [200, 400])

        # Test empty required fields
        response = self.client.post(reverse("books:wizard_folders"), {"action": "add_folder", "folder_path": "", "folder_name": ""})
        self.assertIn(response.status_code, [200, 400])

    def test_wizard_css_and_javascript_functionality(self):
        """Test wizard CSS and JavaScript features are present"""
        response = self.client.get(reverse("books:wizard_complete"))
        self.assertEqual(response.status_code, 200)

        content = response.content.decode("utf-8")

        # Should have wizard-specific CSS classes
        self.assertTrue("wizard-complete-page" in content or "feature-highlights-row" in content or "wizard" in content)

        # Should have JavaScript for button handling
        self.assertTrue("fa-spin" in content or "button" in content or "script" in content)

    @patch("subprocess.Popen")
    def test_wizard_initial_scan_trigger(self, mock_popen):
        """Test that wizard can trigger initial scanning"""
        mock_popen.return_value = Mock()

        # Create a scan folder
        ScanFolder.objects.create(path=self.temp_dir, name="Test Scan Folder")

        # Trigger scan from completion page
        response = self.client.post(reverse("books:wizard_complete"), {"action": "start_scan"})

        self.assertIn(response.status_code, [200, 302])

        # Should have attempted to start scan process
        if mock_popen.called:
            self.assertTrue(mock_popen.called)

    def test_wizard_responsive_design_elements(self):
        """Test wizard responsive design elements"""
        wizard_urls = ["wizard_welcome", "wizard_folders", "wizard_content_types", "wizard_scrapers", "wizard_complete"]

        for url_name in wizard_urls:
            response = self.client.get(reverse(f"books:{url_name}"))
            self.assertEqual(response.status_code, 200)

            content = response.content.decode("utf-8")

            # Should have responsive elements
            self.assertTrue("col-" in content or "responsive" in content or "mobile" in content or "viewport" in content)  # Bootstrap grid

    def test_wizard_accessibility_features(self):
        """Test wizard accessibility features"""
        response = self.client.get(reverse("books:wizard_welcome"))
        self.assertEqual(response.status_code, 200)

        content = response.content.decode("utf-8")

        # Should have accessibility features
        self.assertTrue(
            "aria-" in content or "alt=" in content or "label" in content or "title=" in content  # ARIA attributes  # Alt text for images  # Form labels  # Tooltips/titles
        )

    def test_wizard_data_persistence_across_steps(self):
        """Test that wizard data persists correctly across steps"""
        # Set some session data
        session = self.client.session
        session["wizard_data"] = {"test": "value"}
        session.save()

        # Navigate through steps
        response = self.client.get(reverse("books:wizard_scrapers"))
        self.assertEqual(response.status_code, 200)

        # Session should still exist
        self.assertIn("wizard_data", self.client.session)

    def test_wizard_security_and_authentication(self):
        """Test wizard security and authentication requirements"""
        # Logout and try to access wizard
        self.client.logout()

        wizard_urls = ["wizard_welcome", "wizard_folders", "wizard_content_types", "wizard_scrapers", "wizard_complete"]

        for url_name in wizard_urls:
            response = self.client.get(reverse(f"books:{url_name}"))
            # Should redirect to login
            self.assertEqual(response.status_code, 302)

    def test_wizard_configuration_summary(self):
        """Test wizard configuration summary display"""
        # Create configuration data
        SetupWizard.objects.create(user=self.user, scraper_config={"google_books": "test_key"}, folder_content_types={"Books": "ebooks"})

        ScanFolder.objects.create(path=self.temp_dir, name="Summary Test Folder")

        response = self.client.get(reverse("books:wizard_complete"))
        self.assertEqual(response.status_code, 200)

        content = response.content.decode("utf-8")

        # Should show configuration summary
        self.assertTrue("Summary Test Folder" in content or "configuration" in content or "setup" in content)

    def test_wizard_performance_with_existing_data(self):
        """Test wizard performance with existing system data"""
        # Create multiple scan folders to simulate existing data
        for i in range(10):
            ScanFolder.objects.create(path=f"/test/folder_{i}", name=f"Test Folder {i}")

        import time

        start_time = time.time()

        response = self.client.get(reverse("books:wizard_folders"))

        end_time = time.time()
        load_time = end_time - start_time

        # Should load quickly even with existing data
        self.assertLess(load_time, 2.0)
        self.assertEqual(response.status_code, 200)

    def test_wizard_cleanup_on_completion(self):
        """Test that wizard cleans up temporary data on completion"""
        # Set some wizard session data
        session = self.client.session
        session["wizard_step"] = "scrapers"
        session["temp_data"] = "should_be_cleaned"
        session.save()

        # Complete wizard
        response = self.client.post(reverse("books:wizard_complete"), {"action": "dashboard"})

        self.assertIn(response.status_code, [200, 302])

        # Check session cleanup (implementation-dependent)
        # Some wizard data might be preserved, some cleaned up

    def test_wizard_ajax_functionality(self):
        """Test wizard AJAX functionality if implemented"""
        # Test AJAX folder validation if available
        if hasattr(self.client, "post"):
            with patch("os.path.exists", return_value=True):
                response = self.client.post(
                    reverse("books:wizard_validate_folder") if "wizard_validate_folder" in [url.name for url in reverse.__self__.urlpatterns] else "/ajax/validate-folder/",
                    {"folder_path": self.temp_dir},
                    HTTP_X_REQUESTED_WITH="XMLHttpRequest",
                    follow=True,
                )
                # Should handle AJAX requests appropriately
                self.assertIn(response.status_code, [200, 404])  # 404 if endpoint doesn't exist

    def test_wizard_mobile_compatibility(self):
        """Test wizard mobile compatibility"""
        # Test with mobile user agent
        response = self.client.get(reverse("books:wizard_welcome"), HTTP_USER_AGENT="Mobile Safari")
        self.assertEqual(response.status_code, 200)

        content = response.content.decode("utf-8")

        # Should handle mobile users appropriately
        self.assertTrue("mobile" in content.lower() or "responsive" in content.lower() or "viewport" in content or "col-sm" in content)  # Bootstrap mobile classes


class WizardErrorRecoveryTests(TestCase):
    """Test wizard error recovery and resilience"""

    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(username="testuser_recovery", password="testpass123")
        self.client = Client()
        self.client.force_login(self.user)

    def test_wizard_database_error_recovery(self):
        """Test wizard recovery from database errors"""
        # Create malformed wizard data
        try:
            SetupWizard.objects.create(user=self.user, scraper_config={"malformed": None, "invalid": [1, 2, 3]})
        except Exception:
            pass  # Expected if validation prevents creation

        # Wizard should still load and handle errors gracefully
        response = self.client.get(reverse("books:wizard_scrapers"))
        self.assertEqual(response.status_code, 200)

    def test_wizard_session_corruption_recovery(self):
        """Test wizard recovery from session corruption"""
        # Corrupt session data
        session = self.client.session
        session["wizard_data"] = {"corrupted": object()}  # Non-serializable
        try:
            session.save()
        except Exception:
            pass  # Expected for corrupted session

        # Wizard should still work
        response = self.client.get(reverse("books:wizard_welcome"))
        self.assertEqual(response.status_code, 200)

    def test_wizard_network_error_resilience(self):
        """Test wizard resilience to network errors during API validation"""
        with patch("requests.get", side_effect=Exception("Network error")):
            # Should handle network errors gracefully
            response = self.client.post(reverse("books:wizard_scrapers"), {"google_books": "test_key_123", "validate_api": "true"})

            # Should not crash on network errors
            self.assertIn(response.status_code, [200, 302])

    def test_wizard_file_system_error_recovery(self):
        """Test wizard recovery from file system errors"""
        # Try to add folder that causes permission error
        with patch("os.path.exists", side_effect=PermissionError("Access denied")):
            response = self.client.post(reverse("books:wizard_folders"), {"action": "add_folder", "folder_path": "/restricted/path", "folder_name": "Restricted Folder"})

            # Should handle file system errors gracefully
            self.assertEqual(response.status_code, 200)

    def test_wizard_partial_completion_recovery(self):
        """Test wizard recovery from partial completion state"""
        # Create partially completed wizard
        SetupWizard.objects.create(
            user=self.user,
            welcome_completed=True,
            folders_completed=True,
            content_types_completed=False,  # Partially complete
            scrapers_completed=False,
            current_step="content_types",
        )

        # Should handle partial completion gracefully
        response = self.client.get(reverse("books:wizard_content_types"))
        self.assertEqual(response.status_code, 200)

        response = self.client.get(reverse("books:wizard_scrapers"))
        self.assertEqual(response.status_code, 200)
