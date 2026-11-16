"""Shared surname-particle handling for author-name splitting.

The single source of truth for surname particles (``van``, ``von``, ``den``,
``d'``, ...) used across the library.  Matching is exact and case-sensitive:
``vanden`` and ``Vanden`` are different words, each a valid particle, and no
letter of any name is ever changed.
"""

# The union of the two historical particle lists (``surname_prefixes`` in
# books/utils/authors.py and ``surname_particles`` in
# books/utils/parsing_helpers.py), lowercased, multi-word entries kept.
SURNAME_PARTICLES = {
    "o'",
    "mac",
    "mc",
    "van",
    "von",
    "vander",
    "vonder",
    "van der",
    "von der",
    "van den",
    "von den",
    "van de",
    "vanden",
    "vonden",
    "del",
    "della",
    "dela",
    "d'",
    "du",
    "de",
    "di",
    "ter",
    "lo",
    "gel",
    "van t",
    "la",
    "le",
    "da",
    "den",
    "der",
    "dos",
    "das",
    "ibn",
    "bin",
    "ben",
    "abd",
    "abu",
    "al",
    "o",
    "d",
}

# Particles whose capitalised form (first letter upper, rest lower: ``Van``,
# ``Von``, ``De``, ...) also counts as a particle.  Any other capitalised form
# is not a particle.
CAPITAL_OK = {
    "van",
    "von",
    "de",
    "den",
    "der",
    "ter",
    "del",
    "della",
    "dela",
    "vanden",
    "vander",
    "di",
    "da",
    "du",
    "le",
    "la",
}


def _is_particle_word(word):
    """Whether a single whitespace token is a particle (case-sensitive)."""
    if word in SURNAME_PARTICLES:
        return True
    if word[:1].isupper() and word[1:].islower() and word.lower() in CAPITAL_OK:
        return True
    return False


def _multi_word_particle_at(tokens, i):
    """Whether a two-token particle starts at index ``i`` (exact, lowercased)."""
    if i + 2 <= len(tokens):
        return " ".join(tokens[i : i + 2]) in SURNAME_PARTICLES
    return False


def split_author(full_name):
    """Return ``(first, last)`` for an author name, keeping every letter.

    A name containing a comma is ``last, first``: the last name is everything
    before the first comma (no particle logic), and trailing particles at the
    end of the first-name part move to the front of the last name.  A name
    without a comma is split at the earliest particle (position >= 1); if there
    is none, the last word is the last name.
    """
    if not full_name:
        return "", ""
    name = full_name.strip()
    if not name:
        return "", ""

    if "," in name:
        head, _, tail = name.partition(",")
        last_tokens = head.split()
        tail_tokens = tail.split()
        # Move trailing particles from the first-name part to the front of the
        # last name.
        moved = []
        while tail_tokens and _is_particle_word(tail_tokens[-1]):
            moved.insert(0, tail_tokens.pop())
        last_tokens = moved + last_tokens
        return " ".join(tail_tokens).strip(), " ".join(last_tokens).strip()

    tokens = name.split()
    if len(tokens) == 1:
        return "", tokens[0]

    # A particle in first position: with exactly two tokens a capitalised first
    # token is not a particle ("Van Morrison"), while a lowercase particle first
    # makes the whole name the last name ("van Gogh").
    if len(tokens) == 2 and _is_particle_word(tokens[0]):
        if tokens[0][:1].isupper() and tokens[0][1:].islower():
            return tokens[0], tokens[1]
        return "", " ".join(tokens)

    for i in range(1, len(tokens)):
        if _is_particle_word(tokens[i]) or _multi_word_particle_at(tokens, i):
            return " ".join(tokens[:i]).strip(), " ".join(tokens[i:]).strip()

    return " ".join(tokens[:-1]).strip(), tokens[-1]


def sort_name(full_name):
    """Return ``last, first`` (just the last name when there is no first name)."""
    first, last = split_author(full_name)
    if not last:
        return first or ""
    if first:
        return f"{last}, {first}"
    return last
