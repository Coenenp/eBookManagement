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
            detailEndpoint: window.comicsConfig?.ajax_urls?.detail || '/books/comics/ajax/detail/',
        });

        this.expandedSeries = new Set();
    }

    filterItems(searchTerm, sortBy, formatFilter, statusFilter) {
        // Filter comics data
        this.filteredData = this.currentData.filter((series) => {
            const matchesSearch =
                !searchTerm ||
                series.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
                series.books.some(
                    (book) =>
                        book.title.toLowerCase().includes(searchTerm.toLowerCase()) ||
                        book.author.toLowerCase().includes(searchTerm.toLowerCase())
                );

            const matchesFormat = !formatFilter || series.books.some((book) => book.file_format === formatFilter);

            const matchesStatus =
                !statusFilter ||
                (statusFilter === 'read' && series.books.every((book) => book.is_read)) ||
                (statusFilter === 'unread' && series.books.every((book) => !book.is_read)) ||
                (statusFilter === 'reading' && series.books.some((book) => book.reading_progress > 0 && !book.is_read));

            return matchesSearch && matchesFormat && matchesStatus;
        });

        // Sort results
        this.sortComicsData(sortBy);

        this.renderList();
        this.updateItemCount(this.filteredData.length);
    }

    sortComicsData(sortBy) {
        this.filteredData.sort((a, b) => {
            switch (sortBy) {
                case 'title':
                    return a.name.localeCompare(b.name);
                case 'author':
                    const aAuthor = a.books[0]?.author || '';
                    const bAuthor = b.books[0]?.author || '';
                    return aAuthor.localeCompare(bAuthor);
                case 'date':
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
                'No Comics Found',
                'No comics match your current filters.',
                'fas fa-mask'
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

        this.bindComicsEvents();
    }

    renderGridView() {
        let html = '';

        // Render series
        if (this.filteredData.length > 0) {
            html += '<div class="comics-section"><h6 class="text-muted mb-3">Series</h6>';
            html += this.filteredData
                .map(
                    (series) => `
                <div class="list-item grid-item comic-series-item" data-series-id="${series.id}" onclick="window.comicsManager.toggleSeries(${series.id})">
                    <div class="grid-cover mb-3 position-relative">
                        ${
                            series.cover_url
                                ? `
                            <img src="${series.cover_url}" alt="Series Cover" class="img-fluid rounded shadow">
                        `
                                : `
                            <div class="placeholder-cover d-flex align-items-center justify-content-center bg-light rounded">
                                <i class="fas fa-mask text-muted fa-2x"></i>
                            </div>
                        `
                        }
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
            `
                )
                .join('');
            html += '</div>';
        }

        return html;
    }

    renderListView() {
        // Condensed table view with series rows that expand to show issues
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
                            <th class="col-size" data-sort="total_books">
                                Issues <i class="fas fa-sort sort-icon"></i>
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
                            <tr class="${this.expandedSeries.has(series.id) ? 'expanded' : ''}" 
                                data-series-id="${series.id}">
                                <td style="cursor: pointer; text-align: center;" onclick="event.stopPropagation(); window.comicsManager.toggleSeries(${series.id})">
                                    <i class="fas fa-chevron-right expand-icon" style="transition: transform 0.2s; ${this.expandedSeries.has(series.id) ? 'transform: rotate(90deg);' : ''}"></i>
                                </td>
                                <td class="col-title truncate" title="${MediaLibraryUtils.escapeHtml(series.name)}" style="cursor: pointer;" onclick="window.comicsManager.toggleSeries(${series.id})">
                                    <i class="fas fa-mask file-icon"></i>
                                    ${MediaLibraryUtils.escapeHtml(series.name)}
                                </td>
                                <td class="col-author truncate" title="${series.authors.join(', ')}" style="cursor: pointer;" onclick="window.comicsManager.toggleSeries(${series.id})">
                                    ${series.authors.map((a) => MediaLibraryUtils.escapeHtml(a)).join(', ')}
                                </td>
                                <td class="col-format" style="cursor: pointer;" onclick="window.comicsManager.toggleSeries(${series.id})">
                                    ${series.formats.map((f) => `<span class="badge bg-secondary me-1">${f.toUpperCase()}</span>`).join('')}
                                </td>
                                <td class="col-size" style="cursor: pointer;" onclick="window.comicsManager.toggleSeries(${series.id})">${series.total_books}</td>
                                <td class="col-size" style="cursor: pointer;" onclick="window.comicsManager.toggleSeries(${series.id})">${MediaLibraryUtils.formatFileSize(series.total_size)}</td>
                            </tr>
                            ${this.expandedSeries.has(series.id) ? this.renderSeriesIssuesRows(series) : ''}
                        `
                            )
                            .join('')}
                    </tbody>
                </table>
            </div>
        `;

        return tableHtml;
    }

    renderSeriesIssuesRows(series) {
        return series.books
            .map(
                (book) => `
            <tr class="series-book-row ${this.selectedItemId === book.id ? 'selected' : ''}" 
                style="background-color: var(--bs-secondary-bg);" 
                data-item-id="${book.id}" 
                onclick="window.comicsManager.selectItem(${book.id})">
                <td></td>
                <td class="col-title truncate" style="padding-left: 40px; cursor: pointer;" title="${MediaLibraryUtils.escapeHtml(book.title)}">
                    <i class="fas fa-book-open me-2" style="color: var(--bs-secondary);"></i>
                    ${book.position ? `#${book.position} - ` : ''}${MediaLibraryUtils.escapeHtml(book.title)}
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
                         onclick="event.stopPropagation(); window.comicsManager.selectItem(${book.id})">
                        <div class="item-cover-tiny ms-4">
                            ${
                                book.cover_url
                                    ? `
                                <img src="${book.cover_url}" alt="Issue Cover">
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
                    'X-Requested-With': 'XMLHttpRequest',
                },
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
                                ${
                                    comic.cover_url
                                        ? `
                                    <img src="${comic.cover_url}" alt="Comic Cover" class="img-fluid rounded shadow-sm">
                                `
                                        : `
                                    <div class="placeholder-cover d-flex align-items-center justify-content-center bg-light rounded">
                                        <i class="fas fa-mask text-muted"></i>
                                    </div>
                                `
                                }
                            </div>
                        </div>
                        <div class="col">
                            <h4 class="mb-1">${MediaLibraryUtils.escapeHtml(comic.title)}</h4>
                            <p class="text-muted mb-0">
                                <i class="fas fa-user me-1"></i>${MediaLibraryUtils.escapeHtml(comic.author)}
                            </p>
                            ${
                                comic.series
                                    ? `
                                <small class="text-muted">
                                    <i class="fas fa-layer-group me-1"></i>Part of series: ${MediaLibraryUtils.escapeHtml(comic.series)}
                                </small>
                            `
                                    : ''
                            }
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
                    <div class="row mt-2">
                        <div class="col">
                            <a href="/book/${comic.id}/" class="btn btn-primary btn-sm w-100">
                                <i class="fas fa-eye me-1"></i>View Full Details
                            </a>
                        </div>
                </div>

                <!-- Tabbed content area -->
                <div class="detail-content flex-fill">
                    <ul class="nav nav-tabs px-3 pt-2" role="tablist">
                        <li class="nav-item" role="presentation">
                            <button class="nav-link active" data-bs-toggle="tab" data-bs-target="#comic-info-${comic.id}" type="button" role="tab">
                                <i class="fas fa-info-circle me-1"></i>Info
                            </button>
                        </li>
                        <li class="nav-item" role="presentation">
                            <button class="nav-link" data-bs-toggle="tab" data-bs-target="#comic-meta-${comic.id}" type="button" role="tab">
                                <i class="fas fa-tags me-1"></i>Meta
                            </button>
                        </li>
                        <li class="nav-item" role="presentation">
                            <button class="nav-link" data-bs-toggle="tab" data-bs-target="#comic-files-${comic.id}" type="button" role="tab">
                                <i class="fas fa-folder me-1"></i>Files
                            </button>
                        </li>
                    </ul>
                    
                    <div class="tab-content">
                        <div class="tab-pane fade show active" id="comic-info-${comic.id}" role="tabpanel">
                            <div class="p-3">
                                ${this.renderComicInformation(comic)}
                            </div>
                        </div>
                        
                        <div class="tab-pane fade" id="comic-meta-${comic.id}" role="tabpanel">
                            <div class="p-3">
                                ${this.renderComicMetadata(comic)}
                            </div>
                        </div>
                        
                        <div class="tab-pane fade" id="comic-files-${comic.id}" role="tabpanel">
                            <div class="p-3">
                                ${this.renderComicFilesTab(comic)}
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `;

        container.innerHTML = html;
    }

    renderComicInformation(comic) {
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
            if (comic.file_format) return comic.file_format.toUpperCase();
            if (comic.file_path) {
                const ext = comic.file_path.split('.').pop();
                return ext ? ext.toUpperCase() : null;
            }
            return null;
        };

        const fileFormat = getFileFormat();
        const pubYear = formatYear(comic.publication_date);

        // Split file path into scan folder and relative path
        const getPathParts = () => {
            if (!comic.file_path) return null;

            const fullPath = comic.file_path;
            const scanFolderPath = comic.scan_folder_path || '';

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
                    scanFolder: comic.scan_folder_name || scanFolderPath,
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

        // Helper for confidence/completeness badges
        const getQualityBadge = (value) => {
            const percent = Math.round(value * 100);
            const colorClass = percent >= 80 ? 'bg-success' : (percent >= 50 ? 'bg-warning' : 'bg-danger');
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
                    ${comic.publisher ? `<div class="mb-2"><i class="fas fa-building me-2 text-muted"></i><strong>Publisher:</strong> ${MediaLibraryUtils.escapeHtml(comic.publisher)}</div>` : ''}
                    
                    <!-- Issue Number -->
                    ${comic.issue_number ? `<div class="mb-2"><i class="fas fa-hashtag me-2 text-muted"></i><strong>Issue Number:</strong> ${MediaLibraryUtils.escapeHtml(comic.issue_number)}</div>` : ''}
                    
                    <!-- Publication Year -->
                    ${pubYear ? `<div class="mb-2"><i class="fas fa-calendar me-2 text-muted"></i><strong>Year:</strong> ${pubYear}</div>` : ''}
                    
                    <!-- Genre -->
                    ${comic.genre ? `<div class="mb-2"><i class="fas fa-tags me-2 text-muted"></i><strong>Genre:</strong> ${MediaLibraryUtils.escapeHtml(comic.genre)}</div>` : ''}
                    
                    <!-- Format & File Size (together) -->
                    ${fileFormat || (comic.file_size && comic.file_size > 0) ? `<div class="mb-2"><i class="fas fa-file-alt me-2 text-muted"></i><strong>Format & Size:</strong> ${fileFormat ? `<span class="badge ${getFormatColor(comic.file_format)}">${fileFormat}</span>` : ''} ${comic.file_size && comic.file_size > 0 ? MediaLibraryUtils.formatFileSize(comic.file_size) : ''}</div>` : ''}
                    
                    <!-- Scan Folder & Path -->
                    ${
                        pathParts
                            ? `
                    <div class="mb-2">
                        ${pathParts.scanFolder && comic.scan_folder_id ? `<div class="mb-1"><i class="fas fa-hdd me-2 text-muted"></i><strong>Scan Folder:</strong> <a href="/scan_folders/${comic.scan_folder_id}/edit/" class="text-primary text-decoration-none">${MediaLibraryUtils.escapeHtml(pathParts.scanFolder)}</a></div>` : pathParts.scanFolder ? `<div class="mb-1"><i class="fas fa-hdd me-2 text-muted"></i><strong>Scan Folder:</strong> ${MediaLibraryUtils.escapeHtml(pathParts.scanFolder)}</div>` : ''}
                        ${pathParts.directory ? `<div class="mb-1"><i class="fas fa-folder me-2 text-muted"></i><strong>Path:</strong> <code class="small">${MediaLibraryUtils.escapeHtml(pathParts.directory)}</code></div>` : ''}
                        <div class="d-flex align-items-center">
                            <div class="flex-grow-1"><i class="fas fa-file me-2 text-muted"></i><strong>Filename:</strong> <code class="small fw-bold">${MediaLibraryUtils.escapeHtml(pathParts.filename)}</code></div>
                            <button type="button" class="btn btn-outline-secondary btn-sm ms-2" onclick="MediaLibraryUtils.openFileLocation(decodeURIComponent('${encodeURIComponent(comic.file_path)}'))" title="Open file location">
                                <i class="fas fa-folder-open"></i>
                            </button>
                        </div>
                    </div>
                    `
                            : ''
                    }
                    
                    <!-- Last Scanned -->
                    ${comic.last_scanned ? `<div class="mb-2"><i class="fas fa-clock me-2 text-muted"></i><strong>Last Scanned:</strong> ${MediaLibraryUtils.formatDate(comic.last_scanned)}</div>` : ''}
                    
                    <!-- Confidence Score -->
                    ${comic.confidence !== undefined && comic.confidence !== null ? `<div class="mb-2"><strong>Confidence:</strong> ${getQualityBadge(comic.confidence)}</div>` : ''}
                    
                    <!-- Completeness Score -->
                    ${comic.completeness !== undefined && comic.completeness !== null ? `<div class="mb-2"><strong>Completeness:</strong> ${getQualityBadge(comic.completeness)}</div>` : ''}
                    
                    <!-- Reading Status -->
                    <div class="mb-2"><strong>Reading Status:</strong> 
                        ${
                            comic.is_read
                                ? '<span class="badge bg-success">Read</span>'
                                : '<span class="badge bg-secondary">Unread</span>'
                        }
                    </div>
                </div>
                
                ${
                    comic.description
                        ? `
                    <div class="mt-4">
                        <strong>Description:</strong>
                        <div class="description-content mt-2">
                            ${MediaLibraryUtils.sanitizeHtml(comic.description)}
                        </div>
                    </div>
                `
                        : ''
                }
            </div>
        `;
    }

    renderComicMetadata(comic) {
        const metadata = comic.metadata || [];

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
                    comic.file_path
                        ? `
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
                `
                        : ''
                }
            </div>
        `;
    }

    renderComicFilesTab(comic) {
        return `
            <div class="d-flex justify-content-between align-items-center mb-3">
                <h6 class="fw-bold mb-0">Comic Files</h6>
                <button type="button" class="btn btn-outline-primary btn-sm load-comic-files-btn" 
                        data-comic-id="${comic.id}">
                    <i class="fas fa-sync me-1"></i>Load Files
                </button>
            </div>
            
            <div id="comic-files-container">
                <div class="text-center text-muted p-4">
                    <i class="fas fa-folder-open fa-2x mb-2"></i>
                    <p>Click "Load Files" to scan for related files in the same directory.</p>
                </div>
            </div>
        `;
    }

    formatMetadataKey(key) {
        return key.replace(/_/g, ' ').replace(/\b\w/g, (l) => l.toUpperCase());
    }

    downloadComic(comicId, filename) {
        try {
            const downloadUrl =
                window.comicsConfig?.ajax_urls?.download?.replace('{id}', comicId) ||
                `/books/comics/${comicId}/download/`;
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
                body: JSON.stringify({ comic_id: comicId }),
            });

            if (data.success) {
                MediaLibraryUtils.showToast(`Comic marked as ${data.is_read ? 'read' : 'unread'}`, 'success');

                // Update the item in current data
                const updateItems = (items) => {
                    const item = items.find((c) => c.id == comicId);
                    if (item) item.is_read = data.is_read;
                };

                updateItems(this.currentStandaloneComics);

                // Update in series
                this.currentData.forEach((series) => {
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

// Initialize the comics manager when the DOM is ready
document.addEventListener('DOMContentLoaded', function () {
    console.log('Comics DOMContentLoaded - Creating ComicsSectionManager');
    try {
        window.comicsManager = new ComicsSectionManager();
        console.log('Comics manager created successfully:', window.comicsManager);
    } catch (error) {
        console.error('Error creating comics manager:', error);
    }

    // Set up event delegation for clear filters button
    document.addEventListener('click', function (e) {
        if (e.target.closest('.clear-filters-btn')) {
            e.preventDefault();
            clearFilters();
        }
    });
});
