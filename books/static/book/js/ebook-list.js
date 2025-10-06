/**
 * Enhanced Ebook List Manager - Dynamic table rendering and sorting
 * Extracted from ebook_list_enhanced.html inline JavaScript
 */

class EnhancedEbookList {
    constructor() {
        this.filteredEbooks = [];
        this.init();
    }

    init() {
        this.bindEvents();
    }

    bindEvents() {
        // Handle clear filters button using CSS class
        document.addEventListener('click', (e) => {
            if (e.target.closest('.clear-filters-btn')) {
                e.preventDefault();
                this.clearFilters();
            }
        });

        // Initialize table sorting when content is loaded
        this.initializeTableSorting();
    }

    renderEbookRow(ebook) {
        const coverImg = ebook.cover_url ? 
            `<img src="${ebook.cover_url}" alt="Cover" class="list-cover">` :
            `<div class="list-cover-placeholder"><i class="fas fa-book"></i></div>`;
        
        const seriesText = ebook.series_name ? 
            `${this.escapeHtml(ebook.series_name)}${ebook.series_position ? ` #${ebook.series_position}` : ''}` : 
            '-';
        
        return `
            <tr class="enhanced-row list-item" 
                data-id="${ebook.id}" 
                onclick="selectEbook(${ebook.id})"
                ondblclick="onItemActivate(${ebook.id})"
                role="button"
                tabindex="0"
                aria-label="Select ebook ${this.escapeHtml(ebook.title)}">
                
                <td class="align-middle">
                    <div class="d-flex align-items-center">
                        <div class="me-2">
                            ${coverImg}
                        </div>
                        <div class="book-info">
                            <div class="book-title fw-semibold text-truncate">${this.escapeHtml(ebook.title || 'Unknown Title')}</div>
                            ${ebook.subtitle ? `<div class="book-subtitle text-muted small text-truncate">${this.escapeHtml(ebook.subtitle)}</div>` : ''}
                        </div>
                    </div>
                </td>
                
                <td class="align-middle">
                    <span class="fw-medium">${this.escapeHtml(ebook.author || 'Unknown Author')}</span>
                </td>
                
                <td class="align-middle">
                    <span>${this.escapeHtml(ebook.publisher || '-')}</span>
                </td>
                
                <td class="align-middle">
                    <span>${seriesText}</span>
                </td>
                
                <td class="align-middle">
                    <span class="badge bg-primary">${ebook.file_format ? ebook.file_format.toUpperCase() : 'UNKNOWN'}</span>
                </td>
                
                <td class="align-middle">
                    <span>${this.formatFileSize(ebook.file_size)}</span>
                </td>
                
                <td class="align-middle">
                    <span class="text-muted small">${ebook.last_scanned ? this.formatDate(ebook.last_scanned) : 'Never'}</span>
                </td>
            </tr>
        `;
    }

    populateEbookTable(ebooks) {
        const tableContainer = document.getElementById('ebook-table-container');
        const tableBody = document.getElementById('ebook-table-body');
        const loadingState = document.getElementById('loading-state');
        const emptyState = document.getElementById('empty-state');
        
        // Hide loading state
        if (loadingState) {
            loadingState.classList.add('d-none');
        }
        
        if (ebooks && ebooks.length > 0) {
            // Show table and populate with data
            tableContainer?.classList.remove('d-none');
            emptyState?.classList.add('d-none');
            
            if (tableBody) {
                tableBody.innerHTML = ebooks.map(ebook => this.renderEbookRow(ebook)).join('');
            }
            
            // Initialize table sorting
            this.initializeTableSorting();
        } else {
            // Show empty state
            tableContainer?.classList.add('d-none');
            emptyState?.classList.remove('d-none');
        }
    }

    initializeTableSorting() {
        const sortColumns = document.querySelectorAll('.sortable-column');
        sortColumns.forEach(column => {
            // Remove existing listeners to avoid duplicates
            const newColumn = column.cloneNode(true);
            column.parentNode.replaceChild(newColumn, column);
            
            newColumn.addEventListener('click', () => {
                const sortField = newColumn.dataset.sort;
                this.sortEbookTable(sortField);
            });
        });
    }

