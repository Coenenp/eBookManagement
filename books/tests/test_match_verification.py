"""
Tests for the M1 match verification gate (books/scanner/match_verification.py).

Covers the three verdict rules and the per-book unresolved-reason flag helpers.
"""

import os
import shutil
import tempfile

from django.test import TestCase

from books.models import Book, BookTitle, DataSource, FinalMetadata, ScanFolder, UnresolvedReason
from books.scanner.match_verification import (
    Verdict,
    _issues_match,
    combined_match_confidence,
    disambiguate_isbn,
    first_isbn,
    flag_unresolved,
    isbn_match,
    isbn_rank_from_source,
    mark_resolved,
    mark_unresolved,
    title_similarity,
    verify_comic,
    verify_title_author,
)
from books.scanner.match_verification import (
    ISBN_RANK_BACK,
    ISBN_RANK_DECLARED,
    ISBN_RANK_ELSEWHERE,
    ISBN_RANK_FRONT,
)

# Valid ISBN-13, a second (different) valid ISBN for mismatch tests, and a
# checksum-invalid ISBN that must fall through to title/author matching.
ISBN_A13 = "9780306406157"
ISBN_B13 = "9780132350884"
ISBN_C13 = "9780747532699"
INVALID_ISBN = "9780123456789"  # wrong check digit


class TitleAuthorVerdictTests(TestCase):
    def test_title_similarity(self):
        self.assertEqual(title_similarity("The Hobbit", "the hobbit"), 1.0)
        self.assertEqual(title_similarity("", "x"), 0.0)
        self.assertEqual(title_similarity(None, "x"), 0.0)

    def test_combined_confidence_title_author_weights(self):
        # title 1.0, author 0.0 -> 0.6
        self.assertAlmostEqual(combined_match_confidence("A", "X", "A", ["Y"]), 0.6, places=6)

    def test_verified_on_clean_title_and_author(self):
        v = verify_title_author("The Hobbit", "J.R.R. Tolkien", "The Hobbit", ["J.R.R. Tolkien"])
        self.assertIs(v, Verdict.VERIFIED)

    def test_rejected_on_clear_mismatch(self):
        v = verify_title_author("The Hobbit", "Tolkien", "Completely Different", ["Nobody"])
        self.assertIs(v, Verdict.REJECTED)

    def test_uncertain_on_title_match_but_author_mismatch(self):
        # title 1.0, author ~0 -> combined ~0.64, above reject floor but below accept
        v = verify_title_author("The Hobbit", "Tolkien", "The Hobbit", ["Someone Else"])
        self.assertIs(v, Verdict.UNCERTAIN)

    def test_isbn_exact_match_overrides_title_mismatch(self):
        # Valid query ISBN matches candidate ISBN -> VERIFIED even with wrong title/author
        v = verify_title_author(
            "Wrong Title", "Wrong Author", "Actual Title", ["Actual Author"],
            query_isbn=ISBN_A13, result_isbn=ISBN_A13,
        )
        self.assertIs(v, Verdict.VERIFIED)

    def test_isbn_mismatch_with_mismatched_title_author_rejects(self):
        # Different ISBNs AND clearly mismatched title/author -> reject. (Rule 5:
        # a different-format ISBN only counts when title+author also match.)
        v = verify_title_author(
            "The Hobbit", "Tolkien", "Completely Different", ["Nobody"],
            query_isbn=ISBN_A13, result_isbn=ISBN_B13,
        )
        self.assertIs(v, Verdict.REJECTED)

    def test_isbn_mismatch_with_matching_title_author_verifies(self):
        # Rule 5: a different-format ISBN of the same work counts (verifies)
        # when title+author match above threshold.
        v = verify_title_author(
            "The Hobbit", "J.R.R. Tolkien", "The Hobbit", ["J.R.R. Tolkien"],
            query_isbn=ISBN_A13, result_isbn=ISBN_B13,
        )
        self.assertIs(v, Verdict.VERIFIED)

    def test_same_title_different_author_different_isbn_uncertain(self):
        # Same title but a different author and a different valid ISBN: the
        # title agrees but the author and ISBN disagree, so identity is not
        # established. Not verified (author mismatch) and not hard-rejected
        # (title matches), so the verdict is UNCERTAIN.
        v = verify_title_author(
            "The Hobbit", "J.R.R. Tolkien", "The Hobbit", ["J.K. Rowling"],
            query_isbn=ISBN_A13, result_isbn=ISBN_B13,
        )
        self.assertIs(v, Verdict.UNCERTAIN)

    def test_invalid_query_isbn_falls_through_to_title_author(self):
        # Checksum-invalid ISBN is ignored; clean title+author still verifies.
        v = verify_title_author("The Hobbit", "Tolkien", "The Hobbit", ["Tolkien"], query_isbn=INVALID_ISBN)
        self.assertIs(v, Verdict.VERIFIED)


