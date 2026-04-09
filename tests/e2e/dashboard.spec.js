// @ts-check
const { test, expect } = require('@playwright/test');

test.describe('Dashboard', () => {
    test.beforeEach(async ({ page }) => {
        // Login before each test
        await page.goto('/accounts/login/');
        await page.fill('input[name="username"]', 'testuser');
        await page.fill('input[name="password"]', 'testpass123');
        await page.click('button[type="submit"]');
        await expect(page).toHaveURL(/\/books\/dashboard\//);
    });

    test('should display dashboard statistics', async ({ page }) => {
        await page.goto('/books/dashboard/');

        // Check for main dashboard elements
        await expect(page.locator('h1, h2').filter({ hasText: /dashboard/i })).toBeVisible();

        // Check for statistics cards/widgets
        const statsCards = page.locator('.card, .stat-card, .widget');
        await expect(statsCards.first()).toBeVisible();
    });

    test('should navigate to books list', async ({ page }) => {
        await page.goto('/books/dashboard/');

        // Find and click link to books/ebooks
        const booksLink = page.locator('a[href*="/books/ebooks"], a:has-text("Books"), a:has-text("E-books")').first();
        await booksLink.click();

        // Should be on books list page
        await expect(page).toHaveURL(/\/books\/ebooks/);
    });

    test('should navigate to comics', async ({ page }) => {
        await page.goto('/books/dashboard/');

        const comicsLink = page.locator('a[href*="/books/comics"]').first();
        if ((await comicsLink.count()) > 0) {
            await comicsLink.click();
            await expect(page).toHaveURL(/\/books\/comics/);
        }
    });

    test('should navigate to audiobooks', async ({ page }) => {
        await page.goto('/books/dashboard/');

        const audiobooksLink = page.locator('a[href*="/books/audiobooks"]').first();
        if ((await audiobooksLink.count()) > 0) {
            await audiobooksLink.click();
            await expect(page).toHaveURL(/\/books\/audiobooks/);
        }
    });

    test('should display recent activity', async ({ page }) => {
        await page.goto('/books/dashboard/');

        // Look for recent activity section
        const recentActivity = page.locator('text=/recent/i, .recent-activity, #recent-activity');

        // If recent activity exists, it should be visible
        if ((await recentActivity.count()) > 0) {
            await expect(recentActivity.first()).toBeVisible();
        }
    });
});
