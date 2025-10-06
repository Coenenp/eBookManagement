// =============================================================================
// BOOK DETAIL PAGE JAVASCRIPT
// =============================================================================

class BookDetailManager {
    constructor(bookId) {
        this.bookId = bookId;
        this.metadataManager = new MetadataTabManager(bookId);
        this.coversManager = new CoversTabManager(bookId);
        this.formManager = new EditFormManager();
        this.rescanManager = new RescanTabManager(bookId);
        this.init();
    }

    init() {
        this.initializeTabFunctionality();
        this.initializeTooltips();
        this.initializeKeyboardNavigation();
        this.bindGlobalEvents();
    }

    initializeTabFunctionality() {
        const tabButtons = document.querySelectorAll('#bookTabs .nav-link[data-bs-toggle="tab"]');
        const tabContents = document.querySelectorAll('.tab-pane');
        
        tabButtons.forEach(button => {
            button.addEventListener('click', function(e) {
                e.preventDefault();
                
                tabButtons.forEach(btn => btn.classList.remove('active'));
                tabContents.forEach(content => content.classList.remove('active', 'show'));
                
                this.classList.add('active');
                const target = this.getAttribute('data-bs-target');
                const targetContent = document.querySelector(target);
                if (targetContent) {
                    targetContent.classList.add('active', 'show');
                }
            });
        });
    }

    initializeTooltips() {
        const confidenceBadges = document.querySelectorAll('.badge.bg-success, .badge.bg-warning, .badge.bg-danger');
        
        confidenceBadges.forEach(badge => {
            const confidence = parseFloat(badge.textContent.trim());
            if (!isNaN(confidence)) {
                let tooltipText = '';
                if (confidence >= 0.8) {
                    tooltipText = 'High confidence (≥0.8) - This value is very likely correct';
                } else if (confidence >= 0.5) {
                    tooltipText = 'Medium confidence (0.5-0.8) - This value may be correct';
                } else {
                    tooltipText = 'Low confidence (<0.5) - This value is uncertain';
                }
                
                badge.setAttribute('title', tooltipText);
                badge.setAttribute('data-bs-toggle', 'tooltip');
            }
        });
        
        if (typeof bootstrap !== 'undefined' && bootstrap.Tooltip) {
            const tooltipTriggerList = document.querySelectorAll('[data-bs-toggle="tooltip"]');
            tooltipTriggerList.forEach(tooltipTriggerEl => {
                new bootstrap.Tooltip(tooltipTriggerEl, { placement: 'top', trigger: 'hover focus' });
            });
        }
    }

    initializeKeyboardNavigation() {
        // Get navigation links for keyboard shortcuts
        const navigationLinks = {
            prevBook: document.querySelector('a[href*="/books/"][title*="Previous Book"]'),
            nextBook: document.querySelector('a[href*="/books/"][title*="Next Book"]'),
            nextUnreviewed: document.querySelector('a[href*="/books/"][title*="Next Unreviewed"]'),
            nextAuthor: document.querySelector('a[href*="/books/"][title*="Next by"]'),
            nextSeries: document.querySelector('a[href*="/books/"][title*="Next in"]')
        };

        // Add keyboard event listener
        document.addEventListener('keydown', (e) => {
            // Only trigger if no input field is focused
            if (document.activeElement.tagName === 'INPUT' || 
                document.activeElement.tagName === 'TEXTAREA' || 
                document.activeElement.tagName === 'SELECT') {
                return;
            }

            switch(e.key) {
                case 'ArrowLeft':
                    if (navigationLinks.prevBook) {
                        e.preventDefault();
                        window.location.href = navigationLinks.prevBook.href;
                    }
                    break;
                case 'ArrowRight':
                    if (navigationLinks.nextBook) {
                        e.preventDefault();
                        window.location.href = navigationLinks.nextBook.href;
                    }
                    break;
                case 'u': // 'u' for unreviewed
                case 'U':
                    if (navigationLinks.nextUnreviewed) {
                        e.preventDefault();
                        window.location.href = navigationLinks.nextUnreviewed.href;
                    }
                    break;
                case 'a': // 'a' for author
                case 'A':
                    if (navigationLinks.nextAuthor) {
                        e.preventDefault();
                        window.location.href = navigationLinks.nextAuthor.href;
                    }
                    break;
                case 's': // 's' for series
                case 'S':
                    if (navigationLinks.nextSeries) {
                        e.preventDefault();
                        window.location.href = navigationLinks.nextSeries.href;
                    }
                    break;
            }
        });

        // Add help text for keyboard shortcuts
        this.addKeyboardShortcutsHelp();
    }

    addKeyboardShortcutsHelp() {
        // Find the navigation cards and add help text
        const navigationCards = document.querySelectorAll('.navigation-card');
        if (navigationCards.length > 0) {
            const helpText = `
                <div class="text-muted small mt-2">
                    <i class="fas fa-keyboard me-1"></i>
                    <strong>Keyboard shortcuts:</strong> 
                    ← Prev • → Next • U Unreviewed • A Author • S Series
                </div>
            `;
            
            // Add to the first navigation card only
            const firstCard = navigationCards[0];
            const cardBody = firstCard.querySelector('.card-body');
            if (cardBody) {
                cardBody.insertAdjacentHTML('beforeend', helpText);
            }
        }
    }

