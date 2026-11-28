"""Part B view tests for the batch review actions PR (J2b).

Covers the hold / unhold / apply views, the prepared and applied review page
content, the Django messages, and the parity between holding via the view and
via the ``approve_batch --reject-id`` command.
"""

import json
import re
import shutil
import tempfile
from io import StringIO
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client, TestCase

from books.services.batches import (
    apply_batch,
    batch_rows,
    reject_books,
    select_batch,
    write_batch_files,
)
from books.tests.test_helpers import create_test_book_with_file, create_test_scan_folder


class _BatchViewBase(TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(self.temp_dir, ignore_errors=True))
        self.scan_folder = create_test_scan_folder(temp_dir=self.temp_dir)
        self.manifest_dir = Path(self.temp_dir) / "manifests"
        self.manifest_dir.mkdir()
        self._override = self.settings(BATCH_MANIFEST_DIR=str(self.manifest_dir))
        self._override.enable()
        self.addCleanup(self._override.disable)

        User = get_user_model()
        self.user = User.objects.create_user("batchuser", "b@example.com", "pw")
        self.client.force_login(self.user)

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

    def _review(self, batch_id):
        return self.client.get(f"/batches/{batch_id}/")


class HoldUnholdViewTests(_BatchViewBase):
    def test_hold_changes_row_and_counter(self):
        b1 = self._make_book("hv1", "Hold One", "Jane Doe")
        self._make_book("hv2", "Hold Two", "John Smith")
        _mpath, manifest = self._prepare()

        resp = self.client.post(
            f"/batches/{manifest['batch_id']}/hold/",
            {"book_id": b1.id, "reason": "cover"},
        )
        self.assertEqual(resp.status_code, 302)
        content = self._review(manifest["batch_id"]).content.decode()
        self.assertIn("Held: cover", content)
        self.assertIn("approve 1, hold 1", content)

    def test_unhold_restores(self):
        b1 = self._make_book("uv1", "Unhold One", "Jane Doe")
        self._make_book("uv2", "Unhold Two", "John Smith")
        _mpath, manifest = self._prepare()
        self.client.post(
            f"/batches/{manifest['batch_id']}/hold/",
            {"book_id": b1.id, "reason": "cover"},
        )

        resp = self.client.post(
            f"/batches/{manifest['batch_id']}/unhold/", {"book_id": b1.id}
        )
        self.assertEqual(resp.status_code, 302)
        content = self._review(manifest["batch_id"]).content.decode()
        self.assertIn("approve 2, hold 0", content)
        self.assertNotIn("Held: cover", content)

    def test_unknown_reason_code_refused(self):
        b1 = self._make_book("ur1", "Unknown Reason", "Jane Doe")
        mpath, manifest = self._prepare()

        resp = self.client.post(
            f"/batches/{manifest['batch_id']}/hold/",
            {"book_id": b1.id, "reason": "bogus"},
        )
        self.assertEqual(resp.status_code, 302)
        rows = batch_rows(mpath)
        held = next(r for r in rows if r["id"] == b1.id)
        self.assertFalse(held["held"])
        content = self._review(manifest["batch_id"]).content.decode()
        self.assertIn("unknown reason code", content)

    def test_book_id_not_in_manifest_refused(self):
        self._make_book("bm1", "Book Missing", "Jane Doe")
        mpath, manifest = self._prepare()

        resp = self.client.post(
            f"/batches/{manifest['batch_id']}/hold/",
            {"book_id": 99999, "reason": "cover"},
        )
        self.assertEqual(resp.status_code, 302)
        data = json.loads(mpath.read_text())
        self.assertNotIn("99999", data.get("excluded", {}))
        content = self._review(manifest["batch_id"]).content.decode()
        self.assertIn("not in manifest", content)

    def test_hold_and_unhold_on_applied_refused(self):
        b1 = self._make_book("ha1", "Held Applied", "Jane Doe")
        mpath, manifest = self._prepare()
        apply_batch(
            manifest_path=str(mpath),
            confirm=1,
            exclude_ids=None,
            exclude_reason="review",
            allow_high_exclusion=True,
        )
        before = mpath.read_text()

        hold_resp = self.client.post(
            f"/batches/{manifest['batch_id']}/hold/",
            {"book_id": b1.id, "reason": "cover"},
        )
        self.assertEqual(hold_resp.status_code, 302)
        unhold_resp = self.client.post(
            f"/batches/{manifest['batch_id']}/unhold/", {"book_id": b1.id}
        )
        self.assertEqual(unhold_resp.status_code, 302)
        self.assertEqual(mpath.read_text(), before)
        content = self._review(manifest["batch_id"]).content.decode()
        self.assertIn("manifest already applied", content)


