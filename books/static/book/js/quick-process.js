/**
 * quick-process.js
 * Handles metadata selection and preview functionality for quick process
 * Extracted from quick_process.html inline script
 */

/**
 * Select metadata value and update preview
 * @param {string} fieldName - Name of the field to update
 * @param {string} value - Value to set
 * @param {HTMLElement} element - The clicked element for visual feedback
 */
function selectMetadata(fieldName, value, element) {
    // Update the input field
    document.getElementById(fieldName).value = value;

    // Visual feedback
    if (element) {
        const parent = element.parentElement;
        const siblings = parent.querySelectorAll('.metadata-option');
        siblings.forEach((s) => s.classList.remove('selected'));
        element.classList.add('selected');
    }

    // Update preview
    updatePreview();
}

/**
 * Toggle genre selection
 * @param {string} genreName - Name of the genre
 * @param {HTMLElement} element - The clicked element
 */
function toggleGenre(genreName, element) {
    // Toggle visual selection
    element.classList.toggle('selected');

    // Get all selected genres
    const parent = element.parentElement;
    const selectedElements = parent.querySelectorAll('.metadata-option.selected');
    const selectedGenres = Array.from(selectedElements).map((el) => {
        return el.querySelector('span').textContent;
    });

    // Update the genres input field
    document.getElementById('genres').value = selectedGenres.join(', ');
}

/**
 * Toggle cover selection
 * @param {string} url - Cover URL
 * @param {HTMLElement} element - The clicked element
 */
function toggleCover(url, element) {
    const checkbox = element.querySelector('input[type="checkbox"]');
    checkbox.checked = !checkbox.checked;

    if (checkbox.checked) {
        element.classList.add('selected');
    } else {
        element.classList.remove('selected');
    }
}

/**
 * Update preview of the rename pattern
 */
function updatePreview() {
    const bookId = document.querySelector('input[name="book_id"]').value;
    const folderPattern = document.getElementById('folder_pattern').value;
    const filenamePattern = document.getElementById('filename_pattern').value;

    if (!folderPattern || !filenamePattern) {
        return;
    }

    // Make AJAX request to get preview
    fetch(
        `/quick-process/preview/?book_id=${bookId}&folder_pattern=${encodeURIComponent(folderPattern)}&filename_pattern=${encodeURIComponent(filenamePattern)}`
    )
        .then((response) => response.json())
        .then((data) => {
            if (data.error) {
                document.getElementById('preview-path').innerHTML = `<span class="text-danger">${data.error}</span>`;
            } else {
                document.getElementById('preview-path').textContent = data.preview;
            }
        })
        .catch((error) => {
            console.error('Error:', error);
            document.getElementById('preview-path').innerHTML =
                '<span class="text-danger">Error generating preview</span>';
        });
}

/**
 * Initialize quick process functionality
 */
function initializeQuickProcess() {
    updatePreview();

    // Auto-select first option for each metadata field if nothing is selected
    const metadataContainers = document.querySelectorAll('.metadata-option');
    const fieldGroups = {};

    metadataContainers.forEach((option) => {
        const parent = option.parentElement;
        if (!fieldGroups[parent]) {
            fieldGroups[parent] = [];
        }
        fieldGroups[parent].push(option);
    });

    // If final metadata fields are empty, select the first (highest confidence) option
    Object.values(fieldGroups).forEach((group) => {
        if (group.length > 0) {
            const firstOption = group[0];
            // Check if corresponding input is empty
            // This would require matching the field, but for simplicity we'll skip auto-selection
        }
    });
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', initializeQuickProcess);

// Export functions for template use
window.selectMetadata = selectMetadata;
window.toggleGenre = toggleGenre;
window.toggleCover = toggleCover;
window.updatePreview = updatePreview;
