/**
 * Template Manager - Handles template creation, editing, and deletion
 */
class TemplateManager {
    constructor() {
        this.previewTimeout = null;
        this.validationState = {
            folder: false,
            filename: false,
        };
        this.savedTemplates = [];
        this.init();
    }

    init() {
        this.bindEvents();
        // Initially disable fields until a template is selected
        this.setInitialState();
        this.loadSavedTemplates().then(() => {
            // After templates are loaded, check if there's a template parameter in the URL
            this.loadTemplateFromUrl();
        });
    }

    /**
     * Set initial state - disable fields when no template is selected
     */
    setInitialState() {
        const $select = $('#template-selector');
        if (!$select.val()) {
            $('#folder-pattern').prop('disabled', true);
            $('#filename-pattern').prop('disabled', true);
            $('#save-template-btn').prop('disabled', true);
            $('#delete-template-btn').prop('disabled', true);
        }
    }

    /**
     * Load a template from URL parameter if present
     */
    loadTemplateFromUrl() {
        const urlParams = new URLSearchParams(window.location.search);
        const templateParam = urlParams.get('template');

        // Prioritize URL parameter, then fall back to default template
        let templateToLoad = templateParam || window.defaultTemplateKey;

        if (templateToLoad) {
            const $select = $('#template-selector');

            // Check if we need to add 'system-' prefix for system templates
            let $option = $select.find(`option[value="${templateToLoad}"]`);
            if ($option.length === 0 && !templateToLoad.startsWith('user-') && !templateToLoad.startsWith('system-')) {
                // Try with 'system-' prefix
                templateToLoad = `system-${templateToLoad}`;
                $option = $select.find(`option[value="${templateToLoad}"]`);
            }

            if ($option.length > 0) {
                $select.val(templateToLoad).trigger('change');
                console.log(`Pre-loaded template: ${templateToLoad}`);
            } else {
                console.warn(`Template not found in selector: ${templateToLoad}`);
            }
        }
    }

    bindEvents() {
        // Template selector
        $('#template-selector').on('change', (e) => this.loadTemplate(e));
        $('#save-template-btn').on('click', () => this.showSaveTemplateDialog());
        $('#delete-template-btn').on('click', () => this.deleteTemplate());

        // Pattern form events with live preview
        $('#folder-pattern, #filename-pattern').on('input', (e) => {
            this.validatePattern(e);
            this.updateLivePreview();
            this.updateButtonStates();
        });

        // Token reference events
        $('.token-clickable').on('click', (e) => this.insertToken(e));
        $('.example-clickable').on('click', (e) => this.loadExample(e));
    }

    async loadSavedTemplates() {
        try {
            const response = await $.get('/renamer/load-templates/');
            if (response.success && response.templates) {
                const group = $('#saved-templates-group');
                group.empty();

                this.savedTemplates = response.templates;

                response.templates.forEach((template) => {
                    group.append(`<option value="user-${template.name}" 
                                          data-folder="${template.folder}" 
                                          data-filename="${template.filename}"
                                          data-description="${template.description || ''}"
                                          data-deletable="true">
                                    ⭐ ${template.name}${template.description ? ' - ' + template.description : ''}
                                  </option>`);
                });
            }
        } catch (error) {
            console.error('Error loading templates:', error);
        }
    }