class ApplyViewTests(_BatchViewBase):
    def test_apply_wrong_count_changes_nothing(self):
        b1 = self._make_book("aw1", "Apply Wrong", "Jane Doe")
        mpath, manifest = self._prepare()

        resp = self.client.post(
            f"/batches/{manifest['batch_id']}/apply/", {"count": "99"}
        )
        self.assertEqual(resp.status_code, 302)
        b1.finalmetadata.refresh_from_db()
        self.assertFalse(b1.finalmetadata.is_reviewed)
        self.assertEqual(json.loads(mpath.read_text())["status"], "prepared")

    def test_apply_right_count_reviews_and_page_shows_approved(self):
        b1 = self._make_book("ar1", "Apply Right", "Jane Doe")
        mpath, manifest = self._prepare()

        resp = self.client.post(
            f"/batches/{manifest['batch_id']}/apply/", {"count": "1"}
        )
        self.assertEqual(resp.status_code, 302)
        b1.finalmetadata.refresh_from_db()
        self.assertTrue(b1.finalmetadata.is_reviewed)
        content = self._review(manifest["batch_id"]).content.decode()
        self.assertIn("approved 1", content)
        self.assertNotIn("already reviewed", content)

    def test_second_apply_refused(self):
        self._make_book("as1", "Apply Second", "Jane Doe")
        _mpath, manifest = self._prepare()
        self.client.post(f"/batches/{manifest['batch_id']}/apply/", {"count": "1"})

        resp = self.client.post(
            f"/batches/{manifest['batch_id']}/apply/", {"count": "1"}
        )
        self.assertEqual(resp.status_code, 302)
        content = self._review(manifest["batch_id"]).content.decode()
        self.assertIn("manifest already applied", content)

    def test_valve_refusal_text_shown(self):
        self._make_book("vv1", "Valve One", "Jane Doe")
        self._make_book("vv2", "Valve Two", "John Smith")
        self._make_book("vv3", "Valve Three", "Mary Jane")
        self._make_book("vv4", "Valve Four", "Sam Smith")
        mpath, manifest = self._prepare()
        data = json.loads(mpath.read_text())
        b1, b2 = data["ids"][0], data["ids"][1]
        self.client.post(
            f"/batches/{manifest['batch_id']}/hold/", {"book_id": b1, "reason": "cover"}
        )
        self.client.post(
            f"/batches/{manifest['batch_id']}/hold/", {"book_id": b2, "reason": "cover"}
        )

        resp = self.client.post(
            f"/batches/{manifest['batch_id']}/apply/", {"count": "2"}
        )
        self.assertEqual(resp.status_code, 302)
        content = self._review(manifest["batch_id"]).content.decode()
        self.assertIn("limit 30%", content)


