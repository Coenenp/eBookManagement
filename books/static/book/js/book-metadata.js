/**
 * Book Metadata Form Handler
 * Handles form interactions and functionality for the book metadata review page
 */

class MetadataFormHandler {
    constructor(finalMetadata, currentGenres, languageChoices, csrfToken, bookId) {
        this.finalMetadata = finalMetadata;
        this.currentGenres = currentGenres;
        this.languageChoices = languageChoices;
        this.csrfToken = csrfToken;
        this.bookId = bookId;
        this.init();
    }

    /**
     * Initialize all form handlers and functionality
     */
    init() {
        this.setupLanguageDropdown();
        this.setupGenreHandling();
        this.setupCoverPreview();
        this.setupQuickRescan();
        this.setupResetHandlers();
        this.setupUploadHandlers();
        this.setupEventDelegation();
        
        // Set up global functions for backward compatibility
        this.attachGlobalFunctions();
    }

    /**
     * Setup language dropdown functionality
     */
    setupLanguageDropdown() {
        const languageRadio = document.getElementById('language_manual');
        const languageDropdown = document.getElementById('language_dropdown');
        
        if (languageRadio && languageDropdown) {
            languageDropdown.addEventListener('change', () => {
                if (languageDropdown.value) {
                    languageRadio.checked = true;
                }
            });
        }
    }

    /**
     * Setup genre handling
     */
    setupGenreHandling() {
        // Genre selection will work with existing form handling
        // Add any specific genre validation or interactions here
    }

    /**
     * Setup cover preview functionality
     */
    setupCoverPreview() {
        const coverUpload = document.getElementById('cover_upload');
        if (coverUpload) {
            coverUpload.addEventListener('change', (event) => {
                this.uploadCoverImmediate(event.target);
            });
        }
    }

    /**
     * Upload cover immediately when file is selected
     */
    async uploadCoverImmediate(inputElement) {
        const file = inputElement.files[0];
        if (!file) return;

        const uploadCard = document.getElementById('uploadCoverCard');
        const uploadBody = document.getElementById('uploadCoverBody');
        const progressDiv = document.getElementById('uploadProgress');
        const progressBar = progressDiv?.querySelector('.progress-bar');

        try {
            // Show progress
            uploadBody.classList.add('d-hidden');
            progressDiv?.classList.remove('d-hidden');
            
            // Create form data
            const formData = new FormData();
            formData.append('cover_upload', file);
            formData.append('csrfmiddlewaretoken', this.csrfToken);

            // Upload with progress
            const response = await this.uploadWithProgress(
                `/books/${this.bookId}/upload-cover/`,
                formData,
                (percent) => {
                    if (progressBar) {
                        progressBar.style.width = percent + '%';
                        progressBar.setAttribute('aria-valuenow', percent);
                    }
                }
            );

            if (response.ok) {
                const result = await response.json();
                this.displayUploadedCover(result, uploadCard);
            } else {
                throw new Error('Upload failed');
            }

        } catch (error) {
            console.error('Cover upload error:', error);
            this.showUploadError(uploadCard, 'Upload failed. Please try again.');
        }
    }

    /**
     * Preview cover without uploading (fallback method)
     */
    previewCover(inputElement) {
        const file = inputElement.files[0];
        if (!file) return;

        if (!this.validateCoverFile(file)) {
            inputElement.value = '';
            return;
        }

        const reader = new FileReader();
        reader.onload = (e) => {
            this.updateCoverPreview(inputElement, e.target.result);
        };
        reader.readAsDataURL(file);
    }

    /**
     * Validate cover file type and size
     */
    validateCoverFile(file) {
        const allowedTypes = ['image/jpeg', 'image/jpg', 'image/png', 'image/gif', 'image/webp'];
        const maxSize = 5 * 1024 * 1024; // 5MB

        if (!allowedTypes.includes(file.type)) {
            alert('Invalid file type. Please select a valid image file (JPEG, PNG, GIF, WebP).');
            return false;
        }

        if (file.size > maxSize) {
            alert('File too large. Please select an image under 5MB.');
            return false;
        }

        return true;
    }

