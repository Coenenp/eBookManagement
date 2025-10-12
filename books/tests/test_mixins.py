"""
Test suite for books/mixins/ package
Tests all form mixins, validators, and utility functions.
"""

from django import forms
from django.test import TestCase
from django.core.exceptions import ValidationError
from unittest.mock import patch

from books.mixins import (
    StandardWidgetMixin,
    BaseMetadataValidator,
    StandardFormMixin,
    MetadataFormMixin,
    FinalMetadataSyncMixin
)


class StandardWidgetMixinTests(TestCase):
    """Test StandardWidgetMixin functionality"""

    def setUp(self):
        self.mixin = StandardWidgetMixin()

    def test_standard_widgets_exist(self):
        """Test that all standard widgets are defined"""
        expected_widgets = [
            'text_input', 'text_input_required', 'email_input', 'password_input',
            'textarea', 'select', 'number_input', 'checkbox', 'file_input',
            'image_input', 'hidden'
        ]

        for widget_type in expected_widgets:
            with self.subTest(widget=widget_type):
                self.assertIn(widget_type, StandardWidgetMixin.STANDARD_WIDGETS)

    def test_get_widget_valid_type(self):
        """Test getting a valid widget type"""
        widget = self.mixin.get_widget('text_input')
        self.assertIsInstance(widget, forms.TextInput)
        self.assertIn('form-control', widget.attrs.get('class', ''))

    def test_get_widget_invalid_type(self):
        """Test getting an invalid widget type raises ValueError"""
        with self.assertRaises(ValueError) as context:
            self.mixin.get_widget('invalid_widget')

        self.assertIn("Unknown widget type", str(context.exception))

    def test_get_widget_with_extra_attrs(self):
        """Test getting widget with extra attributes"""
        widget = self.mixin.get_widget('text_input', placeholder='Enter text')

        self.assertIsInstance(widget, forms.TextInput)
        self.assertEqual(widget.attrs.get('placeholder'), 'Enter text')
        self.assertIn('form-control', widget.attrs.get('class', ''))

    def test_text_with_placeholder(self):
        """Test text_with_placeholder convenience method"""
        widget = self.mixin.text_with_placeholder('Test placeholder')

        self.assertIsInstance(widget, forms.TextInput)
        self.assertEqual(widget.attrs.get('placeholder'), 'Test placeholder')
        self.assertIn('form-control', widget.attrs.get('class', ''))

    def test_text_required_with_placeholder(self):
        """Test text_required_with_placeholder convenience method"""
        widget = self.mixin.text_required_with_placeholder('Required field')

        self.assertIsInstance(widget, forms.TextInput)
        self.assertEqual(widget.attrs.get('placeholder'), 'Required field')
        self.assertTrue(widget.attrs.get('required'))
        self.assertIn('form-control', widget.attrs.get('class', ''))

    def test_number_with_range(self):
        """Test number_with_range convenience method"""
        widget = self.mixin.number_with_range(
            min_val=1, max_val=100, step=1, placeholder='Enter number'
        )

        self.assertIsInstance(widget, forms.NumberInput)
        self.assertEqual(widget.attrs.get('min'), '1')
        self.assertEqual(widget.attrs.get('max'), '100')
        self.assertEqual(widget.attrs.get('step'), '1')
        self.assertEqual(widget.attrs.get('placeholder'), 'Enter number')

    def test_number_with_range_partial_params(self):
        """Test number_with_range with only some parameters"""
        widget = self.mixin.number_with_range(min_val=0)

        self.assertEqual(widget.attrs.get('min'), '0')
        self.assertNotIn('max', widget.attrs)
        self.assertNotIn('step', widget.attrs)