    loadTemplate(e) {
        const $select = $(e.target);
        const $option = $select.find('option:selected');

        if (!$option.val()) {
            // Clear fields if no template selected and disable them
            $('#folder-pattern').val('').removeClass('field-filled').addClass('field-empty').prop('disabled', true);
            $('#filename-pattern').val('').removeClass('field-filled').addClass('field-empty').prop('disabled', true);
            $('#delete-template-btn').prop('disabled', true);
            $('#save-template-btn').prop('disabled', true);
            this.updateLivePreview();
            return;
        }

        // Enable fields when a template is selected
        $('#folder-pattern').prop('disabled', false);
        $('#filename-pattern').prop('disabled', false);

        const folderPattern = $option.data('folder');
        const filenamePattern = $option.data('filename');
        const isDeletable = $option.data('deletable');

        // Fill pattern fields with visual feedback
        if (folderPattern) {
            $('#folder-pattern').val(folderPattern).removeClass('field-empty').addClass('field-filled');
        } else {
            $('#folder-pattern').val('').removeClass('field-filled').addClass('field-empty');
        }

        if (filenamePattern) {
            $('#filename-pattern').val(filenamePattern).removeClass('field-empty').addClass('field-filled');
        } else {
            $('#filename-pattern').val('').removeClass('field-filled').addClass('field-empty');
        }

        // Enable/disable delete button based on whether template is deletable
        $('#delete-template-btn').prop('disabled', !isDeletable);

        // Trigger validation and preview
        $('#folder-pattern, #filename-pattern').trigger('input');
        this.updateButtonStates();
    }

    validatePattern(e) {
        const $input = $(e.target);
        const value = $input.val();
        const $validationDiv = $input.siblings('[id$="-validation"]');
        const patternType = $input.attr('id').replace('-pattern', '');

        if (!value) {
            $validationDiv.html('');
            this.validationState[patternType] = false;
            return;
        }

        // Basic validation - check for required tokens
        const hasTokens = value.includes('${');

        if (hasTokens) {
            $validationDiv.html(
                '<small class="text-success"><i class="fas fa-check-circle me-1"></i>Valid pattern</small>'
            );
            this.validationState[patternType] = true;
        } else {
            $validationDiv.html(
                '<small class="text-warning"><i class="fas fa-exclamation-triangle me-1"></i>Consider using tokens for dynamic values</small>'
            );
            this.validationState[patternType] = true; // Still valid, just a warning
        }
    }

    updateLivePreview() {
        clearTimeout(this.previewTimeout);
        this.previewTimeout = setTimeout(() => this.generateLivePreview(), 300);
    }

    async generateLivePreview() {
        const folderPattern = $('#folder-pattern').val();
        const filenamePattern = $('#filename-pattern').val();

        if (!folderPattern && !filenamePattern) {
            $('#pattern-preview').html('<em class="text-muted">Enter patterns to see preview...</em>');
            return;
        }

        try {
            const response = await $.post('/renamer/preview-pattern/', {
                folder_pattern: folderPattern,
                filename_pattern: filenamePattern,
                csrfmiddlewaretoken: $('[name=csrfmiddlewaretoken]').val(),
            });

            if (response.success) {
                const { book_id, title, author, target_folder, target_filename, full_target_path } = response;
                $('#pattern-preview').html(`
                    <div><strong>Book:</strong> ${title} by ${author}</div>
                    <div><strong>Folder:</strong> <code>${target_folder || 'N/A'}</code></div>
                    <div><strong>Filename:</strong> <code>${target_filename || 'N/A'}</code></div>
                    <div class="mt-2"><strong>Full Path:</strong> <code class="text-primary">${full_target_path || 'N/A'}</code></div>
                `);
            } else {
                $('#pattern-preview').html(
                    `<div class="text-danger"><i class="fas fa-exclamation-triangle me-1"></i>${response.error || 'Error generating preview'}</div>`
                );
            }
        } catch (error) {
            console.error('Preview error:', error);
            $('#pattern-preview').html(
                '<div class="text-danger"><i class="fas fa-exclamation-triangle me-1"></i>Error generating preview</div>'
            );
        }
    }

