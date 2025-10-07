/**
 * Additional scanning dashboard functionality
 * Extracted from scanning/dashboard.html inline JavaScript
 */

// Configuration and utility functions
window.scanningDashboardInline = {
    
    /**
     * Load folder progress asynchronously - compatible with existing template structure
     */
    async loadFolderProgressAsync() {
        const progressContainers = document.querySelectorAll('.folder-progress-container[data-folder-id]');
        
        // Collect folder IDs that need loading
        const folderIds = [];
        const containerMap = new Map();
        
        progressContainers.forEach(container => {
            // Skip if not in loading state
            if (!container.querySelector('.fa-spinner')) {
                return;
            }
            
            const folderId = container.dataset.folderId;
            folderIds.push(folderId);
            containerMap.set(folderId, container);
        });
        
        if (folderIds.length === 0) {
            return;
        }
        
        try {
            // Load progress info for all folders in bulk using GET method with query params
            const params = new URLSearchParams();
            folderIds.forEach(id => params.append('folder_ids[]', id));
            
            const url = `${window.scanningDashboardConfig.bulkFolderProgressUrl}?${params}`;
            
            const response = await fetch(url, {
                method: 'GET',
                headers: {
                    'X-CSRFToken': window.scanningDashboardConfig.csrfToken,
                },
                credentials: 'same-origin'
            });
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            const data = await response.json();
            
            if (data.success && data.progress_data) {
                // Update each container with its progress data
                Object.entries(data.progress_data).forEach(([folderId, progress]) => {
                    const container = containerMap.get(folderId);
                    if (container && !progress.error) {
                        this.updateProgressContainer(container, progress);
                    } else if (container && progress.error) {
                        this.showProgressError(container, 'Failed to load progress');
                    }
                });
            } else {
                // Show error for all containers
                containerMap.forEach(container => {
                    this.showProgressError(container, 'Failed to load progress');
                });
            }
        } catch (error) {
            console.error('Failed to load folder progress:', error);
            // Show error for all containers
            containerMap.forEach(container => {
                this.showProgressError(container, 'Network error');
            });
        }
    },

    /**
     * Update progress container with progress data - matches new template structure
     */
    updateProgressContainer(container, progress) {
        const totalFilesSpan = container.querySelector('.total-files');
        const progressNumbers = container.querySelector('.progress-numbers');
        const progressBar = container.querySelector('.progress-bar');
        const progressPercent = container.querySelector('.progress-percent');
        
        // Update text content
        if (totalFilesSpan) {
            totalFilesSpan.textContent = progress.total_files;
        }
        
        // Update progress numbers display
        if (progressNumbers) {
            progressNumbers.innerHTML = `${progress.scanned}/${progress.total_files}`;
        }
        
        // Update progress bar using standardized classes
        if (progressBar) {
            progressBar.classList.remove('progress-loading', 'progress-bar-striped', 'progress-bar-animated');
            
            if (progress.needs_scan) {
                progressBar.classList.add('progress-active', 'progress-bar-dynamic');
                progressBar.style.setProperty('--progress-width', progress.percentage);
                progressBar.setAttribute('data-width', progress.percentage);
                progressBar.title = progress.percentage + '% scanned';
                progressBar.setAttribute('aria-valuenow', Math.round(progress.percentage));
                
                if (progressPercent) {
                    progressPercent.innerHTML = progress.percentage + '%';
                }
            } else {
                // Complete - show success
                progressBar.classList.remove('progress-active', 'progress-bar-dynamic');
                progressBar.classList.add('progress-complete');
                progressBar.title = 'Complete';
                progressBar.setAttribute('aria-valuenow', '100');
                
                if (progressPercent) {
                    progressPercent.innerHTML = '<span class="badge status-success"><i class="fas fa-check me-1"></i>Complete</span>';
                }
            }
        }
    },

    /**
     * Show error state for progress container
     */
    showProgressError(container, message) {
        const progressPercent = container.querySelector('.progress-percent');
        const progressBar = container.querySelector('.progress-bar');
        const progressNumbers = container.querySelector('.progress-numbers');
        
        if (progressPercent) {
            progressPercent.innerHTML = `<i class="fas fa-exclamation-triangle text-warning me-1" title="${message}"></i>Error`;
            progressPercent.classList.add('progress-error');
        }
        if (progressBar) {
            progressBar.classList.remove('progress-bar-striped', 'progress-bar-animated', 'progress-active', 'progress-complete');
            progressBar.classList.add('progress-error');
            progressBar.style.width = '100%';
            progressBar.title = `Error: ${message}`;
        }
        if (progressNumbers) {
            progressNumbers.innerHTML = `<i class="fas fa-exclamation-triangle text-warning me-1"></i>Error loading`;
        }
    },

    /**
     * Initialize scan all folders button functionality
     */
    initScanAllButton() {
        document.addEventListener('DOMContentLoaded', function() {
            const scanAllBtn = document.getElementById('scan-all-folders-btn');
            
            if (scanAllBtn) {
                scanAllBtn.addEventListener('click', function() {
                    // Confirm action
                    if (!confirm('Start scanning all active folders? This may take some time.')) {
                        return;
                    }
                    
                    // Set loading state
                    const originalHTML = scanAllBtn.innerHTML;
                    scanAllBtn.disabled = true;
                    scanAllBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>Starting Scans...';
                    
                    // Make AJAX request
                    fetch(window.scanningDashboardConfig.scanAllFoldersUrl, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': window.scanningDashboardConfig.csrfToken,
                        },
                        credentials: 'same-origin'
                    })
                    .then(response => response.json())
                    .then(data => {
                        if (data.status === 'success') {
                            // Show success message
                            scanAllBtn.innerHTML = '<i class="fas fa-check-circle me-2 text-white"></i>Scans Started!';
                            scanAllBtn.classList.remove('btn-success');
                            scanAllBtn.classList.add('btn-success', 'opacity-75');
                            
                            // Show notification
                            window.scanningDashboardInline.showNotification('success', `Started scans for ${data.folder_count} folder(s)`, data.message);
                            
                            // Refresh active scans display if available
                            if (window.scanningDashboard && window.scanningDashboard.updateActiveScans) {
                                window.scanningDashboard.updateActiveScans();
                                window.scanningDashboard.startAggressivePolling();
                            }
                            
                            // Reset button after 3 seconds
                            setTimeout(() => {
                                scanAllBtn.disabled = false;
                                scanAllBtn.innerHTML = originalHTML;
                                scanAllBtn.classList.remove('opacity-75');
                            }, 3000);
                        } else {
                            // Show error message
                            scanAllBtn.innerHTML = '<i class="fas fa-exclamation-triangle me-2"></i>Failed';
                            scanAllBtn.classList.add('btn-warning');
                            window.scanningDashboardInline.showNotification('error', 'Scan Failed', data.message || 'Failed to start scans');
                            
                            // Reset button after 2 seconds
                            setTimeout(() => {
                                scanAllBtn.disabled = false;
                                scanAllBtn.innerHTML = originalHTML;
                                scanAllBtn.classList.remove('btn-warning');
                            }, 2000);
                        }
                    })
                    .catch(error => {
                        console.error('Error starting scan all:', error);
                        scanAllBtn.innerHTML = '<i class="fas fa-exclamation-triangle me-2"></i>Error';
                        scanAllBtn.classList.add('btn-danger');
                        window.scanningDashboardInline.showNotification('error', 'Network Error', 'Failed to communicate with server');
                        
                        // Reset button after 2 seconds
                        setTimeout(() => {
                            scanAllBtn.disabled = false;
                            scanAllBtn.innerHTML = originalHTML;
                            scanAllBtn.classList.remove('btn-danger');
                        }, 2000);
                    });
                });
            }
        });
    },

    /**
     * Show notification with auto-dismiss
     */
    showNotification(type, title, message) {
        // Create notification element
        const notification = document.createElement('div');
        notification.className = `alert alert-${type === 'success' ? 'success' : 'danger'} alert-dismissible fade show position-fixed`;
        notification.style.cssText = 'top: 20px; right: 20px; z-index: 9999; min-width: 300px;';
        
        notification.innerHTML = `
            <strong>${title}</strong>
            ${message ? `<br><small>${message}</small>` : ''}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;
        
        document.body.appendChild(notification);
        
        // Auto-remove after 5 seconds
        setTimeout(() => {
            if (notification.parentNode) {
                notification.remove();
            }
        }, 5000);
    },

    /**
     * Initialize all inline functionality
     */
    init() {
        console.log('Scanning dashboard inline JS initialized');
        this.initScanAllButton();
        
        // Auto-load folder progress when page loads
        document.addEventListener('DOMContentLoaded', () => {
            console.log('DOM loaded, starting folder progress load');
            // Wait a bit for the page to be fully loaded
            setTimeout(() => {
                console.log('Timeout reached, calling loadFolderProgressAsync');
                this.loadFolderProgressAsync().catch(error => {
                    console.error('Failed to load folder progress:', error);
                });
            }, 500);
        });
    }
};

// Initialize inline functionality
window.scanningDashboardInline.init();

// Global function access for backward compatibility
window.loadFolderProgressAsync = () => window.scanningDashboardInline.loadFolderProgressAsync();
window.updateProgressContainer = (container, progress) => window.scanningDashboardInline.updateProgressContainer(container, progress);
window.showProgressError = (container, message) => window.scanningDashboardInline.showProgressError(container, message);
window.showNotification = (type, title, message) => window.scanningDashboardInline.showNotification(type, title, message);