/**
 * Metadata & Processing JavaScript
 * Merged functionality from book_metadata.html and quick_process.html
 */

$(document).ready(function () {
    // Cover selection functionality
    initializeCoverSelection();

    // Rename preview functionality
    initializeRenamePreview();

    // Duplicate selection functionality
    initializeDuplicateSelection();

    // Form submission handling
    initializeFormSubmission();

    // Load default template if available
    loadDefaultTemplate();
});

/**
 * Load default template from window.defaultTemplateKey
 */
function loadDefaultTemplate() {
    const select = $('#pattern_preset');
    if (!select.length || !window.defaultTemplateKey) {
        return;
    }

    // Try to find option by value matching the template key
    const options = select.find('option');
    let foundIndex = -1;

    options.each(function (index) {
        const $option = $(this);
        const optionValue = $option.val();

        // For system templates, the template key might be "system-comprehensive"
        // and we need to match it to the right index
        // Since rename_templates has custom templates first, then system templates,
        // we need to match by comparing the data attributes
        if (optionValue !== '') {
            const folderPattern = $option.attr('data-folder');
            const filenamePattern = $option.attr('data-filename');

            // Get the current input values which should match the default template
            const currentFolder = $('#folder_pattern').val();
            const currentFilename = $('#filename_pattern').val();

            if (folderPattern === currentFolder && filenamePattern === currentFilename) {
                foundIndex = index;
                return false; // Break the loop
            }
        }
    });

    if (foundIndex >= 0) {
        select.prop('selectedIndex', foundIndex);
    }
}

/**
 * Cover Selection Grid - Enhanced with Radio + Checkbox
 */
function initializeCoverSelection() {
    // Update cover selection visual feedback when radio button changes
    window.updateCoverSelection = function (radioElement) {
        // Remove selected-final class from all cover options
        document.querySelectorAll('.cover-option').forEach((option) => {
            option.classList.remove('selected-final');
        });

        // Add selected-final class to the selected cover
        const selectedCover = radioElement.closest('.cover-option-wrapper').querySelector('.cover-option');
        if (selectedCover) {
            selectedCover.classList.add('selected-final');
        }
    };

    // Select all download checkboxes
    window.selectAllDownloads = function () {
        const checkboxes = document.querySelectorAll('.cover-download-checkbox');
        checkboxes.forEach((checkbox) => {
            checkbox.checked = true;
        });
        updateDownloadButton();
    };

    // Deselect all download checkboxes
    window.deselectAllDownloads = function () {
        const checkboxes = document.querySelectorAll('.cover-download-checkbox');
        checkboxes.forEach((checkbox) => {
            checkbox.checked = false;
        });
        updateDownloadButton();
    };

    // Update download button state
    function updateDownloadButton() {
        const checkboxes = document.querySelectorAll('.cover-download-checkbox:checked');
        const downloadBtn = document.querySelector('button[onclick="downloadSelectedCovers()"]');

        if (downloadBtn) {
            if (checkboxes.length > 0) {
                downloadBtn.disabled = false;
                downloadBtn.innerHTML = `<i class="fas fa-download me-1"></i>Download Selected (${checkboxes.length})`;
            } else {
                downloadBtn.disabled = true;
                downloadBtn.innerHTML = '<i class="fas fa-download me-1"></i>Download Selected Covers';
            }
        }
    }

    // Download selected covers
    window.downloadSelectedCovers = function () {
        const checkboxes = document.querySelectorAll('.cover-download-checkbox:checked');
        const coverIds = Array.from(checkboxes).map((cb) => cb.value);

        if (coverIds.length === 0) {
            alert('Please select at least one cover to download.');
            return;
        }

        // Submit form with download action
        const form = document.getElementById('metadataForm');
        if (form) {
            // Add hidden input for download action
            const actionInput = document.createElement('input');
            actionInput.type = 'hidden';
            actionInput.name = 'action';
            actionInput.value = 'download_covers';
            form.appendChild(actionInput);

            form.submit();
        }
    };

    // Initialize: highlight currently selected final cover
    const selectedRadio = document.querySelector('.cover-final-radio:checked');
    if (selectedRadio) {
        updateCoverSelection(selectedRadio);
    }

    // Add change listeners to download checkboxes
    document.querySelectorAll('.cover-download-checkbox').forEach((checkbox) => {
        checkbox.addEventListener('change', updateDownloadButton);
    });

    // Initial button state
    updateDownloadButton();
}

/**
 * Rename Preview
 */
