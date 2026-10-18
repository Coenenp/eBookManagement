"""Tests for filename-metadata persistence and the embedded-metadata denylist.

Covers the fixes that make a "Last, First - Title (Year)" filename win over
structural folder names and placeholder embedded metadata:

- The parsed title is stored as the active title; the raw-filename seed is
  demoted to inactive when it differs.
- publication_year from the filename parse is persisted.
- Structural folder names (Papers, Miscellaneous Articles, ...) are never
  author clues.
- Denylisted embedded PDF/EPUB values are ignored as author or title, while a
  legitimate mononym author (e.g. "Homer") is kept.
"""

from pathlib import Path
from unittest.mock import patch

from django.test import TestCase

from books.models import Book, BookFile, BookMetadata, BookTitle, DataSource, FinalMetadata
from books.scanner.extractors.denylist import is_denylisted
from books.scanner.folder import _extract_filename_metadata
from books.scanner.resolver import resolve_final_metadata
from books.utils.parsing_helpers import extract_folder_clues


class EmbeddedMetadataDenylistTests(TestCase):
    """The embedded-metadata denylist is an explicit data table."""

    def test_denylisted_placeholder_values(self):
        for value in [
            "Administrator",
            "administrator",
            "untitled",
            "Untitled",
            "Faxafdruk op volledige pagina",
            "faxafdruk op volledige pagina",
        ]:
            with self.subTest(value=value):
                self.assertTrue(is_denylisted(value))

    def test_isbn_named_file_is_denylisted(self):
        self.assertTrue(is_denylisted("978-90-313-8000-8_BookFrontmatter_OnlinePDF.pdf"))
        self.assertTrue(is_denylisted("9789031380008_BookFrontmatter_OnlinePDF.pdf"))

    def test_legitimate_mononym_author_is_kept(self):
        self.assertFalse(is_denylisted("Homer"))
        self.assertFalse(is_denylisted("Naomi Klein"))
        self.assertFalse(is_denylisted("A Real Book Title"))

    def test_empty_value_is_denylisted(self):
        self.assertTrue(is_denylisted(""))
        self.assertTrue(is_denylisted(None))


class StructuralFolderClueTests(TestCase):
    """Structural folder names are never author clues."""

    def test_papers_folder_is_not_an_author(self):
        clues = extract_folder_clues(Path("/library/Klein, Naomi/Papers/Klein, Naomi - A Paper (2020).pdf"))
        self.assertEqual(clues["all_authors"], [])
        self.assertIsNone(clues["likely_author"])

    def test_other_structural_folders_are_not_authors(self):
        for folder in [
            "Miscellaneous Articles",
            "Miscellaneous Papers",
            "Anarchist Library reprints",
            "(3 books, 2 papers)",
            "(12 books, 5 papers)",
        ]:
            with self.subTest(folder=folder):
                clues = extract_folder_clues(Path(f"/library/{folder}/Some Title (2020).pdf"))
                self.assertEqual(clues["all_authors"], [])
                self.assertIsNone(clues["likely_author"])

    def test_real_author_folder_is_still_an_author_clue(self):
        clues = extract_folder_clues(Path("/library/Jane Austen/Pride and Prejudice.epub"))
        self.assertEqual(clues["all_authors"], ["Jane Austen"])


