#!/usr/bin/env python
"""
Test runner script for VS Code integration with Django tests.

This script helps VS Code discover and run Django tests properly
by setting up the Django environment before running tests.
"""
import os
import sys
import django
from django.conf import settings
from django.test.utils import get_runner

if __name__ == "__main__":
    # Set up environment variables
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ebook_manager.settings')
    os.environ.setdefault('USE_SQLITE_TEMPORARILY', 'true')

    # Initialize Django
    django.setup()

    # Get the Django test runner
    TestRunner = get_runner(settings)
    test_runner = TestRunner()

    # Run tests
    if len(sys.argv) > 1:
        # Run specific tests if provided
        test_labels = sys.argv[1:]
    else:
        # Run all tests in books app
        test_labels = ['books.tests']

    failures = test_runner.run_tests(test_labels)

    if failures:
        sys.exit(bool(failures))
