/**
 * Wizard Complete Page JavaScript
 * Handles functionality for the final wizard completion step
 */

(function () {
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

            buttons.forEach((button) => {
                // Remove disabled attribute if present
                if (button.hasAttribute('disabled')) {
                    button.removeAttribute('disabled');
                }

                // Fix spinner icons and ensure correct icons
                const icons = button.querySelectorAll('i');
                icons.forEach((icon) => {
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
                    // IMPORTANT: Preserve button name/value before disabling
                    // Disabled buttons don't submit their name/value in POST data
                    if (submitButton.name && submitButton.value) {
                        // Check if hidden input already exists
                        const existingInput = form.querySelector(`input[name="${submitButton.name}"][type="hidden"]`);
                        if (!existingInput) {
                            // Create hidden input to preserve the button's name/value
                            const hiddenInput = document.createElement('input');
                            hiddenInput.type = 'hidden';
                            hiddenInput.name = submitButton.name;
                            hiddenInput.value = submitButton.value;
                            form.appendChild(hiddenInput);
                        }
                    }

                    // Show loading state but DON'T disable until form is actually submitting
                    // Only change visual state, keep button enabled so its value is submitted
                    this.setButtonLoadingStateVisualOnly(submitButton);
                    // Form will submit normally and Django will handle the redirect
                }
            });
        },

        /**
         * Set button loading state (visual only, don't disable)
         * @param {HTMLElement} button - Button element
         */
        setButtonLoadingStateVisualOnly(button) {
            const icon = button.querySelector('i');

            // Store original content
            if (!button.dataset.originalContent) {
                button.dataset.originalContent = button.innerHTML;
            }

            // Set loading state visually but keep button enabled
            if (button.name === 'start_scan') {
                button.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>Starting...';
            } else {
                button.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>Completing...';
            }
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
                    button.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>Starting...';
                } else {
                    button.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>Completing...';
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
         * Setup interactive action cards
         */
        setupActionCards() {
            const actionCards = document.querySelectorAll('.action-card-clickable');

            actionCards.forEach((card) => {
                // Add hover effects
                card.addEventListener('mouseenter', () => {
                    card.classList.add('shadow-sm');
                });

                card.addEventListener('mouseleave', () => {
                    card.classList.remove('shadow-sm');
                });

                // Add click feedback
                card.addEventListener('click', (e) => {
                    // Add brief scale effect
                    card.classList.add('card-press');

                    setTimeout(() => {
                        card.classList.remove('card-press');
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
                    completionIcon.parentElement.classList.add('is-animated');
                }, 500);
            }

            // Animate feature highlights
            const features = document.querySelectorAll('.feature-highlight');
            features.forEach((feature, index) => {
                feature.classList.add('is-entering');

                setTimeout(() => {
                    feature.classList.add('is-visible');
                }, 200 * index);
            });

            // Animate action cards
            const cards = document.querySelectorAll('.action-card');
            cards.forEach((card, index) => {
                card.classList.add('is-entering');

                setTimeout(() => {
                    card.classList.add('is-visible');
                }, 100 * index);
            });
        },
    };

    // Fix buttons immediately (before DOM loaded) to prevent spinning
    function fixButtonsImmediately() {
        const buttons = document.querySelectorAll('.wizard-navigation button');
        buttons.forEach((button) => {
            if (button.hasAttribute('disabled')) {
                button.removeAttribute('disabled');
            }

            const icons = button.querySelectorAll('i.fa-spin, i.fa-spinner');
            icons.forEach((icon) => {
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
