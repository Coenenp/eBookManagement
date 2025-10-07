/**
 * Base Section Manager - Base class for all media section managers
 * Provides common functionality for ebooks, audiobooks, comics, and series sections
 */

class BaseSectionManager {
    constructor(sectionType, config = {}) {
        this.sectionType = sectionType;
        this.config = {
            listContainer: '#list-container',
            detailContainer: '#detail-container',
            apiEndpoint: '/ajax/',
            detailEndpoint: '/ajax/',
            ...config
        };
        
        this.currentData = [];
        this.filteredData = [];
        this.selectedItemId = null;
        this.isLoading = false;
        
        this.initialize();
    }

    initialize() {
        this.bindEvents();
        this.loadInitialData();
    }

    bindEvents() {
        // Search functionality
        const searchInput = document.getElementById('search-input');
        if (searchInput) {
            searchInput.addEventListener('input', this.debounce(() => {
                this.handleSearch();
            }, 300));
        }

        // Sort functionality
        const sortSelect = document.getElementById('sort-select');
        if (sortSelect) {
            sortSelect.addEventListener('change', () => {
                this.handleSearch();
            });
        }

        // Format filter
        const formatFilter = document.getElementById('format-filter');
        if (formatFilter) {
            formatFilter.addEventListener('change', () => {
                this.handleSearch();
            });
        }

        // Status filter
        const statusFilter = document.getElementById('status-filter');
        if (statusFilter) {
            statusFilter.addEventListener('change', () => {
                this.handleSearch();
            });
        }

        // View toggle buttons
        document.querySelectorAll('[data-view-type]').forEach(button => {
            button.addEventListener('click', (e) => {
                const viewType = e.target.dataset.viewType;
                this.setViewType(viewType);
                this.renderList(viewType);
                
                // Update button states
                document.querySelectorAll('[data-view-type]').forEach(b => b.classList.remove('active'));
                e.target.classList.add('active');
            });
        });
    }

    debounce(func, wait) {
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

    handleSearch() {
        const searchTerm = document.getElementById('search-input')?.value || '';
        const sortBy = document.getElementById('sort-select')?.value || 'title';
        const formatFilter = document.getElementById('format-filter')?.value || '';
        const statusFilter = document.getElementById('status-filter')?.value || '';
        
        this.filterItems(searchTerm, sortBy, formatFilter, statusFilter);
    }

    loadInitialData() {
        this.loadData();
    }

    loadData() {
        if (this.isLoading) return;
        
        const container = document.querySelector(this.config.listContainer);
        this.showLoadingState(container, `Loading ${this.sectionType}...`);
        
        this.isLoading = true;
        
        fetch(this.config.apiEndpoint, {
            method: 'GET',
            headers: {
                'X-Requested-With': 'XMLHttpRequest'
            }
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                this.currentData = data[this.sectionType] || data.items || [];
                this.filteredData = [...this.currentData];
                this.renderList();
                this.updateItemCount(this.currentData.length);
            } else {
                this.showErrorState(container, data.error || 'Failed to load data');
            }
        })
        .catch(error => {
            console.error(`Error loading ${this.sectionType}:`, error);
            this.showErrorState(container, 'Network error occurred. Please try again.');
        })
        .finally(() => {
            this.isLoading = false;
        });
    }

    filterItems(searchTerm, sortBy, formatFilter, statusFilter) {
        // Override in child classes
        console.warn('filterItems method should be overridden in child classes');
    }

    renderList(viewType = null) {
        // Override in child classes
        console.warn('renderList method should be overridden in child classes');
    }

    selectItem(itemId) {
        this.selectedItemId = itemId;
        
        // Update UI selection
        this.updateItemSelection(itemId);
        
        // Load detail view
        this.loadDetail(itemId);
        
        // Store selection for mobile navigation
        if (window.innerWidth <= 768) {
            this.handleMobileLayout();
        }
    }

    updateItemSelection(itemId) {
        // Remove previous selection
        document.querySelectorAll('.list-item.selected').forEach(el => {
            el.classList.remove('selected');
        });
        
        // Add selection to new item
        const newItem = document.querySelector(`[data-item-id="${itemId}"]`);
        if (newItem) {
            newItem.classList.add('selected');
        }
    }

    loadDetail(itemId) {
        // Override in child classes or implement generic detail loading
        console.warn('loadDetail method should be overridden in child classes');
    }

    showLoadingState(container, message = 'Loading...') {
        if (!container) return;
        
        container.innerHTML = `
            <div class="d-flex justify-content-center align-items-center py-5">
                <div class="text-center">
                    <div class="spinner-border text-primary mb-3" role="status">
                        <span class="visually-hidden">${message}</span>
                    </div>
                    <div class="text-muted">${message}</div>
                </div>
            </div>
        `;
    }

    showErrorState(container, message) {
        if (!container) return;
        
        container.innerHTML = `
            <div class="alert alert-danger m-3">
                <i class="fas fa-exclamation-triangle me-2"></i>
                ${MediaLibraryUtils.escapeHtml(message)}
            </div>
        `;
    }

    updateItemCount(count) {
        const countElement = document.getElementById('item-count');
        if (countElement) {
            countElement.textContent = count;
        }
    }

    getCurrentViewType() {
        const activeButton = document.querySelector('[data-view-type].active');
        return activeButton ? activeButton.dataset.viewType : 'list';
    }

    setViewType(viewType) {
        // Store view type preference
        localStorage.setItem(`${this.sectionType}_view_type`, viewType);
    }

    getViewType() {
        return localStorage.getItem(`${this.sectionType}_view_type`) || 'list';
    }

    handleMobileLayout() {
        // Hide list pane and show detail pane on mobile
        const listPane = document.getElementById('list-pane');
        const detailPane = document.getElementById('detail-pane');
        
        if (listPane && detailPane) {
            listPane.classList.add('d-none');
            detailPane.classList.remove('d-none');
        }
    }

    addMobileBackButton() {
        const detailContainer = document.querySelector(this.config.detailContainer);
        if (!detailContainer) return;
        
        // Remove existing back button
        const existingButton = detailContainer.querySelector('.mobile-back-button');
        if (existingButton) {
            existingButton.remove();
        }
        
        // Add new back button
        const backButton = document.createElement('div');
        backButton.className = 'mobile-back-button d-md-none mb-3';
        backButton.innerHTML = `
            <button class="btn btn-outline-secondary" onclick="window.sectionManager.showListPane()">
                <i class="fas fa-arrow-left me-2"></i>Back to List
            </button>
        `;
        
        detailContainer.insertBefore(backButton, detailContainer.firstChild);
    }

    showListPane() {
        // Show list pane and hide detail pane on mobile
        const listPane = document.getElementById('list-pane');
        const detailPane = document.getElementById('detail-pane');
        
        if (listPane && detailPane) {
            listPane.classList.remove('d-none');
            detailPane.classList.add('d-none');
        }
    }

    getCsrfToken() {
        // Get CSRF token from meta tag or cookie
        const metaToken = document.querySelector('meta[name="csrf-token"]');
        if (metaToken) {
            return metaToken.getAttribute('content');
        }
        
        // Fallback to cookie method
        const cookies = document.cookie.split(';');
        for (let cookie of cookies) {
            const [name, value] = cookie.trim().split('=');
            if (name === 'csrftoken') {
                return value;
            }
        }
        return '';
    }

    // Virtual methods that can be overridden
    onItemActivate(itemId) {
        // Override in child classes for double-click or enter key handling
    }
}

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = BaseSectionManager;
}