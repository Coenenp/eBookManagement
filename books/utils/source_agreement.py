"""Source-agreement voting for final metadata.

Part B: pick_by_support chooses the best source value by how much the other
sources agree with it, rather than by a single highest-confidence value.

A candidate is a ``(value, confidence, source)`` tuple. The vote never edits a
value; it only selects one of the already-present source values.
"""

import re


def _key(value, mode):
    """Return the comparison key of a value.

    For ``title`` the key is the ordered tuple of word tokens (so one title
    being contained in another can be detected as a contiguous run). For
    ``author`` the key is the sorted tuple of tokens, so word order does not
    matter when matching the same author.
    """
    tokens = tuple(re.findall(r"\w+", value.casefold()))
    if mode == "author":
        tokens = tuple(sorted(tokens))
    return tokens


def _contains_run(haystack, needle):
    """True if ``needle`` occurs as a contiguous run of tokens in ``haystack``."""
    n = len(needle)
    if n == 0:
        return False
    for i in range(len(haystack) - n + 1):
        if haystack[i : i + n] == needle:
            return True
    return False


def pick_by_support(candidates, mode):
    """Return the winning value, or None for an empty candidate list.

    Support of a candidate is the number of candidates from *other* sources
    whose key equals its key (``mode == "author"``) or contains its key as a
    contiguous run of tokens (``mode == "title"``). Rows from the same source
    never support each other.

    The winner is the candidate with, in order: the highest support, the
    highest number of candidates with exactly the same string (case sensitive),
    and the highest confidence.
    """
    if not candidates:
        return None

    keys = [_key(value, mode) for value, _, _ in candidates]

    def support(i):
        ki = keys[i]
        src = candidates[i][2]
        total = 0
        for j, (_, _, srcj) in enumerate(candidates):
            if j == i or srcj == src:
                continue
            kj = keys[j]
            if mode == "author":
                if kj == ki:
                    total += 1
            else:
                if _contains_run(kj, ki):
                    total += 1
        return total

    def same_string(i):
        value = candidates[i][0]
        return sum(1 for v, _, _ in candidates if v == value)

    best_index = 0
    best_score = None
    for i in range(len(candidates)):
        score = (support(i), same_string(i), candidates[i][1])
        if best_score is None or score > best_score:
            best_score = score
            best_index = i

    return candidates[best_index][0]
