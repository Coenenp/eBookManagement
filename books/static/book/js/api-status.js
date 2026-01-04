/**
 * api-status.js
 * Handles API status page functionality including retry operations
 * Extracted from api_status.html inline script
 */

/**
 * Retry metadata lookup for a single book
 * @param {number} bookId - Book ID to retry
 */
function retryBook(bookId) {
    const modal = new bootstrap.Modal(document.getElementById('retryModal'));
    modal.show();

    fetch(`/books/api-status/retry/${bookId}/`, {
        method: 'POST',
        headers: {
            'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value,
            'Content-Type': 'application/json',
        },
    })
        .then((response) => response.json())
        .then((data) => {
            document.getElementById('retryStatus').textContent = data.message;
            document.getElementById('retryProgress').style.width = '100%';

            setTimeout(() => {
                modal.hide();
                location.reload();
            }, 1500);
        })
        .catch((error) => {
            document.getElementById('retryStatus').textContent = 'Error: ' + error;
            document.getElementById('retryProgress').classList.add('bg-danger');
        });
}

/**
 * Retry all high priority books
 */
function retryAllHigh() {
    if (!confirm('Retry all high priority books? This may take a while.')) {
        return;
    }

    const modal = new bootstrap.Modal(document.getElementById('retryModal'));
    modal.show();

    fetch('/books/api-status/retry-all/high/', {
        method: 'POST',
        headers: {
            'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value,
            'Content-Type': 'application/json',
        },
    })
        .then((response) => response.json())
        .then((data) => {
            document.getElementById('retryStatus').textContent = data.message;
            document.getElementById('retryProgress').style.width = '100%';

            setTimeout(() => {
                modal.hide();
                location.reload();
            }, 2000);
        })
        .catch((error) => {
            document.getElementById('retryStatus').textContent = 'Error: ' + error;
            document.getElementById('retryProgress').classList.add('bg-danger');
        });
}

/**
 * Refresh the status page
 */
function refreshStatus() {
    location.reload();
}

// Export functions for template use
window.retryBook = retryBook;
window.retryAllHigh = retryAllHigh;
window.refreshStatus = refreshStatus;
