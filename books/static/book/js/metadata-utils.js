/**
 * Metadata Utilities - External JavaScript file
 * Save as: static/js/metadata-utils.js
 * 
 * Shared utilities for book metadata management
 */

/**
 * AJAX utilities for metadata operations
 */
class MetadataAjax {
    static async updateBookStatus(bookId, statusData) {
        const url = `/books/${bookId}/status/`;
        const response = await fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': this.getCSRFToken()
            },
            body: JSON.stringify(statusData)
        });
        return response.json();
    }

    static async manageCoverAction(bookId, actionData) {
        const url = `/books/${bookId}/cover-action/`;
        const response = await fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': this.getCSRFToken()
            },
            body: JSON.stringify(actionData)
        });
        return response.json();
    }

    static async getMetadataConflicts(bookId) {
        const url = `/books/${bookId}/conflicts/`;
        const response = await fetch(url, {
            method: 'GET',
            headers: {
                'X-CSRFToken': this.getCSRFToken()
            }
        });
        return response.json();
    }

    static async removeMetadata(bookId, metadataData) {
        const url = `/books/${bookId}/remove-metadata/`;
        const response = await fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': this.getCSRFToken()
            },
            body: JSON.stringify(metadataData)
        });
        return response.json();
    }

    static getCSRFToken() {
        return document.querySelector('[name=csrfmiddlewaretoken]').value;
    }
}

/**
 * Image utilities for cover handling
 */
class ImageUtils {
    static validateImageFile(file) {
        const allowedTypes = ['image/jpeg', 'image/jpg', 'image/png', 'image/gif', 'image/webp'];
        const maxSize = 5 * 1024 * 1024; // 5MB

        if (!allowedTypes.includes(file.type)) {
            throw new Error('Invalid file type. Please select a valid image file.');
        }

        if (file.size > maxSize) {
            throw new Error('File too large. Please select an image under 5MB.');
        }

        return true;
    }

    static createImagePreview(file) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = (e) => resolve(e.target.result);
            reader.onerror = (e) => reject(e);
            reader.readAsDataURL(file);
        });
    }

    static getImageDimensions(src) {
        return new Promise((resolve) => {
            const img = new Image();
            img.onload = () => {
                resolve({
                    width: img.naturalWidth,
                    height: img.naturalHeight
                });
            };
            img.src = src;
        });
    }
}

/**
 * Form validation utilities
 */
class FormValidators {
    static validateISBN(isbn) {
        if (!isbn) return true;
        
        const cleanISBN = isbn.replace(/[-\s]/g, '');
        // Add length validation
        if (cleanISBN.length !== 10 && cleanISBN.length !== 13) {
            return false;
        }
        return /^(\d{10}|\d{13}|[\dX]{10})$/i.test(cleanISBN);
    }

    static validateYear(year) {
        if (!year) return true;
        
        const yearInt = parseInt(year);
        const currentYear = new Date().getFullYear();
        // More restrictive validation
        return yearInt >= 1000 && yearInt <= currentYear + 5; // Allow some future dates
    }

    static sanitizeText(text) {
        if (!text) return '';
        // Remove potentially dangerous characters
        return text.trim()
                  .replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, '')
                  .replace(/[<>]/g, '');
    }

    // Add file size validation
    static validateFileSize(file, maxSizeMB = 5) {
        const maxSize = maxSizeMB * 1024 * 1024;
        return file.size <= maxSize;
    }
}

/**
 * UI utilities for metadata management
 */
class MetadataUI {
    static showNotification(message, type = 'info') {
        // Create notification element
        const notification = document.createElement('div');
        notification.className = `alert alert-${type} alert-dismissible fade show`;
        notification.innerHTML = `
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;
        
        // Find container or create one
        let container = document.querySelector('.notification-container');
        if (!container) {
            container = document.createElement('div');
            container.className = 'notification-container position-fixed top-0 end-0 p-3';
            container.style.zIndex = '1050';
            document.body.appendChild(container);
        }
        
        container.appendChild(notification);
        
        // Auto-dismiss after 5 seconds
        setTimeout(() => {
            if (notification.parentNode) {
                notification.remove();
            }
        }, 5000);
    }

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

    static toggleLoadingState(button, loading = true) {
        if (loading) {
            button.disabled = true;
            button.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i>Processing...';
        } else {
            button.disabled = false;
            button.innerHTML = button.getAttribute('data-original-text') || 'Submit';
        }
    }
}

/**
 * Keyboard shortcuts handler
 */
class KeyboardShortcuts {
    constructor(shortcuts = {}) {
        this.shortcuts = shortcuts;
        this.init();
    }

    init() {
        document.addEventListener('keydown', (e) => {
            const key = this.getKeyString(e);
            if (this.shortcuts[key]) {
                e.preventDefault();
                this.shortcuts[key]();
            }
        });
    }

    getKeyString(e) {
        const parts = [];
        if (e.ctrlKey) parts.push('ctrl');
        if (e.metaKey) parts.push('cmd');
        if (e.altKey) parts.push('alt');
        if (e.shiftKey) parts.push('shift');
        parts.push(e.key.toLowerCase());
        return parts.join('+');
    }

    addShortcut(key, callback) {
        this.shortcuts[key] = callback;
    }
}

/**
 * Export utilities for use in other scripts
 */
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        MetadataAjax,
        ImageUtils,
        FormValidators,
        MetadataUI,
        KeyboardShortcuts
    };
} else {
    // Browser global
    window.MetadataUtils = {
        MetadataAjax,
        ImageUtils,
        FormValidators,
        MetadataUI,
        KeyboardShortcuts
    };
}