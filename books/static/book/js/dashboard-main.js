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
        { selector: '.progress-bar-author', cssProperty: '--author-width' },
    ];

    // Set progress bar widths using CSS custom properties for stat cards
    progressBarConfigs.forEach((config) => {
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
        { selector: '.progress-bar-completeness', cssProperty: '--completeness-width' },
    ];

    qualityMetrics.forEach((metric) => {
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
    formatBars.forEach((bar) => {
        const width = bar.getAttribute('data-width');
        if (width) {
            bar.style.setProperty('--format-width', width + '%');
        }
    });

    // Set dynamic progress bars (used for quality metrics and other dynamic content)
    const dynamicBars = document.querySelectorAll('.progress-bar-dynamic');
    dynamicBars.forEach((bar) => {
        const width = bar.getAttribute('data-width');
        if (width) {
            bar.style.setProperty('--progress-width', width);
        }
    });
}

// Dashboard navigation functions - will be populated with URLs via data attributes
const DashboardNavigation = {
    // Initialize navigation with URL data attributes
    init: function () {
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

    navigateToBooks: function () {
        if (this.urls.book_list) {
            window.location.href = this.urls.book_list;
        }
    },

    navigateToEbooks: function () {
        if (this.urls.ebooks_main) {
            window.location.href = this.urls.ebooks_main;
        }
    },

    navigateToComics: function () {
        if (this.urls.comics_main) {
            window.location.href = this.urls.comics_main;
        }
    },

    navigateToAudiobooks: function () {
        if (this.urls.audiobooks_main) {
            window.location.href = this.urls.audiobooks_main;
        }
    },

    navigateToSeries: function () {
        if (this.urls.series_main) {
            window.location.href = this.urls.series_main;
        }
    },

    navigateToAuthors: function () {
        if (this.urls.author_list) {
            window.location.href = this.urls.author_list;
        }
    },

    // Handle navigation based on data attribute
    handleNavigation: function (navType) {
        switch (navType) {
            case 'books':
                this.navigateToBooks();
                break;
            case 'ebooks':
                this.navigateToEbooks();
                break;
            case 'comics':
                this.navigateToComics();
                break;
            case 'audiobooks':
                this.navigateToAudiobooks();
                break;
            case 'series':
                this.navigateToSeries();
                break;
            case 'authors':
                this.navigateToAuthors();
                break;
            default:
                console.warn('Unknown navigation type:', navType);
        }
    },
};

// Dashboard functionality
const DashboardMain = {
    // Initialize dashboard components
    init: function () {
        this.initializeProgressBars();
        this.initializeNavigation();
        this.initializeRefreshButton();
        this.initializeFilters();
    },

    // Initialize progress bars
    initializeProgressBars: function () {
        initializeDashboardProgressBars();
    },

    // Initialize navigation system
    initializeNavigation: function () {
        DashboardNavigation.init();

        // Set up event delegation for navigation cards
        document.addEventListener('click', function (e) {
            const navCard = e.target.closest('.nav-card');
            if (navCard) {
                const navType = navCard.getAttribute('data-nav');
                DashboardNavigation.handleNavigation(navType);
            }
        });

        // Set up keyboard navigation for nav cards
        document.addEventListener('keydown', function (e) {
            const navCard = e.target.closest('.nav-card');
            if (navCard && (e.key === 'Enter' || e.key === ' ')) {
                e.preventDefault();
                const navType = navCard.getAttribute('data-nav');
                DashboardNavigation.handleNavigation(navType);
            }
        });

        // Bind navigation functions to window for legacy onclick handlers (if any remain)
        window.navigateToBooks = () => DashboardNavigation.navigateToBooks();
        window.navigateToEbooks = () => DashboardNavigation.navigateToEbooks();
        window.navigateToComics = () => DashboardNavigation.navigateToComics();
        window.navigateToAudiobooks = () => DashboardNavigation.navigateToAudiobooks();
        window.navigateToSeries = () => DashboardNavigation.navigateToSeries();
        window.navigateToAuthors = () => DashboardNavigation.navigateToAuthors();
    },

    // Initialize refresh button
    initializeRefreshButton: function () {
        const refreshBtn = document.getElementById('refreshDashboard');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', function () {
                location.reload();
            });
        }
    },

    // Initialize filter form handling
    initializeFilters: function () {
        const filterForm = document.getElementById('dashboardFilters');
        if (filterForm) {
            filterForm.addEventListener('submit', function (e) {
                e.preventDefault();

                // Get form data
                const formData = new FormData(this);
                const contentType = formData.get('content_type');
                const reviewStatus = formData.get('review_status');

                // Build URL with query parameters
                const params = new URLSearchParams();
                if (contentType) params.append('content_type', contentType);
                if (reviewStatus) params.append('review_status', reviewStatus);

                // Reload dashboard with filters
                const baseUrl = window.location.pathname;
                const queryString = params.toString();
                window.location.href = queryString ? `${baseUrl}?${queryString}` : baseUrl;
            });
        }
    },
};

// Initialize dashboard when DOM is loaded
document.addEventListener('DOMContentLoaded', function () {
    DashboardMain.init();
});

// Export for global access
window.DashboardMain = DashboardMain;
window.DashboardNavigation = DashboardNavigation;
