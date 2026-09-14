"""Scan-triggering AJAX views for book management."""

import logging

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

logger = logging.getLogger("books.scanner")


@login_required
@require_http_methods(["POST"])
def ajax_trigger_scan(request):
    """AJAX trigger scan for a specific folder."""
    try:
        import json

        from django.apps import apps

        # Parse JSON data
        data = json.loads(request.body)
        folder_id = data.get("folder_id")
        use_external_apis = data.get("use_external_apis", True)

        if not folder_id:
            return JsonResponse({"status": "error", "message": "Folder ID is required"})

        # Get the scan folder
        ScanFolder = apps.get_model("books", "ScanFolder")
        try:
            scan_folder = ScanFolder.objects.get(id=folder_id)
        except ScanFolder.DoesNotExist:
            return JsonResponse({"status": "error", "message": "Scan folder not found"})

        # Import scanning functionality
        from books.scanner.background import scan_folder_in_background

        # Trigger the scan
        job_id = scan_folder_in_background(
            folder_id=scan_folder.id,
            folder_path=scan_folder.path,
            folder_name=scan_folder.name,
            content_type=scan_folder.content_type,
            language=scan_folder.language,
            enable_external_apis=use_external_apis,
        )

        api_status = "with external APIs" if use_external_apis else "without external APIs"
        return JsonResponse({"status": "success", "message": f'Scan started for "{scan_folder.name}" {api_status}', "job_id": job_id})

    except Exception as e:
        logger.error(f"Failed to trigger scan: {str(e)}")
        return JsonResponse({"status": "error", "message": f"Failed to start scan: {str(e)}"})


@login_required
@require_http_methods(["POST"])
def ajax_trigger_scan_all_folders(request):
    """AJAX endpoint to trigger scans for all active scan folders."""
    try:
        import json

        from django.apps import apps

        # Parse JSON data
        data = json.loads(request.body) if request.body else {}
        use_external_apis = data.get("use_external_apis", True)

        # Get all active scan folders
        ScanFolder = apps.get_model("books", "ScanFolder")
        active_folders = ScanFolder.objects.filter(is_active=True)

        if not active_folders.exists():
            return JsonResponse({"status": "error", "message": "No active scan folders found"})

        # Import scanning functionality
        from books.scanner.background import scan_folder_in_background

        job_ids = []
        folder_names = []

        # Trigger scan for each active folder
        for scan_folder in active_folders:
            try:
                job_id = scan_folder_in_background(
                    folder_id=scan_folder.id,
                    folder_path=scan_folder.path,
                    folder_name=scan_folder.name,
                    content_type=scan_folder.content_type,
                    language=scan_folder.language,
                    enable_external_apis=use_external_apis,
                )
                job_ids.append(job_id)
                folder_names.append(scan_folder.name)
            except Exception as e:
                logger.error(f"Failed to start scan for folder {scan_folder.name}: {str(e)}")
                continue

        if job_ids:
            api_status = "with external APIs" if use_external_apis else "without external APIs"
            folder_list = ", ".join(folder_names)
            return JsonResponse(
                {"status": "success", "message": f"Started scans for {len(job_ids)} folder(s) {api_status}: {folder_list}", "job_ids": job_ids, "folder_count": len(job_ids)}
            )
        else:
            return JsonResponse({"status": "error", "message": "Failed to start any scans"})

    except Exception as e:
        logger.error(f"Failed to trigger scan all folders: {str(e)}")
        return JsonResponse({"status": "error", "message": f"Failed to start scans: {str(e)}"})


@login_required
@require_http_methods(["POST"])
def ajax_rescan_folder(request):
    """AJAX rescan folder endpoint."""
    try:
        import json

        from django.apps import apps

        # Parse JSON data
        data = json.loads(request.body)
        folder_id = data.get("folder_id")
        use_external_apis = data.get("use_external_apis", True)

        if not folder_id:
            return JsonResponse({"status": "error", "message": "Folder ID is required"})

        # Get the scan folder
        ScanFolder = apps.get_model("books", "ScanFolder")
        try:
            scan_folder = ScanFolder.objects.get(id=folder_id)
        except ScanFolder.DoesNotExist:
            return JsonResponse({"status": "error", "message": "Scan folder not found"})

        # Import scanning functionality
        from books.scanner.background import scan_folder_in_background

        # Trigger the rescan (same as scan but with different message)
        job_id = scan_folder_in_background(
            folder_id=scan_folder.id,
            folder_path=scan_folder.path,
            folder_name=scan_folder.name,
            content_type=scan_folder.content_type,
            language=scan_folder.language,
            enable_external_apis=use_external_apis,
        )

        api_status = "with external APIs" if use_external_apis else "without external APIs"
        return JsonResponse({"status": "success", "message": f'Rescan started for "{scan_folder.name}" {api_status}', "job_id": job_id})

    except Exception as e:
        logger.error(f"Failed to trigger rescan: {str(e)}")
        return JsonResponse({"status": "error", "message": f"Failed to start rescan: {str(e)}"})
