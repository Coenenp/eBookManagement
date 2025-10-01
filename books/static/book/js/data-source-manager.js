/**
 * Data Source Manager - Manage data source trust levels and settings
 * Extracted from data_source_list.html inline JavaScript
 */

class DataSourceManager {
    constructor() {
        this.init();
    }

    init() {
        this.bindEvents();
        this.initializeProgressBars();
    }

    bindEvents() {
        // Handle trust level form submission
        const trustLevelForm = document.getElementById('trustLevelForm');
        if (trustLevelForm) {
            trustLevelForm.addEventListener('submit', (e) => this.handleTrustLevelSubmission(e));
        }

        // Reset form when modal is hidden
        const trustLevelModal = document.getElementById('trustLevelModal');
        if (trustLevelModal) {
            trustLevelModal.addEventListener('hidden.bs.modal', () => {
                const form = document.getElementById('trustLevelForm');
                if (form) form.reset();
            });
        }
    }

    initializeProgressBars() {
        // Set progress bar widths dynamically using CSS custom properties
        const progressBars = document.querySelectorAll('.progress-bar[data-width]');
        progressBars.forEach(bar => {
            const width = bar.getAttribute('data-width');
            bar.style.setProperty('--trust-width', width + '%');
        });
    }

    editTrustLevel(buttonElement) {
        // Get data from the button that was clicked
        const sourceId = buttonElement.getAttribute('data-source-id');
        const currentLevel = buttonElement.getAttribute('data-current-level');
        const updateUrl = buttonElement.getAttribute('data-update-url');
        
        console.log('Opening modal for source:', sourceId, 'current level:', currentLevel, 'URL:', updateUrl);
        
        // Set the current trust level value
        const trustLevelInput = document.getElementById('trustLevelInput');
        if (trustLevelInput) {
            trustLevelInput.value = currentLevel;
        }
        
        // Set the form action URL
        const trustLevelForm = document.getElementById('trustLevelForm');
        if (trustLevelForm) {
            trustLevelForm.action = updateUrl;
        }
        
        // Show the modal using Bootstrap 5
        const modalElement = document.getElementById('trustLevelModal');
        if (modalElement && typeof bootstrap !== 'undefined') {
            const modal = new bootstrap.Modal(modalElement);
            modal.show();
        }
    }

    async handleTrustLevelSubmission(e) {
        e.preventDefault();
        
        const form = e.target;
        const formData = new FormData(form);
        const url = form.action;
        
        console.log('Submitting to URL:', url);
        console.log('Form data:', Object.fromEntries(formData));
        console.log('EbookLibrary available:', typeof EbookLibrary !== 'undefined');
        if (typeof EbookLibrary !== 'undefined') {
            console.log('EbookLibrary.Ajax available:', typeof EbookLibrary.Ajax !== 'undefined');
            console.log('EbookLibrary.Forms available:', typeof EbookLibrary.Forms !== 'undefined');
        }
        
        // Show loading state
        const submitBtn = form.querySelector('button[type="submit"]');
        if (!submitBtn) return;
        
        const originalText = submitBtn.textContent;
        submitBtn.disabled = true;
        submitBtn.textContent = 'Updating...';
        
        try {
            // Get CSRF token with fallbacks
            let csrfToken;
            if (typeof EbookLibrary !== 'undefined' && 
                EbookLibrary.Ajax && 
                typeof EbookLibrary.Ajax.getCSRFToken === 'function') {
                csrfToken = EbookLibrary.Ajax.getCSRFToken();
            } else if (typeof EbookLibrary !== 'undefined' && 
                       EbookLibrary.Forms && 
                       typeof EbookLibrary.Forms.getCSRFToken === 'function') {
                csrfToken = EbookLibrary.Forms.getCSRFToken();
            } else {
                // Direct fallback
                const csrfInput = document.querySelector('[name=csrfmiddlewaretoken]');
                csrfToken = csrfInput ? csrfInput.value : '';
            }
            
            console.log('Using CSRF token:', csrfToken);
            
            const response = await fetch(url, {
                method: 'POST',
                body: formData,
                headers: {
                    'X-CSRFToken': csrfToken
                }
            });
            
            console.log('Response status:', response.status);
            console.log('Response URL:', response.url);
            
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            const data = await response.json();
            console.log('Response data:', data);
            
            if (data.success) {
                // Close modal using Bootstrap 5 syntax
                const modalElement = document.getElementById('trustLevelModal');
                if (modalElement && typeof bootstrap !== 'undefined') {
                    const modal = bootstrap.Modal.getInstance(modalElement);
                    if (modal) {
                        modal.hide();
                    }
                }
                
                // Show success message and reload
                if (typeof EbookLibrary !== 'undefined' && EbookLibrary.UI) {
                    EbookLibrary.UI.showAlert('Trust level updated successfully!', 'success');
                }
                
                setTimeout(() => {
                    location.reload();
                }, 100);
            } else {
                const errorMsg = 'Error updating trust level: ' + (data.error || 'Unknown error');
                if (typeof EbookLibrary !== 'undefined' && EbookLibrary.UI) {
                    EbookLibrary.UI.showAlert(errorMsg, 'danger');
                } else {
                    alert(errorMsg);
                }
            }
        } catch (error) {
            console.error('Full error:', error);
            const errorMsg = 'Error updating trust level: ' + error.message;
            if (typeof EbookLibrary !== 'undefined' && EbookLibrary.UI) {
                EbookLibrary.UI.showAlert(errorMsg, 'danger');
            } else {
                alert(errorMsg);
            }
        } finally {
            // Restore button state
            submitBtn.disabled = false;
            submitBtn.textContent = originalText;
        }
    }
}

// Global instance
let dataSourceManager;

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    dataSourceManager = new DataSourceManager();
});

// Global function for button onclick handlers
function editTrustLevel(buttonElement) {
    if (dataSourceManager) {
        dataSourceManager.editTrustLevel(buttonElement);
    }
}

// Export for global access
window.DataSourceManager = DataSourceManager;