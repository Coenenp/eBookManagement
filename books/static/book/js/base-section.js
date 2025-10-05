/**
 * Base Section JavaScript - Shared functionality for all media sections
 * Provides common functions and integrations for split-pane functionality
 */

/**
 * Base Split-Pane Integration Functions
 * These functions provide compatibility between the new class-based managers
 * and the existing split-pane infrastructure
 */

// Global item selection function for split-pane compatibility
function selectItem(itemId) {
    // Clear previous selection
    document.querySelectorAll('.list-item.selected').forEach(el => {
        el.classList.remove('selected');
    });
    
    // Add selection to new item
    const newItem = document.querySelector(`[data-item-id="${itemId}"]`);
    if (newItem) {
        newItem.classList.add('selected');
    }
    
    // Determine which manager to use based on the current page
    const currentSection = getCurrentSection();
    const manager = getManagerForSection(currentSection);
    
    if (manager && manager.selectItem) {
        manager.selectItem(itemId);
    } else {
        console.warn(`No manager found for section: ${currentSection}`);
    }
    
    // Smooth scroll to selected item
    if (window.SplitPaneUtils && window.SplitPaneUtils.scrollToSelected) {
        window.SplitPaneUtils.scrollToSelected();
    }
}

// Update item count display
function updateItemCount(count) {
    const countElement = document.getElementById('item-count');
    if (countElement) {
        countElement.textContent = count;
    }
}

// Get current section based on URL or page indicators
function getCurrentSection() {
    const path = window.location.pathname;
    
    if (path.includes('/ebooks/')) return 'ebooks';
    if (path.includes('/comics/')) return 'comics';
    if (path.includes('/audiobooks/')) return 'audiobooks';
    if (path.includes('/series/')) return 'series';
    
    // Fallback: check for section-specific elements
    if (document.getElementById('ebooks-list-container')) return 'ebooks';
    if (document.getElementById('comics-list-container')) return 'comics';
    if (document.getElementById('audiobooks-list-container')) return 'audiobooks';
    if (document.getElementById('series-list-container')) return 'series';
    
    return 'unknown';
}

// Get the appropriate manager for the current section
function getManagerForSection(section) {
    const managers = {
        'ebooks': window.ebookManager,
        'comics': window.comicsManager,
        'audiobooks': window.audiobookManager,
        'series': window.seriesManager
    };
    
    return managers[section] || null;
}

// Legacy compatibility functions - these delegate to the appropriate manager
function customLoadItems() {
    const manager = getManagerForSection(getCurrentSection());
    if (manager && manager.loadItems) {
        manager.loadItems();
    }
}

function customFilterItems(searchTerm, sortBy, formatFilter, statusFilter) {
    const manager = getManagerForSection(getCurrentSection());
    if (manager && manager.filterItems) {
        manager.filterItems(searchTerm, sortBy, formatFilter, statusFilter);
    }
}

function customRenderView(viewType) {
    const manager = getManagerForSection(getCurrentSection());
    if (manager && manager.renderList) {
        manager.renderList(viewType);
    }
}

function customRefreshItems() {
    const manager = getManagerForSection(getCurrentSection());
    if (manager && manager.loadItems) {
        manager.loadItems();
    }
}

function customLoadDetail(itemId) {
    const manager = getManagerForSection(getCurrentSection());
    if (manager && manager.loadDetail) {
        manager.loadDetail(itemId);
    }
}

// Item activation handler (double-click or Enter key)
function onItemActivate(itemId) {
    const manager = getManagerForSection(getCurrentSection());
    if (manager && manager.onItemActivate) {
        manager.onItemActivate(itemId);
    }
}

// Comics-specific legacy function
function toggleSeries(seriesId) {
    if (window.comicsManager && window.comicsManager.toggleSeries) {
        window.comicsManager.toggleSeries(seriesId);
    }
}

/**
 * Common Event Binding for Split-Pane Sections
 * Binds standard events that all sections use
 */