    /**
     * Update cover preview after file selection
     */
    updateCoverPreview(input, imageSrc) {
        const uploadCard = input.closest('.card');
        const cardBody = uploadCard.querySelector('.card-body');
        
        cardBody.innerHTML = `
            <div class="cover-container">
                <img src="${imageSrc}" alt="Cover preview" class="card-img-top cover-image cover-large max-width-100 max-height-300 object-fit-contain">
            </div>
            <div class="card-body p-2">
                <div class="form-check">
                    <input class="form-check-input" type="radio" name="final_cover_path" 
                           value="custom_upload" id="cover_custom" checked>
                    <label class="form-check-label fw-bold" for="cover_custom">
                        <i class="fas fa-upload me-1"></i>Custom Upload
                    </label>
                </div>
                <button type="button" class="btn btn-sm btn-outline-secondary mt-2" 
                        data-action="reset-cover-upload">
                    <i class="fas fa-times me-1"></i>Remove
                </button>
            </div>
        `;
    }

    /**
     * Upload file with progress tracking
     */
    uploadWithProgress(url, formData, onProgress) {
        return new Promise((resolve, reject) => {
            const xhr = new XMLHttpRequest();
            
            xhr.upload.addEventListener('progress', (e) => {
                if (e.lengthComputable) {
                    const percent = Math.round((e.loaded / e.total) * 100);
                    onProgress(percent);
                }
            });

            xhr.addEventListener('load', () => {
                if (xhr.status >= 200 && xhr.status < 300) {
                    resolve({ ok: true, json: () => Promise.resolve(JSON.parse(xhr.responseText)) });
                } else {
                    reject(new Error(`HTTP ${xhr.status}`));
                }
            });

            xhr.addEventListener('error', () => reject(new Error('Network error')));
            
            xhr.open('POST', url);
            xhr.send(formData);
        });
    }

    /**
     * Display uploaded cover in the form
     */
    displayUploadedCover(result, uploadCard) {
        if (result.cover_url) {
            const newContent = `
                <div class="cover-wrapper">
                    <div class="cover-container cover-medium">
                        <img src="${result.cover_url}" alt="Uploaded cover" class="cover-image">
                    </div>
                </div>
                <div class="form-check mt-2">
                    <input class="form-check-input" type="radio" name="final_cover_path" 
                           value="${result.cover_path}" id="cover_uploaded" checked>
                    <label class="form-check-label fw-bold" for="cover_uploaded">
                        Uploaded Cover
                        <span class="badge bg-success ms-1">New</span>
                    </label>
                </div>
                <button type="button" class="btn btn-sm btn-outline-danger mt-2" 
                        data-action="reset-cover-upload">
                    <i class="fas fa-trash me-1"></i>Remove
                </button>
            `;
            
            uploadCard.querySelector('.card-body').innerHTML = newContent;
            uploadCard.classList.remove('border-dashed', 'border-secondary');
            uploadCard.classList.add('border-2', 'border-success');
        }
    }

    /**
     * Show upload error
     */
    showUploadError(uploadCard, message) {
        const uploadBody = uploadCard.querySelector('.card-body');
        const errorDiv = document.createElement('div');
        errorDiv.className = 'alert alert-danger mt-2';
        errorDiv.innerHTML = `<i class="fas fa-exclamation-triangle me-2"></i>${message}`;
        uploadBody.appendChild(errorDiv);
        
        // Reset upload UI
        const progressDiv = document.getElementById('uploadProgress');
        progressDiv?.classList.add('d-hidden');
        document.getElementById('uploadCoverBody')?.classList.remove('d-hidden');
    }

    /**
     * Setup quick rescan functionality
     */
    setupQuickRescan() {
        const quickRescanBtn = document.getElementById('quickRescanBtn');
        if (quickRescanBtn) {
            quickRescanBtn.addEventListener('click', () => this.performQuickRescan());
        }
    }

