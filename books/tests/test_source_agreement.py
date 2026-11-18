"""Tests for source-agreement voting in final metadata (Part B)."""

from django.test import TestCase

from books.models import Author, Book, BookAuthor, BookTitle, DataSource, FinalMetadata
from books.utils.source_agreement import pick_by_support


class PickBySupportUnitTests(TestCase):
    """Unit tests for pick_by_support, one per tie-break rule."""

    def test_empty_returns_none(self):
        self.assertIsNone(pick_by_support([], "title"))
        self.assertIsNone(pick_by_support([], "author"))

    def test_single_candidate_returns_its_value(self):
        self.assertEqual(
            pick_by_support([("The Vegetarian", 0.8, "EPUB")], "title"),
            "The Vegetarian",
        )

    def test_title_containment_wins(self):
        candidates = [
            ("The Vegetarian", 0.8, "EPUB"),
            ("The Vegetarian: A Novel", 0.665, "Google Books"),
        ]
        self.assertEqual(pick_by_support(candidates, "title"), "The Vegetarian")

    def test_author_token_set_wins(self):
        candidates = [
            ("Victoria Clayton", 0.2, "Initial Scan"),
            ("Victoria Clayton", 0.8, "EPUB"),
            ("Victoria Clayton", 0.665, "Google Books"),
            ("V. CLAYTON", 0.833, "Open Library"),
        ]
        self.assertEqual(pick_by_support(candidates, "author"), "Victoria Clayton")

    def test_same_source_never_supports(self):
        candidates = [
            ("Samen met jou", 0.8, "EPUB"),
            ("Samen met jou", 0.2, "EPUB"),
            ("SAMEN MET JOU", 0.833, "Open Library"),
        ]
        self.assertEqual(pick_by_support(candidates, "title"), "SAMEN MET JOU")

    def test_same_string_count_tiebreak(self):
        candidates = [
            ("Han Kang", 0.5, "A"),
            ("Han Kang", 0.4, "B"),
            ("Kang Han", 0.9, "C"),
        ]
        self.assertEqual(pick_by_support(candidates, "author"), "Han Kang")

    def test_confidence_tiebreak_when_no_shared_tokens(self):
        candidates = [
            ("Foo Bar", 0.6, "A"),
            ("Baz Qux", 0.9, "B"),
        ]
        self.assertEqual(pick_by_support(candidates, "title"), "Baz Qux")

    def test_never_returns_non_candidate(self):
        candidates = [
            ("Dragon Moon", 0.8, "EPUB"),
            ("Dragonkeeper 3: Dragon Moon", 0.665, "Google Books"),
            ("Carole Wilkinson", 0.2, "Initial Scan"),
        ]
        result = pick_by_support(candidates, "title")
        self.assertIn(result, {v for v, _, _ in candidates})

    def test_initial_scan_cannot_win_with_other_sources(self):
        candidates = [
            ("Dune Messiah", 0.8, "EPUB"),
            ("Dune Messiah", 0.665, "Google Books"),
            ("Dune", 0.2, "Initial Scan"),
        ]
        self.assertEqual(pick_by_support(candidates, "title"), "Dune Messiah")

    def test_initial_scan_only_returns_it(self):
        self.assertEqual(pick_by_support([("Dune", 0.2, "Initial Scan")], "title"), "Dune")

    def test_exact_tie_returns_first_listed(self):
        candidates = [("Foo", 0.5, "A"), ("Bar", 0.5, "B")]
        self.assertEqual(pick_by_support(candidates, "title"), "Foo")

    def test_leading_article_not_containment(self):
        # Book 14: "Een Verborgen leven" must not lose to "Verborgen leven":
        # a leading article is neither a series prefix nor an edition suffix.
        candidates = [
            ("Een Verborgen leven", 0.8, "EPUB"),
            ("Verborgen leven", 0.665, "Google Books"),
        ]
        self.assertEqual(pick_by_support(candidates, "title"), "Een Verborgen leven")

    def test_series_prefix_shorter_wins(self):
        # A longer title that is the shorter one plus a series prefix still
        # supports the shorter one.
        candidates = [
            ("Merlijn Trilogie 03 - De Laatste Betovering", 0.8, "EPUB"),
            ("De laatste betovering", 0.7, "Google Books"),
        ]
        self.assertEqual(pick_by_support(candidates, "title"), "De laatste betovering")

    def test_initial_scan_not_a_same_string_vote(self):
        # Book 285: the official "L.J. Smith" must not lose to "L J Smith"
        # because an Initial Scan file-name value counts as a same-string vote.
        candidates = [
            ("L.J. Smith", 0.9, "OPF File"),
            ("L J Smith", 0.8, "EPUB"),
            ("L J Smith", 0.2, "Initial Scan"),
        ]
        self.assertEqual(pick_by_support(candidates, "author"), "L.J. Smith")

    def test_embedded_group_rows_never_support_each_other(self):
        # EPUB and OPF File are one "embedded" group, so two rows with the same
        # string count as a single vote and cannot support each other.
        candidates = [
            ("Foo", 0.6, "EPUB"),
            ("Foo", 0.6, "OPF File"),
            ("Bar", 0.9, "Google Books"),
        ]
        self.assertEqual(pick_by_support(candidates, "title"), "Bar")

    def test_nfc_and_nfd_count_as_same_string(self):
        import unicodedata

        nfc = "Björn Hellberg"
        nfd = unicodedata.normalize("NFD", nfc)
        candidates = [
            (nfc, 0.4, "EPUB"),
            (nfd, 0.5, "Google Books"),
            ("Unrelated Title", 0.99, "Open Library"),
        ]
        self.assertIn(pick_by_support(candidates, "title"), (nfc, nfd))


