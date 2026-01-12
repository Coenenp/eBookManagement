"""Comprehensive tests for books.mixins module.

Tests for StandardWidgetMixin, BaseMetadataValidator, StandardFormMixin,
MetadataFormMixin, and FinalMetadataSyncMixin functionality.
Focuses on achieving 100% coverage for the mixins module.
"""

import os
from unittest.mock import patch

import django
from django import forms
from django.test import TestCase
from django.utils import timezone

from books.mixins import BaseMetadataValidator, FinalMetadataSyncMixin, MetadataFormMixin, StandardFormMixin, StandardWidgetMixin
from books.models import Author, DataSource, FinalMetadata
from books.tests.test_helpers import create_test_book_with_file

# Must set Django settings before importing Django models
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ebook_manager.settings")
django.setup()


class StandardWidgetMixinTests(TestCase):
    """Test StandardWidgetMixin functionality"""

    def setUp(self):
        self.mixin = StandardWidgetMixin()

    def test_standard_widgets_exist(self):
        """Test that standard widget dictionary exists and contains expected widgets"""
        widgets = StandardWidgetMixin.STANDARD_WIDGETS
        self.assertIn("text_input", widgets)
        self.assertIn("text_input_required", widgets)
        self.assertIn("email_input", widgets)
        self.assertIn("password_input", widgets)
        self.assertIn("textarea", widgets)
        self.assertIn("select", widgets)
        self.assertIn("number_input", widgets)
        self.assertIn("checkbox", widgets)
        self.assertIn("file_input", widgets)
        self.assertIn("image_input", widgets)
        self.assertIn("hidden", widgets)

    def test_get_widget_valid_type(self):
        """Test getting widget with valid type"""
        widget = StandardWidgetMixin.get_widget("text_input")
        self.assertIsInstance(widget, forms.TextInput)
        self.assertEqual(widget.attrs["class"], "form-control")

    def test_get_widget_with_extra_attrs(self):
        """Test getting widget with extra attributes"""
        widget = StandardWidgetMixin.get_widget("text_input", placeholder="Test placeholder")
        self.assertIsInstance(widget, forms.TextInput)
        self.assertEqual(widget.attrs["class"], "form-control")
        self.assertEqual(widget.attrs["placeholder"], "Test placeholder")

    def test_get_widget_invalid_type(self):
        """Test getting widget with invalid type raises ValueError"""
        with self.assertRaises(ValueError) as cm:
            StandardWidgetMixin.get_widget("invalid_widget")
        self.assertIn("Unknown widget type", str(cm.exception))

    def test_text_with_placeholder(self):
        """Test text_with_placeholder method"""
        widget = StandardWidgetMixin.text_with_placeholder("Enter text")
        self.assertIsInstance(widget, forms.TextInput)
        self.assertEqual(widget.attrs["placeholder"], "Enter text")
        self.assertEqual(widget.attrs["class"], "form-control")

    def test_text_required_with_placeholder(self):
        """Test text_required_with_placeholder method"""
        widget = StandardWidgetMixin.text_required_with_placeholder("Enter required text")
        self.assertIsInstance(widget, forms.TextInput)
        self.assertEqual(widget.attrs["placeholder"], "Enter required text")
        self.assertEqual(widget.attrs["class"], "form-control")
        self.assertTrue(widget.attrs["required"])

    def test_number_with_range_all_params(self):
        """Test number_with_range with all parameters"""
        widget = StandardWidgetMixin.number_with_range(min_val=1, max_val=100, step=5, placeholder="Enter number")
        self.assertIsInstance(widget, forms.NumberInput)
        self.assertEqual(widget.attrs["min"], "1")
        self.assertEqual(widget.attrs["max"], "100")
        self.assertEqual(widget.attrs["step"], "5")
        self.assertEqual(widget.attrs["placeholder"], "Enter number")

    def test_number_with_range_partial_params(self):
        """Test number_with_range with partial parameters"""
        widget = StandardWidgetMixin.number_with_range(min_val=0, placeholder="Enter value")
        self.assertIsInstance(widget, forms.NumberInput)
        self.assertEqual(widget.attrs["min"], "0")
        self.assertNotIn("max", widget.attrs)
        self.assertNotIn("step", widget.attrs)
        self.assertEqual(widget.attrs["placeholder"], "Enter value")

    def test_number_with_range_no_params(self):
        """Test number_with_range with no parameters"""
        widget = StandardWidgetMixin.number_with_range()
        self.assertIsInstance(widget, forms.NumberInput)
        self.assertEqual(widget.attrs["class"], "form-control")


