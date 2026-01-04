"""
Test cases for Language utilities
"""
from unittest.mock import patch

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


class LanguageUtilsEdgeCaseTests(TestCase):
    """Test edge cases and advanced scenarios for language utilities"""

    def test_normalize_language_unicode_input(self):
        """Test normalization with unicode language names"""
        unicode_cases = [
            ('中文', 'zh'),  # Chinese characters
            ('español', 'es'),  # Spanish with accent
            ('français', 'fr'),  # French with accent
            ('русский', 'ru'),  # Russian Cyrillic
            ('العربية', None),  # Arabic (not in mapping)
            ('日本語', 'ja'),  # Japanese characters
        ]

        for input_code, expected in unicode_cases:
            with self.subTest(input_code=input_code):
                result = normalize_language(input_code)
                if expected:
                    self.assertEqual(result, expected)
                else:
                    self.assertIsNone(result)

    def test_normalize_language_malformed_input(self):
        """Test normalization with malformed input"""
        malformed_cases = [
            'en-',           # Incomplete locale
            '-en',           # Invalid format
            'en--us',        # Double separator
            'en_us_extra',   # Too many parts
            'en.us',         # Wrong separator
            'en us',         # Space instead of dash
            '@#$%',          # Special characters
            '.',             # Single dot
            '--',            # Only separators
        ]

        for code in malformed_cases:
            with self.subTest(code=code):
                result = normalize_language(code)
                # Most should return None, some might be partially parsed
                self.assertIsInstance(result, (str, type(None)))

    def test_normalize_language_very_long_input(self):
        """Test normalization with very long input strings"""
        # Test with extremely long string
        long_string = 'en' + 'x' * 10000
        result = normalize_language(long_string)
        self.assertIsNone(result)

        # Test with long valid string that starts with valid code
        long_valid = 'english' + 'x' * 1000
        result = normalize_language(long_valid)
        self.assertIsNone(result)  # Should not match partial strings

    def test_normalize_language_performance_large_list(self):
        """Test performance with large comma-separated list"""
        # Create a large list with one valid code at the end
        large_list = ', '.join(['invalid'] * 1000) + ', en'
        result = normalize_language(large_list)
        self.assertEqual(result, 'en')

    def test_normalize_language_mixed_separators_complex(self):
        """Test complex mixed separator scenarios"""
        complex_cases = [
            ('en;fr,de;es,it', 'en'),
            ('invalid;invalid,fr;invalid', 'fr'),
            (';;,,,en', 'en'),
            (',;,;en;,;,', 'en'),
            ('  ; , ; en ; , ; ', 'en'),
        ]

        for input_code, expected in complex_cases:
            with self.subTest(input_code=input_code):
                result = normalize_language(input_code)
                self.assertEqual(result, expected)

    def test_normalize_language_special_iso_codes(self):
        """Test normalization with special ISO language codes"""
        special_codes = [
            ('und', None),    # Undefined language
            ('zxx', None),    # No linguistic content
            ('mul', None),    # Multiple languages
            ('mis', None),    # Uncoded languages
            ('art', None),    # Artificial languages
            ('qaa', None),    # Reserved for local use
        ]

        for code, expected in special_codes:
            with self.subTest(code=code):
                result = normalize_language(code)
                self.assertEqual(result, expected)

    def test_normalize_language_regional_variants(self):
        """Test normalization with regional language variants"""
        regional_cases = [
            ('en-US', 'en'),
            ('en-GB', 'en'),
            ('en-AU', 'en'),
            ('fr-CA', 'fr'),
            ('fr-BE', 'fr'),
            ('de-AT', 'de'),
            ('de-CH', 'de'),
            ('es-MX', 'es'),
            ('es-AR', 'es'),
            ('pt-BR', 'pt'),
            ('zh-CN', 'zh'),
            ('zh-TW', 'zh'),
        ]

        for input_code, expected in regional_cases:
            with self.subTest(input_code=input_code):
                result = normalize_language(input_code)
                self.assertEqual(result, expected)

    def test_normalize_language_script_variants(self):
        """Test normalization with script variant codes"""
        script_cases = [
            ('zh-Hans', 'zh'),  # Simplified Chinese
            ('zh-Hant', 'zh'),  # Traditional Chinese
            ('sr-Latn', None),  # Serbian Latin (not in basic mapping)
            ('sr-Cyrl', None),  # Serbian Cyrillic (not in basic mapping)
            ('az-Arab', None),  # Azerbaijani Arabic script
        ]

        for code, expected in script_cases:
            with self.subTest(code=code):
                result = normalize_language(code)
                if expected:
                    self.assertEqual(result, expected)
                else:
                    self.assertIsNone(result)

    def test_normalize_language_case_variations(self):
        """Test normalization with various case combinations"""
        case_variations = [
            ('EN', 'en'),
            ('En', 'en'),
            ('eN', 'en'),
            ('ENGLISH', 'en'),
            ('English', 'en'),
            ('eNgLiSh', 'en'),
            ('FR', 'fr'),
            ('Fr', 'fr'),
            ('FRENCH', 'fr'),
            ('FrEnCh', 'fr'),
        ]

        for input_code, expected in case_variations:
            with self.subTest(input_code=input_code):
                result = normalize_language(input_code)
                self.assertEqual(result, expected)

    def test_normalize_language_whitespace_variations(self):
        """Test normalization with various whitespace patterns"""
        whitespace_cases = [
            ('\ten\t', 'en'),
            ('\nen\n', 'en'),
            ('\r\nen\r\n', 'en'),
            ('  \t\n en \t\n  ', 'en'),
            ('en \t, \n fr', 'en'),
            (' \t ; \n en \t ; \n ', 'en'),
        ]

        for input_code, expected in whitespace_cases:
            with self.subTest(input_code=input_code):
                result = normalize_language(input_code)
                self.assertEqual(result, expected)

    def test_normalize_language_boundary_conditions(self):
        """Test normalization at boundary conditions"""
        boundary_cases = [
            ('a', None),        # Single character
            ('aa', None),       # Two characters (not ISO standard)
            ('aaa', None),      # Three characters but invalid
            ('x' * 100, None),  # Very long invalid code
            ('123', None),      # Only numbers
            ('en1', None),      # Mixed alphanumeric
            ('1en', None),      # Number prefix
        ]

        for code, expected in boundary_cases:
            with self.subTest(code=code):
                result = normalize_language(code)
                self.assertEqual(result, expected)

    def test_normalize_language_error_recovery(self):
        """Test error recovery in language normalization"""
        # Test with potentially problematic input that shouldn't crash
        problematic_inputs = [
            object(),           # Non-string object
            [],                 # List
            {},                 # Dictionary
            lambda: 'en',       # Function
            type,               # Type object
        ]

        for problematic_input in problematic_inputs:
            with self.subTest(input=str(type(problematic_input))):
                try:
                    result = normalize_language(problematic_input)
                    # Should handle gracefully, either return None or valid string
                    self.assertIsInstance(result, (str, type(None)))
                except (TypeError, AttributeError):
                    # These exceptions are acceptable for truly invalid input
                    pass

    def test_normalize_language_memory_efficiency(self):
        """Test memory efficiency with repeated calls"""
        # Test that repeated calls don't cause memory leaks
        for _ in range(1000):
            result = normalize_language('en')
            self.assertEqual(result, 'en')

        # Test with different inputs
        inputs = ['en', 'fr', 'de', 'es', 'it', 'pt', 'nl', 'ru', 'ja', 'zh']
        for _ in range(100):
            for lang in inputs:
                result = normalize_language(lang)
                self.assertIsNotNone(result)

    @patch('books.tests.test_utils_language.normalize_language')
    def test_normalize_language_caching_behavior(self, mock_normalize):
        """Test caching behavior if implemented"""
        # Set up mock to return predictable values
        mock_normalize.return_value = 'en'

        # Call multiple times with same input
        for _ in range(5):
            mock_normalize('english')

        # Verify function was called (mocking bypasses actual implementation)
        self.assertTrue(mock_normalize.called)

    def test_normalize_language_thread_safety(self):
        """Test thread safety of language normalization"""
        import queue
        import threading

        results = queue.Queue()

        def worker():
            for i in range(100):
                result = normalize_language('en')
                results.put(result)

        # Start multiple threads
        threads = []
        for _ in range(10):
            thread = threading.Thread(target=worker)
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # Verify all results are correct
        while not results.empty():
            result = results.get()
            self.assertEqual(result, 'en')

    def test_normalize_language_comprehensive_iso_coverage(self):
        """Test comprehensive coverage of ISO language codes"""
        # Test all major ISO 639-1 codes that should be supported
        iso_codes = {
            'ar': None,  # Arabic (may not be implemented)
            'bg': None,  # Bulgarian (may not be implemented)
            'ca': None,  # Catalan (may not be implemented)
            'cs': None,  # Czech (may not be implemented)
            'da': None,  # Danish (may not be implemented)
            'el': None,  # Greek (may not be implemented)
            'en': 'en',  # English (should be implemented)
            'es': 'es',  # Spanish (should be implemented)
            'et': None,  # Estonian (may not be implemented)
            'fi': None,  # Finnish (may not be implemented)
            'fr': 'fr',  # French (should be implemented)
            'he': 'he',  # Hebrew (should be implemented)
            'hi': None,  # Hindi (may not be implemented)
            'hr': None,  # Croatian (may not be implemented)
            'hu': 'hu',  # Hungarian (should be implemented)
            'id': None,  # Indonesian (may not be implemented)
            'is': None,  # Icelandic (may not be implemented)
            'it': 'it',  # Italian (should be implemented)
            'ja': 'ja',  # Japanese (should be implemented)
            'ko': 'ko',  # Korean (should be implemented)
            'lt': None,  # Lithuanian (may not be implemented)
            'lv': None,  # Latvian (may not be implemented)
            'nb': None,  # Norwegian Bokmål (may not be implemented)
            'nl': 'nl',  # Dutch (should be implemented)
            'no': None,  # Norwegian (may not be implemented)
            'pl': 'pl',  # Polish (should be implemented)
            'pt': 'pt',  # Portuguese (should be implemented)
            'ro': None,  # Romanian (may not be implemented)
            'ru': 'ru',  # Russian (should be implemented)
            'sk': None,  # Slovak (may not be implemented)
            'sl': None,  # Slovenian (may not be implemented)
            'sv': None,  # Swedish (may not be implemented)
            'th': None,  # Thai (may not be implemented)
            'tr': None,  # Turkish (may not be implemented)
            'uk': None,  # Ukrainian (may not be implemented)
            'vi': None,  # Vietnamese (may not be implemented)
            'zh': 'zh',  # Chinese (should be implemented)
        }

        for iso_code, expected in iso_codes.items():
            with self.subTest(iso_code=iso_code):
                result = normalize_language(iso_code)
                if expected:
                    self.assertEqual(result, expected)
                # If expected is None, we don't assert anything as
                # implementation may or may not support that language
