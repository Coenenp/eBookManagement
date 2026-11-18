"""Source-agreement voting for final metadata.

Part B: pick_by_support chooses the best source value by how much the other
sources agree with it, rather than by a single highest-confidence value.

A candidate is a ``(value, confidence, source)`` tuple. The vote never edits a
value; it only selects one of the already-present source values.
"""

import re
import unicodedata

# Matches DataSource.INITIAL_SCAN in books.models, kept as a literal here so
# this module does not import books.models (books.models_metadata imports us).
INITIAL_SCAN_SOURCE = "Initial Scan"

# EPUB and OPF File read the same embedded file, so they vote as one group.
EMBEDDED_SOURCE_NAMES = {"EPUB", "OPF File"}
EMBEDDED_GROUP = "embedded"


def _norm(value):
    """Normalize a value for key comparison: NFC, casefold, collapse spaces."""
    value = unicodedata.normalize("NFC", value)
    value = value.casefold()
    return re.sub(r"\s+", " ", value).strip()


def _nfc(value):
    """Normalize a value to NFC for exact same-string comparison."""
    return unicodedata.normalize("NFC", value)


def _tokens(norm):
    """Word token tuple of an already-normalized value."""
    return tuple(re.findall(r"\w+", norm))


def _key(value, mode):
    """Return the comparison key of a value.

    For ``title`` the key is the ordered tuple of word tokens; for ``author``
    the key is the sorted tuple of tokens, so word order does not matter when
    matching the same author.
    """
    tokens = _tokens(_norm(value))
    if mode == "author":
        tokens = tuple(sorted(tokens))
    return tokens


def _group(source):
    """Return the voting group of a source; EPUB and OPF File share one."""
    name = getattr(source, "name", source)
    return EMBEDDED_GROUP if name in EMBEDDED_SOURCE_NAMES else name


def _title_support(c_norm, t_norm):
    """True if ``t_norm`` supports ``c_norm`` under the title rule.

    ``c_norm`` is supported when the word token tuples are equal, or when
    ``t_norm`` is ``c_norm`` plus a series prefix (before) or an edition
    suffix (after) at a recognised boundary. Containment anywhere else does
    not count. Both arguments are already NFC/casefolded, whitespace-collapsed.
    """
    if not c_norm:
        return False
    if _tokens(c_norm) == _tokens(t_norm):
        return True
    if t_norm.startswith(c_norm) and len(t_norm) > len(c_norm):
        after = t_norm[len(c_norm):]
        if not after[0].isalnum():
            after = after.lstrip(" ")
            if after.startswith((":", "/", "(", "[", "- ")):
                return True
    if t_norm.endswith(c_norm) and len(t_norm) > len(c_norm):
        before = t_norm[: len(t_norm) - len(c_norm)].rstrip(" ")
        if before.endswith(":"):
            return True
        if before.endswith("-") and len(before) >= 2 and before[-2] == " ":
            return True
    return False


def pick_by_support(candidates, mode):
    """Return the winning value, or None for an empty candidate list.

    Support of a candidate is the number of *other* groups whose value equals
    its key (``author``) or supports it under the title rule. Values from the
    same group never support each other. Initial Scan still supports other
    candidates but contributes nothing to the same-string count.

    The winner is the candidate with, in order: the highest support, the
    highest number of groups with exactly the same string (NFC form), and the
    highest confidence. An exact tie is won by the candidate listed first. A
    candidate whose source is Initial Scan cannot win while at least one
    candidate from another source exists; when every candidate is Initial Scan
    the rule above applies unchanged.
    """
    if not candidates:
        return None

    norm_values = [_norm(value) for value, _, _ in candidates]
    nfc_values = [_nfc(value) for value, _, _ in candidates]
    keys = [_key(value, mode) for value, _, _ in candidates]
    groups = [_group(source) for _, _, source in candidates]
    is_initial_scan = [
        getattr(source, "name", source) == INITIAL_SCAN_SOURCE
        for _, _, source in candidates
    ]
    has_non_initial_scan = any(not x for x in is_initial_scan)

    def support(i):
        ki = keys[i]
        gi = groups[i]
        supporting = set()
        for j in range(len(candidates)):
            if j == i or groups[j] == gi or groups[j] in supporting:
                continue
            if mode == "author":
                if keys[j] == ki:
                    supporting.add(groups[j])
            elif _title_support(norm_values[i], norm_values[j]):
                supporting.add(groups[j])
        return len(supporting)

    def same_string(i):
        vi = nfc_values[i]
        seen = set()
        for j in range(len(candidates)):
            if is_initial_scan[j]:
                continue
            if nfc_values[j] == vi:
                seen.add(groups[j])
        return len(seen)

    best_index = None
    best_score = None
    for i in range(len(candidates)):
        if has_non_initial_scan and is_initial_scan[i]:
            continue
        score = (support(i), same_string(i), candidates[i][1])
        if best_score is None or score > best_score:
            best_score = score
            best_index = i

    return candidates[best_index][0] if best_index is not None else None
