/**
 * scanning-queue-init.js
 * Initializes scanning queue management
 * Extracted from scanning/queue.html inline script
 */

/**
 * Initialize scanning queue functionality
 */
function initializeScanningQueue() {
    if (typeof ScanningQueue !== 'undefined') {
        new ScanningQueue();
    }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', initializeScanningQueue);
