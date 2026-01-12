"""
Management command to test the intelligent API scanner system.

This command demonstrates the enhanced API tracking and resumption functionality.
"""

import logging

from django.core.management.base import BaseCommand
from django.db import transaction

from books.models import (
    APIAccessLog,
    BookAPICompleteness,
    DataSource,
    ScanFolder,
    ScanSession,
)
from books.scanner.background import BackgroundScanner
from books.scanner.intelligent import IntelligentAPIScanner

logger = logging.getLogger("books.scanner")


class Command(BaseCommand):
    help = "Test intelligent API scanning with graceful degradation and resumption"

    def add_arguments(self, parser):
        parser.add_argument("--folder", type=int, help="Scan folder ID to test with")
        parser.add_argument("--resume-session", type=str, help="Resume a specific scan session by ID")
        parser.add_argument(
            "--show-stats",
            action="store_true",
            help="Show API usage statistics for all books",
        )
        parser.add_argument(
            "--reset-api-logs",
            action="store_true",
            help="Reset all API access logs (for testing)",
        )

    def handle(self, *args, **options):
        if options["show_stats"]:
            self.show_api_statistics()
            return

        if options["reset_api_logs"]:
            self.reset_api_logs()
            return

        if options["resume_session"]:
            self.resume_scan_session(options["resume_session"])
            return

        if options["folder"]:
            self.test_intelligent_scanning(options["folder"])
        else:
            self.stdout.write(self.style.ERROR("Please specify --folder, --resume-session, --show-stats, or --reset-api-logs"))

    def test_intelligent_scanning(self, folder_id):
        """Test intelligent scanning on a specific folder"""
        try:
            scan_folder = ScanFolder.objects.get(id=folder_id)
            self.stdout.write(f"Testing intelligent scanning on: {scan_folder.name}")

            # Create background scanner with intelligent API features
            import uuid

            job_id = str(uuid.uuid4())
            scanner = BackgroundScanner(job_id)

            # Test with intelligent API tracking
            self.stdout.write("Starting intelligent scan with API tracking...")

            # Scan the folder
            result = scanner.scan_folder(
                scan_folder.path,
                language=scan_folder.language,
                enable_external_apis=True,
                content_type=scan_folder.content_type,
            )

            self.stdout.write(self.style.SUCCESS("Intelligent scan completed!"))

            # Show results
            self.stdout.write("\nScan Results:")
            self.stdout.write(f"  Books Processed: {result.get('books_processed', 0)}")
            self.stdout.write(f"  Errors: {result.get('errors', 0)}")
            self.stdout.write(f"  API Mode: {result.get('api_mode', 'unknown')}")
            self.stdout.write(f"  Available APIs: {result.get('available_apis', [])}")
            self.stdout.write(f"  Books Needing Retry: {result.get('books_needing_retry', 0)}")
            if result.get("session_id"):
                self.stdout.write(f"  Session ID: {result['session_id']}")

        except ScanFolder.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"Scan folder with ID {folder_id} not found"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error during scanning: {e}"))
            logger.exception("Error in test scanning")

    def resume_scan_session(self, session_id):
        """Resume an interrupted scan session"""
        try:
            session = ScanSession.objects.get(session_id=session_id)
            self.stdout.write(f"Resuming scan session: {session_id}")

            if not session.can_resume:
                self.stdout.write(self.style.WARNING("Session cannot be resumed (no pending books)"))
                return

            # Create intelligent scanner
            intelligent_scanner = IntelligentAPIScanner()

            # Resume the session
            results = intelligent_scanner.resume_interrupted_scans(session_id)

            self.stdout.write(self.style.SUCCESS(f"Resume completed! Processed {results['processed']} books"))

            # Show updated session stats
            session.refresh_from_db()
            self.show_session_stats(session)

        except ScanSession.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"Scan session '{session_id}' not found"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error resuming session: {e}"))
            logger.exception("Error in resume scanning")

    def show_api_statistics(self):
        """Show comprehensive API usage statistics"""
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write("API USAGE STATISTICS")
        self.stdout.write("=" * 60)

        # Overall stats
        total_logs = APIAccessLog.objects.count()
        successful_logs = APIAccessLog.objects.filter(status=APIAccessLog.SUCCESS).count()
        rate_limited_logs = APIAccessLog.objects.filter(status=APIAccessLog.RATE_LIMITED).count()
        failed_logs = APIAccessLog.objects.filter(status=APIAccessLog.FAILED).count()

        self.stdout.write(f"Total API Access Records: {total_logs}")
        if total_logs > 0:
            self.stdout.write(f"  - Successful: {successful_logs} ({successful_logs/total_logs*100:.1f}%)")
            self.stdout.write(f"  - Rate Limited: {rate_limited_logs} ({rate_limited_logs/total_logs*100:.1f}%)")
            self.stdout.write(f"  - Failed: {failed_logs} ({failed_logs/total_logs*100:.1f}%)")

        # Per-source breakdown
        self.stdout.write("\nPer-Source Breakdown:")
        for source in DataSource.objects.filter(
            name__in=[
                DataSource.GOOGLE_BOOKS,
                DataSource.OPEN_LIBRARY,
                DataSource.COMICVINE,
            ]
        ):
            logs = APIAccessLog.objects.filter(data_source=source)
            if logs.exists():
                success_rate = logs.filter(status=APIAccessLog.SUCCESS).count() / logs.count() * 100
                self.stdout.write(f"  {source.name}: {logs.count()} attempts, {success_rate:.1f}% success")

        # Recent sessions
        self.stdout.write("\nRecent Scan Sessions:")
        sessions = ScanSession.objects.all()[:5]
        for session in sessions:
            status = "✅ Complete" if session.completed_at else "🔄 Active" if session.is_active else "⏸️ Paused"
            resume_status = f" (Resume: {len(session.resume_queue)} pending)" if session.can_resume else ""
            self.stdout.write(f"  {session.session_id}: {status}{resume_status}")

        # Books needing external data
        books_needing_scan = BookAPICompleteness.objects.filter(needs_external_scan=True).count()
        self.stdout.write(f"\nBooks needing external API data: {books_needing_scan}")

        # High priority books
        high_priority = BookAPICompleteness.objects.filter(scan_priority="high").count()
        self.stdout.write(f"High priority books: {high_priority}")

    def show_scan_results(self, job_id):
        """Show results of a scan session"""
        try:
            session = ScanSession.objects.get(session_id=job_id)
            self.show_session_stats(session)
        except ScanSession.DoesNotExist:
            self.stdout.write("No session statistics available for this job")

    def show_session_stats(self, session):
        """Display detailed session statistics"""
        self.stdout.write("\n" + "-" * 40)
        self.stdout.write(f"SESSION: {session.session_id}")
        self.stdout.write("-" * 40)
        self.stdout.write(f"Progress: {session.processed_books}/{session.total_books} ({session.completion_percentage:.1f}%)")
        self.stdout.write(f"External data: {session.books_with_external_data} books ({session.external_data_percentage:.1f}%)")

        if session.api_calls_made:
            self.stdout.write("API Calls Made:")
            for source, count in session.api_calls_made.items():
                failures = session.api_failures.get(source, 0)
                rate_limits = session.rate_limits_hit.get(source, 0)
                success_rate = ((count - failures) / count * 100) if count > 0 else 0
                self.stdout.write(f"  {source}: {count} calls, {success_rate:.1f}% success, {rate_limits} rate limits")

        if session.can_resume:
            self.stdout.write(f"Can resume: Yes ({len(session.resume_queue)} books pending)")
        else:
            self.stdout.write("Can resume: No")

    def reset_api_logs(self):
        """Reset all API logs for testing purposes"""
        if input("Are you sure you want to reset all API logs? (yes/no): ").lower() == "yes":
            with transaction.atomic():
                APIAccessLog.objects.all().delete()
                ScanSession.objects.all().delete()
                BookAPICompleteness.objects.all().delete()
            self.stdout.write(self.style.SUCCESS("All API logs have been reset"))
        else:
            self.stdout.write("Operation cancelled")