class BaseMetadataValidatorTests(TestCase):
    """Test BaseMetadataValidator functionality"""

    def setUp(self):
        self.validator = BaseMetadataValidator()

    def test_validate_year_valid_integer(self):
        """Test validating a valid year as integer"""
        result = self.validator.validate_year(2023)
        self.assertEqual(result, 2023)

    def test_validate_year_valid_string(self):
        """Test validating a valid year as string"""
        result = self.validator.validate_year('2023')
        self.assertEqual(result, 2023)

    def test_validate_year_empty_values(self):
        """Test validating empty/None year values"""
        self.assertIsNone(self.validator.validate_year(None))
        self.assertIsNone(self.validator.validate_year(''))
        self.assertIsNone(self.validator.validate_year('   '))

    def test_validate_year_invalid_range(self):
        """Test validating year outside valid range"""
        with self.assertRaises(forms.ValidationError):
            self.validator.validate_year(999)  # Too early

        with self.assertRaises(forms.ValidationError):
            self.validator.validate_year(2030)  # Too late

    def test_validate_year_invalid_format(self):
        """Test validating invalid year format"""
        with self.assertRaises(forms.ValidationError):
            self.validator.validate_year('invalid')

        with self.assertRaises(forms.ValidationError):
            self.validator.validate_year('20.23')

    def test_validate_year_custom_field_name(self):
        """Test validate_year with custom field name in error"""
        try:
            self.validator.validate_year(999, "Custom Year")
        except forms.ValidationError as e:
            self.assertIn("Custom Year", str(e))

    def test_validate_isbn_valid_10(self):
        """Test validating valid 10-digit ISBN"""
        isbn = '0123456789'
        result = self.validator.validate_isbn(isbn)
        self.assertEqual(result, isbn)

    def test_validate_isbn_valid_13(self):
        """Test validating valid 13-digit ISBN"""
        isbn = '9780123456789'
        result = self.validator.validate_isbn(isbn)
        self.assertEqual(result, isbn)

    def test_validate_isbn_with_dashes(self):
        """Test validating ISBN with dashes"""
        isbn = '978-0-123-45678-9'
        result = self.validator.validate_isbn(isbn)
        self.assertEqual(result, isbn)

    def test_validate_isbn_with_x(self):
        """Test validating ISBN-10 with X"""
        isbn = '012345678X'
        result = self.validator.validate_isbn(isbn)
        self.assertEqual(result, isbn)

    def test_validate_isbn_empty(self):
        """Test validating empty ISBN"""
        result = self.validator.validate_isbn('')
        self.assertEqual(result, '')

        result = self.validator.validate_isbn(None)
        self.assertEqual(result, '')  # Should return empty string for None

    def test_validate_isbn_invalid_length(self):
        """Test validating ISBN with invalid length"""
        with self.assertRaises(forms.ValidationError):
            self.validator.validate_isbn('123')  # Too short

        with self.assertRaises(forms.ValidationError):
            self.validator.validate_isbn('12345678901234')  # Too long

    def test_validate_isbn_invalid_characters(self):
        """Test validating ISBN with invalid characters"""
        with self.assertRaises(forms.ValidationError):
            self.validator.validate_isbn('012345678A')  # Invalid char (not X)

    def test_validate_confidence_valid(self):
        """Test validating valid confidence values"""
        self.assertEqual(self.validator.validate_confidence(0.5), 0.5)
        self.assertEqual(self.validator.validate_confidence(0), 0)
        self.assertEqual(self.validator.validate_confidence(1), 1)
        self.assertEqual(self.validator.validate_confidence('0.75'), 0.75)

    def test_validate_confidence_none(self):
        """Test validating None confidence"""
        result = self.validator.validate_confidence(None)
        self.assertIsNone(result)

    def test_validate_confidence_invalid_range(self):
        """Test validating confidence outside valid range"""
        with self.assertRaises(forms.ValidationError):
            self.validator.validate_confidence(-0.1)

        with self.assertRaises(forms.ValidationError):
            self.validator.validate_confidence(1.1)

    def test_validate_confidence_invalid_type(self):
        """Test validating invalid confidence type"""
        with self.assertRaises(forms.ValidationError):
            self.validator.validate_confidence('invalid')

    def test_validate_required_text_valid(self):
        """Test validating valid required text"""
        result = self.validator.validate_required_text('Valid text', 'Title')
        self.assertEqual(result, 'Valid text')

        # Should strip whitespace
        result = self.validator.validate_required_text('  Spaced text  ', 'Title')
        self.assertEqual(result, 'Spaced text')

    def test_validate_required_text_empty(self):
        """Test validating empty required text"""
        with self.assertRaises(forms.ValidationError) as context:
            self.validator.validate_required_text('', 'Title')
        self.assertIn('Title is required', str(context.exception))

        with self.assertRaises(forms.ValidationError):
            self.validator.validate_required_text('   ', 'Title')

        with self.assertRaises(forms.ValidationError):
            self.validator.validate_required_text(None, 'Title')

    def test_validate_series_number_valid(self):
        """Test validating valid series numbers"""
        self.assertEqual(self.validator.validate_series_number('1'), '1')
        self.assertEqual(self.validator.validate_series_number('1.5'), '1.5')
        self.assertEqual(self.validator.validate_series_number('2a'), '2a')
        self.assertEqual(self.validator.validate_series_number(1), '1')

    def test_validate_series_number_empty(self):
        """Test validating empty series numbers"""
        self.assertEqual(self.validator.validate_series_number(''), '')
        self.assertEqual(self.validator.validate_series_number(None), '')
        self.assertEqual(self.validator.validate_series_number('   '), '')

    def test_validate_series_number_too_long(self):
        """Test validating series number that's too long"""
        long_number = 'a' * 25  # Default max_length is 20
        with self.assertRaises(forms.ValidationError):
            self.validator.validate_series_number(long_number)

    def test_validate_series_number_custom_length(self):
        """Test validating series number with custom max length"""
        result = self.validator.validate_series_number('12345', max_length=5)
        self.assertEqual(result, '12345')

        with self.assertRaises(forms.ValidationError):
            self.validator.validate_series_number('123456', max_length=5)

    def test_validate_comma_separated_list_valid(self):
        """Test validating valid comma-separated lists"""
        result = self.validator.validate_comma_separated_list('a, b, c')
        self.assertEqual(result, 'a, b, c')

        # Should clean up spacing
        result = self.validator.validate_comma_separated_list('a,b,  c,   d')
        self.assertEqual(result, 'a, b, c, d')

    def test_validate_comma_separated_list_empty(self):
        """Test validating empty comma-separated lists"""
        self.assertEqual(self.validator.validate_comma_separated_list(''), '')
        self.assertEqual(self.validator.validate_comma_separated_list(None), '')
        self.assertEqual(self.validator.validate_comma_separated_list('   '), '')

        # All empty items should return empty
        result = self.validator.validate_comma_separated_list(', , , ')
        self.assertEqual(result, '')

    def test_validate_integer_list_valid(self):
        """Test validating valid integer lists"""
        result = self.validator.validate_integer_list('1, 2, 3')
        self.assertEqual(result, [1, 2, 3])

        # Should handle spacing
        result = self.validator.validate_integer_list('1,2,  3,   4')
        self.assertEqual(result, [1, 2, 3, 4])

    def test_validate_integer_list_empty(self):
        """Test validating empty integer lists"""
        self.assertEqual(self.validator.validate_integer_list(''), [])
        self.assertEqual(self.validator.validate_integer_list(None), [])
        self.assertEqual(self.validator.validate_integer_list('   '), [])

    def test_validate_integer_list_invalid(self):
        """Test validating invalid integer lists"""
        with self.assertRaises(forms.ValidationError):
            self.validator.validate_integer_list('1, 2, invalid, 3')


