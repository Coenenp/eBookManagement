"""Management command: plan or apply lossless EPUB structural fixes.

Usage::

    python manage.py epub_fix <path> [--apply] [--output-dir DIR] [--cover FILE]

Without ``--apply`` the command only prints the plan of fixes and writes
nothing. With ``--apply`` it writes ``<stem>_fixed.epub`` into ``--output-dir``
(default: beside the input) and refuses to write over the input path.
"""

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from books.utils.epub_fix import fix_epub, plan_fixes


class Command(BaseCommand):
    help = "Plan or apply lossless EPUB structural fixes."

    def add_arguments(self, parser):
        parser.add_argument("path", help="An .epub file to fix.")
        parser.add_argument("--apply", action="store_true", help="Write the fixed EPUB (default: print plan only).")
        parser.add_argument("--output-dir", help="Directory for the fixed output (default: beside the input).")
        parser.add_argument("--cover", help="Cover image to embed (used with --apply).")

    def handle(self, *args, **options):
        src = Path(options["path"])
        if not src.is_file():
            raise CommandError(f"Path not found: {src}")

        cover = options["cover"]

        if options["apply"]:
            out_dir = Path(options["output_dir"]) if options["output_dir"] else src.parent
            out_dir.mkdir(parents=True, exist_ok=True)
            output = out_dir / (src.stem + "_fixed" + src.suffix)
            if output.resolve() == src.resolve():
                raise CommandError("output path must differ from the input path")
            fix_epub(src, output, cover=cover)
            self.stdout.write(f"Wrote: {output}")
        else:
            try:
                plan = plan_fixes(src, cover=cover)
            except ValueError as exc:
                raise CommandError(str(exc))
            if not plan:
                self.stdout.write(f"No fixes needed: {src}")
            else:
                self.stdout.write(f"Plan for {src}:")
                for f in plan:
                    self.stdout.write(f"  [{f.code}] {f.description}")
