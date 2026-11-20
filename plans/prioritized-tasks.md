# Prioritized Implementation Tasks

This is a proposal, not a description of fully implemented behavior. It describes a desired metadata-accuracy and file-organization pipeline; the score gate, automatic rename, AI pre-confirmation, and keyboard workbench remain unfinished. See [`ROADMAP.md`](../ROADMAP.md#implementation-status-checked-against-pr-history) and [`FUNCTIONAL_SPECIFICATION.md`](../FUNCTIONAL_SPECIFICATION.md) for verified current behavior.

## Pipeline at a glance

| Stage               | Status               | Where                                                                                                                    |
| ------------------- | -------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| 1. Scan             | Implemented; in-process background execution | [`scanner/background.py`](../books/scanner/background.py), [`scan_books`](../books/management/commands/scan_books.py)    |
| 2. Recognize (AI)   | Implemented for filename segments only | [`scanner/ai/filename_recognizer.py`](../books/scanner/ai/filename_recognizer.py)                                        |
| 3. Extract          | Partial              | [`scanner/extractors/`](../books/scanner/extractors/), external APIs                                                     |
| 4. Validate         | Partial; no score gate | [`FinalMetadata`](../books/models_metadata.py), source agreement and match verification |
| 5. Rename + OPF     | Partial; manual/batch rename and separate approved-move path, no auto gate | [`utils/batch_renamer.py`](../books/utils/batch_renamer.py), [`utils/opf_generator.py`](../books/utils/opf_generator.py) |
| 6. Verify + confirm | Partial; review and staged approval, no spreadsheet workbench | review workflow, [`AIFeedback`](../books/models_operations.py:235) |

Order below is dependency-driven: the validation gate first (it decides what can be renamed safely), then the rename pipeline itself, then the scale layer, then the review/feedback loop and the filter workbenches that turn the last ~10% into more corrections and training data.

## Priority order

**P0 — core accuracy path (do in order):**

1. Multi-signal metadata accuracy & validation engine
2. Confidence-gated auto-rename + OPF generation
3. Scalable batch processing for 100k+ books
4. Ultrafast metadata verification & confirmation workbench

**P0 — foundation (can be done in parallel):**

- Stop tracking numbered migrations (task 8; the `reset_database` command itself is implemented)

**P1 — completes the loop:** 5. Metadata-quality filters and workbench actions 6. External metadata enrichment at scale 7. Bulk metadata edits (language / genre / publisher)

**P2 — later, non-blocking:**

- MOBI/AZW3 internal cover extraction
- Cover quality auto-selection
- Comic/audiobook first-class grouping

---

## 1. Multi-signal metadata accuracy & validation engine

**Status: Partial.** `FinalMetadata` has deterministic accuracy/completeness signals, title/author source-agreement logic, and external-result match verification. The planned OCR-derived title/author/publisher signals and score-based external-lookup/rename gate do not exist. Current `accuracy_score` is not calibrated as a probability.

**Priority:** P0 — the gate that decides external lookups, automatic rename, and what needs human review.

### Remaining problem

The current accuracy heuristic does not fuse OCR title/author/publisher evidence, does not gate external lookups or automatic renaming, and does not provide a calibrated probability. Match verification now exists, so the planned step to verify all external responses is no longer wholly outstanding.

### Steps

1. Extend the existing OCR path (currently PDF-only and ISBN-focused, using flat `pytesseract.image_to_string()`) to also extract **title, author, and publisher**. Switch to `image_to_data()` for word boxes + confidence, then apply:
    - **Labeled-field regex** — capture `Title:`, `Author:`, `Publisher:`, `ISBN:` (present on copyright/colophon pages).
    - **Layout heuristics** — title is usually the largest/top text and author the line below or after "by"; covers rarely print literal labels.
    - **Optional compact LLM** — map unstructured OCR blocks to {title, author, publisher} when regex + layout are ambiguous.
2. Build a unified candidate per book from filename parsing + cleaning ([`filename_recognizer.py`](../books/scanner/ai/filename_recognizer.py), [`parsing_helpers.py`](../books/utils/parsing_helpers.py:6)), embedded metadata (EPUB/OPF/ComicInfo/ID3), and OCR fields.
3. Add a `metadata_accuracy_score` to `FinalMetadata` in [`models_metadata.py`](../books/models_metadata.py:37), driven by an AI model that weighs per-field agreement across all signals, source trust levels, field completeness, and OCR confidence.
4. Add score-based lookup gating only after the score is validated against representative data; match verification already rejects mismatching external results in the current lookup path.
5. Expand test coverage to ensure every external provider path applies match verification before persisting a candidate.
6. Add a `validate_metadata` command and a dashboard showing the accuracy-score distribution plus how many books are ready for external lookup.

### Acceptance criteria

- OCR produces title/author/publisher/ISBN candidates, not just ISBN.
- Every book carries an accuracy score that fuses filename, embedded, and OCR signals.
- External lookups are skipped unless the accuracy score says a correct match is likely.
- Returned records are match-verified immediately and rejected when they do not correspond to the request.

### Verification

- Extend OCR and validation tests; assert low-confidence books do not trigger external lookups.

---

## 2. Confidence-gated auto-rename + OPF generation

**Status: Not implemented as specified.** Template renaming and a separate criteria-based approved safe-move workflow exist, but no accuracy threshold triggers unattended renames.

**Priority:** P0 — the core deliverable: auto-rename ~90% of the library unattended.

### Current state

- [`BatchRenamer`](../books/utils/batch_renamer.py:183) already previews renames.
- Template-based renaming and [`opf_generator.py`](../books/utils/opf_generator.py) exist.
- Missing: a confidence threshold that decides whether a book is renamed automatically or queued for review.

### Steps

1. Add a configurable threshold (e.g. `RENAME_CONFIDENCE_THRESHOLD = 0.99`).
2. For every book at or above threshold, apply the active naming template **and** regenerate/embed OPF metadata in one operation.
3. Route everything below threshold to the review queue (task 4) and leave the file untouched.
4. Produce a dry-run report (counts, before/after paths, per-book score) and reuse the `FileOperation` / `batch_id` pattern for rollback.

### Acceptance criteria

- A single command/action renames all high-confidence books and generates OPF metadata.
- Low-confidence books are never renamed automatically.
- The run is dry-run-able and reversible.

### Verification

- Extend [`test_batch_renamer.py`](../books/tests/test_batch_renamer.py) and [`test_opf_generator.py`](../books/tests/test_opf_generator.py) with threshold and rollback cases.

---

## 3. Scalable batch processing for 100k+ books

**Status: Partial.** Scan jobs use in-process daemon threads with status tracking; no durable worker, cross-restart retry, or verified 100k-book processing path exists.

**Priority:** P0 — the pipeline must not fall over at the target library size.

### Current state

- [`background.py`](../books/scanner/background.py) runs scans on daemon threads through [`ScanQueue`](../books/models_operations.py:530); threads die with the web process and there is no cross-restart retry.

### Steps

1. Add a durable worker (Celery on Redis/RabbitMQ default; Django-RQ lighter) and keep [`ScanQueue`](../books/models_operations.py:530) as the user-facing scheduling layer.
2. Run validation, rename, and external-enrichment passes as chunked jobs using `bulk_update` / `bulk_create` and `select_related` / `prefetch_related` so each batch stays within memory and time limits.
3. Add progress reporting, resume-after-restart, and retry/backoff for network-dependent stages.

### Acceptance criteria

- A 100k-book validation + rename pass completes without OOM and survives a process restart.
- Progress is observable and resumable.

### Verification

- Add a large synthetic fixture test (e.g. 20k rows) asserting bounded memory and resume behavior.

---

## 4. Ultrafast metadata verification & confirmation workbench

**Status: Partial.** Book-level metadata review and the `approve_batch` staged approval manifest exist. The spreadsheet-style diff, keyboard navigation, bulk confirmation, and integrated correction-to-training workflow remain unimplemented.

**Priority:** P0 — the human step must only touch the small low-confidence remainder; the majority is auto-confirmed by tasks 1–2 at near-100% accuracy. This workbench clears the rest at seconds per book.

### Problem

The review workflow exists but is page-oriented. Confirming 100k books one detail page at a time is the long pole; the workbench must present many books at once with instant confirm/reject and inline correction.

### Steps

1. Build a spreadsheet-style queue fed by `metadata_validation_score` (task 1) and every metadata-quality filter (task 5).
2. Show each book as a row with suggested vs. current metadata as an inline diff (changed fields highlighted).
3. Add keyboard control: `Enter`/`Y` confirm, `N`/`Esc` reject, arrow keys to move between fields and rows, auto-advance to the next unconfirmed book.
4. Add bulk confirm for the current filtered page (or everything above a confidence threshold).
5. Support inline single-field correction without leaving the flow; each confirm/edit/reject is recorded as `AIFeedback` and auto-collected as training data.
6. Auto-schedule retraining when pending feedback crosses a threshold.

### Acceptance criteria

- A user can confirm or correct hundreds of books per session at seconds per book.
- Confirmed books flow directly into the rename + move step; rejected/edited books feed retraining.

### Verification

- Playwright coverage for keyboard confirm/reject, bulk confirm, inline edit, and auto-advance.

---

## 5. Metadata-quality filters and workbench actions

**Priority:** P1 — every filter and statistic becomes a metadata-correction workbench, not a browsing view.

### Problem

The UI should expose filters that select books needing the same metadata fix, then a bulk action applies the correction. The goal is not discovery — it is to zero out each category of missing/wrong metadata.

### Filters to implement

- **Same author** — all books whose author resolves to a normalized name, to verify the spelling is clean and identical.
- **Series completeness** — all books in a series, to spot missing volumes and fix series name/numbering.
- **Missing covers** — books with no cached cover, to re-trigger extraction/downloads.
- **Missing/incorrect filenames** — books not yet renamed or whose filename diverges from the template.
- **Unprocessed enrichment** — books where a specific external source (e.g. Google Books) has not run yet.
- **Unconfirmed / low validation score** — the ultrafast verification workbench from task 4.

### Steps

1. Build the filters on [`filters.py`](../books/mixins/filters.py) and the per-section AJAX lists so each returns a book selection (not just a count).
2. Wire each filter to its matching bulk action (rename, metadata set, cover reprocess, enrichment trigger) so "fix the selected books" is one click.
3. Surface filter counts on the dashboard so the total remaining work is visible at a glance.

### Acceptance criteria

- Each named filter selects the right books and offers the matching corrective action.
- Counts drive the dashboard; the loop is filter → correct → rename → move.

### Verification

- Extend the filter/view tests for each workbench and the bulk actions they trigger.

---

## 6. External metadata enrichment at scale

**Priority:** P1 — fill missing/inaccurate fields from Google Books, Open Library, Goodreads, and Comic Vine for ebooks, comics, and audiobooks.

### Current state

- [`enrich_metadata`](../books/management/commands/enrich_metadata.py), [`scan_content_isbn`](../books/management/commands/scan_content_isbn.py), and [`rate_limiting.py`](../books/scanner/rate_limiting.py) exist.

### Steps

1. Make enrichment batch-oriented: prioritize books with missing key fields, cache every API response, and resume cleanly across restarts.
2. Respect rate limits and circuit breakers while keeping throughput as high as the APIs allow.
3. Record enrichment results as additional source-attributed metadata so the trust hierarchy and the validation score (task 1) can weigh them.
4. Immediately verify each returned record against the request (ISBN / title / author similarity) and reject mismatches before persisting.

### Acceptance criteria

- Enrichment can run unattended over the full library with progress, caching, and resume.
- New external data flows through the existing trust hierarchy.
- Mismatched external results are rejected immediately and never persisted.

### Verification

- Extend the scanner/enrichment tests with a large mocked-API batch.

---

## 7. Bulk metadata edits (language / genre / publisher)

**Status: Not implemented for the advertised metadata updates.** The current `ajax_batch_update_metadata`, `ajax_bulk_update_books`, and `ajax_batch_update_books` paths are placeholders or simulated responses; they do not persist the requested batch changes.

**Priority:** P1 — manual bulk corrections for the fields AI cannot always infer.

### Current state

- [`BulkUpdateForm`](../books/forms.py:462) only supports review/duplicate/placeholder actions.
- [`ajax_batch_update_metadata`](../books/views/ajax_books.py:156), [`ajax_bulk_update_books`](../books/views/ajax_books.py:172), and [`ajax_batch_update_books`](../books/views/ajax_books.py:178) are stubs.

### Steps

1. Extend [`BulkUpdateForm`](../books/forms.py:462) with `language`, `publisher`, `add_genres`, `remove_genres`.
2. Implement one real endpoint that updates `FinalMetadata.language` / `final_publisher` and `BookGenre` relations (creating `Genre` rows as needed).
3. Report per-book success/failure; partial failures must not abort the batch.

### Acceptance criteria

- Language/publisher/genre can be applied to a selection and persists to every book.
- Adding/removing genres is idempotent; partial failures are reported per book.

### Verification

- Extend [`test_forms_comprehensive.py`](../books/tests/test_forms_comprehensive.py) and [`test_integration.py`](../books/tests/test_integration.py).

---

## 8. `reset_database` command + stop tracking migrations

**Status: Partial.** The reset command exists and deletes/regenerates `books` migration modules during a reset. Numbered migration files remain tracked, and the ignore/untrack policy is not implemented.

**Priority:** P0 foundation — safe, repeatable database rebuilds and clean migration hygiene.

### Current state

- [`reset_database`](../books/management/commands/reset_database.py) exists, prompts before dropping the configured MySQL/MariaDB database, optionally backs it up, regenerates migrations, and applies them.
- [`books/migrations/`](../books/migrations/) still tracks numbered migration files.
- The planned `.gitignore` rule and removal of numbered migrations from the Git index have not been done.

### Steps

1. Add `books/migrations/*.py` + `!books/migrations/__init__.py` to [`.gitignore`](../.gitignore) and remove the numbered migrations from Git tracking.
2. Verify and document the existing reset command's actual options, backup, destructive confirmation, and migration-regeneration behavior.
3. Test the reset workflow against a disposable MySQL/MariaDB database before relying on it operationally.

### Acceptance criteria

- The migration ignore/untrack policy is in effect.
- `reset_database` rebuilds the schema and prompts before dropping unless `--noinput`; its destructive flow has been tested against a disposable database.

### Verification

- Run against a disposable MySQL database and confirm the app boots.

---

## Lower-priority (P2)

These stay in scope (comics and audiobooks are kept) but do not block the rename pipeline.

- **MOBI/AZW3 internal cover extraction** — add `MOBICoverExtractor` to [`cover_extractor.py`](../books/utils/cover_extractor.py) and wire [`folder.py`](../books/scanner/folder.py) so Kindle formats stop falling back to companion covers.
- **Cover quality auto-selection** — upgrade [`_calculate_quality_score`](../books/views/ajax_cover.py:210) with sharpness/contrast and pick the best cover across sources.
- **Comic/audiobook first-class grouping** — add a `Comic` series model and a `disc_number` field on `BookFile` so series/chapter metadata is stored once and renames stay consistent across a series.

---

## Remaining backlog (single-line)

De-prioritized items are kept only where they serve metadata accuracy or rename throughput; browsing/discovery features are owned by BookOrbit.

### Format Support

9. **FB2** — FictionBook XML metadata/cover parser.
10. **LIT** — Microsoft Reader parser.
11. **PRC** — PalmDOC/Mobipocket header parser.
12. **CB7** — 7z archive support.
13. **CBT** — TAR-based comic archive support.
14. **Audiobook ID3/tags** — complete the partial audio metadata extraction.

### Cover System (remaining)

15. **Multi-cover selection picker UI** — gallery on book detail; backend listing exists via [`list_all_covers`](../books/utils/cover_extractor.py:210).
16. **Bulk cover operations** — download/clear/export covers for many books.
17. **Cover search** — Open Library / Google Books for missing covers.
18. **Large-cover downscale + compress** — downscale to ≤ 2000 px instead of rejecting oversized uploads.

### Scanner and CLI

19. **Fold metadata-maintenance commands** — expose `scan_content_isbn` as `scan_books isbn` and `enrich_metadata` as `scan_books enrich`.

### Content Organization (remaining)

20. **Enhanced archive processing** — multi-ebook archives and nested folder structures.

### Bulk Actions (remaining)

21. **Flexible selection + dry-run preview** — select by filter/author/series/genre/saved search, preview before applying.
22. **Undo/rollback for bulk metadata** — reuse `FileOperation` / `batch_id`.

### AI and Intelligence (remaining)

23. **Auto-collect reviewed books + auto-schedule retraining** on feedback threshold (overlaps with task 4).
24. **Clean author/title + normalize ensemble comparison** before persisting predictions.
25. **Ensemble models / multi-language recognition / genre classification / feedback weighting**.

### UI and Experience

26. **Segmented media-type areas** — tailor per-media filters, columns, and bulk actions.
27. **Analytics dashboard** — surface validation-score distribution, field completeness, and filter counts (see task 5).
28. **Advanced search and filtering** — covered by task 5 (metadata-quality filters).
29. **UI cleanup/consolidation** — remove orphaned assets, dedupe JS, wire existing partials.

### Data Management and Integration

30. **Saved searches / virtual libraries (De-prioritized)** — only as a way to build the review/rename queue.
31. **Collections and reading lists (De-prioritized)** — BookOrbit owns these.
32. **Hierarchical genres/tags + creator/people tagging**.
33. **Custom metadata columns** per media type.
34. **Duplicate detection and merge** for books.
35. **Metadata review queue** — superseded by task 4 (low-confidence queue).
36. **OPDS catalogue feed (De-prioritized)** — BookOrbit provides it.
37. **Import/export between installations**.
38. **Cloud sync / backup (De-prioritized)**.
39. **Full-text search (De-prioritized)**.
40. **Plugin architecture (De-prioritized)**.

### Background Processing (remaining)

41. **Durable worker for external enrichment** (see task 3).
42. **Offload AI training + scheduled maintenance + long bulk jobs** to the worker.

### Testing (remaining)

43. **Expand Playwright UI tests** to the validation dashboard, bulk rename, review queue, and AI feedback.

### Legal and Privacy

44. **Disclaimer acceptance** on login.
45. **Enhanced privacy controls**.

### Calibre-style catalog additions

46. **Persistent sort fields** — add stored `author_sort` and `title_sort` fields and use them for ordering. Author cleanup and surname-aware parsing exist, but separate sort fields are still planned.
47. **Bulk search & replace** — regex find/replace across a field with preview.
48. **Flexible book identifiers** — multiple IDs per book (`isbn`, `asin`, `doi`, `goodreads`).
49. **Metadata backup/restore** — export/restore library metadata independently of files.
50. **Catalog generation (De-prioritized)**.
51. **Multiple libraries (De-prioritized)**.