    updateButtonStates() {
        const folderPattern = $('#folder-pattern').val();
        const filenamePattern = $('#filename-pattern').val();
        const hasPatterns = folderPattern || filenamePattern;
        const isValid = this.validationState.folder || this.validationState.filename;

        // Check if current pattern is a duplicate
        const isDuplicate = this.savedTemplates.some(
            (template) => template.folder === folderPattern && template.filename === filenamePattern
        );

        // Also check system templates
        const systemTemplates = $('#template-selector optgroup[label="System Templates"] option');
        const isSystemDuplicate = Array.from(systemTemplates).some((option) => {
            const $option = $(option);
            return $option.data('folder') === folderPattern && $option.data('filename') === filenamePattern;
        });

        // Enable save only if valid and not a duplicate
        $('#save-template-btn').prop('disabled', !hasPatterns || !isValid || isDuplicate || isSystemDuplicate);
    }

    showSaveTemplateDialog() {
        const folderPattern = $('#folder-pattern').val();
        const filenamePattern = $('#filename-pattern').val();

        if (!folderPattern && !filenamePattern) {
            alert('Please enter at least one pattern before saving.');
            return;
        }

        const name = prompt('Enter a name for this template:');
        if (!name) return;

        const description = prompt('Enter a description (optional):');

        this.saveTemplate(name, description, folderPattern, filenamePattern);
    }

    async saveTemplate(name, description, folderPattern, filenamePattern) {
        try {
            const response = await $.post('/renamer/save-template/', {
                name: name,
                description: description || '',
                folder_pattern: folderPattern,
                filename_pattern: filenamePattern,
                csrfmiddlewaretoken: $('[name=csrfmiddlewaretoken]').val(),
            });

            if (response.success) {
                alert('Template saved successfully!');
                await this.loadSavedTemplates();
                // Select the newly saved template
                $(`#template-selector option[value="user-${name}"]`).prop('selected', true);
            } else {
                alert('Error saving template: ' + (response.error || 'Unknown error'));
            }
        } catch (error) {
            console.error('Save error:', error);
            alert('Error saving template. Please try again.');
        }
    }

    async deleteTemplate() {
        const $select = $('#template-selector');
        const selectedValue = $select.val();

        if (!selectedValue || !selectedValue.startsWith('user-')) {
            alert('Please select a user template to delete.');
            return;
        }

        const templateName = selectedValue.replace('user-', '');

        if (!confirm(`Are you sure you want to delete the template "${templateName}"?`)) {
            return;
        }

        try {
            const response = await $.post('/renamer/delete-template/', {
                name: templateName,
                csrfmiddlewaretoken: $('[name=csrfmiddlewaretoken]').val(),
            });

            if (response.success) {
                alert('Template deleted successfully!');
                await this.loadSavedTemplates();
                $select.val('').trigger('change');
            } else {
                alert('Error deleting template: ' + (response.error || 'Unknown error'));
            }
        } catch (error) {
            console.error('Delete error:', error);
            alert('Error deleting template. Please try again.');
        }
    }

    insertToken(e) {
        const token = $(e.target).data('token');
        const $focusedInput = $('#folder-pattern:focus, #filename-pattern:focus');

        if ($focusedInput.length) {
            const input = $focusedInput[0];
            const start = input.selectionStart;
            const end = input.selectionEnd;
            const value = $focusedInput.val();
            const newValue = value.substring(0, start) + token + value.substring(end);

            $focusedInput.val(newValue);
            input.setSelectionRange(start + token.length, start + token.length);
            $focusedInput.trigger('input');
            $focusedInput.focus();
        } else {
            // If no input focused, append to folder pattern
            const $folder = $('#folder-pattern');
            $folder.val($folder.val() + ($folder.val() ? '/' : '') + token);
            $folder.trigger('input');
        }
    }

    loadExample(e) {
        const $example = $(e.currentTarget);
        const folderPattern = $example.data('folder');
        const filenamePattern = $example.data('filename');

        $('#folder-pattern').val(folderPattern).removeClass('field-empty').addClass('field-filled');
        $('#filename-pattern').val(filenamePattern).removeClass('field-empty').addClass('field-filled');

        $('#folder-pattern, #filename-pattern').trigger('input');
    }
}

// Initialize when DOM is ready
$(document).ready(() => {
    new TemplateManager();
});
