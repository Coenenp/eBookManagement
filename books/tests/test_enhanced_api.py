"""
Test the enhanced API endpoints for content-centric UI structure.

This test validates that the API endpoints provide the correct structure
for the new UI design with content entities and file aggregation.
"""

import os
import sys

import django
import pytest
from django.contrib.auth.models import User
from django.test import Client

# Add the project directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Set up Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ebook_manager.settings")
django.setup()


@pytest.mark.skip(reason="Legacy API integration script; requires rewrite to use current models and endpoints")
@pytest.mark.django_db
def test_enhanced_api_endpoints():
    """Legacy script skipped in CI — needs porting to current models/endpoints"""

    # Create test client and user
    client = Client()
    user, created = User.objects.get_or_create(username="testuser", defaults={"password": "testpass123", "email": "test@example.com"})
    if created:
        user.set_password("testpass123")
        user.save()

    # Login
    login_result = client.login(username="testuser", password="testpass123")
    print(f"Login successful: {login_result}")

    if not login_result:
        print("❌ Login failed - checking if user exists...")
        if User.objects.filter(username="testuser").exists():
            print("   User exists, trying to reset password...")
            user = User.objects.get(username="testuser")
            user.set_password("testpass123")
            user.save()
            login_result = client.login(username="testuser", password="testpass123")
            print(f"   Login after reset: {login_result}")

    print("🧪 Testing Enhanced API Endpoints")
    print("=" * 50)

    # Test URLs with different patterns to find the right structure
    test_urls = [
        "/books/ebooks/ajax/list/",
        "/ebooks/ajax/list/",
        "ebooks/ajax/list/",
    ]

    print("\n🔍 Testing URL patterns...")
    for url in test_urls:
        response = client.get(url)
        print(f"   {url} -> {response.status_code}")

    # Test 1: Ebooks List
    print("\n1️⃣  Testing Ebooks List API...")
    response = client.get("/ebooks/ajax/list/", follow=True)
    print(f"Status: {response.status_code}")
    if response.redirect_chain:
        print(f"   Redirected from: {response.redirect_chain}")

    if response.status_code == 200:
        data = response.json()
        print(f"✅ Success: Found {len(data.get('ebooks', []))} ebooks")

        if data.get("ebooks"):
            first_ebook = data["ebooks"][0]
            print(f"   Sample ebook: {first_ebook.get('title', 'Unknown')} by {first_ebook.get('author', 'Unknown')}")
            print(f"   Fields: {list(first_ebook.keys())}")
    else:
        print(f"❌ Failed: {response.status_code}")

    # Test 2: Comics List with Sub-rows
    print("\n2️⃣  Testing Comics List API with Sub-rows...")
    response = client.get("/comics/ajax/list/", follow=True)
    print(f"Status: {response.status_code}")

    if response.status_code == 200:
        data = response.json()
        comics = data.get("comics", [])
        print(f"✅ Success: Found {len(comics)} comic series")

        if comics:
            first_comic = comics[0]
            print(f"   Sample comic: {first_comic.get('title', 'Unknown')} ({first_comic.get('issue_count', 0)} issues)")
            issues = first_comic.get("issues", [])
            print(f"   Issues data: {len(issues)} issues including missing/uncategorized")

            # Check for missing issues
            missing_count = sum(1 for issue in issues if issue.get("missing"))
            print(f"   Missing issues detected: {missing_count}")

    else:
        print(f"❌ Failed: {response.status_code}")

    # Test 3: Series List with Sub-rows
    print("\n3️⃣  Testing Series List API with Sub-rows...")
    response = client.get("/series/ajax/list/", follow=True)
    print(f"Status: {response.status_code}")

    if response.status_code == 200:
        data = response.json()
        series = data.get("series", [])
        print(f"✅ Success: Found {len(series)} series")

        if series:
            first_series = series[0]
            print(f"   Sample series: {first_series.get('name', 'Unknown')} ({first_series.get('book_count', 0)} books)")
            books = first_series.get("books", [])
            print(f"   Books data: {len(books)} books with position info")

    else:
        print(f"❌ Failed: {response.status_code}")

    # Test 4: Audiobooks List
    print("\n4️⃣  Testing Audiobooks List API...")
    response = client.get("/audiobooks/ajax/list/", follow=True)
    print(f"Status: {response.status_code}")

    if response.status_code == 200:
        data = response.json()
        print(f"✅ Success: Found {len(data.get('audiobooks', []))} audiobooks")

        if data.get("audiobooks"):
            first_audiobook = data["audiobooks"][0]
            print(f"   Sample audiobook: {first_audiobook.get('title', 'Unknown')} by {first_audiobook.get('author', 'Unknown')}")
            print(f"   Duration: {first_audiobook.get('duration', 'Unknown')}")
    else:
        print(f"❌ Failed: {response.status_code}")

    # Test 5: Detail Endpoints with File Tabs
    print("\n5️⃣  Testing Detail Endpoints with File Aggregation...")

    # Find a sample ebook for detail test
    response = client.get("/ebooks/ajax/list/", follow=True)
    if response.status_code == 200:
        ebooks = response.json().get("ebooks", [])
        if ebooks:
            ebook_id = ebooks[0]["id"]

            print(f"\n   🔍 Testing Ebook Detail API (ID: {ebook_id})...")
            detail_response = client.get(f"/ebooks/ajax/detail/{ebook_id}/", follow=True)
            print(f"   Status: {detail_response.status_code}")

            if detail_response.status_code == 200:
                detail_data = detail_response.json()
                ebook = detail_data.get("ebook", {})

                files = ebook.get("files", [])
                covers = ebook.get("covers", [])
                metadata = ebook.get("metadata", {})

                print(f"   ✅ Files Tab: {len(files)} files")
                print(f"   ✅ Covers Tab: {len(covers)} covers")
                print(f"   ✅ Metadata Tab: {len(metadata)} metadata fields")

                if files:
                    print(f"      File types: {[f.get('type') for f in files]}")
                    print(f"      Sample file: {files[0].get('filename', 'Unknown')} ({files[0].get('size', 0)} bytes)")
            else:
                print(f"   ❌ Detail Failed: {detail_response.status_code}")
        else:
            print("   No ebooks available for detail test")  # Find a sample comic for detail test
    response = client.get("/books/comics/ajax/list/")
    if response.status_code == 200:
        comics = response.json().get("comics", [])
        if comics:
            comic_id = comics[0]["id"]

            print(f"\n   🔍 Testing Comic Detail API (ID: {comic_id})...")
            detail_response = client.get(f"/books/comics/ajax/detail/{comic_id}/")
            print(f"   Status: {detail_response.status_code}")

            if detail_response.status_code == 200:
                detail_data = detail_response.json()
                comic = detail_data.get("comic", {})

                files = comic.get("files", [])
                covers = comic.get("covers", [])

                print(f"   ✅ Aggregated Files: {len(files)} files across all issues")
                print(f"   ✅ Aggregated Covers: {len(covers)} covers")

                if files:
                    file_types = [f.get("type") for f in files]
                    print(f"      File types: {set(file_types)}")
            else:
                print(f"   ❌ Comic Detail Failed: {detail_response.status_code}")

    print("\n" + "=" * 50)
    print("🎯 API Enhancement Test Complete!")


if __name__ == "__main__":
    test_enhanced_api_endpoints()
