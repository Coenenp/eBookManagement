// Add to script.js - CSP-safe image error handling
console.log("Ebook Library Manager: script.js loaded");

document.addEventListener('DOMContentLoaded', function () {
    // Initialize Bootstrap tooltips
    var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    var tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });

    // Handle image load errors for book covers
    const bookCovers = document.querySelectorAll('.cover-img');
    bookCovers.forEach(function(img) {
        // Add loaded class when image loads successfully
        img.addEventListener('load', function() {
            this.classList.add('loaded');
        });
        
        // Improved error handling with proper fallback creation
        img.addEventListener('error', function() {
            const coverSize = Array.from(this.classList).find(cls => cls.startsWith('cover-')) || 'cover-medium';
            
            // Create fallback element with proper sizing
            const fallback = document.createElement('div');
            fallback.className = `bg-secondary text-white rounded shadow-sm d-flex align-items-center justify-content-center cover-placeholder ${coverSize}`;
            fallback.innerHTML = '<div class="text-center"><i class="fas fa-book fa-2x mb-2"></i><div class="small">Cover Error</div></div>';
            
            // Replace image with fallback
            if (this.parentNode) {
                this.parentNode.replaceChild(fallback, this);
            }
        });
    });

    // Add loading states for forms
    const forms = document.querySelectorAll('form');
    forms.forEach(function(form) {
        form.addEventListener('submit', function() {
            const submitBtn = form.querySelector('button[type="submit"]');
            if (submitBtn) {
                submitBtn.disabled = true;
                submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i>' + submitBtn.textContent;
            }
        });
    });
});