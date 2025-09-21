#!/usr/bin/env python3
"""
Test script for Comic Vine API integration

This script tests the Comic Vine API integration to ensure:
1. API key configuration works
2. Comic Vine API wrapper functions correctly
3. Comic extraction with Comic Vine enrichment works
4. Database integration is working properly

Usage:
    python test_comicvine_integration.py

Requirements:
    - COMICVINE_API_KEY environment variable set
    - Comic book files in test directory (CBR/CBZ)
"""

import os
import sys
import django

# Setup Django environment
if __name__ == "__main__":
    # Add the project directory to Python path
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

    # Set Django settings module
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ebook_manager.settings')

    # Initialize Django
    django.setup()

from books.models import Book, DataSource
from books.scanner.extractors import comic
from books.scanner.extractors.comicvine import ComicVineAPI
from pathlib import Path
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def test_api_key_configuration():
    """Test if Comic Vine API key is properly configured"""
    print("=" * 60)
    print("Testing Comic Vine API Key Configuration")
    print("=" * 60)

    from django.conf import settings

    if hasattr(settings, 'COMICVINE_API_KEY') and settings.COMICVINE_API_KEY:
        print(f"✅ Comic Vine API key configured: {settings.COMICVINE_API_KEY[:8]}...")
        return True
    else:
        print("❌ Comic Vine API key not configured")
        print("Please set COMICVINE_API_KEY environment variable")
        return False


def test_comicvine_api_wrapper():
    """Test Comic Vine API wrapper functionality"""
    print("\n" + "=" * 60)
    print("Testing Comic Vine API Wrapper")
    print("=" * 60)

    try:
        api = ComicVineAPI()

        # Test search functionality
        print("Testing Comic Vine search...")
        search_results = api.search_issue("Batman #1")

        if search_results:
            print(f"✅ Search successful - Found: {search_results.get('name', 'Unknown')}")
            print(f"   Issue ID: {search_results.get('id')}")
            print(f"   Volume: {search_results.get('volume', {}).get('name', 'Unknown')}")
            return True
        else:
            print("❌ Search returned no results")
            return False

    except Exception as e:
        print(f"❌ Comic Vine API wrapper error: {e}")
        return False


def test_datasource_creation():
    """Test if COMICVINE data source is properly created"""
    print("\n" + "=" * 60)
    print("Testing DataSource Creation")
    print("=" * 60)

    try:
        # Check if COMICVINE data source exists
        comicvine_source = DataSource.objects.filter(name=DataSource.COMICVINE).first()

        if comicvine_source:
            print("✅ COMICVINE data source exists")
            print(f"   Trust level: {comicvine_source.trust_level}")
            return True
        else:
            print("❌ COMICVINE data source not found")
            print("Run bootstrap to create data sources:")
            print("python manage.py shell -c \"from books.scanner.bootstrap import ensure_data_sources; ensure_data_sources()\"")
            return False

    except Exception as e:
        print(f"❌ DataSource test error: {e}")
        return False


def test_comic_extraction_with_comicvine():
    """Test comic extraction with Comic Vine enrichment"""
    print("\n" + "=" * 60)
    print("Testing Comic Extraction with Comic Vine")
    print("=" * 60)

    # Look for test comic files
    test_files = []
    for ext in ['*.cbr', '*.cbz']:
        test_files.extend(Path('.').glob(f"**/{ext}"))

    if not test_files:
        print("❌ No comic files found for testing")
        print("Please place some CBR/CBZ files in the project directory for testing")
        return False

    test_file = test_files[0]
    print(f"Using test file: {test_file}")

    try:
        # Create a temporary book object
        book = Book.objects.create(
            file_path=str(test_file.absolute()),
            file_format=test_file.suffix.lstrip('.').lower()
        )

        print(f"Created test book with ID: {book.id}")

        # Test comic extraction
        if test_file.suffix.lower() == '.cbr':
            result = comic.extract_cbr(book)
        else:
            result = comic.extract_cbz(book)

        if result:
            print("✅ Comic extraction successful")
            print(f"   Title: {result.get('title', 'Unknown')}")
            print(f"   Series: {result.get('series', 'Unknown')}")
            print(f"   Authors: {result.get('authors', [])}")

            # Check if Comic Vine metadata was added
            comicvine_metadata = book.metadata.filter(source__name=DataSource.COMICVINE)
            if comicvine_metadata.exists():
                print(f"✅ Comic Vine metadata added: {comicvine_metadata.count()} fields")
                for meta in comicvine_metadata[:3]:  # Show first 3
                    print(f"   {meta.field_name}: {meta.field_value}")
            else:
                print("⚠️  No Comic Vine metadata found (may be expected if no matches)")

            return True
        else:
            print("❌ Comic extraction failed")
            return False

    except Exception as e:
        print(f"❌ Comic extraction test error: {e}")
        return False
    finally:
        # Clean up test book
        if 'book' in locals():
            try:
                book.delete()
                print("Test book cleaned up")
            except Exception as e:
                print(f"Warning: Could not clean up test book: {e}")
                pass


def test_comic_vine_search_variations():
    """Test Comic Vine search with different query patterns"""
    print("\n" + "=" * 60)
    print("Testing Comic Vine Search Variations")
    print("=" * 60)

    try:
        api = ComicVineAPI()

        test_queries = [
            "Batman #1",
            "Spider-Man",
            "X-Men #100",
            "Detective Comics #27",
            "Action Comics #1"
        ]

        successful_searches = 0

        for query in test_queries:
            print(f"Searching for: {query}")
            try:
                result = api.search_issue(query)
                if result:
                    print(f"  ✅ Found: {result.get('name', 'Unknown')}")
                    successful_searches += 1
                else:
                    print(f"  ❌ No results for {query}")
            except Exception as e:
                print(f"  ❌ Error searching for {query}: {e}")

        print(f"\nSearch success rate: {successful_searches}/{len(test_queries)}")
        return successful_searches > 0

    except Exception as e:
        print(f"❌ Search variations test error: {e}")
        return False


def main():
    """Run all Comic Vine integration tests"""
    print("Comic Vine Integration Test Suite")
    print("=" * 60)

    tests = [
        ("API Key Configuration", test_api_key_configuration),
        ("DataSource Creation", test_datasource_creation),
        ("Comic Vine API Wrapper", test_comicvine_api_wrapper),
        ("Search Variations", test_comic_vine_search_variations),
        ("Comic Extraction with Comic Vine", test_comic_extraction_with_comicvine),
    ]

    results = []

    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ Test '{test_name}' failed with exception: {e}")
            results.append((test_name, False))

    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    passed = 0
    total = len(results)

    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {test_name}")
        if result:
            passed += 1

    print(f"\nOverall: {passed}/{total} tests passed")

    if passed == total:
        print("🎉 All tests passed! Comic Vine integration is working correctly.")
    else:
        print("⚠️  Some tests failed. Please check the configuration and setup.")

    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
