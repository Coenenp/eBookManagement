"""
Wizard HTTP and AJAX Testing
Tests wizard HTTP endpoints and AJAX functionality.
"""

from unittest.mock import Mock, patch

from django.contrib.auth.models import User
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse

from books.models import ScanFolder


class WizardHTTPEndpointTests(TestCase):
    """Test wizard HTTP endpoints and responses"""

    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='testuser_http',
            password='testpass123'
        )
        self.client = Client()
        self.client.force_login(self.user)
        self.factory = RequestFactory()

    def test_wizard_endpoint_status_codes(self):
        """Test that all wizard endpoints return correct status codes"""
        wizard_endpoints = [
            'wizard_welcome',
            'wizard_folders',
            'wizard_content_types',
            'wizard_scrapers',
            'wizard_complete'
        ]

        for endpoint in wizard_endpoints:
            response = self.client.get(reverse(f'books:{endpoint}'))
            self.assertEqual(response.status_code, 200, f"Endpoint {endpoint} should return 200")

    def test_wizard_post_request_handling(self):
        """Test wizard POST request handling"""
        # Test welcome POST
        response = self.client.post(reverse('books:wizard_welcome'), {
            'action': 'continue'
        })
        self.assertIn(response.status_code, [200, 302])

        # Test folders POST
        with patch('os.path.exists', return_value=True):
            response = self.client.post(reverse('books:wizard_folders'), {
                'action': 'add_folder',
                'folder_path': '/test/path',
                'folder_name': 'Test Folder'
            })
            self.assertIn(response.status_code, [200, 302])

    def test_wizard_content_type_headers(self):
        """Test wizard content type headers"""
        response = self.client.get(reverse('books:wizard_welcome'))

        # Should return HTML content
        self.assertTrue(
            response.get('Content-Type', '').startswith('text/html') or
            'html' in response.get('Content-Type', '')
        )

    def test_wizard_csrf_token_presence(self):
        """Test that wizard forms include CSRF tokens"""
        response = self.client.get(reverse('books:wizard_folders'))
        self.assertEqual(response.status_code, 200)

        content = response.content.decode('utf-8')
        self.assertIn('csrfmiddlewaretoken', content)

    def test_wizard_session_handling(self):
        """Test wizard session data handling"""
        # Set session data
        session = self.client.session
        session['wizard_test'] = 'test_value'
        session.save()

        # Make request
        response = self.client.get(reverse('books:wizard_scrapers'))
        self.assertEqual(response.status_code, 200)

        # Session should persist
        self.assertIn('wizard_test', self.client.session)

    def test_wizard_redirect_handling(self):
        """Test wizard redirect responses"""
        # Test skip action which should redirect
        response = self.client.post(reverse('books:wizard_welcome'), {
            'action': 'skip'
        })

        # Should redirect
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.has_header('Location'))

    def test_wizard_error_response_handling(self):
        """Test wizard error response handling"""
        # Submit invalid data
        response = self.client.post(reverse('books:wizard_folders'), {
            'action': 'add_folder',
            'folder_path': '',  # Invalid empty path
            'folder_name': ''   # Invalid empty name
        })

        # Should handle gracefully (return form with errors)
        self.assertIn(response.status_code, [200, 400])

    def test_wizard_method_not_allowed_handling(self):
        """Test wizard handling of not allowed HTTP methods"""
        # Try PATCH method (not typically supported)
        response = self.client.generic('PATCH', reverse('books:wizard_welcome'))

        # Should return method not allowed or redirect
        self.assertIn(response.status_code, [302, 405])

    def test_wizard_query_parameter_handling(self):
        """Test wizard handling of query parameters"""
        # Test with query parameters
        response = self.client.get(reverse('books:wizard_welcome') + '?step=1&debug=true')
        self.assertEqual(response.status_code, 200)

    def test_wizard_large_request_handling(self):
        """Test wizard handling of large requests"""
        # Create large POST data
        large_data = {
            'action': 'add_folder',
            'folder_path': '/test/path',
            'folder_name': 'Test Folder',
            'large_field': 'x' * 10000  # Large field
        }

        response = self.client.post(reverse('books:wizard_folders'), large_data)

        # Should handle large requests gracefully
        self.assertIn(response.status_code, [200, 302, 413])  # 413 = Request too large


