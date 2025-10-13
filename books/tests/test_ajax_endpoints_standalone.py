#!/usr/bin/env python3
"""
Test script to check AJAX endpoint responses
"""

import os
import django
import pytest

# Now import Django models
from django.test import Client
from django.contrib.auth.models import User
# Setup Django environment FIRST
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ebook_manager.settings')
django.setup()


@pytest.mark.django_db
def test_endpoints():
    """Test the AJAX endpoints"""

    # Create a test client
    client = Client()

    # Create a test user
    user, created = User.objects.get_or_create(
        username='testuser',
        defaults={'email': 'test@test.com'}
    )
    if created:
        user.set_password('testpass')
        user.save()

    # Log in the user
    client.login(username='testuser', password='testpass')

    print("Testing AJAX endpoints...")

    # Test audiobooks endpoint
    print("\n=== Testing Audiobooks ===")
    response = client.get('/audiobooks/ajax/list/', HTTP_X_REQUESTED_WITH='XMLHttpRequest')
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.content.decode()}")

    # Test comics endpoint
    print("\n=== Testing Comics ===")
    response = client.get('/comics/ajax/list/', HTTP_X_REQUESTED_WITH='XMLHttpRequest')
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.content.decode()}")

    # Test ebooks endpoint
    print("\n=== Testing Ebooks ===")
    response = client.get('/ebooks/ajax/list/', HTTP_X_REQUESTED_WITH='XMLHttpRequest')
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.content.decode()}")

    # Test series endpoint
    print("\n=== Testing Series ===")
    response = client.get('/series/ajax/list/', HTTP_X_REQUESTED_WITH='XMLHttpRequest')
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.content.decode()}")


if __name__ == '__main__':
    test_endpoints()