    sortEbookTable(field) {
        // Sort the current filtered data
        if (this.filteredEbooks && this.filteredEbooks.length > 0) {
            const sortedEbooks = [...this.filteredEbooks].sort((a, b) => {
                let aVal = a[field] || '';
                let bVal = b[field] || '';
                
                // Handle special cases
                if (field === 'file_size') {
                    aVal = parseInt(aVal) || 0;
                    bVal = parseInt(bVal) || 0;
                    return bVal - aVal; // Descending for file size
                }
                
                if (field === 'last_scanned') {
                    aVal = new Date(aVal || 0);
                    bVal = new Date(bVal || 0);
                    return bVal - aVal; // Descending for dates
                }
                
                // String comparison
                return aVal.toString().toLowerCase().localeCompare(bVal.toString().toLowerCase());
            });
            
            this.populateEbookTable(sortedEbooks);
            
            // Update sort indicators
            document.querySelectorAll('.sort-icon').forEach(icon => {
                icon.className = 'fas fa-sort ms-1 sort-icon';
            });
            const activeSort = document.querySelector(`[data-sort="${field}"] .sort-icon`);
            if (activeSort) {
                activeSort.className = 'fas fa-sort-up ms-1 sort-icon';
            }
        }
    }

    clearFilters() {
        const searchFilter = document.getElementById('search-filter');
        const formatFilter = document.getElementById('format-filter');
        const sortFilter = document.getElementById('sort-filter');
        
        if (searchFilter) searchFilter.value = '';
        if (formatFilter) formatFilter.value = '';
        if (sortFilter) sortFilter.value = 'title';
        
        // Reload data
        if (typeof customLoadItems === 'function') {
            customLoadItems();
        }
    }

    selectEbook(ebookId) {
        // Remove selection from all rows
        document.querySelectorAll('.list-item').forEach(row => {
            row.classList.remove('selected');
        });
        
        // Add selection to clicked row
        const row = document.querySelector(`[data-id="${ebookId}"]`);
        if (row) {
            row.classList.add('selected');
        }
        
        // Load ebook details
        if (typeof customLoadDetail === 'function') {
            customLoadDetail(ebookId);
        }
    }

    // Main render function called from main JavaScript
    renderEbooksList(ebooks) {
        this.filteredEbooks = ebooks; // Store for sorting
        window.filteredEbooks = ebooks; // Keep global for compatibility
        this.populateEbookTable(ebooks);
        
        // Update item count if function exists
        if (typeof updateItemCount === 'function') {
            updateItemCount(ebooks.length);
        }
    }

    // Utility functions
    escapeHtml(text) {
        if (typeof EbookLibrary !== 'undefined' && EbookLibrary.Utils && EbookLibrary.Utils.escapeHtml) {
            return EbookLibrary.Utils.escapeHtml(text);
        }
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    formatFileSize(bytes) {
        if (typeof EbookLibrary !== 'undefined' && EbookLibrary.Utils && EbookLibrary.Utils.formatFileSize) {
            return EbookLibrary.Utils.formatFileSize(bytes);
        }
        
        if (!bytes || bytes === 0) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
    }

    formatDate(dateString) {
        if (typeof EbookLibrary !== 'undefined' && EbookLibrary.Utils && EbookLibrary.Utils.formatDate) {
            return EbookLibrary.Utils.formatDate(dateString);
        }
        
        try {
            return new Date(dateString).toLocaleDateString();
        } catch (e) {
            return 'Invalid Date';
        }
    }
}

// Global instance
let enhancedEbookList;

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    enhancedEbookList = new EnhancedEbookList();
});

// Global functions for backward compatibility
function renderEbookRow(ebook) {
    return enhancedEbookList ? enhancedEbookList.renderEbookRow(ebook) : '';
}

function populateEbookTable(ebooks) {
    if (enhancedEbookList) {
        enhancedEbookList.populateEbookTable(ebooks);
    }
}

function selectEbook(ebookId) {
    if (enhancedEbookList) {
        enhancedEbookList.selectEbook(ebookId);
    }
}

function clearFilters() {
    if (enhancedEbookList) {
        enhancedEbookList.clearFilters();
    }
}

function renderEbooksList(ebooks) {
    if (enhancedEbookList) {
        enhancedEbookList.renderEbooksList(ebooks);
    }
}

// Export for global access
window.EnhancedEbookList = EnhancedEbookList;