class FilenameMetadataPersistenceTests(TestCase):
    """A Klein-style path stores title/author/year from the filename."""

    def setUp(self):
        super().setUp()
        self.source, _ = DataSource.objects.get_or_create(name=DataSource.INITIAL_SCAN, defaults={"trust_level": 0.2})

    def _make_klein_book(self, filename):
        file_path = f"/library/Klein, Naomi/Papers/{filename}"
        book = Book.objects.create(content_type="ebook")
        BookFile.objects.create(book=book, file_path=file_path, file_format="pdf")
        return book, file_path

    def test_stores_title_and_author_from_filename(self):
        book, file_path = self._make_klein_book("Klein, Naomi - A Summer of Wildfires and Hurricanes (2017).pdf")
        _extract_filename_metadata(book)

        active_titles = set(book.titles.filter(is_active=True).values_list("title", flat=True))
        self.assertIn("A Summer of Wildfires and Hurricanes", active_titles)
        self.assertNotIn("Klein, Naomi - A Summer of Wildfires and Hurricanes", active_titles)

        authors = list(book.author_relationships.filter(is_active=True).values_list("author__name", flat=True))
        self.assertIn("Naomi Klein", authors)
        self.assertNotIn("Papers", authors)

    def test_raw_seed_stays_inactive_when_it_differs(self):
        book, file_path = self._make_klein_book("Klein, Naomi - A Summer of Wildfires and Hurricanes (2017).pdf")
        raw_stem = "Klein, Naomi - A Summer of Wildfires and Hurricanes (2017)"
        BookTitle.objects.create(book=book, title=raw_stem, source=self.source, confidence=0.2, is_active=True)

        _extract_filename_metadata(book)

        self.assertFalse(BookTitle.objects.filter(book=book, title=raw_stem, is_active=True).exists())
        self.assertTrue(
            BookTitle.objects.filter(
                book=book,
                title="A Summer of Wildfires and Hurricanes",
                is_active=True,
            ).exists()
        )

    def test_publication_year_is_persisted(self):
        book, file_path = self._make_klein_book("Klein, Naomi - A Summer of Wildfires and Hurricanes (2017).pdf")
        _extract_filename_metadata(book)

        self.assertTrue(
            BookMetadata.objects.filter(
                book=book,
                field_name="publication_year",
                field_value="2017",
                is_active=True,
            ).exists()
        )

    def test_reviewer_deactivated_title_stays_inactive_on_rescan(self):
        # A reviewer deactivated an embedded-PDF title that happens to equal
        # the filename-parsed title. A rescan must NOT reactivate it.
        book, file_path = self._make_klein_book("Klein, Naomi - A Summer of Wildfires and Hurricanes (2017).pdf")
        pdf_source, _ = DataSource.objects.get_or_create(name=DataSource.PDF_INTERNAL, defaults={"trust_level": 0.6})
        BookTitle.objects.create(
            book=book,
            title="A Summer of Wildfires and Hurricanes",
            source=pdf_source,
            confidence=0.6,
            is_active=False,
        )

        _extract_filename_metadata(book)

        self.assertFalse(
            BookTitle.objects.filter(
                book=book,
                title="A Summer of Wildfires and Hurricanes",
                source=pdf_source,
                is_active=True,
            ).exists()
        )

    def test_embedded_pdf_title_equal_to_stem_not_demoted(self):
        # An embedded-PDF title equal to the raw filename stem must stay active;
        # only the Initial Scan raw-filename seed may be demoted.
        book, file_path = self._make_klein_book("Klein, Naomi - A Summer of Wildfires and Hurricanes (2017).pdf")
        raw_stem = "Klein, Naomi - A Summer of Wildfires and Hurricanes (2017)"
        pdf_source, _ = DataSource.objects.get_or_create(name=DataSource.PDF_INTERNAL, defaults={"trust_level": 0.6})
        BookTitle.objects.create(
            book=book,
            title=raw_stem,
            source=pdf_source,
            confidence=0.6,
            is_active=True,
        )

        _extract_filename_metadata(book)

        self.assertTrue(BookTitle.objects.filter(book=book, title=raw_stem, source=pdf_source, is_active=True).exists())

    def test_year_row_updates_on_rescan(self):
        book, file_path = self._make_klein_book("Klein, Naomi - A Summer of Wildfires and Hurricanes (2017).pdf")
        _extract_filename_metadata(book)

        # The file is renamed with a different year; a rescan must update the
        # existing year row, not leave the stale one or create a second row.
        primary_file = book.primary_file
        primary_file.file_path = "/library/Klein, Naomi/Papers/Klein, Naomi - A Summer of Wildfires and Hurricanes (2020).pdf"
        primary_file.save()
        _extract_filename_metadata(book)

        rows = BookMetadata.objects.filter(book=book, field_name="publication_year", source=self.source)
        self.assertEqual(rows.count(), 1)
        self.assertEqual(rows.first().field_value, "2020")

    def test_final_metadata_publication_year_populated(self):
        book, file_path = self._make_klein_book("Klein, Naomi - A Summer of Wildfires and Hurricanes (2017).pdf")
        _extract_filename_metadata(book)

        resolve_final_metadata(book)

        final_metadata = FinalMetadata.objects.get(book=book)
        self.assertEqual(final_metadata.publication_year, 2017)


class FilenameParserRoutingTests(TestCase):
    """The comic/ebook parser choice follows content_type, not the extension."""

    def setUp(self):
        super().setUp()
        self.source, _ = DataSource.objects.get_or_create(name=DataSource.INITIAL_SCAN, defaults={"trust_level": 0.2})

    def test_comic_content_type_uses_comic_parser(self):
        book = Book.objects.create(content_type="comic")
        BookFile.objects.create(
            book=book,
            file_path="/library/Klein, Naomi/Some Comic.pdf",
            file_format="pdf",
        )
        with (
            patch(
                "books.scanner.parsing.parse_comic_metadata",
                return_value={"title": "Comic Title", "authors": [], "series": None},
            ) as comic_mock,
            patch("books.scanner.folder.parse_path_metadata") as path_mock,
        ):
            _extract_filename_metadata(book)
            comic_mock.assert_called_once()
            path_mock.assert_not_called()

    def test_ebook_content_type_uses_path_parser(self):
        book = Book.objects.create(content_type="ebook")
        BookFile.objects.create(
            book=book,
            file_path="/library/Klein, Naomi/Some Book.pdf",
            file_format="pdf",
        )
        with (
            patch(
                "books.scanner.folder.parse_path_metadata",
                return_value={"title": "Path Title", "authors": [], "series": None},
            ) as path_mock,
            patch("books.scanner.parsing.parse_comic_metadata") as comic_mock,
        ):
            _extract_filename_metadata(book)
            path_mock.assert_called_once()
            comic_mock.assert_not_called()
