# Roadmap and Future Direction

This document tracks planned, partially implemented, and proposed features. Implemented behavior is documented in [`FUNCTIONAL_SPECIFICATION.md`](FUNCTIONAL_SPECIFICATION.md) and [`README.md`](README.md).

## Mission

This app is intended to prepare digital libraries for downstream cataloging, including import into BookOrbit. The high-throughput review pipeline is a **target design, not the current end-to-end behavior**. The implemented system scans libraries, extracts local and external metadata, validates external matches, resolves source records into reviewable final metadata, and provides separate rename and approved-move workflows. It does not currently provide AI pre-confirmation or spreadsheet-style verification at the planned scale. The UI must provide a functional overview of review, correction, rename, and move status; general library browsing and reading belong to BookOrbit.

## How to Read

- **Planned** — agreed direction with a known design.
- **Partial** — some pieces exist but the feature is not complete.
- **Proposed** — ideas open for discussion.

## Implementation status checked against PR history

The project Markdown was compared with the code delivered through the repository's 78 pull requests (76 merged; 2 closed without merge). The merged changes are reflected in the current repository, but the Markdown had not kept pace. The following capabilities are implemented and should be treated as current behavior:

- Metadata resolution includes source-agreement voting for title and author, separate completeness and accuracy signals, and external-result match verification. The accuracy value is a deterministic heuristic, not a calibrated probability or automatic-rename gate.
- `approve_batch` stages criteria-based approvals; `move_approved` is dry-run by default and executes eligible moves through the journaled safe-move path. Recovery tooling is available for interrupted moves.
- EPUB metadata synchronization, improved author cleanup/name handling, and per-process test/live-resource isolation have been added.
- The `reset_database` command exists and recreates local `books` migrations during a reset. Numbered migration files are currently tracked.

Important unfinished work remains: durable background execution and reliable checkpoint recovery; consistent rescan semantics; OCR-driven multi-signal validation; AI-assisted review and the keyboard spreadsheet workbench; complete bulk metadata operations; and a single rename/move engine shared by all entry points. The existing template batch renamer and approved safe-move workflow have different safety and collision behavior.

---

## Format Support

| Format             | Status                  | Notes                                                             |
| ------------------ | ----------------------- | ----------------------------------------------------------------- |
| FB2                | Declared, not extracted | FictionBook XML parser needed                                     |
| LIT                | Declared, not extracted | Microsoft Reader format                                           |
| PRC                | Declared, not extracted | PalmDOC/Mobipocket headers                                        |
| CB7                | Declared, not extracted | 7z archive support                                                |
| CBT                | Declared, not extracted | TAR-based comic archive                                           |
| Audiobook ID3/tags | Partial                 | Content-type section exists; audio metadata extraction is limited |

## Cover System (Phase 2)

The core pipeline is implemented: extraction ([`cover_extractor.py`](books/utils/cover_extractor.py)), hash-based caching ([`cover_cache.py`](books/utils/cover_cache.py)), manual upload/restore/info ([`ajax_cover.py`](books/views/ajax_cover.py)), internal-cover listing ([`ajax_list_internal_covers`](books/views/ajax.py:86)), and EPUB cover embedding ([`metadata_embedder.py`](books/utils/epub/metadata_embedder.py)). Remaining items:

### Multi-cover selection UI

- **Backend listing exists** — [`EPUBCoverExtractor.list_all_covers()`](books/utils/cover_extractor.py:210) returns every image with width, height, file size, format, OPF-cover flag, and position; [`ajax_list_internal_covers`](books/views/ajax.py:86) exposes them with preview URLs.
- **Picker UI (Planned)** — build the book-detail gallery that shows all internal images, highlights the OPF-designated and currently selected covers, and persists the user's choice to `BookFile.cover_image_preference`.

### MOBI/AZW3 internal cover extraction

