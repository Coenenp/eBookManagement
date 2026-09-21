"""Test that comic scanning produces FinalMetadata records.

Regression test for the M0 finding that the comic scan path
(content_processing._process_comic_issue) never called
resolve_final_metadata(book), so comics had no FinalMetadata row while the
ebook path created one for every book.
"""

import os
import shutil
import tempfile
import zipfile

from PIL import Image
from django.test import TestCase

from books.models import Book, DataSource, FinalMetadata, ScanFolder
from books.scanner.content_processing import _process_comic_issue
from books.scanner.grouping import ComicFileGrouper


def _make_cbz(directory, name):
    """Create a minimal valid CBZ (zip with one image) and return its path."""
    img = Image.new("RGB", (10, 10), color="white")
    tmp_img = os.path.join(directory, "_cover.png")
    img.save(tmp_img)

    cbz_path = os.path.join(directory, name)
    with zipfile.ZipFile(cbz_path, "w") as zf:
        zf.write(tmp_img, "cover.png")
    return cbz_path


class ComicFinalMetadataTests(TestCase):
    def setUp(self):
        self.initial_scan_source, _ = DataSource.objects.get_or_create(
            name=DataSource.INITIAL_SCAN, defaults={"trust_level": 0.2}
        )
        self.content_source, _ = DataSource.objects.get_or_create(
            name=DataSource.CONTENT_SCAN, defaults={"trust_level": 1.0}
        )
        self.test_dir = tempfile.mkdtemp()
        self.scan_folder = ScanFolder.objects.create(
            name="Test Comics",
            path=self.test_dir,
            content_type="comics",
            language="en",
        )

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_comic_issue_creates_final_metadata(self):
        """A comic file scanned through the comic path gets a FinalMetadata row."""
        cbz_path = _make_cbz(self.test_dir, "Asterix 01 - Asterix the Gaul.cbz")

        _process_comic_issue(
            file_path=cbz_path,
            series_name="Asterix",
            comic_grouper=ComicFileGrouper(),
            cover_files=[],
            opf_files=[],
            rescan=False,
            scan_folder=self.scan_folder,
        )

        book = Book.objects.get(content_type="comic", files__file_path=cbz_path)
        self.assertTrue(
            FinalMetadata.objects.filter(book=book).exists(),
            "Comic book should have a FinalMetadata record after processing",
        )