class ComicVerdictTests(TestCase):
    def test_series_and_issue_match_verifies(self):
        self.assertIs(verify_comic("Alix", "17", "Alix", "17"), Verdict.VERIFIED)

    def test_issue_mismatch_rejects(self):
        self.assertIs(verify_comic("Alix", "17", "Alix", "18"), Verdict.REJECTED)

    def test_series_mismatch_rejects(self):
        self.assertIs(verify_comic("Alix", "17", "Asterix", "17"), Verdict.REJECTED)

    def test_missing_issue_is_uncertain(self):
        self.assertIs(verify_comic("Alix", None, "Alix", "17"), Verdict.UNCERTAIN)

    def test_missing_issue_falls_back_to_series_and_title(self):
        # No issue number -> series + title similarity, both >= 0.90, verifies.
        v = verify_comic(
            "Alix", None, "Alix", "17",
            query_title="Le Fils de Spartacus", result_title="Le Fils de Spartacus",
        )
        self.assertIs(v, Verdict.VERIFIED)

    def test_missing_issue_weak_title_stays_uncertain(self):
        v = verify_comic("Alix", None, "Alix", "17", query_title="Wrong", result_title="Different")
        self.assertIs(v, Verdict.UNCERTAIN)

    def test_publisher_mismatch_demotes_to_uncertain(self):
        v = verify_comic("Alix", "17", "Alix", "17", query_publisher="Casterman", result_publisher="Marvel")
        self.assertIs(v, Verdict.UNCERTAIN)

    def test_publisher_match_verifies(self):
        v = verify_comic("Alix", "17", "Alix", "17", query_publisher="Casterman", result_publisher="Casterman")
        self.assertIs(v, Verdict.VERIFIED)

    def test_issues_match_tolerant(self):
        self.assertTrue(_issues_match("1", "1"))
        self.assertTrue(_issues_match("1", "01"))  # numeric equality
        self.assertFalse(_issues_match("1", "2"))
        self.assertTrue(_issues_match("1/2", "1/2"))  # exact string
        self.assertFalse(_issues_match(None, "1"))
        self.assertFalse(_issues_match("1", None))


class FirstIsbnTests(TestCase):
    def test_first_isbn_from_list(self):
        self.assertEqual(first_isbn([ISBN_A13, "junk"]), ISBN_A13)

    def test_first_isbn_from_string(self):
        self.assertEqual(first_isbn(ISBN_A13), ISBN_A13)

    def test_first_isbn_invalid(self):
        self.assertIsNone(first_isbn(None))
        self.assertIsNone(first_isbn("not an isbn"))

    def test_isbn_match(self):
        self.assertTrue(isbn_match(ISBN_A13, ISBN_A13))
        self.assertFalse(isbn_match(ISBN_A13, ISBN_B13))
        self.assertFalse(isbn_match(ISBN_A13, None))
        self.assertFalse(isbn_match(None, ISBN_A13))


