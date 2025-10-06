/**
 * Wizard System - Setup wizard functionality
 * Extracted from wizard/*.html inline JavaScript
 */

class SetupWizard {
    constructor() {
        this.currentStep = 1;
        this.totalSteps = 4;
        this.validationRules = {};
        
        this.init();
    }

    init() {
        this.bindEvents();
        this.initializeValidation();
        this.updateProgress();
    }

    bindEvents() {
        // Navigation buttons
        const nextBtn = document.getElementById('nextBtn');
        const prevBtn = document.getElementById('prevBtn');
        const skipBtn = document.getElementById('skipBtn');
        
        nextBtn?.addEventListener('click', () => this.nextStep());
        prevBtn?.addEventListener('click', () => this.prevStep());
        skipBtn?.addEventListener('click', () => this.skipStep());
        
        // Form validation on input changes
        document.addEventListener('input', (e) => {
            if (e.target.closest('.wizard-form')) {
                this.validateCurrentStep();
            }
        });
        
        // Content type grid selection
        document.addEventListener('click', (e) => {
            if (e.target.closest('.content-type-card')) {
                this.handleContentTypeSelection(e.target.closest('.content-type-card'));
            }
        });
        
        // Folder suggestion handling
        document.addEventListener('click', (e) => {
            if (e.target.classList.contains('folder-suggestion')) {
                this.handleFolderSuggestion(e.target);
            }
        });
        
        // API key testing
        document.addEventListener('click', (e) => {
            if (e.target.classList.contains('test-api-btn')) {
                this.testAPIKey(e.target);
            }
        });
    }

    initializeValidation() {
        this.validationRules = {
            1: { // Welcome step - no validation needed
                required: [],
                validator: () => true
            },
            2: { // Folders step
                required: ['library_path'],
                validator: () => this.validateFolders()
            },
            3: { // Content types step
                required: [],
                validator: () => this.validateContentTypes()
            },
            4: { // Scrapers step
                required: [],
                validator: () => this.validateScrapers()
            }
        };
    }

    updateProgress() {
        // Progress and step indicators are now managed server-side via Django templates
        // This method is kept for compatibility but doesn't override server values
        const progressBar = document.querySelector('.wizard-progress .progress-bar');
        const stepIndicators = document.querySelectorAll('.step-indicator');
        
        // Don't override progress bar - server handles this correctly now
        
        // Don't override step indicators - Django template handles this correctly
        
        // Keep the navigation button updates if needed
        this.updateNavigationButtons();
    }

    updateNavigationButtons() {
        const nextBtn = document.getElementById('nextBtn');
        const prevBtn = document.getElementById('prevBtn');
        const skipBtn = document.getElementById('skipBtn');
        
        if (prevBtn) {
            prevBtn.disabled = this.currentStep === 1;
        }
        
        if (nextBtn) {
            nextBtn.textContent = this.currentStep === this.totalSteps ? 'Complete Setup' : 'Next Step';
        }
        
        if (skipBtn) {
            skipBtn.style.display = this.currentStep === this.totalSteps ? 'none' : 'inline-block';
        }
    }

    async nextStep() {
        if (!await this.validateCurrentStep()) {
            return false;
        }
        
        await this.saveStepData();
        
        if (this.currentStep === this.totalSteps) {
            return this.completeSetup();
        }
        
        this.currentStep++;
        this.navigateToStep(this.currentStep);
        return true;
    }

    prevStep() {
        if (this.currentStep > 1) {
            this.currentStep--;
            this.navigateToStep(this.currentStep);
        }
    }

    skipStep() {
        if (this.currentStep < this.totalSteps) {
            this.currentStep++;
            this.navigateToStep(this.currentStep);
        }
    }

    navigateToStep(stepNumber) {
        // This would typically involve AJAX call or form submission
        // For now, we'll use URL navigation
        const currentUrl = window.location.pathname;
        const baseUrl = currentUrl.replace(/\/step\/\d+/, '');
        window.location.href = `${baseUrl}/step/${stepNumber}/`;
    }

