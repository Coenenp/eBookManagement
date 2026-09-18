# Functional Specification

This document describes the implemented, user-facing behavior of the Universal Media Manager. Planned or partial features live in [`ROADMAP.md`](ROADMAP.md).

## Table of Contents

1. [System Overview](#system-overview)
2. [User Interface and Navigation](#user-interface-and-navigation)
3. [Core Features and Workflows](#core-features-and-workflows)
    - [1. Setup Wizard and Configuration](#1-setup-wizard-and-configuration)
    - [2. File Import and Scanning](#2-file-import-and-scanning)
    - [3. Metadata Management](#3-metadata-management)
    - [4. Book Renaming and Organization](#4-book-renaming-and-organization)
    - [5. Series Management](#5-series-management)
    - [6. Cover Image Management](#6-cover-image-management)
    - [7. Author Management](#7-author-management)
    - [8. Genre Management](#8-genre-management)
    - [9. Search and Filtering](#9-search-and-filtering)
    - [10. Data Sources and Trust Management](#10-data-sources-and-trust-management)
    - [11. AI Filename Recognition](#11-ai-filename-recognition)
    - [12. Background Processing and Task Management](#12-background-processing-and-task-management)
    - [13. Error Handling and Recovery](#13-error-handling-and-recovery)
    - [14. System Configuration and Customization](#14-system-configuration-and-customization)
4. [Data Flow and Integration](#data-flow-and-integration)
5. [Security and Data Protection](#security-and-data-protection)
6. [Performance and Scalability](#performance-and-scalability)

---

## System Overview

The system catalogs and organizes digital media in three content types: **ebooks**, **comics**, and **audiobooks**. It scans directories, extracts metadata from file contents and external APIs, resolves conflicts using a trust hierarchy, and reorganizes files with user-defined naming patterns.

### Core Principles

- **Multi-source metadata aggregation** with confidence scoring.
- **Non-destructive operations** with rollback and audit logging.
- **Background processing** for long-running scans.
- **User review** before destructive file actions.

### Supported Formats

| Content Type | Extracted Metadata                 | Notes                                  |
| ------------ | ---------------------------------- | -------------------------------------- |
| Ebooks       | EPUB, MOBI, AZW3, PDF              | OPF companion files also parsed        |
| Comics       | CBR, CBZ                           | ComicInfo.xml and first-image covers   |
| Audiobooks   | MP3, M4A, M4B, AAC, FLAC, OGG, WAV | Content-type section and file grouping |

AZW, FB2, LIT, PRC, CB7, and CBT are declared in the format constants but have no dedicated extractor yet; see [`ROADMAP.md`](ROADMAP.md).

---

## User Interface and Navigation

The interface uses a top authentication bar and a set of content pills.

### Top Authentication Bar

- **Brand/logo** — links to the dashboard.
- **Authenticated user menu** — profile, settings, dashboard, sign out.
- **Unauthenticated** — sign in and sign up.

### Main Navigation

| Item         | URL              | Purpose                                   |
| ------------ | ---------------- | ----------------------------------------- |
| Dashboard    | `/dashboard/`    | Activity, scan status, statistics         |
| Library      | `/books/`        | Combined view across all content types    |
| Ebooks       | `/ebooks/`       | Ebook-specific list, filter, and download |
| Series       | `/series/`       | Series browsing and management            |
| Comics       | `/comics/`       | Comic list, filter, and download          |
| Audiobooks   | `/audiobooks/`   | Audiobook list, filter, and download      |
| Authors      | `/authors/`      | Author browsing and management            |
| Rename Books | `/rename-books/` | Bulk file organization                    |
| Scanning     | `/scanning/`     | Scan dashboard and background tasks       |

The **Management** dropdown groups administrative functions: authors, genres, data sources, scan folders, API status, rename books, and AI feedback.

### Content Type Organization

A content type is assigned at the scan-folder level and drives how files are processed and where they appear. A PDF in a "Comics" folder is treated as a comic; the same file in an "Ebooks" folder is treated as an ebook.

---

## Core Features and Workflows

### 1. Setup Wizard and Configuration

Guides first-time users through library setup.

**Entry points:** `/wizard/`, `/wizard/welcome/`, `/wizard/folders/`, `/wizard/content-types/`, `/wizard/scrapers/`, `/wizard/complete/`.

**Steps:**

1. Welcome.
2. Select library root folders and assign languages.
3. Assign a content type to each folder.
4. Configure scrapers (optional).
5. Complete — creates `ScanFolder` records and queues initial deep scans.

**Behavior:**

- Invalid paths show a specific error; network issues warn but allow continuation.
- The wizard can be resumed or skipped at any step.
- No files are moved or modified during setup.

---

### 2. File Import and Scanning

Discovers files, extracts metadata, and imports them into the library.

**Entry points:** `/scanning/`, `/scanning/start-folder/`, `/scanning/start-rescan/`, and the setup wizard.

The single command-line scanning entry point is [`scan_books`](books/management/commands/scan_books.py), with `scan`, `rescan`, `status`, `list`, and `cancel` subcommands. `scan --resume` continues an interrupted scan and completes metadata for books that were never fully processed.

#### Scan Types

| Type                  | File Discovery | Metadata Extraction | External APIs | Resume |
| --------------------- | -------------- | ------------------- | ------------- | ------ |
| Initial / wizard scan | Yes            | Yes                 | Yes           | Yes    |
| Quick scan            | Yes            | Yes (local only)    | No            | Yes    |
| Deep scan             | Yes            | Yes                 | Yes           | Yes    |

- **Quick scan** finds new/changed/removed files and extracts local metadata (filename, EPUB/MOBI/PDF internals, OPF). It does not call external APIs.
- **Deep scan** adds external metadata, cover downloads, and author enrichment.

#### Process

1. Recursively traverse each `ScanFolder`.
2. Detect supported files and compute a file-path hash for uniqueness.
3. Create or update `Book` and `BookFile` records.
4. Extract embedded metadata and generate an initial `FinalMetadata` record.
5. Queue external lookups (deep scan only).
6. Detect duplicates and soft-delete files that disappeared.

#### File Change Detection

- **New files** — create book records.
- **Removed files** — soft-delete book records.
- **Reappearing files** — reactivate soft-deleted books.
- **Modified files** — update file metadata.

**Guarantees:** original files are never modified during scanning; failed files do not block the rest of the scan; scans can be interrupted and resumed.

---

### 3. Metadata Management

Provides a single-page workflow for reviewing and finalizing metadata.

**Entry points:** `/book/<id>/metadata/`, `/book/<id>/metadata/?workflow=1`, and `/ajax/rescan-external-metadata/`.

**Sections:**

1. **Metadata review** — radio-button selection per field (title, author, series, genre, publisher, language, year) with confidence scores and source attribution.
2. **Cover selection** — grid of all covers with quality and source info (see [Cover Image Management](#6-cover-image-management)).
3. **File operations** — rename/move configuration with live preview and template selection.
4. **Duplicate detection** — compare and merge/keep duplicates.
5. **External metadata refresh** — select sources and rescan.

**Workflow mode** (`?workflow=1`) adds previous/next navigation for rapid batch review.

**Aggregation rules:**

- Manual entries receive the highest confidence and always win.
- Fields are aggregated from the most trusted source.
- Source records are preserved for transparency; final values are denormalized into `FinalMetadata`.

---

### 4. Book Renaming and Organization

Renames and reorganizes files using user-defined templates.

**Entry points:** `/rename-books/`, `/rename-books/templates/`, `/settings/`, `/book/<id>/metadata/`.

#### Templates

Predefined templates:

- Comprehensive: `${author.sortname}/${bookseries.title}/${title}.${ext}`
- Author-Title: `${author.sortname}/${title}.${ext}`
- Title Only: `${title}.${ext}`
- Series Focused: `${bookseries.title}/${bookseries.title} ${bookseries.number} - ${title}.${ext}`
- Year-Author: `${publicationyear}/${author.sortname}/${title}.${ext}`
- Genre Organization: `${genre}/${author.sortname}/${title}.${ext}`

Available tokens: `${title}`, `${author}`, `${author.sortname}`, `${series}`, `${series_number}`, `${bookseries.title}`, `${bookseries.number}`, `${year}` / `${publicationyear}`, `${genre}`, `${ext}`, `${publisher}`.

Custom templates are stored in `UserProfile.saved_patterns` and managed at `/rename-books/templates/`.

#### Process

1. Process template tokens and sanitize filesystem-unsafe characters.
2. Detect destination conflicts.
3. Move files atomically and handle companion files (covers, OPF, NFO).
4. Update database paths.
5. Record a `FileOperation` for audit and reversal.

#### OPF Generation

Renaming generates an OPF metadata file next to the book, containing title, author, publisher, language, year, ISBN, series, description, and confidence metrics. This is Calibre-compatible.

**Guarantees:** previews show exact results before execution; operations are logged and reversible; no metadata is lost during renaming.

---

### 5. Series Management

Groups books into ordered series.

**Entry points:** `/series/`, `/series/<id>/`, `/ajax/series-detail/`, and book-level assignment in metadata.

- Detects series from metadata, title patterns, and external sources.
- Supports numeric ordering (including decimals for novellas/prequels).
- Tracks series metadata and reading order.

---

### 6. Cover Image Management

Manages cover images from internal extraction, external download, and manual upload.

**Entry points:** `/ajax/book/<id>/manage_cover/`, `/ajax/book/<id>/upload_cover/`, `/ajax/bookfile/<id>/upload_cover/`, `/ajax/bookfile/<id>/restore_cover/`.

#### Cover Sources and Priority

1. **External companion** (`book.jpg` next to `book.epub`) — highest priority.
2. **EPUB internal** — OPF reference, common paths, then first image.
3. **PDF first page** — rendered at 150 DPI.
4. **Archive first image** — first image (alphabetically) from CBR/CBZ.
5. **Manual upload** — user-provided, stored with `manual` source type.

#### Unified Cover Selection

The cover grid shows all covers from every source and supports two actions:

- **Radio button** — select one final cover; stores `FinalMetadata.final_cover_path`.
- **Checkbox** — download one or more external covers to local storage.

#### Manual Upload and Restore

- Validates formats (JPG, PNG, WebP), size (≤ 5 MB), and dimensions.
- Calculates a 0–100 quality score (resolution, aspect ratio, file size).
- Preserves the original cover for one-click restore.

#### EPUB Image Cleanup

When embedding metadata into an EPUB, an optional "remove unused images" flag deletes orphaned images not referenced in the OPF manifest, reducing file size.

#### Cover State Propagation

1. User selects a final cover and (optionally) enables cleanup.
2. The metadata view saves `FinalMetadata.final_cover_path`.
3. On rename, `BatchRenamer` retrieves the selected cover.
4. `embed_metadata_in_epub` copies the selected cover into the EPUB and updates the OPF manifest.
5. If cleanup is enabled, orphaned images are removed.
6. The resulting EPUB contains the selected cover and updated metadata.

If the selected cover file is missing, the operation continues without a cover rather than failing.

#### Cover Cache Robustness

- Cache naming is idempotent — saving the same cover twice overwrites the canonical `cover_cache/<hash>.jpg` instead of appending a random suffix.
- When a cached cover file is missing, the UI falls back to a placeholder image instead of emitting a 404.
- `CoverCache.cleanup_orphans()` removes cached files no longer referenced by any `BookFile`.

---

### 7. Author Management

Provides author data-quality controls, duplicate detection, and external enrichment.

**Entry points:** `/authors/`, `/authors/duplicates/`, `/authors/merge/`, `/authors/<id>/profile/`, `/authors/<id>/enrich/`.

#### Data Validation

Rejects invalid author data: years as names, birth/death dates, single-letter names, and empty/malformed names.

Automatic cleaning removes:

- Trailing dates (`Bunting, Michael, 1973-` → `Bunting, Michael`).
- Date ranges (`Dubos, René J. (René Jules), 1901-1982` → `Dubos, René J. (René Jules)`).
- Trailing punctuation and extra whitespace.

#### Fuzzy Duplicate Detection

Uses `difflib.SequenceMatcher`, initials matching, name-reversal detection, and case-insensitive comparison with a configurable threshold (default 0.85).

#### Merge

From `/authors/duplicates/`, select two or more authors plus a primary author to merge; `BookAuthor` relationships are re-pointed to the primary and the merged authors are removed.

#### Profile Enrichment

Fetches biography, photo, birth/death dates, and Wikipedia links from Open Library (primary) with Google Books as fallback. Results are cached (30 days success, 7 days negative).

#### Management Command

```bash
python manage.py clean_authors --dry-run --all
python manage.py clean_authors --remove-invalid
python manage.py clean_authors --clean-names
python manage.py clean_authors --merge-duplicates
python manage.py clean_authors --find-fuzzy-duplicates --fuzzy-threshold 0.85
```

---

### 8. Genre Management

Provides genre browsing, bulk deletion, and review marking.

**Entry points:** `/genres/`, `/genres/bulk-delete/`, `/genres/mark-reviewed/`, `/genres/<id>/delete/`.

---

### 9. Search and Filtering

**Entry points:** `/books/`, `/ajax/search-books/`, and content-type-specific AJAX list endpoints.

- Text search across title, author, and description.
- Filters for format, genre, language, publication year, and content type.
- Sorting and pagination with preserved search state.

Search is read-only and never modifies data.

---

### 10. Data Sources and Trust Management

**Entry points:** `/data_sources/`, `/data_sources/<id>/update/`, `/data_sources/<id>/update_trust/`.

- Tracks `DataSource` trust levels (0.0–1.0) and priorities.
- Resolves conflicting metadata using the trust hierarchy (see [README](README.md#metadata-trust-hierarchy)).
- Manual overrides always take highest priority.

---

### 11. AI Filename Recognition

Extracts title, author, series, and volume from filenames when embedded metadata is unavailable.

- Uses a `RandomForestClassifier` with TF-IDF text vectorization and engineered filename features.
- Produces confidence scores for every prediction.
- Stores user corrections in `AIFeedback` for retraining via `python manage.py train_ai_models`.

**Entry points:** `/ai-feedback/`, `/ajax/book/<id>/ai-feedback/`, `/ajax/ai/retrain/`, `/ajax/ai/status/`.

---

### 12. Background Processing and Task Management

**Entry points:** `/scanning/`, `/scanning/queue/`, `/scanning/cancel/<job_id>/`.

- Scans and metadata operations run in the background without blocking the UI.
- `ScanQueue` schedules jobs with priority, retry, and status tracking.
- `ScanHistory` records outcomes, timings, and API usage.
- Progress is reported via AJAX polling; jobs can be cancelled and resumed.

---

### 13. Error Handling and Recovery

The system degrades gracefully and preserves data:

- **File system errors** — pre-operation validation and retry; no data loss.
- **Database errors** — connection pooling and transaction integrity.
- **External API failures** — fallback to cached/internal data and alternative sources.
- **Data consistency issues** — soft deletes, audit logs, and reversible corrections.

All destructive operations validate before executing and record a reversible audit entry.

---

### 14. System Configuration and Customization

**Entry point:** `/settings/`.

- **Renaming templates** — select a default, preview patterns, and toggle companion files.
- **Themes** — 26 Bootswatch themes with instant preview.
- **Display options** — items per page and table/grid view mode.
- **Language and user preferences.**

System-level configuration uses environment variables (see [README](README.md#configuration)).

---

## Data Flow and Integration

### Import → Metadata → Organization

1. Scanning creates basic book records.
2. Background enhancement populates detailed metadata.
3. Renaming uses finalized metadata for organization.

### Source → Quality Loop

1. Sources provide metadata with confidence scores.
2. User feedback adjusts trust.
3. Improved trust improves future metadata quality.

### Cache Management

- Local memory cache by default; Memcached/Redis optional.
- API responses cached to reduce external calls.
- Cover images cached permanently in `MEDIA_ROOT/cover_cache/`.
- Rate-limit state persists across restarts.

---

## Security and Data Protection

- Session-based authentication with configurable timeouts.
- CSRF protection on all state-changing operations.
- Input validation and file-path validation to prevent directory traversal.
- Metadata sanitization to prevent XSS and injection.
- Soft deletes preserve audit history.

---

## Performance and Scalability

- Indexed fields for common search and filter patterns.
- Efficient directory traversal with minimal file I/O.
- AJAX operations for real-time updates and progressive loading.
- Background processing for resource-intensive operations.
- Cached covers and API responses reduce repeated work.
