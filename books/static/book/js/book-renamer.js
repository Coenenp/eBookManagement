/**
 * Book Renamer - Interactive renaming functionality
 * Extracted from book_renamer.html inline JavaScript
 */

class BookRenamer {
    constructor() {
        this.selectAllBtn = document.getElementById('selectAllBtn');
        this.selectNoneBtn = document.getElementById('selectNoneBtn');
        this.selectCompleteSeriesBtn = document.getElementById('selectCompleteSeriesBtn');
        this.selectAllCheckbox = document.getElementById('selectAllCheckbox');
        this.previewBtn = document.getElementById('previewBtn');
        this.executeBtn = document.getElementById('executeBtn');
        this.interactiveRenameBtn = document.getElementById('interactiveRenameBtn');
        this.bookCheckboxes = document.querySelectorAll('.book-checkbox');
        
        // Bootstrap modals
        this.previewModal = new bootstrap.Modal(document.getElementById('previewModal'));
        this.progressModal = new bootstrap.Modal(document.getElementById('progressModal'));
        this.interactiveModal = new bootstrap.Modal(document.getElementById('interactiveRenameModal'));
        
        // Interactive rename state
        this.renameQueue = [];
        this.currentBookIndex = 0;
        this.processedBooks = {
            success: [],
            errors: [],
            skipped: []
        };
        
        this.init();
    }

    init() {
        this.bindEvents();
        this.updateButtonStates();
    }

    bindEvents() {
        // Select All functionality
        this.selectAllBtn?.addEventListener('click', () => this.selectAll());
        
        // Select None functionality
        this.selectNoneBtn?.addEventListener('click', () => this.selectNone());
        
        // Select Complete Series functionality
        this.selectCompleteSeriesBtn?.addEventListener('click', () => this.selectCompleteSeries());
        
        // Master checkbox functionality
        this.selectAllCheckbox?.addEventListener('change', (e) => this.toggleAllCheckboxes(e.target.checked));
        
        // Individual checkbox changes
        this.bookCheckboxes.forEach(checkbox => {
            checkbox.addEventListener('change', () => this.updateButtonStates());
        });
        
        // Preview functionality
        this.previewBtn?.addEventListener('click', () => this.previewRenames());
        
        // Execute functionality
        this.executeBtn?.addEventListener('click', () => this.executeRenames());
        
        // Interactive rename functionality
        this.interactiveRenameBtn?.addEventListener('click', () => this.startInteractiveRename());
    }

    selectAll() {
        this.bookCheckboxes.forEach(checkbox => checkbox.checked = true);
        this.selectAllCheckbox.checked = true;
        this.updateButtonStates();
    }

    selectNone() {
        this.bookCheckboxes.forEach(checkbox => checkbox.checked = false);
        this.selectAllCheckbox.checked = false;
        this.updateButtonStates();
    }

    selectCompleteSeries() {
        this.bookCheckboxes.forEach(checkbox => {
            if (checkbox.dataset.completeSeries === 'true') {
                checkbox.checked = true;
            }
        });
        this.updateMasterCheckbox();
        this.updateButtonStates();
    }

    toggleAllCheckboxes(checked) {
        this.bookCheckboxes.forEach(checkbox => checkbox.checked = checked);
        this.updateButtonStates();
    }

    updateMasterCheckbox() {
        const selectedCount = document.querySelectorAll('.book-checkbox:checked').length;
        const totalCount = this.bookCheckboxes.length;
        
        if (selectedCount === 0) {
            this.selectAllCheckbox.checked = false;
            this.selectAllCheckbox.indeterminate = false;
        } else if (selectedCount === totalCount) {
            this.selectAllCheckbox.checked = true;
            this.selectAllCheckbox.indeterminate = false;
        } else {
            this.selectAllCheckbox.checked = false;
            this.selectAllCheckbox.indeterminate = true;
        }
    }

    updateButtonStates() {
        const selectedCount = document.querySelectorAll('.book-checkbox:checked').length;
        
        this.previewBtn.disabled = selectedCount === 0;
        this.executeBtn.disabled = selectedCount === 0;
        this.interactiveRenameBtn.disabled = selectedCount === 0;
        
        this.updateMasterCheckbox();
    }

