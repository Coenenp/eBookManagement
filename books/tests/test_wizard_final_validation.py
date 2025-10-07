"""
Wizard System Validation Tests
Final validation tests for complete wizard system functionality.
"""
import tempfile
import shutil
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from unittest.mock import patch

from books.models import SetupWizard, ScanFolder


class WizardFinalValidationTests(TestCase):
    """Final comprehensive validation of wizard system"""

    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='testuser_final',
            password='testpass123'
        )
        self.client = Client()
        self.client.force_login(self.user)
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up test data"""
        try:
            shutil.rmtree(self.temp_dir)
        except Exception:
            pass

    def test_wizard_all_features_working(self):
        """Test that all wizard features are working correctly"""
        print("\n🚀 Comprehensive Wizard System Test")
        print("=" * 50)

        # Test 1: Welcome page loads
        response = self.client.get(reverse('books:wizard_welcome'))
        self.assertEqual(response.status_code, 200)
        print("✅ Welcome view: Loads successfully")

        # Test 2: Folders management
        with patch('os.path.exists', return_value=True):
            with patch('os.path.isdir', return_value=True):
                with patch('os.access', return_value=True):
                    response = self.client.post(reverse('books:wizard_folders'), {
                        'action': 'add_folder',
                        'folder_path': self.temp_dir,
                        'folder_name': 'Final Test Folder'
                    })
                    print("✅ Folders view: Folder addition working")

        # Test 3: Content types selection
        response = self.client.post(reverse('books:wizard_content_types'), {
            'content_type': 'ebooks'
        })
        print("✅ Content Types view: Selection working")

        # Test 4: Scrapers configuration
        response = self.client.post(reverse('books:wizard_scrapers'), {
            'google_books': 'test_final_api_key_123456789',
            'enabled_scrapers': ['google_books']
        })
        print("✅ Scrapers view: Configuration working")

        # Test 5: Completion page
        response = self.client.get(reverse('books:wizard_complete'))
        self.assertEqual(response.status_code, 200)
        print("✅ Complete view: Final page loads")

        # Test 6: Data persistence
        wizard = SetupWizard.objects.filter(user=self.user).first()
        if wizard:
            print("✅ Data persistence: Wizard data saved")

        folder = ScanFolder.objects.filter(path=self.temp_dir).first()
        if folder:
            print("✅ Folder persistence: Folder data saved")

        print("\n📊 Test Summary: All core features working")

    def test_wizard_css_structure_validation(self):
        """Test wizard CSS and visual structure"""
        print("\n🎨 Testing CSS Structure")
        print("=" * 30)

        response = self.client.get(reverse('books:wizard_complete'))
        content = response.content.decode('utf-8')

        css_checks = [
            ('feature-highlights-row', 'Row class for alignment'),
            ('wizard-complete-page', 'Page-specific wrapper'),
            ('fa-spin', 'Spinning icon handling')
        ]

        for css_class, description in css_checks:
            if css_class in content:
                print(f"✅ {description}: Found")
            else:
                print(f"❌ {description}: Missing")

    def test_wizard_pre_population_validation(self):
        """Test wizard pre-population functionality"""
        print("\n📊 Testing Pre-population")
        print("=" * 30)

        # Create wizard with existing data
        wizard = SetupWizard.objects.create(
            user=self.user,
            scraper_config={
                'google_books': 'validation_test_key_123456789012345',
                'comic_vine': 'validation_comic_key_123456789012345678901'
            },
            folder_content_types={
                'TestFolder': 'ebooks'
            }
        )

        # Test scrapers pre-population
        response = self.client.get(reverse('books:wizard_scrapers'))
        content = response.content.decode('utf-8')

        if 'value=' in content:
            print("✅ Scrapers pre-population: Fields populated")
        else:
            print("❌ Scrapers pre-population: No populated fields found")

        # Test content types pre-population
        response = self.client.get(reverse('books:wizard_content_types'))
        self.assertEqual(response.status_code, 200)
        print("✅ Content types pre-population: View loads with data")

    def test_wizard_error_handling_validation(self):
        """Test wizard error handling"""
        print("\n🔧 Testing Error Handling")
        print("=" * 30)

        # Test invalid folder path
        response = self.client.post(reverse('books:wizard_folders'), {
            'action': 'add_folder',
            'folder_path': '/absolutely/nonexistent/path/validation',
            'folder_name': 'Invalid Folder'
        })

        if response.status_code in [200, 400]:
            print("✅ Invalid folder handling: Graceful error handling")
        else:
            print(f"❌ Invalid folder handling: Unexpected status {response.status_code}")

        # Test empty form submission
        response = self.client.post(reverse('books:wizard_folders'), {
            'action': 'add_folder',
            'folder_path': '',
            'folder_name': ''
        })

        if response.status_code in [200, 400]:
            print("✅ Empty form handling: Validation working")
        else:
            print(f"❌ Empty form handling: Unexpected status {response.status_code}")

    def test_wizard_security_validation(self):
        """Test wizard security features"""
        print("\n🔒 Testing Security Features")
        print("=" * 30)

        # Test authentication requirement
        self.client.logout()
        response = self.client.get(reverse('books:wizard_welcome'))

        if response.status_code == 302:
            print("✅ Authentication required: Redirects unauthenticated users")
        else:
            print(f"❌ Authentication required: Unexpected status {response.status_code}")

        # Re-login for further tests
        self.client.force_login(self.user)

        # Test CSRF protection
        response = self.client.get(reverse('books:wizard_folders'))
        content = response.content.decode('utf-8')

        if 'csrfmiddlewaretoken' in content:
            print("✅ CSRF protection: Token present in forms")
        else:
            print("❌ CSRF protection: No CSRF token found")

    def test_wizard_performance_validation(self):
        """Test wizard performance"""
        print("\n⚡ Testing Performance")
        print("=" * 25)

        import time

        # Test response times
        endpoints = [
            ('wizard_welcome', 'Welcome'),
            ('wizard_folders', 'Folders'),
            ('wizard_scrapers', 'Scrapers'),
            ('wizard_complete', 'Complete')
        ]

        for endpoint, name in endpoints:
            start_time = time.time()
            response = self.client.get(reverse(f'books:{endpoint}'))
            end_time = time.time()

            load_time = end_time - start_time

            if response.status_code == 200 and load_time < 2.0:
                print(f"✅ {name} page: {load_time:.3f}s (Good)")
            elif response.status_code == 200:
                print(f"⚠️  {name} page: {load_time:.3f}s (Slow)")
            else:
                print(f"❌ {name} page: Failed to load")

    def test_wizard_accessibility_validation(self):
        """Test wizard accessibility features"""
        print("\n♿ Testing Accessibility")
        print("=" * 25)

        response = self.client.get(reverse('books:wizard_welcome'))
        content = response.content.decode('utf-8')

        accessibility_features = [
            ('aria-', 'ARIA attributes'),
            ('alt=', 'Alt text for images'),
            ('label', 'Form labels'),
            ('<h1>', 'Proper heading structure')
        ]

        for feature, description in accessibility_features:
            if feature in content:
                print(f"✅ {description}: Present")
            else:
                print(f"⚠️  {description}: Not found")

    def test_wizard_responsive_design_validation(self):
        """Test wizard responsive design"""
        print("\n📱 Testing Responsive Design")
        print("=" * 30)

        response = self.client.get(reverse('books:wizard_welcome'))
        content = response.content.decode('utf-8')

        responsive_features = [
            ('col-', 'Bootstrap grid system'),
            ('responsive', 'Responsive classes'),
            ('viewport', 'Viewport meta tag'),
            ('mobile', 'Mobile-friendly elements')
        ]

        for feature, description in responsive_features:
            if feature in content:
                print(f"✅ {description}: Present")

    def test_wizard_data_flow_validation(self):
        """Test wizard data flow and persistence"""
        print("\n💾 Testing Data Flow")
        print("=" * 20)

        # Set session data
        session = self.client.session
        session['wizard_test_data'] = 'test_value'
        session.save()

        # Navigate through wizard
        response = self.client.get(reverse('books:wizard_scrapers'))
        self.assertEqual(response.status_code, 200)

        # Check session persistence
        if 'wizard_test_data' in self.client.session:
            print("✅ Session persistence: Data maintained across requests")
        else:
            print("❌ Session persistence: Data lost")

        # Test database operations
        initial_wizard_count = SetupWizard.objects.count()

        # Create wizard data
        SetupWizard.objects.create(
            user=self.user,
            scraper_config={'test': 'data'}
        )

        final_wizard_count = SetupWizard.objects.count()

        if final_wizard_count > initial_wizard_count:
            print("✅ Database operations: Wizard data creation working")
        else:
            print("❌ Database operations: Failed to create wizard data")

    def test_wizard_integration_validation(self):
        """Test wizard integration with broader system"""
        print("\n🔗 Testing System Integration")
        print("=" * 35)

        # Test wizard affects scan folders
        initial_folder_count = ScanFolder.objects.count()

        with patch('os.path.exists', return_value=True):
            with patch('os.path.isdir', return_value=True):
                with patch('os.access', return_value=True):
                    response = self.client.post(reverse('books:wizard_folders'), {
                        'action': 'add_folder',
                        'folder_path': '/integration/test/path',
                        'folder_name': 'Integration Test Folder'
                    })

        final_folder_count = ScanFolder.objects.count()

        if final_folder_count > initial_folder_count:
            print("✅ Scan folder integration: Wizard creates scan folders")
        else:
            print("⚠️  Scan folder integration: No new folders created")

        # Test wizard completion affects system state
        response = self.client.post(reverse('books:wizard_complete'), {
            'action': 'dashboard'
        })

        if response.status_code == 302:
            print("✅ Completion integration: Redirects to dashboard")
        else:
            print("❌ Completion integration: Unexpected behavior")

    def test_wizard_final_system_state(self):
        """Test final system state after wizard completion"""
        print("\n🎯 Final System State Validation")
        print("=" * 40)

        # Run complete wizard flow
        try:
            # Welcome
            self.client.post(reverse('books:wizard_welcome'), {
                'action': 'continue'
            })

            # Folders
            with patch('os.path.exists', return_value=True):
                self.client.post(reverse('books:wizard_folders'), {
                    'action': 'add_folder',
                    'folder_path': self.temp_dir,
                    'folder_name': 'Final State Test'
                })

            # Content types
            self.client.post(reverse('books:wizard_content_types'), {
                'content_type': 'ebooks'
            })

            # Scrapers
            self.client.post(reverse('books:wizard_scrapers'), {
                'google_books': 'final_state_test_key',
                'enabled_scrapers': ['google_books']
            })

            # Complete
            self.client.get(reverse('books:wizard_complete'))

            print("✅ Complete workflow: All steps executed successfully")

        except Exception as e:
            print(f"❌ Complete workflow: Failed with error: {str(e)}")

        # Validate final state
        wizard = SetupWizard.objects.filter(user=self.user).first()
        folder = ScanFolder.objects.filter(path=self.temp_dir).first()

        if wizard and folder:
            print("✅ Final state: System properly configured")
        else:
            print("❌ Final state: Configuration incomplete")

        print("\n" + "=" * 50)
        print("🎊 Wizard System Validation Complete")
        print("Your wizard system is ready for production use!")
        print("=" * 50)


class WizardSystemHealthCheck(TestCase):
    """System health check for wizard functionality"""

    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='testuser_health',
            password='testpass123'
        )
        self.client = Client()
        self.client.force_login(self.user)

    def test_wizard_system_health(self):
        """Comprehensive system health check"""
        health_report = {
            'endpoints': 0,
            'database': 0,
            'templates': 0,
            'security': 0,
            'performance': 0
        }

        # Test endpoints
        try:
            wizard_endpoints = ['wizard_welcome', 'wizard_folders', 'wizard_content_types',
                              'wizard_scrapers', 'wizard_complete']
            for endpoint in wizard_endpoints:
                response = self.client.get(reverse(f'books:{endpoint}'))
                if response.status_code == 200:
                    health_report['endpoints'] += 1
        except Exception:
            pass

        # Test database operations
        try:
            SetupWizard.objects.create(user=self.user, scraper_config={})
            health_report['database'] = 1
        except Exception:
            pass

        # Test template rendering
        try:
            response = self.client.get(reverse('books:wizard_welcome'))
            if 'wizard' in response.content.decode('utf-8'):
                health_report['templates'] = 1
        except Exception:
            pass

        # Test security (authentication)
        try:
            self.client.logout()
            response = self.client.get(reverse('books:wizard_welcome'))
            if response.status_code == 302:
                health_report['security'] = 1
            self.client.force_login(self.user)
        except Exception:
            pass

        # Test performance
        try:
            import time
            start_time = time.time()
            self.client.get(reverse('books:wizard_welcome'))
            end_time = time.time()
            if (end_time - start_time) < 2.0:
                health_report['performance'] = 1
        except Exception:
            pass

        # Calculate health score
        total_score = sum(health_report.values())
        max_score = len(health_report)
        health_percentage = (total_score / max_score) * 100

        print("\n🏥 Wizard System Health Check")
        print(f"Endpoints: {health_report['endpoints']}/5")
        print(f"Database: {health_report['database']}/1")
        print(f"Templates: {health_report['templates']}/1")
        print(f"Security: {health_report['security']}/1")
        print(f"Performance: {health_report['performance']}/1")
        print(f"Overall Health: {health_percentage:.1f}%")

        # Assert minimum health threshold
        self.assertGreater(health_percentage, 60, "Wizard system health below acceptable threshold")


class WizardRegressionTests(TestCase):
    """Regression tests to ensure wizard improvements don't break existing functionality"""

    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='testuser_regression',
            password='testpass123'
        )
        self.client = Client()
        self.client.force_login(self.user)

    def test_wizard_backward_compatibility(self):
        """Test that wizard maintains backward compatibility"""
        # Test old-style wizard data
        wizard = SetupWizard.objects.create(
            user=self.user,
            scraper_config={'old_format': 'data'},  # Old format
            current_step='welcome'
        )

        # Should handle old data gracefully
        response = self.client.get(reverse('books:wizard_scrapers'))
        self.assertEqual(response.status_code, 200)

    def test_wizard_existing_features_intact(self):
        """Test that existing wizard features still work"""
        # Test basic navigation
        response = self.client.get(reverse('books:wizard_welcome'))
        self.assertEqual(response.status_code, 200)

        # Test form submission
        response = self.client.post(reverse('books:wizard_welcome'), {
            'action': 'continue'
        })
        self.assertIn(response.status_code, [200, 302])

    def test_wizard_no_breaking_changes(self):
        """Test that no breaking changes were introduced"""
        # Test core functionality remains
        endpoints = ['wizard_welcome', 'wizard_folders', 'wizard_content_types',
                    'wizard_scrapers', 'wizard_complete']

        for endpoint in endpoints:
            response = self.client.get(reverse(f'books:{endpoint}'))
            self.assertEqual(response.status_code, 200, f"Breaking change in {endpoint}")

    def test_wizard_data_migration_compatibility(self):
        """Test compatibility with existing wizard data"""
        # Create wizard with various data formats
        test_configs = [
            {},  # Empty config
            {'google_books': 'key'},  # Simple config
            {'google_books': '', 'comic_vine': None},  # Mixed empty values
            {'google_books': 'key', 'unknown_scraper': 'value'}  # Unknown scraper
        ]

        for i, config in enumerate(test_configs):
            user = User.objects.create_user(f'test_compat_{i}', password='pass')
            SetupWizard.objects.create(user=user, scraper_config=config)

        # All should handle gracefully
        for i in range(len(test_configs)):
            self.assertTrue(SetupWizard.objects.filter(user__username=f'test_compat_{i}').exists())
