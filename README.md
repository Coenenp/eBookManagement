# Universal Media Manager

A Django application that prepares a large personal media library (100,000+ books) for import into **BookOrbit**. It scans ebooks, comics, and audiobooks, extracts metadata from files and external APIs, validates it with AI, and renames/organizes files with user-defined naming templates plus embedded OPF metadata. It is **not a reader** — reading, reading status, and library browsing are handled by BookOrbit.

## Documentation Index

| Document                                                     | Purpose                                                                 |
| ------------------------------------------------------------ | ----------------------------------------------------------------------- |
| [`README.md`](README.md)                                     | Installation, usage, architecture, and developer reference (this file). |
| [`FUNCTIONAL_SPECIFICATION.md`](FUNCTIONAL_SPECIFICATION.md) | User-facing behavior of every implemented feature.                      |
| [`ROADMAP.md`](ROADMAP.md)                                   | Planned, partially implemented, and proposed features.                  |
| [`docs/TESTING.md`](docs/TESTING.md)                         | Unit and end-to-end testing guide.                                      |

## Pipeline

1. **Scan** — recursively discover books, comics, and audiobooks.
2. **Recognize (AI, multi-signal)** — fuse filename parsing/cleaning, embedded metadata (EPUB, OPF, ComicInfo, ID3), and OCR (title, author, publisher, ISBN) into structured candidate fields.
3. **Decide (AI)** — the accuracy engine scores each signal and decides whether enough accurate information exists to query external providers.
4. **Enrich + validate (AI)** — query Google Books, Open Library, Goodreads, and Comic Vine only when confidence is high; immediately verify the returned record matches the request (ISBN/title/author) and reject mismatches, then merge through the trust hierarchy and produce a per-book accuracy score.
5. **Rename** — auto-apply the naming template and (re)generate OPF only when the score clears a high-confidence threshold (~99%), covering ~90% of the library unattended.
6. **AI pre-confirmation** — for books below the auto-rename threshold, a heavier agent-driven pass opens the file, OCRs the title page, and cross-checks candidate metadata against a live websearch; it resolves the book with a recorded evidence trail or narrows it to a specific unresolved reason. Corrupted files and duplicate resolution bypass this tier and go straight to step 7.
7. **Verify + confirm (ultrafast, human)** — the remaining books are confirmed, edited, or rejected in a keyboard-driven workbench in seconds each; corrections retrain the AI. This human-only step is the ground truth for retraining, and step 6 exists to shrink its volume.

See [`ROADMAP.md`](ROADMAP.md) for status and [`FUNCTIONAL_SPECIFICATION.md`](FUNCTIONAL_SPECIFICATION.md) for what is already implemented.

## Ultrafast verification & confirmation

The human step is the bottleneck at 100k+ books, so confirmation is optimized for **seconds per book**, not page-by-page editing:

- **Spreadsheet workbench** — every book is a row with suggested vs. current metadata shown as an inline diff.
- **Keyboard-driven** — move with the keyboard, `Enter`/`Y` to confirm, `N`/`Esc` to reject, arrow keys to jump fields; auto-advance to the next unconfirmed book.
- **Bulk confirm** — confirm a whole filtered page (or everything above a confidence threshold) in one action.
- **Inline correction** — fix a single wrong field without leaving the flow; the correction becomes training data.
- **Confirm-to-rename** — confirmed books flow straight into the rename + move step.

## Metadata quality filters

Every filter and statistic is a metadata-quality workbench, not a browsing view. Common examples:

- **Same author** — verify the author name is clean and identical across all books.
- **Series completeness** — find missing volumes and correct series name/numbering.
- **Missing covers** — re-trigger cover extraction/downloads.
- **Missing/incorrect filenames** — target books that still need renaming.
- **Unprocessed enrichment** — e.g. books where the Google Books lookup has not run yet.

The loop is always **filter → correct metadata → rename → move to the final library location**, and every correction becomes training data for the AI.

## Features

### Content Types