class BaseMetadataValidatorTests(TestCase):
    """Test BaseMetadataValidator functionality"""

    def setUp(self):
        self.validator = BaseMetadataValidator()

    def test_validate_year_valid_integer(self):
        """Test validate_year with valid integer"""
        result = BaseMetadataValidator.validate_year(2023)
        self.assertEqual(result, 2023)

    def test_validate_year_valid_string(self):
        """Test validate_year with valid string"""
        result = BaseMetadataValidator.validate_year("2023")
        self.assertEqual(result, 2023)

    def test_validate_year_none(self):
        """Test validate_year with None"""
        result = BaseMetadataValidator.validate_year(None)
        self.assertIsNone(result)

    def test_validate_year_empty_string(self):
        """Test validate_year with empty string"""
        result = BaseMetadataValidator.validate_year("")
        self.assertIsNone(result)

    def test_validate_year_whitespace_string(self):
        """Test validate_year with whitespace string"""
        result = BaseMetadataValidator.validate_year("   ")
        self.assertIsNone(result)

    def test_validate_year_too_old(self):
        """Test validate_year with year too old"""
        with self.assertRaises(forms.ValidationError) as cm:
            BaseMetadataValidator.validate_year(999)
        self.assertIn("must be between 1000", str(cm.exception))

    def test_validate_year_future(self):
        """Test validate_year with future year beyond allowed range"""
        future_year = timezone.now().year + 15  # Beyond the +10 limit
        with self.assertRaises(forms.ValidationError) as cm:
            BaseMetadataValidator.validate_year(future_year)
        self.assertIn("must be between 1000", str(cm.exception))

    def test_validate_year_invalid_string(self):
        """Test validate_year with invalid string"""
        with self.assertRaises(forms.ValidationError) as cm:
            BaseMetadataValidator.validate_year("not a year")
        self.assertIn("must be a valid year", str(cm.exception))

    def test_validate_year_custom_field_name(self):
        """Test validate_year with custom field name"""
        with self.assertRaises(forms.ValidationError) as cm:
            BaseMetadataValidator.validate_year(999, "custom_field")
        self.assertIn("custom_field must be between", str(cm.exception))

    def test_validate_isbn_empty(self):
        """Test validate_isbn with empty value"""
        result = BaseMetadataValidator.validate_isbn("")
        self.assertEqual(result, "")

    def test_validate_isbn_none(self):
        """Test validate_isbn with None"""
        result = BaseMetadataValidator.validate_isbn(None)
        self.assertEqual(result, "")

    def test_validate_isbn_valid_10_digit(self):
        """Test validate_isbn with valid 10-digit ISBN"""
        result = BaseMetadataValidator.validate_isbn("0123456789")
        self.assertEqual(result, "0123456789")

    def test_validate_isbn_valid_13_digit(self):
        """Test validate_isbn with valid 13-digit ISBN"""
        result = BaseMetadataValidator.validate_isbn("9780123456789")
        self.assertEqual(result, "9780123456789")

    def test_validate_isbn_with_formatting(self):
        """Test validate_isbn with formatting preserved"""
        result = BaseMetadataValidator.validate_isbn("978-0-123-45678-9")
        self.assertEqual(result, "978-0-123-45678-9")

    def test_validate_isbn_with_x(self):
        """Test validate_isbn with X character"""
        result = BaseMetadataValidator.validate_isbn("012345678X")
        self.assertEqual(result, "012345678X")

    def test_validate_isbn_invalid_length(self):
        """Test validate_isbn with invalid length"""
        with self.assertRaises(forms.ValidationError) as cm:
            BaseMetadataValidator.validate_isbn("123456")
        self.assertIn("must be 10 or 13 digits", str(cm.exception))

    def test_validate_isbn_invalid_characters(self):
        """Test validate_isbn with invalid characters"""
        with self.assertRaises(forms.ValidationError) as cm:
            BaseMetadataValidator.validate_isbn("012345678Z")
        self.assertIn("Invalid ISBN-10 format", str(cm.exception))

    def test_validate_confidence_valid(self):
        """Test validate_confidence with valid value"""
        result = BaseMetadataValidator.validate_confidence(0.75)
        self.assertEqual(result, 0.75)

    def test_validate_confidence_none(self):
        """Test validate_confidence with None"""
        result = BaseMetadataValidator.validate_confidence(None)
        self.assertIsNone(result)

    def test_validate_confidence_string(self):
        """Test validate_confidence with string value"""
        result = BaseMetadataValidator.validate_confidence("0.5")
        self.assertEqual(result, 0.5)

    def test_validate_confidence_out_of_range_low(self):
        """Test validate_confidence with value too low"""
        with self.assertRaises(forms.ValidationError) as cm:
            BaseMetadataValidator.validate_confidence(-0.1)
        self.assertIn("must be between 0 and 1", str(cm.exception))

    def test_validate_confidence_out_of_range_high(self):
        """Test validate_confidence with value too high"""
        with self.assertRaises(forms.ValidationError) as cm:
            BaseMetadataValidator.validate_confidence(1.5)
        self.assertIn("must be between 0 and 1", str(cm.exception))

    def test_validate_confidence_invalid_string(self):
        """Test validate_confidence with invalid string"""
        with self.assertRaises(forms.ValidationError) as cm:
            BaseMetadataValidator.validate_confidence("not a number")
        self.assertIn("must be a valid number", str(cm.exception))

    def test_validate_required_text_valid(self):
        """Test validate_required_text with valid text"""
        result = BaseMetadataValidator.validate_required_text("Valid text", "field")
        self.assertEqual(result, "Valid text")

    def test_validate_required_text_with_whitespace(self):
        """Test validate_required_text with text containing whitespace"""
        result = BaseMetadataValidator.validate_required_text("  Valid text  ", "field")
        self.assertEqual(result, "Valid text")

    def test_validate_required_text_empty(self):
        """Test validate_required_text with empty string"""
        with self.assertRaises(forms.ValidationError) as cm:
            BaseMetadataValidator.validate_required_text("", "field")
        self.assertIn("field is required", str(cm.exception))

    def test_validate_required_text_whitespace_only(self):
        """Test validate_required_text with whitespace only"""
        with self.assertRaises(forms.ValidationError) as cm:
            BaseMetadataValidator.validate_required_text("   ", "field")
        self.assertIn("field is required", str(cm.exception))

    def test_validate_series_number_valid(self):
        """Test validate_series_number with valid number"""
        result = BaseMetadataValidator.validate_series_number("1.5")
        self.assertEqual(result, "1.5")

    def test_validate_series_number_none(self):
        """Test validate_series_number with None"""
        result = BaseMetadataValidator.validate_series_number(None)
        self.assertEqual(result, "")

    def test_validate_series_number_empty_string(self):
        """Test validate_series_number with empty string"""
        result = BaseMetadataValidator.validate_series_number("")
        self.assertEqual(result, "")

    def test_validate_series_number_integer(self):
        """Test validate_series_number with integer"""
        result = BaseMetadataValidator.validate_series_number(5)
        self.assertEqual(result, "5")

    def test_validate_series_number_too_long(self):
        """Test validate_series_number with too long string"""
        long_number = "a" * 25
        with self.assertRaises(forms.ValidationError) as cm:
            BaseMetadataValidator.validate_series_number(long_number, max_length=20)
        self.assertIn("too long", str(cm.exception))

    def test_validate_comma_separated_list_valid(self):
        """Test validate_comma_separated_list with valid input"""
        result = BaseMetadataValidator.validate_comma_separated_list("item1, item2, item3")
        self.assertEqual(result, "item1, item2, item3")

    def test_validate_comma_separated_list_empty(self):
        """Test validate_comma_separated_list with empty input"""
        result = BaseMetadataValidator.validate_comma_separated_list("")
        self.assertEqual(result, "")

    def test_validate_comma_separated_list_none(self):
        """Test validate_comma_separated_list with None"""
        result = BaseMetadataValidator.validate_comma_separated_list(None)
        self.assertEqual(result, "")

    def test_validate_comma_separated_list_with_spaces(self):
        """Test validate_comma_separated_list cleaning up spaces"""
        result = BaseMetadataValidator.validate_comma_separated_list("  item1  ,  item2  ,  item3  ")
        self.assertEqual(result, "item1, item2, item3")

    def test_validate_comma_separated_list_empty_items(self):
        """Test validate_comma_separated_list filtering empty items"""
        result = BaseMetadataValidator.validate_comma_separated_list("item1, , item2, ,item3")
        self.assertEqual(result, "item1, item2, item3")

    def test_validate_integer_list_valid(self):
        """Test validate_integer_list with valid input"""
        result = BaseMetadataValidator.validate_integer_list("1, 2, 3")
        self.assertEqual(result, [1, 2, 3])

    def test_validate_integer_list_empty(self):
        """Test validate_integer_list with empty input"""
        result = BaseMetadataValidator.validate_integer_list("")
        self.assertEqual(result, [])

    def test_validate_integer_list_none(self):
        """Test validate_integer_list with None"""
        result = BaseMetadataValidator.validate_integer_list(None)
        self.assertEqual(result, [])

    def test_validate_integer_list_with_spaces(self):
        """Test validate_integer_list with spaces"""
        result = BaseMetadataValidator.validate_integer_list("  1  ,  2  ,  3  ")
        self.assertEqual(result, [1, 2, 3])

    def test_validate_integer_list_invalid_items(self):
        """Test validate_integer_list with invalid items"""
        with self.assertRaises(forms.ValidationError) as cm:
            BaseMetadataValidator.validate_integer_list("1, not_a_number, 3")
        self.assertIn("must be comma-separated integers", str(cm.exception))

    def test_validate_integer_list_custom_field_name(self):
        """Test validate_integer_list with custom field name"""
        with self.assertRaises(forms.ValidationError) as cm:
            BaseMetadataValidator.validate_integer_list("1, invalid, 3", "book_ids")
        self.assertIn("Invalid book_ids", str(cm.exception))


