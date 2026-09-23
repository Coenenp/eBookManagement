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


def detect_language(book):
    """Determine a book's language explicitly, in priority order:

    1. a concrete embedded/external metadata language (not "und"), then
    2. a concrete scan-folder language.

    Returns a normalized ISO language code (e.g. "nl"), "und" when the only
    signals are "undetermined" markers (und / other / unknown), or None when
    there is no signal at all. This is the single place language is detected,
    so callers (the resolver, the Dutch-comic Google Books fallback) agree on it.
    """
    signals = []
    best = book.metadata.filter(field_name="language", is_active=True).order_by("-confidence").first()
    if best and best.field_value:
        signals.append(best.field_value)
    scan_folder = getattr(book, "scan_folder", None)
    if scan_folder and scan_folder.language:
        signals.append(scan_folder.language)

    for signal in signals:
        lang = normalize_language(signal)
        if lang and lang != "und":
            return lang

    # Only "undetermined" markers present -> canonical "und".
    if any(normalize_language(signal) == "und" for signal in signals):
        return "und"

    return None
