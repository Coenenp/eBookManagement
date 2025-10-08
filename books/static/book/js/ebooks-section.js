/**
 * Ebooks Section Manager - Handles ebook-specific functionality
 * Extends the BaseSectionManager for ebook browsing and management
 */

class EbooksSectionManager extends BaseSectionManager {
    constructor() {
        super('ebooks', {
            listContainer: '#ebooks-list-container',
            detailContainer: '#ebook-detail-container',
            apiEndpoint: window.ebooksConfig?.ajax_urls?.list || '/books/ebooks/ajax/list/',
            detailEndpoint: window.ebooksConfig?.ajax_urls?.detail || '/books/ebooks/ajax/detail/'
        });
        
        this.expandedEbooks = new Set();
    }

    bindEvents() {
        // Bind ebook-specific events
        this.bindReadingProgressEvents();
        this.bindDownloadEvents();
        this.bindCompanionFileEvents();
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

    renderList(viewType = null) {
        const container = document.querySelector(this.config.listContainer);
        const currentView = viewType || this.getCurrentViewType();
        const dataToRender = this.filteredData;
        
        if (dataToRender.length === 0) {
            MediaLibraryUtils.showEmptyState(container, 'No Ebooks Found', 'No ebooks match your current filters.', 'fas fa-book');
            return;
        }
        
        let html = '';
        
        if (currentView === 'grid') {
            html = this.renderGridView(dataToRender);
        } else {
            html = this.renderListView(dataToRender);
        }
        
        container.innerHTML = html;
        container.classList.add('fade-in');
        
        // Initialize reading progress bars
        this.initializeReadingProgressBars();
    }

    renderGridView(ebooksData) {
        return ebooksData.map(ebook => `
            <div class="list-item grid-item" data-item-id="${ebook.id}" onclick="window.ebookManager.selectItem(${ebook.id})">
                <div class="grid-cover mb-3">
                    ${ebook.cover_url ? `
                        <img src="${ebook.cover_url}" alt="Book Cover" class="img-fluid rounded shadow">
                    ` : `
                        <div class="placeholder-cover d-flex align-items-center justify-content-center bg-light rounded">
                            <i class="fas fa-book text-muted fa-2x"></i>
                        </div>
                    `}
                    ${ebook.reading_progress > 0 ? `
                        <div class="reading-progress mt-2">
                            <div class="reading-progress-bar" data-width="${ebook.reading_progress}"></div>
                        </div>
                    ` : ''}
                </div>
                <div class="item-title">${MediaLibraryUtils.escapeHtml(ebook.title)}</div>
                <div class="item-subtitle">${MediaLibraryUtils.escapeHtml(ebook.author)}</div>
                <div class="item-meta">
                    <div class="item-badges">
                        <span class="badge bg-secondary">${ebook.file_format.toUpperCase()}</span>
                        ${ebook.is_read ? '<span class="badge bg-success">Read</span>' : ''}
                    </div>
                    <div class="text-muted small mt-1">
                        ${MediaLibraryUtils.formatFileSize(ebook.file_size)}
                    </div>
                </div>
            </div>
        `).join('');
    }

    renderListView(ebooksData) {
        const headerHtml = `
            <div class="list-header">
                <div class="list-header-title">Title</div>
                <div class="list-header-author">Author</div>
                <div class="list-header-info">Size • Format</div>
            </div>
        `;
        
        const itemsHtml = ebooksData.map(ebook => `
            <div class="list-item ebook-item ${this.expandedEbooks.has(ebook.id) ? 'expanded' : ''}" 
                 data-item-id="${ebook.id}" onclick="window.ebookManager.toggleEbook(${ebook.id})">
                <div class="item-cover-tiny">
                    ${ebook.cover_url ? `
                        <img src="${ebook.cover_url}" alt="Book Cover">
                    ` : `
                        <div class="placeholder-cover">
                            <i class="fas fa-book"></i>
                        </div>
                    `}
                </div>
                <div class="item-title">
                    <i class="fas fa-chevron-right expand-icon me-2"></i>
                    ${MediaLibraryUtils.escapeHtml(ebook.title)}
                </div>
                <div class="item-subtitle">${MediaLibraryUtils.escapeHtml(ebook.author)}</div>
                <div class="item-info">
                    <div class="item-badges">
                        <span class="badge bg-secondary">${ebook.file_format.toUpperCase()}</span>
                        ${ebook.is_read ? '<span class="badge bg-success">✓</span>' : ''}
                        ${ebook.reading_progress > 0 && !ebook.is_read ? '<span class="badge bg-warning">📖</span>' : ''}
                        ${ebook.companion_files && ebook.companion_files.length > 0 ? `<span class="badge bg-info">${ebook.companion_files.length} files</span>` : ''}
                    </div>
                    <div class="text-muted small">
                        ${MediaLibraryUtils.formatFileSize(ebook.file_size)}
                    </div>
                </div>
            </div>
            ${this.expandedEbooks.has(ebook.id) ? this.renderCompanionFiles(ebook) : ''}
        `).join('');
        
        return headerHtml + itemsHtml;
    }

    renderCompanionFiles(ebook) {
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
                ${ebook.companion_files.map(file => `
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
                `).join('')}
            </div>
        `;
    }

    toggleEbook(ebookId) {
        if (this.expandedEbooks.has(ebookId)) {
            this.expandedEbooks.delete(ebookId);
        } else {
            this.expandedEbooks.add(ebookId);
            // Load companion files if not already loaded
            this.loadCompanionFiles(ebookId);
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
        navigator.clipboard.writeText(filePath).then(() => {
            this.showToast('File path copied to clipboard', 'info');
        }).catch(() => {
            this.showToast('Unable to copy path to clipboard', 'warning');
        });
    }

    getCurrentViewType() {
        const viewContainer = document.getElementById('view-container');
        return viewContainer?.className.includes('grid') ? 'grid' : 'list';
    }

    initializeReadingProgressBars() {
        // Animate reading progress bars
        document.querySelectorAll('.reading-progress-bar').forEach(bar => {
            const width = bar.dataset.width || 0;
            setTimeout(() => {
                bar.style.width = width + '%';
            }, 100);
        });
    }

    async loadDetail(ebookId) {
        try {
            const container = document.querySelector(this.config.detailContainer);
            MediaLibraryUtils.showLoadingState(container, 'Loading ebook details...');
            
            const url = this.config.detailEndpoint.replace('0', ebookId);
            const data = await MediaLibraryUtils.makeRequest(url, {
                credentials: 'same-origin',
                headers: {
                    'X-Requested-With': 'XMLHttpRequest'
                }
            });
            
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
            
            MediaLibraryUtils.showErrorState(container, errorMessage);
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
                                ${ebook.cover_url ? `
                                    <img src="${ebook.cover_url}" alt="Book Cover" class="img-fluid rounded shadow-sm">
                                ` : `
                                    <div class="placeholder-cover d-flex align-items-center justify-content-center bg-light rounded">
                                        <i class="fas fa-book text-muted"></i>
                                    </div>
                                `}
                            </div>
                        </div>
                        <div class="col">
                            <h4 class="mb-1">${MediaLibraryUtils.escapeHtml(ebook.title)}</h4>
                            <p class="text-muted mb-0">
                                <i class="fas fa-user me-1"></i>${MediaLibraryUtils.escapeHtml(ebook.author)}
                            </p>
                            ${ebook.reading_progress > 0 ? `
                                <div class="progress mt-2" style="height: 6px;">
                                    <div class="progress-bar bg-success" style="width: ${ebook.reading_progress}%"></div>
                                </div>
                                <small class="text-muted">${ebook.reading_progress}% complete</small>
                            ` : ''}
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
                </div>

                <!-- Tabbed content area -->
                <div class="detail-content flex-fill">
                    <ul class="nav nav-tabs nav-fill" id="ebookDetailTabs" role="tablist">
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
        return `
            <div class="row">
                <div class="col-md-8">
                    ${ebook.description ? `
                        <div class="mb-4">
                            <h6 class="fw-bold mb-2">Description</h6>
                            <div class="description-content">
                                ${MediaLibraryUtils.sanitizeHtml(ebook.description)}
                            </div>
                        </div>
                    ` : ''}
                    
                    <div class="row g-3">
                        <div class="col-sm-6">
                            <div class="info-item">
                                <label class="form-label small fw-bold text-muted mb-1">Publisher</label>
                                <div>${MediaLibraryUtils.escapeHtml(ebook.publisher || 'Unknown')}</div>
                            </div>
                        </div>
                        <div class="col-sm-6">
                            <div class="info-item">
                                <label class="form-label small fw-bold text-muted mb-1">Publication Date</label>
                                <div>${ebook.publication_date ? MediaLibraryUtils.formatDate(ebook.publication_date) : 'Unknown'}</div>
                            </div>
                        </div>
                        <div class="col-sm-6">
                            <div class="info-item">
                                <label class="form-label small fw-bold text-muted mb-1">Language</label>
                                <div>${MediaLibraryUtils.escapeHtml(ebook.language || 'Unknown')}</div>
                            </div>
                        </div>
                        <div class="col-sm-6">
                            <div class="info-item">
                                <label class="form-label small fw-bold text-muted mb-1">ISBN</label>
                                <div>${MediaLibraryUtils.escapeHtml(ebook.isbn || 'None')}</div>
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
                                <span class="badge bg-secondary">${ebook.file_format?.toUpperCase() || 'Unknown'}</span>
                            </div>
                        </div>
                        <div class="info-item mb-3">
                            <label class="form-label small fw-bold text-muted mb-1">File Size</label>
                            <div>${MediaLibraryUtils.formatFileSize(ebook.file_size)}</div>
                        </div>
                        <div class="info-item mb-3">
                            <label class="form-label small fw-bold text-muted mb-1">Last Scanned</label>
                            <div>${ebook.last_scanned ? MediaLibraryUtils.formatDate(ebook.last_scanned) : 'Never'}</div>
                        </div>
                        <div class="info-item mb-3">
                            <label class="form-label small fw-bold text-muted mb-1">Reading Status</label>
                            <div>
                                ${ebook.is_read ? '<span class="badge bg-success">Read</span>' : 
                                  ebook.reading_progress > 0 ? '<span class="badge bg-warning">Reading</span>' : 
                                  '<span class="badge bg-secondary">Unread</span>'}
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }

    renderMetadataTab(ebook) {
        const metadata = ebook.metadata || {};
        
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
                
                ${ebook.file_path ? `
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
                ` : ''}
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
        return key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
    }

    initializeDetailTabs() {
        // Bootstrap tab functionality is already included
        // Add any custom tab event handlers here if needed
    }

    async toggleReadStatus(ebookId) {
        try {
            const url = window.ebooksConfig?.ajax_urls?.toggle_read || '/books/ebooks/ajax/toggle-read/';
            const data = await MediaLibraryUtils.makeRequest(url, {
                method: 'POST',
                body: JSON.stringify({ ebook_id: ebookId })
            });
            
            if (data.success) {
                MediaLibraryUtils.showToast(`Ebook marked as ${data.is_read ? 'read' : 'unread'}`, 'success');
                
                // Update the item in current data
                const item = this.currentData.find(e => e.id == ebookId);
                if (item) {
                    item.is_read = data.is_read;
                }
                
                // Refresh the detail view if this item is selected
                if (this.selectedItem && this.selectedItem.id == ebookId) {
                    this.selectedItem.is_read = data.is_read;
                    this.renderDetail(this.selectedItem);
                }
                
                // Refresh the list view
                this.renderList();
            } else {
                throw new Error(data.message || 'Failed to update reading status');
            }
        } catch (error) {
            console.error('Error toggling read status:', error);
            MediaLibraryUtils.showToast('Failed to update reading status', 'error');
        }
    }

    downloadEbook(ebookId, filename) {
        try {
            const downloadUrl = window.ebooksConfig?.ajax_urls?.download?.replace('0', ebookId) || `/books/ebooks/${ebookId}/download/`;
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
            MediaLibraryUtils.showLoadingState(container, 'Scanning for companion files...');
            
            const url = window.ebooksConfig?.ajax_urls?.companion_files?.replace('0', ebookId) || `/books/ebooks/${ebookId}/companion-files/`;
            const data = await MediaLibraryUtils.makeRequest(url);
            
            if (data.success) {
                this.renderCompanionFiles(data.files);
            } else {
                throw new Error(data.message || 'Failed to load companion files');
            }
        } catch (error) {
            console.error('Error loading companion files:', error);
            const container = document.getElementById('companion-files-container');
            MediaLibraryUtils.showErrorState(container, 'Failed to load companion files');
        }
    }

    renderCompanionFiles(files) {
        const container = document.getElementById('companion-files-container');
        
        if (!files || files.length === 0) {
            MediaLibraryUtils.showEmptyState(container, 'No Files Found', 'No companion files found in the same directory.', 'fas fa-folder');
            return;
        }
        
        const html = `
            <div class="companion-files-list">
                ${files.map(file => `
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
                `).join('')}
            </div>
        `;
        
        container.innerHTML = html;
    }

    // Handle item activation (double-click or Enter)
    onItemActivate(ebookId) {
        const detailUrl = window.ebooksConfig?.urls?.detail?.replace('0', ebookId) || `/books/book/${ebookId}/`;
        window.location.href = detailUrl;
    }
}

// Legacy functions removed - now handled by base-section.js global compatibility layer

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

// Initialize the ebooks manager when the DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    window.ebookManager = new EbooksSectionManager();
});