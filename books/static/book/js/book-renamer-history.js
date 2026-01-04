/**
 * book-renamer-history.js
 * Handles renamer history functionality including revert operations
 * Extracted from book_renamer_history.html inline script
 */

/**
 * Initialize renamer history functionality
 */
function initializeRenamerHistory() {
    const confirmModal = new bootstrap.Modal(document.getElementById('confirmModal'));
    let currentRevertAction = null;

    // Initialize tooltips
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });

    // Revert batch functionality
    document.querySelectorAll('.revert-batch-btn').forEach((btn) => {
        btn.addEventListener('click', function () {
            const batchId = this.dataset.batchId;
            document.getElementById('confirmMessage').textContent =
                'Are you sure you want to revert all operations in this batch? This will move all files back to their original locations.';

            currentRevertAction = {
                type: 'batch',
                batchId: batchId,
                button: this,
            };

            confirmModal.show();
        });
    });

    // Revert single operation functionality
    document.querySelectorAll('.revert-single-btn').forEach((btn) => {
        btn.addEventListener('click', function () {
            const operationId = this.dataset.operationId;
            document.getElementById('confirmMessage').textContent =
                'Are you sure you want to revert this operation? This will move the file back to its original location.';

            currentRevertAction = {
                type: 'single',
                operationId: operationId,
                button: this,
            };

            confirmModal.show();
        });
    });

    // Confirm revert button
    document.getElementById('confirmRevertBtn').addEventListener('click', function () {
        if (!currentRevertAction) return;

        confirmModal.hide();

        const formData = new FormData();
        formData.append('csrfmiddlewaretoken', document.querySelector('[name=csrfmiddlewaretoken]').value);

        if (currentRevertAction.type === 'batch') {
            formData.append('batch_id', currentRevertAction.batchId);
        } else {
            formData.append('operation_ids', currentRevertAction.operationId);
        }

        // Disable button and show progress
        currentRevertAction.button.disabled = true;
        currentRevertAction.button.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';

        // Get revert URL from current page context
        const revertUrl =
            currentRevertAction.button.closest('form')?.action ||
            document.querySelector('[data-revert-url]')?.dataset.revertUrl ||
            '/books/renamer/revert/';

        fetch(revertUrl, {
            method: 'POST',
            body: formData,
        })
            .then((response) => response.json())
            .then((data) => {
                if (data.errors.length === 0) {
                    alert(`Successfully reverted ${data.success.length} operation(s).`);
                    window.location.reload();
                } else {
                    alert(
                        `Revert completed with ${data.success.length} successes and ${data.errors.length} errors. Check console for details.`
                    );
                    console.log('Revert errors:', data.errors);
                    window.location.reload();
                }
            })
            .catch((error) => {
                alert('Error reverting operation: ' + error);
                currentRevertAction.button.disabled = false;
                currentRevertAction.button.innerHTML = '<i class="fas fa-undo"></i>';
            });

        currentRevertAction = null;
    });
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', initializeRenamerHistory);
