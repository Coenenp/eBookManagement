/**
 * 📝 Scan Folder Form Enhancement
 * Enhanced functionality for adding and managing scan folders
 */

class ScanFolderFormManager {
    constructor() {
        this.form = document.getElementById('scan-folder-form');
        this.pathField = document.getElementById('id_path');
        this.activeSwitch = document.getElementById('id_is_active');
        this.submitButton = null;
        
        this.init();
    }

    init() {
        if (!this.form) return;
        
        this.submitButton = this.form.querySelector('button[type="submit"]');
        this.setupEventListeners();
        this.setupValidation();
        this.setupPathValidation();
        this.setupFormSubmission();
    }

    setupEventListeners() {
        // Path field validation
        if (this.pathField) {
            this.pathField.addEventListener('blur', () => this.validatePath());
            this.pathField.addEventListener('input', () => this.clearPathValidation());
        }

        // Switch toggle enhancement
        if (this.activeSwitch) {
            this.activeSwitch.addEventListener('change', () => this.updateSwitchLabel());
        }

        // Form change detection
        this.form.addEventListener('input', () => this.handleFormChange());
        this.form.addEventListener('change', () => this.handleFormChange());
    }

    setupValidation() {
        // Enable Bootstrap validation
        this.form.classList.add('needs-validation');
        
        // Custom validation messages
        const inputs = this.form.querySelectorAll('input, select, textarea');
        inputs.forEach(input => {
            input.addEventListener('invalid', (e) => {
                e.preventDefault();
                this.showCustomValidation(input);
            });
        });
    }

    setupPathValidation() {
        if (!this.pathField) return;

        // Path format validation
        this.pathField.addEventListener('input', () => {
            const path = this.pathField.value.trim();
            
            if (path && !this.isValidPathFormat(path)) {
                this.pathField.setCustomValidity('Please enter a valid file path');
                this.showPathFormatHint();
            } else {
                this.pathField.setCustomValidity('');
                this.hidePathFormatHint();
            }
        });
    }

    setupFormSubmission() {
        this.form.addEventListener('submit', (e) => {
            e.preventDefault();
            
            if (this.form.checkValidity()) {
                this.submitForm();
            } else {
                this.showValidationErrors();
            }
        });
    }

    validatePath() {
        if (!this.pathField) return;
        
        const path = this.pathField.value.trim();
        
        if (!path) {
            this.setFieldError(this.pathField, 'Please provide a folder path');
            return false;
        }

        if (!this.isValidPathFormat(path)) {
            this.setFieldError(this.pathField, 'Please enter a valid file path format');
            return false;
        }

        this.clearFieldError(this.pathField);
        return true;
    }

    clearPathValidation() {
        this.clearFieldError(this.pathField);
    }

