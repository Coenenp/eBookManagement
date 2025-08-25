from django import forms
from django.utils import timezone
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from django.core.exceptions import ValidationError
from .models import ScanFolder, Book, FinalMetadata, BookCover, LANGUAGE_CHOICES
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

class ScanFolderForm(forms.ModelForm):
    class Meta:
        model = ScanFolder
        fields = ['name', 'path', 'language', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'path': forms.TextInput(attrs={'class': 'form-control'}),
            'language': forms.Select(attrs={'class': 'form-control'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

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

class BookSearchForm(forms.Form):
    search_query = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Search books, authors, series...'
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

    has_placeholder = forms.ChoiceField(
        required=False,
        choices=[
            ('', 'All Books'),
            ('false', 'Real files only'),
            ('true', 'Placeholders only'),
        ],
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    is_reviewed = forms.ChoiceField(
        required=False,
        choices=[
            ('', 'All Books'),
            ('false', 'Needs Review'),
            ('true', 'Reviewed'),
        ],
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    confidence_level = forms.ChoiceField(
        required=False,
        choices=[
            ('', 'All Confidence Levels'),
            ('high', 'High (>0.8)'),
            ('medium', 'Medium (0.5-0.8)'),
            ('low', 'Low (<0.5)'),
        ],
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    has_cover = forms.ChoiceField(
        required=False,
        choices=[
            ('', 'All Books'),
            ('true', 'Has Cover'),
            ('false', 'No Cover'),
        ],
        widget=forms.Select(attrs={'class': 'form-select'})
    )


# ------------------------
# Final Metadata Review Form (Enhanced for Radio/Dropdown Selection)
# ------------------------


class BaseMetadataValidator:
    @staticmethod
    def validate_year(value, field_name="year"):
        if value is None or (isinstance(value, str) and value.strip() == ''):
            return None

        try:
            year = int(value) if isinstance(value, int) else int(str(value).strip())
            current_year = timezone.now().year

            if year < 1000 or year > current_year + 1:
                raise ValidationError(f"{field_name} must be between 1000 and {current_year + 1}.")

            return year
        except (ValueError, TypeError):
            raise ValidationError(f"{field_name} must be a valid year.")

    @staticmethod
    def validate_isbn(value):
        if not value:
            return ''

        isbn_str = str(value).strip()
        isbn_clean = isbn_str.replace('-', '').replace(' ', '')

        if not (len(isbn_clean) == 10 or len(isbn_clean) == 13):
            raise ValidationError("ISBN must be 10 or 13 digits long.")

        if not isbn_clean.replace('X', '').replace('x', '').isdigit():
            raise ValidationError("ISBN must contain only digits (and X for ISBN-10).")

        return isbn_str


class MetadataReviewForm(forms.ModelForm):
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

        widgets = {
            'final_title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter title',
                'required': True
            }),
            'final_author': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter author',
                'required': True
            }),
            'final_series': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter series name'
            }),
            'final_series_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter series number',
                'pattern': '[0-9]*',
                'title': 'Please enter numbers only'
            }),
            'final_publisher': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter publisher'
            }),
            'final_cover_path': forms.HiddenInput(),
            'language': forms.Select(attrs={'class': 'form-select'}),
            'isbn': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter ISBN'
            }),
            'publication_year': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter publication year',
                'min': '1000',
                'max': '2030',
                'title': 'Enter a 4-digit year'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 5,
                'placeholder': 'Enter description'
            }),
            'is_reviewed': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        self.book = kwargs.pop('book', None)
        super().__init__(*args, **kwargs)

        # Set language choices including empty option
        self.fields['language'].choices = [('', 'Select language')] + LANGUAGE_CHOICES

    def clean_final_title(self):
        """Validate that title is provided."""
        title = self.cleaned_data.get('final_title', '').strip()
        if not title:
            raise forms.ValidationError('Title is required.')
        return title

    def clean_final_author(self):
        """Validate that author is provided."""
        author = self.cleaned_data.get('final_author', '').strip()
        if not author:
            raise forms.ValidationError('Author is required.')
        return author

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
        return BaseMetadataValidator.validate_year(
            self.cleaned_data.get('publication_year'),
            "Publication year"
        )

    def clean_isbn(self):
        return BaseMetadataValidator.validate_isbn(
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

class BookCoverForm(forms.ModelForm):
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
            'cover_path': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Path to cover image or URL'
            }),
            'confidence': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0',
                'max': '1',
                'step': '0.1'
            }),
            'width': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Width in pixels'
            }),
            'height': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Height in pixels'
            }),
            'format': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'jpg, png, gif, etc.'
            }),
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

        if year_from and year_to and year_from > year_to:
            raise forms.ValidationError("'From year' must be less than or equal to 'To year'.")

        conf_min = cleaned_data.get('confidence_min')
        conf_max = cleaned_data.get('confidence_max')

        if conf_min is not None and conf_max is not None and conf_min > conf_max:
            raise forms.ValidationError("Minimum confidence must be less than or equal to maximum confidence.")

        return cleaned_data