    async validateCurrentStep() {
        const rules = this.validationRules[this.currentStep];
        if (!rules) return true;
        
        // Check required fields
        for (const fieldName of rules.required) {
            const field = document.querySelector(`[name="${fieldName}"]`);
            if (!field || !field.value.trim()) {
                this.showValidationError(`${fieldName} is required`);
                field?.focus();
                return false;
            }
        }
        
        // Run custom validator
        if (rules.validator) {
            const result = await rules.validator();
            if (!result) {
                return false;
            }
        }
        
        this.clearValidationErrors();
        return true;
    }

    validateFolders() {
        const libraryPath = document.querySelector('[name="library_path"]');
        if (!libraryPath || !libraryPath.value.trim()) {
            this.showValidationError('Library path is required');
            return false;
        }
        
        // Additional folder validation could go here
        return true;
    }

    validateContentTypes() {
        const selectedTypes = document.querySelectorAll('.content-type-card.selected');
        if (selectedTypes.length === 0) {
            this.showValidationError('Please select at least one content type');
            return false;
        }
        
        return true;
    }

    validateScrapers() {
        // Scrapers are optional, but we can validate API keys if provided
        const apiKeys = document.querySelectorAll('.api-key-input');
        
        for (const input of apiKeys) {
            if (input.value.trim() && !this.isValidAPIKeyFormat(input.value)) {
                this.showValidationError(`Invalid API key format for ${input.dataset.service}`);
                input.focus();
                return false;
            }
        }
        
        return true;
    }

    isValidAPIKeyFormat(key) {
        // Basic API key format validation
        return key.length >= 10 && /^[A-Za-z0-9_-]+$/.test(key);
    }

    handleContentTypeSelection(card) {
        const checkbox = card.querySelector('input[type="checkbox"]');
        
        if (checkbox) {
            checkbox.checked = !checkbox.checked;
            card.classList.toggle('selected', checkbox.checked);
            
            // Update visual feedback
            const icon = card.querySelector('.content-type-icon');
            if (icon) {
                icon.classList.toggle('text-primary', checkbox.checked);
                icon.classList.toggle('text-muted', !checkbox.checked);
            }
        }
    }

    handleFolderSuggestion(suggestion) {
        const path = suggestion.dataset.path;
        const pathInput = document.querySelector('[name="library_path"]');
        
        if (pathInput && path) {
            pathInput.value = path;
            
            // Trigger validation
            this.validateCurrentStep();
            
            // Visual feedback
            suggestion.classList.add('selected');
            setTimeout(() => suggestion.classList.remove('selected'), 1000);
        }
    }

    async testAPIKey(button) {
        const service = button.dataset.service;
        const input = document.querySelector(`[name="${service}_api_key"]`);
        
        if (!input || !input.value.trim()) {
            this.showAPITestResult(service, false, 'Please enter an API key first');
            return;
        }
        
        // Show loading state
        const originalText = button.textContent;
        button.textContent = 'Testing...';
        button.disabled = true;
        
        try {
            const response = await fetch('/wizard/test-api/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': EbookLibrary.Ajax.getCSRFToken()
                },
                body: JSON.stringify({
                    service: service,
                    api_key: input.value.trim()
                })
            });
            
