"""
Helper script to create test users for E2E testing
Usage: python scripts/create_test_user.py
"""

import os
import sys

import django
from django.contrib.auth.models import User

# Add the project directory to the path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Setup Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ebook_manager.settings")
django.setup()


def create_test_user():
    """Create a test user for E2E tests"""
    username = "testuser"
    email = "test@example.com"
    password = "testpass123"

    # Check if user already exists
    if User.objects.filter(username=username).exists():
        print(f"✓ Test user '{username}' already exists")
        user = User.objects.get(username=username)
        # Update password in case it changed
        user.set_password(password)
        user.save()
        print("✓ Updated password for test user")
    else:
        # Create new user
        user = User.objects.create_user(username, email, password)
        print(f"✓ Created test user: {username}")
        print(f"Email: {email}")
        print(f"Password: {password}")

    return user


if __name__ == "__main__":
    create_test_user()
