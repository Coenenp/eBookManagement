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
        
        this.init();
    }

    init() {
        this.initializeProgressBars();
        this.bindEvents();
        this.startAutoRefresh();
    }

    initializeProgressBars() {
        // Initialize progress bars from data attributes
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
        document.querySelectorAll('input[name="rescan_type"]').forEach(radio => {
            radio.addEventListener('change', (e) => this.handleRescanTypeChange(e.target.value));
        });

        // Handle cancel scan buttons
        document.addEventListener('click', (e) => {
            if (e.target.classList.contains('cancel-scan-btn') || e.target.closest('.cancel-scan-btn')) {
                const btn = e.target.classList.contains('cancel-scan-btn') ? e.target : e.target.closest('.cancel-scan-btn');
                const jobId = btn.getAttribute('data-job-id');
                
                if (confirm('Are you sure you want to cancel this scan?')) {
                    this.cancelScan(jobId);
                }
            }
        });

        // Handle scan folder buttons
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
        });

        // Handle rescan form submission
        const rescanForm = document.getElementById('rescanForm');
        if (rescanForm) {
            rescanForm.addEventListener('submit', (e) => this.handleRescanForm(e));
        }
    }

    handleRescanTypeChange(value) {
        const folderGroup = document.getElementById('folder-select-group');
        const bookIdsGroup = document.getElementById('book-ids-group');
        
        if (value === 'folder') {
            folderGroup?.classList.remove('hidden-group');
            bookIdsGroup?.classList.add('hidden-group');
        } else if (value === 'specific') {
            folderGroup?.classList.add('hidden-group');
            bookIdsGroup?.classList.remove('hidden-group');
        } else {
            folderGroup?.classList.add('hidden-group');
            bookIdsGroup?.classList.add('hidden-group');
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
            const response = await fetch('/books/api/active-scans/');
            const data = await response.json();
            
            if (data.status === 'success') {
                this.renderActiveScans(data.active_scans);
            }
        } catch (error) {
            console.error('Failed to update active scans:', error);
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
            const response = await fetch('/books/api/status/');
            const data = await response.json();
            
            if (data.status === 'success') {
                this.renderAPIStatus(data.api_status);
            }
        } catch (error) {
            console.error('Failed to update API status:', error);
        }
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

// Global instance
let scanningDashboard;

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    scanningDashboard = new ScanningDashboard();
});

// Clean up when page is unloaded
window.addEventListener('beforeunload', function() {
    if (scanningDashboard) {
        scanningDashboard.destroy();
    }
});

/**
 * Scan Status Monitor - Live status updates for scan progress
 * Extracted from scan_status.html inline JavaScript
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
}

// Export for global access
window.ScanningDashboard = ScanningDashboard;
window.ScanStatusMonitor = ScanStatusMonitor;
window.ScanningQueue = ScanningQueue;