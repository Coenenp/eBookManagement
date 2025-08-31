from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from .models import ScanFolder, Book, FinalMetadata, BookCover, LANGUAGE_CHOICES
from .mixins import StandardFormMixin, BaseMetadataValidator
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

class ScanFolderForm(StandardFormMixin, forms.ModelForm):
    class Meta:
        model = ScanFolder
        fields = ['name', 'path', 'language', 'is_active']
        # StandardFormMixin will apply standard styling automatically

    def clean_path(self):
        path = self.cleaned_data['path']
        if not os.path.exists(path):
            raise forms.ValidationError("The specified path does not exist.")
        if not os.path.isdir(path):
            raise forms.ValidationError("The specified path is not a directory.")
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


class MetadataReviewForm(StandardFormMixin, BaseMetadataValidator, forms.ModelForm):
    """Form for reviewing and updating final metadata with dropdown + manual entry support."""

    # Cover upload field
    new_cover_upload = forms.ImageField(
        required=False,
        widget=StandardWidgetMixin.get_widget('image_input'),
        label="Upload New Cover"
    )

    # Manual entry fields for additional genres
    manual_genres = forms.CharField(
        required=False,
        widget=StandardWidgetMixin.text_with_placeholder('Enter additional genres...'),
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

        widgets = {
            'final_title': StandardWidgetMixin.text_required_with_placeholder('Enter title'),
            'final_author': StandardWidgetMixin.text_required_with_placeholder('Enter author'),
            'final_series': StandardWidgetMixin.text_with_placeholder('Enter series name'),
            'final_series_number': StandardWidgetMixin.get_widget('text_input', 
                placeholder='Enter series number', pattern='[0-9]*', 
                title='Please enter numbers only'),
            'final_publisher': StandardWidgetMixin.text_with_placeholder('Enter publisher'),
            'final_cover_path': StandardWidgetMixin.get_widget('hidden'),
            'language': StandardWidgetMixin.get_widget('select'),
            'isbn': StandardWidgetMixin.text_with_placeholder('Enter ISBN'),
            'publication_year': StandardWidgetMixin.number_with_range(
                min_val=1000, max_val=2030, placeholder='Enter publication year'),
            'description': StandardWidgetMixin.get_widget('textarea', 
                placeholder='Enter description'),
            'is_reviewed': StandardWidgetMixin.get_widget('checkbox'),
        }

    def __init__(self, *args, **kwargs):
        self.book = kwargs.pop('book', None)
        super().__init__(*args, **kwargs)

        # Set language choices including empty option
        self.fields['language'].choices = [('', 'Select language')] + LANGUAGE_CHOICES

    def clean_final_title(self):
        """Validate that title is provided."""
        title = self.cleaned_data.get('final_title', '').strip()
        return self.validate_required_text(title, 'Title')

    def clean_final_author(self):
        """Validate that author is provided."""
        author = self.cleaned_data.get('final_author', '').strip()
        return self.validate_required_text(author, 'Author')

    def clean_final_series_number(self):
        value = self.cleaned_data.get('final_series_number')
        if value is None or (isinstance(value, str) and value.strip() == ''):
            return ''

        # Allow alphanumeric series numbers (1, 1.5, 2a, etc.)
        value_str = str(value).strip()
        if len(value_str) > 20:  # Length check only
            raise forms.ValidationError("Series number too long (max 20 characters).")

        return value_str

    def clean_publication_year(self):
        return self.validate_year(
            self.cleaned_data.get('publication_year'),
            "Publication year"
        )

    def clean_isbn(self):
        return self.validate_isbn(
            self.cleaned_data.get('isbn')
        )

    def clean_manual_genres(self):
        """Clean manual genres input."""
        genres = self.cleaned_data.get('manual_genres', '').strip()
        if genres:
            # Split by comma and clean each genre
            genre_list = [g.strip() for g in genres.split(',') if g.strip()]
            return ', '.join(genre_list)
        return ''


# ------------------------
# Book Status Update Form
# ------------------------

class BookStatusForm(StandardFormMixin, forms.ModelForm):
    class Meta:
        model = Book
        fields = ['is_duplicate']


# ------------------------
# Book Edit Form
# ------------------------

class BookEditForm(StandardFormMixin, forms.ModelForm):
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
            'file_format': StandardWidgetMixin.get_widget('select'),
            'cover_path': StandardWidgetMixin.text_with_placeholder('Path to cover image'),
            'opf_path': StandardWidgetMixin.text_with_placeholder('Path to .opf metadata file'),
            'is_placeholder': StandardWidgetMixin.get_widget('checkbox'),
            'is_duplicate': StandardWidgetMixin.get_widget('checkbox'),
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
        widgets = {
            'cover_path': StandardWidgetMixin.text_with_placeholder('Path to cover image or URL'),
            'confidence': StandardWidgetMixin.number_with_range(
                min_val=0, max_val=1, step=0.1, placeholder='Confidence score'),
            'width': StandardWidgetMixin.text_with_placeholder('Width in pixels'),
            'height': StandardWidgetMixin.text_with_placeholder('Height in pixels'),
            'format': StandardWidgetMixin.text_with_placeholder('jpg, png, gif, etc.'),
        }


# ------------------------
# Bulk Update Form
# ------------------------

class BulkUpdateForm(forms.Form):
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
        selected = self.cleaned_data.get('selected_books', '')
        if not selected:
            raise forms.ValidationError("No books selected.")

        try:
            book_ids = [int(id.strip()) for id in selected.split(',') if id.strip()]
        except ValueError:
            raise forms.ValidationError("Invalid book IDs selected.")

        if not book_ids:
            raise forms.ValidationError("No valid book IDs selected.")

        return book_ids


# ------------------------
# Advanced Search Form
# ------------------------

class AdvancedSearchForm(StandardFormMixin, BaseMetadataValidator, forms.Form):
    title = forms.CharField(
        required=False,
        widget=StandardWidgetMixin.text_with_placeholder('Title contains...')
    )

    author = forms.CharField(
        required=False,
        widget=StandardWidgetMixin.text_with_placeholder('Author contains...')
    )

    series = forms.CharField(
        required=False,
        widget=StandardWidgetMixin.text_with_placeholder('Series contains...')
    )

    isbn = forms.CharField(
        required=False,
        widget=StandardWidgetMixin.text_with_placeholder('ISBN')
    )

    publisher = forms.CharField(
        required=False,
        widget=StandardWidgetMixin.text_with_placeholder('Publisher contains...')
    )

    publication_year_from = forms.IntegerField(
        required=False,
        widget=StandardWidgetMixin.text_with_placeholder('From year')
    )

    publication_year_to = forms.IntegerField(
        required=False,
        widget=StandardWidgetMixin.text_with_placeholder('To year')
    )

    language = forms.ChoiceField(
        choices=[('', 'All Languages')] + LANGUAGE_CHOICES,
        required=False,
        widget=StandardWidgetMixin.get_widget('select')
    )

    file_format = forms.ChoiceField(
        choices=[('', 'All Formats')] + Book.FORMAT_CHOICES,
        required=False,
        widget=StandardWidgetMixin.get_widget('select')
    )

    confidence_min = forms.FloatField(
        required=False,
        widget=StandardWidgetMixin.number_with_range(
            min_val=0, max_val=1, step=0.1, placeholder='Min confidence')
    )

    confidence_max = forms.FloatField(
        required=False,
        widget=StandardWidgetMixin.number_with_range(
            min_val=0, max_val=1, step=0.1, placeholder='Max confidence')
    )

    def clean(self):
        cleaned_data = super().clean()
        year_from = cleaned_data.get('publication_year_from')
        year_to = cleaned_data.get('publication_year_to')

        if year_from and year_to and year_from > year_to:
            raise forms.ValidationError("'From year' must be less than or equal to 'To year'.")

        conf_min = cleaned_data.get('confidence_min')
        conf_max = cleaned_data.get('confidence_max')

        if conf_min is not None and conf_max is not None:
            # Use inherited validation method
            self.validate_confidence(conf_min)
            self.validate_confidence(conf_max)
            if conf_min > conf_max:
                raise forms.ValidationError("Minimum confidence must be less than or equal to maximum confidence.")

        return cleaned_data
