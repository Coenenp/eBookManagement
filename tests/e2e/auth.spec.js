// @ts-check
const { test, expect } = require('@playwright/test');

test.describe('Authentication', () => {
    test('should display login page', async ({ page }) => {
        await page.goto('/accounts/login/');

        await expect(page).toHaveTitle(/Login/i);
        await expect(page.locator('input[name="username"]')).toBeVisible();
        await expect(page.locator('input[name="password"]')).toBeVisible();
        await expect(page.locator('button[type="submit"]')).toBeVisible();
    });

    test('should login with valid credentials', async ({ page }) => {
        await page.goto('/accounts/login/');

        // Fill in login form
        await page.fill('input[name="username"]', 'testuser');
        await page.fill('input[name="password"]', 'testpass123');

        // Submit form
        await page.click('button[type="submit"]');

        // Should redirect to dashboard
        await expect(page).toHaveURL(/\/books\/dashboard\//);
    });

    test('should show error with invalid credentials', async ({ page }) => {
        await page.goto('/accounts/login/');

        await page.fill('input[name="username"]', 'invaliduser');
        await page.fill('input[name="password"]', 'wrongpassword');
        await page.click('button[type="submit"]');

        // Should show error message
        await expect(page.locator('.alert-danger, .error, .invalid-feedback')).toBeVisible();
    });

    test('should logout successfully', async ({ page }) => {
        // Login first
        await page.goto('/accounts/login/');
        await page.fill('input[name="username"]', 'testuser');
        await page.fill('input[name="password"]', 'testpass123');
        await page.click('button[type="submit"]');

        // Wait for dashboard
        await expect(page).toHaveURL(/\/books\/dashboard\//);

        // Logout
        await page.click('a[href*="logout"], button:has-text("Logout")');

        // Should redirect to login
        await expect(page).toHaveURL(/\/accounts\/login\//);
    });
});
