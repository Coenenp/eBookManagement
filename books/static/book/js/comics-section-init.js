/**
 * comics-section-init.js
 * Initializes comics section with split-pane compatibility
 * Extracted from sections/comics_main.html inline script
 */

/**
 * Select and display comic item
 * Base functionality integration for split-pane compatibility
 * @param {number} itemId - Comic item ID
 */
function selectItem(itemId) {
    // Clear previous selection
    document.querySelectorAll('.list-item.selected').forEach((el) => {
        el.classList.remove('selected');
    });

    // Add selection to new item
    const newItem = document.querySelector(`[data-item-id="${itemId}"]`);
    if (newItem) {
        newItem.classList.add('selected');
    }

    // Load item detail using the comics manager
    if (window.comicsManager) {
        window.comicsManager.selectItem(itemId);
    }
}

/**
 * Initialize comics section manager
 */
function initializeComicsSection() {
    window.comicsManager = new ComicsSectionManager();
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', initializeComicsSection);

// Export for template use
window.selectItem = selectItem;
