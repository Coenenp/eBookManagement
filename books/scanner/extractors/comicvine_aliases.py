"""Dutch -> canonical ComicVine series-name alias table.

Stripverhalen holds Dutch translations of Franco-Belgian bande dessinee,
which ComicVine indexes under the original French series name (e.g. the
Dutch "Alex" is the French "Alix" by Jacques Martin). A naive search on the
Dutch name returns unrelated volumes, so the lookup must resolve the Dutch
series name to the canonical ComicVine series name first.

Extend deliberately: add an entry here (with a test) when a series is
confirmed to fail naive ComicVine search and its canonical name is verified.
Do not discover aliases by accident inside inline lookup logic.
"""

# Lowercased Dutch series name -> canonical ComicVine series name.
SERIES_ALIASES = {
    "alex": "Alix",
    "de reizen van alex": "Les Voyages d'Alix",
    "de jeugd van alex": "Alix Origines",
}


def canonicalize_series(series_name):
    """Return the canonical ComicVine series name for a Dutch series name.

    Matching is case-insensitive on a trimmed input. Unknown series names are
    returned unchanged so the caller can still attempt a naive search.
    """
    if not series_name:
        return series_name
    return SERIES_ALIASES.get(series_name.strip().lower(), series_name)


def has_alias(series_name):
    """Return True if the series name has a canonical alias entry."""
    if not series_name:
        return False
    return series_name.strip().lower() in SERIES_ALIASES
