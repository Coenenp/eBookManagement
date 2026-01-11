/**
 * Series Section Manager - Handles series-specific functionality
 * Extends the BaseSectionManager for series browsing and management
 */

class SeriesSectionManager extends BaseSectionManager {
    constructor() {
        super('series', {
            listContainer: '#series-list-container',
            detailContainer: '#series-detail-container',
            apiEndpoint: window.seriesConfig?.ajax_urls?.list || '/books/series/ajax/list/',
            detailEndpoint: window.seriesConfig?.ajax_urls?.detail || '/books/series/ajax/detail/',
        });

        this.expandedSeries = new Set();
    }

    filterItems(searchTerm, sortBy, formatFilter, statusFilter) {
        this.filteredData = this.currentData.filter((series) => {
            // Search filter
            const matchesSearch =
                !searchTerm ||
                series.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
                series.authors.some((author) => author.toLowerCase().includes(searchTerm.toLowerCase()));

            // Format filter
            const matchesFormat = !formatFilter || series.formats.includes(formatFilter);

            // Status filter (based on books in series)
            const matchesStatus =
                !statusFilter ||
                (statusFilter === 'read' && series.books.every((book) => book.is_read)) ||
                (statusFilter === 'unread' && series.books.every((book) => !book.is_read)) ||
                (statusFilter === 'reading' && series.books.some((book) => book.reading_progress > 0 && !book.is_read));

            return matchesSearch && matchesFormat && matchesStatus;
        });

        // Sort results
        this.sortSeriesData(sortBy);

        this.renderList();
        this.updateItemCount(this.filteredData.length);
    }

    sortSeriesData(sortBy) {
        this.filteredData.sort((a, b) => {
            switch (sortBy) {
                case 'title':
                    return a.name.localeCompare(b.name);
                case 'author':
                    return (a.authors[0] || '').localeCompare(b.authors[0] || '');
                case 'date':
                    // Sort by most recent book in series
                    const aLatest = Math.max(...a.books.map((book) => new Date(book.last_scanned || 0)));
                    const bLatest = Math.max(...b.books.map((book) => new Date(book.last_scanned || 0)));
                    return bLatest - aLatest;
                case 'size':
                    return b.total_size - a.total_size;
                default:
                    return a.name.localeCompare(b.name);
            }
        });
    }

    renderList(viewType = null) {
        const container = document.querySelector(this.config.listContainer);
        const currentView = viewType || this.getCurrentViewType();

        if (this.filteredData.length === 0) {
            MediaLibraryUtils.showEmptyState(
                container,
                'No Series Found',
                'No series match your current filters.',
                'fas fa-layer-group'
            );
            return;
        }

        let html = '';

        if (currentView === 'grid') {
            html = this.renderGridView();
        } else {
            html = this.renderListView();
        }

        container.innerHTML = html;
        container.classList.add('fade-in');

        this.bindSeriesEvents();
    }

    renderGridView() {
        return this.filteredData
            .map(
                (series) => `
            <div class="list-item grid-item series-grid-item" data-series-name="${MediaLibraryUtils.escapeHtml(series.name)}" onclick="window.seriesManager.toggleSeries('${MediaLibraryUtils.escapeHtml(series.name).replace(/'/g, "\\'")}')">                <div class="grid-cover mb-3 position-relative">
                    ${
                        series.cover_url
                            ? `
                        <img src="${series.cover_url}" alt="Series Cover" class="img-fluid rounded shadow">
                    `
                            : `
                        <div class="placeholder-cover d-flex align-items-center justify-content-center bg-light rounded">
                            <i class="fas fa-layer-group text-muted fa-2x"></i>
                        </div>
                    `
                    }
                    <div class="series-count-badge position-absolute top-0 end-0 m-2">
                        <span class="badge bg-primary">${series.books.length}</span>
                    </div>
                </div>
                <div class="item-title">${MediaLibraryUtils.escapeHtml(series.name)}</div>
                <div class="item-subtitle">${series.authors.map((author) => MediaLibraryUtils.escapeHtml(author)).join(', ')}</div>
                <div class="item-meta">
                    <div class="item-badges">
                        ${series.formats.map((format) => `<span class="badge bg-secondary">${format.toUpperCase()}</span>`).join(' ')}
                    </div>
                    <div class="text-muted small mt-1">
                        ${series.books.length} book${series.books.length !== 1 ? 's' : ''} • 
                        ${MediaLibraryUtils.formatFileSize(series.total_size)}
                    </div>
                </div>
            </div>
        `
            )
            .join('');
    }

