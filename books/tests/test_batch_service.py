"""Golden output and parity tests for the approve_batch service layer.

The golden tests pin the command's printed output byte-for-byte against the
current implementation, so the extraction into ``books.services.batches``
cannot drift the output. The parity tests assert the command and the service
agree on the same fixture.
"""

import json
import re
import shutil
import tempfile
from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from books.tests.test_helpers import create_test_book_with_file, create_test_scan_folder


class BatchGoldenOutputTests(TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(self.temp_dir, ignore_errors=True))
        self.scan_folder = create_test_scan_folder(temp_dir=self.temp_dir)
        self.manifest_dir = Path(self.temp_dir) / "manifests"
        self.manifest_dir.mkdir()

    def _make_book(self, name, *, title="A Great Title", author="Jane Doe"):
        stem = re.sub(r"[^A-Za-z0-9 ]+", " ", f"{name} {title} {author}")
        stem = re.sub(r"\s+", " ", stem).strip()[:80]
        path = Path(self.temp_dir) / f"{stem}.epub"
        path.write_bytes(b"fake")
        cover_path = str(Path(self.temp_dir) / f"{name}_cover.jpg")
        Path(cover_path).write_bytes(b"\xff\xd8\xff" + b"\x00" * 16)
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
            final_cover_path=cover_path,
            final_cover_confidence=0.95,
            language="en",
        )
        return book

    def _prepare(self, **opts):
        out = StringIO()
        call_command("approve_batch", manifest_dir=str(self.manifest_dir), stdout=out, **opts)
        text = out.getvalue()
        m = re.search(r"manifest:\s*(\S+)", text)
        return text, (Path(m.group(1)) if m else None)

    def _apply(self, manifest, **opts):
        out = StringIO()
        call_command(
            "approve_batch",
            manifest=str(manifest),
            apply=True,
            stdout=out,
            **opts,
        )
        return out.getvalue()

    def _apply_error(self, manifest, **opts):
        with self.assertRaises(CommandError) as cm:
            call_command(
                "approve_batch",
                manifest=str(manifest),
                apply=True,
                stdout=StringIO(),
                **opts,
            )
        return str(cm.exception)

    # ------------------------------------------------------------------ #
    # Golden output (pinned against the current command)
    # ------------------------------------------------------------------ #

    def test_golden_apply_hold_list(self):
        b1 = self._make_book("hold1", title="Hold One", author="Hold Author One")
        b2 = self._make_book("hold2", title="Hold Two", author="Hold Author Two")
        _, mpath = self._prepare()
        out = self._apply(
            mpath,
            confirm=2,
            exclude_ids=str(b1.id),
            allow_high_exclusion=True,
        )
        self.assertEqual(out, f"skipped {b1.id}: review\napproved 1, skipped 1\n")

    def test_golden_apply_valve_refused(self):
        books = [
            self._make_book(f"gv{i}", title=f"Golden Valve {chr(65 + i)}", author=f"GV Author {chr(65 + i)}")
            for i in range(10)
        ]
        _, mpath = self._prepare()
        excl = ",".join(str(books[i].id) for i in range(4))
        err = self._apply_error(mpath, confirm=10, exclude_ids=excl)
        self.assertEqual(err, "refusing: 40.0% of manifest ids excluded (limit 30%)")

    def test_golden_apply_valve_allowed(self):
        books = [
            self._make_book(f"ga{i}", title=f"Golden Allow {chr(65 + i)}", author=f"GA Author {chr(65 + i)}")
            for i in range(10)
        ]
        _, mpath = self._prepare()
        excl = ",".join(str(books[i].id) for i in range(4))
        out = self._apply(
            mpath,
            confirm=10,
            exclude_ids=excl,
            allow_high_exclusion=True,
        )
        skipped_lines = "\n".join(
            f"skipped {books[i].id}: review" for i in range(4)
        )
        self.assertEqual(out, f"{skipped_lines}\napproved 6, skipped 4\n")

    def test_golden_apply_wrong_confirm_count(self):
        book = self._make_book("wrongconfirm", title="Wrong Confirm", author="WC Author")
        _, mpath = self._prepare()
        err = self._apply_error(mpath, confirm=2)
        self.assertEqual(err, "refusing: confirm 2 != id count 1")

    def test_golden_reject(self):
        book = self._make_book("rejectgold", title="Reject Golden", author="RG Author")
        _, mpath = self._prepare()
        out = StringIO()
        call_command(
            "approve_batch",
            manifest=str(mpath),
            reject_id=book.id,
            reason="still works",
            stdout=out,
        )
        self.assertEqual(out.getvalue(), f"rejected {book.id}: still works\n")