    bindGlobalEvents() {
        // Global event delegation for better performance
        document.addEventListener('click', this.handleGlobalClick.bind(this));
    }

    handleGlobalClick(e) {
        console.log('Global click detected on:', e.target);
        
        // Check if clicked element or its parent is a trash button
        let removeBtn = null;
        
        // First check if the clicked element itself is a button with delete attributes
        if (e.target.matches('button[data-type][data-id], button[data-meta-type][data-meta-id]')) {
            removeBtn = e.target;
        }
        // Then check if we clicked on an icon inside such a button
        else if (e.target.matches('i.fa-trash') && e.target.parentElement.matches('button[data-type][data-id], button[data-meta-type][data-meta-id]')) {
            removeBtn = e.target.parentElement;
        }
        // Finally use closest as fallback
        else {
            removeBtn = e.target.closest('button[data-type][data-id], button[data-meta-type][data-meta-id]');
        }

        if (removeBtn) {
            console.log('Remove button found:', removeBtn);
            e.preventDefault();
            e.stopPropagation();
            
            const type = removeBtn.dataset.type || removeBtn.dataset.metaType;
            const id = removeBtn.dataset.id || removeBtn.dataset.metaId;
            
            console.log('Delete button clicked:', { type, id, element: removeBtn });
            
            if (type && id) {
                this.metadataManager.removeMetadata(type, id);
            } else {
                console.error('Missing type or id for metadata removal', { type, id });
            }
            return;
        }

        // Cover actions - check for both button clicks and icon clicks inside buttons
        let coverBtn = null;
        
        if (e.target.matches('button[data-action^="select-cover"], button[data-action^="remove-cover"]')) {
            coverBtn = e.target;
        }
        else if (e.target.matches('i') && e.target.parentElement.matches('button[data-action^="select-cover"], button[data-action^="remove-cover"]')) {
            coverBtn = e.target.parentElement;
        }
        else {
            coverBtn = e.target.closest('button[data-action^="select-cover"], button[data-action^="remove-cover"]');
        }

        if (coverBtn) {
            console.log('Cover button found:', coverBtn);
            e.preventDefault();
            e.stopPropagation();
            this.coversManager.handleCoverAction(coverBtn);
            return;
        }
        
        // Handle refresh page button
        if (e.target.closest('.refresh-page-btn')) {
            e.preventDefault();
            refreshPageHandler();
            return;
        }
        
        // Handle view metadata tab button
        if (e.target.closest('.view-metadata-tab-btn')) {
            e.preventDefault();
            viewMetadataTab();
            return;
        }
    }
}

// =============================================================================
// METADATA TAB MANAGER
// =============================================================================
class MetadataTabManager {
    constructor(bookId) {
        this.bookId = bookId;
    }

    async removeMetadata(type, id) {
        console.log('MetadataTabManager.removeMetadata called:', { type, id });
        
        if (!confirm("Remove this metadata entry? This action cannot be undone.")) {
            return;
        }

        try {
            const response = await this.makeRequest('/ajax/book/' + this.bookId + '/remove_metadata/', {
                type: type,
                id: id
            });

            console.log('Remove metadata response:', response);

            if (response.status === 'success') {
                Utils.showToast("Metadata removed successfully.", "success");
                this.removeMetadataElement(id);
                this.updateMetadataCounts();
            } else {
                Utils.showToast(response.message || "Failed to remove metadata.", "danger");
            }
        } catch (error) {
            console.error("Error removing metadata:", error);
            Utils.showToast("An error occurred while removing metadata.", "danger");
        }
    }

    removeMetadataElement(id) {
        // Try multiple selectors to find the metadata item
        const selectors = [
            `[data-id="${id}"]`,
            `[data-meta-id="${id}"]`,
            `.metadata-item[data-id="${id}"]`,
            `button[data-id="${id}"]`,
            `button[data-meta-id="${id}"]`
        ];

        let metadataItem = null;
        for (const selector of selectors) {
            const element = document.querySelector(selector);
            if (element) {
                metadataItem = element.closest('.metadata-item');
                if (metadataItem) break;
            }
        }

        if (metadataItem) {
            console.log('Removing metadata element:', metadataItem);
            metadataItem.classList.add('metadata-fade');
            setTimeout(() => metadataItem.remove(), 300);
        } else {
            console.warn('Could not find metadata element to remove for id:', id);
        }
    }

