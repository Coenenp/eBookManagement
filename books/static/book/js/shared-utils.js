/**
 * Shared Utilities - Common functionality across the application
 * Consolidated to reduce redundancy
 */

// Global namespace for shared utilities
window.EbookLibrary = window.EbookLibrary || {};

/**
 * Bootstrap utilities - consolidated initialization
 */
EbookLibrary.Bootstrap = {
    initTooltips() {
        const tooltipTriggerList = document.querySelectorAll('[data-bs-toggle="tooltip"]');
        return Array.from(tooltipTriggerList).map(el => new bootstrap.Tooltip(el));
    },

    initPopovers() {
        const popoverTriggerList = document.querySelectorAll('[data-bs-toggle="popover"]');
        return Array.from(popoverTriggerList).map(el => new bootstrap.Popover(el));
    },

    destroyTooltips() {
        document.querySelectorAll('[data-bs-toggle="tooltip"]').forEach(el => {
            const tooltip = bootstrap.Tooltip.getInstance(el);
            if (tooltip) tooltip.dispose();
        });
    }
};

/**
 * Image handling utilities - consolidated from script.js
 */
EbookLibrary.Images = {
    handleCoverErrors() {
        const bookCovers = document.querySelectorAll('.cover-img');
        bookCovers.forEach(img => {
            img.addEventListener('load', function() {
                this.classList.add('loaded');
            });
            
            img.addEventListener('error', function() {
                const coverSize = Array.from(this.classList).find(cls => cls.startsWith('cover-')) || 'cover-medium';
                
                const fallback = document.createElement('div');
                fallback.className = `bg-secondary text-white rounded shadow-sm d-flex align-items-center justify-content-center cover-placeholder ${coverSize}`;
                fallback.innerHTML = '<div class="text-center"><i class="fas fa-book fa-2x mb-2"></i><div class="small">Cover Error</div></div>';
                
                if (this.parentNode) {
                    this.parentNode.replaceChild(fallback, this);
                }
            });
        });
    },

    validateImageFile(file) {
        const allowedTypes = ['image/jpeg', 'image/jpg', 'image/png', 'image/gif', 'image/webp'];
        const maxSize = 5 * 1024 * 1024; // 5MB

        if (!allowedTypes.includes(file.type)) {
            throw new Error('Invalid file type. Please select a valid image file.');
        }

        if (file.size > maxSize) {
            throw new Error('File too large. Please select an image under 5MB.');
        }

        return true;
    },

    createImagePreview(file) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = (e) => resolve(e.target.result);
            reader.onerror = (e) => reject(e);
            reader.readAsDataURL(file);
        });
    }
};

/**
 * Form utilities - consolidated form handling
 */
EbookLibrary.Forms = {
    addLoadingStates() {
        document.querySelectorAll('form').forEach(form => {
            form.addEventListener('submit', function() {
                const submitBtn = form.querySelector('button[type="submit"]');
                if (submitBtn) {
                    submitBtn.disabled = true;
                    const originalText = submitBtn.textContent;
                    submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i>' + originalText;
                }
            });
        });
    },

    toggleLoadingState(button, loading = true) {
        if (loading) {
            button.disabled = true;
            button.setAttribute('data-original-text', button.textContent);
            button.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i>Processing...';
        } else {
            button.disabled = false;
            button.innerHTML = button.getAttribute('data-original-text') || 'Submit';
        }
    },

    getCSRFToken() {
        return document.querySelector('[name=csrfmiddlewaretoken]')?.value;
    }
};

/**
 * Notification system - consolidated UI feedback
 */
EbookLibrary.Notifications = {
    show(message, type = 'info', duration = 5000) {
        const notification = document.createElement('div');
        notification.className = `alert alert-${type} alert-dismissible fade show`;
        notification.innerHTML = `
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;
        
        let container = document.querySelector('.notification-container');
        if (!container) {
            container = document.createElement('div');
            container.className = 'notification-container position-fixed top-0 end-0 p-3';
            container.style.zIndex = '1050';
            document.body.appendChild(container);
        }
        
        container.appendChild(notification);
        
        if (duration > 0) {
            setTimeout(() => {
                if (notification.parentNode) {
                    notification.remove();
                }
            }, duration);
        }
    }
};

/**
 * AJAX utilities - consolidated request handling
 */
EbookLibrary.Ajax = {
    async makeRequest(url, options = {}) {
        const defaultOptions = {
            method: 'GET',
            headers: {
                'X-CSRFToken': EbookLibrary.Forms.getCSRFToken(),
                'Content-Type': 'application/json'
            }
        };

        const mergedOptions = { ...defaultOptions, ...options };
        
        try {
            const response = await fetch(url, mergedOptions);
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return await response.json();
        } catch (error) {
            EbookLibrary.Notifications.show(`Request failed: ${error.message}`, 'danger');
            throw error;
        }
    }
};

/**
 * Initialize all common functionality
 */
EbookLibrary.init = function() {
    // Initialize Bootstrap components
    this.Bootstrap.initTooltips();
    
    // Setup image error handling
    this.Images.handleCoverErrors();
    
    // Setup form loading states
    this.Forms.addLoadingStates();
    
    console.log('Ebook Library shared utilities initialized');
};

// Auto-initialize when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => EbookLibrary.init());
} else {
    EbookLibrary.init();
}
