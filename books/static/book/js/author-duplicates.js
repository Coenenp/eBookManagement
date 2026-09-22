/**
 * Author Duplicates Management
 * Handles duplicate author detection, threshold adjustment, and merging
 */

class AuthorDuplicatesManager {
    constructor(mergeUrl, csrfToken) {
        this.mergeUrl = mergeUrl;
        this.csrfToken = csrfToken;

        this.initializeEventListeners();
        this.initializeMergeButtons();
    }

    initializeEventListeners() {
        // Threshold slider
        const thresholdSlider = document.getElementById('threshold');
        const thresholdDisplay = document.getElementById('threshold-value');

        if (thresholdSlider && thresholdDisplay) {
            thresholdSlider.addEventListener('input', () => {
                thresholdDisplay.textContent = parseFloat(thresholdSlider.value).toFixed(2);
            });
        }

        // Author selection checkboxes
        document.querySelectorAll('input[name="author_ids[]"]').forEach((checkbox) => {
            checkbox.addEventListener('change', (e) => {
                const form = e.target.closest('form');
                const groupId = form.dataset.groupId;
                this.updateMergeButton(groupId);
            });
        });

        // Merge buttons
        document.querySelectorAll('.merge-button').forEach((button) => {
            button.addEventListener('click', (e) => {
                e.preventDefault();
                const form = e.target.closest('form');
                const groupId = form.dataset.groupId;
                this.mergeAuthors(groupId);
            });
        });
    }

    initializeMergeButtons() {
        // Initialize button states for all groups
        document.querySelectorAll('form[data-group-id]').forEach((form) => {
            const groupId = form.dataset.groupId;
            this.updateMergeButton(groupId);
        });
    }

    updateMergeButton(groupId) {
        const form = document.querySelector(`form[data-group-id="${groupId}"]`);
        if (!form) return;

        const checkedCount = form.querySelectorAll('input[name="author_ids[]"]:checked').length;
        const mergeButton = form.querySelector('.merge-button');

        if (!mergeButton) return;

        mergeButton.disabled = checkedCount < 2;

        if (checkedCount < 2) {
            mergeButton.textContent = ' Select at least 2 authors';
        } else {
            mergeButton.textContent = ` Merge ${checkedCount} Authors`;
        }
    }

    mergeAuthors(groupId) {
        const form = document.querySelector(`form[data-group-id="${groupId}"]`);
        if (!form) return;

        const checkedBoxes = form.querySelectorAll('input[name="author_ids[]"]:checked');
        const primaryRadio = form.querySelector(`input[name="primary_author_${groupId}"]:checked`);

        // Validation
        if (checkedBoxes.length < 2) {
            alert('Please select at least 2 authors to merge');
            return;
        }

        if (!primaryRadio) {
            alert('Please select a primary author (radio button)');
            return;
        }

        // Get author names for confirmation
        const authorNames = Array.from(checkedBoxes).map((cb) => {
            return cb.closest('.author-item').querySelector('.author-name').textContent.trim();
        });

        const primaryName = primaryRadio.closest('.author-item').querySelector('.author-name').textContent.trim();

        // Confirm merge
        if (!confirm(`Merge ${authorNames.length} authors into "${primaryName}"?\n\nThis action cannot be undone.`)) {
            return;
        }

        // Prepare data
        const authorIds = Array.from(checkedBoxes).map((cb) => cb.value);

        // Send merge request
        fetch(this.mergeUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': this.csrfToken,
            },
            body: JSON.stringify({
                author_ids: authorIds,
                primary_author_id: primaryRadio.value,
            }),
        })
            .then((response) => response.json())
            .then((data) => {
                if (data.success) {
                    alert(data.message);
                    // Remove the merged group from display
                    form.closest('.duplicate-group').classList.add('d-none');
                } else {
                    alert('Error: ' + data.error);
                }
            })
            .catch((error) => {
                console.error('Merge error:', error);
                alert('Network error: ' + error.message);
            });
    }
}

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', function () {
    const duplicatesContainer = document.getElementById('authorDuplicatesContainer');
    if (duplicatesContainer) {
        const mergeUrl = duplicatesContainer.dataset.mergeUrl;
        const csrfToken = duplicatesContainer.dataset.csrfToken;

        new AuthorDuplicatesManager(mergeUrl, csrfToken);
    }
});
