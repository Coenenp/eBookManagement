/**
 * Scanning Dashboard - Scanning management and progress tracking
 * Extracted from scanning/dashboard.html inline JavaScript
 */

class ScanningDashboard {
    constructor() {
        this.refreshIntervals = {
            activeScans: null,
            apiStatus: null
        };
        
        // Configuration for URL endpoints (will be injected from template)
        this.config = window.scanningDashboardConfig || {};
        
        this.init();
    }

    init() {
        this.initializeProgressBars();
        this.bindEvents();
        this.startAutoRefresh();
    }

    initializeProgressBars() {
        // Set width for API rate progress bars
        document.querySelectorAll('.api-rate-progress').forEach(progressBar => {
            const width = progressBar.getAttribute('data-width');
            if (width !== null) {
                progressBar.style.width = width + '%';
            }
        });
        
        // Set width for scan progress bars  
        document.querySelectorAll('.scan-progress-bar').forEach(progressBar => {
            const width = progressBar.getAttribute('data-width');
            if (width !== null) {
                progressBar.style.width = width + '%';
            }
        });

        // Initialize progress bars from data attributes (legacy support)
        const progressBars = document.querySelectorAll('.progress-bar[data-width]');
        progressBars.forEach(bar => {
            const width = bar.getAttribute('data-width');
            bar.style.width = width + '%';
            
            // Add animation
            setTimeout(() => {
                bar.classList.add('progress-bar-animated');
            }, 100);
        });
    }

    bindEvents() {
        // Handle rescan type changes
        this.setupRescanFormHandling();

        // Handle cancel scan buttons
        document.addEventListener('click', (e) => {
            if (e.target.classList.contains('cancel-scan-btn') || e.target.closest('.cancel-scan-btn')) {
                const btn = e.target.classList.contains('cancel-scan-btn') ? e.target : e.target.closest('.cancel-scan-btn');
                const jobId = btn.getAttribute('data-job-id');
                
                if (confirm('Are you sure you want to cancel this scan?')) {
                    this.cancelScanJob(jobId);
                }
            }
        });

        // Handle scan folder buttons and dropdown options
        document.addEventListener('click', (e) => {
            // Handle main scan buttons (default with external APIs)
            if (e.target.classList.contains('scan-folder-btn') || e.target.closest('.scan-folder-btn')) {
                const btn = e.target.classList.contains('scan-folder-btn') ? e.target : e.target.closest('.scan-folder-btn');
                const folderId = btn.getAttribute('data-folder-id');
                const folderName = btn.getAttribute('data-folder-name');
                
                if (confirm(`Start scanning folder "${folderName}"?`)) {
                    this.startScan(folderId, true); // with external APIs
                }
            }

            // Handle fast scan buttons (no external APIs)
            if (e.target.classList.contains('fast-scan-btn') || e.target.closest('.fast-scan-btn')) {
                const btn = e.target.classList.contains('fast-scan-btn') ? e.target : e.target.closest('.fast-scan-btn');
                const folderId = btn.getAttribute('data-folder-id');
                const folderName = btn.getAttribute('data-folder-name');
                
                if (confirm(`Start fast scanning folder "${folderName}"? (No external API calls)`)) {
                    this.startScan(folderId, false); // without external APIs
                }
            }

            // Handle rescan buttons
            if (e.target.classList.contains('rescan-folder-btn') || e.target.closest('.rescan-folder-btn')) {
                const btn = e.target.classList.contains('rescan-folder-btn') ? e.target : e.target.closest('.rescan-folder-btn');
                const folderId = btn.getAttribute('data-folder-id');
                const folderName = btn.getAttribute('data-folder-name');
                
                if (confirm(`Rescan folder "${folderName}"? This will update existing books.`)) {
                    this.startRescan(folderId);
                }
            }
            
            // Handle dropdown scan options
            if (e.target.classList.contains('scan-with-api-btn')) {
                e.preventDefault();
                const folderId = e.target.getAttribute('data-folder-id');
                const folderName = e.target.getAttribute('data-folder-name');
                
                if (confirm(`Start scanning folder "${folderName}" with external APIs?`)) {
                    this.startFolderScanById(folderId, true);
                }
            }
            
            if (e.target.classList.contains('scan-without-api-btn')) {
                e.preventDefault();
                const folderId = e.target.getAttribute('data-folder-id');
                const folderName = e.target.getAttribute('data-folder-name');
                
                if (confirm(`Start scanning folder "${folderName}" without external APIs?`)) {
                    this.startFolderScanById(folderId, false);
                }
            }
            
            if (e.target.classList.contains('rescan-with-api-btn')) {
                e.preventDefault();
                const folderId = e.target.getAttribute('data-folder-id');
                const folderName = e.target.getAttribute('data-folder-name');
                
                if (confirm(`Start rescanning folder "${folderName}" with external APIs? This will update existing books.`)) {
                    this.startFolderRescanById(folderId, true);
                }
            }
            
            if (e.target.classList.contains('rescan-without-api-btn')) {
                e.preventDefault();
                const folderId = e.target.getAttribute('data-folder-id');
                const folderName = e.target.getAttribute('data-folder-name');
                
                if (confirm(`Start rescanning folder "${folderName}" without external APIs? This will update existing books.`)) {
                    this.startFolderRescanById(folderId, false);
                }
            }
        });

        // Handle rescan form submission (find form by action URL)
        const rescanForm = document.querySelector('form[action*="start_book_rescan"]');
        if (rescanForm) {
            rescanForm.addEventListener('submit', (e) => this.handleRescanFormSubmission(e));
        }
    }

