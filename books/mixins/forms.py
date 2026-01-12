"""
Form mixins for standardized widget styling and validation.
"""

from django import forms
from django.utils import timezone


class StandardWidgetMixin:
    """Mixin providing standard widget configurations"""

    STANDARD_WIDGETS = {
        "text_input": forms.TextInput(attrs={"class": "form-control"}),
        "text_input_required": forms.TextInput(attrs={"class": "form-control", "required": True}),
        "email_input": forms.EmailInput(attrs={"class": "form-control"}),
        "password_input": forms.PasswordInput(attrs={"class": "form-control"}),
        "textarea": forms.Textarea(attrs={"class": "form-control", "rows": 5}),
        "select": forms.Select(attrs={"class": "form-select"}),
        "number_input": forms.NumberInput(attrs={"class": "form-control"}),
        "checkbox": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        "file_input": forms.ClearableFileInput(attrs={"class": "form-control"}),
        "image_input": forms.ClearableFileInput(attrs={"class": "form-control", "accept": "image/*"}),
        "hidden": forms.HiddenInput(),
    }

    @classmethod
    def get_widget(cls, widget_type, **extra_attrs):
        """Get a standard widget with optional extra attributes"""
        base_widget = cls.STANDARD_WIDGETS.get(widget_type)
        if not base_widget:
            raise ValueError(f"Unknown widget type: {widget_type}")

        if extra_attrs:
            # Clone the widget and add extra attributes
            new_attrs = base_widget.attrs.copy()
            new_attrs.update(extra_attrs)
            return base_widget.__class__(attrs=new_attrs)

        return base_widget

    @classmethod
    def text_with_placeholder(cls, placeholder):
        """Text input with placeholder"""
        return cls.get_widget("text_input", placeholder=placeholder)

    @classmethod
    def text_required_with_placeholder(cls, placeholder):
        """Required text input with placeholder"""
        return cls.get_widget("text_input_required", placeholder=placeholder)

    @classmethod
    def number_with_range(cls, min_val=None, max_val=None, step=None, placeholder=None):
        """Number input with range constraints"""
        attrs = {}
        if min_val is not None:
            attrs["min"] = str(min_val)
        if max_val is not None:
            attrs["max"] = str(max_val)
        if step is not None:
            attrs["step"] = str(step)
        if placeholder:
            attrs["placeholder"] = placeholder

        return cls.get_widget("number_input", **attrs)


class BaseMetadataValidator:
    """Base validator for metadata forms"""

    @staticmethod
    def validate_required_text(value, field_name):
        """Validate required text field"""
        if not value or not value.strip():
            raise forms.ValidationError(f"{field_name} is required.")
        return value.strip()

    @staticmethod
    def validate_series_number(value, max_length=20):
        """Validate series number (alphanumeric)"""
        if value is None or (isinstance(value, str) and value.strip() == ""):
            return ""

        # Allow alphanumeric series numbers (1, 1.5, 2a, etc.)
        value_str = str(value).strip()
        if len(value_str) > max_length:
            raise forms.ValidationError(f"Series number too long (max {max_length} characters).")

        return value_str

    @staticmethod
    def validate_year(value, field_name="Year"):
        """Validate year field"""
        if value is None or (isinstance(value, str) and value.strip() == ""):
            return None

        try:
            year = int(value) if isinstance(value, int) else int(str(value).strip())
            current_year = timezone.now().year

            if year < 1000 or year > current_year + 1:
                raise forms.ValidationError(f"{field_name} must be between 1000 and {current_year + 1}.")

            return year
        except (ValueError, TypeError):
            raise forms.ValidationError(f"{field_name} must be a valid year.")

    @staticmethod
    def validate_isbn(value):
        """Basic ISBN validation"""
        if not value:
            return ""

        # Remove hyphens, spaces, and other formatting for validation
        isbn = "".join(c for c in str(value) if c.isalnum())

        # Check length (ISBN-10 or ISBN-13)
        if len(isbn) not in [10, 13]:
            raise forms.ValidationError("ISBN must be 10 or 13 digits.")

        # Check if all characters are digits (except last character of ISBN-10 can be 'X')
        if len(isbn) == 10:
            if not (isbn[:9].isdigit() and (isbn[9].isdigit() or isbn[9].upper() == "X")):
                raise forms.ValidationError("Invalid ISBN-10 format.")
        else:  # ISBN-13
            if not isbn.isdigit():
                raise forms.ValidationError("Invalid ISBN-13 format.")

        return value

    @staticmethod
    def validate_confidence(value):
        """Validate confidence score"""
        if value is None:
            return value

        try:
            conf = float(value)
            if not (0 <= conf <= 1):
                raise forms.ValidationError("Confidence must be between 0 and 1.")
            return conf
        except (ValueError, TypeError):
            raise forms.ValidationError("Confidence must be a valid number.")

    @staticmethod
    def validate_comma_separated_list(value, field_name="items"):
        """Validate and clean comma-separated input"""
        if not value:
            return ""

        value_str = str(value).strip()
        if not value_str:
            return ""

        # Split by comma and clean each item
        item_list = [item.strip() for item in value_str.split(",") if item.strip()]
        if not item_list:
            return ""

        return ", ".join(item_list)

    @staticmethod
    def validate_integer_list(value, field_name="items"):
        """Validate comma-separated integer list"""
        if not value:
            return []

        value_str = str(value).strip()
        if not value_str:
            return []

        try:
            item_list = [int(item.strip()) for item in value_str.split(",") if item.strip()]
            return item_list
        except ValueError:
            raise forms.ValidationError(f"Invalid {field_name} - must be comma-separated integers.")


