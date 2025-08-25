def normalize_language(value):
    """Normalize various language codes or names into a consistent display format."""

    lang_map = {
        # English
        'en': 'English', 'eng': 'English', 'english': 'English',
        'en-us': 'English', 'en-gb': 'English',

        # French
        'fr': 'French', 'fra': 'French', 'fre': 'French', 'french': 'French', 'fr-fr': 'French',

        # German
        'de': 'German', 'deu': 'German', 'ger': 'German', 'german': 'German', 'de-de': 'German',

        # Dutch
        'nl': 'Dutch', 'nld': 'Dutch', 'dut': 'Dutch', 'dutch': 'Dutch', 'nl-nl': 'Dutch',

        # Spanish
        'es': 'Spanish', 'spa': 'Spanish', 'spanish': 'Spanish',

        # Portuguese
        'pt': 'Portuguese', 'por': 'Portuguese', 'pt-br': 'Portuguese (Brazil)', 'portuguese': 'Portuguese',

        # Italian
        'it': 'Italian', 'ita': 'Italian', 'italian': 'Italian',

        # Japanese
        'ja': 'Japanese', 'jpn': 'Japanese', 'japanese': 'Japanese',

        # Korean
        'ko': 'Korean', 'kor': 'Korean', 'korean': 'Korean',

        # Chinese
        'zh': 'Chinese', 'chi': 'Chinese', 'zho': 'Chinese', 'chinese': 'Chinese',

        # Hebrew
        'he': 'Hebrew', 'heb': 'Hebrew', 'hebrew': 'Hebrew',

        # Hungarian
        'hu': 'Hungarian', 'hun': 'Hungarian', 'hungarian': 'Hungarian',

        # Polish
        'pl': 'Polish', 'pol': 'Polish', 'polish': 'Polish',

        # Russian
        'ru': 'Russian', 'rus': 'Russian', 'russian': 'Russian',

        # Turkish
        'tr': 'Turkish', 'tur': 'Turkish', 'turkish': 'Turkish',

        # Catalan
        'ca': 'Catalan', 'cat': 'Catalan', 'catalan': 'Catalan',

        # Indonesian
        'id': 'Indonesian', 'ind': 'Indonesian', 'indonesian': 'Indonesian',

        # Hebrew mis-capitalizations
        'Heb': 'Hebrew', 'HEB': 'Hebrew',

        # Unknown or undefined
        'und': 'Unknown', 'zxx': 'Unknown', '': 'Unknown',
    }

    normalized_values = []
    for segment in str(value).replace(';', ',').split(','):
        code = segment.strip().lower()
        if code:
            normalized_values.append(lang_map.get(code, code.title()))

    return normalized_values[0] if len(normalized_values) == 1 else ', '.join(normalized_values)
