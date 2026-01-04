#!/usr/bin/env python
"""
Quick test script to verify the ebooks AJAX endpoint is working correctly.
Run this after setting up Django environment to test the AJAX functionality.
"""

import os

import django
from django.contrib.auth.models import User
from django.test.client import Client

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ebook_manager.settings')
django.setup()


def test_ebooks_ajax():
    """Test the ebooks AJAX endpoint with authentication."""

    # Create a test client
    client = Client()

    # Try to get admin user (or create a test user)
    try:
        # Try to find an existing user
        user = User.objects.first()
        if not user:
            print("No users found in database. Creating test user...")
            user = User.objects.create_user(
                username='testuser',
                password='testpass123',
                email='test@example.com'
            )
            print(f"Created test user: {user.username}")
        else:
            print(f"Using existing user: {user.username}")

        # Login the user
        client.force_login(user)
        print("User logged in successfully")

        # Test the main ebooks view
        response = client.get('/ebooks/')
        print(f"Main ebooks view status: {response.status_code}")
        if response.status_code == 200:
            print("✓ Main ebooks page loads successfully")
        else:
            print(f"✗ Main ebooks page failed with status {response.status_code}")
            return

        # Test the AJAX list endpoint
        response = client.get('/ebooks/ajax/list/')
        print(f"AJAX list endpoint status: {response.status_code}")

        if response.status_code == 200:
            try:
                data = response.json()
                print("✓ AJAX endpoint returns JSON data")
                print(f"Response keys: {list(data.keys())}")

                if 'success' in data and data['success']:
                    print("✓ AJAX response indicates success")
                    ebooks_count = len(data.get('ebooks', []))
                    print(f"✓ Found {ebooks_count} ebooks in response")

                    # Show first few ebooks for verification
                    if ebooks_count > 0:
                        print("\nFirst few ebooks:")
                        for i, ebook in enumerate(data['ebooks'][:3]):
                            print(f"  {i+1}. {ebook.get('title', 'No title')} by {ebook.get('author_display', 'Unknown')}")

                else:
                    print("✗ AJAX response indicates failure")
                    print(f"Error: {data.get('error', 'Unknown error')}")

            except Exception as e:
                print(f"✗ Error parsing JSON response: {e}")
                print(f"Raw response: {response.content[:200]}...")
        else:
            print(f"✗ AJAX endpoint failed with status {response.status_code}")
            print(f"Response content: {response.content[:200]}...")

    except Exception as e:
        print(f"Error during testing: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    print("Testing ebooks AJAX functionality...")
    print("=" * 50)
    test_ebooks_ajax()
    print("=" * 50)
    print("Test completed!")
