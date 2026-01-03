/**
 * Comics Section Manager - Handles comic-specific functionality
 * Extends the BaseSectionManager for comic browsing and management
 */

class ComicsSectionManager extends BaseSectionManager {
    constructor() {
        super('comics', {
            listContainer: '#comics-list-container',
            detailContainer: '#comic-detail-container',
            apiEndpoint: window.comicsConfig?.ajax_urls?.list || '/books/comics/ajax/list/',
            detailEndpoint: window.comicsConfig?.ajax_urls?.detail || '/books/comics/ajax/detail/'
        });
        
        this.expandedSeries = new Set();
    }

    filterItems(searchTerm, sortBy, formatFilter, statusFilter) {
        // Filter comics data
        this.filteredData = this.currentData.filter(series => {
            const matchesSearch = !searchTerm || 
                series.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
                series.books.some(book => 
                    book.title.toLowerCase().includes(searchTerm.toLowerCase()) ||
                    book.author.toLowerCase().includes(searchTerm.toLowerCase())
                );
            
            const matchesFormat = !formatFilter || 
                series.books.some(book => book.file_format === formatFilter);
            
            const matchesStatus = !statusFilter || 
                (statusFilter === 'read' && series.books.every(book => book.is_read)) ||
                (statusFilter === 'unread' && series.books.every(book => !book.is_read)) ||
                (statusFilter === 'reading' && series.books.some(book => book.reading_progress > 0 && !book.is_read));
            
            return matchesSearch && matchesFormat && matchesStatus;
        });
        
        // Sort results
        this.sortComicsData(sortBy);
        
        this.renderList();
        this.updateItemCount(this.filteredData.length);
    }

