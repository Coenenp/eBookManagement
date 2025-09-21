/**
 * Split Pane Functionality
 * Provides resizable split-pane interface for media type sections
 */

let isResizing = false;
let startX = 0;
let startWidth = 0;

function initializeSplitPane() {
    const resizeHandle = document.querySelector('.resize-handle');
    const leftPanel = document.getElementById('list-panel');
    
    if (!resizeHandle || !leftPanel) {
        // Create resize handle if it doesn't exist
        createResizeHandle();
    }
    
    const handle = document.querySelector('.resize-handle');
    const panel = document.getElementById('list-panel');
    
    if (!handle || !panel) return;
    
    // Set initial position of resize handle
    updateResizeHandlePosition();
    
    // Mouse events for desktop
    handle.addEventListener('mousedown', startResize);
    document.addEventListener('mousemove', doResize);
    document.addEventListener('mouseup', stopResize);
    
    // Touch events for mobile
    handle.addEventListener('touchstart', startResize);
    document.addEventListener('touchmove', doResize);
    document.addEventListener('touchend', stopResize);
    
    // Window resize handler
    window.addEventListener('resize', updateResizeHandlePosition);
    
    // Make handle visible on hover
    makeResizeHandleVisible();
}

function createResizeHandle() {
    const existingHandle = document.querySelector('.resize-handle');
    if (existingHandle) return;
    
    const handle = document.createElement('div');
    handle.className = 'resize-handle';
    handle.setAttribute('data-direction', 'horizontal');
    
    // Insert after the main container
    const container = document.querySelector('.container-fluid.h-100');
    if (container && container.parentNode) {
        container.parentNode.insertBefore(handle, container.nextSibling);
    } else {
        document.body.appendChild(handle);
    }
}

function makeResizeHandleVisible() {
    const handle = document.querySelector('.resize-handle');
    const leftPanel = document.getElementById('list-panel');
    
    if (!handle || !leftPanel) return;
    
    // Show handle on panel hover
    leftPanel.addEventListener('mouseenter', () => {
        handle.style.opacity = '0.7';
    });
    
    leftPanel.addEventListener('mouseleave', () => {
        if (!isResizing) {
            handle.style.opacity = '0';
        }
    });
    
    // Show handle when near the border
    leftPanel.addEventListener('mousemove', (e) => {
        const rect = leftPanel.getBoundingClientRect();
        const distanceFromRight = rect.right - e.clientX;
        
        if (distanceFromRight <= 10) {
            handle.style.opacity = '1';
        } else if (distanceFromRight > 20 && !isResizing) {
            handle.style.opacity = '0';
        }
    });
}

function startResize(e) {
    e.preventDefault();
    isResizing = true;
    
    const resizeHandle = document.querySelector('.resize-handle');
    const leftPanel = document.getElementById('list-panel');
    
    if (!resizeHandle || !leftPanel) return;
    
    resizeHandle.classList.add('dragging');
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
    
    // Get initial values
    startX = e.clientX || (e.touches && e.touches[0].clientX);
    startWidth = leftPanel.offsetWidth;
    
    // Prevent text selection during resize
    document.addEventListener('selectstart', preventSelection);
}

function doResize(e) {
    if (!isResizing) return;
    
    e.preventDefault();
    
    const leftPanel = document.getElementById('list-panel');
    const rightPanel = document.getElementById('detail-panel');
    const container = document.querySelector('.container-fluid.h-100 .row');
    
    if (!leftPanel || !rightPanel || !container) return;
    
    const currentX = e.clientX || (e.touches && e.touches[0].clientX);
    const deltaX = currentX - startX;
    const newWidth = startWidth + deltaX;
    
    // Get container width
    const containerWidth = container.offsetWidth;
    
    // Calculate percentages
    const minWidthPx = 250;
    const maxWidthPx = Math.min(600, containerWidth * 0.7);
    const constrainedWidth = Math.max(minWidthPx, Math.min(maxWidthPx, newWidth));
    
    // Calculate percentage for Bootstrap grid
    const leftPercentage = (constrainedWidth / containerWidth) * 100;
    const rightPercentage = 100 - leftPercentage;
    
    // Update panel widths using flex-basis
    leftPanel.style.flexBasis = leftPercentage + '%';
    leftPanel.style.maxWidth = leftPercentage + '%';
    leftPanel.style.width = leftPercentage + '%';
    
    rightPanel.style.flexBasis = rightPercentage + '%';
    rightPanel.style.maxWidth = rightPercentage + '%';
    rightPanel.style.width = rightPercentage + '%';
    
    // Update handle position
    updateResizeHandlePosition();
}

function stopResize() {
    if (!isResizing) return;
    
    isResizing = false;
    
    const resizeHandle = document.querySelector('.resize-handle');
    if (resizeHandle) {
        resizeHandle.classList.remove('dragging');
    }
    
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
    document.removeEventListener('selectstart', preventSelection);
    
    // Save the panel width to localStorage for persistence
    const leftPanel = document.getElementById('list-panel');
    if (leftPanel) {
        localStorage.setItem('splitPaneWidth', leftPanel.offsetWidth);
    }
}

function updateResizeHandlePosition() {
    const resizeHandle = document.querySelector('.resize-handle');
    const leftPanel = document.getElementById('list-panel');
    
    if (!resizeHandle || !leftPanel) return;
    
    const rect = leftPanel.getBoundingClientRect();
    const containerRect = document.querySelector('.container-fluid.h-100').getBoundingClientRect();
    
    // Position handle at the right edge of the left panel
    resizeHandle.style.left = (rect.right - 3) + 'px';
    resizeHandle.style.top = containerRect.top + 'px';
    resizeHandle.style.height = containerRect.height + 'px';
    resizeHandle.style.position = 'fixed';
    resizeHandle.style.zIndex = '1000';
}