- **Gap** — MOBI/AZW3 currently fall back to companion covers; the `mobi_internal` source type exists but has no extractor behind it.
- **Planned** — add a `MOBICoverExtractor` (parse PalmDB/MOBI headers to locate the embedded cover record) and an AZW3 variant, then wire them into [`folder.py`](books/scanner/folder.py) cover detection.

### Cover quality auto-selection

- **Current** — a simple heuristic in [`_calculate_quality_score()`](books/views/ajax_cover.py:210) scores resolution + aspect ratio + file size, stored on `BookFile.cover_quality_score`.
- **Planned** — richer scoring (sharpness, contrast, portrait correctness) and automatic preference of the highest-scoring cover across internal images, companion files, and manual uploads.

### Bulk cover operations

- **Planned** — download/clear/export covers for many books at once, reusing [`CoverCache.clear_all()`](books/utils/cover_cache.py:138) and [`get_cache_size()`](books/utils/cover_cache.py:171); target by selection (see Bulk Actions and Maintenance) or per-series after grouping lands.

### Cache management UI

- **Implemented** — the [`clean_cover_cache`](books/management/commands/clean_cover_cache.py) command reports cache stats, removes orphaned covers (`--dry-run` supported), and rebuilds missing internal covers (`--rebuild-missing`). Dashboard stats and a one-click cleanup action live in [`user_settings.py`](books/views/user_settings.py:78) and [`clean_cover_cache_ajax`](books/views/ajax_cover.py:259).

### Cover search

- **Planned** — search Open Library / Google Books for missing covers; the existing [`image_utils.download_and_store_cover()`](books/utils/image_utils.py:15) already provides the download-and-store path.

### Decisions

- **Manual cover uploads replace auto-detected covers** — [`ajax_upload_bookfile_cover`](books/views/ajax_cover.py:30) sets the manual image as the active cover and saves the previous path to `original_cover_path` for [`ajax_restore_original_cover`](books/views/ajax_cover.py:115). This is replace-with-restore, not supplement.
- **Large cover handling** — currently oversized uploads are rejected by [`CoverUploadForm`](books/forms.py:661) (>5MB, >2000x3000px) and no resize happens; extraction paths convert to JPEG quality=85 but do not downscale. Decide: downscale to ≤ 2000 px on the longest side and compress instead of rejecting (Planned).

## Scanner and CLI

[`scan_books`](books/management/commands/scan_books.py) is the primary scan command and exposes `scan`, `rescan`, `status`, `list`, and `cancel` subcommands. Metadata-maintenance commands remain separate, and web scans run in process rather than through a durable worker. The legacy `scan_ebooks` / `EbookScanner` path was retired in Phase 4. Remaining work:

- **Durable execution and resume (Planned)** — background scans currently use daemon threads. A `ScanStatus` checkpoint records progress, and `scan --resume` attempts to continue after the last processed file, but execution is not restart-safe and recovery is manual/best-effort. Add durable execution and per-job/per-folder checkpoints so an interrupted job can reliably continue where it stopped without being confused with a new scan or rescan.
- **Unify rescan modes (Planned)** — define book-ID rescan as a targeted metadata rebuild (clear/re-extract source-derived metadata while preserving reviewed values); define folder rescan as a folder traversal with file-change detection and missing/reappearing-file cleanup. Marking a book unreviewed permits external sources to replace earlier manual values. The web folder-rescan thread currently passes incompatible arguments and cannot start its intended traversal; `scan_books rescan --folder` instead resolves the folder to book IDs and uses the targeted path. Fix and align the CLI and web behavior, make both modes idempotent, and make the distinction explicit to users.
- **OPF companion review (Partial)** — ebook scanning matches OPF filename stems and records ambiguous or unmatched companions in the scan log rather than guessing. Surface these warnings in the per-book review workflow and provide a safe way to repair previously misassociated OPF metadata.
- **Fold metadata-maintenance commands (Planned)** — make `scan_content_isbn` and `enrich_metadata` subcommands of `scan_books` so there is a single scanning CLI.
- **Content-ISBN subcommand** — expose [`bulk_scan_content_isbns`](books/scanner/extractors/content_isbn.py:343) as `scan_books isbn`.
- **Enrichment subcommand** — expose [`enrich_metadata`](books/management/commands/enrich_metadata.py) behavior as `scan_books enrich` for external-API repair of earlier filename-only scans.
- **Health/status** — keep `status --apis` for rate-limit and circuit-breaker state via [`get_api_status`](books/scanner/rate_limiting.py:397).

