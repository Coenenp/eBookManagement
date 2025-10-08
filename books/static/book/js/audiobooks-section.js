/**
 * Audiobooks Section Manager - Handles audiobook-specific functionality
 * Extends the BaseSectionManager for audiobook browsing and management
 */

class AudiobooksSectionManager extends BaseSectionManager {
    constructor() {
        super('audiobooks', {
            listContainer: '#audiobooks-list-container',
            detailContainer: '#audiobook-detail-container',
            apiEndpoint: window.audiobooksConfig?.ajax_urls?.list || '/books/audiobooks/ajax/list/',
            detailEndpoint: window.audiobooksConfig?.ajax_urls?.detail || '/books/audiobooks/ajax/detail/'
        });
        
        this.expandedAudiobooks = new Set();
    }

    filterItems(searchTerm, sortBy, formatFilter, statusFilter) {
        this.filteredData = this.currentData.filter(audiobook => {
            // Search filter
            const matchesSearch = !searchTerm || 
                audiobook.title.toLowerCase().includes(searchTerm.toLowerCase()) ||
                audiobook.author.toLowerCase().includes(searchTerm.toLowerCase()) ||
                (audiobook.narrator && audiobook.narrator.toLowerCase().includes(searchTerm.toLowerCase()));
            
            // Format filter - extract format from file_format field
            const bookFormat = audiobook.file_format ? audiobook.file_format.toLowerCase() : '';
            const matchesFormat = !formatFilter || bookFormat === formatFilter.toLowerCase();
            
            // Status filter
            const matchesStatus = !statusFilter || 
                (statusFilter === 'read' && audiobook.is_read) ||
                (statusFilter === 'unread' && !audiobook.is_read) ||
                (statusFilter === 'listening' && audiobook.listening_progress > 0 && !audiobook.is_read);
            
            return matchesSearch && matchesFormat && matchesStatus;
        });
        
        // Sort results
        this.sortAudiobooksData(sortBy);
        
        this.renderList();
        this.updateItemCount(this.filteredData.length);
    }

    sortAudiobooksData(sortBy) {
        this.filteredData.sort((a, b) => {
            switch(sortBy) {
                case 'title':
                    return a.title.localeCompare(b.title);
                case 'author':
                    return a.author.localeCompare(b.author);
                case 'date':
                    return new Date(b.last_scanned) - new Date(a.last_scanned);
                case 'size':
                    return (b.file_size || 0) - (a.file_size || 0);
                case 'duration':
                    return (b.duration_seconds || 0) - (a.duration_seconds || 0);
                default:
                    return a.title.localeCompare(b.title);
            }
        });
    }

