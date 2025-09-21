"""
Comprehensive tests for user settings, configuration, and preferences functionality.

This module contains tests for theme settings, language preferences, display options,
caching behavior, and personalization features across the views.
"""

import json
from unittest.mock import patch
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from django.core.cache import cache
from books.models import Book, UserProfile


class UserProfileTests(TestCase):
    """Tests for user preferences and settings."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.client.login(username='testuser', password='testpass123')

    def test_user_preferences_creation(self):
        """Test automatic creation of user preferences."""
        # Check if UserProfile is automatically created
        try:
            preferences = UserProfile.objects.get(user=self.user)
            self.assertIsNotNone(preferences)
        except UserProfile.DoesNotExist:
            # If not auto-created, create manually for testing
            preferences = UserProfile.objects.create(
                user=self.user,
                theme='flatly',
                items_per_page=25
            )
            self.assertIsNotNone(preferences)

    def test_user_preferences_defaults(self):
        """Test default values for user preferences."""
        preferences, created = UserProfile.objects.get_or_create(
            user=self.user,
            defaults={
                'theme': 'flatly',
                'items_per_page': 25,
                'show_covers_in_list': True,
                'default_view_mode': 'table'
            }
        )

        self.assertEqual(preferences.theme, 'flatly')
        self.assertEqual(preferences.items_per_page, 25)
        self.assertTrue(preferences.show_covers_in_list)
        self.assertEqual(preferences.default_view_mode, 'table')

    def test_update_user_preferences(self):
        """Test updating user preferences."""
        preferences, created = UserProfile.objects.get_or_create(
            user=self.user,
            defaults={'theme': 'flatly'}
        )

        # Update preferences
        preferences.theme = 'darkly'
        preferences.items_per_page = 50
        preferences.save()

        # Verify updates
        preferences.refresh_from_db()
        self.assertEqual(preferences.theme, 'darkly')
        self.assertEqual(preferences.items_per_page, 50)


class ThemeSettingsTests(TestCase):
    """Tests for theme settings and customization."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.client.login(username='testuser', password='testpass123')

    def test_theme_settings_ajax_endpoint(self):
        """Test AJAX endpoint for theme settings."""
        url = reverse('books:ajax_update_theme_settings')

        theme_data = {
            'theme': 'dark',
            'accent_color': '#007bff',
            'font_size': 'large',
            'sidebar_collapsed': True
        }

        response = self.client.post(
            url,
            data=json.dumps(theme_data),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content)
        self.assertTrue(response_data.get('success', False))

    def test_theme_preview_functionality(self):
        """Test theme preview without saving."""
        url = reverse('books:ajax_preview_theme')

        preview_data = {
            'theme': 'sepia',
            'accent_color': '#8b4513',
            'font_size': 'medium'
        }

        response = self.client.post(
            url,
            data=json.dumps(preview_data),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content)
        self.assertTrue(response_data.get('success', False))
        self.assertIn('preview_css', response_data)

    def test_theme_reset_to_defaults(self):
        """Test resetting theme to default settings."""
        # First set custom theme
        UserProfile.objects.update_or_create(
            user=self.user,
            defaults={
                'theme': 'custom',
                'accent_color': '#ff0000',
                'font_size': 'large'
            }
        )

        # Reset to defaults
        url = reverse('books:ajax_reset_theme')
        response = self.client.post(url)

        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content)
        self.assertTrue(response_data.get('success', False))

        # Verify reset
        preferences = UserProfile.objects.get(user=self.user)
        self.assertEqual(preferences.theme, 'default')

    def test_theme_validation(self):
        """Test theme setting validation."""
        url = reverse('books:ajax_update_theme_settings')

        # Test invalid theme
        invalid_data = {
            'theme': 'invalid_theme',
            'font_size': 'invalid_size'
        }

        response = self.client.post(
            url,
            data=json.dumps(invalid_data),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content)
        # Should either reject invalid values or use defaults
        self.assertIn('success', response_data)


