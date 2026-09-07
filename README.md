# Universal Media Manager

A Django application for scanning, cataloging, and organizing a personal media library. It handles ebooks, comics, and audiobooks: extracting metadata from files and external APIs, resolving conflicts with a trust hierarchy, and reorganizing files with user-defined naming templates.

## Documentation Index

| Document                                                     | Purpose                                                                 |
| ------------------------------------------------------------ | ----------------------------------------------------------------------- |
| [`README.md`](README.md)                                     | Installation, usage, architecture, and developer reference (this file). |
| [`FUNCTIONAL_SPECIFICATION.md`](FUNCTIONAL_SPECIFICATION.md) | User-facing behavior of every implemented feature.                      |
| [`ROADMAP.md`](ROADMAP.md)                                   | Planned, partially implemented, and proposed features.                  |
| [`docs/TESTING.md`](docs/TESTING.md)                         | Unit and end-to-end testing guide.                                      |

## Features

### Content Types

- **Ebooks** — EPUB, MOBI, AZW3, and PDF with embedded-metadata and OPF extraction.
- **Comics** — CBR/CBZ with ComicInfo.xml parsing and first-image cover extraction.
- **Audiobooks** — MP3, M4A, M4B, AAC, FLAC, OGG, and WAV as a media section.

### Core Functionality

- Recursive folder scanning with background jobs, progress tracking, resume, and history.
- AI filename recognition with confidence scoring and a user feedback loop.
- Multi-source metadata aggregation from Google Books, Open Library, and Comic Vine.
- Trust-hierarchy conflict resolution (manual edits always win).
- Unified metadata review workflow with cover, file, and duplicate handling.
- Template-based renaming and file organization with OPF metadata generation.
- Series, author, and genre management (including duplicate author detection).
- Cover extraction, caching, manual upload, restore, and internal-cover selection.
- User settings with themes and default renaming templates.
- Setup wizard for first-run configuration.

## Supported Formats

| Content Type | Extensions                                              |
| ------------ | ------------------------------------------------------- |
| Ebooks       | `.epub`, `.mobi`, `.azw`, `.azw3`, `.pdf`, `.opf`       |
| Comics       | `.cbr`, `.cbz`                                          |
| Audiobooks   | `.mp3`, `.m4a`, `.m4b`, `.aac`, `.flac`, `.ogg`, `.wav` |

> FB2, LIT, PRC, CB7, and CBT are declared in the format constants but do not yet have dedicated extractors. See [`ROADMAP.md`](ROADMAP.md).

## Requirements

- Python 3.8–3.12 (tested up to 3.13)
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

- `pdf2image` (better PDF cover rendering; requires poppler)
- `rarfile` (CBR cover extraction; requires unrar)

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

SQLite is the default and needs no configuration. For large collections, MySQL/MariaDB is supported by setting environment variables (see [Configuration](#configuration)) and installing `mysqlclient`.

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
python manage.py scan_books rescan --all --background
python manage.py scan_books status --job-id <job_id>
python manage.py scan_books list
python manage.py scan_books cancel <job_id>

# Metadata and maintenance
python manage.py complete_metadata
python manage.py train_ai_models
python manage.py scan_content_isbn
python manage.py scan_ebooks

# Author data quality
python manage.py clean_authors --dry-run --all
python manage.py clean_authors --remove-invalid
python manage.py clean_authors --merge-duplicates
python manage.py clean_authors --find-fuzzy-duplicates --fuzzy-threshold 0.85

# Test utilities
python manage.py create_test_superuser
```

## Configuration

Create a `.env` file in the project root:

```env
DEBUG=True
SECRET_KEY=your-secret-key-here
ALLOWED_HOSTS=localhost,127.0.0.1

# Database (optional; defaults to SQLite)
USE_SQLITE_TEMPORARILY=True
DB_NAME=ebook_manager
DB_USER=ebook_user
DB_PASSWORD=your_password
DB_HOST=localhost
DB_PORT=3306

# Cache (optional; defaults to local memory)
CACHE_BACKEND=locmem
```

Cache backends: `locmem` (default), `memcached`, or `redis`.

External APIs are used automatically and require no API keys for basic functionality. Optional keys raise rate limits for Google Books and Comic Vine.

## Architecture

### Django Apps

- **books** — models, views, scanner, extractors, and templates.
- **ebook_manager** — project settings and root URL configuration.

### Key Models

- [`Book`](books/models.py:353) — a single work with a content type (`ebook`, `comic`, `audiobook`).
- [`BookFile`](books/models.py:548) — one file of a work, including cover fields.
- [`FinalMetadata`](books/models.py:987) — consolidated, user-reviewable metadata.
- Source-attributed metadata: `BookTitle`, `BookAuthor`, `BookSeries`, `BookGenre`, `BookPublisher`, `BookCover`, `BookMetadata`.
- [`DataSource`](books/models.py:85) — metadata sources with trust levels.
- [`Author`](books/models.py:631), [`Series`](books/models.py:778), [`Genre`](books/models.py:820), [`Publisher`](books/models.py:918).
- [`ScanQueue`](books/models.py:1922) and [`ScanHistory`](books/models.py:1459) — background scan scheduling and results.
- [`AIFeedback`](books/models.py:1629) — AI prediction feedback for retraining.
- [`UserProfile`](books/models.py:1697) — themes and renaming preferences.

### Metadata Trust Hierarchy

When sources disagree, the highest-trust value wins:

| Priority | Source        | Trust |
| -------- | ------------- | ----- |
| 1        | Manual entry  | 1.0   |
| 2        | Open Library  | 0.95  |
| 3        | OPF file      | 0.9   |
| 4        | Content scan  | 0.85  |
| 5        | EPUB internal | 0.8   |
| 6        | MOBI internal | 0.75  |
| 7        | Google Books  | 0.7   |
| 8        | PDF internal  | 0.6   |
| 9        | Filename      | 0.2   |

### External APIs

- **Google Books** — metadata and covers.
- **Open Library** — metadata and covers (also author enrichment).
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
ebook_library_manager/
├── books/
│   ├── models.py                # database models
│   ├── views.py                 # main views and AJAX endpoints
│   ├── urls.py                  # URL routing
│   ├── scanner/                 # scanning engine and format extractors
│   │   ├── scanner_engine.py
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
├── ROADMAP.md
└── FUNCTIONAL_SPECIFICATION.md
```

## Testing

See [`docs/TESTING.md`](docs/TESTING.md) for unit and Playwright E2E instructions.

```bash
python manage.py test books.tests
```

## Troubleshooting

- **CBR errors**: install `rarfile` and the `unrar` system package.
- **PDF covers low quality**: install `pdf2image` and poppler.
- **Cache connection errors during scanning**: set `CACHE_BACKEND=locmem` in `.env`.
- **MySQL "key too long"**: long file paths are limited to 191 chars; shorten paths or use SQLite/PostgreSQL.
- **Covers missing**: run a deep scan to re-extract and download covers.
- **Scan stuck**: check the scanning dashboard, cancel the job, and restart.

## License

This project is open source. Use, modify, and distribute as needed.
