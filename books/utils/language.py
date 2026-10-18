# Language-detection gates (M1-OCR item 2). A slice only votes when it carries
# at least ``SLICE_VOTE_CHARS`` non-whitespace characters; a code is accepted
# only when at least ``SLICE_VOTE_MIN_SLICES`` slices vote, all voting slices
# agree, and the total non-whitespace across slices reaches
# ``MIN_LANGUAGE_TEXT_CHARS``. A book that fails the gate is flagged
# LANGUAGE_UNDETERMINED and never guessed from the folder name alone. langid's
# normalized confidence is not a decision gate (it saturates near 1.0 for any
# length-gated sample, so it discriminates nothing).
SLICE_VOTE_CHARS = 150
SLICE_VOTE_MIN_SLICES = 2
MIN_LANGUAGE_TEXT_CHARS = 300

# langid identifiers in normalized-probability mode, one per candidate language
# set (a ``frozenset`` of codes, or ``None`` for the full model), created lazily
# so importing this module never loads the ~2 MB model until detection is needed.
# A restricted identifier is a distinct object, so the shared full-model
# identifier is never mutated when a caller narrows the candidate set.
_langid_identifiers = {}


def _get_langid_identifier(languages=None):
    """Return a langid identifier for ``languages``, cached per language set.

    ``languages`` is a list/set of ISO codes restricting the candidate set;
    ``None`` means the full model. Each distinct set gets its own identifier,
    built with ``set_languages`` at creation time, so callers never mutate an
    identifier that another language set shares.
    """
    from langid.langid import LanguageIdentifier, model

    key = frozenset(languages) if languages else None
    identifier = _langid_identifiers.get(key)
    if identifier is None:
        identifier = LanguageIdentifier.from_modelstring(model, norm_probs=True)
        if languages:
            identifier.set_languages(list(languages))
        _langid_identifiers[key] = identifier
    return identifier


def _vote_slices(slices, languages=None):
    """Vote a language code across disjoint text slices.

    A slice votes only when it has at least ``SLICE_VOTE_CHARS`` non-whitespace
    characters. Returns ``(code, disagreed)``:

    - ``code`` is the agreed code when at least ``SLICE_VOTE_MIN_SLICES`` slices
      vote, all voting slices agree, and the total non-whitespace reaches
      ``MIN_LANGUAGE_TEXT_CHARS`` — else ``None``.
    - ``disagreed`` is True when at least two slices voted with differing codes
      (genuinely ambiguous), and False when the slices simply could not vote
      (too little text, a single slice, or an empty sample).

    There is no confidence gate: langid's normalized probability saturates near
    1.0 for any length-gated sample and discriminates nothing.
    """
    if not slices:
        return None, False

    identifier = _get_langid_identifier(languages)
    votes = []
    total = 0
    for text in slices:
        if not text:
            continue
        non_ws = sum(1 for ch in text if not ch.isspace())
        total += non_ws
        if non_ws < SLICE_VOTE_CHARS:
            continue
        code, _confidence = identifier.classify(text)
        votes.append(code)

    if len(votes) < SLICE_VOTE_MIN_SLICES:
        return None, False
    if len(set(votes)) != 1:
        return None, True
    if total < MIN_LANGUAGE_TEXT_CHARS:
        return None, False
    return votes[0], False


def detect_language_from_slices(slices, languages=None):
    """Vote a language code from disjoint text slices (normalized langid).

    Returns the agreed code when the slices vote and agree, else ``None``.
    See ``_vote_slices`` for the exact gates.

    ``languages`` optionally restricts the candidate set langid scores against
    (e.g. the registered scan-folder languages). When ``None``, the full model
    is used. Production detection passes no restriction so any language is
    detected.
    """
    code, _disagreed = _vote_slices(slices, languages)
    return code


def registered_scan_folder_languages():
    """The set of languages declared by the active scan folders."""
    from books.models import ScanFolder

    return {folder.language for folder in ScanFolder.objects.filter(is_active=True) if folder.language}


def normalize_language(value):
    """Normalize various language codes or names into consistent ISO language codes."""

    lang_map = {
        # English
        "en": "en",
        "eng": "en",
        "english": "en",
        "en-us": "en",
        "en-gb": "en",
        "en-au": "en",
        # French
        "fr": "fr",
        "fra": "fr",
        "fre": "fr",
        "french": "fr",
        "fr-fr": "fr",
        "français": "fr",
        "fr-ca": "fr",
        "fr-be": "fr",
        # German
        "de": "de",
        "deu": "de",
        "ger": "de",
        "german": "de",
        "de-de": "de",
        "de-at": "de",
        "de-ch": "de",
        # Dutch
        "nl": "nl",
        "nld": "nl",
        "dut": "nl",
        "dutch": "nl",
        "nl-nl": "nl",
        # Spanish
        "es": "es",
        "spa": "es",
        "spanish": "es",
        "español": "es",
        "es-mx": "es",
        "es-ar": "es",
        # Portuguese
        "pt": "pt",
        "por": "pt",
        "pt-br": "pt",
        "portuguese": "pt",
        # Italian
        "it": "it",
        "ita": "it",
        "italian": "it",
        # Japanese
        "ja": "ja",
        "jpn": "ja",
        "japanese": "ja",
        "日本語": "ja",
        # Korean
        "ko": "ko",
        "kor": "ko",
        "korean": "ko",
        # Chinese
        "zh": "zh",
        "chi": "zh",
        "zho": "zh",
        "chinese": "zh",
        "zh-hans": "zh",
        "zh-hant": "zh",
        "zh-cn": "zh",
        "zh-tw": "zh",
        "中文": "zh",
        # Additional languages to match LANGUAGE_CHOICES
        # Hebrew
        "he": "he",
        "heb": "he",
        "hebrew": "he",
        # Hungarian
        "hu": "hu",
        "hun": "hu",
        "hungarian": "hu",
        # Polish
        "pl": "pl",
        "pol": "pl",
        "polish": "pl",
        # Russian
        "ru": "ru",
        "rus": "ru",
        "russian": "ru",
        "русский": "ru",
        # Turkish
        "tr": "tr",
        "tur": "tr",
        "turkish": "tr",
        # Catalan
        "ca": "ca",
        "cat": "ca",
        "catalan": "ca",
        # Indonesian
        "id": "id",
        "ind": "id",
        "indonesian": "id",
        # Hebrew mis-capitalizations
        "Heb": "he",
        "HEB": "he",
        # Undetermined / catch-all markers collapse to a single canonical "und"
        "und": "und",
        "other": "und",
        "unknown": "und",
        "undefined": "und",
        "undetermined": "und",
        "unspecified": "und",
        "not defined": "und",
        "not specified": "und",
        # No linguistic content / empty still mean "no language" -> None
        "zxx": None,
        "": None,
    }

    # Import here to avoid circular imports
    from books.utils.language_manager import LanguageManager

    valid_codes = LanguageManager.get_valid_codes()

    normalized_values = []
    for segment in str(value).replace(";", ",").split(","):
        code = segment.strip().lower()
        if code:
            normalized_code = lang_map.get(code)
            # Only include codes that are in our LANGUAGE_CHOICES
            if normalized_code and normalized_code in valid_codes:
                normalized_values.append(normalized_code)

    # Return the first valid code, or None if no valid codes found
    return normalized_values[0] if normalized_values else None