class StandardFormMixin(StandardWidgetMixin):
    """Complete form mixin with common functionality"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_standard_styling()

    def apply_standard_styling(self):
        """Apply standard Bootstrap styling to all form fields"""
        for field_name, field in self.fields.items():
            if isinstance(field.widget, forms.TextInput):
                field.widget.attrs.update({"class": "form-control"})
            elif isinstance(field.widget, forms.Select):
                field.widget.attrs.update({"class": "form-select"})
            elif isinstance(field.widget, forms.Textarea):
                field.widget.attrs.update({"class": "form-control"})
            elif isinstance(field.widget, forms.NumberInput):
                field.widget.attrs.update({"class": "form-control"})
            elif isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.update({"class": "form-check-input"})
            elif isinstance(field.widget, forms.FileInput):
                field.widget.attrs.update({"class": "form-control"})


class MetadataFormMixin(StandardFormMixin, BaseMetadataValidator):
    """Specialized mixin for metadata forms with common validation"""

    def get_standard_metadata_widgets(self):
        """Get standard widget configuration for metadata fields"""
        return {
            "final_title": self.text_required_with_placeholder("Enter title"),
            "final_author": self.text_required_with_placeholder("Enter author"),
            "final_series": self.text_with_placeholder("Enter series name"),
            "final_series_number": self.text_with_placeholder("Enter series number"),
            "final_publisher": self.text_with_placeholder("Enter publisher"),
            "final_cover_path": self.get_widget("file_input"),
            "language": self.get_widget("select"),
            "isbn": self.text_with_placeholder("Enter ISBN"),
            "publication_year": self.number_with_range(min_val=1000, max_val=2030, placeholder="Enter publication year"),
            "description": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 5,
                    "placeholder": "Enter description",
                }
            ),
            "is_reviewed": self.get_widget("checkbox"),
        }

    def clean_final_title(self):
        """Validate final title using base validator"""
        return self.validate_required_text(self.cleaned_data.get("final_title"), "Title")

    def clean_final_author(self):
        """Validate final author using base validator"""
        return self.validate_required_text(self.cleaned_data.get("final_author"), "Author")

    def clean_final_series_number(self):
        """Validate final series number using base validator"""
        return self.validate_series_number(self.cleaned_data.get("final_series_number"))

    def clean_publication_year(self):
        """Validate publication year using base validator"""
        return self.validate_year(self.cleaned_data.get("publication_year"), "Publication year")

    def clean_isbn(self):
        """Validate ISBN using base validator"""
        return self.validate_isbn(self.cleaned_data.get("isbn"))

    def clean_manual_genres(self):
        """Validate manual genres using base validator"""
        return self.validate_comma_separated_list(self.cleaned_data.get("manual_genres"), "Manual genres")