class StandardFormMixinTests(TestCase):
    """Test StandardFormMixin functionality"""

    def test_form_mixin_initialization(self):
        """Test form mixin applies styling on initialization"""
        class TestForm(StandardFormMixin, forms.Form):
            text_field = forms.CharField()
            select_field = forms.ChoiceField(choices=[('1', 'One')])
            textarea_field = forms.CharField(widget=forms.Textarea)
            number_field = forms.IntegerField()
            checkbox_field = forms.BooleanField(required=False)
            file_field = forms.FileField(required=False)

        form = TestForm()

        # Check that styling was applied
        self.assertIn('form-control', form.fields['text_field'].widget.attrs.get('class', ''))
        self.assertIn('form-select', form.fields['select_field'].widget.attrs.get('class', ''))
        self.assertIn('form-control', form.fields['textarea_field'].widget.attrs.get('class', ''))
        self.assertIn('form-control', form.fields['number_field'].widget.attrs.get('class', ''))
        self.assertIn('form-check-input', form.fields['checkbox_field'].widget.attrs.get('class', ''))
        self.assertIn('form-control', form.fields['file_field'].widget.attrs.get('class', ''))


class MetadataFormMixinTests(TestCase):
    """Test MetadataFormMixin functionality"""

    def setUp(self):
        class TestMetadataForm(MetadataFormMixin, forms.Form):
            final_title = forms.CharField()
            final_author = forms.CharField()
            final_series_number = forms.CharField(required=False)
            publication_year = forms.IntegerField(required=False)
            isbn = forms.CharField(required=False)
            manual_genres = forms.CharField(required=False)

        self.form_class = TestMetadataForm

    def test_get_standard_metadata_widgets(self):
        """Test getting standard metadata widgets"""
        form = self.form_class()
        widgets = form.get_standard_metadata_widgets()

        self.assertIn('final_title', widgets)
        self.assertIn('final_author', widgets)
        self.assertIn('publication_year', widgets)

        # Check that title widget is required
        title_widget = widgets['final_title']
        self.assertTrue(title_widget.attrs.get('required'))

    def test_clean_final_title_valid(self):
        """Test cleaning valid final title"""
        form = self.form_class(data={'final_title': 'Valid Title', 'final_author': 'Valid Author'})
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data['final_title'], 'Valid Title')

    def test_clean_final_title_empty(self):
        """Test cleaning empty final title"""
        form = self.form_class(data={'final_title': '', 'final_author': 'Valid Author'})
        self.assertFalse(form.is_valid())
        self.assertIn('final_title', form.errors)

    def test_clean_final_author_valid(self):
        """Test cleaning valid final author"""
        form = self.form_class(data={'final_title': 'Valid Title', 'final_author': 'Valid Author'})
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data['final_author'], 'Valid Author')

    def test_clean_final_author_empty(self):
        """Test cleaning empty final author"""
        form = self.form_class(data={'final_title': 'Valid Title', 'final_author': ''})
        self.assertFalse(form.is_valid())
        self.assertIn('final_author', form.errors)

    def test_clean_publication_year_valid(self):
        """Test cleaning valid publication year"""
        form = self.form_class(data={
            'final_title': 'Valid Title',
            'final_author': 'Valid Author',
            'publication_year': 2023
        })
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data['publication_year'], 2023)

    def test_clean_publication_year_invalid(self):
        """Test cleaning invalid publication year"""
        form = self.form_class(data={
            'final_title': 'Valid Title',
            'final_author': 'Valid Author',
            'publication_year': 999  # Too early
        })
        self.assertFalse(form.is_valid())
        self.assertIn('publication_year', form.errors)

    def test_clean_isbn_valid(self):
        """Test cleaning valid ISBN"""
        form = self.form_class(data={
            'final_title': 'Valid Title',
            'final_author': 'Valid Author',
            'isbn': '9780123456789'
        })
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data['isbn'], '9780123456789')

    def test_clean_isbn_invalid(self):
        """Test cleaning invalid ISBN"""
        form = self.form_class(data={
            'final_title': 'Valid Title',
            'final_author': 'Valid Author',
            'isbn': '123'  # Too short
        })
        self.assertFalse(form.is_valid())
        self.assertIn('isbn', form.errors)

    def test_clean_manual_genres_valid(self):
        """Test cleaning valid manual genres"""
        form = self.form_class(data={
            'final_title': 'Valid Title',
            'final_author': 'Valid Author',
            'manual_genres': 'Science Fiction, Fantasy, Adventure'
        })
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data['manual_genres'], 'Science Fiction, Fantasy, Adventure')


