"""Management command for background book scanning.

This command provides a CLI interface for triggering background scanning operations:
- Scan folders for new books
- Rescan existing books for updated metadata
- Monitor scanning progress
- Check API rate limit status
"""
import uuid
import time
from django.core.management.base import BaseCommand, CommandError
from books.models import Book
from books.scanner.background import (
    background_scan_folder, background_rescan_books,
    get_scan_progress, get_all_active_scans
)
from books.scanner.rate_limiting import get_api_status, check_api_health


class Command(BaseCommand):
    help = 'Manage background book scanning operations'

    def add_arguments(self, parser):
        subparsers = parser.add_subparsers(dest='action', help='Available actions')

        # Scan folder command
        scan_parser = subparsers.add_parser('scan', help='Scan a folder for books')
        scan_parser.add_argument('folder_path', help='Path to folder to scan')
        scan_parser.add_argument('--language', default='en', help='Default language for books')
        scan_parser.add_argument('--no-external-apis', action='store_true', help='Skip external API queries')
        scan_parser.add_argument('--background', action='store_true', help='Run in background (returns job ID)')
        scan_parser.add_argument('--wait', action='store_true', help='Wait for completion and show progress')

        # Rescan books command
        rescan_parser = subparsers.add_parser('rescan', help='Rescan existing books')
        rescan_parser.add_argument('--book-ids', nargs='+', type=int, help='Specific book IDs to rescan')
        rescan_parser.add_argument('--all', action='store_true', help='Rescan all books')
        rescan_parser.add_argument('--folder', help='Rescan books in specific folder')
        rescan_parser.add_argument('--no-external-apis', action='store_true', help='Skip external API queries')
        rescan_parser.add_argument('--background', action='store_true', help='Run in background (returns job ID)')
        rescan_parser.add_argument('--wait', action='store_true', help='Wait for completion and show progress')

        # Status command
        status_parser = subparsers.add_parser('status', help='Show scanning status')
        status_parser.add_argument('--job-id', help='Show status for specific job')
        status_parser.add_argument('--apis', action='store_true', help='Show API rate limit status')

        # List active scans
        subparsers.add_parser('list', help='List all active scan jobs')

        # Cancel scan
        cancel_parser = subparsers.add_parser('cancel', help='Cancel a scan job')
        cancel_parser.add_argument('job_id', help='Job ID to cancel')

    def handle(self, *args, **options):
        action = options['action']

        if action == 'scan':
            self.handle_scan(options)
        elif action == 'rescan':
            self.handle_rescan(options)
        elif action == 'status':
            self.handle_status(options)
        elif action == 'list':
            self.handle_list()
        elif action == 'cancel':
            self.handle_cancel(options)
        else:
            self.print_help('manage.py', 'scan_books')

    def handle_scan(self, options):
        """Handle folder scanning."""
        folder_path = options['folder_path']
        language = options['language']
        enable_external_apis = not options['no_external_apis']
        background = options['background']
        wait = options['wait']

        self.stdout.write("Scanning folder: {folder_path}")

        if enable_external_apis:
            # Check API health first
            api_health = check_api_health()
            healthy_apis = [api for api, healthy in api_health.items() if healthy]

            if healthy_apis:
                self.stdout.write(f"External APIs available: {', '.join(healthy_apis)}")
            else:
                self.stdout.write(self.style.WARNING("No external APIs are available"))
                enable_external_apis = False

        job_id = str(uuid.uuid4())

        if background or wait:
            # Run in background
            self.stdout.write(f"Starting background scan (Job ID: {job_id})")

            # Start the background job
            result = background_scan_folder(job_id, folder_path, language, enable_external_apis)

            if wait:
                self.wait_for_completion(job_id)
            else:
                self.stdout.write(f"Background scan started. Use 'scan_books status --job-id {job_id}' to monitor progress.")
        else:
            # Run synchronously (not recommended for large folders)
            self.stdout.write("Running synchronous scan...")
            from books.scanner.background import BackgroundScanner
            scanner = BackgroundScanner(job_id)
            result = scanner.scan_folder(folder_path, language, enable_external_apis)

            if result['success']:
                self.stdout.write(self.style.SUCCESS(f"Scan completed: {result['message']}"))
            else:
                self.stdout.write(self.style.ERROR(f"Scan failed: {result.get('error', 'Unknown error')}"))

    def handle_rescan(self, options):
        """Handle book rescanning."""
        book_ids = options.get('book_ids', [])
        rescan_all = options['all']
        folder = options.get('folder')
        enable_external_apis = not options['no_external_apis']
        background = options['background']
        wait = options['wait']

        # Determine which books to rescan
        if rescan_all:
            books = Book.objects.all()
            book_ids = list(books.values_list('id', flat=True))
            self.stdout.write(f"Rescanning all {len(book_ids)} books")
        elif folder:
            books = Book.objects.filter(scan_folder__path=folder)
            book_ids = list(books.values_list('id', flat=True))
            self.stdout.write(f"Rescanning {len(book_ids)} books in folder: {folder}")
        elif book_ids:
            self.stdout.write(f"Rescanning {len(book_ids)} specific books")
        else:
            raise CommandError("Must specify --book-ids, --all, or --folder")

        if not book_ids:
            self.stdout.write(self.style.WARNING("No books found to rescan"))
            return

        if enable_external_apis:
            # Check API health
            api_health = check_api_health()
            healthy_apis = [api for api, healthy in api_health.items() if healthy]

            if healthy_apis:
                self.stdout.write(f"External APIs available: {', '.join(healthy_apis)}")
            else:
                self.stdout.write(self.style.WARNING("No external APIs are available"))
                enable_external_apis = False

        job_id = str(uuid.uuid4())

        if background or wait:
            # Run in background
            self.stdout.write(f"Starting background rescan (Job ID: {job_id})")

            result = background_rescan_books(job_id, book_ids, enable_external_apis)

            if wait:
                self.wait_for_completion(job_id)
            else:
                self.stdout.write(f"Background rescan started. Use 'scan_books status --job-id {job_id}' to monitor progress.")
        else:
            # Run synchronously
            self.stdout.write("Running synchronous rescan...")
            from books.scanner.background import BackgroundScanner
            scanner = BackgroundScanner(job_id)
            result = scanner.rescan_existing_books(book_ids, enable_external_apis)

            if result['success']:
                self.stdout.write(self.style.SUCCESS(f"Rescan completed: {result['message']}"))
            else:
                self.stdout.write(self.style.ERROR(f"Rescan failed: {result.get('error', 'Unknown error')}"))

    def handle_status(self, options):
        """Handle status queries."""
        job_id = options.get('job_id')
        show_apis = options['apis']

        if job_id:
            # Show specific job status
            status = get_scan_progress(job_id)
            if not status:
                self.stdout.write(self.style.WARNING(f"No job found with ID: {job_id}"))
                return

            self.display_job_status(job_id, status)

        if show_apis:
            # Show API status
            self.display_api_status()

    def handle_list(self):
        """Handle listing active scans."""
        active_scans = get_all_active_scans()

        if not active_scans:
            self.stdout.write("No active scan jobs")
            return

        self.stdout.write("Active scan jobs:")
        for scan in active_scans:
            self.stdout.write(f"  {scan['job_id']}: {scan.get('status', 'Unknown')}")

    def handle_cancel(self, options):
        """Handle scan cancellation."""
        job_id = options['job_id']

        from books.scanner.background import cancel_scan
        success = cancel_scan(job_id)

        if success:
            self.stdout.write(self.style.SUCCESS(f"Cancelled scan job: {job_id}"))
        else:
            self.stdout.write(self.style.ERROR(f"Failed to cancel scan job: {job_id}"))

    def wait_for_completion(self, job_id):
        """Wait for a background job to complete and show progress."""
        self.stdout.write("Waiting for completion...")

        last_percentage = -1
        while True:
            status = get_scan_progress(job_id)

            if not status:
                self.stdout.write(self.style.ERROR("Job not found"))
                break

            if status.get('completed'):
                if status.get('success'):
                    self.stdout.write(self.style.SUCCESS(f"Completed: {status.get('message', 'Success')}"))
                else:
                    self.stdout.write(self.style.ERROR(f"Failed: {status.get('error', 'Unknown error')}"))
                break

            percentage = status.get('percentage', 0)
            if percentage != last_percentage:
                current_status = status.get('status', 'Working')
                details = status.get('details', '')
                eta = status.get('eta_seconds')

                progress_line = f"{current_status}: {percentage}%"
                if details:
                    progress_line += f" - {details}"
                if eta:
                    eta_min = int(eta / 60)
                    eta_sec = int(eta % 60)
                    progress_line += f" (ETA: {eta_min}m {eta_sec}s)"

                self.stdout.write(progress_line)
                last_percentage = percentage

            time.sleep(2)  # Check every 2 seconds

    def display_job_status(self, job_id, status):
        """Display detailed job status."""
        self.stdout.write(f"Job ID: {job_id}")

        if status.get('completed'):
            self.stdout.write("Status: Completed")
            if status.get('success'):
                self.stdout.write(self.style.SUCCESS(f"Result: {status.get('message', 'Success')}"))
            else:
                self.stdout.write(self.style.ERROR(f"Error: {status.get('error', 'Unknown error')}"))

            total_time = status.get('total_time', 0)
            self.stdout.write(f"Total time: {int(total_time)}s")
        else:
            current = status.get('current', 0)
            total = status.get('total', 0)
            percentage = status.get('percentage', 0)
            current_status = status.get('status', 'Working')
            details = status.get('details', '')

            self.stdout.write(f"Status: {current_status}")
            self.stdout.write(f"Progress: {current}/{total} ({percentage}%)")
            if details:
                self.stdout.write(f"Details: {details}")

            elapsed = status.get('elapsed_time', 0)
            self.stdout.write(f"Elapsed: {int(elapsed)}s")

            eta = status.get('eta_seconds')
            if eta:
                eta_min = int(eta / 60)
                eta_sec = int(eta % 60)
                self.stdout.write(f"ETA: {eta_min}m {eta_sec}s")

    def display_api_status(self):
        """Display API rate limit status."""
        self.stdout.write("API Rate Limit Status:")

        api_status = get_api_status()
        api_health = check_api_health()

        for api_name, status in api_status.items():
            health = "🟢 Healthy" if api_health.get(api_name, False) else "🔴 Down"
            self.stdout.write(f"\n{status['api_name']}: {health}")

            rate_limits = status.get('rate_limits', {})
            current_counts = rate_limits.get('current_counts', {})
            limits = rate_limits.get('limits', {})

            for period in ['daily', 'hourly', 'minute']:
                if period in current_counts:
                    count = current_counts[period]
                    limit = limits.get(period, 'N/A')
                    percentage = int((count / limit * 100)) if isinstance(limit, int) and limit > 0 else 0
                    self.stdout.write(f"  {period.title()}: {count}/{limit} ({percentage}%)")
