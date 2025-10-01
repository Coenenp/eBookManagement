/**
 * Wizard Folders JavaScript functionality
 * Handles folder browsing, validation, and preview functionality
 */

document.addEventListener('DOMContentLoaded', function() {
    // Browse folder functionality (placeholder - would need native file dialog)
    document.getElementById('browseFolder')?.addEventListener('click', function() {
        alert('Folder browsing requires a native file dialog. Please type the path manually for now.');
    });
    
    // Enhanced folder validation with preview
    const customFolderInput = document.getElementById('customFolder');
    if (customFolderInput) {
        let validationTimeout;
        
        customFolderInput.addEventListener('input', function() {
            clearTimeout(validationTimeout);
            const path = this.value.trim();
            
            if (path.length > 3) {
                validationTimeout = setTimeout(() => {
                    validateFolderWithPreview(path);
                }, 500);
            }
        });
    }
});

function validateFolderWithPreview(path) {
    const input = document.getElementById('customFolder');
    const feedback = document.getElementById('customFolderFeedback');
    
    if (!input || !feedback) {
        console.error('Required elements not found for folder validation');
        return;
    }
    
    // Show loading state
    feedback.innerHTML = '<small class="text-info"><i class="fas fa-spinner fa-spin me-1"></i>Checking folder...</small>';
    
    // Get CSRF token
    const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value;
    if (!csrfToken) {
        console.error('CSRF token not found');
        return;
    }
    
    // Get the validation URL - will need to be passed dynamically or configured
    const validationUrl = window.wizardFoldersConfig?.validateUrl || '/books/wizard/validate-folder/';
    
    fetch(validationUrl, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/x-www-form-urlencoded',
            'X-CSRFToken': csrfToken
        },
        body: 'path=' + encodeURIComponent(path)
    })
    .then(response => response.json())
    .then(data => {
        input.classList.remove('is-invalid', 'is-valid');
        
        if (data.valid) {
            input.classList.add('is-valid');
            feedback.innerHTML = `
                <small class="text-success">
                    <i class="fas fa-check-circle me-1"></i>
                    Valid folder: <strong>${data.name}</strong> 
                    <span class="badge bg-success ms-2">${data.file_count} files</span>
                </small>
            `;
        } else {
            input.classList.add('is-invalid');
            feedback.innerHTML = `
                <small class="text-danger">
                    <i class="fas fa-exclamation-circle me-1"></i>
                    ${data.error}
                </small>
            `;
        }
    })
    .catch(error => {
        console.error('Error validating folder:', error);
        feedback.innerHTML = '<small class="text-warning"><i class="fas fa-exclamation-triangle me-1"></i>Unable to validate folder</small>';
    });
}

// Export for global access if needed
window.WizardFolders = {
    validateFolderWithPreview
};