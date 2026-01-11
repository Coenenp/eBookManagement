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
            detailEndpoint: window.audiobooksConfig?.ajax_urls?.detail || '/books/audiobooks/ajax/detail/',
        });

        this.expandedAudiobooks = new Set();
    }

    filterItems(searchTerm, sortBy, formatFilter, statusFilter) {
        this.filteredData = this.currentData.filter((audiobook) => {
            // Search filter
            const matchesSearch =
                !searchTerm ||
                audiobook.title.toLowerCase().includes(searchTerm.toLowerCase()) ||
                audiobook.author.toLowerCase().includes(searchTerm.toLowerCase()) ||
                (audiobook.narrator && audiobook.narrator.toLowerCase().includes(searchTerm.toLowerCase()));

            // Format filter - extract format from file_format field
            const bookFormat = audiobook.file_format ? audiobook.file_format.toLowerCase() : '';
            const matchesFormat = !formatFilter || bookFormat === formatFilter.toLowerCase();

            // Status filter
            const matchesStatus =
                !statusFilter ||
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
            switch (sortBy) {
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
            MediaLibraryUtils.showEmptyState(
                container,
                'No Audiobooks Found',
                'No audiobooks match your current filters.',
                'fas fa-headphones'
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

        this.bindAudiobooksEvents();
    }

    renderListView() {
        // Condensed table view with expandable rows for companion audio files
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
                        ${this.filteredData
                            .map(
                                (audiobook) => `
                            <tr class="${this.selectedItemId === audiobook.id ? 'selected' : ''} ${this.expandedAudiobooks.has(audiobook.id) ? 'expanded' : ''}" 
                                data-item-id="${audiobook.id}">
                                <td style="cursor: pointer; text-align: center;" onclick="event.stopPropagation(); window.sectionManager.toggleAudiobook(${audiobook.id})">
                                    <i class="fas fa-chevron-right expand-icon" style="transition: transform 0.2s; ${this.expandedAudiobooks.has(audiobook.id) ? 'transform: rotate(90deg);' : ''}"></i>
                                </td>
                                <td class="col-title truncate" title="${MediaLibraryUtils.escapeHtml(audiobook.title)}" onclick="window.sectionManager.selectItem(${audiobook.id})" style="cursor: pointer;">
                                    <i class="fas fa-headphones file-icon"></i>
                                    ${MediaLibraryUtils.escapeHtml(audiobook.title)}
                                </td>
                                <td class="col-author truncate" title="${MediaLibraryUtils.escapeHtml(audiobook.author || '')}" onclick="window.sectionManager.selectItem(${audiobook.id})" style="cursor: pointer;">
                                    ${MediaLibraryUtils.escapeHtml(audiobook.author || '-')}
                                </td>
                                <td class="col-series truncate" title="${MediaLibraryUtils.escapeHtml(audiobook.series_name || '')}" onclick="window.sectionManager.selectItem(${audiobook.id})" style="cursor: pointer;">
                                    ${MediaLibraryUtils.escapeHtml(audiobook.series_name || '-')}
                                </td>
                                <td class="col-publisher truncate" title="${MediaLibraryUtils.escapeHtml(audiobook.publisher || '')}" onclick="window.sectionManager.selectItem(${audiobook.id})" style="cursor: pointer;">
                                    ${MediaLibraryUtils.escapeHtml(audiobook.publisher || '-')}
                                </td>
                                <td class="col-format" onclick="window.sectionManager.selectItem(${audiobook.id})" style="cursor: pointer;">
                                    <span class="badge bg-secondary">${(audiobook.file_format || '').toUpperCase()}</span>
                                </td>
                                <td class="col-size" onclick="window.sectionManager.selectItem(${audiobook.id})" style="cursor: pointer;">${MediaLibraryUtils.formatFileSize(audiobook.file_size)}</td>
                                <td class="col-year" onclick="window.sectionManager.selectItem(${audiobook.id})" style="cursor: pointer;">${audiobook.publication_date?.substring(0, 4) || '-'}</td>
                                <td class="col-language" onclick="window.sectionManager.selectItem(${audiobook.id})" style="cursor: pointer;">${(audiobook.language || 'en').toUpperCase()}</td>
                                <td class="col-path truncate" title="${MediaLibraryUtils.escapeHtml(audiobook.file_path || audiobook.scan_folder || '')}" onclick="window.sectionManager.selectItem(${audiobook.id})" style="cursor: pointer;">
                                    ${this.getShortPath(audiobook.file_path || audiobook.scan_folder || '')}
                                </td>
                                <td class="col-status" onclick="window.sectionManager.selectItem(${audiobook.id})" style="cursor: pointer;">
                                    ${
                                        audiobook.is_finished
                                            ? '<span class="badge bg-success" title="Finished">✓</span>'
                                            : audiobook.reading_progress > 0
                                              ? '<span class="badge bg-warning" title="Listening">🎧</span>'
                                              : '<span class="badge bg-secondary" title="Not Started">○</span>'
                                    }
                                </td>
                            </tr>
                            ${this.expandedAudiobooks.has(audiobook.id) ? this.renderCompanionFilesRow(audiobook) : ''}
                        `
                            )
                            .join('')}
                    </tbody>
                </table>
            </div>
        `;

        return tableHtml;
    }

    renderCompanionFilesRow(audiobook) {
        if (!audiobook.audio_files || audiobook.audio_files.length === 0) {
            return `
                <tr class="companion-row">
                    <td></td>
                    <td colspan="10" style="padding-left: 40px; font-size: 0.75rem; color: var(--bs-secondary);">
                        <i class="fas fa-info-circle me-2"></i>No audio files found
                    </td>
                </tr>
            `;
        }

        return audiobook.audio_files
            .map(
                (file) => `
            <tr class="companion-row" style="background-color: var(--bs-secondary-bg);">
                <td></td>
                <td colspan="10" style="padding-left: 40px; font-size: 0.75rem;">
                    <i class="fas fa-file-audio me-2" style="color: var(--bs-secondary);"></i>
                    <span style="font-family: monospace;">${MediaLibraryUtils.escapeHtml(file.name)}</span>
                    <span class="badge bg-info ms-2">${file.type.toUpperCase()}</span>
                    <span class="text-muted ms-2">${MediaLibraryUtils.formatFileSize(file.size)}</span>
                    ${file.duration ? `<span class="text-muted ms-2"><i class="fas fa-clock me-1"></i>${file.duration}</span>` : ''}
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

    renderGridView() {
        return this.filteredData
            .map(
                (audiobook) => `
            <div class="list-item grid-item" data-item-id="${audiobook.id}" onclick="window.sectionManager.selectItem(${audiobook.id})">
                <div class="grid-cover mb-3">
                    ${
                        audiobook.cover_url
                            ? `
                        <img src="${audiobook.cover_url}" alt="Audiobook Cover" class="img-fluid rounded shadow">
                    `
                            : `
                        <div class="placeholder-cover d-flex align-items-center justify-content-center bg-light rounded">
                            <i class="fas fa-headphones text-muted fa-2x"></i>
                        </div>
                    `
                    }
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
        `
            )
            .join('');
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
                                ${
                                    audiobook.duration
                                        ? `
                                <div class="detail-row">
                                    <strong>Duration:</strong> ${MediaLibraryUtils.escapeHtml(audiobook.duration)}
                                </div>
                                `
                                        : ''
                                }
                                ${
                                    audiobook.bitrate
                                        ? `
                                <div class="detail-row">
                                    <strong>Bitrate:</strong> ${audiobook.bitrate}
                                </div>
                                `
                                        : ''
                                }
                            </div>
                            <div class="col-md-6">
                                <h6 class="mb-2"><i class="fas fa-info-circle me-2"></i>Technical Info</h6>
                                ${
                                    audiobook.sample_rate
                                        ? `
                                <div class="detail-row">
                                    <strong>Sample Rate:</strong> ${audiobook.sample_rate}
                                </div>
                                `
                                        : ''
                                }
                                ${
                                    audiobook.channels
                                        ? `
                                <div class="detail-row">
                                    <strong>Channels:</strong> ${audiobook.channels}
                                </div>
                                `
                                        : ''
                                }
                                <div class="detail-row">
                                    <strong>Last Scanned:</strong> ${new Date(audiobook.last_scanned).toLocaleString()}
                                </div>
                                ${
                                    audiobook.chapters && audiobook.chapters.length > 0
                                        ? `
                                <div class="detail-row">
                                    <strong>Chapters:</strong> ${audiobook.chapters.length} chapters
                                </div>
                                `
                                        : ''
                                }
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
                                <i class="fas fa-info-circle me-1"></i>Info
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
        const audiobook = this.currentData.find((a) => a.id == audiobookId);
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
            <div class="audiobook-detail-wrapper h-100">
                <!-- Header with audiobook title and cover -->
                <div class="detail-header p-3 border-bottom bg-white sticky-top">
                    <div class="row align-items-center">
                        <div class="col-auto">
                            <div class="detail-cover-small">
                                ${
                                    audiobook.cover_url
                                        ? `
                                    <img src="${audiobook.cover_url}" alt="Audiobook Cover" class="img-fluid rounded shadow-sm">
                                `
                                        : `
                                    <div class="placeholder-cover d-flex align-items-center justify-content-center bg-light rounded">
                                        <i class="fas fa-headphones text-muted"></i>
                                    </div>
                                `
                                }
                            </div>
                        </div>
                        <div class="col">
                            <h4 class="mb-1">${MediaLibraryUtils.escapeHtml(audiobook.title)}</h4>
                            <p class="text-muted mb-0">
                                <i class="fas fa-user me-1"></i>${MediaLibraryUtils.escapeHtml(audiobook.author)}
                                ${audiobook.narrator ? `<br><small class="text-info"><i class="fas fa-microphone me-1"></i>Narrated by ${MediaLibraryUtils.escapeHtml(audiobook.narrator)}</small>` : ''}
                            </p>
                        </div>
                        <div class="col-auto">
                            <div class="btn-group" role="group">
                                <button type="button" class="btn btn-outline-success btn-sm" 
                                        onclick="window.sectionManager.playAudiobook(${audiobook.id})">
                                    <i class="fas fa-play me-1"></i>Listen
                                </button>
                                <button type="button" class="btn btn-outline-primary btn-sm" 
                                        onclick="window.sectionManager.downloadAudiobook(${audiobook.id})">
                                    <i class="fas fa-download me-1"></i>Download
                                </button>
                                <button type="button" class="btn btn-outline-secondary btn-sm" 
                                        onclick="window.sectionManager.toggleRead(${audiobook.id})">
                                    <i class="fas fa-${audiobook.is_read ? 'times' : 'check'} me-1"></i>
                                    ${audiobook.is_read ? 'Mark Unlistened' : 'Mark Listened'}
                                </button>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- Audiobook content with tabs -->
                <div class="detail-content flex-fill">
                    <ul class="nav nav-tabs px-3 pt-2" role="tablist">
                        <li class="nav-item" role="presentation">
                            <button class="nav-link active" data-bs-toggle="tab" data-bs-target="#audiobook-info-${audiobook.id}" type="button" role="tab">
                                <i class="fas fa-info-circle me-1"></i>Info
                            </button>
                        </li>
                        <li class="nav-item" role="presentation">
                            <button class="nav-link" data-bs-toggle="tab" data-bs-target="#audiobook-meta-${audiobook.id}" type="button" role="tab">
                                <i class="fas fa-tags me-1"></i>Meta
                            </button>
                        </li>
                        <li class="nav-item" role="presentation">
                            <button class="nav-link" data-bs-toggle="tab" data-bs-target="#audiobook-files-${audiobook.id}" type="button" role="tab">
                                <i class="fas fa-folder me-1"></i>Files
                            </button>
                        </li>
                    </ul>
                    <div class="tab-content">
                        <div class="tab-pane fade show active" id="audiobook-info-${audiobook.id}" role="tabpanel">
                            ${this.renderAudiobookInfoTab(audiobook)}
                        </div>
                        <div class="tab-pane fade" id="audiobook-meta-${audiobook.id}" role="tabpanel">
                            ${this.renderAudiobookMetadataTab(audiobook)}
                        </div>
                        <div class="tab-pane fade" id="audiobook-files-${audiobook.id}" role="tabpanel">
                            ${this.renderAudiobookFilesTab(audiobook)}
                        </div>
                    </div>
                </div>
            </div>
        `;

        container.innerHTML = html;
        container.classList.add('fade-in');
    }

    renderAudiobookInfoTab(audiobook) {
        const getFileFormat = () => {
            if (audiobook.file_format) return audiobook.file_format.toUpperCase();
            if (audiobook.file_path) {
                const ext = audiobook.file_path.split('.').pop();
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
        const languageName = getLanguageName(audiobook.language);

        // Split file path into scan folder and relative path
        const getPathParts = () => {
            if (!audiobook.file_path) return null;

            const fullPath = audiobook.file_path;
            const scanFolderPath = audiobook.scan_folder_path || '';

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
                    scanFolder: audiobook.scan_folder_name || scanFolderPath,
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
                    ${audiobook.publisher ? `<div class="mb-2"><i class="fas fa-building me-2 text-muted"></i><strong>Publisher:</strong> ${MediaLibraryUtils.escapeHtml(audiobook.publisher)}</div>` : ''}
                    ${pubYear ? `<div class="mb-2"><i class="fas fa-calendar me-2 text-muted"></i><strong>Year:</strong> ${pubYear}</div>` : ''}
                    ${languageName ? `<div class="mb-2"><i class="fas fa-language me-2 text-muted"></i><strong>Language:</strong> ${MediaLibraryUtils.escapeHtml(languageName)}</div>` : ''}
                    ${fileFormat && audiobook.file_size ? `<div class="mb-2"><i class="fas fa-file-alt me-2 text-muted"></i><strong>Format & Size:</strong> <span class="badge ${getFormatColor(audiobook.file_format)}">${fileFormat}</span> · ${MediaLibraryUtils.formatFileSize(audiobook.file_size)}</div>` : fileFormat ? `<div class="mb-2"><i class="fas fa-file-alt me-2 text-muted"></i><strong>Format:</strong> <span class="badge ${getFormatColor(audiobook.file_format)}">${fileFormat}</span></div>` : ''}
                    ${audiobook.duration ? `<div class="mb-2"><i class="fas fa-headphones me-2 text-muted"></i><strong>Duration:</strong> ${audiobook.duration}</div>` : ''}
                    ${audiobook.bitrate ? `<div class="mb-2"><i class="fas fa-signal me-2 text-muted"></i><strong>Bitrate:</strong> ${audiobook.bitrate}</div>` : ''}
                    ${audiobook.sample_rate ? `<div class="mb-2"><i class="fas fa-wave-square me-2 text-muted"></i><strong>Sample Rate:</strong> ${audiobook.sample_rate}</div>` : ''}
                    ${audiobook.series_name ? `<div class="mb-2"><i class="fas fa-list me-2 text-muted"></i><strong>Series:</strong> ${MediaLibraryUtils.escapeHtml(audiobook.series_name)}</div>` : ''}
                    ${pathParts && pathParts.scanFolder ? `<div class="mb-2"><i class="fas fa-hdd me-2 text-muted"></i><strong>Scan Folder:</strong> ${MediaLibraryUtils.escapeHtml(pathParts.scanFolder)}</div>` : ''}
                    ${pathParts && pathParts.directory ? `<div class="mb-2"><i class="fas fa-folder me-2 text-muted"></i><strong>Path:</strong> <code class="small">${MediaLibraryUtils.escapeHtml(pathParts.directory)}</code></div>` : ''}
                    ${pathParts && pathParts.filename ? `<div class="mb-2"><i class="fas fa-file me-2 text-muted"></i><strong>Filename:</strong> <code class="small">${MediaLibraryUtils.escapeHtml(pathParts.filename)}</code> <button type="button" class="btn btn-outline-secondary btn-sm ms-2" onclick="MediaLibraryUtils.openFileLocation(decodeURIComponent('${encodeURIComponent(audiobook.file_path)}'))"><i class="fas fa-folder-open me-1"></i>Open</button></div>` : ''}
                    ${audiobook.last_scanned ? `<div class="mb-2"><i class="fas fa-clock me-2 text-muted"></i><strong>Last Scanned:</strong> ${MediaLibraryUtils.formatDate(audiobook.last_scanned)}</div>` : ''}
                    ${audiobook.confidence !== undefined ? `<div class="mb-2"><strong>Confidence:</strong> ${getQualityBadge(audiobook.confidence)}</div>` : ''}
                    ${audiobook.completeness !== undefined ? `<div class="mb-2"><strong>Completeness:</strong> ${getQualityBadge(audiobook.completeness)}</div>` : ''}
                    <div class="mb-2"><strong>Listening Status:</strong> 
                        ${audiobook.is_read ? '<span class="badge bg-success">Listened</span>' : '<span class="badge bg-secondary">Not Listened</span>'}
                    </div>
                </div>
                
                ${
                    audiobook.description
                        ? `
                    <div class="mt-4">
                        <strong>Description:</strong>
                        <div class="description-content mt-2">
                            ${MediaLibraryUtils.sanitizeHtml(audiobook.description)}
                        </div>
                    </div>
                `
                        : ''
                }
            </div>
        `;
    }

    renderAudiobookMetadataTab(audiobook) {
        const metadata = audiobook.metadata || [];

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
                        audiobook.file_path
                            ? `
                        <hr class="my-4">
                        <h6 class="fw-bold mb-3">File Location</h6>
                        <div class="info-item">
                            <div class="d-flex align-items-center justify-content-between">
                                <code class="small text-muted flex-grow-1 me-2">${MediaLibraryUtils.escapeHtml(audiobook.file_path)}</code>
                                <button type="button" class="btn btn-outline-secondary btn-sm" onclick="MediaLibraryUtils.openFileLocation('${MediaLibraryUtils.escapeHtml(audiobook.file_path)}')">
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

    renderAudiobookFilesTab(audiobook) {
        return `
            <div class="p-3">
                <div class="d-flex justify-content-between align-items-center mb-3">
                    <h6 class="fw-bold mb-0">Audio Files</h6>
                    <button type="button" class="btn btn-outline-primary btn-sm load-audio-files-btn" 
                            data-audiobook-id="${audiobook.id}">
                        <i class="fas fa-sync me-1"></i>Load Files
                    </button>
                </div>
                
                <div id="audio-files-container">
                    <div class="text-center text-muted p-4">
                        <i class="fas fa-folder-open fa-2x mb-2"></i>
                        <p>Click "Load Files" to scan for audio files in the same directory.</p>
                    </div>
                </div>
            </div>
        `;
    }

    formatMetadataKey(key) {
        return key.replace(/_/g, ' ').replace(/\b\w/g, (l) => l.toUpperCase());
    }

    playAudiobook(audiobookId) {
        // Find the audiobook
        const audiobook = this.currentData.find((a) => a.id == audiobookId);
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

        const audiobook = this.currentData.find((a) => a.id == audiobookId);
        if (!audiobook) {
            MediaLibraryUtils.showToast('Audiobook not found', 'danger');
            return;
        }

        const action = audiobook.is_read ? 'Mark as Not Listened' : 'Mark as Listened';

        fetch(urls.toggle_read, {
            method: 'POST',
            headers: {
                'X-CSRFToken': this.getCsrfToken(),
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                audiobook_id: audiobookId,
            }),
        })
            .then((response) => response.json())
            .then((data) => {
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
            .catch((error) => {
                console.error('Error toggling read status:', error);
                MediaLibraryUtils.showToast('Error updating status. Please try again.', 'danger');
            });
    }

    showFileInfo(audiobookId) {
        const audiobook = this.currentData.find((a) => a.id == audiobookId);
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
document.addEventListener('DOMContentLoaded', function () {
    if (typeof window.audiobooksConfig !== 'undefined') {
        window.sectionManager = new AudiobooksSectionManager();
    }
});
