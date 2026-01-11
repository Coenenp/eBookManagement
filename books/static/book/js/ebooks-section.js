/**
 * Ebooks Section Manager - Handles ebook-specific functionality
 * Extends the BaseSectionManager for ebook browsing and management
 */
if (typeof EbooksSectionManager === 'undefined') {
    window.EbooksSectionManager = class EbooksSectionManager extends BaseSectionManager {
        constructor() {
            super('ebooks', {
                listContainer: '#ebooks-list-container',
                detailContainer: '#ebook-detail-container',
                apiEndpoint: window.ebooksConfig?.ajax_urls?.list || '/books/ebooks/ajax/list/',
                detailEndpoint: window.ebooksConfig?.ajax_urls?.detail || '/books/ebooks/ajax/detail/',
            });

            this.expandedEbooks = new Set();

            // Create safe utility accessors
            this.utils = this.getUtils();
        }

        getUtils() {
            // Helper to get utility functions with fallbacks
            const lib = window.EbookLibrary || {};

            return {
                escapeHtml:
                    lib.escapeHtml ||
                    ((str) => {
                        if (!str) return '';
                        const div = document.createElement('div');
                        div.textContent = str;
                        return div.innerHTML;
                    }),

                formatFileSize:
                    lib.formatFileSize ||
                    ((bytes) => {
                        if (!bytes) return '0 B';
                        const k = 1024;
                        const sizes = ['B', 'KB', 'MB', 'GB'];
                        const i = Math.floor(Math.log(bytes) / Math.log(k));
                        return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + ' ' + sizes[i];
                    }),

                formatDate:
                    lib.formatDate ||
                    ((dateStr) => {
                        if (!dateStr) return '';
                        try {
                            return new Date(dateStr).toLocaleDateString();
                        } catch {
                            return dateStr;
                        }
                    }),

                sanitizeHtml:
                    lib.sanitizeHtml ||
                    ((html) => {
                        // Basic sanitization - just escape
                        return this.utils.escapeHtml(html);
                    }),

                showToast:
                    lib.showToast ||
                    ((message, type = 'info') => {
                        console.log(`Toast [${type}]:`, message);
                    }),

                showLoadingState:
                    lib.showLoadingState ||
                    ((container, message = 'Loading...') => {
                        if (container) {
                            container.innerHTML = `<div class="text-center p-5"><div class="spinner-border" role="status"></div><p class="mt-3">${message}</p></div>`;
                        }
                    }),

                showEmptyState:
                    lib.showEmptyState ||
                    ((container, title, message, icon = 'fas fa-inbox') => {
                        if (container) {
                            container.innerHTML = `<div class="text-center p-5 text-muted"><i class="${icon} fa-3x mb-3"></i><h5>${title}</h5><p>${message}</p></div>`;
                        }
                    }),

                showErrorState:
                    lib.showErrorState ||
                    ((container, message) => {
                        if (container) {
                            container.innerHTML = `<div class="alert alert-danger m-3">${message}</div>`;
                        }
                    }),

                downloadFile:
                    lib.downloadFile ||
                    ((url, filename) => {
                        const a = document.createElement('a');
                        a.href = url;
                        a.download = filename || '';
                        a.click();
                    }),

                openFileLocation:
                    lib.openFileLocation ||
                    ((path) => {
                        console.log('Open file location:', path);
                        alert('File location: ' + path);
                    }),

                makeRequest:
                    lib.makeRequest ||
                    lib.Ajax?.makeRequest ||
                    lib.ajax?.makeRequest ||
                    (async (url, options) => {
                        const response = await fetch(url, options);
                        return await response.json();
                    }),
            };
        }

        bindEvents() {
            // Call parent's bindEvents to set up filter listeners
            super.bindEvents();

            // Bind ebook-specific events
            this.bindReadingProgressEvents();
            this.bindDownloadEvents();
            this.bindCompanionFileEvents();
            this.bindViewToggle();
            this.bindRefreshButton();
            this.bindFiltersToggle();
            this.bindClearSearch();
        }

        bindReadingProgressEvents() {
            // Handle reading progress updates
            document.addEventListener('click', (e) => {
                if (e.target.matches('.mark-read-btn')) {
                    e.preventDefault();
                    const ebookId = e.target.dataset.ebookId;
                    this.toggleReadStatus(ebookId);
                }
            });
        }

        bindDownloadEvents() {
            // Handle download actions
            document.addEventListener('click', (e) => {
                if (e.target.matches('.download-ebook-btn')) {
                    e.preventDefault();
                    const ebookId = e.target.dataset.ebookId;
                    const filename = e.target.dataset.filename;
                    this.downloadEbook(ebookId, filename);
                }
            });
        }

        bindCompanionFileEvents() {
            // Handle companion file operations
            document.addEventListener('click', (e) => {
                if (e.target.matches('.load-companion-files-btn')) {
                    e.preventDefault();
                    const ebookId = e.target.dataset.ebookId;
                    this.loadCompanionFiles(ebookId);
                }
            });
        }

        bindViewToggle() {
            // Handle view toggle buttons
            document.querySelectorAll('.view-toggle-btn').forEach((btn) => {
                btn.addEventListener('click', (e) => {
                    // Remove active class from all buttons
                    document.querySelectorAll('.view-toggle-btn').forEach((b) => b.classList.remove('active'));
                    // Add active class to clicked button
                    e.currentTarget.classList.add('active');

                    // Get view type and render
                    const viewType = e.currentTarget.dataset.view;
                    this.renderList(viewType);
                });
            });
        }

        bindRefreshButton() {
            const refreshBtn = document.querySelector('.refresh-btn');
            if (refreshBtn) {
                refreshBtn.addEventListener('click', async () => {
                    refreshBtn.disabled = true;
                    refreshBtn.innerHTML = '<i class="fas fa-sync-alt fa-spin me-1"></i>Refreshing...';

                    try {
                        await this.loadData();
                        this.renderList();
                        MediaLibraryUtils.showToast('Ebooks refreshed', 'success');
                    } catch (error) {
                        MediaLibraryUtils.showToast('Failed to refresh ebooks', 'error');
                    } finally {
                        refreshBtn.disabled = false;
                        refreshBtn.innerHTML = '<i class="fas fa-sync-alt me-1"></i>Refresh';
                    }
                });
            }
        }

        bindFiltersToggle() {
            const filtersBtn = document.querySelector('.filters-btn');
            const advancedFilters = document.getElementById('advanced-filters');

            if (filtersBtn && advancedFilters) {
                filtersBtn.addEventListener('click', () => {
                    advancedFilters.classList.toggle('d-none');
                    const icon = filtersBtn.querySelector('i');
                    if (advancedFilters.classList.contains('d-none')) {
                        icon.className = 'fas fa-filter me-1';
                    } else {
                        icon.className = 'fas fa-filter-slash me-1';
                    }
                });
            }
        }

        bindClearSearch() {
            const searchInput = document.getElementById('search-filter');
            const clearBtn = document.getElementById('clear-search');

            if (searchInput && clearBtn) {
                // Show/hide clear button based on input
                searchInput.addEventListener('input', () => {
                    if (searchInput.value.trim()) {
                        clearBtn.style.display = 'block';
                    } else {
                        clearBtn.style.display = 'none';
                    }
                });

                // Clear search on click
                clearBtn.addEventListener('click', () => {
                    searchInput.value = '';
                    clearBtn.style.display = 'none';
                    // Trigger filter update
                    if (this.applyFilters) {
                        this.applyFilters();
                    }
                });
            }
        }

        async loadData() {
            try {
                // Use EbookLibrary directly since MediaLibraryUtils is just an alias
                const utils = window.MediaLibraryUtils || window.EbookLibrary;

                if (!utils) {
                    throw new Error('Neither MediaLibraryUtils nor EbookLibrary is available');
                }

                // Check all possible locations for makeRequest
                const makeRequest = utils.makeRequest || utils.Ajax?.makeRequest || utils.ajax?.makeRequest;

                if (typeof makeRequest !== 'function') {
                    console.error('Available utils properties:', Object.keys(utils));
                    throw new Error('makeRequest function not found in utils object');
                }

                console.log('Loading ebooks from:', this.config.apiEndpoint);
                const response = await makeRequest(this.config.apiEndpoint);

                console.log('Ebooks loaded:', response);

                if (response.success && response.ebooks) {
                    this.currentData = response.ebooks;
                    this.filteredData = [...this.currentData];

                    // Update count badge
                    const countBadge = document.getElementById('item-count');
                    if (countBadge) {
                        countBadge.textContent = this.currentData.length;
                    }

                    console.log(`Loaded ${this.currentData.length} ebooks`);

                    // Render the list after loading data
                    this.renderList();

                    return this.currentData;
                } else {
                    throw new Error(response.error || 'Failed to load ebooks');
                }
            } catch (error) {
                console.error('Error loading ebooks:', error);
                throw error;
            }
        }

        renderList(viewType = null) {
            console.log(
                'renderList called with viewType:',
                viewType,
                'filtered data length:',
                this.filteredData.length
            );

            const container = document.querySelector(this.config.listContainer);
            if (!container) {
                console.error('List container not found:', this.config.listContainer);
                return;
            }

            const currentView = viewType || this.getCurrentViewType();
            const dataToRender = this.filteredData;

            if (dataToRender.length === 0) {
                if (window.MediaLibraryUtils && typeof window.MediaLibraryUtils.showEmptyState === 'function') {
                    MediaLibraryUtils.showEmptyState(
                        container,
                        'No Ebooks Found',
                        'No ebooks match your current filters.',
                        'fas fa-book'
                    );
                } else {
                    container.innerHTML = '<div class="text-center p-5"><p>No ebooks found</p></div>';
                }
                return;
            }

            console.log('Rendering', dataToRender.length, 'ebooks in', currentView, 'view');

            let html = '';

            if (currentView === 'grid') {
                html = this.renderGridView(dataToRender);
            } else {
                html = this.renderListView(dataToRender);
            }

            container.innerHTML = html;
            container.classList.add('fade-in');

            console.log('List rendered successfully');

            // Initialize reading progress bars
            this.initializeReadingProgressBars();
        }

        renderGridView(ebooksData) {
            return ebooksData
                .map(
                    (ebook) => `
                <div class="list-item grid-item" data-item-id="${ebook.id}" onclick="window.ebookManager.selectItem(${ebook.id})">
                    <div class="grid-cover mb-3">
                        ${
                            ebook.cover_url
                                ? `
                            <img src="${ebook.cover_url}" alt="Book Cover" class="img-fluid rounded shadow">
                        `
                                : `
                            <div class="placeholder-cover d-flex align-items-center justify-content-center bg-light rounded">
                                <i class="fas fa-book text-muted fa-2x"></i>
                            </div>
                        `
                        }
                        ${
                            ebook.reading_progress > 0
                                ? `
                            <div class="reading-progress mt-2">
                                <div class="reading-progress-bar" data-width="${ebook.reading_progress}"></div>
                            </div>
                        `
                                : ''
                        }
                    </div>
                    <div class="item-title">${this.utils.escapeHtml(ebook.title)}</div>
                    <div class="item-subtitle">${this.utils.escapeHtml(ebook.author)}</div>
                    <div class="item-meta">
                        <div class="item-badges">
                            <span class="badge bg-secondary">${ebook.file_format.toUpperCase()}</span>
                            ${ebook.is_read ? '<span class="badge bg-success">Read</span>' : ''}
                        </div>
                        <div class="text-muted small mt-1">
                            ${this.utils.formatFileSize(ebook.file_size)}
                        </div>
                    </div>
                </div>
            `
                )
                .join('');
        }

        renderListView(ebooksData) {
            // Condensed table view with expandable rows for companion files
            const tableHtml = `
                <div class="condensed-table-container">
                    <table class="condensed-table">
                        <thead>
                            <tr>
                                <th style="width: 30px;"></th>
                                <th class="col-title" data-sort="title">
                                    Title <i class="fas fa-sort sort-icon"></i>
                                </th>
                                <th class="col-author" data-sort="author">
                                    Author(s) <i class="fas fa-sort sort-icon"></i>
                                </th>
                                <th class="col-series" data-sort="series">
                                    Series <i class="fas fa-sort sort-icon"></i>
                                </th>
                                <th class="col-publisher" data-sort="publisher">
                                    Publisher <i class="fas fa-sort sort-icon"></i>
                                </th>
                                <th class="col-format" data-sort="format">
                                    Format <i class="fas fa-sort sort-icon"></i>
                                </th>
                                <th class="col-size" data-sort="size">
                                    Size <i class="fas fa-sort sort-icon"></i>
                                </th>
                                <th class="col-year" data-sort="year">
                                    Year <i class="fas fa-sort sort-icon"></i>
                                </th>
                                <th class="col-language" data-sort="language">
                                    Lang <i class="fas fa-sort sort-icon"></i>
                                </th>
                                <th class="col-path" data-sort="path">
                                    Path <i class="fas fa-sort sort-icon"></i>
                                </th>
                                <th class="col-status">Status</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${ebooksData
                                .map(
                                    (ebook) => `
                                <tr class="${this.selectedItemId === ebook.id ? 'selected' : ''} ${this.expandedEbooks.has(ebook.id) ? 'expanded' : ''}" 
                                    data-item-id="${ebook.id}">
                                    <td style="cursor: pointer; text-align: center;" onclick="event.stopPropagation(); window.ebookManager.toggleEbook(${ebook.id})">
                                        <i class="fas fa-chevron-right expand-icon" style="transition: transform 0.2s; ${this.expandedEbooks.has(ebook.id) ? 'transform: rotate(90deg);' : ''}"></i>
                                    </td>
                                    <td class="col-title truncate" title="${this.utils.escapeHtml(ebook.title)}" onclick="window.ebookManager.selectItem(${ebook.id})" style="cursor: pointer;">
                                        <i class="fas fa-book file-icon"></i>
                                        ${this.utils.escapeHtml(ebook.title)}
                                    </td>
                                    <td class="col-author truncate" title="${this.utils.escapeHtml(ebook.author || '')}" onclick="window.ebookManager.selectItem(${ebook.id})" style="cursor: pointer;">
                                        ${this.utils.escapeHtml(ebook.author || '-')}
                                    </td>
                                    <td class="col-series truncate" title="${this.utils.escapeHtml(ebook.series || '')}" onclick="window.ebookManager.selectItem(${ebook.id})" style="cursor: pointer;">
                                        ${this.utils.escapeHtml(ebook.series || '-')}
                                    </td>
                                    <td class="col-publisher truncate" title="${this.utils.escapeHtml(ebook.publisher || '')}" onclick="window.ebookManager.selectItem(${ebook.id})" style="cursor: pointer;">
                                        ${this.utils.escapeHtml(ebook.publisher || '-')}
                                    </td>
                                    <td class="col-format" onclick="window.ebookManager.selectItem(${ebook.id})" style="cursor: pointer;">
                                        <span class="badge bg-secondary">${(ebook.file_format || '').toUpperCase()}</span>
                                    </td>
                                    <td class="col-size" onclick="window.ebookManager.selectItem(${ebook.id})" style="cursor: pointer;">${this.utils.formatFileSize(ebook.file_size)}</td>
                                    <td class="col-year" onclick="window.ebookManager.selectItem(${ebook.id})" style="cursor: pointer;">${ebook.publication_year || '-'}</td>
                                    <td class="col-language" onclick="window.ebookManager.selectItem(${ebook.id})" style="cursor: pointer;">${(ebook.language || 'en').toUpperCase()}</td>
                                    <td class="col-path truncate" title="${this.utils.escapeHtml(ebook.file_path || ebook.scan_folder || '')}" onclick="window.ebookManager.selectItem(${ebook.id})" style="cursor: pointer;">
                                        ${this.utils.escapeHtml(this.getShortPath(ebook.file_path || ebook.scan_folder || ''))}
                                    </td>
                                    <td class="col-status" onclick="window.ebookManager.selectItem(${ebook.id})" style="cursor: pointer;">
                                        ${
                                            ebook.is_read
                                                ? '<span class="badge bg-success" title="Read">✓</span>'
                                                : ebook.reading_progress > 0
                                                  ? '<span class="badge bg-warning" title="Reading">📖</span>'
                                                  : '<span class="badge bg-secondary" title="Unread">○</span>'
                                        }
                                    </td>
                                </tr>
                                ${this.expandedEbooks.has(ebook.id) ? this.renderCompanionFilesRow(ebook) : ''}
                            `
                                )
                                .join('')}
                        </tbody>
                    </table>
                </div>
            `;

            return tableHtml;
        }

        renderCompanionFilesRow(ebook) {
            if (!ebook.companion_files || ebook.companion_files.length === 0) {
                return `
                    <tr class="companion-row">
                        <td></td>
                        <td colspan="10" style="padding-left: 40px; font-size: 0.75rem; color: var(--bs-secondary);">
                            <i class="fas fa-info-circle me-2"></i>No companion files found
                        </td>
                    </tr>
                `;
            }

            return ebook.companion_files
                .map(
                    (file) => `
                <tr class="companion-row" style="background-color: var(--bs-secondary-bg);">
                    <td></td>
                    <td colspan="10" style="padding-left: 40px; font-size: 0.75rem;">
                        <i class="fas fa-file me-2" style="color: var(--bs-secondary);"></i>
                        <span style="font-family: monospace;">${this.utils.escapeHtml(file.name)}</span>
                        <span class="badge bg-info ms-2">${file.type.toUpperCase()}</span>
                        <span class="text-muted ms-2">${this.utils.formatFileSize(file.size)}</span>
                    </td>
                </tr>
            `
                )
                .join('');
        }

        getShortPath(fullPath) {
            // Extract just the filename and parent folder for display
            if (!fullPath) return '-';
            const parts = fullPath.replace(/\\/g, '/').split('/');
            if (parts.length > 2) {
                return '.../' + parts.slice(-2).join('/');
            }
            return fullPath;
        }

        renderCompanionFilesInline(ebook) {
            if (!ebook.companion_files || ebook.companion_files.length === 0) {
                return `
                    <div class="companion-files-container">
                        <div class="list-item companion-file-item ms-4 text-muted">
                            <small><i class="fas fa-info-circle me-2"></i>No companion files found</small>
                        </div>
                    </div>
                `;
            }

            return `
                <div class="companion-files-container">
                    ${ebook.companion_files
                        .map(
                            (file) => `
                        <div class="list-item companion-file-item ms-4" 
                             onclick="event.stopPropagation(); window.ebookManager.selectItem(${ebook.id})">
                            <div class="companion-file-details">
                                <div class="d-flex justify-content-between align-items-center">
                                    <div>
                                        <div class="file-name">
                                            <i class="fas fa-file me-2"></i>
                                            ${MediaLibraryUtils.escapeHtml(file.name)}
                                        </div>
                                        <small class="text-muted">${file.type} • ${MediaLibraryUtils.formatFileSize(file.size)}</small>
                                    </div>
                                    <div class="file-actions">
                                        <button class="btn btn-sm btn-outline-primary me-1" 
                                                onclick="event.stopPropagation(); window.ebookManager.downloadCompanionFile('${file.path}')" 
                                                title="Download file">
                                            <i class="fas fa-download"></i>
                                        </button>
                                        <button class="btn btn-sm btn-outline-secondary" 
                                                onclick="event.stopPropagation(); window.ebookManager.showFileLocation('${file.path}')" 
                                                title="Show in folder">
                                            <i class="fas fa-folder-open"></i>
                                        </button>
                                    </div>
                                </div>
                            </div>
                        </div>
                    `
                        )
                        .join('')}
                </div>
            `;
        }

        toggleEbook(ebookId) {
            // Ensure ebookId is a number for consistent Set comparison
            const id = parseInt(ebookId, 10);
            if (this.expandedEbooks.has(id)) {
                this.expandedEbooks.delete(id);
            } else {
                this.expandedEbooks.add(id);
                // Load companion files if not already loaded
                this.loadCompanionFiles(id);
            }
            this.renderList();
        }

        downloadCompanionFile(filePath) {
            const urls = window.ebooksConfig?.ajax_urls;
            if (!urls?.companion_files) {
                this.showToast('Download functionality not available', 'warning');
                return;
            }

            // In a real implementation, this would trigger the download
            this.showToast('Downloading companion file...', 'info');
        }

        showFileLocation(filePath) {
            // Copy path to clipboard as a fallback
            navigator.clipboard
                .writeText(filePath)
                .then(() => {
                    this.showToast('File path copied to clipboard', 'info');
                })
                .catch(() => {
                    this.showToast('Unable to copy path to clipboard', 'warning');
                });
        }

        getCurrentViewType() {
            const activeBtn = document.querySelector('.view-toggle-btn.active');
            return activeBtn ? activeBtn.dataset.view : 'list';
        }

        initializeReadingProgressBars() {
            // Animate reading progress bars
            document.querySelectorAll('.reading-progress-bar').forEach((bar) => {
                const width = bar.dataset.width || 0;
                setTimeout(() => {
                    bar.style.width = width + '%';
                }, 100);
            });
        }

        async loadDetail(ebookId) {
            try {
                const container = document.querySelector(this.config.detailContainer);
                this.utils.showLoadingState(container, 'Loading ebook details...');

                const url = this.config.detailEndpoint.replace('{id}', ebookId);
                const data = await this.utils.makeRequest(url);

                if (data.success) {
                    this.renderDetail(data.ebook);
                } else {
                    throw new Error(data.error || 'Failed to load ebook details');
                }

                // Handle mobile layout
                if (window.innerWidth <= 768 && window.SplitPane) {
                    window.SplitPane.handleMobileLayout();
                    window.SplitPane.addMobileBackButton();
                }
            } catch (error) {
                console.error('Error loading ebook detail:', error);
                const container = document.querySelector(this.config.detailContainer);

                let errorMessage = `Error loading ebook details: ${error.message}`;
                if (error.message.includes('Authentication')) {
                    errorMessage += '<br><a href="/login/" class="btn btn-primary btn-sm mt-2">Login</a>';
                }

                this.utils.showErrorState(container, errorMessage);
            }
        }

        renderDetail(ebook) {
            const container = document.querySelector(this.config.detailContainer);

            const html = `
                <div class="ebook-detail-wrapper h-100">
                    <!-- Header with book title and cover -->
                    <div class="detail-header p-3 border-bottom bg-white sticky-top">
                        <div class="row align-items-center">
                            <div class="col-auto">
                                <div class="detail-cover-small">
                                    ${
                                        ebook.cover_url
                                            ? `
                                        <img src="${ebook.cover_url}" alt="Book Cover" class="img-fluid rounded shadow-sm">
                                    `
                                            : `
                                        <div class="placeholder-cover d-flex align-items-center justify-content-center bg-light rounded">
                                            <i class="fas fa-book text-muted"></i>
                                        </div>
                                    `
                                    }
                                </div>
                            </div>
                            <div class="col">
                                <h4 class="mb-1">${MediaLibraryUtils.escapeHtml(ebook.title)}</h4>
                                <p class="text-muted mb-0">
                                    <i class="fas fa-user me-1"></i>${MediaLibraryUtils.escapeHtml(ebook.author)}
                                </p>
                                ${
                                    ebook.reading_progress > 0
                                        ? `
                                    <div class="progress mt-2" style="height: 6px;">
                                        <div class="progress-bar bg-success" style="width: ${ebook.reading_progress}%"></div>
                                    </div>
                                    <small class="text-muted">${ebook.reading_progress}% complete</small>
                                `
                                        : ''
                                }
                            </div>
                            <div class="col-auto">
                                <div class="btn-group" role="group">
                                    <button type="button" class="btn btn-outline-primary btn-sm download-ebook-btn" 
                                            data-ebook-id="${ebook.id}" data-filename="${MediaLibraryUtils.escapeHtml(ebook.filename)}">
                                        <i class="fas fa-download me-1"></i>Download
                                    </button>
                                    <button type="button" class="btn btn-outline-secondary btn-sm mark-read-btn" 
                                            data-ebook-id="${ebook.id}">
                                        <i class="fas fa-${ebook.is_read ? 'times' : 'check'} me-1"></i>
                                        ${ebook.is_read ? 'Mark Unread' : 'Mark Read'}
                                    </button>
                                </div>
                            </div>
                        </div>
                        <div class="row mt-2">
                            <div class="col">
                                <a href="/book/${ebook.id}/" class="btn btn-primary btn-sm w-100">
                                    <i class="fas fa-eye me-1"></i>View Full Details
                                </a>
                            </div>
                        </div>
                    </div>

                    <!-- Tabbed content area -->
                    <div class="detail-content flex-fill">
                        <ul class="nav nav-tabs nav-fill" id="ebookDetailTabs" role="tablist">
                            <li class="nav-item" role="presentation">
                                <button class="nav-link active" id="info-tab" data-bs-toggle="tab" data-bs-target="#info" type="button" role="tab">
                                    <i class="fas fa-info-circle me-1"></i>Info
                                </button>
                            </li>
                            <li class="nav-item" role="presentation">
                                <button class="nav-link" id="metadata-tab" data-bs-toggle="tab" data-bs-target="#metadata" type="button" role="tab">
                                    <i class="fas fa-tags me-1"></i>Meta
                                </button>
                            </li>
                            <li class="nav-item" role="presentation">
                                <button class="nav-link" id="files-tab" data-bs-toggle="tab" data-bs-target="#files" type="button" role="tab">
                                    <i class="fas fa-folder me-1"></i>Files
                                </button>
                            </li>
                        </ul>
                        
                        <div class="tab-content h-100">
                            <!-- Information Tab -->
                            <div class="tab-pane fade show active h-100" id="info" role="tabpanel">
                                <div class="p-3">
                                    ${this.renderInformationTab(ebook)}
                                </div>
                            </div>
                            
                            <!-- Metadata Tab -->
                            <div class="tab-pane fade h-100" id="metadata" role="tabpanel">
                                <div class="p-3">
                                    ${this.renderMetadataTab(ebook)}
                                </div>
                            </div>
                            
                            <!-- Files Tab -->
                            <div class="tab-pane fade h-100" id="files" role="tabpanel">
                                <div class="p-3">
                                    ${this.renderFilesTab(ebook)}
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            `;

            container.innerHTML = html;

            // Initialize tab functionality
            this.initializeDetailTabs();
        }

        renderInformationTab(ebook) {
            const formatYear = (dateStr) => {
                if (!dateStr) return null;
                try {
                    const date = new Date(dateStr);
                    const year = date.getFullYear();
                    // Filter out invalid years (Unix epoch 1970, future dates, etc.)
                    if (year <= 1970 || year > new Date().getFullYear() + 5) return null;
                    return year;
                } catch {
                    return null;
                }
            };

            const getFileFormat = () => {
                if (ebook.file_format) return ebook.file_format.toUpperCase();
                if (ebook.file_path) {
                    const ext = ebook.file_path.split('.').pop();
                    return ext ? ext.toUpperCase() : null;
                }
                return null;
            };

            const getLanguageName = (code) => {
                if (!code) return null;
                const languages = {
                    en: 'English',
                    de: 'German',
                    fr: 'French',
                    es: 'Spanish',
                    it: 'Italian',
                    nl: 'Dutch',
                    pt: 'Portuguese',
                    ru: 'Russian',
                    ja: 'Japanese',
                    zh: 'Chinese',
                    ko: 'Korean',
                    ar: 'Arabic',
                    pl: 'Polish',
                    sv: 'Swedish',
                    da: 'Danish',
                    no: 'Norwegian',
                    fi: 'Finnish',
                    tr: 'Turkish',
                    el: 'Greek',
                    cs: 'Czech',
                    hu: 'Hungarian',
                    ro: 'Romanian',
                };
                return languages[code.toLowerCase()] || code;
            };

            const fileFormat = getFileFormat();
            const pubYear = formatYear(ebook.publication_date);
            const languageName = getLanguageName(ebook.language);

            // Split file path into scan folder and relative path
            const getPathParts = () => {
                if (!ebook.file_path) return null;

                const fullPath = ebook.file_path;
                const scanFolderPath = ebook.scan_folder_path || '';

                if (scanFolderPath && fullPath.startsWith(scanFolderPath)) {
                    // Extract relative path
                    let relativePath = fullPath.substring(scanFolderPath.length);
                    // Remove leading slashes/backslashes
                    relativePath = relativePath.replace(/^[\/\\]+/, '');

                    // Split into directory and filename
                    const lastSeparator = Math.max(relativePath.lastIndexOf('/'), relativePath.lastIndexOf('\\'));
                    const filename = lastSeparator >= 0 ? relativePath.substring(lastSeparator + 1) : relativePath;
                    const directory = lastSeparator >= 0 ? relativePath.substring(0, lastSeparator) : '';

                    return {
                        scanFolder: ebook.scan_folder_name || scanFolderPath,
                        directory: directory,
                        filename: filename,
                    };
                }

                // Fallback if no scan folder match
                const lastSeparator = Math.max(fullPath.lastIndexOf('/'), fullPath.lastIndexOf('\\'));
                return {
                    scanFolder: null,
                    directory: lastSeparator >= 0 ? fullPath.substring(0, lastSeparator) : '',
                    filename: lastSeparator >= 0 ? fullPath.substring(lastSeparator + 1) : fullPath,
                };
            };

            const pathParts = getPathParts();

            // Helper for confidence/completeness badges
            const getQualityBadge = (value) => {
                const percent = Math.round(value * 100);
                const colorClass = percent >= 80 ? 'bg-success' : percent >= 50 ? 'bg-warning' : 'bg-danger';
                return `<span class="badge ${colorClass}">${percent}%</span>`;
            };

            const getFormatColor = (format) => {
                const fmt = format.toUpperCase();
                if (fmt === 'EPUB') return 'bg-primary';
                if (fmt === 'PDF') return 'bg-danger';
                if (['MOBI', 'AZW', 'AZW3'].includes(fmt)) return 'bg-success';
                if (['CBZ', 'CBR', 'CB7', 'CBT'].includes(fmt)) return 'bg-warning';
                if (['MP3', 'M4A', 'M4B', 'AAC', 'OGG'].includes(fmt)) return 'bg-info';
                return 'bg-secondary';
            };

            const getSourceIcon = (source) => {
                if (!source) return 'fa-question';
                const src = source.toLowerCase();
                if (src.includes('ai') || src.includes('gpt') || src.includes('gemini')) return 'fa-robot';
                if (src.includes('filename') || src.includes('file')) return 'fa-file';
                if (src.includes('embedded') || src.includes('metadata')) return 'fa-book-open';
                if (src.includes('google') || src.includes('openlibrary') || src.includes('api')) return 'fa-cloud';
                if (src.includes('manual') || src.includes('user')) return 'fa-user';
                return 'fa-database';
            };

            return `
                <div class="ebook-info-content">
                    <div class="row g-3">
                        <div class="col-12">
                        ${ebook.publisher ? `<div class="mb-2"><i class="fas fa-building me-2 text-muted"></i><strong>Publisher:</strong> ${MediaLibraryUtils.escapeHtml(ebook.publisher)}</div>` : ''}
                        
                        <!-- Publication Year -->
                        ${pubYear ? `<div class="mb-2"><i class="fas fa-calendar me-2 text-muted"></i><strong>Year:</strong> ${pubYear}</div>` : ''}
                        
                        <!-- Language -->
                        ${languageName ? `<div class="mb-2"><i class="fas fa-language me-2 text-muted"></i><strong>Language:</strong> ${MediaLibraryUtils.escapeHtml(languageName)}</div>` : ''}
                        
                        <!-- Format & File Size (together) -->
                        ${fileFormat || (ebook.file_size && ebook.file_size > 0) ? `<div class="mb-2"><i class="fas fa-file-alt me-2 text-muted"></i><strong>Format & Size:</strong> ${fileFormat ? `<span class="badge ${getFormatColor(ebook.file_format)}">${fileFormat}</span>` : ''} ${ebook.file_size && ebook.file_size > 0 ? MediaLibraryUtils.formatFileSize(ebook.file_size) : ''}</div>` : ''}
                        
                        <!-- ISBN -->
                        ${ebook.isbn ? `<div class="mb-2"><i class="fas fa-barcode me-2 text-muted"></i><strong>ISBN:</strong> ${MediaLibraryUtils.escapeHtml(ebook.isbn)}</div>` : ''}
                        
                        <!-- Scan Folder & Path -->
                        ${
                            pathParts
                                ? `
                        <div class="mb-2">
                            ${pathParts.scanFolder && ebook.scan_folder_id ? `<div class="mb-1"><i class="fas fa-hdd me-2 text-muted"></i><strong>Scan Folder:</strong> <a href="/scan_folders/${ebook.scan_folder_id}/edit/" class="text-primary text-decoration-none">${MediaLibraryUtils.escapeHtml(pathParts.scanFolder)}</a></div>` : pathParts.scanFolder ? `<div class="mb-1"><i class="fas fa-hdd me-2 text-muted"></i><strong>Scan Folder:</strong> ${MediaLibraryUtils.escapeHtml(pathParts.scanFolder)}</div>` : ''}
                            ${pathParts.directory ? `<div class="mb-1"><i class="fas fa-folder me-2 text-muted"></i><strong>Path:</strong> <code class="small">${MediaLibraryUtils.escapeHtml(pathParts.directory)}</code></div>` : ''}
                            <div class="d-flex align-items-center">
                                <div class="flex-grow-1"><i class="fas fa-file me-2 text-muted"></i><strong>Filename:</strong> <code class="small fw-bold">${MediaLibraryUtils.escapeHtml(pathParts.filename)}</code></div>
                                <button type="button" class="btn btn-outline-secondary btn-sm ms-2" onclick="MediaLibraryUtils.openFileLocation(decodeURIComponent('${encodeURIComponent(ebook.file_path)}'))" title="Open file location">
                                    <i class="fas fa-folder-open"></i>
                                </button>
                            </div>
                        </div>
                        `
                                : ''
                        }
                        
                        <!-- Last Scanned -->
                        ${ebook.last_scanned ? `<div class="mb-2"><i class="fas fa-clock me-2 text-muted"></i><strong>Last Scanned:</strong> ${MediaLibraryUtils.formatDate(ebook.last_scanned)}</div>` : ''}
                        
                        <!-- Confidence Score -->
                        ${ebook.confidence !== undefined && ebook.confidence !== null ? `<div class="mb-2"><strong>Confidence:</strong> ${getQualityBadge(ebook.confidence)}</div>` : ''}
                        
                        <!-- Completeness Score -->
                        ${ebook.completeness !== undefined && ebook.completeness !== null ? `<div class="mb-2"><strong>Completeness:</strong> ${getQualityBadge(ebook.completeness)}</div>` : ''}
                        
                        <!-- Reading Status -->
                        <div class="mb-2"><strong>Reading Status:</strong> 
                            ${
                                ebook.is_read
                                    ? '<span class="badge bg-success">Read</span>'
                                    : ebook.reading_progress > 0
                                      ? '<span class="badge bg-warning">Reading</span>'
                                      : '<span class="badge bg-secondary">Unread</span>'
                            }
                        </div>
                    </div>
                    
                    ${
                        ebook.description
                            ? `
                        <div class="mt-4">
                            <strong>Description:</strong>
                            <div class="description-content mt-2">
                                ${MediaLibraryUtils.sanitizeHtml(ebook.description)}
                            </div>
                        </div>
                    `
                            : ''
                    }
                </div>
            `;
        }

        renderMetadataTab(ebook) {
            const metadata = ebook.metadata || [];

            return `
                <div class="metadata-grid">
                    <h6 class="fw-bold mb-3">Metadata Sources</h6>
                    ${
                        metadata.length > 0
                            ? `
                        <div class="table-responsive">
                            <table class="table table-sm table-hover">
                                <thead>
                                    <tr>
                                        <th>Source</th>
                                        <th>Field</th>
                                        <th>Value</th>
                                        <th>Confidence</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    ${metadata
                                        .map(
                                            (meta) => `
                                        <tr class="${meta.is_active ? 'table-success' : ''}">
                                            <td><span class="badge bg-info">${MediaLibraryUtils.escapeHtml(meta.source)}</span></td>
                                            <td><strong>${this.formatMetadataKey(meta.field_name)}</strong></td>
                                            <td>${MediaLibraryUtils.escapeHtml(String(meta.field_value))}</td>
                                            <td>${meta.confidence ? (meta.confidence * 100).toFixed(0) + '%' : 'N/A'}</td>
                                        </tr>
                                    `
                                        )
                                        .join('')}
                                </tbody>
                            </table>
                        </div>
                    `
                            : '<p class="text-muted">No metadata sources available</p>'
                    }
                    
                    ${
                        ebook.file_path
                            ? `
                        <hr class="my-4">
                        <h6 class="fw-bold mb-3">File Location</h6>
                        <div class="info-item">
                            <div class="d-flex align-items-center justify-content-between">
                                <code class="small text-muted flex-grow-1 me-2">${MediaLibraryUtils.escapeHtml(ebook.file_path)}</code>
                                <button type="button" class="btn btn-outline-secondary btn-sm" onclick="MediaLibraryUtils.openFileLocation('${MediaLibraryUtils.escapeHtml(ebook.file_path)}')">
                                    <i class="fas fa-folder-open me-1"></i>Open Location
                                </button>
                            </div>
                        </div>
                    `
                            : ''
                    }
                </div>
            `;
        }

        renderFilesTab(ebook) {
            return `
                <div class="files-content">
                    <div class="d-flex justify-content-between align-items-center mb-3">
                        <h6 class="fw-bold mb-0">Companion Files</h6>
                        <button type="button" class="btn btn-outline-primary btn-sm load-companion-files-btn" 
                                data-ebook-id="${ebook.id}">
                            <i class="fas fa-sync me-1"></i>Load Files
                        </button>
                    </div>
                    
                    <div id="companion-files-container">
                        <div class="text-center text-muted p-4">
                            <i class="fas fa-folder-open fa-2x mb-2"></i>
                            <p>Click "Load Files" to scan for companion files in the same directory.</p>
                        </div>
                    </div>
                </div>
            `;
        }

        formatMetadataKey(key) {
            return key.replace(/_/g, ' ').replace(/\b\w/g, (l) => l.toUpperCase());
        }

        initializeDetailTabs() {
            // Bootstrap tab functionality is already included
            // Add any custom tab event handlers here if needed
        }

        async toggleReadStatus(ebookId) {
            try {
                // Get CSRF token from cookie
                const csrfToken = this.getCsrfToken();

                const url = window.ebooksConfig?.ajax_urls?.toggle_read || '/books/ebooks/ajax/toggle_read/';
                const data = await MediaLibraryUtils.makeRequest(url, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': csrfToken,
                    },
                    body: JSON.stringify({
                        book_id: ebookId,
                    }),
                });

                if (data.success) {
                    MediaLibraryUtils.showToast(`Ebook marked as ${data.is_read ? 'read' : 'unread'}`, 'success');

                    // Update the item in current data
                    const item = this.currentData.find((e) => e.id == ebookId);
                    if (item) {
                        item.is_read = data.is_read;
                    }

                    // Update filtered data as well
                    const filteredItem = this.filteredData.find((e) => e.id == ebookId);
                    if (filteredItem) {
                        filteredItem.is_read = data.is_read;
                    }

                    // Refresh the detail view if this item is selected - reload from server
                    if (this.selectedItem && this.selectedItem.id == ebookId) {
                        // Reload the detail from the server to get fresh data
                        await this.loadDetail(ebookId);
                    }

                    // Refresh the list view
                    this.renderList();
                } else {
                    throw new Error(data.error || 'Failed to update reading status');
                }
            } catch (error) {
                console.error('Error toggling read status:', error);
                MediaLibraryUtils.showToast('Failed to update reading status', 'error');
            }
        }

        getCsrfToken() {
            // Try to get from meta tag first
            const metaTag = document.querySelector('meta[name="csrf-token"]');
            if (metaTag) {
                return metaTag.getAttribute('content');
            }

            // Fallback to cookie
            const name = 'csrftoken';
            let cookieValue = null;
            if (document.cookie && document.cookie !== '') {
                const cookies = document.cookie.split(';');
                for (let i = 0; i < cookies.length; i++) {
                    const cookie = cookies[i].trim();
                    if (cookie.substring(0, name.length + 1) === name + '=') {
                        cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                        break;
                    }
                }
            }
            return cookieValue;
        }

        downloadEbook(ebookId, filename) {
            try {
                const downloadUrl =
                    window.ebooksConfig?.ajax_urls?.download?.replace('0', ebookId) ||
                    `/books/ebooks/ajax/download/${ebookId}/`;
                MediaLibraryUtils.downloadFile(downloadUrl, filename);
                MediaLibraryUtils.showToast('Download started', 'success');
            } catch (error) {
                console.error('Error downloading ebook:', error);
                MediaLibraryUtils.showToast('Failed to start download', 'error');
            }
        }

        async loadCompanionFiles(ebookId) {
            try {
                const container = document.getElementById('companion-files-container');
                this.utils.showLoadingState(container, 'Scanning for companion files...');

                const url =
                    window.ebooksConfig?.ajax_urls?.companion_files?.replace('{id}', ebookId) ||
                    `/ebooks/ajax/companion_files/${ebookId}/`;
                const data = await this.utils.makeRequest(url);

                if (data.success) {
                    this.renderCompanionFiles(data.files);
                } else {
                    throw new Error(data.message || 'Failed to load companion files');
                }
            } catch (error) {
                console.error('Error loading companion files:', error);
                const container = document.getElementById('companion-files-container');
                this.utils.showErrorState(container, 'Failed to load companion files');
            }
        }

        renderCompanionFiles(files) {
            const container = document.getElementById('companion-files-container');

            if (!files || files.length === 0) {
                this.utils.showEmptyState(
                    container,
                    'No Files Found',
                    'No companion files found in the same directory.',
                    'fas fa-folder'
                );
                return;
            }

            const html = `
                <div class="companion-files-list">
                    ${files
                        .map(
                            (file) => `
                        <div class="companion-file-item d-flex align-items-center justify-content-between p-2 border-bottom">
                            <div class="file-info flex-grow-1">
                                <div class="fw-medium">${MediaLibraryUtils.escapeHtml(file.name)}</div>
                                <small class="text-muted">
                                    ${MediaLibraryUtils.formatFileSize(file.size)} • 
                                    ${MediaLibraryUtils.formatDate(file.modified)}
                                </small>
                            </div>
                            <div class="file-actions">
                                <button type="button" class="btn btn-outline-primary btn-sm" 
                                        onclick="MediaLibraryUtils.openFileLocation('${MediaLibraryUtils.escapeHtml(file.path)}')">
                                    <i class="fas fa-external-link-alt"></i>
                                </button>
                            </div>
                        </div>
                    `
                        )
                        .join('')}
                </div>
            `;
            container.innerHTML = html;
        }
    };
}

