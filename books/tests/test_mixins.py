"""
Test cases for form mixins and utilities
"""
from django.test import TestCase
from django import forms
from books.mixins import (
    StandardWidgetMixin, BaseMetadataValidator,
    StandardFormMixin
)
from books.models import Book, FinalMetadata, ScanFolder


class BaseMetadataValidatorTests(TestCase):
    """Test cases for BaseMetadataValidator mixin"""

    def test_validate_year(self):
        """Test year validation"""
        # Valid years
        self.assertEqual(BaseMetadataValidator.validate_year(2023), 2023)
        self.assertEqual(BaseMetadataValidator.validate_year('2023'), 2023)
        self.assertIsNone(BaseMetadataValidator.validate_year(''))
        self.assertIsNone(BaseMetadataValidator.validate_year(None))

        # Invalid years
        with self.assertRaises(forms.ValidationError):
            BaseMetadataValidator.validate_year(800)  # Too old (< 1000)

        with self.assertRaises(forms.ValidationError):
            BaseMetadataValidator.validate_year(2100)  # Too future

        with self.assertRaises(forms.ValidationError):
            BaseMetadataValidator.validate_year('invalid')  # Not a number

    def test_validate_isbn(self):
        """Test ISBN validation"""
        # Valid ISBNs
        self.assertEqual(BaseMetadataValidator.validate_isbn('978-0123456789'), '978-0123456789')
        self.assertEqual(BaseMetadataValidator.validate_isbn('9780123456789'), '9780123456789')
        self.assertEqual(BaseMetadataValidator.validate_isbn('0123456789'), '0123456789')
        self.assertEqual(BaseMetadataValidator.validate_isbn(''), '')

        # Invalid ISBNs
        with self.assertRaises(forms.ValidationError):
            BaseMetadataValidator.validate_isbn('123')  # Too short

        with self.assertRaises(forms.ValidationError):
            BaseMetadataValidator.validate_isbn('abcd123456')  # Contains letters

    def test_validate_confidence(self):
        """Test confidence validation"""
        # Valid confidence values
        self.assertEqual(BaseMetadataValidator.validate_confidence(0.0), 0.0)
        self.assertEqual(BaseMetadataValidator.validate_confidence(0.5), 0.5)
        self.assertEqual(BaseMetadataValidator.validate_confidence(1.0), 1.0)
        self.assertIsNone(BaseMetadataValidator.validate_confidence(None))

        # Invalid confidence values
        with self.assertRaises(forms.ValidationError):
            BaseMetadataValidator.validate_confidence(-0.1)  # Too low

        with self.assertRaises(forms.ValidationError):
            BaseMetadataValidator.validate_confidence(1.1)  # Too high

        with self.assertRaises(forms.ValidationError):
            BaseMetadataValidator.validate_confidence('invalid')

    def test_validate_required_text(self):
        """Test required text validation"""
        # Valid text
        self.assertEqual(BaseMetadataValidator.validate_required_text('Valid Text', 'field'), 'Valid Text')
        self.assertEqual(BaseMetadataValidator.validate_required_text('  Trimmed  ', 'field'), 'Trimmed')

        # Invalid text
        with self.assertRaises(forms.ValidationError):
            BaseMetadataValidator.validate_required_text('', 'field')

        with self.assertRaises(forms.ValidationError):
            BaseMetadataValidator.validate_required_text('   ', 'field')

        with self.assertRaises(forms.ValidationError):
            BaseMetadataValidator.validate_required_text(None, 'field')

    def test_validate_series_number(self):
        """Test series number validation"""
        # Valid series numbers
        self.assertEqual(BaseMetadataValidator.validate_series_number('1'), '1')
        self.assertEqual(BaseMetadataValidator.validate_series_number('1.5'), '1.5')
        self.assertEqual(BaseMetadataValidator.validate_series_number('2a'), '2a')
        self.assertEqual(BaseMetadataValidator.validate_series_number(''), '')
        self.assertEqual(BaseMetadataValidator.validate_series_number(None), '')

        # Invalid series numbers (too long)
        with self.assertRaises(forms.ValidationError):
            BaseMetadataValidator.validate_series_number('x' * 25, max_length=20)

    def test_validate_comma_separated_list(self):
        """Test comma-separated list validation"""
        # Valid lists
        self.assertEqual(BaseMetadataValidator.validate_comma_separated_list('a, b, c'), 'a, b, c')
        self.assertEqual(BaseMetadataValidator.validate_comma_separated_list('single'), 'single')
        self.assertEqual(BaseMetadataValidator.validate_comma_separated_list(''), '')
        self.assertEqual(BaseMetadataValidator.validate_comma_separated_list(None), '')

        # Test cleanup
        self.assertEqual(BaseMetadataValidator.validate_comma_separated_list('  a  ,  b  ,  c  '), 'a, b, c')

    def test_validate_integer_list(self):
        """Test integer list validation"""
        # Valid integer lists
        result = BaseMetadataValidator.validate_integer_list('1,2,3,4,5')
        self.assertEqual(result, [1, 2, 3, 4, 5])

        result = BaseMetadataValidator.validate_integer_list('42')
        self.assertEqual(result, [42])

        result = BaseMetadataValidator.validate_integer_list('')
        self.assertEqual(result, [])

        # Invalid integer lists
        with self.assertRaises(forms.ValidationError):
            BaseMetadataValidator.validate_integer_list('1,2,invalid,4')