    /**
     * Setup rescan form visibility and validation handling
     */
    setupRescanFormHandling() {
        const updateRescanFormVisibility = () => {
            const folderGroup = document.getElementById('folder-select-group');
            const bookIdsGroup = document.getElementById('book-ids-group');
            const folderSelect = document.getElementById('folder_id');
            const bookIdsInput = document.getElementById('book_ids');
            const checkedRadio = document.querySelector('input[name="rescan_type"]:checked');
            
            if (!folderGroup || !bookIdsGroup) return;
            
            // Remove required attributes first
            if (folderSelect) folderSelect.removeAttribute('required');
            if (bookIdsInput) bookIdsInput.removeAttribute('required');
            
            // Clear any previous validation states
            if (folderSelect) folderSelect.setCustomValidity('');
            if (bookIdsInput) bookIdsInput.setCustomValidity('');
            
            if (checkedRadio) {
                const rescanType = checkedRadio.value;
                
                if (rescanType === 'all') {
                    // Rescan all books - hide both folder selector and book IDs
                    folderGroup.classList.add('hidden-group');
                    bookIdsGroup.classList.add('hidden-group');
                } else if (rescanType === 'folder') {
                    // Rescan books in specific folder - show folder selector, hide book IDs
                    folderGroup.classList.remove('hidden-group');
                    bookIdsGroup.classList.add('hidden-group');
                    if (folderSelect) folderSelect.setAttribute('required', 'required');
                } else if (rescanType === 'specific') {
                    // Rescan specific books by ID - hide folder selector, show book IDs
                    folderGroup.classList.add('hidden-group');
                    bookIdsGroup.classList.remove('hidden-group');
                    if (bookIdsInput) bookIdsInput.setAttribute('required', 'required');
                }
            } else {
                // Default state - show folder selector (since "folder" is the default checked option)
                folderGroup.classList.remove('hidden-group');
                bookIdsGroup.classList.add('hidden-group');
                if (folderSelect) folderSelect.setAttribute('required', 'required');
            }
        };

        // Initialize the form visibility on page load
        // Wait a bit to ensure DOM is fully rendered
        setTimeout(updateRescanFormVisibility, 50);
        
        // Add event listeners to radio buttons
        document.querySelectorAll('input[name="rescan_type"]').forEach(radio => {
            radio.addEventListener('change', updateRescanFormVisibility);
        });
        
        // Also update when the tab becomes active (important for Bootstrap tabs)
        const rescanTab = document.getElementById('book-rescan-tab');
        if (rescanTab) {
            rescanTab.addEventListener('shown.bs.tab', () => {
                // Delay to ensure tab content is visible before updating
                setTimeout(updateRescanFormVisibility, 100);
            });
        }
        
        // Also update when the modal is shown (important for Bootstrap modals)
        const newScanModal = document.getElementById('newScanModal');
        if (newScanModal) {
            newScanModal.addEventListener('shown.bs.modal', () => {
                // Delay to ensure modal content is visible before updating
                setTimeout(updateRescanFormVisibility, 100);
            });
        }
        
        // Add form validation for book IDs
        const bookIdsInput = document.getElementById('book_ids');
        if (bookIdsInput) {
            bookIdsInput.addEventListener('input', function() {
                const value = this.value.trim();
                if (value && !/^(\d+)(,\s*\d+)*$/.test(value)) {
                    this.setCustomValidity('Please enter valid book IDs separated by commas (e.g., 1,2,3)');
                } else {
                    this.setCustomValidity('');
                }
            });
        }
    }

    /**
     * Handle rescan form submission with client-side validation
     */
    handleRescanFormSubmission(e) {
        const formData = new FormData(e.target);
        const rescanType = formData.get('rescan_type');
        
        // Validate based on rescan type
        let isValid = true;
        let errorMessage = '';
        
        if (rescanType === 'folder') {
            const folderId = formData.get('folder_id');
            if (!folderId) {
                isValid = false;
                errorMessage = 'Must select a folder to rescan';
            }
        } else if (rescanType === 'specific') {
            const bookIds = formData.get('book_ids');
            if (!bookIds || !bookIds.trim()) {
                isValid = false;
                errorMessage = 'Must specify book IDs to rescan';
            } else {
                // Validate book IDs format
                const bookIdPattern = /^(\d+)(,\s*\d+)*$/;
                if (!bookIdPattern.test(bookIds.trim())) {
                    isValid = false;
                    errorMessage = 'Please enter valid book IDs separated by commas (e.g., 1,2,3)';
                }
            }
        }
        // 'all' rescan type doesn't need additional validation
        
        if (!isValid) {
            e.preventDefault();
            this.showValidationError(errorMessage);
            return false;
        }
        
        // If we get here, validation passed - let the form submit normally
        return true;
    }

    /**
     * Show validation error message with warning styling
     */
    showValidationError(message) {
        // Remove any existing validation errors first
        const existingError = document.querySelector('.alert-validation-error');
        if (existingError) {
            existingError.remove();
        }
        
        // Find the modal body to insert the error
        const modalBody = document.querySelector('#newScanModal .modal-body');
        if (!modalBody) return;
        
        // Create error alert
        const errorAlert = document.createElement('div');
        errorAlert.className = 'alert alert-warning alert-dismissible fade show alert-validation-error';
        errorAlert.innerHTML = `
            <strong><i class="fas fa-exclamation-triangle me-2"></i>Validation Error:</strong> ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
        `;
        
        // Insert at the top of modal body
        modalBody.insertBefore(errorAlert, modalBody.firstChild);
        
        // Auto-remove after 5 seconds
        setTimeout(() => {
            if (errorAlert.parentElement) {
                errorAlert.remove();
            }
        }, 5000);
        
        // Also scroll to top of modal to ensure error is visible
        modalBody.scrollTop = 0;
    }

