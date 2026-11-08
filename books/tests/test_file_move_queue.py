"""FileMove queue schema: QUEUED state, queued_at, and batch_id.

A queued move is enqueued for a later batch and must never be touched by the
recovery or purge commands, which select only their own explicit allowlists.
"""

import io

from django.core.management import call_command
from django.test import TestCase

from books.models import FileMove


class FileMoveQueueTests(TestCase):
    def test_state_choices_include_queued(self):
        self.assertIn("queued", dict(FileMove.State.choices))

    def test_queued_row_created_and_filtered_by_batch_id(self):
        FileMove.objects.create(
            source_path="/s/a", target_path="/t/a",
            state=FileMove.State.QUEUED, batch_id="batch-123",
        )
        FileMove.objects.create(
            source_path="/s/b", target_path="/t/b",
            state=FileMove.State.PLANNED, batch_id="batch-456",
        )
        qs = FileMove.objects.filter(state=FileMove.State.QUEUED, batch_id="batch-123")
        self.assertEqual(qs.count(), 1)
        self.assertEqual(qs.get().batch_id, "batch-123")

    def test_queued_row_has_null_queued_at_by_default(self):
        row = FileMove.objects.create(
            source_path="/s/a", target_path="/t/a",
            state=FileMove.State.QUEUED, batch_id="b",
        )
        self.assertIsNone(row.queued_at)

    def test_recover_file_moves_ignores_queued_rows(self):
        queued = FileMove.objects.create(
            source_path="/s/a", target_path="/t/a",
            state=FileMove.State.QUEUED, batch_id="b",
        )
        out = io.StringIO()
        call_command("recover_file_moves", stdout=out)
        queued.refresh_from_db()
        self.assertEqual(queued.state, FileMove.State.QUEUED)
        self.assertIn("0 recoverable move(s)", out.getvalue())

    def test_purge_pending_deletions_ignores_queued_rows(self):
        queued = FileMove.objects.create(
            source_path="/s/a", target_path="/t/a",
            state=FileMove.State.QUEUED, batch_id="b",
        )
        out = io.StringIO()
        call_command("purge_pending_deletions", stdout=out)
        queued.refresh_from_db()
        self.assertEqual(queued.state, FileMove.State.QUEUED)
        self.assertIn("0 eligible row(s)", out.getvalue())