    updateMetadataCounts() {
        const sections = ['titles', 'authors', 'series', 'genres', 'publishers'];
        sections.forEach(section => {
            const targetLabel = section.charAt(0).toUpperCase() + section.slice(1);
            const card = Array.from(document.querySelectorAll('.card')).find(card => {
                const header = card.querySelector('h5');
                return header && header.textContent.includes(targetLabel);
            });

            if (card) {
                const items = card.querySelectorAll('.metadata-item');
                const badge = card.querySelector('.badge.bg-info');
                if (badge) {
                    badge.textContent = `${items.length} found`;
                }
            }
        });
    }

    async makeRequest(url, data) {
        console.log('Making request to:', url, 'with data:', data);
        
        const response = await fetch(url, {
            method: 'POST',
            headers: {
                'X-CSRFToken': Utils.getCookie('csrftoken'),
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(data),
        });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        return await response.json();
    }
}

// =============================================================================
// COVERS TAB MANAGER
// =============================================================================
class CoversTabManager {
    constructor(bookId) {
        this.bookId = bookId;
        this.initializeCoverPreview();
    }

    handleCoverAction(button) {
        const action = button.dataset.action;
        const coverPath = button.dataset.coverPath;
        const source = button.dataset.source;

        console.log('Cover action:', { action, coverPath, source });

        if (action === 'select-cover') {
            this.selectCover(coverPath, source);
        } else if (action === 'remove-cover') {
            this.removeCover(coverPath, source);
        }
    }

    async selectCover(coverPath, sourceName) {
        if (!coverPath) {
            Utils.showToast("Invalid cover path.", "danger");
            return;
        }

        try {
            const response = await this.makeCoverRequest('select', coverPath, sourceName);
            
            if (response.success) {
                Utils.showToast("Cover selected successfully.", "success");
                this.updateCoverSelection(coverPath);
                
                setTimeout(() => {
                    if (confirm("Cover updated. Reload page to see changes?")) {
                        location.reload();
                    }
                }, 1500);
            } else {
                Utils.showToast(response.message || "Failed to select cover.", "danger");
            }
        } catch (error) {
            console.error("Error selecting cover:", error);
            Utils.showToast("An error occurred while selecting cover.", "danger");
        }
    }

    async removeCover(coverPath, sourceName) {
        if (!confirm("Remove this cover? This action cannot be undone.")) return;

        try {
            const response = await this.makeCoverRequest('remove', coverPath, sourceName);
            
            if (response.success) {
                Utils.showToast("Cover removed successfully.", "success");
                this.removeCoverElement(coverPath);
                
                // Check if a new cover was automatically selected (fallback logic)
                if (response.new_cover_path) {
                    Utils.showToast(`Switched to next best cover: ${response.new_cover_path}`, "info");
                    this.updateCoverSelection(response.new_cover_path);
                    
                    // Suggest page reload to see the updated cover
                    setTimeout(() => {
                        if (confirm("Cover updated. Reload page to see changes?")) {
                            location.reload();
                        }
                    }, 2000);
                }
            } else {
                Utils.showToast(response.message || "Failed to remove cover.", "danger");
            }
        } catch (error) {
            console.error("Error removing cover:", error);
            Utils.showToast("An error occurred while removing cover.", "danger");
        }
    }

    async makeCoverRequest(action, coverPath, sourceName) {
        const response = await fetch(`/ajax/book/${this.bookId}/manage_cover/`, {
            method: 'POST',
            headers: {
                'X-CSRFToken': Utils.getCookie('csrftoken'),
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                action: action,
                cover_path: coverPath,
                source: sourceName
            }),
        });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        return await response.json();
    }

    updateCoverSelection(selectedCoverPath) {
        // Remove existing selected badges
        document.querySelectorAll('#covers .badge.bg-primary').forEach(badge => {
            if (badge.textContent.trim() === 'Selected') {
                badge.remove();
            }
        });

        // Add selected badge to new cover and hide select button
        document.querySelectorAll('#covers .col-md-6.col-lg-4').forEach(card => {
            const img = card.querySelector('img');
            const selectBtn = card.querySelector('[data-action="select-cover"]');
            
            if (img && img.src.includes(selectedCoverPath)) {
                const badgeContainer = card.querySelector('.card-header > div');
                if (badgeContainer) {
                    const selectedBadge = document.createElement('span');
                    selectedBadge.className = 'badge bg-primary ms-1';
                    selectedBadge.textContent = 'Selected';
                    badgeContainer.appendChild(selectedBadge);
                }
                if (selectBtn) selectBtn.classList.add('d-hidden');
            } else {
                if (selectBtn) selectBtn.classList.remove('d-hidden');
            }
        });
    }

    removeCoverElement(coverPath) {
        const coverCards = document.querySelectorAll('#covers .col-md-6.col-lg-4');
        coverCards.forEach(card => {
            const img = card.querySelector('img');
            if (img && img.src.includes(coverPath)) {
                card.classList.add('scale-down');
                setTimeout(() => card.remove(), 300);
            }
        });
    }