- **Ebooks** — EPUB, MOBI, AZW3, and PDF with embedded-metadata and OPF extraction.
- **Comics** — CBR/CBZ with ComicInfo.xml parsing and first-image cover extraction.
- **Audiobooks** — MP3, M4A, M4B, AAC, FLAC, OGG, and WAV as a media section.

### Core Functionality

- Recursive folder scanning with background jobs, progress tracking, resume, and history.
- AI filename recognition with confidence scoring and a user feedback loop.
- Multi-source metadata aggregation from Google Books, Open Library, Goodreads, and Comic Vine.
- Trust-hierarchy conflict resolution (manual edits always win).
- Ultrafast metadata verification workbench (keyboard confirm/reject, bulk accept, inline edit) with cover, file, and duplicate handling.
- Template-based renaming and file organization with OPF metadata generation.
- Series, author, and genre management (including duplicate author detection, name normalization, and fix-all-by-author).
- Cover extraction, caching, manual upload, restore, and internal-cover selection.
- User settings with themes and default renaming templates.
- Setup wizard for first-run configuration.

## Supported Formats

| Content Type | Extensions                                              |
| ------------ | ------------------------------------------------------- |
| Ebooks       | `.epub`, `.mobi`, `.azw`, `.azw3`, `.pdf`               |
| Comics       | `.cbr`, `.cbz`                                          |
| Audiobooks   | `.mp3`, `.m4a`, `.m4b`, `.aac`, `.flac`, `.ogg`, `.wav` |

> FB2, LIT, PRC, CB7, and CBT are declared in the format constants but do not yet have dedicated extractors. OPF files are both parsed as metadata companion files and generated as the metadata handoff to BookOrbit. See [`ROADMAP.md`](ROADMAP.md).

## Requirements

- Python 3.11+ (tested up to 3.13)
- Windows, Linux, or macOS
- 500 MB+ free disk space

Key Python dependencies (see `requirements.txt` for the full list):

- Django 5.2+
- EbookLib (EPUB/AZW3 processing)
- PyPDF2 (PDF processing)
- Pillow (image processing)
- Requests (API calls)
- rarfile (CBR/RAR archives)
- scikit-learn, pandas, scipy (AI filename recognition)

Optional libraries for enhanced functionality:

- `pdf2image` (better PDF cover rendering and OCR rasterization; requires poppler)
- `pytesseract` (OCR for image-based/scanned PDFs; requires the Tesseract binary)
- `unrar` system binary (required with `rarfile` to extract CBR/RAR covers)

## Installation

```bash
git clone https://github.com/Coenenp/eBookManagement.git
cd eBookManagement
python -m venv venv

# Windows
venv\Scripts\activate
# Linux/macOS
source venv/bin/activate

pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Visit `http://127.0.0.1:8000`.

### Database

MariaDB/MySQL is the default database. To use SQLite instead (no external database required), set `USE_SQLITE_TEMPORARILY=True` in `.env`. `mysqlclient` is included in `requirements.txt`.

## Usage

### First Run

1. Complete the setup wizard (`/wizard/`) to add library folders, assign content types, and select scrapers.
2. Start a scan from the dashboard or the scanning page.

### Scanning

Scans run in the background and can be monitored, cancelled, and resumed.

- **Quick scan** — discovers new/changed/removed files and extracts local metadata without calling external APIs.
- **Deep scan** — everything in a quick scan, plus external metadata and cover lookups.
- **Rescan** — re-query external sources for existing books.

### Management Commands

```bash
# Background scanning
python manage.py scan_books scan /path/to/books --language en --background --wait
python manage.py scan_books scan /path/to/books --resume
python manage.py scan_books rescan --all --background
python manage.py scan_books status --job-id <job_id>
python manage.py scan_books list
python manage.py scan_books cancel <job_id>

# Metadata and maintenance
python manage.py enrich_metadata
python manage.py train_ai_models --include-seed
python manage.py scan_content_isbn

# Author data quality
python manage.py clean_authors --dry-run --all
python manage.py clean_authors --remove-invalid
python manage.py clean_authors --merge-duplicates
python manage.py clean_authors --find-fuzzy-duplicates --fuzzy-threshold 0.85
python manage.py normalize_authors --dry-run

# Cover cache maintenance
python manage.py clean_cover_cache --dry-run
python manage.py clean_cover_cache --rebuild-missing

# Test utilities
python manage.py create_test_superuser
```

