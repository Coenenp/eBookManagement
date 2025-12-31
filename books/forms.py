from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from .models import ScanFolder, Book, FinalMetadata, BookCover, DataSource, COMIC_FORMATS, EBOOK_FORMATS, AUDIOBOOK_FORMATS
from .mixins import StandardFormMixin, MetadataFormMixin, BaseMetadataValidator
from .utils.language_manager import LanguageManager
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
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
                'checked': True
            }),
        }

    def clean_path(self):

        path = self.cleaned_data.get('path', '')
        if not path or not path.strip():
            raise forms.ValidationError("Please provide a folder path.")

        # Strip whitespace and normalize path
        path = path.strip()

        if not os.path.exists(path):
            raise forms.ValidationError(f"The specified path does not exist: {path}")
        if not os.path.isdir(path):
            raise forms.ValidationError(f"The specified path is not a directory: {path}")
        return path

    def clean(self):
        cleaned_data = super().clean()

        # Set default content_type if not provided
        if 'content_type' not in cleaned_data or not cleaned_data['content_type']:
            cleaned_data['content_type'] = 'ebooks'

        return cleaned_data


class ScanFolderEditForm(StandardFormMixin, forms.ModelForm):
    """Restricted form for editing scan folders - excludes path and content_type."""
    class Meta:
        model = ScanFolder
        fields = ['name', 'language', 'is_active']
        widgets = {
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
        }

    def _post_clean(self):
        """Override to apply form data while skipping model validation."""
        # Apply form data to instance (this is what _post_clean normally does)
        opts = self._meta
        exclude = self._get_validation_exclusions()

        # Update the instance with cleaned data
        for f in opts.model._meta.fields:
            if f.name in self.cleaned_data and f.name not in exclude:
                setattr(self.instance, f.name, self.cleaned_data[f.name])

        # Skip model validation (model.clean() and unique validation)
        # because the model's clean() method validates the 'path' field
        # which is excluded from this form and might not exist

    def save(self, commit=True):
        """Override save to skip model validation since path field is not editable."""
        instance = super().save(commit=False)

        if commit:
            # Save without calling model's full_clean() validation
            # Generate path hash as the original model save does
            if instance.path:
                instance.path_hash = instance.generate_hash(instance.path)
            # Skip instance.full_clean() and call Django's Model.save directly
            super(ScanFolder, instance).save()

        return instance


class TriggerScanForm(forms.Form):
    """Form for triggering scans with options."""
    query_external_apis = forms.BooleanField(
        required=False,
        initial=True,
        label='Query external APIs for metadata',
        help_text='Enable this to fetch metadata from external sources during scanning',
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input'
        })
    )


class DataSourceForm(StandardFormMixin, forms.ModelForm):
    class Meta:
        model = DataSource
        fields = ['name', 'trust_level', 'priority', 'is_active']
        widgets = {
            'name': forms.Select(attrs={
                'class': 'form-select'
            }),
            'trust_level': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0',
                'max': '1',
                'step': '0.1',
                'placeholder': '0.0-1.0'
            }),
            'priority': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '1',
                'placeholder': 'Priority (1 = highest)'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Ensure is_active defaults to True for new instances
        # For existing instances, the form will automatically use the model value
        if not self.instance.pk:
            self.fields['is_active'].initial = True
        else:
            # Explicitly set the initial value from the database for existing instances
            self.fields['is_active'].initial = self.instance.is_active

        # Add help text
        self.fields['trust_level'].help_text = 'Trust level for this source (0.0 = lowest, 1.0 = highest)'
        self.fields['priority'].help_text = 'Lower numbers have higher priority'
        self.fields['is_active'].help_text = 'Whether this data source is currently active'


