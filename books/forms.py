"""Django forms for ebook library management.

This module contains form classes for user registration, book metadata editing,
cover management, and scan folder configuration. Includes validation mixins
and standardized form components.
"""
from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from django.utils.safestring import mark_safe
from .models import ScanFolder, Book, FinalMetadata, BookCover, LANGUAGE_CHOICES
from .mixins import StandardFormMixin, MetadataFormMixin
import os

# ------------------------
# User Registration Form
# ------------------------


class UserRegisterForm(UserCreationForm):
    email = forms.EmailField()

    class Meta:
        model = User
        fields = ['username', 'email', 'password1', 'password2']


# ------------------------
# Scan Folder Form
# ------------------------

class FolderSelectWidget(forms.TextInput):
    """Simple text input for folder paths with helpful guidance."""

    def __init__(self, attrs=None):
        default_attrs = {
            'class': 'form-control',
            'placeholder': 'Enter the full path to your folder (e.g., C:\\Users\\Pieter\\Documents\\eBooks)'
        }
        if attrs:
            default_attrs.update(attrs)
        super().__init__(default_attrs)

    def render(self, name, value, attrs=None, renderer=None):
        # Render the main input field
        text_input = super().render(name, value, attrs, renderer)

        # Simple widget with clear guidance
        widget_html = f'''
        <div class="folder-path-container">
            {text_input}
            <div class="form-text mt-2">
                <i class="fas fa-info-circle text-primary"></i>
                <strong>How to find your folder path:</strong>
            </div>
            <div class="form-text">
                <ol class="mb-0 small">
                    <li>Open File Explorer and navigate to your folder</li>
                    <li>Click on the address bar at the top</li>
                    <li>Copy the full path (e.g., C:\\Users\\Pieter\\Documents\\eBooks)</li>
                    <li>Paste it in the field above</li>
                </ol>
            </div>
        </div>
        '''

        return mark_safe(widget_html)


class ScanFolderForm(StandardFormMixin, forms.ModelForm):
    class Meta:
        model = ScanFolder
        fields = ['name', 'path', 'language', 'is_active']
        widgets = {
            'path': FolderSelectWidget(),
        }

    def clean_path(self):
        path = self.cleaned_data['path']
        if not path or not path.strip():
            raise forms.ValidationError("Please provide a folder path.")

        path = path.strip()

        if not os.path.exists(path):
            raise forms.ValidationError(f"The specified path does not exist: {path}")
        if not os.path.isdir(path):
            raise forms.ValidationError(f"The specified path is not a directory: {path}")
        return path


# ------------------------
# Book Search Form
# ------------------------

class BookSearchForm(StandardFormMixin, forms.Form):
    search_query = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Search books, authors, series...'})
    )

    language = forms.ChoiceField(
        choices=[('', 'All Languages')] + LANGUAGE_CHOICES,
        required=False
    )

    file_format = forms.ChoiceField(
        choices=[('', 'All Formats')] + Book.FORMAT_CHOICES,
        required=False
    )

    has_placeholder = forms.ChoiceField(
        required=False,
        choices=[
            ('', 'All Books'),
            ('false', 'Real files only'),
            ('true', 'Placeholders only'),
        ]
    )

    is_reviewed = forms.ChoiceField(
        required=False,
        choices=[
            ('', 'All Books'),
            ('false', 'Needs Review'),
            ('true', 'Reviewed'),
        ]
    )

    confidence_level = forms.ChoiceField(
        required=False,
        choices=[
            ('', 'All Confidence Levels'),
            ('high', 'High (>0.8)'),
            ('medium', 'Medium (0.5-0.8)'),
            ('low', 'Low (<0.5)'),
        ]
    )

    has_cover = forms.ChoiceField(
        required=False,
        choices=[
            ('', 'All Books'),
            ('true', 'Has Cover'),
            ('false', 'No Cover'),
        ]
    )


# ------------------------
# Final Metadata Review Form (Enhanced for Radio/Dropdown Selection)
# ------------------------


# Remove the duplicate BaseMetadataValidator class - using the one from mixins
# class BaseMetadataValidator: ... (removed)


class MetadataReviewForm(MetadataFormMixin, forms.ModelForm):
    """Form for reviewing and updating final metadata with dropdown + manual entry support."""

    # Cover upload field
    new_cover_upload = forms.ImageField(
        required=False,
        widget=forms.ClearableFileInput(attrs={
            'class': 'form-control',
            'accept': 'image/*'
        }),
        label="Upload New Cover"
    )

    # Manual entry fields for additional genres
    manual_genres = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter additional genres...'
        }),
        label="Add Custom Genres (comma-separated)"
    )

    class Meta:
        model = FinalMetadata
        fields = [
            'final_title',
            'final_author',
            'final_series',
            'final_series_number',
            'final_publisher',
            'final_cover_path',
            'language',
            'isbn',
            'publication_year',
            'description',
            'is_reviewed',
        ]

    def __init__(self, *args, **kwargs):
        self.book = kwargs.pop('book', None)
        super().__init__(*args, **kwargs)

        # Apply standard metadata widgets
        standard_widgets = self.get_standard_metadata_widgets()
        for field_name, widget in standard_widgets.items():
            if field_name in self.fields:
                self.fields[field_name].widget = widget

        # Set language choices including empty option
        self.fields['language'].widget.choices = [('', 'Select language')] + LANGUAGE_CHOICES

        # Update cover upload widget using mixin
        self.fields['new_cover_upload'].widget = self.get_widget('image_input')

        # Update manual genres widget using mixin
        self.fields['manual_genres'].widget = self.text_with_placeholder('Enter additional genres...')

    # The clean methods are now inherited from MetadataFormMixin, so we can remove the duplicates


