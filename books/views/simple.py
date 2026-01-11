"""
Simple utility views for the book library.

This module contains miscellaneous utility views that don't fit into
other categories - privacy policy, about pages, statistics, etc.
"""

import requests
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST
from django.views.generic import TemplateView

from books.models import Author, Book, FinalMetadata, Genre, Series


# Static/Information Pages
class AboutView(TemplateView):
    """About page view."""

    template_name = "books/about.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["active_tab"] = "about"
        return context


class PrivacyPolicyView(TemplateView):
    """Privacy policy page view."""

    template_name = "books/privacy.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["active_tab"] = "privacy"
        return context


class HelpView(TemplateView):
    """Help and documentation page view."""

    template_name = "books/help.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["active_tab"] = "help"
        return context


# Statistics and Analytics Views
class StatisticsView(LoginRequiredMixin, TemplateView):
    """Library statistics and analytics view."""

    template_name = "books/statistics.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Basic statistics
        context.update(
            {
                "active_tab": "statistics",
                "total_books": Book.objects.count(),
                "total_authors": Author.objects.count(),
                "total_genres": Genre.objects.count(),
                "total_series": Series.objects.count(),
            }
        )

        # Metadata statistics
        context.update(
            {
                "books_with_metadata": FinalMetadata.objects.count(),
                "books_without_metadata": Book.objects.count() - FinalMetadata.objects.count(),
            }
        )

        # Top statistics
        context.update(
            {
                "top_authors": Author.objects.annotate(book_count=Count("book")).order_by("-book_count")[:10],
                "top_genres": Genre.objects.annotate(book_count=Count("book")).order_by("-book_count")[:10],
                "top_series": Series.objects.annotate(book_count=Count("book")).order_by("-book_count")[:10],
            }
        )

        return context


@login_required
def library_statistics_json(request):
    """Return library statistics as JSON for charts/widgets."""
    try:
        # Basic counts
        stats = {
            "totals": {
                "books": Book.objects.count(),
                "authors": Author.objects.count(),
                "genres": Genre.objects.count(),
                "series": Series.objects.count(),
                "metadata_entries": FinalMetadata.objects.count(),
            },
            "top_authors": list(Author.objects.annotate(book_count=Count("book")).order_by("-book_count")[:5].values("name", "book_count")),
            "top_genres": list(Genre.objects.annotate(book_count=Count("book")).order_by("-book_count")[:5].values("name", "book_count")),
            "metadata_coverage": {
                "with_metadata": FinalMetadata.objects.count(),
                "without_metadata": Book.objects.count() - FinalMetadata.objects.count(),
            },
        }

        return JsonResponse({"success": True, "statistics": stats})

    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)


# Health Check and System Status
@login_required
def system_status(request):
    """System health check and status view."""
    try:
        import os

        from django.conf import settings

        status = {
            "database": "connected",
            "media_directory": "accessible" if os.path.exists(settings.MEDIA_ROOT) else "missing",
            "static_directory": "accessible" if os.path.exists(settings.STATIC_ROOT or settings.STATICFILES_DIRS[0]) else "missing",
        }

        # Test database connectivity
        try:
            Book.objects.exists()
            status["database"] = "connected"
        except Exception:
            status["database"] = "error"

        context = {
            "active_tab": "system_status",
            "status": status,
            "debug_mode": settings.DEBUG,
        }

        return render(request, "books/system_status.html", context)

    except Exception as e:
        context = {
            "active_tab": "system_status",
            "error": str(e),
        }
        return render(request, "books/system_status.html", context)


# Utility Functions for Templates
@login_required
def get_navigation_data(request):
    """Return navigation data for AJAX requests."""
    try:
        # Recent books
        recent_books = Book.objects.order_by("-date_added")[:5].values("id", "title", "file_name")

        # Navigation counts
        counts = {
            "total_books": Book.objects.count(),
            "recent_books": list(recent_books),
        }

        return JsonResponse({"success": True, "data": counts})

    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)


