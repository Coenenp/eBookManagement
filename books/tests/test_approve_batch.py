"""Tests for the approve_batch management command."""

import json
import re
import shutil
import tempfile
from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from books.management.commands.approve_batch import (
    CRITERIA_VERSION,
    DEFAULT_MANIFEST_DIR,
    MAX_SAMPLE,
    SUSPICIOUS_PATTERNS,
    Command,
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
            Path(cover_path).write_bytes(b"\xff\xd8\xff" + b"\x00" * 16)
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

    def test_criteria_version_is_v2(self):
        self.assertEqual(CRITERIA_VERSION, "v2")

    def test_default_manifest_dir_outside_repository(self):
        repo = Path("/workspace/eBookManagement").resolve()
        self.assertFalse(str(DEFAULT_MANIFEST_DIR.resolve()).startswith(str(repo)))

    # ------------------------------------------------------------------ #
    # Books without FinalMetadata
    # ------------------------------------------------------------------ #

    def test_book_without_final_metadata_does_not_raise(self):
        # A book with no FinalMetadata row must not crash report/prepare/apply;
        # report counts it under the first exclusion label, apply skips it.
        bare = create_test_book_with_file(
            file_path=str(Path(self.temp_dir) / "bare.epub"),
            file_format="epub",
            scan_folder=self.scan_folder,
            content_type="ebook",
        )
        # report
        out = StringIO()
        call_command("approve_batch", report=True, stdout=out)
        self.assertIn("no final metadata: 1", out.getvalue())
        # prepare
        call_command(
            "approve_batch",
            manifest_dir=str(self.manifest_dir),
            prepare=True,
            stdout=StringIO(),
        )
        # apply with that id in a manifest
        mpath = self.manifest_dir / "bare.json"
        mpath.write_text(
            json.dumps({"batch_id": "bare", "ids": [bare.id], "status": "prepared"})
        )
        out_apply = StringIO()
        call_command(
            "approve_batch",
            manifest=str(mpath),
            apply=True,
            confirm=1,
            stdout=out_apply,
        )
        self.assertIn(f"skipped {bare.id}", out_apply.getvalue())

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
            ("cover_empty", {"cover_path": ""}),
            ("cover_missing", {"cover_path": str(Path(self.temp_dir) / "gone.jpg")}),
            ("bad_format", {"fmt": "pdf"}),
            ("title_stoplist", {"title": "untitled"}),
            ("title_equals_author", {"title": "Jane Doe", "author": "Jane Doe"}),
        ]
        for idx, (name, kwargs) in enumerate(cases):
            title = kwargs.get("title", f"Case {name} Title")
            author = kwargs.get("author", f"Author {name}")
            extra = {k: v for k, v in kwargs.items() if k not in ("title", "author")}
            case_book = self._make_book(name=f"case_{name}", title=title, author=author, **extra)
            letter = chr(ord("a") + idx)
            control = self._make_book(
                name=f"ctrl_{name}",
                title=f"Control Book {letter}",
                author=f"Control Author {letter}",
            )
            _, mpath = self._prepare()
            manifest = self._manifest(mpath)
            self.assertNotIn(case_book.id, manifest["ids"], f"criterion {name} must exclude")
            self.assertIn(control.id, manifest["ids"], f"control for {name} must be eligible")

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

    def test_duplicate_with_url_cover_counted_as_duplicate(self):
        # A book that is both a duplicate and has a URL cover is attributed to
        # the duplicate criterion (cheap criteria run before the cover checks).
        self._make_book("dupurl1", title="Same Again", author="Dup Author",
                        cover_path="https://books.google.com/x")
        self._make_book("dupurl2", title="Same Again", author="Dup Author")
        out = StringIO()
        call_command("approve_batch", report=True, stdout=out)
        text = out.getvalue()
        self.assertIn("duplicate: 2", text)
        self.assertIn("cover url (needs download): 0", text)

    # ------------------------------------------------------------------ #
    # Cover path resolution
    # ------------------------------------------------------------------ #

    def test_relative_cover_path_resolves_against_media_root(self):
        from django.test import override_settings

        media = Path(self.temp_dir) / "media"
        media.mkdir()
        rel_ok = "cover_cache/abc.jpg"
        abs_ok = media / rel_ok
        abs_ok.parent.mkdir(parents=True)
        abs_ok.write_bytes(b"\xff\xd8\xff" + b"\x00" * 16)
        ok_book = self._make_book("relok", title="Relative Cover Book", author="Rel Author", cover_path=rel_ok)
        missing_book = self._make_book("relmissing", title="Missing Cover Book", author="Miss Author", cover_path="cover_cache/gone.jpg")
        with override_settings(MEDIA_ROOT=str(media)):
            _, mpath = self._prepare()
        manifest = self._manifest(mpath)
        self.assertIn(ok_book.id, manifest["ids"], "relative cover under media dir must pass")
        self.assertNotIn(missing_book.id, manifest["ids"], "missing relative cover must be excluded")

    def test_cover_sub_reasons_exclude(self):
        from django.test import override_settings

        media = Path(self.temp_dir) / "media"
        media.mkdir()
        bad = Path(self.temp_dir) / "bad.jpg"
        bad.write_bytes(b"not an image")
        cases = [
            ("empty", ""),
            ("url", "https://books.google.com/books/content?id=abc123"),
            ("missing", "cover_cache/gone.jpg"),
            ("invalid", str(bad)),
        ]
        for name, cover_path in cases:
            book = self._make_book(
                f"cov_{name}",
                title=f"Cover {name} Title",
                author=f"Cover {name} Author",
                cover_path=cover_path,
            )
            with override_settings(MEDIA_ROOT=str(media)):
                _, mpath = self._prepare()
            manifest = self._manifest(mpath)
            self.assertNotIn(book.id, manifest["ids"], f"cover sub-reason {name} must exclude")

        # Clean control: a valid local cover must not be excluded by the cover checks.
        control = self._make_book("cov_clean", title="Clean Cover Title", author="Clean Author")
        with override_settings(MEDIA_ROOT=str(media)):
            _, mpath = self._prepare()
        manifest = self._manifest(mpath)
        self.assertIn(control.id, manifest["ids"], "clean cover control must pass")

    def test_valid_local_cover_passes_regardless_of_confidence(self):
        book = self._make_book(
            "lowconf", title="Low Conf Book", author="Low Author", cover_conf=0.0
        )
        _, mpath = self._prepare()
        manifest = self._manifest(mpath)
        self.assertIn(book.id, manifest["ids"], "valid local cover must pass whatever its confidence")

    def test_report_counts_cover_sub_reasons(self):
        self._make_book("okr", title="Report OK", author="Rep Author")
        self._make_book("empt", title="Empty Cover", author="Emp Author", cover_path="")
        self._make_book("urlc", title="URL Cover", author="Url Author",
                        cover_path="https://books.google.com/x")
        self._make_book("miss", title="Missing Cover", author="Mis Author",
                        cover_path=str(Path(self.temp_dir) / "gone.jpg"))
        bad = Path(self.temp_dir) / "badcov.jpg"
        bad.write_bytes(b"nope")
        self._make_book("inv", title="Invalid Cover", author="Inv Author", cover_path=str(bad))
        out = StringIO()
        call_command("approve_batch", report=True, stdout=out)
        text = out.getvalue()
        self.assertIn("cover empty: 1", text)
        self.assertIn("cover url (needs download): 1", text)
        self.assertIn("cover missing file: 1", text)
        self.assertIn("cover invalid image: 1", text)

    # ------------------------------------------------------------------ #
    # Shared cover criterion
    # ------------------------------------------------------------------ #

    def test_two_books_sharing_cover_are_both_excluded(self):
        shared = Path(self.temp_dir) / "shared.jpg"
        shared.write_bytes(b"\xff\xd8\xff" + b"\x00" * 16)
        b1 = self._make_book("sh1", title="Shared One", author="Shar Author A", cover_path=str(shared))
        b2 = self._make_book("sh2", title="Shared Two", author="Shar Author B", cover_path=str(shared))
        _, mpath = self._prepare()
        manifest = self._manifest(mpath)
        self.assertNotIn(b1.id, manifest["ids"])
        self.assertNotIn(b2.id, manifest["ids"])

    def test_book_with_own_cover_is_not_excluded(self):
        book = self._make_book("owncover", title="Own Cover", author="Own Author")
        _, mpath = self._prepare()
        manifest = self._manifest(mpath)
        self.assertIn(book.id, manifest["ids"])

    def test_report_counts_shared_covers(self):
        shared = Path(self.temp_dir) / "shared2.jpg"
        shared.write_bytes(b"\xff\xd8\xff" + b"\x00" * 16)
        self._make_book("rsh1", title="Report Shared One", author="RSh A", cover_path=str(shared))
        self._make_book("rsh2", title="Report Shared Two", author="RSh B", cover_path=str(shared))
        out = StringIO()
        call_command("approve_batch", report=True, stdout=out)
        self.assertIn("cover shared: 2", out.getvalue())

    # ------------------------------------------------------------------ #
    # Contact sheets
    # ------------------------------------------------------------------ #

    def test_prepare_writes_contact_sheet_for_all_ids(self):
        for name in ("alpha", "beta", "gamma"):
            self._make_book(f"cs_{name}", title=f"Contact {name}", author=f"CA {name}")
        text, mpath = self._prepare()
        manifest = self._manifest(mpath)
        self.assertIn("sheets", manifest)
        self.assertTrue(manifest["sheets"])
        sheet_name = manifest["sheets"][0]
        self.assertEqual(sheet_name, f"{manifest['batch_id']}sheet0.png")
        sheet_path = self.manifest_dir / sheet_name
        self.assertTrue(sheet_path.exists())
        with open(sheet_path, "rb") as fh:
            self.assertEqual(fh.read(8), b"\x89PNG\r\n\x1a\n")
        self.assertIn(str(sheet_path), text)

    def test_unreadable_cover_draws_err_without_raising(self):
        from PIL import Image

        bad = Path(self.temp_dir) / "badcover.jpg"
        bad.write_bytes(b"\xff\xd8\xff" + b"\x00" * 16)  # valid magic, undecodable
        book = self._make_book("badc", title="Bad Cover", author="Bad Author", cover_path=str(bad))
        _, mpath = self._prepare()  # must not raise
        manifest = self._manifest(mpath)
        self.assertIn(book.id, manifest["ids"])
        sheet_path = self.manifest_dir / manifest["sheets"][0]
        img = Image.open(sheet_path).convert("RGB")
        px = img.load()
        has_red = any(
            px[x, y][0] > 250 and px[x, y][1] < 200 and px[x, y][2] < 200
            for x in range(img.width) for y in range(img.height)
        )
        self.assertTrue(has_red, "ERR label must be drawn red for an unreadable cover")

    # ------------------------------------------------------------------ #
    # Per-book exclusion (--exclude-ids)
    # ------------------------------------------------------------------ #

    def test_apply_exclude_ids_skips_excluded(self):
        b1 = self._make_book("x1", title="Exclude One", author="XA One")
        b2 = self._make_book("x2", title="Exclude Two", author="XA Two")
        _, mpath = self._prepare()
        manifest = self._manifest(mpath)
        out = StringIO()
        call_command(
            "approve_batch",
            manifest=str(mpath),
            apply=True,
            confirm=len(manifest["ids"]),
            exclude_ids=str(b1.id),
            stdout=out,
        )
        b1.refresh_from_db()
        b2.refresh_from_db()
        self.assertFalse(b1.finalmetadata.is_reviewed)
        self.assertTrue(b2.finalmetadata.is_reviewed)
        self.assertIn(str(b1.id), out.getvalue())

    def test_exclude_writes_rejected_file(self):
        b1 = self._make_book("rf1", title="Rej One", author="RA One")
        self._make_book("rf2", title="Rej Two", author="RA Two")
        _, mpath = self._prepare()
        manifest = self._manifest(mpath)
        call_command(
            "approve_batch",
            manifest=str(mpath),
            apply=True,
            confirm=len(manifest["ids"]),
            exclude_ids=str(b1.id),
            stdout=StringIO(),
        )
        rejected_file = self.manifest_dir / "cover_rejected.txt"
        self.assertTrue(rejected_file.exists())
        self.assertIn(str(b1.id), rejected_file.read_text().splitlines())

    def test_later_prepare_skips_rejected_ids(self):
        b1 = self._make_book("sp1", title="Skip One", author="SA One")
        _, mpath = self._prepare()
        manifest = self._manifest(mpath)
        call_command(
            "approve_batch",
            manifest=str(mpath),
            apply=True,
            confirm=len(manifest["ids"]),
            exclude_ids=str(b1.id),
            stdout=StringIO(),
        )
        b3 = self._make_book("sp3", title="Skip Three", author="SA Three")
        _, mpath2 = self._prepare()
        manifest2 = self._manifest(mpath2)
        self.assertNotIn(b1.id, manifest2["ids"])
        self.assertIn(b3.id, manifest2["ids"])

    def test_unknown_exclude_id_raises(self):
        book = self._make_book("ue", title="Unknown Exclude", author="UA")
        _, mpath = self._prepare()
        manifest = self._manifest(mpath)
        with self.assertRaises(CommandError):
            call_command(
                "approve_batch",
                manifest=str(mpath),
                apply=True,
                confirm=len(manifest["ids"]),
                exclude_ids="999999",
                stdout=StringIO(),
            )

    def test_report_counts_rejected_by_review(self):
        b1 = self._make_book("rr1", title="Rej Report", author="RRA")
        self._make_book("rr2", title="Keep Report", author="RRA Two")
        (self.manifest_dir / "cover_rejected.txt").write_text(f"{b1.id}\n")
        out = StringIO()
        call_command("approve_batch", report=True, manifest_dir=str(self.manifest_dir), stdout=out)
        self.assertIn("cover rejected by review: 1", out.getvalue())

    def test_reject_id_behaviour_unchanged(self):
        book = self._make_book("rj", title="Reject Id", author="RJ")
        _, mpath = self._prepare()
        call_command(
            "approve_batch",
            manifest=str(mpath),
            reject_id=book.id,
            reason="still works",
            stdout=StringIO(),
        )
        manifest = self._manifest(mpath)
        self.assertEqual(manifest["status"], "blocked")
        self.assertEqual(manifest["rejected_id"], book.id)

    def test_sample_line_ends_with_resolved_cover_path(self):
        from django.test import override_settings

        media = Path(self.temp_dir) / "media"
        media.mkdir()
        book = self._make_book(
            "samp", title="Sample Book", author="Sample Author", cover_path="cover_cache/s.jpg"
        )
        (media / "cover_cache").mkdir(parents=True)
        (media / "cover_cache" / "s.jpg").write_bytes(b"\xff\xd8\xff" + b"\x00" * 8)
        with override_settings(MEDIA_ROOT=str(media)):
            text, _ = self._prepare(seed=1)
        expected = str(media / "cover_cache" / "s.jpg")
        lines = [ln for ln in text.splitlines() if ln.startswith(f"{book.id} |")]
        self.assertTrue(lines, "sample line for the book must be printed")
        self.assertTrue(lines[0].rstrip().endswith(expected),
                        f"sample line must end with resolved cover path, got: {lines[0]!r}")

    def test_apply_skips_disappeared_cover(self):
        from django.test import override_settings

        media = Path(self.temp_dir) / "media"
        media.mkdir()
        book = self._make_book(
            "vanish", title="Vanish Cover", author="Van Author", cover_path="cover_cache/v.jpg"
        )
        (media / "cover_cache").mkdir(parents=True)
        cover_file = media / "cover_cache" / "v.jpg"
        cover_file.write_bytes(b"\xff\xd8\xff" + b"\x00" * 8)
        with override_settings(MEDIA_ROOT=str(media)):
            _, mpath = self._prepare()
        manifest = self._manifest(mpath)
        cover_file.unlink()
        out = StringIO()
        with override_settings(MEDIA_ROOT=str(media)):
            call_command(
                "approve_batch",
                manifest=str(mpath),
                apply=True,
                confirm=len(manifest["ids"]),
                stdout=out,
            )
        book.refresh_from_db()
        self.assertFalse(book.finalmetadata.is_reviewed)
        self.assertIn(str(book.id), out.getvalue())

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
        for idx, (name, kwargs) in enumerate(cases):
            title = kwargs.get("title", f"Case {name} Title")
            author = kwargs.get("author", f"Author {name}")
            extra = {k: v for k, v in kwargs.items() if k not in ("title", "author")}
            case_book = self._make_book(name=f"case_{name}", title=title, author=author, **extra)
            letter = chr(ord("a") + idx)
            control = self._make_book(
                name=f"ctrl_{name}",
                title=f"Control Book {letter}",
                author=f"Control Author {letter}",
            )
            _, mpath = self._prepare()
            manifest = self._manifest(mpath)
            self.assertNotIn(case_book.id, manifest["ids"], f"suspicious {name} must exclude")
            self.assertIn(control.id, manifest["ids"], f"control for {name} must be eligible")

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
        self.assertEqual(manifest["criteria_version"], "v2")
        self.assertEqual(manifest["status"], "prepared")

    def test_sample_deterministic_for_seed(self):
        for i in range(30):
            self._make_book(f"b{i:02d}", title=f"Title {i:02d}", author=f"Author {i:02d}")
        _, m1 = self._prepare(seed=42)
        _, m2 = self._prepare(seed=42)
        self.assertEqual(self._manifest(m1)["sample_ids"], self._manifest(m2)["sample_ids"])

    def test_planned_target_called_only_for_sample(self):
        import itertools
        import string
        from unittest.mock import patch

        suffixes = ["".join(p) for p in itertools.product(string.ascii_lowercase, repeat=2)]
        for i in range(30):
            self._make_book(
                f"s{i:02d}",
                title=f"Scale Title {suffixes[i]}",
                author=f"Scale Author {suffixes[i]}",
            )
        with patch.object(Command, "_planned_target") as mock_target:
            call_command(
                "approve_batch",
                manifest_dir=str(self.manifest_dir),
                prepare=True,
                stdout=StringIO(),
            )
        self.assertLessEqual(mock_target.call_count, MAX_SAMPLE)

    def test_rejection_reason_stored(self):
        book = self._make_book("rej")
        _, mpath = self._prepare()
        call_command(
            "approve_batch",
            manifest=str(mpath),
            reject_id=book.id,
            reason="title looks wrong",
            stdout=StringIO(),
        )
        manifest = self._manifest(mpath)
        self.assertEqual(manifest["status"], "blocked")
        self.assertEqual(manifest["rejection_reason"], "title looks wrong")
        self.assertEqual(manifest["rejected_id"], book.id)

    # ------------------------------------------------------------------ #
    # Apply
    # ------------------------------------------------------------------ #

    def test_apply_requires_exact_confirm(self):
        book = self._make_book("apply")
        _, mpath = self._prepare()
        manifest = self._manifest(mpath)
        n = len(manifest["ids"])
        with self.assertRaises(CommandError):
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
            reject_id=book.id,
            reason="hold",
            stdout=StringIO(),
        )
        manifest = self._manifest(mpath)
        with self.assertRaises(CommandError):
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

    def test_apply_preserves_language_flag(self):
        # A language flag present at apply time survives: the apply-time exclusion
        # re-check skips the flagged book, so its flag is never cleared. A clean
        # sibling is approved and its unresolved_reason stays empty.
        flagged = self._make_book("langflag", title="Flagged Title", author="Flag Author")
        clean = self._make_book("cleanctl", title="Clean Title", author="Clean Author")
        _, mpath = self._prepare()
        manifest = self._manifest(mpath)
        ffm = flagged.finalmetadata
        ffm.unresolved_reason = "language_undetermined"
        ffm.save(update_fields=["unresolved_reason"])
        out = StringIO()
        call_command(
            "approve_batch",
            manifest=str(mpath),
            apply=True,
            confirm=len(manifest["ids"]),
            stdout=out,
        )
        ffm.refresh_from_db()
        clean.refresh_from_db()
        self.assertEqual(ffm.unresolved_reason, "language_undetermined")  # survives
        self.assertFalse(ffm.is_reviewed)
        self.assertTrue(clean.finalmetadata.is_reviewed)
        self.assertEqual(clean.finalmetadata.unresolved_reason, "")  # stays empty

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
