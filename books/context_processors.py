"""
Context processors for the books app.
"""
from django.conf import settings


def theme_context(request):
    """Add theme context to all templates"""

    # Default theme
    theme = getattr(settings, 'DEFAULT_BOOTSWATCH_THEME', 'flatly')

    # If user is authenticated, get their theme preference
    if request.user.is_authenticated:
        try:
            from books.models import UserProfile
            profile = UserProfile.get_or_create_for_user(request.user)
            theme = profile.theme
        except Exception:
            # Fallback to default theme if profile doesn't exist or error occurs
            pass

    # Check for session override (for preview functionality)
    if 'preview_theme' in request.session:
        theme = request.session['preview_theme']

    return {
        'current_theme': theme,
        'bootswatch_themes': [
            {'value': 'flatly', 'name': 'Flatly', 'description': 'Clean and modern'},
            {'value': 'cosmo', 'name': 'Cosmo', 'description': 'Friendly and accessible'},
            {'value': 'bootstrap', 'name': 'Bootstrap Default', 'description': 'Classic Bootstrap'},
            {'value': 'cerulean', 'name': 'Cerulean', 'description': 'Blue and professional'},
            {'value': 'cyborg', 'name': 'Cyborg', 'description': 'Dark futuristic'},
            {'value': 'darkly', 'name': 'Darkly', 'description': 'Dark mode elegance'},
            {'value': 'journal', 'name': 'Journal', 'description': 'Readable typography'},
            {'value': 'litera', 'name': 'Litera', 'description': 'Book-inspired'},
            {'value': 'lumen', 'name': 'Lumen', 'description': 'Light and airy'},
            {'value': 'lux', 'name': 'Lux', 'description': 'Sophisticated gold accents'},
            {'value': 'materia', 'name': 'Materia', 'description': 'Material Design inspired'},
            {'value': 'minty', 'name': 'Minty', 'description': 'Fresh mint green'},
            {'value': 'morph', 'name': 'Morph', 'description': 'Neumorphic design'},
            {'value': 'pulse', 'name': 'Pulse', 'description': 'Purple energy'},
            {'value': 'quartz', 'name': 'Quartz', 'description': 'Warm and inviting'},
            {'value': 'sandstone', 'name': 'Sandstone', 'description': 'Desert-inspired'},
            {'value': 'simplex', 'name': 'Simplex', 'description': 'Minimalist'},
            {'value': 'sketchy', 'name': 'Sketchy', 'description': 'Hand-drawn style'},
            {'value': 'slate', 'name': 'Slate', 'description': 'Dark professional'},
            {'value': 'solar', 'name': 'Solar', 'description': 'Dark amber'},
            {'value': 'spacelab', 'name': 'Spacelab', 'description': 'Space-age blue'},
            {'value': 'superhero', 'name': 'Superhero', 'description': 'Comic book inspired'},
            {'value': 'united', 'name': 'United', 'description': 'Corporate orange'},
            {'value': 'vapor', 'name': 'Vapor', 'description': 'Vaporwave aesthetic'},
            {'value': 'yeti', 'name': 'Yeti', 'description': 'Crisp winter'},
            {'value': 'zephyr', 'name': 'Zephyr', 'description': 'Soft and gentle'},
        ]
    }