    initializeCoverPreview() {
        document.addEventListener('click', (e) => {
            const img = e.target.closest('.img-thumbnail');
            if (img && img.closest('#covers')) {
                this.showCoverPreview(img.src, img.alt);
            }
        });

        // Add hover effects
        const coverImages = document.querySelectorAll('#covers .img-thumbnail');
        coverImages.forEach(img => {
            img.classList.add('cover-hover-effect');
        });
    }

    showCoverPreview(src, alt) {
        let modal = document.getElementById('coverPreviewModal');
        if (!modal) {
            modal = this.createPreviewModal();
        }

        const previewImg = modal.querySelector('#previewImage');
        previewImg.src = src;
        previewImg.alt = alt;
        modal.querySelector('.modal-title').textContent = alt || 'Cover Preview';

        if (typeof bootstrap !== 'undefined' && bootstrap.Modal) {
            new bootstrap.Modal(modal).show();
        }
    }

    createPreviewModal() {
        const modal = document.createElement('div');
        modal.id = 'coverPreviewModal';
        modal.className = 'modal fade';
        modal.innerHTML = `
            <div class="modal-dialog modal-lg modal-dialog-centered">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title">Cover Preview</h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body text-center">
                        <img id="previewImage" class="img-fluid max-height-70vh">>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Close</button>
                    </div>
                </div>
            </div>
        `;
        document.body.appendChild(modal);
        return modal;
    }
}

// =============================================================================
// EDIT FORM MANAGER
// =============================================================================
class EditFormManager {
    constructor() {
        this.init();
    }

    init() {
        this.initializeDropdownHandlers();
        this.initializeCoverHandling();
        this.initializeFormSubmission();
        this.initializeResetButton();
        this.initializeManualEntryDetection();
    }

    initializeDropdownHandlers() {
        const dropdowns = document.querySelectorAll('select[data-field]');
        
        dropdowns.forEach(dropdown => {
            dropdown.addEventListener('change', (e) => {
                this.handleDropdownChange(e.target);
            });
        });
    }

    handleDropdownChange(dropdown) {
        const fieldName = dropdown.dataset.field;
        const selectedValue = dropdown.value;
        const targetInput = this.getTargetInput(fieldName);
        
        if (!targetInput) return;

        if (selectedValue === '__manual__') {
            targetInput.value = '';
            this.updateFieldInfo(fieldName, 'Manual', null, true);
            targetInput.focus();
        } else if (selectedValue) {
            const selectedOption = dropdown.options[dropdown.selectedIndex];
            const source = selectedOption.dataset.source;
            const confidence = selectedOption.dataset.confidence;
            
            targetInput.value = selectedValue;
            this.updateFieldInfo(fieldName, source, confidence, false);
            
            // Handle series number special case
            if (fieldName === 'final_series') {
                const seriesNumber = selectedOption.dataset.number;
                const seriesNumberInput = document.getElementById('id_final_series_number');
                if (seriesNumber && seriesNumberInput) {
                    seriesNumberInput.value = seriesNumber;
                }
            }
        } else {
            if (fieldName !== 'language') {
                targetInput.value = '';
            }
            this.updateFieldInfo(fieldName, null, null, false);
        }
    }

    getTargetInput(fieldName) {
        const fieldMap = {
            'language': 'id_language',
            'publication_year': 'id_publication_year',
            'isbn': 'id_isbn',
            'description': 'id_description'
        };
        
        const inputId = fieldMap[fieldName] || 'id_' + fieldName;
        return document.getElementById(inputId);
    }

    updateFieldInfo(fieldName, source, confidence, isManual) {
        const badge = document.getElementById(fieldName + '_badge');
        if (!badge) return;
        
        if (isManual) {
            badge.textContent = 'Manual';
            badge.className = 'badge bg-info';
        } else if (source && confidence) {
            badge.textContent = `${source} (${confidence})`;
            badge.className = 'badge bg-secondary';
        } else {
            badge.textContent = 'Final';
            badge.className = 'badge bg-primary';
        }
    }

    initializeCoverHandling() {
        const coverDropdown = document.getElementById('cover_dropdown');
        const coverUploadSection = document.getElementById('coverUploadSection');
        const hiddenCoverPath = document.getElementById('id_final_cover_path');
        
        if (!coverDropdown) return;
        
        coverDropdown.addEventListener('change', (e) => {
            const selectedValue = e.target.value;
            
            if (selectedValue === '__manual__') {
                coverUploadSection.classList.remove('d-hidden');
                hiddenCoverPath.value = '';
                this.updateCoverPreview('');
            } else {
                coverUploadSection.classList.add('d-hidden');
                hiddenCoverPath.value = selectedValue;
                this.updateCoverPreview(selectedValue);
            }
        });
        
        // Handle file upload preview
        const fileInput = document.getElementById('id_new_cover_upload');
        if (fileInput) {
            fileInput.addEventListener('change', (e) => {
                const file = e.target.files[0];
                if (file) {
                    const reader = new FileReader();
                    reader.onload = (e) => this.updateCoverPreview(e.target.result, true);
                    reader.readAsDataURL(file);
                }
            });
        }
    }