## Content Organization

Grouping is the foundation for series-level bulk operations (see Bulk Actions and Maintenance), so it is tracked here before those higher-level features.

### Comic grouping

- **Current (Partial)** — [`ComicFileGrouper`](books/scanner/grouping.py:14) groups files by series name and [`_process_comic_issue`](books/scanner/content_processing.py:160) stores issue/volume/year as `BookMetadata`, but each issue is still one `Book` with `content_type='comic'`; there is no first-class series record.
- **Planned** — introduce `Comic` (series) and `ComicIssue` (file) models so series-level metadata (publisher, author, genre, cover) is extracted once and every issue links to its series.

### Audiobook grouping

- **Current (Partial)** — [`AudiobookFileGrouper`](books/scanner/grouping.py:112) groups audio files by a book key, and [`_process_audiobook_files`](books/scanner/content_processing.py:289) already creates one `Book` (`content_type='audiobook'`) with multiple `BookFile` entries plus duration/size totals.
- **Planned** — make the logical `Audiobook` a first-class entity with reliable chapter/track ordering, per-track titles, and chapter-level metadata (instead of relying only on filename-derived numbers).

### Enhanced archive processing

- **Planned** — multi-ebook archives (a single CBZ/ZIP containing several books), nested folder structures, and improved companion-file matching.

## Bulk Actions and Maintenance

Many of the primitives below already exist (author cleanup, batch delete, batch rename, a `BulkUpdateForm`); the work is to turn them into a cohesive, previewable bulk-management surface. Grouping (comics/audiobooks) feeds directly into this because a group becomes a natural selection and application unit.

### Unified rename/move engine and batch UI

- **Current gap** — the template UI uses `RenamingEngine` / `BatchRenamer`, while `move_approved` computes a target and executes through `safe_move_book`. These paths differ in collision reservation, journaling/recovery, companion handling, and EPUB metadata/cover synchronization.
- **Shared engine (Planned, foundational)** — route single-book UI, batch UI, APIs, management commands, approval flows, and future background jobs through the same destination planner and file-operation engine. Entry points may orchestrate selection, confirmation, and reporting, but must not implement independent path planning, collision handling, or file mutation. Batch target reservations must prevent collisions among books in the same batch.
- **Shared services and parity (Planned)** — UI, CLI, APIs, and background jobs call the same service for each operation, including batch preparation, holds, approval, planning, execution, status, author order, and metadata resynchronization. Test equivalent entry points against the same fixtures and require equivalent results and outcomes.
- **Batch lifecycle UI (Planned)** — create, preview, execute, monitor, and control batches from the UI. Show which books have been reviewed, corrected, approved, renamed, and moved. Include review details, contact sheets, holds with reasons, dry runs, and explicit confirmation counts. Persist per-item status and show actionable outcomes (pending, moved, `needs_review`, failed, skipped), reasons, and recovery/retry actions. A `needs_review` item must remain visible and must not be presented as moved.
- **Destination and execution (Planned)** — support a validated destination root distinct from the scan source. The current `move_approved` target is anchored to the scan folder. UI move requests enqueue work rather than moving files inside the request; execution uses durable state and the shared service.
- **EPUB parity (Planned)** — every EPUB rename/move through the shared engine synchronizes curated metadata and embeds the selected cover; companion OPF handling and failures must be consistent across entry points.
- **Metadata after move (Planned)** — allow users to edit and save metadata for already-moved books. Preserve the existing reviewed-`FinalMetadata` protection against automatic source replacement; saving a manual edit must also update the EPUB and OPF at their current location without requiring another rename.
- **Trust display (Partial)** — source trust values are already shown in source-management and book-detail views. Complete the UI so source trust, candidate confidence, evidence/agreement, and the actual winning value/source are distinct and consistent with the resolver's selection rules. Saving a manual choice applies it; reviewed values, including intentional blanks, are protected from automatic updates. Marking a book unreviewed permits source-derived values to replace them. An edit does not automatically approve the book.