## Configuration

Create a `.env` file in the project root:

```env
DEBUG=True
SECRET_KEY=your-secret-key-here

# Database
# The default engine is MariaDB/MySQL. Set USE_SQLITE_TEMPORARILY=True to use
# SQLite instead (no external database required).
USE_SQLITE_TEMPORARILY=True

# MariaDB/MySQL connection (used when USE_SQLITE_TEMPORARILY is False or unset)
DB_NAME=ebook_manager
DB_USER=ebook_user
DB_PASSWORD=your_password
DB_HOST=localhost
DB_PORT=3306

# OCR for image-based/scanned PDFs (optional)
PDF_OCR_ENABLED=True
PDF_OCR_DPI=300
TESSERACT_CMD=  # e.g. C:\Program Files\Tesseract-OCR\tesseract.exe
```

Caching uses Django's file-based cache backend (stored in `cache_storage/`) and needs no configuration.

Google Books and Open Library are queried automatically without API keys. Optional `GOOGLE_BOOKS_API_KEY` and `COMICVINE_API_KEY` values raise rate limits; Goodreads enrichment requires an `APIFY_API_TOKEN`.

## Architecture

### Django Apps

- **books** — models, views, scanner, extractors, and templates.
- **ebook_manager** — project settings and root URL configuration.

### Key Models

- [`Book`](books/models.py:350) — a single work with a content type (`ebook`, `comic`, `audiobook`).
- [`BookFile`](books/models.py:545) — one file of a work, including cover fields.
- [`FinalMetadata`](books/models_metadata.py:13) — consolidated, user-reviewable metadata.
- Source-attributed metadata: `BookTitle`, `BookAuthor`, `BookSeries`, `BookGenre`, `BookPublisher`, `BookCover`, `BookMetadata`.
- [`DataSource`](books/models.py:82) — metadata sources with trust levels.
- [`Author`](books/models.py:628), [`Series`](books/models.py:775), [`Genre`](books/models.py:817), [`Publisher`](books/models.py:915).
- [`ScanQueue`](books/models_operations.py:530) and [`ScanHistory`](books/models_operations.py:65) — background scan scheduling and results.
- [`AIFeedback`](books/models_operations.py:235) — AI prediction feedback for retraining.
- [`UserProfile`](books/models_operations.py:303) — themes and renaming preferences.

### Metadata Trust Hierarchy

When sources disagree, the highest-trust value wins:

| Priority | Source              | Trust |
| -------- | ------------------- | ----- |
| 1        | Manual Entry        | 1.0   |
| 2        | Open Library        | 0.95  |
| 3        | Comic Vine          | 0.9   |
| 4        | OPF File            | 0.9   |
| 5        | ISBN Content Scan   | 0.85  |
| 6        | EPUB                | 0.8   |
| 7        | MOBI                | 0.75  |
| 8        | Google Books        | 0.7   |
| 9        | Open Library Covers | 0.65  |
| 10       | PDF                 | 0.6   |
| 11       | Google Books Covers | 0.55  |
| 12       | Initial Scan        | 0.2   |

### External APIs

- **Google Books** — metadata and covers.
- **Open Library** — metadata and covers (also author enrichment).
- **Goodreads** — metadata and covers (via the Apify Goodreads scraper).
- **Comic Vine** — comic metadata and creator information.

API responses are cached, rate-limited, and backed off automatically.

## Cover System Developer Reference

The cover system extracts internal covers during scanning and caches them in `MEDIA_ROOT/cover_cache/`. External companion files (`book.jpg` next to `book.epub`) take priority.

### Source Types

| Type            | Meaning                                  |
| --------------- | ---------------------------------------- |
| `external`      | Companion file next to the book          |
| `epub_internal` | Cover extracted from an EPUB             |
| `pdf_page`      | First page of a PDF rendered as an image |
| `archive_first` | First image in a CBZ/CBR                 |
| `mobi_internal` | Cover extracted from a MOBI              |
| `manual`        | User-uploaded cover                      |

