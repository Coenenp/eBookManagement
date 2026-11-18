"""Tests for deriving series from title rows (Part D)."""

from django.test import TestCase

from books.models import Book, BookSeries, BookTitle, DataSource, FinalMetadata, Series


class SeriesFromTitleTests(TestCase):
    def _source(self, name):
        return DataSource.objects.get_or_create(
            name=name, defaults={"priority": 1, "trust_level": 5}
        )[0]

    def test_series_derived_from_title(self):
        book = Book.objects.create()
        epub = self._source(DataSource.EPUB_INTERNAL)
        gb = self._source(DataSource.GOOGLE_BOOKS)

        BookTitle.objects.create(book=book, title="Dragon Moon", source=epub, confidence=0.8)
        BookTitle.objects.create(book=book, title="Dragonkeeper 3: Dragon Moon", source=gb, confidence=0.665)

        final = FinalMetadata.objects.create(book=book)
        final.update_final_title()
        final.update_final_series()
        self.assertEqual(final.final_series, "Dragonkeeper")
        self.assertEqual(final.final_series_number, "3")
        self.assertEqual(final.final_series_confidence, 0.665)

    def test_existing_series_row_wins(self):
        book = Book.objects.create()
        epub = self._source(DataSource.EPUB_INTERNAL)
        gb = self._source(DataSource.GOOGLE_BOOKS)

        BookTitle.objects.create(book=book, title="Dragon Moon", source=epub, confidence=0.8)
        BookTitle.objects.create(book=book, title="Dragonkeeper 3: Dragon Moon", source=gb, confidence=0.665)

        series = Series.objects.create(name="Existing Series")
        BookSeries.objects.create(book=book, series=series, series_number="7", source=epub, confidence=0.9)

        final = FinalMetadata.objects.create(book=book)
        final.update_final_series()
        self.assertEqual(final.final_series, "Existing Series")
        self.assertEqual(final.final_series_number, "7")

    def test_vegetarian_gives_no_series(self):
        book = Book.objects.create()
        epub = self._source(DataSource.EPUB_INTERNAL)
        gb = self._source(DataSource.GOOGLE_BOOKS)

        BookTitle.objects.create(book=book, title="The Vegetarian", source=epub, confidence=0.8)
        BookTitle.objects.create(book=book, title="The Vegetarian: A Novel", source=gb, confidence=0.7)

        final = FinalMetadata.objects.create(book=book)
        final.update_final_series()
        self.assertEqual(final.final_series, "")
        self.assertEqual(final.final_series_number, "")

    def test_conflicting_derivations_give_none(self):
        book = Book.objects.create()
        epub = self._source(DataSource.EPUB_INTERNAL)
        gb = self._source(DataSource.GOOGLE_BOOKS)
        scan = self._source(DataSource.INITIAL_SCAN)

        BookTitle.objects.create(book=book, title="Dragon Moon", source=epub, confidence=0.8)
        BookTitle.objects.create(book=book, title="Dragonkeeper 3: Dragon Moon", source=gb, confidence=0.665)
        BookTitle.objects.create(book=book, title="Dragon 2: Dragon Moon", source=scan, confidence=0.2)

        final = FinalMetadata.objects.create(book=book)
        final.update_final_series()
        self.assertEqual(final.final_series, "")
        self.assertEqual(final.final_series_number, "")