function initializeRenamePreview() {
    const folderInput = document.getElementById('folder_pattern');
    const filenameInput = document.getElementById('filename_pattern');
    const previewElement = document.getElementById('preview-path-text');

    if (!folderInput || !filenameInput || !previewElement) {
        return;
    }

    // Update preview on input change
    function updatePreview() {
        const bookId = document.querySelector('[name="book_id"]')?.value;
        const folderPattern = folderInput.value;
        const filenamePattern = filenameInput.value;

        if (!bookId || (!folderPattern && !filenamePattern)) {
            previewElement.textContent = 'Enter patterns to preview...';
            return;
        }

        // Make AJAX request to get preview
        $.ajax({
            url: `/ajax/book/${bookId}/rename-preview/`,
            method: 'GET',
            data: {
                folder_pattern: folderPattern,
                filename_pattern: filenamePattern,
            },
            success: function (response) {
                if (response.success && response.preview_path) {
                    previewElement.textContent = response.preview_path;
                } else if (response.error) {
                    previewElement.textContent = 'Error: ' + response.error;
                } else {
                    previewElement.textContent = 'Error generating preview';
                }
            },
            error: function (xhr) {
                const response = xhr.responseJSON;
                if (response && response.error) {
                    previewElement.textContent = 'Error: ' + response.error;
                } else {
                    previewElement.textContent = 'Error generating preview';
                }
            },
        });
    }

    // Expose as global function for inline calls
    window.updateRenamePreview = updatePreview;

    // Apply pattern preset - MUST be global for onclick handler
    window.applyPatternPreset = function () {
        const select = document.getElementById('pattern_preset');
        if (!select) {
            console.error('Pattern preset select not found');
            return;
        }

        const selectedOption = select.options[select.selectedIndex];

        if (selectedOption && selectedOption.value !== '') {
            const folderPattern = selectedOption.getAttribute('data-folder');
            const filenamePattern = selectedOption.getAttribute('data-filename');

            console.log('Applying template:', { folderPattern, filenamePattern });

            // Get input elements directly (don't rely on closure)
            const folderInputElem = document.getElementById('folder_pattern');
            const filenameInputElem = document.getElementById('filename_pattern');

            if (folderInputElem && filenameInputElem) {
                folderInputElem.value = folderPattern || '';
                filenameInputElem.value = filenamePattern || '';

                // Trigger the update
                updatePreview();
            } else {
                console.error('Input elements not found');
            }
        }
    };

    // Attach event listeners
    folderInput.addEventListener('input', updatePreview);
    filenameInput.addEventListener('input', updatePreview);

    // Preview is already generated server-side, no need for initial update
}

/**
 * Duplicate Selection
 */
function initializeDuplicateSelection() {
    // Toggle duplicate selection
    window.toggleDuplicateSelection = function (duplicateId) {
        const checkbox = document.getElementById('dup_' + duplicateId);
        const row = checkbox.closest('tr');

        if (checkbox.checked) {
            row.classList.add('table-warning');
        } else {
            row.classList.remove('table-warning');
        }
    };

    // Select all duplicates
    window.selectAllDuplicates = function () {
        const checkboxes = document.querySelectorAll('[id^="dup_"]');
        checkboxes.forEach((checkbox) => {
            checkbox.checked = true;
            const row = checkbox.closest('tr');
            row.classList.add('table-warning');
        });
    };

    // Deselect all duplicates
    window.deselectAllDuplicates = function () {
        const checkboxes = document.querySelectorAll('[id^="dup_"]');
        checkboxes.forEach((checkbox) => {
            checkbox.checked = false;
            const row = checkbox.closest('tr');
            row.classList.remove('table-warning');
        });
    };
}

/**
 * Form Submission Handling
 */
function initializeFormSubmission() {
    const form = document.getElementById('metadataForm');

    if (!form) {
        return;
    }

    // Prevent double submission
    let isSubmitting = false;

    form.addEventListener('submit', function (e) {
        if (isSubmitting) {
            e.preventDefault();
            return false;
        }

        // Validate required fields based on action
        const action = e.submitter?.value || 'save';

        if (action === 'save' || action === 'save_next') {
            const title = document.querySelector('[name="final_title"]');

            if (title && !title.value.trim()) {
                e.preventDefault();
                alert('Title is required and cannot be empty.');
                title.focus();
                return false;
            }
        }

        // Set submitting flag
        isSubmitting = true;

        // Show loading indicator on submit button
        const submitBtn = e.submitter;
        if (submitBtn) {
            const originalText = submitBtn.innerHTML;
            submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i> Processing...';
            submitBtn.disabled = true;

            // Reset after timeout (in case submission fails)
            setTimeout(function () {
                submitBtn.innerHTML = originalText;
                submitBtn.disabled = false;
                isSubmitting = false;
            }, 30000);
        }
    });
}