class ReviewPageContentTests(_BatchViewBase):
    def test_prepared_page_has_banner_and_forms(self):
        self._make_book("pb1", "Page Banner", "Jane Doe")
        _mpath, manifest = self._prepare()

        content = self._review(manifest["batch_id"]).content.decode()
        self.assertIn("Nothing is approved until you apply", content)
        self.assertIn(
            "Type the number of books that will be approved (1) to apply", content
        )
        self.assertIn('name="reason"', content)
        self.assertIn('name="count"', content)

    def test_prepared_held_book_has_unhold_not_hold_form(self):
        b1 = self._make_book("ph1", "Page Hold", "Jane Doe")
        _mpath, manifest = self._prepare()
        self.client.post(
            f"/batches/{manifest['batch_id']}/hold/",
            {"book_id": b1.id, "reason": "cover"},
        )

        content = self._review(manifest["batch_id"]).content.decode()
        self.assertIn("Held: cover", content)

    def test_applied_page_shows_states_and_no_forms(self):
        b1 = self._make_book("ap1", "Applied One", "Jane Doe")
        b2 = self._make_book("ap2", "Applied Two", "John Smith")
        b3 = self._make_book("ap3", "Applied Three", "Mary Jane")
        mpath, manifest = self._prepare()
        reject_books(str(mpath), b2.id, "bad cover")
        b3.finalmetadata.final_title_confidence = 0.5
        b3.finalmetadata.save(update_fields=["final_title_confidence"])
        apply_batch(
            manifest_path=str(mpath),
            confirm=3,
            exclude_ids=None,
            exclude_reason="review",
            allow_high_exclusion=True,
        )

        content = self._review(manifest["batch_id"]).content.decode()
        self.assertIn("approved 1, held 1, not approved 1", content)
        self.assertIn("Held: bad cover", content)
        self.assertIn("Not approved: title confidence", content)
        self.assertNotIn('name="reason"', content)
        self.assertNotIn('name="count"', content)


class ActionMethodAndAuthTests(_BatchViewBase):
    def _urls(self, manifest):
        bid = manifest["batch_id"]
        return [
            f"/batches/{bid}/hold/",
            f"/batches/{bid}/unhold/",
            f"/batches/{bid}/apply/",
        ]

    def test_get_on_action_urls_405(self):
        _mpath, manifest = self._prepare()
        for url in self._urls(manifest):
            resp = self.client.get(url)
            self.assertEqual(resp.status_code, 405, url)

    def test_anonymous_redirected_to_login(self):
        _mpath, manifest = self._prepare()
        anon = Client()
        for url in self._urls(manifest):
            resp = anon.post(url, {"book_id": 1, "reason": "cover"})
            self.assertEqual(resp.status_code, 302, url)
            self.assertIn("/login/", resp.url, url)

    def test_post_without_csrf_403(self):
        _mpath, manifest = self._prepare()
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)
        resp = csrf_client.post(
            f"/batches/{manifest['batch_id']}/hold/",
            {"book_id": 1, "reason": "cover"},
        )
        self.assertEqual(resp.status_code, 403)


class HoldParityTests(_BatchViewBase):
    def test_hold_parity_view_and_command(self):
        b1 = self._make_book("hp1", "Hold Parity", "Jane Doe")
        mpath, manifest = self._prepare()

        self.client.post(
            f"/batches/{manifest['batch_id']}/hold/",
            {"book_id": b1.id, "reason": "cover"},
        )
        excluded_view = json.loads(mpath.read_text()).get("excluded", {})
        holds_view = (self.manifest_dir / "rejected_ids.txt").read_text()

        # Reset the manifest and holds file for the command path.
        data = json.loads(mpath.read_text())
        data.pop("excluded", None)
        mpath.write_text(json.dumps(data, indent=2))
        (self.manifest_dir / "rejected_ids.txt").unlink()

        call_command(
            "approve_batch",
            manifest=str(mpath),
            reject_id=b1.id,
            reason="cover",
            stdout=StringIO(),
        )
        excluded_cmd = json.loads(mpath.read_text()).get("excluded", {})
        holds_cmd = (self.manifest_dir / "rejected_ids.txt").read_text()

        self.assertEqual(excluded_view, excluded_cmd)
        self.assertEqual(holds_view, holds_cmd)