function bindCommonSectionEvents() {
    // Search input
    const searchInput = document.getElementById('search-input');
    if (searchInput) {
        searchInput.addEventListener('input', function() {
            const sortSelect = document.getElementById('sort-select');
            const formatSelect = document.getElementById('format-filter');
            const statusSelect = document.getElementById('status-filter');
            
            customFilterItems(
                this.value,
                sortSelect ? sortSelect.value : 'title',
                formatSelect ? formatSelect.value : '',
                statusSelect ? statusSelect.value : ''
            );
        });
    }
    
    // Sort selection
    const sortSelect = document.getElementById('sort-select');
    if (sortSelect) {
        sortSelect.addEventListener('change', function() {
            const searchInput = document.getElementById('search-input');
            const formatSelect = document.getElementById('format-filter');
            const statusSelect = document.getElementById('status-filter');
            
            customFilterItems(
                searchInput ? searchInput.value : '',
                this.value,
                formatSelect ? formatSelect.value : '',
                statusSelect ? statusSelect.value : ''
            );
        });
    }
    
    // Format filter
    const formatSelect = document.getElementById('format-filter');
    if (formatSelect) {
        formatSelect.addEventListener('change', function() {
            const searchInput = document.getElementById('search-input');
            const sortSelect = document.getElementById('sort-select');
            const statusSelect = document.getElementById('status-filter');
            
            customFilterItems(
                searchInput ? searchInput.value : '',
                sortSelect ? sortSelect.value : 'title',
                this.value,
                statusSelect ? statusSelect.value : ''
            );
        });
    }
    
    // Status filter (if present)
    const statusSelect = document.getElementById('status-filter');
    if (statusSelect) {
        statusSelect.addEventListener('change', function() {
            const searchInput = document.getElementById('search-input');
            const sortSelect = document.getElementById('sort-select');
            const formatSelect = document.getElementById('format-filter');
            
            customFilterItems(
                searchInput ? searchInput.value : '',
                sortSelect ? sortSelect.value : 'title',
                formatSelect ? formatSelect.value : '',
                this.value
            );
        });
    }
    
    // Refresh button
    const refreshBtn = document.getElementById('refresh-btn');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', function() {
            customRefreshItems();
        });
    }
    
    // View toggle buttons
    document.querySelectorAll('[data-view-type]').forEach(btn => {
        btn.addEventListener('click', function() {
            const viewType = this.getAttribute('data-view-type');
            
            // Update active state
            document.querySelectorAll('[data-view-type]').forEach(b => b.classList.remove('active'));
            this.classList.add('active');
            
            // Update view
            customRenderView(viewType);
        });
    });
}

/**
 * Common Keyboard Event Handlers
 * Provides keyboard navigation that works with all section managers
 */
function bindCommonKeyboardEvents() {
    document.addEventListener('keydown', function(e) {
        // Only handle keyboard events when not in an input field
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') {
            return;
        }
        
        const selectedItem = document.querySelector('.list-item.selected');
        const allItems = document.querySelectorAll('.list-item[data-item-id]');
        
        if (allItems.length === 0) return;
        
        let currentIndex = -1;
        if (selectedItem) {
            currentIndex = Array.from(allItems).indexOf(selectedItem);
        }
        
        switch(e.key) {
            case 'ArrowDown':
                e.preventDefault();
                if (currentIndex < allItems.length - 1) {
                    const nextItem = allItems[currentIndex + 1];
                    const itemId = nextItem.getAttribute('data-item-id');
                    if (itemId) selectItem(itemId);
                }
                break;
                
            case 'ArrowUp':
                e.preventDefault();
                if (currentIndex > 0) {
                    const prevItem = allItems[currentIndex - 1];
                    const itemId = prevItem.getAttribute('data-item-id');
                    if (itemId) selectItem(itemId);
                } else if (currentIndex === -1 && allItems.length > 0) {
                    const firstItem = allItems[0];
                    const itemId = firstItem.getAttribute('data-item-id');
                    if (itemId) selectItem(itemId);
                }
                break;
                
            case 'Enter':
                if (selectedItem) {
                    e.preventDefault();
                    const itemId = selectedItem.getAttribute('data-item-id');
                    if (itemId) onItemActivate(itemId);
                }
                break;
                
            case 'Escape':
                if (window.innerWidth <= 768) {
                    // Mobile: go back to list view
                    const leftPanel = document.getElementById('list-panel');
                    const detailPanel = document.getElementById('detail-panel');
                    
                    if (leftPanel && detailPanel) {
                        leftPanel.style.display = 'block';
                        detailPanel.style.display = 'none';
                        
                        document.querySelectorAll('.list-item.selected').forEach(el => {
                            el.classList.remove('selected');
                        });
                    }
                }
                break;
                
            case 'r':
                if (e.ctrlKey || e.metaKey) {
                    e.preventDefault();
                    customRefreshItems();
                }
                break;
        }
    });
}

/**
 * Initialize Common Section Functionality
 * Call this from each section's initialization
 */
function initializeBaseSection() {
    // Bind common events
    bindCommonSectionEvents();
    bindCommonKeyboardEvents();
    
    // Load initial data for the current section
    setTimeout(() => {
        customLoadItems();
    }, 100);
}

// Auto-initialize when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    // Small delay to ensure section-specific scripts have loaded
    setTimeout(() => {
        initializeBaseSection();
    }, 200);
});

// Export functions for use by other scripts
window.BaseSection = {
    selectItem,
    updateItemCount,
    getCurrentSection,
    getManagerForSection,
    customLoadItems,
    customFilterItems,
    customRenderView,
    customRefreshItems,
    customLoadDetail,
    onItemActivate,
    toggleSeries,
    bindCommonSectionEvents,
    bindCommonKeyboardEvents,
    initializeBaseSection
};