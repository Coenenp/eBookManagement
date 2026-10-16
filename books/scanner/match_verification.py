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
from typing import NamedTuple, Optional

from books.utils.isbn import normalize_isbn


class Verdict(Enum):
    VERIFIED = "verified"
    REJECTED = "rejected"
    UNCERTAIN = "uncertain"


# ISBN source ranks for disambiguation (TASK.md item 4), highest priority first.
ISBN_RANK_DECLARED = "declared"    # declared in the file's own metadata
ISBN_RANK_FRONT = "front"          # front matter near the title
ISBN_RANK_ELSEWHERE = "elsewhere"  # anywhere else in the text
ISBN_RANK_BACK = "back"            # back matter; only when the sole candidate

# Priority order of the non-back-matter ranks.
_ISBN_RANK_PRIORITY = (ISBN_RANK_DECLARED, ISBN_RANK_FRONT, ISBN_RANK_ELSEWHERE)

# Every rank a caller may tag a candidate with; anything else is a bug.
_ISBN_RANK_VALID = (ISBN_RANK_DECLARED, ISBN_RANK_FRONT, ISBN_RANK_ELSEWHERE, ISBN_RANK_BACK)


def isbn_rank_from_source(source_name):
    """Map a DataSource name to a local ISBN candidate rank (or None).

    Only the file's own ISBN evidence is a local candidate:

    - EPUB/OPF embedded metadata is the file's declared ISBN -> DECLARED.
    - A legacy ``CONTENT_SCAN`` row carries no front/back location, so it is
      treated as ELSEWHERE: several of them tie, which ``disambiguate_isbn``
      turns into AMBIGUOUS_ISBN rather than a guess, until a rescan retags
      them front/back.
    - External query results (Open Library, Google Books, ComicVine, ...) and
      anything unknown return None — they are never fed to disambiguate_isbn.
    """
    from books.models import DataSource

    if source_name in (DataSource.EPUB_INTERNAL, DataSource.OPF_FILE):
        return ISBN_RANK_DECLARED
    if source_name == DataSource.CONTENT_SCAN:
        return ISBN_RANK_ELSEWHERE
    return None


class IsbnDisambiguation(NamedTuple):
    """Outcome of disambiguating a book's local ISBN candidates."""

    isbn: Optional[str]  # chosen normalized ISBN-13, or None if ambiguous/none
    reason: str          # "" if resolved, else an UnresolvedReason value
    conflict: bool       # True if a declared ISBN disagreed with a lower-rank ISBN


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


def disambiguate_isbn(candidates):
    """Choose the single ISBN identifying this book from local candidates.

    ``candidates`` is an iterable of ``(rank, raw_isbn)`` tuples where ``rank``
    is one of ``ISBN_RANK_DECLARED`` / ``ISBN_RANK_FRONT`` / ``ISBN_RANK_ELSEWHERE``
    / ``ISBN_RANK_BACK``.

    Rules (TASK.md item 4), implemented exactly:

    - Only checksum-valid ISBNs are candidates; the rest are dropped.
    - Rank by source: declared > front > elsewhere. A back-matter ISBN counts
      only when it is the sole candidate.
    - Disambiguation is local-only (no external call).
    - Several distinct candidates at the same (best) rank: return no ISBN plus
      a reason code so the book is flagged. Never guess.

    Raises ``ValueError`` if any candidate carries a rank outside
    ``ISBN_RANK_DECLARED`` / ``ISBN_RANK_FRONT`` / ``ISBN_RANK_ELSEWHERE`` /
    ``ISBN_RANK_BACK``.

    Returns an ``IsbnDisambiguation``. A declared ISBN that disagrees with a
    lower-rank candidate still wins, but the disagreement is recorded via the
    ``conflict`` flag.
    """
    from books.models import UnresolvedReason

    # 1. Keep only checksum-valid, normalized ISBNs, grouped by rank (dedup).
    ranked = {}
    for rank, raw in candidates:
        if rank not in _ISBN_RANK_VALID:
            raise ValueError(f"Unknown ISBN rank: {rank!r}")
        n = normalize_isbn(raw)
        if n is None:
            continue
        ranked.setdefault(rank, set()).add(n)

    # 2. Back matter only counts when it is the sole candidate.
    non_back = {}
    for rank in _ISBN_RANK_PRIORITY:
        non_back[rank] = ranked.get(rank, set())
    has_non_back = any(non_back.values())
    back = ranked.get(ISBN_RANK_BACK, set()) if not has_non_back else set()

    # 3. Choose the highest-priority rank that has candidates.
    for rank in _ISBN_RANK_PRIORITY:
        vals = non_back[rank]
        if not vals:
            continue
        if len(vals) == 1:
            return _disambiguate_result(next(iter(vals)), rank, ranked)
        # Several distinct ISBNs at the same rank: do not guess.
        return IsbnDisambiguation(None, UnresolvedReason.AMBIGUOUS_ISBN, False)

    # 4. No front/elsewhere/declared candidates: back matter is the sole source.
    if back:
        if len(back) == 1:
            return IsbnDisambiguation(next(iter(back)), "", False)
        return IsbnDisambiguation(None, UnresolvedReason.AMBIGUOUS_ISBN, False)

    return IsbnDisambiguation(None, "", False)


def _disambiguate_result(chosen, rank, ranked):
    """Wrap a single-candidate win, recording any declared-vs-lower conflict."""
    conflict = False
    if rank == ISBN_RANK_DECLARED:
        lower = set()
        for r in _ISBN_RANK_PRIORITY[1:]:
            lower |= ranked.get(r, set())
        conflict = any(v != chosen for v in lower)
    return IsbnDisambiguation(chosen, "", conflict)


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
            # If r is a differing valid ISBN (a different format of the same
            # work) or absent, fall through to title/author matching: rule 5
            # lets a different-format ISBN verify only when title+author also
            # match above threshold, which the Rule 1 block below enforces.

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


def flag_unresolved(book, reason):
    """Record a review flag unless a reason is already set (first reason wins).

    Unlike ``mark_unresolved`` (which records the latest match-verification
    verdict), this never overwrites an existing non-empty ``unresolved_reason``:
    the first flag wins, so an earlier signal is preserved. Used by
    language-detection flags and ISBN-disambiguation ambiguity.
    """
    from books.models import FinalMetadata

    fm = FinalMetadata.objects.filter(book=book).first()
    if fm is not None and fm.unresolved_reason:
        return
    _set_unresolved_reason(book, reason)


def _set_unresolved_reason(book, reason):
    from books.models import FinalMetadata

    fm = FinalMetadata.objects.filter(book=book).first()
    if fm is None:
        fm = FinalMetadata(book=book)
        fm.save(auto_sync=False)
    fm.unresolved_reason = reason
    fm.save(update_fields=["unresolved_reason"])