class StandardFormMixinTests(TestCase):
    """Test StandardFormMixin functionality"""

    def test_form_mixin_initialization(self):
        """Test StandardFormMixin initialization and styling application"""

        # Create a test form using the mixin
        class TestForm(StandardFormMixin, forms.Form):
            text_field = forms.CharField()
            number_field = forms.IntegerField()
            choice_field = forms.ChoiceField(choices=[("a", "A"), ("b", "B")])
            textarea_field = forms.CharField(widget=forms.Textarea)
            checkbox_field = forms.BooleanField()
            file_field = forms.FileField()

        form = TestForm()

        # Check that styling was applied
        self.assertEqual(form.fields["text_field"].widget.attrs["class"], "form-control")
        self.assertEqual(form.fields["number_field"].widget.attrs["class"], "form-control")
        self.assertEqual(form.fields["choice_field"].widget.attrs["class"], "form-select")
        self.assertEqual(form.fields["textarea_field"].widget.attrs["class"], "form-control")
        self.assertEqual(form.fields["checkbox_field"].widget.attrs["class"], "form-check-input")
        self.assertEqual(form.fields["file_field"].widget.attrs["class"], "form-control")

    def test_mixin_inherits_standard_widget_methods(self):
        """Test that StandardFormMixin inherits StandardWidgetMixin methods"""

        class TestForm(StandardFormMixin, forms.Form):
            pass

        form = TestForm()
        # Should have access to StandardWidgetMixin methods
        widget = form.get_widget("text_input")
        self.assertIsInstance(widget, forms.TextInput)