class BatchApplyParityTests(TestCase):
    """The apply command and the apply_batch service agree on one fixture."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(self.temp_dir, ignore_errors=True))
        self.scan_folder = create_test_scan_folder(temp_dir=self.temp_dir)
        self.manifest_dir = Path(self.temp_dir) / "manifests"
        self.manifest_dir.mkdir()

    def _make_book(self, name, *, title="A Great Title", author="Jane Doe"):
        stem = re.sub(r"[^A-Za-z0-9 ]+", " ", f"{name} {title} {author}")
        stem = re.sub(r"\s+", " ", stem).strip()[:80]
        path = Path(self.temp_dir) / f"{stem}.epub"
        path.write_bytes(b"fake")
        cover_path = str(Path(self.temp_dir) / f"{name}_cover.jpg")
        Path(cover_path).write_bytes(b"\xff\xd8\xff" + b"\x00" * 16)
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
            final_cover_path=cover_path,
            final_cover_confidence=0.95,
            language="en",
        )
        return book

    def test_apply_command_and_service_agree(self):
        from books.models import FinalMetadata

        from books.services.batches import apply_batch

        b1 = self._make_book("p1", title="Parity One", author="Parity Author One")
        b2 = self._make_book("p2", title="Parity Two", author="Parity Author Two")
        b3 = self._make_book("p3", title="Parity Three", author="Parity Author Three")

        out = StringIO()
        call_command("approve_batch", manifest_dir=str(self.manifest_dir), stdout=out)
        mpath = Path(re.search(r"manifest:\s*(\S+)", out.getvalue()).group(1))
        pristine = mpath.read_text()
        rejects = self.manifest_dir / "rejected_ids.txt"

        def reviewed(books):
            return {b.id for b in books if FinalMetadata.objects.get(book=b).is_reviewed}

        # --- command path ---
        cmd_out = StringIO()
        call_command(
            "approve_batch",
            manifest=str(mpath),
            apply=True,
            confirm=3,
            exclude_ids=str(b1.id),
            allow_high_exclusion=True,
            stdout=cmd_out,
        )
        self.assertEqual(cmd_out.getvalue(), f"skipped {b1.id}: review\napproved 2, skipped 1\n")
        cmd_reviewed = reviewed((b1, b2, b3))
        cmd_holds = rejects.read_text()

        # --- reset for the service path ---
        FinalMetadata.objects.update(is_reviewed=False)
        mpath.write_text(pristine)
        rejects.unlink()

        # --- service path ---
        result = apply_batch(
            manifest_path=str(mpath),
            confirm=3,
            exclude_ids=str(b1.id),
            exclude_reason="review",
            allow_high_exclusion=True,
        )
        svc_reviewed = reviewed((b1, b2, b3))
        svc_holds = rejects.read_text()

        self.assertEqual(result["approved_count"], 2)
        self.assertEqual(result["skipped_count"], 1)
        self.assertEqual(set(result["approved"]), cmd_reviewed)
        self.assertEqual(result["skipped"], [{"id": b1.id, "reason": "review"}])
        self.assertEqual(svc_reviewed, cmd_reviewed)
        self.assertEqual(svc_holds, cmd_holds)