# Search and Filter Helpers
@login_required
def quick_search(request):
    """Quick search functionality for the search bar."""
    query = request.GET.get("q", "").strip()

    if not query or len(query) < 2:
        return JsonResponse({"success": False, "error": "Query too short"})

    try:
        # Search in books, authors, genres, series
        results = {
            "books": list(Book.objects.filter(title__icontains=query)[:5].values("id", "title")),
            "authors": list(Author.objects.filter(name__icontains=query)[:3].values("id", "name")),
            "genres": list(Genre.objects.filter(name__icontains=query)[:3].values("id", "name")),
            "series": list(Series.objects.filter(name__icontains=query)[:3].values("id", "name")),
        }

        return JsonResponse({"success": True, "results": results})

    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)


# Export and Backup Utilities
@login_required
def export_library_csv(request):
    """Export library data as CSV."""
    import csv

    from django.http import HttpResponse

    try:
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="library_export.csv"'

        writer = csv.writer(response)
        writer.writerow(["Title", "Author", "Genre", "Series", "File Path", "Date Added"])

        for book in Book.objects.select_related("author", "genre", "series"):
            writer.writerow(
                [
                    book.title or "Unknown",
                    book.author.name if book.author else "Unknown",
                    book.genre.name if book.genre else "Unknown",
                    book.series.name if book.series else "None",
                    book.file_path or "Unknown",
                    book.date_added.strftime("%Y-%m-%d") if book.date_added else "Unknown",
                ]
            )

        return response

    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)


# Debug and Development Views (only available in DEBUG mode)
def debug_view_info(request):
    """Debug information view (only in DEBUG mode)."""
    from django.conf import settings

    if not settings.DEBUG:
        return JsonResponse({"error": "Debug mode not enabled"}, status=403)

    try:
        debug_info = {
            "django_version": getattr(settings, "DJANGO_VERSION", "Unknown"),
            "python_version": __import__("sys").version,
            "database_engine": settings.DATABASES["default"]["ENGINE"],
            "installed_apps": len(settings.INSTALLED_APPS),
            "middleware_count": len(settings.MIDDLEWARE),
            "template_dirs": getattr(settings, "TEMPLATES", [{}])[0].get("DIRS", []),
        }

        return JsonResponse({"success": True, "debug_info": debug_info})

    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)


# =============================================================================
# ADDITIONAL MISSING FUNCTIONS FOR URL COMPATIBILITY
# =============================================================================


@login_required
def toggle_needs_review(request, book_id):
    """Toggle needs review status for a book."""
    # TODO: Implement toggle needs review functionality
    return JsonResponse({"status": "success", "message": "Toggle needs review not yet implemented"})


