/**
 * Metadata Utilities - Specialized functionality for metadata management
 * Uses shared utilities from shared-utils.js to avoid redundancy
 */

/**
 * AJAX utilities for metadata operations
 */
class MetadataAjax {
    static async updateBookStatus(bookId, statusData) {
        const url = `/books/${bookId}/status/`;
        return await EbookLibrary.Ajax.makeRequest(url, {
            method: 'POST',
            body: JSON.stringify(statusData)
        });
    }

    static async manageCoverAction(bookId, actionData) {
        const url = `/books/${bookId}/cover-action/`;
        return await EbookLibrary.Ajax.makeRequest(url, {
            method: 'POST',
            body: JSON.stringify(actionData)
        });
    }

    static async getMetadataConflicts(bookId) {
        const url = `/books/${bookId}/conflicts/`;
        return await EbookLibrary.Ajax.makeRequest(url);
    }

    static async removeMetadata(bookId, metadataData) {
        const url = `/books/${bookId}/remove-metadata/`;
        return await EbookLibrary.Ajax.makeRequest(url, {
            method: 'POST',
            body: JSON.stringify(metadataData)
        });
    }
}

/**
 * Form validation utilities specific to metadata
 * Uses backend validation patterns for consistency
 */
class MetadataValidators {
    static validateISBN(isbn) {
        try {
            // Use the shared validation pattern from the backend
            if (!isbn) return { valid: true, value: '' };
            
            const cleanISBN = isbn.replace(/[-\s]/g, '');
            if (cleanISBN.length !== 10 && cleanISBN.length !== 13) {
                return { valid: false, error: 'ISBN must be 10 or 13 digits long.' };
            }
            
            if (!/^(\d{10}|\d{13}|[\dX]{10})$/i.test(cleanISBN)) {
                return { valid: false, error: 'ISBN must contain only digits (and X for ISBN-10).' };
            }
            
            return { valid: true, value: isbn.trim() };
        } catch (error) {
            return { valid: false, error: 'Invalid ISBN format.' };
        }
    }

    static validateYear(year) {
        try {
            if (!year) return { valid: true, value: null };
            
            const yearInt = parseInt(year);
            const currentYear = new Date().getFullYear();
            
            if (yearInt < 1000 || yearInt > currentYear + 1) {
                return { 
                    valid: false, 
                    error: `Year must be between 1000 and ${currentYear + 1}.` 
                };
            }
            
            return { valid: true, value: yearInt };
        } catch (error) {
            return { valid: false, error: 'Year must be a valid number.' };
        }
    }

    static sanitizeText(text) {
        if (!text) return '';
        return text.trim()
                  .replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, '')
                  .replace(/[<>]/g, '');
    }
}

/**
 * UI utilities specific to metadata management
 */
class MetadataUI {
    static updateConfidenceBadge(element, confidence) {
        const badge = element.querySelector('.confidence-badge');
        if (badge) {
            badge.className = `badge ${this.getConfidenceBadgeClass(confidence)}`;
            badge.textContent = `★ ${confidence.toFixed(2)}`;
        }
    }

    static getConfidenceBadgeClass(confidence) {
        if (confidence >= 0.8) return 'bg-success';
        if (confidence >= 0.5) return 'bg-warning text-dark';
        return 'bg-danger';
    }
}

/**
 * Keyboard shortcuts specific to metadata editing
 */
let MetadataShortcuts;
if (
    typeof EbookLibrary !== 'undefined' &&
    EbookLibrary.KeyboardShortcuts &&
    typeof EbookLibrary.KeyboardShortcuts.prototype === 'object'
) {
    MetadataShortcuts = class extends EbookLibrary.KeyboardShortcuts {
        constructor() {
            const metadataShortcuts = {
                'ctrl+s': () => this.saveMetadata(),
                'ctrl+shift+r': () => this.refreshMetadata(),
                'escape': () => this.cancelEdit()
            };
            super(metadataShortcuts);
        }

        saveMetadata() {
            const saveBtn = document.querySelector('[data-action="save-metadata"]');
            if (saveBtn && !saveBtn.disabled) saveBtn.click();
        }

        refreshMetadata() {
            const refreshBtn = document.querySelector('[data-action="refresh-metadata"]');
            if (refreshBtn && !refreshBtn.disabled) refreshBtn.click();
        }

        cancelEdit() {
            const cancelBtn = document.querySelector('[data-action="cancel-edit"]');
            if (cancelBtn) cancelBtn.click();
        }
    };
} else {
    MetadataShortcuts = class {
        constructor() {
            // No keyboard shortcuts available
        }
    };
}

// Export for use in other scripts
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        MetadataAjax,
        MetadataValidators,
        MetadataUI,
        MetadataShortcuts
    };
} else {
    window.MetadataUtils = {
        MetadataAjax,
        MetadataValidators,
        MetadataUI,
        MetadataShortcuts
    };
}