    updateCoverPreview(src, isUpload = false) {
        const coverPreview = document.getElementById('coverPreview');
        const coverImage = document.getElementById('coverImage');
        
        if (!coverPreview) return;
        
        if (src && src.trim() !== '') {
            if (coverImage) {
                coverImage.src = src;
                coverImage.classList.remove('d-hidden');
            } else {
                coverPreview.innerHTML = `<img src="${src}" alt="Cover preview" class="img-thumbnail cover-preview-small" id="coverImage">`;
            }
        } else {
            coverPreview.innerHTML = '<div class="text-muted">No cover selected</div>';
        }
    }

    initializeFormSubmission() {
        const form = document.getElementById('metadataUpdateForm');
        if (!form) return;

        form.addEventListener('submit', (e) => {
            if (!this.validateForm(form)) {
                e.preventDefault();
                return;
            }
            
            this.addManualEntryFlags();
            this.showLoadingState(e.submitter);
        });
    }

    validateForm(form) {
        const titleField = document.getElementById('id_final_title');
        const authorField = document.getElementById('id_final_author');
        
        if (!titleField.value.trim()) {
            titleField.focus();
            Utils.showValidationError('Title is required');
            return false;
        }
        
        if (!authorField.value.trim()) {
            authorField.focus();
            Utils.showValidationError('Author is required');
            return false;
        }
        
        return true;
    }

    addManualEntryFlags() {
        const manualFields = [
            'final_title', 'final_author', 'final_series',
            'final_publisher', 'publication_year', 'description',
            'isbn', 'language'
        ];

        const form = document.getElementById('metadataUpdateForm');

        manualFields.forEach(fieldName => {
            const dropdownId = fieldName === 'publication_year' ? 'year_dropdown' :
                            fieldName === 'final_title' ? 'title_dropdown' :
                            fieldName === 'final_author' ? 'author_dropdown' :
                            fieldName === 'final_series' ? 'series_dropdown' :
                            fieldName === 'final_publisher' ? 'publisher_dropdown' :
                            `${fieldName}_dropdown`;

            const dropdown = document.getElementById(dropdownId);
            const textInput = this.getTargetInput(fieldName);

            // Always create or update the hidden input
            let hiddenInput = form.querySelector(`input[name="manual_entry_${fieldName}"]`);
            if (!hiddenInput) {
                hiddenInput = document.createElement('input');
                hiddenInput.type = 'hidden';
                hiddenInput.name = 'manual_entry_' + fieldName;
                form.appendChild(hiddenInput);
            }

            // Determine if this should be manual entry:
            // 1. Dropdown explicitly set to __manual__
            // 2. No dropdown exists but text input has a value
            // 3. Dropdown exists but is empty/unselected, and text input has a value
            let shouldBeManual = false;
            
            if (dropdown && dropdown.value === '__manual__') {
                // Explicitly selected manual entry
                shouldBeManual = true;
            } else if (!dropdown && textInput && textInput.value.trim()) {
                // No dropdown available, but text field has content
                shouldBeManual = true;
            } else if (dropdown && (!dropdown.value || dropdown.value === '') && textInput && textInput.value.trim()) {
                // Dropdown exists but nothing selected, text field has content
                shouldBeManual = true;
            }

            hiddenInput.value = shouldBeManual ? 'true' : 'false';
            
            // Debug logging
            console.log(`Field ${fieldName}: dropdown=${dropdown ? 'exists' : 'none'}, ` +
                    `dropdownValue=${dropdown ? dropdown.value : 'n/a'}, ` +
                    `textValue='${textInput ? textInput.value : 'n/a'}', ` +
                    `manual=${shouldBeManual}`);
        });

        // Handle cover separately
        const coverDropdown = document.getElementById('cover_dropdown');
        let coverInput = form.querySelector(`input[name="manual_entry_final_cover_path"]`);
        if (!coverInput) {
            coverInput = document.createElement('input');
            coverInput.type = 'hidden';
            coverInput.name = 'manual_entry_final_cover_path';
            form.appendChild(coverInput);
        }
        coverInput.value = (coverDropdown && coverDropdown.value === '__manual__') ? 'true' : 'false';
    }

    initializeManualEntryDetection() {
        const manualFields = [
            'final_title', 'final_author', 'final_series',
            'final_publisher', 'publication_year', 'description',
            'isbn', 'language'
        ];

        manualFields.forEach(fieldName => {
            const textInput = this.getTargetInput(fieldName);
            const dropdownId = fieldName === 'publication_year' ? 'year_dropdown' :
                            fieldName === 'final_title' ? 'title_dropdown' :
                            fieldName === 'final_author' ? 'author_dropdown' :
                            fieldName === 'final_series' ? 'series_dropdown' :
                            fieldName === 'final_publisher' ? 'publisher_dropdown' :
                            `${fieldName}_dropdown`;
            
            const dropdown = document.getElementById(dropdownId);

            if (textInput) {
                // Add event listeners for input changes
                textInput.addEventListener('input', () => {
                    this.updateManualEntryStatus(fieldName, textInput, dropdown);
                });
                
                textInput.addEventListener('blur', () => {
                    this.updateManualEntryStatus(fieldName, textInput, dropdown);
                });
            }
        });
    }

