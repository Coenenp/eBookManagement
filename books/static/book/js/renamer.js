/**
 * Ebook & Series Renamer - Interactive JavaScript
 *
 * Handles pattern validation, live previews, and batch operations
 */

class EbookRenamer {
    constructor() {
        this.selectedBooks = new Set();
        this.currentPreview = null;
        this.validationTimeouts = {};
        this.currentTemplate = null; // Track currently selected template
        this.previewTimeout = null;
        this.validationState = {
            folder: false,
            filename: false,
        };
        this.savedTemplates = []; // Track saved template names

        this.init();
    }

    init() {
        this.bindEvents();
        this.updateSelectionCount();
        this.loadSavedTemplates().then(() => {
            // After templates are loaded, load default template if specified
            this.loadDefaultTemplate();
        });
        this.restoreScrollPosition(); // Restore scroll position after filter
    }

    /**
     * Load default template if specified
     */
    loadDefaultTemplate() {
        const defaultTemplateKey = window.defaultTemplateKey;
        if (defaultTemplateKey) {
            const $select = $('#template-selector');
            const $option = $select.find(`option[value="${defaultTemplateKey}"]`);

            if ($option.length > 0) {
                $select.val(defaultTemplateKey).trigger('change');
                console.log(`Loaded default template: ${defaultTemplateKey}`);
            } else {
                console.warn(`Default template not found: ${defaultTemplateKey}`);
            }
        }
    }

    bindEvents() {
        // Unified template selector
        $('#template-selector').on('change', (e) => this.loadTemplate(e));
        $('#save-template-btn').on('click', () => this.showSaveTemplateDialog());
        $('#delete-template-btn').on('click', () => this.deleteTemplate());

        // Pattern form events - not needed since patterns are read-only displays
        // Patterns are selected via template dropdown only

        // Token reference events
        $('.token-clickable').on('click', (e) => this.insertToken(e));
        $('.example-clickable').on('click', (e) => this.loadExample(e));

        // Action buttons
        $('#preview-btn').on('click', () => this.previewChanges());
        $('#execute-btn').on('click', () => this.executeRename());

        // Book selection events
        $('#select-all-checkbox').on('change', (e) => this.toggleAllBooks(e));
        $('.book-checkbox').on('change', (e) => this.toggleBook(e));
        $('#select-all-btn').on('click', () => this.selectAllBooks());
        $('#select-none-btn').on('click', () => this.selectNoneBooks());

        // Filter events
        $('#apply-filters-btn').on('click', () => this.applyFilters());
        $('#search-filter').on('keypress', (e) => {
            if (e.which === 13) this.applyFilters();
        });

        // Apply filters on Enter key for all filter fields
        $('#content-type-filter, #format-filter, #language-filter').on('keypress', (e) => {
            if (e.which === 13) this.applyFilters();
        });
    }

