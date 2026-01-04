/**
 * series-list.js
 * Handles series list functionality including view modes and selection
 * Extracted from series_list.html inline script
 */

/**
 * Navigate to series details page
 * @param {number} seriesId - Series ID to view
 */
function viewSeriesDetails(seriesId) {
    window.location.href = `/books/series/${seriesId}/`;
}

/**
 * Navigate to series edit page
 * @param {number} seriesId - Series ID to edit
 */
function editSeries(seriesId) {
    window.location.href = `/books/series/${seriesId}/edit/`;
}

/**
 * Confirm and delete series
 * @param {number} seriesId - Series ID to delete
 */
function confirmDeleteSeries(seriesId) {
    if (confirm('Are you sure you want to delete this series? This action cannot be undone.')) {
        window.location.href = `/books/series/${seriesId}/delete/`;
    }
}

/**
 * Select/highlight a series and view its details
 * @param {number} seriesId - Series ID to select
 */
function selectSeries(seriesId) {
    // Remove selection from all items
    document.querySelectorAll('.series-row, .series-card').forEach((item) => {
        item.classList.remove('selected');
    });

    // Add selection to clicked item
    const items = document.querySelectorAll(`[data-id="${seriesId}"]`);
    items.forEach((item) => {
        item.classList.add('selected');
    });

    // Navigate to details
    viewSeriesDetails(seriesId);
}

/**
 * Toggle between table and grid view modes
 * @param {string} mode - View mode: 'table' or 'grid'
 */
function toggleViewMode(mode) {
    const tableView = document.querySelector('.table-view');
    const gridView = document.querySelector('.grid-view');
    const buttons = document.querySelectorAll('[onclick*="toggleViewMode"]');

    if (mode === 'grid') {
        tableView?.classList.add('d-none');
        gridView?.classList.remove('d-none');
        buttons.forEach((btn) => btn.classList.remove('active'));
        document.querySelector('[onclick*="grid"]')?.classList.add('active');

        // Save preference
        localStorage.setItem('seriesViewMode', 'grid');
    } else {
        tableView?.classList.remove('d-none');
        gridView?.classList.add('d-none');
        buttons.forEach((btn) => btn.classList.remove('active'));
        document.querySelector('[onclick*="table"]')?.classList.add('active');

        // Save preference
        localStorage.setItem('seriesViewMode', 'table');
    }
}

/**
 * Clear all filters and reset search
 */
function clearFilters() {
    const form = document.querySelector('form[method="get"]');
    if (form) {
        const inputs = form.querySelectorAll('input[name], select[name]');
        inputs.forEach((input) => {
            if (input.type === 'text' || input.type === 'search') {
                input.value = '';
            } else if (input.tagName === 'SELECT') {
                input.selectedIndex = 0;
            }
        });
        form.submit();
    }
}

/**
 * Initialize series list functionality
 */
function initializeSeriesList() {
    // Restore saved view mode
    const savedMode = localStorage.getItem('seriesViewMode');
    if (savedMode) {
        toggleViewMode(savedMode);
    }

    // Initialize enhanced series list functionality
    if (typeof EnhancedListUtils !== 'undefined') {
        EnhancedListUtils.initEnhancedSeriesList();
    }

    // Ensure proper initial state
    const tableView = document.querySelector('.table-view');
    const gridView = document.querySelector('.grid-view');

    if (tableView && gridView && !savedMode) {
        gridView.classList.add('d-none');
        tableView.classList.remove('d-none');
    }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', initializeSeriesList);

// Export functions for template use
window.selectSeries = selectSeries;
window.viewSeriesDetails = viewSeriesDetails;
window.editSeries = editSeries;
window.confirmDeleteSeries = confirmDeleteSeries;
window.toggleViewMode = toggleViewMode;
window.clearFilters = clearFilters;
