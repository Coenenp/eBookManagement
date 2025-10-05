"""
Setup Wizard Views for guiding new users through initial configuration.
"""
import os
import logging
from django.shortcuts import redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse
from django.utils import timezone

from books.models import SetupWizard, ScanFolder

logger = logging.getLogger('books.scanner')


class WizardRequiredMixin:
    """Mixin to redirect users to wizard if not completed."""

    def dispatch(self, request, *args, **kwargs):
        # Check if this is a wizard URL before any processing
        is_wizard_url = 'wizard' in request.path

        if request.user.is_authenticated:
            wizard, created = SetupWizard.get_or_create_for_user(request.user)
            if not wizard.is_completed and not wizard.is_skipped and not is_wizard_url:
                # Redirect to current wizard step if not accessing wizard itself
                return redirect('books:wizard_step', step=wizard.current_step)

        # Call parent dispatch if it exists
        if hasattr(super(), 'dispatch'):
            return super().dispatch(request, *args, **kwargs)
        return None


class SetupWizardView(LoginRequiredMixin, TemplateView):
    """Base setup wizard view."""
    template_name = 'books/wizard/base.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        wizard, created = SetupWizard.get_or_create_for_user(self.request.user)

        context.update({
            'wizard': wizard,
            'step': self.kwargs.get('step', wizard.current_step),
            'progress_percentage': wizard.progress_percentage,
        })
        return context


class WizardWelcomeView(SetupWizardView):
    """Welcome step of the setup wizard."""
    template_name = 'books/wizard/welcome.html'

    def post(self, request, *args, **kwargs):
        wizard, created = SetupWizard.get_or_create_for_user(request.user)

        if request.POST.get('action') == 'skip':
            wizard.skip_wizard()
            messages.success(request, "Setup wizard skipped. You can configure settings later.")
            return redirect('books:dashboard')

        # Mark welcome step as completed
        wizard.mark_step_completed('welcome')
        return redirect('books:wizard_step', step='folders')


class WizardFoldersView(SetupWizardView):
    """Folder selection step."""
    template_name = 'books/wizard/folders.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Get common folder suggestions
        common_folders = self._get_suggested_folders()
        context['suggested_folders'] = common_folders

        return context

    def post(self, request, *args, **kwargs):
        wizard, created = SetupWizard.get_or_create_for_user(request.user)

        if request.POST.get('action') == 'skip':
            wizard.skip_wizard()
            return redirect('books:dashboard')

        # Process selected folders
        selected_folders = request.POST.getlist('folders')
        custom_folder = request.POST.get('custom_folder', '').strip()

        if custom_folder and os.path.exists(custom_folder):
            selected_folders.append(custom_folder)

        # Validate folders exist
        valid_folders = [folder for folder in selected_folders if os.path.exists(folder)]

        if not valid_folders:
            messages.error(request, "Please select at least one valid folder.")
            return self.get(request, *args, **kwargs)

        # Save selected folders to wizard
        wizard.selected_folders = valid_folders
        wizard.mark_step_completed('folders')
        wizard.save()

        messages.success(request, f"Selected {len(valid_folders)} folder(s) for scanning.")
        return redirect('books:wizard_step', step='content_types')

    def _get_suggested_folders(self):
        """Get suggested common ebook folders."""
        user_home = os.path.expanduser('~')

        suggestions = []
        common_paths = [
            os.path.join(user_home, 'Documents', 'Books'),
            os.path.join(user_home, 'Documents', 'eBooks'),
            os.path.join(user_home, 'Downloads'),
            os.path.join(user_home, 'Desktop', 'Books'),
            'C:\\Books' if os.name == 'nt' else '/home/books',
            'D:\\eBooks' if os.name == 'nt' else '/media/ebooks',
        ]

        for path in common_paths:
            if os.path.exists(path):
                # Count potential ebook files
                file_count = self._count_ebook_files(path)
                suggestions.append({
                    'path': path,
                    'name': os.path.basename(path) or path,
                    'file_count': file_count,
                    'exists': True
                })

        return suggestions

    def _count_ebook_files(self, folder_path, max_depth=2):
        """Count ebook files in a folder (limited depth to avoid performance issues)."""
        count = 0
        extensions = {'.epub', '.pdf', '.mobi', '.azw', '.azw3', '.cbr', '.cbz', '.fb2'}

        try:
            for root, dirs, files in os.walk(folder_path):
                # Limit depth to avoid scanning too deep
                depth = root[len(folder_path):].count(os.sep)
                if depth >= max_depth:
                    dirs[:] = []  # Don't recurse deeper
                    continue

                for file in files:
                    if any(file.lower().endswith(ext) for ext in extensions):
                        count += 1
                        if count >= 100:  # Stop counting at 100 for performance
                            return "100+"

        except (PermissionError, OSError):
            pass

        return count