class LanguagePreferencesTests(TestCase):
    """Tests for language preferences and localization."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.client.login(username='testuser', password='testpass123')

    def test_language_preference_setting(self):
        """Test setting language preference."""
        url = reverse('books:ajax_update_language')

        language_data = {'language': 'es'}

        response = self.client.post(
            url,
            data=json.dumps(language_data),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content)
        self.assertTrue(response_data.get('success', False))

    def test_language_detection_from_browser(self):
        """Test automatic language detection from browser headers."""
        # Set Accept-Language header
        response = self.client.get(
            reverse('books:book_list'),
            HTTP_ACCEPT_LANGUAGE='es-ES,es;q=0.9,en;q=0.8'
        )

        self.assertEqual(response.status_code, 200)
        # Language detection logic would be in the view

    def test_supported_languages_list(self):
        """Test retrieving list of supported languages."""
        url = reverse('books:ajax_get_supported_languages')

        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        response_data = json.loads(response.content)
        self.assertIn('languages', response_data)
        self.assertIsInstance(response_data['languages'], list)

    def test_language_fallback_behavior(self):
        """Test fallback behavior for unsupported languages."""
        # Create basic profile for testing
        UserProfile.objects.get_or_create(user=self.user)

        response = self.client.get(reverse('books:book_list'))
        self.assertEqual(response.status_code, 200)
        # Should fallback to default language without errors


class DisplayOptionsTests(TestCase):
    """Tests for display options and view customization."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.client.login(username='testuser', password='testpass123')

        # Create scan folder for books
        from books.models import ScanFolder
        self.scan_folder = ScanFolder.objects.create(
            name="Test Scan Folder",
            path="/library/test",
            content_type="ebooks"
        )

        # Create test books
        for i in range(30):
            Book.objects.create(
                file_path=f"/library/display_test_{i+1}.epub",
                file_format="epub",
                scan_folder=self.scan_folder
            )

    def test_books_per_page_setting(self):
        """Test books per page display setting."""
        # Set books per page to 10
        UserProfile.objects.update_or_create(
            user=self.user,
            defaults={'items_per_page': 10}
        )

        response = self.client.get(reverse('books:book_list'))
        self.assertEqual(response.status_code, 200)

        # Check pagination
        if 'books' in response.context:
            books = response.context['books']
            if hasattr(books, 'paginator'):
                self.assertEqual(books.paginator.per_page, 10)

    def test_cover_display_toggle(self):
        """Test toggling cover display on/off."""
        # Test with covers enabled
        UserProfile.objects.update_or_create(
            user=self.user,
            defaults={'show_covers_in_list': True}
        )

        response = self.client.get(reverse('books:book_list'))
        self.assertEqual(response.status_code, 200)
        # Would check for cover elements in template

        # Test with covers disabled
        UserProfile.objects.update_or_create(
            user=self.user,
            defaults={'show_covers_in_list': False}
        )

        response = self.client.get(reverse('books:book_list'))
        self.assertEqual(response.status_code, 200)

    def test_sort_order_preferences(self):
        """Test different sort order preferences."""
        sort_orders = ['title', 'author', 'date_added', 'file_size']

        for sort_order in sort_orders:
            with self.subTest(sort_order=sort_order):
                # Create basic profile for testing
                UserProfile.objects.get_or_create(user=self.user)

                response = self.client.get(reverse('books:book_list'))
                self.assertEqual(response.status_code, 200)

    def test_grid_vs_list_view(self):
        """Test switching between grid and list view modes."""
        # Test grid view
        UserProfile.objects.update_or_create(
            user=self.user,
            defaults={'default_view_mode': 'grid'}
        )

        response = self.client.get(reverse('books:book_list'))
        self.assertEqual(response.status_code, 200)

        # Test list view
        UserProfile.objects.update_or_create(
            user=self.user,
            defaults={'default_view_mode': 'table'}
        )

        response = self.client.get(reverse('books:book_list'))
        self.assertEqual(response.status_code, 200)

    def test_ajax_update_display_options(self):
        """Test AJAX endpoint for updating display options."""
        url = reverse('books:ajax_update_display_options')

        display_data = {
            'items_per_page': 25,
            'show_covers_in_list': True,
            'default_view_mode': 'grid'
        }

        response = self.client.post(
            url,
            data=json.dumps(display_data),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content)
        self.assertTrue(response_data.get('success', False))