class StandardWidgetMixinTests(TestCase):
    """Test cases for StandardWidgetMixin"""

    def test_get_widget(self):
        """Test widget retrieval"""
        # Test basic widget retrieval
        widget = StandardWidgetMixin.get_widget('text_input')
        self.assertIsInstance(widget, forms.TextInput)
        self.assertIn('form-control', widget.attrs.get('class', ''))

        # Test widget with extra attributes
        widget = StandardWidgetMixin.get_widget('text_input', placeholder='Test placeholder')
        self.assertEqual(widget.attrs.get('placeholder'), 'Test placeholder')

        # Test invalid widget type
        with self.assertRaises(ValueError):
            StandardWidgetMixin.get_widget('invalid_widget_type')

    def test_text_with_placeholder(self):
        """Test text widget with placeholder helper"""
        widget = StandardWidgetMixin.text_with_placeholder('Enter text here')
        self.assertIsInstance(widget, forms.TextInput)
        self.assertEqual(widget.attrs.get('placeholder'), 'Enter text here')
        self.assertIn('form-control', widget.attrs.get('class', ''))

    def test_number_with_range(self):
        """Test number widget with range helper"""
        widget = StandardWidgetMixin.number_with_range(min_val=0, max_val=100, step=5)
        self.assertIsInstance(widget, forms.NumberInput)
        self.assertEqual(widget.attrs.get('min'), '0')
        self.assertEqual(widget.attrs.get('max'), '100')
        self.assertEqual(widget.attrs.get('step'), '5')


class MetadataFormMixinTests(TestCase):
    """Test cases for MetadataFormMixin functionality"""

    def setUp(self):
        """Set up test data"""
        self.scan_folder = ScanFolder.objects.create(
            path="/test/scan/folder",
            name="Test Scan Folder"
        )

        self.book = Book.objects.create(
            file_path="/test/path/book.epub",
            file_format="epub",
            file_size=1024000,
            scan_folder=self.scan_folder
        )

        self.final_metadata = FinalMetadata.objects.create(
            book=self.book,
            final_title="Test Title",
            final_author="Test Author",
            is_reviewed=False
        )

    def test_metadata_form_mixin_integration(self):
        """Test that MetadataFormMixin integrates properly"""
        from books.forms import MetadataReviewForm

        form = MetadataReviewForm(instance=self.final_metadata)

        # Check that mixin methods are available
        self.assertTrue(hasattr(form, 'get_standard_metadata_widgets'))
        self.assertTrue(hasattr(form, 'validate_required_text'))
        self.assertTrue(hasattr(form, 'validate_year'))
        self.assertTrue(hasattr(form, 'validate_isbn'))

    def test_standard_metadata_widgets(self):
        """Test standard metadata widget generation"""
        from books.forms import MetadataReviewForm

        form = MetadataReviewForm(instance=self.final_metadata)
        widgets = form.get_standard_metadata_widgets()

        # Check that standard widgets are generated
        self.assertIn('final_title', widgets)
        self.assertIn('final_author', widgets)
        self.assertIn('publication_year', widgets)
        self.assertIn('isbn', widgets)
        self.assertIn('language', widgets)

        # Check widget types
        self.assertIsInstance(widgets['final_title'], forms.TextInput)
        self.assertIsInstance(widgets['publication_year'], forms.NumberInput)


class StandardFormMixinTests(TestCase):
    """Test cases for StandardFormMixin functionality"""

    def test_form_styling_application(self):
        """Test that StandardFormMixin applies styling correctly"""

        class TestForm(StandardFormMixin, forms.Form):
            text_field = forms.CharField()
            choice_field = forms.ChoiceField(choices=[('a', 'A'), ('b', 'B')])
            number_field = forms.IntegerField()

        form = TestForm()

        # Check that styling was applied
        self.assertIn('form-control', form.fields['text_field'].widget.attrs.get('class', ''))
        self.assertIn('form-select', form.fields['choice_field'].widget.attrs.get('class', ''))
        self.assertIn('form-control', form.fields['number_field'].widget.attrs.get('class', ''))

    def test_mixin_inheritance_chain(self):
        """Test that mixin inheritance works properly"""

        class TestForm(StandardFormMixin, forms.Form):
            pass

        form = TestForm()

        # Should have both StandardFormMixin and StandardWidgetMixin methods
        self.assertTrue(hasattr(form, 'apply_standard_styling'))
        self.assertTrue(hasattr(form, 'get_widget'))
        self.assertTrue(hasattr(form, 'text_with_placeholder'))