class WizardContentTypesView(SetupWizardView):
    """Content type assignment step."""
    template_name = 'books/wizard/content_types.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        wizard, created = SetupWizard.get_or_create_for_user(self.request.user)

        # Analyze folders for suggested content types
        folder_analysis = []
        for folder_path in wizard.selected_folders:
            analysis = self._analyze_folder_content(folder_path)
            folder_analysis.append({
                'path': folder_path,
                'name': os.path.basename(folder_path) or folder_path,
                'analysis': analysis,
                'suggested_type': analysis.get('suggested_type', 'ebooks')
            })

        context['folder_analysis'] = folder_analysis
        context['content_type_choices'] = ScanFolder.CONTENT_TYPE_CHOICES

        return context

    def post(self, request, *args, **kwargs):
        wizard, created = SetupWizard.get_or_create_for_user(request.user)

        if request.POST.get('action') == 'skip':
            wizard.skip_wizard()
            return redirect('books:dashboard')

        # Process content type assignments
        folder_content_types = {}

        for index, folder_path in enumerate(wizard.selected_folders, 1):
            folder_key = f"folder_{index}"  # Match template naming: folder_1, folder_2, etc.
            content_type = request.POST.get(folder_key, 'ebooks')
            folder_content_types[folder_path] = content_type

        # Save content type assignments
        wizard.folder_content_types = folder_content_types
        wizard.mark_step_completed('content_types')
        wizard.save()

        return redirect('books:wizard_step', step='scrapers')

    def _analyze_folder_content(self, folder_path):
        """Analyze folder content to suggest content type."""
        analysis = {
            'epub_count': 0,
            'pdf_count': 0,
            'comic_count': 0,
            'audio_count': 0,
            'total_files': 0,
            'suggested_type': 'ebooks'
        }

        try:
            for root, dirs, files in os.walk(folder_path):
                # Limit depth for performance
                depth = root[len(folder_path):].count(os.sep)
                if depth >= 2:
                    dirs[:] = []
                    continue

                for file in files:
                    file_lower = file.lower()

                    if file_lower.endswith(('.epub', '.mobi', '.azw', '.azw3', '.fb2')):
                        analysis['epub_count'] += 1
                    elif file_lower.endswith('.pdf'):
                        analysis['pdf_count'] += 1
                    elif file_lower.endswith(('.cbr', '.cbz', '.cb7', '.cbt')):
                        analysis['comic_count'] += 1
                    elif file_lower.endswith(('.mp3', '.m4a', '.m4b', '.aac', '.flac', '.ogg')):
                        analysis['audio_count'] += 1

                    analysis['total_files'] += 1

                    # Stop counting at reasonable limit for performance
                    if analysis['total_files'] >= 200:
                        break

        except (PermissionError, OSError):
            pass

        # Suggest content type based on analysis
        if analysis['comic_count'] > analysis['epub_count'] and analysis['comic_count'] > analysis['pdf_count']:
            analysis['suggested_type'] = 'comics'
        elif analysis['audio_count'] > analysis['epub_count']:
            analysis['suggested_type'] = 'audiobooks'
        elif 'comic' in folder_path.lower() or 'manga' in folder_path.lower():
            analysis['suggested_type'] = 'comics'
        elif 'audio' in folder_path.lower() or 'audiobook' in folder_path.lower():
            analysis['suggested_type'] = 'audiobooks'
        else:
            analysis['suggested_type'] = 'ebooks'

        return analysis


class WizardScrapersView(SetupWizardView):
    """Scraper configuration step."""
    template_name = 'books/wizard/scrapers.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Get available data sources that might need configuration
        scrapers_info = [
            {
                'name': 'Open Library',
                'description': 'Free service for book metadata and covers',
                'required': False,
                'config_needed': False,
                'status': 'Built-in'
            },
            {
                'name': 'Google Books',
                'description': 'Google\'s book database with rich metadata',
                'required': False,
                'config_needed': True,
                'config_field': 'google_books_api_key',
                'status': 'Optional API Key'
            },
            {
                'name': 'Comic Vine',
                'description': 'Comprehensive comic book database',
                'required': False,
                'config_needed': True,
                'config_field': 'comicvine_api_key',
                'status': 'Optional API Key'
            }
        ]

        context['scrapers_info'] = scrapers_info
        return context

    def post(self, request, *args, **kwargs):
        wizard, created = SetupWizard.get_or_create_for_user(request.user)

        if request.POST.get('action') == 'skip':
            wizard.skip_wizard()
            return redirect('books:dashboard')

        # Process scraper configuration
        scraper_config = {}

        # Google Books API Key
        google_api_key = request.POST.get('google_books_api_key', '').strip()
        if google_api_key:
            scraper_config['google_books_api_key'] = google_api_key

        # Comic Vine API Key
        comicvine_api_key = request.POST.get('comicvine_api_key', '').strip()
        if comicvine_api_key:
            scraper_config['comicvine_api_key'] = comicvine_api_key

        # Save configuration
        wizard.scraper_config = scraper_config
        wizard.mark_step_completed('scrapers')
        wizard.save()

        return redirect('books:wizard_step', step='complete')