/**
 * Utility: Show/Hide Manual Entry Fields
 */
function toggleManualEntry(fieldName, show) {
    const manualDiv = document.getElementById(fieldName + '_manual_entry');
    const selectElement = document.getElementById(fieldName + '_select');

    if (manualDiv) {
        manualDiv.style.display = show ? 'block' : 'none';
    }

    if (selectElement && show) {
        selectElement.value = '__manual__';
    }
}

/**
 * Utility: Confidence Score Badge Color
 */
function getConfidenceBadgeClass(confidence) {
    if (confidence >= 0.8) return 'bg-success';
    if (confidence >= 0.6) return 'bg-warning';
    return 'bg-danger';
}

/**
 * Multi-Cover Selector Functions (Feature 2)
 */
let selectedInternalCoverPath = null;

/**
 * Open the multi-cover selector modal
 */
function openMultiCoverSelector(bookId) {
    const modal = new bootstrap.Modal(document.getElementById('multiCoverSelectorModal'));
    const loadingDiv = document.getElementById('multiCoverLoading');
    const errorDiv = document.getElementById('multiCoverError');
    const gridDiv = document.getElementById('multiCoverGrid');

    // Reset state
    loadingDiv.classList.remove('d-none');
    errorDiv.classList.add('d-none');
    gridDiv.classList.add('d-none');
    selectedInternalCoverPath = null;
    document.getElementById('confirmCoverSelection').disabled = true;

    modal.show();

    // Fetch internal covers via AJAX
    fetch(`/books/ajax/book/${bookId}/list_internal_covers/`, {
        method: 'GET',
        headers: {
            'X-CSRFToken': getCsrfToken(),
        },
    })
        .then((response) => response.json())
        .then((data) => {
            loadingDiv.classList.add('d-none');

            if (!data.success) {
                showMultiCoverError(data.error || 'Failed to load covers');
                return;
            }

            if (!data.covers || data.covers.length === 0) {
                showMultiCoverError('No images found in EPUB');
                return;
            }

            // Populate grid
            populateMultiCoverGrid(data.covers, data.current_cover);
            gridDiv.classList.remove('d-none');

            // Update count
            document.getElementById('multiCoverCount').textContent = data.total_count;
        })
        .catch((error) => {
            loadingDiv.classList.add('d-none');
            showMultiCoverError('Network error: ' + error.message);
        });
}

/**
 * Show error message in modal
 */
function showMultiCoverError(message) {
    const errorDiv = document.getElementById('multiCoverError');
    document.getElementById('multiCoverErrorMessage').textContent = message;
    errorDiv.classList.remove('d-none');
}

/**
 * Populate the cover grid with covers data
 */
function populateMultiCoverGrid(covers, currentCoverPath) {
    const container = document.getElementById('multiCoverContainer');
    const template = document.getElementById('coverCardTemplate');

    // Clear existing content
    container.innerHTML = '';

    covers.forEach((cover, index) => {
        // Clone template
        const clone = template.content.cloneNode(true);
        const wrapper = clone.querySelector('.cover-card-wrapper');
        const card = clone.querySelector('.cover-card');
        const img = clone.querySelector('.cover-preview');
        const radio = clone.querySelector('.cover-radio');

        // Set data attributes
        wrapper.dataset.coverIndex = index;
        wrapper.dataset.minDimension = Math.min(cover.width, cover.height);
        card.dataset.internalPath = cover.internal_path;

        // Set image
        if (cover.preview_url) {
            img.src = cover.preview_url;
        } else {
            img.src = '/static/images/placeholder-cover.png';
        }

        // Set radio button
        radio.value = cover.internal_path;
        radio.id = `cover-radio-${index}`;

        // Show badges
        if (cover.is_opf_cover) {
            clone.querySelector('.opf-badge').classList.remove('d-none');
        }
        if (cover.is_current) {
            clone.querySelector('.current-badge').classList.remove('d-none');
            radio.checked = true;
            card.classList.add('selected');
            selectedInternalCoverPath = cover.internal_path;
            document.getElementById('confirmCoverSelection').disabled = false;
        }

        // Set metadata
        clone.querySelector('.cover-filename').textContent = cover.display_name;
        clone.querySelector('.card-title').title = cover.internal_path;
        clone.querySelector('.cover-dimensions').textContent = `${cover.width}×${cover.height}`;
        clone.querySelector('.cover-format').textContent = cover.format;
        clone.querySelector('.cover-size').textContent = formatFileSize(cover.file_size);

        // Calculate quality score
        const qualityInfo = calculateCoverQuality(cover.width, cover.height);
        const qualitySpan = clone.querySelector('.cover-quality');
        qualitySpan.textContent = qualityInfo.label;
        qualitySpan.classList.add(qualityInfo.class);

        container.appendChild(clone);
    });

    // Add event listeners
    initializeMultiCoverSelection();
}

