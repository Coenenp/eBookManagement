"""
Views for API status and intelligent scanning management.

This module provides views for monitoring API completeness,
retrying failed API calls, and managing intelligent scanning sessions.
"""
import logging
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.shortcuts import redirect, get_object_or_404
from django.views.generic import ListView
from django.http import JsonResponse

from books.models import Book, BookAPICompleteness
from books.scanner.intelligent import IntelligentAPIScanner
from books.mixins.navigation import BookNavigationMixin

logger = logging.getLogger('books.scanner')


class APIStatusView(LoginRequiredMixin, BookNavigationMixin, ListView):
    """View for displaying API completeness status for all books"""

    model = Book
    template_name = 'books/api_status.html'
    context_object_name = 'page_obj'
    paginate_by = 50

    def get_queryset(self):
        """Get books with API completeness tracking"""
        queryset = Book.objects.filter(
            api_completeness__isnull=False
        ).select_related(
            'api_completeness',
            'finalmetadata'
        ).order_by(
            'api_completeness__scan_priority',
            '-api_completeness__metadata_completeness'
        )

        # Apply filters
        priority = self.request.GET.get('priority')
        if priority:
            queryset = queryset.filter(api_completeness__scan_priority=priority)

        missing_source = self.request.GET.get('missing_source')
        if missing_source:
            queryset = queryset.filter(
                api_completeness__missing_sources__contains=[missing_source]
            )

        completeness_range = self.request.GET.get('completeness')
        if completeness_range:
            ranges = {
                '0-25': (0.0, 0.25),
                '25-50': (0.25, 0.50),
                '50-75': (0.50, 0.75),
                '75-100': (0.75, 1.0),
            }
            if completeness_range in ranges:
                min_val, max_val = ranges[completeness_range]
                queryset = queryset.filter(
                    api_completeness__metadata_completeness__gte=min_val,
                    api_completeness__metadata_completeness__lt=max_val
                )

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Calculate statistics
        all_completeness = BookAPICompleteness.objects.all()
        context['stats'] = {
            'high_priority': all_completeness.filter(scan_priority='high').count(),
            'medium_priority': all_completeness.filter(scan_priority='medium').count(),
            'low_priority': all_completeness.filter(scan_priority='low').count(),
            'complete': all_completeness.filter(scan_priority='complete').count(),
        }

        return context


@login_required
def retry_book_api(request, book_id):
    """Retry API calls for a specific book"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=400)

    try:
        book = get_object_or_404(Book, pk=book_id)

        # Initialize intelligent scanner
        scanner = IntelligentAPIScanner()

        # Force retry all APIs for this book
        result = scanner.scan_book_with_intelligence(book, force_all_apis=True)

        # Update completeness
        if hasattr(book, 'api_completeness'):
            book.api_completeness.calculate_completeness()

        return JsonResponse({
            'success': True,
            'message': f'Retried {len(result["apis_attempted"])} APIs. Succeeded: {len(result["apis_succeeded"])}',
            'apis_succeeded': result['apis_succeeded'],
            'apis_failed': result['apis_failed'],
        })

    except Exception as e:
        logger.error(f"Error retrying API for book {book_id}: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def retry_all_priority(request, priority):
    """Retry API calls for all books of a specific priority"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=400)

    try:
        books = Book.objects.filter(
            api_completeness__scan_priority=priority,
            api_completeness__needs_external_scan=True
        ).select_related('api_completeness')[:100]  # Limit to prevent timeout

        scanner = IntelligentAPIScanner()
        success_count = 0

        for book in books:
            result = scanner.scan_book_with_intelligence(book, force_all_apis=False)
            if result['apis_succeeded']:
                success_count += 1

        return JsonResponse({
            'success': True,
            'message': f'Processed {len(books)} books. {success_count} had successful API calls.',
            'processed': len(books),
            'successful': success_count
        })

    except Exception as e:
        logger.error(f"Error retrying priority {priority}: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def resume_failed_api_calls(request, session_id):
    """Resume API calls for books that failed during a previous scan"""
    try:
        scanner = IntelligentAPIScanner(session_id=session_id)
        session = scanner.session

        if not session:
            messages.error(request, "Session not found")
            return redirect('books:scan_dashboard')

        if not session.can_resume:
            messages.warning(request, "No books to retry in this session")
            return redirect('books:scan_dashboard')

        # Process resume queue
        success_count = 0
        failed_count = 0

        for book_data in list(session.resume_queue):  # Copy list to avoid modification during iteration
            try:
                book = Book.objects.get(id=book_data['book_id'])
                result = scanner.scan_book_with_intelligence(book, force_all_apis=False)

                if result['apis_succeeded']:
                    success_count += 1
                    # Remove from queue if all missing sources were attempted
                    session.remove_book_from_resume_queue(book.id)
                else:
                    failed_count += 1

            except Book.DoesNotExist:
                logger.warning(f"Book {book_data['book_id']} not found, removing from queue")
                session.remove_book_from_resume_queue(book_data['book_id'])
            except Exception as e:
                logger.error(f"Error processing book {book_data['book_id']}: {e}")
                failed_count += 1

        messages.success(
            request,
            f"Processed {success_count + failed_count} books. "
            f"Success: {success_count}, Failed: {failed_count}"
        )

    except Exception as e:
        logger.error(f"Error resuming session {session_id}: {e}", exc_info=True)
        messages.error(request, f"Error resuming scan: {str(e)}")

    return redirect('books:scan_dashboard')


@login_required
def api_health_status(request):
    """AJAX endpoint for current API health status"""
    from books.scanner.rate_limiting import check_api_health, get_api_status

    api_health = check_api_health()
    api_status = get_api_status()

    # Format response
    apis = {}
    for api_name in ['google_books', 'open_library']:
        apis[api_name] = {
            'healthy': api_health.get(api_name, False),
            'status': api_status.get(api_name, {}),
        }

    return JsonResponse({
        'apis': apis,
        'timestamp': api_status.get('timestamp', None)
    })
