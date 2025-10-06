/**
 * Common Wizard JavaScript functionality
 * Shared utilities and functions for all wizard steps
 */

// Wizard namespace for all wizard-related functionality
window.Wizard = window.Wizard || {};

/**
 * Common utilities and helper functions
 */
Wizard.Utils = {
    /**
     * Get CSRF token from the page
     * @returns {string|null} CSRF token or null if not found
     */
    getCsrfToken() {
        return document.querySelector('[name=csrfmiddlewaretoken]')?.value || null;
    },

    /**
     * Show loading state in an element
     * @param {HTMLElement} element - Element to show loading state in
     * @param {string} message - Loading message
     */
    showLoading(element, message = 'Loading...') {
        if (element) {
            element.innerHTML = `<small class="text-info"><i class="fas fa-spinner fa-spin me-1"></i>${message}</small>`;
        }
    },

    /**
     * Show success state in an element
     * @param {HTMLElement} element - Element to show success state in
     * @param {string} message - Success message
     */
    showSuccess(element, message) {
        if (element) {
            element.innerHTML = `<small class="text-success"><i class="fas fa-check-circle me-1"></i>${message}</small>`;
        }
    },

    /**
     * Show error state in an element
     * @param {HTMLElement} element - Element to show error state in
     * @param {string} message - Error message
     */
    showError(element, message) {
        if (element) {
            element.innerHTML = `<small class="text-danger"><i class="fas fa-exclamation-circle me-1"></i>${message}</small>`;
        }
    },

    /**
     * Show warning state in an element
     * @param {HTMLElement} element - Element to show warning state in
     * @param {string} message - Warning message
     */
    showWarning(element, message) {
        if (element) {
            element.innerHTML = `<small class="text-warning"><i class="fas fa-exclamation-triangle me-1"></i>${message}</small>`;
        }
    },

    /**
     * Clear validation classes from input
     * @param {HTMLElement} input - Input element to clear
     */
    clearValidation(input) {
        if (input) {
            input.classList.remove('is-valid', 'is-invalid');
        }
    },

    /**
     * Set input validation state
     * @param {HTMLElement} input - Input element
     * @param {boolean} isValid - Whether input is valid
     */
    setValidationState(input, isValid) {
        if (input) {
            this.clearValidation(input);
            input.classList.add(isValid ? 'is-valid' : 'is-invalid');
        }
    },

    /**
     * Make AJAX request with proper error handling
     * @param {string} url - Request URL
     * @param {Object} options - Request options
     * @returns {Promise} Fetch promise
     */
    async makeRequest(url, options = {}) {
        const csrfToken = this.getCsrfToken();
        
        const defaultOptions = {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
                'X-CSRFToken': csrfToken
            }
        };

        const finalOptions = { ...defaultOptions, ...options };
        
        if (finalOptions.headers && csrfToken) {
            finalOptions.headers['X-CSRFToken'] = csrfToken;
        }

        try {
            const response = await fetch(url, finalOptions);
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return await response.json();
        } catch (error) {
            console.error('Request failed:', error);
            throw error;
        }
    },

    /**
     * Debounce function calls
     * @param {Function} func - Function to debounce
     * @param {number} wait - Wait time in milliseconds
     * @returns {Function} Debounced function
     */
    debounce(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    },

    /**
     * Toggle Bootstrap collapse element
     * @param {HTMLElement} element - Element to toggle
     * @param {HTMLElement} button - Button that triggered the toggle (optional)
     */
    toggleCollapse(element, button = null) {
        if (!element) return;

        if (element.classList.contains('show')) {
            element.classList.remove('show');
            if (button) {
                const icon = button.querySelector('i');
                if (icon && icon.classList.contains('fa-times-circle')) {
                    icon.className = 'fas fa-question-circle';
                }
            }
        } else {
            element.classList.add('show');
            if (button) {
                const icon = button.querySelector('i');
                if (icon && icon.classList.contains('fa-question-circle')) {
                    icon.className = 'fas fa-times-circle';
                }
            }
        }
    }
};

/**
 * Form validation utilities
 */