/**
 * Calculate cover quality based on dimensions
 */
function calculateCoverQuality(width, height) {
    const minDim = Math.min(width, height);
    const maxDim = Math.max(width, height);

    if (minDim >= 1200) {
        return { label: 'Excellent', class: 'quality-excellent' };
    } else if (minDim >= 800) {
        return { label: 'Good', class: 'quality-good' };
    } else if (minDim >= 500) {
        return { label: 'Fair', class: 'quality-fair' };
    } else {
        return { label: 'Poor', class: 'quality-poor' };
    }
}

/**
 * Format file size in human-readable format
 */
function formatFileSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

/**
 * Initialize multi-cover selection event handlers
 */
function initializeMultiCoverSelection() {
    // Card click to select
    document.querySelectorAll('.cover-card').forEach((card) => {
        card.addEventListener('click', function (e) {
            if (e.target.classList.contains('btn')) return; // Skip button clicks

            const radio = this.querySelector('.cover-radio');
            radio.checked = true;
            handleCoverSelection(radio);
        });
    });

    // Radio change
    document.querySelectorAll('.cover-radio').forEach((radio) => {
        radio.addEventListener('change', function () {
            handleCoverSelection(this);
        });
    });

    // Filter checkbox
    document.getElementById('showOnlyLargeImages').addEventListener('change', function () {
        const showOnlyLarge = this.checked;
        document.querySelectorAll('.cover-card-wrapper').forEach((wrapper) => {
            const minDim = parseInt(wrapper.dataset.minDimension);
            if (showOnlyLarge && minDim < 800) {
                wrapper.classList.add('filtered-out');
            } else {
                wrapper.classList.remove('filtered-out');
            }
        });
    });

    // Confirm selection
    document.getElementById('confirmCoverSelection').addEventListener('click', function () {
        if (selectedInternalCoverPath) {
            selectInternalCover(selectedInternalCoverPath);
        }
    });
}

/**
 * Handle cover selection change
 */
function handleCoverSelection(radio) {
    // Remove selected class from all cards
    document.querySelectorAll('.cover-card').forEach((c) => c.classList.remove('selected'));

    // Add selected class to this card
    const card = radio.closest('.cover-card');
    card.classList.add('selected');

    // Store selection
    selectedInternalCoverPath = radio.value;

    // Enable confirm button
    document.getElementById('confirmCoverSelection').disabled = false;
}

/**
 * Select an internal cover and update the unified cover selection
 */
function selectInternalCover(internalPath) {
    // Update the final_cover_path hidden input or radio selection
    // This integrates with the existing unified cover selection system

    // Find if there's already an internal cover radio button
    const internalCoverRadio = document.querySelector(`input[name="final_cover_path"][value="${internalPath}"]`);

    if (internalCoverRadio) {
        internalCoverRadio.checked = true;
        updateCoverSelection(); // Call existing function
    } else {
        // If not found in unified grid, set it directly
        const hiddenInput = document.getElementById('final_cover_path_input');
        if (hiddenInput) {
            hiddenInput.value = internalPath;
        }
    }

    // Show success message
    showToast('success', 'Internal cover selected: ' + internalPath.split('/').pop());

    // Close modal
    bootstrap.Modal.getInstance(document.getElementById('multiCoverSelectorModal')).hide();
}

/**
 * Get CSRF token
 */
function getCsrfToken() {
    return document.querySelector('[name=csrfmiddlewaretoken]').value;
}

/**
 * Show toast notification
 */
function showToast(type, message) {
    // Use existing toast system or create simple alert
    const alertClass = type === 'success' ? 'alert-success' : 'alert-danger';
    const alert = document.createElement('div');
    alert.className = `alert ${alertClass} alert-dismissible fade show position-fixed top-0 end-0 m-3`;
    alert.style.zIndex = '9999';
    alert.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    document.body.appendChild(alert);

    setTimeout(() => {
        alert.remove();
    }, 3000);
}