class SourceAgreementIntegrationTests(TestCase):
    """End-to-end tests of the vote through update_final_title/author."""

    def _source(self, name):
        return DataSource.objects.get_or_create(
            name=name, defaults={"priority": 1, "trust_level": 5}
        )[0]

    def _book(self):
        return Book.objects.create()

    def test_book_148_titles(self):
        book = self._book()
        scan = self._source(DataSource.INITIAL_SCAN)
        epub = self._source(DataSource.EPUB_INTERNAL)
        gb = self._source(DataSource.GOOGLE_BOOKS)
        ol = self._source(DataSource.OPEN_LIBRARY)

        BookTitle.objects.create(book=book, title="Samen met jou", source=scan, confidence=0.2)
        BookTitle.objects.create(book=book, title="Samen met jou", source=epub, confidence=0.8)
        BookTitle.objects.create(book=book, title="Samen met jou", source=gb, confidence=0.665)
        BookTitle.objects.create(book=book, title="SAMEN MET JOU", source=ol, confidence=0.833)

        final = FinalMetadata.objects.create(book=book)
        final.update_final_title()
        self.assertEqual(final.final_title, "Samen met jou")
        self.assertEqual(final.final_title_confidence, 0.8)

    def test_book_148_authors(self):
        book = self._book()
        scan = self._source(DataSource.INITIAL_SCAN)
        epub = self._source(DataSource.EPUB_INTERNAL)
        gb = self._source(DataSource.GOOGLE_BOOKS)
        ol = self._source(DataSource.OPEN_LIBRARY)

        a1 = Author.objects.create(name="Victoria Clayton")
        a2 = Author.objects.create(name="V. CLAYTON")
        BookAuthor.objects.create(book=book, author=a1, source=scan, confidence=0.2)
        BookAuthor.objects.create(book=book, author=a1, source=epub, confidence=0.8)
        BookAuthor.objects.create(book=book, author=a1, source=gb, confidence=0.665)
        BookAuthor.objects.create(book=book, author=a2, source=ol, confidence=0.833)

        final = FinalMetadata.objects.create(book=book)
        final.update_final_author()
        self.assertEqual(final.final_author, "Victoria Clayton")

    def test_book_150_titles(self):
        book = self._book()
        epub = self._source(DataSource.EPUB_INTERNAL)
        gb = self._source(DataSource.GOOGLE_BOOKS)
        scan = self._source(DataSource.INITIAL_SCAN)

        BookTitle.objects.create(book=book, title="Vlammen / druk 1", source=epub, confidence=0.8)
        BookTitle.objects.create(book=book, title="Vlammen", source=gb, confidence=0.665)
        BookTitle.objects.create(book=book, title="Hongerspelen 2 - Vlammen", source=scan, confidence=0.2)

        final = FinalMetadata.objects.create(book=book)
        final.update_final_title()
        self.assertEqual(final.final_title, "Vlammen")
        self.assertEqual(final.final_title_confidence, 0.665)

    def test_book_150_authors(self):
        book = self._book()
        epub = self._source(DataSource.EPUB_INTERNAL)
        gb = self._source(DataSource.GOOGLE_BOOKS)
        scan = self._source(DataSource.INITIAL_SCAN)

        a1 = Author.objects.create(name="Collins, S.")
        a2 = Author.objects.create(name="Suzanne Collins")
        BookAuthor.objects.create(book=book, author=a1, source=epub, confidence=0.8)
        BookAuthor.objects.create(book=book, author=a2, source=gb, confidence=0.665)
        BookAuthor.objects.create(book=book, author=a2, source=scan, confidence=0.2)

        final = FinalMetadata.objects.create(book=book)
        final.update_final_author()
        self.assertEqual(final.final_author, "Suzanne Collins")

    def test_book_688_title(self):
        book = self._book()
        epub = self._source(DataSource.EPUB_INTERNAL)
        gb = self._source(DataSource.GOOGLE_BOOKS)
        scan = self._source(DataSource.INITIAL_SCAN)

        BookTitle.objects.create(book=book, title="Dragon Moon", source=epub, confidence=0.8)
        BookTitle.objects.create(book=book, title="Dragonkeeper 3: Dragon Moon", source=gb, confidence=0.665)
        BookTitle.objects.create(book=book, title="Carole Wilkinson", source=scan, confidence=0.2)

        final = FinalMetadata.objects.create(book=book)
        final.update_final_title()
        self.assertEqual(final.final_title, "Dragon Moon")

    def test_vegetarian_title(self):
        book = self._book()
        epub = self._source(DataSource.EPUB_INTERNAL)
        gb = self._source(DataSource.GOOGLE_BOOKS)

        BookTitle.objects.create(book=book, title="The Vegetarian", source=epub, confidence=0.8)
        BookTitle.objects.create(book=book, title="The Vegetarian: A Novel", source=gb, confidence=0.7)

        final = FinalMetadata.objects.create(book=book)
        final.update_final_title()
        self.assertEqual(final.final_title, "The Vegetarian")

    def test_dune_messiah_not_dune(self):
        book = self._book()
        epub = self._source(DataSource.EPUB_INTERNAL)
        gb = self._source(DataSource.GOOGLE_BOOKS)
        scan = self._source(DataSource.INITIAL_SCAN)

        BookTitle.objects.create(book=book, title="Dune Messiah", source=epub, confidence=0.8)
        BookTitle.objects.create(book=book, title="Dune Messiah", source=gb, confidence=0.665)
        BookTitle.objects.create(book=book, title="Dune", source=scan, confidence=0.2)

        final = FinalMetadata.objects.create(book=book)
        final.update_final_title()
        self.assertEqual(final.final_title, "Dune Messiah")

    def test_monaldi_main_before_secondary(self):
        book = self._book()
        epub = self._source(DataSource.EPUB_INTERNAL)

        sorti = Author.objects.create(name="Sorti")
        monaldi = Author.objects.create(name="Monaldi")
        BookAuthor.objects.create(book=book, author=sorti, source=epub, confidence=0.8, is_main_author=False)
        BookAuthor.objects.create(book=book, author=monaldi, source=epub, confidence=0.8, is_main_author=True)

        final = FinalMetadata.objects.create(book=book)
        final.update_final_author()
        self.assertEqual(final.final_author, "Monaldi")
