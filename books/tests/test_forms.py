"""
Test cases for form validation and functionality
"""
from django.test import TestCase
from django import forms
from books.forms import MetadataReviewForm
from books.models import Book, FinalMetadata, ScanFolder


class MetadataReviewFormTests(TestCase):
    """Test cases for MetadataReviewForm"""

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
            final_title="Test Book",
            final_author="Test Author",
            is_reviewed=False
        )

    def test_form_initialization(self):
        """Test form initializes correctly with instance"""
        form = MetadataReviewForm(instance=self.final_metadata)

        # Check that form has the required fields
        self.assertIn('final_title', form.fields)
        self.assertIn('final_author', form.fields)
        self.assertIn('publication_year', form.fields)
        self.assertIn('isbn', form.fields)
        self.assertIn('language', form.fields)
        self.assertIn('description', form.fields)
        self.assertIn('is_reviewed', form.fields)

    def test_form_validation_valid_data(self):
        """Test form validation with valid data"""
        form_data = {
            'final_title': 'Updated Test Book',
            'final_author': 'Updated Test Author',
            'publication_year': 2023,
            'isbn': '978-0123456789',
            'language': 'en',
            'description': 'Test description',
            'is_reviewed': True
        }

        form = MetadataReviewForm(data=form_data, instance=self.final_metadata)
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")

    def test_form_validation_required_fields(self):
        """Test form validation with missing required fields"""
        form_data = {
            'final_title': '',  # Required field empty
            'final_author': 'Test Author',
            'is_reviewed': False
        }

        form = MetadataReviewForm(data=form_data, instance=self.final_metadata)
        self.assertFalse(form.is_valid())
        self.assertIn('final_title', form.errors)

    def test_form_validation_invalid_year(self):
        """Test form validation with invalid publication year"""
        form_data = {
            'final_title': 'Test Book',
            'final_author': 'Test Author',
            'publication_year': 2100,  # Future year
            'is_reviewed': False
        }

        form = MetadataReviewForm(data=form_data, instance=self.final_metadata)
        self.assertFalse(form.is_valid())
        self.assertIn('publication_year', form.errors)

    def test_form_validation_invalid_isbn(self):
        """Test form validation with invalid ISBN"""
        form_data = {
            'final_title': 'Test Book',
            'final_author': 'Test Author',
            'isbn': '123',  # Too short
            'is_reviewed': False
        }

        form = MetadataReviewForm(data=form_data, instance=self.final_metadata)
        self.assertFalse(form.is_valid())
        self.assertIn('isbn', form.errors)

    def test_form_save(self):
        """Test form saves data correctly"""
        form_data = {
            'final_title': 'Updated Test Book',
            'final_author': 'Updated Test Author',
            'publication_year': 2023,
            'isbn': '978-0123456789',
            'language': 'en',
            'description': 'Updated description',
            'is_reviewed': True
        }

        form = MetadataReviewForm(data=form_data, instance=self.final_metadata)
        self.assertTrue(form.is_valid())

        saved_instance = form.save()
        self.assertEqual(saved_instance.final_title, 'Updated Test Book')
        self.assertEqual(saved_instance.final_author, 'Updated Test Author')
        self.assertEqual(saved_instance.publication_year, 2023)
        self.assertEqual(saved_instance.isbn, '978-0123456789')
        self.assertEqual(saved_instance.language, 'en')
        self.assertEqual(saved_instance.description, 'Updated description')
        self.assertTrue(saved_instance.is_reviewed)

    def test_form_mixin_integration(self):
        """Test that form integrates properly with mixins"""
        form = MetadataReviewForm(instance=self.final_metadata)

        # Check that mixin methods are available
        self.assertTrue(hasattr(form, 'get_standard_metadata_widgets'))

        # Check that styling was applied (from StandardFormMixin)
        for field_name, field in form.fields.items():
            if isinstance(field.widget, (forms.TextInput, forms.NumberInput, forms.Textarea)):
                self.assertIn('form-control', field.widget.attrs.get('class', ''))

    def test_widget_customization(self):
        """Test that form widgets are properly customized"""
        form = MetadataReviewForm(instance=self.final_metadata)

        # Check specific widget customizations
        self.assertIsInstance(form.fields['final_title'].widget, forms.TextInput)
        self.assertIsInstance(form.fields['final_author'].widget, forms.TextInput)
        self.assertIsInstance(form.fields['publication_year'].widget, forms.NumberInput)
        self.assertIsInstance(form.fields['description'].widget, forms.Textarea)
        self.assertIsInstance(form.fields['is_reviewed'].widget, forms.CheckboxInput)

    def test_form_field_help_text(self):
        """Test that form fields are properly configured"""
        form = MetadataReviewForm(instance=self.final_metadata)

        # Check that form fields exist and are properly configured
        self.assertIn('isbn', form.fields)
        self.assertIn('publication_year', form.fields)

        # ISBN field should be a CharField
        self.assertIsInstance(form.fields['isbn'], forms.CharField)

        # Publication year should be an IntegerField
        self.assertIsInstance(form.fields['publication_year'], forms.IntegerField)

    def test_form_with_no_instance(self):
        """Test form behavior when no instance is provided"""
        form = MetadataReviewForm()

        # Form should still initialize correctly
        self.assertIn('final_title', form.fields)
        self.assertIn('final_author', form.fields)

    def test_language_field_choices(self):
        """Test that language field is properly configured"""
        form = MetadataReviewForm(instance=self.final_metadata)

        # Language field should be a CharField (as defined in the model)
        self.assertIsInstance(form.fields['language'], forms.CharField)

        # Check that the field is properly configured
        self.assertEqual(form.fields['language'].max_length, 10)
        self.assertFalse(form.fields['language'].required)  # blank=True in model