@login_required
@require_POST
@login_required
def rescan_external_metadata(request, book_id):
    """Rescan external metadata for a book."""
    import logging

    from django.apps import apps

    from books.scanner.external import query_metadata_and_covers_with_terms
    from books.scanner.resolver import resolve_final_metadata

    logger = logging.getLogger(__name__)

    try:
        # Get the Book model
        Book = apps.get_model("books", "Book")
        book = Book.objects.get(id=book_id)

        # Parse request data
        if request.content_type == "application/json":
            import json

            data = json.loads(request.body)
        else:
            data = request.POST

        # Get user-provided search terms
        search_title = data.get("title_override", "").strip()
        search_author = data.get("author_override", "").strip()
        search_isbn = data.get("isbn_override", "").strip()

        # Get selected sources
        sources = data.getlist("sources[]") or data.getlist("sources") or []
        if not sources:
            # Default to all sources if none selected
            sources = ["google", "openlibrary", "goodreads"]
        logger.info(f"Selected sources: {sources}")

        # Get options
        clear_existing = data.get("clear_existing") == "true"
        force_refresh = data.get("force_refresh") == "true"

        logger.info(f"Rescan options - Clear existing: {clear_existing}, Force refresh: {force_refresh}")

        # Handle clear existing metadata option
        if clear_existing:
            logger.info(f"Clearing existing external metadata for book {book_id}")
            # Define external API sources to clear (NOT internal sources like EPUB, PDF, Manual Entry, etc.)
            external_sources = ["Open Library", "Google Books", "Comic Vine", "Goodreads", "Open Library Covers", "Google Books Covers"]

            # Soft delete existing metadata from external API sources only
            total_deleted = 0

            # Clear BookMetadata (language, year, isbn, description, etc.)
            external_metadata = book.metadata.filter(source__name__in=external_sources)
            count = external_metadata.update(is_active=False)
            total_deleted += count
            logger.info(f"Deactivated {count} BookMetadata entries")

            # Clear titles
            count = book.titles.filter(source__name__in=external_sources).update(is_active=False)
            total_deleted += count
            logger.info(f"Deactivated {count} title entries")

            # Clear authors
            count = book.author_relationships.filter(source__name__in=external_sources).update(is_active=False)
            total_deleted += count
            logger.info(f"Deactivated {count} author entries")

            # Clear covers
            count = book.covers.filter(source__name__in=external_sources).update(is_active=False)
            total_deleted += count
            logger.info(f"Deactivated {count} cover entries")

            # Clear publishers
            count = book.publisher_relationships.filter(source__name__in=external_sources).update(is_active=False)
            total_deleted += count
            logger.info(f"Deactivated {count} publisher entries")

            # Clear genres
            count = book.genre_relationships.filter(source__name__in=external_sources).update(is_active=False)
            total_deleted += count
            logger.info(f"Deactivated {count} genre entries")

            logger.info(f"Total deactivated: {total_deleted} metadata entries")

        # Get counts before rescan
        before_counts = {
            "metadata": book.metadata.filter(is_active=True).count(),
            "covers": book.covers.filter(is_active=True).count(),
        }

        logger.info(f"Starting rescan for book {book_id}: {book.file_path}")
        logger.info(f"Search terms - Title: '{search_title}', Author: '{search_author}', ISBN: '{search_isbn}'")

        # Perform the actual external metadata query with custom terms and options
        try:
            query_metadata_and_covers_with_terms(
                book, search_title=search_title or None, search_author=search_author or None, search_isbn=search_isbn or None, sources=sources, force_refresh=force_refresh
            )

            # Resolve final metadata after fetching new data
            resolve_final_metadata(book)
            success = True
        except Exception as query_error:
            logger.error(f"Error during metadata query: {query_error}")
            success = False

        # Get counts after rescan
        after_counts = {
            "metadata": book.metadata.filter(is_active=True).count(),
            "covers": book.covers.filter(is_active=True).count(),
        }

        # Calculate what was added
        added_counts = {
            "metadata": after_counts["metadata"] - before_counts["metadata"],
            "covers": after_counts["covers"] - before_counts["covers"],
        }

        # Refresh book from database to get updated data
        book.refresh_from_db()

        if success:
            message = f'Rescan completed successfully. Added {added_counts["metadata"]} metadata entries and {added_counts["covers"]} covers.'
            logger.info(f"Rescan successful for book {book_id}: {message}")
        else:
            message = "Rescan completed with warnings. Check logs for details."
            logger.warning(f"Rescan had warnings for book {book_id}")

        return JsonResponse(
            {
                "success": success,
                "message": message,
                "metadata_updated": True,
                "before_counts": before_counts,
                "after_counts": after_counts,
                "added_counts": added_counts,
            }
        )

    except Book.DoesNotExist:
        return JsonResponse({"success": False, "message": "Book not found", "search_terms": {}, "sources_queried": []}, status=404)
    except Exception as e:
        return JsonResponse({"success": False, "message": f"Rescan failed: {str(e)}", "search_terms": {}, "sources_queried": []}, status=500)


@login_required
def isbn_lookup(request, isbn=None):
    """Quick ISBN lookup to show what book this ISBN belongs to."""
    from django.conf import settings
    from django.core.cache import cache

    if not isbn:
        isbn = request.GET.get("isbn", "").strip()

    if not isbn:
        return JsonResponse({"success": False, "error": "ISBN required"})

    try:
        # Clean the ISBN
        clean_isbn = isbn.replace("-", "").replace(" ", "")

        # Validate ISBN
        if len(clean_isbn) not in [10, 13]:
            return JsonResponse({"success": False, "error": "Invalid ISBN length"})

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
def logout_view(request):
    """Custom logout view."""
    # TODO: Implement custom logout functionality
    from django.contrib.auth import logout
    from django.shortcuts import redirect

    logout(request)
    return redirect("books:login")