            const data = await response.json();
            this.showAPITestResult(service, data.valid, data.message);
            
        } catch (error) {
            this.showAPITestResult(service, false, 'Network error occurred');
        } finally {
            button.textContent = originalText;
            button.disabled = false;
        }
    }

    showAPITestResult(service, success, message) {
        const container = document.querySelector(`[data-service="${service}"] .api-test-result`);
        if (!container) return;
        
        container.innerHTML = `
            <div class="alert alert-${success ? 'success' : 'danger'} alert-sm mt-2">
                <i class="fas fa-${success ? 'check-circle' : 'exclamation-circle'} me-2"></i>
                ${EbookLibrary.Utils.escapeHtml(message)}
            </div>
        `;
        
        // Auto-hide after 5 seconds
        setTimeout(() => {
            container.innerHTML = '';
        }, 5000);
    }

    async saveStepData() {
        const form = document.querySelector('.wizard-form');
        if (!form) return;
        
        const formData = new FormData(form);
        
        try {
            await fetch(window.location.href, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': EbookLibrary.Ajax.getCSRFToken()
                },
                body: formData
            });
        } catch (error) {
            console.error('Failed to save step data:', error);
        }
    }

    async completeSetup() {
        try {
            const response = await fetch('/wizard/complete/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': EbookLibrary.Ajax.getCSRFToken()
                }
            });
            
            const data = await response.json();
            
            if (data.status === 'success') {
                // Show completion message
                this.showCompletionMessage();
                
                // Redirect after a delay
                setTimeout(() => {
                    window.location.href = data.redirect_url || '/dashboard/';
                }, 2000);
            } else {
                this.showValidationError(data.message || 'Failed to complete setup');
            }
        } catch (error) {
            this.showValidationError('Network error occurred during setup completion');
        }
    }

    showCompletionMessage() {
        const container = document.querySelector('.wizard-content');
        if (!container) return;
        
        container.innerHTML = `
            <div class="text-center py-5">
                <div class="mb-4">
                    <i class="fas fa-check-circle text-success" style="font-size: 4rem;"></i>
                </div>
                <h3 class="text-success mb-3">Setup Complete!</h3>
                <p class="text-muted mb-4">
                    Your eBook Library Manager has been successfully configured.
                    You will be redirected to the dashboard shortly.
                </p>
                <div class="spinner-border text-primary" role="status">
                    <span class="visually-hidden">Loading...</span>
                </div>
            </div>
        `;
    }

    showValidationError(message) {
        let errorContainer = document.querySelector('.wizard-validation-errors');
        
        if (!errorContainer) {
            errorContainer = document.createElement('div');
            errorContainer.className = 'wizard-validation-errors';
            
            const form = document.querySelector('.wizard-form');
            if (form) {
                form.insertBefore(errorContainer, form.firstChild);
            }
        }
        
        errorContainer.innerHTML = `
            <div class="alert alert-danger">
                <i class="fas fa-exclamation-triangle me-2"></i>
                ${EbookLibrary.Utils.escapeHtml(message)}
            </div>
        `;
        
        // Scroll to error
        errorContainer.scrollIntoView({ behavior: 'smooth' });
    }

    clearValidationErrors() {
        const errorContainer = document.querySelector('.wizard-validation-errors');
        if (errorContainer) {
            errorContainer.innerHTML = '';
        }
    }
}

// Folder validation utilities
class FolderValidator {
    static async validatePath(path) {
        try {
            const response = await fetch('/wizard/validate-folder/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': EbookLibrary.Ajax.getCSRFToken()
                },
                body: JSON.stringify({ path })
            });
            
            return await response.json();
        } catch (error) {
            return { valid: false, message: 'Network error occurred' };
        }
    }

    static async getSuggestions() {
        try {
            const response = await fetch('/wizard/folder-suggestions/');
            const data = await response.json();
            return data.suggestions || [];
        } catch (error) {
            return [];
        }
    }
}

// Content type management
class ContentTypeManager {
    static getSelectedTypes() {
        return Array.from(document.querySelectorAll('.content-type-card.selected input'))
                   .map(input => input.value);
    }

    static selectType(type) {
        const card = document.querySelector(`[data-content-type="${type}"]`);
        if (card) {
            const checkbox = card.querySelector('input[type="checkbox"]');
            if (checkbox) {
                checkbox.checked = true;
                card.classList.add('selected');
            }
        }
    }

    static deselectType(type) {
        const card = document.querySelector(`[data-content-type="${type}"]`);
        if (card) {
            const checkbox = card.querySelector('input[type="checkbox"]');
            if (checkbox) {
                checkbox.checked = false;
                card.classList.remove('selected');
            }
        }
    }
}

/**
 * API Key Validator - validates API keys for external services
 */
class ApiKeyValidator {
    constructor() {
        this.init();
    }

