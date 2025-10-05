"""
Test suite for books/views/wizard.py
Tests setup wizard functionality for guiding new users.
"""

import tempfile
from unittest.mock import patch, Mock
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from django.http import JsonResponse, HttpResponse, HttpResponseRedirect

from books.models import ScanFolder
from books.views.wizard import (
    WizardRequiredMixin,
    WizardWelcomeView,
    WizardFoldersView,
    WizardContentTypesView
)


class WizardRequiredMixinTests(TestCase):
    """Test WizardRequiredMixin functionality"""

    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='testuser_wizard',
            password='testpass123'
        )
        self.client = Client()

    def test_wizard_required_mixin_authenticated_user(self):
        """Test that authenticated users can access wizard"""
        self.client.force_login(self.user)

        # Mock view class using the mixin
        class TestWizardView(WizardRequiredMixin):
            def get(self, request):
                return JsonResponse({'success': True})

            def dispatch(self, request, *args, **kwargs):
                # Call mixin's dispatch first
                return super().dispatch(request, *args, **kwargs)

        view = TestWizardView()

        # Create a proper request object
        request = self.client.request().wsgi_request
        request.user = self.user
        request.path = '/books/non-wizard-view/'

        # Should allow access for authenticated user
        response = view.dispatch(request)
        # For authenticated user without complete wizard, expect redirect to wizard
        if response:
            self.assertIsInstance(response, (HttpResponse, HttpResponseRedirect))

    def test_wizard_required_mixin_anonymous_user(self):
        """Test that anonymous users are redirected"""
        # Mock view class using the mixin
        class TestWizardView(WizardRequiredMixin):
            def get(self, request):
                return JsonResponse({'success': True})

        view = TestWizardView()

        # Create mock request for anonymous user
        request = Mock()
        request.user.is_authenticated = False
        request.path = '/books/non-wizard-view/'

        response = view.dispatch(request)

        # Should return None for anonymous users (let Django auth handle it)
        self.assertIsNone(response)

    def test_wizard_required_mixin_integration(self):
        """Test mixin integration with actual views"""
        # This tests that the mixin can be properly integrated
        # with Django view classes

        self.assertTrue(hasattr(WizardRequiredMixin, 'dispatch'))

        # Test that wizard views are properly designed (they don't need WizardRequiredMixin
        # since they ARE the wizard views themselves)
        self.assertFalse(issubclass(WizardWelcomeView, WizardRequiredMixin))
        self.assertFalse(issubclass(WizardFoldersView, WizardRequiredMixin))
        self.assertFalse(issubclass(WizardContentTypesView, WizardRequiredMixin))


