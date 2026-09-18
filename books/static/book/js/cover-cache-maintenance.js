/**
 * Cover Cache Library Maintenance
 * Handles orphaned-cover cleanup in Settings -> Library Maintenance.
 */
class CoverCacheMaintenanceManager {
    constructor(cleanUrl, csrfToken) {
        this.cleanUrl = cleanUrl;
        this.csrfToken = csrfToken;

        this.container = document.getElementById('coverCacheContainer');
        this.cleanBtn = document.getElementById('cover-cache-clean-btn');
        this.fileCountEl = document.getElementById('cover-cache-file-count');
        this.totalSizeEl = document.getElementById('cover-cache-total-size');
        this.orphanCountEl = document.getElementById('cover-cache-orphan-count');
        this.resultEl = document.getElementById('cover-cache-result');

        if (!this.container || !this.cleanBtn || !this.resultEl) {
            return;
        }

        this.initializeEventListeners();
    }

    initializeEventListeners() {
        this.cleanBtn.addEventListener('click', () => this.runCleanup());
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = String(text);
        return div.innerHTML;
    }

    formatSize(bytes) {
        bytes = Number(bytes) || 0;
        if (bytes === 0) {
            return '0 B';
        }

        const units = ['B', 'KB', 'MB', 'GB', 'TB'];
        let value = bytes;
        let index = 0;
        while (value >= 1024 && index < units.length - 1) {
            value /= 1024;
            index += 1;
        }

        return `${value.toFixed(1)} ${units[index]}`;
    }

    showResult(type, message) {
        this.resultEl.innerHTML = `<div class="alert alert-${type}">${this.escapeHtml(message)}</div>`;
        this.resultEl.style.display = 'block';
    }

    updateStats(data) {
        if (this.fileCountEl) {
            this.fileCountEl.textContent = data.file_count;
        }
        if (this.totalSizeEl) {
            this.totalSizeEl.textContent = this.formatSize(data.total_size);
        }
        if (this.orphanCountEl) {
            this.orphanCountEl.textContent = data.orphan_count ?? 0;
        }
    }

    runCleanup() {
        this.cleanBtn.disabled = true;

        fetch(this.cleanUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
                'X-CSRFToken': this.csrfToken,
                'X-Requested-With': 'XMLHttpRequest',
            },
            body: '',
        })
            .then((response) => response.json())
            .then((data) => {
                if (data.success) {
                    const orphanCount = data.orphan_count ?? 0;
                    this.updateStats(data);
                    this.showResult(
                        'success',
                        `Deleted ${data.deleted} orphaned covers${data.errors ? ` · ${data.errors} errors` : ''}.`
                    );
                    this.cleanBtn.disabled = orphanCount === 0;
                } else {
                    this.showResult('danger', data.error || 'An error occurred.');
                    this.cleanBtn.disabled = false;
                }
            })
            .catch(() => {
                this.showResult('danger', 'Request failed. Please try again.');
                this.cleanBtn.disabled = false;
            });
    }
}

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', function () {
    const container = document.getElementById('coverCacheContainer');
    if (container) {
        const cleanUrl = container.dataset.cleanUrl;
        const csrfToken = container.dataset.csrfToken;

        new CoverCacheMaintenanceManager(cleanUrl, csrfToken);
    }
});
