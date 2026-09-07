/**
 * Author Profile Management
 * Handles fetching and displaying author enrichment data from external sources
 */

class AuthorProfileManager {
    constructor(authorId, enrichUrl, csrfToken) {
        this.authorId = authorId;
        this.enrichUrl = enrichUrl;
        this.csrfToken = csrfToken;

        // DOM elements
        this.button = document.getElementById('enrichButton');
        this.errorDiv = document.getElementById('enrichmentError');
        this.noDataMsg = document.getElementById('noEnrichmentMessage');
        this.contentDiv = document.getElementById('enrichmentContent');

        this.initializeEventListeners();
    }

    initializeEventListeners() {
        if (this.button) {
            this.button.addEventListener('click', () => this.enrichAuthor());
        }
    }

    enrichAuthor() {
        // Disable button and show loading state
        this.button.disabled = true;
        this.button.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Fetching...';
        this.errorDiv.classList.add('d-none');

        // Make AJAX request
        fetch(this.enrichUrl, {
            method: 'POST',
            headers: {
                'X-CSRFToken': this.csrfToken,
                'Content-Type': 'application/json',
            },
        })
            .then((response) => response.json())
            .then((data) => {
                if (data.success) {
                    this.displayEnrichmentData(data.data);
                } else {
                    this.displayError(data.error || 'Failed to fetch author data');
                }
            })
            .catch((error) => {
                console.error('Error:', error);
                this.displayError('Network error: ' + error.message);
            });
    }

    displayEnrichmentData(data) {
        // Hide "no data" message
        this.noDataMsg.classList.add('d-none');
        this.contentDiv.classList.remove('d-none');

        // Display photo if available
        if (data.photo_url) {
            document.getElementById('authorPhoto').src = data.photo_url;
            document.getElementById('photoSection').classList.remove('d-none');
        }

        // Display biography if available
        if (data.bio) {
            document.getElementById('authorBio').textContent = data.bio;
            document.getElementById('bioSection').classList.remove('d-none');
        }

        // Display dates if available
        if (data.birth_date || data.death_date) {
            if (data.birth_date) {
                document.getElementById('birthDate').textContent = data.birth_date;
            }
            if (data.death_date) {
                document.getElementById('deathDate').textContent = data.death_date;
            }
            document.getElementById('datesSection').classList.remove('d-none');
        }

        // Display Wikipedia link if available
        if (data.wikipedia_url) {
            document.getElementById('wikipediaLink').href = data.wikipedia_url;
            document.getElementById('linksSection').classList.remove('d-none');
        }

        // Display data source
        if (data.source) {
            document.getElementById('dataSource').textContent = data.source;
            document.getElementById('sourceSection').classList.remove('d-none');
        }

        // Update button to success state
        this.button.innerHTML = '<i class="fas fa-check"></i> Data Fetched';
        this.button.classList.remove('btn-primary');
        this.button.classList.add('btn-success');
    }

    displayError(errorMessage) {
        // Show error message
        this.errorDiv.textContent = errorMessage;
        this.errorDiv.classList.remove('d-none');

        // Reset button
        this.button.disabled = false;
        this.button.innerHTML = '<i class="fas fa-download"></i> Fetch Profile Data';
    }
}

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', function () {
    const profileContainer = document.getElementById('authorProfileContainer');
    if (profileContainer) {
        const authorId = profileContainer.dataset.authorId;
        const enrichUrl = profileContainer.dataset.enrichUrl;
        const csrfToken = profileContainer.dataset.csrfToken;

        new AuthorProfileManager(authorId, enrichUrl, csrfToken);
    }
});
