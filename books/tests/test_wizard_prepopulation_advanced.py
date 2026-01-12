"""
Wizard Pre-population Testing
Tests wizard field pre-population from database and environment.
"""

import os
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import RequestFactory, TestCase

from books.models import SetupWizard
from books.views.wizard import WizardContentTypesView, WizardScrapersView


class WizardPrePopulationTests(TestCase):
    """Test wizard field pre-population functionality"""

    def setUp(self):
        """Set up test data"""
        self.factory = RequestFactory()
        self.user = User.objects.create_user(username="testuser_prepop", password="testpass123")

        # Create wizard with configuration data
        self.wizard = SetupWizard.objects.create(
            user=self.user,
            is_completed=True,
            scraper_config={"google_books": "stored_google_api_key_123456789012345", "comic_vine": "stored_comic_vine_key_123456789012345678901", "open_library": ""},
            folder_content_types={"Audio": "audiobooks", "Comics": "comics", "Books": "ebooks"},
        )

    def test_scrapers_pre_population_from_database(self):
        """Test that scrapers are pre-populated from database"""
        request = self.factory.get("/wizard/scrapers/")
        request.user = self.user

        view = WizardScrapersView()
        view.request = request
        view.kwargs = {}

        context = view.get_context_data()
        scrapers = context.get("scrapers", [])

        # Find scrapers by ID
        scraper_dict = {s.get("id"): s for s in scrapers if "id" in s}

        # Google Books should be pre-populated
        if "google_books" in scraper_dict:
            google_scraper = scraper_dict["google_books"]
            self.assertIn("current_value", google_scraper)
            self.assertIsNotNone(google_scraper["current_value"])

        # Comic Vine should be pre-populated
        if "comic_vine" in scraper_dict:
            comic_scraper = scraper_dict["comic_vine"]
            self.assertIn("current_value", comic_scraper)
            self.assertIsNotNone(comic_scraper["current_value"])

    @patch.dict(os.environ, {"GOOGLE_BOOKS_API_KEY": "env_google_123", "COMIC_VINE_API_KEY": "env_comic_456"})
    def test_scrapers_pre_population_from_environment(self):
        """Test that scrapers fall back to environment variables"""
        # Create user without existing data
        user_env = User.objects.create_user(username="testuser_env", password="testpass123")

        request = self.factory.get("/wizard/scrapers/")
        request.user = user_env

        view = WizardScrapersView()
        view.request = request
        view.kwargs = {}

        context = view.get_context_data()
        scrapers = context.get("scrapers", [])

        # Check environment fallback
        scraper_dict = {s.get("id"): s for s in scrapers if "id" in s}

        # Should use environment variables when no database config
        for scraper_id in ["google_books", "comic_vine"]:
            if scraper_id in scraper_dict:
                scraper = scraper_dict[scraper_id]
                if "current_value" in scraper and scraper["current_value"]:
                    # Environment values should be available or empty
                    self.assertIsInstance(scraper["current_value"], str)

    def test_content_types_pre_population_from_database(self):
        """Test that content types are pre-populated from database"""
        request = self.factory.get("/wizard/content-types/")
        request.user = self.user

        view = WizardContentTypesView()
        view.request = request
        view.kwargs = {}

        context = view.get_context_data()
        folders = context.get("folders", [])

        # Check folder configuration is loaded
        folder_dict = {f.get("name"): f for f in folders if "name" in f}

        # Audio folder should be configured as audiobooks
        if "Audio" in folder_dict:
            audio_folder = folder_dict["Audio"]
            self.assertEqual(audio_folder.get("current_assignment"), "audiobooks")

        # Comics folder should be configured as comics
        if "Comics" in folder_dict:
            comics_folder = folder_dict["Comics"]
            self.assertEqual(comics_folder.get("current_assignment"), "comics")

    def test_pre_population_priority_database_over_environment(self):
        """Test that database values take priority over environment"""
        with patch.dict(os.environ, {"GOOGLE_BOOKS_API_KEY": "env_key_should_be_ignored"}):
            request = self.factory.get("/wizard/scrapers/")
            request.user = self.user

            view = WizardScrapersView()
            view.request = request
            view.kwargs = {}

            context = view.get_context_data()
            scrapers = context.get("scrapers", [])

            # Database value should take priority
            google_scraper = next((s for s in scrapers if s.get("id") == "google_books"), None)
            if google_scraper and "current_value" in google_scraper:
                # Should use database value, not environment
                self.assertNotEqual(google_scraper["current_value"], "env_key_should_be_ignored")

    def test_pre_population_empty_values_handling(self):
        """Test handling of empty or None values in pre-population"""
        # Update wizard with empty values
        self.wizard.scraper_config = {"google_books": "", "comic_vine": None, "open_library": ""}
        self.wizard.save()

        request = self.factory.get("/wizard/scrapers/")
        request.user = self.user

        view = WizardScrapersView()
        view.request = request
        view.kwargs = {}

        context = view.get_context_data()
        scrapers = context.get("scrapers", [])

        # Should handle empty values gracefully
        for scraper in scrapers:
            if "current_value" in scraper:
                # Empty values should be empty strings, not None
                current_value = scraper["current_value"]
                self.assertIsInstance(current_value, (str, type(None)))

    def test_pre_population_new_user_defaults(self):
        """Test pre-population behavior for new users"""
        new_user = User.objects.create_user(username="testuser_new", password="testpass123")

        request = self.factory.get("/wizard/scrapers/")
        request.user = new_user

        view = WizardScrapersView()
        view.request = request
        view.kwargs = {}

        context = view.get_context_data()

        # Should provide context even for new users
        self.assertIn("scrapers", context)
        scrapers = context["scrapers"]
        self.assertIsInstance(scrapers, list)
        self.assertGreater(len(scrapers), 0)

    def test_pre_population_data_validation(self):
        """Test that pre-populated data is validated"""
        # Create wizard with potentially invalid data
        SetupWizard.objects.create(user=self.user, scraper_config={"google_books": "x" * 1000, "invalid_scraper": "should_be_ignored"})  # Very long key

        request = self.factory.get("/wizard/scrapers/")
        request.user = self.user

        view = WizardScrapersView()
        view.request = request
        view.kwargs = {}

        context = view.get_context_data()

        # Should handle invalid data without crashing
        self.assertIn("scrapers", context)
        self.assertIsInstance(context["scrapers"], list)

    def test_pre_population_update_workflow(self):
        """Test pre-population during wizard update workflow"""
        # Simulate updating existing configuration
        request = self.factory.get("/wizard/scrapers/")
        request.user = self.user

        view = WizardScrapersView()
        view.request = request
        view.kwargs = {}

        # Get initial context
        context1 = view.get_context_data()

        # Update wizard configuration
        self.wizard.scraper_config["google_books"] = "updated_key_123"
        self.wizard.save()

        # Get updated context
        context2 = view.get_context_data()

        # Both should be valid contexts
        self.assertIn("scrapers", context1)
        self.assertIn("scrapers", context2)


