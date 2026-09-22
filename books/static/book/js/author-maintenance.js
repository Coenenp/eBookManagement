/**
 * Author Library Maintenance
 * Handles the author cleanup operations exposed in Settings -> Library
 * Maintenance: clean names, merge duplicates, and remove invalid authors.
 * Supports a dry-run preview before applying changes.
 */
class AuthorMaintenanceManager {
    constructor(cleanUrl, csrfToken) {
        this.cleanUrl = cleanUrl;
        this.csrfToken = csrfToken;

        this.cleanNamesCheckbox = document.getElementById('maint-clean-names');
        this.mergeDuplicatesCheckbox = document.getElementById('maint-merge-duplicates');
        this.removeInvalidCheckbox = document.getElementById('maint-remove-invalid');
        this.previewBtn = document.getElementById('maint-preview-btn');
        this.applyBtn = document.getElementById('maint-apply-btn');
        this.resultEl = document.getElementById('maint-result');

        if (
            !this.cleanNamesCheckbox ||
            !this.mergeDuplicatesCheckbox ||
            !this.removeInvalidCheckbox ||
            !this.previewBtn ||
            !this.applyBtn ||
            !this.resultEl
        ) {
            return;
        }

        this.initializeEventListeners();
    }

    initializeEventListeners() {
        [this.cleanNamesCheckbox, this.mergeDuplicatesCheckbox, this.removeInvalidCheckbox].forEach((checkbox) => {
            checkbox.addEventListener('change', () => this.updateApplyButton());
        });

        this.previewBtn.addEventListener('click', () => this.runMaintenance(true));
        this.applyBtn.addEventListener('click', () => this.runMaintenance(false));
    }

    selectedOperations() {
        return {
            clean_names: this.cleanNamesCheckbox.checked,
            merge_duplicates: this.mergeDuplicatesCheckbox.checked,
            remove_invalid: this.removeInvalidCheckbox.checked,
        };
    }

    anySelected() {
        const ops = this.selectedOperations();
        return ops.clean_names || ops.merge_duplicates || ops.remove_invalid;
    }

    updateApplyButton() {
        this.applyBtn.disabled = !this.anySelected();
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    showResult(type, message) {
        this.resultEl.innerHTML = `<div class="alert alert-${type}">${this.escapeHtml(message)}</div>`;
        this.resultEl.classList.remove('d-none');
    }

    renderStats(data) {
        const stats = data.stats;
        const dryRun = data.dry_run;
        let html = `<div class="alert alert-${dryRun ? 'info' : 'success'}">`;
        html += `<strong>${dryRun ? 'Preview' : 'Completed'}:</strong> `;
        html += `Invalid authors deactivated: ${stats.invalid_removed} · `;
        html += `Names cleaned: ${stats.names_cleaned} · `;
        html += `Duplicates merged: ${stats.duplicates_merged}`;
        if (dryRun) {
            html +=
                '<br><small class="text-muted">No changes were applied. Click "Apply Changes" to run these operations for real.</small>';
        }
        html += '</div>';

        if (stats.invalid_authors && stats.invalid_authors.length) {
            html += '<div class="mb-2"><strong>Invalid authors:</strong><ul class="small mb-1">';
            stats.invalid_authors.slice(0, 50).forEach((author) => {
                html += `<li>${this.escapeHtml(author.name)} (${author.book_count} books)</li>`;
            });
            if (stats.invalid_authors.length > 50) {
                html += `<li>…and ${stats.invalid_authors.length - 50} more</li>`;
            }
            html += '</ul></div>';
        }

        if (stats.cleaned_names && stats.cleaned_names.length) {
            html += '<div class="mb-2"><strong>Names to clean:</strong><ul class="small mb-1">';
            stats.cleaned_names.slice(0, 50).forEach((entry) => {
                html += `<li>${this.escapeHtml(entry.before)} -> ${this.escapeHtml(entry.after)}</li>`;
            });
            if (stats.cleaned_names.length > 50) {
                html += `<li>…and ${stats.cleaned_names.length - 50} more</li>`;
            }
            html += '</ul></div>';
        }

        if (stats.merged_groups && stats.merged_groups.length) {
            html += '<div class="mb-2"><strong>Duplicate groups to merge:</strong><ul class="small mb-1">';
            stats.merged_groups.slice(0, 50).forEach((group) => {
                const dupNames = group.duplicates.map((d) => this.escapeHtml(d.name)).join(', ');
                html += `<li>Keep <em>${this.escapeHtml(group.primary.name)}</em>; merge: ${dupNames}</li>`;
            });
            if (stats.merged_groups.length > 50) {
                html += `<li>…and ${stats.merged_groups.length - 50} more</li>`;
            }
            html += '</ul></div>';
        }

        if (!stats.invalid_authors.length && !stats.cleaned_names.length && !stats.merged_groups.length) {
            html += '<div class="text-muted small">Nothing to change for the selected operations.</div>';
        }

        this.resultEl.innerHTML = html;
        this.resultEl.classList.remove('d-none');
    }

    runMaintenance(dryRun) {
        const ops = this.selectedOperations();
        if (!this.anySelected()) {
            this.showResult('warning', 'Select at least one operation to run.');
            return;
        }

        const body = new URLSearchParams();
        body.set('dry_run', dryRun ? 'true' : 'false');
        body.set('clean_names', ops.clean_names ? 'true' : 'false');
        body.set('merge_duplicates', ops.merge_duplicates ? 'true' : 'false');
        body.set('remove_invalid', ops.remove_invalid ? 'true' : 'false');

        this.previewBtn.disabled = true;
        this.applyBtn.disabled = true;

        fetch(this.cleanUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
                'X-CSRFToken': this.csrfToken,
                'X-Requested-With': 'XMLHttpRequest',
            },
            body: body.toString(),
        })
            .then((response) => response.json())
            .then((data) => {
                if (data.success) {
                    this.renderStats(data);
                } else {
                    this.showResult('danger', data.error || 'An error occurred.');
                }
            })
            .catch(() => {
                this.showResult('danger', 'Request failed. Please try again.');
            })
            .finally(() => {
                this.previewBtn.disabled = false;
                this.updateApplyButton();
            });
    }
}

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', function () {
    const container = document.getElementById('authorMaintenanceContainer');
    if (container) {
        const cleanUrl = container.dataset.authorCleanUrl;
        const csrfToken = container.dataset.csrfToken;

        new AuthorMaintenanceManager(cleanUrl, csrfToken);
    }
});
