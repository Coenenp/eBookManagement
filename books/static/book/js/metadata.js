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
});

/**
 * Cover Selection Grid
 */
function initializeCoverSelection() {
    // Toggle individual cover selection
    window.toggleCoverSelection = function (coverId) {
        const checkbox = document.getElementById('cover_' + coverId);
        const card = checkbox.closest('.card');

        if (checkbox.checked) {
            card.classList.add('border-primary', 'bg-light');
        } else {
            card.classList.remove('border-primary', 'bg-light');
        }

        updateCoverDownloadButton();
    };

    // Select all covers
    window.selectAllCovers = function () {
        const checkboxes = document.querySelectorAll('[id^="cover_"]');
        checkboxes.forEach((checkbox) => {
            checkbox.checked = true;
            const card = checkbox.closest('.card');
            card.classList.add('border-primary', 'bg-light');
        });
        updateCoverDownloadButton();
    };

    // Deselect all covers
    window.deselectAllCovers = function () {
        const checkboxes = document.querySelectorAll('[id^="cover_"]');
        checkboxes.forEach((checkbox) => {
            checkbox.checked = false;
            const card = checkbox.closest('.card');
            card.classList.remove('border-primary', 'bg-light');
        });
        updateCoverDownloadButton();
    };

    // Update download button state
    function updateCoverDownloadButton() {
        const checkboxes = document.querySelectorAll('[id^="cover_"]:checked');
        const downloadBtn = document.getElementById('downloadCoversBtn');

        if (downloadBtn) {
            if (checkboxes.length > 0) {
                downloadBtn.disabled = false;
                downloadBtn.textContent = `Download Selected (${checkboxes.length})`;
            } else {
                downloadBtn.disabled = true;
                downloadBtn.textContent = 'Download Selected';
            }
        }
    }

    // Download selected covers
    window.downloadSelectedCovers = function () {
        const checkboxes = document.querySelectorAll('[id^="cover_"]:checked');
        const coverUrls = Array.from(checkboxes).map((cb) => cb.value);

        if (coverUrls.length === 0) {
            alert('Please select at least one cover to download.');
            return;
        }

        // Add hidden inputs to form for selected covers
        const form = document.getElementById('metadataForm');
        coverUrls.forEach((url) => {
            const input = document.createElement('input');
            input.type = 'hidden';
            input.name = 'selected_covers';
            input.value = url;
            form.appendChild(input);
        });

        // Submit form with download action
        form.submit();
    };
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