### Review-gated rename

- **Approval required (P0)** — until metadata accuracy is independently demonstrated to be extremely high and the policy is explicitly revisited, only books reviewed and approved by a person may be renamed or moved. Reviewed group approval is allowed; a score alone never approves a book.
- **Review routing** — use validation and confidence to prioritize review and propose eligible batches. Flagged or unapproved books remain in place.
- **Dry-run and recovery** — use the shared planner and journaled safe-move workflow to preview, execute, and recover approved batches consistently across entry points.

### Author management (bulk)

- **Author-name normalization (Implemented)** — [`normalize_all_author_names()`](books/services/author_cleanup.py:133) applies [`clean_author_name()`](books/utils/authors.py:8) and [`parse_author_name()`](books/utils/authors.py:62) across all authors; exposed via the [`normalize_authors`](books/management/commands/normalize_authors.py) command and the Library Maintenance UI.
- **Fix all books by an author (Implemented)** — [`fix_all_books_by_author()`](books/services/author_cleanup.py:195) resolves the book's primary author, fuzzy-matches related records, and applies the canonical spelling across the matching set; exposed from the book detail page via [`author_management.py`](books/views/author_management.py:281).

### Bulk metadata edits

- **Language / genre / publisher bulk set (Partial)** — extend [`BulkUpdateForm`](books/forms.py:462) and the [`ajax_batch_update_*`](books/views/ajax_books.py:156) endpoints so language, genre(s), publisher, and other `FinalMetadata` fields can be applied to many selected books at once.
- **Add or remove genres in bulk** — apply one or more genres to a selection, or strip a genre across the selection.
- **Review / deduplicate / availability flags** — mark reviewed or unreviewed, toggle `is_duplicate`, and change availability in bulk (already partially covered by `BulkUpdateForm`).

### Selection and preview

- **Flexible selection sources** — select by checkbox, filtered list, author (or author group), series, genre, scan folder, or saved search so bulk operations target exactly the right books.
- **Preview before apply** — show a dry-run diff (before/after per book) before persisting, mirroring the existing [`BatchRenamer`](books/utils/batch_renamer.py:183) dry-run pattern.

### Grouping-driven bulk operations

- **Series/audiobook as selection units (Planned)** — once `Comic`/`ComicIssue` and `Audiobook` grouping lands (see Content Organization), treat a whole series or audiobook as one bulk target: extract metadata once and apply it to all members.
- **Bulk cover operations** — already tracked under Cover System (Phase 2); grouping enables applying one cover/quality choice per series.

### Execution and safety

- **Undo/rollback (Partial)** — reuse the `FileOperation` / `batch_id` pattern from [`models_operations.py`](books/models_operations.py:178) to make bulk metadata changes reversible.
- **Progress for large batches** — run long jobs through the worker described in Background Processing and Scheduled Jobs; fast DB-only updates stay synchronous.
- **Partial-failure handling** — keep the per-item error tolerance in [`ajax_batch_update_books`](books/views/ajax_books.py:178) and report successes/failures separately.

## AI and Intelligence

The filename-recognition engine is an ensemble in [`filename_recognizer.py`](books/scanner/ai/filename_recognizer.py):

