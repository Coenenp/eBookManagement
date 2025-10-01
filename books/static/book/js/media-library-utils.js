/**
 * Media Library Utilities - Shared functionality across all media sections
 * Provides common utilities for ebooks, comics, series, and other media types
 */

/**
 * Media Library Utilities Class
 * Contains shared functionality used across different media sections
 */
class MediaLibraryUtils {
    /**
     * Escape HTML special characters
     * @param {string} text - Text to escape
     * @returns {string} Escaped text
     */
    static escapeHtml(text) {
        if (!text) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    /**
     * Format file size in human readable format
     * @param {number} bytes - Size in bytes
     * @returns {string} Formatted size string
     */
    static formatFileSize(bytes) {
        if (!bytes || bytes === 0) return '0 B';
        
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }

    /**
     * Format date string in readable format
     * @param {string} dateString - Date string to format
     * @returns {string} Formatted date
     */
    static formatDate(dateString) {
        if (!dateString) return 'Never';
        
        try {
            const date = new Date(dateString);
            return date.toLocaleDateString('en-US', {
                year: 'numeric',
                month: 'short',
                day: 'numeric',
                hour: '2-digit',
                minute: '2-digit'
            });
        } catch (error) {
            console.error('Error formatting date:', error);
            return dateString;
        }
    }

    /**
     * Get CSRF token from Django template
     * @returns {string} CSRF token
     */
    static getCsrfToken() {
        const token = document.querySelector('[name=csrfmiddlewaretoken]');
        return token ? token.value : '';
    }

    /**
     * Show loading state in container
     * @param {HTMLElement} container - Container to show loading in
     * @param {string} message - Loading message
     */
    static showLoadingState(container, message = 'Loading...') {
        if (!container) return;
        
        container.innerHTML = `
            <div class="text-center p-4">
                <div class="spinner-border text-primary mb-3" role="status">
                    <span class="visually-hidden">Loading...</span>
                </div>
                <p class="text-muted">${MediaLibraryUtils.escapeHtml(message)}</p>
            </div>
        `;
    }

    /**
     * Show empty state in container
     * @param {HTMLElement} container - Container to show empty state in
     * @param {string} title - Empty state title
     * @param {string} message - Empty state message
     * @param {string} icon - Font Awesome icon class
     */
    static showEmptyState(container, title = 'No Items Found', message = 'No items match your current filters.', icon = 'fas fa-inbox') {
        if (!container) return;
        
        container.innerHTML = `
            <div class="text-center p-4 text-muted">
                <i class="${MediaLibraryUtils.escapeHtml(icon)} fa-3x mb-3"></i>
                <h5>${MediaLibraryUtils.escapeHtml(title)}</h5>
                <p>${MediaLibraryUtils.escapeHtml(message)}</p>
            </div>
        `;
    }

    /**
     * Show error state in container
     * @param {HTMLElement} container - Container to show error in
     * @param {string} message - Error message
     */
    static showErrorState(container, message = 'An error occurred while loading data.') {
        if (!container) return;
        
        container.innerHTML = `
            <div class="text-center p-4 text-danger">
                <i class="fas fa-exclamation-triangle fa-3x mb-3"></i>
                <h5>Error</h5>
                <p>${MediaLibraryUtils.escapeHtml(message)}</p>
                <button class="btn btn-outline-primary btn-sm" onclick="location.reload()">
                    <i class="fas fa-redo me-1"></i>Retry
                </button>
            </div>
        `;
    }

    /**
     * Show toast notification
     * @param {string} message - Message to display
     * @param {string} type - Toast type (success, error, warning, info)
     * @param {number} duration - Duration in milliseconds
     */
    static showToast(message, type = 'info', duration = 5000) {
        // Remove existing toasts
        document.querySelectorAll('.media-toast').forEach(toast => toast.remove());
        
        const toastTypes = {
            success: { icon: 'check-circle', class: 'success' },
            error: { icon: 'exclamation-circle', class: 'danger' },
            warning: { icon: 'exclamation-triangle', class: 'warning' },
            info: { icon: 'info-circle', class: 'info' }
        };
        
        const toastConfig = toastTypes[type] || toastTypes.info;
        
        const toast = document.createElement('div');
        toast.className = `media-toast alert alert-${toastConfig.class} alert-dismissible fade show position-fixed`;
        toast.style.cssText = `
            top: 20px;
            right: 20px;
            z-index: 9999;
            min-width: 300px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        `;
        
        toast.innerHTML = `
            <i class="fas fa-${toastConfig.icon} me-2"></i>
            ${MediaLibraryUtils.escapeHtml(message)}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;
        
        document.body.appendChild(toast);
        
        // Auto-remove after duration
        setTimeout(() => {
            if (toast.parentNode) {
                toast.remove();
            }
        }, duration);
    }

    /**
     * Make AJAX request with proper error handling
     * @param {string} url - Request URL
     * @param {Object} options - Fetch options
     * @returns {Promise} Promise that resolves with response data
     */
    static async makeRequest(url, options = {}) {
        try {
            const defaultOptions = {
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': MediaLibraryUtils.getCsrfToken()
                }
            };
            
            const response = await fetch(url, { ...defaultOptions, ...options });
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            return await response.json();
        } catch (error) {
            console.error('Request failed:', error);
            throw error;
        }
    }

    /**
     * Debounce function calls
     * @param {Function} func - Function to debounce
     * @param {number} wait - Wait time in milliseconds
     * @returns {Function} Debounced function
     */
    static debounce(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    }

    /**
     * Filter items based on search and filter criteria
     * @param {Array} items - Items to filter
     * @param {string} searchTerm - Search term
     * @param {string} sortBy - Sort field
     * @param {string} formatFilter - Format filter
     * @param {string} statusFilter - Status filter
     * @returns {Array} Filtered and sorted items
     */
    static filterAndSortItems(items, searchTerm = '', sortBy = 'title', formatFilter = '', statusFilter = '') {
        let filtered = [...items];

        // Apply search filter
        if (searchTerm.trim()) {
            const search = searchTerm.toLowerCase();
            filtered = filtered.filter(item => {
                const title = (item.title || '').toLowerCase();
                const author = (item.author || '').toLowerCase();
                const series = (item.series || '').toLowerCase();
                
                return title.includes(search) || 
                       author.includes(search) || 
                       series.includes(search);
            });
        }

        // Apply format filter
        if (formatFilter) {
            filtered = filtered.filter(item => 
                (item.format || '').toLowerCase() === formatFilter.toLowerCase()
            );
        }

        // Apply status filter
        if (statusFilter) {
            filtered = filtered.filter(item => {
                switch (statusFilter) {
                    case 'read':
                        return item.is_read;
                    case 'unread':
                        return !item.is_read;
                    case 'reading':
                        return item.is_reading;
                    default:
                        return true;
                }
            });
        }

        // Sort items
        filtered.sort((a, b) => {
            let aVal = a[sortBy] || '';
            let bVal = b[sortBy] || '';
            
            // Handle date sorting
            if (sortBy.includes('date') || sortBy.includes('time')) {
                aVal = new Date(aVal);
                bVal = new Date(bVal);
            }
            
            // Handle numeric sorting
            if (sortBy === 'size') {
                aVal = parseInt(aVal) || 0;
                bVal = parseInt(bVal) || 0;
            }
            
            if (aVal < bVal) return -1;
            if (aVal > bVal) return 1;
            return 0;
        });

        return filtered;
    }

    /**
     * Download file via hidden link
     * @param {string} url - File URL
     * @param {string} filename - Suggested filename
     */
    static downloadFile(url, filename = '') {
        const link = document.createElement('a');
        link.href = url;
        if (filename) {
            link.download = filename;
        }
        link.target = '_blank';
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
    }

    /**
     * Open file location (if supported by browser)
     * @param {string} filePath - Path to file
     */
    static openFileLocation(filePath) {
        // This is limited by browser security - mainly works in desktop apps
        try {
            if (window.electronAPI) {
                // Electron app
                window.electronAPI.showItemInFolder(filePath);
            } else {
                // Fallback: copy path to clipboard
                navigator.clipboard.writeText(filePath).then(() => {
                    MediaLibraryUtils.showToast(`File path copied to clipboard: ${filePath}`, 'info');
                }).catch(() => {
                    MediaLibraryUtils.showToast('File path: ' + filePath, 'info', 10000);
                });
            }
        } catch (error) {
            console.error('Error opening file location:', error);
            MediaLibraryUtils.showToast('Unable to open file location', 'error');
        }
    }

    /**
     * Validate and sanitize HTML content
     * @param {string} html - HTML content to sanitize
     * @returns {string} Sanitized HTML
     */
    static sanitizeHtml(html) {
        if (!html) return '';
        
        // Create a temporary div to parse HTML
        const temp = document.createElement('div');
        temp.innerHTML = html;
        
        // Remove script tags and event handlers
        temp.querySelectorAll('script').forEach(el => el.remove());
        temp.querySelectorAll('[on*]').forEach(el => {
            Array.from(el.attributes).forEach(attr => {
                if (attr.name.startsWith('on')) {
                    el.removeAttribute(attr.name);
                }
            });
        });
        
        return temp.innerHTML;
    }
}

/**
 * Base Section Manager Class
 * Provides common functionality for all media section managers
 */
class BaseSectionManager {
    constructor(sectionType, config = {}) {
        this.sectionType = sectionType;
        this.config = {
            listContainer: `#${sectionType}-list-container`,
            detailContainer: `#${sectionType}-detail-container`,
            apiEndpoint: `/books/${sectionType}/ajax/`,
            ...config
        };
        
        this.currentData = [];
        this.filteredData = [];
        this.selectedItem = null;
        
        this.init();
    }

