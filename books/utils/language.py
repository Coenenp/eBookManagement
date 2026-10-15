# Language-detection gates (M1-OCR item 1). A text sample must clear both to be
# trusted as a language signal; otherwise the book is flagged with language
# "undetermined" and never guessed from the folder name alone.
MIN_LANGUAGE_TEXT_CHARS = 300
MIN_LANGUAGE_CONFIDENCE = 0.90

# langid identifier in normalized-probability mode, created lazily so importing
# this module never loads the ~2 MB model until detection is actually needed.
_langid_identifier = None


def _get_langid_identifier():
    """Return the shared langid identifier (normalized-probability mode)."""
    global _langid_identifier
    if _langid_identifier is None:
        from langid.langid import LanguageIdentifier, model

        _langid_identifier = LanguageIdentifier.from_modelstring(model, norm_probs=True)
    return _langid_identifier


def detect_language_from_text(text, languages=None):
    """Detect a text's language with langid (normalized-probability mode).

    Returns ``(code, confidence)`` when the sample clears both gates — at least
    ``MIN_LANGUAGE_TEXT_CHARS`` non-whitespace characters and a detector
    confidence of at least ``MIN_LANGUAGE_CONFIDENCE`` — else ``None``.

    ``languages`` optionally restricts the candidate set langid scores against
    (e.g. the registered scan-folder languages). When ``None``, the full model
    is used.
    """
    if not text:
        return None
    non_ws = sum(1 for ch in text if not ch.isspace())
    if non_ws < MIN_LANGUAGE_TEXT_CHARS:
        return None

    identifier = _get_langid_identifier()
    if languages:
        identifier.set_languages(list(languages))
        try:
            code, confidence = identifier.classify(text)
        finally:
            identifier.set_languages(None)
    else:
        code, confidence = identifier.classify(text)

    if confidence < MIN_LANGUAGE_CONFIDENCE:
        return None
    return code, confidence


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
    """Normalized concrete embedded language, or None / "und"."""
    best = book.metadata.filter(field_name="language", is_active=True).order_by("-confidence").first()
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
    """Record a language-detection flag on the book's FinalMetadata."""
    from books.models import FinalMetadata

    fm = FinalMetadata.objects.filter(book=book).first()
    if fm is None:
        fm = FinalMetadata(book=book)
        fm.save(auto_sync=False)
    fm.unresolved_reason = reason
    fm.save(update_fields=["unresolved_reason"])


def detect_language(book, extracted_text=None):
    """Determine a book's language explicitly.

    When ``extracted_text`` is provided (born-digital content), langid is the
    primary signal, gated on length + confidence. The embedded metadata language
    and the scan-folder language are comparison signals only: a confident
    detection that contradicts either flags the book (LANGUAGE_DISAGREEMENT),
    and a sample that fails the gates flags it LANGUAGE_UNDETERMINED with
    language "und". The folder language is never written as a detection.

    Without ``extracted_text`` the existing fallback applies: a concrete
    embedded metadata language, then a concrete scan-folder language, then
    "und" for undetermined-only markers, else None. This is the single place
    language is detected, so callers (the resolver, the Dutch-comic Google
    Books fallback) agree on it.
    """
    from books.models import UnresolvedReason

    embedded = _embedded_language(book)
    folder = _folder_language(book)

    if extracted_text:
        result = detect_language_from_text(extracted_text, languages=registered_scan_folder_languages() or None)
        if result is None:
            _flag_language(book, UnresolvedReason.LANGUAGE_UNDETERMINED)
            return "und"
        code, _confidence = result
        if _contradicts(embedded, code) or _contradicts(folder, code):
            _flag_language(book, UnresolvedReason.LANGUAGE_DISAGREEMENT)
        return code

    for signal in (embedded, folder):
        if signal and signal != "und":
            return signal

    if embedded == "und" or folder == "und":
        return "und"

    return None
