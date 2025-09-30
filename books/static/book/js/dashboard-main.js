/**
 * Dashboard Main - Primary dashboard functionality and navigation
 * Extracted from dashboard.html inline JavaScript
 */

// Dashboard progress bar initialization
function initializeDashboardProgressBars() {
    // Progress bar configurations for different categories
    const progressBarConfigs = [
        { selector: '.progress-bar-ebook', cssProperty: '--ebook-width' },
        { selector: '.progress-bar-comic', cssProperty: '--comic-width' },
        { selector: '.progress-bar-audiobook', cssProperty: '--audiobook-width' },
        { selector: '.progress-bar-series', cssProperty: '--series-width' },
        { selector: '.progress-bar-author', cssProperty: '--author-width' }
    ];

    // Set progress bar widths using CSS custom properties for stat cards
    progressBarConfigs.forEach(config => {
        const bar = document.querySelector(config.selector);
        if (bar) {
            const width = bar.getAttribute('data-width');
            if (width) {
                document.documentElement.style.setProperty(config.cssProperty, width + '%');
            }
        }
    });

    // Set progress bar widths for quality metrics
    const qualityMetrics = [
        { selector: '.progress-bar-confidence', cssProperty: '--confidence-width' },
        { selector: '.progress-bar-completeness', cssProperty: '--completeness-width' }
    ];

    qualityMetrics.forEach(metric => {
        const bar = document.querySelector(metric.selector);
        if (bar) {
            const width = bar.getAttribute('data-width');
            if (width) {
                bar.style.setProperty(metric.cssProperty, width + '%');
            }
        }
    });

    // Set format progress bars
    const formatBars = document.querySelectorAll('.progress-bar-format');
    formatBars.forEach(bar => {
        const width = bar.getAttribute('data-width');
        if (width) {
            bar.style.setProperty('--format-width', width + '%');
        }
    });
}

// Dashboard navigation functions - will be populated with URLs via data attributes
const DashboardNavigation = {
    // Initialize navigation with URL data attributes
    init: function() {
        // Get navigation URLs from data attributes on the dashboard container
        const dashboard = document.querySelector('[data-urls]');
        if (dashboard) {
            try {
                this.urls = JSON.parse(dashboard.dataset.urls);
            } catch (e) {
                console.warn('Could not parse dashboard URLs:', e);
                this.urls = {};
            }
        }
    },

    navigateToBooks: function() {
        if (this.urls.book_list) {
            window.location.href = this.urls.book_list;
        }
    },

    navigateToEbooks: function() {
        if (this.urls.ebooks_main) {
            window.location.href = this.urls.ebooks_main;
        }
    },

    navigateToComics: function() {
        if (this.urls.comics_main) {
            window.location.href = this.urls.comics_main;
        }
    },

    navigateToAudiobooks: function() {
        if (this.urls.audiobooks_main) {
            window.location.href = this.urls.audiobooks_main;
        }
    },

    navigateToSeries: function() {
        if (this.urls.series_main) {
            window.location.href = this.urls.series_main;
        }
    },

    navigateToAuthors: function() {
        if (this.urls.author_list) {
            window.location.href = this.urls.author_list;
        }
    }
};

// Dashboard functionality
const DashboardMain = {
    // Initialize dashboard components
    init: function() {
        this.initializeProgressBars();
        this.initializeNavigation();
        this.initializeRefreshButton();
        this.initializeFilters();
    },

    // Initialize progress bars
    initializeProgressBars: function() {
        initializeDashboardProgressBars();
    },

    // Initialize navigation system
    initializeNavigation: function() {
        DashboardNavigation.init();
        
        // Bind navigation functions to window for onclick handlers
        window.navigateToBooks = () => DashboardNavigation.navigateToBooks();
        window.navigateToEbooks = () => DashboardNavigation.navigateToEbooks();
        window.navigateToComics = () => DashboardNavigation.navigateToComics();
        window.navigateToAudiobooks = () => DashboardNavigation.navigateToAudiobooks();
        window.navigateToSeries = () => DashboardNavigation.navigateToSeries();
        window.navigateToAuthors = () => DashboardNavigation.navigateToAuthors();
    },

    // Initialize refresh button
    initializeRefreshButton: function() {
        const refreshBtn = document.getElementById('refreshDashboard');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', function() {
                location.reload();
            });
        }
    },

    // Initialize filter form handling
    initializeFilters: function() {
        const filterForm = document.getElementById('dashboardFilters');
        if (filterForm) {
            filterForm.addEventListener('submit', function(e) {
                e.preventDefault();
                // In future implementation, update dashboard with filters via AJAX
                console.log('Filters applied:', new FormData(this));
            });
        }
    }
};

// Initialize dashboard when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    DashboardMain.init();
});

// Export for global access
window.DashboardMain = DashboardMain;
window.DashboardNavigation = DashboardNavigation;