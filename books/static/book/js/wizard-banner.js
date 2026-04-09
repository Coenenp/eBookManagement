/**
 * Wizard Banner Skip Handler
 * Handles the skip functionality for the wizard banner shown on first visit
 */

(function() {
    'use strict';

    /**
     * Initialize wizard banner skip button handler
     */
    function initWizardBannerSkip() {
        const skipBtn = document.querySelector('.skip-wizard-btn');
        if (!skipBtn) return;

        skipBtn.addEventListener('click', function() {
            // Create a form and submit it
            const form = document.createElement('form');
            form.method = 'POST';
            form.action = skipBtn.dataset.wizardUrl || '/wizard/';
            
            // Add CSRF token
            const csrfInput = document.createElement('input');
            csrfInput.type = 'hidden';
            csrfInput.name = 'csrfmiddlewaretoken';
            csrfInput.value = getCSRFToken();
            form.appendChild(csrfInput);
            
            // Add action input
            const actionInput = document.createElement('input');
            actionInput.type = 'hidden';
            actionInput.name = 'action';
            actionInput.value = 'skip';
            form.appendChild(actionInput);
            
            // Append to body and submit
            document.body.appendChild(form);
            form.submit();
        });
    }

    /**
     * Get CSRF token from the page
     * @returns {string} CSRF token
     */
    function getCSRFToken() {
        // Try from cookie first
        const cookieValue = document.cookie
            .split('; ')
            .find(row => row.startsWith('csrftoken='));
        
        if (cookieValue) {
            return cookieValue.split('=')[1];
        }

        // Fallback to meta tag or input
        const metaTag = document.querySelector('meta[name="csrf-token"]');
        if (metaTag) {
            return metaTag.getAttribute('content');
        }

        const csrfInput = document.querySelector('input[name="csrfmiddlewaretoken"]');
        if (csrfInput) {
            return csrfInput.value;
        }

        return '';
    }

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initWizardBannerSkip);
    } else {
        initWizardBannerSkip();
    }

})();
