/**
 * wizard-base-init.js
 * Initializes wizard base functionality including progress bar
 * Extracted from wizard/base.html inline script
 */

/**
 * Initialize wizard progress bar
 */
function initializeWizardProgress() {
    const progressBar = document.querySelector('.progress-bar');
    if (progressBar) {
        const progress = progressBar.getAttribute('data-progress') || '0';
        progressBar.style.width = progress + '%';
        progressBar.setAttribute('aria-valuenow', progress);
    }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', initializeWizardProgress);
