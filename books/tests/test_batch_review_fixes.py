"""Service-fix tests for the batch review PR (Part A).

Each test pins a behaviour added in Part A: apply refuses an already-applied
manifest, ``exclude_ids`` accepts containers, ``add_holds`` cleans the reason,
and ``store_author_order`` reports an explicit ``refused`` key.
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


class BatchServiceFixTests(TestCase):
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
    # Item 1: apply refuses an already-applied manifest
    # ------------------------------------------------------------------ #

    def test_apply_refuses_already_applied_manifest(self):
        from books.services.batches import apply_batch

        b1 = self._make_book("already", title="Already Applied", author="AA Author")
        _, mpath = self._prepare()

        # First apply succeeds and records applied_ids.
        result = apply_batch(
            manifest_path=str(mpath),
            confirm=1,
            exclude_ids=None,
            exclude_reason="review",
            allow_high_exclusion=True,
        )
        self.assertEqual(result["approved_count"], 1)

        manifest_before = mpath.read_text()
        holds_path = self.manifest_dir / "rejected_ids.txt"
        holds_before = holds_path.read_text() if holds_path.exists() else ""
        self.assertEqual(json.loads(manifest_before)["applied_ids"], [b1.id])

        # A second apply is refused and touches nothing.
        refused = apply_batch(
            manifest_path=str(mpath),
            confirm=1,
            exclude_ids=None,
            exclude_reason="review",
            allow_high_exclusion=True,
        )
        self.assertEqual(refused, {"refusal": "refusing: manifest already applied"})
        self.assertEqual(mpath.read_text(), manifest_before)
        self.assertEqual(
            holds_path.read_text() if holds_path.exists() else "", holds_before
        )
        self.assertEqual(json.loads(mpath.read_text())["applied_ids"], [b1.id])

    def test_command_raises_already_applied(self):
        self._make_book("cmdapplied", title="Cmd Applied", author="CA Author")
        _, mpath = self._prepare()
        call_command(
            "approve_batch",
            manifest=str(mpath),
            apply=True,
            confirm=1,
            stdout=StringIO(),
        )
        err = self._apply_error(mpath, confirm=1)
        self.assertEqual(err, "refusing: manifest already applied")

    # ------------------------------------------------------------------ #
    # Item 2: exclude_ids accepts list / tuple / set of ints or digits
    # ------------------------------------------------------------------ #

    def test_parse_exclude_ids_accepts_containers(self):
        from books.services.batches import _parse_exclude_ids

        self.assertEqual(_parse_exclude_ids("1,2,3"), ([1, 2, 3], None))
        self.assertEqual(_parse_exclude_ids([1, 2, 3]), ([1, 2, 3], None))
        self.assertEqual(_parse_exclude_ids((1, 2, 3)), ([1, 2, 3], None))
        self.assertEqual(set(_parse_exclude_ids({1, 2, 3})[0]), {1, 2, 3})
        self.assertEqual(_parse_exclude_ids(["1", "2", "3"]), ([1, 2, 3], None))
        self.assertEqual(_parse_exclude_ids(["1", 2, "3"]), ([1, 2, 3], None))
        self.assertEqual(_parse_exclude_ids([]), ([], None))

    def test_parse_exclude_ids_invalid_entry_same_text(self):
        from books.services.batches import _parse_exclude_ids

        self.assertEqual(
            _parse_exclude_ids("1,abc"), (None, "refusing: invalid exclude id 'abc'")
        )
        self.assertEqual(
            _parse_exclude_ids([1, "abc"]),
            (None, "refusing: invalid exclude id 'abc'"),
        )

    def test_apply_exclude_ids_as_list_matches_string(self):
        from books.services.batches import apply_batch

        b1 = self._make_book("l1", title="List One", author="List Author One")
        b2 = self._make_book("l2", title="List Two", author="List Author Two")
        _, mpath = self._prepare()
        pristine = mpath.read_text()
        rejects = self.manifest_dir / "rejected_ids.txt"

        out_str = apply_batch(
            manifest_path=str(mpath),
            confirm=2,
            exclude_ids=str(b1.id),
            exclude_reason="review",
            allow_high_exclusion=True,
        )
        str_skipped = out_str["skipped"]
        str_approved = out_str["approved"]

        # Reset for the list path.
        from books.models import FinalMetadata

        FinalMetadata.objects.update(is_reviewed=False)
        mpath.write_text(pristine)
        rejects.unlink()

        out_list = apply_batch(
            manifest_path=str(mpath),
            confirm=2,
            exclude_ids=[b1.id],
            exclude_reason="review",
            allow_high_exclusion=True,
        )
        self.assertEqual(out_list["skipped"], str_skipped)
        self.assertEqual(out_list["approved"], str_approved)
        self.assertEqual(out_list["approved_count"], 1)
        self.assertEqual(out_list["skipped_count"], 1)

    # ------------------------------------------------------------------ #
    # Item 3: add_holds cleans the reason
    # ------------------------------------------------------------------ #

    def test_golden_add_holds_plain_reason_unchanged(self):
        from books.services.batches import add_holds

        add_holds([7], str(self.manifest_dir), "still works")
        self.assertEqual(
            (self.manifest_dir / "rejected_ids.txt").read_text(), "7\tstill works\n"
        )

    def test_add_holds_cleans_tabs_and_newlines(self):
        from books.services.batches import add_holds

        add_holds([42], str(self.manifest_dir), "bad\ttitle\nwith\rnewline")
        content = (self.manifest_dir / "rejected_ids.txt").read_text()
        self.assertEqual(content, "42\tbad title with newline\n")

    def test_reject_books_relies_on_add_holds_cleaning(self):
        from books.services.batches import reject_books

        book = self._make_book("cleanreject", title="Clean Reject", author="CR Author")
        _, mpath = self._prepare()
        result = reject_books(
            manifest_path=str(mpath), reject_id=book.id, reason="bad\ttitle\nnewline"
        )
        self.assertIn("rejected", result["line"])
        content = (self.manifest_dir / "rejected_ids.txt").read_text()
        self.assertIn(f"{book.id}\tbad title newline", content)
        # The reason is stored raw in the manifest excluded map (unchanged).
        self.assertEqual(
            json.loads(mpath.read_text())["excluded"][str(book.id)],
            "bad\ttitle\nnewline",
        )


class StoreAuthorOrderRefusedKeyTests(TestCase):
    """Item 4: store_author_order returns an explicit 'refused' key."""

    def _refused_setup(self):
        from books.models import Author, Book, BookAuthor, DataSource

        natural = Author.objects.create(name="Natsume Soseki", is_reviewed=True)
        holder = Author.objects.create(
            name="Soseki Natsume", first_name="Soseki", last_name="Natsume"
        )
        source = DataSource.objects.get_or_create(
            name=DataSource.EPUB_INTERNAL, defaults={"priority": 1, "trust_level": 5}
        )[0]
        book = Book.objects.create()
        BookAuthor.objects.create(book=book, author=natural, source=source)
        return natural, holder, book

    def test_refused_false_on_success(self):
        from books.services.authors import store_author_order

        result = store_author_order("Han Kang", "Han", "Kang", True)
        self.assertIn("refused", result)
        self.assertFalse(result["refused"])

    def test_refused_false_on_dry_run(self):
        from books.services.authors import store_author_order

        result = store_author_order("Han Kang", "Han", "Kang", False)
        self.assertIn("refused", result)
        self.assertFalse(result["refused"])

    def test_refused_true_on_refusal(self):
        from books.services.authors import store_author_order

        self._refused_setup()
        result = store_author_order("Natsume Soseki", "Natsume", "Soseki", True)
        self.assertIn("refused", result)
        self.assertTrue(result["refused"])
        self.assertFalse(result["merged"])