    init() {
        this.bindEvents();
        this.loadItems();
    }

    bindEvents() {
        // Override in subclasses
    }

    async loadItems() {
        try {
            const container = document.querySelector(this.config.listContainer);
            MediaLibraryUtils.showLoadingState(container, `Loading ${this.sectionType}...`);
            
            const data = await MediaLibraryUtils.makeRequest(this.config.apiEndpoint);
            
            if (data.success) {
                this.currentData = data[this.sectionType] || [];
                this.filteredData = [...this.currentData];
                this.renderList();
                this.updateItemCount(this.filteredData.length);
            } else {
                throw new Error(data.message || 'Failed to load data');
            }
        } catch (error) {
            console.error(`Error loading ${this.sectionType}:`, error);
            const container = document.querySelector(this.config.listContainer);
            MediaLibraryUtils.showErrorState(container, `Failed to load ${this.sectionType}`);
        }
    }

    filterItems(searchTerm, sortBy, formatFilter, statusFilter) {
        this.filteredData = MediaLibraryUtils.filterAndSortItems(
            this.currentData,
            searchTerm,
            sortBy,
            formatFilter,
            statusFilter
        );
        
        this.renderList();
        this.updateItemCount(this.filteredData.length);
    }

    renderList(viewType = null) {
        // Override in subclasses
        console.log(`Rendering ${this.sectionType} list with ${this.filteredData.length} items`);
    }

