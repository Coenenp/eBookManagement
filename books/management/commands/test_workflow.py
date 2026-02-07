"""
Quick Test Suite - Django Management Command
Run comprehensive tests on sample book collection

Usage:
    python manage.py test_workflow --quick
    python manage.py test_workflow --phase epub
    python manage.py test_workflow --full
"""

from django.core.management.base import BaseCommand

from books.models import Book, BookFile, ScanFolder


class Command(BaseCommand):
    help = "Run comprehensive workflow testing"

    def add_arguments(self, parser):
        parser.add_argument(
            "--quick",
            action="store_true",
            help="Run quick validation test (10 files)",
        )
        parser.add_argument(
            "--phase",
            type=str,
            choices=["epub", "comic", "pdf", "all"],
            help="Test specific file type phase",
        )
        parser.add_argument(
            "--full",
            action="store_true",
            help="Run full batch processing test",
        )
        parser.add_argument(
            "--stats",
            action="store_true",
            help="Show current statistics only",
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("=== eBook Workflow Test Suite ===\n"))

        # Get scan folder
        try:
            scan_folder = ScanFolder.objects.get(path__icontains="Sample [To Delete]")
            self.stdout.write(f"📁 Scan Folder: {scan_folder.name}")
            self.stdout.write(f"   Path: {scan_folder.path}\n")
        except ScanFolder.DoesNotExist:
            self.stdout.write(self.style.ERROR("❌ No sample scan folder found!"))
            self.stdout.write("   Add scan folder first:\n")
            self.stdout.write("   Name: Test Sample Books")
            self.stdout.write("   Path: \\\\TS-469L\\Multimedia\\Books -sample DB - Copy\\Sample [To Delete]")
            return

        if options["stats"]:
            self._show_stats(scan_folder)
            return

        if options["quick"]:
            self._run_quick_test(scan_folder)
        elif options["phase"]:
            self._run_phase_test(scan_folder, options["phase"])
        elif options["full"]:
            self._run_full_test(scan_folder)
        else:
            self._show_stats(scan_folder)
            self.stdout.write("\nUsage:")
            self.stdout.write("  --quick      Quick validation (10 files)")
            self.stdout.write("  --phase epub Test EPUB files")
            self.stdout.write("  --full       Full batch test")
            self.stdout.write("  --stats      Show statistics")

    def _show_stats(self, scan_folder):
        """Display current statistics."""
        books = Book.objects.filter(scan_folder=scan_folder)
        reviewed = books.filter(finalmetadata__is_reviewed=True)
        with_covers = books.exclude(finalmetadata__final_cover_path="")

        self.stdout.write("\n📊 Current Statistics:")
        self.stdout.write(f"   Total Books: {books.count()}")
        self.stdout.write(f"   Reviewed: {reviewed.count()} ({reviewed.count()/books.count()*100 if books.count() > 0 else 0:.1f}%)")
        self.stdout.write(f"   With Covers: {with_covers.count()}")

        # File types
        epub_count = BookFile.objects.filter(book__scan_folder=scan_folder, file_format="epub").count()
        cbz_count = BookFile.objects.filter(book__scan_folder=scan_folder, file_format="cbz").count()
        cbr_count = BookFile.objects.filter(book__scan_folder=scan_folder, file_format="cbr").count()
        pdf_count = BookFile.objects.filter(book__scan_folder=scan_folder, file_format="pdf").count()

        self.stdout.write("\n📚 File Types:")
        self.stdout.write(f"   EPUB: {epub_count}")
        self.stdout.write(f"   CBZ: {cbz_count}")
        self.stdout.write(f"   CBR: {cbr_count}")
        self.stdout.write(f"   PDF: {pdf_count}")

    def _run_quick_test(self, scan_folder):
        """Run quick validation test."""
        self.stdout.write(self.style.WARNING("\n🚀 Quick Test - 10 Sample Files"))
        self.stdout.write("   Duration: ~30 minutes\n")

        # TODO: Implement quick test workflow
        self.stdout.write("Steps:")
        self.stdout.write("1. Select 10 sample files")
        self.stdout.write("2. Scan files")
        self.stdout.write("3. Fetch external metadata")
        self.stdout.write("4. Upload custom cover (manual)")
        self.stdout.write("5. View multi-cover selector")
        self.stdout.write("6. Rename with preview")
        self.stdout.write("7. Verify results\n")

        self.stdout.write(self.style.SUCCESS("✓ Quick test template ready"))
        self.stdout.write("  Follow TESTING_WORKFLOW.md for manual steps")

    def _run_phase_test(self, scan_folder, phase):
        """Run specific phase test."""
        self.stdout.write(self.style.WARNING(f"\n🧪 Phase Test - {phase.upper()}"))

        if phase == "epub":
            epub_files = BookFile.objects.filter(book__scan_folder=scan_folder, file_format="epub")
            self.stdout.write(f"   EPUB Files: {epub_files.count()}")
            self.stdout.write("\nTest Scenarios:")
            self.stdout.write("  ✓ Clean metadata EPUBs")
            self.stdout.write("  ✓ Multi-cover selection")
            self.stdout.write("  ✓ Orphaned image cleanup")
            self.stdout.write("  ✓ Metadata embedding")

        elif phase == "comic":
            cbz_count = BookFile.objects.filter(book__scan_folder=scan_folder, file_format="cbz").count()
            cbr_count = BookFile.objects.filter(book__scan_folder=scan_folder, file_format="cbr").count()
            self.stdout.write(f"   CBZ Files: {cbz_count}")
            self.stdout.write(f"   CBR Files: {cbr_count}")

        elif phase == "pdf":
            pdf_count = BookFile.objects.filter(book__scan_folder=scan_folder, file_format="pdf").count()
            self.stdout.write(f"   PDF Files: {pdf_count}")

    def _run_full_test(self, scan_folder):
        """Run full batch processing test."""
        self.stdout.write(self.style.WARNING("\n🎯 Full Batch Test"))
        books = Book.objects.filter(scan_folder=scan_folder)
        self.stdout.write(f"   Total Books: {books.count()}")
        self.stdout.write("   Duration: 4-6 hours (estimated)\n")

        self.stdout.write(self.style.ERROR("⚠ This is a large operation!"))
        self.stdout.write("  Ensure you have:")
        self.stdout.write("  - Sufficient disk space")
        self.stdout.write("  - Good network connection")
        self.stdout.write("  - API rate limits configured")
        self.stdout.write("  - Backup of database\n")

        self.stdout.write("Follow TESTING_WORKFLOW.md for full instructions")
