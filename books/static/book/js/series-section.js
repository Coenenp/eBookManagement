/**
 * Series Section Manager - Handles series-specific functionality
 * Extends the BaseSectionManager for series browsing and management
 */

class SeriesSectionManager extends BaseSectionManager {
    constructor() {
        super('series', {
            listContainer: '#series-list-container',
            detailContainer: '#series-detail-container',
            apiEndpoint: window.seriesConfig?.ajax_urls?.list || '/books/series/ajax/',
            detailEndpoint: window.seriesConfig?.ajax_urls?.detail || '/books/series/ajax/'
        });
        
        this.expandedSeries = new Set();
    }

    filterItems(searchTerm, sortBy, formatFilter, statusFilter) {
        this.filteredData = this.currentData.filter(series => {
            // Search filter
            const matchesSearch = !searchTerm || 
                series.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
                series.authors.some(author => author.toLowerCase().includes(searchTerm.toLowerCase()));
            
            // Format filter
            const matchesFormat = !formatFilter || series.formats.includes(formatFilter);
            
            // Status filter (based on books in series)
            const matchesStatus = !statusFilter || 
                (statusFilter === 'read' && series.books.every(book => book.is_read)) ||
                (statusFilter === 'unread' && series.books.every(book => !book.is_read)) ||
                (statusFilter === 'reading' && series.books.some(book => book.reading_progress > 0 && !book.is_read));
            
            return matchesSearch && matchesFormat && matchesStatus;
        });
        
        // Sort results
        this.sortSeriesData(sortBy);
        
        this.renderList();
        this.updateItemCount(this.filteredData.length);
    }

