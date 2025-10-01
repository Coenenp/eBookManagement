/**
 * Wizard Content Types JavaScript functionality
 * Handles content type preview updates and suggestion badge management
 */

document.addEventListener('DOMContentLoaded', function() {
    // Update preview when content type changes
    document.querySelectorAll('select[name^="folder_"]').forEach(function(select) {
        select.addEventListener('change', function() {
            updateContentTypePreview(this);
        });
    });
});

function updateContentTypePreview(select) {
    const container = select.closest('.content-type-assignment');
    const preview = container.querySelector('.content-type-preview span');
    if (preview) {
        const selectedText = select.options[select.selectedIndex].text;
        preview.textContent = selectedText;
        
        // Update suggestion badge if different from suggestion
        const suggestionBadge = container.querySelector('.badge.bg-info');
        if (suggestionBadge) {
            const originalSuggestion = suggestionBadge.textContent.replace('Suggested: ', '');
            if (selectedText.toLowerCase() !== originalSuggestion.toLowerCase()) {
                suggestionBadge.className = 'badge bg-warning';
                suggestionBadge.innerHTML = '<i class="fas fa-edit me-1"></i>Modified from suggestion';
            } else {
                suggestionBadge.className = 'badge bg-info';
                suggestionBadge.innerHTML = '<i class="fas fa-lightbulb me-1"></i>Suggested: ' + originalSuggestion;
            }
        }
    }
}

// Export for global access if needed
window.WizardContentTypes = {
    updateContentTypePreview
};