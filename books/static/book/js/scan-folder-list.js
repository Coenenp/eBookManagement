/**
 * Scan Folder List JavaScript functionality
 * Handles table sorting and folder management interactions
 */

/**
 * Sort table by column
 * @param {string} column - Column name to sort by
 */
function sortTable(column) {
    const urlParams = new URLSearchParams(window.location.search);
    const currentSort = urlParams.get('sort');
    const currentOrder = urlParams.get('order');
    
    let newOrder = 'asc';
    if (currentSort === column && currentOrder === 'asc') {
        newOrder = 'desc';
    }
    
    urlParams.set('sort', column);
    urlParams.set('order', newOrder);
    
    window.location.search = urlParams.toString();
}

// Initialize folder list functionality when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    // Add keyboard navigation support for table sorting
    document.querySelectorAll('.sortable-header').forEach(header => {
        header.addEventListener('keydown', function(e) {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                const sortColumn = this.getAttribute('data-sort');
                if (sortColumn) {
                    sortTable(sortColumn);
                }
            }
        });
        
        // Make headers focusable for accessibility
        header.setAttribute('tabindex', '0');
        header.setAttribute('role', 'button');
        header.setAttribute('aria-label', `Sort by ${header.textContent.trim()}`);
    });
    
    // Add hover effects for action buttons
    document.querySelectorAll('.action-btn').forEach(btn => {
        btn.addEventListener('mouseenter', function() {
            this.style.transform = 'scale(1.1)';
        });
        
        btn.addEventListener('mouseleave', function() {
            this.style.transform = 'scale(1)';
        });
    });
});

// Export for global access
window.ScanFolderList = {
    sortTable
};