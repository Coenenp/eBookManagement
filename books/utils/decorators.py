"""
Shared decorators for views
"""

import json
import logging
from functools import wraps

from django.http import Http404, JsonResponse

logger = logging.getLogger("books.scanner")


def ajax_response_handler(view_func):
    """
    Decorator to standardize AJAX response handling across all views.

    Features:
    - Automatic JSON parsing for POST requests with application/json content-type
    - Converts dict returns to JsonResponse
    - Standardized error handling with appropriate status codes
    - Logging of errors

    Usage:
        @ajax_response_handler
        @login_required
        def my_ajax_view(request):
            return {'success': True, 'data': 'value'}
    """

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        try:
            # Auto-parse JSON body for POST requests
            if request.method == "POST" and request.content_type == "application/json":
                request.json = json.loads(request.body)

            result = view_func(request, *args, **kwargs)

            # Auto-convert dict to JsonResponse
            if isinstance(result, dict):
                return JsonResponse(result)
            return result

        except Http404:
            # Re-raise Http404 to let Django handle it properly
            raise
        except json.JSONDecodeError:
            return JsonResponse({"success": False, "error": "Invalid JSON"}, status=400)
        except Exception as e:
            logger.error(f"Error in {view_func.__name__}: {e}", exc_info=True)
            return JsonResponse({"success": False, "error": str(e)}, status=500)

    return wrapper
