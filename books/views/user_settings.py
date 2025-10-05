"""
User settings views.

This module contains views for user preferences and settings management.
"""
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.views.generic import TemplateView
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.shortcuts import redirect
from ..models import UserProfile
from ..forms import UserProfileForm


class UserSettingsView(LoginRequiredMixin, TemplateView):
    """User settings and preferences view."""
    template_name = 'books/user_settings.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Get or create user profile
        profile = UserProfile.get_or_create_for_user(self.request.user)

        # Create form with current profile data
        form = UserProfileForm(instance=profile)

        context.update({
            'user': self.request.user,
            'profile': profile,
            'form': form,
            'current_theme': profile.theme,
            'settings': {
                'theme': profile.theme,
                'books_per_page': profile.items_per_page,
                'auto_scan': getattr(self.request.user, 'auto_scan_enabled', False),
            },
        })
        return context

    def post(self, request, *args, **kwargs):
        """Handle user settings updates."""
        # Get or create user profile
        profile = UserProfile.get_or_create_for_user(request.user)

        # Create form with POST data
        form = UserProfileForm(request.POST, instance=profile)

        # Check if this is an AJAX request
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

        if form.is_valid():
            # Save the form which will update the profile
            form.save()

            # Store theme in session for immediate effect (until next page load)
            # This helps the theme context processor pick up the change immediately
            request.session['user_theme'] = form.cleaned_data['theme']

            if is_ajax:
                return JsonResponse({
                    'success': True,
                    'message': 'Settings updated successfully'
                })
            else:
                # Regular form submission - redirect back to settings page
                messages.success(request, 'Settings updated successfully!')
                return redirect('books:user_settings')
        else:
            # Form validation failed
            error_msg = 'Please correct the errors below.'
            if form.errors:
                error_msg = '; '.join([f"{field}: {', '.join(errors)}" for field, errors in form.errors.items()])

            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': error_msg
                })
            else:
                # Regular form submission - redirect back with error message
                messages.error(request, error_msg)
                return redirect('books:user_settings')


@login_required
@require_POST
def preview_theme(request):
    """Preview a theme setting."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'POST required'}, status=405)

    theme = request.POST.get('theme')
    if not theme:
        return JsonResponse({'success': False, 'error': 'Theme parameter required'})

    # Get valid themes from context processor to match what's available in templates
    from books.context_processors import theme_context
    context_themes = theme_context(request)['bootswatch_themes']
    valid_themes = [theme_data['value'] for theme_data in context_themes]

    if theme not in valid_themes:
        return JsonResponse({'success': False, 'error': 'Invalid theme'})

    # Store theme preview in session
    request.session['preview_theme'] = theme

    return JsonResponse({'success': True, 'theme': theme, 'message': f'Theme preview set to {theme}'})


@login_required
def clear_theme_preview(request):
    """Clear theme preview setting."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST method required'}, status=405)

    # Get user's saved theme from profile
    profile = UserProfile.get_or_create_for_user(request.user)
    user_theme = profile.theme

    if 'preview_theme' in request.session:
        del request.session['preview_theme']

    return JsonResponse({'success': True, 'message': 'Preview cleared', 'theme': user_theme})


@login_required
@require_POST
def reset_to_defaults(request):
    """Reset user settings to default values."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST method required'}, status=405)

    # Get or create user profile
    profile = UserProfile.get_or_create_for_user(request.user)

    # Reset to default values (these should match the model field defaults)
    profile.theme = 'flatly'  # Default theme from UserProfile model
    profile.items_per_page = 50  # Default items per page
    profile.show_covers_in_list = True  # Default show covers
    profile.default_view_mode = 'table'  # Default view mode
    profile.share_reading_progress = False  # Default sharing setting
    profile.default_folder_pattern = ''  # Default folder pattern
    profile.default_filename_pattern = ''  # Default filename pattern
    profile.include_companion_files = True  # Default include companion files

    # Save the profile with default values
    profile.save()

    # Clear any theme preview session data
    if 'preview_theme' in request.session:
        del request.session['preview_theme']

    # Update session theme for immediate effect
    request.session['user_theme'] = profile.theme

    # Check if this is an AJAX request
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    if is_ajax:
        return JsonResponse({
            'success': True,
            'message': 'Settings reset to default values',
            'defaults': {
                'theme': profile.theme,
                'items_per_page': profile.items_per_page,
                'show_covers_in_list': profile.show_covers_in_list,
                'default_view_mode': profile.default_view_mode,
                'share_reading_progress': profile.share_reading_progress,
                'default_folder_pattern': profile.default_folder_pattern,
                'default_filename_pattern': profile.default_filename_pattern,
                'include_companion_files': profile.include_companion_files,
            }
        })
    else:
        messages.success(request, 'Settings reset to default values!')
        return redirect('books:user_settings')
