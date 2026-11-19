"""Tests for the resync_final_metadata management command (Part C)."""

import csv
import os
import tempfile
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from books.models import Book, BookTitle, DataSource, FinalMetadata


class ResyncFinalMetadataCommandTests(TestCase):
    def _source(self, name):
        return DataSource.objects.get_or_create(
            name=name, defaults={"priority": 1, "trust_level": 5}
        )[0]

    def _book_with_changed_title(self, **final_kwargs):
        book = Book.objects.create()
        epub = self._source(DataSource.EPUB_INTERNAL)
        BookTitle.objects.create(book=book, title="New Title", source=epub, confidence=0.8)
        defaults = {"final_title": "Old Title", "final_title_confidence": 0.5}
        defaults.update(final_kwargs)
        fm = FinalMetadata.objects.create(book=book, **defaults)
        return book, fm

    def test_dry_run_stores_nothing_and_counts_changed_title(self):
        book, fm = self._book_with_changed_title()

        out = StringIO()
        call_command("resync_final_metadata", stdout=out)

        fm.refresh_from_db()
        self.assertEqual(fm.final_title, "Old Title")
        self.assertEqual(fm.final_title_confidence, 0.5)
        self.assertIn("Checked 1 books", out.getvalue())
        self.assertIn("Changed titles: 1", out.getvalue())
        self.assertIn("Changed authors: 0", out.getvalue())
        self.assertIn("Changed series: 0", out.getvalue())

    def test_execute_stores_only_seven_fields(self):
        book, fm = self._book_with_changed_title(
            final_cover_path="/covers/x.jpg",
            final_cover_confidence=0.9,
            overall_confidence=0.7,
            completeness_score=0.6,
            accuracy_score=0.55,
        )

        call_command("resync_final_metadata", "--execute")

        fm.refresh_from_db()
        self.assertEqual(fm.final_title, "New Title")
        self.assertEqual(fm.final_title_confidence, 0.8)
        self.assertEqual(fm.final_cover_path, "/covers/x.jpg")
        self.assertEqual(fm.final_cover_confidence, 0.9)
        self.assertEqual(fm.overall_confidence, 0.7)
        self.assertEqual(fm.completeness_score, 0.6)
        self.assertEqual(fm.accuracy_score, 0.55)

    def test_approved_book_never_touched(self):
        book, fm = self._book_with_changed_title(is_reviewed=True)

        call_command("resync_final_metadata", "--execute")

        fm.refresh_from_db()
        self.assertEqual(fm.final_title, "Old Title")

    def test_csv_holds_changed_fields(self):
        book, fm = self._book_with_changed_title()

        path = tempfile.mktemp(suffix=".csv")
        try:
            call_command("resync_final_metadata", "--csv", path)

            with open(path) as fh:
                rows = list(csv.reader(fh))

            self.assertEqual(rows[0], ["book_id", "field", "old", "new"])
            fields = {r[1]: (r[2], r[3]) for r in rows[1:]}
            self.assertIn("final_title", fields)
            self.assertIn("final_title_confidence", fields)
            self.assertEqual(fields["final_title"], ("Old Title", "New Title"))
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_second_execute_changes_nothing(self):
        book, fm = self._book_with_changed_title()

        call_command("resync_final_metadata", "--execute")

        out = StringIO()
        call_command("resync_final_metadata", "--execute", stdout=out)
        self.assertIn("Changed titles: 0", out.getvalue())

    def test_limit_stops_after_n_books(self):
        self._book_with_changed_title()
        self._book_with_changed_title()
        self._book_with_changed_title()

        out = StringIO()
        call_command("resync_final_metadata", "--limit", "1", stdout=out)
        self.assertIn("Checked 1 books", out.getvalue())