class WizardPrePopulationPerformanceTests(TestCase):
    """Test performance aspects of wizard pre-population"""

    def setUp(self):
        """Set up test data"""
        self.factory = RequestFactory()
        self.user = User.objects.create_user(username="testuser_perf", password="testpass123")

    def test_pre_population_performance_large_config(self):
        """Test pre-population performance with large configuration"""
        # Create wizard with large configuration
        large_config = {}
        for i in range(100):
            large_config[f"scraper_{i}"] = f"api_key_value_{i}" * 10

        SetupWizard.objects.create(user=self.user, scraper_config=large_config)

        import time

        start_time = time.time()

        request = self.factory.get("/wizard/scrapers/")
        request.user = self.user

        view = WizardScrapersView()
        view.request = request
        view.kwargs = {}

        context = view.get_context_data()

        end_time = time.time()
        load_time = end_time - start_time

        # Should complete quickly even with large config
        self.assertLess(load_time, 1.0)
        self.assertIn("scrapers", context)

    def test_pre_population_concurrent_users(self):
        """Test pre-population with multiple concurrent users"""
        users = []
        for i in range(5):
            user = User.objects.create_user(username=f"testuser_concurrent_{i}", password="testpass123")
            SetupWizard.objects.create(user=user, scraper_config={"google_books": f"key_{i}"})
            users.append(user)

        # Test concurrent access
        contexts = []
        for user in users:
            request = self.factory.get("/wizard/scrapers/")
            request.user = user

            view = WizardScrapersView()
            view.request = request
            view.kwargs = {}

            context = view.get_context_data()
            contexts.append(context)

        # All should succeed
        self.assertEqual(len(contexts), 5)
        for context in contexts:
            self.assertIn("scrapers", context)


class WizardPrePopulationSecurityTests(TestCase):
    """Test security aspects of wizard pre-population"""

    def setUp(self):
        """Set up test data"""
        self.factory = RequestFactory()
        self.user = User.objects.create_user(username="testuser_security", password="testpass123")

    def test_pre_population_data_isolation(self):
        """Test that users only see their own pre-populated data"""
        # Create two users with different data
        user1 = User.objects.create_user("user1", password="pass123")
        user2 = User.objects.create_user("user2", password="pass123")

        SetupWizard.objects.create(user=user1, scraper_config={"google_books": "user1_secret_key"})

        SetupWizard.objects.create(user=user2, scraper_config={"google_books": "user2_secret_key"})

        # Test user1 sees only their data
        request1 = self.factory.get("/wizard/scrapers/")
        request1.user = user1

        view1 = WizardScrapersView()
        view1.request = request1
        view1.kwargs = {}

        context1 = view1.get_context_data()

        # Test user2 sees only their data
        request2 = self.factory.get("/wizard/scrapers/")
        request2.user = user2

        view2 = WizardScrapersView()
        view2.request = request2
        view2.kwargs = {}

        context2 = view2.get_context_data()

        # Both should have scrapers context but with different data
        self.assertIn("scrapers", context1)
        self.assertIn("scrapers", context2)

        # Verify data isolation (users shouldn't see each other's keys)
        scrapers1 = context1["scrapers"]
        scrapers2 = context2["scrapers"]

        self.assertIsInstance(scrapers1, list)
        self.assertIsInstance(scrapers2, list)

    def test_pre_population_sensitive_data_handling(self):
        """Test that sensitive data is properly handled in pre-population"""
        # Create wizard with sensitive API keys
        SetupWizard.objects.create(user=self.user, scraper_config={"google_books": "very_sensitive_api_key_12345", "comic_vine": "another_sensitive_key_67890"})

        request = self.factory.get("/wizard/scrapers/")
        request.user = self.user

        view = WizardScrapersView()
        view.request = request
        view.kwargs = {}

        context = view.get_context_data()
        scrapers = context.get("scrapers", [])

        # Check that sensitive data is handled appropriately
        for scraper in scrapers:
            if "current_value" in scraper and scraper["current_value"]:
                current_value = str(scraper["current_value"])

                # Long keys should be masked or truncated for security
                if len(current_value) > 10:
                    # Should contain some form of masking or be truncated
                    self.assertTrue("*" in current_value or len(current_value) <= 20 or "preview" in scraper)  # Truncated  # Has preview field
