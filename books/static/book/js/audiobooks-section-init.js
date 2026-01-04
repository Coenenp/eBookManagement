/**
 * audiobooks-section-init.js
 * Initializes audiobooks section manager
 * Extracted from sections/audiobooks_main.html inline script
 */

/**
 * Initialize audiobooks section manager
 */
function initializeAudiobooksSection() {
    window.audiobooksManager = new AudiobooksSectionManager();
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', initializeAudiobooksSection);