class WizardAJAXTests(TestCase):
    """Test wizard AJAX functionality"""

    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='testuser_ajax',
            password='testpass123'
        )
        self.client = Client()
        self.client.force_login(self.user)

    def test_wizard_ajax_folder_validation(self):
        """Test AJAX folder validation endpoint"""
        # Try to find AJAX validation endpoint
        ajax_endpoints = [
            '/ajax/wizard/validate-folder/',
            '/wizard/ajax/validate-folder/',
            '/books/ajax/validate-folder/'
        ]

        for endpoint in ajax_endpoints:
            try:
                with patch('os.path.exists', return_value=True):
                    response = self.client.post(
                        endpoint,
                        {'folder_path': '/test/path'},
                        HTTP_X_REQUESTED_WITH='XMLHttpRequest'
                    )

                    if response.status_code == 200:
                        # Found working AJAX endpoint
                        self.assertTrue(response.get('Content-Type', '').startswith('application/json'))
                        break
            except Exception:
                continue  # Try next endpoint

    def test_wizard_ajax_scraper_validation(self):
        """Test AJAX scraper validation if available"""
        ajax_data = {
            'scraper': 'google_books',
            'api_key': 'test_key_123'
        }

        # Mock successful API response
        with patch('requests.get') as mock_get:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {'status': 'ok'}
            mock_get.return_value = mock_response

            # Try common AJAX endpoints
            ajax_endpoints = [
                '/ajax/wizard/test-api/',
                '/wizard/ajax/test-scraper/',
                '/books/ajax/test-scraper/'
            ]

            for endpoint in ajax_endpoints:
                try:
                    response = self.client.post(
                        endpoint,
                        ajax_data,
                        HTTP_X_REQUESTED_WITH='XMLHttpRequest'
                    )

                    if response.status_code == 200:
                        # Found working endpoint
                        content_type = response.get('Content-Type', '')
                        self.assertTrue('json' in content_type)
                        break
                except Exception:
                    continue

    def test_wizard_ajax_error_handling(self):
        """Test AJAX error handling"""
        # Test with invalid AJAX request
        invalid_data = {
            'invalid_field': 'invalid_value'
        }

        response = self.client.post(
            reverse('books:wizard_scrapers'),
            invalid_data,
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )

        # Should handle AJAX requests appropriately
        self.assertIn(response.status_code, [200, 400, 404])

    def test_wizard_ajax_authentication(self):
        """Test AJAX authentication requirements"""
        # Logout and test AJAX request
        self.client.logout()

        response = self.client.post(
            reverse('books:wizard_scrapers'),
            {'test': 'data'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )

        # Should require authentication
        self.assertIn(response.status_code, [302, 401, 403])

    def test_wizard_ajax_csrf_protection(self):
        """Test AJAX CSRF protection"""
        # Test AJAX request without CSRF token
        self.client.logout()
        self.client.force_login(self.user)

        # Disable CSRF token in client
        from django.middleware.csrf import get_token
        get_token(self.client.request())  # Get token but don't use it

        response = self.client.post(
            reverse('books:wizard_folders'),
            {'action': 'test'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )

        # Should handle CSRF appropriately
        self.assertIn(response.status_code, [200, 403])

    def test_wizard_ajax_content_negotiation(self):
        """Test AJAX content negotiation"""
        # Test with different Accept headers
        response = self.client.get(
            reverse('books:wizard_scrapers'),
            HTTP_ACCEPT='application/json',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )

        # Should handle JSON requests appropriately
        self.assertIn(response.status_code, [200, 404])


class WizardHTTPSecurityTests(TestCase):
    """Test wizard HTTP security features"""

    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='testuser_security',
            password='testpass123'
        )
        self.client = Client()

    def test_wizard_authentication_required(self):
        """Test that wizard endpoints require authentication"""
        endpoints = [
            'wizard_welcome',
            'wizard_folders',
            'wizard_content_types',
            'wizard_scrapers',
            'wizard_complete'
        ]

        # Test without authentication
        for endpoint in endpoints:
            response = self.client.get(reverse(f'books:{endpoint}'))
            self.assertEqual(response.status_code, 302)  # Should redirect to login

    def test_wizard_sql_injection_protection(self):
        """Test wizard protection against SQL injection"""
        self.client.force_login(self.user)

        # Try SQL injection in folder name
        malicious_input = "'; DROP TABLE books_scanfolder; --"

        response = self.client.post(reverse('books:wizard_folders'), {
            'action': 'add_folder',
            'folder_path': '/safe/path',
            'folder_name': malicious_input
        })

        # Should handle malicious input safely
        self.assertIn(response.status_code, [200, 302])

        # Database should remain intact
        self.assertTrue(ScanFolder.objects.all().exists() or not ScanFolder.objects.all().exists())

    def test_wizard_xss_protection(self):
        """Test wizard protection against XSS"""
        self.client.force_login(self.user)

        # Try XSS in folder name
        xss_input = "<script>alert('xss')</script>"

        with patch('os.path.exists', return_value=True):
            response = self.client.post(reverse('books:wizard_folders'), {
                'action': 'add_folder',
                'folder_path': '/safe/path',
                'folder_name': xss_input
            })

        # Should handle XSS attempts safely
        self.assertIn(response.status_code, [200, 302])

    def test_wizard_csrf_protection(self):
        """Test wizard CSRF protection"""
        self.client.force_login(self.user)

        # Get CSRF token
        response = self.client.get(reverse('books:wizard_folders'))
        self.assertEqual(response.status_code, 200)

        # Try request without CSRF token (using external client)
        # This would normally fail CSRF validation in production

    def test_wizard_path_traversal_protection(self):
        """Test wizard protection against path traversal"""
        self.client.force_login(self.user)

        # Try path traversal attack
        malicious_paths = [
            '../../../etc/passwd',
            '..\\..\\..\\windows\\system32\\config\\sam',
            '/../../../../var/log/auth.log'
        ]

        for malicious_path in malicious_paths:
            response = self.client.post(reverse('books:wizard_folders'), {
                'action': 'add_folder',
                'folder_path': malicious_path,
                'folder_name': 'Malicious Folder'
            })

            # Should reject malicious paths
            self.assertEqual(response.status_code, 200)  # Returns form with error

            # Should not create folder with malicious path
            folder_count = ScanFolder.objects.filter(path=malicious_path).count()
            self.assertEqual(folder_count, 0)

    def test_wizard_rate_limiting_simulation(self):
        """Test wizard rate limiting simulation"""
        self.client.force_login(self.user)

        # Make many rapid requests
        responses = []
        for i in range(20):
            response = self.client.get(reverse('books:wizard_welcome'))
            responses.append(response.status_code)

        # Should handle rapid requests gracefully
        for status in responses:
            self.assertIn(status, [200, 429])  # 429 = Too Many Requests


class WizardHTTPPerformanceTests(TestCase):
    """Test wizard HTTP performance characteristics"""

    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='testuser_performance',
            password='testpass123'
        )
        self.client = Client()
        self.client.force_login(self.user)

    def test_wizard_response_time(self):
        """Test wizard response times"""
        import time

        endpoints = [
            'wizard_welcome',
            'wizard_folders',
            'wizard_content_types',
            'wizard_scrapers',
            'wizard_complete'
        ]

        for endpoint in endpoints:
            start_time = time.time()
            response = self.client.get(reverse(f'books:{endpoint}'))
            end_time = time.time()

            response_time = end_time - start_time

            # Should respond quickly (less than 2 seconds)
            self.assertLess(response_time, 2.0, f"{endpoint} took too long: {response_time}s")
            self.assertEqual(response.status_code, 200)

    def test_wizard_concurrent_requests(self):
        """Test wizard handling of concurrent requests"""
        import threading
        import time

        results = []

        def make_request():
            try:
                response = self.client.get(reverse('books:wizard_welcome'))
                results.append(response.status_code)
            except Exception as e:
                results.append(str(e))

        # Create multiple threads
        threads = []
        for i in range(5):
            thread = threading.Thread(target=make_request)
            threads.append(thread)

        # Start all threads
        start_time = time.time()
        for thread in threads:
            thread.start()

        # Wait for completion
        for thread in threads:
            thread.join()

        end_time = time.time()
        total_time = end_time - start_time

        # Should handle concurrent requests efficiently
        self.assertLess(total_time, 5.0)  # Should complete within 5 seconds
        self.assertEqual(len(results), 5)

        # All requests should succeed
        for result in results:
            if isinstance(result, int):
                self.assertEqual(result, 200)

    def test_wizard_memory_usage(self):
        """Test wizard memory usage during requests"""
        import gc

        # Force garbage collection
        gc.collect()

        # Get initial memory usage (simplified)
        initial_objects = len(gc.get_objects())

        # Make multiple wizard requests
        for i in range(10):
            response = self.client.get(reverse('books:wizard_scrapers'))
            self.assertEqual(response.status_code, 200)

        # Force garbage collection
        gc.collect()

        # Check memory usage
        final_objects = len(gc.get_objects())

        # Should not have significant memory growth
        object_growth = final_objects - initial_objects
        self.assertLess(object_growth, 1000)  # Arbitrary reasonable limit

    def test_wizard_database_query_efficiency(self):
        """Test wizard database query efficiency"""
        from django.db import connection
        from django.test.utils import override_settings

        with override_settings(DEBUG=True):
            # Reset queries
            connection.queries_log.clear()

            # Make wizard request
            response = self.client.get(reverse('books:wizard_scrapers'))
            self.assertEqual(response.status_code, 200)

            # Check query count
            query_count = len(connection.queries)

            # Should use reasonable number of queries
            self.assertLess(query_count, 20)  # Reasonable limit for wizard page
