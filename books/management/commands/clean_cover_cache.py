"""
Management command to clean and maintain the cover cache.

This command:
1. Reports current cover-cache statistics (file count and total size).
2. Deletes cached covers that are not referenced by any ``BookFile``.
3. Optionally rebuilds missing internal covers from their source files.

Use ``--dry-run`` to preview changes without touching the filesystem.
"""

import logging

from django.core.management.base import BaseCommand

from books.utils.cover_cache import CoverCache

logger = logging.getLogger("books.scanner")


def _format_size(size_bytes):
    """Format a byte count into a human-readable string."""
    size_bytes = int(size_bytes or 0)
    if size_bytes == 0:
        return "0 B"

    names = ["B", "KB", "MB", "GB", "TB"]
    value = float(size_bytes)
    index = 0
    while value >= 1024.0 and index < len(names) - 1:
        value /= 1024.0
        index += 1

    return f"{value:.1f} {names[index]}"


class Command(BaseCommand):
    help = "Clean orphaned cached covers and optionally rebuild missing internal covers"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be done without making changes",
        )
        parser.add_argument(
            "--rebuild-missing",
            action="store_true",
            help="Re-extract internal covers for BookFiles whose cached cover is missing",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        rebuild_missing = options["rebuild_missing"]

        self.stdout.write(self.style.SUCCESS("\n" + "=" * 70))
        self.stdout.write(self.style.SUCCESS("COVER CACHE MAINTENANCE"))
        self.stdout.write(self.style.SUCCESS("=" * 70))

        if dry_run:
            self.stdout.write(self.style.WARNING("\nDRY RUN MODE - No changes will be made\n"))

        file_count, total_bytes = CoverCache.get_cache_size()
        self.stdout.write("\n" + "-" * 70)
        self.stdout.write(self.style.NOTICE("CACHE STATISTICS"))
        self.stdout.write("-" * 70)
        self.stdout.write(f"  Cached files: {file_count}")
        self.stdout.write(f"  Total size:   {_format_size(total_bytes)}")

        self._clean_orphans(dry_run)

        if rebuild_missing:
            self._rebuild_missing(dry_run)

        self.stdout.write("\n" + "=" * 70)

    def _clean_orphans(self, dry_run):
        """Delete (or preview deletion of) unreferenced cached covers."""
        self.stdout.write("\n" + "-" * 70)
        self.stdout.write(self.style.NOTICE("ORPHAN CLEANUP"))
        self.stdout.write("-" * 70)

        deleted, errors = CoverCache.cleanup_orphans(dry_run=dry_run)

        if dry_run:
            self.stdout.write(self.style.WARNING(f"  Would delete orphaned covers: {deleted}"))
        else:
            self.stdout.write(self.style.SUCCESS(f"  Deleted orphaned covers: {deleted}"))

        if errors:
            self.stdout.write(self.style.ERROR(f"  Errors encountered: {errors}"))
        else:
            self.stdout.write(self.style.SUCCESS("  Errors: 0"))

    def _rebuild_missing(self, dry_run):
        """Re-extract internal covers whose cached file is missing."""
        from books.models import BookFile
        from books.scanner.folder import _detect_and_extract_cover

        self.stdout.write("\n" + "-" * 70)
        self.stdout.write(self.style.NOTICE("REBUILD MISSING INTERNAL COVERS"))
        self.stdout.write("-" * 70)

        candidates = BookFile.objects.filter(has_internal_cover=True)
        rebuilt = 0
        errors = 0

        for book_file in candidates.iterator():
            if not self._needs_rebuild(book_file):
                continue

            if dry_run:
                rebuilt += 1
                self.stdout.write(self.style.WARNING(f"  [would rebuild] {book_file.file_path}"))
                continue

            try:
                cover_path, source_type, internal_path, has_internal = _detect_and_extract_cover(
                    book_file.file_path,
                    book_file.file_format,
                    [],
                )

                if cover_path:
                    book_file.cover_path = cover_path
                    book_file.cover_source_type = source_type or book_file.cover_source_type
                    book_file.cover_internal_path = internal_path or ""
                    book_file.has_internal_cover = has_internal
                    book_file.save(update_fields=["cover_path", "cover_source_type", "cover_internal_path", "has_internal_cover"])
                    rebuilt += 1
                    self.stdout.write(self.style.SUCCESS(f"  Rebuilt cover for {book_file.file_path}"))
                else:
                    errors += 1
                    logger.warning(f"Could not extract internal cover for {book_file.file_path}")
            except Exception as e:
                errors += 1
                logger.error(f"Failed to rebuild cover for {book_file.file_path}: {e}")

        if dry_run:
            self.stdout.write(self.style.WARNING(f"  Would rebuild covers: {rebuilt}"))
        else:
            self.stdout.write(self.style.SUCCESS(f"  Rebuilt covers: {rebuilt}"))

        if errors:
            self.stdout.write(self.style.ERROR(f"  Errors encountered: {errors}"))
        else:
            self.stdout.write(self.style.SUCCESS("  Errors: 0"))

    @staticmethod
    def _needs_rebuild(book_file):
        """Return True when a BookFile has an internal cover whose cached file is gone."""
        if not book_file.file_path or not book_file.cover_path:
            return False

        # Only internal covers are stored in the cover cache.
        if not book_file.cover_path.startswith("cover_cache/"):
            return False

        return not CoverCache.media_exists(book_file.cover_path)
