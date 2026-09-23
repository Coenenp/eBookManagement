"""Match verification: reject non-matching external candidates before merge.

M1 correctness gate. Verifies a candidate's identity against the query
before it is persisted as source-attributed metadata, so an unverified
wrong match from a high-trust source cannot override correct embedded data.

Verdicts (TASK.md section 6):

- VERIFIED   -> persist as source-attributed metadata.
- REJECTED   -> discard; do not persist.
- UNCERTAIN  -> hold for review; do not auto-merge.

The thresholds below are starting points, to be calibrated on the gold set
in a later milestone (M4).
"""

from difflib import SequenceMatcher
from enum import Enum

from books.utils.isbn import normalize_isbn


class Verdict(Enum):
    VERIFIED = "verified"
    REJECTED = "rejected"
    UNCERTAIN = "uncertain"


# Rule 1 — title/author similarity (ebooks/audiobooks)
TITLE_ACCEPT = 0.85
TITLE_REJECT = 0.55
COMBINED_ACCEPT = 0.85
COMBINED_REJECT = 0.60

# Rule 3 — comic series + issue + publisher
SERIES_ACCEPT = 0.85
PUBLISHER_ACCEPT = 0.85
SERIES_TITLE_FALLBACK = 0.90


def title_similarity(a, b):
    """Case-insensitive SequenceMatcher ratio; 0.0 if either side is empty."""
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a.strip().lower(), b.strip().lower()).ratio()


def combined_match_confidence(query_title, query_author, result_title, result_authors):
    """Title 60% / author 40%, matching external._calculate_match_confidence."""
    title_score = title_similarity(query_title, result_title)
    author_score = 0.0
    if query_author and result_authors:
        author_score = max(title_similarity(query_author, a) for a in result_authors if a)

    if query_title and query_author:
        return 0.6 * title_score + 0.4 * author_score
    if query_title:
        return title_score
    if query_author:
        return author_score
    return 0.0


def first_isbn(value):
    """Return the first checksum-valid normalized ISBN from a string or list."""
    if not value:
        return None
    if isinstance(value, (list, tuple)):
        for v in value:
            n = normalize_isbn(v)
            if n:
                return n
        return None
    return normalize_isbn(value)


def isbn_match(query_isbn, result_isbn):
    """True if both sides carry the same checksum-valid ISBN."""
    q = first_isbn(query_isbn)
    if not q:
        return False
    return first_isbn(result_isbn) == q


def verify_title_author(query_title, query_author, result_title, result_authors, query_isbn=None, result_isbn=None):
    """Rules 1 + 2: verdict for an ebook/audiobook candidate (OL/GB/Goodreads).

    query_isbn/result_isbn may be raw strings or lists of candidate ISBNs;
    ``first_isbn`` normalizes and checksum-validates, so a non-None query
    ISBN is a verified strong identifier.
    """
    # Rule 2 — ISBN strong identifier.
    if query_isbn:
        q = first_isbn(query_isbn)
        if q:
            r = first_isbn(result_isbn)
            if r == q:
                return Verdict.VERIFIED
            if r:
                return Verdict.REJECTED
            # Candidate carries no ISBN: fall through to title/author.

    # Rule 1 — title/author similarity.
    title_score = title_similarity(query_title, result_title)
    combined = combined_match_confidence(query_title, query_author, result_title, result_authors)

    if title_score >= TITLE_ACCEPT and combined >= COMBINED_ACCEPT:
        return Verdict.VERIFIED
    if title_score < TITLE_REJECT or combined < COMBINED_REJECT:
        return Verdict.REJECTED
    return Verdict.UNCERTAIN


def _issues_match(a, b):
    """Tolerant issue-number equality: exact string, else numeric equality."""
    sa = str(a).strip() if a is not None else ""
    sb = str(b).strip() if b is not None else ""
    if not sa or not sb:
        return False
    if sa == sb:
        return True
    try:
        return float(sa) == float(sb)
    except ValueError:
        return False


def verify_comic(query_series, query_issue, result_series, result_issue, query_publisher=None, result_publisher=None, query_title=None, result_title=None):
    """Rule 3: verdict for a comic candidate (series + issue + publisher).

    Issue number is the comic's strong identifier (the ISBN equivalent); a
    publisher mismatch demotes to UNCERTAIN (reprints/reissues exist) rather
    than rejecting. When no issue number is known, fall back to series + title
    similarity (both >= SERIES_TITLE_FALLBACK) instead of auto-verifying.
    """
    series_score = title_similarity(query_series, result_series)
    if series_score < SERIES_ACCEPT:
        return Verdict.REJECTED

    if query_issue is not None and result_issue is not None:
        if not _issues_match(query_issue, result_issue):
            return Verdict.REJECTED
        if query_publisher and result_publisher:
            if title_similarity(query_publisher, result_publisher) >= PUBLISHER_ACCEPT:
                return Verdict.VERIFIED
            return Verdict.UNCERTAIN
        return Verdict.VERIFIED

    # No issue number to pin identity: fall back to series + title similarity.
    title_score = title_similarity(query_title, result_title)
    if series_score >= SERIES_TITLE_FALLBACK and title_score >= SERIES_TITLE_FALLBACK:
        return Verdict.VERIFIED
    return Verdict.UNCERTAIN


def mark_resolved(book):
    """Clear any unresolved flag: a verified match resolved this book."""
    _set_unresolved_reason(book, "")


def mark_unresolved(book, reason):
    """Record the unresolved reason on the book's FinalMetadata."""
    _set_unresolved_reason(book, reason)


def _set_unresolved_reason(book, reason):
    from books.models import FinalMetadata

    fm = FinalMetadata.objects.filter(book=book).first()
    if fm is None:
        fm = FinalMetadata(book=book)
        fm.save(auto_sync=False)
    fm.unresolved_reason = reason
    fm.save(update_fields=["unresolved_reason"])