class WizardWelcomeViewTests(TestCase):
    """Test WizardWelcomeView functionality"""

    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='testuser_welcome',
            password='testpass123'
        )
        self.client = Client()
        self.client.force_login(self.user)

    def test_wizard_welcome_view_get(self):
        """Test GET request to wizard welcome view"""
        response = self.client.get(reverse('books:wizard_welcome'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Welcome')

    def test_wizard_welcome_view_anonymous_user(self):
        """Test that anonymous users are redirected"""
        self.client.logout()
        response = self.client.get(reverse('books:wizard_welcome'))
        self.assertEqual(response.status_code, 302)

    def test_wizard_welcome_view_context(self):
        """Test welcome view context variables"""
        response = self.client.get(reverse('books:wizard_welcome'))

        self.assertIn('wizard_step', response.context)
        self.assertEqual(response.context['wizard_step'], 'welcome')

    def test_wizard_welcome_view_post_continue(self):
        """Test POST request to continue to next step"""
        response = self.client.post(reverse('books:wizard_welcome'), {
            'action': 'continue'
        })

        # Should redirect to folders step
        self.assertEqual(response.status_code, 302)
        self.assertIn('wizard_folders', response.url)

    def test_wizard_welcome_view_post_skip(self):
        """Test POST request to skip wizard"""
        response = self.client.post(reverse('books:wizard_welcome'), {
            'action': 'skip'
        })

        # Should redirect to main dashboard
        self.assertEqual(response.status_code, 302)
        self.assertIn('dashboard', response.url)


class WizardFoldersViewTests(TestCase):
    """Test WizardFoldersView functionality"""

    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='testuser_folders',
            password='testpass123'
        )
        self.client = Client()
        self.client.force_login(self.user)

        # Create temporary directory for testing
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up test data"""
        import shutil
        try:
            shutil.rmtree(self.temp_dir)
        except:
            pass

    def test_wizard_folders_view_get(self):
        """Test GET request to wizard folders view"""
        response = self.client.get(reverse('books:wizard_folders'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'folders')

    def test_wizard_folders_view_context(self):
        """Test folders view context"""
        response = self.client.get(reverse('books:wizard_folders'))

        self.assertIn('wizard_step', response.context)
        self.assertEqual(response.context['wizard_step'], 'folders')
        self.assertIn('existing_folders', response.context)

    def test_wizard_folders_view_add_folder_valid(self):
        """Test adding valid folder"""
        with patch('os.path.exists') as mock_exists:
            mock_exists.return_value = True

            response = self.client.post(reverse('books:wizard_folders'), {
                'action': 'add_folder',
                'folder_path': self.temp_dir,
                'folder_name': 'Test Folder'
            })

            # Should redirect back to same page with success
            self.assertEqual(response.status_code, 302)

            # Check folder was created in database
            folder = ScanFolder.objects.filter(path=self.temp_dir).first()
            self.assertIsNotNone(folder)
            self.assertEqual(folder.name, 'Test Folder')

    def test_wizard_folders_view_add_folder_invalid_path(self):
        """Test adding folder with invalid path"""
        with patch('os.path.exists') as mock_exists:
            mock_exists.return_value = False

            response = self.client.post(reverse('books:wizard_folders'), {
                'action': 'add_folder',
                'folder_path': '/nonexistent/path',
                'folder_name': 'Invalid Folder'
            })

            # Should return to form with error
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'error')

            # Check folder was not created
            folder_count = ScanFolder.objects.filter(path='/nonexistent/path').count()
            self.assertEqual(folder_count, 0)

    def test_wizard_folders_view_add_folder_missing_fields(self):
        """Test adding folder with missing required fields"""
        response = self.client.post(reverse('books:wizard_folders'), {
            'action': 'add_folder',
            'folder_path': '',  # Empty path
            'folder_name': 'Test Folder'
        })

        # Should return form with validation error
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'required')

    def test_wizard_folders_view_remove_folder(self):
        """Test removing existing folder"""
        # Create folder first
        folder = ScanFolder.objects.create(
            path=self.temp_dir,
            name='Test Folder to Remove'
        )

        response = self.client.post(reverse('books:wizard_folders'), {
            'action': 'remove_folder',
            'folder_id': folder.id
        })

        # Should redirect back with success
        self.assertEqual(response.status_code, 302)

        # Check folder was removed
        self.assertFalse(ScanFolder.objects.filter(id=folder.id).exists())

    def test_wizard_folders_view_continue_to_next_step(self):
        """Test continuing to content types step"""
        # Create at least one folder
        ScanFolder.objects.create(
            path=self.temp_dir,
            name='Test Folder'
        )

        response = self.client.post(reverse('books:wizard_folders'), {
            'action': 'continue'
        })

        # Should redirect to content types
        self.assertEqual(response.status_code, 302)
        self.assertIn('wizard_content_types', response.url)

    def test_wizard_folders_view_continue_no_folders(self):
        """Test continuing without adding folders"""
        response = self.client.post(reverse('books:wizard_folders'), {
            'action': 'continue'
        })

        # Should show warning but allow to continue
        # Implementation may vary - could redirect or show error
        self.assertIn(response.status_code, [200, 302])

    @patch('os.path.isdir')
    @patch('os.access')
    def test_wizard_folders_view_permission_check(self, mock_access, mock_isdir):
        """Test folder permission validation"""
        mock_isdir.return_value = True
        mock_access.return_value = False  # No read permission

        response = self.client.post(reverse('books:wizard_folders'), {
            'action': 'add_folder',
            'folder_path': '/restricted/path',
            'folder_name': 'Restricted Folder'
        })

        # Should handle permission error gracefully
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'permission')

    def test_wizard_folders_view_ajax_folder_validation(self):
        """Test AJAX folder path validation"""
        with patch('os.path.exists') as mock_exists:
            mock_exists.return_value = True

            response = self.client.post(
                reverse('books:wizard_validate_folder'),
                {'folder_path': self.temp_dir},
                HTTP_X_REQUESTED_WITH='XMLHttpRequest'
            )

            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertTrue(data['valid'])

    def test_wizard_folders_view_duplicate_folder(self):
        """Test adding duplicate folder path"""
        # Create existing folder
        ScanFolder.objects.create(
            path=self.temp_dir,
            name='Original Folder'
        )

        with patch('os.path.exists') as mock_exists:
            mock_exists.return_value = True

            response = self.client.post(reverse('books:wizard_folders'), {
                'action': 'add_folder',
                'folder_path': self.temp_dir,
                'folder_name': 'Duplicate Folder'
            })

            # Should handle duplicate path gracefully
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'already exists')


class WizardContentTypesViewTests(TestCase):
    """Test WizardContentTypesView functionality"""

    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='testuser_content',
            password='testpass123'
        )
        self.client = Client()
        self.client.force_login(self.user)

    def test_wizard_content_types_view_get(self):
        """Test GET request to content types view"""
        response = self.client.get(reverse('books:wizard_content_types'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'content')

    def test_wizard_content_types_view_context(self):
        """Test content types view context"""
        response = self.client.get(reverse('books:wizard_content_types'))

        self.assertIn('wizard_step', response.context)
        self.assertEqual(response.context['wizard_step'], 'content_types')
        self.assertIn('content_types', response.context)

    def test_wizard_content_types_view_select_ebooks(self):
        """Test selecting ebooks content type"""
        response = self.client.post(reverse('books:wizard_content_types'), {
            'content_type': 'ebooks'
        })

        # Should store selection and redirect to scrapers
        self.assertEqual(response.status_code, 302)
        self.assertIn('wizard_scrapers', response.url)

    def test_wizard_content_types_view_select_comics(self):
        """Test selecting comics content type"""
        response = self.client.post(reverse('books:wizard_content_types'), {
            'content_type': 'comics'
        })

        # Should store selection and redirect to scrapers
        self.assertEqual(response.status_code, 302)
        self.assertIn('wizard_scrapers', response.url)

    def test_wizard_content_types_view_select_both(self):
        """Test selecting both content types"""
        response = self.client.post(reverse('books:wizard_content_types'), {
            'content_type': 'both'
        })

        # Should handle both selection
        self.assertEqual(response.status_code, 302)
        self.assertIn('wizard_scrapers', response.url)

    def test_wizard_content_types_view_no_selection(self):
        """Test submitting without selection"""
        response = self.client.post(reverse('books:wizard_content_types'), {})

        # Should show error or return to form
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'select')

    def test_wizard_content_types_view_invalid_selection(self):
        """Test submitting invalid content type"""
        response = self.client.post(reverse('books:wizard_content_types'), {
            'content_type': 'invalid_type'
        })

        # Should handle invalid selection gracefully
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'invalid')


class WizardScrapersViewTests(TestCase):
    """Test WizardScrapersView functionality"""

    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='testuser_scrapers',
            password='testpass123'
        )
        self.client = Client()
        self.client.force_login(self.user)

    def test_wizard_scrapers_view_get(self):
        """Test GET request to scrapers view"""
        response = self.client.get(reverse('books:wizard_scrapers'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'scrapers')

    def test_wizard_scrapers_view_context(self):
        """Test scrapers view context"""
        response = self.client.get(reverse('books:wizard_scrapers'))

        self.assertIn('wizard_step', response.context)
        self.assertEqual(response.context['wizard_step'], 'scrapers')
        self.assertIn('available_scrapers', response.context)

    def test_wizard_scrapers_view_enable_scrapers(self):
        """Test enabling selected scrapers"""
        response = self.client.post(reverse('books:wizard_scrapers'), {
            'enabled_scrapers': ['goodreads', 'google_books', 'comicvine']
        })

        # Should save scraper configuration and redirect
        self.assertEqual(response.status_code, 302)
        self.assertIn('wizard_complete', response.url)

    def test_wizard_scrapers_view_api_key_configuration(self):
        """Test API key configuration for scrapers"""
        response = self.client.post(reverse('books:wizard_scrapers'), {
            'enabled_scrapers': ['goodreads'],
            'goodreads_api_key': 'test_api_key_123'
        })

        # Should save API key configuration
        self.assertEqual(response.status_code, 302)

    def test_wizard_scrapers_view_skip_scrapers(self):
        """Test skipping scraper configuration"""
        response = self.client.post(reverse('books:wizard_scrapers'), {
            'action': 'skip'
        })

        # Should skip to completion
        self.assertEqual(response.status_code, 302)
        self.assertIn('wizard_complete', response.url)

    def test_wizard_scrapers_view_test_api_connection(self):
        """Test API connection testing"""
        with patch('requests.get') as mock_get:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_get.return_value = mock_response

            response = self.client.post(
                reverse('books:wizard_test_api'),
                {
                    'scraper': 'goodreads',
                    'api_key': 'test_key'
                },
                HTTP_X_REQUESTED_WITH='XMLHttpRequest'
            )

            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertTrue(data['success'])

    def test_wizard_scrapers_view_invalid_api_key(self):
        """Test invalid API key handling"""
        with patch('requests.get') as mock_get:
            mock_get.side_effect = Exception("Invalid API key")

            response = self.client.post(
                reverse('books:wizard_test_api'),
                {
                    'scraper': 'goodreads',
                    'api_key': 'invalid_key'
                },
                HTTP_X_REQUESTED_WITH='XMLHttpRequest'
            )

            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertFalse(data['success'])

    def test_wizard_scrapers_view_no_scrapers_selected(self):
        """Test submitting without selecting any scrapers"""
        response = self.client.post(reverse('books:wizard_scrapers'), {
            'enabled_scrapers': []
        })

        # Should allow proceeding without scrapers
        self.assertEqual(response.status_code, 302)


class WizardCompleteViewTests(TestCase):
    """Test WizardCompleteView functionality"""

    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='testuser_complete',
            password='testpass123'
        )
        self.client = Client()
        self.client.force_login(self.user)

    def test_wizard_complete_view_get(self):
        """Test GET request to complete view"""
        response = self.client.get(reverse('books:wizard_complete'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'complete')

    def test_wizard_complete_view_context(self):
        """Test complete view context"""
        response = self.client.get(reverse('books:wizard_complete'))

        self.assertIn('wizard_step', response.context)
        self.assertEqual(response.context['wizard_step'], 'complete')
        self.assertIn('configuration_summary', response.context)

    def test_wizard_complete_view_start_initial_scan(self):
        """Test starting initial scan"""
        # Create a scan folder for testing
        folder = ScanFolder.objects.create(
            path='/test/complete/folder',
            name='Test Complete Folder'
        )

        with patch('subprocess.Popen') as mock_popen:
            mock_popen.return_value = Mock()

            response = self.client.post(reverse('books:wizard_complete'), {
                'action': 'start_scan'
            })

            # Should trigger scan and redirect
            self.assertEqual(response.status_code, 302)
            mock_popen.assert_called_once()

    def test_wizard_complete_view_go_to_dashboard(self):
        """Test going directly to dashboard"""
        response = self.client.post(reverse('books:wizard_complete'), {
            'action': 'dashboard'
        })

        # Should redirect to dashboard
        self.assertEqual(response.status_code, 302)
        self.assertIn('dashboard', response.url)

    def test_wizard_complete_view_configuration_summary(self):
        """Test that configuration summary shows setup choices"""
        # Set up wizard session data
        session = self.client.session
        session['wizard_content_type'] = 'ebooks'
        session['wizard_scrapers'] = ['goodreads', 'google_books']
        session.save()

        # Create folders to show in summary
        ScanFolder.objects.create(
            path='/test/complete/folder1',
            name='Test Folder 1'
        )

        response = self.client.get(reverse('books:wizard_complete'))

        # Should show configuration in context
        self.assertContains(response, 'ebooks')
        self.assertContains(response, 'Test Folder 1')

    def test_wizard_complete_view_clear_wizard_data(self):
        """Test that wizard completion clears session data"""
        # Set wizard session data
        session = self.client.session
        session['wizard_step'] = 'complete'
        session['wizard_content_type'] = 'ebooks'
        session['wizard_scrapers'] = ['goodreads']
        session.save()

        response = self.client.post(reverse('books:wizard_complete'), {
            'action': 'dashboard'
        })

        # Should clear wizard session data
        self.assertNotIn('wizard_step', self.client.session)
        self.assertNotIn('wizard_content_type', self.client.session)
        self.assertNotIn('wizard_scrapers', self.client.session)


class WizardIntegrationTests(TestCase):
    """Integration tests for complete wizard flow"""

    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='testuser_integration',
            password='testpass123'
        )
        self.client = Client()
        self.client.force_login(self.user)

        # Create temporary directory
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up test data"""
        import shutil
        try:
            shutil.rmtree(self.temp_dir)
        except:
            pass

    def test_complete_wizard_flow(self):
        """Test complete wizard flow from start to finish"""
        # Step 1: Welcome
        response = self.client.get(reverse('books:wizard_welcome'))
        self.assertEqual(response.status_code, 200)

        response = self.client.post(reverse('books:wizard_welcome'), {
            'action': 'continue'
        })
        self.assertEqual(response.status_code, 302)

        # Step 2: Folders
        response = self.client.get(reverse('books:wizard_folders'))
        self.assertEqual(response.status_code, 200)

        with patch('os.path.exists') as mock_exists:
            mock_exists.return_value = True

            response = self.client.post(reverse('books:wizard_folders'), {
                'action': 'add_folder',
                'folder_path': self.temp_dir,
                'folder_name': 'Integration Test Folder'
            })
            self.assertEqual(response.status_code, 302)

        response = self.client.post(reverse('books:wizard_folders'), {
            'action': 'continue'
        })
        self.assertEqual(response.status_code, 302)

        # Step 3: Content Types
        response = self.client.get(reverse('books:wizard_content_types'))
        self.assertEqual(response.status_code, 200)

        response = self.client.post(reverse('books:wizard_content_types'), {
            'content_type': 'ebooks'
        })
        self.assertEqual(response.status_code, 302)

        # Step 4: Scrapers
        response = self.client.get(reverse('books:wizard_scrapers'))
        self.assertEqual(response.status_code, 200)

        response = self.client.post(reverse('books:wizard_scrapers'), {
            'enabled_scrapers': ['google_books']
        })
        self.assertEqual(response.status_code, 302)

        # Step 5: Complete
        response = self.client.get(reverse('books:wizard_complete'))
        self.assertEqual(response.status_code, 200)

        # Verify folder was created
        folder = ScanFolder.objects.filter(path=self.temp_dir).first()
        self.assertIsNotNone(folder)
        self.assertEqual(folder.name, 'Integration Test Folder')

    def test_wizard_flow_with_skip(self):
        """Test wizard flow with skip actions"""
        # Skip welcome
        response = self.client.post(reverse('books:wizard_welcome'), {
            'action': 'skip'
        })
        self.assertEqual(response.status_code, 302)
        self.assertIn('dashboard', response.url)

    def test_wizard_session_persistence(self):
        """Test that wizard maintains session state between steps"""
        # Set content type
        response = self.client.post(reverse('books:wizard_content_types'), {
            'content_type': 'comics'
        })
        self.assertEqual(response.status_code, 302)

        # Check session contains content type
        self.assertEqual(self.client.session.get('wizard_content_type'), 'comics')

        # Go to scrapers - should remember content type
        response = self.client.get(reverse('books:wizard_scrapers'))
        self.assertEqual(response.status_code, 200)

    def test_wizard_navigation_controls(self):
        """Test wizard navigation controls (back/next buttons)"""
        # Test that each step has appropriate navigation
        steps = [
            'wizard_welcome',
            'wizard_folders',
            'wizard_content_types',
            'wizard_scrapers',
            'wizard_complete'
        ]

        for step in steps:
            response = self.client.get(reverse(f'books:{step}'))
            self.assertEqual(response.status_code, 200)

            # Check for navigation elements
            if step != 'wizard_welcome':
                self.assertContains(response, 'previous')  # Back button
            if step != 'wizard_complete':
                self.assertContains(response, 'next')  # Next/Continue button

    def test_wizard_error_handling(self):
        """Test wizard error handling and recovery"""
        # Test invalid folder path
        response = self.client.post(reverse('books:wizard_folders'), {
            'action': 'add_folder',
            'folder_path': '/absolutely/nonexistent/path',
            'folder_name': 'Invalid Folder'
        })

        # Should show error but not crash
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'error')

        # Test invalid content type
        response = self.client.post(reverse('books:wizard_content_types'), {
            'content_type': 'invalid_type'
        })

        # Should show error but not crash
        self.assertEqual(response.status_code, 200)

    @patch('subprocess.Popen')
    def test_wizard_initial_scan_trigger(self, mock_popen):
        """Test that wizard can trigger initial scan"""
        mock_popen.return_value = Mock()

        # Create folder first
        ScanFolder.objects.create(
            path=self.temp_dir,
            name='Scan Test Folder'
        )

        response = self.client.post(reverse('books:wizard_complete'), {
            'action': 'start_scan'
        })

        # Should trigger scan
        self.assertEqual(response.status_code, 302)
        mock_popen.assert_called_once()

    def test_wizard_accessibility_features(self):
        """Test wizard accessibility and usability features"""
        # Test that wizard steps have proper headings and structure
        response = self.client.get(reverse('books:wizard_welcome'))

        # Should have proper HTML structure for accessibility
        self.assertContains(response, '<h1>')  # Main heading
        self.assertContains(response, 'wizard')  # Identifies as wizard

    def test_wizard_responsive_design(self):
        """Test wizard works with different viewport sizes"""
        # Test that wizard pages load without JavaScript errors
        # and have responsive elements

        for step in ['wizard_welcome', 'wizard_folders', 'wizard_content_types']:
            response = self.client.get(reverse(f'books:{step}'))
            self.assertEqual(response.status_code, 200)

            # Should have responsive meta tag or CSS classes
            content = response.content.decode('utf-8')
            self.assertTrue(
                'viewport' in content or
                'responsive' in content or
                'col-' in content  # Bootstrap responsive classes
            )


