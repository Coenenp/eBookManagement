"""Views for background scanning monitoring and control.

This module provides web interface views for:
- Starting background scan jobs
- Monitoring scan progress
- Viewing API rate limit status
- Managing active scan jobs
"""
import uuid
import logging
import threading
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.contrib import messages
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.apps import apps

# Import scanner modules
from books.scanner.background import (
    background_scan_folder, background_rescan_books,
    get_scan_progress, get_all_active_scans, add_active_scan
)
from books.scanner.rate_limiting import get_api_status, check_api_health

logger = logging.getLogger('books.scanner')


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

    # Get recent scan folders with book count annotation and scan status
    from django.db.models import Count, Q
    ScanFolder = apps.get_model('books', 'ScanFolder')
    ScanStatus = apps.get_model('books', 'ScanStatus')

    # Get folders with their scan progress information
    recent_folders = ScanFolder.objects.annotate(
        book_count=Count('book')
    ).order_by('-created_at')[:10]

    # Add progress information to each folder
    folders_with_progress = []
    for folder in recent_folders:
        progress_info = folder.get_scan_progress_info()
        folder.progress_info = progress_info
        folders_with_progress.append(folder)

    recent_folders = folders_with_progress

    # Check for interrupted scans (Failed status with progress > 0)
    interrupted_scans = ScanStatus.objects.filter(
        Q(status='Failed') & Q(processed_files__gt=0),
        scan_folders__isnull=False
    ).order_by('-updated')[:5]

    # Get recent scan history for dashboard
    from books.models import ScanHistory, ScanQueue
    recent_scan_history = ScanHistory.objects.order_by('-completed_at')[:5]

    # Enhance interrupted scans with progress details
    interrupted_scans_enhanced = []
    for scan in interrupted_scans:
        total_files = scan.total_files if hasattr(scan, 'total_files') else 0
        processed_files = scan.processed_files if hasattr(scan, 'processed_files') else 0

        # Calculate progress percentage
        progress_percentage = 0
        if total_files > 0:
            progress_percentage = (processed_files / total_files) * 100

        # Get folder info if available
        folder_name = "Unknown"
        if scan.scan_folders.exists():
            folder_name = scan.scan_folders.first().name

        interrupted_scans_enhanced.append({
            'scan': scan,
            'folder_name': folder_name,
            'processed_files': processed_files,
            'total_files': total_files,
            'progress_percentage': progress_percentage,
            'progress_display': f"{processed_files}/{total_files}" if total_files > 0 else f"{processed_files}/?"
        })

    # Get upcoming scan queue (next 5 pending items)
    scan_queue = ScanQueue.objects.filter(
        status__in=['pending', 'scheduled']
    ).order_by('-priority', 'created_at')[:5]

    context = {
        'active_scans': active_scans,
        'api_status': api_info,
        'recent_folders': recent_folders,
        'interrupted_scans': interrupted_scans,
        'interrupted_scans_enhanced': interrupted_scans_enhanced,
        'scan_queue': scan_queue,
        'recent_scan_history': recent_scan_history,
        'page_title': 'Scanning Dashboard'
    }

    return render(request, 'books/scanning/dashboard.html', context)


@login_required
@require_http_methods(["POST"])
def start_folder_scan(request):
    """Start a background folder scan."""
    folder_path = request.POST.get('folder_path')
    folder_id = request.POST.get('folder_id')
    folder_name = request.POST.get('folder_name', '').strip()
    content_type = request.POST.get('content_type', 'ebooks')
    language = request.POST.get('language', 'en')
    enable_external_apis = request.POST.get('enable_external_apis') == 'on'

    # Handle scanning by folder_id
    if folder_id and not folder_path:
        ScanFolder = apps.get_model('books', 'ScanFolder')
        try:
            scan_folder = ScanFolder.objects.get(id=folder_id)
            folder_path = scan_folder.path
            folder_name = scan_folder.name
            content_type = scan_folder.content_type
            language = scan_folder.language
        except ScanFolder.DoesNotExist:
            messages.error(request, "Scan folder not found")
            return redirect('books:scan_dashboard')

    if not folder_path:
        messages.error(request, "Folder path is required")
        return redirect('books:scan_dashboard')

    # Check if we should queue or execute immediately
    from books.models import ScanQueue

    # Check current active scans
    active_scans = get_all_active_scans()
    max_concurrent_scans = 2  # Allow max 2 concurrent scans

    if len(active_scans) >= max_concurrent_scans:
        # Queue the scan instead of running it immediately
        queue_item = ScanQueue.objects.create(
            name=f"Folder Scan: {folder_name or folder_path}",
            scan_type='folder',
            status='pending',
            priority=2,  # Normal priority
            folder_paths=[folder_path],
            rescan_existing=False,
            update_metadata=True,
            fetch_covers=enable_external_apis,
            deep_scan=False,
            created_by=request.user,
        )

        messages.info(request,
            f"Scan queued due to concurrent scan limit ({len(active_scans)}/{max_concurrent_scans} active). "
            f"Your scan will start automatically when a slot becomes available.")
        return redirect('books:scan_dashboard')

    # Generate job ID and execute immediately
    job_id = str(uuid.uuid4())

    try:
        # Add job to active scans list first
        add_active_scan(job_id)

        # Always treat folder scan as initial scan (full scan) - run in background thread
        logger.info(f"[THREAD START] Creating background thread for job {job_id}")
        thread = threading.Thread(
            target=background_scan_folder,
            args=(
                job_id,
                folder_path,
                language,
                enable_external_apis,
                content_type,
                folder_name,
                False,  # rescan=False
                None    # resume_from=None
            ),
            daemon=True
        )
        thread.start()
        logger.info(f"[THREAD STARTED] Background thread started for job {job_id}, thread: {thread.name}")

        messages.success(request, f"Background scan started for {folder_path} (Job ID: {job_id})")

        # Check if we can process any queued scans
        _check_and_process_queue()
    except Exception as e:
        messages.error(request, f"Failed to start scan: {str(e)}")

    return redirect('books:scan_dashboard')


