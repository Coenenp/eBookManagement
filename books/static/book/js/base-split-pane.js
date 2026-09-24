/**
 * Base Split Pane JavaScript functionality
 * Handles filtering, view toggling, keyboard shortcuts, and UI interactions
 */

document.addEventListener('DOMContentLoaded', function () {
    // Initialize split pane functionality
    initializeSplitPane();

    // Initialize enhanced UI features (view toggle, clear, keyboard, delegation).
    // Filtering itself is owned by the section managers (BaseSectionManager.bindEvents),
    // which bind the search/sort/format/status controls; base-split-pane must not
    // double-bind them.
    initializeEnhancedUI();

    // Load initial data (delegates to the section manager's loadData via the
    // customLoadItems compatibility function).
    loadItems();

    // Initialize keyboard navigation
    initializeKeyboardNavigation();
});

function initializeEnhancedUI() {
    // Initialize view toggle
    initializeViewToggle();

    // Initialize search clear functionality
    initializeSearchClear();

    // Initialize keyboard shortcuts
    initializeKeyboardShortcuts();

    // Initialize event delegation for dynamic content
    initializeEventDelegation();
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
            viewContainer: !!viewContainer,
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
        searchFilter.addEventListener('paste', function () {
            setTimeout(updateClearButton, 10);
        });

        // Handle programmatic value changes
        const observer = new MutationObserver(function (mutations) {
            mutations.forEach(function (mutation) {
                if (mutation.type === 'attributes' && mutation.attributeName === 'value') {
                    updateClearButton();
                }
            });
        });

        observer.observe(searchFilter, {
            attributes: true,
            attributeFilter: ['value'],
        });
    }
}

function clearSearch() {
    const searchFilter = document.getElementById('search-filter');
    const clearBtn = document.getElementById('clear-search');

    if (searchFilter) {
        searchFilter.value = '';
        searchFilter.focus();

        // Dispatch an input event; the section manager's own listener re-filters.
        searchFilter.dispatchEvent(new Event('input', { bubbles: true }));
    }

    if (clearBtn) {
        clearBtn.style.display = 'none';
    }
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
    document.addEventListener('keydown', function (e) {
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

function initializeEventDelegation() {
    // Use event delegation to handle clicks on dynamically added elements
    document.addEventListener('click', function (e) {
        // View toggle buttons
        if (e.target.matches('.view-toggle-btn') || e.target.closest('.view-toggle-btn')) {
            const button = e.target.closest('.view-toggle-btn');
            const viewType = button.getAttribute('data-view');
            if (viewType) {
                toggleView(viewType);
            }
        }

        // Clear search button
        if (e.target.matches('#clear-search') || e.target.closest('#clear-search')) {
            clearSearch();
        }

        // Refresh button
        if (e.target.matches('.refresh-btn') || e.target.closest('.refresh-btn')) {
            refreshItems();
        }

        // Filters toggle button
        if (e.target.matches('.filters-btn') || e.target.closest('.filters-btn')) {
            toggleFilters();
        }
    });
}

function initializeKeyboardNavigation() {
    // This function can be extended for keyboard navigation between items
    document.addEventListener('keydown', function (e) {
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

function loadItems() {
    // Implementation will be customized per media type
    if (typeof customLoadItems === 'function') {
        customLoadItems();
    }
}

function selectItem(itemId) {
    // Remove previous selection
    document.querySelectorAll('.list-item.selected').forEach((el) => {
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
        counter.classList.add('count-bump');
        setTimeout(() => {
            counter.classList.remove('count-bump');
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
                block: 'center',
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
    loadItems,
};
