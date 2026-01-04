"""
Setup Wizard Views for guiding new users through initial configuration.
"""
import logging
import os

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.views.generic import TemplateView

from books.models import AUDIOBOOK_FORMATS, COMIC_FORMATS, EBOOK_FORMATS, ScanFolder, SetupWizard

logger = logging.getLogger('books.scanner')


def get_all_media_extensions():
    """Get all supported media file extensions from centralized constants."""
    extensions = set()

    # Add all format lists with dots
    for fmt in EBOOK_FORMATS:
        extensions.add(f'.{fmt}')
    for fmt in COMIC_FORMATS:
        extensions.add(f'.{fmt}')
    for fmt in AUDIOBOOK_FORMATS:
        extensions.add(f'.{fmt}')

    return extensions


class WizardRequiredMixin:
    """Mixin to redirect users to wizard if not completed."""

    def dispatch(self, request, *args, **kwargs):
        # Check if this is a wizard URL before any processing
        is_wizard_url = 'wizard' in request.path

        if request.user.is_authenticated:
            # Check if wizard should be shown based on system state
            should_show_wizard = self._should_show_wizard()

            if should_show_wizard and not is_wizard_url:
                wizard, created = SetupWizard.get_or_create_for_user(request.user)
                # Only redirect if wizard is not completed or skipped
                if not wizard.is_completed and not wizard.is_skipped:
                    return redirect('books:wizard_step', step=wizard.current_step)

        # Call parent dispatch if it exists
        if hasattr(super(), 'dispatch'):
            return super().dispatch(request, *args, **kwargs)
        return None

    def _should_show_wizard(self):
        """Determine if wizard should be shown based on system state."""
        from books.models import Book, ScanFolder

        # Don't show wizard if there are scan folders configured
        if ScanFolder.objects.exists():
            # Auto-skip wizard if folders exist but wizard was never completed
            if hasattr(self, 'request') and self.request.user.is_authenticated:
                try:
                    wizard = SetupWizard.objects.get(user=self.request.user)
                    if not wizard.is_completed and not wizard.is_skipped:
                        wizard.skip_wizard()
                        logger.info(f"Auto-skipped wizard for user {self.request.user.username} - scan folders already exist")
                except SetupWizard.DoesNotExist:
                    pass
            return False

        # Don't show wizard if there are books already imported
        if Book.objects.filter(is_placeholder=False).exists():
            # Auto-skip wizard if books exist but wizard was never completed
            if hasattr(self, 'request') and self.request.user.is_authenticated:
                try:
                    wizard = SetupWizard.objects.get(user=self.request.user)
                    if not wizard.is_completed and not wizard.is_skipped:
                        wizard.skip_wizard()
                        logger.info(f"Auto-skipped wizard for user {self.request.user.username} - books already exist")
                except SetupWizard.DoesNotExist:
                    pass
            return False

        return True