    handleRescanTypeChange(value) {
        // This method is kept for backward compatibility
        // The actual functionality is now in setupRescanFormHandling
        const folderGroup = document.getElementById('folder-select-group');
        const bookIdsGroup = document.getElementById('book-ids-group');
        const folderSelect = document.getElementById('folder_id');
        const bookIdsInput = document.getElementById('book_ids');
        
        // Clear previous required states
        if (folderSelect) folderSelect.removeAttribute('required');
        if (bookIdsInput) bookIdsInput.removeAttribute('required');
        
        if (value === 'all') {
            // Rescan all books - hide both fields
            folderGroup?.classList.add('hidden-group');
            bookIdsGroup?.classList.add('hidden-group');
        } else if (value === 'folder') {
            // Rescan books in folder - show folder selector only
            folderGroup?.classList.remove('hidden-group');
            bookIdsGroup?.classList.add('hidden-group');
            if (folderSelect) folderSelect.setAttribute('required', 'required');
        } else if (value === 'specific') {
            // Rescan specific books by ID - show book IDs only
            folderGroup?.classList.add('hidden-group');
            bookIdsGroup?.classList.remove('hidden-group');
            if (bookIdsInput) bookIdsInput.setAttribute('required', 'required');
        }
    }

    async handleRescanForm(e) {
        e.preventDefault();
        
        const formData = new FormData(e.target);
        const rescanType = formData.get('rescan_type');
        
        try {
            let endpoint;
            let data = {};
            
            if (rescanType === 'all') {
                endpoint = '/books/rescan-all/';
            } else if (rescanType === 'folder') {
                endpoint = '/books/rescan-folder/';
                data.folder_id = formData.get('folder_id');
            } else if (rescanType === 'specific') {
                endpoint = '/books/rescan-specific/';
                data.book_ids = formData.get('book_ids').split(',').map(id => id.trim()).filter(id => id);
            }
            
            if (confirm(`Are you sure you want to start this rescan operation?`)) {
                const response = await this.makeRequest(endpoint, data);
                
                if (response.status === 'success') {
                    EbookLibrary.UI.showAlert('Rescan started successfully!', 'success');
                    this.updateActiveScans();
                } else {
                    EbookLibrary.UI.showAlert(response.message || 'Failed to start rescan', 'danger');
                }
            }
        } catch (error) {
            EbookLibrary.UI.showAlert('Failed to start rescan', 'danger');
        }
    }

    async startScan(folderId, useExternalAPIs = true) {
        try {
            const response = await this.makeRequest('/books/trigger-scan/', {
                folder_id: folderId,
                use_external_apis: useExternalAPIs
            });
            
            if (response.status === 'success') {
                EbookLibrary.UI.showAlert('Scan started successfully!', 'success');
                this.updateActiveScans();
            } else {
                EbookLibrary.UI.showAlert(response.message || 'Failed to start scan', 'danger');
            }
        } catch (error) {
            EbookLibrary.UI.showAlert('Failed to start scan', 'danger');
        }
    }

    async startRescan(folderId) {
        try {
            const response = await this.makeRequest('/books/rescan-folder/', {
                folder_id: folderId
            });
            
            if (response.status === 'success') {
                EbookLibrary.UI.showAlert('Rescan started successfully!', 'success');
                this.updateActiveScans();
            } else {
                EbookLibrary.UI.showAlert(response.message || 'Failed to start rescan', 'danger');
            }
        } catch (error) {
            EbookLibrary.UI.showAlert('Failed to start rescan', 'danger');
        }
    }

    async cancelScan(jobId) {
        try {
            const response = await this.makeRequest('/books/cancel-scan/', {
                job_id: jobId
            });
            
            if (response.status === 'success') {
                EbookLibrary.UI.showAlert('Scan cancelled successfully!', 'success');
                this.updateActiveScans();
            } else {
                EbookLibrary.UI.showAlert(response.message || 'Failed to cancel scan', 'danger');
            }
        } catch (error) {
            EbookLibrary.UI.showAlert('Failed to cancel scan', 'danger');
        }
    }

