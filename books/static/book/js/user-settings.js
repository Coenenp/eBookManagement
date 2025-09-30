/**
 * User Settings - Theme preview and settings management
 * Complete functionality for user settings page
 */

class UserSettingsManager {
    constructor() {
        this.form = document.getElementById('settingsForm');
        this.themeSelect = document.getElementById('id_theme');
        this.previewCards = document.querySelectorAll('.theme-preview-card');
        this.previewControls = document.getElementById('previewControls');
        this.savePreview = document.getElementById('savePreview');
        this.cancelPreview = document.getElementById('cancelPreview');
        this.resetButton = document.getElementById('resetForm');
        this.saveButton = document.getElementById('saveForm');
        
        // Debug: Verify all elements are found
        console.log('UserSettingsManager initialized with elements:');
        console.log('- form:', this.form ? 'found' : 'NOT FOUND');
        console.log('- themeSelect:', this.themeSelect ? 'found' : 'NOT FOUND');
        console.log('- previewCards:', this.previewCards.length + ' found');
        console.log('- saveButton:', this.saveButton ? 'found' : 'NOT FOUND');
        console.log('- resetButton:', this.resetButton ? 'found' : 'NOT FOUND');
        
        this.isPreviewMode = false;
        this.formChanged = false;
        this.originalTheme = '';
        this.originalFormData = null;
        
        // Get configuration from template
        const config = window.userSettingsConfig || {};
        this.originalTheme = config.currentTheme || 'flatly';
        this.csrfToken = config.csrfToken || 
                        document.querySelector('[name=csrfmiddlewaretoken]')?.value ||
                        document.querySelector('meta[name=csrf-token]')?.getAttribute('content');
        
        // URLs from config or fallbacks
        this.previewThemeUrl = config.urls?.previewTheme || '/settings/preview-theme/';
        this.clearThemePreviewUrl = config.urls?.clearThemePreview || '/settings/clear-theme-preview/';
        this.resetToDefaultsUrl = config.urls?.resetToDefaults || '/settings/reset-to-defaults/';
        this.userSettingsUrl = config.urls?.userSettings || '/settings/';
        
        this.init();
    }

    init() {
        if (!this.form) return;
        
        this.bindEvents();
        this.initializeFormTracking();
        this.initializeThemePreview();
    }



    bindEvents() {
        // Theme preview functionality
        this.previewCards.forEach(card => {
            card.addEventListener('click', (e) => this.handleThemePreview(e));
        });

        // Form change tracking
        const formInputs = this.form.querySelectorAll('input, select, textarea');
        formInputs.forEach(input => {
            input.addEventListener('change', () => {
                console.log(`Form field changed: ${input.name || input.id} = ${input.value}`);
                this.checkFormChanges();
            });
            input.addEventListener('input', () => {
                console.log(`Form field input: ${input.name || input.id} = ${input.value}`);
                this.checkFormChanges();
            });
        });

        // Special handling for theme dropdown to update theme tiles
        if (this.themeSelect) {
            this.themeSelect.addEventListener('change', (e) => {
                console.log(`Theme dropdown changed to: ${e.target.value}`);
                this.updateActiveThemeCard(e.target.value);
            });
        }

        // Preview controls
        this.savePreview?.addEventListener('click', () => this.handleSavePreview());
        this.cancelPreview?.addEventListener('click', () => this.clearPreview());

        // Reset form (always active now)
        this.resetButton?.addEventListener('click', () => this.handleReset());

        // Form submission
        this.form.addEventListener('submit', (e) => this.handleFormSubmit(e));
    }

    initializeFormTracking() {
        // Wait a bit to ensure all form fields are properly populated
        setTimeout(() => {
            // Store original form data for change detection
            this.originalFormData = new FormData(this.form);
            this.formChanged = false;
            
            // Debug: Log the original form data
            console.log('Original form data captured:');
            for (let [key, value] of this.originalFormData.entries()) {
                console.log(`  ${key}: "${value}"`);
            }
            
            // Initialize button states
            this.updateButtonStates();
        }, 100);
    }

    initializeThemePreview() {
        // Store original theme from the form or page data
        if (this.themeSelect) {
            this.originalTheme = this.themeSelect.value;
        }
        
        // Mark current theme card as active
        this.updateActiveThemeCard();
    }