    async loadSavedTemplates() {
        try {
            const response = await $.get('/renamer/load-templates/');
            if (response.success && response.templates) {
                const group = $('#saved-templates-group');
                group.empty();

                // Store templates for duplicate checking
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
            this.updateButtonStates();
        } catch (error) {
            console.error('Error loading templates:', error);
        }
    }

    loadTemplate(event) {
        const selectedOption = $(event.target).find(':selected');
        const templateValue = selectedOption.val();

        if (templateValue) {
            const folderPattern = selectedOption.data('folder') || '';
            const filenamePattern = selectedOption.data('filename') || '';
            const isDeletable = selectedOption.data('deletable') === true;

            console.log('Loading template:', { templateValue, folderPattern, filenamePattern, isDeletable });

            // Store patterns for later use
            this.currentFolderPattern = folderPattern;
            this.currentFilenamePattern = filenamePattern;

            // Update display divs (read-only pattern displays)
            if (folderPattern) {
                $('#folder-pattern-display').html(`<code>${folderPattern}</code>`);
            } else {
                $('#folder-pattern-display').html('<em class="text-muted">Select a template...</em>');
            }

            if (filenamePattern) {
                $('#filename-pattern-display').html(`<code>${filenamePattern}</code>`);
            } else {
                $('#filename-pattern-display').html('<em class="text-muted">Select a template...</em>');
            }

            // Track current template
            this.currentTemplate = templateValue.startsWith('user-') ? templateValue.replace('user-', '') : null;

            // Update preview example
            this.updatePreviewExample(folderPattern, filenamePattern);

            // Update book table previews
            this.updateBookTablePreviews();

            // Enable/disable delete button based on template type
            $('#delete-template-btn').prop('disabled', !isDeletable);

            // Trigger validation and preview
            this.validatePattern({ target: $('#folder-pattern')[0] });
            this.validatePattern({ target: $('#filename-pattern')[0] });
            this.updateLivePreview();
            this.updateButtonStates();
        } else {
            // Clear stored patterns and display divs when no template selected
            this.currentFolderPattern = '';
            this.currentFilenamePattern = '';
            $('#folder-pattern-display').html('<em class="text-muted">Select a template...</em>');
            $('#filename-pattern-display').html('<em class="text-muted">Select a template...</em>');
            this.currentTemplate = null;
            this.validationState = { folder: false, filename: false };

            // Clear validation and preview
            $('#folder-pattern-validation').empty();
            $('#filename-pattern-validation').empty();
            $('#pattern-preview').html('<em class="text-muted">Select a template to get started...</em>');
            this.updateButtonStates();
        }
    }

    /**
     * Update preview example with sample book metadata
     */
    updatePreviewExample(folderPattern, filenamePattern) {
        // Example book metadata for preview
        const exampleAuthor = 'Asimov, Isaac';
        const exampleTitle = 'Foundation';
        const exampleSeries = 'Foundation Series';
        const exampleSeriesNum = '01';
        const exampleYear = '1951';
        const exampleGenre = 'Science Fiction';
        const exampleExt = 'epub';

        // Simple token replacement for preview
        let folderPreview = folderPattern || '';
        let filenamePreview = filenamePattern || '';

        // Replace common tokens
        const replacements = {
            '${author.sortname}': exampleAuthor,
            '${author}': exampleAuthor,
            '${title}': exampleTitle,
            '${bookseries.title}': exampleSeries,
            '${series}': exampleSeries,
            '${bookseries.number}': exampleSeriesNum,
            '${series_number}': exampleSeriesNum,
            '${publicationyear}': exampleYear,
            '${year}': exampleYear,
            '${genre}': exampleGenre,
            '${ext}': exampleExt,
        };

        Object.keys(replacements).forEach((token) => {
            folderPreview = folderPreview.replace(
                new RegExp(token.replace(/[.*+?^${}()|[\\]\\\\]/g, '\\\\$&'), 'g'),
                replacements[token]
            );
            filenamePreview = filenamePreview.replace(
                new RegExp(token.replace(/[.*+?^${}()|[\\]\\\\]/g, '\\\\$&'), 'g'),
                replacements[token]
            );
        });

        // Update preview displays
        if (folderPreview) {
            $('#preview-folder-example').text(folderPreview);
        } else {
            $('#preview-folder-example').text('Select a template to see preview');
        }

        if (filenamePreview) {
            $('#preview-filename-example').text(filenamePreview);
        } else {
            $('#preview-filename-example').text('Select a template to see preview');
        }
    }

    /**
     * Update book table previews for all books
     */
    async updateBookTablePreviews() {
        const folderPattern = this.currentFolderPattern;
        const filenamePattern = this.currentFilenamePattern;

        if (!folderPattern || !filenamePattern) {
            // Clear all previews if no patterns
            $('.preview-path').each(function () {
                $(this).html('<span class="text-muted fst-italic">Configure patterns to see preview</span>');
            });
            return;
        }

        // Get all book IDs from the table
        const bookIds = [];
        $('.book-checkbox').each(function () {
            bookIds.push($(this).val());
        });

        if (bookIds.length === 0) {
            return;
        }

        try {
            const response = await $.post('/renamer/preview-pattern/', {
                folder_pattern: folderPattern,
                filename_pattern: filenamePattern,
                book_ids: bookIds,
                csrfmiddlewaretoken: $('[name=csrfmiddlewaretoken]').val(),
            });

            if (response.success && response.previews) {
                // Update each book's preview in the table
                response.previews.forEach((preview) => {
                    const bookRow = $(`.book-checkbox[value="${preview.book_id}"]`).closest('tr');
                    const previewCell = bookRow.find('.preview-path');

                    if (preview.new_path) {
                        previewCell.html(
                            `<span class="text-truncate d-inline-block" title="${preview.new_path}">${preview.new_path}</span>`
                        );
                    } else if (preview.error) {
                        previewCell.html(`<span class="text-danger fst-italic">${preview.error}</span>`);
                    }
                });
            }
        } catch (error) {
            console.error('Error updating book previews:', error);
        }
    }

    updateLivePreview() {
        // Debounce preview updates
        if (this.previewTimeout) {
            clearTimeout(this.previewTimeout);
        }

        this.previewTimeout = setTimeout(() => {
            this.generateLivePreview();
        }, 300);
    }

    async generateLivePreview() {
        const folderPattern = $('#folder-pattern').val();
        const filenamePattern = $('#filename-pattern').val();
        const previewDiv = $('#pattern-preview');

        if (!folderPattern && !filenamePattern) {
            previewDiv.html('<em class=\"text-muted\">Enter patterns to see preview...</em>');
            return;
        }

        try {
            // Get preview using the first book (don't send book_ids to use first reviewed book)
            const response = await $.post('/renamer/preview-pattern/', {
                folder_pattern: folderPattern,
                filename_pattern: filenamePattern,
                // Don't send book_ids at all - backend will fetch first reviewed book
                csrfmiddlewaretoken: $('[name=csrfmiddlewaretoken]').val(),
            });

            console.log('Live preview response:', response);

            if (response.success && response.previews && response.previews.length > 0) {
                const preview = response.previews[0];
                previewDiv.html(`
                    <strong>Book:</strong> ${preview.title || 'Unknown'} by ${preview.author || 'Unknown'}<br>
                    <strong>Folder:</strong> <span class="text-primary">${preview.target_folder || 'N/A'}</span><br>
                    <strong>Filename:</strong> <span class="text-success">${preview.target_filename || 'N/A'}</span><br>
                    <strong>Full Path:</strong> <code class="text-muted">[library]/${preview.full_target_path || 'N/A'}</code>
                `);
            } else {
                console.log('No previews in response:', response);
                previewDiv.html('<em class=\"text-warning\">No books available for preview</em>');
            }
        } catch (error) {
            console.error('Preview error:', error);
            previewDiv.html('<em class=\"text-danger\">Error generating preview</em>');
        }
    }

    showSaveTemplateDialog() {
        const folderPattern = $('#folder-pattern').val();
        const filenamePattern = $('#filename-pattern').val();

        if (!folderPattern && !filenamePattern) {
            this.showAlert('Please enter at least one pattern before saving.', 'warning');
            return;
        }

        const name = prompt('Enter a name for this template:', this.currentTemplate || '');
        if (!name) return;

        const description = prompt('Enter a description (optional):', '');

        this.saveTemplate(name, folderPattern, filenamePattern, description);
    }

    async saveTemplate(name, folderPattern, filenamePattern, description) {
        try {
            const response = await $.post('/renamer/save-template/', {
                name: name,
                folder_pattern: folderPattern,
                filename_pattern: filenamePattern,
                description: description || '',
                csrfmiddlewaretoken: $('[name=csrfmiddlewaretoken]').val(),
            });

            if (response.success) {
                this.showAlert(response.message, 'success');
                this.currentTemplate = name;
                await this.loadSavedTemplates();
                // Select the newly saved template
                $('#template-selector').val('user-' + name);
                $('#delete-template-btn').prop('disabled', false);
            } else {
                this.showAlert(response.error || 'Failed to save template', 'danger');
            }
        } catch (error) {
            console.error('Error saving template:', error);
            this.showAlert('Failed to save template', 'danger');
        }
    }

    async deleteTemplate() {
        if (!this.currentTemplate) return;

        if (!confirm(`Are you sure you want to delete the template "${this.currentTemplate}"?`)) {
            return;
        }

        try {
            const response = await $.post('/renamer/delete-template/', {
                name: this.currentTemplate,
                csrfmiddlewaretoken: $('[name=csrfmiddlewaretoken]').val(),
            });

            if (response.success) {
                this.showAlert(response.message, 'success');
                this.currentTemplate = null;
                $('#delete-template-btn').prop('disabled', true);
                await this.loadSavedTemplates();
                $('#template-selector').val('');
            } else {
                this.showAlert(response.error || 'Failed to delete template', 'danger');
            }
        } catch (error) {
            console.error('Error deleting template:', error);
            this.showAlert('Failed to delete template', 'danger');
        }
    }

    insertToken(event) {
        const token = $(event.target).data('token');
        const activeInput = document.activeElement;

        if (activeInput && (activeInput.id === 'folder-pattern' || activeInput.id === 'filename-pattern')) {
            const start = activeInput.selectionStart;
            const end = activeInput.selectionEnd;
            const currentValue = activeInput.value;

            const newValue = currentValue.substring(0, start) + token + currentValue.substring(end);
            activeInput.value = newValue;

            // Set cursor position after the inserted token
            const newPosition = start + token.length;
            activeInput.setSelectionRange(newPosition, newPosition);

            // Trigger validation
            this.validatePattern({ target: activeInput });
        } else {
            // No active input, show tooltip
            this.showTooltip(event.target, 'Click in a pattern field first, then click this token');
        }
    }

    loadExample(event) {
        const folderPattern = $(event.target).data('folder');
        const filenamePattern = $(event.target).data('filename');

        $('#folder-pattern').val(folderPattern);
        $('#filename-pattern').val(filenamePattern);

        // Trigger validation
        this.validatePattern({ target: $('#folder-pattern')[0] });
        this.validatePattern({ target: $('#filename-pattern')[0] });
    }

    validatePattern(event) {
        const input = $(event.target);
        const pattern = input.val();
        const patternType = input.attr('id').replace('-pattern', '');

        // Clear previous timeout
        if (this.validationTimeouts[patternType]) {
            clearTimeout(this.validationTimeouts[patternType]);
        }

        // Debounce validation
        this.validationTimeouts[patternType] = setTimeout(() => {
            this.performPatternValidation(pattern, patternType);
        }, 300);
    }

    async performPatternValidation(pattern, patternType) {
        if (!pattern.trim()) {
            this.updateValidationUI(patternType, false, [], null);
            return;
        }

        try {
            const response = await $.post('/renamer/validate-pattern/', {
                pattern: pattern,
                type: patternType,
                csrfmiddlewaretoken: $('[name=csrfmiddlewaretoken]').val(),
            });

            if (response.success) {
                this.updateValidationUI(patternType, response.valid, response.warnings, response.preview);
            }
        } catch (error) {
            console.error('Pattern validation error:', error);
            this.updateValidationUI(patternType, false, ['Validation error'], null);
        }
    }

    updateValidationUI(patternType, isValid, warnings, preview) {
        const validationDiv = $(`#${patternType}-pattern-validation`);
        validationDiv.empty();

        // Update validation state
        this.validationState[patternType] = isValid;

        if (isValid) {
            validationDiv.append('<div class="text-success"><i class="fas fa-check"></i> Valid pattern</div>');
            if (preview) {
                validationDiv.append(`<div class="text-muted"><small>Preview: ${preview}</small></div>`);
            }
        } else {
            validationDiv.append(
                '<div class="text-danger"><i class="fas fa-exclamation-triangle"></i> Invalid pattern</div>'
            );
        }

        if (warnings && warnings.length > 0) {
            warnings.forEach((warning) => {
                validationDiv.append(
                    `<div class="text-warning"><small><i class="fas fa-exclamation-circle"></i> ${warning}</small></div>`
                );
            });
        }

        // Update button states after validation
        this.updateButtonStates();
    }

    updateButtonStates() {
        const folderPattern = $('#folder-pattern').val();
        const filenamePattern = $('#filename-pattern').val();
        const selectedTemplate = $('#template-selector').val();

        // Check if both patterns are valid
        const bothPatternsValid = this.validationState.folder && this.validationState.filename;

        // Check if current pattern matches any saved template (user templates)
        const matchesSavedTemplate = this.savedTemplates.some(
            (template) => template.folder === folderPattern && template.filename === filenamePattern
        );

        // Check if current pattern matches any system template
        const matchesSystemTemplate = $('#template-selector optgroup[label="System Templates"] option')
            .toArray()
            .some((option) => {
                const $option = $(option);
                return $option.data('folder') === folderPattern && $option.data('filename') === filenamePattern;
            });

        const isDuplicate = matchesSavedTemplate || matchesSystemTemplate;

        // Save button: Enable only if both patterns valid, not empty, and not a duplicate
        const canSave = bothPatternsValid && folderPattern && filenamePattern && !isDuplicate;
        $('#save-template-btn').prop('disabled', !canSave);

        // Delete button: Enable only if a user template is selected
        const selectedOption = $('#template-selector option:selected');
        const isDeletable = selectedOption.data('deletable') === true && selectedTemplate;
        $('#delete-template-btn').prop('disabled', !isDeletable);
    }

    updateExecuteButton() {
        const folderValid = $('#folder-pattern-validation .text-success').length > 0;
        const filenameValid = $('#filename-pattern-validation .text-success').length > 0;
        const hasSelection = this.selectedBooks.size > 0;

        const canExecute = folderValid && filenameValid && hasSelection;
        $('#execute-btn').prop('disabled', !canExecute);
    }

    toggleAllBooks(event) {
        const isChecked = $(event.target).is(':checked');
        $('.book-checkbox').prop('checked', isChecked);

        if (isChecked) {
            $('.book-checkbox').each((_, checkbox) => {
                this.selectedBooks.add($(checkbox).val());
            });
        } else {
            this.selectedBooks.clear();
        }

        this.updateSelectionCount();
        this.updateExecuteButton();
    }

    toggleBook(event) {
        const bookId = $(event.target).val();
        const isChecked = $(event.target).is(':checked');

        if (isChecked) {
            this.selectedBooks.add(bookId);
        } else {
            this.selectedBooks.delete(bookId);
        }

        // Update "select all" checkbox
        const totalBooks = $('.book-checkbox').length;
        const selectedCount = this.selectedBooks.size;

        $('#select-all-checkbox').prop('indeterminate', selectedCount > 0 && selectedCount < totalBooks);
        $('#select-all-checkbox').prop('checked', selectedCount === totalBooks);

        this.updateSelectionCount();
        this.updateExecuteButton();
    }

    selectAllBooks() {
        $('#select-all-checkbox').prop('checked', true).trigger('change');
    }

    selectNoneBooks() {
        $('#select-all-checkbox').prop('checked', false).trigger('change');
    }

    updateSelectionCount() {
        $('#selection-count').text(`${this.selectedBooks.size} selected`);
    }

    async previewChanges() {
        if (this.selectedBooks.size === 0) {
            this.showAlert('Please select at least one book to preview.', 'warning');
            return;
        }

        const folderPattern = this.currentFolderPattern || '';
        const filenamePattern = this.currentFilenamePattern || '';

        if (!folderPattern || !filenamePattern) {
            this.showAlert('Please configure both folder and filename patterns.', 'warning');
            return;
        }

        this.showLoading();

        try {
            const response = await $.post('/renamer/preview-pattern/', {
                folder_pattern: folderPattern,
                filename_pattern: filenamePattern,
                book_ids: Array.from(this.selectedBooks),
                csrfmiddlewaretoken: $('[name=csrfmiddlewaretoken]').val(),
            });

            if (response.success) {
                this.displayPreviewResults(response);
            } else {
                this.showAlert(response.error || 'Preview generation failed', 'danger');
            }
        } catch (error) {
            console.error('Preview error:', error);
            this.showAlert('Failed to generate preview. Please try again.', 'danger');
        } finally {
            this.hideLoading();
        }
    }

    displayPreviewResults(response) {
        const previews = response.previews;
        let html = '<h6>Rename Preview</h6>';

        if (response.folder_warnings && response.folder_warnings.length > 0) {
            html +=
                '<div class="alert alert-warning">Folder pattern warnings: ' +
                response.folder_warnings.join(', ') +
                '</div>';
        }

        if (response.filename_warnings && response.filename_warnings.length > 0) {
            html +=
                '<div class="alert alert-warning">Filename pattern warnings: ' +
                response.filename_warnings.join(', ') +
                '</div>';
        }

        html += '<div class="table-responsive"><table class="table table-sm">';
        html += '<thead><tr><th>Title</th><th>Current Path</th><th>New Path</th></tr></thead>';
        html += '<tbody>';

        previews.forEach((preview) => {
            if (preview.error) {
                html += `<tr class="table-danger">
                    <td colspan="3">Book ID ${preview.book_id}: ${preview.error}</td>
                </tr>`;
            } else {
                html += `<tr>
                    <td><strong>${preview.title}</strong><br><small class="text-muted">${preview.author}</small></td>
                    <td><small class="font-monospace">${this.truncatePath(preview.current_path)}</small></td>
                    <td><small class="font-monospace text-primary">${this.truncatePath(preview.full_target_path)}</small></td>
                </tr>`;
            }
        });

        html += '</tbody></table></div>';

        if (response.total_books > response.preview_count) {
            html += `<div class="alert alert-info">Showing ${response.preview_count} of ${response.total_books} selected books.</div>`;
        }

        $('#results-title').text('Rename Preview');
        $('#results-content').html(html);
        $('#results-modal').modal('show');

        // Update table previews
        this.updateTablePreviews(previews);
    }

    updateTablePreviews(previews) {
        previews.forEach((preview) => {
            const row = $(`tr[data-book-id="${preview.book_id}"]`);
            const previewCell = row.find('.preview-path');

            if (preview.error) {
                previewCell.html(`<span class="text-danger">${preview.error}</span>`);
            } else if (preview.full_target_path) {
                previewCell.html(this.truncatePath(preview.full_target_path, 50));
                previewCell.removeClass('text-muted').addClass('text-primary');
            }
        });
    }

    async executeRename() {
        if (this.selectedBooks.size === 0) {
            this.showAlert('Please select at least one book to rename.', 'warning');
            return;
        }

        const folderPattern = $('#folder-pattern').val();
        const filenamePattern = $('#filename-pattern').val();
        const dryRun = $('#dry-run').is(':checked');
        const embedMetadata = $('#embed-metadata').is(':checked');

        if (!folderPattern || !filenamePattern) {
            this.showAlert('Please configure both folder and filename patterns.', 'warning');
            return;
        }

        // Check if we have EPUB files selected and embed_metadata is enabled
        if (embedMetadata && !dryRun) {
            const hasEpubs = await this.checkForEpubFiles();
            if (hasEpubs) {
                // Show EPUB preview for the first EPUB file
                const firstEpubId = await this.getFirstEpubFileId();
                if (firstEpubId) {
                    // Store the callback to proceed after preview confirmation
                    window.proceedWithRename = () =>
                        this.proceedWithActualRename(folderPattern, filenamePattern, dryRun, embedMetadata);
                    // Show EPUB preview modal
                    window.showEpubPreview(firstEpubId, embedMetadata);
                    return; // Wait for user confirmation
                }
            }
        }

        // If no EPUBs or dry run, proceed directly
        await this.proceedWithActualRename(folderPattern, filenamePattern, dryRun, embedMetadata);
    }

    async checkForEpubFiles() {
        // Check if any selected books are EPUB files
        for (const bookId of this.selectedBooks) {
            const row = $(`.book-checkbox[value="${bookId}"]`).closest('tr');
            const format = row.find('td').eq(3).text().trim().toLowerCase(); // Assuming format is in 4th column
            if (format === 'epub') {
                return true;
            }
        }
        return false;
    }

    async getFirstEpubFileId() {
        // Get the first EPUB file from selected books
        for (const bookId of this.selectedBooks) {
            const row = $(`.book-checkbox[value="${bookId}"]`).closest('tr');
            const format = row.find('td').eq(3).text().trim().toLowerCase();
            if (format === 'epub') {
                return bookId;
            }
        }
        return null;
    }

    async proceedWithActualRename(folderPattern, filenamePattern, dryRun, embedMetadata) {
        // Confirmation dialog for actual rename
        if (!dryRun) {
            if (
                !confirm(
                    `Are you sure you want to rename ${this.selectedBooks.size} books? This action cannot be easily undone.`
                )
            ) {
                return;
            }
        }

        this.showLoading();

        try {
            const response = await $.post('/renamer/execute-batch/', {
                folder_pattern: folderPattern,
                filename_pattern: filenamePattern,
                book_ids: Array.from(this.selectedBooks),
                dry_run: dryRun,
                embed_metadata: embedMetadata,
                csrfmiddlewaretoken: $('[name=csrfmiddlewaretoken]').val(),
            });

            if (response.success) {
                this.displayExecuteResults(response);

                // If actual execution, refresh the page to show updated paths
                if (!response.dry_run) {
                    setTimeout(() => {
                        window.location.reload();
                    }, 3000);
                }
            } else {
                this.showAlert(response.error || 'Rename operation failed', 'danger');
            }
        } catch (error) {
            console.error('Execute error:', error);
            this.showAlert('Failed to execute rename operation. Please try again.', 'danger');
        } finally {
            this.hideLoading();
        }
    }

    displayExecuteResults(response) {
        const summary = response.summary;
        const results = response.results;

        let html = `<h6>Rename ${response.dry_run ? 'Preview' : 'Results'}</h6>`;

        html += '<div class="row mb-3">';
        html += `<div class="col-md-3"><div class="card text-center"><div class="card-body">
            <h5 class="card-title">${summary.total_operations}</h5>
            <p class="card-text">Total Operations</p>
        </div></div></div>`;
        html += `<div class="col-md-3"><div class="card text-center"><div class="card-body">
            <h5 class="card-title">${summary.main_files}</h5>
            <p class="card-text">Main Files</p>
        </div></div></div>`;
        html += `<div class="col-md-3"><div class="card text-center"><div class="card-body">
            <h5 class="card-title">${summary.companion_files}</h5>
            <p class="card-text">Companion Files</p>
        </div></div></div>`;
        html += `<div class="col-md-3"><div class="card text-center"><div class="card-body">
            <h5 class="card-title">${summary.books_affected}</h5>
            <p class="card-text">Books Affected</p>
        </div></div></div>`;
        html += '</div>';

        if (response.dry_run) {
            html += '<div class="alert alert-info">This was a dry run - no files were actually moved.</div>';
            if (response.operations && response.operations.length > 0) {
                html += this.formatOperationsList(response.operations);
            }
        } else if (results) {
            if (results.successful > 0) {
                html += `<div class="alert alert-success">${results.successful} operations completed successfully.</div>`;
            }
            if (results.failed > 0) {
                html += `<div class="alert alert-danger">${results.failed} operations failed.</div>`;
                if (results.errors && results.errors.length > 0) {
                    html += '<ul>';
                    results.errors.forEach((error) => {
                        html += `<li>${error}</li>`;
                    });
                    html += '</ul>';
                }
            }
        }

        $('#results-title').text(`Rename ${response.dry_run ? 'Preview' : 'Results'}`);
        $('#results-content').html(html);
        $('#results-modal').modal('show');
    }

    formatOperationsList(operations) {
        let html = '<div class="table-responsive"><table class="table table-sm">';
        html += '<thead><tr><th>Type</th><th>Source</th><th>Target</th><th>Warnings</th></tr></thead>';
        html += '<tbody>';

        operations.forEach((op) => {
            const warningClass = op.warnings && op.warnings.length > 0 ? 'table-warning' : '';
            html += `<tr class="${warningClass}">
                <td><span class="badge bg-secondary">${op.operation_type.replace('_', ' ')}</span></td>
                <td><small class="font-monospace">${this.truncatePath(op.source_path)}</small></td>
                <td><small class="font-monospace text-primary">${this.truncatePath(op.target_path)}</small></td>
                <td>`;

            if (op.warnings && op.warnings.length > 0) {
                html += op.warnings.map((w) => `<small class="text-warning">${w}</small>`).join('<br>');
            }

            html += '</td></tr>';
        });

        html += '</tbody></table></div>';
        return html;
    }

    applyFilters() {
        const searchTerm = $('#search-filter').val();
        const contentTypeFilter = $('#content-type-filter').val();
        const formatFilter = $('#format-filter').val();
        const languageFilter = $('#language-filter').val();

        console.log('Applying filters:', {
            search: searchTerm,
            content_type: contentTypeFilter,
            file_format: formatFilter,
            language: languageFilter,
        });

        // Build URL with filters, preserving current page URL structure
        const url = new URL(window.location.href);
        const params = new URLSearchParams();

        // Add filters to params
        if (searchTerm) params.set('search', searchTerm);
        if (contentTypeFilter) params.set('content_type', contentTypeFilter);
        if (formatFilter) params.set('file_format', formatFilter);
        if (languageFilter) params.set('language', languageFilter);

        // Preserve scroll position before reload
        sessionStorage.setItem('filterScrollPosition', window.scrollY);

        const finalUrl = url.pathname + '?' + params.toString();
        console.log('Navigating to:', finalUrl);

        // Navigate with new filters
        window.location.href = finalUrl;
    }

    restoreScrollPosition() {
        const scrollPos = sessionStorage.getItem('filterScrollPosition');
        if (scrollPos) {
            window.scrollTo(0, parseInt(scrollPos));
            sessionStorage.removeItem('filterScrollPosition');
        }
    }

    truncatePath(path, maxLength = 60) {
        if (!path) return '';
        return path.length > maxLength ? '...' + path.slice(-(maxLength - 3)) : path;
    }

    showLoading() {
        $('#loading-overlay').removeClass('d-none');
    }

    hideLoading() {
        $('#loading-overlay').addClass('d-none');
    }

    showAlert(message, type = 'info') {
        const alertHtml = `
            <div class="alert alert-${type} alert-dismissible fade show" role="alert">
                ${message}
                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
            </div>
        `;

        // Insert at top of content area
        $('.container-fluid').prepend(alertHtml);

        // Auto-dismiss after 5 seconds
        setTimeout(() => {
            $('.alert').fadeOut();
        }, 5000);
    }

    showTooltip(element, message) {
        // Simple tooltip implementation
        const tooltip = $(`<div class="tooltip bs-tooltip-top show" role="tooltip">
            <div class="tooltip-inner">${message}</div>
        </div>`);

        $('body').append(tooltip);

        const rect = element.getBoundingClientRect();
        tooltip.css({
            position: 'fixed',
            top: rect.top - tooltip.outerHeight() - 5,
            left: rect.left + rect.width / 2 - tooltip.outerWidth() / 2,
            zIndex: 1070,
        });

        setTimeout(() => {
            tooltip.fadeOut(() => tooltip.remove());
        }, 2000);
    }
}

// Initialize when document is ready
$(document).ready(function () {
    // Add CSRF token to all AJAX requests
    $.ajaxSetup({
        beforeSend: function (xhr, settings) {
            if (!/^(GET|HEAD|OPTIONS|TRACE)$/i.test(settings.type) && !this.crossDomain) {
                xhr.setRequestHeader('X-CSRFToken', $('[name=csrfmiddlewaretoken]').val());
            }
        },
    });

    // Initialize the renamer
    window.ebookRenamer = new EbookRenamer();
});