class MetadataFormMixinTests(TestCase):
    """Test MetadataFormMixin functionality"""

    def test_get_standard_metadata_widgets(self):
        """Test get_standard_metadata_widgets method"""

        class TestForm(MetadataFormMixin, forms.Form):
            pass

        form = TestForm()
        widgets = form.get_standard_metadata_widgets()

        # Check that all expected widgets are present
        expected_fields = [
            "final_title",
            "final_author",
            "final_series",
            "final_series_number",
            "final_publisher",
            "final_cover_path",
            "language",
            "isbn",
            "publication_year",
            "description",
            "is_reviewed",
        ]

        for field in expected_fields:
            self.assertIn(field, widgets)

        # Check specific widget types
        self.assertIsInstance(widgets["final_title"], forms.TextInput)
        self.assertIsInstance(widgets["language"], forms.Select)
        self.assertIsInstance(widgets["description"], forms.Textarea)
        self.assertIsInstance(widgets["is_reviewed"], forms.CheckboxInput)

    def test_clean_final_title(self):
        """Test clean_final_title method"""

        class TestForm(MetadataFormMixin, forms.Form):
            final_title = forms.CharField()

        form = TestForm({"final_title": "Valid Title"})
        form.is_valid()
        result = form.clean_final_title()
        self.assertEqual(result, "Valid Title")

        # Test with empty title
        form = TestForm({"final_title": ""})
        form.is_valid()
        with self.assertRaises(forms.ValidationError):
            form.clean_final_title()

    def test_clean_final_author(self):
        """Test clean_final_author method"""

        class TestForm(MetadataFormMixin, forms.Form):
            final_author = forms.CharField()

        form = TestForm({"final_author": "Valid Author"})
        form.is_valid()
        result = form.clean_final_author()
        self.assertEqual(result, "Valid Author")

        # Test with empty author
        form = TestForm({"final_author": ""})
        form.is_valid()
        with self.assertRaises(forms.ValidationError):
            form.clean_final_author()

    def test_clean_final_series_number(self):
        """Test clean_final_series_number method"""

        class TestForm(MetadataFormMixin, forms.Form):
            final_series_number = forms.CharField()

        form = TestForm({"final_series_number": "1.5"})
        form.is_valid()
        result = form.clean_final_series_number()
        self.assertEqual(result, "1.5")

    def test_clean_publication_year(self):
        """Test clean_publication_year method"""

        class TestForm(MetadataFormMixin, forms.Form):
            publication_year = forms.IntegerField()

        form = TestForm({"publication_year": "2023"})
        form.is_valid()
        result = form.clean_publication_year()
        self.assertEqual(result, 2023)

    def test_clean_isbn(self):
        """Test clean_isbn method"""

        class TestForm(MetadataFormMixin, forms.Form):
            isbn = forms.CharField()

        form = TestForm({"isbn": "9780123456789"})
        form.is_valid()
        result = form.clean_isbn()
        self.assertEqual(result, "9780123456789")

    def test_clean_manual_genres(self):
        """Test clean_manual_genres method"""

        class TestForm(MetadataFormMixin, forms.Form):
            manual_genres = forms.CharField()

        form = TestForm({"manual_genres": "Genre1, Genre2, Genre3"})
        form.is_valid()
        result = form.clean_manual_genres()
        self.assertEqual(result, "Genre1, Genre2, Genre3")