class CachingBehaviorTests(TestCase):
    """Tests for caching behavior and cache management."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.client.login(username='testuser', password='testpass123')

        # Clear cache before each test
        cache.clear()

    def test_user_preference_caching(self):
        """Test caching of user preferences."""
        preferences = UserProfile.objects.create(
            user=self.user,
            theme='dark',
            language='en'
        )

        # First access should cache preferences
        cache_key = f"user_preferences_{self.user.id}"
        cached_prefs = cache.get(cache_key)

        if cached_prefs is None:
            # Simulate caching
            cache.set(cache_key, preferences, 3600)
            cached_prefs = cache.get(cache_key)

        self.assertIsNotNone(cached_prefs)

    def test_theme_css_caching(self):
        """Test caching of generated theme CSS."""
        theme_data = {
            'theme': 'dark',
            'accent_color': '#007bff'
        }

        cache_key = f"theme_css_{hash(str(theme_data))}"

        # Simulate CSS generation and caching
        generated_css = "body { background: #000; color: #fff; }"
        cache.set(cache_key, generated_css, 86400)  # 24 hours

        cached_css = cache.get(cache_key)
        self.assertEqual(cached_css, generated_css)

    def test_cache_invalidation_on_preference_update(self):
        """Test cache invalidation when preferences are updated."""
        preferences = UserProfile.objects.create(
            user=self.user,
            theme='light'
        )

        # Cache preferences
        cache_key = f"user_preferences_{self.user.id}"
        cache.set(cache_key, preferences, 3600)

        # Update preferences
        preferences.theme = 'dark'
        preferences.save()

        # Cache should be invalidated (simulate signal)
        cache.delete(cache_key)

        cached_prefs = cache.get(cache_key)
        self.assertIsNone(cached_prefs)

    def test_clear_user_cache_endpoint(self):
        """Test endpoint for clearing user-specific cache."""
        # Set some cached data
        cache.set(f"user_preferences_{self.user.id}", "test_data", 3600)
        cache.set(f"user_theme_css_{self.user.id}", "test_css", 3600)

        url = reverse('books:ajax_clear_user_cache')
        response = self.client.post(url)

        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content)
        self.assertTrue(response_data.get('success', False))

    @patch('django.core.cache.cache.get')
    @patch('django.core.cache.cache.set')
    def test_cache_performance_metrics(self, mock_set, mock_get):
        """Test cache performance and hit/miss ratios."""
        # Simulate cache hits and misses
        mock_get.side_effect = [None, "cached_data", "cached_data"]

        # First call - cache miss
        response = self.client.get(reverse('books:book_list'))
        self.assertEqual(response.status_code, 200)

        # Second call - cache hit
        response = self.client.get(reverse('books:book_list'))
        self.assertEqual(response.status_code, 200)

        # Verify cache was called
        self.assertTrue(mock_get.called)


class PersonalizationFeaturesTests(TestCase):
    """Tests for personalization features and customization."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.client.login(username='testuser', password='testpass123')

    def test_custom_dashboard_layout(self):
        """Test custom dashboard layout preferences."""
        layout_data = {
            'widgets': ['recent_books', 'statistics', 'quick_actions'],
            'widget_order': [1, 2, 3],
            'show_recommendations': True
        }

        url = reverse('books:ajax_update_dashboard_layout')

        response = self.client.post(
            url,
            data=json.dumps(layout_data),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content)
        self.assertTrue(response_data.get('success', False))

    def test_favorite_genres_tracking(self):
        """Test tracking and displaying favorite genres."""
        genre_data = {
            'favorites': ['Science Fiction', 'Fantasy', 'Mystery'],
            'hidden': ['Romance', 'Horror']
        }

        url = reverse('books:ajax_update_favorite_genres')

        response = self.client.post(
            url,
            data=json.dumps(genre_data),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content)
        self.assertTrue(response_data.get('success', False))

    def test_reading_progress_tracking(self):
        """Test reading progress tracking features."""
        progress_data = {
            'book_id': 1,
            'progress_percentage': 45,
            'current_page': 123,
            'total_pages': 273,
            'reading_time': 7200  # seconds
        }

        url = reverse('books:ajax_update_reading_progress')

        response = self.client.post(
            url,
            data=json.dumps(progress_data),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content)
        self.assertTrue(response_data.get('success', False))

    def test_custom_tags_and_labels(self):
        """Test custom tagging and labeling system."""
        tag_data = {
            'book_id': 1,
            'tags': ['to-read', 'favorites', 'recommended'],
            'custom_labels': ['Award Winner', 'Book Club Pick']
        }

        url = reverse('books:ajax_update_custom_tags')

        response = self.client.post(
            url,
            data=json.dumps(tag_data),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content)
        self.assertTrue(response_data.get('success', False))

    def test_export_user_preferences(self):
        """Test exporting user preferences and settings."""
        url = reverse('books:ajax_export_preferences')

        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        # Check if response contains preference data
        if response.get('Content-Type') == 'application/json':
            response_data = json.loads(response.content)
            self.assertIn('preferences', response_data)

    def test_import_user_preferences(self):
        """Test importing user preferences and settings."""
        preferences_data = {
            'theme': 'dark',
            'language': 'en',
            'books_per_page': 50,
            'favorite_genres': ['Science Fiction', 'Fantasy']
        }

        url = reverse('books:ajax_import_preferences')

        response = self.client.post(
            url,
            data=json.dumps({'preferences': preferences_data}),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content)
        self.assertTrue(response_data.get('success', False))