    renderList(viewType = null) {
        const container = document.querySelector(this.config.listContainer);
        const currentView = viewType || this.getCurrentViewType();
        
        if (this.filteredData.length === 0) {
            MediaLibraryUtils.showEmptyState(container, 'No Audiobooks Found', 'No audiobooks match your current filters.', 'fas fa-headphones');
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
        
        this.bindAudiobooksEvents();
    }

    renderListView() {
        const headerHtml = `
            <div class="list-header">
                <div class="list-header-title">Title</div>
                <div class="list-header-author">Author</div>
                <div class="list-header-info">Duration • Size</div>
            </div>
        `;
        
        const itemsHtml = this.filteredData.map(audiobook => `
            <div class="list-item audiobook-item ${this.expandedAudiobooks.has(audiobook.id) ? 'expanded' : ''}" 
                 data-item-id="${audiobook.id}" onclick="window.sectionManager.toggleAudiobook(${audiobook.id})">
                <div class="item-cover-tiny">
                    ${audiobook.cover_url ? `
                        <img src="${audiobook.cover_url}" alt="Audiobook Cover">
                    ` : `
                        <div class="placeholder-cover">
                            <i class="fas fa-headphones"></i>
                        </div>
                    `}
                </div>
                <div class="item-title">
                    <i class="fas fa-chevron-right expand-icon me-2"></i>
                    ${MediaLibraryUtils.escapeHtml(audiobook.title)}
                </div>
                <div class="item-subtitle">
                    by ${MediaLibraryUtils.escapeHtml(audiobook.author)}
                    ${audiobook.narrator ? `<br><small class="text-info">Narrated by ${MediaLibraryUtils.escapeHtml(audiobook.narrator)}</small>` : ''}
                </div>
                <div class="item-info">
                    <div class="item-badges">
                        <span class="badge bg-success">${audiobook.file_format}</span>
                        ${audiobook.series_name ? `<span class="badge bg-info">${MediaLibraryUtils.escapeHtml(audiobook.series_name)}</span>` : ''}
                        <span class="badge bg-warning text-dark">
                            <i class="fas fa-headphones me-1"></i>Audio
                        </span>
                        ${audiobook.duration ? `<span class="badge bg-light text-dark">${MediaLibraryUtils.escapeHtml(audiobook.duration)}</span>` : ''}
                        ${audiobook.is_read ? '<span class="badge bg-success"><i class="fas fa-check me-1"></i>Listened</span>' : ''}
                    </div>
                    <div class="text-muted small">
                        ${MediaLibraryUtils.formatFileSize(audiobook.file_size)}
                    </div>
                </div>
            </div>
            ${this.expandedAudiobooks.has(audiobook.id) ? this.renderAudiobookDetails(audiobook) : ''}
        `).join('');
        
        return headerHtml + itemsHtml;
    }

    renderGridView() {
        return this.filteredData.map(audiobook => `
            <div class="list-item grid-item" data-item-id="${audiobook.id}" onclick="window.sectionManager.selectItem(${audiobook.id})">
                <div class="grid-cover mb-3">
                    ${audiobook.cover_url ? `
                        <img src="${audiobook.cover_url}" alt="Audiobook Cover" class="img-fluid rounded shadow">
                    ` : `
                        <div class="placeholder-cover d-flex align-items-center justify-content-center bg-light rounded">
                            <i class="fas fa-headphones text-muted fa-2x"></i>
                        </div>
                    `}
                </div>
                <div class="item-title">${MediaLibraryUtils.escapeHtml(audiobook.title)}</div>
                <div class="item-subtitle">
                    by ${MediaLibraryUtils.escapeHtml(audiobook.author)}
                    ${audiobook.narrator ? `<br><small class="text-info">Narrated by ${MediaLibraryUtils.escapeHtml(audiobook.narrator)}</small>` : ''}
                </div>
                <div class="item-meta">
                    <div class="item-badges">
                        <span class="badge bg-success">${audiobook.file_format}</span>
                        ${audiobook.series_name ? `<span class="badge bg-info">${MediaLibraryUtils.escapeHtml(audiobook.series_name)}</span>` : ''}
                        <span class="badge bg-warning text-dark">
                            <i class="fas fa-headphones me-1"></i>Audio
                        </span>
                        ${audiobook.duration ? `<span class="badge bg-light text-dark">${MediaLibraryUtils.escapeHtml(audiobook.duration)}</span>` : ''}
                        ${audiobook.is_read ? '<span class="badge bg-success"><i class="fas fa-check me-1"></i>Listened</span>' : ''}
                    </div>
                    <div class="text-muted small mt-1">
                        ${MediaLibraryUtils.formatFileSize(audiobook.file_size)}
                    </div>
                </div>
            </div>
        `).join('');
    }

    renderAudiobookDetails(audiobook) {
        return `
            <div class="audiobook-details-container">
                <div class="list-item audiobook-detail-item ms-4" 
                     onclick="event.stopPropagation(); window.sectionManager.selectItem(${audiobook.id})">
                    <div class="audiobook-file-details">
                        <div class="row">
                            <div class="col-md-6">
                                <h6 class="mb-2"><i class="fas fa-file-audio me-2"></i>Audio File Details</h6>
                                <div class="detail-row">
                                    <strong>File Path:</strong>
                                    <div class="font-monospace small text-muted">${MediaLibraryUtils.escapeHtml(audiobook.file_path || 'Not available')}</div>
                                </div>
                                <div class="detail-row">
                                    <strong>Format:</strong> ${audiobook.file_format}
                                </div>
                                <div class="detail-row">
                                    <strong>File Size:</strong> ${MediaLibraryUtils.formatFileSize(audiobook.file_size)}
                                </div>
                                ${audiobook.duration ? `
                                <div class="detail-row">
                                    <strong>Duration:</strong> ${MediaLibraryUtils.escapeHtml(audiobook.duration)}
                                </div>
                                ` : ''}
                                ${audiobook.bitrate ? `
                                <div class="detail-row">
                                    <strong>Bitrate:</strong> ${audiobook.bitrate}
                                </div>
                                ` : ''}
                            </div>
                            <div class="col-md-6">
                                <h6 class="mb-2"><i class="fas fa-info-circle me-2"></i>Technical Info</h6>
                                ${audiobook.sample_rate ? `
                                <div class="detail-row">
                                    <strong>Sample Rate:</strong> ${audiobook.sample_rate}
                                </div>
                                ` : ''}
                                ${audiobook.channels ? `
                                <div class="detail-row">
                                    <strong>Channels:</strong> ${audiobook.channels}
                                </div>
                                ` : ''}
                                <div class="detail-row">
                                    <strong>Last Scanned:</strong> ${new Date(audiobook.last_scanned).toLocaleString()}
                                </div>
                                ${audiobook.chapters && audiobook.chapters.length > 0 ? `
                                <div class="detail-row">
                                    <strong>Chapters:</strong> ${audiobook.chapters.length} chapters
                                </div>
                                ` : ''}
                            </div>
                        </div>
                        <div class="mt-3">
                            <button class="btn btn-sm btn-success me-2" onclick="event.stopPropagation(); window.sectionManager.playAudiobook(${audiobook.id})">
                                <i class="fas fa-play me-1"></i>Listen
                            </button>
                            <button class="btn btn-sm btn-outline-primary me-2" onclick="event.stopPropagation(); window.sectionManager.downloadAudiobook(${audiobook.id})">
                                <i class="fas fa-download me-1"></i>Download
                            </button>
                            <button class="btn btn-sm btn-outline-info" onclick="event.stopPropagation(); window.sectionManager.showFileInfo(${audiobook.id})">
                                <i class="fas fa-info-circle me-1"></i>More Info
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }

    toggleAudiobook(audiobookId) {
        if (this.expandedAudiobooks.has(audiobookId)) {
            this.expandedAudiobooks.delete(audiobookId);
        } else {
            this.expandedAudiobooks.add(audiobookId);
        }
        this.renderList();
    }

    bindAudiobooksEvents() {
        // Audiobook-specific event bindings
        document.addEventListener('click', (e) => {
            if (e.target.matches('.download-audiobook-btn')) {
                e.preventDefault();
                const audiobookId = e.target.dataset.audiobookId;
                this.downloadAudiobook(audiobookId);
            }
        });
    }

    loadDetail(audiobookId) {
        const container = document.querySelector(this.config.detailContainer);
        this.showLoadingState(container, 'Loading audiobook details...');
        
        // Find the audiobook data locally since we already have it
        const audiobook = this.currentData.find(a => a.id == audiobookId);
        if (audiobook) {
            this.renderAudiobookDetail(audiobook);
            
            // Handle mobile layout
            if (window.innerWidth <= 768) {
                this.handleMobileLayout();
                this.addMobileBackButton();
            }
        } else {
            container.innerHTML = `
                <div class="alert alert-danger m-3">
                    <i class="fas fa-exclamation-triangle me-2"></i>
                    Audiobook not found. Please try again.
                </div>
            `;
        }
    }

    renderAudiobookDetail(audiobook) {
        const container = document.querySelector(this.config.detailContainer);
        
        const html = `
            <div class="detail-content">
                <div class="detail-header">
                    <h2 class="detail-title">
                        <i class="fas fa-headphones me-2 text-primary"></i>
                        ${MediaLibraryUtils.escapeHtml(audiobook.title)}
                    </h2>
                    <h5 class="detail-subtitle">
                        by ${MediaLibraryUtils.escapeHtml(audiobook.author)}
                        ${audiobook.narrator ? `<br><small class="text-info">Narrated by ${MediaLibraryUtils.escapeHtml(audiobook.narrator)}</small>` : ''}
                    </h5>
                    <div class="detail-meta">
                        <div class="detail-meta-item">
                            <div class="detail-meta-label">Format</div>
                            <div class="detail-meta-value">${audiobook.file_format}</div>
                        </div>
                        <div class="detail-meta-item">
                            <div class="detail-meta-label">Duration</div>
                            <div class="detail-meta-value">${audiobook.duration || 'Unknown'}</div>
                        </div>
                        <div class="detail-meta-item">
                            <div class="detail-meta-label">Size</div>
                            <div class="detail-meta-value">${MediaLibraryUtils.formatFileSize(audiobook.file_size)}</div>
                        </div>
                        ${audiobook.series_name ? `
                        <div class="detail-meta-item">
                            <div class="detail-meta-label">Series</div>
                            <div class="detail-meta-value">${MediaLibraryUtils.escapeHtml(audiobook.series_name)}</div>
                        </div>
                        ` : ''}
                    </div>
                </div>
                
                ${audiobook.description ? `
                <div class="detail-description">
                    <h6 class="fw-bold mb-3">Description</h6>
                    <p>${MediaLibraryUtils.escapeHtml(audiobook.description)}</p>
                </div>
                ` : ''}
                
                <div class="detail-actions">
                    <button class="btn btn-success" onclick="window.sectionManager.playAudiobook(${audiobook.id})">
                        <i class="fas fa-play me-1"></i>Listen
                    </button>
                    <button class="btn btn-outline-primary" onclick="window.sectionManager.downloadAudiobook(${audiobook.id})">
                        <i class="fas fa-download me-1"></i>Download
                    </button>
                    <button class="btn btn-outline-success" onclick="window.sectionManager.toggleRead(${audiobook.id})">
                        <i class="fas fa-check me-1"></i>
                        ${audiobook.is_read ? 'Mark as Not Listened' : 'Mark as Listened'}
                    </button>
                    <button class="btn btn-outline-info" onclick="window.sectionManager.showFileInfo(${audiobook.id})">
                        <i class="fas fa-info-circle me-1"></i>File Info
                    </button>
                </div>
            </div>
        `;
        
        container.innerHTML = html;
        container.classList.add('fade-in');
    }

    playAudiobook(audiobookId) {
        // Find the audiobook
        const audiobook = this.currentData.find(a => a.id == audiobookId);
        if (!audiobook) {
            MediaLibraryUtils.showToast('Audiobook not found', 'danger');
            return;
        }

        // In a real implementation, this would open an audio player or external player
        MediaLibraryUtils.showToast('Audio player functionality not yet implemented', 'info');
    }

    downloadAudiobook(audiobookId) {
        const urls = window.audiobooksConfig?.ajax_urls;
        if (!urls?.download) {
            MediaLibraryUtils.showToast('Download functionality not available', 'warning');
            return;
        }

        const downloadUrl = urls.download.replace('{id}', audiobookId);
        window.open(downloadUrl, '_blank');
        MediaLibraryUtils.showToast('Starting download...', 'success');
    }

    toggleRead(audiobookId) {
        const urls = window.audiobooksConfig?.ajax_urls;
        if (!urls?.toggle_read) {
            MediaLibraryUtils.showToast('Toggle read functionality not available', 'warning');
            return;
        }

        const audiobook = this.currentData.find(a => a.id == audiobookId);
        if (!audiobook) {
            MediaLibraryUtils.showToast('Audiobook not found', 'danger');
            return;
        }

        const action = audiobook.is_read ? 'Mark as Not Listened' : 'Mark as Listened';
        
        fetch(urls.toggle_read, {
            method: 'POST',
            headers: {
                'X-CSRFToken': this.getCsrfToken(),
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                audiobook_id: audiobookId
            })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                // Update local data
                audiobook.is_read = data.is_read;
                
                // Refresh the display
                this.renderList();
                if (this.selectedItemId == audiobookId) {
                    this.renderAudiobookDetail(audiobook);
                }
                
                MediaLibraryUtils.showToast(`${action} successful`, 'success');
            } else {
                MediaLibraryUtils.showToast(`Error: ${data.error || 'Unknown error'}`, 'danger');
            }
        })
        .catch(error => {
            console.error('Error toggling read status:', error);
            MediaLibraryUtils.showToast('Error updating status. Please try again.', 'danger');
        });
    }

    showFileInfo(audiobookId) {
        const audiobook = this.currentData.find(a => a.id == audiobookId);
        if (!audiobook) {
            MediaLibraryUtils.showToast('Audiobook not found', 'danger');
            return;
        }

        const modal = document.createElement('div');
        modal.className = 'modal fade';
        modal.innerHTML = `
            <div class="modal-dialog">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title">File Information</h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body">
                        <table class="table table-borderless">
                            <tr><td><strong>File Path:</strong></td><td class="font-monospace">${MediaLibraryUtils.escapeHtml(audiobook.file_path || 'Not available')}</td></tr>
                            <tr><td><strong>File Size:</strong></td><td>${MediaLibraryUtils.formatFileSize(audiobook.file_size)}</td></tr>
                            <tr><td><strong>Format:</strong></td><td>${audiobook.file_format}</td></tr>
                            <tr><td><strong>Duration:</strong></td><td>${audiobook.duration || 'Unknown'}</td></tr>
                            <tr><td><strong>Last Scanned:</strong></td><td>${new Date(audiobook.last_scanned).toLocaleString()}</td></tr>
                            ${audiobook.bitrate ? `<tr><td><strong>Bitrate:</strong></td><td>${audiobook.bitrate}</td></tr>` : ''}
                            ${audiobook.sample_rate ? `<tr><td><strong>Sample Rate:</strong></td><td>${audiobook.sample_rate}</td></tr>` : ''}
                        </table>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Close</button>
                    </div>
                </div>
            </div>
        `;
        
        document.body.appendChild(modal);
        const bsModal = new bootstrap.Modal(modal);
        bsModal.show();
        
        // Clean up modal after it's hidden
        modal.addEventListener('hidden.bs.modal', () => {
            modal.remove();
        });
    }

    onItemActivate(audiobookId) {
        this.playAudiobook(audiobookId);
    }
}

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    if (typeof window.audiobooksConfig !== 'undefined') {
        window.sectionManager = new AudiobooksSectionManager();
    }
});
