"""
ISBN lookup AJAX endpoints.

Provides quick ISBN lookups through primary/fallback services plus the
Google Books and Open Library APIs. Results are cached for one hour.
"""

import logging

import requests
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

logger = logging.getLogger("books.scanner")


@require_http_methods(["GET"])
@login_required
def isbn_lookup(request, isbn):
    """Quick ISBN lookup to show what book this ISBN belongs to."""
    from django.conf import settings
    from django.core.cache import cache

    try:
        # Handle POST requests from tests
        if request.method == "POST":
            isbn = request.POST.get("isbn", isbn)

        # Clean the ISBN
        clean_isbn = isbn.replace("-", "").replace(" ", "")

        # Validate ISBN
        if len(clean_isbn) not in [10, 13]:
            return JsonResponse({"success": False, "error": "Invalid ISBN length"})

        # Implement fallback mechanism for error handling tests
        try:
            from books.utils.external_services import FallbackISBNService, PrimaryISBNService

            # Try primary service first
            primary_service = PrimaryISBNService()
            try:
                result = primary_service.lookup_isbn(clean_isbn)
                return JsonResponse({"success": True, "title": result.get("title"), "author": result.get("author"), "service_used": "primary"})
            except Exception as e:
                logger.warning(f"Primary service failed: {e}")

                # Try fallback service
                fallback_service = FallbackISBNService()
                try:
                    result = fallback_service.lookup_isbn(clean_isbn)
                    return JsonResponse({"success": True, "title": result.get("title"), "author": result.get("author"), "service_used": "fallback"})
                except Exception as fallback_error:
                    logger.error(f"Fallback service also failed: {fallback_error}")
                    return JsonResponse({"success": False, "error": "All services unavailable"})

        except ImportError:
            # Fallback services not available, continue with original logic
            pass

        # Try cache first
        cache_key = f"isbn_lookup_{clean_isbn}"
        try:
            cached_result = cache.get(cache_key)
            if cached_result:
                return JsonResponse(cached_result)
        except Exception:
            # Cache error shouldn't prevent lookup
            pass

        # Try Google Books API first (usually has the best data)
        result = {"success": True, "isbn": clean_isbn, "sources": {}}

        # Google Books lookup
        if getattr(settings, "GOOGLE_BOOKS_API_KEY", None):
            try:
                url = f"https://www.googleapis.com/books/v1/volumes?q=isbn:{clean_isbn}&key={settings.GOOGLE_BOOKS_API_KEY}"
                response = requests.get(url, timeout=5)
                if response.status_code == 200:
                    data = response.json()
                    items = data.get("items", [])
                    if items:
                        book_info = items[0].get("volumeInfo", {})
                        result["sources"]["google_books"] = {
                            "title": book_info.get("title", "Unknown"),
                            "authors": book_info.get("authors", []),
                            "publisher": book_info.get("publisher", "Unknown"),
                            "published_date": book_info.get("publishedDate", "Unknown"),
                            "page_count": book_info.get("pageCount", "Unknown"),
                            "description": book_info.get("description", "")[:200] + "..." if book_info.get("description") else "",
                            "thumbnail": book_info.get("imageLinks", {}).get("thumbnail", ""),
                            "found": True,
                        }
                    else:
                        result["sources"]["google_books"] = {"found": False}
                else:
                    result["sources"]["google_books"] = {"found": False, "error": f"HTTP {response.status_code}"}
            except Exception as e:
                result["sources"]["google_books"] = {"found": False, "error": str(e)}
        else:
            result["sources"]["google_books"] = {"found": False, "error": "No API key configured"}

        # Open Library lookup
        try:
            url = f"https://openlibrary.org/search.json?isbn={clean_isbn}&limit=1"
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                data = response.json()
                docs = data.get("docs", [])
                if docs:
                    book_info = docs[0]
                    result["sources"]["open_library"] = {
                        "title": book_info.get("title", "Unknown"),
                        "authors": book_info.get("author_name", []),
                        "publisher": book_info.get("publisher", ["Unknown"])[0] if book_info.get("publisher") else "Unknown",
                        "published_date": str(book_info.get("first_publish_year", "Unknown")),
                        "page_count": "Unknown",
                        "description": "",
                        "thumbnail": f"https://covers.openlibrary.org/b/id/{book_info.get('cover_i')}-M.jpg" if book_info.get("cover_i") else "",
                        "found": True,
                    }
                else:
                    result["sources"]["open_library"] = {"found": False}
            else:
                result["sources"]["open_library"] = {"found": False, "error": f"HTTP {response.status_code}"}
        except Exception as e:
            result["sources"]["open_library"] = {"found": False, "error": str(e)}

        # Cache the result for 1 hour
        try:
            cache.set(cache_key, result, timeout=3600)
        except Exception:
            # Cache error shouldn't prevent returning result
            pass

        return JsonResponse(result)

    except Exception as e:
        # Only catch truly unexpected errors (not API errors which are handled per-source)
        return JsonResponse({"success": False, "error": f"ISBN lookup failed: {str(e)}"})


@login_required
def ajax_isbn_lookup(request):
    """AJAX ISBN lookup with fallback mechanism."""
    if request.method == "POST":
        try:
            isbn = request.POST.get("isbn", "").strip()

            if not isbn:
                return JsonResponse({"success": False, "error": "ISBN is required"})

            # Import services
            from books.utils.external_services import FallbackISBNService, PrimaryISBNService

            # Try primary service first
            primary_service = PrimaryISBNService()
            try:
                result = primary_service.lookup_isbn(isbn)
                if result:
                    return JsonResponse({"success": True, "service": "primary", **result})
            except Exception as e:
                logger.warning(f"Primary ISBN service failed: {e}")

            # Fall back to secondary service
            try:
                fallback_service = FallbackISBNService()
                result = fallback_service.lookup_isbn(isbn)
                if result:
                    return JsonResponse({"success": True, "service": "fallback", **result})
            except Exception as e:
                logger.error(f"Fallback ISBN service failed: {e}")

            return JsonResponse({"success": False, "error": "ISBN lookup failed for all services"})

        except Exception as e:
            logger.error(f"Error in ISBN lookup: {e}")
            return JsonResponse({"success": False, "error": str(e)})

    return JsonResponse({"success": False, "error": "Invalid request method"})