    async updateActiveScans() {
        try {
            const url = this.config.activeScanUrl || '/books/api/active-scans/';
            const response = await fetch(url);
            const data = await response.json();
            
            const activeScanContainer = document.querySelector('#active-scans-container');
            if (!activeScanContainer) return;
            
            // Track if we had active scans before this update
            const hadActiveScans = activeScanContainer.querySelectorAll('.scan-card').length > 0;
            
            // Check if there are any completed scans still showing success messages
            const completedScans = activeScanContainer.querySelectorAll('.scan-card.completed, .scan-card.error');
            const hasCompletedScans = completedScans.length > 0;
            
            if (data.scans && data.scans.length > 0) {
                // Hide "no active scans" message
                const noScansAlert = activeScanContainer.querySelector('.alert-info');
                if (noScansAlert) {
                    noScansAlert.style.display = 'none';
                }
                
                // Update existing scans and add new ones
                data.scans.forEach(scan => {
                    let scanCard = document.querySelector(`[data-job-id="${scan.job_id}"]`);
                    if (!scanCard) {
                        // Create new scan card if it doesn't exist
                        this.createScanCard(scan, activeScanContainer);
                    } else {
                        // Update existing scan progress
                        this.updateScanProgress(scan.job_id);
                    }
                });
            } else {
                // No active scans
                if (hadActiveScans && !hasCompletedScans) {
                    // Only refresh if we don't have completion messages showing
                    console.log('All scans completed - refreshing to update folder states');
                    setTimeout(() => {
                        window.location.reload();
                    }, 8000); // Longer delay to let users see completion status
                    return;
                } else if (hasCompletedScans) {
                    // Don't refresh yet - let completion messages show
                    console.log('Scans completed but showing completion messages - delaying refresh');
                    return;
                }
                
                // Show "no active scans" message only if no completion messages
                if (!hasCompletedScans) {
                    const noScansAlert = activeScanContainer.querySelector('.alert-info');
                    if (noScansAlert) {
                        noScansAlert.style.display = 'block';
                    }
                    // Remove all scan cards
                    activeScanContainer.querySelectorAll('.scan-card').forEach(card => card.remove());
                }
            }
        } catch (error) {
            console.error('Failed to update active scans:', error);
        }
    }

    createScanCard(scan, container) {
        const scanCard = document.createElement('div');
        scanCard.className = 'card scan-card mb-2';
        scanCard.setAttribute('data-job-id', scan.job_id);
        scanCard.innerHTML = `
            <div class="card-body">
                <div class="row align-items-center">
                    <div class="col-md-8">
                        <h6 class="card-title mb-1">${scan.status || 'Scanning'}</h6>
                        <div class="progress mb-2">
                            <div class="progress-bar scan-progress-bar" role="progressbar"
                                 style="width: ${scan.percentage || 0}%"
                                 aria-label="Scan progress: ${scan.percentage || 0}% complete"
                                 aria-valuenow="${scan.percentage || 0}"
                                 aria-valuemin="0"
                                 aria-valuemax="100"
                                 data-width="${scan.percentage || 0}">
                                ${scan.percentage || 0}%
                            </div>
                        </div>
                        <small class="text-muted scan-details">${scan.details || 'Processing...'}</small>
                    </div>
                    <div class="col-md-4 text-end">
                        <button class="btn btn-outline-danger btn-sm cancel-scan-btn" 
                                data-job-id="${scan.job_id}">
                            <i class="fas fa-stop me-1"></i>Cancel
                        </button>
                    </div>
                </div>
            </div>
        `;
        
        // Insert new card at the beginning
        const firstChild = container.firstChild;
        container.insertBefore(scanCard, firstChild);
    }

    /**
     * Update individual scan progress
     */
    async updateScanProgress(jobId) {
        try {
            const baseUrl = this.config.scanProgressUrl || '/books/scanning/progress/PLACEHOLDER/';
            const url = baseUrl.replace('PLACEHOLDER', jobId);
            const response = await fetch(url);
            const data = await response.json();
            
            const scanCard = document.querySelector(`[data-job-id="${jobId}"]`);
            if (!scanCard) return;
            
            // Update progress bar
            const progressBar = scanCard.querySelector('.scan-progress-bar');
            if (progressBar) {
                progressBar.style.width = `${data.percentage || 0}%`;
                progressBar.textContent = `${data.percentage || 0}%`;
            }
            
            // Update status and details
            const titleElement = scanCard.querySelector('.card-title');
            const detailsElement = scanCard.querySelector('.scan-details');
            
            if (titleElement) {
                titleElement.textContent = data.status || 'Scanning';
            }
            
            if (detailsElement) {
                detailsElement.textContent = data.details || 'Processing...';
            }
            
            // Handle completion
            if (data.completed) {
                scanCard.classList.add(data.success ? 'completed' : 'error');
                
                // Remove cancel button
                const cancelBtn = scanCard.querySelector('.cancel-scan-btn');
                if (cancelBtn) {
                    cancelBtn.remove();
                }
                
                // Show completion message
                if (detailsElement) {
                    detailsElement.textContent = data.success ? data.message : data.error;
                }
                
                // Auto-remove completed scans after 30 seconds
                setTimeout(() => {
                    if (scanCard.parentElement) {
                        scanCard.remove();
                    }
                }, 30000);
            }
        } catch (error) {
            console.error('Error updating scan progress:', error);
        }
    }

    /**
     * Cancel a scan job (new method for template compatibility)
     */
    async cancelScanJob(jobId) {
        try {
            const baseUrl = this.config.cancelScanUrl || '/books/scanning/cancel/PLACEHOLDER/';
            const url = baseUrl.replace('PLACEHOLDER', jobId);
            const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value;
            
            const response = await fetch(url, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': csrfToken,
                    'Content-Type': 'application/json'
                }
            });
            
            const data = await response.json();
            