    updateItemCount(count) {
        if (typeof window.updateItemCount === 'function') {
            window.updateItemCount(count);
        }
    }

    selectItem(itemId) {
        this.selectedItem = this.currentData.find(item => item.id == itemId);
        if (this.selectedItem) {
            this.loadDetail(itemId);
        }
    }

    async loadDetail(itemId) {
        try {
            const container = document.querySelector(this.config.detailContainer);
            MediaLibraryUtils.showLoadingState(container, 'Loading details...');
            
            const data = await MediaLibraryUtils.makeRequest(`${this.config.apiEndpoint}${itemId}/`);
            
            if (data.success) {
                this.renderDetail(data[this.sectionType.slice(0, -1)]); // Remove 's' from plural
            } else {
                throw new Error(data.message || 'Failed to load details');
            }
        } catch (error) {
            console.error(`Error loading ${this.sectionType} details:`, error);
            const container = document.querySelector(this.config.detailContainer);
            MediaLibraryUtils.showErrorState(container, 'Failed to load details');
        }
    }

    renderDetail(item) {
        // Override in subclasses
        console.log(`Rendering ${this.sectionType} detail for:`, item);
    }
}

// Export for global access
window.MediaLibraryUtils = MediaLibraryUtils;
window.BaseSectionManager = BaseSectionManager;