    updateManualEntryStatus(fieldName, textInput, dropdown) {
        const hasValue = textInput.value.trim() !== '';
        const dropdownHasNoValue = !dropdown || !dropdown.value || dropdown.value === '';
        
        if (hasValue && (dropdownHasNoValue || dropdown.value === '__manual__')) {
            // This looks like manual entry - update the info display
            this.updateFieldInfo(fieldName, 'Manual Entry', null, true);
            
            // Also set a data attribute for later reference
            textInput.setAttribute('data-is-manual', 'true');
        } else if (hasValue && dropdown && dropdown.value && dropdown.value !== '__manual__') {
            // Value matches a dropdown selection
            const selectedOption = dropdown.options[dropdown.selectedIndex];
            const source = selectedOption.dataset.source;
            const confidence = selectedOption.dataset.confidence;
            this.updateFieldInfo(fieldName, source, confidence, false);
            textInput.removeAttribute('data-is-manual');
        } else {
            // No value or unclear state
            textInput.removeAttribute('data-is-manual');
        }
    }

    showLoadingState(submitButton) {
        if (!submitButton) return;
        
        const originalContent = submitButton.innerHTML;
        submitButton.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i> Saving...';
        submitButton.disabled = true;
        
        const form = document.getElementById('metadataUpdateForm');
        const allSubmitButtons = form.querySelectorAll('button[type="submit"]');
        allSubmitButtons.forEach(btn => {
            if (btn !== submitButton) {
                btn.disabled = true;
            }
        });
    }

    initializeResetButton() {
        const resetButton = document.getElementById('resetAllBtn');
        if (!resetButton) return;
        
        resetButton.addEventListener('click', () => {
            if (!confirm('Reset all fields to their current final metadata values? This will undo any unsaved changes.')) {
                return;
            }
            this.resetAllFields();
        });
    }

    resetAllFields() {
        // Reset dropdowns
        document.querySelectorAll('select[data-field]').forEach(dropdown => {
            dropdown.selectedIndex = 0;
        });
        
        // Reset input fields
        document.querySelectorAll('#metadataUpdateForm input[type="text"], #metadataUpdateForm input[type="number"], #metadataUpdateForm textarea').forEach(input => {
            const originalValue = input.getAttribute('value') || input.defaultValue || '';
            input.value = originalValue;
        });
        
        // Reset cover selection and other specific fields
        this.resetSpecificFields();
        
        // Reset all badges
        document.querySelectorAll('[id$="_badge"]').forEach(badge => {
            badge.textContent = 'Final';
            badge.className = 'badge bg-primary';
        });
        
        // Hide cover upload section
        const coverUploadSection = document.getElementById('coverUploadSection');
        if (coverUploadSection) {
            coverUploadSection.classList.add('d-hidden');
        }
    }

    resetSpecificFields() {
        // Language field reset would go here with template data
        // Genre checkboxes reset would go here with template data
        // Cover selection reset would go here with template data
        // This method can be extended with specific reset logic
    }
}

// =============================================================================
// UTILITY FUNCTIONS
// =============================================================================
class Utils {
    static getCookie(name) {
        const cookieValue = document.cookie.split('; ')
            .find(row => row.startsWith(name + '='))
            ?.split('=')[1];
        return decodeURIComponent(cookieValue || '');
    }

    static showToast(message, type = 'info') {
        const container = document.getElementById('toast-container');
        if (!container) {
            alert(message);
            return;
        }

        const toast = document.createElement('div');
        const typeClass = {
            'danger': 'bg-danger text-white',
            'success': 'bg-success text-white',
            'warning': 'bg-warning text-dark',
            'info': 'bg-info text-white'
        }[type] || 'bg-info text-white';

        toast.className = `toast ${typeClass} border-0 mb-2`;
        toast.role = 'alert';
        toast.innerHTML = `
            <div class="d-flex align-items-center">
                <div class="toast-body">${message}</div>
                <button type="button" class="btn-close ${type === 'warning' ? '' : 'btn-close-white'} me-2 m-auto" data-bs-dismiss="toast"></button>
            </div>
        `;

        container.appendChild(toast);
        
        if (typeof bootstrap !== 'undefined' && bootstrap.Toast) {
            new bootstrap.Toast(toast, { delay: 4000 }).show();
        } else {
            toast.classList.remove('d-hidden');
            setTimeout(() => toast.remove(), 4000);
        }

        setTimeout(() => toast.remove(), 5000);
    }

