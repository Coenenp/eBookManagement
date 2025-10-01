/**
 * Base Split Pane JavaScript functionality
 * Handles filtering, view toggling, keyboard shortcuts, and UI interactions
 */

document.addEventListener('DOMContentLoaded', function() {
    // Initialize split pane functionality
    initializeSplitPane();
    
    // Initialize filtering
    initializeFilters();
    
    // Initialize enhanced UI features
    initializeEnhancedUI();
    
    // Load initial data
    loadItems();
    
    // Initialize keyboard navigation
    initializeKeyboardNavigation();
});

function initializeFilters() {
    const searchFilter = document.getElementById('search-filter');
    const sortFilter = document.getElementById('sort-filter');
    const formatFilter = document.getElementById('format-filter');
    const statusFilter = document.getElementById('status-filter');
    
    if (searchFilter) {
        searchFilter.addEventListener('input', debounce(handleSearchInput, 300));
    }
    
    if (sortFilter) {
        sortFilter.addEventListener('change', filterItems);
    }
    
    if (formatFilter) {
        formatFilter.addEventListener('change', filterItems);
    }
    
    if (statusFilter) {
        statusFilter.addEventListener('change', filterItems);
    }
}

function initializeEnhancedUI() {
    // Initialize view toggle
    initializeViewToggle();
    
    // Initialize search clear functionality
    initializeSearchClear();
    
    // Initialize keyboard shortcuts
    initializeKeyboardShortcuts();
}

function initializeViewToggle() {
    const listViewBtn = document.getElementById('list-view-btn');
    const gridViewBtn = document.getElementById('grid-view-btn');
    const viewContainer = document.getElementById('view-container');
    
    if (listViewBtn && gridViewBtn && viewContainer) {
        // Load saved view preference
        const savedView = localStorage.getItem('preferredView') || 'list';
        toggleView(savedView);
    }
}

function toggleView(viewType) {
    const listViewBtn = document.getElementById('list-view-btn');
    const gridViewBtn = document.getElementById('grid-view-btn');
    const viewContainer = document.getElementById('view-container');
    
    if (!listViewBtn || !gridViewBtn || !viewContainer) {
        console.error('Toggle view elements not found:', {
            listViewBtn: !!listViewBtn,
            gridViewBtn: !!gridViewBtn,
            viewContainer: !!viewContainer
        });
        return;
    }
    
    // Update button states
    listViewBtn.classList.toggle('active', viewType === 'list');
    gridViewBtn.classList.toggle('active', viewType === 'grid');
    
    // Update container class
    viewContainer.className = `${viewType}-view`;
    
    // Save preference
    localStorage.setItem('preferredView', viewType);
    
    // Trigger re-render if custom function exists
    if (typeof customRenderView === 'function') {
        customRenderView(viewType);
    } else {
        console.log('customRenderView function not found, view updated to:', viewType);
    }
}

function initializeSearchClear() {
    const searchFilter = document.getElementById('search-filter');
    const clearBtn = document.getElementById('clear-search');
    
    if (searchFilter && clearBtn) {
        // Show/hide clear button based on input content
        function updateClearButton() {
            clearBtn.style.display = searchFilter.value ? 'flex' : 'none';
        }
        
        // Initialize button visibility
        updateClearButton();
        
        // Update on input
        searchFilter.addEventListener('input', updateClearButton);
        
        // Handle paste events
        searchFilter.addEventListener('paste', function() {
            setTimeout(updateClearButton, 10);
        });
        
        // Handle programmatic value changes
        const observer = new MutationObserver(function(mutations) {
            mutations.forEach(function(mutation) {
                if (mutation.type === 'attributes' && mutation.attributeName === 'value') {
                    updateClearButton();
                }
            });
        });
        
        observer.observe(searchFilter, {
            attributes: true,
            attributeFilter: ['value']
        });
    }
}

function clearSearch() {
    const searchFilter = document.getElementById('search-filter');
    const clearBtn = document.getElementById('clear-search');
    
    if (searchFilter) {
        searchFilter.value = '';
        searchFilter.focus();
        
        // Trigger input event to update any listeners
        searchFilter.dispatchEvent(new Event('input', { bubbles: true }));
    }
    
    if (clearBtn) {
        clearBtn.style.display = 'none';
    }
    
    filterItems();
}

function handleSearchInput() {
    const searchFilter = document.getElementById('search-filter');
    const clearBtn = document.getElementById('clear-search');
    
    if (clearBtn) {
        clearBtn.style.display = searchFilter && searchFilter.value ? 'block' : 'none';
    }
    
    filterItems();
}

function toggleFilters() {
    const advancedFilters = document.getElementById('advanced-filters');
    const btn = event.target.closest('button');
    
    if (advancedFilters) {
        const isHidden = advancedFilters.classList.contains('d-none');
        advancedFilters.classList.toggle('d-none');
        
        // Update button text
        if (btn) {
            const icon = btn.querySelector('i');
            const text = btn.querySelector('.btn-text') || btn.childNodes[1];
            if (isHidden) {
                if (icon) icon.className = 'fas fa-filter-circle-xmark me-1';
                if (text) text.textContent = 'Hide';
            } else {
                if (icon) icon.className = 'fas fa-filter me-1';
                if (text) text.textContent = 'Filters';
            }
        }
    }
}