@login_required
@require_http_methods(["POST"])
def start_book_rescan(request):
    """Start a background rescan of existing books."""
    book_ids_str = request.POST.get('book_ids', '')
    folder_id = request.POST.get('folder_id')
    rescan_all = request.POST.get('rescan_all') == 'on'
    enable_external_apis = request.POST.get('enable_external_apis') == 'on'

    # Priority 1: Folder rescan (rescan=True means full folder scan with cleanup)
    if folder_id and rescan_all:
        ScanFolder = apps.get_model('books', 'ScanFolder')
        try:
            folder = ScanFolder.objects.get(id=folder_id)

            # Check if we should queue or execute immediately
            active_scans = get_all_active_scans()
            max_concurrent_scans = 2  # Allow max 2 concurrent scans

            if len(active_scans) >= max_concurrent_scans:
                # Queue the rescan
                from books.models import ScanQueue
                queue_item = ScanQueue.objects.create(
                    name=f"Folder Rescan: {folder.name}",
                    scan_type='folder',
                    status='pending',
                    priority=3,  # High priority for rescans
                    folder_paths=[folder.path],
                    rescan_existing=True,
                    update_metadata=True,
                    fetch_covers=enable_external_apis,
                    deep_scan=False,
                    created_by=request.user,
                )

                messages.info(request,
                    f"Rescan queued due to concurrent scan limit ({len(active_scans)}/{max_concurrent_scans} active). "
                    f"Your rescan will start automatically when a slot becomes available.")
                return redirect('books:scan_dashboard')

            job_id = str(uuid.uuid4())
            # Add job to active scans list first
            add_active_scan(job_id)

            # Full folder rescan with cleanup of removed books - run in background thread
            thread = threading.Thread(
                target=background_scan_folder,
                args=(
                    job_id,
                    folder.path,
                    folder.language,
                    enable_external_apis,
                    folder.content_type,
                    folder.name,
                    True,  # rescan=True
                    None   # resume_from=None
                ),
                daemon=True
            )
            thread.start()

            messages.success(request, f"Folder rescan started for {folder.name} (Job ID: {job_id})")

            # Check if we can process any queued scans
            _check_and_process_queue()

        except ScanFolder.DoesNotExist:
            messages.error(request, "Scan folder not found")
        except Exception as e:
            messages.error(request, f"Failed to start folder rescan: {str(e)}")
        return redirect('books:scan_dashboard')

    # Priority 2: Global rescan of all books (legacy support)
    elif rescan_all:
        Book = apps.get_model('books', 'Book')
        book_ids = list(Book.objects.values_list('id', flat=True))
        scan_description = f"all {len(book_ids)} books"
        job_id = str(uuid.uuid4())
        try:
            # Add job to active scans list first
            add_active_scan(job_id)

            # Run rescan in background thread
            thread = threading.Thread(
                target=background_rescan_books,
                args=(job_id, book_ids, enable_external_apis),
                daemon=True
            )
            thread.start()

            messages.success(request, f"Background rescan started for {scan_description} (Job ID: {job_id})")
        except Exception as e:
            messages.error(request, f"Failed to start global rescan: {str(e)}")
        return redirect('books:scan_dashboard')

    # Priority 3: Specific book IDs rescan
    elif book_ids_str:
        try:
            book_ids = [int(id_str.strip()) for id_str in book_ids_str.split(',') if id_str.strip()]
            scan_description = f"{len(book_ids)} selected books"
            job_id = str(uuid.uuid4())
            # Add job to active scans list first
            add_active_scan(job_id)

            # Run rescan in background thread
            thread = threading.Thread(
                target=background_rescan_books,
                args=(job_id, book_ids, enable_external_apis),
                daemon=True
            )
            thread.start()

            messages.success(request, f"Background rescan started for {scan_description} (Job ID: {job_id})")
        except ValueError:
            messages.error(request, "Invalid book IDs")
        return redirect('books:scan_dashboard')
    else:
        messages.error(request, "Must specify books to rescan")
        return redirect('books:scan_dashboard')


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
    from django.core.paginator import Paginator
    from books.models import ScanHistory

    # Get all scan history entries, ordered by most recent first
    scan_history_list = ScanHistory.objects.all().select_related('scan_folder')

    # Pagination
    paginator = Paginator(scan_history_list, 20)  # Show 20 scans per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Get statistics
    total_scans = scan_history_list.count()
    successful_scans = scan_history_list.filter(status='completed').count()
    failed_scans = scan_history_list.filter(status='failed').count()

    # Calculate success rate
    success_rate = (successful_scans / total_scans * 100) if total_scans > 0 else 0

    # Get recent statistics (last 30 days)
    from datetime import timedelta
    from django.utils import timezone
    recent_date = timezone.now() - timedelta(days=30)
    recent_scans = scan_history_list.filter(completed_at__gte=recent_date)

    context = {
        'page_title': 'Scan History',
        'page_obj': page_obj,
        'scan_history': page_obj.object_list,
        'stats': {
            'total_scans': total_scans,
            'successful_scans': successful_scans,
            'failed_scans': failed_scans,
            'success_rate': round(success_rate, 1),
            'recent_scans_count': recent_scans.count(),
        }
    }

    return render(request, 'books/scanning/history.html', context)


