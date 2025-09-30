/**
 * User Settings - Theme preview and settings management
 * Extracted from user_settings.html inline JavaScript
 */

class UserSettingsManager {
    constructor() {
        this.form = document.getElementById('settingsForm');
        this.themeSelect = document.querySelector('select[name="theme"]');
        this.previewCards = document.querySelectorAll('.theme-preview-card');
        this.previewControls = document.getElementById('previewControls');
        this.savePreview = document.getElementById('savePreview');
        this.cancelPreview = document.getElementById('cancelPreview');
        this.resetButton = document.getElementById('resetForm');
        
        this.isPreviewMode = false;
        this.originalTheme = '';
        
        this.init();
    }

    init() {
        if (!this.form) return;
        
        this.bindEvents();
        this.initializeThemePreview();
    }

    bindEvents() {
        // Theme preview functionality
        this.previewCards.forEach(card => {
            card.addEventListener('click', (e) => this.handleThemePreview(e));
        });

        // Theme select change
        if (this.themeSelect) {
            this.themeSelect.addEventListener('change', (e) => this.handleThemeChange(e));
        }

        // Preview controls
        this.savePreview?.addEventListener('click', () => this.saveThemePreview());
        this.cancelPreview?.addEventListener('click', () => this.cancelThemePreview());

        // Reset form
        this.resetButton?.addEventListener('click', () => this.resetForm());

        // Form submission
        this.form.addEventListener('submit', (e) => this.handleFormSubmit(e));
    }

    initializeThemePreview() {
        // Store original theme
        if (this.themeSelect) {
            this.originalTheme = this.themeSelect.value;
        }

        // Mark current theme card as active
        this.updateActiveThemeCard();
    }

    handleThemePreview(e) {
        const card = e.currentTarget;
        const themeName = card.dataset.theme;
        
        if (!themeName) return;

        // Update theme select
        if (this.themeSelect) {
            this.themeSelect.value = themeName;
        }

        // Apply theme preview
        this.applyThemePreview(themeName);
        
        // Show preview controls
        this.showPreviewMode();
        
        // Update active card
        this.updateActiveThemeCard(themeName);
    }

    handleThemeChange(e) {
        const newTheme = e.target.value;
        this.applyThemePreview(newTheme);
        this.updateActiveThemeCard(newTheme);
        
        if (newTheme !== this.originalTheme) {
            this.showPreviewMode();
        } else {
            this.hidePreviewMode();
        }
    }

    applyThemePreview(themeName) {
        // Remove existing theme classes
        document.documentElement.className = document.documentElement.className
            .replace(/theme-[^\s]+/g, '');
        
        // Apply new theme
        if (themeName && themeName !== 'default') {
            document.documentElement.classList.add(`theme-${themeName}`);
        }

        // Update Bootstrap theme if available
        const themeLink = document.getElementById('bootstrap-theme');
        if (themeLink && themeName !== 'default') {
            themeLink.href = `/static/book/css/themes/${themeName}.min.css`;
        } else if (themeLink) {
            themeLink.href = '/static/book/css/themes/default.min.css';
        }
    }

    updateActiveThemeCard(activeTheme = null) {
        const currentTheme = activeTheme || this.themeSelect?.value || 'default';
        
        this.previewCards.forEach(card => {
            card.classList.remove('active');
            if (card.dataset.theme === currentTheme) {
                card.classList.add('active');
            }
        });
    }

    showPreviewMode() {
        this.isPreviewMode = true;
        
        if (this.previewControls) {
            this.previewControls.classList.remove('d-none');
        }
        
        // Add visual indicator
        document.body.classList.add('theme-preview-mode');
    }

    hidePreviewMode() {
        this.isPreviewMode = false;
        
        if (this.previewControls) {
            this.previewControls.classList.add('d-none');
        }
        
        // Remove visual indicator
        document.body.classList.remove('theme-preview-mode');
    }

    saveThemePreview() {
        // Update original theme
        this.originalTheme = this.themeSelect?.value || 'default';
        
        // Hide preview mode
        this.hidePreviewMode();
        
        // Submit form to save settings
        if (this.form) {
            this.form.submit();
        }
    }

    cancelThemePreview() {
        // Revert to original theme
        if (this.themeSelect) {
            this.themeSelect.value = this.originalTheme;
        }
        
        this.applyThemePreview(this.originalTheme);
        this.updateActiveThemeCard(this.originalTheme);
        this.hidePreviewMode();
    }

    resetForm() {
        if (confirm('Are you sure you want to reset all settings to default values?')) {
            // Reset form fields
            if (this.form) {
                this.form.reset();
            }
            
            // Reset theme
            this.originalTheme = 'default';
            this.applyThemePreview('default');
            this.updateActiveThemeCard('default');
            this.hidePreviewMode();
        }
    }

    async handleFormSubmit(e) {
        e.preventDefault();
        
        // Show loading state
        const submitBtn = this.form.querySelector('button[type="submit"]');
        const originalText = submitBtn?.textContent;
        
        if (submitBtn) {
            submitBtn.disabled = true;
            submitBtn.textContent = 'Saving...';
        }

        try {
            const formData = new FormData(this.form);
            
            const response = await fetch(this.form.action || window.location.href, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': EbookLibrary.Ajax.getCSRFToken()
                },
                body: formData
            });

            if (response.ok) {
                // Update original theme on successful save
                this.originalTheme = this.themeSelect?.value || 'default';
                this.hidePreviewMode();
                
                EbookLibrary.UI.showAlert('Settings saved successfully!', 'success');
            } else {
                EbookLibrary.UI.showAlert('Failed to save settings', 'danger');
            }
        } catch (error) {
            EbookLibrary.UI.showAlert('Network error occurred', 'danger');
        } finally {
            if (submitBtn) {
                submitBtn.disabled = false;
                submitBtn.textContent = originalText;
            }
        }
    }
}

// Global instance
let userSettingsManager;

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    userSettingsManager = new UserSettingsManager();
});

// Export for global access
window.UserSettingsManager = UserSettingsManager;