    sortComicsData(sortBy) {
        this.filteredData.sort((a, b) => {
            switch(sortBy) {
                case 'title':
                    return a.name.localeCompare(b.name);
                case 'author':
                    const aAuthor = a.books[0]?.author || '';
                    const bAuthor = b.books[0]?.author || '';
                    return aAuthor.localeCompare(bAuthor);
                case 'date':
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
            MediaLibraryUtils.showEmptyState(container, 'No Comics Found', 'No comics match your current filters.', 'fas fa-mask');
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
        
        this.bindComicsEvents();
    }

    renderGridView() {
        let html = '';
        
        // Render series
        if (this.filteredData.length > 0) {
            html += '<div class="comics-section"><h6 class="text-muted mb-3">Series</h6>';
            html += this.filteredData.map(series => `
                <div class="list-item grid-item comic-series-item" data-series-id="${series.id}" onclick="window.comicsManager.toggleSeries(${series.id})">
                    <div class="grid-cover mb-3 position-relative">
                        ${series.cover_url ? `
                            <img src="${series.cover_url}" alt="Series Cover" class="img-fluid rounded shadow">
                        ` : `
                            <div class="placeholder-cover d-flex align-items-center justify-content-center bg-light rounded">
                                <i class="fas fa-mask text-muted fa-2x"></i>
                            </div>
                        `}
                        <div class="series-count-badge position-absolute top-0 end-0 m-2">
                            <span class="badge bg-primary">${series.books.length}</span>
                        </div>
                    </div>
                    <div class="item-title">${MediaLibraryUtils.escapeHtml(series.name)}</div>
                    <div class="item-subtitle">${series.books.length} issue${series.books.length !== 1 ? 's' : ''}</div>
                    <div class="item-meta">
                        <div class="text-muted small">
                            ${MediaLibraryUtils.formatFileSize(series.total_size)}
                        </div>
                    </div>
                </div>
            `).join('');
            html += '</div>';
        }
        
        return html;
    }

    renderListView() {
        let html = '';
        
        // Render series
        if (this.filteredData.length > 0) {
            html += `
                <div class="comics-section">
                    <div class="section-header">
                        <h6 class="text-muted mb-2">Series</h6>
                    </div>
                    <div class="list-header">
                        <div class="list-header-title">Series Name</div>
                        <div class="list-header-author">Issues</div>
                        <div class="list-header-info">Total Size</div>
                    </div>
                    ${this.filteredData.map(series => `
                        <div class="list-item comic-series-item ${this.expandedSeries.has(series.id) ? 'expanded' : ''}" 
                             data-series-id="${series.id}" onclick="window.comicsManager.toggleSeries(${series.id})">
                            <div class="item-cover-tiny">
                                ${series.cover_url ? `
                                    <img src="${series.cover_url}" alt="Series Cover">
                                ` : `
                                    <div class="placeholder-cover">
                                        <i class="fas fa-mask"></i>
                                    </div>
                                `}
                            </div>
                            <div class="item-title">
                                <i class="fas fa-chevron-right expand-icon me-2"></i>
                                ${MediaLibraryUtils.escapeHtml(series.name)}
                            </div>
                            <div class="item-subtitle">${series.books.length} issue${series.books.length !== 1 ? 's' : ''}</div>
                            <div class="item-info">
                                <div class="text-muted small">
                                    ${MediaLibraryUtils.formatFileSize(series.total_size)}
                                </div>
                            </div>
                        </div>
                        ${this.expandedSeries.has(series.id) ? this.renderSeriesBooks(series) : ''}
                    `).join('')}
                </div>
            `;
        }
        

        
        return html;
    }

    renderSeriesBooks(series) {
        return `
            <div class="series-books-container">
                ${series.books.map(book => `
                    <div class="list-item series-book-item" data-item-id="${book.id}" 
                         onclick="event.stopPropagation(); window.comicsManager.selectItem(${book.id})">
                        <div class="item-cover-tiny ms-4">
                            ${book.cover_url ? `
                                <img src="${book.cover_url}" alt="Issue Cover">
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

    bindComicsEvents() {
        // Comics-specific event bindings
        document.addEventListener('click', (e) => {
            if (e.target.matches('.download-comic-btn')) {
                e.preventDefault();
                const comicId = e.target.dataset.comicId;
                const filename = e.target.dataset.filename;
                this.downloadComic(comicId, filename);
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
            MediaLibraryUtils.showLoadingState(container, 'Loading comic details...');
            
            const url = this.config.detailEndpoint.replace('{id}', itemId);
            const data = await MediaLibraryUtils.makeRequest(url, {
                credentials: 'same-origin',
                headers: {
                    'X-Requested-With': 'XMLHttpRequest'
                }
            });
            
            if (data.success) {
                this.renderDetail(data.comic);
            } else {
                throw new Error(data.error || 'Failed to load comic details');
            }
            
            // Handle mobile layout
            if (window.innerWidth <= 768 && window.SplitPane) {
                window.SplitPane.handleMobileLayout();
                window.SplitPane.addMobileBackButton();
            }
        } catch (error) {
            console.error('Error loading comic detail:', error);
            const container = document.querySelector(this.config.detailContainer);
            MediaLibraryUtils.showErrorState(container, 'Failed to load comic details');
        }
    }

    renderDetail(comic) {
        const container = document.querySelector(this.config.detailContainer);
        
        const html = `
            <div class="comic-detail-wrapper h-100">
                <!-- Header with comic title and cover -->
                <div class="detail-header p-3 border-bottom bg-white sticky-top">
                    <div class="row align-items-center">
                        <div class="col-auto">
                            <div class="detail-cover-small">
                                ${comic.cover_url ? `
                                    <img src="${comic.cover_url}" alt="Comic Cover" class="img-fluid rounded shadow-sm">
                                ` : `
                                    <div class="placeholder-cover d-flex align-items-center justify-content-center bg-light rounded">
                                        <i class="fas fa-mask text-muted"></i>
                                    </div>
                                `}
                            </div>
                        </div>
                        <div class="col">
                            <h4 class="mb-1">${MediaLibraryUtils.escapeHtml(comic.title)}</h4>
                            <p class="text-muted mb-0">
                                <i class="fas fa-user me-1"></i>${MediaLibraryUtils.escapeHtml(comic.author)}
                            </p>
                            ${comic.series ? `
                                <small class="text-muted">
                                    <i class="fas fa-layer-group me-1"></i>Part of series: ${MediaLibraryUtils.escapeHtml(comic.series)}
                                </small>
                            ` : ''}
                        </div>
                        <div class="col-auto">
                            <div class="btn-group" role="group">
                                <button type="button" class="btn btn-outline-primary btn-sm download-comic-btn" 
                                        data-comic-id="${comic.id}" data-filename="${MediaLibraryUtils.escapeHtml(comic.filename)}">
                                    <i class="fas fa-download me-1"></i>Download
                                </button>
                                <button type="button" class="btn btn-outline-secondary btn-sm" 
                                        onclick="window.comicsManager.toggleReadStatus(${comic.id})">
                                    <i class="fas fa-${comic.is_read ? 'times' : 'check'} me-1"></i>
                                    ${comic.is_read ? 'Mark Unread' : 'Mark Read'}
                                </button>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- Tabbed content area -->
                <div class="detail-content flex-fill">
                    <ul class="nav nav-tabs nav-fill" id="comicDetailTabs" role="tablist">
                        <li class="nav-item" role="presentation">
                            <button class="nav-link active" id="info-tab" data-bs-toggle="tab" data-bs-target="#info" type="button" role="tab">
                                <i class="fas fa-info-circle me-1"></i>Information
                            </button>
                        </li>
                        <li class="nav-item" role="presentation">
                            <button class="nav-link" id="metadata-tab" data-bs-toggle="tab" data-bs-target="#metadata" type="button" role="tab">
                                <i class="fas fa-tags me-1"></i>Metadata
                            </button>
                        </li>
                    </ul>
                    
                    <div class="tab-content h-100">
                        <!-- Information Tab -->
                        <div class="tab-pane fade show active h-100" id="info" role="tabpanel">
                            <div class="p-3">
                                ${this.renderComicInformation(comic)}
                            </div>
                        </div>
                        
                        <!-- Metadata Tab -->
                        <div class="tab-pane fade h-100" id="metadata" role="tabpanel">
                            <div class="p-3">
                                ${this.renderComicMetadata(comic)}
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `;
        
        container.innerHTML = html;
    }

    renderComicInformation(comic) {
        return `
            <div class="row">
                <div class="col-md-8">
                    ${comic.description ? `
                        <div class="mb-4">
                            <h6 class="fw-bold mb-2">Description</h6>
                            <div class="description-content">
                                ${MediaLibraryUtils.sanitizeHtml(comic.description)}
                            </div>
                        </div>
                    ` : ''}
                    
                    <div class="row g-3">
                        <div class="col-sm-6">
                            <div class="info-item">
                                <label class="form-label small fw-bold text-muted mb-1">Publisher</label>
                                <div>${MediaLibraryUtils.escapeHtml(comic.publisher || 'Unknown')}</div>
                            </div>
                        </div>
                        <div class="col-sm-6">
                            <div class="info-item">
                                <label class="form-label small fw-bold text-muted mb-1">Issue Number</label>
                                <div>${MediaLibraryUtils.escapeHtml(comic.issue_number || 'N/A')}</div>
                            </div>
                        </div>
                        <div class="col-sm-6">
                            <div class="info-item">
                                <label class="form-label small fw-bold text-muted mb-1">Publication Date</label>
                                <div>${comic.publication_date ? MediaLibraryUtils.formatDate(comic.publication_date) : 'Unknown'}</div>
                            </div>
                        </div>
                        <div class="col-sm-6">
                            <div class="info-item">
                                <label class="form-label small fw-bold text-muted mb-1">Genre</label>
                                <div>${MediaLibraryUtils.escapeHtml(comic.genre || 'Unknown')}</div>
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
                                <span class="badge bg-secondary">${comic.file_format?.toUpperCase() || 'Unknown'}</span>
                            </div>
                        </div>
                        <div class="info-item mb-3">
                            <label class="form-label small fw-bold text-muted mb-1">File Size</label>
                            <div>${MediaLibraryUtils.formatFileSize(comic.file_size)}</div>
                        </div>
                        <div class="info-item mb-3">
                            <label class="form-label small fw-bold text-muted mb-1">Last Scanned</label>
                            <div>${comic.last_scanned ? MediaLibraryUtils.formatDate(comic.last_scanned) : 'Never'}</div>
                        </div>
                        <div class="info-item mb-3">
                            <label class="form-label small fw-bold text-muted mb-1">Reading Status</label>
                            <div>
                                ${comic.is_read ? '<span class="badge bg-success">Read</span>' : 
                                  '<span class="badge bg-secondary">Unread</span>'}
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }

    renderComicMetadata(comic) {
        const metadata = comic.metadata || {};
        
        return `
            <div class="metadata-grid">
                <h6 class="fw-bold mb-3">Technical Metadata</h6>
                <div class="row g-3">
                    ${Object.entries(metadata).map(([key, value]) => `
                        <div class="col-md-6">
                            <div class="info-item">
                                <label class="form-label small fw-bold text-muted mb-1">${this.formatMetadataKey(key)}</label>
                                <div class="small">${MediaLibraryUtils.escapeHtml(String(value))}</div>
                            </div>
                        </div>
                    `).join('')}
                </div>
                
                ${comic.file_path ? `
                    <hr class="my-4">
                    <h6 class="fw-bold mb-3">File Location</h6>
                    <div class="info-item">
                        <div class="d-flex align-items-center justify-content-between">
                            <code class="small text-muted flex-grow-1 me-2">${MediaLibraryUtils.escapeHtml(comic.file_path)}</code>
                            <button type="button" class="btn btn-outline-secondary btn-sm" onclick="MediaLibraryUtils.openFileLocation('${MediaLibraryUtils.escapeHtml(comic.file_path)}')">
                                <i class="fas fa-folder-open me-1"></i>Open Location
                            </button>
                        </div>
                    </div>
                ` : ''}
            </div>
        `;
    }

    formatMetadataKey(key) {
        return key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
    }

    downloadComic(comicId, filename) {
        try {
            const downloadUrl = window.comicsConfig?.ajax_urls?.download?.replace('{id}', comicId) || `/books/comics/${comicId}/download/`;
            MediaLibraryUtils.downloadFile(downloadUrl, filename);
            MediaLibraryUtils.showToast('Download started', 'success');
        } catch (error) {
            console.error('Error downloading comic:', error);
            MediaLibraryUtils.showToast('Failed to start download', 'error');
        }
    }

    async toggleReadStatus(comicId) {
        try {
            const url = window.comicsConfig?.ajax_urls?.toggle_read || '/books/comics/ajax/toggle-read/';
            const data = await MediaLibraryUtils.makeRequest(url, {
                method: 'POST',
                body: JSON.stringify({ comic_id: comicId })
            });
            
            if (data.success) {
                MediaLibraryUtils.showToast(`Comic marked as ${data.is_read ? 'read' : 'unread'}`, 'success');
                
                // Update the item in current data
                const updateItems = (items) => {
                    const item = items.find(c => c.id == comicId);
                    if (item) item.is_read = data.is_read;
                };
                
                updateItems(this.currentStandaloneComics);
                
                // Update in series
                this.currentData.forEach(series => {
                    updateItems(series.books);
                });
                
                // Refresh views if this item is selected
                if (this.selectedItem && this.selectedItem.id == comicId) {
                    this.selectedItem.is_read = data.is_read;
                    this.renderDetail(this.selectedItem);
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
    onItemActivate(comicId) {
        const detailUrl = window.comicsConfig?.urls?.detail?.replace('{id}', comicId) || `/books/book/${comicId}/`;
        window.location.href = detailUrl;
    }
}

// Legacy functions removed - now handled by base-section.js global compatibility layer

function selectItem(itemId) {
    if (window.comicsManager) {
        window.comicsManager.selectItem(itemId);
    }
}

function toggleSeries(seriesId) {
    EbookLibrary.Sections.toggleSeries(seriesId, 'comics');
}

function onItemActivate(comicId) {
    if (window.comicsManager) {
        window.comicsManager.onItemActivate(comicId);
    }
}

// Template compatibility function for clearFilters
function clearFilters() {
    // Clear all form inputs
    const form = document.querySelector('form[method="get"]');
    if (form) {
        const inputs = form.querySelectorAll('input[type="text"], select');
        inputs.forEach(input => {
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

// Initialize the comics manager when the DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    console.log('Comics DOMContentLoaded - Creating ComicsSectionManager');
    try {
        window.comicsManager = new ComicsSectionManager();
        console.log('Comics manager created successfully:', window.comicsManager);
    } catch (error) {
        console.error('Error creating comics manager:', error);
    }
    
    // Set up event delegation for clear filters button
    document.addEventListener('click', function(e) {
        if (e.target.closest('.clear-filters-btn')) {
            e.preventDefault();
            clearFilters();
        }
    });
});