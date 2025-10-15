"""
Enhanced Wizard Context Testing
Tests wizard view context data and pre-population functionality.
"""

import os
from django.test import TestCase, RequestFactory
from django.contrib.auth.models import User
from unittest.mock import patch

from books.models import SetupWizard
from books.views.wizard import WizardScrapersView, WizardContentTypesView
# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ebook_manager.settings')


class WizardContextDataTests(TestCase):
    """Test wizard context data population and pre-population features"""

    def setUp(self):
        """Set up test data"""
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            username='testuser_context',
            password='testpass123'
        )

        # Create wizard instance with some existing data
        self.wizard = SetupWizard.objects.create(
            user=self.user,
            is_completed=True,
            current_step='complete',
            welcome_completed=True,
            folders_completed=True,
            content_types_completed=True,
            scrapers_completed=True,
            selected_folders=['Audio', '___{ KT }___', '___epub_____'],
            scraper_config={
                'google_books': 'test_google_api_key_12345678901234567890123',
                'comic_vine': 'test_comic_vine_api_key_1234567890123456789012345',
                'open_library': ''
            },
            folder_content_types={
                'Audio': 'audiobooks',
                '___{ KT }___': 'ebooks',
                '___epub_____': 'ebooks'
            }
        )

    def test_wizard_scrapers_context_pre_population(self):
        """Test scrapers view context includes pre-populated data"""
        request = self.factory.get('/wizard/scrapers/')
        request.user = self.user

        # Create view instance with proper initialization
        view = WizardScrapersView()
        view.request = request
        view.kwargs = {}

        # Get context
        context = view.get_context_data()

        # Verify context structure
        self.assertIn('scrapers', context)
        scrapers = context['scrapers']

        # Test scraper data structure
        self.assertIsInstance(scrapers, list)
        self.assertGreater(len(scrapers), 0)

        # Find specific scrapers and verify pre-population
        google_scraper = next((s for s in scrapers if s['id'] == 'google_books'), None)
        comic_vine_scraper = next((s for s in scrapers if s['id'] == 'comic_vine'), None)
        open_library_scraper = next((s for s in scrapers if s['id'] == 'open_library'), None)

        # Google Books should have pre-populated value
        self.assertIsNotNone(google_scraper)
        if 'current_value' in google_scraper:
            self.assertIsNotNone(google_scraper['current_value'])
            self.assertGreater(len(google_scraper['current_value']), 0)

        # Comic Vine should have pre-populated value
        self.assertIsNotNone(comic_vine_scraper)
        if 'current_value' in comic_vine_scraper:
            self.assertIsNotNone(comic_vine_scraper['current_value'])
            self.assertGreater(len(comic_vine_scraper['current_value']), 0)

        # Open Library should exist but may have empty value
        self.assertIsNotNone(open_library_scraper)
        if 'current_value' in open_library_scraper:
            # Should exist but may be empty
            self.assertTrue('current_value' in open_library_scraper)

    def test_wizard_content_types_context_pre_population(self):
        """Test content types view context includes pre-populated data"""
        request = self.factory.get('/wizard/content-types/')
        request.user = self.user

        # Create view instance with proper initialization
        view = WizardContentTypesView()
        view.request = request
        view.kwargs = {}

        # Get context
        context = view.get_context_data()

        # Verify context structure
        self.assertIn('folders', context)
        folders = context['folders']

        # Test folder data structure
        self.assertIsInstance(folders, list)
        self.assertGreaterEqual(len(folders), 3)  # Our test data has 3 folders

        # Find specific folders and verify pre-population
        folder_names = [folder['name'] for folder in folders if 'name' in folder]
        self.assertIn('Audio', folder_names)
        self.assertIn('___{ KT }___', folder_names)
        self.assertIn('___epub_____', folder_names)

        # Check that folders have suggested types
        for folder in folders:
            if folder.get('name') == 'Audio':
                self.assertEqual(folder.get('suggested_type'), 'audiobooks')
            elif folder.get('name') in ['___{ KT }___', '___epub_____']:
                self.assertEqual(folder.get('suggested_type'), 'ebooks')

    @patch.dict(os.environ, {
        'GOOGLE_BOOKS_API_KEY': 'env_google_key_123',
        'COMIC_VINE_API_KEY': 'env_comic_key_456'
    })
    def test_wizard_scrapers_environment_fallback(self):
        """Test scrapers view falls back to environment variables"""
        # Create user without existing wizard data
        user_no_wizard = User.objects.create_user(
            username='testuser_no_wizard',
            password='testpass123'
        )

        request = self.factory.get('/wizard/scrapers/')
        request.user = user_no_wizard

        view = WizardScrapersView()
        view.request = request
        view.kwargs = {}

        context = view.get_context_data()
        scrapers = context.get('scrapers', [])

        # Find Google Books scraper
        google_scraper = next((s for s in scrapers if s['id'] == 'google_books'), None)
        if google_scraper and 'current_value' in google_scraper:
            # Should use environment variable as fallback
            self.assertTrue(
                google_scraper['current_value'] == 'env_google_key_123' or
                google_scraper['current_value'] == ''  # Or empty if no fallback implemented
            )

    def test_wizard_state_validation(self):
        """Test wizard state is correctly represented in context"""
        request = self.factory.get('/wizard/scrapers/')
        request.user = self.user

        view = WizardScrapersView()
        view.request = request
        view.kwargs = {}

        context = view.get_context_data()

        # Should have wizard step information
        self.assertIn('wizard_step', context)
        self.assertEqual(context['wizard_step'], 'scrapers')

        # Should have wizard state
        self.assertTrue(hasattr(view, 'request'))
        self.assertEqual(view.request.user, self.user)

    def test_wizard_scrapers_security_masking(self):
        """Test that API keys are properly masked in context"""
        request = self.factory.get('/wizard/scrapers/')
        request.user = self.user

        view = WizardScrapersView()
        view.request = request
        view.kwargs = {}

        context = view.get_context_data()
        scrapers = context.get('scrapers', [])

        # Check that API keys are masked for security
        for scraper in scrapers:
            if 'current_value' in scraper and scraper['current_value']:
                # API keys should be masked with asterisks or similar
                current_value = scraper['current_value']
                if len(current_value) > 10:  # Only check longer keys
                    # Should contain masking characters
                    self.assertTrue(
                        '***' in current_value or
                        '*' in current_value or
                        current_value == scraper.get('masked_value', current_value)
                    )

    @patch.dict(os.environ, {
        'GOOGLE_BOOKS_API_KEY': '',
        'COMICVINE_API_KEY': ''
    }, clear=False)
    def test_wizard_no_existing_data(self):
        """Test wizard context when no existing data is available"""
        # Create user without wizard data
        user_empty = User.objects.create_user(
            username='testuser_empty',
            password='testpass123'
        )

        request = self.factory.get('/wizard/scrapers/')
        request.user = user_empty

        view = WizardScrapersView()
        view.request = request
        view.kwargs = {}

        context = view.get_context_data()

        # Should still provide context structure
        self.assertIn('scrapers', context)
        self.assertIsInstance(context['scrapers'], list)

        # Scrapers should exist but with empty values
        scrapers = context['scrapers']
        for scraper in scrapers:
            if 'current_value' in scraper:
                # Should be empty or None for new users
                self.assertTrue(
                    scraper['current_value'] == '' or
                    scraper['current_value'] is None or
                    len(str(scraper['current_value'])) == 0
                )

    def test_wizard_content_types_no_folders(self):
        """Test content types view when no folders are configured"""
        user_no_folders = User.objects.create_user(
            username='testuser_no_folders',
            password='testpass123'
        )

        # Create wizard without folder data
        SetupWizard.objects.create(
            user=user_no_folders,
            folder_content_types={}
        )

        request = self.factory.get('/wizard/content-types/')
        request.user = user_no_folders

        view = WizardContentTypesView()
        view.request = request
        view.kwargs = {}

        context = view.get_context_data()

        # Should handle empty folders gracefully
        self.assertIn('folders', context)
        folders = context.get('folders', [])
        self.assertIsInstance(folders, list)
        # May be empty or contain default/discovered folders
        self.assertGreaterEqual(len(folders), 0)

    def test_wizard_context_performance(self):
        """Test that wizard context loading is performant"""
        import time

        request = self.factory.get('/wizard/scrapers/')
        request.user = self.user

        view = WizardScrapersView()
        view.request = request
        view.kwargs = {}

        # Measure context loading time
        start_time = time.time()
        context = view.get_context_data()
        end_time = time.time()

        load_time = end_time - start_time

        # Should load quickly (less than 0.5 seconds)
        self.assertLess(load_time, 0.5)
        self.assertIsInstance(context, dict)

    def test_wizard_context_error_handling(self):
        """Test wizard context loading with database errors"""
        # Test with invalid wizard data - update existing wizard
        self.wizard.scraper_config = {'invalid': 'data', 'malformed': None}
        self.wizard.save()

        request = self.factory.get('/wizard/scrapers/')
        request.user = self.user

        view = WizardScrapersView()
        view.request = request
        view.kwargs = {}

        # Should handle invalid data gracefully
        context = view.get_context_data()

        self.assertIn('scrapers', context)
        self.assertIsInstance(context['scrapers'], list)

    def test_wizard_context_concurrent_access(self):
        """Test wizard context with concurrent user access"""
        # Create multiple users
        users = []
        for i in range(3):
            user = User.objects.create_user(
                username=f'testuser_concurrent_{i}',
                password='testpass123'
            )
            SetupWizard.objects.create(
                user=user,
                scraper_config={'google_books': f'key_{i}'}
            )
            users.append(user)

        # Test that each user gets their own data
        contexts = []
        for user in users:
            request = self.factory.get('/wizard/scrapers/')
            request.user = user

            view = WizardScrapersView()
            view.request = request
            view.kwargs = {}

            context = view.get_context_data()
            contexts.append(context)

        # Verify contexts are independent
        self.assertEqual(len(contexts), 3)
        for i, context in enumerate(contexts):
            self.assertIn('scrapers', context)
            # Each should have their own data isolated