function preventSelection(e) {
    e.preventDefault();
    return false;
}

// Restore saved panel width on page load
function restorePanelWidth() {
    const savedWidth = localStorage.getItem('splitPaneWidth');
    const leftPanel = document.getElementById('list-panel');
    const rightPanel = document.getElementById('detail-panel');
    const container = document.querySelector('.container-fluid.h-100 .row');
    
    if (savedWidth && leftPanel && rightPanel && container && window.innerWidth > 768) {
        const width = parseInt(savedWidth);
        const containerWidth = container.offsetWidth || window.innerWidth;
        
        if (width >= 250 && width <= Math.min(600, containerWidth * 0.7)) {
            // Calculate percentages
            const leftPercentage = (width / containerWidth) * 100;
            const rightPercentage = 100 - leftPercentage;
            
            // Apply styles
            leftPanel.style.flexBasis = leftPercentage + '%';
            leftPanel.style.maxWidth = leftPercentage + '%';
            leftPanel.style.width = leftPercentage + '%';
            
            rightPanel.style.flexBasis = rightPercentage + '%';
            rightPanel.style.maxWidth = rightPercentage + '%';
            rightPanel.style.width = rightPercentage + '%';
            
            setTimeout(() => updateResizeHandlePosition(), 100);
        }
    }
}

// Auto-hide panels on mobile
function handleMobileLayout() {
    const leftPanel = document.getElementById('list-panel');
    const detailPanel = document.getElementById('detail-panel');
    
    if (window.innerWidth <= 768) {
        // Mobile layout: show only one panel at a time
        if (leftPanel && detailPanel) {
            const hasSelectedItem = document.querySelector('.list-item.selected');
            
            if (hasSelectedItem) {
                leftPanel.style.display = 'none';
                detailPanel.style.display = 'block';
            } else {
                leftPanel.style.display = 'block';
                detailPanel.style.display = 'none';
            }
        }
    } else {
        // Desktop layout: show both panels
        if (leftPanel && detailPanel) {
            leftPanel.style.display = 'block';
            detailPanel.style.display = 'block';
        }
    }
}

// Add back button for mobile detail view
function addMobileBackButton() {
    const detailPanel = document.getElementById('detail-panel');
    if (!detailPanel || window.innerWidth > 768) return;
    
    const existingBackBtn = detailPanel.querySelector('.mobile-back-btn');
    if (existingBackBtn) return;
    
    const backButton = document.createElement('button');
    backButton.className = 'btn btn-outline-secondary btn-sm mobile-back-btn position-absolute';
    backButton.style.cssText = 'top: 10px; left: 10px; z-index: 1000;';
    backButton.innerHTML = '<i class="fas fa-arrow-left me-1"></i>Back to List';
    
    backButton.addEventListener('click', function() {
        const leftPanel = document.getElementById('list-panel');
        const detailPanel = document.getElementById('detail-panel');
        
        if (leftPanel && detailPanel) {
            leftPanel.style.display = 'block';
            detailPanel.style.display = 'none';
            
            // Clear selection
            document.querySelectorAll('.list-item.selected').forEach(el => {
                el.classList.remove('selected');
            });
        }
    });
    
    detailPanel.appendChild(backButton);
}

// Initialize everything when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    // Small delay to ensure all other scripts have loaded
    setTimeout(() => {
        // Restore panel width
        restorePanelWidth();
        
        // Initialize split pane
        initializeSplitPane();
        
        // Handle window resize
        window.addEventListener('resize', function() {
            handleMobileLayout();
            updateResizeHandlePosition();
        });
        
        // Initial mobile layout check
        handleMobileLayout();
    }, 100);
});

// Export functions for use in other scripts
window.SplitPane = {
    initializeSplitPane,
    handleMobileLayout,
    addMobileBackButton,
    restorePanelWidth
};

/**
 * Generic List Management Functions
 */

// Smooth scrolling to selected item
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

// Keyboard navigation
function initializeKeyboardNavigation() {
    document.addEventListener('keydown', function(e) {
        const selectedItem = document.querySelector('.list-item.selected');
        const allItems = document.querySelectorAll('.list-item');
        
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
                    if (itemId && typeof onItemActivate === 'function') {
                        onItemActivate(itemId);
                    }
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
        }
    });
}

// Initialize keyboard navigation
document.addEventListener('DOMContentLoaded', initializeKeyboardNavigation);

// Utility function to show loading state
function showLoadingState(container, message = 'Loading...') {
    if (!container) return;
    
    container.innerHTML = `
        <div class="loading-item">
            <div class="spinner-border text-primary mb-2" role="status">
                <span class="visually-hidden">Loading...</span>
            </div>
            <p class="mb-0">${message}</p>
        </div>
    `;
}

// Utility function to show empty state
function showEmptyState(container, icon = 'fas fa-inbox', message = 'No items found') {
    if (!container) return;
    
    container.innerHTML = `
        <div class="empty-state">
            <i class="${icon}"></i>
            <p class="mb-0">${message}</p>
        </div>
    `;
}

// Export utility functions
window.SplitPaneUtils = {
    scrollToSelected,
    showLoadingState,
    showEmptyState
};