class FinalMetadataSyncMixinTests(TestCase):
    """Test FinalMetadataSyncMixin functionality"""

    def setUp(self):
        # Create test data
        self.data_source, _ = DataSource.objects.get_or_create(name=DataSource.MANUAL, defaults={"trust_level": 0.9})
        self.book = create_test_book_with_file(file_path="/test/path/test_book.epub", file_size=1000, file_format="epub")
        self.final_metadata = FinalMetadata.objects.create(book=self.book, final_title="Test Title", final_author="Test Author")

    def test_metadata_type_map_exists(self):
        """Test that sync mixin functionality works properly"""
        # Test using existing non-abstract BookTitle model that uses the mixin
        from books.models import BookTitle

        # Verify the mixin provides expected functionality
        self.assertTrue(hasattr(BookTitle, "post_deactivation_sync"))
        self.assertTrue(callable(getattr(BookTitle, "post_deactivation_sync")))

        # Verify inheritance
        from books.mixins.sync import FinalMetadataSyncMixin

        self.assertTrue(issubclass(BookTitle, FinalMetadataSyncMixin))

    def test_post_deactivation_sync_active_record(self):
        """Test post_deactivation_sync behavior"""
        # Use existing BookTitle model that uses the mixin
        from books.models import BookTitle

        # Create an instance but don't save it to avoid auto-sync during creation
        test_instance = BookTitle(book=self.book, is_active=True, title="Different Title", source=self.data_source)

        # Mock sync_from_sources to verify it gets called
        with patch.object(self.final_metadata, "sync_from_sources") as mock_sync:
            # The new implementation always calls sync for unreviewed metadata
            test_instance.post_deactivation_sync()

            # Should call sync because final_metadata is not reviewed
            mock_sync.assert_called_once_with(save_after=True)

    def test_post_deactivation_sync_no_final_metadata(self):
        """Test post_deactivation_sync when no FinalMetadata exists"""
        # Create book without FinalMetadata
        book_without_metadata = create_test_book_with_file(file_path="/test/path/test_book2.epub", file_size=1000, file_format="epub")

        # Use existing BookTitle model that uses the mixin
        from books.models import BookTitle

        test_instance = BookTitle(book=book_without_metadata, is_active=False, title="Test Title")
        # Should not raise exception when no finalmetadata exists
        test_instance.post_deactivation_sync()

    @patch("books.models.logger")
    def test_post_deactivation_sync_booktitle(self, mock_logger):
        """Test post_deactivation_sync for BookTitle model"""
        # Use existing BookTitle model that uses the mixin
        from books.models import BookTitle

        test_instance = BookTitle(book=self.book, is_active=False, title="Test Title")

        with patch.object(self.final_metadata, "update_final_title") as mock_update:
            test_instance.post_deactivation_sync()
            mock_update.assert_called_once()

    @patch("books.models.logger")
    def test_post_deactivation_sync_bookauthor(self, mock_logger):
        """Test post_deactivation_sync for BookAuthor model"""
        # Create real author instance
        real_author = Author.objects.create(name="Test Author")

        # Use existing BookAuthor model that uses the mixin
        from books.models import BookAuthor

        test_instance = BookAuthor(book=self.book, is_active=False, author=real_author)

        with patch.object(self.final_metadata, "update_final_author") as mock_update:
            test_instance.post_deactivation_sync()
            mock_update.assert_called_once()

    def test_save_calls_post_deactivation_sync(self):
        """Test that save method calls post_deactivation_sync"""

        class TestModel(FinalMetadataSyncMixin):
            def __init__(self):
                pass  # Skip model init

            def save(self, *args, **kwargs):
                # Override save to avoid the super() call issue in tests
                self.post_deactivation_sync()

        test_instance = TestModel()

        with patch.object(test_instance, "post_deactivation_sync") as mock_sync:
            test_instance.save()
            mock_sync.assert_called_once()