            if (data.success) {
                // Remove the scan card
                const scanCard = document.querySelector(`[data-job-id="${jobId}"]`);
                if (scanCard) {
                    scanCard.remove();
                }
                
                this.showToast('Scan cancelled successfully', 'success');
            } else {
                this.showToast('Failed to cancel scan: ' + data.error, 'error');
            }
        } catch (error) {
            console.error('Error canceling scan:', error);
            this.showToast('Failed to cancel scan', 'error');
        }
    }

    renderActiveScans(scans) {
        const container = document.getElementById('activeScansList');
        if (!container) return;
        
        if (scans.length === 0) {
            container.innerHTML = `
                <div class="alert alert-info">
                    <i class="fas fa-info-circle me-2"></i>
                    No active scans currently running.
                </div>
            `;
            return;
        }
        
        container.innerHTML = scans.map(scan => `
            <div class="card mb-3">
                <div class="card-body">
                    <div class="d-flex justify-content-between align-items-start">
                        <div>
                            <h6 class="card-title mb-1">${EbookLibrary.Utils.escapeHtml(scan.folder_name)}</h6>
                            <p class="card-text text-muted mb-2">
                                Job ID: ${scan.job_id}<br>
                                Started: ${new Date(scan.started_at).toLocaleString()}
                            </p>
                        </div>
                        <button class="btn btn-outline-danger btn-sm cancel-scan-btn" data-job-id="${scan.job_id}">
                            <i class="fas fa-times me-1"></i>Cancel
                        </button>
                    </div>
                    
                    <div class="progress mb-2" style="height: 20px;">
                        <div class="progress-bar progress-bar-striped progress-bar-animated bg-primary" 
                             style="width: ${scan.progress}%">
                            ${scan.progress.toFixed(1)}%
                        </div>
                    </div>
                    
                    <div class="row text-center">
                        <div class="col-4">
                            <small class="text-muted">Processed</small><br>
                            <strong>${scan.processed_files}</strong>
                        </div>
                        <div class="col-4">
                            <small class="text-muted">Total</small><br>
                            <strong>${scan.total_files}</strong>
                        </div>
                        <div class="col-4">
                            <small class="text-muted">Status</small><br>
                            <span class="badge bg-primary">${scan.status}</span>
                        </div>
                    </div>
                </div>
            </div>
        `).join('');
    }

    async updateAPIStatus() {
        try {
            const url = this.config.apiStatusUrl || '/books/api/status/';
            const response = await fetch(url);
            const data = await response.json();
            
            // Update API status indicators and progress bars
            console.log('Updated API status:', data);
            
            if (data.status === 'success') {
                this.renderAPIStatus(data.api_status);
            }
        } catch (error) {
            console.error('Failed to update API status:', error);
        }
    }

    /**
     * Show toast notification
     */
    showToast(message, type = 'info') {
        // Try to use EbookLibrary.UI if available, otherwise create toast manually
        if (typeof EbookLibrary !== 'undefined' && EbookLibrary.UI && EbookLibrary.UI.showAlert) {
            const alertType = type === 'error' ? 'danger' : type;
            EbookLibrary.UI.showAlert(message, alertType);
            return;
        }

        // Fallback: Create toast manually
        let toastContainer = document.querySelector('.toast-container');
        if (!toastContainer) {
            toastContainer = document.createElement('div');
            toastContainer.className = 'toast-container position-fixed bottom-0 end-0 p-3';
            document.body.appendChild(toastContainer);
        }
        
        // Create toast
        const toast = document.createElement('div');
        const bgClass = type === 'error' ? 'text-bg-danger' : 
                       type === 'success' ? 'text-bg-success' : 
                       type === 'warning' ? 'text-bg-warning' : 'text-bg-info';
        
        toast.className = `toast show align-items-center ${bgClass} border-0`;
        toast.setAttribute('role', 'alert');
        toast.innerHTML = `
            <div class="d-flex">
                <div class="toast-body">
                    <i class="fas fa-${this.getToastIcon(type)} me-2"></i>
                    ${message}
                </div>
                <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
            </div>
        `;
        
        toastContainer.appendChild(toast);
        
        // Auto-remove after 5 seconds
        setTimeout(() => {
            if (toast.parentElement) {
                toast.remove();
            }
        }, 5000);
    }

    /**
     * Get appropriate icon for toast type
     */
    getToastIcon(type) {
        const icons = {
            success: 'check-circle',
            error: 'exclamation-circle',
            warning: 'exclamation-triangle',
            info: 'info-circle'
        };
        return icons[type] || 'info-circle';
    }

    renderAPIStatus(apiStatus) {
        const container = document.getElementById('apiStatusContainer');
        if (!container) return;
        
        container.innerHTML = Object.entries(apiStatus).map(([api, status]) => `
            <div class="col-md-4 mb-3">
                <div class="card h-100">
                    <div class="card-body text-center">
                        <h6 class="card-title">${api}</h6>
                        <div class="mb-2">
                            <span class="badge ${status.available ? 'bg-success' : 'bg-danger'}">
                                ${status.available ? 'Available' : 'Unavailable'}
                            </span>
                        </div>
                        <small class="text-muted">
                            Last checked: ${new Date(status.last_checked).toLocaleString()}
                        </small>
                        ${status.rate_limit_info ? `
                            <div class="mt-2">
                                <small class="text-info">
                                    Rate limit: ${status.rate_limit_info.remaining}/${status.rate_limit_info.limit}
                                </small>
                            </div>
                        ` : ''}
                    </div>
                </div>
            </div>
        `).join('');
    }

    startAutoRefresh() {
        // Auto-refresh active scans every 5 seconds
        this.refreshIntervals.activeScans = setInterval(() => {
            this.updateActiveScans();
        }, 5000);
        
        // Auto-refresh API status every 30 seconds  
        this.refreshIntervals.apiStatus = setInterval(() => {
            this.updateAPIStatus();
        }, 30000);
    }

    stopAutoRefresh() {
        if (this.refreshIntervals.activeScans) {
            clearInterval(this.refreshIntervals.activeScans);
            this.refreshIntervals.activeScans = null;
        }
        
        if (this.refreshIntervals.apiStatus) {
            clearInterval(this.refreshIntervals.apiStatus);
            this.refreshIntervals.apiStatus = null;
        }
    }

    async makeRequest(url, data = {}) {
        const response = await fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': EbookLibrary.Ajax.getCSRFToken()
            },
            body: JSON.stringify(data)
        });
        
        return await response.json();
    }

    destroy() {
        this.stopAutoRefresh();
    }
}

