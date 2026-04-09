# End-to-End Testing with Playwright

This directory contains end-to-end (E2E) tests for the eBook Management System using Playwright.

## Prerequisites

- Node.js installed
- Python virtual environment activated
- Dependencies installed (both npm and pip)

## Installation

1. Install npm dependencies:

```bash
npm install
```

2. Install Playwright browsers:

```bash
npx playwright install
```

3. Install Python dependencies:

```bash
pip install -r requirements.txt
```

## Running Tests

### Run all E2E tests

```bash
npm run test:e2e
```

### Run tests in headed mode (see browser)

```bash
npm run test:e2e:headed
```

### Run tests in UI mode (interactive)

```bash
npm run test:e2e:ui
```

### Run tests in debug mode

```bash
npm run test:e2e:debug
```

### Run specific test file

```bash
npx playwright test tests/e2e/auth.spec.js
```

### Run tests in specific browser

```bash
npx playwright test --project=chromium
npx playwright test --project=firefox
npx playwright test --project=webkit
```

## Test Structure

- `auth.spec.js` - Authentication and login/logout tests
- `dashboard.spec.js` - Dashboard functionality tests
- `books.spec.js` - Book management (list, detail, filter, pagination)
- `wizard.spec.js` - Setup wizard flow tests

## Test Data

Before running tests, ensure you have:

- A test user created with username `testuser` and password `testpass123`
- Database migrations applied
- Django development server running (or it will start automatically)

You can create a test user with:

```bash
python manage.py shell
```

```python
from django.contrib.auth.models import User
User.objects.create_user('testuser', 'test@example.com', 'testpass123')
```

## Debugging

### View last test run report

```bash
npx playwright show-report
```

### Generate trace for debugging

Tests automatically generate traces on failure. View them with:

```bash
npx playwright show-trace trace.zip
```

### Take screenshots

Screenshots are automatically captured on test failures and saved in `test-results/`

## Configuration

Playwright configuration is in `playwright.config.js` at the project root.

Key settings:

- Base URL: `http://localhost:8000` (can be overridden with `BASE_URL` env var)
- Test timeout: 30 seconds
- Retries: 2 on CI, 0 locally
- Browsers: Chromium, Firefox, WebKit

## CI/CD Integration

For CI environments, tests run with:

- Parallel execution disabled
- 2 retries per test
- HTML reporter for results

## Writing New Tests

1. Create a new `.spec.js` file in `tests/e2e/`
2. Follow the pattern in existing tests
3. Use page object pattern for complex pages
4. Add descriptive test names
5. Use proper assertions with `expect()`

Example:

```javascript
const { test, expect } = require('@playwright/test');

test.describe('My Feature', () => {
    test.beforeEach(async ({ page }) => {
        // Login or setup
    });

    test('should do something', async ({ page }) => {
        await page.goto('/my-page/');
        await expect(page.locator('h1')).toBeVisible();
    });
});
```

## Common Selectors

- Login: `input[name="username"]`, `input[name="password"]`
- Buttons: `button[type="submit"]`, `button:has-text("Text")`
- Links: `a[href="/path/"]`, `a:has-text("Text")`
- Forms: `form`, `input[name="field"]`

## Troubleshooting

**Tests timing out:**

- Increase timeout in `playwright.config.js`
- Check if Django server is running
- Verify database has test data

**Element not found:**

- Use `page.pause()` to debug interactively
- Check selector with browser DevTools
- Wait for dynamic content: `await page.waitForSelector('.selector')`

**Authentication issues:**

- Ensure test user exists
- Check credentials match in tests
- Verify session/CSRF token handling