class SetupWizardView(LoginRequiredMixin, TemplateView):
    """Base setup wizard view."""
    template_name = 'books/wizard/base.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        wizard, created = SetupWizard.get_or_create_for_user(self.request.user)

        # Get current step from URL or infer from view class
        current_step = self.kwargs.get('step')
        if not current_step:
            # Map view class to step name
            view_step_mapping = {
                'WizardWelcomeView': 'welcome',
                'WizardFoldersView': 'folders',
                'WizardContentTypesView': 'content_types',
                'WizardScrapersView': 'scrapers',
                'WizardCompleteView': 'complete',
            }
            current_step = view_step_mapping.get(self.__class__.__name__, 'welcome')

        # Calculate step number for display
        step_order = [choice[0] for choice in wizard.WIZARD_STEPS]
        try:
            step_index = step_order.index(current_step)
            step_number = step_index + 1
        except ValueError:
            step_index = 0
            step_number = 1

        # Calculate previous step based on current displayed step
        previous_step = None
        if step_index > 0:
            previous_step = step_order[step_index - 1]

        # Calculate current position progress (where the user is now)
        # vs completion progress (what they've actually finished)
        current_position_percentage = int((step_number / len(step_order)) * 100)

        context.update({
            'wizard': wizard,
            'step': current_step,
            'wizard_step': current_step,  # For test compatibility
            'step_number': step_number,
            'total_steps': len(step_order),
            'progress_percentage': wizard.progress_percentage,  # Completed steps
            'current_position_percentage': current_position_percentage,  # Current position
            'can_go_back': step_number > 1,
            'previous_step': previous_step,
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
        wizard = context['wizard']

        # Get common folder suggestions
        common_folders = self._get_suggested_folders()
        context['suggested_folders'] = common_folders

        # Prefill with previously selected folders if returning to this step
        selected_folders = wizard.selected_folders or []
        context['selected_folders'] = selected_folders

        # Mark suggested folders as selected if they were previously chosen
        suggested_folder_paths = [folder['path'] for folder in common_folders]
        for folder in common_folders:
            folder['selected'] = folder['path'] in selected_folders

        # Get custom folders (those not in suggested folders)
        custom_folders = [path for path in selected_folders if path not in suggested_folder_paths]
        context['custom_folders'] = custom_folders

        return context

    def post(self, request, *args, **kwargs):
        wizard, created = SetupWizard.get_or_create_for_user(request.user)

        if request.POST.get('action') == 'skip':
            wizard.skip_wizard()
            return redirect('books:dashboard')

        # Process selected folders
        selected_folders = request.POST.getlist('folders')

        # Process multiple custom folders
        custom_folders = request.POST.getlist('custom_folders')
        for custom_folder in custom_folders:
            custom_folder = custom_folder.strip()
            if custom_folder and os.path.exists(custom_folder):
                selected_folders.append(custom_folder)

        # Handle legacy single custom folder field for backward compatibility
        legacy_custom_folder = request.POST.get('custom_folder', '').strip()
        if legacy_custom_folder and os.path.exists(legacy_custom_folder):
            selected_folders.append(legacy_custom_folder)

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

    def _count_ebook_files(self, folder_path, max_depth=3):
        """Count ebook files in a folder with optimized performance."""
        count = 0
        files_checked = 0
        max_files_to_check = 300  # Limit total files for performance
        extensions = get_all_media_extensions()

        try:
            for root, dirs, files in os.walk(folder_path):
                # Limit depth to avoid scanning too deep
                depth = root[len(folder_path):].count(os.sep)
                if depth >= max_depth:
                    dirs[:] = []  # Don't recurse deeper
                    continue

                # Limit files checked per directory
                for file in files[:30]:  # Only check first 30 files per directory
                    files_checked += 1

                    if any(file.lower().endswith(ext) for ext in extensions):
                        count += 1
                        if count >= 100:  # Early termination at 100 for quick response
                            return "100+"

                    # Overall limit to prevent long scans
                    if files_checked >= max_files_to_check:
                        break

                if files_checked >= max_files_to_check:
                    break

        except (PermissionError, OSError):
            pass

        return count


class WizardContentTypesView(SetupWizardView):
    """Content type assignment step."""
    template_name = 'books/wizard/content_types.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        wizard, created = SetupWizard.get_or_create_for_user(self.request.user)

        # Get existing content type assignments
        existing_assignments = wizard.folder_content_types or {}

        # Analyze folders for suggested content types
        folder_analysis = []
        for folder_path in wizard.selected_folders:
            analysis = self._analyze_folder_content(folder_path)

            # Use existing assignment if available, otherwise use suggested type
            current_assignment = existing_assignments.get(folder_path)
            suggested_type = analysis.get('suggested_type', 'ebooks')

            folder_analysis.append({
                'path': folder_path,
                'name': os.path.basename(folder_path) or folder_path,
                'analysis': analysis,
                'suggested_type': suggested_type,
                'current_assignment': current_assignment or suggested_type
            })

        context['folder_analysis'] = folder_analysis
        context['folders'] = folder_analysis  # For test compatibility
        context['content_type_choices'] = ScanFolder.CONTENT_TYPE_CHOICES

        return context

    def post(self, request, *args, **kwargs):
        wizard, created = SetupWizard.get_or_create_for_user(request.user)

        if request.POST.get('action') == 'skip':
            wizard.skip_wizard()
            return redirect('books:dashboard')

        # Process content type assignments
        folder_content_types = {}

        # The template uses folder_{{ folder.path|hash }} as the field name
        for folder_path in wizard.selected_folders:
            folder_hash = str(abs(hash(str(folder_path))))
            folder_key = f"folder_{folder_hash}"
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
            'ebooks': {
                'total': 0,
                'formats': {
                    'epub': 0,
                    'mobi': 0,
                    'azw': 0,
                    'pdf': 0,
                    'other': 0
                }
            },
            'comics': {
                'total': 0,
                'formats': {
                    'cbr': 0,
                    'cbz': 0,
                    'cb7': 0,
                    'cbt': 0,
                    'pdf': 0
                }
            },
            'audiobooks': {
                'total': 0,
                'formats': {
                    'mp3': 0,
                    'm4a': 0,
                    'm4b': 0,
                    'aac': 0,
                    'flac': 0,
                    'other': 0
                }
            },
            'total_files': 0,
            'suggested_type': 'ebooks'
        }

        try:
            for root, dirs, files in os.walk(folder_path):
                # Allow deeper recursion but limit to reasonable depth for performance
                depth = root[len(folder_path):].count(os.sep)
                if depth >= 8:  # Increased from 2 to 8 for better coverage
                    dirs[:] = []
                    continue

                for file in files:
                    file_lower = file.lower()
                    file_ext = os.path.splitext(file_lower)[1]

                    # Check if this is a supported media file
                    if file_ext not in get_all_media_extensions():
                        continue

                    # Ebook formats
                    if file_ext in [f'.{fmt}' for fmt in EBOOK_FORMATS]:
                        if file_ext == '.epub':
                            analysis['ebooks']['formats']['epub'] += 1
                        elif file_ext in ['.mobi', '.azw', '.azw3']:
                            analysis['ebooks']['formats']['mobi'] += 1
                        elif file_ext == '.pdf':
                            # PDF could be ebook or comic, check folder context
                            if 'comic' in folder_path.lower() or 'manga' in folder_path.lower():
                                analysis['comics']['formats']['pdf'] += 1
                                analysis['comics']['total'] += 1
                                analysis['total_files'] += 1
                                continue  # Skip the ebook counting below
                            else:
                                analysis['ebooks']['formats']['pdf'] += 1
                        else:  # fb2, lit, pdb, prc, etc.
                            analysis['ebooks']['formats']['other'] += 1

                        analysis['ebooks']['total'] += 1
                        analysis['total_files'] += 1

                    # Comic formats (excluding PDF which is handled above)
                    elif file_ext in [f'.{fmt}' for fmt in COMIC_FORMATS if fmt != 'pdf']:
                        if file_ext == '.cbr':
                            analysis['comics']['formats']['cbr'] += 1
                        elif file_ext == '.cbz':
                            analysis['comics']['formats']['cbz'] += 1
                        elif file_ext == '.cb7':
                            analysis['comics']['formats']['cb7'] += 1
                        elif file_ext == '.cbt':
                            analysis['comics']['formats']['cbt'] += 1

                        analysis['comics']['total'] += 1
                        analysis['total_files'] += 1

                    # Audiobook formats
                    elif file_ext in [f'.{fmt}' for fmt in AUDIOBOOK_FORMATS]:
                        if file_ext == '.mp3':
                            analysis['audiobooks']['formats']['mp3'] += 1
                        elif file_ext in ['.m4a', '.m4b']:
                            analysis['audiobooks']['formats']['m4a'] += 1
                        elif file_ext == '.aac':
                            analysis['audiobooks']['formats']['aac'] += 1
                        elif file_ext == '.flac':
                            analysis['audiobooks']['formats']['flac'] += 1
                        else:  # ogg, wav, etc.
                            analysis['audiobooks']['formats']['other'] += 1

                        analysis['audiobooks']['total'] += 1
                        analysis['total_files'] += 1

                    # Increased limit and only count relevant files
                    if analysis['total_files'] >= 2000:  # Increased from 200 to 2000
                        break

        except (PermissionError, OSError):
            pass

        # Suggest content type based on analysis
        if analysis['comics']['total'] > analysis['ebooks']['total'] and analysis['comics']['total'] > analysis['audiobooks']['total']:
            analysis['suggested_type'] = 'comics'
        elif analysis['audiobooks']['total'] > analysis['ebooks']['total']:
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
        wizard = context['wizard']

        # Get existing scraper configuration
        existing_config = wizard.scraper_config or {}

        # Check environment variables as fallback
        import os
        env_google_key = os.environ.get('GOOGLE_BOOKS_API_KEY', '')
        env_comicvine_key = os.environ.get('COMICVINE_API_KEY', '')

        # Get available data sources that might need configuration
        scrapers_info = [
            {
                'id': 'open_library',
                'name': 'Open Library',
                'description': 'Free service for book metadata and covers',
                'required': False,
                'config_needed': False,
                'status': 'Built-in'
            },
            {
                'id': 'google_books',
                'name': 'Google Books',
                'description': 'Google\'s book database with rich metadata',
                'required': False,
                'config_needed': True,
                'config_field': 'google_books_api_key',
                'current_value': existing_config.get('google_books_api_key', env_google_key),
                'status': 'Optional API Key'
            },
            {
                'id': 'comic_vine',
                'name': 'Comic Vine',
                'description': 'Comprehensive comic book database',
                'required': False,
                'config_needed': True,
                'config_field': 'comicvine_api_key',
                'current_value': existing_config.get('comicvine_api_key', env_comicvine_key),
                'status': 'Optional API Key'
            }
        ]

        context['scrapers_info'] = scrapers_info
        context['scrapers'] = scrapers_info  # For test compatibility
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
            # Redirect to scanning dashboard with auto-start parameter
            messages.success(request, "Setup complete! Starting scan for all configured folders...")
            return redirect('books:scan_dashboard')

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
    """AJAX endpoint to validate a folder path with optimized performance."""
    if request.method == 'POST':
        folder_path = request.POST.get('path', '').strip()

        if not folder_path:
            return JsonResponse({'valid': False, 'error': 'No path provided'})

        if not os.path.exists(folder_path):
            return JsonResponse({'valid': False, 'error': 'Path does not exist'})

        if not os.path.isdir(folder_path):
            return JsonResponse({'valid': False, 'error': 'Path is not a directory'})

        # Fast validation with early termination for performance
        try:
            file_count = 0
            files_checked = 0
            max_files_to_check = 500  # Limit total files checked for performance
            max_depth = 4  # Reduced depth for faster scanning
            early_termination_count = 20  # Stop after finding this many media files for quick validation

            # Use centralized extension list
            extensions = get_all_media_extensions()

            for root, dirs, files in os.walk(folder_path):
                depth = root[len(folder_path):].count(os.sep)
                if depth >= max_depth:
                    dirs[:] = []
                    continue

                # Limit files checked per directory for performance
                for file in files[:50]:  # Only check first 50 files per directory
                    files_checked += 1

                    if any(file.lower().endswith(ext) for ext in extensions):
                        file_count += 1

                        # Early termination for quick validation
                        if file_count >= early_termination_count:
                            return JsonResponse({
                                'valid': True,
                                'file_count': f"{file_count}+",
                                'name': os.path.basename(folder_path) or folder_path
                            })

                    # Overall limit to prevent long scans
                    if files_checked >= max_files_to_check:
                        break

                if files_checked >= max_files_to_check:
                    break

            # Return result even with limited scan
            if file_count > 0:
                return JsonResponse({
                    'valid': True,
                    'file_count': file_count,
                    'name': os.path.basename(folder_path) or folder_path
                })
            else:
                # No media files found in limited scan - still valid folder
                return JsonResponse({
                    'valid': True,
                    'file_count': 0,
                    'name': os.path.basename(folder_path) or folder_path
                })

        except (PermissionError, OSError) as e:
            return JsonResponse({'valid': False, 'error': f'Cannot access folder: {str(e)}'})
        except Exception as e:
            return JsonResponse({'valid': False, 'error': f'Error validating folder: {str(e)}'})

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

    # For GET requests (navigation), we don't update the wizard's current_step
    # This allows users to go back and forth without losing their progress
    # Instantiate view and manually set the kwargs
    view_instance = view_class()
    view_instance.kwargs = {'step': step}
    view_instance.request = request
    view_instance.args = []

    return view_instance.dispatch(request)
