"""Part A service tests for the batch review actions PR (J2b).

Each test pins one service behaviour added in J2b: the additive ``skipped``
manifest key, the ``state`` key on every ``batch_rows`` row, ``batch_summary``,
``remove_holds``, ``apply_reviewed``, the single context build during prepare,
and the ``HOLD_REASON_CODES`` constant.
"""

import json
import re
import shutil
import tempfile
from io import StringIO
from pathlib import Path
from unittest import mock

from django.core.management import call_command
from django.test import TestCase

from books.services.batches import (
    HOLD_REASON_CODES,
    apply_batch,
    apply_reviewed,
    batch_rows,
    batch_summary,
    reject_books,
    remove_holds,
    select_batch,
    write_batch_files,
)
from books.tests.test_helpers import create_test_book_with_file, create_test_scan_folder


class _BatchBase(TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(self.temp_dir, ignore_errors=True))
        self.scan_folder = create_test_scan_folder(temp_dir=self.temp_dir)
        self.manifest_dir = Path(self.temp_dir) / "manifests"
        self.manifest_dir.mkdir()

    def _make_book(self, name, title, author, series="", number=""):
        stem = re.sub(r"[^A-Za-z0-9 ]+", " ", f"{name} {title} {author}")
        stem = re.sub(r"\s+", " ", stem).strip()[:80]
        path = Path(self.temp_dir) / f"{stem}.epub"
        path.write_bytes(b"fake")
        cover = str(Path(self.temp_dir) / f"{name}_cover.jpg")
        Path(cover).write_bytes(b"\xff\xd8\xff" + b"\x00" * 16)
        book = create_test_book_with_file(
            file_path=str(path),
            file_format="epub",
            scan_folder=self.scan_folder,
            content_type="ebook",
        )
        from books.models import FinalMetadata

        FinalMetadata.objects.create(
            book=book,
            final_title=title,
            final_title_confidence=0.95,
            final_author=author,
            final_author_confidence=0.95,
            final_cover_path=cover,
            final_cover_confidence=0.95,
            language="en",
            final_series=series,
            final_series_number=number,
        )
        return book

    def _prepare(self):
        selection = select_batch(size=25, manifest_dir=self.manifest_dir)
        result = write_batch_files(selection, self.manifest_dir)
        return result["manifest_path"], result["manifest"]


class ApplyBatchSkippedKeyTests(_BatchBase):
    def test_apply_records_skipped_key(self):
        b1 = self._make_book("sk", "Skip Key", "Jane Doe")
        mpath, _ = self._prepare()
        b1.finalmetadata.final_title_confidence = 0.5
        b1.finalmetadata.save(update_fields=["final_title_confidence"])

        apply_batch(
            manifest_path=str(mpath),
            confirm=1,
            exclude_ids=None,
            exclude_reason="review",
            allow_high_exclusion=True,
        )
        data = json.loads(mpath.read_text())
        self.assertIn("skipped", data)
        self.assertEqual(data["skipped"], {str(b1.id): "title confidence"})

    def test_held_books_stay_in_excluded_not_skipped(self):
        b1 = self._make_book("hd", "Held Book", "Jane Doe")
        b2 = self._make_book("ap", "Approved Book", "John Smith")
        mpath, _ = self._prepare()
        reject_books(str(mpath), b1.id, "bad cover")

        apply_batch(
            manifest_path=str(mpath),
            confirm=2,
            exclude_ids=None,
            exclude_reason="review",
            allow_high_exclusion=True,
        )
        data = json.loads(mpath.read_text())
        self.assertEqual(data["excluded"][str(b1.id)], "bad cover")
        self.assertNotIn(str(b1.id), data.get("skipped", {}))
        self.assertIn(b2.id, data["applied_ids"])

    def test_old_applied_manifest_without_skipped_key_reads(self):
        # An applied manifest written before the 'skipped' key exists still
        # loads and its rows get an empty reason for 'not approved' books.
        b1 = self._make_book("old", "Old Manifest", "Jane Doe")
        mpath, manifest = self._prepare()
        apply_batch(
            manifest_path=str(mpath),
            confirm=1,
            exclude_ids=None,
            exclude_reason="review",
            allow_high_exclusion=True,
        )
        data = json.loads(mpath.read_text())
        del data["skipped"]
        mpath.write_text(json.dumps(data, indent=2))

        rows = batch_rows(mpath)
        self.assertEqual(rows[0]["state"], "approved")