- **Regex member** — deterministic [`parse_path_metadata`](books/scanner/parsing.py) parser.
- **Segment member** — splits the filename and votes on each segment's role (title / author / series / volume) via heuristics.
- **Learned member** — a `RandomForestClassifier` trained on segment _roles_ (not memorised title/author strings) so it generalises to unseen filenames.

### Metadata validation

- **Planned (P0)** — a validation model/score that estimates whether the merged `FinalMetadata` for a book is correct, not just whether the filename parsed. Use it to prioritize and support human review, not to bypass approval.
- **Inputs** — OCR (title, author, publisher, ISBN), filename parsing/cleaning confidence from [`filename_recognizer.py`](books/scanner/ai/filename_recognizer.py), embedded metadata (EPUB, OPF, ComicInfo, ID3), per-field agreement across sources, trust levels, and field completeness.
- **External-lookup gating** — the same model decides whether enough accurate input exists to query Google Books / Open Library / Goodreads / Comic Vine, so a low-confidence query is never sent and cannot return the wrong book.
- **Result match verification** — when a query is sent, immediately verify the returned record against the request (ISBN, title, author similarity) so a mismatch (e.g. author parsed as title) is flagged as "no match" and never persisted.
- **Output** — a per-book accuracy/confidence score stored on `FinalMetadata`, available to review and batch-selection workflows. Demonstrate accuracy on independent held-out data before considering any future change to the approval policy.

### AI pre-confirmation tier

- **Planned** — an agent-driven verification pass to gather additional evidence for uncertain books before human review. Unlike the validation score, this tier does new work: opens the file, runs OCR against the title page, and cross-checks the result against a live websearch rather than only the cached provider response. It does not itself approve a rename.
- **Output** — either a resolved book with a recorded evidence trail (OCR text, search result used, confidence score), or a specific unresolved reason (no ISBN, degraded OCR, suspected duplicate, corrupted file, uncertain language) that routes directly to the human workbench with that reason attached, so the human doesn't re-derive what the AI already ruled out.
- **Explicitly out of scope for this tier** — corrupted file handling and duplicate resolution. Both require a judgment call (which copy to keep, whether a file is salvageable) that stays with the human step.

### AIFeedback provenance

- **Planned** — add a `confirmed_by` field (`human` / `ai_preconfirmation` / `auto_gate`) to `AIFeedback` so retraining can distinguish genuine human-verified ground truth from AI-confirmed rows. Default `train_ai_models` to human-confirmed data only, with AI-confirmed rows available as an opt-in, separately weighted set, so the pre-confirmation tier can't quietly reinforce its own errors through the training loop.

### Bundled learning set

- **Seed training corpus (Implemented)** — [`training_data.csv`](books/scanner/ai/models/training_data.csv) ships curated, privacy-safe public-domain examples covering the common naming patterns, so a fresh install can train immediately.
- **Corpus format** — one row per book (`filename`, `original_filename`, `title`, `author`, `series`, `volume`, `file_format`, `book_id`) so the bundled set merges seamlessly with locally generated data.
- **`--include-seed` (Implemented)** — [`train_ai_models --include-seed`](books/management/commands/train_ai_models.py:49) merges the seed corpus with locally reviewed data before training/retraining, deduping on `filename` with user data winning.

### Learning from reviewed books

- **Every reviewed book is a training sample (Partial)** — [`collect_training_data()`](books/scanner/ai/filename_recognizer.py:114) already reads all books with `finalmetadata__is_reviewed=True` and writes them to `training_data.csv`; tighten this so reviews are picked up automatically after metadata is corrected.
- **Feedback loop (Partial)** — [`AIFeedback`](books/models_operations.py:235) stores corrections and `needs_retraining`; [`train_ai_models --use-feedback`](books/management/commands/train_ai_models.py) folds them in. Extend to auto-schedule retraining when pending feedback crosses a threshold.

### Accuracy and cleanliness goals

