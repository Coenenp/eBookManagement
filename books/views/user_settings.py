"""
User settings views.

This module contains views for user preferences and settings management.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.shortcuts import redirect
from django.views.decorators.http import require_POST
from django.views.generic import TemplateView

from books.constants import DEFAULT_THEME, DEFAULT_USER_ITEMS_PER_PAGE
from books.forms import UserProfileForm
from books.models import UserProfile


class UserSettingsView(LoginRequiredMixin, TemplateView):
    """User settings and preferences view."""

    template_name = "books/user_settings.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Get or create user profile
        profile = UserProfile.get_or_create_for_user(self.request.user)

        # Create form with current profile data
        form = UserProfileForm(instance=profile)

        # Get predefined and user templates for renaming
        from books.utils.renaming_engine import PREDEFINED_PATTERNS

        # Convert PREDEFINED_PATTERNS to list format for template
        system_templates = [
            {"key": key, "name": data["name"], "folder": data["folder"], "filename": data["filename"], "description": data.get("description", ""), "is_system": True}
            for key, data in PREDEFINED_PATTERNS.items()
        ]

        # Get user templates
        user_templates = [
            {
                "key": f"user-{template['name']}",
                "name": template["name"],
                "folder": template["folder"],
                "filename": template["filename"],
                "description": template.get("description", ""),
                "is_system": False,
            }
            for template in profile.saved_patterns
        ]

        # Find default template by matching patterns
        default_template_key = None
        for template in user_templates + system_templates:
            if template["folder"] == profile.default_folder_pattern and template["filename"] == profile.default_filename_pattern:
                default_template_key = template["key"]
                break

        # Fall back to 'comprehensive' if no match found
        if not default_template_key:
            default_template_key = "comprehensive"

        # Select a few system templates to show as examples (using actual template data)
        example_template_keys = ["simple_author_title", "category_author", "series_aware"]
        pattern_examples = []
        for key in example_template_keys:
            if key in PREDEFINED_PATTERNS:
                template = PREDEFINED_PATTERNS[key]
                # Generate a sample result for display
                sample_result = self._generate_sample_result(template["folder"], template["filename"])
                pattern_examples.append({"name": template["name"], "folder": template["folder"], "filename": template["filename"], "result": sample_result})

        context.update(
            {
                "user": self.request.user,
                "profile": profile,
                "form": form,
                "current_theme": profile.theme,
                "system_templates": system_templates,
                "user_templates": user_templates,
                "default_template_key": default_template_key,
                "pattern_examples": pattern_examples,
                "settings": {
                    "theme": profile.theme,
                    "books_per_page": profile.items_per_page,
                    "auto_scan": getattr(self.request.user, "auto_scan_enabled", False),
                },
            }
        )
        return context

    def _generate_sample_result(self, folder_pattern, filename_pattern):
        """Generate a sample file path from patterns for preview."""
        # Sample replacements for common tokens
        replacements = {
            "${language}": "English",
            "${author.sortname}": "Asimov, Isaac",
            "${author}": "Isaac Asimov",
            "${title}": "Foundation",
            "${category}": "Fiction",
            "${bookseries.title}": "Foundation Series",
            "${bookseries.number}": "01",
            "${format}": "ebook",
            "${ext}": "epub",
        }

        folder = folder_pattern
        filename = filename_pattern

        # Replace all tokens
        for token, value in replacements.items():
            folder = folder.replace(token, value)
            filename = filename.replace(token, value)

        return f"{folder}/{filename}"

    def post(self, request, *args, **kwargs):
        """Handle user settings updates."""
        # Get or create user profile
        profile = UserProfile.get_or_create_for_user(request.user)

        # Create form with POST data
        form = UserProfileForm(request.POST, instance=profile)

        # Check if this is an AJAX request
        is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"

        if form.is_valid():
            # Save the form which will update the profile
            form.save()

            # Store theme in session for immediate effect (until next page load)
            # This helps the theme context processor pick up the change immediately
            request.session["user_theme"] = form.cleaned_data["theme"]

            if is_ajax:
                return JsonResponse({"success": True, "message": "Settings updated successfully"})
            else:
                # Regular form submission - redirect back to settings page
                messages.success(request, "Settings updated successfully!")
                return redirect("books:user_settings")
        else:
            # Form validation failed
            error_msg = "Please correct the errors below."
            if form.errors:
                error_msg = "; ".join([f"{field}: {', '.join(errors)}" for field, errors in form.errors.items()])

            if is_ajax:
                return JsonResponse({"success": False, "message": error_msg})
            else:
                # Regular form submission - redirect back with error message
                messages.error(request, error_msg)
                return redirect("books:user_settings")


@login_required
@require_POST
def preview_theme(request):
    """Preview a theme setting."""
    if request.method != "POST":
        return JsonResponse({"success": False, "message": "POST required"}, status=405)

    theme = request.POST.get("theme")
    if not theme:
        return JsonResponse({"success": False, "error": "Theme parameter required"})

    # Get valid themes from context processor to match what's available in templates
    from books.context_processors import theme_context

    context_themes = theme_context(request)["bootswatch_themes"]
    valid_themes = [theme_data["value"] for theme_data in context_themes]

    if theme not in valid_themes:
        return JsonResponse({"success": False, "error": "Invalid theme"})

    # Store theme preview in session
    request.session["preview_theme"] = theme

    return JsonResponse({"success": True, "theme": theme, "message": f"Theme preview set to {theme}"})


@login_required
def clear_theme_preview(request):
    """Clear theme preview setting."""
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "POST method required"}, status=405)

    # Get user's saved theme from profile
    profile = UserProfile.get_or_create_for_user(request.user)
    user_theme = profile.theme

    if "preview_theme" in request.session:
        del request.session["preview_theme"]

    return JsonResponse({"success": True, "message": "Preview cleared", "theme": user_theme})


@login_required
@require_POST
def reset_to_defaults(request):
    """Reset user settings to default values."""
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "POST method required"}, status=405)

    # Get or create user profile
    profile = UserProfile.get_or_create_for_user(request.user)

    # Reset to default values (these should match the model field defaults)
    profile.theme = DEFAULT_THEME  # Default theme from constants
    profile.items_per_page = DEFAULT_USER_ITEMS_PER_PAGE  # Default items per page from constants
    profile.show_covers_in_list = True  # Default show covers
    profile.default_view_mode = "table"  # Default view mode
    profile.share_reading_progress = False  # Default sharing setting
    profile.default_folder_pattern = ""  # Default folder pattern
    profile.default_filename_pattern = ""  # Default filename pattern
    profile.include_companion_files = True  # Default include companion files

    # Save the profile with default values
    profile.save()

    # Clear any theme preview session data
    if "preview_theme" in request.session:
        del request.session["preview_theme"]

    # Update session theme for immediate effect
    request.session["user_theme"] = profile.theme

    # Check if this is an AJAX request
    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"

    if is_ajax:
        return JsonResponse(
            {
                "success": True,
                "message": "Settings reset to default values",
                "defaults": {
                    "theme": profile.theme,
                    "items_per_page": profile.items_per_page,
                    "show_covers_in_list": profile.show_covers_in_list,
                    "default_view_mode": profile.default_view_mode,
                    "share_reading_progress": profile.share_reading_progress,
                    "default_folder_pattern": profile.default_folder_pattern,
                    "default_filename_pattern": profile.default_filename_pattern,
                    "include_companion_files": profile.include_companion_files,
                },
            }
        )
    else:
        messages.success(request, "Settings reset to default values!")
        return redirect("books:user_settings")


@login_required
@require_POST
def save_default_template(request):
    """Save selected template as user's default."""
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "POST method required"}, status=405)

    template_key = request.POST.get("template_key")
    folder_pattern = request.POST.get("folder_pattern")
    filename_pattern = request.POST.get("filename_pattern")

    if not template_key or not folder_pattern or not filename_pattern:
        return JsonResponse({"success": False, "error": "Missing required parameters"})

    try:
        # Get or create user profile
        profile = UserProfile.get_or_create_for_user(request.user)

        # Update default patterns
        profile.default_folder_pattern = folder_pattern
        profile.default_filename_pattern = filename_pattern
        profile.save()

        return JsonResponse({"success": True, "message": "Template saved as default", "folder_pattern": folder_pattern, "filename_pattern": filename_pattern})

    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)})