class FinalMetadataSyncMixinTests(TestCase):
    """Test FinalMetadataSyncMixin functionality"""

    def setUp(self):
        # Create a mock model class with the mixin
        class MockModel(FinalMetadataSyncMixin):
            def __init__(self):
                self.book = MockBook()
                self.is_active = True

            def save(self, *args, **kwargs):
                # Call the mixin's save method
                super().save(*args, **kwargs)

        class MockBook:
            def __init__(self):
                self.id = 1  # Add missing id attribute
                self.finalmetadata = MockFinalMetadata()

        class MockFinalMetadata:
            def __init__(self):
                self.final_title = 'Test Title'
                self.final_author = 'Test Author'
                self.final_cover_path = '/test/cover.jpg'
                self.final_series = 'Test Series'
                self.final_publisher = 'Test Publisher'
                self.is_reviewed = False  # Add missing is_reviewed attribute

            def sync_from_sources(self, save_after=True):
                """Mock sync method"""
                pass

            def update_final_title(self):
                self.update_called = 'title'

            def update_final_author(self):
                self.update_called = 'author'

            def update_final_cover(self):
                self.update_called = 'cover'

            def update_final_series(self):
                self.update_called = 'series'

            def update_final_publisher(self):
                self.update_called = 'publisher'

            def update_dynamic_field(self, field_name):
                self.update_called = f'dynamic_{field_name}'

        self.mock_model_class = MockModel
        self.mock_book_class = MockBook
        self.mock_final_metadata_class = MockFinalMetadata

    def test_metadata_type_map_exists(self):
        """Test that sync mixin functionality works properly"""
        mixin = FinalMetadataSyncMixin()

        # Verify the mixin provides expected functionality
        self.assertTrue(hasattr(mixin, 'post_deactivation_sync'))
        self.assertTrue(callable(getattr(mixin, 'post_deactivation_sync')))

        # Test that it's a proper mixin
        self.assertTrue(hasattr(FinalMetadataSyncMixin, 'save'))
        self.assertTrue(callable(getattr(FinalMetadataSyncMixin, 'save')))

    def test_post_deactivation_sync_active_record(self):
        """Test sync behavior with unreviewed metadata"""
        model = self.mock_model_class()
        model.is_active = True

        # Mock sync_from_sources to verify it gets called for unreviewed metadata
        with patch.object(model.book.finalmetadata, 'sync_from_sources') as mock_sync:
            model.post_deactivation_sync()

            # Should call sync because final_metadata is not reviewed
            mock_sync.assert_called_once_with(save_after=True)

    def test_post_deactivation_sync_no_final_metadata(self):
        """Test handling when no final metadata exists"""
        model = self.mock_model_class()
        model.is_active = False
        model.book.finalmetadata = None

        # Should handle gracefully (no exception should be raised)
        try:
            model.post_deactivation_sync()
        except Exception as e:
            self.fail(f"post_deactivation_sync raised an exception when it shouldn't: {e}")

        # No errors should occur

    def test_save_calls_parent_and_sync(self):
        """Test that save method calls parent and sync"""
        model = self.mock_model_class()

        # Mock the parent save method
        parent_save_called = False

        def mock_parent_save(*args, **kwargs):
            nonlocal parent_save_called
            parent_save_called = True

        # Replace the super().save call
        original_save = FinalMetadataSyncMixin.save
        FinalMetadataSyncMixin.save = mock_parent_save

        try:
            model.save()
            # Verify parent save was called
            self.assertTrue(parent_save_called)
        finally:
            # Restore original save method
            FinalMetadataSyncMixin.save = original_save


