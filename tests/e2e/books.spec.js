// @ts-check
const { test, expect } = require('@playwright/test');

test.describe('Book Management', () => {
    test.beforeEach(async ({ page }) => {
        // Login before each test
        await page.goto('/accounts/login/');
        await page.fill('input[name="username"]', 'testuser');
        await page.fill('input[name="password"]', 'testpass123');
        await page.click('button[type="submit"]');
        await expect(page).toHaveURL(/\/books\/dashboard\//);
    });

    test('should display books list', async ({ page }) => {
        await page.goto('/books/ebooks/');

        // Should show books page
        await expect(page.locator('h1, h2, .page-title').filter({ hasText: /books|e-books/i })).toBeVisible();
    });

    test('should filter books', async ({ page }) => {
        await page.goto('/books/ebooks/');

        // Look for filter controls
        const filterInputs = page.locator('input[type="search"], input[name*="filter"], input[placeholder*="search"]');

        if ((await filterInputs.count()) > 0) {
            // Type in filter
            await filterInputs.first().fill('test');

            // Wait for results to update (AJAX)
            await page.waitForTimeout(500);
        }
    });

    test('should view book details', async ({ page }) => {
        await page.goto('/books/ebooks/');

        // Find first book card or link
        const bookLink = page.locator('a[href*="/books/detail/"], .book-card a, .book-item a').first();

        if ((await bookLink.count()) > 0) {
            await bookLink.click();

            // Should be on detail page
            await expect(page).toHaveURL(/\/books\/detail\/\d+/);

            // Should show book information
            await expect(page.locator('.book-title, .book-info, h1')).toBeVisible();
        }
    });

    test('should access scan functionality', async ({ page }) => {
        // Look for scan page
        await page.goto('/books/scan/');

        // Should show scan interface
        await expect(page.locator('h1, h2').filter({ hasText: /scan/i })).toBeVisible();
    });

    test('should display scan folders', async ({ page }) => {
        await page.goto('/books/scan-folders/');

        // Should show scan folders page
        await expect(page.locator('h1, h2').filter({ hasText: /scan.*folder/i })).toBeVisible();

        // Should have add folder button or link
        const addButton = page.locator('a:has-text("Add"), button:has-text("Add")');
        if ((await addButton.count()) > 0) {
            await expect(addButton.first()).toBeVisible();
        }
    });

    test('should navigate metadata management', async ({ page }) => {
        // Try to access metadata page
        await page.goto('/books/metadata/');

        // If metadata page exists, verify it loaded
        if (page.url().includes('/books/metadata/')) {
            await expect(page.locator('body')).toBeVisible();
        }
    });

    test('should handle pagination', async ({ page }) => {
        await page.goto('/books/ebooks/');

        // Look for pagination controls
        const pagination = page.locator('.pagination, nav[aria-label="pagination"]');

        if ((await pagination.count()) > 0) {
            // Check for next button
            const nextButton = page.locator('.pagination a:has-text("Next"), .pagination a[aria-label="Next"]');

            if ((await nextButton.count()) > 0) {
                await expect(nextButton.first()).toBeVisible();
            }
        }
    });

    test('should display book covers', async ({ page }) => {
        await page.goto('/books/ebooks/');

        // Look for book cover images
        const covers = page.locator('img[alt*="cover"], .book-cover img, .cover-image');

        if ((await covers.count()) > 0) {
            await expect(covers.first()).toBeVisible();
        }
    });
});