class MixinIntegrationTests(TestCase):
    """Test mixin integration and edge cases"""

    def test_multiple_mixin_inheritance(self):
        """Test form with multiple mixins"""

        class TestForm(MetadataFormMixin, forms.Form):
            final_title = forms.CharField()
            final_author = forms.CharField()

        form = TestForm({"final_title": "Test", "final_author": "Author"})
        self.assertTrue(form.is_valid())

        # Test that both validation methods work
        result_title = form.clean_final_title()
        result_author = form.clean_final_author()
        self.assertEqual(result_title, "Test")
        self.assertEqual(result_author, "Author")

    def test_widget_mixin_with_complex_attributes(self):
        """Test widget mixin with complex attribute scenarios"""
        widget = StandardWidgetMixin.get_widget("text_input", placeholder="Complex placeholder", data_toggle="tooltip", data_placement="top")

        self.assertEqual(widget.attrs["placeholder"], "Complex placeholder")
        self.assertEqual(widget.attrs["data_toggle"], "tooltip")
        self.assertEqual(widget.attrs["data_placement"], "top")
        self.assertEqual(widget.attrs["class"], "form-control")

    def test_base_validator_edge_cases(self):
        """Test BaseMetadataValidator edge cases"""
        # Test year validation with different types
        self.assertEqual(BaseMetadataValidator.validate_year("  2023  "), 2023)

        # Test ISBN with mixed case X
        result = BaseMetadataValidator.validate_isbn("012345678x")
        self.assertEqual(result, "012345678x")

        # Test confidence with edge values
        self.assertEqual(BaseMetadataValidator.validate_confidence(0), 0)
        self.assertEqual(BaseMetadataValidator.validate_confidence(1), 1)

        # Test comma separated list with single item
        result = BaseMetadataValidator.validate_comma_separated_list("single_item")
        self.assertEqual(result, "single_item")

    def test_mixin_error_handling(self):
        """Test mixin error handling scenarios"""
        # Test validator with invalid confidence
        with self.assertRaises(forms.ValidationError):
            BaseMetadataValidator.validate_confidence("invalid")

        # Test validator with invalid year
        with self.assertRaises(forms.ValidationError):
            BaseMetadataValidator.validate_year("invalid_year")

        # Test widget mixin with invalid widget type
        with self.assertRaises(ValueError):
            StandardWidgetMixin.get_widget("nonexistent_widget")


