"""Django management command for scanning ebooks.

This command provides a CLI interface for scanning ebook folders
and extracting metadata using the EbookScanner engine.
"""
from django.core.management.base import BaseCommand
from books.scanner.scanner_engine import EbookScanner


class Command(BaseCommand):
    help = 'Scan folders for ebooks and extract metadata'

    def add_arguments(self, parser):
        parser.add_argument('folder_path', nargs='?', type=str)
        parser.add_argument('--rescan', action='store_true')

    def handle(self, *args, **options):
        scanner = EbookScanner(rescan=options.get('rescan', False))
        scanner.run(options.get('folder_path'))