    checkFormChanges() {
        // Ensure we have original form data to compare against
        if (!this.originalFormData) {
            console.log('No original form data available yet, skipping change check');
            return;
        }

        const currentFormData = new FormData(this.form);
        let hasChanges = false;
        let changedFields = [];
        
        console.log('Checking form changes...');
        console.log('Current form data:');
        for (let [key, value] of currentFormData.entries()) {
            console.log(`  ${key}: "${value}"`);
        }
        
        // Compare current form data with original
        for (let [key, value] of currentFormData.entries()) {
            const originalValue = this.originalFormData.get(key);
            if (originalValue !== value) {
                hasChanges = true;
                changedFields.push(`${key}: "${originalValue}" -> "${value}"`);
            }
        }
        
        // Check if any original fields are missing in current form
        if (!hasChanges) {
            for (let [key, value] of this.originalFormData.entries()) {
                const currentValue = currentFormData.get(key);
                if (currentValue !== value) {
                    hasChanges = true;
                    changedFields.push(`${key}: "${value}" -> "${currentValue}"`);
                }
            }
        }
        
        // Debug logging
        if (changedFields.length > 0) {
            console.log('Form changes detected:', changedFields);
        } else {
            console.log('No form changes detected');
        }
        
        console.log(`Form changed: ${hasChanges}, Save button will be: ${hasChanges ? 'enabled' : 'disabled'}`);
        
        this.formChanged = hasChanges;
        this.updateButtonStates();
    }

    updateButtonStates() {
        console.log(`Updating button states - formChanged: ${this.formChanged}, isPreviewMode: ${this.isPreviewMode}`);
        
        // Reset button is always enabled since it performs a true reset to defaults
        if (this.resetButton) {
            this.resetButton.disabled = false;
            this.resetButton.classList.remove('disabled');
        }
        
        // Save button only enabled when there are changes or in preview mode
        if (this.saveButton) {
            const shouldEnable = this.formChanged || this.isPreviewMode;
            console.log(`Save button should be: ${shouldEnable ? 'enabled' : 'disabled'}`);
            
            if (shouldEnable) {
                this.saveButton.disabled = false;
                this.saveButton.classList.remove('disabled');
                console.log('Save button enabled');
            } else {
                this.saveButton.disabled = true;
                this.saveButton.classList.add('disabled');
                console.log('Save button disabled');
            }
        } else {
            console.log('Save button not found!');
        }
    }

    setSaveButtonLoading(loading = true) {
        if (!this.saveButton) return;
        
        if (loading) {
            // Just disable the button temporarily during save
            this.saveButton.disabled = true;
            console.log('Save button disabled during save operation');
        } else {
            // Update button state based on form changes
            this.updateButtonStates();
            console.log('Save button loading state cleared');
        }
    }

    resetFormTracking() {
        this.originalFormData = new FormData(this.form);
        this.formChanged = false;
        this.updateButtonStates();
    }

    handleThemePreview(e) {
        const card = e.currentTarget;
        const theme = card.dataset.theme;
        
        if (!theme) return;
        
        this.previewTheme(theme);
    }

