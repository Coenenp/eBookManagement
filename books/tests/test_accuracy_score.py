"""
Tests for the per-book accuracy score on FinalMetadata.

The accuracy score is DISTINCT from overall_confidence (source trust) and
completeness_score (field fill rate): it measures evidence agreement, i.e.
how strongly independent candidates corroborate the final title/author and
whether a strong identifier (ISBN) backs the identity.
"""

import os
import shutil
import tempfile

from django.test import TestCase

from books.models import Author, BookAuthor, BookTitle, DataSource, FinalMetadata, ScanFolder
from books.tests.test_helpers import create_test_book_with_file


class AccuracyScoreTests(TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.scan_folder = ScanFolder.objects.create(path=self.temp_dir, name="Accuracy Scan Folder")
        self.book = create_test_book_with_file(
            file_path=os.path.join(self.temp_dir, "book.epub"),
            file_format="epub",
            file_size=1024000,
            scan_folder=self.scan_folder,
        )
        # Drop the auto-created filename-derived title so tests control candidates.
        self.book.titles.all().delete()

        self.src_a, _ = DataSource.objects.get_or_create(name="src_a", defaults={"trust_level": 0.9})
        self.src_b, _ = DataSource.objects.get_or_create(name="src_b", defaults={"trust_level": 0.8})

    def tearDown(self):
        if hasattr(self, "temp_dir") and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def _title(self, name, source=None):
        return BookTitle.objects.create(book=self.book, title=name, source=source or self.src_a, confidence=0.9, is_active=True)

    def _author(self, name, source=None):
        author, _ = Author.objects.get_or_create(name=name)
        return BookAuthor.objects.create(book=self.book, author=author, source=source or self.src_a, confidence=0.9, is_active=True, is_main_author=True)

    # --- _corroboration unit tests ---

    def test_corroboration_empty_final_is_zero(self):
        self.assertEqual(FinalMetadata._corroboration("", ["The Great Book"]), 0.0)
        self.assertEqual(FinalMetadata._corroboration(None, ["The Great Book"]), 0.0)
        self.assertEqual(FinalMetadata._corroboration("The Great Book", []), 0.0)

    def test_corroboration_single_matching_is_uncorroborated(self):
        self.assertEqual(FinalMetadata._corroboration("The Great Book", ["The Great Book"]), 0.5)

    def test_corroboration_single_nonmatching_is_zero(self):
        self.assertEqual(FinalMetadata._corroboration("The Great Book", ["Totally Different"]), 0.0)

    def test_corroboration_multiple_agreeing_is_one(self):
        self.assertEqual(
            FinalMetadata._corroboration("The Great Book", ["The Great Book", "the great book"]),
            1.0,
        )

    def test_corroboration_disagreement_lowers_score(self):
        self.assertEqual(
            FinalMetadata._corroboration("The Great Book", ["The Great Book", "Totally Different"]),
            0.5,
        )

    # --- calculate_accuracy_score tests ---

    def test_no_evidence_is_zero(self):
        fm = FinalMetadata(book=self.book, final_title="", final_author="", isbn="")
        self.assertEqual(fm.calculate_accuracy_score(), 0.0)

    def test_single_source_no_isbn_is_uncorroborated(self):
        # A lone high-trust value is NOT accurate on its own: 0.35 * 0.5 (title)
        # + 0.35 * 0.5 (author) + 0.30 * 0.0 (no ISBN) = 0.35.
        self._title("The Great Book")
        self._author("Jane Doe")
        fm = FinalMetadata(book=self.book, final_title="The Great Book", final_author="Jane Doe", isbn="")
        self.assertAlmostEqual(fm.calculate_accuracy_score(), 0.35, places=6)

    def test_multiple_agreeing_sources_with_isbn_is_one(self):
        self._title("The Great Book", self.src_a)
        self._title("The Great Book", self.src_b)
        self._author("Jane Doe", self.src_a)
        self._author("Jane Doe", self.src_b)
        fm = FinalMetadata(book=self.book, final_title="The Great Book", final_author="Jane Doe", isbn="9780123456789")
        self.assertAlmostEqual(fm.calculate_accuracy_score(), 1.0, places=6)

    def test_multiple_agreeing_no_isbn_caps_below_one(self):
        self._title("The Great Book", self.src_a)
        self._title("The Great Book", self.src_b)
        self._author("Jane Doe", self.src_a)
        self._author("Jane Doe", self.src_b)
        fm = FinalMetadata(book=self.book, final_title="The Great Book", final_author="Jane Doe", isbn="")
        # 0.35 * 1.0 + 0.35 * 1.0 + 0.30 * 0.0 = 0.70
        self.assertAlmostEqual(fm.calculate_accuracy_score(), 0.70, places=6)

    def test_disagreeing_title_lowers_score(self):
        self._title("The Great Book", self.src_a)
        self._title("Totally Different", self.src_b)
        self._author("Jane Doe", self.src_a)
        self._author("Jane Doe", self.src_b)
        fm = FinalMetadata(book=self.book, final_title="The Great Book", final_author="Jane Doe", isbn="")
        # title corroboration 0.5, author 1.0, no ISBN:
        # 0.35 * 0.5 + 0.35 * 1.0 + 0.30 * 0.0 = 0.525
        self.assertAlmostEqual(fm.calculate_accuracy_score(), 0.525, places=6)

    # --- integration: sync persists the score ---

    def test_sync_persists_accuracy_score(self):
        self._title("The Great Book", self.src_a)
        self._title("The Great Book", self.src_b)
        self._author("Jane Doe", self.src_a)
        self._author("Jane Doe", self.src_b)

        fm = FinalMetadata.objects.create(book=self.book)
        fm.sync_from_sources()

        fm.refresh_from_db()
        self.assertAlmostEqual(fm.accuracy_score, 0.70, places=6)
