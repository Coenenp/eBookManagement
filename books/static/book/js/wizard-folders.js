/**
 * Wizard Folders JavaScript functionality
 * Handles folder browsing, validation, and preview functionality
 */

// Wizard Folders namespace
Wizard.Folders = {
    /**
     * Initialize the folders step
     */
    init() {
        if (this.initialized) {
            return;
        }
        this.initialized = true;
        
        this.setupEventListeners();
        this.setupFormValidation();
        this.initializeExistingInputs();
    },

    /**
     * Setup event listeners for folder functionality
     */
    setupEventListeners() {
        // Add event listeners using event delegation for dynamic elements
        document.addEventListener('click', (e) => {
            if (e.target.matches('.add-folder-btn') || e.target.closest('.add-folder-btn')) {
                e.preventDefault();
                e.stopPropagation();
                this.addCustomFolder();
            }
            
            if (e.target.matches('.remove-folder-btn') || e.target.closest('.remove-folder-btn')) {
                e.preventDefault();
                e.stopPropagation();
                this.removeCustomFolder(e.target.closest('.remove-folder-btn'));
            }
            
            if (e.target.matches('.show-examples-btn') || e.target.closest('.show-examples-btn')) {
                e.preventDefault();
                e.stopPropagation();
                this.togglePathExamples(e.target.closest('.show-examples-btn'));
            }
        });

        // Handle checkbox changes for suggested folders
        document.addEventListener('change', (e) => {
            if (e.target.matches('input[name="folders"]')) {
                this.toggleFolderSelection(e.target);
            }
        });
    },

    /**
     * Setup form validation
     */
    setupFormValidation() {
        const form = document.querySelector('form');
        Wizard.Form.setupValidation(form, this.validateForm.bind(this));
    },

    /**
     * Initialize existing folder inputs with validation
     */
    initializeExistingInputs() {
        const customFolderInputs = document.querySelectorAll('.custom-folder-input');
        customFolderInputs.forEach(input => {
            this.addFolderValidation(input);
        });

        // Initialize visual state for pre-selected folders
        const folderCheckboxes = document.querySelectorAll('input[name="folders"]');
        folderCheckboxes.forEach(checkbox => {
            if (checkbox.checked) {
                this.toggleFolderSelection(checkbox);
            }
        });

        // Initialize add button state
        this.updateAddFolderButtonState();
    },

    /**
     * Add a new custom folder input
     */
    addCustomFolder() {
        const container = document.getElementById('customFoldersContainer');
        if (!container) return;

        // Check if we should allow adding more folders
        if (!this.canAddMoreFolders()) {
            return;
        }

        const newFolderCard = document.createElement('div');
        newFolderCard.className = 'card mb-3 custom-folder-card';
        newFolderCard.innerHTML = `
            <div class="card-body">
                <div class="d-flex align-items-start">
                    <div class="flex-grow-1">
                        <label class="form-label">Folder Path</label>
                        <div class="input-group">
                            <span class="input-group-text bg-light">
                                <i class="fas fa-folder text-primary"></i>
                            </span>
                            <input type="text" class="form-control custom-folder-input" 
                                   name="custom_folders" 
                                   placeholder="Enter folder path (e.g., C:\\\\Books or /home/user/ebooks)"
                                   autocomplete="off">
                            <button class="btn btn-outline-secondary show-examples-btn" type="button" title="Show path examples">
                                <i class="fas fa-question-circle" aria-hidden="true"></i>
                                <span class="visually-hidden">Show path examples</span>
                            </button>
                        </div>
                        <div class="form-text custom-folder-feedback"></div>
                    </div>
                    <button type="button" class="btn btn-outline-danger btn-sm ms-2 mt-4 remove-folder-btn" 
                            title="Remove this folder">
                        <i class="fas fa-trash"></i>
                    </button>
                </div>
            </div>
        `;
        
        container.appendChild(newFolderCard);
        
        // Focus on the new input and add validation
        const newInput = newFolderCard.querySelector('.custom-folder-input');
        newInput.focus();
        this.addFolderValidation(newInput);
        
        // Update button state after adding new folder
        this.updateAddFolderButtonState();
    },

    /**
     * Remove a custom folder input
     */
    removeCustomFolder(button) {
        const card = button.closest('.custom-folder-card');
        const container = document.getElementById('customFoldersContainer');
        
        if (!card || !container) return;

        // Don't remove if it's the only folder input
        if (container.children.length > 1) {
            card.remove();
        } else {
            // Clear the input instead of removing the card
            const input = card.querySelector('.custom-folder-input');
            const feedback = card.querySelector('.custom-folder-feedback');
            if (input) {
                input.value = '';
                Wizard.Utils.clearValidation(input);
            }
            if (feedback) {
                feedback.innerHTML = '';
            }
        }
        
        // Update button state after removing folder
        this.updateAddFolderButtonState();
    },

    /**
     * Toggle path examples visibility
     */
    togglePathExamples(button) {
        const examples = document.getElementById('pathExamples');
        if (examples) {
            Wizard.Utils.toggleCollapse(examples, button);
        }
    },

    /**
     * Add validation to a folder input
     */
    addFolderValidation(input) {
        if (!input) return;

        const debouncedValidation = Wizard.Utils.debounce(() => {
            const path = input.value.trim();
            if (path.length > 3) {
                this.validateCustomFolderPath(input);
            } else {
                // Clear validation state for short inputs
                Wizard.Utils.clearValidation(input);
                const feedback = input.closest('.card-body').querySelector('.custom-folder-feedback');
                if (feedback) {
                    feedback.innerHTML = '';
                }
                // Update button state when input changes
                this.updateAddFolderButtonState();
            }
        }, 500);

        input.addEventListener('input', debouncedValidation);
    },

    /**
     * Validate a custom folder path via AJAX with improved UI feedback
     */
    async validateCustomFolderPath(input) {
        const feedback = input.closest('.card-body').querySelector('.custom-folder-feedback');
        const path = input.value.trim();
        
        if (!feedback) {
            console.error('Feedback element not found for folder validation');
            return;
        }
        
        // Disable form submission during validation
        this.setFormValidationState(false);
        
        // Show loading state with better message
        Wizard.Utils.showLoading(feedback, 'Validating folder... <small class="text-muted">(checking for media files)</small>');
        
        try {
            const validationUrl = window.wizardConfig?.validateUrl || 
                                window.wizardFoldersConfig?.validateUrl || 
                                '/books/wizard/ajax/validate-folder/';
            
            const data = await Wizard.Utils.makeRequest(validationUrl, {
                body: 'path=' + encodeURIComponent(path)
            });
            
            if (data.valid) {
                Wizard.Utils.setValidationState(input, true);
                const fileMessage = data.file_count === 0 ? 'no media files found' : 
                                  `${data.file_count} media files found`;
                const message = `<i class="fas fa-check-circle text-success me-1"></i>Valid folder: <strong>${data.name}</strong> 
                               <span class="badge bg-success ms-2">${fileMessage}</span>`;
                Wizard.Utils.showSuccess(feedback, message);
            } else {
                Wizard.Utils.setValidationState(input, false);
                Wizard.Utils.showError(feedback, `<i class="fas fa-exclamation-triangle me-1"></i>${data.error}`);
            }
            
        } catch (error) {
            console.error('Error validating folder:', error);
            Wizard.Utils.setValidationState(input, false);
            Wizard.Utils.showWarning(feedback, '<i class="fas fa-exclamation-circle me-1"></i>Validation timeout - folder may be too large or inaccessible');
        }
        
        // Re-enable form and update button state
        this.setFormValidationState(true);
        this.updateAddFolderButtonState();
    },

    /**
     * Enable/disable form submission during validation
     */
    setFormValidationState(enabled) {
        const continueButton = document.querySelector('button[type="submit"]');
        if (continueButton) {
            continueButton.disabled = !enabled;
            if (!enabled) {
                continueButton.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>Validating folders...';
            } else {
                continueButton.innerHTML = '<i class="fas fa-arrow-right me-2"></i>Continue to Content Types';
            }
        }
    },

    /**
     * Check if more folders can be added (all existing inputs must be valid)
     */
    canAddMoreFolders() {
        const customFolderInputs = document.querySelectorAll('.custom-folder-input');
        
        // If no inputs exist, allow adding the first one
        if (customFolderInputs.length === 0) {
            return true;
        }
        
        // Check if all inputs either are empty (and thus can be filled) or are valid
        for (const input of customFolderInputs) {
            const value = input.value.trim();
            // If input has value but is not valid, don't allow adding more
            if (value && !input.classList.contains('is-valid')) {
                return false;
            }
            // If input is empty, it needs to be filled first
            if (!value) {
                return false;
            }
        }
        
        return true;
    },

    /**
     * Update the add folder button state based on validation
     */
    updateAddFolderButtonState() {
        const addButton = document.querySelector('.add-folder-btn');
        if (!addButton) return;
        
        const canAdd = this.canAddMoreFolders();
        addButton.disabled = !canAdd;
        
        if (canAdd) {
            addButton.classList.remove('btn-outline-secondary');
            addButton.classList.add('btn-outline-primary');
            addButton.title = 'Add another scan folder';
        } else {
            addButton.classList.remove('btn-outline-primary');
            addButton.classList.add('btn-outline-secondary');
            addButton.title = 'Complete the current folder path before adding another';
        }
    },

    /**
     * Toggle folder selection visual state
     */
    toggleFolderSelection(checkbox) {
        const card = checkbox.closest('.card');
        if (!card) return;

        if (checkbox.checked) {
            card.classList.add('border-primary', 'bg-primary-subtle');
        } else {
            card.classList.remove('border-primary', 'bg-primary-subtle');
        }
    },

    /**
     * Validate the entire form before submission
     */
    validateForm(form) {
        const selectedFolders = form.querySelectorAll('input[name="folders"]:checked');
        const customFolderInputs = form.querySelectorAll('.custom-folder-input');
        
        // Check if any custom folders have values
        const hasCustomFolders = Wizard.Form.hasAtLeastOneValue(customFolderInputs);
        
        if (selectedFolders.length === 0 && !hasCustomFolders) {
            Wizard.Form.showValidationError('Please select at least one folder or enter a custom folder path.');
            return false;
        }

        // Check if any custom folder inputs are still being validated
        const invalidInputs = form.querySelectorAll('.custom-folder-input.is-invalid');
        if (invalidInputs.length > 0) {
            Wizard.Form.showValidationError('Please fix invalid folder paths before continuing.');
            return false;
        }
        
        return true;
    }
};

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    Wizard.Folders.init();
});

// Legacy support removed - using event delegation only

// Export for global access
window.WizardFolders = Wizard.Folders;

// Initialize when DOM is ready (with flag to prevent double initialization)
if (!window.wizardFoldersInitialized) {
    window.wizardFoldersInitialized = true;
    document.addEventListener('DOMContentLoaded', function() {
        Wizard.Folders.init();
    });
}