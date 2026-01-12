# Functional Specification and User Behavior Analysis for the Django Ebook Management System

## Table of Contents

1. [System Overview](#system-overview)
2. [User Interface and Navigation](#user-interface-and-navigation)
3. [Core Features and Workflows](#core-features-and-workflows)
    - [Initial Setup and Configuration](#1-initial-setup-and-configuration)
    - [File Import and Scanning](#2-file-import-and-scanning)
    - [Metadata Management System](#3-metadata-management-system)
    - [Book Renaming and Organization](#4-book-renaming-and-organization)
    - [Series Management](#5-series-management)
    - [Cover Image Management](#6-cover-image-management)
    - [Advanced Search and Filtering](#7-advanced-search-and-filtering)
    - [Data Sources and Trust Management](#8-data-sources-and-trust-management)
    - [Background Processing and Task Management](#9-background-processing-and-task-management)
    - [Error Handling and Recovery](#10-error-handling-and-recovery)
    - [System Configuration and Customization](#11-system-configuration-and-customization)
4. [Data Flow and Integration Patterns](#data-flow-and-integration-patterns)
5. [Security and Data Protection](#security-and-data-protection)
6. [Performance and Scalability Considerations](#performance-and-scalability-considerations)
7. [Future Architecture Enhancements](#future-architecture-enhancements)

---

## System Overview

The Django Ebook Management System is a comprehensive library management application designed to organize, catalog, and maintain large collections of digital media across multiple formats:

- **Ebooks:** EPUB, PDF, MOBI, AZW, AZW3, FB2, LIT, PRC
- **Comics:** CBR, CBZ, CB7, CBT, PDF
- **Audiobooks:** MP3, M4A, M4B, AAC, FLAC, OGG, WAV

The system provides automated metadata extraction, intelligent file organization, series management, and comprehensive search capabilities across all supported media types.

### Core Architecture Principles

- **Multi-source metadata aggregation** with confidence scoring
- **Non-destructive operations** with rollback capabilities
- **Background processing** for resource-intensive operations
- **Flexible file organization** with user-defined patterns
- **Comprehensive audit logging** for all operations

---

## User Interface and Navigation

### Main Navigation Structure

The system provides a dual-level navigation structure designed for efficient access to all major features:

#### Top Authentication Bar

**Purpose:** User account management and quick access to core settings.

**Components:**

- **Brand/Logo:** Links to dashboard, provides consistent home navigation
- **User Menu (Authenticated):** - User profile dropdown with username display - Settings - Personal preferences and template management - Dashboard - Overview and activity feed - Sign out - Secure logout functionality
- **Authentication Links (Unauthenticated):** - Sign in button - Sign up button

#### Main Content Navigation Pills

**Purpose:** Primary content access organized by media type and function.

**Navigation Items:**

1. **Dashboard**
    - URL: `/dashboard/`
    - Icon: Tachometer
    - Purpose: Activity overview, recent scans, statistics, quick actions
    - Features: Real-time scan status, library statistics, recent activity feed

2. **Library (Full Library)**
    - URL: `/books/`
    - Icon: Swatchbook
    - Purpose: Unified view of entire library across all content types
    - Features:
        - Combined listing of all books, comics, and audiobooks
        - Advanced filtering by content type, format, metadata
        - Bulk operations across different media types
        - Export and reporting capabilities
        - Cross-content-type search

3. **Ebooks**
    - URL: `/ebooks/`
    - Icon: Book
    - Purpose: Focused view of traditional ebooks (EPUB, MOBI, AZW, AZW3, PDF, FB2, LIT, PRC)
    - Features:
        - Format-specific filtering
        - Reading progress tracking
        - Export to e-reader devices
        - Metadata quality indicators
        - Format conversion capabilities (where applicable)

4. **Series**
    - URL: `/series/`
    - Icon: Layer Group
    - Purpose: Series-centric organization and browsing
    - Features:
        - Series completion tracking
        - Reading order management
        - Multi-book operations
        - Series metadata editing

5. **Comics**
    - URL: `/comics/`
    - Icon: Mask
    - Purpose: Comic book management (CBR, CBZ, CB7, CBT, PDF)
    - Features:
        - Issue number tracking
        - Creator information
        - Publication chronology
        - Cover gallery view
        - Archive format conversion
        - Series and volume organization

6. **Audiobooks**
    - URL: `/audiobooks/`
    - Icon: Headphones
    - Purpose: Audiobook library management (MP3, M4A, M4B, AAC, FLAC, OGG, WAV)
    - Features:
        - Chapter and track organization
        - Playback duration tracking
        - Narrator information
        - Series and collection management
        - Album art display
        - Multi-file audiobook grouping

7. **Authors**
    - URL: `/authors/`
    - Icon: User Group
    - Purpose: Author-centric browsing and management
    - Features:
        - Author bibliography
        - Name normalization tools
        - Pseudonym management
        - Author statistics

8. **Rename Books**
    - URL: `/rename-books/`
    - Icon: Edit
    - Purpose: Bulk file organization and renaming
    - Features:
        - Batch renaming with templates
        - Preview before execution
        - Template management (redirects to Template Management)
        - Companion file handling

9. **Scanning**
    - URL: `/scanning/`
    - Icon: Search
    - Purpose: Library scanning and background task management
    - Features:
        - Active scan monitoring
        - Scan folder configuration
        - Task queue management
        - Scan history and logs

10. **Management** (Dropdown Menu)
    - Icon: Cogs
    - Purpose: Administrative and advanced management functions
    - Submenu Items:
        - **Authors** - Author management and bibliography
        - **Genres** - Genre taxonomy and categorization
        - **Data Sources** - Metadata source configuration
        - **Scan Folders** - Library directory management
        - **Add Scan Folder** - Quick folder addition
        - **API Status** - External API health monitoring
        - **Rename Books** - Bulk file organization (also available in main nav)
        - **Quick Process** - Legacy quick metadata processing (deprecated - functionality merged into unified metadata workflow)
        - **AI Feedback** - AI-assisted metadata feedback review

**Navigation Behavior:**

- Active tab highlighted with visual indicator
- Responsive design: Icons only on mobile, full text on desktop
- Maintains context when navigating between related views
- Breadcrumb support on detail pages
- Dropdown menus for grouped administrative functions

### Content Type Organization

The system employs a **content-type-centric architecture** that provides specialized views while maintaining unified data management:

**Design Philosophy:**

- **Unified Data Model:** All content types share core book metadata structure
- **Specialized Views:** Each content type has optimized UI and filtering
- **Cross-Type Operations:** Library view enables operations across all types
- **Consistent UX:** Similar patterns across different content areas

**Content Type Detection:**

- Ebooks: `.epub`, `.pdf`, `.mobi`, `.azw`, `.azw3`, `.fb2`, `.lit`, `.prc`
- Comics: `.cbr`, `.cbz`, `.cb7`, `.cbt`, `.pdf`
- Audiobooks: `.mp3`, `.m4a`, `.m4b`, `.aac`, `.flac`, `.ogg`, `.wav`

---

## Core Features and Workflows

### 1. Initial Setup and Configuration

#### Setup Wizard

**Purpose:** Guide new users through initial system configuration and library setup.

**Entry Points:**

- `/wizard/` - Main wizard entry point
- `/wizard/welcome/` - Welcome screen
- `/wizard/folders/` - Folder configuration
- `/wizard/content-types/` - Content type selection

**User Inputs:**

- Library root directories
- Preferred file formats
- Naming conventions
- Data source preferences

**System Actions:**

- Creates `ScanFolder` records for each library directory
- Validates directory permissions and accessibility
- Initializes default `DataSource` configurations
- Sets up user preferences in session/database

**Expected Output:**

- Configured scan folders ready for initial import
- Default metadata sources activated
- User redirected to dashboard with initial scan prompt

**Data Impact:**

- Creates new `ScanFolder`, `DataSource`, and user preference records
- No existing data is modified during setup

**Error Handling:**

- Invalid directory paths: Shows error message, allows correction
- Permission issues: Displays specific error and suggested solutions
- Network connectivity for metadata sources: Warns but allows continuation

**Edge Cases:**

- Directory already contains books: Prompts for scan vs. import options
- Multiple users: Each user gets independent configuration
- Cancelled wizard: Can be resumed from any step

**User Guarantees:**

- Setup can be rerun without data loss
- All configuration is reversible through settings
- No files are moved or modified during setup

---

### 2. File Import and Scanning

#### Automatic File Discovery

**Purpose:** Continuously monitor configured directories for new ebook files and automatically import them into the system.

**Entry Points:**

- `/scanning/start-folder/` - Manual folder scan trigger
- Background task: Periodic directory monitoring
- `/scanning/` - Scan management dashboard

**User Inputs:**

- Scan folder selection (manual scans)
- Scan frequency configuration
- File format filters

**System Actions:**

1. **Directory Traversal:**
    - Recursively scans all subdirectories of configured `ScanFolder` paths
    - Identifies files matching supported formats:
        - Ebooks: `.epub`, `.pdf`, `.mobi`, `.azw`, `.azw3`, `.fb2`, `.lit`, `.prc`
        - Comics: `.cbr`, `.cbz`, `.cb7`, `.cbt`, `.pdf`
        - Audiobooks: `.mp3`, `.m4a`, `.m4b`, `.aac`, `.flac`, `.ogg`, `.wav`
    - Calculates SHA256 hash of file path for uniqueness

2. **File Processing:**
    - Creates `Book` record with file metadata (path, size, format, scan timestamp)
    - Extracts embedded metadata (EPUB internal, MOBI headers, PDF properties)
    - Generates initial `FinalMetadata` record with low confidence scores
    - Queues background tasks for enhanced metadata retrieval

3. **Duplicate Detection:**
    - Uses file path hash to prevent duplicate imports
    - Handles file moves/renames by updating existing records
    - Logs conflicts when same file appears in multiple locations

**Expected Output:**

- New books appear in library with basic metadata
- Background processes begin enhancing metadata
- Scan progress visible in real-time dashboard
- Completion notifications with import statistics

**Data Impact:**

- Creates new `Book`, `FinalMetadata`, and related records
- Never overwrites existing book records
- Updates `last_scanned` timestamps on existing books

**Error Handling:**

- **Corrupted files:** Marked as corrupted, import continues
- **Permission denied:** Logged with specific file path, scan continues
- **Disk space:** Scan pauses with warning, resumes when space available
- **Network issues (for metadata):** Queued for retry, local scan completes

**Edge Cases:**

- **Empty directories:** Logged but no error generated
- **Symlinks/shortcuts:** Followed if valid, logged if broken
- **Very large files (>2GB):** Import continues with size warning
- **Unicode filenames:** Properly handled with UTF-8 encoding
- **Nested archives:** Only outer archive imported, contents ignored

**User Guarantees:**

- Original files are never modified or moved during scanning
- Failed imports don't prevent other files from processing
- Scan can be safely interrupted and resumed
- All scan activity is logged with timestamps

**Dependencies:**

- Read access to configured scan directories
- Write access to media directory for cover extraction
- Network access for external metadata retrieval (optional)

**Example Workflow:**

1. User adds `/home/books/` as scan folder
2. System discovers 1,247 EPUB files
3. Basic metadata extracted from 1,240 files (7 corrupted)
4. Background tasks queued for external metadata lookup
5. User sees books in library immediately with improving metadata over time

---

### 3. Metadata Management System

#### Unified Metadata Review and Processing

**Purpose:** Provide a comprehensive, single-page workflow for reviewing, editing, and processing book metadata, covers, file operations, and duplicates. This unified interface replaces the previous separate "Metadata" and "Quick Process" views.

**Entry Points:**

- `/book/<id>/metadata/` - Unified metadata review and processing interface
- `/book/<id>/metadata/?workflow=1` - Workflow mode with prev/next navigation
- Automatic: Triggered during file import
- `/ajax/rescan-external-metadata/` - AJAX metadata update

**Interface Sections:**

The metadata page is organized into distinct, collapsible sections:

1. **Metadata Review**
    - Radio button selection for title, author, series, genre, publisher, language, publication year
    - Confidence scores displayed for each option
    - Source attribution (e.g., "Google Books", "Calibre", "Manual")
    - Manual entry options for custom metadata
    - Quick access to add new metadata sources

2. **Cover Selection**
    - Grid display of all available covers from different sources
    - Quality indicators (resolution, file size)
    - Confidence scoring for each cover
    - Select/deselect individual covers
    - Bulk download selected covers
    - Upload custom cover option

3. **File Operations**
    - Rename and move configuration with live preview
    - Template selection dropdown (loads user's default from Settings)
    - Folder pattern and filename pattern inputs
    - Live preview showing resulting path
    - Companion file inclusion checkbox (synced with Settings)
    - Link to Template Management for advanced configuration

4. **Duplicate Detection** (conditional)
    - Displays potential duplicate books
    - Comparison view with metadata differences
    - Merge or keep separate options
    - File path comparison

5. **External Metadata Refresh**
    - Source selection checkboxes (Google Books, Open Library, etc.)
    - Option to clear existing metadata before rescan
    - Rescan trigger button

**Workflow Mode:**

- Activated via `?workflow=1` parameter
- Provides Previous/Next book navigation
- Streamlined review process for batch metadata curation
- Progress indicator showing position in queue
- Quick save and move to next functionality

**User Inputs:**

- Manual metadata corrections
- Source trust level adjustments
- Metadata field priorities
- External API credentials

**System Actions:**

1. **Internal Metadata Extraction:**
    - **EPUB:** Parses OPF files, Dublin Core elements, content.opf
    - **MOBI/AZW/AZW3:** Extracts EXTH headers, title, author, ASIN
    - **PDF:** Reads document properties, XMP metadata
    - **FB2 (FictionBook):** Parses XML structure for title, author, genre, annotation
    - **LIT (Microsoft Reader):** Extracts embedded metadata where accessible
    - **PRC (Palm Resource):** Reads PalmDOC/Mobipocket headers
    - **Comics (CBR/CBZ/CB7/CBT):** Extracts ComicInfo.xml if present, analyzes archive contents

2. **External API Queries:**
    - **Open Library:** ISBN/title lookup for books
    - **Google Books:** Comprehensive metadata and covers
    - **Comic Vine:** Comic series and issue information
    - Rate limiting and API key management

3. **Confidence Scoring:**
    - Each metadata source assigned trust level (0.0-1.0)
    - Field-specific confidence based on data completeness
    - Weighted aggregation determines final values
    - Manual entries receive highest confidence (1.0)

4. **Data Harmonization:**
    - Author name normalization (Last, First format)
    - Series number standardization (padded integers)
    - Genre mapping to standardized taxonomy
    - Language code normalization (ISO 639-1)

**Expected Output:**

- `FinalMetadata` record with best available information
- Individual source records maintained for transparency
- Confidence scores for each field displayed to user
- Metadata quality indicators in UI

**Data Impact:**

- Creates/updates `BookTitle`, `BookAuthor`, `BookSeries`, `BookGenre` records
- Updates `FinalMetadata` with aggregated results
- Preserves all source data for audit trail
- Never deletes source metadata records

**Error Handling:**

- **API failures:** Graceful degradation to cached/internal data
- **Rate limiting:** Automatic backoff and retry scheduling
- **Invalid data formats:** Data cleaned or rejected with logging
- **Network timeouts:** Operations continue with available data

**Edge Cases:**

- **Conflicting metadata:** Higher confidence source wins
- **Multiple editions:** Attempts to identify correct edition by file size/format
- **Foreign language titles:** Preserves original with English translation if available
- **Missing ISBN:** Uses title/author fuzzy matching
- **Series numbering conflicts:** Manual resolution required

**User Guarantees:**

- Original file metadata never modified
- All metadata changes are reversible
- Confidence scores help users identify reliability
- Manual corrections always override automated data

**Dependencies:**

- Network access for external APIs
- Valid API keys for commercial services
- Sufficient disk space for cover image caching

---

### 4. Book Renaming and Organization

#### Intelligent File Renaming System with Template Management

**Purpose:** Rename and reorganize book files according to user-defined patterns while preserving all metadata and ensuring no data loss. The system provides both predefined templates and custom pattern creation, with centralized management through user settings.

**Entry Points:**

- `/rename-books/` - Bulk renaming interface
- `/rename-books/templates/` - Template management (CRUD operations)
- `/settings/` - Default template selection and preview
- `/book/<id>/metadata/` - Single-file rename within metadata workflow
- `/ajax/bulk-rename-preview/` - AJAX preview generation

**Template Management Architecture:**

1. **Predefined System Templates:**
    - Comprehensive: `${author.sortname}/${bookseries.title}/${title}.${ext}`
    - Author-Title: `${author.sortname}/${title}.${ext}`
    - Title Only: `${title}.${ext}`
    - Series Focused: `${bookseries.title}/${bookseries.title} ${bookseries.number} - ${title}.${ext}`
    - Year-Author: `${publicationyear}/${author.sortname}/${title}.${ext}`
    - Genre Organization: `${genre}/${author.sortname}/${title}.${ext}`

2. **Custom User Templates:**
    - Created and managed in `/rename-books/templates/`
    - Stored in UserProfile.saved_patterns as JSON
    - Full CRUD operations available
    - Pattern validation before save

3. **Settings Integration (Single Source of Truth):**
    - `/settings/` page includes template selection section
    - Preview example showing folder and filename patterns
    - "Save as Default Template" button persists choice to UserProfile
    - Pattern examples displayed with clickable selection
    - Visual feedback (green border) when template matches current default
    - All rename operations automatically load user's default template:
        - Bulk rename page (`/rename-books/`)
        - Template management page (`/rename-books/templates/`)
        - Metadata page file operations (`/book/<id>/metadata/`)

**Template Variables:**

- `${title}` - Book title
- `${author}` - Author name (Last, First)
- `${author.sortname}` - Author sort name
- `${series}` - Series title
- `${series_number}` - Series number (padded)
- `${bookseries.title}` - Series title (alternative)
- `${bookseries.number}` - Series number (alternative)
- `${year}` / `${publicationyear}` - Publication year
- `${genre}` - Primary genre
- `${ext}` - File extension
- `${publisher}` - Publisher name

**User Inputs:**

- Renaming patterns using template tokens (e.g., `${author.sortname}/${title}.${ext}`)
- Target directory selection
- Conflict resolution preferences
- Companion file handling options

**System Actions:**

1. **Pattern Processing:**
    - Template engine processes tokens like `${author.sortname}`, `${bookseries.title}`, `${publicationyear}`
    - Character sanitization for filesystem compatibility
    - Path length validation (Windows/Linux limits)
    - Preview generation showing before/after paths

2. **Conflict Detection:**
    - Checks for destination file existence
    - Identifies potential path collisions
    - Detects circular references or invalid patterns
    - Validates directory creation permissions

3. **File Operations:**
    - Creates target directories as needed
    - Moves primary book file atomically
    - Handles companion files (covers, OPF, NFO)
    - Updates database paths after successful move

4. **Rollback Capability:**
    - Maintains operation log for reversal
    - Atomic operations where possible
    - Recovery procedures for partial failures

**Expected Output:**

- Files reorganized according to specified pattern
- Updated file paths in database
- Preserved file associations and metadata
- Detailed operation log with success/failure status

**Data Impact:**

- Updates `Book.file_path` and related path fields
- Creates `RenameOperation` audit records
- Preserves all metadata and relationships
- May create/remove directory structure

**Error Handling:**

- **Destination exists:** Offers skip, rename, or overwrite options
- **Permission denied:** Logs error, continues with other files
- **Disk full:** Pauses operation, allows cleanup and resume
- **Invalid characters:** Automatically sanitizes or prompts for correction

**Edge Cases:**

- **Duplicate destinations:** Adds numeric suffix (Book (1).epub)
- **Very long paths:** Truncates intelligently while preserving uniqueness
- **Network drives:** Handles slower I/O and potential disconnections
- **Case-sensitive filesystems:** Prevents conflicts on Linux/macOS
- **Unicode filenames:** Properly handles international characters

**User Guarantees:**

- Original files preserved until move confirmed successful
- All operations logged and reversible
- No metadata loss during rename operations
- Preview shows exact results before execution

**Dependencies:**

- Write permissions on source and target directories
- Sufficient disk space for temporary operations
- Valid metadata for pattern token resolution

**Example Workflow:**

1. User selects 500 books for renaming
2. Pattern `${author.sortname}/${bookseries.title}/${title}.${ext}` applied
3. Preview shows: "Adams, Douglas/Hitchhiker's Guide/Restaurant at End of Universe.epub"
4. 3 conflicts detected and resolution options presented
5. Execution moves 497 files successfully, logs 3 skipped
6. User can review operation log and revert if needed

---

### 5. Series Management

#### Comprehensive Series Organization

**Purpose:** Group related books into series with proper ordering, handle series metadata, and maintain relationships between books and series.

**Entry Points:**

- `/series/` - Series browser and management
- `/series/<id>/` - Individual series details
- `/ajax/series-detail/` - AJAX series information
- `/book/<id>/metadata/` - Book-level series assignment

**User Inputs:**

- Series names and descriptions
- Book ordering within series
- Series metadata corrections
- Manual series assignments

**System Actions:**

1. **Series Detection:**
    - Automatic detection from book metadata
    - Pattern recognition in titles (Book 1, Part I, Vol. 2)
    - External metadata source series information
    - Manual series creation and assignment

2. **Ordering Management:**
    - Numeric series positions with decimal support (1.5 for novellas)
    - Multiple ordering schemes (publication vs. chronological)
    - Gap detection and suggested corrections
    - Duplicate number conflict resolution

3. **Series Metadata:**
    - Series descriptions and cover art
    - Author consistency validation
    - Genre and category inheritance
    - Reading status tracking across series

**Expected Output:**

- Organized series with proper book ordering
- Series-level statistics and completion tracking
- Consistent metadata across series books
- Reading progress visualization

**Data Impact:**

- Creates/updates `Series` records
- Manages `BookSeries` relationship records
- Updates series-related metadata in `FinalMetadata`
- Maintains reading status in user preferences

**Error Handling:**

- **Duplicate series names:** Offers merge or rename options
- **Missing books in sequence:** Highlights gaps, allows manual filling
- **Conflicting authors:** Prompts for resolution or series split
- **Invalid ordering:** Provides suggested corrections

**Edge Cases:**

- **Multi-author series:** Handles shared universes and collaborations
- **Reboot/restart series:** Distinguishes between series with same name
- **Omnibus editions:** Can belong to multiple positions or separate tracking
- **Prequel insertion:** Handles non-integer positioning (0.5, -1)

**User Guarantees:**

- Series assignments don't affect file organization unless explicitly requested
- All series relationships are manually reversible
- Reading progress preserved during series reorganization
- No duplicate series created without user confirmation

---

### 6. Cover Image Management

#### Comprehensive Cover Handling System

**Purpose:** Manage book cover images from multiple sources, maintain high-quality covers, and ensure covers remain associated with books through file operations.

**Entry Points:**

- `/ajax/book/<id>/manage_cover/` - Cover management interface
- `/ajax/book/<id>/upload_cover/` - Manual cover upload
- `/ajax/fetch-cover-image/` - External cover retrieval
- Automatic: During metadata import

**User Inputs:**

- Manual cover image uploads
- Cover source preferences
- Image quality thresholds
- Cover extraction settings

**System Actions:**

1. **Cover Extraction:**
    - **EPUB:** Extracts covers from OPF manifest and content
    - **MOBI/AZW/AZW3:** Retrieves embedded cover images from EXTH records
    - **PDF:** Generates thumbnails from first page
    - **FB2:** Extracts inline base64-encoded cover images from XML
    - **LIT:** Attempts extraction from internal structure
    - **Comics (CBR/CBZ/CB7/CBT):** Uses first page or dedicated cover.jpg/cover.png from archive
    - **Audiobooks:** Extracts embedded album art from ID3 tags (MP3) or iTunes metadata (M4A/M4B)

2. **External Cover Retrieval:**
    - Open Library cover API integration
    - Google Books cover download
    - Comic Vine cover matching
    - High-resolution preference settings

3. **Image Processing:**
    - Automatic resize and optimization
    - Format standardization (JPEG for photos, PNG for graphics)
    - Quality assessment and duplicate detection
    - Thumbnail generation for UI performance

4. **Cover Association:**
    - Multiple covers per book with confidence scoring
    - Primary cover selection based on quality metrics
    - Cover preservation during file operations
    - Backup and recovery procedures

**Expected Output:**

- High-quality cover images for library display
- Optimized thumbnails for performance
- Multiple cover options with quality indicators
- Consistent cover availability across formats

**Data Impact:**

- Creates `BookCover` records with image paths
- Updates `FinalMetadata.final_cover_path`
- Manages cover file storage in media directory
- Maintains cover-to-book relationships

**Error Handling:**

- **Missing covers:** Generates placeholder or extracts from content
- **Corrupted images:** Attempts repair or marks as unavailable
- **Download failures:** Retries with exponential backoff
- **Storage full:** Cleanup old/low-quality covers automatically

**Edge Cases:**

- **Multiple covers per book:** User can select preferred cover
- **Very large images:** Automatic resizing with quality preservation
- **Unusual formats:** Conversion to standard formats when possible
- **Copyright concerns:** Respects fair use and provides attribution

**User Guarantees:**

- Original cover files preserved during operations
- Cover quality never degraded without user consent
- All cover changes are logged and reversible
- No covers deleted without replacement available

---

### 7. Advanced Search and Filtering

#### Comprehensive Search System

**Purpose:** Provide powerful search and filtering capabilities across all book metadata, series, authors, and custom fields.

**Entry Points:**

- `/books/` - Main library browser with search
- `/ajax/search-books/` - AJAX search interface
- `/ebooks/ajax/list/` - Format-specific browsing
- `/series/ajax/list/` - Series-focused search

**User Inputs:**

- Text search queries (title, author, description)
- Metadata filters (format, genre, language, publication year)
- Custom field searches
- Sorting and pagination preferences

**System Actions:**

1. **Search Processing:**
    - Full-text search across multiple fields
    - Fuzzy matching for typos and variations
    - Boolean operators (AND, OR, NOT)
    - Wildcard and regex pattern support

2. **Filtering Engine:**
    - Multiple simultaneous filters
    - Range queries (publication years, file sizes)
    - Existence filters (has cover, has series)
    - Quality filters (metadata completeness)

3. **Result Ranking:**
    - Relevance scoring based on field matches
    - Boost factors for exact vs. partial matches
    - User preference influence on ranking
    - Recently accessed book prioritization

**Expected Output:**

- Relevant search results with highlighting
- Filter controls with result counts
- Sorting options with preserved search state
- Export capabilities for result sets

**Data Impact:**

- Read-only operations, no data modification
- Search history tracking for user preferences
- Performance analytics for optimization
- Caching of common search patterns

**Error Handling:**

- **Invalid regex:** Graceful fallback to literal search
- **No results:** Suggests similar searches or filter relaxation
- **Performance issues:** Automatic query optimization and result limiting
- **Encoding problems:** Handles various character sets properly

**Edge Cases:**

- **Very large result sets:** Pagination and progressive loading
- **Complex queries:** Query parsing with error messages
- **Accent-insensitive search:** Handles international characters
- **Case sensitivity:** User-configurable matching behavior

**User Guarantees:**

- All book data searchable without performance degradation
- Search preferences preserved across sessions
- No accidental data modification through search
- Search results always reflect current data state

---

### 8. Data Sources and Trust Management

#### Metadata Source Reliability System

**Purpose:** Manage multiple metadata sources, assign trust levels, and handle conflicts between different data sources.

**Entry Points:**

- `/data_sources/` - Data source management
- `/data_sources/create/` - Add new source
- `/data_sources/<id>/update_trust/` - Adjust trust levels
- Background: Automatic source quality assessment

**User Inputs:**

- Source trust level adjustments (0.0-1.0)
- API credentials and endpoints
- Source priority ordering
- Quality threshold settings

**System Actions:**

1. **Source Management:**
    - Track reliability statistics for each source
    - Automatic quality assessment based on accuracy
    - Performance monitoring and timeout handling
    - API quota and rate limit management

2. **Trust Level Calculation:**
    - Historical accuracy tracking
    - Data completeness scoring
    - User feedback integration
    - Automatic trust adjustment based on performance

3. **Conflict Resolution:**
    - Weighted voting system for conflicting data
    - Manual override capabilities
    - Confidence scoring for final decisions
    - Audit trail for all resolutions

**Expected Output:**

- Reliable metadata with confidence indicators
- Source performance statistics
- Conflict resolution recommendations
- Quality improvement suggestions

**Data Impact:**

- Updates `DataSource` trust levels and statistics
- Creates conflict resolution records
- Influences `FinalMetadata` confidence scores
- Maintains source performance metrics

**Error Handling:**

- **Source unavailable:** Graceful degradation to other sources
- **Invalid responses:** Data validation and rejection
- **API changes:** Error detection and admin notification
- **Trust level conflicts:** User intervention required for critical decisions

**Edge Cases:**

- **New source integration:** Probationary period with lower initial trust
- **Source retirement:** Graceful handling of deprecated APIs
- **Bulk trust adjustments:** Batch operations with rollback capability
- **Manual overrides:** Highest priority regardless of source trust

**User Guarantees:**

- Trust level changes are immediately effective
- All source decisions are auditable and reversible
- No data loss when sources become unavailable
- User manual corrections always preserved

---

### 9. Background Processing and Task Management

#### Asynchronous Operation System

**Purpose:** Handle resource-intensive operations (metadata retrieval, file operations, scanning) in background processes without blocking the user interface.

**Entry Points:**

- Automatic: Triggered by various user actions
- `/scanning/queue/` - Background task monitoring
- `/scanning/cancel/<job_id>/` - Task cancellation
- `/ajax/processing-status/` - Real-time status updates

**User Inputs:**

- Task priority adjustments
- Cancellation requests
- Retry preferences
- Notification settings

**System Actions:**

1. **Task Queue Management:**
    - Priority-based task scheduling
    - Resource allocation and throttling
    - Progress tracking and status updates
    - Error handling and retry logic

2. **Operation Types:**
    - **Metadata Enhancement:** External API queries, cover downloads
    - **File Operations:** Batch renaming, organization, validation
    - **Maintenance Tasks:** Database optimization, cleanup operations
    - **Import Processing:** Large-scale file discovery and cataloging

3. **Progress Reporting:**
    - Real-time progress updates via WebSocket/AJAX
    - Detailed operation logs
    - Performance metrics and statistics
    - Completion notifications

**Expected Output:**

- Smooth user experience without blocking operations
- Detailed progress information and ETAs
- Successful completion with comprehensive results
- Error reports with recovery recommendations

**Data Impact:**

- Updates various models based on task type
- Creates operation logs and audit records
- May modify file system structure
- Maintains task queue state

**Error Handling:**

- **Task failures:** Automatic retry with exponential backoff
- **System overload:** Task throttling and queue management
- **Resource constraints:** Graceful degradation and prioritization
- **User cancellation:** Clean task termination and rollback

**Edge Cases:**

- **Long-running operations:** Checkpointing and resume capability
- **System restart:** Task queue recovery and status restoration
- **Concurrent operations:** Resource conflict detection and resolution
- **Memory constraints:** Batch processing and memory management

**User Guarantees:**

- Operations can be safely cancelled at any time
- System remains responsive during background processing
- All operations are logged for troubleshooting
- Failed operations provide clear error messages and recovery options

---

### 10. Error Handling and Recovery

#### Comprehensive Error Management System

**Purpose:** Provide robust error handling, data recovery, and system resilience across all operations.

**System-Wide Error Handling Principles:**

1. **Graceful Degradation:**
    - Operations continue with reduced functionality when possible
    - Clear user communication about limitations
    - Automatic fallback to alternative approaches
    - No complete system failures from individual component errors

2. **Data Integrity Protection:**
    - Atomic operations where possible
    - Transaction rollback on failures
    - Backup and recovery procedures
    - Validation before destructive operations

3. **User Communication:**
    - Clear, actionable error messages
    - Progress indicators during recovery
    - Suggested resolution steps
    - Contact information for support

**Common Error Scenarios:**

#### File System Errors

**Scenarios:** Permission denied, disk full, file locks, network storage issues

**Handling:**

- **Detection:** Pre-operation validation and real-time monitoring
- **Recovery:** Automatic retry with exponential backoff
- **User Action:** Clear instructions for resolution (free space, check permissions)
- **Data Protection:** No data loss, operations marked for retry

#### Database Errors

**Scenarios:** Connection loss, constraint violations, corruption

**Handling:**

- **Detection:** Connection pooling and health checks
- **Recovery:** Automatic reconnection and transaction retry
- **User Action:** Temporary read-only mode during recovery
- **Data Protection:** Transaction integrity maintained

#### External API Failures

**Scenarios:** Rate limiting, service unavailable, invalid responses

**Handling:**

- **Detection:** Response validation and timeout management
- **Recovery:** Fallback to cached data and alternative sources
- **User Action:** Manual retry options available
- **Data Protection:** No existing data overwritten with invalid responses

#### Data Consistency Issues

**Scenarios:** Orphaned records, missing files, metadata conflicts

**Handling:**

- **Detection:** Regular integrity checks and validation
- **Recovery:** Automatic cleanup and relationship repair
- **User Action:** Manual review and correction interface
- **Data Protection:** All corrections logged and reversible

**User Guarantees:**

- No data loss from system errors
- Clear communication about error status and resolution
- Alternative workflows available during component failures
- All error recovery actions are logged and auditable

---

### 11. System Configuration and Customization

#### User Settings and Preferences

**Purpose:** Provide comprehensive user-level configuration options with immediate effect across all system operations.

**Entry Points:**

- `/settings/` - User preferences and configuration hub
- `/admin/` - Django admin interface for system-level settings
- Configuration files and environment variables
- `/scanning/help/` - Configuration guidance

**User Settings Page (`/settings/`):**

The Settings page serves as the **single source of truth** for user preferences, ensuring consistent behavior across all system features.

**Configuration Sections:**

#### 1. File Renaming Templates

**Purpose:** Centralized template selection and management for all file renaming operations.

**Features:**

- **Template Selection:** - Dropdown showing all available templates (system + custom) - Custom templates marked with ⭐ indicator - Read-only display with link to Template Management for editing

- **Pattern Preview:** - Live example showing folder pattern - Live example showing filename pattern - Sample result preview using example book metadata - Optimized font sizing (0.7-0.75rem) for readability - Word-break handling to prevent overflow

- **Pattern Examples:** - Dynamically generated from predefined system templates - Clickable examples that update dropdown selection - Visual feedback: Green border when example matches current default, orange when different - Automatic scroll to dropdown on selection - Examples sourced from PREDEFINED_PATTERNS (not hardcoded)

- **Save Functionality:** - "Save as Default Template" button - AJAX save to UserProfile (default_folder_pattern, default_filename_pattern) - Visual confirmation ("Saved!" message for 2 seconds) - Immediate effect across all rename operations

- **Companion Files:** - Checkbox to include companion files (covers, OPF, metadata) - Synced to UserProfile.include_companion_files - Automatically applied in bulk rename and metadata workflows

**Integration Points:**

- Settings selections automatically load in: - `/rename-books/` - Bulk rename page - `/rename-books/templates/` - Template management - `/book/<id>/metadata/` - File operations section

- UserProfile Model Fields: - `default_folder_pattern` - User's preferred folder organization pattern - `default_filename_pattern` - User's preferred filename pattern - `include_companion_files` - Boolean for companion file handling - `saved_patterns` - JSON array of custom templates

#### 2. Library Management

- **Scan Folders:** Add/remove directories, set scan frequency
- **File Formats:** Enable/disable format support, set processing priorities
- **Organization:** Default naming patterns (managed via templates above)
- **Cleanup:** Orphan file handling, duplicate management

#### Metadata Sources

- **API Configuration:** Credentials, endpoints, timeouts
- **Trust Levels:** Source reliability settings, conflict resolution
- **Data Quality:** Completeness thresholds, validation rules
- **Cache Management:** Retention policies, refresh schedules

#### User Interface

- **Themes:** Visual appearance, layout options
- **Performance:** Page sizes, caching preferences
- **Notifications:** Email settings, real-time updates
- **Accessibility:** Screen reader support, keyboard navigation

#### System Performance

- **Resource Limits:** Memory usage, concurrent operations
- **Background Processing:** Task priorities, queue management
- **Database:** Connection pooling, query optimization
- **Storage:** Media management, backup policies

**Expected Output:**

- Customized system behavior matching organizational needs
- Optimized performance for specific hardware configurations
- Consistent user experience across different access methods
- Proper integration with existing infrastructure

**Data Impact:**

- Updates system configuration tables
- May trigger background reconfiguration tasks
- Affects future operation behavior
- Preserves user data during configuration changes

**Error Handling:**

- **Invalid settings:** Validation with specific error messages
- **Configuration conflicts:** Detection and resolution guidance
- **Performance issues:** Automatic rollback to previous settings
- **Service dependencies:** Graceful handling of unavailable services

**User Guarantees:**

- Configuration changes are immediately effective where possible
- All settings changes are logged and reversible
- No data loss during configuration updates
- System remains functional during reconfiguration

---

## Data Flow and Integration Patterns

### Cross-Module Dependencies

1. **Import → Metadata → Organization Flow:**
    - File scanning creates basic book records
    - Background metadata enhancement populates detailed information
    - Renaming system uses enhanced metadata for organization

2. **Search → Display → Action Pattern:**
    - Search system queries across all metadata sources
    - Results display with consistent formatting and controls
    - User actions (rename, edit, delete) maintain data integrity

3. **Source Management → Quality Assessment Loop:**
    - Data sources provide metadata with confidence scores
    - User feedback and accuracy tracking adjusts source trust
    - Improved trust levels enhance future metadata quality

### System Integration Points

#### Database Consistency

- Foreign key constraints maintain referential integrity
- Soft deletes preserve audit trails
- Transaction boundaries prevent partial updates
- Regular integrity checks identify and resolve inconsistencies

#### File System Synchronization

- Database paths always reflect actual file locations
- File operations update database atomically
- Orphan detection identifies missing files or database records
- Recovery procedures restore consistency after system issues

#### External Service Integration

- Graceful degradation when external services unavailable
- Caching reduces dependency on external services
- Fallback chains provide alternative data sources
- Rate limiting prevents service abuse and maintains access

#### Cache Management System

- **Local Memory Cache**: Default for development environments
- **Memcached Support**: Production-ready distributed caching
- **API Response Caching**: 1-hour cache for external API results
- **Cover Image Caching**: Permanent storage with cleanup utilities
- **Rate Limit Tracking**: Persistent rate limit state across restarts

#### Comic Book Processing Pipeline

- **Specialized Parsing**: Comic-specific filename pattern recognition
- **Creator Database**: Built-in knowledge of comic creators and their series
- **Archive Handling**: CBR/CBZ processing with ComicInfo.xml support
- **Cover Extraction**: First-page automatic cover generation
- **Series Management**: Intelligent series and issue number detection

#### Background Processing Architecture

- **Asynchronous Task Queue**: Non-blocking operations for large libraries
- **Progress Tracking**: Real-time progress with ETA calculations
- **Error Recovery**: Automatic retry with exponential backoff
- **Resource Management**: Memory and CPU throttling for system stability
- **API Health Monitoring**: Circuit breaker pattern for failing services

---

## Security and Data Protection

### User Authentication and Authorization

- Session-based authentication with configurable timeouts
- Role-based permissions for administrative functions
- CSRF protection on all state-changing operations
- Secure password requirements and management

### Data Validation and Sanitization

- Input validation on all user-provided data
- File path validation prevents directory traversal
- Metadata sanitization prevents XSS and injection attacks
- File type validation ensures only supported formats processed

### Privacy and Data Handling

- User data isolation in multi-user environments
- Configurable data retention policies
- Export capabilities for data portability
- Secure deletion procedures for sensitive information

---

## Performance and Scalability Considerations

### Database Optimization

- Indexed fields for common search patterns
- Query optimization for large libraries
- Connection pooling for concurrent access
- Regular maintenance procedures for optimal performance

### File System Management

- Efficient directory traversal algorithms
- Minimal file system I/O during normal operations
- Batch operations for large-scale changes
- Storage optimization through duplicate detection

### User Interface Responsiveness

- AJAX operations for real-time updates
- Progressive loading for large result sets
- Background processing for resource-intensive operations
- Caching strategies for frequently accessed data

---

## Future Architecture Enhancements

### Planned Comics and Audiobooks Architecture Improvements

The current system treats each comic file (CBR/CBZ) and audio file as individual books, which creates organizational challenges. Future improvements will implement proper grouping:

#### Enhanced Data Models (Planned)

**Comic Series Organization:**

- `Comic` model representing series/titles with metadata extracted once per series
- `ComicIssue` model for individual files with issue-specific information
- Proper series, volume, and issue number tracking
- Support for variants, annuals, and special issues

**Audiobook Organization:**

- `Audiobook` model representing complete audiobooks
- `AudiobookFile` model for individual audio files within an audiobook
- Chapter detection and continuous playback support
- Progress tracking across multiple files

#### Implementation Strategy

**File Grouping Algorithms:**

- Comics: Group by series name detection from filenames and directories
- Audiobooks: Group by directory structure or similar naming patterns
- Maintain backwards compatibility during transition

**Enhanced Scanning Logic:**

- Content-type specific processing workflows
- Metadata extraction optimization (once per group vs. per file)
- Improved UI organization with expandable series/audiobook views

**Migration Path:**

- Parallel processing during transition period
- Data migration scripts for existing collections
- Gradual rollout with fallback capabilities

These enhancements will provide more logical organization for comics and audiobooks while maintaining the robust metadata and file management capabilities of the current system.

### Content-Centric UI Architecture

The system implements a content-centric approach that prioritizes user experience through intelligent organization and presentation of media content:

#### Core Design Principles

**Content-First Organization:**

- Interface elements dynamically adapt based on content type (Ebooks, Comics, Audiobooks)
- Visual hierarchy emphasizes content discovery over administrative functions
- Consistent color coding and iconography across all content types

**Dynamic Content Presentation:**

- Cover-centric grid layouts with optimized thumbnail rendering
- Contextual metadata display appropriate for each media type
- Progressive disclosure of detailed information on user interaction

**Intelligent Filtering and Search:**

- Content-type aware search with specialized filters
- Smart categorization based on extracted metadata
- Quick access patterns for different user workflows

#### API Design Pattern

**RESTful Content Endpoints:**

- Unified API structure: `/api/v1/{content_type}/{action}/`
- Content type routing: automatically routes requests to appropriate handlers
- Consistent response formats with content-type specific payload structures

**AJAX Integration:**

- Real-time updates without full page reloads
- Progress tracking for long-running operations (scanning, metadata refresh)
- Optimistic UI updates with rollback capabilities

**Data Flow Architecture:**

```
Frontend Request → Content Type Router → Specialized Handler → Database Layer
                                    ↓
Response Formatter ← Data Transformer ← Query Results
```

**Content Type Separation:**

- Dedicated view classes per content type while maintaining shared base functionality
- Specialized form handling and validation per media type
- Type-specific metadata extraction and processing pipelines

This architecture ensures scalable content management while providing specialized user experiences for each media type, maintaining system performance even with large, diverse media collections.

---

This specification provides a comprehensive overview of the Django Ebook Management System's functionality from a user perspective. Each feature includes detailed information about expected behavior, error handling, and data integrity guarantees. The system is designed to be robust, user-friendly, and capable of managing large-scale digital library collections while maintaining data integrity and providing powerful organizational tools.
