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

The system catalogs and organizes digital media in three content types: **ebooks**, **comics**, and **audiobooks**. It scans directories, extracts metadata from supported file formats and external APIs, verifies external matches, resolves source records into reviewable final metadata, and organizes approved files with naming patterns.

### Core Principles

- **Multi-source metadata aggregation** with source agreement, confidence, completeness, and accuracy signals.
- **Journaled file moves** with staged verification, recovery, and audit history on the approved-move path.
- **Background scanning** with progress and scan history; jobs currently run in process and are not durable across web-process restarts.
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

The primary command-line scan entry point is [`scan_books`](books/management/commands/scan_books.py), with `scan`, `rescan`, `status`, `list`, and `cancel` subcommands. Resume and rescan are different operations: resume continues an interrupted folder scan from its saved progress checkpoint; rescan deliberately processes existing books or a folder again. Background scans currently run in-process, so the worker itself does not survive a web-process restart. A saved checkpoint can be used to resume manually, but this is not durable job execution or automatic restart recovery.

#### Scan Types

| Type                  | File Discovery | Metadata Extraction | External APIs | Resume |
| --------------------- | -------------- | ------------------- | ------------- | ------ |
| Initial / wizard scan | Yes            | Yes                 | Yes           | Yes    |
| Quick scan            | Yes            | Yes (local only)    | No            | Yes    |
| Deep scan             | Yes            | Yes                 | Yes           | Yes    |

- **Quick scan** finds new/changed/removed files and extracts local metadata (filename, EPUB/MOBI/PDF internals, OPF). It does not call external APIs.
- **Deep scan** adds external metadata, cover downloads, and author enrichment.

#### Resume and Rescan

- **Resume an interrupted scan** — continue the same folder scan after its last recorded file checkpoint, completing metadata for incomplete books first. Resume is not a fresh scan and should not reset completed metadata. Current recovery is best-effort and must be requested; the in-process background thread is not restart-safe.
- **Rescan selected book IDs** — re-extract file metadata and, when enabled, query external metadata for those books, then resolve final metadata again. The intended reset is to rebuild source-derived metadata for the selected books, not to apply folder-level file discovery or missing-file cleanup. Current ID-based code re-extracts and resolves, but does not fully clear old source records first; reviewed final metadata is protected from automatic resolution.
- **Rescan a folder** — traverse the folder and apply the file-change detection behavior below, including handling files that are new, modified, missing, or reappearing. This is distinct from selecting a fixed set of existing book IDs.

The web folder-rescan workflow uses the folder traversal path. There is an entry-point inconsistency to resolve: `scan_books rescan --folder` currently collects book IDs and dispatches the ID-based rescan rather than the folder traversal path. Until unified, those two folder-rescan entry points do not have identical behavior.

#### Process

1. Recursively traverse each `ScanFolder`.
2. Detect supported files and compute a file-path hash for uniqueness.
3. Create or update `Book` and `BookFile` records.
4. Extract supported embedded and filename metadata and resolve available source records into `FinalMetadata`.
5. Query external sources inline when enabled by the scan configuration; returned candidates are match-verified before persistence.
6. During a folder rescan, reconcile missing and reappearing files using the scan cleanup path. A book-ID rescan does not perform folder-wide missing-file detection. Duplicate identification is a separate review/move concern.

#### File Change Detection

- **New files** — create book records.
- **Removed files** — soft-delete book records.
- **Reappearing files** — reactivate soft-deleted books.
- **Modified files** — update file metadata.

**Behavior:** scanning reads source files and records extracted metadata; it does not rename or reorganize them. Individual file failures are logged and scanning generally continues. Resume is checkpointed continuation, not a rescan; background execution is not durable across process restarts, so interruption requires a manual, best-effort resume.

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

- Reviewed `FinalMetadata` is protected from ordinary source synchronization.
- Title and author candidates use source-agreement voting across independent source groups; EPUB and OPF are treated as one embedded source, and an `Initial Scan` value cannot win when another source group has a candidate.
- Other fields use field-specific selection, often confidence ordering. `overall_confidence`, `completeness_score`, and `accuracy_score` measure different things; the accuracy score is a deterministic evidence-agreement heuristic, not a calibrated AI probability.
- External records are checked against the query before persistence. The accuracy score does not currently gate external lookups or trigger automatic renaming.
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

#### Current Entry Points

1. **Template renamer UI** — previews and batch operations use `RenamingEngine` and `BatchRenamer`. This path applies templates, sanitizes paths, and attempts collision handling for destinations already on disk. It updates the primary file path and has its own EPUB-embedding and companion-file handling.
2. **Approved move workflow** — `approve_batch` creates/applies a criteria-based approval manifest; it does not move files. `move_approved` is dry-run by default and, with `--execute`, sends eligible reviewed books through `safe_move_book`. This path journals each move, stages and verifies file content, updates database paths, synchronizes EPUB metadata, and processes companion files. Use `recover_file_moves` to inspect or apply recovery for interrupted operations.