class BookSearchForm(StandardFormMixin, forms.Form):
    search_query = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Search books, authors, series...'})
    )

    language = forms.ChoiceField(
        choices=LanguageManager.get_language_choices_with_all('All Languages'),
        required=False
    )

    file_format = forms.ChoiceField(
        choices=[('', 'All Formats')] + [(fmt, fmt.upper()) for fmt in sorted(set(
            COMIC_FORMATS + EBOOK_FORMATS + AUDIOBOOK_FORMATS
        ))],
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
        self.fields['language'].widget.choices = LanguageManager.get_language_choices_with_empty('Select language')

        # Update cover upload widget using mixin
        self.fields['new_cover_upload'].widget = self.get_widget('image_input')

        # Update manual genres widget using mixin
        self.fields['manual_genres'].widget = self.text_with_placeholder('Enter additional genres...')

        # Set required fields
        self.fields['final_title'].required = True
        self.fields['final_author'].required = True

    def clean_manual_genres(self):
        """Validate manual genres using base validator"""
        value = self.cleaned_data.get('manual_genres', '')
        if not value:
            return ''

        value_str = str(value).strip()
        if not value_str:
            return ''

        # Split by comma and clean each item
        item_list = [item.strip() for item in value_str.split(',') if item.strip()]
        if not item_list:
            return ''

        return ', '.join(item_list)

    def clean(self):
        """Custom form validation including publication year"""
        from django.utils import timezone

        cleaned_data = super().clean()

        # Validate publication year
        publication_year = cleaned_data.get('publication_year')

        if publication_year is not None:
            current_year = timezone.now().year

            if publication_year < 1000 or publication_year > current_year + 1:
                self.add_error('publication_year', forms.ValidationError(
                    f"Publication year must be between 1000 and {current_year + 1}."
                ))

        return cleaned_data


class BookStatusForm(StandardFormMixin, forms.ModelForm):
    class Meta:
        model = Book
        fields = ['is_duplicate']


class BookEditForm(StandardFormMixin, forms.ModelForm):
    class Meta:
        model = Book
        fields = [
            'is_placeholder',
            'is_duplicate',
        ]
        widgets = {}


class BookCoverForm(MetadataFormMixin, forms.ModelForm):
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
        value = self.cleaned_data.get('confidence')
        if value is None:
            return value

        try:
            conf = float(value)
            if not (0 <= conf <= 1):
                raise forms.ValidationError("Confidence must be between 0 and 1.")
            return conf
        except (ValueError, TypeError):
            raise forms.ValidationError("Confidence must be a valid number.")


class BulkUpdateForm(MetadataFormMixin, forms.Form):
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

        # Validate and convert comma-separated integer list
        value_str = str(selected).strip()
        if not value_str:
            return []

        try:
            item_list = [int(item.strip()) for item in value_str.split(',') if item.strip()]
            return item_list
        except ValueError:
            raise forms.ValidationError("Invalid book IDs - must be comma-separated integers.")


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
        choices=LanguageManager.get_language_choices_with_all('All Languages'),
        required=False
    )

    file_format = forms.ChoiceField(
        choices=[('', 'All Formats')] + [(fmt, fmt.upper()) for fmt in sorted(set(
            COMIC_FORMATS + EBOOK_FORMATS + AUDIOBOOK_FORMATS
        ))],
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
            try:
                BaseMetadataValidator.validate_year(year_from, "From year")
            except forms.ValidationError:
                self.add_error('publication_year_from', 'Invalid from year.')

        if year_to is not None:
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
        fields = [
            'theme', 'items_per_page', 'show_covers_in_list', 'default_view_mode', 'share_reading_progress',
            'default_folder_pattern', 'default_filename_pattern', 'include_companion_files'
        ]
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
            'default_folder_pattern': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '{author}/{series_name} #{series_number} - {title}',
                'maxlength': 255
            }),
            'default_filename_pattern': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '{author} - {title}',
                'maxlength': 255
            }),
            'include_companion_files': forms.CheckboxInput(attrs={
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
        self.fields['default_folder_pattern'].help_text = (
            'Default pattern for organizing folders when renaming (use {author}, {title}, {series_name}, {series_number})'
        )
        self.fields['default_filename_pattern'].help_text = (
            'Default pattern for naming files when renaming (use {author}, {title}, {series_name}, {series_number})'
        )
        self.fields['include_companion_files'].help_text = 'Include companion files (images, metadata) when renaming'