// Global instance and initialization
let scanningDashboard;

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    scanningDashboard = new ScanningDashboard();
    
    // Initialize progress bars immediately
    initializeProgressBars();
    
    // Auto-refresh API status every 30 seconds
    setInterval(updateAPIStatus, 30000);
    
    // Handle rescan type changes
    document.querySelectorAll('input[name="rescan_type"]').forEach(radio => {
        radio.addEventListener('change', function() {
            const folderGroup = document.getElementById('folder-select-group');
            const bookIdsGroup = document.getElementById('book-ids-group');
            
            if (this.value === 'folder') {
                folderGroup.classList.remove('hidden-group');
                bookIdsGroup.classList.add('hidden-group');
            } else if (this.value === 'specific') {
                folderGroup.classList.add('hidden-group');
                bookIdsGroup.classList.remove('hidden-group');
            } else {
                folderGroup.classList.add('hidden-group');
                bookIdsGroup.classList.add('hidden-group');
            }
        });
    });
});

// Global functions for backward compatibility and HTML onclick handlers
window.initializeProgressBars = function() {
    // Set width for API rate progress bars
    document.querySelectorAll('.api-rate-progress').forEach(progressBar => {
        const width = progressBar.getAttribute('data-width');
        if (width !== null) {
            progressBar.style.width = width + '%';
        }
    });
    
    // Set width for scan progress bars
    document.querySelectorAll('.scan-progress-bar').forEach(progressBar => {
        const width = progressBar.getAttribute('data-width');
        if (width !== null) {
            progressBar.style.width = width + '%';
            // Update ARIA attributes for accessibility
            if (progressBar.hasAttribute('role') && progressBar.getAttribute('role') === 'progressbar') {
                progressBar.setAttribute('aria-valuenow', width);
                progressBar.setAttribute('aria-label', `Scan progress: ${width}% complete`);
            }
        }
    });
};

window.updateActiveScans = function() {
    if (typeof scanningDashboard !== 'undefined' && scanningDashboard) {
        scanningDashboard.updateActiveScans();
    }
};

window.updateAPIStatus = function() {
    if (typeof scanningDashboard !== 'undefined' && scanningDashboard) {
        scanningDashboard.updateAPIStatus();
    }
};

window.cancelScan = function(jobId) {
    if (typeof scanningDashboard !== 'undefined' && scanningDashboard) {
        scanningDashboard.cancelScanJob(jobId);
    }
};

window.startFolderScanById = function(folderId, enableExternalApis = true) {
    if (typeof scanningDashboard !== 'undefined' && scanningDashboard) {
        scanningDashboard.startFolderScanById(folderId, enableExternalApis);
    }
};

window.startFolderRescanById = function(folderId, enableExternalApis = true) {
    if (typeof scanningDashboard !== 'undefined' && scanningDashboard) {
        scanningDashboard.startFolderRescanById(folderId, enableExternalApis);
    }
};

window.disableFolderButton = function(folderId) {
    if (typeof scanningDashboard !== 'undefined' && scanningDashboard) {
        scanningDashboard.disableFolderButton(folderId);
    }
};

window.enableFolderButton = function(folderId) {
    if (typeof scanningDashboard !== 'undefined' && scanningDashboard) {
        scanningDashboard.enableFolderButton(folderId);
    }
};

// Clean up when page is unloaded
window.addEventListener('beforeunload', function() {
    if (scanningDashboard) {
        scanningDashboard.destroy();
    }
});

/**
 * Scan Status Monitor - Live status updates for scan progress
 * Extracted from scanning/status.html inline JavaScript
 */
class ScanStatusMonitor {
    constructor(statusUrl) {
        this.statusUrl = statusUrl;
        this.intervalId = null;
        this.init();
    }

    init() {
        this.initializeProgressBar();
        this.startStatusPolling();
    }

    initializeProgressBar() {
        // Initialize progress bar with CSS custom property
        const progressBar = document.getElementById("scan-progress-bar");
        if (progressBar) {
            const width = progressBar.getAttribute("data-width") || "0";
            progressBar.style.setProperty("--scan-width", width + "%");
        }
    }

    async fetchStatus() {
        try {
            const response = await fetch(this.statusUrl);
            const data = await response.json();
            
            if (data.status) {
                this.updateStatusDisplay(data);
                
                // Stop polling if scan is complete
                if (data.status !== "Running") {
                    this.stopStatusPolling();
                }
            }
        } catch (error) {
            console.error("Status fetch error:", error);
        }
    }

    updateStatusDisplay(data) {
        // Update status badge
        const statusBadge = document.getElementById("scan-status");
        if (statusBadge) {
            statusBadge.textContent = data.status;
            statusBadge.className = "badge " + this.getStatusBadgeClass(data.status);
        }
        
        // Update started time
        const startedEl = document.getElementById("scan-started");
        if (startedEl) startedEl.textContent = data.started;

        // Update message
        const messageEl = document.getElementById("scan-message");
        if (messageEl) messageEl.textContent = data.message;

        // Update progress bar
        this.updateProgressBar(data.progress || 0);
    }