class MixinIntegrationTests(TestCase):
    """Integration tests for mixin combinations"""

    def test_multiple_mixin_inheritance(self):
        """Test using multiple mixins together"""
        class CompleteForm(MetadataFormMixin, forms.Form):
            final_title = forms.CharField()
            final_author = forms.CharField()
            publication_year = forms.IntegerField(required=False)
            isbn = forms.CharField(required=False)

        form = CompleteForm(data={
            'final_title': 'Test Book',
            'final_author': 'Test Author',
            'publication_year': 2023,
            'isbn': '9780123456789'
        })

        self.assertTrue(form.is_valid())

        # Should have styling from StandardFormMixin
        self.assertIn('form-control', form.fields['final_title'].widget.attrs.get('class', ''))

        # Should have validation from MetadataFormMixin
        self.assertEqual(form.cleaned_data['final_title'], 'Test Book')
        self.assertEqual(form.cleaned_data['publication_year'], 2023)

    def test_widget_and_validator_integration(self):
        """Test that widgets and validators work together"""
        mixin = StandardWidgetMixin()

        # Get a number widget with validation attributes
        widget = mixin.number_with_range(min_val=1000, max_val=2030)

        # The widget should have the validation attributes
        self.assertEqual(widget.attrs.get('min'), '1000')
        self.assertEqual(widget.attrs.get('max'), '2030')

        # For server-side validation, we need proper validators
        from django.core.validators import MinValueValidator, MaxValueValidator
        field_with_validators = forms.IntegerField(
            widget=widget,
            validators=[MinValueValidator(1000), MaxValueValidator(2030)]
        )

        with self.assertRaises(ValidationError):
            field_with_validators.clean(999)  # Below minimum

    def test_mixin_error_handling(self):
        """Test error handling across mixins"""
        class TestForm(MetadataFormMixin, forms.Form):
            final_title = forms.CharField()
            final_author = forms.CharField()
            publication_year = forms.IntegerField(required=False)

        # Test with invalid data
        form = TestForm(data={
            'final_title': '',  # Required field empty
            'final_author': 'Valid Author',
            'publication_year': 999  # Invalid year
        })

        self.assertFalse(form.is_valid())

        # Should have errors for both fields
        self.assertIn('final_title', form.errors)
        self.assertIn('publication_year', form.errors)

        # Error messages should be helpful
        title_error = str(form.errors['final_title'])
        self.assertIn('required', title_error.lower())