    sortSeriesData(sortBy) {
        this.filteredData.sort((a, b) => {
            switch(sortBy) {
                case 'title':
                    return a.name.localeCompare(b.name);
                case 'author':
                    return (a.authors[0] || '').localeCompare(b.authors[0] || '');
                case 'date':
                    // Sort by most recent book in series
                    const aLatest = Math.max(...a.books.map(book => new Date(book.last_scanned || 0)));
                    const bLatest = Math.max(...b.books.map(book => new Date(book.last_scanned || 0)));
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
            MediaLibraryUtils.showEmptyState(container, 'No Series Found', 'No series match your current filters.', 'fas fa-layer-group');
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
        return this.filteredData.map(series => `
            <div class="list-item grid-item series-grid-item" data-series-id="${series.id}" onclick="window.seriesManager.toggleSeries(${series.id})">
                <div class="grid-cover mb-3 position-relative">
                    ${series.cover_url ? `
                        <img src="${series.cover_url}" alt="Series Cover" class="img-fluid rounded shadow">
                    ` : `
                        <div class="placeholder-cover d-flex align-items-center justify-content-center bg-light rounded">
                            <i class="fas fa-layer-group text-muted fa-2x"></i>
                        </div>
                    `}
                    <div class="series-count-badge position-absolute top-0 end-0 m-2">
                        <span class="badge bg-primary">${series.books.length}</span>
                    </div>
                </div>
                <div class="item-title">${MediaLibraryUtils.escapeHtml(series.name)}</div>
                <div class="item-subtitle">${series.authors.map(author => MediaLibraryUtils.escapeHtml(author)).join(', ')}</div>
                <div class="item-meta">
                    <div class="item-badges">
                        ${series.formats.map(format => `<span class="badge bg-secondary">${format.toUpperCase()}</span>`).join(' ')}
                    </div>
                    <div class="text-muted small mt-1">
                        ${series.books.length} book${series.books.length !== 1 ? 's' : ''} • 
                        ${MediaLibraryUtils.formatFileSize(series.total_size)}
                    </div>
                </div>
            </div>
        `).join('');
    }

    renderListView() {
        const headerHtml = `
            <div class="list-header">
                <div class="list-header-title">Series</div>
                <div class="list-header-author">Authors</div>
                <div class="list-header-info">Books • Size</div>
            </div>
        `;
        
        const itemsHtml = this.filteredData.map(series => `
            <div class="list-item series-item ${this.expandedSeries.has(series.id) ? 'expanded' : ''}" 
                 data-series-id="${series.id}" onclick="window.seriesManager.toggleSeries(${series.id})">
                <div class="item-cover-tiny">
                    ${series.cover_url ? `
                        <img src="${series.cover_url}" alt="Series Cover">
                    ` : `
                        <div class="placeholder-cover">
                            <i class="fas fa-layer-group"></i>
                        </div>
                    `}
                </div>
                <div class="item-title">
                    <i class="fas fa-chevron-right expand-icon me-2"></i>
                    ${MediaLibraryUtils.escapeHtml(series.name)}
                </div>
                <div class="item-subtitle">${series.authors.map(author => MediaLibraryUtils.escapeHtml(author)).join(', ')}</div>
                <div class="item-info">
                    <div class="item-badges">
                        ${series.formats.map(format => `<span class="badge bg-secondary">${format.toUpperCase()}</span>`).join(' ')}
                    </div>
                    <div class="text-muted small">
                        ${series.books.length} book${series.books.length !== 1 ? 's' : ''} • 
                        ${MediaLibraryUtils.formatFileSize(series.total_size)}
                    </div>
                </div>
            </div>
            ${this.expandedSeries.has(series.id) ? this.renderSeriesBooks(series) : ''}
        `).join('');
        
        return headerHtml + itemsHtml;
    }

    renderSeriesBooks(series) {
        return `
            <div class="series-books-container">
                ${series.books.map(book => `
                    <div class="list-item series-book-item" data-item-id="${book.id}" 
                         onclick="event.stopPropagation(); window.seriesManager.selectItem(${book.id})">
                        <div class="item-cover-tiny ms-4">
                            ${book.cover_url ? `
                                <img src="${book.cover_url}" alt="Book Cover">
                            ` : `
                                <div class="placeholder-cover">
                                    <i class="fas fa-book"></i>
                                </div>
                            `}
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
                `).join('')}
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

    toggleSeries(seriesId) {
        if (this.expandedSeries.has(seriesId)) {
            this.expandedSeries.delete(seriesId);
        } else {
            this.expandedSeries.add(seriesId);
        }
        this.renderList();
    }

    async loadDetail(itemId) {
        try {
            const container = document.querySelector(this.config.detailContainer);
            MediaLibraryUtils.showLoadingState(container, 'Loading series details...');
            
            const url = this.config.detailEndpoint.replace('0', itemId);
            const data = await MediaLibraryUtils.makeRequest(url, {
                credentials: 'same-origin',
                headers: {
                    'X-Requested-With': 'XMLHttpRequest'
                }
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
                                ${series.cover_url ? `
                                    <img src="${series.cover_url}" alt="Series Cover" class="img-fluid rounded shadow-sm">
                                ` : `
                                    <div class="placeholder-cover d-flex align-items-center justify-content-center bg-light rounded">
                                        <i class="fas fa-layer-group text-muted"></i>
                                    </div>
                                `}
                            </div>
                        </div>
                        <div class="col">
                            <h4 class="mb-1">${MediaLibraryUtils.escapeHtml(series.name)}</h4>
                            <p class="text-muted mb-0">
                                <i class="fas fa-user me-1"></i>${series.authors.map(author => MediaLibraryUtils.escapeHtml(author)).join(', ')}
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

                <!-- Series content -->
                <div class="detail-content flex-fill p-3">
                    <div class="row">
                        <div class="col-md-8">
                            <h6 class="fw-bold mb-3">Books in Series</h6>
                            <div class="series-books-detail">
                                ${series.books.map(book => `
                                    <div class="series-book-card card mb-3" onclick="window.seriesManager.selectItem(${book.id})">
                                        <div class="card-body">
                                            <div class="row align-items-center">
                                                <div class="col-auto">
                                                    <div class="book-cover-mini">
                                                        ${book.cover_url ? `
                                                            <img src="${book.cover_url}" alt="Book Cover" class="img-fluid rounded">
                                                        ` : `
                                                            <div class="placeholder-cover-mini d-flex align-items-center justify-content-center bg-light rounded">
                                                                <i class="fas fa-book"></i>
                                                            </div>
                                                        `}
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
                                `).join('')}
                            </div>
                        </div>
                        
                        <div class="col-md-4">
                            <div class="info-sidebar">
                                <h6 class="fw-bold mb-3">Series Information</h6>
                                <div class="info-item mb-3">
                                    <label class="form-label small fw-bold text-muted mb-1">Total Books</label>
                                    <div>${series.books.length}</div>
                                </div>
                                <div class="info-item mb-3">
                                    <label class="form-label small fw-bold text-muted mb-1">Formats</label>
                                    <div>
                                        ${series.formats.map(format => `<span class="badge bg-secondary me-1">${format.toUpperCase()}</span>`).join('')}
                                    </div>
                                </div>
                                <div class="info-item mb-3">
                                    <label class="form-label small fw-bold text-muted mb-1">Total Size</label>
                                    <div>${MediaLibraryUtils.formatFileSize(series.total_size)}</div>
                                </div>
                                <div class="info-item mb-3">
                                    <label class="form-label small fw-bold text-muted mb-1">Progress</label>
                                    <div>
                                        ${series.books.filter(b => b.is_read).length} / ${series.books.length} read
                                        <div class="progress mt-1" style="height: 6px;">
                                            <div class="progress-bar bg-success" style="width: ${(series.books.filter(b => b.is_read).length / series.books.length) * 100}%"></div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `;
        
        container.innerHTML = html;
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
                                ${book.cover_url ? `
                                    <img src="${book.cover_url}" alt="Book Cover" class="img-fluid rounded shadow-sm">
                                ` : `
                                    <div class="placeholder-cover d-flex align-items-center justify-content-center bg-light rounded">
                                        <i class="fas fa-book text-muted"></i>
                                    </div>
                                `}
                            </div>
                        </div>
                        <div class="col">
                            <h4 class="mb-1">${MediaLibraryUtils.escapeHtml(book.title)}</h4>
                            <p class="text-muted mb-0">
                                <i class="fas fa-user me-1"></i>${MediaLibraryUtils.escapeHtml(book.author)}
                            </p>
                            ${book.series ? `
                                <small class="text-muted">
                                    <i class="fas fa-layer-group me-1"></i>Part of series: ${MediaLibraryUtils.escapeHtml(book.series)}
                                </small>
                            ` : ''}
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

                <!-- Book content (reuse ebook detail structure) -->
                <div class="detail-content flex-fill p-3">
                    <div class="row">
                        <div class="col-md-8">
                            ${book.description ? `
                                <div class="mb-4">
                                    <h6 class="fw-bold mb-2">Description</h6>
                                    <div class="description-content">
                                        ${MediaLibraryUtils.sanitizeHtml(book.description)}
                                    </div>
                                </div>
                            ` : ''}
                            
                            <div class="row g-3">
                                <div class="col-sm-6">
                                    <div class="info-item">
                                        <label class="form-label small fw-bold text-muted mb-1">Publisher</label>
                                        <div>${MediaLibraryUtils.escapeHtml(book.publisher || 'Unknown')}</div>
                                    </div>
                                </div>
                                <div class="col-sm-6">
                                    <div class="info-item">
                                        <label class="form-label small fw-bold text-muted mb-1">Publication Date</label>
                                        <div>${book.publication_date ? MediaLibraryUtils.formatDate(book.publication_date) : 'Unknown'}</div>
                                    </div>
                                </div>
                                <div class="col-sm-6">
                                    <div class="info-item">
                                        <label class="form-label small fw-bold text-muted mb-1">Language</label>
                                        <div>${MediaLibraryUtils.escapeHtml(book.language || 'Unknown')}</div>
                                    </div>
                                </div>
                                <div class="col-sm-6">
                                    <div class="info-item">
                                        <label class="form-label small fw-bold text-muted mb-1">ISBN</label>
                                        <div>${MediaLibraryUtils.escapeHtml(book.isbn || 'None')}</div>
                                    </div>
                                </div>
                            </div>
                        </div>
                        
                        <div class="col-md-4">
                            <div class="info-sidebar">
                                <h6 class="fw-bold mb-3">File Information</h6>
                                <div class="info-item mb-3">
                                    <label class="form-label small fw-bold text-muted mb-1">Format</label>
                                    <div>
                                        <span class="badge bg-secondary">${book.file_format?.toUpperCase() || 'Unknown'}</span>
                                    </div>
                                </div>
                                <div class="info-item mb-3">
                                    <label class="form-label small fw-bold text-muted mb-1">File Size</label>
                                    <div>${MediaLibraryUtils.formatFileSize(book.file_size)}</div>
                                </div>
                                <div class="info-item mb-3">
                                    <label class="form-label small fw-bold text-muted mb-1">Last Scanned</label>
                                    <div>${book.last_scanned ? MediaLibraryUtils.formatDate(book.last_scanned) : 'Never'}</div>
                                </div>
                                <div class="info-item mb-3">
                                    <label class="form-label small fw-bold text-muted mb-1">Reading Status</label>
                                    <div>
                                        ${book.is_read ? '<span class="badge bg-success">Read</span>' : 
                                          book.reading_progress > 0 ? '<span class="badge bg-warning">Reading</span>' : 
                                          '<span class="badge bg-secondary">Unread</span>'}
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `;
        
        container.innerHTML = html;
    }

    downloadSeries(seriesId) {
        try {
            const downloadUrl = window.seriesConfig?.ajax_urls?.download?.replace('0', seriesId) || `/books/series/${seriesId}/download/`;
            MediaLibraryUtils.downloadFile(downloadUrl);
            MediaLibraryUtils.showToast('Series download started', 'success');
        } catch (error) {
            console.error('Error downloading series:', error);
            MediaLibraryUtils.showToast('Failed to start series download', 'error');
        }
    }

    downloadBook(bookId) {
        try {
            const downloadUrl = window.seriesConfig?.ajax_urls?.download_book?.replace('0', bookId) || `/books/book/${bookId}/download/`;
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
                body: JSON.stringify({ series_id: seriesId })
            });
            
            if (data.success) {
                MediaLibraryUtils.showToast('Series marked as read', 'success');
                
                // Update the series in current data
                const series = this.currentData.find(s => s.id == seriesId);
                if (series) {
                    series.books.forEach(book => book.is_read = true);
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
            const url = window.seriesConfig?.ajax_urls?.toggle_read || '/books/series/ajax/toggle-read/';
            const data = await MediaLibraryUtils.makeRequest(url, {
                method: 'POST',
                body: JSON.stringify({ book_id: bookId })
            });
            
            if (data.success) {
                MediaLibraryUtils.showToast(`Book marked as ${data.is_read ? 'read' : 'unread'}`, 'success');
                
                // Update the book in current data
                this.currentData.forEach(series => {
                    const book = series.books.find(b => b.id == bookId);
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

// Legacy function compatibility for templates
function customLoadItems() {
    if (window.seriesManager) {
        window.seriesManager.loadItems();
    }
}

function customFilterItems(searchTerm, sortBy, formatFilter, statusFilter) {
    if (window.seriesManager) {
        window.seriesManager.filterItems(searchTerm, sortBy, formatFilter, statusFilter);
    }
}

function customRenderView(viewType) {
    if (window.seriesManager) {
        window.seriesManager.renderList(viewType);
    }
}

function customRefreshItems() {
    if (window.seriesManager) {
        window.seriesManager.loadItems();
    }
}

function customLoadDetail(itemId) {
    if (window.seriesManager) {
        window.seriesManager.loadDetail(itemId);
    }
}

function selectItem(itemId) {
    if (window.seriesManager) {
        window.seriesManager.selectItem(itemId);
    }
}

function toggleSeries(seriesId) {
    if (window.seriesManager) {
        window.seriesManager.toggleSeries(seriesId);
    }
}

function onItemActivate(itemId) {
    if (window.seriesManager) {
        window.seriesManager.onItemActivate(itemId);
    }
}

// Initialize the series manager when the DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    window.seriesManager = new SeriesSectionManager();
});