    updateProgressBar(progress) {
        const progressBar = document.getElementById("scan-progress-bar");
        if (progressBar) {
            progressBar.style.setProperty("--scan-width", progress + "%");
            progressBar.textContent = progress + "%";
            progressBar.setAttribute("aria-valuenow", progress);
            
            // Update color class while preserving other classes
            const colorClass = "bg-" + this.getProgressColorClass(progress);
            progressBar.className = "progress-bar progress-bar-scan " + colorClass;
        }
    }

    getStatusBadgeClass(status) {
        switch (status) {
            case "Running": return "bg-primary";
            case "Completed": return "bg-success";
            case "Failed": return "bg-danger";
            default: return "bg-secondary";
        }
    }

    getProgressColorClass(progress) {
        if (progress === 100) return "success";
        if (progress >= 50) return "info";
        return "warning";
    }

    startStatusPolling() {
        // Start immediately
        this.fetchStatus();
        
        // Keep polling every 5 seconds
        this.intervalId = setInterval(() => this.fetchStatus(), 5000);
    }

    stopStatusPolling() {
        if (this.intervalId) {
            clearInterval(this.intervalId);
            this.intervalId = null;
        }
    }

    destroy() {
        this.stopStatusPolling();
    }
}

/**
 * Scanning Queue Management - Handle queue operations
 * Extracted from scanning/queue.html inline JavaScript  
 */
class ScanningQueue {
    constructor() {
        this.init();
    }

    init() {
        this.bindEvents();
    }

    bindEvents() {
        // Handle queue action buttons with event delegation
        document.addEventListener('click', (e) => {
            const target = e.target;
            
            if (target.matches('[onclick*="addToQueue"]') || target.closest('[onclick*="addToQueue"]')) {
                e.preventDefault();
                this.addToQueue();
            }
            
            if (target.matches('[onclick*="executeQueueItem"]') || target.closest('[onclick*="executeQueueItem"]')) {
                e.preventDefault();
                const itemId = this.extractItemId(target.getAttribute('onclick') || target.closest('[onclick]').getAttribute('onclick'));
                this.executeQueueItem(itemId);
            }
            
            if (target.matches('[onclick*="editQueueItem"]') || target.closest('[onclick*="editQueueItem"]')) {
                e.preventDefault();
                const itemId = this.extractItemId(target.getAttribute('onclick') || target.closest('[onclick]').getAttribute('onclick'));
                this.editQueueItem(itemId);
            }
            
            if (target.matches('[onclick*="retryQueueItem"]') || target.closest('[onclick*="retryQueueItem"]')) {
                e.preventDefault();
                const itemId = this.extractItemId(target.getAttribute('onclick') || target.closest('[onclick]').getAttribute('onclick'));
                this.retryQueueItem(itemId);
            }
            
            if (target.matches('[onclick*="removeQueueItem"]') || target.closest('[onclick*="removeQueueItem"]')) {
                e.preventDefault();
                const itemId = this.extractItemId(target.getAttribute('onclick') || target.closest('[onclick]').getAttribute('onclick'));
                this.removeQueueItem(itemId);
            }
        });
    }