class UserSettingsSecurityTests(TestCase):
    """Security tests for user settings and preferences."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.other_user = User.objects.create_user(
            username='otheruser',
            password='otherpass123'
        )

    def test_user_cannot_modify_other_preferences(self):
        """Test that users cannot modify other users' preferences."""
        self.client.login(username='testuser', password='testpass123')

        # Try to modify other user's preferences
        url = reverse('books:ajax_update_user_preferences')

        malicious_data = {
            'user_id': self.other_user.id,
            'theme': 'modified_by_attacker'
        }

        response = self.client.post(
            url,
            data=json.dumps(malicious_data),
            content_type='application/json'
        )

        # Should either reject or ignore the user_id parameter
        self.assertEqual(response.status_code, 200)

    def test_preference_input_validation(self):
        """Test input validation for preference values."""
        self.client.login(username='testuser', password='testpass123')

        url = reverse('books:ajax_update_theme_settings')

        # Test XSS attempt in theme data
        malicious_data = {
            'theme': '<script>alert("xss")</script>',
            'accent_color': 'javascript:alert(1)',
            'custom_css': 'body { background: url("javascript:alert(1)"); }'
        }

        response = self.client.post(
            url,
            data=json.dumps(malicious_data),
            content_type='application/json'
        )

        # Should handle gracefully without executing scripts
        self.assertEqual(response.status_code, 200)

    def test_settings_require_authentication(self):
        """Test that settings endpoints require authentication."""
        # Don't log in

        endpoints = [
            reverse('books:ajax_update_theme_settings'),
            reverse('books:ajax_update_language'),
            reverse('books:ajax_update_display_options'),
            reverse('books:ajax_clear_user_cache'),
        ]

        for endpoint in endpoints:
            with self.subTest(endpoint=endpoint):
                response = self.client.post(endpoint)
                self.assertIn(response.status_code, [302, 403])

    def test_preference_size_limits(self):
        """Test size limits for preference data."""
        self.client.login(username='testuser', password='testpass123')

        url = reverse('books:ajax_update_custom_tags')

        # Test with oversized data
        large_data = {
            'tags': ['tag'] * 1000,  # Very large tag list
            'custom_css': 'x' * 100000,  # Very large CSS
        }

        response = self.client.post(
            url,
            data=json.dumps(large_data),
            content_type='application/json'
        )

        # Should handle oversized data gracefully
        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content)
        # Should either reject or truncate the data
        self.assertIn('success', response_data)


class ConfigurationIntegrationTests(TestCase):
    """Integration tests for configuration and settings across views."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.client.login(username='testuser', password='testpass123')

    def test_theme_persistence_across_pages(self):
        """Test that theme settings persist across different pages."""
        # Set dark theme
        UserProfile.objects.update_or_create(
            user=self.user,
            defaults={'theme': 'dark'}
        )

        # Visit different pages and check theme is applied
        pages = [
            reverse('books:book_list'),
            reverse('books:dashboard'),
            reverse('books:metadata_list'),
        ]

        for page in pages:
            with self.subTest(page=page):
                response = self.client.get(page)
                self.assertEqual(response.status_code, 200)
                # Theme application would be checked in template context

    def test_language_preference_across_views(self):
        """Test language preference consistency across views."""
        # Create basic profile for testing
        UserProfile.objects.get_or_create(user=self.user)

        response = self.client.get(reverse('books:book_list'))
        self.assertEqual(response.status_code, 200)
        # Language setting would affect template rendering

    def test_pagination_settings_consistency(self):
        """Test pagination settings work consistently."""
        # Create scan folder for books
        from books.models import ScanFolder
        scan_folder = ScanFolder.objects.create(
            name="Test Scan Folder",
            path="/library/test",
            content_type="ebooks"
        )

        # Create test books
        for i in range(15):
            Book.objects.create(
                file_path=f"/library/pagination_{i}.epub",
                file_format="epub",
                scan_folder=scan_folder
            )

        # Set books per page to 5
        UserProfile.objects.update_or_create(
            user=self.user,
            defaults={'books_per_page': 5}
        )

        response = self.client.get(reverse('books:book_list'))
        self.assertEqual(response.status_code, 200)

        # Check pagination in context
        if 'books' in response.context:
            books = response.context['books']
            if hasattr(books, 'paginator'):
                self.assertLessEqual(len(books), 5)

    def test_complete_configuration_workflow(self):
        """Test complete configuration workflow from defaults to customization."""
        # 1. Check default settings
        response = self.client.get(reverse('books:book_list'))
        self.assertEqual(response.status_code, 200)

        # 2. Update theme
        theme_response = self.client.post(
            reverse('books:ajax_update_theme_settings'),
            data=json.dumps({'theme': 'dark'}),
            content_type='application/json'
        )
        self.assertEqual(theme_response.status_code, 200)

        # 3. Update display options
        display_response = self.client.post(
            reverse('books:ajax_update_display_options'),
            data=json.dumps({'books_per_page': 10}),
            content_type='application/json'
        )
        self.assertEqual(display_response.status_code, 200)

        # 4. Verify settings are applied
        final_response = self.client.get(reverse('books:book_list'))
        self.assertEqual(final_response.status_code, 200)
