/**
 * Unified Tables JavaScript
 * Handles dynamic styling and interactions for unified table components
 */

document.addEventListener('DOMContentLoaded', function() {
    // Set progress bar widths from data attributes
    const progressBars = document.querySelectorAll('.progress-bar[data-width]');
    progressBars.forEach(function(bar) {
        const width = bar.getAttribute('data-width');
        if (width !== null) {
            bar.style.width = width + '%';
        }
    });
    
    // Enhanced table sorting (if needed in the future)
    // This can be expanded to handle client-side sorting
});