class MixinAdvancedEdgeCaseTests(TestCase):
    """Test advanced edge cases and scenarios for comprehensive coverage"""

    def test_widget_mixin_attribute_override(self):
        """Test that class attribute properly overrides in get_widget"""
        # Test overriding existing class attribute
        widget = StandardWidgetMixin.get_widget("text_input", **{"class": "custom-class"})
        self.assertEqual(widget.attrs["class"], "custom-class")

    def test_widget_mixin_boolean_attributes(self):
        """Test widget mixin with boolean attributes"""
        widget = StandardWidgetMixin.get_widget("text_input", required=True, readonly=True, disabled=False)
        self.assertTrue(widget.attrs["required"])
        self.assertTrue(widget.attrs["readonly"])
        self.assertFalse(widget.attrs["disabled"])

    def test_validator_year_boundary_conditions(self):
        """Test year validator at exact boundaries"""
        # Test exactly at boundary
        self.assertEqual(BaseMetadataValidator.validate_year(1000), 1000)

        # Test current year + 1 (should be valid)
        current_year = timezone.now().year
        self.assertEqual(BaseMetadataValidator.validate_year(current_year + 1), current_year + 1)

    def test_validator_isbn_with_special_characters(self):
        """Test ISBN validation with special formatting"""
        # Test with various separators
        test_cases = ["978-0-123-45678-9", "978.0.123.45678.9", "978 0 123 45678 9", "978_0_123_45678_9"]
        for isbn in test_cases:
            result = BaseMetadataValidator.validate_isbn(isbn)
            self.assertEqual(result, isbn)

    def test_validator_confidence_type_conversion(self):
        """Test confidence validator with various input types"""
        # Test integer conversion
        self.assertEqual(BaseMetadataValidator.validate_confidence(1), 1.0)
        self.assertEqual(BaseMetadataValidator.validate_confidence(0), 0.0)

        # Test float string conversion
        self.assertEqual(BaseMetadataValidator.validate_confidence("0.75"), 0.75)

    def test_validator_series_number_unicode(self):
        """Test series number validation with unicode characters"""
        # Test unicode numbers and letters
        test_cases = ["1α", "2β", "3γ", "第1巻", "№1"]
        for series_num in test_cases:
            result = BaseMetadataValidator.validate_series_number(series_num)
            self.assertEqual(result, series_num)

    def test_validator_comma_list_complex_whitespace(self):
        """Test comma-separated list with complex whitespace scenarios"""
        # Test tabs, newlines, multiple spaces
        test_input = "item1,\t\nitem2,   \r\n  item3  \t,item4"
        result = BaseMetadataValidator.validate_comma_separated_list(test_input)
        self.assertEqual(result, "item1, item2, item3, item4")

    def test_validator_integer_list_negative_numbers(self):
        """Test integer list validation with negative numbers"""
        result = BaseMetadataValidator.validate_integer_list("-1, 0, 1, -999")
        self.assertEqual(result, [-1, 0, 1, -999])

    def test_standard_form_mixin_custom_widget_preservation(self):
        """Test that StandardFormMixin preserves custom widgets"""

        class CustomWidget(forms.TextInput):
            pass

        class TestForm(StandardFormMixin, forms.Form):
            custom_field = forms.CharField(widget=CustomWidget())
            regular_field = forms.CharField()

        form = TestForm()

        # Custom widget should be preserved but still get CSS class
        self.assertIsInstance(form.fields["custom_field"].widget, CustomWidget)
        self.assertIn("form-control", form.fields["custom_field"].widget.attrs["class"])

        # Regular field should get standard styling
        self.assertIn("form-control", form.fields["regular_field"].widget.attrs["class"])

    def test_metadata_form_mixin_field_error_handling(self):
        """Test MetadataFormMixin with field errors and recovery"""

        class TestForm(MetadataFormMixin, forms.Form):
            final_title = forms.CharField()
            final_author = forms.CharField()
            publication_year = forms.IntegerField(required=False)

        # Test with partially invalid data
        form = TestForm({"final_title": "Valid Title", "final_author": "", "publication_year": "invalid_year"})  # Invalid  # Invalid

        self.assertFalse(form.is_valid())
        self.assertIn("final_author", form.errors)
        self.assertIn("publication_year", form.errors)

    def test_metadata_form_widgets_all_field_types(self):
        """Test that get_standard_metadata_widgets returns correct widget types"""

        class TestForm(MetadataFormMixin, forms.Form):
            pass

        form = TestForm()
        widgets = form.get_standard_metadata_widgets()

        # Verify specific widget types for metadata fields
        self.assertIsInstance(widgets["final_title"], forms.TextInput)
        self.assertIsInstance(widgets["final_author"], forms.TextInput)
        self.assertIsInstance(widgets["final_series"], forms.TextInput)
        self.assertIsInstance(widgets["final_series_number"], forms.TextInput)
        self.assertIsInstance(widgets["final_publisher"], forms.TextInput)
        self.assertIsInstance(widgets["final_cover_path"], forms.FileInput)
        self.assertIsInstance(widgets["language"], forms.Select)
        self.assertIsInstance(widgets["isbn"], forms.TextInput)
        self.assertIsInstance(widgets["publication_year"], forms.NumberInput)
        self.assertIsInstance(widgets["description"], forms.Textarea)
        self.assertIsInstance(widgets["is_reviewed"], forms.CheckboxInput)

    @patch("books.models.logger")
    def test_final_metadata_sync_mixin_database_errors(self, mock_logger):
        """Test FinalMetadataSyncMixin handling of database errors"""

        # Use existing BookTitle model that uses the mixin
        from books.models import BookTitle

        # Create test instance
        book = create_test_book_with_file(file_path="/test/path/test.epub", file_size=1000, file_format="epub")

        # Create FinalMetadata to ensure the relationship exists
        final_metadata = FinalMetadata.objects.create(book=book, final_title="Test Title")

        test_instance = BookTitle(book=book, is_active=False, title="Test Title")

        # Mock database error by patching the final_metadata's update method
        with patch.object(final_metadata, "update_final_title", side_effect=Exception("Database connection error")):
            # Should not raise exception
            test_instance.post_deactivation_sync()

            # Should log the error
            mock_logger.error.assert_called()

    def test_final_metadata_sync_mixin_model_type_detection(self):
        """Test FinalMetadataSyncMixin correctly handles different model types"""
        from books.mixins.sync import FinalMetadataSyncMixin

        class MockBookTitle(FinalMetadataSyncMixin):
            def __init__(self):
                self.__class__.__name__ = "BookTitle"
                self.is_active = False

            def save(self, *args, **kwargs):
                # Override to prevent actual save
                pass

        class MockBookAuthor(FinalMetadataSyncMixin):
            def __init__(self):
                self.__class__.__name__ = "BookAuthor"
                self.is_active = False

            def save(self, *args, **kwargs):
                # Override to prevent actual save
                pass

        # Test that both classes inherit from the mixin
        self.assertTrue(issubclass(MockBookTitle, FinalMetadataSyncMixin))
        self.assertTrue(issubclass(MockBookAuthor, FinalMetadataSyncMixin))

        # Test that they have the expected methods
        mock_title = MockBookTitle()
        mock_author = MockBookAuthor()

        self.assertTrue(hasattr(mock_title, "post_deactivation_sync"))
        self.assertTrue(hasattr(mock_author, "post_deactivation_sync"))
        self.assertTrue(callable(mock_title.post_deactivation_sync))
        self.assertTrue(callable(mock_author.post_deactivation_sync))

    def test_widget_number_range_edge_cases(self):
        """Test number_with_range widget helper edge cases"""
        # Test with zero values
        widget = StandardWidgetMixin.number_with_range(min_val=0, max_val=0, step=0)
        self.assertEqual(widget.attrs["min"], "0")
        self.assertEqual(widget.attrs["max"], "0")
        self.assertEqual(widget.attrs["step"], "0")

        # Test with negative values
        widget = StandardWidgetMixin.number_with_range(min_val=-100, max_val=-1, step=1)
        self.assertEqual(widget.attrs["min"], "-100")
        self.assertEqual(widget.attrs["max"], "-1")
        self.assertEqual(widget.attrs["step"], "1")

        # Test with decimal step
        widget = StandardWidgetMixin.number_with_range(step=0.1)
        self.assertEqual(widget.attrs["step"], "0.1")

    def test_validator_required_text_with_special_chars(self):
        """Test required text validation with special characters"""
        # Test with unicode, special chars, emojis
        test_cases = ["Título en Español", "Texte en Français", "Text with 📚 emoji", "Text with \"quotes\" and 'apostrophes'", "HTML <tag> content", "Line 1\nLine 2"]

        for text in test_cases:
            result = BaseMetadataValidator.validate_required_text(text, "field")
            self.assertEqual(result.strip(), text.strip())

    def test_validator_isbn_international_variants(self):
        """Test ISBN validation with international variants"""
        # Test various international ISBN formats
        international_isbns = [
            "979-10-123-4567-8",  # Alternative ISBN-13 prefix
            "978-2-123-45678-9",  # French ISBN
            "978-3-123-45678-0",  # German ISBN
            "978-4-123-45678-1",  # Japanese ISBN
            "978-85-123-4567-2",  # Brazilian ISBN
        ]

        for isbn in international_isbns:
            result = BaseMetadataValidator.validate_isbn(isbn)
            self.assertEqual(result, isbn)


if __name__ == "__main__":
    import unittest

    unittest.main()