class BatchRowsStateTests(_BatchBase):
    def test_state_prepared_pending_and_held(self):
        b1 = self._make_book("sa", "State Alpha", "Jane Doe")
        b2 = self._make_book("sb", "State Beta", "John Smith")
        mpath, _ = self._prepare()
        reject_books(str(mpath), b1.id, "bad cover")

        rows = batch_rows(mpath)
        by_id = {r["id"]: r for r in rows}
        self.assertEqual(by_id[b1.id]["state"], "held")
        self.assertEqual(by_id[b2.id]["state"], "pending")

    def test_state_applied_approved_and_held(self):
        b1 = self._make_book("aa", "App Alpha", "Jane Doe")
        b2 = self._make_book("ab", "App Beta", "John Smith")
        mpath, _ = self._prepare()
        reject_books(str(mpath), b1.id, "bad cover")
        apply_batch(
            manifest_path=str(mpath),
            confirm=2,
            exclude_ids=None,
            exclude_reason="review",
            allow_high_exclusion=True,
        )

        rows = batch_rows(mpath)
        by_id = {r["id"]: r for r in rows}
        self.assertEqual(by_id[b1.id]["state"], "held")
        self.assertEqual(by_id[b2.id]["state"], "approved")

    def test_state_not_approved_with_skip_reason(self):
        b1 = self._make_book("na", "Not App", "Jane Doe")
        mpath, _ = self._prepare()
        b1.finalmetadata.final_title_confidence = 0.5
        b1.finalmetadata.save(update_fields=["final_title_confidence"])
        apply_batch(
            manifest_path=str(mpath),
            confirm=1,
            exclude_ids=None,
            exclude_reason="review",
            allow_high_exclusion=True,
        )

        rows = batch_rows(mpath)
        self.assertEqual(rows[0]["state"], "not approved")
        self.assertEqual(rows[0]["skip_reason"], "title confidence")

    def test_applied_flag_is_none(self):
        b1 = self._make_book("af", "App Flag", "Jane Doe")
        mpath, _ = self._prepare()
        apply_batch(
            manifest_path=str(mpath),
            confirm=1,
            exclude_ids=None,
            exclude_reason="review",
            allow_high_exclusion=True,
        )

        rows = batch_rows(mpath)
        self.assertIsNone(rows[0]["flag"])


class BatchSummaryTests(_BatchBase):
    def test_summary_prepared(self):
        b1 = self._make_book("sp1", "Sum Prep One", "Jane Doe")
        b2 = self._make_book("sp2", "Sum Prep Two", "John Smith")
        mpath, _ = self._prepare()
        reject_books(str(mpath), b1.id, "bad cover")

        s = batch_summary(mpath)
        self.assertEqual(s, {"approve": 1, "hold": 1, "not_approved": 0, "total": 2})

    def test_summary_applied(self):
        b1 = self._make_book("sh1", "Sum Hold", "Jane Doe")
        b2 = self._make_book("sh2", "Sum Approve", "John Smith")
        b3 = self._make_book("sh3", "Sum Skip", "Mary Jane")
        mpath, _ = self._prepare()
        reject_books(str(mpath), b1.id, "bad cover")
        b3.finalmetadata.final_title_confidence = 0.5
        b3.finalmetadata.save(update_fields=["final_title_confidence"])
        apply_batch(
            manifest_path=str(mpath),
            confirm=3,
            exclude_ids=None,
            exclude_reason="review",
            allow_high_exclusion=True,
        )

        s = batch_summary(mpath)
        self.assertEqual(s["approve"], 1)
        self.assertEqual(s["hold"], 1)
        self.assertEqual(s["not_approved"], 1)
        self.assertEqual(s["total"], 3)