    isValidPathFormat(path) {
        // Basic path validation - allows Windows and Unix paths
        const windowsPath = /^[a-zA-Z]:\\(?:[^<>:"|?*\r\n]+\\)*[^<>:"|?*\r\n]*$/;
        const unixPath = /^\/(?:[^\/\0]+\/)*[^\/\0]*$/;
        const relativePath = /^\.{1,2}(?:[\/\\][^<>:"|?*\r\n]+)*$/;
        
        return windowsPath.test(path) || unixPath.test(path) || relativePath.test(path);
    }

    updateSwitchLabel() {
        if (!this.activeSwitch) return;
        
        const label = this.activeSwitch.parentElement.querySelector('.badge');
        if (label) {
            if (this.activeSwitch.checked) {
                label.textContent = 'Active';
                label.className = 'badge bg-success-subtle text-success-emphasis';
            } else {
                label.textContent = 'Inactive';
                label.className = 'badge bg-secondary-subtle text-secondary-emphasis';
            }
        }
    }

    handleFormChange() {
        // Enable smart button states
        if (this.submitButton) {
            const hasChanges = this.hasFormChanges();
            this.submitButton.classList.toggle('btn-outline-primary', !hasChanges);
            this.submitButton.classList.toggle('btn-primary', hasChanges);
        }
    }

    hasFormChanges() {
        const inputs = this.form.querySelectorAll('input, select, textarea');
        return Array.from(inputs).some(input => {
            if (input.type === 'checkbox' || input.type === 'radio') {
                return input.checked !== input.defaultChecked;
            }
            return input.value !== input.defaultValue;
        });
    }

    showCustomValidation(input) {
        const fieldContainer = input.closest('.mb-3, .mb-4');
        if (!fieldContainer) return;

        let feedback = fieldContainer.querySelector('.invalid-feedback');
        if (!feedback) {
            feedback = document.createElement('div');
            feedback.className = 'invalid-feedback d-block';
            input.parentElement.appendChild(feedback);
        }

        const icon = '<i class="fas fa-exclamation-circle me-1"></i>';
        feedback.innerHTML = icon + (input.validationMessage || 'Please check this field');
        
        input.classList.add('is-invalid');
    }

    setFieldError(input, message) {
        input.setCustomValidity(message);
        this.showCustomValidation(input);
    }

    clearFieldError(input) {
        input.setCustomValidity('');
        input.classList.remove('is-invalid');
        
        const fieldContainer = input.closest('.mb-3, .mb-4');
        if (fieldContainer) {
            const feedback = fieldContainer.querySelector('.invalid-feedback');
            if (feedback && !feedback.textContent.includes('error')) {
                feedback.remove();
            }
        }
    }

    showPathFormatHint() {
        if (!this.pathField) return;
        
        const formText = this.pathField.parentElement.querySelector('.form-text');
        if (formText && !formText.querySelector('.format-hint')) {
            const hint = document.createElement('small');
            hint.className = 'format-hint text-warning d-block mt-1';
            hint.innerHTML = '<i class="fas fa-info-circle me-1"></i>Examples: C:\\Users\\Name\\Documents or /home/user/books';
            formText.appendChild(hint);
        }
    }

    hidePathFormatHint() {
        if (!this.pathField) return;
        
        const hint = this.pathField.parentElement.querySelector('.format-hint');
        if (hint) {
            hint.remove();
        }
    }

    showValidationErrors() {
        const invalidFields = this.form.querySelectorAll('.is-invalid, :invalid');
        if (invalidFields.length > 0) {
            // Focus first invalid field
            invalidFields[0].focus();
            
            // Show toast notification
            this.showToast('Please check the highlighted fields', 'warning');
        }
    }

    async submitForm() {
        if (!this.submitButton) return;
        
        // Show loading state
        const originalText = this.submitButton.innerHTML;
        this.submitButton.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i>Saving...';
        this.submitButton.disabled = true;
        this.form.classList.add('form-submitting');
        
        try {
            // Create FormData and submit
            const formData = new FormData(this.form);
            
            const response = await fetch(this.form.action || window.location.href, {
                method: 'POST',
                body: formData,
                headers: {
                    'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value,
                }
            });
            
            if (response.ok) {
                // Check if response is JSON (AJAX) or HTML (redirect)
                const contentType = response.headers.get('content-type');
                
                if (contentType && contentType.includes('application/json')) {
                    const result = await response.json();
                    if (result.success) {
                        this.showToast('Scan folder saved successfully!', 'success');
                        setTimeout(() => {
                            if (result.redirect_url) {
                                window.location.href = result.redirect_url;
                            } else {
                                window.location.href = this.form.dataset.listUrl || '/scan_folders/';
                            }
                        }, 1000);
                    } else {
                        this.handleFormErrors(result.errors || {});
                    }
                } else {
                    // HTML response - likely a redirect or form with errors
                    const html = await response.text();
                    if (html.includes('form')) {
                        // Form has errors - would need server-side handling
                        this.form.submit(); // Fall back to regular form submission
                    } else {
                        // Successful redirect
                        this.showToast('Scan folder saved successfully!', 'success');
                        setTimeout(() => {
                            window.location.href = this.form.dataset.listUrl || '/scan_folders/';
                        }, 1000);
                    }
                }
            } else {
                throw new Error('Server error occurred');
            }
        } catch (error) {
            console.error('Form submission error:', error);
            this.showToast('An error occurred while saving. Please try again.', 'danger');
        } finally {
            // Restore button state
            this.submitButton.innerHTML = originalText;
            this.submitButton.disabled = false;
            this.form.classList.remove('form-submitting');
        }
    }

    handleFormErrors(errors) {
        // Clear existing errors
        this.form.querySelectorAll('.is-invalid').forEach(field => {
            this.clearFieldError(field);
        });
        
        // Show new errors
        Object.entries(errors).forEach(([fieldName, messages]) => {
            const field = this.form.querySelector(`[name="${fieldName}"]`);
            if (field && messages.length > 0) {
                this.setFieldError(field, messages[0]);
            }
        });
        
        this.showToast('Please correct the errors below', 'warning');
    }

    showToast(message, type = 'info') {
        // Create toast container if it doesn't exist
        let toastContainer = document.querySelector('.toast-container');
        if (!toastContainer) {
            toastContainer = document.createElement('div');
            toastContainer.className = 'toast-container position-fixed bottom-0 end-0 p-3';
            document.body.appendChild(toastContainer);
        }
        
        // Create toast
        const toast = document.createElement('div');
        toast.className = `toast show align-items-center text-bg-${type} border-0`;
        toast.setAttribute('role', 'alert');
        toast.innerHTML = `
            <div class="d-flex">
                <div class="toast-body">
                    <i class="fas fa-${this.getToastIcon(type)} me-2"></i>
                    ${message}
                </div>
                <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
            </div>
        `;
        
        toastContainer.appendChild(toast);
        
        // Auto-remove after 5 seconds
        setTimeout(() => {
            if (toast.parentElement) {
                toast.remove();
            }
        }, 5000);
    }

    getToastIcon(type) {
        const icons = {
            success: 'check-circle',
            warning: 'exclamation-triangle',
            danger: 'exclamation-circle',
            info: 'info-circle'
        };
        return icons[type] || 'info-circle';
    }
}

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    new ScanFolderFormManager();
});