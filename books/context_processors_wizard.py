"""
Context processors for wizard functionality.
"""

from books.models import Book, ScanFolder, SetupWizard


def wizard_context(request):
    """Add wizard-related context to all templates."""
    context = {
        "should_show_wizard_banner": False,
        "wizard_required": False,
    }

    if request.user.is_authenticated:
        # Check if wizard should be shown
        should_show = _should_show_wizard()

        if should_show:
            wizard, created = SetupWizard.get_or_create_for_user(request.user)

            # Show banner if wizard is not completed/skipped and we're not already in wizard
            if not wizard.is_completed and not wizard.is_skipped:
                is_wizard_url = "wizard" in request.path
                if not is_wizard_url:
                    context["should_show_wizard_banner"] = True
                    context["wizard_required"] = True
                    context["wizard_step_url"] = f"/wizard/{wizard.current_step}/"

    return context


def _should_show_wizard():
    """Determine if wizard should be shown based on system state."""
    # Don't show wizard if there are scan folders configured
    if ScanFolder.objects.exists():
        return False

    # Don't show wizard if there are books already imported
    if Book.objects.filter(is_placeholder=False).exists():
        return False

    return True
