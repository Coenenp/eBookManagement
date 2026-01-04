/**
 * series-section-init.js
 * Initializes series section manager
 * Extracted from sections/series_main.html inline script
 */

/**
 * Initialize series section manager
 */
function initializeSeriesSection() {
    new SeriesSectionManager();
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', initializeSeriesSection);
