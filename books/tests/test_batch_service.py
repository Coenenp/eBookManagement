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


class BatchReportPrepareGoldenTests(TestCase):
    """Golden output for --report and --prepare, pinned against the current command."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(self.temp_dir, ignore_errors=True))
        self.scan_folder = create_test_scan_folder(temp_dir=self.temp_dir)
        self.manifest_dir = Path(self.temp_dir) / "manifests"
        self.manifest_dir.mkdir()

    def _make_book(self, name, *, title, author):
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

    def _make_book_no_fm(self, name, *, title, author):
        stem = re.sub(r"[^A-Za-z0-9 ]+", " ", f"{name} {title} {author}")
        stem = re.sub(r"\s+", " ", stem).strip()[:80]
        path = Path(self.temp_dir) / f"{stem}.epub"
        path.write_bytes(b"fake")
        return create_test_book_with_file(
            file_path=str(path),
            file_format="epub",
            scan_folder=self.scan_folder,
            content_type="ebook",
        )

    def test_golden_report(self):
        from books.services.batches import CRITERIA_LABELS

        self._make_book("r1", title="Report One", author="Report Author One")
        self._make_book("r2", title="Report Two", author="Report Author Two")
        self._make_book_no_fm("r3", title="Report Three", author="Report Author Three")
        rev = self._make_book("r4", title="Report Four", author="Report Author Four")
        from books.models import FinalMetadata

        FinalMetadata.objects.filter(book=rev).update(is_reviewed=True)

        out = StringIO()
        call_command("approve_batch", report=True, manifest_dir=str(self.manifest_dir), stdout=out)
        text = out.getvalue()

        excl = {label: 0 for label in CRITERIA_LABELS}
        excl["no final metadata"] = 1
        excl["already reviewed"] = 1
        expected = (
            "total books: 4\n"
            "eligible: 2\n"
            "exclusions:\n"
            + "".join(f"  {label}: {excl[label]}\n" for label in CRITERIA_LABELS)
            + "eligible by format:\n"
            "  epub: 2\n"
            "eligible by language:\n"
            "  en: 2\n"
            "eligible by confidence tier:\n"
            "  corroborated: 2\n"
            f"python manage.py approve_batch --apply --manifest {self.manifest_dir}/<batch_id>.json "
            "--confirm 2 --exclude-ids <comma separated ids>\n"
        )
        self.assertEqual(text, expected)

    def test_golden_prepare(self):
        self._make_book("p1", title="Prepare One", author="Prepare Author One")
        self._make_book("p2", title="Prepare Two", author="Prepare Author Two")

        out = StringIO()
        call_command("approve_batch", manifest_dir=str(self.manifest_dir), stdout=out)
        lines = out.getvalue().splitlines()

        self.assertEqual(len(lines), 7)
        self.assertTrue(lines[0].startswith("contact sheet: "), lines[0])
        self.assertTrue(lines[1].startswith("review page: "), lines[1])
        self.assertTrue(lines[2].startswith("batch_id: "), lines[2])
        batch_id = lines[2].split("batch_id: ", 1)[1]
        self.assertEqual(lines[3], f"manifest: {self.manifest_dir}/{batch_id}.json")

        sample_lines = sorted(lines[4:6])
        self.assertRegex(sample_lines[0], r"^1 \| Prepare One \| Prepare Author One \| en \| epub \| corroborated \| ")
        self.assertRegex(sample_lines[1], r"^2 \| Prepare Two \| Prepare Author Two \| en \| epub \| corroborated \| ")

        self.assertEqual(
            lines[6],
            f"python manage.py approve_batch --apply --manifest {self.manifest_dir}/{batch_id}.json "
            "--confirm 2 --exclude-ids <comma separated ids>",
        )

    def test_golden_manifest_json(self):
        b1 = self._make_book("m1", title="Manifest One", author="Manifest Author One")
        b2 = self._make_book("m2", title="Manifest Two", author="Manifest Author Two")

        out = StringIO()
        call_command("approve_batch", manifest_dir=str(self.manifest_dir), stdout=out)
        mpath = Path(re.search(r"manifest:\s*(\S+)", out.getvalue()).group(1))
        data = json.loads(mpath.read_text())

        self.assertEqual(
            set(data.keys()),
            {"batch_id", "criteria_version", "ids", "sample_ids", "status", "sheets", "review_page"},
        )
        self.assertEqual(data["criteria_version"], "v2")
        self.assertEqual(data["status"], "prepared")
        self.assertEqual(data["ids"], [b1.id, b2.id])
        self.assertEqual(set(data["sample_ids"]), {b1.id, b2.id})
        self.assertEqual(len(data["sheets"]), 1)
        self.assertTrue(data["sheets"][0].endswith("sheet1.png"))
        self.assertEqual(data["review_page"], f"{data['batch_id']}_review.html")


class BatchReportPrepareParityTests(TestCase):
    """The report/prepare command and the batch_report/select_batch service agree."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(self.temp_dir, ignore_errors=True))
        self.scan_folder = create_test_scan_folder(temp_dir=self.temp_dir)
        self.manifest_dir = Path(self.temp_dir) / "manifests"
        self.manifest_dir.mkdir()

    def _make_book(self, name, *, title, author):
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

    def _make_book_no_fm(self, name, *, title, author):
        stem = re.sub(r"[^A-Za-z0-9 ]+", " ", f"{name} {title} {author}")
        stem = re.sub(r"\s+", " ", stem).strip()[:80]
        path = Path(self.temp_dir) / f"{stem}.epub"
        path.write_bytes(b"fake")
        return create_test_book_with_file(
            file_path=str(path),
            file_format="epub",
            scan_folder=self.scan_folder,
            content_type="ebook",
        )

    def test_report_command_and_service_agree(self):
        from books.services.batches import batch_report

        self._make_book("r1", title="Parity Report One", author="Parity Report Author One")
        self._make_book("r2", title="Parity Report Two", author="Parity Report Author Two")
        self._make_book_no_fm("r3", title="Parity Report Three", author="Parity Report Author Three")
        rev = self._make_book("r4", title="Parity Report Four", author="Parity Report Author Four")
        from books.models import FinalMetadata

        FinalMetadata.objects.filter(book=rev).update(is_reviewed=True)

        cmd_out = StringIO()
        call_command("approve_batch", report=True, manifest_dir=str(self.manifest_dir), stdout=cmd_out)
        cmd_text = cmd_out.getvalue()

        report = batch_report(manifest_dir=str(self.manifest_dir))

        self.assertIn(f"total books: {report['total']}\n", cmd_text)
        self.assertIn(f"eligible: {report['eligible']}\n", cmd_text)
        for label, count in report["exclusions"].items():
            self.assertIn(f"  {label}: {count}\n", cmd_text)
        for fmt, n in report["by_format"].items():
            self.assertIn(f"  {fmt}: {n}\n", cmd_text)
        for lang, n in report["by_language"].items():
            self.assertIn(f"  {lang}: {n}\n", cmd_text)
        for tier, n in report["by_tier"].items():
            self.assertIn(f"  {tier}: {n}\n", cmd_text)

    def test_prepare_command_and_service_agree(self):
        from books.services.batches import select_batch, write_batch_files

        self._make_book("p1", title="Parity Prepare One", author="Parity Prepare Author One")
        self._make_book("p2", title="Parity Prepare Two", author="Parity Prepare Author Two")

        cmd_out = StringIO()
        call_command("approve_batch", manifest_dir=str(self.manifest_dir), stdout=cmd_out)
        cmd_mpath = Path(re.search(r"manifest:\s*(\S+)", cmd_out.getvalue()).group(1))
        cmd_manifest = json.loads(cmd_mpath.read_text())

        selection = select_batch(size=25, manifest_dir=self.manifest_dir)
        result = write_batch_files(selection, self.manifest_dir)
        svc_manifest = result["manifest"]

        self.assertEqual(cmd_manifest["ids"], svc_manifest["ids"])
        self.assertEqual(set(cmd_manifest["sample_ids"]), set(svc_manifest["sample_ids"]))
        self.assertEqual(cmd_manifest["criteria_version"], svc_manifest["criteria_version"])
        self.assertEqual(cmd_manifest["status"], svc_manifest["status"])
        self.assertEqual(svc_manifest["status"], "prepared")

    def test_select_batch_and_batch_report_write_nothing(self):
        from books.models import FinalMetadata

        from books.services.batches import batch_report, select_batch

        b1 = self._make_book("w1", title="Write One", author="Write Author One")
        fresh_dir = Path(self.temp_dir) / "nothing"

        selection = select_batch(size=10, manifest_dir=fresh_dir)
        report = batch_report(manifest_dir=fresh_dir)

        # No files written (the directory is created, but stays empty).
        self.assertFalse(list(fresh_dir.iterdir()))
        # No database side effects: the book is still not reviewed.
        self.assertFalse(FinalMetadata.objects.get(book=b1).is_reviewed)
        # The selection and report are returned as data.
        self.assertEqual([bid for _corr, bid in selection["selected"]], [b1.id])
        self.assertEqual(report["eligible"], 1)
