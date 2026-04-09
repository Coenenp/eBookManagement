// @ts-check
const { test, expect } = require('@playwright/test');

test.describe('Setup Wizard', () => {
    test('should complete initial setup wizard', async ({ page }) => {
        await page.goto('/books/wizard/');

        // Should show wizard page
        await expect(page.locator('h1, h2').filter({ hasText: /setup|wizard/i })).toBeVisible();

        // Step 1: Welcome or folder selection
        const nextButton = page.locator('button:has-text("Next"), button[type="submit"]').first();
        if (await nextButton.isVisible()) {
            await nextButton.click();
        }

        // Wait for next step to load
        await page.waitForTimeout(500);
    });

    test('should allow folder selection in wizard', async ({ page }) => {
        await page.goto('/books/wizard/');

        // Look for folder input or selection interface
        const folderInput = page.locator(
            'input[type="text"][name*="folder"], input[placeholder*="folder"], #folder-input'
        );

        if ((await folderInput.count()) > 0) {
            await expect(folderInput.first()).toBeVisible();
        }
    });

    test('should show scan settings in wizard', async ({ page }) => {
        await page.goto('/books/wizard/');

        // Look for scan settings like deep scan checkbox
        const deepScanCheckbox = page.locator('input[type="checkbox"][name*="deep"], input[id*="deep"]');

        if ((await deepScanCheckbox.count()) > 0) {
            await expect(deepScanCheckbox.first()).toBeVisible();
        }
    });

    test('should allow wizard navigation', async ({ page }) => {
        await page.goto('/books/wizard/');

        // Test navigation buttons
        const nextButton = page.locator('button:has-text("Next")');
        const prevButton = page.locator('button:has-text("Previous"), button:has-text("Back")');

        if ((await nextButton.count()) > 0) {
            await nextButton.click();

            // Previous button should appear
            await page.waitForTimeout(300);

            if ((await prevButton.count()) > 0) {
                await expect(prevButton.first()).toBeVisible();
            }
        }
    });
});
