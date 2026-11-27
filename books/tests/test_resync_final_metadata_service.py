"""Golden output and parity tests for the resync_final_metadata service layer."""

import csv
import os
import tempfile
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from books.models import Book, BookTitle, DataSource, FinalMetadata


class ResyncFinalMetadataGoldenTests(TestCase):
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

    def _run(self, *args):
        out = StringIO()
        call_command("resync_final_metadata", *args, stdout=out)
        return out.getvalue()

    def test_golden_dry_run(self):
        self._book_with_changed_title()
        out = self._run()
        self.assertEqual(
            out,
            "Checked 1 books\n"
            "Changed titles: 1\n"
            "Changed authors: 0\n"
            "Changed series: 0\n",
        )

    def test_golden_execute(self):
        book, fm = self._book_with_changed_title()
        out = self._run("--execute")
        self.assertEqual(
            out,
            "Checked 1 books\n"
            "Changed titles: 1\n"
            "Changed authors: 0\n"
            "Changed series: 0\n",
        )
        fm.refresh_from_db()
        self.assertEqual(fm.final_title, "New Title")

    def test_golden_limit(self):
        self._book_with_changed_title()
        self._book_with_changed_title()
        self._book_with_changed_title()
        out = self._run("--limit", "1")
        self.assertEqual(
            out,
            "Checked 1 books\n"
            "Changed titles: 1\n"
            "Changed authors: 0\n"
            "Changed series: 0\n",
        )

    def test_golden_csv_utf8(self):
        book, fm = self._book_with_changed_title()
        BookTitle.objects.filter(book=book).update(title="Café")
        path = tempfile.mktemp(suffix=".csv")
        try:
            out = self._run("--execute", "--csv", path)
            lines = out.splitlines()
            self.assertEqual(
                lines[:4],
                [
                    "Checked 1 books",
                    "Changed titles: 1",
                    "Changed authors: 0",
                    "Changed series: 0",
                ],
            )
            self.assertEqual(lines[4], f"Wrote 2 changed fields to {path}")
            with open(path, encoding="utf-8", errors="replace") as fh:
                rows = list(csv.reader(fh))
            new_titles = [r[3] for r in rows[1:] if r[1] == "final_title"]
            self.assertIn("Café", new_titles)
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_golden_second_execute_reports_zero(self):
        self._book_with_changed_title()
        self._run("--execute")
        out = self._run("--execute")
        self.assertEqual(
            out,
            "Checked 1 books\n"
            "Changed titles: 0\n"
            "Changed authors: 0\n"
            "Changed series: 0\n",
        )

    def test_golden_approved_book_untouched(self):
        book, fm = self._book_with_changed_title(is_reviewed=True)
        out = self._run("--execute")
        self.assertEqual(
            out,
            "Checked 0 books\n"
            "Changed titles: 0\n"
            "Changed authors: 0\n"
            "Changed series: 0\n",
        )
        fm.refresh_from_db()
        self.assertEqual(fm.final_title, "Old Title")


def _csv_cell(value):
    return "" if value is None else str(value)


class ResyncFinalMetadataParityTests(TestCase):
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

    def test_command_and_service_agree(self):
        from books.services.authors import resync_final_metadata

        book, fm = self._book_with_changed_title()

        # Command path.
        cmd_out = StringIO()
        path = tempfile.mktemp(suffix=".csv")
        try:
            call_command(
                "resync_final_metadata", "--execute", "--csv", path, stdout=cmd_out
            )
            with open(path, encoding="utf-8") as fh:
                cmd_rows = list(csv.reader(fh))
        finally:
            if os.path.exists(path):
                os.unlink(path)
        fm.refresh_from_db()
        cmd_state = (
            fm.final_title,
            fm.final_title_confidence,
            fm.final_author,
            fm.final_series,
        )

        # Reset the same book to its pre-resync state and run the service path.
        fm.final_title = "Old Title"
        fm.final_title_confidence = 0.5
        fm.save(update_fields=["final_title", "final_title_confidence"])

        result = resync_final_metadata(execute=True)
        fm.refresh_from_db()
        svc_state = (
            fm.final_title,
            fm.final_title_confidence,
            fm.final_author,
            fm.final_series,
        )

        # The command prints exactly the service counts, plus the CSV count.
        self.assertEqual(
            cmd_out.getvalue().splitlines(),
            [
                f"Checked {result['checked']} books",
                f"Changed titles: {result['changed_titles']}",
                f"Changed authors: {result['changed_authors']}",
                f"Changed series: {result['changed_series']}",
                f"Wrote {len(result['changes'])} changed fields to {path}",
            ],
        )
        # The service changes are the CSV rows (minus the header).
        expected_rows = [["book_id", "field", "old", "new"]] + [
            [_csv_cell(book_id), field, _csv_cell(old), _csv_cell(new)]
            for (book_id, field, old, new) in result["changes"]
        ]
        self.assertEqual(cmd_rows, expected_rows)
        self.assertEqual(svc_state, cmd_state)

