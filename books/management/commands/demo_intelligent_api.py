"""
Management command to demonstrate intelligent API scanner integration.

This shows how the new API tracking system integrates with existing scanning.
"""
import logging
from django.core.management.base import BaseCommand
from django.db import transaction
from books.models import Book, DataSource, APIAccessLog, ScanSession, BookAPICompleteness


logger = logging.getLogger('books.scanner')


class Command(BaseCommand):
    help = 'Demonstrate intelligent API tracking integration'

    def add_arguments(self, parser):
        parser.add_argument(
            '--setup-demo',
            action='store_true',
            help='Set up demo data for API tracking'
        )
        parser.add_argument(
            '--simulate-api-calls',
            action='store_true',
            help='Simulate API calls and demonstrate tracking'
        )

    def handle(self, *args, **options):
        if options['setup_demo']:
            self.setup_demo_data()
        elif options['simulate_api_calls']:
            self.simulate_api_interactions()
        else:
            self.show_system_overview()

    def setup_demo_data(self):
        """Create sample data to demonstrate API tracking"""
        self.stdout.write("Setting up demo data for API tracking system...")

        # Get some existing books
        books = Book.objects.available()[:5]
        if not books:
            self.stdout.write(self.style.ERROR("No books found. Please run a scan first."))
            return

        # Get API data sources
        google_books = DataSource.objects.filter(name=DataSource.GOOGLE_BOOKS).first()
        open_library = DataSource.objects.filter(name=DataSource.OPEN_LIBRARY).first()

        if not google_books or not open_library:
            self.stdout.write(self.style.ERROR("Required data sources not found."))
            return

        with transaction.atomic():
            for book in books:
                # Create API access logs with different statuses
                if book.pk % 3 == 0:
                    # Successful Google Books access
                    log, created = APIAccessLog.objects.get_or_create(
                        book=book,
                        data_source=google_books,
                        defaults={
                            'status': APIAccessLog.SUCCESS,
                            'metadata_retrieved': True,
                            'items_found': 5,
                            'confidence_score': 0.8
                        }
                    )
                    log.record_attempt(success=True, items_found=5, confidence=0.8, metadata_retrieved=True)
                elif book.pk % 3 == 1:
                    # Rate limited Open Library
                    log, created = APIAccessLog.objects.get_or_create(
                        book=book,
                        data_source=open_library,
                        defaults={'status': APIAccessLog.RATE_LIMITED}
                    )
                    log.record_attempt(success=False, error_message="Rate limit exceeded")
                else:
                    # Failed API call
                    log, created = APIAccessLog.objects.get_or_create(
                        book=book,
                        data_source=google_books,
                        defaults={'status': APIAccessLog.FAILED}
                    )
                    log.record_attempt(success=False, error_message="API timeout")

                # Create completeness tracking
                completeness, created = BookAPICompleteness.objects.get_or_create(
                    book=book,
                    defaults={
                        'google_books_complete': book.pk % 3 == 0,
                        'open_library_complete': False,
                        'needs_external_scan': True,
                        'missing_sources': ['Open Library'] if book.pk % 3 != 2 else []
                    }
                )
                completeness.calculate_completeness()

        # Create a demo scan session
        session = ScanSession.objects.create(
            session_id='demo_session_001',
            total_books=len(books),
            processed_books=len(books),
            books_with_external_data=len([b for b in books if b.pk % 3 == 0]),
            api_calls_made={
                'Google Books': len(books),
                'Open Library': len(books) // 2
            },
            api_failures={
                'Google Books': len([b for b in books if b.pk % 3 == 2]),
                'Open Library': len([b for b in books if b.pk % 3 == 1])
            },
            rate_limits_hit={
                'Open Library': len([b for b in books if b.pk % 3 == 1])
            },
            is_active=False,
            can_resume=True,
            resume_queue=[
                {
                    'book_id': b.pk,
                    'missing_sources': ['Open Library'],
                    'added_at': '2024-01-15T10:00:00Z'
                } for b in books if b.pk % 3 != 0
            ]
        )

        self.stdout.write(self.style.SUCCESS(f"Demo data created for {len(books)} books"))
        self.stdout.write(f"Session created: {session.session_id}")

    def simulate_api_interactions(self):
        """Simulate API interactions to show intelligent behavior"""
        self.stdout.write("Simulating intelligent API interactions...")

        # Get books that need external data
        books_needing_scan = BookAPICompleteness.objects.filter(
            needs_external_scan=True
        )[:3]

        if not books_needing_scan:
            self.stdout.write(self.style.WARNING("No books need external scanning. Run --setup-demo first."))
            return

        google_books = DataSource.objects.filter(name=DataSource.GOOGLE_BOOKS).first()

        for completeness in books_needing_scan:
            book = completeness.book
            self.stdout.write(f"\nProcessing book: {book.title}")

            # Check if we can retry Google Books
            log, created = APIAccessLog.objects.get_or_create(
                book=book,
                data_source=google_books,
                defaults={'status': APIAccessLog.NOT_ATTEMPTED}
            )

            if log.can_retry_now:
                self.stdout.write("  ✅ API available, making request...")
                # Simulate successful request
                log.record_attempt(
                    success=True,
                    items_found=3,
                    confidence=0.75,
                    metadata_retrieved=True
                )
                completeness.mark_source_complete('Google Books')
                self.stdout.write("  📚 Metadata retrieved successfully!")
            else:
                next_retry = log.next_retry_after.strftime('%Y-%m-%d %H:%M') if log.next_retry_after else 'N/A'
                self.stdout.write(f"  ⏳ API not available (next retry: {next_retry})")

        self.stdout.write(self.style.SUCCESS("\nAPI interaction simulation complete!"))

    def show_system_overview(self):
        """Show overview of the intelligent API system"""
        self.stdout.write("\n" + "="*60)
        self.stdout.write("INTELLIGENT API SCANNING SYSTEM OVERVIEW")
        self.stdout.write("="*60)

        # System components
        self.stdout.write("\n📦 SYSTEM COMPONENTS:")
        self.stdout.write("  • APIAccessLog: Tracks per-book API success/failure")
        self.stdout.write("  • ScanSession: Manages scan sessions and resumption")
        self.stdout.write("  • BookAPICompleteness: Optimizes future scans")
        self.stdout.write("  • IntelligentAPIScanner: Graceful degradation logic")
        self.stdout.write("  • BackgroundScanner: Integrated intelligent API management")

        # Current state
        total_books = Book.objects.count()
        api_logs = APIAccessLog.objects.count()
        sessions = ScanSession.objects.count()
        completeness_records = BookAPICompleteness.objects.count()

        self.stdout.write("\n CURRENT STATE:")
        self.stdout.write(f"  • Total books: {total_books}")
        self.stdout.write(f"  • API access logs: {api_logs}")
        self.stdout.write(f"  • Scan sessions: {sessions}")
        self.stdout.write(f"  • Completeness records: {completeness_records}")

        # Key features
        self.stdout.write("\n KEY FEATURES:")
        self.stdout.write("  • Continues scanning when APIs fail")
        self.stdout.write("  • Tracks successful API access per book")
        self.stdout.write("  • Creates resumption queues for failed calls")
        self.stdout.write("  • Automatic retry with exponential backoff")
        self.stdout.write("  • Intelligent API availability checking")
        self.stdout.write("  • Graceful degradation and recovery")

        # Usage examples
        self.stdout.write("\n USAGE EXAMPLES:")
        self.stdout.write("  python manage.py demo_intelligent_api --setup-demo")
        self.stdout.write("  python manage.py demo_intelligent_api --simulate-api-calls")
        self.stdout.write("  python manage.py test_intelligent_scan --show-stats")

        # Integration points
        self.stdout.write("\n INTEGRATION POINTS:")
        self.stdout.write("  • Enhanced background scanner extends existing system")
        self.stdout.write("  • Intelligent scanner works with rate limiting system")
        self.stdout.write("  • API tracking integrates with external data sources")
        self.stdout.write("  • Seamless integration with current scanning workflow")

        self.stdout.write("\n" + "="*60)
