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
    EbookLibrary.Sections.updateContentTypePreview(select);
}

// Export for global access if needed
window.WizardContentTypes = {
    updateContentTypePreview
};