    /**
     * Perform quick metadata rescan
     */
    async performQuickRescan() {
        const btn = document.getElementById('quickRescanBtn');
        const progressDiv = document.getElementById('quickRescanProgress');
        const progressBar = document.getElementById('quickRescanProgressBar');
        const statusDiv = document.getElementById('quickRescanStatus');
        const resultsDiv = document.getElementById('quickRescanResults');
        const summarySpan = document.getElementById('quickRescanSummary');

        try {
            // Show progress
            btn.disabled = true;
            progressDiv.classList.remove('d-none');
            resultsDiv.classList.add('d-none');
            
            progressBar.style.width = '10%';
            statusDiv.textContent = 'Starting rescan...';

            // Start rescan
            const response = await fetch(`/books/${this.bookId}/rescan/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.csrfToken
                },
                body: JSON.stringify({
                    sources: ['google', 'openlibrary'],
                    clear_existing: false,
                    force_refresh: false
                })
            });

            const result = await response.json();
            
            if (result.success) {
                // Simulate progress
                progressBar.style.width = '50%';
                statusDiv.textContent = 'Querying external sources...';
                
                await new Promise(resolve => setTimeout(resolve, 1000));
                
                progressBar.style.width = '100%';
                statusDiv.textContent = 'Processing results...';
                
                await new Promise(resolve => setTimeout(resolve, 500));
                
                // Show results
                progressDiv.classList.add('d-none');
                resultsDiv.classList.remove('d-none');
                
                const summary = this.buildRescanSummary(result.added_metadata);
                summarySpan.textContent = summary;
                
            } else {
                throw new Error(result.error || 'Rescan failed');
            }

        } catch (error) {
            console.error('Quick rescan error:', error);
            statusDiv.innerHTML = `<div class="text-danger">Error: ${error.message}</div>`;
        } finally {
            btn.disabled = false;
        }
    }

    /**
     * Build rescan summary message
     */
    buildRescanSummary(addedMetadata) {
        const counts = addedMetadata || {};
        const total = Object.values(counts).reduce((sum, count) => sum + count, 0);
        
        if (total === 0) {
            return 'No new metadata found.';
        }
        
        const parts = [];
        if (counts.titles > 0) parts.push(`${counts.titles} titles`);
        if (counts.authors > 0) parts.push(`${counts.authors} authors`);
        if (counts.covers > 0) parts.push(`${counts.covers} covers`);
        if (counts.metadata > 0) parts.push(`${counts.metadata} other fields`);
        
        return `Found ${total} new metadata items: ${parts.join(', ')}.`;
    }

    /**
     * Setup reset handlers
     */
    setupResetHandlers() {
        const resetHandlers = {
            cover: (value) => this.resetSelection('final_cover_path', value),
            title: () => this.resetTitleSelection(),
            author: () => this.resetAuthorSelection(),
            series: () => this.resetSeriesSelection(),
            seriesNumber: (value) => this.resetSelection('final_series_number', value, 'series_number_override'),
            genre: () => this.resetGenreSelection(),
            description: (value) => this.resetSelection('final_description', value, 'description_override'),
            isbn: (value) => this.resetSelection('final_isbn', value, 'isbn_override'),
            publisher: (value) => this.resetSelection('final_publisher', value, 'publisher_override'),
            year: (value) => this.resetSelection('final_publication_year', value, 'year_override'),
            language: () => this.resetLanguageSelection()
        };

        // Attach global reset functions for backward compatibility
        Object.entries(resetHandlers).forEach(([key, handler]) => {
            const functionName = `reset${key.charAt(0).toUpperCase() + key.slice(1)}Selection`;
            window[functionName] = () => handler(this.finalMetadata[key]);
        });

        this.resetHandlers = resetHandlers;
    }

    /**
     * Setup upload-related handlers
     */
    setupUploadHandlers() {
        // Handle cover upload reset buttons
        document.addEventListener('click', (event) => {
            if (event.target.matches('[data-action="reset-cover-upload"]')) {
                this.resetCoverUpload(event.target);
            }
        });
    }

    /**
     * Setup event delegation for data-action buttons
     */
    setupEventDelegation() {
        // Handle click events
        document.addEventListener('click', (event) => {
            const action = event.target.getAttribute('data-action');
            if (!action) return;

            switch (action) {
                case 'reset-cover':
                    this.resetSelection('final_cover_path', this.finalMetadata.cover);
                    break;
                case 'reset-title':
                    this.resetTitleSelection();
                    break;
                case 'reset-author':
                    this.resetAuthorSelection();
                    break;
                case 'reset-series':
                    this.resetSeriesSelection();
                    break;
                case 'reset-series-number':
                    this.resetSelection('final_series_number', this.finalMetadata.seriesNumber, 'series_number_override');
                    break;
                case 'reset-genre':
                    this.resetGenreSelection();
                    break;
                case 'reset-description':
                    this.resetSelection('final_description', this.finalMetadata.description, 'description_override');
                    break;
                case 'reset-isbn':
                    this.resetSelection('final_isbn', this.finalMetadata.isbn, 'isbn_override');
                    break;
                case 'reset-publisher':
                    this.resetSelection('final_publisher', this.finalMetadata.publisher, 'publisher_override');
                    break;
                case 'reset-year':
                    this.resetSelection('final_publication_year', this.finalMetadata.year, 'year_override');
                    break;
                case 'reset-language':
                    this.resetLanguageSelection();
                    break;
                case 'reload-page':
                    location.reload();
                    break;
                case 'reset-uploaded-cover':
                    this.resetUploadedCover();
                    break;
                case 'reset-cover-upload':
                    this.resetCoverUpload(event.target);
                    break;
                case 'lookup-isbn':
                    const isbn = event.target.getAttribute('data-isbn');
                    const counter = event.target.getAttribute('data-counter');
                    if (isbn && counter && window.isbnLookup) {
                        window.isbnLookup.lookupISBN(isbn, counter);
                    }
                    break;
                case 'hide-isbn-lookup':
                    const hideCounter = event.target.getAttribute('data-counter');
                    if (hideCounter && window.isbnLookup) {
                        window.isbnLookup.hideISBNLookup(hideCounter);
                    }
                    break;
                default:
                    // Handle any unknown actions
                    console.warn('Unknown action:', action);
            }
        });

        // Handle change events for file inputs
        document.addEventListener('change', (event) => {
            const action = event.target.getAttribute('data-action');
            if (!action) return;

            switch (action) {
                case 'upload-cover-immediate':
                    this.uploadCoverImmediate(event.target);
                    break;
                case 'preview-cover':
                    this.previewCover(event.target);
                    break;
            }
        });
    }

    /**
     * Generic reset function for radio button selections
     */
    resetSelection(fieldName, value, overrideInputId = null) {
        // Clear manual override if exists
        if (overrideInputId) {
            const overrideInput = document.getElementById(overrideInputId);
            if (overrideInput) {
                overrideInput.value = '';
            }
        }

        // Find and select the radio button with the target value
        const radios = document.querySelectorAll(`input[name="${fieldName}"]`);
        let found = false;

        radios.forEach(radio => {
            if (radio.value === value) {
                radio.checked = true;
                found = true;
            } else {
                radio.checked = false;
            }
        });

        // If exact value not found, try to select first option or "none" option
        if (!found && radios.length > 0) {
            const noneRadio = Array.from(radios).find(r => 
                r.value === '' || r.id.includes('none')
            );
            if (noneRadio) {
                noneRadio.checked = true;
            } else {
                radios[0].checked = true;
            }
        }
    }

    /**
     * Reset title selection with manual override handling
     */
    resetTitleSelection() {
        this.resetSelection('final_title', this.finalMetadata.title);
        const titleOverride = document.getElementById('title_override');
        if (titleOverride) titleOverride.value = '';
    }

    /**
     * Reset author selection with manual override handling
     */
    resetAuthorSelection() {
        this.resetSelection('final_author', this.finalMetadata.author);
        const authorOverride = document.getElementById('author_override');
        if (authorOverride) authorOverride.value = '';
    }

    /**
     * Reset series selection with manual override handling
     */
    resetSeriesSelection() {
        this.resetSelection('final_series', this.finalMetadata.series);
        const seriesOverride = document.getElementById('series_override');
        if (seriesOverride) seriesOverride.value = '';
    }

    /**
     * Reset genre selection
     */
    resetGenreSelection() {
        // Uncheck all genre checkboxes first
        const genreCheckboxes = document.querySelectorAll('input[name="final_genres"]');
        genreCheckboxes.forEach(checkbox => checkbox.checked = false);

        // Check only current genres
        this.currentGenres.forEach(genreName => {
            const checkbox = Array.from(genreCheckboxes).find(cb => cb.value === genreName);
            if (checkbox) checkbox.checked = true;
        });

        // Clear manual genres input
        const manualGenres = document.getElementById('manual_genres');
        if (manualGenres) manualGenres.value = '';
    }

    /**
     * Reset language selection with dropdown handling
     */
    resetLanguageSelection() {
        this.resetSelection('final_language', this.finalMetadata.language);
        
        // Reset language dropdown
        const languageDropdown = document.getElementById('language_dropdown');
        if (languageDropdown) {
            languageDropdown.value = '';
        }
    }

    /**
     * Reset uploaded cover
     */
    resetUploadedCover() {
        const uploadCard = document.getElementById('uploadCoverCard');
        const originalContent = `
            <div class="card-body d-flex flex-column justify-content-center align-items-center" id="uploadCoverBody">
                <i class="fas fa-upload fa-3x text-muted mb-3"></i>
                <div class="mb-3 text-center">
                    <label for="cover_upload" class="form-label fw-bold">Upload Custom Cover</label>
                    <input type="file" class="form-control" id="cover_upload" name="cover_upload" 
                           accept="image/*">
                    <div class="form-text">JPG, PNG, GIF, WebP (max 5MB)</div>
                </div>
                <div class="form-check">
                    <input class="form-check-input" type="radio" name="final_cover_path" 
                           value="custom_upload" id="cover_custom">
                    <label class="form-check-label" for="cover_custom">
                        Use uploaded cover
                    </label>
                </div>
            </div>
            <div class="progress d-hidden" id="uploadProgress">
                <div class="progress-bar progress-bar-striped progress-bar-animated progress-bar-width-0" 
                     role="progressbar" aria-label="Cover upload progress" aria-valuenow="0" aria-valuemin="0" aria-valuemax="100"></div>
            </div>
        `;
        
        uploadCard.innerHTML = originalContent;
        uploadCard.className = 'card h-100 border-2 border-dashed border-secondary';
        
        // Reattach upload handler
        const newUploadInput = uploadCard.querySelector('#cover_upload');
        if (newUploadInput) {
            newUploadInput.addEventListener('change', (event) => {
                this.uploadCoverImmediate(event.target);
            });
        }
    }

    /**
     * Reset cover upload (different from resetUploadedCover)
     */
    resetCoverUpload(button) {
        this.resetUploadedCover();
    }

    /**
     * Attach global functions for backward compatibility
     */
    attachGlobalFunctions() {
        // Individual reset functions
        window.resetCoverSelection = () => this.resetSelection('final_cover_path', this.finalMetadata.cover);
        window.resetTitleSelection = () => this.resetTitleSelection();
        window.resetAuthorSelection = () => this.resetAuthorSelection();
        window.resetSeriesSelection = () => this.resetSeriesSelection();
        window.resetSeriesNumberSelection = () => this.resetSelection('final_series_number', this.finalMetadata.seriesNumber, 'series_number_override');
        window.resetGenreSelection = () => this.resetGenreSelection();
        window.resetDescriptionSelection = () => this.resetSelection('final_description', this.finalMetadata.description, 'description_override');
        window.resetISBNSelection = () => this.resetSelection('final_isbn', this.finalMetadata.isbn, 'isbn_override');
        window.resetPublisherSelection = () => this.resetSelection('final_publisher', this.finalMetadata.publisher, 'publisher_override');
        window.resetYearSelection = () => this.resetSelection('final_publication_year', this.finalMetadata.year, 'year_override');
        window.resetLanguageSelection = () => this.resetLanguageSelection();
        window.resetUploadedCover = () => this.resetUploadedCover();
        window.resetCoverUpload = (button) => this.resetCoverUpload(button);

        // Upload function
        window.uploadCoverImmediate = (input) => this.uploadCoverImmediate(input);
    }
}

/**
 * ISBN Lookup functionality
 */
class ISBNLookup {
    constructor(csrfToken) {
        this.csrfToken = csrfToken;
    }

    /**
     * Look up ISBN information
     */
    async lookupISBN(isbn, counterId) {
        const resultsContainer = document.getElementById(`isbn_lookup_${counterId}`);
        const contentContainer = document.getElementById(`isbn_lookup_content_${counterId}`);
        
        if (!resultsContainer || !contentContainer) return;

        // Show loading state
        resultsContainer.classList.remove('isbn-lookup-hidden');
        contentContainer.innerHTML = `
            <div class="text-center py-2">
                <div class="spinner-border spinner-border-sm text-info me-2" role="status" aria-hidden="true"></div>
                Looking up ISBN...
            </div>
        `;

        try {
            const response = await fetch(`/ajax/isbn-lookup/${isbn}/`, {
                method: 'GET',
                headers: {
                    'X-CSRFToken': this.csrfToken
                }
            });

            const data = await response.json();
            
            if (data.success) {
                this.displayLookupResults(data, contentContainer);
            } else {
                this.displayLookupError(data.error || 'Lookup failed', contentContainer);
            }

        } catch (error) {
            console.error('ISBN lookup error:', error);
            this.displayLookupError('Network error occurred', contentContainer);
        }
    }

    /**
     * Display lookup results
     */
    displayLookupResults(data, container) {
        let html = '';

        if (data.google_books) {
            html += this.formatGoogleBooksResult(data.google_books);
        }

        if (data.open_library) {
            html += this.formatOpenLibraryResult(data.open_library);
        }

        if (!html) {
            html = '<div class="text-muted">No results found for this ISBN.</div>';
        }

        container.innerHTML = html;
    }

    /**
     * Format Google Books result
     */
    formatGoogleBooksResult(gb) {
        return `
            <div class="border-start border-primary border-3 ps-3 mb-3">
                <div class="row align-items-start">
                    ${gb.thumbnail ? `<div class="col-auto"><img src="${gb.thumbnail}" alt="Book cover" class="img-thumbnail lookup-thumbnail"></div>` : ''}
                    <div class="col">
                        <div class="d-flex align-items-center mb-2">
                            <strong class="text-primary me-2">Google Books</strong>
                            <span class="badge bg-primary">High Quality</span>
                        </div>
                        ${gb.title ? `<div><strong>Title:</strong> ${gb.title}</div>` : ''}
                        ${gb.authors ? `<div><strong>Authors:</strong> ${gb.authors.join(', ')}</div>` : ''}
                        ${gb.publisher ? `<div><strong>Publisher:</strong> ${gb.publisher}</div>` : ''}
                        ${gb.publishedDate ? `<div><strong>Published:</strong> ${gb.publishedDate}</div>` : ''}
                        ${gb.pageCount ? `<div><strong>Pages:</strong> ${gb.pageCount}</div>` : ''}
                        ${gb.description ? `<div class="mt-2"><strong>Description:</strong><br><small class="text-muted">${gb.description.substring(0, 200)}${gb.description.length > 200 ? '...' : ''}</small></div>` : ''}
                    </div>
                </div>
            </div>
        `;
    }

    /**
     * Format Open Library result
     */
    formatOpenLibraryResult(ol) {
        return `
            <div class="border-start border-info border-3 ps-3">
                <div class="row align-items-start">
                    ${ol.thumbnail ? `<div class="col-auto"><img src="${ol.thumbnail}" alt="Book cover" class="img-thumbnail lookup-thumbnail"></div>` : ''}
                    <div class="col">
                        <div class="d-flex align-items-center mb-2">
                            <strong class="text-info me-2">Open Library</strong>
                            <span class="badge bg-info">Community Verified</span>
                        </div>
                        ${ol.title ? `<div><strong>Title:</strong> ${ol.title}</div>` : ''}
                        ${ol.authors ? `<div><strong>Authors:</strong> ${ol.authors.join(', ')}</div>` : ''}
                        ${ol.publishers ? `<div><strong>Publishers:</strong> ${ol.publishers.join(', ')}</div>` : ''}
                        ${ol.publish_date ? `<div><strong>Published:</strong> ${ol.publish_date}</div>` : ''}
                        ${ol.number_of_pages ? `<div><strong>Pages:</strong> ${ol.number_of_pages}</div>` : ''}
                        ${ol.description ? `<div class="mt-2"><strong>Description:</strong><br><small class="text-muted">${ol.description.substring(0, 200)}${ol.description.length > 200 ? '...' : ''}</small></div>` : ''}
                    </div>
                </div>
            </div>
        `;
    }

    /**
     * Display lookup error
     */
    displayLookupError(error, container) {
        container.innerHTML = `
            <div class="text-danger">
                <i class="fas fa-exclamation-triangle me-2"></i>
                ${error}
            </div>
        `;
    }

    /**
     * Hide ISBN lookup results
     */
    hideISBNLookup(counterId) {
        const resultsContainer = document.getElementById(`isbn_lookup_${counterId}`);
        if (resultsContainer) {
            resultsContainer.classList.add('isbn-lookup-hidden');
        }
    }
}

// Global functions for backward compatibility
let isbnLookup;

function lookupISBN(isbn, counterId) {
    if (isbnLookup) {
        isbnLookup.lookupISBN(isbn, counterId);
    }
}

function hideISBNLookup(counterId) {
    if (isbnLookup) {
        isbnLookup.hideISBNLookup(counterId);
    }
}