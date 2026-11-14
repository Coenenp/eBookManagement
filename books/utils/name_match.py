"""Name agreement: does the stored title/author share a word with the file path?

The external lookup can return a wrong title and author with a high confidence
(see the 2026-11-14 measurement in ``/workspace/state/name_match_20261114.txt``).
``name_agrees`` is a cheap, deterministic guard: it accepts a book only when at
least one significant word of the title or the author also appears in the last
two components of the primary file path (the containing folder and the file
name). Accents are folded away so ``Kök`` and ``Kok`` are the same token.
"""

import re
import unicodedata

# Words that carry no identifying signal and are ignored on both sides.
STOP_TOKENS = frozenset(
    [
        "the", "and", "for", "with", "from", "van", "der", "het", "een",
        "von", "des", "les", "une", "epub", "mobi", "pdf", "azw3",
        "unknown", "book", "novel", "retail", "copy",
    ]
)

_TOKEN_RE = re.compile(r"[a-z0-9]{3,}")
_PATH_SPLIT_RE = re.compile(r"[\\/]+")


def name_tokens(text):
    """Fold accents/case and return significant tokens (len >= 3, no stop words)."""
    if not text:
        return []
    folded = unicodedata.normalize("NFKD", text or "")
    folded = "".join(ch for ch in folded if not unicodedata.combining(ch))
    folded = folded.casefold()
    return [tok for tok in _TOKEN_RE.findall(folded) if tok not in STOP_TOKENS]


def _last_two_components(path):
    """The containing folder and the file name (all but nothing when short)."""
    parts = [p for p in _PATH_SPLIT_RE.split(path or "") if p]
    return parts[-2:]


def name_agrees(title, author, source_path):
    """True when a title or author token appears in the last two path components.

    Returns False when neither title nor author yields a single token.
    """
    title_tokens = name_tokens(title)
    author_tokens = name_tokens(author)
    if not title_tokens and not author_tokens:
        return False
    path_tokens = set(name_tokens(" ".join(_last_two_components(source_path))))
    return any(t in path_tokens for t in title_tokens) or any(
        t in path_tokens for t in author_tokens
    )