    renderListView() {
        // Condensed table view with series rows that expand to show books
        const tableHtml = `
            <div class="condensed-table-container">
                <table class="condensed-table">
                    <thead>
                        <tr>
                            <th style="width: 30px;"></th>
                            <th class="col-title" data-sort="name">
                                Series Name <i class="fas fa-sort sort-icon"></i>
                            </th>
                            <th class="col-author" data-sort="authors">
                                Author(s) <i class="fas fa-sort sort-icon"></i>
                            </th>
                            <th class="col-format" data-sort="formats">
                                Formats <i class="fas fa-sort sort-icon"></i>
                            </th>
                            <th class="col-size" data-sort="book_count">
                                Books <i class="fas fa-sort sort-icon"></i>
                            </th>
                            <th class="col-size" data-sort="total_size">
                                Total Size <i class="fas fa-sort sort-icon"></i>
                            </th>
                        </tr>
                    </thead>
                    <tbody>
                        ${this.filteredData
                            .map(
                                (series) => `
                            <tr class="${this.expandedSeries.has(series.name) ? 'expanded' : ''}" 
                                data-series-name="${MediaLibraryUtils.escapeHtml(series.name)}">
                                <td style="cursor: pointer; text-align: center;" onclick="event.stopPropagation(); window.seriesManager.toggleSeries('${MediaLibraryUtils.escapeHtml(series.name).replace(/'/g, "\\'")}')">                                    <i class="fas fa-chevron-right expand-icon" style="transition: transform 0.2s; ${this.expandedSeries.has(series.name) ? 'transform: rotate(90deg);' : ''}"></i>
                                </td>
                                <td class="col-title truncate" title="${MediaLibraryUtils.escapeHtml(series.name)}" style="cursor: pointer;" onclick="window.seriesManager.toggleSeries('${MediaLibraryUtils.escapeHtml(series.name).replace(/'/g, "\\'")}')">
                                    <i class="fas fa-layer-group file-icon"></i>
                                    ${MediaLibraryUtils.escapeHtml(series.name)}
                                </td>
                                <td class="col-author truncate" title="${series.authors.join(', ')}" style="cursor: pointer;" onclick="window.seriesManager.toggleSeries('${MediaLibraryUtils.escapeHtml(series.name).replace(/'/g, "\\'")}')">
                                    ${series.authors.map((a) => MediaLibraryUtils.escapeHtml(a)).join(', ')}
                                </td>
                                <td class="col-format" style="cursor: pointer;" onclick="window.seriesManager.toggleSeries('${MediaLibraryUtils.escapeHtml(series.name).replace(/'/g, "\\'")}')">
                                    ${series.formats.map((f) => `<span class="badge bg-secondary me-1">${f.toUpperCase()}</span>`).join('')}
                                </td>
                                <td class="col-size" style="cursor: pointer;" onclick="window.seriesManager.toggleSeries('${MediaLibraryUtils.escapeHtml(series.name).replace(/'/g, "\\'")}')">${series.book_count}</td>
                                <td class="col-size" style="cursor: pointer;" onclick="window.seriesManager.toggleSeries('${MediaLibraryUtils.escapeHtml(series.name).replace(/'/g, "\\'")}')"> ${MediaLibraryUtils.formatFileSize(series.total_size)}</td>
                            </tr>
                            ${this.expandedSeries.has(series.name) ? this.renderSeriesBooksRows(series) : ''}
                        `
                            )
                            .join('')}
                    </tbody>
                </table>
            </div>
        `;

        return tableHtml;
    }

    renderSeriesBooksRows(series) {
        return series.books
            .map(
                (book) => `
            <tr class="series-book-row ${this.selectedItemId === book.id ? 'selected' : ''}" 
                style="background-color: var(--bs-secondary-bg);" 
                data-item-id="${book.id}" 
                onclick="window.seriesManager.selectItem(${book.id})">
                <td></td>
                <td class="col-title truncate" style="padding-left: 40px; cursor: pointer;" title="${MediaLibraryUtils.escapeHtml(book.title)}">
                    <i class="fas fa-book me-2" style="color: var(--bs-secondary);"></i>
                    ${book.position ? `[${book.position}] ` : ''}${MediaLibraryUtils.escapeHtml(book.title)}
                </td>
                <td class="col-author truncate" style="cursor: pointer;" title="${MediaLibraryUtils.escapeHtml(book.author)}">
                    ${MediaLibraryUtils.escapeHtml(book.author)}
                </td>
                <td class="col-format" style="cursor: pointer;">
                    <span class="badge bg-secondary">${book.file_format.toUpperCase()}</span>
                </td>
                <td class="col-size" style="cursor: pointer;">
                    ${
                        book.is_read
                            ? '<span class="badge bg-success" title="Read">✓</span>'
                            : book.reading_progress > 0
                              ? '<span class="badge bg-warning" title="Reading">📖</span>'
                              : '<span class="badge bg-secondary" title="Unread">○</span>'
                    }
                </td>
                <td class="col-size" style="cursor: pointer;">${MediaLibraryUtils.formatFileSize(book.file_size)}</td>
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

    renderSeriesBooks(series) {
        return `
            <div class="series-books-container">
                ${series.books
                    .map(
                        (book) => `
                    <div class="list-item series-book-item" data-item-id="${book.id}" 
                         onclick="event.stopPropagation(); window.seriesManager.selectItem(${book.id})">
                        <div class="item-cover-tiny ms-4">
                            ${
                                book.cover_url
                                    ? `
                                <img src="${book.cover_url}" alt="Book Cover">
                            `
                                    : `
                                <div class="placeholder-cover">
                                    <i class="fas fa-book"></i>
                                </div>
                            `
                            }
                        </div>
                        <div class="item-title">${MediaLibraryUtils.escapeHtml(book.title)}</div>
                        <div class="item-subtitle">${MediaLibraryUtils.escapeHtml(book.author)}</div>
                        <div class="item-info">
                            <div class="item-badges">
                                <span class="badge bg-secondary">${book.file_format.toUpperCase()}</span>
                                ${book.is_read ? '<span class="badge bg-success">✓</span>' : ''}
                                ${book.reading_progress > 0 && !book.is_read ? '<span class="badge bg-warning">📖</span>' : ''}
                            </div>
                            <div class="text-muted small">
                                ${MediaLibraryUtils.formatFileSize(book.file_size)}
                            </div>
                        </div>
                    </div>
                `
                    )
                    .join('')}
            </div>
        `;
    }

    getCurrentViewType() {
        const viewContainer = document.getElementById('view-container');
        return viewContainer?.className.includes('grid') ? 'grid' : 'list';
    }

    bindSeriesEvents() {
        // Series-specific event bindings
        document.addEventListener('click', (e) => {
            if (e.target.matches('.download-series-btn')) {
                e.preventDefault();
                const seriesId = e.target.dataset.seriesId;
                this.downloadSeries(seriesId);
            }
        });
    }

    toggleSeries(seriesName) {
        // Use series name as the identifier (backend doesn't return IDs)
        if (this.expandedSeries.has(seriesName)) {
            this.expandedSeries.delete(seriesName);
        } else {
            this.expandedSeries.add(seriesName);
        }
        this.renderList();
    }

    async loadDetail(itemId) {
        try {
            console.log('loadDetail called with itemId:', itemId, 'type:', typeof itemId);

            const container = document.querySelector(this.config.detailContainer);
            MediaLibraryUtils.showLoadingState(container, 'Loading series details...');

            // itemId might be a series name (string) or book ID (number)
            // If it's a number, it's a book - load book detail instead
            if (typeof itemId === 'number' || !isNaN(itemId)) {
                console.log('Detected as book ID, loading book detail');
                // It's a book ID - use book detail endpoint
                const bookUrl =
                    this.config.bookDetailEndpoint?.replace('{id}', itemId) ||
                    window.seriesConfig?.ajax_urls?.book_detail?.replace('{id}', itemId) ||
                    `/books/book/ajax/detail/${itemId}/`;
                console.log('Book URL:', bookUrl);
                const data = await MediaLibraryUtils.makeRequest(bookUrl, {
                    credentials: 'same-origin',
                    headers: {
                        'X-Requested-With': 'XMLHttpRequest',
                    },
                });

                console.log('Book data received:', data);

                if (data.success && (data.book || data.ebook)) {
                    console.log('Rendering book detail');
                    const bookData = data.book || data.ebook;
                    this.renderBookDetail(bookData);
                } else {
                    console.error('Book data missing or unsuccessful:', data);
                }
                return;
            }

            // It's a series name - URL encode it
            console.log('Detected as series name, loading series detail');
            const encodedSeriesName = encodeURIComponent(itemId);
            const url = this.config.detailEndpoint.replace('{id}', encodedSeriesName);
            console.log('Series URL:', url);
            const data = await MediaLibraryUtils.makeRequest(url, {
                credentials: 'same-origin',
                headers: {
                    'X-Requested-With': 'XMLHttpRequest',
                },
            });

            if (data.success) {
                if (data.series) {
                    this.renderSeriesDetail(data.series);
                } else if (data.book) {
                    this.renderBookDetail(data.book);
                }
            } else {
                throw new Error(data.error || 'Failed to load details');
            }

            // Handle mobile layout
            if (window.innerWidth <= 768 && window.SplitPane) {
                window.SplitPane.handleMobileLayout();
                window.SplitPane.addMobileBackButton();
            }
        } catch (error) {
            console.error('Error loading series detail:', error);
            const container = document.querySelector(this.config.detailContainer);
            MediaLibraryUtils.showErrorState(container, 'Failed to load details');
        }
    }

    renderSeriesDetail(series) {
        const container = document.querySelector(this.config.detailContainer);

        const html = `
            <div class="series-detail-wrapper h-100">
                <!-- Header with series title and cover -->
                <div class="detail-header p-3 border-bottom bg-white sticky-top">
                    <div class="row align-items-center">
                        <div class="col-auto">
                            <div class="detail-cover-small">
                                ${
                                    series.cover_url
                                        ? `
                                    <img src="${series.cover_url}" alt="Series Cover" class="img-fluid rounded shadow-sm">
                                `
                                        : `
                                    <div class="placeholder-cover d-flex align-items-center justify-content-center bg-light rounded">
                                        <i class="fas fa-layer-group text-muted"></i>
                                    </div>
                                `
                                }
                            </div>
                        </div>
                        <div class="col">
                            <h4 class="mb-1">${MediaLibraryUtils.escapeHtml(series.name)}</h4>
                            <p class="text-muted mb-0">
                                <i class="fas fa-user me-1"></i>${series.authors.map((author) => MediaLibraryUtils.escapeHtml(author)).join(', ')}
                            </p>
                            <small class="text-muted">
                                <i class="fas fa-books me-1"></i>${series.books.length} book${series.books.length !== 1 ? 's' : ''} • 
                                ${MediaLibraryUtils.formatFileSize(series.total_size)}
                            </small>
                        </div>
                        <div class="col-auto">
                            <div class="btn-group" role="group">
                                <button type="button" class="btn btn-outline-primary btn-sm download-series-btn" 
                                        data-series-id="${series.id}">
                                    <i class="fas fa-download me-1"></i>Download All
                                </button>
                                <button type="button" class="btn btn-outline-secondary btn-sm" 
                                        onclick="window.seriesManager.markSeriesRead(${series.id})">
                                    <i class="fas fa-check me-1"></i>Mark All Read
                                </button>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- Series content with tabs -->
                <div class="detail-content flex-fill">
                    <ul class="nav nav-tabs px-3 pt-2" role="tablist">
                        <li class="nav-item" role="presentation">
                            <button class="nav-link active" data-bs-toggle="tab" data-bs-target="#series-info-${series.id}" type="button" role="tab">
                                <i class="fas fa-info-circle me-1"></i>Info
                            </button>
                        </li>
                        <li class="nav-item" role="presentation">
                            <button class="nav-link" data-bs-toggle="tab" data-bs-target="#series-meta-${series.id}" type="button" role="tab">
                                <i class="fas fa-tags me-1"></i>Meta
                            </button>
                        </li>
                        <li class="nav-item" role="presentation">
                            <button class="nav-link" data-bs-toggle="tab" data-bs-target="#series-files-${series.id}" type="button" role="tab">
                                <i class="fas fa-folder me-1"></i>Books
                            </button>
                        </li>
                    </ul>
                    <div class="tab-content">
                        <div class="tab-pane fade show active" id="series-info-${series.id}" role="tabpanel">
                            ${this.renderSeriesInfoTab(series)}
                        </div>
                        <div class="tab-pane fade" id="series-meta-${series.id}" role="tabpanel">
                            ${this.renderSeriesMetadataTab(series)}
                        </div>
                        <div class="tab-pane fade" id="series-files-${series.id}" role="tabpanel">
                            ${this.renderSeriesBooksTab(series)}
                        </div>
                    </div>
                </div>
            </div>
        `;

        container.innerHTML = html;
    }

    renderSeriesInfoTab(series) {
        return `
            <div class="p-3">
                <div class="row">
                    <div class="col-md-8">
                        <h6 class="fw-bold mb-3">Series Overview</h6>
                        <div class="row g-3">
                            <div class="col-sm-6">
                                <div class="info-item">
                                    <label class="form-label small fw-bold text-muted mb-1">Total Books</label>
                                    <div>${series.books.length}</div>
                                </div>
                            </div>
                            <div class="col-sm-6">
                                <div class="info-item">
                                    <label class="form-label small fw-bold text-muted mb-1">Total Size</label>
                                    <div>${MediaLibraryUtils.formatFileSize(series.total_size)}</div>
                                </div>
                            </div>
                            <div class="col-sm-6">
                                <div class="info-item">
                                    <label class="form-label small fw-bold text-muted mb-1">Progress</label>
                                    <div>
                                        ${series.books.filter((b) => b.is_read).length} / ${series.books.length} read
                                        <div class="progress mt-1" style="height: 6px;">
                                            <div class="progress-bar bg-success" style="width: ${(series.books.filter((b) => b.is_read).length / series.books.length) * 100}%"></div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                            <div class="col-sm-6">
                                <div class="info-item">
                                    <label class="form-label small fw-bold text-muted mb-1">Authors</label>
                                    <div>${series.authors.map((author) => MediaLibraryUtils.escapeHtml(author)).join(', ')}</div>
                                </div>
                            </div>
                        </div>
                    </div>
                    
                    <div class="col-md-4">
                        <div class="info-sidebar">
                            <h6 class="fw-bold mb-3">Formats</h6>
                            <div class="info-item mb-3">
                                <div>
                                    ${series.formats.map((format) => `<span class="badge bg-secondary me-1">${format.toUpperCase()}</span>`).join('')}
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }

    renderSeriesMetadataTab(series) {
        // For series, we can show metadata from the first book as a sample
        const firstBook = series.books && series.books[0];
        const metadata = firstBook?.metadata || [];

        return `
            <div class="p-3">
                <div class="metadata-grid">
                    <h6 class="fw-bold mb-3">Series Metadata</h6>
                    ${
                        metadata.length > 0
                            ? `
                        <p class="text-muted small mb-3">Showing metadata from first book in series</p>
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
                </div>
            </div>
        `;
    }

    renderSeriesBooksTab(series) {
        return `
            <div class="p-3">
                <h6 class="fw-bold mb-3">Books in Series</h6>
                <div class="series-books-detail">
                    ${series.books
                        .map(
                            (book) => `
                        <div class="series-book-card card mb-3" onclick="window.seriesManager.selectItem(${book.id})">
                            <div class="card-body">
                                <div class="row align-items-center">
                                    <div class="col-auto">
                                        <div class="book-cover-mini">
                                            ${
                                                book.cover_url
                                                    ? `
                                                <img src="${book.cover_url}" alt="Book Cover" class="img-fluid rounded">
                                            `
                                                    : `
                                                <div class="placeholder-cover-mini d-flex align-items-center justify-content-center bg-light rounded">
                                                    <i class="fas fa-book"></i>
                                                </div>
                                            `
                                            }
                                        </div>
                                    </div>
                                    <div class="col">
                                        <h6 class="card-title mb-1">${MediaLibraryUtils.escapeHtml(book.title)}</h6>
                                        <p class="card-text text-muted mb-1">${MediaLibraryUtils.escapeHtml(book.author)}</p>
                                        <div class="d-flex align-items-center">
                                            <span class="badge bg-secondary me-2">${book.file_format.toUpperCase()}</span>
                                            ${book.is_read ? '<span class="badge bg-success me-2">Read</span>' : ''}
                                            ${book.reading_progress > 0 && !book.is_read ? '<span class="badge bg-warning me-2">Reading</span>' : ''}
                                            <small class="text-muted">${MediaLibraryUtils.formatFileSize(book.file_size)}</small>
                                        </div>
                                    </div>
                                    <div class="col-auto">
                                        <button type="button" class="btn btn-sm btn-outline-primary" 
                                                onclick="event.stopPropagation(); window.seriesManager.downloadBook(${book.id})">
                                            <i class="fas fa-download"></i>
                                        </button>
                                    </div>
                                </div>
                            </div>
                        </div>
                    `
                        )
                        .join('')}
                </div>
            </div>
        `;
    }

    formatMetadataKey(key) {
        return key.replace(/_/g, ' ').replace(/\b\w/g, (l) => l.toUpperCase());
    }

    renderBookDetail(book) {
        const container = document.querySelector(this.config.detailContainer);

        // For individual books, render similar to ebook detail but with series context
        const html = `
            <div class="book-detail-wrapper h-100">
                <!-- Header with book title and cover -->
                <div class="detail-header p-3 border-bottom bg-white sticky-top">
                    <div class="row align-items-center">
                        <div class="col-auto">
                            <div class="detail-cover-small">
                                ${
                                    book.cover_url
                                        ? `
                                    <img src="${book.cover_url}" alt="Book Cover" class="img-fluid rounded shadow-sm">
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
                            <h4 class="mb-1">${MediaLibraryUtils.escapeHtml(book.title)}</h4>
                            <p class="text-muted mb-0">
                                <i class="fas fa-user me-1"></i>${MediaLibraryUtils.escapeHtml(book.author)}
                            </p>
                            ${
                                book.series
                                    ? `
                                <small class="text-muted">
                                    <i class="fas fa-layer-group me-1"></i>Part of series: ${MediaLibraryUtils.escapeHtml(book.series)}
                                </small>
                            `
                                    : ''
                            }
                        </div>
                        <div class="col-auto">
                            <div class="btn-group" role="group">
                                <button type="button" class="btn btn-outline-primary btn-sm" 
                                        onclick="window.seriesManager.downloadBook(${book.id})">
                                    <i class="fas fa-download me-1"></i>Download
                                </button>
                                <button type="button" class="btn btn-outline-secondary btn-sm" 
                                        onclick="window.seriesManager.toggleBookReadStatus(${book.id})">
                                    <i class="fas fa-${book.is_read ? 'times' : 'check'} me-1"></i>
                                    ${book.is_read ? 'Mark Unread' : 'Mark Read'}
                                </button>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- Book content with tabs -->
                <div class="detail-content flex-fill">
                    <ul class="nav nav-tabs px-3 pt-2" role="tablist">
                        <li class="nav-item" role="presentation">
                            <button class="nav-link active" data-bs-toggle="tab" data-bs-target="#book-info-${book.id}" type="button" role="tab">
                                <i class="fas fa-info-circle me-1"></i>Info
                            </button>
                        </li>
                        <li class="nav-item" role="presentation">
                            <button class="nav-link" data-bs-toggle="tab" data-bs-target="#book-meta-${book.id}" type="button" role="tab">
                                <i class="fas fa-tags me-1"></i>Meta
                            </button>
                        </li>
                        <li class="nav-item" role="presentation">
                            <button class="nav-link" data-bs-toggle="tab" data-bs-target="#book-files-${book.id}" type="button" role="tab">
                                <i class="fas fa-folder me-1"></i>Files
                            </button>
                        </li>
                    </ul>
                    <div class="tab-content">
                        <div class="tab-pane fade show active" id="book-info-${book.id}" role="tabpanel">
                            ${this.renderBookInfoTab(book)}
                        </div>
                        <div class="tab-pane fade" id="book-meta-${book.id}" role="tabpanel">
                            ${this.renderBookMetadataTab(book)}
                        </div>
                        <div class="tab-pane fade" id="book-files-${book.id}" role="tabpanel">
                            ${this.renderBookFilesTab(book)}
                        </div>
                    </div>
                </div>
            </div>
        `;

        container.innerHTML = html;
    }

    renderBookInfoTab(book) {
        const formatYear = (dateStr) => {
            if (!dateStr) return null;
            try {
                const date = new Date(dateStr);
                const year = date.getFullYear();
                if (year < 1800 || year > new Date().getFullYear() + 5) return null;
                return year;
            } catch {
                return null;
            }
        };

        const getFileFormat = () => {
            if (book.file_format) return book.file_format.toUpperCase();
            if (book.file_path) {
                const ext = book.file_path.split('.').pop();
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
        const pubYear = formatYear(book.publication_date);
        const languageName = getLanguageName(book.language);

        // Split file path into scan folder and relative path
        const getPathParts = () => {
            if (!book.file_path) return null;

            const fullPath = book.file_path;
            const scanFolderPath = book.scan_folder_path || '';

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
                    scanFolder: book.scan_folder_name || scanFolderPath,
                    directory: directory,
                    filename: filename,
                };
            }

            // Fallback: no scan folder, just split into directory and filename
            const lastSeparator = Math.max(fullPath.lastIndexOf('/'), fullPath.lastIndexOf('\\'));
            return {
                scanFolder: null,
                directory: lastSeparator >= 0 ? fullPath.substring(0, lastSeparator) : '',
                filename: lastSeparator >= 0 ? fullPath.substring(lastSeparator + 1) : fullPath,
            };
        };

        const pathParts = getPathParts();

        // Helper function for quality badges
        const getQualityBadge = (value) => {
            if (!value && value !== 0) return '<span class="badge bg-secondary">N/A</span>';
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
            <div class="p-3">
                <div class="mb-3">
                    ${book.publisher ? `<div class="mb-2"><i class="fas fa-building me-2 text-muted"></i><strong>Publisher:</strong> ${MediaLibraryUtils.escapeHtml(book.publisher)}</div>` : ''}
                    ${pubYear ? `<div class="mb-2"><i class="fas fa-calendar me-2 text-muted"></i><strong>Year:</strong> ${pubYear}</div>` : ''}
                    ${languageName ? `<div class="mb-2"><i class="fas fa-language me-2 text-muted"></i><strong>Language:</strong> ${MediaLibraryUtils.escapeHtml(languageName)}</div>` : ''}
                    ${fileFormat && book.file_size ? `<div class="mb-2"><i class="fas fa-file-alt me-2 text-muted"></i><strong>Format & Size:</strong> <span class="badge ${getFormatColor(book.file_format)}">${fileFormat}</span> · ${MediaLibraryUtils.formatFileSize(book.file_size)}</div>` : fileFormat ? `<div class="mb-2"><i class="fas fa-file-alt me-2 text-muted"></i><strong>Format:</strong> <span class="badge ${getFormatColor(book.file_format)}">${fileFormat}</span></div>` : ''}
                    ${book.isbn ? `<div class="mb-2"><i class="fas fa-barcode me-2 text-muted"></i><strong>ISBN:</strong> ${MediaLibraryUtils.escapeHtml(book.isbn)}</div>` : ''}
                    ${pathParts && pathParts.scanFolder ? `<div class="mb-2"><i class="fas fa-hdd me-2 text-muted"></i><strong>Scan Folder:</strong> ${MediaLibraryUtils.escapeHtml(pathParts.scanFolder)}</div>` : ''}
                    ${pathParts && pathParts.directory ? `<div class="mb-2"><i class="fas fa-folder me-2 text-muted"></i><strong>Path:</strong> <code class="small">${MediaLibraryUtils.escapeHtml(pathParts.directory)}</code></div>` : ''}
                    ${pathParts && pathParts.filename ? `<div class="mb-2"><i class="fas fa-file me-2 text-muted"></i><strong>Filename:</strong> <code class="small">${MediaLibraryUtils.escapeHtml(pathParts.filename)}</code> <button type="button" class="btn btn-outline-secondary btn-sm ms-2" onclick="MediaLibraryUtils.openFileLocation(decodeURIComponent('${encodeURIComponent(book.file_path)}'))"><i class="fas fa-folder-open me-1"></i>Open</button></div>` : ''}
                    ${book.last_scanned ? `<div class="mb-2"><i class="fas fa-clock me-2 text-muted"></i><strong>Last Scanned:</strong> ${MediaLibraryUtils.formatDate(book.last_scanned)}</div>` : ''}
                    ${book.confidence !== undefined ? `<div class="mb-2"><strong>Confidence:</strong> ${getQualityBadge(book.confidence)}</div>` : ''}
                    ${book.completeness !== undefined ? `<div class="mb-2"><strong>Completeness:</strong> ${getQualityBadge(book.completeness)}</div>` : ''}
                    <div class="mb-2"><strong>Reading Status:</strong> 
                        ${
                            book.is_read
                                ? '<span class="badge bg-success">Read</span>'
                                : book.reading_progress > 0
                                  ? '<span class="badge bg-warning">Reading</span>'
                                  : '<span class="badge bg-secondary">Unread</span>'
                        }
                    </div>
                </div>
                
                ${
                    book.description
                        ? `
                    <div class="mt-4">
                        <strong>Description:</strong>
                        <div class="description-content mt-2">
                            ${MediaLibraryUtils.sanitizeHtml(book.description)}
                        </div>
                    </div>
                `
                        : ''
                }
            </div>
        `;
    }

    renderBookMetadataTab(book) {
        const metadata = book.metadata || [];

        return `
            <div class="p-3">
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
                        book.file_path
                            ? `
                        <hr class="my-4">
                        <h6 class="fw-bold mb-3">File Location</h6>
                        <div class="info-item">
                            <div class="d-flex align-items-center justify-content-between">
                                <code class="small text-muted flex-grow-1 me-2">${MediaLibraryUtils.escapeHtml(book.file_path)}</code>
                                <button type="button" class="btn btn-outline-secondary btn-sm" onclick="MediaLibraryUtils.openFileLocation('${MediaLibraryUtils.escapeHtml(book.file_path)}')">
                                    <i class="fas fa-folder-open me-1"></i>Open Location
                                </button>
                            </div>
                        </div>
                    `
                            : ''
                    }
                </div>
            </div>
        `;
    }

    renderBookFilesTab(book) {
        return `
            <div class="p-3">
                <div class="d-flex justify-content-between align-items-center mb-3">
                    <h6 class="fw-bold mb-0">Companion Files</h6>
                    <button type="button" class="btn btn-outline-primary btn-sm load-companion-files-btn" 
                            data-book-id="${book.id}">
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

    downloadSeries(seriesId) {
        try {
            const downloadUrl =
                window.seriesConfig?.ajax_urls?.download?.replace('0', seriesId) ||
                `/books/series/${seriesId}/download/`;
            MediaLibraryUtils.downloadFile(downloadUrl);
            MediaLibraryUtils.showToast('Series download started', 'success');
        } catch (error) {
            console.error('Error downloading series:', error);
            MediaLibraryUtils.showToast('Failed to start series download', 'error');
        }
    }

    downloadBook(bookId) {
        try {
            const downloadUrl =
                window.seriesConfig?.ajax_urls?.download_book?.replace('{id}', bookId) ||
                `/ebooks/ajax/download/${bookId}/`;
            MediaLibraryUtils.downloadFile(downloadUrl);
            MediaLibraryUtils.showToast('Download started', 'success');
        } catch (error) {
            console.error('Error downloading book:', error);
            MediaLibraryUtils.showToast('Failed to start download', 'error');
        }
    }

    async markSeriesRead(seriesId) {
        try {
            const url = window.seriesConfig?.ajax_urls?.mark_read || '/books/series/ajax/mark-read/';
            const data = await MediaLibraryUtils.makeRequest(url, {
                method: 'POST',
                body: JSON.stringify({ series_id: seriesId }),
            });

            if (data.success) {
                MediaLibraryUtils.showToast('Series marked as read', 'success');

                // Update the series in current data
                const series = this.currentData.find((s) => s.id == seriesId);
                if (series) {
                    series.books.forEach((book) => (book.is_read = true));
                }

                // Refresh views
                this.renderList();
                if (this.selectedItem) {
                    this.loadDetail(seriesId);
                }
            } else {
                throw new Error(data.message || 'Failed to mark series as read');
            }
        } catch (error) {
            console.error('Error marking series as read:', error);
            MediaLibraryUtils.showToast('Failed to mark series as read', 'error');
        }
    }

    async toggleBookReadStatus(bookId) {
        try {
            const url = window.seriesConfig?.ajax_urls?.toggle_read || '/ebooks/ajax/toggle_read/';
            const data = await MediaLibraryUtils.makeRequest(url, {
                method: 'POST',
                body: JSON.stringify({ book_id: bookId }),
            });

            if (data.success) {
                MediaLibraryUtils.showToast(`Book marked as ${data.is_read ? 'read' : 'unread'}`, 'success');

                // Update the book in current data
                this.currentData.forEach((series) => {
                    const book = series.books.find((b) => b.id == bookId);
                    if (book) book.is_read = data.is_read;
                });

                // Refresh views if this item is selected
                if (this.selectedItem && this.selectedItem.id == bookId) {
                    this.selectedItem.is_read = data.is_read;
                    this.renderBookDetail(this.selectedItem);
                }

                this.renderList();
            } else {
                throw new Error(data.message || 'Failed to update reading status');
            }
        } catch (error) {
            console.error('Error toggling read status:', error);
            MediaLibraryUtils.showToast('Failed to update reading status', 'error');
        }
    }

    // Handle item activation (double-click or Enter)
    onItemActivate(itemId) {
        const detailUrl = window.seriesConfig?.urls?.detail?.replace('0', itemId) || `/books/book/${itemId}/`;
        window.location.href = detailUrl;
    }
}

// Legacy functions removed - now handled by base-section.js global compatibility layer

function selectItem(itemId) {
    if (window.seriesManager) {
        window.seriesManager.selectItem(itemId);
    }
}

function toggleSeries(seriesId) {
    EbookLibrary.Sections.toggleSeries(seriesId, 'series');
}

function onItemActivate(itemId) {
    if (window.seriesManager) {
        window.seriesManager.onItemActivate(itemId);
    }
}

// Template compatibility functions
function toggleViewMode(viewType) {
    if (window.seriesManager) {
        window.seriesManager.setViewType(viewType);
        window.seriesManager.renderList(viewType);

        // Update view toggle buttons
        const buttons = document.querySelectorAll('.view-mode-btn');
        buttons.forEach((btn) => {
            btn.classList.toggle('active', btn.dataset.view === viewType);
        });
    }
}

function clearFilters() {
    // Clear all form inputs
    const form = document.querySelector('form[method="get"]');
    if (form) {
        const inputs = form.querySelectorAll('input[type="text"], select');
        inputs.forEach((input) => {
            if (input.type === 'text') {
                input.value = '';
            } else if (input.tagName === 'SELECT') {
                input.selectedIndex = 0;
            }
        });

        // Refresh the page without parameters
        window.location.href = window.location.pathname;
    }
}

function selectSeries(seriesId) {
    if (window.seriesManager) {
        window.seriesManager.selectItem(seriesId);
    }
}

function viewSeriesDetails(seriesId) {
    const detailUrl = window.seriesConfig?.urls?.detail?.replace('0', seriesId) || `/books/series/${seriesId}/`;
    window.location.href = detailUrl;
}

function editSeries(seriesId) {
    const editUrl = window.seriesConfig?.urls?.edit?.replace('0', seriesId) || `/books/series/${seriesId}/edit/`;
    window.location.href = editUrl;
}

// Initialize the series manager when the DOM is ready
document.addEventListener('DOMContentLoaded', function () {
    window.seriesManager = new SeriesSectionManager();

    // Set up event delegation for new CSS class-based events
    const body = document.body;

    // View mode toggle buttons
    body.addEventListener('click', function (e) {
        if (e.target.closest('.view-mode-btn')) {
            const btn = e.target.closest('.view-mode-btn');
            const viewType = btn.dataset.view;
            toggleViewMode(viewType);
        }
    });

    // Clear filters button
    body.addEventListener('click', function (e) {
        if (e.target.closest('.clear-filters-btn')) {
            e.preventDefault();
            clearFilters();
        }
    });

    // Series selection links
    body.addEventListener('click', function (e) {
        if (e.target.closest('.series-select-link')) {
            e.preventDefault();
            const link = e.target.closest('.series-select-link');
            const seriesId = parseInt(link.dataset.seriesId);
            selectSeries(seriesId);
        }
    });

    // Series view buttons
    body.addEventListener('click', function (e) {
        if (e.target.closest('.series-view-btn')) {
            e.stopPropagation();
            const btn = e.target.closest('.series-view-btn');
            const seriesId = parseInt(btn.dataset.seriesId);
            viewSeriesDetails(seriesId);
        }
    });

    // Series edit buttons
    body.addEventListener('click', function (e) {
        if (e.target.closest('.series-edit-btn')) {
            e.stopPropagation();
            const btn = e.target.closest('.series-edit-btn');
            const seriesId = parseInt(btn.dataset.seriesId);
            editSeries(seriesId);
        }
    });
});
