"""Management command: run the EPUB structural checker.

Usage::

    python manage.py epub_check <path-to-epub-or-folder> [--json]
"""

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from books.utils.epub_check import check_epub


class Command(BaseCommand):
    help = "Run the EPUB structural checker over a file or a folder of .epub files."

    def add_arguments(self, parser):
        parser.add_argument("path", help="An .epub file or a folder to scan recursively.")
        parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")

    def handle(self, *args, **options):
        path = Path(options["path"])
        if path.is_file():
            files = [path]
        elif path.is_dir():
            files = sorted(path.rglob("*.epub"))
        else:
            raise CommandError(f"Path not found: {path}")

        if not files:
            self.stderr.write(f"No .epub files found under {path}")
            return

        reports = [check_epub(f) for f in files]

        if options["json"]:
            if len(reports) == 1:
                self.stdout.write(reports[0].to_json())
            else:
                self.stdout.write(json.dumps([r.to_dict() for r in reports], indent=2))
        else:
            for r in reports:
                status = "OK" if r.ok else "FAIL"
                self.stdout.write(f"{status}: {r.file} ({len(r.findings)} finding(s))")
                for f in r.findings:
                    self.stdout.write(f"  [{f.severity.value}] {f.code}: {f.message}")