class FormMixinIntegrationTests(TestCase):
    """Test form mixin integration"""

    def test_metadata_form_mixin_methods(self):
        """Test MetadataFormMixin provides required methods"""
        from books.forms import MetadataReviewForm

        # Create a form instance
        form = MetadataReviewForm()

        # Check that mixin methods are available
        self.assertTrue(hasattr(form, 'get_standard_metadata_widgets'))

        # Test widget generation
        widgets = form.get_standard_metadata_widgets()
        self.assertIsInstance(widgets, dict)
        self.assertIn('final_title', widgets)
        self.assertIn('final_author', widgets)

    def test_standard_form_mixin_styling(self):
        """Test StandardFormMixin applies consistent styling"""
        from books.forms import MetadataReviewForm

        form = MetadataReviewForm()

        # Check that Bootstrap classes are applied
        for field_name, field in form.fields.items():
            widget = field.widget
            if isinstance(widget, (forms.TextInput, forms.NumberInput, forms.Textarea)):
                classes = widget.attrs.get('class', '')
                self.assertIn('form-control', classes)
            elif isinstance(widget, forms.Select):
                classes = widget.attrs.get('class', '')
                self.assertIn('form-select', classes)

    def test_base_metadata_validator_integration(self):
        """Test BaseMetadataValidator integration in forms"""
        from books.forms import MetadataReviewForm

        form_data = {
            'final_title': 'Test Book',
            'final_author': 'Test Author',
            'publication_year': 800,  # Too old - should trigger validator
            'is_reviewed': False
        }

        form = MetadataReviewForm(data=form_data)
        self.assertFalse(form.is_valid())

        # Should have validation error for year
        self.assertIn('publication_year', form.errors)


class FormFieldValidationTests(TestCase):
    """Test individual form field validation"""

    def test_title_validation(self):
        """Test title field validation"""
        from books.forms import MetadataReviewForm

        # Test empty title
        form_data = {'final_title': '', 'final_author': 'Test', 'is_reviewed': False}
        form = MetadataReviewForm(data=form_data)
        self.assertFalse(form.is_valid())

        # Test valid title
        form_data = {'final_title': 'Valid Title', 'final_author': 'Test', 'is_reviewed': False}
        form = MetadataReviewForm(data=form_data)
        self.assertTrue(form.is_valid())

    def test_author_validation(self):
        """Test author field validation"""
        from books.forms import MetadataReviewForm

        # Test empty author
        form_data = {'final_title': 'Test', 'final_author': '', 'is_reviewed': False}
        form = MetadataReviewForm(data=form_data)
        self.assertFalse(form.is_valid())

        # Test valid author
        form_data = {'final_title': 'Test', 'final_author': 'Valid Author', 'is_reviewed': False}
        form = MetadataReviewForm(data=form_data)
        self.assertTrue(form.is_valid())

    def test_isbn_validation_edge_cases(self):
        """Test ISBN validation edge cases"""
        from books.forms import MetadataReviewForm

        valid_isbn_cases = [
            '978-0123456789',
            '9780123456789',
            '0123456789',
            '',  # Empty should be valid (optional field)
        ]

        for isbn in valid_isbn_cases:
            form_data = {
                'final_title': 'Test',
                'final_author': 'Test',
                'isbn': isbn,
                'is_reviewed': False
            }
            form = MetadataReviewForm(data=form_data)
            self.assertTrue(form.is_valid(), f"ISBN {isbn} should be valid")

        invalid_isbn_cases = [
            '123',  # Too short
            '12345678901234567890',  # Too long
            'abc1234567',  # Contains letters
        ]

        for isbn in invalid_isbn_cases:
            form_data = {
                'final_title': 'Test',
                'final_author': 'Test',
                'isbn': isbn,
                'is_reviewed': False
            }
            form = MetadataReviewForm(data=form_data)
            self.assertFalse(form.is_valid(), f"ISBN {isbn} should be invalid")

    def test_year_validation_boundary_cases(self):
        """Test publication year validation boundary cases"""
        from books.forms import MetadataReviewForm
        from django.utils import timezone

        current_year = timezone.now().year

        valid_years = [
            1000,  # Minimum valid year
            2000,  # Common year
            current_year,  # Current year
            current_year + 1,  # Next year (future releases)
        ]

        for year in valid_years:
            form_data = {
                'final_title': 'Test',
                'final_author': 'Test',
                'publication_year': year,
                'is_reviewed': False
            }
            form = MetadataReviewForm(data=form_data)
            self.assertTrue(form.is_valid(), f"Year {year} should be valid")

        invalid_years = [
            999,  # Too old
            current_year + 2,  # Too far in future
        ]

        for year in invalid_years:
            form_data = {
                'final_title': 'Test',
                'final_author': 'Test',
                'publication_year': year,
                'is_reviewed': False
            }
            form = MetadataReviewForm(data=form_data)
            self.assertFalse(form.is_valid(), f"Year {year} should be invalid")