    extractItemId(onclickStr) {
        // Extract item ID from onclick string like "functionName('123')" or "functionName(123)"
        if (!onclickStr) return null;
        const match = onclickStr.match(/\(([^)]+)\)/);
        return match ? match[1].replace(/['"]/g, '') : null;
    }

    addToQueue() {
        if (typeof EbookLibrary !== 'undefined' && EbookLibrary.UI) {
            EbookLibrary.UI.showAlert('Add to Queue functionality to be implemented', 'info');
        } else {
            alert('Add to Queue functionality to be implemented');
        }
    }

    executeQueueItem(itemId) {
        if (!itemId) return;
        
        if (confirm('Execute this queue item now?')) {
            if (typeof EbookLibrary !== 'undefined' && EbookLibrary.UI) {
                EbookLibrary.UI.showAlert(`Execute functionality to be implemented for item: ${itemId}`, 'info');
            } else {
                alert(`Execute functionality to be implemented for item: ${itemId}`);
            }
        }
    }

    editQueueItem(itemId) {
        if (!itemId) return;
        
        if (typeof EbookLibrary !== 'undefined' && EbookLibrary.UI) {
            EbookLibrary.UI.showAlert(`Edit functionality to be implemented for item: ${itemId}`, 'info');
        } else {
            alert(`Edit functionality to be implemented for item: ${itemId}`);
        }
    }

    retryQueueItem(itemId) {
        if (!itemId) return;
        
        if (confirm('Retry this queue item?')) {
            if (typeof EbookLibrary !== 'undefined' && EbookLibrary.UI) {
                EbookLibrary.UI.showAlert(`Retry functionality to be implemented for item: ${itemId}`, 'info');
            } else {
                alert(`Retry functionality to be implemented for item: ${itemId}`);
            }
        }
    }

    removeQueueItem(itemId) {
        if (!itemId) return;
        
        if (confirm('Remove this item from the queue?')) {
            if (typeof EbookLibrary !== 'undefined' && EbookLibrary.UI) {
                EbookLibrary.UI.showAlert(`Remove functionality to be implemented for item: ${itemId}`, 'info');
            } else {
                alert(`Remove functionality to be implemented for item: ${itemId}`);
            }
        }
    }

    // Enhanced folder scanning methods with API options
    startFolderScanById(folderId, enableExternalApis = true) {
        this.disableFolderButton(folderId);
        
        const formData = new FormData();
        formData.append('csrfmiddlewaretoken', this.config.csrfToken);
        formData.append('folder_id', folderId);
        if (enableExternalApis) {
            formData.append('enable_external_apis', 'on');
        }
        
        fetch(this.config.startFolderScanUrl, {
            method: 'POST',
            body: formData
        })
        .then(response => response.text())
        .then(data => {
            this.updateActiveScans();
            this.startAggressivePolling();
            setTimeout(() => this.enableFolderButton(folderId), 3000);
        })
        .catch(error => {
            console.error('Error starting scan:', error);
            alert('Failed to start scan');
            this.enableFolderButton(folderId);
        });
    }

    startFolderRescanById(folderId, enableExternalApis = true) {
        this.disableFolderButton(folderId);
        
        const formData = new FormData();
        formData.append('csrfmiddlewaretoken', this.config.csrfToken);
        formData.append('rescan_all', 'on');
        formData.append('folder_id', folderId);
        if (enableExternalApis) {
            formData.append('enable_external_apis', 'on');
        }
        
        fetch(this.config.startBookRescanUrl, {
            method: 'POST',
            body: formData
        })
        .then(response => response.text())
        .then(data => {
            this.updateActiveScans();
            this.startAggressivePolling();
            setTimeout(() => this.enableFolderButton(folderId), 3000);
        })
        .catch(error => {
            console.error('Error starting rescan:', error);
            alert('Failed to start rescan');
            this.enableFolderButton(folderId);
        });
    }

    disableFolderButton(folderId) {
        const scanBtn = document.getElementById(`folder-${folderId}-scan-btn`);
        const rescanBtn = document.getElementById(`folder-${folderId}-rescan-btn`);
        
        const btn = scanBtn || rescanBtn;
        if (btn) {
            btn.disabled = true;
            btn.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i>Starting...';
            btn.classList.add('disabled');
        }
    }

    enableFolderButton(folderId) {
        const scanBtn = document.getElementById(`folder-${folderId}-scan-btn`);
        const rescanBtn = document.getElementById(`folder-${folderId}-rescan-btn`);
        
        const btn = scanBtn || rescanBtn;
        if (btn) {
            btn.disabled = false;
            btn.classList.remove('disabled');
            if (btn.classList.contains('scan-folder-btn')) {
                btn.innerHTML = '<i class="fas fa-play me-1"></i>Scan';
            } else if (btn.classList.contains('rescan-folder-btn')) {
                btn.innerHTML = '<i class="fas fa-redo me-1"></i>Rescan';
            }
        }
    }

    startAggressivePolling() {
        let pollCount = 0;
        const aggressivePoll = setInterval(() => {
            this.updateActiveScans();
            pollCount++;
            if (pollCount >= 20) {
                clearInterval(aggressivePoll);
            }
        }, 500);
    }
}

/**
 * Scan Status Page Monitor - Handles scan status page specific functionality
 */
class ScanStatusPageMonitor {
    constructor(statusUrl) {
        this.statusUrl = statusUrl;
        this.intervalId = null;
        this.init();
    }

    init() {
        this.initializeProgressBar();
        this.startPolling();
    }

    initializeProgressBar() {
        // Initialize progress bar with CSS custom property
        const progressBar = document.getElementById("scan-progress-bar");
        if (progressBar) {
            const width = progressBar.getAttribute("data-width") || "0";
            progressBar.style.setProperty("--scan-width", width + "%");
        }
    }

    async fetchStatus() {
        try {
            const response = await fetch(this.statusUrl);
            const data = await response.json();
            
            if (data.status) {
                // Update status badge classes
                const statusBadge = document.getElementById("scan-status");
                if (statusBadge) {
                    statusBadge.textContent = data.status;
                    statusBadge.className = "badge " + (
                        data.status === "Running" ? "bg-primary" :
                        data.status === "Completed" ? "bg-success" :
                        data.status === "Failed" ? "bg-danger" : "bg-secondary"
                    );
                }
                
                const startedEl = document.getElementById("scan-started");
                if (startedEl) startedEl.textContent = data.started;

                const messageEl = document.getElementById("scan-message");
                if (messageEl) messageEl.textContent = data.message;

                const progressBar = document.getElementById("scan-progress-bar");
                if (progressBar) {
                    const progress = data.progress || 0;
                    progressBar.style.setProperty("--scan-width", progress + "%");
                    progressBar.textContent = progress + "%";
                    progressBar.setAttribute("aria-valuenow", progress);
                    
                    // Update color class while preserving other classes
                    const colorClass = "bg-" + (progress === 100 ? "success" : progress >= 50 ? "info" : "warning");
                    progressBar.className = "progress-bar progress-bar-scan " + colorClass;
                }

                // Stop polling if scan is not running
                if (data.status !== "Running") {
                    this.stopPolling();
                }
            }
        } catch (error) {
            console.error("Status fetch error:", error);
        }
    }

    startPolling() {
        // Start immediately
        this.fetchStatus();
        
        // Keep polling every 5 seconds
        this.intervalId = setInterval(() => {
            this.fetchStatus();
        }, 5000);
    }

    stopPolling() {
        if (this.intervalId) {
            clearInterval(this.intervalId);
            this.intervalId = null;
        }
    }

    destroy() {
        this.stopPolling();
    }
}

// Clean up when page is unloaded
window.addEventListener('beforeunload', function() {
    if (scanningDashboard) {
        scanningDashboard.destroy();
    }
});

// Export for global access
window.ScanningDashboard = ScanningDashboard;
window.ScanStatusMonitor = ScanStatusMonitor;
window.ScanStatusPageMonitor = ScanStatusPageMonitor;
window.ScanningQueue = ScanningQueue;