def _embedded_language(book):
    """Normalized concrete embedded language, or None / "und".

    Content Scan language rows are excluded: they record a prior text-derived
    detection, not embedded metadata, so a rescan must not read the previous
    run's own answer back as if the file declared it.
    """
    from books.models import DataSource

    best = (
        book.metadata.filter(field_name="language", is_active=True)
        .exclude(source__name=DataSource.CONTENT_SCAN)
        .order_by("-confidence")
        .first()
    )
    if best and best.field_value:
        return normalize_language(best.field_value)
    return None


def _folder_language(book):
    """Normalized concrete scan-folder language, or None / "und"."""
    scan_folder = getattr(book, "scan_folder", None)
    if scan_folder and scan_folder.language:
        return normalize_language(scan_folder.language)
    return None


def _contradicts(signal, detected):
    """True if a concrete comparison signal disagrees with the detected code."""
    return signal is not None and signal != "und" and signal != detected


def _flag_language(book, reason):
    """Record a language-detection flag (first reason wins)."""
    from books.scanner.match_verification import flag_unresolved

    flag_unresolved(book, reason)


def _write_content_scan_language(book, code):
    """Record a content-derived language under the Content Scan source.

    Uses the same ``DataSource`` that content-ISBN extraction uses
    (``DataSource.CONTENT_SCAN``), so the text-derived language is provenance-
    tracked and survives re-resolution like other content-scan metadata. No new
    source is created.
    """
    from books.models import BookMetadata, DataSource

    source, _ = DataSource.objects.get_or_create(
        name=DataSource.CONTENT_SCAN,
        defaults={"trust_level": 0.85},
    )
    # update_or_create keyed on (book, field, source) so a changed detection
    # replaces the earlier content row rather than adding a second active one.
    BookMetadata.objects.update_or_create(
        book=book,
        field_name="language",
        source=source,
        defaults={
            "field_value": code,
            "confidence": source.trust_level,
            "is_active": True,
        },
    )


def detect_language(book, text_slices=None):
    """Determine a book's language explicitly.

    When ``text_slices`` is provided (a list of disjoint text slices extracted
    from the file, born-digital content), slice voting is the primary signal.
    A code is accepted only when at least two slices vote and all agree (see
    ``_vote_slices``). On acceptance the code is written as a Content Scan
    ``BookMetadata`` language row and outranks the embedded metadata language
    and the scan-folder language. A contradiction with the embedded metadata
    language flags the book (LANGUAGE_DISAGREEMENT) but the code still wins; a
    contradiction with the scan-folder language is not an error.

    When the slices vote but disagree, the book is genuinely ambiguous and is
    flagged LANGUAGE_UNDETERMINED with language "und".

    When the slices simply cannot vote (too little text, a single slice, or an
    empty/unreadable sample), the result is exactly what it would be without
    text: the embedded metadata language, then the scan-folder language, then
    "und" for undetermined-only markers, else None. LANGUAGE_UNDETERMINED is
    raised in this case only when no embedded or folder language exists.

    Without ``text_slices`` the same fallback applies. A language flag never
    overwrites an existing non-empty unresolved reason.
    """
    from books.models import UnresolvedReason

    embedded = _embedded_language(book)
    folder = _folder_language(book)

    if text_slices:
        code, disagreed = _vote_slices(text_slices)
        if code is not None:
            _write_content_scan_language(book, code)
            if _contradicts(embedded, code):
                _flag_language(book, UnresolvedReason.LANGUAGE_DISAGREEMENT)
            return code

        if disagreed:
            _flag_language(book, UnresolvedReason.LANGUAGE_UNDETERMINED)
            return "und"

        # Slices could not vote: fall through to the embedded/folder fallback
        # below, flagging undetermined only when nothing concrete exists.

    for signal in (embedded, folder):
        if signal and signal != "und":
            return signal

    if embedded == "und" or folder == "und":
        return "und"

    if text_slices:
        # We had text but it could not vote and there is no embedded/folder
        # language to fall back on.
        _flag_language(book, UnresolvedReason.LANGUAGE_UNDETERMINED)
        return "und"

    return None
