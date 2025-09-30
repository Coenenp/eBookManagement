"""
User settings views.

This module contains views for user preferences and settings management.
"""
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.views.generic import TemplateView
from django.http import JsonResponse
from django.views.decorators.http import require_POST


class UserSettingsView(LoginRequiredMixin, TemplateView):
    """User settings and preferences view."""
    template_name = 'books/user_settings.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'user': self.request.user,
            'settings': {
                'theme': getattr(self.request.user, 'theme_preference', 'bootstrap'),
                'books_per_page': getattr(self.request.user, 'books_per_page', 25),
                'auto_scan': getattr(self.request.user, 'auto_scan_enabled', False),
            },
        })
        return context

    def post(self, request, *args, **kwargs):
        """Handle user settings updates."""
        try:
            # Parse settings from request
            theme = request.POST.get('theme', 'bootstrap')
            books_per_page = int(request.POST.get('books_per_page', 25))
            auto_scan = request.POST.get('auto_scan') == 'on'

            # Store in session for now (in real app would save to user profile)
            request.session['user_theme'] = theme
            request.session['user_books_per_page'] = books_per_page
            request.session['user_auto_scan'] = auto_scan

            return JsonResponse({
                'success': True,
                'message': 'Settings updated successfully'
            })
        except (ValueError, KeyError) as e:
            return JsonResponse({
                'success': False,
                'message': f'Invalid settings: {str(e)}'
            })


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

    # Remove theme preview from session
    user_theme = 'cosmo'  # Default theme, or get from user profile
    if hasattr(request.user, 'profile'):
        user_theme = getattr(request.user.profile, 'theme', 'cosmo')

    if 'preview_theme' in request.session:
        del request.session['preview_theme']

    return JsonResponse({'success': True, 'message': 'Preview cleared', 'theme': user_theme})
