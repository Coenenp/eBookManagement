"""
Test cases for Language utilities
"""
from django.test import TestCase
from books.utils.language import normalize_language


class LanguageUtilsTests(TestCase):
    """Test cases for Language utility functions"""

    def test_normalize_language_english_codes(self):
        """Test normalization of various English language codes"""
        test_cases = ['en', 'eng', 'english', 'en-us', 'en-gb']
        for code in test_cases:
            with self.subTest(code=code):
                result = normalize_language(code)
                self.assertEqual(result, 'en')

    def test_normalize_language_french_codes(self):
        """Test normalization of various French language codes"""
        test_cases = ['fr', 'fra', 'fre', 'french', 'fr-fr']
        for code in test_cases:
            with self.subTest(code=code):
                result = normalize_language(code)
                self.assertEqual(result, 'fr')

    def test_normalize_language_german_codes(self):
        """Test normalization of various German language codes"""
        test_cases = ['de', 'deu', 'ger', 'german', 'de-de']
        for code in test_cases:
            with self.subTest(code=code):
                result = normalize_language(code)
                self.assertEqual(result, 'de')

    def test_normalize_language_dutch_codes(self):
        """Test normalization of various Dutch language codes"""
        test_cases = ['nl', 'nld', 'dut', 'dutch', 'nl-nl']
        for code in test_cases:
            with self.subTest(code=code):
                result = normalize_language(code)
                self.assertEqual(result, 'nl')

    def test_normalize_language_spanish_codes(self):
        """Test normalization of Spanish language codes"""
        test_cases = ['es', 'spa', 'spanish']
        for code in test_cases:
            with self.subTest(code=code):
                result = normalize_language(code)
                self.assertEqual(result, 'es')

    def test_normalize_language_portuguese_codes(self):
        """Test normalization of Portuguese language codes"""
        test_cases = ['pt', 'por', 'pt-br', 'portuguese']
        for code in test_cases:
            with self.subTest(code=code):
                result = normalize_language(code)
                self.assertEqual(result, 'pt')

    def test_normalize_language_case_insensitive(self):
        """Test that normalization is case insensitive"""
        test_cases = [
            ('EN', 'en'),
            ('ENGLISH', 'en'),
            ('French', 'fr'),
            ('GERMAN', 'de'),
            ('Spanish', 'es')
        ]
        for input_code, expected in test_cases:
            with self.subTest(input_code=input_code):
                result = normalize_language(input_code)
                self.assertEqual(result, expected)

    def test_normalize_language_multiple_values(self):
        """Test normalization with multiple comma-separated values"""
        result = normalize_language("en, fr, de")
        # Should return first valid code
        self.assertEqual(result, 'en')

    def test_normalize_language_semicolon_separated(self):
        """Test normalization with semicolon-separated values"""
        result = normalize_language("fr; de; es")
        # Should return first valid code
        self.assertEqual(result, 'fr')

    def test_normalize_language_mixed_separators(self):
        """Test normalization with mixed separators"""
        result = normalize_language("en; fr, de")
        self.assertEqual(result, 'en')

    def test_normalize_language_unknown_codes(self):
        """Test normalization of unknown language codes"""
        unknown_codes = ['und', 'zxx', '', 'unknown', 'xyz']
        for code in unknown_codes:
            with self.subTest(code=code):
                result = normalize_language(code)
                self.assertIsNone(result)

    def test_normalize_language_hebrew_codes(self):
        """Test normalization of Hebrew language codes"""
        test_cases = ['he', 'heb', 'hebrew', 'Heb', 'HEB']
        for code in test_cases:
            with self.subTest(code=code):
                result = normalize_language(code)
                self.assertEqual(result, 'he')

    def test_normalize_language_asian_codes(self):
        """Test normalization of Asian language codes"""
        test_cases = [
            ('ja', 'ja'), ('jpn', 'ja'), ('japanese', 'ja'),
            ('ko', 'ko'), ('kor', 'ko'), ('korean', 'ko'),
            ('zh', 'zh'), ('chi', 'zh'), ('zho', 'zh'), ('chinese', 'zh')
        ]
        for input_code, expected in test_cases:
            with self.subTest(input_code=input_code):
                result = normalize_language(input_code)
                self.assertEqual(result, expected)

    def test_normalize_language_eastern_european_codes(self):
        """Test normalization of Eastern European language codes"""
        test_cases = [
            ('pl', 'pl'), ('pol', 'pl'), ('polish', 'pl'),
            ('ru', 'ru'), ('rus', 'ru'), ('russian', 'ru'),
            ('hu', 'hu'), ('hun', 'hu'), ('hungarian', 'hu')
        ]
        for input_code, expected in test_cases:
            with self.subTest(input_code=input_code):
                result = normalize_language(input_code)
                self.assertEqual(result, expected)

    def test_normalize_language_whitespace_handling(self):
        """Test that whitespace is properly handled"""
        test_cases = [
            ('  en  ', 'en'),
            (' english ', 'en'),
            ('  fr,  de  ', 'fr'),
            ('en ; fr', 'en')
        ]
        for input_code, expected in test_cases:
            with self.subTest(input_code=input_code):
                result = normalize_language(input_code)
                self.assertEqual(result, expected)

    def test_normalize_language_empty_segments(self):
        """Test handling of empty segments in comma-separated values"""
        result = normalize_language("en, , fr")
        self.assertEqual(result, 'en')

    def test_normalize_language_all_unknown(self):
        """Test normalization when all values are unknown"""
        result = normalize_language("unknown, xyz, zxx")
        self.assertIsNone(result)

    def test_normalize_language_mixed_valid_invalid(self):
        """Test normalization with mix of valid and invalid codes"""
        result = normalize_language("unknown, fr, xyz")
        self.assertEqual(result, 'fr')

    def test_normalize_language_numeric_input(self):
        """Test normalization with numeric input"""
        result = normalize_language(123)
        # Should handle conversion to string
        self.assertIsNone(result)  # '123' is not a valid language code

    def test_normalize_language_none_input(self):
        """Test normalization with None input"""
        result = normalize_language(None)
        self.assertIsNone(result)