// Legacy functions for compatibility
function selectItem(itemId) {
    if (window.ebookManager) {
        window.ebookManager.selectItem(itemId);
    }
}

function onItemActivate(ebookId) {
    if (window.ebookManager) {
        window.ebookManager.onItemActivate(ebookId);
    }
}

// Initialize the ebooks manager when ready
function initializeEbooksManager() {
    // Only initialize on pages with ebooks container
    if (!document.getElementById('ebooks-list-container')) {
        console.log('Not on ebooks page, skipping ebooks manager initialization');
        return;
    }

    if (window.ebookManager) {
        console.log('Ebooks manager already initialized');
        return;
    }

    // Check if window.EbookLibrary exists
    if (!window.EbookLibrary) {
        console.error('EbookLibrary not available! Retrying...');
        setTimeout(initializeEbooksManager, 50);
        return;
    }

    // Create MediaLibraryUtils alias if it doesn't exist
    if (!window.MediaLibraryUtils) {
        console.log('Creating MediaLibraryUtils alias to EbookLibrary');
        window.MediaLibraryUtils = window.EbookLibrary;
    }

    if (typeof BaseSectionManager === 'undefined') {
        console.error('BaseSectionManager not loaded! Waiting...');
        setTimeout(initializeEbooksManager, 50);
        return;
    }

    console.log('All dependencies loaded, initializing ebooks manager...');
    try {
        window.ebookManager = new EbooksSectionManager();
        console.log('Ebooks manager initialized successfully');
    } catch (error) {
        console.error('Error initializing ebooks manager:', error);
        console.error('Error stack:', error.stack);
    }
}

// Try multiple initialization strategies
document.addEventListener('DOMContentLoaded', function () {
    console.log('DOM ready, attempting to initialize ebooks manager');
    setTimeout(initializeEbooksManager, 200);
});

// Also listen for the utils ready event
window.addEventListener('MediaLibraryUtilsReady', function () {
    console.log('MediaLibraryUtils ready event received');
    setTimeout(initializeEbooksManager, 100);
});

// Immediate initialization attempt (in case everything is already loaded)
if (document.readyState !== 'loading') {
    console.log('Document already loaded, attempting immediate initialization');
    setTimeout(initializeEbooksManager, 300);
}
