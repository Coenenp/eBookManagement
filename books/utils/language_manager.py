"""
Centralized language management utilities.

This module provides a centralized way to handle language choices and conversions
throughout the ebook library manager application.
"""


class LanguageManager:
    """Centralized manager for language choices and utilities."""

    @classmethod
    def get_language_choices(cls):
        """Get the standard language choices from the model."""
        try:
            # Import the LANGUAGE_CHOICES from models
            from books.models import LANGUAGE_CHOICES

            return LANGUAGE_CHOICES
        except ImportError:
            # Fallback if import fails
            return [
                ("en", "English"),
                ("fr", "French"),
                ("de", "German"),
                ("nl", "Dutch"),
                ("es", "Spanish"),
                ("it", "Italian"),
                ("pt", "Portuguese"),
                ("ja", "Japanese"),
                ("ko", "Korean"),
                ("zh", "Chinese"),
                ("ru", "Russian"),
                ("pl", "Polish"),
                ("he", "Hebrew"),
                ("hu", "Hungarian"),
                ("tr", "Turkish"),
                ("ca", "Catalan"),
                ("id", "Indonesian"),
            ]

    @classmethod
    def get_language_choices_with_empty(cls, empty_label="Select language"):
        """Get language choices with an empty option."""
        return [("", empty_label)] + cls.get_language_choices()

    @classmethod
    def get_language_choices_with_all(cls, all_label="All Languages"):
        """Get language choices with an 'all' option."""
        return [("", all_label)] + cls.get_language_choices()

    @classmethod
    def get_language_dict(cls):
        """Get a dictionary mapping language codes to names."""
        return dict(cls.get_language_choices())

    @classmethod
    def get_language_name(cls, code):
        """Get the display name for a language code."""
        language_dict = cls.get_language_dict()
        return language_dict.get(code, code)

    @classmethod
    def get_valid_codes(cls):
        """Get a list of valid language codes."""
        return [code for code, name in cls.get_language_choices()]

    @classmethod
    def is_valid_code(cls, code):
        """Check if a language code is valid."""
        return code in cls.get_valid_codes()

    @classmethod
    def get_default_language(cls):
        """Get the default language code."""
        return "en"

    @classmethod
    def normalize_language_code(cls, code):
        """Normalize a language code to a valid choice."""
        if not code:
            return cls.get_default_language()

        # Clean the code
        code = code.lower().strip()

        # Check if it's already valid
        if cls.is_valid_code(code):
            return code

        # Try to map common variations
        language_mappings = {
            "eng": "en",
            "english": "en",
            "fra": "fr",
            "french": "fr",
            "deu": "de",
            "ger": "de",
            "german": "de",
            "spa": "es",
            "spanish": "es",
            "ita": "it",
            "italian": "it",
            "por": "pt",
            "portuguese": "pt",
            "jpn": "ja",
            "japanese": "ja",
            "kor": "ko",
            "korean": "ko",
            "chi": "zh",
            "chinese": "zh",
            "rus": "ru",
            "russian": "ru",
            "pol": "pl",
            "polish": "pl",
            "heb": "he",
            "hebrew": "he",
            "hun": "hu",
            "hungarian": "hu",
            "tur": "tr",
            "turkish": "tr",
            "cat": "ca",
            "catalan": "ca",
            "ind": "id",
            "indonesian": "id",
            "dut": "nl",
            "dutch": "nl",
        }

        mapped_code = language_mappings.get(code)
        if mapped_code and cls.is_valid_code(mapped_code):
            return mapped_code

        # Return default if no mapping found
        return cls.get_default_language()


# Convenience functions for backward compatibility
def get_language_choices():
    """Get the standard language choices."""
    return LanguageManager.get_language_choices()


def get_language_choices_with_empty(empty_label="Select language"):
    """Get language choices with an empty option."""
    return LanguageManager.get_language_choices_with_empty(empty_label)


def get_language_choices_with_all(all_label="All Languages"):
    """Get language choices with an 'all' option."""
    return LanguageManager.get_language_choices_with_all(all_label)


def get_language_dict():
    """Get a dictionary mapping language codes to names."""
    return LanguageManager.get_language_dict()


def get_language_name(code):
    """Get the display name for a language code."""
    return LanguageManager.get_language_name(code)


def normalize_language_code(code):
    """Normalize a language code to a valid choice."""
    return LanguageManager.normalize_language_code(code)
