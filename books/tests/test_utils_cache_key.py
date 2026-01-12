"""
Test cases for Cache Key utilities
"""

from django.test import TestCase

from books.utils.cache_key import make_cache_key


class CacheKeyUtilsTests(TestCase):
    """Test cases for Cache Key utility functions"""

    def test_make_cache_key_single_arg(self):
        """Test cache key generation with single argument"""
        result = make_cache_key("test")

        # Should return a SHA1 hash
        self.assertEqual(len(result), 40)  # SHA1 produces 40-character hex
        self.assertTrue(all(c in "0123456789abcdef" for c in result))

    def test_make_cache_key_multiple_args(self):
        """Test cache key generation with multiple arguments"""
        result = make_cache_key("arg1", "arg2", "arg3")

        # Should return a SHA1 hash
        self.assertEqual(len(result), 40)
        self.assertTrue(all(c in "0123456789abcdef" for c in result))

    def test_make_cache_key_consistency(self):
        """Test that same arguments produce same cache key"""
        result1 = make_cache_key("test", "key")
        result2 = make_cache_key("test", "key")

        self.assertEqual(result1, result2)

    def test_make_cache_key_different_args_different_keys(self):
        """Test that different arguments produce different cache keys"""
        result1 = make_cache_key("test1")
        result2 = make_cache_key("test2")

        self.assertNotEqual(result1, result2)

    def test_make_cache_key_with_none(self):
        """Test cache key generation with None values"""
        result = make_cache_key("test", None, "key")

        # Should handle None values gracefully
        self.assertEqual(len(result), 40)
        self.assertTrue(all(c in "0123456789abcdef" for c in result))

    def test_make_cache_key_empty_string(self):
        """Test cache key generation with empty string"""
        result = make_cache_key("")

        # Should handle empty string
        self.assertEqual(len(result), 40)

    def test_make_cache_key_no_args(self):
        """Test cache key generation with no arguments"""
        result = make_cache_key()

        # Should handle no arguments
        self.assertEqual(len(result), 40)

    def test_make_cache_key_unicode_handling(self):
        """Test cache key generation with unicode characters"""
        result = make_cache_key("tést", "ünïcödé")

        # Should handle unicode properly
        self.assertEqual(len(result), 40)
        self.assertTrue(all(c in "0123456789abcdef" for c in result))

    def test_make_cache_key_numeric_args(self):
        """Test cache key generation with numeric arguments"""
        # Arguments should be strings or convertible to strings
        result1 = make_cache_key("123", "456")
        result2 = make_cache_key("123", "456")

        self.assertEqual(result1, result2)

    def test_make_cache_key_order_matters(self):
        """Test that argument order affects the cache key"""
        result1 = make_cache_key("arg1", "arg2")
        result2 = make_cache_key("arg2", "arg1")

        self.assertNotEqual(result1, result2)

    def test_make_cache_key_colon_separator(self):
        """Test that the colon separator is used correctly"""
        # These should produce the same key
        result1 = make_cache_key("test:key")
        result2 = make_cache_key("test", "key")

        self.assertEqual(result1, result2)

    def test_make_cache_key_whitespace_handling(self):
        """Test cache key generation with whitespace"""
        result = make_cache_key("  test  ", " key ")

        # Should preserve whitespace
        self.assertEqual(len(result), 40)

    def test_make_cache_key_special_characters(self):
        """Test cache key generation with special characters"""
        result = make_cache_key("test@key", "value#123", "name&value")

        # Should handle special characters
        self.assertEqual(len(result), 40)

    def test_make_cache_key_very_long_args(self):
        """Test cache key generation with very long arguments"""
        long_arg = "a" * 1000
        result = make_cache_key(long_arg, "test")

        # Should still produce consistent length hash
        self.assertEqual(len(result), 40)

    def test_make_cache_key_mixed_none_and_values(self):
        """Test cache key generation with mix of None and actual values"""
        result1 = make_cache_key("test", None, "key", None)
        result2 = make_cache_key("test", "", "key", "")

        # None should be treated as empty string
        self.assertEqual(result1, result2)

    def test_make_cache_key_case_sensitive(self):
        """Test that cache key generation is case sensitive"""
        result1 = make_cache_key("Test")
        result2 = make_cache_key("test")

        self.assertNotEqual(result1, result2)
