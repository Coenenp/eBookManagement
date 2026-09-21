"""Fixtures and skip-gate for the M1a Playwright UI walkthrough.

These tests drive a live server (port 8001, uitest copy) and are gated off by
default so the normal ``manage.py test`` / ``pytest`` run skips them. They are
pytest-style (using pytest-playwright fixtures), so Django's own test runner
never discovers them; for pytest, ``RUN_UI_TESTS=1`` (and a reachable server)
is required.
"""

import os

import pytest

# The walkthrough server (uitest copy), per TASK.md M1a.
APP_BASE = "http://127.0.0.1:8001"

USERNAME = "admin"
PASSWORD = "admin123"


def _server_is_up() -> bool:
    try:
        import urllib.request

        with urllib.request.urlopen(f"{APP_BASE}/login/", timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-ui"):
        return
    run_ui = os.environ.get("RUN_UI_TESTS") == "1"
    if not run_ui:
        reason = "UI walkthrough tests need RUN_UI_TESTS=1 and a server on 8001"
        skip = pytest.mark.skip(reason=reason)
        for item in items:
            item.add_marker(skip)


def pytest_addoption(parser):
    parser.addoption("--run-ui", action="store_true", default=False, help="Run the UI walkthrough tests")


@pytest.fixture
def app_url():
    """Base URL of the walkthrough server."""
    return APP_BASE


@pytest.fixture
def authenticated_page(page, app_url):
    """A Playwright page already logged in as the walkthrough user."""
    page.goto(f"{app_url}/login/")
    page.fill('input[name="username"]', USERNAME)
    page.fill('input[name="password"]', PASSWORD)
    page.click('button[type="submit"]')
    page.wait_for_url("**/dashboard/**", timeout=15000)
    return page