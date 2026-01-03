/**
 * Base Section JavaScript - Legacy compatibility functions
 * Provides compatibility between new class-based managers and existing split-pane infrastructure
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

// Item activation handler (double-click or Enter key)
function onItemActivate(itemId) {
    const manager = getManagerForSection(getCurrentSection());
    if (manager && manager.onItemActivate) {
        manager.onItemActivate(itemId);
    }
}

// Export functions for use by other scripts
window.BaseSection = {
    selectItem,
    updateItemCount,
    getCurrentSection,
    getManagerForSection,
    onItemActivate
};