- **Maximise fields recovered from the filename** — train the learned member to label every segment so title, author, series, and volume are all recovered where present.
- **Clean author names** — apply [`clean_author_name()`](books/utils/authors.py:8) (strip birth/death dates, `ca.` markers, trailing punctuation) and [`parse_author_name()`](books/utils/authors.py:62) (prefix-aware surname splitting) to every prediction before persisting.
- **Clean titles** — use [`clean_title_and_extract_series_number()`](books/utils/parsing_helpers.py:6) and strip format/noise words so `02 - Book Title` yields a clean title and series number.
- **Normalized comparison** — normalise names/titles before voting so `J.R.R. Tolkien` and `J R R Tolkien` count as the same author in ensemble aggregation.

### Remaining intelligence work

- **Ensemble models (Planned)** — combine multiple classifiers beyond the current single RandomForest (e.g. gradient boosting or a compact language model) for improved segment-role accuracy.
- **Multi-language filename recognition (Proposed)** — train on non-English naming conventions; extend the corpus with non-English seed rows.
- **Automated genre classification (Proposed)** — infer genre from content analysis (separate from filename parsing).
- **Review-based learning loop (Partial)** — strengthen retraining from user corrections, including weighting by `feedback_rating` and only using high-quality reviews.

## UI and Experience

### Ultrafast verification workbench

- **Planned (P0)** — the human confirmation step is the throughput bottleneck at 100k+ books, so it must run at seconds per book, not page-by-page editing.
- **Spreadsheet rows with diff** — each book is a row showing suggested vs. current metadata with changed fields highlighted.
- **Keyboard-driven** — `Enter`/`Y` confirm, `N`/`Esc` reject, arrow keys to move between fields/rows, auto-advance to the next unconfirmed book.
- **Bulk confirm** — explicitly approve a reviewed filtered page or group, with confidence available as a selection aid.
- **Inline correction** — edit a single field in place; the correction is recorded as feedback for retraining.
- **Approve then move** — approved books become eligible for a separately previewed and explicitly started rename/move batch; approval itself does not move files.

### Segmented media-type areas

- **Current (Partial)** — dedicated section views already exist in [`sections.py`](books/views/sections.py) with templates under [`books/templates/books/sections/`](books/templates/books/sections/) (`ebooks_main`, `comics_main`, `series_main`, `audiobooks_main`), a split-pane layout, and per-section JS.
- **Planned** — fully tailor each area: dedicated filters, columns, bulk actions, and cover/metadata workflows per media type, wired to first-class `Comic`/`ComicIssue`/`Audiobook` grouping.

### Analytics dashboard

- **Current (Partial)** — [`dashboard.py`](books/analytics/dashboard.py) and [`scanning/dashboard.html`](books/templates/books/scanning/dashboard.html) exist with chart JS.
- **Planned** — make every statistic a metadata-quality signal: validation-score distribution, field completeness, duplicate author/series counts, missing covers, unprocessed enrichment, and rename readiness; replace the simulated AI-parsing accuracy in [`dashboard.py`](books/analytics/dashboard.py) with real `AIFeedback` data.

### Metadata quality filters

Filters exist to drive metadata correction, not browsing. Each filter is a workbench that selects books needing the same fix, after which a bulk action corrects them. Planned filters include:

- **Same author** — verify the author name is clean and identical across all books.
- **Series completeness** — find missing volumes and correct series name/numbering.
- **Missing covers** — re-trigger cover extraction/downloads.
- **Missing/incorrect filenames** — target books that still need renaming.
- **Unprocessed enrichment** — e.g. books where the Google Books lookup has not run yet.

These reuse [`filters.py`](books/mixins/filters.py) and the per-section AJAX lists, and feed the bulk actions in Bulk Actions and Maintenance. The loop is always **filter → correct metadata → rename → move to the final library location**.

### UI cleanup and consolidation

