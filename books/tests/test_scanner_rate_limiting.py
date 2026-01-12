"""
Tests for the API rate limiting and circuit breaker implementation.
"""

import time
from unittest.mock import MagicMock, patch

from django.core.cache import cache
from django.test import TestCase

from books.scanner.rate_limiting import APIManager, CircuitBreaker, RateLimitConfig, RateLimitedAPIClient, RateLimitTracker


class RateLimitTrackerTests(TestCase):
    """Test cases for the RateLimitTracker."""

    def setUp(self):
        self.tracker = RateLimitTracker("TestAPI", {"minute_limit": 5})
        cache.clear()

    def test_check_limits_allowed(self):
        """Test that requests are allowed when under the limit."""
        result = self.tracker.check_limits()
        self.assertTrue(result["allowed"])

    def test_check_limits_exceeded(self):
        """Test that requests are denied when the limit is exceeded."""
        for _ in range(5):
            self.tracker.record_request()

        result = self.tracker.check_limits()
        self.assertFalse(result["allowed"])
        self.assertIn("Per-minute limit exceeded", result["reason"])

    def test_record_request_increments_count(self):
        """Test that recording a request increments the count."""
        self.tracker.record_request()
        count = self.tracker._get_current_count("minute")
        self.assertEqual(count, 1)

    def test_seconds_until_next_period(self):
        """Test calculation of seconds until the next period."""
        seconds = self.tracker._seconds_until_next_period("minute")
        self.assertGreater(seconds, 0)
        self.assertLessEqual(seconds, 60)


class CircuitBreakerTests(TestCase):
    """Test cases for the CircuitBreaker."""

    def setUp(self):
        self.breaker = CircuitBreaker("TestAPI", failure_threshold=2, timeout=10)
        cache.clear()

    def test_circuit_is_closed_initially(self):
        """Test that the circuit is closed initially."""
        self.assertFalse(self.breaker.is_open())

    def test_circuit_opens_after_failures(self):
        """Test that the circuit opens after the failure threshold is reached."""
        self.breaker.record_failure()
        self.assertFalse(self.breaker.is_open())
        self.breaker.record_failure()
        self.assertTrue(self.breaker.is_open())

    def test_circuit_closes_after_timeout(self):
        """Test that the circuit closes again after the timeout."""
        self.breaker.record_failure()
        self.breaker.record_failure()
        self.assertTrue(self.breaker.is_open())

        # Simulate timeout
        state = cache.get(self.breaker.cache_key)
        state["last_failure"] = time.time() - 11  # 11 seconds ago
        cache.set(self.breaker.cache_key, state)

        self.assertFalse(self.breaker.is_open())

    def test_circuit_resets_on_success(self):
        """Test that the circuit resets after a successful call."""
        self.breaker.record_failure()
        self.breaker.record_success()
        state = cache.get(self.breaker.cache_key)
        self.assertIsNone(state)


class RateLimitedAPIClientTests(TestCase):
    """Test cases for the RateLimitedAPIClient."""

    def setUp(self):
        self.client = RateLimitedAPIClient("TestAPI", RateLimitConfig.OPEN_LIBRARY)
        cache.clear()

    @patch("books.scanner.rate_limiting.requests.get")
    def test_make_request_success(self, mock_get):
        """Test a successful request."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "ok"}
        mock_get.return_value = mock_response

        result = self.client.make_request("http://example.com")
        self.assertEqual(result, {"status": "ok"})
        mock_get.assert_called_once()

    @patch("books.scanner.rate_limiting.requests.get")
    def test_make_request_uses_cache(self, mock_get):
        """Test that the client uses the cache."""
        cache.set("test_cache_key", {"cached": True})
        result = self.client.make_request("http://example.com", cache_key="test_cache_key")

        self.assertEqual(result, {"cached": True})
        mock_get.assert_not_called()

    def test_make_request_respects_rate_limit(self):
        """Test that the client respects the rate limit."""
        # Exceed the minute limit
        for _ in range(60):
            self.client.rate_tracker.record_request()

        with patch("books.scanner.rate_limiting.time.sleep") as mock_sleep:
            result = self.client.make_request("http://example.com")
            self.assertIsNone(result)  # Should return None if it has to wait too long
            # Verify that sleep was called due to rate limiting
            mock_sleep.assert_called()

    def test_make_request_circuit_breaker_open(self):
        """Test that the client stops requests when the circuit is open."""
        # Open the circuit
        for _ in range(self.client.circuit_breaker.failure_threshold):
            self.client.circuit_breaker.record_failure()

        with patch("books.scanner.rate_limiting.requests.get") as mock_get:
            result = self.client.make_request("http://example.com")
            self.assertIsNone(result)
            mock_get.assert_not_called()

    @patch("books.scanner.rate_limiting.requests.get")
    def test_make_request_handles_429_error(self, mock_get):
        """Test that the client handles 429 (Too Many Requests) errors."""
        mock_response_429 = MagicMock()
        mock_response_429.status_code = 429
        mock_response_429.headers = {"Retry-After": "1"}

        mock_response_200 = MagicMock()
        mock_response_200.status_code = 200
        mock_response_200.json.return_value = {"status": "ok"}

        mock_get.side_effect = [mock_response_429, mock_response_200]

        with patch("books.scanner.rate_limiting.time.sleep") as mock_sleep:
            result = self.client.make_request("http://example.com")
            self.assertEqual(result, {"status": "ok"})
            # Should call sleep twice: once for base delay, once for 429 retry
            self.assertEqual(mock_sleep.call_count, 2)
            # The second call should be for the retry-after value
            mock_sleep.assert_any_call(1)
            self.assertEqual(mock_get.call_count, 2)


class APIManagerTests(TestCase):
    """Test cases for the APIManager."""

    def setUp(self):
        self.manager = APIManager()

    def test_get_client(self):
        """Test getting a client from the manager."""
        client = self.manager.get_client("google_books")
        self.assertIsInstance(client, RateLimitedAPIClient)
        self.assertEqual(client.api_name, "Google Books")

    def test_get_all_status(self):
        """Test getting the status of all managed APIs."""
        statuses = self.manager.get_all_status()
        self.assertIn("google_books", statuses)
        self.assertIn("comic_vine", statuses)
        self.assertIn("open_library", statuses)

    def test_check_api_health(self):
        """Test checking the health of all APIs."""
        health = self.manager.check_api_health()
        self.assertIn("google_books", health)
        self.assertTrue(health["google_books"])  # Should be healthy initially
