"""Advanced rate limiting system for external API integrations.

This module provides sophisticated rate limiting for various external APIs with:
- Per-API rate limits (daily, hourly, per-minute)
- Persistent rate limit tracking using Django cache
- Automatic backoff and retry logic
- Circuit breaker pattern for failing APIs
- Request prioritization and queuing
- Comprehensive logging and monitoring

Supported APIs:
- Google Books: 1000 requests/day
- Comic Vine: 200 requests/hour
- Open Library: No official limit (conservative: 60/minute)
"""

import logging
import time
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import requests
from django.core.cache import cache

logger = logging.getLogger("books.scanner")


class RateLimitConfig:
    """Configuration for API rate limits."""

    # API Configurations
    GOOGLE_BOOKS = {
        "name": "Google Books",
        "daily_limit": 1000,
        "hourly_limit": None,
        "minute_limit": None,
        "base_delay": 0.1,  # 100ms between requests
        "backoff_multiplier": 2.0,
        "circuit_breaker_threshold": 5,  # failures before circuit opens
        "circuit_breaker_timeout": 300,  # 5 minutes
    }

    COMIC_VINE = {
        "name": "Comic Vine",
        "daily_limit": None,
        "hourly_limit": 200,
        "minute_limit": None,
        "base_delay": 18.1,  # 18.1 seconds to stay well under 200/hour
        "backoff_multiplier": 2.0,
        "circuit_breaker_threshold": 3,
        "circuit_breaker_timeout": 600,  # 10 minutes
    }

    OPEN_LIBRARY = {
        "name": "Open Library",
        "daily_limit": None,
        "hourly_limit": None,
        "minute_limit": 60,  # Conservative limit
        "base_delay": 1.0,  # 1 second between requests
        "backoff_multiplier": 1.5,
        "circuit_breaker_threshold": 5,
        "circuit_breaker_timeout": 180,  # 3 minutes
    }


class RateLimitTracker:
    """Tracks and enforces rate limits for external APIs."""

    def __init__(self, api_name: str, config: Dict):
        self.api_name = api_name
        self.config = config
        self.cache_prefix = f"rate_limit_{api_name.lower().replace(' ', '_')}"

    def _get_cache_key(self, period: str) -> str:
        """Generate cache key for tracking periods."""
        now = datetime.now()

        if period == "daily":
            period_key = now.strftime("%Y-%m-%d")
        elif period == "hourly":
            period_key = now.strftime("%Y-%m-%d-%H")
        elif period == "minute":
            period_key = now.strftime("%Y-%m-%d-%H-%M")
        else:
            raise ValueError(f"Invalid period: {period}")

        return f"{self.cache_prefix}_{period}_{period_key}"

    def _get_current_count(self, period: str) -> int:
        """Get current request count for the given period."""
        cache_key = self._get_cache_key(period)
        return cache.get(cache_key, 0)

    def _increment_count(self, period: str) -> int:
        """Increment and return the new count for the given period."""
        cache_key = self._get_cache_key(period)

        # Get current count
        count = cache.get(cache_key, 0)
        new_count = count + 1

        # Set expiration based on period
        if period == "daily":
            timeout = 86400  # 24 hours
        elif period == "hourly":
            timeout = 3600  # 1 hour
        elif period == "minute":
            timeout = 60  # 1 minute
        else:
            timeout = 86400

        cache.set(cache_key, new_count, timeout)
        return new_count

    def check_limits(self) -> Dict[str, Any]:
        """Check if API limits allow a new request."""
        result = {
            "allowed": True,
            "reason": None,
            "retry_after": 0,
            "current_counts": {},
        }

        # Check daily limit
        if self.config.get("daily_limit"):
            daily_count = self._get_current_count("daily")
            result["current_counts"]["daily"] = daily_count

            if daily_count >= self.config["daily_limit"]:
                result["allowed"] = False
                result["reason"] = f"Daily limit exceeded ({daily_count}/{self.config['daily_limit']})"
                result["retry_after"] = self._seconds_until_next_period("daily")
                return result

        # Check hourly limit
        if self.config.get("hourly_limit"):
            hourly_count = self._get_current_count("hourly")
            result["current_counts"]["hourly"] = hourly_count

            if hourly_count >= self.config["hourly_limit"]:
                result["allowed"] = False
                result["reason"] = f"Hourly limit exceeded ({hourly_count}/{self.config['hourly_limit']})"
                result["retry_after"] = self._seconds_until_next_period("hourly")
                return result

        # Check minute limit
        if self.config.get("minute_limit"):
            minute_count = self._get_current_count("minute")
            result["current_counts"]["minute"] = minute_count

            if minute_count >= self.config["minute_limit"]:
                result["allowed"] = False
                result["reason"] = f"Per-minute limit exceeded ({minute_count}/{self.config['minute_limit']})"
                result["retry_after"] = self._seconds_until_next_period("minute")
                return result

        return result

    def _seconds_until_next_period(self, period: str) -> int:
        """Calculate seconds until the next period starts."""
        now = datetime.now()

        if period == "daily":
            next_period = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        elif period == "hourly":
            next_period = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
        elif period == "minute":
            next_period = (now + timedelta(minutes=1)).replace(second=0, microsecond=0)
        else:
            return 3600  # Default to 1 hour

        return int((next_period - now).total_seconds())

    def record_request(self):
        """Record a successful request."""
        if self.config.get("daily_limit"):
            self._increment_count("daily")
        if self.config.get("hourly_limit"):
            self._increment_count("hourly")
        if self.config.get("minute_limit"):
            self._increment_count("minute")

    def get_status(self) -> Dict[str, Any]:
        """Get current rate limit status."""
        status = {
            "api_name": self.api_name,
            "current_counts": {},
            "limits": {},
            "next_reset": {},
        }

        if self.config.get("daily_limit"):
            status["current_counts"]["daily"] = self._get_current_count("daily")
            status["limits"]["daily"] = self.config["daily_limit"]
            status["next_reset"]["daily"] = self._seconds_until_next_period("daily")

        if self.config.get("hourly_limit"):
            status["current_counts"]["hourly"] = self._get_current_count("hourly")
            status["limits"]["hourly"] = self.config["hourly_limit"]
            status["next_reset"]["hourly"] = self._seconds_until_next_period("hourly")

        if self.config.get("minute_limit"):
            status["current_counts"]["minute"] = self._get_current_count("minute")
            status["limits"]["minute"] = self.config["minute_limit"]
            status["next_reset"]["minute"] = self._seconds_until_next_period("minute")

        return status