Wizard.Form = {
    /**
     * Validate that at least one field in a group has a value
     * @param {NodeList|Array} elements - Elements to check
     * @returns {boolean} Whether at least one has a value
     */
    hasAtLeastOneValue(elements) {
        return Array.from(elements).some(element => {
            if (element.type === 'checkbox' || element.type === 'radio') {
                return element.checked;
            }
            return element.value && element.value.trim();
        });
    },

    /**
     * Show form validation error
     * @param {string} message - Error message to show
     */
    showValidationError(message) {
        alert(message); // TODO: Replace with better modal/toast system
    },

    /**
     * Setup form validation for wizard steps
     * @param {HTMLFormElement} form - Form element
     * @param {Function} customValidation - Custom validation function
     */
    setupValidation(form, customValidation = null) {
        if (!form) return;

        form.addEventListener('submit', function(e) {
            let isValid = true;

            // Run custom validation if provided
            if (customValidation && typeof customValidation === 'function') {
                isValid = customValidation(form);
            }

            if (!isValid) {
                e.preventDefault();
                return false;
            }
        });
    }
};

/**
 * UI utilities for wizard pages
 */
Wizard.UI = {
    /**
     * Add wizard-specific body class
     */
    initializeWizardPage() {
        document.body.classList.add('wizard-page');
    },

    /**
     * Skip the entire wizard with confirmation
     */
    skipWizard() {
        if (confirm('Are you sure you want to skip the setup wizard? You can always configure your library later in the settings.')) {
            const skipUrl = window.wizardConfig?.skipUrl || '/books/wizard/ajax/skip/';
            
            Wizard.Utils.makeRequest(skipUrl)
                .then(data => {
                    if (data.success) {
                        window.location.reload();
                    } else {
                        alert('Error skipping wizard: ' + data.error);
                    }
                })
                .catch(error => {
                    console.error('Error:', error);
                    alert('An error occurred while skipping the wizard.');
                });
        }
    },

    /**
     * Toggle card selection state
     * @param {HTMLInputElement} checkbox - Checkbox element
     * @param {string} selectedClass - CSS class for selected state
     */
    toggleCardSelection(checkbox, selectedClass = 'border-primary bg-primary-subtle') {
        const card = checkbox.closest('.card');
        if (!card) return;

        const classes = selectedClass.split(' ');
        
        if (checkbox.checked) {
            card.classList.add(...classes);
        } else {
            card.classList.remove(...classes);
        }
    },

    /**
     * Create a new form input group
     * @param {Object} options - Configuration options
     * @returns {HTMLElement} Created element
     */
    createInputGroup(options = {}) {
        const {
            type = 'text',
            name = '',
            placeholder = '',
            icon = 'fas fa-folder',
            buttonHtml = '',
            containerClass = 'mb-3'
        } = options;

        const div = document.createElement('div');
        div.className = containerClass;
        
        div.innerHTML = `
            <div class="input-group">
                <span class="input-group-text bg-light">
                    <i class="${icon} text-primary"></i>
                </span>
                <input type="${type}" class="form-control" name="${name}" 
                       placeholder="${placeholder}" autocomplete="off">
                ${buttonHtml}
            </div>
            <div class="form-text"></div>
        `;

        return div;
    }
};

/**
 * Skip the wizard with user confirmation
 */
function skipWizard() {
    if (confirm('Are you sure you want to skip the setup wizard? You can run it again later from the dashboard.')) {
        // Hide the wizard banner by making an AJAX call to mark wizard as skipped
        Wizard.Utils.ajax('/books/wizard/skip/', {
            method: 'POST'
        })
        .then(response => {
            if (response.success) {
                // Remove the wizard banner from DOM
                const banner = document.querySelector('.wizard-banner, .alert.alert-info');
                if (banner) {
                    banner.remove();
                }
                Wizard.Utils.showMessage('Wizard skipped. You can restart it from the dashboard.', 'success');
            } else {
                Wizard.Utils.showMessage('Failed to skip wizard. Please try again.', 'error');
            }
        })
        .catch(error => {
            console.error('Error skipping wizard:', error);
            // Still hide the banner for better UX even if the AJAX call fails
            const banner = document.querySelector('.wizard-banner, .alert.alert-info');
            if (banner) {
                banner.remove();
            }
        });
    }
}

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    Wizard.UI.initializeWizardPage();
    
    // Add event delegation for skip wizard button
    document.addEventListener('click', function(e) {
        if (e.target.closest('.skip-wizard-btn')) {
            e.preventDefault();
            skipWizard();
        }
    });
});

// Export for use in other files
window.Wizard = Wizard;
window.skipWizard = skipWizard;