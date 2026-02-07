/**
 * Base Section Manager - Base class for all media section managers
 * Provides common functionality for ebooks, audiobooks, comics, and series sections
 */

if (typeof BaseSectionManager === 'undefined') {
    window.BaseSectionManager = class BaseSectionManager {
        constructor(sectionType, config = {}) {
            this.sectionType = sectionType;
            this.config = {
                listContainer: '#list-container',
                detailContainer: '#detail-container',
                apiEndpoint: '/ajax/',
                detailEndpoint: '/ajax/',
                ...config,
            };

            this.currentData = [];
            this.filteredData = [];
            this.selectedItemId = null;
            this.isLoading = false;
            this.expandedItems = new Set(); // Universal expanded items tracker

            // Field mapping for different content types
            this.fieldMap = this.getFieldMapping();

            this.initialize();
        }

        /**
         * Get field mapping for different content types
         * This allows unified filtering/sorting across different data structures
         */
        getFieldMapping() {
            const mappings = {
                series: {
                    title: 'name',
                    author: 'authors[0]',
                    format: 'formats',
                    isArray: { authors: true, formats: true },
                    books: 'books',
                },
                ebooks: {
                    title: 'title',
                    author: 'author',
                    format: 'file_format',
                    isArray: {},
                    books: null,
                },
                audiobooks: {
                    title: 'title',
                    author: 'author',
                    format: 'file_format',
                    isArray: {},
                    books: null,
                },
                comics: {
                    title: 'name',
                    author: 'books[0].author',
                    format: 'books[0].file_format',
                    isArray: {},
                    books: 'books',
                },
            };
            return mappings[this.sectionType] || mappings['ebooks'];
        }

        /**
         * Get field value using the field mapping
         */
        getFieldValue(item, fieldType) {
            const fieldPath = this.fieldMap[fieldType];
            if (!fieldPath) return '';

            return this.getNestedValue(item, fieldPath) || '';
        }

        /**
         * Helper to get nested object values using dot notation
         */
        getNestedValue(obj, path) {
            if (!path) return '';

            // Handle array access like 'authors[0]' or 'books[0].title'
            return path.split('.').reduce((current, key) => {
                if (!current) return '';

                // Handle array indexing
                const arrayMatch = key.match(/^(.+)\[(\d+)\]$/);
                if (arrayMatch) {
                    const [, arrayKey, index] = arrayMatch;
                    const array = current[arrayKey];
                    return Array.isArray(array) ? array[parseInt(index)] : '';
                }

                return current[key];
            }, obj);
        }

        initialize() {
            this.bindEvents();
            this.loadInitialData();
        }

        bindEvents() {
            // Search functionality
            const searchInput = document.getElementById('search-filter');
            if (searchInput) {
                searchInput.addEventListener(
                    'input',
                    this.debounce(() => {
                        this.handleSearch();
                    }, 300)
                );
            }

            // Sort functionality
            const sortSelect = document.getElementById('sort-filter');
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
            document.querySelectorAll('[data-view-type]').forEach((button) => {
                button.addEventListener('click', (e) => {
                    const viewType = e.target.dataset.viewType;
                    this.setViewType(viewType);
                    this.renderList(viewType);

                    // Update button states
                    document.querySelectorAll('[data-view-type]').forEach((b) => b.classList.remove('active'));
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
            const searchTerm = document.getElementById('search-filter')?.value || '';
            const sortBy = document.getElementById('sort-filter')?.value || 'title';
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
                    'X-Requested-With': 'XMLHttpRequest',
                },
            })
                .then((response) => response.json())
                .then((data) => {
                    if (data.success) {
                        this.currentData = data[this.sectionType] || data.items || [];
                        this.filteredData = [...this.currentData];
                        this.renderList();
                        this.updateItemCount(this.currentData.length);
                    } else {
                        // Use friendly error messages instead of generic ones
                        const sectionName = this.sectionType.charAt(0).toUpperCase() + this.sectionType.slice(1);
                        this.showFriendlyEmptyState(
                            container,
                            `No ${sectionName} Found`,
                            `No ${this.sectionType} match your current filters.`
                        );
                    }
                })
                .catch((error) => {
                    console.error(`Error loading ${this.sectionType}:`, error);
                    const sectionName = this.sectionType.charAt(0).toUpperCase() + this.sectionType.slice(1);
                    this.showFriendlyEmptyState(
                        container,
                        `Unable to Load ${sectionName}`,
                        `There was a problem loading ${this.sectionType}. Please try again.`
                    );
                })
                .finally(() => {
                    this.isLoading = false;
                });
        }

        /**
         * UNIFIED FILTERING METHOD
         * Works for all section types using field mapping
         */
        filterItems(searchTerm, sortBy, formatFilter, statusFilter) {
            this.filteredData = this.currentData.filter((item) => {
                // Search filter - works across all content types
                const matchesSearch = !searchTerm || this.matchesSearchTerm(item, searchTerm);

                // Format filter - unified approach
                const matchesFormat = !formatFilter || this.matchesFormat(item, formatFilter);

                // Status filter - unified approach
                const matchesStatus = !statusFilter || this.matchesStatus(item, statusFilter);

                return matchesSearch && matchesFormat && matchesStatus;
            });

            // Sort results using unified sorting
            this.sortData(sortBy);

            this.renderList();
            this.updateItemCount(this.filteredData.length);
        }

        /**
         * Unified search matching across all content types
         */
        matchesSearchTerm(item, searchTerm) {
            const term = searchTerm.toLowerCase();

            // Check title field
            const title = this.getFieldValue(item, 'title').toLowerCase();
            if (title.includes(term)) return true;

            // Check author field(s)
            const author = this.getFieldValue(item, 'author');
            if (Array.isArray(author)) {
                if (author.some((a) => a.toLowerCase().includes(term))) return true;
            } else if (typeof author === 'string') {
                if (author.toLowerCase().includes(term)) return true;
            }

            // For series/comics, also search within books
            const books = item[this.fieldMap.books];
            if (Array.isArray(books)) {
                return books.some(
                    (book) =>
                        (book.title && book.title.toLowerCase().includes(term)) ||
                        (book.author && book.author.toLowerCase().includes(term))
                );
            }

            return false;
        }

        /**
         * Unified format matching
         */
        matchesFormat(item, formatFilter) {
            const format = this.getFieldValue(item, 'format');

            // Normalize both values to lowercase for comparison
            const normalizedFilter = formatFilter.toLowerCase();

            if (Array.isArray(format)) {
                return format.some((f) => f.toLowerCase() === normalizedFilter);
            } else if (typeof format === 'string') {
                return format.toLowerCase() === normalizedFilter;
            }

            // For series/comics, check books
            const books = item[this.fieldMap.books];
            if (Array.isArray(books)) {
                return books.some((book) => book.file_format && book.file_format.toLowerCase() === normalizedFilter);
            }

            return false;
        }

        /**
         * Unified status matching
         */
        matchesStatus(item, statusFilter) {
            switch (statusFilter) {
                case 'read':
                    return this.isItemRead(item);
                case 'unread':
                    return !this.isItemRead(item);
                case 'reading':
                case 'listening':
                    return this.isItemInProgress(item);
                default:
                    return true;
            }
        }

        isItemRead(item) {
            if (item.is_read !== undefined) {
                return item.is_read;
            }

            // For series/comics, check if all books are read
            const books = item[this.fieldMap.books];
            if (Array.isArray(books)) {
                return books.length > 0 && books.every((book) => book.is_read);
            }

            return false;
        }

        isItemInProgress(item) {
            if (item.reading_progress > 0 || item.listening_progress > 0) {
                return !item.is_read;
            }

            // For series/comics, check if any books are in progress
            const books = item[this.fieldMap.books];
            if (Array.isArray(books)) {
                return books.some((book) => book.reading_progress > 0 && !book.is_read);
            }

            return false;
        }

        /**
         * UNIFIED SORTING METHOD
         * Works for all section types using field mapping
         */
        sortData(sortBy) {
            this.filteredData.sort((a, b) => {
                switch (sortBy) {
                    case 'title':
                        const titleA = this.getFieldValue(a, 'title');
                        const titleB = this.getFieldValue(b, 'title');
                        return titleA.localeCompare(titleB);

                    case 'author':
                        const authorA = this.getFieldValue(a, 'author');
                        const authorB = this.getFieldValue(b, 'author');
                        const authStrA = Array.isArray(authorA) ? authorA[0] || '' : authorA;
                        const authStrB = Array.isArray(authorB) ? authorB[0] || '' : authorB;
                        return authStrA.localeCompare(authStrB);

                    case 'date':
                        return this.compareDates(a, b);

                    case 'size':
                        return this.compareSizes(a, b);

                    case 'duration':
                        return (b.duration_seconds || 0) - (a.duration_seconds || 0);

                    default:
                        const defTitleA = this.getFieldValue(a, 'title');
                        const defTitleB = this.getFieldValue(b, 'title');
                        return defTitleA.localeCompare(defTitleB);
                }
            });
        }

        compareDates(a, b) {
            // For series/comics, compare most recent book
            const booksA = a[this.fieldMap.books];
            const booksB = b[this.fieldMap.books];

            if (Array.isArray(booksA) && Array.isArray(booksB)) {
                const aLatest = Math.max(...booksA.map((book) => new Date(book.last_scanned || 0)));
                const bLatest = Math.max(...booksB.map((book) => new Date(book.last_scanned || 0)));
                return bLatest - aLatest;
            }

            // For individual items
            return new Date(b.last_scanned || 0) - new Date(a.last_scanned || 0);
        }

        compareSizes(a, b) {
            // For series/comics, use total_size if available
            if (a.total_size !== undefined && b.total_size !== undefined) {
                return b.total_size - a.total_size;
            }

            // For individual items
            return (b.file_size || 0) - (a.file_size || 0);
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
            document.querySelectorAll('.list-item.selected').forEach((el) => {
                el.classList.remove('selected');
            });

            // Add selection to new item
            const newItem = document.querySelector(`[data-item-id="${itemId}"]`);
            if (newItem) {
                newItem.classList.add('selected');
            }
        }

        async loadDetail(itemId) {
            try {
                const container = document.querySelector(this.config.detailContainer);
                this.showLoadingState(container, 'Loading details...');

                const endpoint = this.config.detailEndpoint.replace('{id}', itemId).replace('0', itemId);
                const data = await fetch(endpoint, {
                    headers: { 'X-Requested-With': 'XMLHttpRequest' },
                }).then((r) => r.json());

                if (data.success) {
                    this.renderDetail(data);
                } else {
                    throw new Error(data.message || 'Failed to load details');
                }
            } catch (error) {
                console.error(`Error loading ${this.sectionType} details:`, error);
                const container = document.querySelector(this.config.detailContainer);
                this.showFriendlyEmptyState(
                    container,
                    'Unable to Load Details',
                    `There was a problem loading details. Please try again.`
                );
            }
        }

        renderDetail(data) {
            // Override in child classes
            console.warn('renderDetail method should be overridden in child classes');
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

        showFriendlyEmptyState(container, title, message) {
            const icon = this.getSectionIcon();
            if (typeof MediaLibraryUtils !== 'undefined' && MediaLibraryUtils.showEmptyState) {
                MediaLibraryUtils.showEmptyState(container, title, message, icon);
            } else {
                // Fallback if MediaLibraryUtils is not available
                container.innerHTML = `
                    <div class="empty-state text-center py-5">
                        <i class="${icon} fa-3x text-muted mb-3"></i>
                        <h5 class="text-muted">${title}</h5>
                        <p class="text-muted">${message}</p>
                    </div>
                `;
            }
        }

        getSectionIcon() {
            const icons = {
                ebooks: 'fas fa-book',
                audiobooks: 'fas fa-headphones',
                comics: 'fas fa-mask',
                series: 'fas fa-layer-group',
            };
            return icons[this.sectionType] || 'fas fa-inbox';
        }

        updateItemCount(count) {
            const countElement = document.getElementById('item-count');
            if (countElement) {
                countElement.textContent = count;
            }
        }

        getCurrentViewType() {
            // Check localStorage first (user override)
            let saved = localStorage.getItem(`${this.sectionType}-view-type`);
            if (saved) {
                return saved;
            }
            // Fall back to user profile default if available
            if (window.userDefaultViewMode) {
                return window.userDefaultViewMode;
            }
            // Final fallback to 'list'
            return 'list';
        }

        setViewType(viewType) {
            localStorage.setItem(`${this.sectionType}-view-type`, viewType);
        }

        getViewType() {
            return this.getCurrentViewType();
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
    };
}

/**
 * BaseSectionManager - Parent class for all section managers
 */
if (typeof BaseSectionManager === 'undefined') {
    window.BaseSectionManager = class BaseSectionManager {
        constructor(sectionType, config) {
            console.log(`Creating ${sectionType} manager with config:`, config);
            this.sectionType = sectionType;
            this.config = config;
            this.currentData = [];
            this.filteredData = [];
            this.selectedItem = null;

            // Auto-initialize
            console.log(`Auto-initializing ${sectionType} manager`);
            this.initialize();
        }

        async initialize() {
            console.log(`Initializing ${this.sectionType} manager`);
            try {
                // Load initial data
                console.log(`Loading data for ${this.sectionType}`);
                await this.loadInitialData();

                // Initialize filters
                console.log(`Initializing filters for ${this.sectionType}`);
                this.initializeFilters();

                // Bind events
                console.log(`Binding events for ${this.sectionType}`);
                this.bindEvents();

                // Render initial view
                console.log(`Rendering initial view for ${this.sectionType}`);
                this.renderList();

                console.log(`${this.sectionType} manager initialized successfully`);
            } catch (error) {
                console.error(`Error initializing ${this.sectionType}:`, error);
                const container = document.querySelector(this.config.listContainer);
                if (container && typeof MediaLibraryUtils !== 'undefined') {
                    MediaLibraryUtils.showErrorState(container, `Failed to load ${this.sectionType}: ${error.message}`);
                }
            }
        }

        async loadInitialData() {
            console.log(`loadInitialData called for ${this.sectionType}`);
            try {
                // Call the child class's loadData method
                if (this.loadData) {
                    await this.loadData();
                    console.log(`Data loaded for ${this.sectionType}, now calling renderList`);

                    // IMPORTANT: Render the list after data loads
                    if (this.renderList) {
                        this.renderList();
                        console.log(`renderList called successfully for ${this.sectionType}`);
                    } else {
                        console.warn(`renderList method not available for ${this.sectionType}`);
                    }
                } else {
                    console.warn(`loadData method not implemented in ${this.sectionType} manager`);
                }
            } catch (error) {
                console.error(`Error in loadInitialData for ${this.sectionType}:`, error);
                throw error;
            }
        }

        /**
         * Get field mapping for different content types
         * This allows unified filtering/sorting across different data structures
         */
        getFieldMapping() {
            const mappings = {
                series: {
                    title: 'name',
                    author: 'authors[0]',
                    format: 'formats',
                    isArray: { authors: true, formats: true },
                    books: 'books',
                },
                ebooks: {
                    title: 'title',
                    author: 'author',
                    format: 'file_format',
                    isArray: {},
                    books: null,
                },
                audiobooks: {
                    title: 'title',
                    author: 'author',
                    format: 'file_format',
                    isArray: {},
                    books: null,
                },
                comics: {
                    title: 'name',
                    author: 'books[0].author',
                    format: 'books[0].file_format',
                    isArray: {},
                    books: 'books',
                },
            };
            return mappings[this.sectionType] || mappings['ebooks'];
        }

        /**
         * Get field value using the field mapping
         */
        getFieldValue(item, fieldType) {
            const fieldPath = this.fieldMap[fieldType];
            if (!fieldPath) return '';

            return this.getNestedValue(item, fieldPath) || '';
        }

        /**
         * Helper to get nested object values using dot notation
         */
        getNestedValue(obj, path) {
            if (!path) return '';

            // Handle array access like 'authors[0]' or 'books[0].title'
            return path.split('.').reduce((current, key) => {
                if (!current) return '';

                // Handle array indexing
                const arrayMatch = key.match(/^(.+)\[(\d+)\]$/);
                if (arrayMatch) {
                    const [, arrayKey, index] = arrayMatch;
                    const array = current[arrayKey];
                    return Array.isArray(array) ? array[parseInt(index)] : '';
                }

                return current[key];
            }, obj);
        }

        initialize() {
            this.bindEvents();
            this.loadInitialData();
        }

        bindEvents() {
            // Search functionality
            const searchInput = document.getElementById('search-filter');
            if (searchInput) {
                searchInput.addEventListener(
                    'input',
                    this.debounce(() => {
                        this.handleSearch();
                    }, 300)
                );
            }

            // Sort functionality
            const sortSelect = document.getElementById('sort-filter');
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
            document.querySelectorAll('[data-view-type]').forEach((button) => {
                button.addEventListener('click', (e) => {
                    const viewType = e.target.dataset.viewType;
                    this.setViewType(viewType);
                    this.renderList(viewType);

                    // Update button states
                    document.querySelectorAll('[data-view-type]').forEach((b) => b.classList.remove('active'));
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
            const searchTerm = document.getElementById('search-filter')?.value || '';
            const sortBy = document.getElementById('sort-filter')?.value || 'title';
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
                    'X-Requested-With': 'XMLHttpRequest',
                },
            })
                .then((response) => response.json())
                .then((data) => {
                    if (data.success) {
                        this.currentData = data[this.sectionType] || data.items || [];
                        this.filteredData = [...this.currentData];
                        this.renderList();
                        this.updateItemCount(this.currentData.length);
                    } else {
                        // Use friendly error messages instead of generic ones
                        const sectionName = this.sectionType.charAt(0).toUpperCase() + this.sectionType.slice(1);
                        this.showFriendlyEmptyState(
                            container,
                            `No ${sectionName} Found`,
                            `No ${this.sectionType} match your current filters.`
                        );
                    }
                })
                .catch((error) => {
                    console.error(`Error loading ${this.sectionType}:`, error);
                    const sectionName = this.sectionType.charAt(0).toUpperCase() + this.sectionType.slice(1);
                    this.showFriendlyEmptyState(
                        container,
                        `Unable to Load ${sectionName}`,
                        `There was a problem loading ${this.sectionType}. Please try again.`
                    );
                })
                .finally(() => {
                    this.isLoading = false;
                });
        }

        /**
         * UNIFIED FILTERING METHOD
         * Works for all section types using field mapping
         */
        filterItems(searchTerm, sortBy, formatFilter, statusFilter) {
            this.filteredData = this.currentData.filter((item) => {
                // Search filter - works across all content types
                const matchesSearch = !searchTerm || this.matchesSearchTerm(item, searchTerm);

                // Format filter - unified approach
                const matchesFormat = !formatFilter || this.matchesFormat(item, formatFilter);

                // Status filter - unified approach
                const matchesStatus = !statusFilter || this.matchesStatus(item, statusFilter);

                return matchesSearch && matchesFormat && matchesStatus;
            });

            // Sort results using unified sorting
            this.sortData(sortBy);

            this.renderList();
            this.updateItemCount(this.filteredData.length);
        }

        /**
         * Unified search matching across all content types
         */
        matchesSearchTerm(item, searchTerm) {
            const term = searchTerm.toLowerCase();

            // Check title field
            const title = this.getFieldValue(item, 'title').toLowerCase();
            if (title.includes(term)) return true;

            // Check author field(s)
            const author = this.getFieldValue(item, 'author');
            if (Array.isArray(author)) {
                if (author.some((a) => a.toLowerCase().includes(term))) return true;
            } else if (typeof author === 'string') {
                if (author.toLowerCase().includes(term)) return true;
            }

            // For series/comics, also search within books
            const books = item[this.fieldMap.books];
            if (Array.isArray(books)) {
                return books.some(
                    (book) =>
                        (book.title && book.title.toLowerCase().includes(term)) ||
                        (book.author && book.author.toLowerCase().includes(term))
                );
            }

            return false;
        }

        /**
         * Unified format matching
         */
        matchesFormat(item, formatFilter) {
            const format = this.getFieldValue(item, 'format');

            // Normalize both values to lowercase for comparison
            const normalizedFilter = formatFilter.toLowerCase();

            if (Array.isArray(format)) {
                return format.some((f) => f.toLowerCase() === normalizedFilter);
            } else if (typeof format === 'string') {
                return format.toLowerCase() === normalizedFilter;
            }

            // For series/comics, check books
            const books = item[this.fieldMap.books];
            if (Array.isArray(books)) {
                return books.some((book) => book.file_format && book.file_format.toLowerCase() === normalizedFilter);
            }

            return false;
        }

        /**
         * Unified status matching
         */
        matchesStatus(item, statusFilter) {
            switch (statusFilter) {
                case 'read':
                    return this.isItemRead(item);
                case 'unread':
                    return !this.isItemRead(item);
                case 'reading':
                case 'listening':
                    return this.isItemInProgress(item);
                default:
                    return true;
            }
        }

        isItemRead(item) {
            if (item.is_read !== undefined) {
                return item.is_read;
            }

            // For series/comics, check if all books are read
            const books = item[this.fieldMap.books];
            if (Array.isArray(books)) {
                return books.length > 0 && books.every((book) => book.is_read);
            }

            return false;
        }

        isItemInProgress(item) {
            if (item.reading_progress > 0 || item.listening_progress > 0) {
                return !item.is_read;
            }

            // For series/comics, check if any books are in progress
            const books = item[this.fieldMap.books];
            if (Array.isArray(books)) {
                return books.some((book) => book.reading_progress > 0 && !book.is_read);
            }

            return false;
        }

        /**
         * UNIFIED SORTING METHOD
         * Works for all section types using field mapping
         */
        sortData(sortBy) {
            this.filteredData.sort((a, b) => {
                switch (sortBy) {
                    case 'title':
                        const titleA = this.getFieldValue(a, 'title');
                        const titleB = this.getFieldValue(b, 'title');
                        return titleA.localeCompare(titleB);

                    case 'author':
                        const authorA = this.getFieldValue(a, 'author');
                        const authorB = this.getFieldValue(b, 'author');
                        const authStrA = Array.isArray(authorA) ? authorA[0] || '' : authorA;
                        const authStrB = Array.isArray(authorB) ? authorB[0] || '' : authorB;
                        return authStrA.localeCompare(authStrB);

                    case 'date':
                        return this.compareDates(a, b);

                    case 'size':
                        return this.compareSizes(a, b);

                    case 'duration':
                        return (b.duration_seconds || 0) - (a.duration_seconds || 0);

                    default:
                        const defTitleA = this.getFieldValue(a, 'title');
                        const defTitleB = this.getFieldValue(b, 'title');
                        return defTitleA.localeCompare(defTitleB);
                }
            });
        }

        compareDates(a, b) {
            // For series/comics, compare most recent book
            const booksA = a[this.fieldMap.books];
            const booksB = b[this.fieldMap.books];

            if (Array.isArray(booksA) && Array.isArray(booksB)) {
                const aLatest = Math.max(...booksA.map((book) => new Date(book.last_scanned || 0)));
                const bLatest = Math.max(...booksB.map((book) => new Date(book.last_scanned || 0)));
                return bLatest - aLatest;
            }

            // For individual items
            return new Date(b.last_scanned || 0) - new Date(a.last_scanned || 0);
        }

        compareSizes(a, b) {
            // For series/comics, use total_size if available
            if (a.total_size !== undefined && b.total_size !== undefined) {
                return b.total_size - a.total_size;
            }

            // For individual items
            return (b.file_size || 0) - (a.file_size || 0);
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
            document.querySelectorAll('.list-item.selected').forEach((el) => {
                el.classList.remove('selected');
            });

            // Add selection to new item
            const newItem = document.querySelector(`[data-item-id="${itemId}"]`);
            if (newItem) {
                newItem.classList.add('selected');
            }
        }

        async loadDetail(itemId) {
            try {
                const container = document.querySelector(this.config.detailContainer);
                this.showLoadingState(container, 'Loading details...');

                const endpoint = this.config.detailEndpoint.replace('{id}', itemId).replace('0', itemId);
                const data = await fetch(endpoint, {
                    headers: { 'X-Requested-With': 'XMLHttpRequest' },
                }).then((r) => r.json());

                if (data.success) {
                    this.renderDetail(data);
                } else {
                    throw new Error(data.message || 'Failed to load details');
                }
            } catch (error) {
                console.error(`Error loading ${this.sectionType} details:`, error);
                const container = document.querySelector(this.config.detailContainer);
                this.showFriendlyEmptyState(
                    container,
                    'Unable to Load Details',
                    `There was a problem loading details. Please try again.`
                );
            }
        }

        renderDetail(data) {
            // Override in child classes
            console.warn('renderDetail method should be overridden in child classes');
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

        showFriendlyEmptyState(container, title, message) {
            const icon = this.getSectionIcon();
            if (typeof MediaLibraryUtils !== 'undefined' && MediaLibraryUtils.showEmptyState) {
                MediaLibraryUtils.showEmptyState(container, title, message, icon);
            } else {
                // Fallback if MediaLibraryUtils is not available
                container.innerHTML = `
                    <div class="empty-state text-center py-5">
                        <i class="${icon} fa-3x text-muted mb-3"></i>
                        <h5 class="text-muted">${title}</h5>
                        <p class="text-muted">${message}</p>
                    </div>
                `;
            }
        }

        getSectionIcon() {
            const icons = {
                ebooks: 'fas fa-book',
                audiobooks: 'fas fa-headphones',
                comics: 'fas fa-mask',
                series: 'fas fa-layer-group',
            };
            return icons[this.sectionType] || 'fas fa-inbox';
        }

        updateItemCount(count) {
            const countElement = document.getElementById('item-count');
            if (countElement) {
                countElement.textContent = count;
            }
        }

        getCurrentViewType() {
            // Check localStorage first (user override)
            let saved = localStorage.getItem(`${this.sectionType}-view-type`);
            if (saved) {
                return saved;
            }
            // Fall back to user profile default if available
            if (window.userDefaultViewMode) {
                return window.userDefaultViewMode;
            }
            // Final fallback to 'list'
            return 'list';
        }

        setViewType(viewType) {
            localStorage.setItem(`${this.sectionType}-view-type`, viewType);
        }

        getViewType() {
            return this.getCurrentViewType();
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
    };
}

// Global functions for backward compatibility
function customLoadItems() {
    const manager = getManagerForCurrentSection();
    if (manager && manager.loadData) {
        manager.loadData();
    }
}

function customFilterItems(searchTerm, sortBy, formatFilter, statusFilter) {
    const manager = getManagerForCurrentSection();
    if (manager && manager.filterItems) {
        manager.filterItems(searchTerm, sortBy, formatFilter, statusFilter);
    }
}

function customRenderView(viewType) {
    const manager = getManagerForCurrentSection();
    if (manager && manager.renderList) {
        manager.renderList(viewType);
    }
}

function customRefreshItems() {
    const manager = getManagerForCurrentSection();
    if (manager && manager.loadData) {
        manager.loadData();
    }
}

function customLoadDetail(itemId) {
    const manager = getManagerForCurrentSection();
    if (manager && manager.loadDetail) {
        manager.loadDetail(itemId);
    }
}

function selectItem(itemId) {
    const manager = getManagerForCurrentSection();
    if (manager && manager.selectItem) {
        manager.selectItem(itemId);
    }
}

function getManagerForCurrentSection() {
    const path = window.location.pathname;

    if (path.includes('/ebooks/')) return window.ebooksManager;
    if (path.includes('/comics/')) return window.comicsManager;
    if (path.includes('/audiobooks/')) return window.audiobooksManager;
    if (path.includes('/series/')) return window.seriesManager;

    return null;
}

// Export for global access
window.BaseSectionManager = BaseSectionManager;
window.SectionUtils = {
    customLoadItems,
    customFilterItems,
    customRenderView,
    customRefreshItems,
    customLoadDetail,
    selectItem,
    getManagerForCurrentSection,
};

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = BaseSectionManager;
}