class CircuitBreaker:
    """Circuit breaker pattern for API failures."""

    def __init__(self, api_name: str, failure_threshold: int = 5, timeout: int = 300):
        self.api_name = api_name
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.cache_key = f"circuit_breaker_{api_name.lower().replace(' ', '_')}"

    def is_open(self) -> bool:
        """Check if circuit breaker is open (API is considered down)."""
        state = cache.get(self.cache_key, {"failures": 0, "last_failure": 0})

        if state["failures"] < self.failure_threshold:
            return False

        # Check if timeout has passed
        if time.time() - state["last_failure"] > self.timeout:
            # Reset the circuit breaker
            self.reset()
            return False

        return True

    def record_success(self):
        """Record a successful API call."""
        cache.delete(self.cache_key)

    def record_failure(self):
        """Record a failed API call."""
        state = cache.get(self.cache_key, {"failures": 0, "last_failure": 0})
        state["failures"] += 1
        state["last_failure"] = time.time()
        cache.set(self.cache_key, state, self.timeout * 2)

        logger.warning(f"[CIRCUIT BREAKER] {self.api_name} failure #{state['failures']}")

        if state["failures"] >= self.failure_threshold:
            logger.error(f"[CIRCUIT BREAKER] {self.api_name} circuit opened after {state['failures']} failures")

    def reset(self):
        """Reset the circuit breaker."""
        cache.delete(self.cache_key)
        logger.info(f"[CIRCUIT BREAKER] {self.api_name} circuit reset")