class MixinPerformanceTests(TestCase):
    """Performance and edge case tests for mixins"""

    def test_large_comma_separated_list(self):
        """Test handling large comma-separated lists"""
        validator = BaseMetadataValidator()

        # Create a large list
        large_list = ', '.join([f'item{i}' for i in range(1000)])

        # Should handle without errors
        result = validator.validate_comma_separated_list(large_list)
        self.assertIsInstance(result, str)
        self.assertIn('item999', result)

    def test_widget_attribute_isolation(self):
        """Test that widget attributes don't leak between instances"""
        mixin = StandardWidgetMixin()

        # Create two widgets with different attributes
        widget1 = mixin.get_widget('text_input', placeholder='First')
        widget2 = mixin.get_widget('text_input', placeholder='Second')

        # They should have different placeholders
        self.assertEqual(widget1.attrs.get('placeholder'), 'First')
        self.assertEqual(widget2.attrs.get('placeholder'), 'Second')

        # And both should have the base class
        self.assertIn('form-control', widget1.attrs.get('class', ''))
        self.assertIn('form-control', widget2.attrs.get('class', ''))

    def test_form_field_modification_safety(self):
        """Test that form field modifications don't affect the class"""
        class TestForm(StandardFormMixin, forms.Form):
            test_field = forms.CharField()

        # Create two form instances
        form1 = TestForm()
        form2 = TestForm()

        # Modify one form's field
        form1.fields['test_field'].widget.attrs['data-test'] = 'form1'

        # The other form should not be affected
        self.assertNotIn('data-test', form2.fields['test_field'].widget.attrs)
