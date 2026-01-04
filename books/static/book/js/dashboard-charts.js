/**
 * Dashboard Charts Initialization
 * Handles Chart.js initialization for the dashboard page
 */

// Bootstrap-themed color palette (vibrant and varied)
const BOOTSTRAP_COLORS = [
    'rgba(13, 110, 253, 0.8)', // Primary Blue
    'rgba(25, 135, 84, 0.8)', // Success Green
    'rgba(220, 53, 69, 0.8)', // Danger Red
    'rgba(255, 193, 7, 0.8)', // Warning Yellow
    'rgba(13, 202, 240, 0.8)', // Info Cyan
    'rgba(111, 66, 193, 0.8)', // Purple
    'rgba(214, 51, 132, 0.8)', // Pink
    'rgba(253, 126, 20, 0.8)', // Orange
    'rgba(32, 201, 151, 0.8)', // Teal
    'rgba(102, 16, 242, 0.8)', // Indigo
];

/**
 * Initialize navigation URLs
 */
function initializeNavigationUrls(urls) {
    const dashboard = document.body;
    dashboard.setAttribute('data-urls', JSON.stringify(urls));
}

/**
 * Initialize Format Distribution Pie Chart
 */
function initializeFormatChart(chartData) {
    if (!chartData || !chartData.format_labels || !document.getElementById('formatChart')) {
        return;
    }

    const formatCtx = document.getElementById('formatChart').getContext('2d');

    // Generate vibrant colors for each format
    const colors = chartData.format_labels.map((_, index) => BOOTSTRAP_COLORS[index % BOOTSTRAP_COLORS.length]);

    new Chart(formatCtx, {
        type: 'pie',
        data: {
            labels: chartData.format_labels,
            datasets: [
                {
                    data: chartData.format_data,
                    backgroundColor: colors,
                    borderWidth: 2,
                    borderColor: '#fff',
                    hoverOffset: 10,
                },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: {
                        padding: 15,
                        font: { size: 12 },
                        usePointStyle: true,
                        pointStyle: 'circle',
                    },
                },
                tooltip: {
                    callbacks: {
                        label: function (context) {
                            const label = context.label || '';
                            const value = context.parsed || 0;
                            const total = context.dataset.data.reduce((a, b) => a + b, 0);
                            const percentage = ((value / total) * 100).toFixed(1);
                            return label + ': ' + value + ' (' + percentage + '%)';
                        },
                    },
                },
            },
        },
    });
}

/**
 * Initialize Metadata Completeness Bar Chart
 */
function initializeMetadataChart(chartData) {
    if (!chartData || !chartData.completeness_labels || !document.getElementById('metadataChart')) {
        return;
    }

    const metadataCtx = document.getElementById('metadataChart').getContext('2d');
    new Chart(metadataCtx, {
        type: 'bar',
        data: {
            labels: chartData.completeness_labels,
            datasets: [
                {
                    label: 'Books',
                    data: chartData.completeness_data,
                    backgroundColor: [
                        'rgba(40, 167, 69, 0.8)', // Complete - green
                        'rgba(255, 193, 7, 0.8)', // Partial - yellow
                        'rgba(220, 53, 69, 0.8)', // Missing - red
                    ],
                    borderColor: ['rgba(40, 167, 69, 1)', 'rgba(255, 193, 7, 1)', 'rgba(220, 53, 69, 1)'],
                    borderWidth: 2,
                },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: {
                        stepSize: 1,
                    },
                },
            },
            plugins: {
                legend: {
                    display: false,
                },
                tooltip: {
                    callbacks: {
                        label: function (context) {
                            const value = context.parsed.y || 0;
                            const total = context.dataset.data.reduce((a, b) => a + b, 0);
                            const percentage = total > 0 ? ((value / total) * 100).toFixed(1) : 0;
                            return 'Books: ' + value + ' (' + percentage + '%)';
                        },
                    },
                },
            },
        },
    });
}

/**
 * Initialize all dashboard charts
 * This is the main entry point called from the template
 */
function initializeDashboardCharts(chartData, navigationUrls) {
    initializeNavigationUrls(navigationUrls);
    initializeFormatChart(chartData);
    initializeMetadataChart(chartData);
}

// Export for use in template
window.initializeDashboardCharts = initializeDashboardCharts;