    init() {
        document.querySelectorAll('input[name$="_api_key"]').forEach(input => {
            input.addEventListener('blur', () => this.validateApiKey(input));
        });
    }

    validateApiKey(input) {
        const key = input.value.trim();
        const fieldName = input.getAttribute('name');
        
        if (!key) {
            input.classList.remove('is-valid', 'is-invalid');
            return;
        }
        
        // Basic validation based on service
        let isValid = false;
        
        if (fieldName === 'google_books_api_key') {
            // Google API keys are typically 39 characters
            isValid = key.length >= 20 && /^[A-Za-z0-9_-]+$/.test(key);
        } else if (fieldName === 'comicvine_api_key') {
            // Comic Vine keys are typically 40 characters hex
            isValid = key.length >= 20 && /^[A-Fa-f0-9]+$/.test(key);
        }
        
        if (isValid) {
            input.classList.remove('is-invalid');
            input.classList.add('is-valid');
        } else {
            input.classList.remove('is-valid');
            input.classList.add('is-invalid');
        }
    }
}

// Global instance
let setupWizard;
let apiKeyValidator;

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    if (document.querySelector('.wizard-container')) {
        setupWizard = new SetupWizard();
        apiKeyValidator = new ApiKeyValidator();
    }
    
    // Initialize progress bar ARIA attributes (use server-provided values)
    const progressBar = document.querySelector('.progress-bar');
    if (progressBar) {
        const progressValue = progressBar.getAttribute('data-progress') || '0';
        const numericValue = parseInt(progressValue, 10) || 0;
        progressBar.setAttribute('aria-valuenow', numericValue.toString());
        // Don't override the server-provided width - it's already set correctly
    }
    
    // Folder selection handling
    document.querySelectorAll('.folder-suggestion').forEach(function(suggestion) {
        suggestion.addEventListener('click', function() {
            const checkbox = this.querySelector('input[type="checkbox"]');
            if (checkbox) {
                checkbox.checked = !checkbox.checked;
                this.classList.toggle('selected', checkbox.checked);
            }
        });
    });
    
    // Content type change handling
    document.querySelectorAll('select[name^="folder_"]').forEach(function(select) {
        select.addEventListener('change', function() {
            updateContentTypePreview(this);
        });
    });
    
    // Custom folder input validation
    const customFolderInput = document.getElementById('customFolder');
    if (customFolderInput) {
        customFolderInput.addEventListener('blur', function() {
            validateFolder(this.value);
        });
    }
});

// Folder validation function (extracted from inline JavaScript)
function validateFolder(path) {
    if (!path.trim()) return;
    
    // Get the validation URL from configuration or use default
    const validationUrl = window.wizardConfig?.validateUrl || '/books/wizard/validate-folder/';
    
    fetch(validationUrl, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/x-www-form-urlencoded',
            'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value
        },
        body: 'path=' + encodeURIComponent(path)
    })
    .then(response => response.json())
    .then(data => {
        const input = document.getElementById('customFolder');
        const feedback = document.getElementById('customFolderFeedback');
        
        if (data.valid) {
            input.classList.remove('is-invalid');
            input.classList.add('is-valid');
            if (feedback) {
                feedback.textContent = `Found ${data.file_count} ebook files`;
                feedback.className = 'text-success small';
            }
        } else {
            input.classList.remove('is-valid');
            input.classList.add('is-invalid');
            if (feedback) {
                feedback.textContent = data.error;
                feedback.className = 'text-danger small';
            }
        }
    })
    .catch(error => {
        console.error('Error validating folder:', error);
    });
}

// Content type preview function (extracted from inline JavaScript)
function updateContentTypePreview(select) {
    const container = select.closest('.content-type-assignment');
    const preview = container.querySelector('.content-type-preview');
    if (preview) {
        preview.textContent = `Will scan as: ${select.options[select.selectedIndex].text}`;
    }
}

// Export for global access
window.SetupWizard = SetupWizard;
window.FolderValidator = FolderValidator;
window.ContentTypeManager = ContentTypeManager;
window.ApiKeyValidator = ApiKeyValidator;