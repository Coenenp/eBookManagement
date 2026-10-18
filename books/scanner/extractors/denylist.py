"""Denylist for embedded PDF/EPUB metadata values.

Some PDF and EPUB files carry placeholder or non-metadata values in their
embedded title/author fields (a generic account name, a literal "untitled", a
Dutch "fax print of full page", or a filename built from an ISBN). These values
must never become a book's title or author.

The literal values are kept as an explicit data table (a frozenset of exact
strings), not a regex pattern, so each entry is auditable and trivially
extended. ISBN-named files are recognised by validating the leading token as an
ISBN rather than by enumerating them.
"""

import re

from books.utils.isbn import normalize_isbn

# Exact (case-insensitive) embedded-metadata values that are never a title or
# author.
EMBEDDED_METADATA_DENYLIST = frozenset(
    {
        "administrator",
        "untitled",
        "faxafdruk op volledige pagina",
    }
)

# An ISBN-named file separates its leading ISBN from the rest with an
# underscore or whitespace. Hyphens are NOT separators here — a hyphenated
# ISBN such as "978-90-313-8000-8" contains its own dashes.
_FILENAME_TOKEN_SPLIT = re.compile(r"[_\s]")


def is_isbn_named_file(value: str) -> bool:
    """True when a value is a filename built from an ISBN, e.g. a title of
    ``978-90-313-8000-8_BookFrontmatter_OnlinePDF.pdf``."""
    value = (value or "").strip()
    if not value:
        return False
    leading_token = _FILENAME_TOKEN_SPLIT.split(value, 1)[0]
    return normalize_isbn(leading_token) is not None


def is_denylisted(value: str) -> bool:
    """True when an embedded title/author value should be ignored."""
    value = (value or "").strip()
    if not value:
        # Empty values are dropped by callers anyway; treat as denylisted so a
        # single predicate covers every "skip this" case.
        return True
    if value.lower() in EMBEDDED_METADATA_DENYLIST:
        return True
    return is_isbn_named_file(value)