- **Remove orphaned assets** — delete leftover files such as [`book_metadata.html.backup`](books/templates/books/book_metadata.html.backup).
- **Consolidate overlapping JS** — deduplicate pairs like `scanning-dashboard.js` / `scanning-dashboard-inline.js` and `ebooks-section.js` / `ebook-list.js` into the shared section base ([`base-section-manager.js`](books/static/book/js/base-section-manager.js), [`base-section.js`](books/static/book/js/base-section.js)).
- **Surface existing partials consistently** — the multi-cover selector [`_multi_cover_selector.html`](books/templates/books/partials/_multi_cover_selector.html) and author-duplicates view [`author_duplicates.html`](books/templates/books/author_duplicates.html) already exist; wire them into the relevant book-detail and maintenance flows (see Cover System and Bulk Actions).

## Data Management and Integration

Scope: cataloguing and maintenance only — **no reader and no reading status**. Discovery, browsing, virtual libraries, collections, and reading are owned by BookOrbit, so the catalog/discovery features below are **de-prioritized** and kept only where they directly improve metadata accuracy or rename throughput (e.g. a saved search that builds the review/rename queue). Book access is via **download links only**.

### Catalog and discovery

- **Saved searches / virtual libraries (De-prioritized)** — useful only as a way to build the review/rename queue; general browsing is owned by BookOrbit.
- **Collections and reading lists (De-prioritized)** — BookOrbit owns these; no reading progress is tracked here.
- **Hierarchical genres and tags (Planned)** — nested genres/tags and creator/people tagging (writers, artists, editors) for comics and audiobooks, beyond flat genres.
- **Custom metadata columns (Proposed)** — user-defined fields per media type, mirroring Calibre custom columns.

### Calibre-style catalog features

- **Persistent sort fields (Planned)** — author-name cleanup and surname-aware parsing now exist, but separate stored `author_sort` / `title_sort` fields and article-ignoring title ordering do not.
- **Bulk search & replace (Planned)** — regex find/replace across a metadata field with a preview, applied to many books.
- **Flexible book identifiers (Proposed)** — store multiple identifiers per book (`isbn`, `asin`, `doi`, `goodreads`, etc.) instead of a single ISBN.
- **Metadata backup/restore (Planned)** — export and restore library metadata independently of files.
- **Catalog generation (Proposed)** — generate a browsable EPUB/HTML catalog beyond CSV/JSON.
- **Multiple libraries (Proposed)** — support separate library databases/partitions with switching.

### Catalog integrity and maintenance

- **Duplicate detection (Planned)** — fuzzy-detect duplicate books (title/author/ISBN/hash) and merge them, re-pointing files and metadata.
- **Metadata verification queue (Planned)** — a dedicated, keyboard-driven confirmation workbench for low-confidence/unconfirmed books instead of burying them in filters.

### Import, export, and interchange

- **Import/export between installations (Planned)** — data migration with compatibility validation (Calibre-style library export).
- **OPDS catalogue feed (De-prioritized)** — BookOrbit provides the catalogue feed.
- **CSV/JSON catalog export (Proposed)** — export metadata for spreadsheet and backup use.

### Storage and extension

- **Cloud sync / backup (Proposed)** — Google Drive, Dropbox, OneDrive.
- **Full-text search (Planned)** — search inside ebook content, catalogue-wide.
- **Plugin architecture (Proposed)** — extensible format and integration support.

### Explicitly out of scope

- Reading (opening/reading books in-app), reading status/progress, ereader connectivity, and social/recommendation features. BookOrbit owns these.

## Background Processing and Scheduled Jobs