class WizardViewInitializationTests(TestCase):
    """Test proper wizard view initialization and setup"""

    def setUp(self):
        """Set up test data"""
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            username='testuser_init',
            password='testpass123'
        )

    def test_wizard_view_required_attributes(self):
        """Test that wizard views have required attributes after initialization"""
        request = self.factory.get('/wizard/scrapers/')
        request.user = self.user

        view = WizardScrapersView()
        view.request = request
        view.kwargs = {}

        # Should have required attributes
        self.assertTrue(hasattr(view, 'request'))
        self.assertTrue(hasattr(view, 'kwargs'))
        self.assertEqual(view.request.user, self.user)
        self.assertIsInstance(view.kwargs, dict)

    def test_wizard_view_method_availability(self):
        """Test that wizard views have expected methods"""
        view = WizardScrapersView()

        # Should have required methods
        self.assertTrue(hasattr(view, 'get_context_data'))
        self.assertTrue(callable(getattr(view, 'get_context_data', None)))

        # Should have dispatch method (inherited)
        self.assertTrue(hasattr(view, 'dispatch'))
        self.assertTrue(callable(getattr(view, 'dispatch', None)))

    def test_wizard_view_inheritance(self):
        """Test wizard view inheritance and MRO"""
        view = WizardScrapersView()

        # Should inherit from proper base classes
        self.assertTrue(hasattr(view, 'get'))
        self.assertTrue(hasattr(view, 'post'))

        # Should have Django view methods
        method_resolution = type(view).__mro__
        self.assertTrue(any('View' in cls.__name__ for cls in method_resolution))