### Key Fields on `BookFile`

```python
cover_path          # path to the cover (external or cached)
cover_source_type   # one of the source types above
cover_internal_path # path within the EPUB/archive
has_internal_cover  # quick existence flag
cover_quality_score # 0-100 quality score (manual uploads)
original_cover_path # pre-upload cover, for restore
```

### Python API

```python
from books.utils.cover_extractor import EPUBCoverExtractor
from books.utils.cover_cache import CoverCache

# Extract and cache
cover_data, internal_path = EPUBCoverExtractor.extract_cover('/path/book.epub')
success, cache_path = CoverCache.save_cover('/path/book.epub', cover_data, internal_path)

# Cache management
CoverCache.has_cover('/path/book.epub', internal_path)
CoverCache.get_cover('/path/book.epub', internal_path)
CoverCache.delete_cover('/path/book.epub', internal_path)
CoverCache.clear_all()
CoverCache.get_cache_size()
```

### Template Tag

```django
{% load book_extras %}
<img src="{% get_book_cover_url book.primary_file %}" alt="{{ book.title }}">
<img src="{% get_book_cover_url book.primary_file default='/static/img/no-cover.jpg' %}" alt="{{ book.title }}">
```

## Project Structure

```text
eBookManagement/
├── books/
│   ├── models.py                # core models and constants
│   ├── models_metadata.py       # FinalMetadata model
│   ├── models_operations.py     # ScanQueue, ScanHistory, AIFeedback, UserProfile
│   ├── views/                   # view modules (core, metadata, ajax, etc.)
│   ├── views.py                 # backward-compatible view re-exports
│   ├── mixins/                  # reusable view mixins
│   ├── services/                # business logic (e.g. author_cleanup)
│   ├── analytics/               # dashboard metrics
│   ├── queries/                 # query helpers
│   ├── templatetags/            # template tags and filters
│   ├── urls.py                  # URL routing
│   ├── scanner/                 # scanning engine and format extractors
│   │   ├── background.py        # BackgroundScanner, the single scan engine
│   │   ├── external.py          # external API integration
│   │   ├── ai/                  # AI filename recognition
│   │   └── extractors/          # epub, mobi, pdf, opf, comic, comicvine
│   ├── utils/                   # cover_cache, cover_extractor, isbn, language, etc.
│   ├── templates/               # HTML templates
│   ├── static/book/             # CSS/JS assets
│   ├── management/commands/     # CLI commands
│   └── tests/                   # unit and integration tests
├── ebook_manager/               # Django project settings
├── tests/e2e/                   # Playwright end-to-end tests
├── docs/TESTING.md              # testing guide
├── manage.py
├── requirements.txt
├── ROADMAP.md
└── FUNCTIONAL_SPECIFICATION.md
```

## Testing

Tests run on a dedicated file-based SQLite database via [`ebook_manager/settings_test.py`](ebook_manager/settings_test.py), so they never touch the live MariaDB/MySQL database. See [`docs/TESTING.md`](docs/TESTING.md) for unit and Playwright E2E instructions.

```bash
python manage.py test books.tests
# or
pytest
```

## Troubleshooting

- **CBR errors**: install `rarfile` and the `unrar` system package.
- **PDF covers low quality**: install `pdf2image` and poppler.
- **Scanned PDFs not recognized (no ISBN/metadata)**: install `pytesseract`, the Tesseract OCR binary, `pdf2image`, and poppler, then set `PDF_OCR_ENABLED=True` (and `TESSERACT_CMD` on Windows) in `.env`.
- **Cache errors during scanning**: the file-based cache lives in `cache_storage/`; clear that directory and retry.
- **MySQL "key too long"**: shorten very long file paths or switch to SQLite.
- **Covers missing**: run a deep scan to re-extract and download covers.
- **Scan stuck**: check the scanning dashboard, cancel the job, and restart.

## License

This project is open source. Use, modify, and distribute as needed.