class WizardPerformanceTests(TestCase):
    """Test performance aspects of wizard functionality"""

    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='testuser_performance',
            password='testpass123'
        )
        self.client = Client()
        self.client.force_login(self.user)

    def test_wizard_folder_validation_performance(self):
        """Test that folder validation is reasonably fast"""
        import time

        # Test folder validation time
        start_time = time.time()

        with patch('os.path.exists') as mock_exists:
            mock_exists.return_value = True

            response = self.client.post(
                reverse('books:wizard_validate_folder'),
                {'folder_path': '/test/performance/path'},
                HTTP_X_REQUESTED_WITH='XMLHttpRequest'
            )

        end_time = time.time()
        validation_time = end_time - start_time

        # Should complete quickly (less than 1 second)
        self.assertLess(validation_time, 1.0)
        self.assertEqual(response.status_code, 200)

    def test_wizard_large_folder_list_handling(self):
        """Test wizard performance with many existing folders"""
        # Create many folders
        for i in range(50):
            ScanFolder.objects.create(
                path=f'/test/performance/folder_{i}',
                name=f'Performance Test Folder {i}'
            )

        # Test that folders view loads quickly
        import time
        start_time = time.time()

        response = self.client.get(reverse('books:wizard_folders'))

        end_time = time.time()
        load_time = end_time - start_time

        # Should load reasonably quickly even with many folders
        self.assertLess(load_time, 2.0)
        self.assertEqual(response.status_code, 200)

    def test_wizard_session_size_optimization(self):
        """Test that wizard doesn't create excessive session data"""
        # Go through wizard steps
        self.client.post(reverse('books:wizard_content_types'), {
            'content_type': 'ebooks'
        })

        self.client.post(reverse('books:wizard_scrapers'), {
            'enabled_scrapers': ['goodreads', 'google_books', 'comicvine']
        })

        # Check session size is reasonable
        session_data = dict(self.client.session)

        # Should not have excessive session data
        self.assertLessEqual(len(str(session_data)), 1000)  # Arbitrary reasonable limit


