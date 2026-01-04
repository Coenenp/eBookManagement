/**
 * book-metadata-init.js
 * Initialization script for book metadata form
 * Extracted from book_metadata.html inline script
 */

/**
 * Initialize metadata form with Django template data
 * @param {Object} finalMetadata - Final metadata object from Django
 * @param {Array} currentGenres - Current genres array
 * @param {Array} languageChoices - Language choices array
 * @param {string} csrfToken - CSRF token for form submission
 * @param {number} bookId - Book ID
 */
function initializeMetadataForm(finalMetadata, currentGenres, languageChoices, csrfToken, bookId) {
    // Initialize the main metadata form handler
    window.metadataHandler = new MetadataFormHandler(finalMetadata, currentGenres, languageChoices, csrfToken, bookId);

    // Initialize ISBN lookup functionality
    window.isbnLookup = new ISBNLookup(csrfToken);
}

// Export for use in template
window.initializeMetadataForm = initializeMetadataForm;
