#!/usr/bin/env python
"""Test script to trigger AJAX scan and capture the exact error."""

import os
import django
import json
from django.test import Client
from django.contrib.auth import get_user_model
import pytest

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ebook_manager.settings')
django.setup()


@pytest.mark.django_db
def test_ajax_scan():
    """Test the AJAX scan endpoint directly"""
    from books.models import ScanFolder

    # Get or create test user
    User = get_user_model()
    user, created = User.objects.get_or_create(username='testuser', defaults={'is_staff': True})

    # Get a scan folder to test with
    folders = ScanFolder.objects.all()
    if not folders:
        print("No scan folders found!")
        return

    folder = folders.first()
    print(f"Testing with folder: {folder.name} (ID: {folder.id})")

    # Create test client and login
    client = Client()
    client.force_login(user)

    # Prepare request data
    data = {
        'folder_id': folder.id,
        'use_external_apis': False
    }

    print(f"Sending request with data: {data}")

    try:
        # Make the AJAX request
        response = client.post(
            '/ajax/trigger-scan/',
            data=json.dumps(data),
            content_type='application/json'
        )

        print(f"Response status: {response.status_code}")
        print(f"Response headers: {dict(response.items())}")

        if hasattr(response, 'content'):
            print(f"Response content: {response.content.decode()}")

        if response.status_code == 302:
            print(f"Redirect location: {response.get('Location', 'Not specified')}")

    except Exception as e:
        print(f"Error making request: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test_ajax_scan()