class RemoveHoldsTests(_BatchBase):
    def test_remove_holds_removes_id_and_preserves_other_lines(self):
        b1 = self._make_book("rh1", "Remove One", "Jane Doe")
        b2 = self._make_book("rh2", "Remove Two", "John Smith")
        mpath, _ = self._prepare()
        reject_books(str(mpath), b1.id, "bad cover")
        reject_books(str(mpath), b2.id, "bad title")

        result = remove_holds([b1.id], str(mpath))
        self.assertEqual(result, {"removed": [b1.id]})
        data = json.loads(mpath.read_text())
        self.assertNotIn(str(b1.id), data.get("excluded", {}))
        self.assertEqual(data["excluded"][str(b2.id)], "bad title")
        holds = (self.manifest_dir / "rejected_ids.txt").read_text()
        self.assertNotIn(f"{b1.id}\t", holds)
        self.assertIn(f"{b2.id}\tbad title", holds)

    def test_remove_holds_refuses_applied(self):
        b1 = self._make_book("ra", "Remove Applied", "Jane Doe")
        mpath, _ = self._prepare()
        apply_batch(
            manifest_path=str(mpath),
            confirm=1,
            exclude_ids=None,
            exclude_reason="review",
            allow_high_exclusion=True,
        )

        result = remove_holds([b1.id], str(mpath))
        self.assertEqual(result, {"refusal": "refusing: manifest already applied"})

    def test_remove_holds_refuses_unknown_id(self):
        self._make_book("ru", "Remove Unknown", "Jane Doe")
        mpath, _ = self._prepare()

        result = remove_holds([99999], str(mpath))
        self.assertEqual(result, {"refusal": "refusing: id 99999 not in manifest"})


class RejectBooksAppliedTests(_BatchBase):
    def test_reject_books_refuses_applied(self):
        b1 = self._make_book("rj", "Reject Applied", "Jane Doe")
        mpath, _ = self._prepare()
        apply_batch(
            manifest_path=str(mpath),
            confirm=1,
            exclude_ids=None,
            exclude_reason="review",
            allow_high_exclusion=True,
        )
        before = mpath.read_text()
        holds_path = self.manifest_dir / "rejected_ids.txt"
        holds_before = holds_path.read_text() if holds_path.exists() else ""

        result = reject_books(str(mpath), b1.id, "bad cover")
        self.assertEqual(result, {"refusal": "refusing: manifest already applied"})
        self.assertEqual(mpath.read_text(), before)
        self.assertEqual(
            holds_path.read_text() if holds_path.exists() else "", holds_before
        )


class ContextOnceTests(_BatchBase):
    def test_prepare_builds_context_once(self):
        self._make_book("cx", "Context Once", "Jane Doe")
        out = StringIO()
        import books.services.batches as bmod

        with mock.patch.object(bmod, "_build_context", wraps=bmod._build_context) as m:
            call_command("approve_batch", manifest_dir=str(self.manifest_dir), stdout=out)
        self.assertEqual(m.call_count, 1)


class ApplyReviewedTests(_BatchBase):
    def test_wrong_typed_count_refused_and_nothing_changed(self):
        b1 = self._make_book("ar1", "Apply Rev One", "Jane Doe")
        mpath, _ = self._prepare()

        result = apply_reviewed(str(mpath), 99)
        self.assertEqual(result, {"refusal": "refusing: typed 99, batch approves 1"})
        b1.finalmetadata.refresh_from_db()
        self.assertFalse(b1.finalmetadata.is_reviewed)
        self.assertEqual(json.loads(mpath.read_text())["status"], "prepared")

    def test_right_typed_count_applies(self):
        b1 = self._make_book("ar2", "Apply Rev Two", "Jane Doe")
        mpath, _ = self._prepare()

        result = apply_reviewed(str(mpath), 1)
        self.assertEqual(result["approved_count"], 1)
        b1.finalmetadata.refresh_from_db()
        self.assertTrue(b1.finalmetadata.is_reviewed)

    def test_valve_stays_in_force(self):
        self._make_book("v1", "Valve One", "Jane Doe")
        self._make_book("v2", "Valve Two", "John Smith")
        self._make_book("v3", "Valve Three", "Mary Jane")
        self._make_book("v4", "Valve Four", "Sam Smith")
        mpath, _ = self._prepare()
        data = json.loads(mpath.read_text())
        b1, b2 = data["ids"][0], data["ids"][1]
        reject_books(str(mpath), b1, "bad cover")
        reject_books(str(mpath), b2, "bad title")

        result = apply_reviewed(str(mpath), 2)
        self.assertEqual(
            result, {"refusal": "refusing: 50.0% of manifest ids excluded (limit 30%)"}
        )


class HoldReasonCodesTests(_BatchBase):
    def test_hold_reason_codes(self):
        self.assertEqual(
            HOLD_REASON_CODES,
            ("cover", "title", "author", "series", "language", "duplicate", "other"),
        )
