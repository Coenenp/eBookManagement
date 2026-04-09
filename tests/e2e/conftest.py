"""
Playwright configuration and fixtures for E2E tests
"""

import pytest
from playwright.sync_api import Page


@pytest.fixture(scope="session")
def base_url():
    """Base URL for the application"""
    return "http://localhost:8000"


@pytest.fixture
def authenticated_page(page: Page, base_url: str):
    """
    Provide a page that is already authenticated

    Usage:
        def test_something(authenticated_page: Page):
            authenticated_page.goto('/books/dashboard/')
            # User is already logged in
    """
    # Go to login page
    page.goto(f"{base_url}/accounts/login/")

    # Fill in login form
    page.fill('input[name="username"]', "testuser")
    page.fill('input[name="password"]', "testpass123")

    # Submit form
    page.click('button[type="submit"]')

    # Wait for redirect to dashboard
    page.wait_for_url(f"{base_url}/books/dashboard/", timeout=10000)

    return page


@pytest.fixture
def test_user_credentials():
    """Provide test user credentials"""
    return {"username": "testuser", "password": "testpass123", "email": "test@example.com"}