- **Current state** — [`background.py`](books/scanner/background.py) launches scans as daemon threads with cache-based progress, serialised through [`ScanQueue`](books/models_operations.py:530). The thread dies with the web process. A database checkpoint (`ScanStatus.last_processed_file`) can support a manual resume attempt, but it does not keep the job running, automatically restart it, or guarantee exact recovery.
- **Keep synchronous** — ordinary CRUD and DB-only bulk updates (`bulk_update`/`bulk_delete`) are fast and stay in the request cycle; they do not need a worker.
- **External data enrichment (Planned)** — the primary worker use. Rate-limited API calls ([`rate_limiting.py`](books/scanner/rate_limiting.py): Comic Vine ~18s/request, Google Books 1000/day, Open Library 60/min) and per-book delays in [`rescan_existing_books`](books/scanner/background.py:526) make this the long pole; run it with retries/backoff and progress.
- **AI training/retraining (Planned)** — [`train_ai_models`](books/management/commands/train_ai_models.py) is CPU-bound (RandomForest); move training and retraining off the request cycle.
- **Scheduled maintenance (Planned)** — support scheduled rescan, orphan cover cleanup, author duplicate detection, cover-cache rebuild, and model retraining.
- **Long bulk jobs (Planned)** — validation, rename, move, and enrichment passes run outside web requests, survive restarts, and report progress; use chunked `bulk_update`/`bulk_create` and `select_related`/`prefetch_related` so each batch stays within memory and time limits.
- **Requirement** — persist job identity, progress, and folder-specific checkpoints, and make resume continue after the last completed unit rather than restarting or behaving like a rescan. The execution framework is not yet chosen; daemon threads alone do not provide this guarantee.

## Testing and Quality

The project already has two test layers — Django tests under [`books/tests/`](books/tests/) (pytest per [`pytest.ini`](pytest.ini)) and Playwright E2E under [`tests/e2e/`](tests/e2e). The remaining work is consolidation, not greenfield.

- **Remove standalone runners (Done)** — all `if __name__ == "__main__"` runner blocks were removed; every module under [`books/tests/`](books/tests/) is now a plain pytest/`TestCase` module.
- **Remove or port legacy tests (Done)** — the legacy `test_enhanced_api.py` and the overlapping AJAX suites (`test_ajax_comprehensive`, `test_ajax_endpoints`, `test_ebooks_ajax`) were removed, leaving a single canonical AJAX suite.
- **Single test entry point** — keep [`pytest.ini`](pytest.ini) as the source of truth (`testpaths = books/tests`) and ensure `python manage.py test books.tests` still works.
- **Expand UI tests (Planned)** — extend Playwright coverage in [`tests/e2e/`](tests/e2e) beyond auth/dashboard/books/wizard to the scanning dashboard, bulk actions, cover picker, AI feedback, and renamer; add `data-testid` selectors and run in CI.
- **Cover new roadmap items** — every new feature (bulk operations, cover quality, MOBI extraction, grouping, background worker) ships with its own tests.

### Test/live database isolation

- **Implemented** — [`settings_test.py`](ebook_manager/settings_test.py) redirects the file-based SQLite database, media, and cache into a unique temporary directory per test process; [`pytest.ini`](pytest.ini:3) and [`manage.py`](manage.py:13) route test runs to it, and the fragile `sys.argv` / `sys.modules` override was removed from [`settings.py`](ebook_manager/settings.py).
- **Rule** — tests may read MySQL fixtures if needed but must never write to the live database.

### Database reset

- **Reset command (Implemented, with deviations)** — [`reset_database`](books/management/commands/reset_database.py) prompts before dropping the configured MySQL/MariaDB database (unless `--noinput`), can back it up, deletes generated `books` migration modules, regenerates them, and applies migrations. This command is destructive and engine-restricted.
- **Pre-release clean database (Planned)** — continue testing against a SQL database. Before the first MySQL deployment, create a clean MySQL database from a single initial `books` migration representing the current schema; retain the resulting migration in version control. The existing three numbered migrations have not yet been consolidated. After release, preserve migration history and use forward migrations for schema changes. Destructive resets are acceptable for explicitly selected pre-release databases, not live data.

## Legal and Privacy

- **Disclaimer acceptance** — login disclaimer (tinyMediaManager-style).
- **Enhanced privacy controls** — granular data-sharing options.
