/**
 * Wizard Scrapers JavaScript functionality
 * Handles API key validation initialization
 */

document.addEventListener('DOMContentLoaded', function() {
    // Initialize API key validation using external utility
    if (typeof window.ApiKeyValidator !== 'undefined') {
        const validator = new ApiKeyValidator();
        validator.init();
    } else {
        console.log('ApiKeyValidator not available, skipping API key validation initialization');
    }
});

// Export for global access if needed
window.WizardScrapers = {
    // Future scraper-specific functionality can be added here
};