function refreshItems() {
    const btn = event.target.closest('button');
    const originalContent = btn.innerHTML;
    
    btn.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i>Refreshing...';
    btn.disabled = true;
    
    // Call custom refresh function or default load
    if (typeof customRefreshItems === 'function') {
        customRefreshItems();
    } else {
        loadItems();
    }
    
    setTimeout(() => {
        btn.innerHTML = originalContent;
        btn.disabled = false;
    }, 1000);
}

function initializeKeyboardShortcuts() {
    document.addEventListener('keydown', function(e) {
        // Ctrl/Cmd + F - Focus search
        if ((e.ctrlKey || e.metaKey) && e.key === 'f') {
            e.preventDefault();
            const searchFilter = document.getElementById('search-filter');
            if (searchFilter) {
                searchFilter.focus();
                searchFilter.select();
            }
        }
        
        // Ctrl/Cmd + R - Refresh
        if ((e.ctrlKey || e.metaKey) && e.key === 'r') {
            e.preventDefault();
            refreshItems();
        }
        
        // Ctrl/Cmd + 1/2 - Toggle view
        if ((e.ctrlKey || e.metaKey) && (e.key === '1' || e.key === '2')) {
            e.preventDefault();
            toggleView(e.key === '1' ? 'list' : 'grid');
        }
    });
}

function initializeKeyboardNavigation() {
    // This function can be extended for keyboard navigation between items
    document.addEventListener('keydown', function(e) {
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT' || e.target.tagName === 'TEXTAREA') {
            return; // Don't interfere with form inputs
        }
        
        // Arrow key navigation (can be extended)
        if (e.key === 'ArrowUp' || e.key === 'ArrowDown') {
            e.preventDefault();
            // Implementation for navigating between list items
            navigateItems(e.key === 'ArrowUp' ? -1 : 1);
        }
    });
}

function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

function filterItems() {
    // Implementation will be customized per media type
    const searchTerm = document.getElementById('search-filter')?.value || '';
    const sortBy = document.getElementById('sort-filter')?.value || 'title';
    const formatFilter = document.getElementById('format-filter')?.value || '';
    const statusFilter = document.getElementById('status-filter')?.value || '';
    
    // Trigger custom filter function
    if (typeof customFilterItems === 'function') {
        customFilterItems(searchTerm, sortBy, formatFilter, statusFilter);
    }
}

function loadItems() {
    // Implementation will be customized per media type
    if (typeof customLoadItems === 'function') {
        customLoadItems();
    }
}

function selectItem(itemId) {
    // Remove previous selection
    document.querySelectorAll('.list-item.selected').forEach(el => {
        el.classList.remove('selected');
    });
    
    // Add selection to clicked item
    const item = document.querySelector(`[data-item-id="${itemId}"]`);
    if (item) {
        item.classList.add('selected');
        
        // Scroll to selected item
        scrollToSelected();
    }
    
    // Load detail view
    if (typeof customLoadDetail === 'function') {
        customLoadDetail(itemId);
    }
}

function navigateItems(direction) {
    const items = document.querySelectorAll('.list-item');
    const selected = document.querySelector('.list-item.selected');
    
    if (items.length === 0) return;
    
    let targetIndex = 0;
    
    if (selected) {
        const currentIndex = Array.from(items).indexOf(selected);
        targetIndex = Math.max(0, Math.min(items.length - 1, currentIndex + direction));
    }
    
    const targetItem = items[targetIndex];
    if (targetItem) {
        const itemId = targetItem.getAttribute('data-item-id');
        if (itemId) {
            selectItem(itemId);
        }
    }
}

function updateItemCount(count) {
    const counter = document.getElementById('item-count');
    if (counter) {
        counter.textContent = count;
        
        // Add animation
        counter.style.transform = 'scale(1.2)';
        setTimeout(() => {
            counter.style.transform = 'scale(1)';
        }, 200);
    }
}

// Utility function for smooth scrolling to selected item
function scrollToSelected() {
    const selectedItem = document.querySelector('.list-item.selected');
    const listContainer = document.getElementById('items-list');
    
    if (selectedItem && listContainer) {
        const itemRect = selectedItem.getBoundingClientRect();
        const containerRect = listContainer.getBoundingClientRect();
        
        if (itemRect.top < containerRect.top || itemRect.bottom > containerRect.bottom) {
            selectedItem.scrollIntoView({
                behavior: 'smooth',
                block: 'center'
            });
        }
    }
}

// Export functions for global access (if needed by other scripts)
window.BaseSplitPane = {
    toggleView,
    clearSearch,
    toggleFilters,
    refreshItems,
    selectItem,
    updateItemCount,
    filterItems,
    loadItems
};