    previewTheme(theme) {
        // Update active card
        this.previewCards.forEach(card => card.classList.remove('active'));
        const themeCard = document.querySelector(`[data-theme="${theme}"]`);
        if (themeCard) {
            themeCard.classList.add('active');
        }
        
        // Update the theme dropdown field to reflect the selection
        if (this.themeSelect) {
            this.themeSelect.value = theme;
            // Trigger change event to activate form change detection
            this.themeSelect.dispatchEvent(new Event('change', { bubbles: true }));
        }
        
        // Show preview controls immediately
        this.isPreviewMode = true;
        if (this.previewControls) {
            this.previewControls.classList.add('show');
        }
        
        // Update button states since we're in preview mode
        this.updateButtonStates();
        
        // Send preview request
        fetch(this.previewThemeUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
                'X-CSRFToken': this.csrfToken
            },
            body: `theme=${theme}`
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                // Store the selected theme for later saving
                if (this.previewControls) {
                    this.previewControls.dataset.selectedTheme = theme;
                }
                
                // Apply theme by updating CSS link
                this.applyThemeCSS(theme);
                
                // Show success feedback
                console.log(`Previewing ${theme} theme`);
            } else {
                console.error('Error previewing theme:', data.error);
                this.clearPreview();
            }
        })
        .catch(error => {
            console.error('Error previewing theme:', error);
            this.clearPreview();
        });
    }

    clearPreview() {
        // Reset active card to original theme
        this.previewCards.forEach(card => card.classList.remove('active'));
        const originalCard = document.querySelector(`[data-theme="${this.originalTheme}"]`);
        if (originalCard) {
            originalCard.classList.add('active');
        }
        
        // Reset the theme dropdown to original value
        if (this.themeSelect) {
            this.themeSelect.value = this.originalTheme;
            // Trigger change event to update form change detection
            this.themeSelect.dispatchEvent(new Event('change', { bubbles: true }));
        }
        
        fetch(this.clearThemePreviewUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
                'X-CSRFToken': this.csrfToken
            }
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                // Restore original theme CSS
                this.applyThemeCSS(this.originalTheme);
            }
        })
        .catch(error => {
            console.error('Error clearing preview:', error);
        });
        
        this.isPreviewMode = false;
        if (this.previewControls) {
            this.previewControls.classList.remove('show');
        }
        
        // Update button states since we're no longer in preview mode
        this.updateButtonStates();
    }

    applyThemeCSS(theme) {
        console.log(`Applying theme CSS: ${theme}`);
        
        // Find the Bootstrap CSS link
        const existingLink = document.querySelector('link[href*="bootswatch"], link[href*="bootstrap"]');
        
        if (existingLink) {
            console.log('Found existing CSS link:', existingLink.href);
            
            // Create new link element
            const newLink = document.createElement('link');
            newLink.rel = 'stylesheet';
            
            if (theme === 'bootstrap') {
                newLink.href = 'https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css';
            } else {
                newLink.href = `https://cdn.jsdelivr.net/npm/bootswatch@5.3.0/dist/${theme}/bootstrap.min.css`;
            }
            
            console.log('New CSS link will be:', newLink.href);
            
            // Replace the existing link
            existingLink.parentNode.insertBefore(newLink, existingLink.nextSibling);
            existingLink.remove();
            
            console.log('Theme CSS replaced successfully');
        } else {
            console.log('No existing Bootstrap CSS link found');
        }
    }

    handleSavePreview() {
        const selectedTheme = this.previewControls?.dataset.selectedTheme;
        if (selectedTheme && this.themeSelect) {
            // Update the form field
            this.themeSelect.value = selectedTheme;
            console.log('Updated theme select to:', selectedTheme);
            
            // Trigger form change detection
            this.checkFormChanges();
            
            // Save the settings
            this.saveSettings();
            
            // Update original theme reference
            this.originalTheme = selectedTheme;
        }
    }

    handleReset() {
        if (confirm('Are you sure you want to reset all settings to their default values?')) {
            this.resetToDefaults();
        }
    }

    resetToDefaults() {
        fetch(this.resetToDefaultsUrl, {
            method: 'POST',
            headers: {
                'X-Requested-With': 'XMLHttpRequest',
                'X-CSRFToken': this.csrfToken
            }
        })
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            console.log('Reset response:', data);
            if (data.success) {
                // Clear any preview mode first
                this.isPreviewMode = false;
                if (this.previewControls) {
                    this.previewControls.classList.remove('show');
                }
                
                // Update original theme reference first
                this.originalTheme = data.defaults.theme;
                
                // Update form fields with default values
                if (data.defaults) {
                    console.log('Resetting to default theme:', data.defaults.theme);
                    
                    // Update theme select
                    if (this.themeSelect) {
                        this.themeSelect.value = data.defaults.theme;
                        // Trigger change event to update theme tiles
                        this.themeSelect.dispatchEvent(new Event('change', { bubbles: true }));
                        console.log('Theme select updated to:', this.themeSelect.value);
                    }
                    
                    // Update other form fields
                    const itemsPerPageField = this.form.querySelector('#id_items_per_page');
                    if (itemsPerPageField) {
                        itemsPerPageField.value = data.defaults.items_per_page;
                    }
                    
                    const showCoversField = this.form.querySelector('#id_show_covers_in_list');
                    if (showCoversField) {
                        showCoversField.checked = data.defaults.show_covers_in_list;
                    }
                    
                    const viewModeField = this.form.querySelector('#id_default_view_mode');
                    if (viewModeField) {
                        viewModeField.value = data.defaults.default_view_mode;
                    }
                    
                    const shareProgressField = this.form.querySelector('#id_share_reading_progress');
                    if (shareProgressField) {
                        shareProgressField.checked = data.defaults.share_reading_progress;
                    }
                    
                    // Update theme cards active state
                    this.previewCards.forEach(card => card.classList.remove('active'));
                    const defaultThemeCard = document.querySelector(`[data-theme="${data.defaults.theme}"]`);
                    if (defaultThemeCard) {
                        defaultThemeCard.classList.add('active');
                        console.log('Default theme card activated:', data.defaults.theme);
                    } else {
                        console.log('Default theme card not found:', data.defaults.theme);
                    }
                    
                    // Apply default theme CSS
                    this.applyThemeCSS(data.defaults.theme);
                    
                    // Update the active theme display
                    this.updateActiveThemeCard(data.defaults.theme);
                }
                
                // Reset form change tracking
                this.resetFormTracking();
                
                // Show success message
                this.showAlert('success', data.message);
                
                console.log('Settings reset to defaults successfully');
            } else {
                this.showAlert('danger', 'Error resetting settings: ' + (data.message || data.error || 'Unknown error'));
            }
        })
        .catch(error => {
            console.error('Error resetting settings:', error);
            this.showAlert('danger', 'Error resetting settings. Please try again.');
        });
    }

    handleFormSubmit(e) {
        e.preventDefault();
        this.saveSettings();
    }

    saveSettings() {
        // Show loading state on save button
        this.setSaveButtonLoading(true);
        
        const formData = new FormData(this.form);
        
        // Log the form data for debugging
        console.log('Saving settings with data:');
        for (let [key, value] of formData.entries()) {
            console.log(key + ': ' + value);
        }
        
        fetch(this.userSettingsUrl, {
            method: 'POST',
            headers: {
                'X-Requested-With': 'XMLHttpRequest',
                'X-CSRFToken': this.csrfToken
            },
            body: formData
        })
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            console.log('Server response:', data);
            if (data.success) {
                // Show success message
                this.showAlert('success', data.message);
                
                // Apply the theme if it changed
                if (this.themeSelect) {
                    const newTheme = this.themeSelect.value;
                    if (newTheme !== this.originalTheme) {
                        console.log(`Applying theme change from ${this.originalTheme} to ${newTheme}`);
                        this.applyThemeCSS(newTheme);
                    }
                    this.originalTheme = newTheme;
                }
                
                // Clear preview mode
                this.isPreviewMode = false;
                if (this.previewControls) {
                    this.previewControls.classList.remove('show');
                }
                
                // Reset form change tracking since settings were saved successfully
                this.resetFormTracking();
                
                console.log('Settings saved successfully');
            } else {
                this.showAlert('danger', 'Error saving settings: ' + (data.message || data.error || 'Unknown error'));
            }
        })
        .catch(error => {
            console.error('Error saving settings:', error);
            this.showAlert('danger', 'Error saving settings. Please try again.');
        })
        .finally(() => {
            // Always clear loading state
            this.setSaveButtonLoading(false);
        });
    }

    showAlert(type, message) {
        const alertDiv = document.createElement('div');
        alertDiv.className = `alert alert-${type} alert-dismissible fade show`;
        alertDiv.innerHTML = `
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;
        
        const container = document.querySelector('.container-fluid');
        if (container) {
            container.insertBefore(alertDiv, container.firstChild);
        }
        
        // Auto-dismiss after 8 seconds
        setTimeout(() => {
            if (alertDiv.parentNode) {
                alertDiv.classList.remove('show');
                alertDiv.classList.add('fade');
                setTimeout(() => {
                    if (alertDiv.parentNode) {
                        alertDiv.remove();
                    }
                }, 300);
            }
        }, 8000);
    }

    updateActiveThemeCard(activeTheme = null) {
        const currentTheme = activeTheme || this.themeSelect?.value || this.originalTheme;
        
        this.previewCards.forEach(card => {
            card.classList.remove('active');
            if (card.dataset.theme === currentTheme) {
                card.classList.add('active');
            }
        });
    }
}

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    // Only initialize if we're on the settings page
    if (document.getElementById('settingsForm')) {
        window.userSettingsManager = new UserSettingsManager();
    }
});

// Export for global access
window.UserSettingsManager = UserSettingsManager;