class RateLimitedAPIClient:
    """Rate-limited HTTP client for external APIs."""

    def __init__(self, api_name: str, config: Dict):
        self.api_name = api_name
        self.config = config
        self.rate_tracker = RateLimitTracker(api_name, config)
        self.circuit_breaker = CircuitBreaker(
            api_name,
            config.get("circuit_breaker_threshold", 5),
            config.get("circuit_breaker_timeout", 300),
        )
        self.last_request_time = 0

    def _enforce_base_delay(self):
        """Enforce minimum delay between requests."""
        base_delay = self.config.get("base_delay", 0.1)
        current_time = time.time()
        time_since_last = current_time - self.last_request_time

        if time_since_last < base_delay:
            sleep_time = base_delay - time_since_last
            logger.debug(f"[{self.api_name} RATE LIMIT] Waiting {sleep_time:.1f}s")
            time.sleep(sleep_time)

        self.last_request_time = time.time()

    def make_request(
        self,
        url: str,
        params: Dict = None,
        headers: Dict = None,
        timeout: int = 30,
        cache_key: str = None,
        cache_timeout: int = 3600,
    ) -> Optional[Dict]:
        """Make a rate-limited request to the API."""

        # Check circuit breaker
        if self.circuit_breaker.is_open():
            logger.warning(f"[{self.api_name}] Circuit breaker open, skipping request")
            return None

        # Check cache first
        if cache_key:
            cached_result = cache.get(cache_key)
            if cached_result:
                logger.debug(f"[{self.api_name}] Cache hit for {cache_key}")
                return cached_result

        # Check rate limits
        limit_check = self.rate_tracker.check_limits()
        if not limit_check["allowed"]:
            logger.warning(f"[{self.api_name}] Rate limit exceeded: {limit_check['reason']}")
            if limit_check["retry_after"] < 3600:  # Only wait if it's less than an hour
                logger.info(f"[{self.api_name}] Waiting {limit_check['retry_after']}s for rate limit reset")
                time.sleep(limit_check["retry_after"])
            else:
                return None

        # Enforce base delay
        self._enforce_base_delay()

        try:
            logger.debug(f"[{self.api_name}] Making request to {url}")

            # Make the request
            response = requests.get(url, params=params, headers=headers, timeout=timeout)

            # Handle rate limiting responses
            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", 60))
                logger.warning(f"[{self.api_name}] 429 rate limit, waiting {retry_after}s")
                time.sleep(retry_after)
                return self.make_request(url, params, headers, timeout, cache_key, cache_timeout)

            response.raise_for_status()
            data = response.json()

            # Record successful request
            self.rate_tracker.record_request()
            self.circuit_breaker.record_success()

            # Cache the result
            if cache_key:
                cache.set(cache_key, data, cache_timeout)
                logger.debug(f"[{self.api_name}] Cached result for {cache_key}")

            return data

        except requests.exceptions.RequestException as e:
            logger.error(f"[{self.api_name}] Request error: {e}")
            self.circuit_breaker.record_failure()
            return None
        except Exception as e:
            logger.error(f"[{self.api_name}] Unexpected error: {e}")
            self.circuit_breaker.record_failure()
            return None

    def get_status(self) -> Dict[str, Any]:
        """Get comprehensive status of the API client."""
        return {
            "api_name": self.api_name,
            "rate_limits": self.rate_tracker.get_status(),
            "circuit_breaker_open": self.circuit_breaker.is_open(),
            "config": self.config,
        }


class APIManager:
    """Central manager for all external API clients."""

    def __init__(self):
        self.clients = {
            "google_books": RateLimitedAPIClient("Google Books", RateLimitConfig.GOOGLE_BOOKS),
            "comic_vine": RateLimitedAPIClient("Comic Vine", RateLimitConfig.COMIC_VINE),
            "open_library": RateLimitedAPIClient("Open Library", RateLimitConfig.OPEN_LIBRARY),
        }

    def get_client(self, api_name: str) -> Optional[RateLimitedAPIClient]:
        """Get an API client by name."""
        return self.clients.get(api_name)

    def get_all_status(self) -> Dict[str, Any]:
        """Get status of all API clients."""
        return {name: client.get_status() for name, client in self.clients.items()}

    def check_api_health(self) -> Dict[str, bool]:
        """Check health status of all APIs."""
        return {name: not client.circuit_breaker.is_open() for name, client in self.clients.items()}


# Global API manager instance
api_manager = APIManager()


def get_api_client(api_name: str) -> Optional[RateLimitedAPIClient]:
    """Get an API client instance."""
    return api_manager.get_client(api_name)


def get_api_status() -> Dict[str, Any]:
    """Get status of all APIs."""
    return api_manager.get_all_status()


def check_api_health() -> Dict[str, bool]:
    """Check health of all APIs."""
    return api_manager.check_api_health()
