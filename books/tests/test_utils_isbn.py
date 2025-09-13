"""
Test cases for ISBN utilities
"""
from django.test import TestCase
from books.utils.isbn import (
    normalize_isbn, is_valid_isbn13, is_valid_isbn10, convert_to_isbn13
)


class ISBNUtilsTests(TestCase):
    """Test cases for ISBN utility functions"""

    def test_normalize_isbn_valid_isbn13(self):
        """Test normalization of valid ISBN-13"""
        isbn = "9780134685991"
        result = normalize_isbn(isbn)
        self.assertEqual(result, "9780134685991")

    def test_normalize_isbn_valid_isbn10(self):
        """Test normalization and conversion of valid ISBN-10"""
        isbn = "0134685997"
        result = normalize_isbn(isbn)
        # Should convert to ISBN-13
        self.assertEqual(result, "9780134685991")

    def test_normalize_isbn_with_hyphens(self):
        """Test normalization of ISBN with hyphens"""
        isbn = "978-0-13-468599-1"
        result = normalize_isbn(isbn)
        self.assertEqual(result, "9780134685991")

    def test_normalize_isbn_with_prefix(self):
        """Test normalization of ISBN with prefix"""
        isbn = "isbn:9780134685991"
        result = normalize_isbn(isbn)
        self.assertEqual(result, "9780134685991")

    def test_normalize_isbn_with_urn_prefix(self):
        """Test normalization of ISBN with URN prefix"""
        isbn = "urn:isbn:9780134685991"
        result = normalize_isbn(isbn)
        self.assertEqual(result, "9780134685991")

    def test_normalize_isbn_invalid_length(self):
        """Test normalization of ISBN with invalid length"""
        isbn = "978013468599"  # 12 digits
        result = normalize_isbn(isbn)
        self.assertIsNone(result)

    def test_normalize_isbn_invalid_checksum(self):
        """Test normalization of ISBN with invalid checksum"""
        isbn = "9780134685990"  # Wrong checksum
        result = normalize_isbn(isbn)
        self.assertIsNone(result)

    def test_normalize_isbn_empty_input(self):
        """Test normalization of empty input"""
        result = normalize_isbn("")
        self.assertIsNone(result)

        result = normalize_isbn(None)
        self.assertIsNone(result)

    def test_normalize_isbn_with_x_check_digit(self):
        """Test normalization of ISBN-10 with X check digit"""
        isbn = "043942089X"
        result = normalize_isbn(isbn)
        self.assertEqual(result, "9780439420891")

    def test_is_valid_isbn13_valid(self):
        """Test valid ISBN-13 validation"""
        self.assertTrue(is_valid_isbn13("9780134685991"))
        self.assertTrue(is_valid_isbn13("9781234567897"))

    def test_is_valid_isbn13_invalid(self):
        """Test invalid ISBN-13 validation"""
        self.assertFalse(is_valid_isbn13("9780134685990"))  # Wrong checksum
        self.assertFalse(is_valid_isbn13("978013468599"))   # Wrong length
        self.assertFalse(is_valid_isbn13("abc0134685991"))  # Non-numeric

    def test_is_valid_isbn10_valid(self):
        """Test valid ISBN-10 validation"""
        self.assertTrue(is_valid_isbn10("0134685997"))
        self.assertTrue(is_valid_isbn10("043942089X"))

    def test_is_valid_isbn10_invalid(self):
        """Test invalid ISBN-10 validation"""
        self.assertFalse(is_valid_isbn10("0134685996"))  # Wrong checksum
        self.assertFalse(is_valid_isbn10("013468599"))   # Wrong length
        self.assertFalse(is_valid_isbn10("abc4685997"))  # Non-numeric

    def test_convert_to_isbn13(self):
        """Test conversion from ISBN-10 to ISBN-13"""
        isbn10 = "0134685997"
        result = convert_to_isbn13(isbn10)
        self.assertEqual(result, "9780134685991")

    def test_convert_to_isbn13_with_x(self):
        """Test conversion from ISBN-10 with X to ISBN-13"""
        isbn10 = "043942089X"
        result = convert_to_isbn13(isbn10)
        self.assertEqual(result, "9780439420891")

    def test_normalize_isbn_case_insensitive(self):
        """Test normalization is case insensitive"""
        isbn_upper = "ISBN:9780134685991"
        isbn_lower = "isbn:9780134685991"

        result_upper = normalize_isbn(isbn_upper)
        result_lower = normalize_isbn(isbn_lower)

        self.assertEqual(result_upper, result_lower)
        self.assertEqual(result_upper, "9780134685991")

    def test_normalize_isbn_with_spaces(self):
        """Test normalization removes spaces"""
        isbn = "978 0 13 468599 1"
        result = normalize_isbn(isbn)
        self.assertEqual(result, "9780134685991")

    def test_normalize_isbn_mixed_formatting(self):
        """Test normalization with mixed formatting"""
        isbn = "  URN:ISBN: 978-0-13-468599-1  "
        result = normalize_isbn(isbn)
        self.assertEqual(result, "9780134685991")
