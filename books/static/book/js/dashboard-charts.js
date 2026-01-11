/**
 * Dashboard Charts Initialization
 * Handles Chart.js initialization for the dashboard page
 */

/**
 * Get computed Bootstrap color from CSS variables
 */
function getBootstrapColor(variableName, opacity = 0.8) {
    const color = getComputedStyle(document.documentElement).getPropertyValue(variableName).trim();
    // If it's already an rgb/rgba, parse and add opacity
    if (color.startsWith('rgb')) {
        const match = color.match(/\d+/g);
        if (match && match.length >= 3) {
            return `rgba(${match[0]}, ${match[1]}, ${match[2]}, ${opacity})`;
        }
    }
    // If it's a hex color, convert to rgba
    if (color.startsWith('#')) {
        const hex = color.replace('#', '');
        const r = parseInt(hex.substr(0, 2), 16);
        const g = parseInt(hex.substr(2, 2), 16);
        const b = parseInt(hex.substr(4, 2), 16);
        return `rgba(${r}, ${g}, ${b}, ${opacity})`;
    }
    // Fallback
    return color;
}

// Bootstrap-themed color palette using CSS variables
const BOOTSTRAP_COLORS = [
    () => getBootstrapColor('--bs-primary', 0.8),
    () => getBootstrapColor('--bs-success', 0.8),
    () => getBootstrapColor('--bs-danger', 0.8),
    () => getBootstrapColor('--bs-warning', 0.8),
    () => getBootstrapColor('--bs-info', 0.8),
    () => getBootstrapColor('--bs-purple', 0.8),
    () => getBootstrapColor('--bs-pink', 0.8),
    () => getBootstrapColor('--bs-orange', 0.8),
    () => getBootstrapColor('--bs-teal', 0.8),
    () => getBootstrapColor('--bs-indigo', 0.8),
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

    // Generate vibrant colors for each format using Bootstrap theme colors
    const colors = chartData.format_labels.map((_, index) => BOOTSTRAP_COLORS[index % BOOTSTRAP_COLORS.length]());

    // Get border color from body background
    const borderColor = getComputedStyle(document.documentElement).getPropertyValue('--bs-body-bg').trim() || 'white';

    new Chart(formatCtx, {
        type: 'pie',
        data: {
            labels: chartData.format_labels,
            datasets: [
                {
                    data: chartData.format_data,
                    backgroundColor: colors,
                    borderWidth: 2,
                    borderColor: borderColor,
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

    // Use Bootstrap theme colors for the chart
    const successColor = getBootstrapColor('--bs-success', 0.8);
    const warningColor = getBootstrapColor('--bs-warning', 0.8);
    const dangerColor = getBootstrapColor('--bs-danger', 0.8);
    const successBorder = getBootstrapColor('--bs-success', 1);
    const warningBorder = getBootstrapColor('--bs-warning', 1);
    const dangerBorder = getBootstrapColor('--bs-danger', 1);

    new Chart(metadataCtx, {
        type: 'bar',
        data: {
            labels: chartData.completeness_labels,
            datasets: [
                {
                    label: 'Books',
                    data: chartData.completeness_data,
                    backgroundColor: [successColor, warningColor, dangerColor],
                    borderColor: [successBorder, warningBorder, dangerBorder],
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