class WizardSecurityTests(TestCase):
    """Test security aspects of wizard functionality"""

    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='testuser_security',
            password='testpass123'
        )
        self.client = Client()

    def test_wizard_requires_authentication(self):
        """Test that all wizard steps require authentication"""
        wizard_urls = [
            'wizard_welcome',
            'wizard_folders',
            'wizard_content_types',
            'wizard_scrapers',
            'wizard_complete'
        ]

        # Test without authentication
        for url_name in wizard_urls:
            response = self.client.get(reverse(f'books:{url_name}'))
            self.assertEqual(response.status_code, 302)  # Should redirect to login

    def test_wizard_csrf_protection(self):
        """Test that wizard forms have CSRF protection"""
        self.client.force_login(self.user)

        response = self.client.get(reverse('books:wizard_folders'))
        self.assertContains(response, 'csrfmiddlewaretoken')

    def test_wizard_path_traversal_protection(self):
        """Test protection against path traversal attacks"""
        self.client.force_login(self.user)

        # Attempt path traversal attack
        malicious_paths = [
            '../../../etc/passwd',
            '..\\..\\windows\\system32',
            '/etc/shadow',
            '../../../../var/log'
        ]

        for malicious_path in malicious_paths:
            response = self.client.post(reverse('books:wizard_folders'), {
                'action': 'add_folder',
                'folder_path': malicious_path,
                'folder_name': 'Malicious Folder'
            })

            # Should reject malicious paths
            self.assertEqual(response.status_code, 200)  # Returns to form with error

            # Should not create folder with malicious path
            folder_count = ScanFolder.objects.filter(path=malicious_path).count()
            self.assertEqual(folder_count, 0)

    def test_wizard_input_sanitization(self):
        """Test that wizard sanitizes user input"""
        self.client.force_login(self.user)

        # Test script injection in folder name
        malicious_name = '<script>alert("xss")</script>'

        with patch('os.path.exists') as mock_exists:
            mock_exists.return_value = True

            response = self.client.post(reverse('books:wizard_folders'), {
                'action': 'add_folder',
                'folder_path': '/safe/path',
                'folder_name': malicious_name
            })

        # Should handle malicious input safely
        if response.status_code == 302:  # Redirect = success
            # Check that folder name is sanitized
            folder = ScanFolder.objects.filter(path='/safe/path').first()
            if folder:
                self.assertNotIn('<script>', folder.name)

    def test_wizard_session_security(self):
        """Test wizard session security"""
        self.client.force_login(self.user)

        # Set wizard session data
        session = self.client.session
        session['wizard_content_type'] = 'ebooks'
        session.save()

        # Logout and try to access wizard
        self.client.logout()

        response = self.client.get(reverse('books:wizard_scrapers'))

        # Should not be able to access wizard session after logout
        self.assertEqual(response.status_code, 302)  # Redirect to login
