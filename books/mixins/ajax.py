"""
AJAX response mixins for standardized JSON responses
"""

import json
import logging
from functools import wraps

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import JsonResponse

logger = logging.getLogger("books.scanner")


class StandardAjaxResponseMixin:
    """Standardized AJAX response patterns"""

    @staticmethod
    def success_response(message="Success", **extra_data):
        """Standard success response"""
        response_data = {"success": True, "message": message}
        response_data.update(extra_data)
        return JsonResponse(response_data)

    @staticmethod
    def error_response(message="Error occurred", status=400, **extra_data):
        """Standard error response"""
        response_data = {"success": False, "error": message}
        response_data.update(extra_data)
        return JsonResponse(response_data, status=status)

    @staticmethod
    def not_found_response(item="Item"):
        """Standard not found response"""
        return JsonResponse(
            {"success": False, "error": f"{item} not found"}, status=404
        )

    @staticmethod
    def validation_error_response(errors):
        """Standard validation error response"""
        return JsonResponse(
            {"success": False, "error": "Validation failed", "errors": errors},
            status=400,
        )


class BookAjaxViewMixin(StandardAjaxResponseMixin):
    """Specialized mixin for book-related AJAX operations"""

    def get_book_or_404(self, book_id):
        """Get book with standard error handling"""
        from django.apps import apps

        Book = apps.get_model("books", "Book")
        try:
            return Book.objects.get(pk=book_id)
        except Book.DoesNotExist:
            return None

    def handle_book_operation(self, book_id, operation_func, *args, **kwargs):
        """Standardized book operation handling"""
        book = self.get_book_or_404(book_id)
        if not book:
            return self.not_found_response("Book")

        try:
            result = operation_func(book, *args, **kwargs)
            return (
                result
                if isinstance(result, JsonResponse)
                else self.success_response(**result)
            )
        except Exception as e:
            logger.error(f"Error in book operation: {e}")
            return self.error_response(str(e), status=500)


def ajax_book_operation(operation_func):
    """Decorator for standardizing book AJAX operations"""

    @wraps(operation_func)
    def wrapper(request, book_id, *args, **kwargs):
        mixin = BookAjaxViewMixin()
        return mixin.handle_book_operation(
            book_id, operation_func, request, *args, **kwargs
        )

    return wrapper


def standard_ajax_handler(view_func):
    """Enhanced AJAX response handler with better error handling"""

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        try:
            # Parse JSON for POST requests
            if request.method == "POST" and request.content_type == "application/json":
                try:
                    request.json = json.loads(request.body)
                except json.JSONDecodeError:
                    return JsonResponse(
                        {"success": False, "error": "Invalid JSON data"}, status=400
                    )

            result = view_func(request, *args, **kwargs)

            # Convert dict responses to JsonResponse
            if isinstance(result, dict):
                return JsonResponse(result)
            return result

        except ValidationError as e:
            return JsonResponse(
                {"success": False, "error": "Validation failed", "details": str(e)},
                status=400,
            )
        except PermissionDenied:
            return JsonResponse(
                {"success": False, "error": "Permission denied"}, status=403
            )
        except Exception as e:
            logger.error(f"Error in {view_func.__name__}: {e}")
            return JsonResponse(
                {
                    "success": False,
                    "error": "An error occurred while processing your request",
                },
                status=500,
            )

    return wrapper