# ------------------------
# Book Status Update Form
# ------------------------

class BookStatusForm(forms.ModelForm):
    class Meta:
        model = Book
        fields = ['is_duplicate']
        widgets = {
            'is_duplicate': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


# ------------------------
# Book Edit Form
# ------------------------

class BookEditForm(forms.ModelForm):
    class Meta:
        model = Book
        fields = [
            'file_format',
            'cover_path',
            'opf_path',
            'is_placeholder',
            'is_duplicate',
        ]
        widgets = {
            'file_format': forms.Select(attrs={'class': 'form-select'}),
            'cover_path': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Path to cover image'
            }),
            'opf_path': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Path to .opf metadata file'
            }),
            'is_placeholder': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_duplicate': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


# ------------------------
# Book Cover Form
# ------------------------

class BookCoverForm(StandardFormMixin, forms.ModelForm):
    class Meta:
        model = BookCover
        fields = [
            'cover_path',
            'confidence',
            'width',
            'height',
            'format',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Apply custom widgets using mixin
        self.fields['cover_path'].widget = self.text_with_placeholder('Path to cover image or URL')
        self.fields['confidence'].widget = self.number_with_range(
            min_val=0, max_val=1, step=0.1, placeholder='Confidence score'
        )
        self.fields['width'].widget = self.text_with_placeholder('Width in pixels')
        self.fields['height'].widget = self.text_with_placeholder('Height in pixels')
        self.fields['format'].widget = self.text_with_placeholder('jpg, png, gif, etc.')

    def clean_confidence(self):
        """Validate confidence using base validator"""
        from .mixins import BaseMetadataValidator
        return BaseMetadataValidator.validate_confidence(
            self.cleaned_data.get('confidence')
        )


# ------------------------
# Bulk Update Form
# ------------------------

class BulkUpdateForm(StandardFormMixin, forms.Form):
    ACTION_CHOICES = [
        ('', 'Select action'),
        ('mark_reviewed', 'Mark as reviewed'),
        ('mark_unreviewed', 'Mark as unreviewed'),
        ('mark_duplicate', 'Mark as duplicate'),
        ('unmark_duplicate', 'Unmark as duplicate'),
        ('delete_placeholders', 'Delete placeholders'),
    ]

    action = forms.ChoiceField(
        choices=ACTION_CHOICES,
        required=True,
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    selected_books = forms.CharField(
        widget=forms.HiddenInput(),
        required=False
    )

    def clean_selected_books(self):
        from .mixins import BaseMetadataValidator

        selected = self.cleaned_data.get('selected_books', '')
        if not selected:
            raise forms.ValidationError("No books selected.")

        # Use the validator from mixins
        return BaseMetadataValidator.validate_integer_list(selected, 'book IDs')


# ------------------------
# Advanced Search Form
# ------------------------

class AdvancedSearchForm(forms.Form):
    title = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Title contains...'
        })
    )

    author = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Author contains...'
        })
    )

    series = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Series contains...'
        })
    )

    isbn = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'ISBN'
        })
    )

    publisher = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Publisher contains...'
        })
    )

    publication_year_from = forms.IntegerField(
        required=False,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': 'From year'
        })
    )

    publication_year_to = forms.IntegerField(
        required=False,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': 'To year'
        })
    )

    language = forms.ChoiceField(
        choices=[('', 'All Languages')] + LANGUAGE_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    file_format = forms.ChoiceField(
        choices=[('', 'All Formats')] + Book.FORMAT_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    confidence_min = forms.FloatField(
        required=False,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'min': '0',
            'max': '1',
            'step': '0.1',
            'placeholder': 'Min confidence'
        })
    )

    confidence_max = forms.FloatField(
        required=False,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'min': '0',
            'max': '1',
            'step': '0.1',
            'placeholder': 'Max confidence'
        })
    )

    def clean(self):
        cleaned_data = super().clean()
        year_from = cleaned_data.get('publication_year_from')
        year_to = cleaned_data.get('publication_year_to')

        # Validate years using base validator
        if year_from is not None:
            from .mixins import BaseMetadataValidator
            try:
                BaseMetadataValidator.validate_year(year_from, "From year")
            except forms.ValidationError:
                self.add_error('publication_year_from', 'Invalid from year.')

        if year_to is not None:
            from .mixins import BaseMetadataValidator
            try:
                BaseMetadataValidator.validate_year(year_to, "To year")
            except forms.ValidationError:
                self.add_error('publication_year_to', 'Invalid to year.')

        if year_from and year_to and year_from > year_to:
            raise forms.ValidationError("'From year' must be less than or equal to 'To year'.")

        conf_min = cleaned_data.get('confidence_min')
        conf_max = cleaned_data.get('confidence_max')

        if conf_min is not None and conf_max is not None and conf_min > conf_max:
            raise forms.ValidationError("Minimum confidence must be less than or equal to maximum confidence.")

        return cleaned_data