These are currently separate implementations with different collision, companion, cover, metadata, and rollback behavior. The template batch planner does not reserve destinations across all books in a batch, and it does not provide the safe-move journal and recovery guarantees. The approved move workflow currently requires a valid selected cover and can leave an item in `needs_review`.

#### Required Unified Rename and Move Behavior

All rename/move entry points—single-book UI, batch UI, API, management command, approval workflow, and future background jobs—must use the same destination planner and file-operation engine. The UI and command layers may orchestrate selection, preview, approval, progress, and reporting, but must not implement separate path planning, collision handling, EPUB synchronization, or file movement. The shared engine must reserve destinations across a batch, journal and verify every operation, and provide consistent rollback/recovery behavior.

The batch UI must let users create a batch, preview it, execute it, monitor progress, and inspect/control each item. It must expose item outcomes such as pending, moved, `needs_review`, failed, and skipped, with the reason and recovery action where applicable. A `needs_review` item must remain visible and actionable; it must not be reported as successfully moved.

Every EPUB rename/move through this engine must embed the selected curated metadata and cover, and regenerate or update the companion OPF when one is managed. Cover or metadata validation failures must be surfaced as an item-level review/failure, not silently omitted. These requirements replace the current path-specific embedding behavior.

Metadata review must display the trust and evidence used to resolve each field accurately. A user-entered manual override must take precedence over source-derived values. This remains true after the file has been moved: users must be able to edit and save metadata for an already-moved book, and the shared engine must synchronize the EPUB and OPF at their current location without requiring another rename.

#### EPUB and OPF Metadata

The approved move workflow currently writes selected `FinalMetadata` fields into an EPUB's internal OPF during its safe repack and regenerates an external OPF sidecar when processing companions. The template batch path has separate EPUB-embedding and companion behavior, so outcomes are not yet consistent across entry points. The unified engine above is the required target. Preview output must match the eventual execution plan, including reserved batch destinations, cover embedding, companion handling, and item-level review outcomes.

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

The selected cover is stored on `FinalMetadata.final_cover_path`. EPUB cover embedding is performed by the EPUB metadata helper when invoked by a workflow that supports embedding; cover propagation is not guaranteed by every rename or move path. The approved safe-move workflow validates its selected-cover prerequisites before moving a book.

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
- Uses field-specific metadata selection. Title/author values use agreement across independent source groups; some other fields use trust/confidence ordering. See [README](README.md#metadata-resolution) for the implemented rules.
- Reviewed final metadata is protected from ordinary source synchronization; this is not the same as a universal manual-source-wins rule.

---

### 11. AI Filename Recognition

Recognizes filename segments as title, author, series, or volume when embedded metadata is unavailable. This is filename classification, not an OCR-driven or whole-book metadata accuracy model.

- Uses a `RandomForestClassifier` with TF-IDF text vectorization and engineered filename features.
- Produces prediction confidence for recognized filename segments; this is not the separate `FinalMetadata.accuracy_score`.
- Stores user corrections in `AIFeedback` for retraining via `python manage.py train_ai_models`.

**Entry points:** `/ai-feedback/`, `/ajax/book/<id>/ai-feedback/`, `/ajax/ai/retrain/`, `/ajax/ai/status/`.

---

### 12. Background Processing and Task Management

**Entry points:** `/scanning/`, `/scanning/queue/`, `/scanning/cancel/<job_id>/`.

- Scanning can run on in-process background threads so the initiating request need not wait for the full scan. This is not a durable worker system; running work can be lost when the web process exits.
- `ScanQueue` provides scheduling and status tracking, but does not guarantee durable cross-restart retries.
- `ScanHistory` records outcomes, timings, and API usage.
- Progress is reported via AJAX polling. Cancellation and scan resume are available through scan controls; these do not preserve or restart a lost background thread.

---

### 13. Error Handling and Recovery

Error handling varies by operation; these behaviors should not be read as a system-wide no-data-loss or rollback guarantee:

- **File system errors** — operations report failures according to their path; the approved move workflow journals progress and supports recovery.
- **Database errors** — transaction handling is used where implemented, but does not roll back external filesystem side effects in every workflow.
- **External API failures** — available caches/internal metadata and alternate sources may be used, depending on the operation.
- **Data consistency issues** — some paths use soft deletes and audit records; not all changes are reversible.

Validation, audit logging, and reversibility are operation-specific. The journal and recovery guarantees described above apply to the approved safe-move path, not all destructive actions.

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
