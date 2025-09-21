from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from .models import ScanFolder, Book, FinalMetadata, BookCover, LANGUAGE_CHOICES
from .mixins import StandardFormMixin, MetadataFormMixin
import os


class UserRegisterForm(UserCreationForm):
    email = forms.EmailField()

    class Meta:
        model = User
        fields = ['username', 'email', 'password1', 'password2']


class ScanFolderForm(StandardFormMixin, forms.ModelForm):
    class Meta:
        model = ScanFolder
        fields = ['name', 'path', 'content_type', 'language', 'is_active']
        widgets = {
            'path': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter the full path to your folder (e.g., C:\\Users\\Pieter\\Documents\\eBooks)'
            }),
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


class BookStatusForm(StandardFormMixin, forms.ModelForm):
    class Meta:
        model = Book
        fields = ['is_duplicate']


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
            'cover_path': forms.TextInput(attrs={'placeholder': 'Path to cover image'}),
            'opf_path': forms.TextInput(attrs={'placeholder': 'Path to .opf metadata file'}),
        }


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


class AdvancedSearchForm(StandardFormMixin, forms.Form):
    title = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Title contains...'})
    )

    author = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Author contains...'})
    )

    series = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Series contains...'})
    )

    isbn = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'ISBN'})
    )

    publisher = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Publisher contains...'})
    )

    publication_year_from = forms.IntegerField(
        required=False,
        widget=forms.NumberInput(attrs={'placeholder': 'From year'})
    )

    publication_year_to = forms.IntegerField(
        required=False,
        widget=forms.NumberInput(attrs={'placeholder': 'To year'})
    )

    language = forms.ChoiceField(
        choices=[('', 'All Languages')] + LANGUAGE_CHOICES,
        required=False
    )

    file_format = forms.ChoiceField(
        choices=[('', 'All Formats')] + Book.FORMAT_CHOICES,
        required=False
    )

    confidence_min = forms.FloatField(
        required=False,
        widget=forms.NumberInput(attrs={
            'min': '0',
            'max': '1',
            'step': '0.1',
            'placeholder': 'Min confidence'
        })
    )

    confidence_max = forms.FloatField(
        required=False,
        widget=forms.NumberInput(attrs={
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


class UserProfileForm(StandardFormMixin, forms.ModelForm):
    """Form for user preferences and settings"""

    class Meta:
        from .models import UserProfile
        model = UserProfile
        fields = ['theme', 'items_per_page', 'show_covers_in_list', 'default_view_mode', 'share_reading_progress']
        widgets = {
            'theme': forms.Select(attrs={
                'class': 'form-select',
                'data-bs-toggle': 'tooltip',
                'data-bs-placement': 'top',
                'title': 'Select your preferred theme'
            }),
            'items_per_page': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '10',
                'max': '200',
                'step': '10'
            }),
            'show_covers_in_list': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'default_view_mode': forms.Select(attrs={
                'class': 'form-select'
            }),
            'share_reading_progress': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Add help text and labels
        self.fields['theme'].help_text = 'Choose your preferred visual theme'
        self.fields['items_per_page'].help_text = 'Number of books to display per page (10-200)'
        self.fields['show_covers_in_list'].help_text = 'Display book cover thumbnails in list views'
        self.fields['default_view_mode'].help_text = 'Default layout for browsing books'
        self.fields['share_reading_progress'].help_text = 'Allow other users to see your reading progress'