class IsbnDisambiguationTests(TestCase):
    def test_tie_at_same_rank_returns_no_isbn_and_reason(self):
        # Two distinct declared ISBNs at the same (best) rank: do not guess.
        result = disambiguate_isbn([
            (ISBN_RANK_DECLARED, ISBN_A13),
            (ISBN_RANK_DECLARED, ISBN_B13),
        ])
        self.assertIsNone(result.isbn)
        self.assertEqual(result.reason, UnresolvedReason.AMBIGUOUS_ISBN)
        self.assertFalse(result.conflict)

    def test_invalid_checksum_is_not_a_candidate(self):
        # A checksum-invalid ISBN is dropped; with nothing valid left, no ISBN.
        result = disambiguate_isbn([(ISBN_RANK_DECLARED, INVALID_ISBN)])
        self.assertIsNone(result.isbn)
        self.assertEqual(result.reason, "")

    def test_invalid_checksum_ignored_alongside_valid(self):
        result = disambiguate_isbn([
            (ISBN_RANK_DECLARED, INVALID_ISBN),
            (ISBN_RANK_DECLARED, ISBN_A13),
        ])
        self.assertEqual(result.isbn, ISBN_A13)
        self.assertEqual(result.reason, "")

    def test_sole_back_matter_isbn_counts(self):
        # Back-matter ISBN is the sole candidate -> it counts.
        result = disambiguate_isbn([(ISBN_RANK_BACK, ISBN_A13)])
        self.assertEqual(result.isbn, ISBN_A13)
        self.assertEqual(result.reason, "")

    def test_back_matter_ignored_when_front_exists(self):
        # Front-matter beats back-matter: back only counts when sole.
        result = disambiguate_isbn([
            (ISBN_RANK_FRONT, ISBN_A13),
            (ISBN_RANK_BACK, ISBN_B13),
        ])
        self.assertEqual(result.isbn, ISBN_A13)
        self.assertEqual(result.reason, "")

    def test_list_of_isbns_for_other_books_ties(self):
        # A list of several distinct ISBNs elsewhere (likely other books) with
        # no declared/front ISBN: no single identifier -> flagged, not guessed.
        result = disambiguate_isbn([
            (ISBN_RANK_ELSEWHERE, ISBN_A13),
            (ISBN_RANK_ELSEWHERE, ISBN_B13),
            (ISBN_RANK_ELSEWHERE, ISBN_C13),
        ])
        self.assertIsNone(result.isbn)
        self.assertEqual(result.reason, UnresolvedReason.AMBIGUOUS_ISBN)

    def test_declared_wins_over_ocr_conflict_and_records_conflict(self):
        # Declared ISBN beats a differing OCR (elsewhere) ISBN, but the
        # disagreement is recorded.
        result = disambiguate_isbn([
            (ISBN_RANK_DECLARED, ISBN_A13),
            (ISBN_RANK_ELSEWHERE, ISBN_B13),
        ])
        self.assertEqual(result.isbn, ISBN_A13)
        self.assertEqual(result.reason, "")
        self.assertTrue(result.conflict)

    def test_declared_no_conflict_when_lower_rank_agrees(self):
        result = disambiguate_isbn([
            (ISBN_RANK_DECLARED, ISBN_A13),
            (ISBN_RANK_ELSEWHERE, ISBN_A13),
        ])
        self.assertEqual(result.isbn, ISBN_A13)
        self.assertFalse(result.conflict)

    def test_front_beats_elsewhere(self):
        result = disambiguate_isbn([
            (ISBN_RANK_ELSEWHERE, ISBN_B13),
            (ISBN_RANK_FRONT, ISBN_A13),
        ])
        self.assertEqual(result.isbn, ISBN_A13)
        self.assertEqual(result.reason, "")

    def test_unknown_rank_raises_value_error(self):
        # A rank outside the known set is a caller bug, not a candidate to
        # silently drop; surface it loudly.
        with self.assertRaises(ValueError):
            disambiguate_isbn([("title-page", ISBN_A13)])