    static showValidationError(message) {
        const alert = document.createElement('div');
        alert.className = 'alert alert-danger alert-dismissible fade show';
        alert.innerHTML = `
            <strong>Validation Error:</strong> ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;
        
        const form = document.getElementById('metadataUpdateForm');
        if (form) {
            form.insertBefore(alert, form.firstChild);
            setTimeout(() => {
                if (alert.parentElement) {
                    alert.remove();
                }
            }, 5000);
        }
    }
}

// =============================================================================
// INITIALIZATION
// =============================================================================
document.addEventListener('DOMContentLoaded', function() {
    console.log('DOM loaded, initializing BookDetailManager');
    
    // Get book ID from a data attribute or window variable
    const bookId = document.body.dataset.bookId || window.bookId;
    
    if (!bookId) {
        console.error('Book ID not found. Make sure to set data-book-id on body or window.bookId');
        return;
    }
    
    console.log('Initializing with book ID:', bookId);
    
    // Initialize the main manager
    window.bookDetailManager = new BookDetailManager(bookId);
    
    console.log('BookDetailManager initialized successfully');
});

// =============================================================================
// RESCAN TAB MANAGER
// =============================================================================

class RescanTabManager {
    constructor(bookId) {
        this.bookId = bookId;
        this.init();
    }

    init() {
        this.bindEvents();
    }

    bindEvents() {
        // Preview search terms button
        const previewBtn = document.getElementById('rescanPreviewBtn');
        if (previewBtn) {
            previewBtn.addEventListener('click', () => this.previewSearchTerms());
        }

        // Start rescan button
        const rescanBtn = document.getElementById('rescanBtn');
        if (rescanBtn) {
            rescanBtn.addEventListener('click', () => this.startRescan());
        }
    }

    previewSearchTerms() {
        const searchTerms = this.getSearchTerms();
        
        let message = 'The following search terms will be used for the rescan:\n\n';
        if (searchTerms.title) message += `Title: "${searchTerms.title}"\n`;
        if (searchTerms.author) message += `Author: "${searchTerms.author}"\n`;
        if (searchTerms.isbn) message += `ISBN: "${searchTerms.isbn}"\n`;
        if (searchTerms.series) message += `Series: "${searchTerms.series}"\n`;
        
        if (!searchTerms.title && !searchTerms.author && !searchTerms.isbn) {
            message = 'No search terms available. Please provide at least a title, author, or ISBN.';
        }
        
        alert(message);
    }

    getSearchTerms() {
        return {
            title: document.getElementById('rescan_title').value.trim(),
            author: document.getElementById('rescan_author').value.trim(),
            isbn: document.getElementById('rescan_isbn').value.trim(),
            series: document.getElementById('rescan_series').value.trim()
        };
    }

    getSelectedSources() {
        const sources = [];
        const checkboxes = document.querySelectorAll('input[name="sources"]:checked');
        checkboxes.forEach(cb => sources.push(cb.value));
        return sources;
    }

    getOptions() {
        return {
            clearExisting: document.getElementById('rescan_clear_existing').checked,
            forceRefresh: document.getElementById('rescan_force_refresh').checked
        };
    }

    async startRescan() {
        const searchTerms = this.getSearchTerms();
        const sources = this.getSelectedSources();
        const options = this.getOptions();

        // Validate inputs
        if (!searchTerms.title && !searchTerms.author && !searchTerms.isbn) {
            alert('Please provide at least a title, author, or ISBN for the rescan.');
            return;
        }

        if (sources.length === 0) {
            alert('Please select at least one external source to query.');
            return;
        }

        // Show progress section
        this.showProgress();
        
        // Disable rescan button
        const rescanBtn = document.getElementById('rescanBtn');
        rescanBtn.disabled = true;
        rescanBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>Rescanning...';

        try {
            // Prepare form data
            const formData = new FormData();
            
            // Add search terms
            formData.append('title_override', searchTerms.title);
            formData.append('author_override', searchTerms.author);
            formData.append('isbn_override', searchTerms.isbn);
            formData.append('series_override', searchTerms.series);
            
            // Add sources
            sources.forEach(source => formData.append('sources[]', source));
            
            // Add options
            formData.append('clear_existing', options.clearExisting);
            formData.append('force_refresh', options.forceRefresh);
            
            // Add CSRF token
            const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]').value;
            formData.append('csrfmiddlewaretoken', csrfToken);

            // Update progress
            this.updateProgress(20, 'Sending request to external sources...');

            // Send request
            const response = await fetch(`/book/${this.bookId}/rescan/`, {
                method: 'POST',
                body: formData
            });

            this.updateProgress(50, 'Processing response...');

            const result = await response.json();

            if (result.success) {
                this.updateProgress(100, 'Rescan completed successfully!');
                this.showResults(result);
            } else {
                throw new Error(result.error || 'Unknown error occurred');
            }

        } catch (error) {
            console.error('Rescan error:', error);
            this.showError(error.message);
        } finally {
            // Re-enable rescan button
            rescanBtn.disabled = false;
            rescanBtn.innerHTML = '<i class="fas fa-sync-alt me-2"></i>Start Rescan';
        }
    }

    showProgress() {
        const progressSection = document.getElementById('rescanProgress');
        const resultsSection = document.getElementById('rescanResults');
        
        progressSection.classList.remove('d-hidden');
        resultsSection.classList.add('d-hidden');
        
        this.updateProgress(0, 'Initializing rescan...');
    }

    updateProgress(percentage, status) {
        const progressBar = document.getElementById('rescanProgressBar');
        const statusText = document.getElementById('rescanStatus');
        const logText = document.getElementById('rescanLog');
        
        progressBar.style.width = percentage + '%';
        progressBar.setAttribute('aria-valuenow', percentage);
        statusText.textContent = status;
        
        // Add to log
        const timestamp = new Date().toLocaleTimeString();
        logText.innerHTML += `<div>${timestamp}: ${status}</div>`;
        logText.scrollTop = logText.scrollHeight;
    }

    showResults(result) {
        const progressSection = document.getElementById('rescanProgress');
        const resultsSection = document.getElementById('rescanResults');
        const summaryDiv = document.getElementById('rescanSummary');
        
        progressSection.classList.add('d-hidden');
        resultsSection.classList.remove('d-hidden');
        
        // Build summary HTML
        let summaryHtml = '<h6>Rescan Summary:</h6>';
        summaryHtml += `<p><strong>Search Terms Used:</strong></p><ul>`;
        if (result.search_terms.title) summaryHtml += `<li>Title: "${result.search_terms.title}"</li>`;
        if (result.search_terms.author) summaryHtml += `<li>Author: "${result.search_terms.author}"</li>`;
        if (result.search_terms.isbn) summaryHtml += `<li>ISBN: "${result.search_terms.isbn}"</li>`;
        if (result.search_terms.series) summaryHtml += `<li>Series: "${result.search_terms.series}"</li>`;
        summaryHtml += '</ul>';
        
        summaryHtml += '<p><strong>Sources Queried:</strong> ' + result.sources_queried.join(', ') + '</p>';
        
        summaryHtml += '<p><strong>New Metadata Added:</strong></p><ul>';
        for (const [key, count] of Object.entries(result.added_counts)) {
            if (count > 0) {
                summaryHtml += `<li>${key.charAt(0).toUpperCase() + key.slice(1)}: ${count} new entries</li>`;
            }
        }
        summaryHtml += '</ul>';
        
        const totalAdded = Object.values(result.added_counts).reduce((sum, count) => sum + count, 0);
        if (totalAdded === 0) {
            summaryHtml += '<p class="text-muted">No new metadata was found.</p>';
        } else {
            summaryHtml += `<p class="text-success"><strong>Total: ${totalAdded} new metadata entries added</strong></p>`;
        }
        
        summaryDiv.innerHTML = summaryHtml;
    }

    showError(errorMessage) {
        const progressSection = document.getElementById('rescanProgress');
        const resultsSection = document.getElementById('rescanResults');
        
        progressSection.classList.add('d-hidden');
        
        // Show error in results section
        const resultsDiv = document.querySelector('#rescanResults .card-header');
        const resultsBody = document.querySelector('#rescanResults .card-body');
        
        resultsDiv.className = 'card-header bg-danger text-white';
        resultsDiv.innerHTML = '<h6 class="mb-0"><i class="fas fa-exclamation-triangle me-2"></i>Rescan Failed</h6>';
        
        resultsBody.innerHTML = `
            <div class="alert alert-danger">
                <strong>Error:</strong> ${errorMessage}
            </div>
            <button type="button" class="btn btn-secondary" onclick="location.reload()">
                <i class="fas fa-refresh me-2"></i>Refresh Page
            </button>
        `;
        
        resultsSection.style.display = 'block';
    }
}

// =============================================================================
// LEGACY COMPATIBILITY (for onclick handlers)
// =============================================================================
function removeMetadata(type, id) {
    console.log('Legacy removeMetadata called:', { type, id });
    if (window.bookDetailManager && window.bookDetailManager.metadataManager) {
        window.bookDetailManager.metadataManager.removeMetadata(type, id);
    } else {
        console.error('BookDetailManager not initialized');
    }
}

function selectCover(coverPath, sourceName) {
    console.log('Legacy selectCover called:', { coverPath, sourceName });
    if (window.bookDetailManager && window.bookDetailManager.coversManager) {
        window.bookDetailManager.coversManager.selectCover(coverPath, sourceName);
    } else {
        console.error('BookDetailManager not initialized');
    }
}

function removeCover(coverPath, sourceName) {
    console.log('Legacy removeCover called:', { coverPath, sourceName });
    if (window.bookDetailManager && window.bookDetailManager.coversManager) {
        window.bookDetailManager.coversManager.removeCover(coverPath, sourceName);
    } else {
        console.error('BookDetailManager not initialized');
    }
}

function refreshPageHandler() {
    location.reload();
}

function viewMetadataTab() {
    const metadataTab = document.getElementById('metadata-tab');
    if (metadataTab) {
        metadataTab.click();
    }
}
