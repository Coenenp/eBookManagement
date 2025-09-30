/**
 * List Utilities - Common functionality for list pages (author, genre, etc.)
 * Extracted from various list HTML templates
 */

// Select all checkbox functionality
function initializeSelectAllCheckbox(selectAllId = 'select-all', targetName = 'selected_items') {
    const selectAllCheckbox = document.getElementById(selectAllId);
    if (selectAllCheckbox) {
        selectAllCheckbox.addEventListener('click', function() {
            const checkboxes = document.querySelectorAll(`input[name="${targetName}"]`);
            checkboxes.forEach(cb => cb.checked = this.checked);
        });
    }
}

// Initialize author list specific functionality
function initializeAuthorList() {
    initializeSelectAllCheckbox('select-all', 'selected_authors');
}

// Initialize genre list specific functionality  
function initializeGenreList() {
    initializeSelectAllCheckbox('select-all', 'selected_genres');
}

// Initialize series list specific functionality
function initializeSeriesList() {
    initializeSelectAllCheckbox('select-all', 'selected_series');
}

// General list functionality
const ListUtils = {
    // Initialize common list features
    init: function(listType = 'general') {
        switch (listType) {
            case 'author':
                initializeAuthorList();
                break;
            case 'genre':
                initializeGenreList();
                break;
            case 'series':
                initializeSeriesList();
                break;
            default:
                initializeSelectAllCheckbox();
                break;
        }
    },

    // Toggle all checkboxes
    toggleAll: function(selectAllId, targetName) {
        const selectAllCheckbox = document.getElementById(selectAllId);
        const checkboxes = document.querySelectorAll(`input[name="${targetName}"]`);
        
        if (selectAllCheckbox && checkboxes.length > 0) {
            const shouldCheck = !selectAllCheckbox.checked;
            checkboxes.forEach(cb => cb.checked = shouldCheck);
            selectAllCheckbox.checked = shouldCheck;
        }
    },

    // Count selected items
    getSelectedCount: function(targetName) {
        return document.querySelectorAll(`input[name="${targetName}"]:checked`).length;
    },

    // Get selected values
    getSelectedValues: function(targetName) {
        return Array.from(document.querySelectorAll(`input[name="${targetName}"]:checked`))
            .map(cb => cb.value);
    }
};

// Auto-initialize based on page context
document.addEventListener('DOMContentLoaded', function() {
    // Check which type of list page this is based on URL or body class
    const path = window.location.pathname;
    
    if (path.includes('/authors/')) {
        ListUtils.init('author');
    } else if (path.includes('/genres/')) {
        ListUtils.init('genre');
    } else if (path.includes('/series/')) {
        ListUtils.init('series');
    } else {
        ListUtils.init();
    }
});

/**
 * Enhanced Series List Functionality
 * Extracted from series_list_enhanced.html inline JavaScript
 */

// Series list specific JavaScript
function selectSeries(seriesId) {
    // Remove selection from all rows
    document.querySelectorAll('.series-row').forEach(row => {
        row.classList.remove('selected');
    });
    
    // Add selection to clicked row
    const row = document.querySelector(`[data-id="${seriesId}"]`);
    if (row) {
        row.classList.add('selected');
    }
    
    // Load series details
    if (typeof customLoadDetail === 'function') {
        customLoadDetail(seriesId);
    }
}

function onSeriesActivate(seriesId) {
    window.location.href = `/books/series/${seriesId}/`;
}

function viewSeriesDetails(seriesId) {
    window.location.href = `/books/series/${seriesId}/`;
}

function editSeries(seriesId) {
    window.location.href = `/books/series/${seriesId}/edit/`;
}

function toggleViewMode(mode) {
    const tableView = document.querySelector('.table-view');
    const gridView = document.querySelector('.grid-view');
    const buttons = document.querySelectorAll('[onclick*="toggleViewMode"]');
    
    if (mode === 'grid') {
        tableView?.classList.add('d-none');
        gridView?.classList.remove('d-none');
        buttons.forEach(btn => btn.classList.remove('active'));
        const gridBtn = document.querySelector('[onclick*="grid"]');
        gridBtn?.classList.add('active');
    } else {
        tableView?.classList.remove('d-none');
        gridView?.classList.add('d-none');
        buttons.forEach(btn => btn.classList.remove('active'));
        const tableBtn = document.querySelector('[onclick*="table"]');
        tableBtn?.classList.add('active');
    }
}

// Enhanced List Utils with series functionality
const EnhancedListUtils = {
    ...ListUtils,

    // Initialize enhanced series list with tooltips
    initEnhancedSeriesList: function() {
        // Initialize basic series functionality
        this.init('series');
        
        // Initialize tooltips
        if (typeof bootstrap !== 'undefined') {
            const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
            tooltipTriggerList.map(function (tooltipTriggerEl) {
                return new bootstrap.Tooltip(tooltipTriggerEl);
            });
        }
    }
};

// Export for global access
window.ListUtils = ListUtils;
window.EnhancedListUtils = EnhancedListUtils;