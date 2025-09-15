"""Views for background scanning monitoring and control.

This module provides web interface views for:
- Starting background scan jobs
- Monitoring scan progress
- Viewing API rate limit status
- Managing active scan jobs
"""
import uuid
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.contrib import messages
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from books.models import Book, ScanFolder
from books.scanner.background import (
    background_scan_folder, background_rescan_books,
    get_scan_progress, get_all_active_scans
)
from books.scanner.rate_limiting import get_api_status, check_api_health


@login_required
def scan_dashboard(request):
    """Main scanning dashboard showing active scans and API status."""
    # Get active scans
    active_scans = get_all_active_scans()

    # Get API status
    api_status = get_api_status()
    api_health = check_api_health()

    # Combine API status with health
    api_info = {}
    for api_name, status in api_status.items():
        api_info[api_name] = {
            **status,
            'healthy': api_health.get(api_name, False)
        }

    # Get recent scan folders
    recent_folders = ScanFolder.objects.order_by('-created_at')[:10]

    context = {
        'active_scans': active_scans,
        'api_status': api_info,
        'recent_folders': recent_folders,
        'page_title': 'Scanning Dashboard'
    }

    return render(request, 'books/scanning/dashboard.html', context)


@login_required
@require_http_methods(["POST"])
def start_folder_scan(request):
    """Start a background folder scan."""
    folder_path = request.POST.get('folder_path')
    language = request.POST.get('language', 'en')
    enable_external_apis = request.POST.get('enable_external_apis') == 'on'

    if not folder_path:
        messages.error(request, "Folder path is required")
        return redirect('scan_dashboard')

    # Generate job ID
    job_id = str(uuid.uuid4())

    try:
        # Start background scan
        background_scan_folder(job_id, folder_path, language, enable_external_apis)
        messages.success(request, f"Background scan started for {folder_path} (Job ID: {job_id})")
    except Exception as e:
        messages.error(request, f"Failed to start scan: {str(e)}")

    return redirect('scan_dashboard')


@login_required
@require_http_methods(["POST"])
def start_book_rescan(request):
    """Start a background rescan of existing books."""
    book_ids_str = request.POST.get('book_ids', '')
    folder_id = request.POST.get('folder_id')
    rescan_all = request.POST.get('rescan_all') == 'on'
    enable_external_apis = request.POST.get('enable_external_apis') == 'on'

    # Determine which books to rescan
    book_ids = []

    if rescan_all:
        book_ids = list(Book.objects.values_list('id', flat=True))
        scan_description = f"all {len(book_ids)} books"
    elif folder_id:
        try:
            folder = ScanFolder.objects.get(id=folder_id)
            book_ids = list(Book.objects.filter(scan_folder=folder).values_list('id', flat=True))
            scan_description = f"{len(book_ids)} books in {folder.name}"
        except ScanFolder.DoesNotExist:
            messages.error(request, "Folder not found")
            return redirect('scan_dashboard')
    elif book_ids_str:
        try:
            book_ids = [int(id_str.strip()) for id_str in book_ids_str.split(',') if id_str.strip()]
            scan_description = f"{len(book_ids)} selected books"
        except ValueError:
            messages.error(request, "Invalid book IDs")
            return redirect('scan_dashboard')
    else:
        messages.error(request, "Must specify books to rescan")
        return redirect('scan_dashboard')

    if not book_ids:
        messages.warning(request, "No books found to rescan")
        return redirect('scan_dashboard')

    # Generate job ID
    job_id = str(uuid.uuid4())

    try:
        # Start background rescan
        background_rescan_books(job_id, book_ids, enable_external_apis)
        messages.success(request, f"Background rescan started for {scan_description} (Job ID: {job_id})")
    except Exception as e:
        messages.error(request, f"Failed to start rescan: {str(e)}")

    return redirect('scan_dashboard')


@login_required
def scan_progress_ajax(request, job_id):
    """AJAX endpoint for getting scan progress."""
    progress = get_scan_progress(job_id)

    if not progress:
        return JsonResponse({'error': 'Job not found'}, status=404)

    return JsonResponse(progress)


@login_required
def api_status_ajax(request):
    """AJAX endpoint for getting API status."""
    api_status = get_api_status()
    api_health = check_api_health()

    # Combine status with health
    combined_status = {}
    for api_name, status in api_status.items():
        combined_status[api_name] = {
            **status,
            'healthy': api_health.get(api_name, False)
        }

    return JsonResponse(combined_status)


@login_required
def active_scans_ajax(request):
    """AJAX endpoint for getting active scans."""
    active_scans = get_all_active_scans()
    return JsonResponse({'scans': active_scans})


@login_required
@require_http_methods(["POST"])
def cancel_scan_ajax(request, job_id):
    """AJAX endpoint for canceling a scan."""
    from books.scanner.background import cancel_scan

    success = cancel_scan(job_id)

    if success:
        return JsonResponse({'success': True, 'message': 'Scan cancelled'})
    else:
        return JsonResponse({'success': False, 'error': 'Failed to cancel scan'}, status=400)


@login_required
def scan_history(request):
    """View scan history and completed jobs."""
    # This would need to be implemented with proper job storage
    # For now, show a placeholder
    context = {
        'page_title': 'Scan History',
        'completed_scans': []  # Would be populated from database/cache
    }

    return render(request, 'books/scanning/history.html', context)


@login_required
def scanning_help(request):
    """Help page for scanning features."""
    context = {
        'page_title': 'Scanning Help'
    }

    return render(request, 'books/scanning/help.html', context)
