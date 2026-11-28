"""Part B tests: golden review page, batch_rows, list_batches and the views."""

import json
import os
import re
import shutil
import tempfile
import time
import uuid
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import TestCase

from books.services.batches import (
    apply_batch,
    batch_rows,
    list_batches,
    reject_books,
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


class ReviewPageGoldenTests(_BatchBase):
    """Pin the review page HTML that write_batch_files produces."""

    def _expected_row(self, bid, title, last, first, series, number, source_stem):
        folder = (
            f"English/Books/{last}, {first}/{series}"
            if series
            else f"English/Books/{last}, {first}"
        )
        filename = (
            f"{last}, {first} - {series} #{int(number):02d} - {title}.epub"
            if series
            else f"{last}, {first} - {title}.epub"
        )
        tail = f"{Path(self.temp_dir).name} / {source_stem}.epub"
        return (
            '<tr class="sampled"><td>ERR</td>'
            f"<td>{bid}</td><td>{title}</td><td>{last}</td><td>{first}</td>"
            f"<td>{series}</td><td>{number}</td><td>en</td><td>epub</td>"
            f"<td>corroborated</td><td>{folder}</td><td>{filename}</td>"
            f"<td>{tail}</td><td>&#10003;</td></tr>"
        )

    def test_review_page_html_golden(self):
        b1 = self._make_book("ga", "Golden Alpha", "Jane Doe", series="The Saga", number="1")
        b2 = self._make_book("gb", "Golden Beta", "John Smith")

        selection = select_batch(size=25, manifest_dir=self.manifest_dir)
        result = write_batch_files(selection, self.manifest_dir)
        page = (self.manifest_dir / result["manifest"]["review_page"]).read_text()
        batch_id = result["manifest"]["batch_id"]

        rows = (
            self._expected_row(b1.id, "Golden Alpha", "Doe", "Jane", "The Saga", "1",
                               "ga Golden Alpha Jane Doe")
            + self._expected_row(b2.id, "Golden Beta", "Smith", "John", "", "",
                                 "gb Golden Beta John Smith")
        )
        expected = (
            '<!doctype html><html><head><meta charset="utf-8">'
            f"<title>Batch review {batch_id}</title>"
            "<style>table{border-collapse:collapse}th,td{border:1px solid #999;"
            "padding:4px;vertical-align:top}tr.sampled{background:#fff59d}"
            "</style></head><body>"
            f"<h1>Batch {batch_id}</h1>"
            "<p>criteria version: v2</p>"
            "<p>To hold back books use --apply --manifest &lt;manifest path&gt; "
            "--confirm &lt;count&gt; --exclude-ids &lt;ids&gt; "
            "--exclude-reason &lt;text&gt;</p>"
            "<table><thead><tr><th>cover</th><th>id</th><th>title</th>"
            "<th>last name</th><th>first name</th><th>series</th><th>number</th>"
            "<th>language</th><th>format</th><th>tier</th><th>folder</th>"
            "<th>file name</th><th>source path</th><th>sample</th>"
            "</tr></thead><tbody>"
            + rows
            + "</tbody></table></body></html>"
        )
        self.assertEqual(page, expected)


class BatchRowsTests(_BatchBase):
    def test_batch_rows_returns_all_fields(self):
        b1 = self._make_book("ra", "Row Alpha", "Jane Doe", series="The Saga", number="1")
        self._make_book("rb", "Row Beta", "John Smith")
        mpath, manifest = self._prepare()

        rows = batch_rows(mpath)
        self.assertEqual([r["id"] for r in rows], sorted(manifest["ids"]))

        first = rows[0]
        self.assertEqual(
            set(first.keys()),
            {
                "id", "title", "last_name", "first_name", "series",
                "series_number", "language", "format", "tier", "cover",
                "source", "folder", "filename", "flag", "held", "hold_reason",
                "state", "skip_reason", "sample",
            },
        )
        self.assertEqual(first["title"], "Row Alpha")
        self.assertEqual(first["last_name"], "Doe")
        self.assertEqual(first["first_name"], "Jane")
        self.assertEqual(first["series"], "The Saga")
        self.assertEqual(first["series_number"], "1")
        self.assertEqual(first["language"], "en")
        self.assertEqual(first["format"], "epub")
        self.assertEqual(first["tier"], "corroborated")
        self.assertIsNone(first["cover"])  # undecodable fake cover -> no URI
        self.assertTrue(first["filename"].endswith(".epub"))
        self.assertFalse(first["held"])
        self.assertIsNone(first["hold_reason"])
        self.assertIsNone(first["flag"])

    def test_batch_rows_flag_when_book_no_longer_passes(self):
        b1 = self._make_book("fa", "Flag Alpha", "Jane Doe")
        mpath, _ = self._prepare()
        # Drift the title so the book would no longer pass the name check.
        fm = b1.finalmetadata
        fm.final_title = "Completely Different Title"
        fm.save(update_fields=["final_title"])

        rows = batch_rows(mpath)
        self.assertEqual(rows[0]["flag"], "name mismatch")

    def test_batch_rows_held_from_excluded_map(self):
        b1 = self._make_book("ha", "Held Alpha", "Jane Doe")
        mpath, _ = self._prepare()
        reject_books(str(mpath), b1.id, "bad cover")

        rows = batch_rows(mpath)
        held = next(r for r in rows if r["id"] == b1.id)
        self.assertTrue(held["held"])
        self.assertEqual(held["hold_reason"], "bad cover")

    def test_batch_rows_held_from_holds_file(self):
        b1 = self._make_book("hf", "Held File", "Jane Doe")
        mpath, _ = self._prepare()
        # A hold recorded only in the shared holds file (no manifest excluded).
        (self.manifest_dir / "rejected_ids.txt").write_text(f"{b1.id}\tfrom file\n")

        rows = batch_rows(mpath)
        held = next(r for r in rows if r["id"] == b1.id)
        self.assertTrue(held["held"])
        self.assertEqual(held["hold_reason"], "from file")


class ListBatchesTests(_BatchBase):
    def _write_manifest(self, batch_id, ids, status="prepared", excluded=None,
                        applied_at=None, applied_ids=None):
        data = {
            "batch_id": batch_id,
            "criteria_version": "v2",
            "ids": ids,
            "sample_ids": [],
            "status": status,
            "sheets": [],
            "review_page": None,
        }
        if excluded:
            data["excluded"] = excluded
        if applied_at:
            data["applied_at"] = applied_at
        if applied_ids is not None:
            data["applied_ids"] = applied_ids
        path = self.manifest_dir / f"{batch_id}.json"
        path.write_text(json.dumps(data))
        return path

    def test_list_batches_newest_first(self):
        a = str(uuid.uuid4())
        b = str(uuid.uuid4())
        pa = self._write_manifest(a, [1, 2])
        pb = self._write_manifest(b, [3])
        os.utime(pa, (1000, 1000))
        os.utime(pb, (2000, 2000))

        batches = list_batches(manifest_dir=self.manifest_dir)
        self.assertEqual([x["batch_id"] for x in batches], [b, a])

    def test_list_batches_fields_and_held_count(self):
        bid = str(uuid.uuid4())
        self._write_manifest(
            bid, [1, 2, 3], status="applied",
            excluded={"1": "bad", "2": "worse"},
            applied_at="2026-11-28T00:00:00+00:00", applied_ids=[3],
        )
        batches = list_batches(manifest_dir=self.manifest_dir)
        self.assertEqual(len(batches), 1)
        entry = batches[0]
        self.assertEqual(entry["batch_id"], bid)
        self.assertEqual(entry["status"], "applied")
        self.assertEqual(entry["id_count"], 3)
        self.assertEqual(entry["held_count"], 2)
        self.assertEqual(entry["applied_at"], "2026-11-28T00:00:00+00:00")
        self.assertIsInstance(entry["created"], float)

    def test_list_batches_skips_non_manifest_json(self):
        (self.manifest_dir / "not_a_manifest.json").write_text('{"foo": "bar"}')
        self.assertEqual(list_batches(manifest_dir=self.manifest_dir), [])


class BatchViewTests(_BatchBase):
    def setUp(self):
        super().setUp()
        User = get_user_model()
        self.user = User.objects.create_user("batchuser", "b@example.com", "pw")
        self.client.force_login(self.user)

    def _manifest_path(self, mpath):
        return mpath

    def _write_manifest(self, batch_id, ids, status="prepared", excluded=None,
                        applied_at=None, applied_ids=None):
        data = {
            "batch_id": batch_id,
            "criteria_version": "v2",
            "ids": ids,
            "sample_ids": [],
            "status": status,
            "sheets": [],
            "review_page": None,
        }
        if excluded:
            data["excluded"] = excluded
        if applied_at:
            data["applied_at"] = applied_at
        if applied_ids is not None:
            data["applied_ids"] = applied_ids
        path = self.manifest_dir / f"{batch_id}.json"
        path.write_text(json.dumps(data))
        return path

    def test_list_page_shows_two_batches_newest_first(self):
        a = str(uuid.uuid4())
        b = str(uuid.uuid4())
        pa = self._write_manifest(a, [1])
        pb = self._write_manifest(b, [2])
        os.utime(pa, (1000, 1000))
        os.utime(pb, (2000, 2000))

        with self.settings(BATCH_MANIFEST_DIR=str(self.manifest_dir)):
            resp = self.client.get("/batches/")
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self.assertLess(content.index(b), content.index(a))

    def test_review_page_shows_titles_status_and_counter(self):
        b1 = self._make_book("va", "View Alpha", "Jane Doe")
        b2 = self._make_book("vb", "View Beta", "John Smith")
        mpath, manifest = self._prepare()

        with self.settings(BATCH_MANIFEST_DIR=str(self.manifest_dir)):
            resp = self.client.get(f"/batches/{manifest['batch_id']}/")
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self.assertIn("View Alpha", content)
        self.assertIn("View Beta", content)
        self.assertIn("Approved when applied", content)
        self.assertIn("approve 2, hold 0", content)
        self.assertIn("prepared", content)

    def test_review_page_held_book_shown_with_reason(self):
        b1 = self._make_book("ha", "Held View", "Jane Doe")
        self._make_book("hb", "Keep View", "John Smith")
        mpath, manifest = self._prepare()
        reject_books(str(mpath), b1.id, "bad cover")

        with self.settings(BATCH_MANIFEST_DIR=str(self.manifest_dir)):
            resp = self.client.get(f"/batches/{manifest['batch_id']}/")
        content = resp.content.decode()
        self.assertIn("Held: bad cover", content)
        self.assertIn("approve 1, hold 1", content)

    def test_review_page_applied_line(self):
        self._make_book("aa", "Apply View", "Jane Doe")
        mpath, manifest = self._prepare()
        apply_batch(
            manifest_path=str(mpath),
            confirm=1,
            exclude_ids=None,
            exclude_reason="review",
            allow_high_exclusion=True,
        )

        with self.settings(BATCH_MANIFEST_DIR=str(self.manifest_dir)):
            resp = self.client.get(f"/batches/{manifest['batch_id']}/")
        content = resp.content.decode()
        self.assertIn("Applied at", content)
        self.assertIn("approved 1", content)

    def test_unknown_batch_id_404(self):
        unknown = str(uuid.uuid4())
        with self.settings(BATCH_MANIFEST_DIR=str(self.manifest_dir)):
            resp = self.client.get(f"/batches/{unknown}/")
        self.assertEqual(resp.status_code, 404)

    def test_malformed_batch_id_404(self):
        # Even a manifest that exists under a non-UUID name must be 404: the
        # value from the URL is rejected before any path is built.
        self._write_manifest("not-a-uuid", [1])
        with self.settings(BATCH_MANIFEST_DIR=str(self.manifest_dir)):
            resp = self.client.get("/batches/not-a-uuid/")
        self.assertEqual(resp.status_code, 404)

    def test_path_traversal_404(self):
        with self.settings(BATCH_MANIFEST_DIR=str(self.manifest_dir)):
            resp = self.client.get("/batches/..%2F..%2Fetc%2Fpasswd/")
        self.assertEqual(resp.status_code, 404)

    def test_post_refused_405(self):
        self._make_book("pa", "Post View", "Jane Doe")
        mpath, manifest = self._prepare()
        with self.settings(BATCH_MANIFEST_DIR=str(self.manifest_dir)):
            resp = self.client.post(f"/batches/{manifest['batch_id']}/", {})
        self.assertEqual(resp.status_code, 405)
