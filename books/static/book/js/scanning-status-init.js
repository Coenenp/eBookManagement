/**
 * scanning-status-init.js
 * Initializes scan status monitoring
 * Extracted from scanning/status.html inline script
 */

/**
 * Initialize scan status page with monitoring
 * @param {string} statusUrl - URL for live status updates
 */
function initializeScanStatus(statusUrl) {
    const scanStatusMonitor = new ScanStatusPageMonitor(statusUrl);

    // Clean up on page unload
    window.addEventListener('beforeunload', function () {
        if (scanStatusMonitor) {
            scanStatusMonitor.destroy();
        }
    });
}

// Export for template use
window.initializeScanStatus = initializeScanStatus;