class WizardCompleteView(SetupWizardView):
    """Final completion step."""
    template_name = 'books/wizard/complete.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        wizard, created = SetupWizard.get_or_create_for_user(self.request.user)

        # Create scan folders from wizard data
        self._create_scan_folders(wizard)

        context.update({
            'folder_count': len(wizard.selected_folders) if wizard.selected_folders else 0,
            'configured_folders': [
                {
                    'path': path,
                    'content_type': wizard.folder_content_types.get(path, 'Unknown')
                } for path in wizard.selected_folders
            ] if wizard.selected_folders else [],
            'configured_scrapers': [
                {
                    'name': key.replace('_api_key', '').replace('_', ' ').title(),
                    'has_api_key': bool(value)
                } for key, value in wizard.scraper_config.items()
                if key.endswith('_api_key') and value
            ],
        })

        return context

    def post(self, request, *args, **kwargs):
        wizard, created = SetupWizard.get_or_create_for_user(request.user)

        # Mark wizard as complete
        if not wizard.is_completed:
            wizard.is_completed = True
            wizard.completed_at = timezone.now()
            wizard.current_step = 'complete'
            wizard.save()

        # Start initial scan if requested
        if request.POST.get('start_scan') == 'true':
            # Create scan folders first
            self._create_scan_folders(wizard)
            return redirect('books:trigger_scan')

        messages.success(request, "Setup complete! Welcome to your ebook library.")
        return redirect('books:dashboard')

    def _create_scan_folders(self, wizard):
        """Create ScanFolder objects from wizard configuration."""
        for folder_path in wizard.selected_folders:
            content_type = wizard.folder_content_types.get(folder_path, 'ebooks')

            # Create scan folder if it doesn't exist
            folder_name = os.path.basename(folder_path) or f"Folder {folder_path}"

            scan_folder, created = ScanFolder.objects.get_or_create(
                path=folder_path,
                defaults={
                    'name': folder_name,
                    'content_type': content_type,
                    'language': 'en',  # Default language
                    'is_active': True,
                }
            )

            if created:
                logger.info(f"Created scan folder: {scan_folder.name} ({content_type})")


# AJAX endpoints for wizard
@login_required
def wizard_validate_folder(request):
    """AJAX endpoint to validate a folder path."""
    if request.method == 'POST':
        folder_path = request.POST.get('path', '').strip()

        if not folder_path:
            return JsonResponse({'valid': False, 'error': 'No path provided'})

        if not os.path.exists(folder_path):
            return JsonResponse({'valid': False, 'error': 'Path does not exist'})

        if not os.path.isdir(folder_path):
            return JsonResponse({'valid': False, 'error': 'Path is not a directory'})

        # Count ebook files
        try:
            file_count = 0
            extensions = {'.epub', '.pdf', '.mobi', '.azw', '.azw3', '.cbr', '.cbz', '.fb2'}

            for root, dirs, files in os.walk(folder_path):
                depth = root[len(folder_path):].count(os.sep)
                if depth >= 2:  # Limit depth
                    dirs[:] = []
                    continue

                for file in files:
                    if any(file.lower().endswith(ext) for ext in extensions):
                        file_count += 1
                        if file_count >= 50:  # Limit for performance
                            break

            return JsonResponse({
                'valid': True,
                'file_count': file_count,
                'name': os.path.basename(folder_path) or folder_path
            })

        except Exception as e:
            return JsonResponse({'valid': False, 'error': f'Error accessing folder: {str(e)}'})

    return JsonResponse({'valid': False, 'error': 'Invalid request'})


@login_required
def wizard_skip(request):
    """Skip the entire wizard."""
    if request.method == 'POST':
        wizard, created = SetupWizard.get_or_create_for_user(request.user)
        wizard.skip_wizard()

        messages.success(request, "Setup wizard skipped. You can configure settings later in the management section.")
        return JsonResponse({'success': True, 'redirect': reverse('books:dashboard')})

    return JsonResponse({'success': False, 'error': 'Invalid request'})


def wizard_dispatcher(request, step):
    """Dispatch wizard requests to appropriate view based on step."""
    step_views = {
        'welcome': WizardWelcomeView,
        'folders': WizardFoldersView,
        'content_types': WizardContentTypesView,
        'scrapers': WizardScrapersView,
        'complete': WizardCompleteView,
    }

    view_class = step_views.get(step)
    if not view_class:
        from django.http import Http404
        raise Http404(f"Unknown wizard step: {step}")

    return view_class.as_view()(request)