class UnresolvedReasonFlagTests(TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.scan_folder = ScanFolder.objects.create(path=self.temp_dir, name="Match Verify Scan Folder")
        self.book = Book.objects.create(content_type="ebook", scan_folder=self.scan_folder)

    def tearDown(self):
        if hasattr(self, "temp_dir") and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_mark_unresolved_sets_reason(self):
        mark_unresolved(self.book, UnresolvedReason.UNCERTAIN)
        fm = FinalMetadata.objects.get(book=self.book)
        self.assertEqual(fm.unresolved_reason, UnresolvedReason.UNCERTAIN)

    def test_mark_resolved_clears_reason(self):
        mark_unresolved(self.book, UnresolvedReason.UNMAPPED_SERIES)
        mark_resolved(self.book)
        fm = FinalMetadata.objects.get(book=self.book)
        self.assertEqual(fm.unresolved_reason, "")

    def test_mark_unresolved_does_not_auto_sync_on_creation(self):
        # Give the book a title source: a real auto-sync would promote it into
        # final_title. auto_sync=False on the creation path must prevent that.
        source, _ = DataSource.objects.get_or_create(name="mv-test", defaults={"trust_level": 0.8})
        BookTitle.objects.create(book=self.book, title="Some Title", source=source, confidence=0.9, is_active=True)

        mark_unresolved(self.book, UnresolvedReason.UNCERTAIN)

        fm = FinalMetadata.objects.get(book=self.book)
        self.assertEqual(fm.unresolved_reason, UnresolvedReason.UNCERTAIN)
        self.assertEqual(fm.final_title, "")  # no sync happened

    def test_unresolved_reason_choices(self):
        # Guard: UNCERTAIN is a distinct, named choice (not lumped with the rest).
        self.assertEqual(UnresolvedReason.UNCERTAIN, "uncertain")
        self.assertIn(("uncertain", "Uncertain match"), UnresolvedReason.choices)

    def test_flag_unresolved_sets_reason_when_blank(self):
        flag_unresolved(self.book, UnresolvedReason.AMBIGUOUS_ISBN)
        fm = FinalMetadata.objects.get(book=self.book)
        self.assertEqual(fm.unresolved_reason, UnresolvedReason.AMBIGUOUS_ISBN)

    def test_flag_unresolved_first_reason_wins(self):
        # A flag never overwrites an existing non-empty unresolved_reason.
        mark_unresolved(self.book, UnresolvedReason.NO_MATCH)
        flag_unresolved(self.book, UnresolvedReason.AMBIGUOUS_ISBN)
        fm = FinalMetadata.objects.get(book=self.book)
        self.assertEqual(fm.unresolved_reason, UnresolvedReason.NO_MATCH)


class IsbnRankFromSourceTests(TestCase):
    """isbn_rank_from_source maps local sources to ranks; external -> None."""

    def test_embedded_sources_are_declared(self):
        self.assertEqual(isbn_rank_from_source(DataSource.EPUB_INTERNAL), ISBN_RANK_DECLARED)
        self.assertEqual(isbn_rank_from_source(DataSource.OPF_FILE), ISBN_RANK_DECLARED)

    def test_legacy_content_scan_is_elsewhere(self):
        self.assertEqual(isbn_rank_from_source(DataSource.CONTENT_SCAN), ISBN_RANK_ELSEWHERE)

    def test_external_sources_are_not_local_candidates(self):
        for name in (DataSource.OPEN_LIBRARY, DataSource.GOOGLE_BOOKS, DataSource.COMICVINE):
            self.assertIsNone(isbn_rank_from_source(name))

    def test_unknown_source_is_not_a_candidate(self):
        self.assertIsNone(isbn_rank_from_source("some-unknown-source"))
