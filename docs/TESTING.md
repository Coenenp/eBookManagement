# Testing Guide

The project has two complementary test layers:

1. **Django unit and integration tests** in [`books/tests/`](../books/tests/) — fast, focused coverage of models, views, forms, scanner, and cover system.
2. **Playwright end-to-end (E2E) tests** in [`tests/e2e/`](../tests/e2e/) — browser-level verification of full workflows.

## 1. Unit and Integration Tests

### Run Everything

```bash
python manage.py test books.tests
```

Or with pytest (configuration in `pytest.ini`):

```bash
pytest
```

### Test database

Tests use SQLite and redirect the database, media files, and file-based cache
into a unique temporary directory for each test process via
[`ebook_manager/settings_test.py`](../ebook_manager/settings_test.py). This
isolates tests from the configured live MariaDB/MySQL database and from
persistent application media/cache directories. The temporary directory is
removed when the process exits, so `pytest --reuse-db` can reuse the schema
within a run but does not preserve it across separate runs.

The numbered `books` migration modules are currently tracked in Git. The
`reset_database` management command is available for a deliberate,
confirmed MySQL/MariaDB database rebuild; it deletes and regenerates the
`books` migration modules before applying them. This is destructive and is
not needed for routine test runs. A plan to stop tracking generated migrations
has not yet been completed.

### Run a Specific Area

```bash
python manage.py test books.tests.test_cover_cache
python manage.py test books.tests.test_cover_extractor
python manage.py test books.tests.test_scanner_background
python manage.py test books.tests.test_scanner_comprehensive
```

### Conventions

- Each test creates and cleans up its own data.
- External dependencies (`pdf2image`, `rarfile`, network calls) are mocked.
- Feature-flag mocking is used for optional imports (e.g., `HAS_PDF2IMAGE`).
- Assertions cover the happy path, error cases, and edge cases.
- `tearDown()` clears any files written during the test.

### Cover System Suite

The cover system is covered by focused suites:

| File                                | Coverage                                                 |
| ----------------------------------- | -------------------------------------------------------- |
| `test_cover_cache.py`               | Cache path generation, save/get/delete/clear, statistics |
| `test_cover_extractor.py`           | EPUB (3 strategies), PDF (pdf2image + PyPDF2), CBZ/CBR   |
| `test_cover_scanner_integration.py` | Detection priority, field population, cache reuse        |
| `test_cover_upload.py`              | Manual upload, restore, cover info, quality scoring      |
| `test_unified_cover_selection.py`   | Final-cover selection and orphan cleanup                 |

Run them together:

```bash
python manage.py test books.tests.test_cover_cache books.tests.test_cover_extractor books.tests.test_cover_scanner_integration books.tests.test_cover_upload books.tests.test_unified_cover_selection
```

Areas still mocked or not yet covered include real-file PDF/CBR extraction (requires poppler/unrar) and concurrency/load testing.

## 2. Playwright End-to-End Tests

### Prerequisites

- Node.js installed.
- Python virtual environment active.
- Both npm and pip dependencies installed.

### Setup

```bash
pip install -r requirements.txt
npm install
npx playwright install
```

### Create a Test User

```bash
python scripts/create_test_user.py
```

This creates `testuser` / `testpass123` / `test@example.com`.

### Run Tests

```bash
npm run test:e2e          # all tests
npm run test:e2e:headed   # visible browser
npm run test:e2e:ui       # interactive UI mode
npm run test:e2e:debug    # debug mode

npx playwright test tests/e2e/auth.spec.js   # one file
npx playwright test --project=chromium       # one browser
```

### Test Structure

```text
tests/e2e/
├── conftest.py          # Playwright fixtures
├── auth.spec.js         # authentication
├── dashboard.spec.js    # dashboard
├── books.spec.js        # book management
└── wizard.spec.js       # setup wizard
```

### Recording Tests (Codegen)

```bash
npx playwright codegen http://localhost:8000
```

Record with saved authentication:

```bash
npx playwright codegen --save-storage=auth.json http://localhost:8000/accounts/login/
npx playwright codegen --load-storage=auth.json http://localhost:8000/books/dashboard/
```

Record in a specific browser or mobile viewport:

```bash
npx playwright codegen --browser=firefox http://localhost:8000
npx playwright codegen --device="iPhone 13" http://localhost:8000
```

Workflow: start the Django server, create a test user, run codegen, perform actions, then copy and refine the generated code into a new `.spec.js` file.

### Debugging Failed Tests

```bash
npx playwright show-report
npx playwright show-trace trace.zip
npx playwright test tests/e2e/auth.spec.js --debug
```

Add `await page.pause()` inside a test to debug interactively.

### CI/CD

In CI, tests run with:

- Single worker (no parallel execution).
- Two retries per failed test.
- HTML report generation.

Environment variables: `CI=true` and `BASE_URL` (default `http://localhost:8000`).

### Common Issues

- **Django server not starting** — run `python manage.py migrate`; verify port 8000 is free.
- **Authentication failures** — run `python scripts/create_test_user.py` and verify credentials.
- **Timeout errors** — increase timeouts in `playwright.config.js` or wait for dynamic content.
- **Element not found** — use `page.pause()` or `await page.waitForSelector('.selector')`.

### Best Practices

- Use descriptive test names.
- Log in once per suite with `beforeEach`.
- Wait for elements rather than fixed timeouts.
- Prefer `data-testid` or semantic selectors.
- Keep tests independent and clean up database state they modify.
