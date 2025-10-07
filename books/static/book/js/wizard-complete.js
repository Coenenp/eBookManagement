/**
 * Wizard Complete Page JavaScript
 * Handles functionality for the final wizard completion step
 */

(function() {
    'use strict';

    // Ensure Wizard namespace exists
    window.Wizard = window.Wizard || {};

    /**
     * Wizard Complete Page functionality
     */
    Wizard.Complete = {
        /**
         * Initialize the complete page
         */
        init() {
            this.fixButtonSpinners();
            this.setupFormSubmission();
            this.setupActionCards();
            this.initializeAnimations();
        },

        /**
         * Fix any spinning button icons that should be static
         */
        fixButtonSpinners() {
            const buttons = document.querySelectorAll('.wizard-navigation button');
            
            buttons.forEach(button => {
                // Remove disabled attribute if present
                if (button.hasAttribute('disabled')) {
                    button.removeAttribute('disabled');
                }

                // Fix spinner icons and ensure correct icons
                const icons = button.querySelectorAll('i');
                icons.forEach(icon => {
                    // Remove any spinning or spinner classes
                    icon.classList.remove('fa-spin', 'fa-spinner');
                    
                    // Set appropriate icon based on button type
                    if (button.name === 'start_scan') {
                        icon.className = 'fas fa-search me-2';
                    } else if (button.type === 'submit') {
                        icon.className = 'fas fa-check me-2';
                    }
                });

                // Ensure button is not disabled
                button.disabled = false;
            });
        },

        /**
         * Setup form submission with proper loading states
         */
        setupFormSubmission() {
            const form = document.querySelector('form[method="post"]');
            if (!form) return;

            form.addEventListener('submit', (e) => {
                const submitButton = document.activeElement;
                
                if (submitButton && submitButton.type === 'submit') {
                    this.setButtonLoadingState(submitButton, true);
                    
                    // Determine action based on button
                    if (submitButton.name === 'start_scan') {
                        this.handleScanSubmission(submitButton);
                    } else {
                        this.handleCompleteSubmission(submitButton);
                    }
                }
            });
        },

        /**
         * Set button loading state
         * @param {HTMLElement} button - Button element
         * @param {boolean} loading - Whether to show loading state
         */
        setButtonLoadingState(button, loading) {
            const icon = button.querySelector('i');
            
            if (loading) {
                // Add loading class to button
                button.classList.add('loading');
                
                // Store original icon classes and text
                if (icon && !button.dataset.originalIcon) {
                    button.dataset.originalIcon = icon.className;
                }
                
                const originalText = button.textContent.trim();
                if (!button.dataset.originalText) {
                    button.dataset.originalText = originalText;
                }
                
                // Set loading state
                button.disabled = true;
                
                if (button.name === 'start_scan') {
                    button.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>Starting Scan...';
                } else {
                    button.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>Completing Setup...';
                }
            } else {
                // Remove loading class
                button.classList.remove('loading');
                
                // Restore original state
                button.disabled = false;
                
                if (button.dataset.originalText && button.dataset.originalIcon) {
                    button.innerHTML = `<i class="${button.dataset.originalIcon}"></i>${button.dataset.originalText}`;
                }
            }
        },

        /**
         * Handle scan submission
         * @param {HTMLElement} button - Submit button
         */
        handleScanSubmission(button) {
            // Call AJAX endpoint to trigger scanning of all folders
            this.triggerScanAllFolders()
                .then(() => {
                    // Show success message after AJAX call succeeds
                    setTimeout(() => {
                        const icon = button.querySelector('i');
                        if (icon) {
                            icon.className = 'fas fa-check-circle me-2 text-success';
                        }
                        button.innerHTML = '<i class="fas fa-check-circle me-2 text-success"></i>Scan Started!';
                    }, 500);
                })
                .catch((error) => {
                    console.error('Failed to start scan:', error);
                    // Show error state
                    setTimeout(() => {
                        const icon = button.querySelector('i');
                        if (icon) {
                            icon.className = 'fas fa-exclamation-circle me-2 text-warning';
                        }
                        button.innerHTML = '<i class="fas fa-exclamation-circle me-2 text-warning"></i>Scan will start on page load';
                    }, 500);
                });
        },

        /**
         * Handle complete submission
         * @param {HTMLElement} button - Submit button
         */
        handleCompleteSubmission(button) {
            // Show completion message
            setTimeout(() => {
                const icon = button.querySelector('i');
                if (icon) {
                    icon.className = 'fas fa-check-circle me-2 text-success';
                }
                button.innerHTML = '<i class="fas fa-check-circle me-2 text-success"></i>Setup Complete!';
            }, 800);
        },

        /**
         * Setup interactive action cards
         */
        setupActionCards() {
            const actionCards = document.querySelectorAll('.action-card-clickable');
            
            actionCards.forEach(card => {
                // Add hover effects
                card.addEventListener('mouseenter', () => {
                    card.classList.add('shadow-sm');
                    const chevron = card.querySelector('.fa-chevron-right');
                    if (chevron) {
                        chevron.style.transform = 'translateX(3px)';
                        chevron.style.transition = 'transform 0.2s ease';
                    }
                });

                card.addEventListener('mouseleave', () => {
                    card.classList.remove('shadow-sm');
                    const chevron = card.querySelector('.fa-chevron-right');
                    if (chevron) {
                        chevron.style.transform = 'translateX(0)';
                    }
                });

                // Add click feedback
                card.addEventListener('click', (e) => {
                    // Add brief scale effect
                    card.style.transform = 'scale(0.98)';
                    card.style.transition = 'transform 0.1s ease';
                    
                    setTimeout(() => {
                        card.style.transform = 'scale(1)';
                    }, 100);
                });
            });
        },

        /**
         * Initialize page animations
         */
        initializeAnimations() {
            // Animate completion icon
            const completionIcon = document.querySelector('.completion-icon i');
            if (completionIcon) {
                setTimeout(() => {
                    completionIcon.style.animation = 'pulse 2s ease-in-out infinite';
                }, 500);
            }

            // Animate feature highlights
            const features = document.querySelectorAll('.feature-highlight');
            features.forEach((feature, index) => {
                feature.style.opacity = '0';
                feature.style.transform = 'translateY(20px)';
                feature.style.transition = 'opacity 0.6s ease, transform 0.6s ease';
                
                setTimeout(() => {
                    feature.style.opacity = '1';
                    feature.style.transform = 'translateY(0)';
                }, 200 * index);
            });

            // Animate action cards
            const cards = document.querySelectorAll('.action-card');
            cards.forEach((card, index) => {
                card.style.opacity = '0';
                card.style.transform = 'translateX(-20px)';
                card.style.transition = 'opacity 0.5s ease, transform 0.5s ease';
                
                setTimeout(() => {
                    card.style.opacity = '1';
                    card.style.transform = 'translateX(0)';
                }, 100 * index);
            });
        },

        /**
         * Trigger scanning of all configured folders via AJAX
         * @returns {Promise} - Promise that resolves when scan is started
         */
        triggerScanAllFolders() {
            return new Promise((resolve, reject) => {
                fetch('/books/ajax/trigger-scan-all-folders/', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': this.getCSRFToken(),
                    },
                    credentials: 'same-origin'
                })
                .then(response => {
                    if (!response.ok) {
                        throw new Error(`HTTP error! status: ${response.status}`);
                    }
                    return response.json();
                })
                .then(data => {
                    if (data.success) {
                        console.log('Successfully started scans for all folders:', data.message);
                        resolve(data);
                    } else {
                        throw new Error(data.error || 'Unknown error starting scans');
                    }
                })
                .catch(error => {
                    console.error('Error triggering scan all folders:', error);
                    reject(error);
                });
            });
        },

        /**
         * Get CSRF token from cookies or meta tag
         * @returns {string} - CSRF token
         */
        getCSRFToken() {
            // Try to get from meta tag first
            const metaTag = document.querySelector('meta[name="csrf-token"]');
            if (metaTag) {
                return metaTag.getAttribute('content');
            }

            // Fallback to cookie
            const cookieValue = document.cookie
                .split('; ')
                .find(row => row.startsWith('csrftoken='));
            
            return cookieValue ? cookieValue.split('=')[1] : '';
        },

        /**
         * Show success message
         * @param {string} message - Message to show
         */
        showSuccessMessage(message) {
            // Create temporary success alert
            const alert = document.createElement('div');
            alert.className = 'alert alert-success alert-dismissible fade show position-fixed top-0 start-50 translate-middle-x mt-3';
            alert.style.zIndex = '9999';
            alert.innerHTML = `
                <i class="fas fa-check-circle me-2"></i>${message}
                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
            `;
            
            document.body.appendChild(alert);
            
            // Auto-hide after 3 seconds
            setTimeout(() => {
                if (alert.parentNode) {
                    alert.remove();
                }
            }, 3000);
        }
    };

    // Fix buttons immediately (before DOM loaded) to prevent spinning
    function fixButtonsImmediately() {
        const buttons = document.querySelectorAll('.wizard-navigation button');
        buttons.forEach(button => {
            if (button.hasAttribute('disabled')) {
                button.removeAttribute('disabled');
            }
            
            const icons = button.querySelectorAll('i.fa-spin, i.fa-spinner');
            icons.forEach(icon => {
                icon.classList.remove('fa-spin', 'fa-spinner');
                if (button.name === 'start_scan') {
                    icon.className = 'fas fa-search me-2';
                } else {
                    icon.className = 'fas fa-check me-2';
                }
            });
        });
    }

    // Initialize when DOM is loaded
    document.addEventListener('DOMContentLoaded', () => {
        // Only initialize if we're on the wizard complete page
        if (document.querySelector('.wizard-complete-page')) {
            Wizard.Complete.init();
        }
    });

    // Also try to fix buttons immediately in case they're already in the DOM
    if (document.readyState !== 'loading') {
        fixButtonsImmediately();
    } else {
        document.addEventListener('DOMContentLoaded', fixButtonsImmediately);
    }

    // Export to window for external access
    window.Wizard.Complete = Wizard.Complete;

})();