@login_required
def scan_queue(request):
    """View for managing the scan queue."""
    from django.core.paginator import Paginator
    from books.models import ScanQueue

    # Get all queue items
    queue_items = ScanQueue.objects.all().order_by('-priority', 'created_at')

    # Pagination
    paginator = Paginator(queue_items, 20)  # 20 items per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Statistics
    total_items = queue_items.count()
    pending_items = queue_items.filter(status='pending').count()
    scheduled_items = queue_items.filter(status='scheduled').count()
    processing_items = queue_items.filter(status='processing').count()
    completed_items = queue_items.filter(status='completed').count()
    failed_items = queue_items.filter(status='failed').count()

    context = {
        'page_title': 'Scan Queue Management',
        'page_obj': page_obj,
        'queue_items': page_obj.object_list,
        'stats': {
            'total_items': total_items,
            'pending_items': pending_items,
            'scheduled_items': scheduled_items,
            'processing_items': processing_items,
            'completed_items': completed_items,
            'failed_items': failed_items,
        }
    }

    return render(request, 'books/scanning/queue.html', context)


def _check_and_process_queue():
    """Check if any queued scans can be processed."""
    from books.models import ScanQueue

    # Check current active scans
    active_scans = get_all_active_scans()
    max_concurrent_scans = 2

    if len(active_scans) >= max_concurrent_scans:
        return  # Still at capacity

    # Get next pending scan from queue
    next_scan = ScanQueue.objects.filter(
        status='pending'
    ).order_by('-priority', 'created_at').first()

    if next_scan:
        # Execute the queued scan
        job_id = str(uuid.uuid4())

        try:
            # Mark queue item as processing
            next_scan.mark_processing(job_id)

            # Add to active scans
            add_active_scan(job_id)

            # Start the scan based on type
            if next_scan.scan_type == 'folder' and next_scan.folder_paths:
                folder_path = next_scan.folder_paths[0]  # Use first folder

                thread = threading.Thread(
                    target=background_scan_folder,
                    args=(
                        job_id,
                        folder_path,
                        'en',  # Default language
                        next_scan.fetch_covers,
                        'ebooks',  # Default content type
                        next_scan.name,
                        next_scan.rescan_existing,
                        None    # resume_from=None
                    ),
                    daemon=True
                )
                thread.start()
                logger.info(f"[QUEUE] Started queued scan {next_scan.name} (Job ID: {job_id})")

        except Exception as e:
            # Mark as failed if something went wrong
            next_scan.mark_failed(str(e))
            logger.error(f"[QUEUE] Failed to start queued scan {next_scan.name}: {e}")


@login_required
def scanning_help(request):
    """Help page for scanning features."""
    context = {
        'page_title': 'Scanning Help'
    }

    return render(request, 'books/scanning/help.html', context)