    getSelectedBooks() {
        return Array.from(document.querySelectorAll('.book-checkbox:checked'))
                   .map(checkbox => ({
                       id: checkbox.value,
                       title: checkbox.dataset.title,
                       currentFilename: checkbox.dataset.currentFilename,
                       suggestedFilename: checkbox.dataset.suggestedFilename
                   }));
    }

    async previewRenames() {
        const selectedBooks = this.getSelectedBooks();
        
        if (selectedBooks.length === 0) {
            EbookLibrary.UI.showAlert('Please select at least one book to preview.', 'warning');
            return;
        }

        // Show loading state
        const originalText = this.previewBtn.textContent;
        this.previewBtn.textContent = 'Generating Preview...';
        this.previewBtn.disabled = true;

        try {
            const response = await fetch('/books/renamer/preview/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': EbookLibrary.Ajax.getCSRFToken()
                },
                body: JSON.stringify({
                    book_ids: selectedBooks.map(book => book.id)
                })
            });

            const data = await response.json();
            
            if (data.status === 'success') {
                this.displayPreview(data.previews);
                this.previewModal.show();
            } else {
                EbookLibrary.UI.showAlert(data.message || 'Failed to generate preview', 'danger');
            }
        } catch (error) {
            EbookLibrary.UI.showAlert('Network error occurred', 'danger');
        } finally {
            this.previewBtn.textContent = originalText;
            this.previewBtn.disabled = false;
        }
    }

    displayPreview(previews) {
        const previewContainer = document.getElementById('previewContainer');
        if (!previewContainer) return;

        previewContainer.innerHTML = previews.map(preview => `
            <div class="card mb-3">
                <div class="card-body">
                    <h6 class="card-title">${EbookLibrary.Utils.escapeHtml(preview.title)}</h6>
                    <div class="row">
                        <div class="col-sm-6">
                            <strong>Current:</strong><br>
                            <code class="text-muted">${EbookLibrary.Utils.escapeHtml(preview.current_name)}</code>
                        </div>
                        <div class="col-sm-6">
                            <strong>Suggested:</strong><br>
                            <code class="text-success">${EbookLibrary.Utils.escapeHtml(preview.suggested_name)}</code>
                        </div>
                    </div>
                    ${preview.conflicts ? `
                        <div class="alert alert-warning mt-2 mb-0">
                            <i class="fas fa-exclamation-triangle me-2"></i>
                            ${preview.conflicts.join(', ')}
                        </div>
                    ` : ''}
                </div>
            </div>
        `).join('');
    }

    async executeRenames() {
        const selectedBooks = this.getSelectedBooks();
        
        if (selectedBooks.length === 0) {
            EbookLibrary.UI.showAlert('Please select at least one book to rename.', 'warning');
            return;
        }

        if (!confirm(`Are you sure you want to rename ${selectedBooks.length} book(s)?`)) {
            return;
        }

        // Show progress modal
        this.showProgressModal('Renaming Books', 'Initializing...');

        try {
            const response = await fetch('/books/renamer/execute/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': EbookLibrary.Ajax.getCSRFToken()
                },
                body: JSON.stringify({
                    book_ids: selectedBooks.map(book => book.id)
                })
            });

            const data = await response.json();
            
            if (data.status === 'success') {
                this.handleExecutionResults(data);
            } else {
                this.hideProgressModal();
                EbookLibrary.UI.showAlert(data.message || 'Failed to execute renames', 'danger');
            }
        } catch (error) {
            this.hideProgressModal();
            EbookLibrary.UI.showAlert('Network error occurred', 'danger');
        }
    }

    startInteractiveRename() {
        const selectedBooks = this.getSelectedBooks();
        
        if (selectedBooks.length === 0) {
            EbookLibrary.UI.showAlert('Please select at least one book for interactive rename.', 'warning');
            return;
        }

        this.renameQueue = selectedBooks;
        this.currentBookIndex = 0;
        this.processedBooks = {
            success: [],
            errors: [],
            skipped: []
        };

        this.showNextBookForRename();
        this.interactiveModal.show();
    }

    showNextBookForRename() {
        if (this.currentBookIndex >= this.renameQueue.length) {
            this.finishInteractiveRename();
            return;
        }

        const book = this.renameQueue[this.currentBookIndex];
        this.displayInteractiveRenameForm(book);
    }

    displayInteractiveRenameForm(book) {
        const container = document.getElementById('interactiveRenameContainer');
        if (!container) return;

        container.innerHTML = `
            <div class="mb-3">
                <strong>Book ${this.currentBookIndex + 1} of ${this.renameQueue.length}</strong>
                <div class="progress mt-2">
                    <div class="progress-bar" style="width: ${((this.currentBookIndex) / this.renameQueue.length) * 100}%"></div>
                </div>
            </div>
            
            <div class="card">
                <div class="card-body">
                    <h6 class="card-title">${EbookLibrary.Utils.escapeHtml(book.title)}</h6>
                    
                    <div class="mb-3">
                        <label class="form-label">Current Filename:</label>
                        <div class="form-control-plaintext bg-light p-2 rounded">
                            <code>${EbookLibrary.Utils.escapeHtml(book.currentFilename)}</code>
                        </div>
                    </div>
                    
                    <div class="mb-3">
                        <label for="newFilename" class="form-label">New Filename:</label>
                        <input type="text" class="form-control" id="newFilename" 
                               value="${EbookLibrary.Utils.escapeHtml(book.suggestedFilename)}">
                        <div class="form-text">You can edit the suggested filename before applying.</div>
                    </div>
                    
                    <div class="d-flex gap-2 justify-content-end">
                        <button type="button" class="btn btn-outline-secondary" onclick="bookRenamer.skipCurrentBook()">
                            <i class="fas fa-forward me-1"></i>Skip
                        </button>
                        <button type="button" class="btn btn-success" onclick="bookRenamer.renameCurrentBook()">
                            <i class="fas fa-check me-1"></i>Rename
                        </button>
                    </div>
                </div>
            </div>
        `;
    }

    skipCurrentBook() {
        const book = this.renameQueue[this.currentBookIndex];
        this.processedBooks.skipped.push(book);
        this.currentBookIndex++;
        this.showNextBookForRename();
    }

    async renameCurrentBook() {
        const book = this.renameQueue[this.currentBookIndex];
        const newFilename = document.getElementById('newFilename')?.value;

        if (!newFilename || newFilename.trim() === '') {
            EbookLibrary.UI.showAlert('Please enter a filename', 'warning');
            return;
        }

        try {
            const response = await fetch(`/books/${book.id}/rename/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': EbookLibrary.Ajax.getCSRFToken()
                },
                body: JSON.stringify({
                    new_filename: newFilename.trim()
                })
            });

            const data = await response.json();
            
            if (data.status === 'success') {
                this.processedBooks.success.push(book);
            } else {
                book.error = data.message;
                this.processedBooks.errors.push(book);
            }
        } catch (error) {
            book.error = 'Network error';
            this.processedBooks.errors.push(book);
        }

        this.currentBookIndex++;
        this.showNextBookForRename();
    }

    finishInteractiveRename() {
        this.interactiveModal.hide();
        
        const { success, errors, skipped } = this.processedBooks;
        const total = success.length + errors.length + skipped.length;
        
        let message = `Interactive rename complete!\n`;
        message += `• ${success.length} books renamed successfully\n`;
        message += `• ${errors.length} books failed to rename\n`;
        message += `• ${skipped.length} books skipped\n`;
        
        EbookLibrary.UI.showAlert(message, errors.length > 0 ? 'warning' : 'success');
        
        // Refresh the page to show updated filenames
        if (success.length > 0) {
            setTimeout(() => window.location.reload(), 2000);
        }
    }

    showProgressModal(title, message) {
        const modalTitle = document.querySelector('#progressModal .modal-title');
        const modalBody = document.querySelector('#progressModal .modal-body');
        
        if (modalTitle) modalTitle.textContent = title;
        if (modalBody) modalBody.innerHTML = `<p>${message}</p>`;
        
        this.progressModal.show();
    }

    hideProgressModal() {
        this.progressModal.hide();
    }

    handleExecutionResults(data) {
        const { results } = data;
        const successful = results.filter(r => r.success).length;
        const failed = results.filter(r => !r.success).length;
        
        this.hideProgressModal();
        
        let message = `Batch rename complete!\n`;
        message += `• ${successful} books renamed successfully\n`;
        message += `• ${failed} books failed to rename`;
        
        EbookLibrary.UI.showAlert(message, failed > 0 ? 'warning' : 'success');
        
        if (successful > 0) {
            setTimeout(() => window.location.reload(), 2000);
        }
    }
}

// Global instance
let bookRenamer;

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    bookRenamer = new BookRenamer();
});

// Export for global access
window.BookRenamer = BookRenamer;