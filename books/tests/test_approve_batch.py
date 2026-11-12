"""Tests for the approve_batch management command."""

import json
import re
import shutil
import tempfile
from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase

from books.management.commands.approve_batch import (
    CRITERIA_VERSION,
    DEFAULT_MANIFEST_DIR,
    SUSPICIOUS_PATTERNS,
)
from books.models import FileMove
from books.tests.test_helpers import create_test_book_with_file, create_test_scan_folder


class ApproveBatchCommandTests(TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(self.temp_dir, ignore_errors=True))
        self.scan_folder = create_test_scan_folder(temp_dir=self.temp_dir)
        self.manifest_dir = Path(self.temp_dir) / "manifests"
        self.manifest_dir.mkdir()

    def _make_book(
        self,
        name="book",
        *,
        title="A Great Title",
        author="Jane Doe",
        language="en",
        title_conf=0.95,
        author_conf=0.95,
        cover_conf=0.95,
        cover_path=None,
        is_reviewed=False,
        unresolved_reason="",
        isbn="",
        fmt="epub",
        content_type="ebook",
    ):
        path = Path(self.temp_dir) / f"{name}.{fmt}"
        path.write_bytes(b"fake")
        if cover_path is None:
            cover_path = str(Path(self.temp_dir) / f"{name}_cover.jpg")
            Path(cover_path).write_bytes(b"cover")
        book = create_test_book_with_file(
            file_path=str(path),
            file_format=fmt,
            scan_folder=self.scan_folder,
            content_type=content_type,
        )
        from books.models import FinalMetadata

        FinalMetadata.objects.create(
            book=book,
            final_title=title,
            final_title_confidence=title_conf,
            final_author=author,
            final_author_confidence=author_conf,
            final_cover_path=cover_path,
            final_cover_confidence=cover_conf,
            language=language,
            isbn=isbn,
            is_reviewed=is_reviewed,
            unresolved_reason=unresolved_reason,
        )
        return book

    def _prepare(self, **opts):
        out = StringIO()
        call_command("approve_batch", manifest_dir=str(self.manifest_dir), stdout=out, **opts)
        text = out.getvalue()
        m = re.search(r"manifest:\s*(\S+)", text)
        return text, (Path(m.group(1)) if m else None)

    def _manifest(self, path):
        return json.loads(Path(path).read_text())

    # ------------------------------------------------------------------ #
    # Constants / plumbing
    # ------------------------------------------------------------------ #

    def test_criteria_version_is_v1(self):
        self.assertEqual(CRITERIA_VERSION, "v1")

    def test_default_manifest_dir_outside_repository(self):
        repo = Path("/workspace/eBookManagement").resolve()
        self.assertFalse(str(DEFAULT_MANIFEST_DIR.resolve()).startswith(str(repo)))

    # ------------------------------------------------------------------ #
    # Each criterion excludes a book
    # ------------------------------------------------------------------ #

    def test_each_criterion_excludes(self):
        cases = [
            ("reviewed", {"is_reviewed": True}),
            ("unresolved", {"unresolved_reason": "uncertain"}),
            ("no_language", {"language": ""}),
            ("und_language", {"language": "und"}),
            ("title_low", {"title_conf": 0.79}),
            ("author_low", {"author_conf": 0.79}),
            ("cover_low", {"cover_conf": 0.79}),
            ("cover_empty", {"cover_path": ""}),
            ("cover_missing", {"cover_path": str(Path(self.temp_dir) / "gone.jpg")}),
            ("bad_format", {"fmt": "pdf"}),
            ("title_stoplist", {"title": "untitled"}),
            ("title_equals_author", {"title": "Jane Doe", "author": "Jane Doe"}),
        ]
        for name, kwargs in cases:
            book = self._make_book(name=name, **kwargs)
            _, mpath = self._prepare()
            manifest = self._manifest(mpath)
            self.assertNotIn(book.id, manifest["ids"], f"criterion {name} must exclude")

    def test_duplicate_title_and_author_excludes(self):
        b1 = self._make_book("dup1", title="The Same Story", author="A. N. Author")
        b2 = self._make_book("dup2", title="The Same Story!", author="A. N. Author")
        _, mpath = self._prepare()
        manifest = self._manifest(mpath)
        self.assertNotIn(b1.id, manifest["ids"])
        self.assertNotIn(b2.id, manifest["ids"])

    def test_duplicate_isbn_excludes(self):
        b1 = self._make_book("isbn1", title="First", author="Alpha", isbn="9780306406157")
        b2 = self._make_book("isbn2", title="Second", author="Beta", isbn="9780306406157")
        _, mpath = self._prepare()
        manifest = self._manifest(mpath)
        self.assertNotIn(b1.id, manifest["ids"])
        self.assertNotIn(b2.id, manifest["ids"])

    # ------------------------------------------------------------------ #
    # Suspicious patterns
    # ------------------------------------------------------------------ #

    def test_each_suspicious_pattern_excludes(self):
        cases = [
            ("http", {"title": "Buy http books"}),
            ("www", {"title": "See www.example.com"}),
            ("at_sign", {"title": "Mail me @ home"}),
            ("title_extension", {"title": "My Book.epub"}),
            ("all_digit_title", {"title": "12345678"}),
            ("title_too_short", {"title": "A"}),
            ("title_too_long", {"title": "X" * 201}),
            ("author_digit", {"author": "Jane Doe 2"}),
            ("author_stoplist", {"author": "anonymous"}),
            ("title_copy_of", {"title": "Copy of War and Peace"}),
            ("title_scan", {"title": "War and Peace scan"}),
        ]
        for name, kwargs in cases:
            book = self._make_book(name=name, **kwargs)
            _, mpath = self._prepare()
            manifest = self._manifest(mpath)
            self.assertNotIn(book.id, manifest["ids"], f"suspicious {name} must exclude")

    def test_suspicious_patterns_is_a_single_constant_list(self):
        self.assertIsInstance(SUSPICIOUS_PATTERNS, (list, tuple))
        self.assertGreater(len(SUSPICIOUS_PATTERNS), 0)

    # ------------------------------------------------------------------ #
    # Report
    # ------------------------------------------------------------------ #

    def test_report_counts(self):
        self._make_book("ok1", title="First Unique", author="Alice Alpha")
        self._make_book("ok2", title="Second Unique", author="Bob Beta")
        self._make_book("rev", title="Reviewed One", author="Cara Gamma", is_reviewed=True)
        out = StringIO()
        call_command("approve_batch", report=True, stdout=out)
        text = out.getvalue()
        self.assertIn("total books: 3", text)
        self.assertIn("eligible: 2", text)

    # ------------------------------------------------------------------ #
    # Prepare / sampling / manifest
    # ------------------------------------------------------------------ #

    def test_prepare_writes_manifest_outside_repository(self):
        self._make_book("outside")
        _, mpath = self._prepare()
        self.assertIsNotNone(mpath)
        self.assertTrue(mpath.exists())
        repo = Path("/workspace/eBookManagement").resolve()
        self.assertFalse(str(mpath.resolve()).startswith(str(repo)))
        manifest = self._manifest(mpath)
        self.assertEqual(manifest["criteria_version"], "v1")
        self.assertEqual(manifest["status"], "prepared")

    def test_sample_deterministic_for_seed(self):
        for i in range(30):
            self._make_book(f"b{i:02d}", title=f"Title {i:02d}", author=f"Author {i:02d}")
        _, m1 = self._prepare(seed=42)
        _, m2 = self._prepare(seed=42)
        self.assertEqual(self._manifest(m1)["sample_ids"], self._manifest(m2)["sample_ids"])

    def test_rejection_reason_stored(self):
        self._make_book("rej")
        _, mpath = self._prepare()
        call_command(
            "approve_batch",
            manifest=str(mpath),
            reject_id=1,
            reason="title looks wrong",
            stdout=StringIO(),
        )
        manifest = self._manifest(mpath)
        self.assertEqual(manifest["status"], "blocked")
        self.assertEqual(manifest["rejection_reason"], "title looks wrong")

    # ------------------------------------------------------------------ #
    # Apply
    # ------------------------------------------------------------------ #

    def test_apply_requires_exact_confirm(self):
        book = self._make_book("apply")
        _, mpath = self._prepare()
        manifest = self._manifest(mpath)
        n = len(manifest["ids"])
        call_command(
            "approve_batch",
            manifest=str(mpath),
            apply=True,
            confirm=n + 1,
            stdout=StringIO(),
        )
        book.refresh_from_db()
        self.assertFalse(book.finalmetadata.is_reviewed)

    def test_apply_refuses_blocked_manifest(self):
        book = self._make_book("blocked")
        _, mpath = self._prepare()
        call_command(
            "approve_batch",
            manifest=str(mpath),
            reject_id=1,
            reason="hold",
            stdout=StringIO(),
        )
        manifest = self._manifest(mpath)
        call_command(
            "approve_batch",
            manifest=str(mpath),
            apply=True,
            confirm=len(manifest["ids"]),
            stdout=StringIO(),
        )
        book.refresh_from_db()
        self.assertFalse(book.finalmetadata.is_reviewed)

    def test_apply_skips_changed_id(self):
        b1 = self._make_book("keep", title="Stays Put")
        b2 = self._make_book("drop", title="Now Changed")
        _, mpath = self._prepare()
        manifest = self._manifest(mpath)
        # b2 no longer qualifies after prepare
        b2.finalmetadata.final_title_confidence = 0.5
        b2.finalmetadata.save(update_fields=["final_title_confidence"])
        out = StringIO()
        call_command(
            "approve_batch",
            manifest=str(mpath),
            apply=True,
            confirm=len(manifest["ids"]),
            stdout=out,
        )
        b1.refresh_from_db()
        b2.refresh_from_db()
        self.assertTrue(b1.finalmetadata.is_reviewed)
        self.assertFalse(b2.finalmetadata.is_reviewed)
        self.assertIn(str(b2.id), out.getvalue())  # listed as skipped
        applied = self._manifest(mpath)
        self.assertIn(b1.id, applied["applied_ids"])
        self.assertNotIn(b2.id, applied["applied_ids"])

    def test_no_file_moves_and_no_filemove_rows(self):
        book = self._make_book("nomove")
        src = Path(book.file_path)
        self.assertTrue(src.exists())
        _, mpath = self._prepare()
        manifest = self._manifest(mpath)
        call_command(
            "approve_batch",
            manifest=str(mpath),
            apply=True,
            confirm=len(manifest["ids"]),
            stdout=StringIO(),
        )
        self.assertTrue(src.exists())  # never moved
        self.assertEqual(FileMove.objects.count(), 0)
