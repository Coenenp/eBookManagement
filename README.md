# Universal Media Manager

A comprehensive Django-based ebook and media library management system that automatically scans, organizes, and manages your digital book collection with advanced metadata extraction, external API integration, intelligent file handling, and content type organization.

## 🚀 Current Features

### Core Functionality

- **Universal Media Scanning**: Recursively scans directories for ebooks (EPUB, MOBI, PDF, AZW3), comics (CBR, CBZ), and supports content type categorization
- **AI-Powered Filename Recognition**: Machine learning system for intelligent metadata extraction from filenames with confidence scoring
- **Content Type Organization**: Dedicated handling for Ebooks, Comics, and Audiobooks media types
- **Intelligent File Organization**: Enhanced file renaming system with automatic detection of related files
- **Metadata Extraction**: Extracts metadata from file contents and external APIs with smart conflict resolution
- **Cover Management**: Automatic cover extraction and external cover downloads with caching system
- **ISBN Lookup**: Quick lookup feature to identify which book each ISBN represents during metadata review
- **Metadata Rescan**: Re-query external sources with updated search terms
- **Progress Tracking**: Real-time scan progress with resume capabilities
- **Theme Management**: User-selectable Bootswatch themes with instant preview functionality

### ✅ Recently Implemented Features

#### Content Type Support & Organization

- **Split Scan Folders by Media Type**: `content_type` field added to `ScanFolder` model with UI support
- **Media Type Categories**: Full support for Ebooks, Comics, and Audiobooks content types
- **Color-Coded UI**: Visual content type identification with Bootstrap badges throughout the interface
- **Scanning Dashboard Integration**: Content type selection and display in scan folder management
- **Form Integration**: Content type selection in both scanning dashboard and add scan folder forms

#### Enhanced UI & Theme System

- **Theme Selector Implementation**: Complete theme selection system with instant preview
- **User-Selectable Bootswatch Themes**: 25+ theme options including Darkly, Flatly, Cosmo, Cyborg, and more
- **Preview Functionality**: Real-time theme preview with CSS manipulation (no page reloads)
- **Enhanced Preview Controls**: Improved toast notifications with longer duration and better user feedback
- **Settings Page Overhaul**: Modern settings interface with theme previews and better organization

#### Expanded Format Support

- **Comic Book Support**: Full CBR/CBZ handling with ComicInfo.xml metadata extraction
- **Archive Processing**: Enhanced RAR/ZIP archive handling for comic formats
- **Content Type Routing**: Scanner automatically routes files to appropriate extractors based on content type

### AI-Powered Filename Recognition System

The system includes a sophisticated machine learning component that analyzes filename patterns to extract metadata intelligently:

#### Key Features

- **Multi-Field Extraction**: Automatically extracts title, author, series, and volume information from filenames
- **Pattern Recognition**: Uses 20+ engineered features including text patterns, numeric sequences, and structural analysis
- **Confidence Scoring**: Each prediction comes with a confidence score to ensure reliability
- **User Feedback Loop**: Learns from user corrections to improve future predictions
- **Production Ready**: Robust error handling and fallback mechanisms

#### Technical Implementation

- **Machine Learning**: RandomForestClassifier with TF-IDF text vectorization
- **Feature Engineering**: Advanced pattern detection for author names, series information, and volume numbers
- **Database Integration**: AIFeedback model stores user corrections for continuous improvement
- **Scanner Integration**: Seamlessly integrated with the scanning pipeline for enhanced metadata extraction

#### AI System Benefits

- **Reduced Manual Work**: Automatically extracts metadata from even poorly named files
- **Improved Accuracy**: Learns from your corrections to get better over time
- **Intelligent Fallback**: Works alongside traditional parsing methods for comprehensive coverage
- **User Control**: Always provides confidence scores so you can review before accepting

### Enhanced File Handling System

- **Automatic File Detection**: Detects related files (covers, metadata, documents) automatically
- **Smart File Categorization**: Distinguishes between essential files (covers, OPF) and optional files (author bios, extras)
- **Interactive File Management**: User choice interface for handling additional files during organization
- **File Action Processing**: Rename, delete, or skip individual files with full user control
- **Error Recovery**: Robust handling of file system operations with rollback capabilities

### Supported Formats & Content Types

#### Primary Ebook Formats

- **EPUB**: Full metadata extraction including internal covers
- **MOBI**: Metadata and cover extraction
- **AZW3**: Kindle format support with metadata extraction
- **PDF**: Basic metadata extraction

#### Comic/Graphic Novel Formats ✅ IMPLEMENTED

- **CBR**: Comic book RAR archives with ComicInfo.xml metadata and content extraction
- **CBZ**: Comic book ZIP archives with ComicInfo.xml metadata and content extraction
- **Automatic Comic Detection**: Content type-aware processing for comic formats

#### Content Type Organization ✅ IMPLEMENTED

- **Ebooks**: Traditional book formats (EPUB, MOBI, AZW3, PDF)
- **Comics**: Comic book archives (CBR, CBZ) with specialized handling
- **Audiobooks**: Support for MP3, M4A, M4B formats

#### Future Format Support (Planned)

- **Audio Formats**: MP3, M4A, M4B audiobook support with chapter detection
- **Additional Ebook Formats**: FB2, TXT, RTF format support
- **Enhanced Archive Processing**: Multi-ebook archives and nested folder structures

#### Comic Book Processing

The system includes specialized support for comic book formats with intelligent metadata extraction:

**Supported Formats:**

- **CBR**: Comic book RAR archives with ComicInfo.xml support
- **CBZ**: Comic book ZIP archives with automatic cover extraction
- **Content Type Integration**: Comics are processed differently from ebooks

**Smart Comic Recognition:**

- Specialized filename parsing for comic naming conventions
- Built-in database of known comic creators (Willy Vandersteen, Stan Lee, etc.)
- Automatic series and issue number detection
- No unnecessary ISBN lookups for comic files

**Comic-Specific Features:**

- ComicInfo.xml metadata extraction and processing
- First page automatic cover extraction
- Series and volume organization
- Creator and publisher information handling

**Example Processing:**

```text
Input: "De Rode Ridder - 271 - De kruisvaarder (Digitale rip).cbr"
Output:
- Title: "De kruisvaarder"
- Author: "Willy Vandersteen" (from creator database)
- Series: "De Rode Ridder"  
- Series Number: "271"
- Language: From scan folder setting
```

#### Content Type Organization ✅ IMPLEMENTED

The system supports sophisticated content type organization for multi-media libraries:

**Content Type Categories:**

- **Ebooks**: Traditional book formats (EPUB, MOBI, AZW3, PDF)
- **Comics**: Comic book archives (CBR, CBZ) with specialized handling
- **Audiobooks**: Audio content (MP3, M4A, M4B)

**Key Features:**

- Content type designation independent of file formats
- Visual organization with color-coded badges throughout UI
- Content type-aware scanning and processing  
- Dedicated interfaces for each media type

**How It Works:**

- Each scan folder is assigned a content type during setup
- Files are processed according to their folder's designation
- A PDF in "Comics" folder = treated as comic
- A PDF in "Ebooks" folder = treated as ebook
- Content appears in the appropriate section based on folder content type

**User Benefits:**

- Clear separation between different media types
- Specialized processing for each content category
- Flexible organization for diverse collections
- Administrator control over content categorization

### Web Interface

- **Modern Bootstrap UI**: Responsive design with tabbed interfaces and user-selectable themes
- **Theme Management**: 25+ Bootswatch themes with instant preview and seamless switching
- **Content Type Organization**: Color-coded badges and categorization throughout the interface
- **Scanning Dashboard**: Enhanced interface with content type selection and management
- **Book Detail Views**: Comprehensive metadata display and editing
- **Cover Gallery**: Visual cover selection and management
- **Search & Filter**: Advanced book filtering and search capabilities
- **Metadata Review**: Manual metadata review and editing workflow
- **Interactive File Renamer**: Enhanced modal interface for file organization with real-time preview
- **Settings Panel**: Comprehensive user settings with theme preview and configuration options
- **OPF Metadata Generation**: Automatic generation of OPF (Open Packaging Format) files during book renaming for standards-compliant metadata preservation

## 📋 Requirements

### System Requirements

- **Python 3.8-3.12** (tested up to 3.13)
- **Windows/Linux/macOS**
- **500MB+ free disk space**
- **Additional Windows Requirements**: Visual C++ Build Tools (for some dependencies)
- **Additional Linux Requirements**: May require `python3-dev`, `libmysqlclient-dev` packages

### Dependencies

See `requirements.txt` for complete list. Key dependencies:

- Django 5.2.6
- EbookLib 0.19 (EPUB/AZW3 processing)
- PyPDF2 3.0.1 (PDF processing)
- Pillow 11.3.0 (Image processing)
- Requests 2.32.5 (API calls)
- rarfile 4.2 (RAR/CBR archive support)
- zipfile (ZIP/CBZ archive support - built-in)

#### AI/Machine Learning Dependencies

- **scikit-learn 1.7.2**: Machine learning framework for filename pattern recognition
- **pandas 2.3.2**: Data manipulation and analysis for training data processing
- **scipy 1.16.2**: Scientific computing support for advanced ML operations

## 🛠 Installation

### 1. Clone Repository

```bash
git clone https://github.com/Coenenp/eBookManagement.git
cd ebook_library_manager
```

### 2. Setup Virtual Environment

```bash
python -m venv venv
# Windows
venv\Scripts\activate
# Linux/macOS
source venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Database Setup

#### Option A: SQLite (Default - Easy Setup)

```bash
python manage.py migrate
```

#### Option B: MySQL/MariaDB (Recommended for Large Collections 50K+ books)

**Prerequisites**: MySQL 5.7+ or MariaDB 10.3+ installed and running

1. **Create Database and User**:

   ```sql
   CREATE DATABASE ebook_manager CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
   CREATE USER 'ebook_user'@'localhost' IDENTIFIED BY 'your_password';
   GRANT ALL PRIVILEGES ON ebook_manager.* TO 'ebook_user'@'localhost';
   FLUSH PRIVILEGES;
   ```

2. **Configure Environment Variables**:
   Create/update `.env` file:

   ```env
   USE_SQLITE_TEMPORARILY=False
   DB_NAME=ebook_manager
   DB_USER=ebook_user
   DB_PASSWORD=your_password
   DB_HOST=localhost
   DB_PORT=3306
   ```

3. **Install MySQL Driver**:

   ```bash
   pip install mysqlclient
   ```

4. **Run Migrations**:

   ```bash
   python manage.py migrate
   ```

**Performance Benefits**: MySQL/MariaDB provides 5-10x performance improvement for large collections, full-text search, and concurrent user support.

### 5. Cache Configuration (Optional)

Create a `.env` file in the project root to configure caching:

```env
CACHE_BACKEND=locmem
```

**Cache Backend Options**:

- `locmem`: Local memory cache (default, no external dependencies required)
- `memcached`: Memcached for production (requires external Memcached service)

**Development**: The default `locmem` setting works out of the box with no additional setup.

**Production**: For high-traffic applications, install and configure Memcached, then set `CACHE_BACKEND=memcached`.

### 6. Create Superuser (Optional)

```bash
python manage.py createsuperuser
```

### 7. Run Development Server

```bash
python manage.py runserver
```

Visit `http://127.0.0.1:8000` to access the application.

## 📚 Usage

### Initial Setup

1. **Add Scan Folders**: Navigate to the admin interface to add directories containing your ebooks
2. **Start Scanning**: Use the scan interface to begin scanning your ebook collection
3. **Review Metadata**: Review and edit extracted metadata as needed

### Scanning Process

The system performs a multi-stage scan:

1. **File Discovery**: Recursively finds all supported ebook files (EPUB, MOBI, AZW3, PDF, CBR, CBZ)
2. **Metadata Extraction**: Extracts internal metadata and covers
3. **External API Queries**: Queries Google Books, Open Library, and Goodreads for additional metadata
4. **Cover Processing**: Downloads and processes book covers
5. **Metadata Consolidation**: Creates final consolidated metadata

### Metadata Management

- **Final Metadata**: Consolidated, user-reviewable metadata for each book
- **Source Tracking**: Tracks metadata sources with confidence scores based on trust hierarchy
- **Manual Override**: Manual metadata editing with source attribution
- **Rescan Capability**: Re-query external sources with updated search terms

### Background Scanning & Management Commands

For large collections and automation, the system provides command-line tools:

#### Background Scanning Commands

```bash
# Scan a folder in the background
python manage.py scan_books scan /path/to/books --language en --background --wait

# Rescan existing books
python manage.py scan_books rescan --all --background
python manage.py scan_books rescan --folder /path/to/books
python manage.py scan_books rescan --book-ids 1,2,3,4

# Monitor scan progress
python manage.py scan_books status --job-id abc123
python manage.py scan_books status --apis

# List active scans
python manage.py scan_books list

# Cancel a running scan
python manage.py scan_books cancel abc123
```

#### Additional Management Commands

```bash
# Complete metadata processing
python manage.py complete_metadata

# Train AI models with new data
python manage.py train_ai_models

# Debug specific books
python manage.py debug_books --book-id 123

# Content-specific ISBN scanning
python manage.py scan_content_isbn
```

**Background Processing Benefits:**

- Large scan operations don't block the web interface
- Real-time progress tracking with ETA calculations
- Resume capability for interrupted operations
- API rate limiting ensures respectful external API usage
- Error recovery and automatic retry logic

#### Data Source Trust Hierarchy

The system uses a smart trust level hierarchy to automatically resolve conflicts when multiple sources provide different metadata for the same book. This ensures you get the most reliable information automatically.

**How It Works**: When the system finds conflicting metadata (e.g., different publication years from different sources), it automatically selects the information from the most trusted source.

| Priority | Data Source | Trust Level | Why It's Trusted |
|----------|-------------|-------------|------------------|
| 1 | Manual Entry | 1.0 | You verified it personally (highest priority) |
| 2 | Open Library | 0.95 | Highly curated, community-verified database |
| 3 | OPF File | 0.9 | Official publisher metadata files |
| 4 | Content Scan | 0.85 | Extracted directly from book content |
| 5 | EPUB Internal | 0.8 | Well-structured ebook format with good metadata |
| 6 | MOBI Internal | 0.75 | Good format but with some limitations |
| 7 | Google Books | 0.7 | Comprehensive but less curated than Open Library |
| 8 | PDF Internal | 0.6 | PDFs have limited, often incomplete metadata |
| 9 | Filename | 0.2 | Last resort - filenames are often unreliable |

**User Benefits**:

- **Consistent Results**: Same book always gets the same metadata regardless of scan order
- **Quality Assurance**: Higher quality sources automatically take priority
- **Manual Override**: Your manual edits always take highest priority
- **Transparent Process**: You can see which source provided each piece of metadata

This hierarchy ensures consistent, predictable metadata resolution when multiple sources provide conflicting information.

### ISBN Lookup Feature

The system includes a quick ISBN lookup feature to help users distinguish between multiple ISBNs during metadata review:

#### Features

- **One-Click Lookup**: "Lookup" buttons appear next to each valid ISBN in the metadata review interface
- **Multi-Source Queries**: Uses Google Books and Open Library APIs for comprehensive book information
- **Visual Results**: Displays book title, author(s), publisher, publication date, and description
- **Cover Thumbnails**: Shows book cover images when available from external sources
- **Caching**: Results are cached for 1 hour to improve performance and reduce API calls
- **Validation**: Only valid ISBN-10 and ISBN-13 formats show lookup buttons

#### User Benefits

- **Informed Decisions**: See what book each ISBN represents before selecting the correct one
- **Metadata Verification**: Compare external information with extracted metadata
- **Enhanced Workflow**: Streamlined metadata review process with contextual information
- **Error Prevention**: Avoid selecting incorrect ISBNs by seeing actual book details

This feature significantly improves the metadata review workflow by providing users with the information needed to make informed decisions about ISBN selection.

## 🔮 Roadmap: Implemented vs Planned Features

### ✅ Recently Completed (2025)

#### Core Intelligence & Content Organization

- **✅ Content Type Support**: Complete implementation of media type categorization (Ebooks, Comics, Audiobooks)
- **✅ Split Scan Folders by Media Type**: Full UI and backend support for content type-specific scanning
- **✅ Theme & UI Overhaul**: Complete theme selection system with 25+ Bootswatch themes and instant preview
- **✅ Enhanced Comic Support**: Full CBR/CBZ processing with ComicInfo.xml metadata extraction

#### UI & UX Enhancements

- **✅ User-Selectable Themes**: Complete implementation with real-time preview and CSS manipulation
- **✅ Enhanced Settings Interface**: Modern settings page with theme management and improved user experience
- **✅ Content Type UI Integration**: Color-coded badges and visual identification throughout all interfaces
- **✅ Improved Toast Notifications**: Enhanced preview controls with better timing and user feedback

### 🚧 In Progress & Next Priority

#### Format & Media Expansion

- **🔄 Audiobook Support**: MP3, M4A, M4B processing with chapter detection and ID3 tag metadata extraction
- **🔄 Enhanced Archive Processing**: Improved handling of multi-ebook archives and nested folder structures
- **🔄 Additional Ebook Formats**: FB2, TXT, RTF format support with content-aware processing

#### AI & Intelligence Features

- **🔄 Enhanced AI Filename Recognition**: Ensemble ML models for improved accuracy and multi-language support
- **🔄 Automated Genre Classification**: Content analysis for automatic genre tagging
- **🔄 Review-Based Learning System**: Enhanced AI feedback loop using user corrections and review data

### 📋 Future Planned Features

#### Advanced Metadata & Organization

- **📅 OFP Format & Naming for Ebooks**: Customizable file naming templates with preview functionality
- **📅 JMTE-Based Renamer System**: Advanced template-based renaming with token system
- **📅 Metadata Scraper Selection**: Registry system for per-media-type scraper configuration
- **📅 Scraper Configuration Panel**: Per-scraper settings with API key management and field selection

#### UI & Experience Enhancements

- **📅 Segmented UI Areas**: Dedicated sections for Ebooks, Series, Comics, Audiobooks with tailored views
- **📅 Dashboard & Analytics**: Visualizations for format distribution, metadata completeness, and parsing accuracy
- **📅 Scan Folder Setup Wizard**: First-login wizard for folder configuration with skip options
- **📅 Enhanced Search & Filtering**: Advanced search across all media types with content-specific filters

#### Data Management & Integration

- **📅 Import/Export Between Installations**: Complete data migration system with compatibility validation
- **📅 Database Initialization**: Enhanced init_library command with UI integration
- **📅 Cover Image Management**: Advanced caching system with cache statistics and management tools
- **📅 Cloud Integration**: Google Drive, Dropbox, OneDrive sync capabilities

#### Advanced Features

- **📅 Full-Text Search**: Search within ebook content and metadata
- **📅 Reading Progress Tracking**: Integration with ebook readers
- **📅 Social Features**: Book recommendations and reading list sharing
- **📅 Plugin Architecture**: Extensible system for custom format support and integrations

#### Legal & Compliance

- **📅 Disclaimer Acceptance**: Login disclaimer system based on tinyMediaManager approach
- **📅 Enhanced Privacy Controls**: Granular privacy settings and data sharing options

### 🎯 Current Development Focus

The current development cycle is focused on completing the media type ecosystem:

1. **Audiobook Processing Pipeline**: Implementing MP3/M4A/M4B support with chapter detection
2. **Enhanced Format Support**: Adding FB2, TXT, RTF processing capabilities  
3. **AI System Improvements**: Ensemble models and multi-language filename recognition
4. **Advanced UI Components**: Segmented media type interfaces and enhanced analytics

### 📊 Implementation Progress

- **✅ Content Organization**: 100% Complete (Media types, UI integration, scanning support)
- **✅ Theme System**: 100% Complete (Theme selection, preview, settings integration)
- **✅ Comic Support**: 100% Complete (CBR/CBZ processing, metadata extraction)
- **🔄 Audiobook Support**: 30% Complete (Planning phase, initial format research)
- **📅 Advanced AI Features**: 0% Complete (Next major development cycle)
- **📅 Cloud Integration**: 0% Complete (Future enhancement phase)

### 🔮 Planned Features

### Future Enhancements

- **Audiobook Support**: Full MP3, M4A, M4B audiobook processing with chapter detection and metadata extraction
- **Enhanced Archive Processing**: Improved handling of RAR/ZIP archives containing multiple ebooks
- **Advanced AI Features**:
  - Ensemble ML models for improved metadata prediction accuracy
  - Multi-language filename pattern recognition
  - Automated genre classification from content analysis
- **Additional Format Support**: FB2, TXT, RTF, and other ebook formats
- **Cloud Integration**: Google Drive, Dropbox, and OneDrive sync capabilities
- **Advanced Search**: Full-text search within ebook content
- **Reading Progress Tracking**: Integration with ebook readers to track reading progress
- **Social Features**: Book recommendations and reading lists sharing

### Resume Functionality

If scans are interrupted:

```bash
python resume_scan.py
```

## 🏗 Architecture

### Django Applications

- **books**: Core ebook management functionality
- **ebook_manager**: Main Django project configuration

### Key Models

- **Book**: Core book entity with file information
- **FinalMetadata**: User-reviewable consolidated metadata
- **BookTitle/BookAuthor/etc**: Source-attributed metadata entities
- **ScanStatus**: Scan progress tracking
- **DataSource**: Metadata source management
- **AIFeedback**: User feedback system for AI predictions with 5-point rating system and correction tracking

### External API Integration

The system integrates with multiple external APIs to provide comprehensive metadata enhancement:

#### Primary APIs

- **Google Books API**: Primary metadata source with extensive book database
- **Open Library API**: Community-driven metadata and cover images
- **Comic Vine API**: Specialized comic book metadata and creator information

#### API Rate Limiting & Background Processing

The system includes sophisticated rate limiting to respect external API quotas:

- **Google Books**: 1,000 requests/day with intelligent backoff
- **Comic Vine**: 200 requests/hour with circuit breaker protection
- **Open Library**: 60 requests/minute with community-respectful delays

**Background Scanning Features:**

- Asynchronous folder scanning for large collections
- Real-time progress tracking with ETA calculations
- Automatic retry logic and error recovery
- API health monitoring during scanning
- Resume capability for interrupted scans

#### Integration Features

- **Automatic Querying**: All APIs are queried automatically during scanning
- **Smart Fallback**: If one API fails, others continue to provide data
- **Trust Hierarchy**: Results are automatically prioritized based on source reliability (see [Data Source Trust Hierarchy](#data-source-trust-hierarchy))
- **Caching**: API responses are cached to improve performance and reduce API calls
- **No API Keys Required**: Basic functionality works without any API key configuration
- **Background Processing**: Large scan operations run in background without blocking the UI

## 🔧 Configuration

### Environment Variables

Create a `.env` file in the project root:

```env
DEBUG=True
SECRET_KEY=your-secret-key-here
ALLOWED_HOSTS=localhost,127.0.0.1

# Database Configuration (Optional - defaults to SQLite)
USE_SQLITE_TEMPORARILY=True
DB_NAME=ebook_manager
DB_USER=ebook_user
DB_PASSWORD=your_password
DB_HOST=localhost
DB_PORT=3306

# Cache Configuration (Optional - defaults to local memory)
CACHE_BACKEND=locmem  # or 'memcached' for production
```

### Cache Configuration

The system uses intelligent caching for performance:

- **Development**: Local memory cache (no external dependencies)
- **Production**: Memcached or Redis for shared caching
- **API Responses**: Cached for 1 hour to reduce external API calls
- **Cover Images**: Permanent caching with cleanup utilities

**Cache Backend Options:**

- `CACHE_BACKEND=locmem` (default) - Django's built-in local memory cache, no external dependencies
- `CACHE_BACKEND=memcached` - Memcached for production environments with shared caching
- `CACHE_BACKEND=redis` - Redis for advanced caching with persistence (if configured)

**Troubleshooting Cache Issues:**
If you encounter connection errors during scanning, ensure your `.env` file includes `CACHE_BACKEND=locmem` for development setups.

### API Configuration

External APIs are automatically used. No API keys required for basic functionality.

**Optional API Keys for Enhanced Features:**

- Google Books API: Increased rate limits and enhanced metadata
- Comic Vine API: Extended comic book database access
- Open Library: No API key needed (community service)

## 🧪 Testing & Quality Assurance

The system includes a comprehensive test suite with **554 test cases** covering all functionality. This ensures reliability and helps prevent issues as the system evolves.

### Current Test Status

- **✅ All Tests Passing**: 554/554 tests passing (100% success rate)
- **Comprehensive Coverage**: Core functionality, AI system, database operations, web interface, file handling
- **AI System Testing**: Complete ML pipeline testing including feature extraction, model training, and prediction accuracy
- **Integration Testing**: End-to-end workflow testing from scanning to metadata finalization

### Why Testing Matters for Users

- **Reliability**: Extensive testing prevents data loss and scanning failures
- **Quality Assurance**: Your metadata and files are handled safely
- **Regression Prevention**: New features won't break existing functionality
- **Error Detection**: Issues are caught before they affect your library
- **AI Accuracy**: Machine learning components are validated for consistent performance

### Test Coverage Overview

- **Scanner Engine**: File discovery, metadata extraction, error recovery
- **AI System**: Machine learning pipeline, feature extraction, prediction accuracy, user feedback processing
- **Database Operations**: Book storage, relationship management, data integrity
- **Web Interface**: All views, forms, and user interactions
- **File Handling**: Book renaming, cover processing, file operations
- **External APIs**: Google Books, Open Library integration
- **Edge Cases**: Unicode handling, malformed files, network issues

### Running Tests (Optional)

If you're technically inclined, you can verify system functionality:

```bash
# Test all functionality
python manage.py test books.tests

# Test specific components
python manage.py test books.tests.test_scanner_engine
python manage.py test books.tests.test_views
```

### Advanced Testing (Optional)

Test your database setup with included utilities:

```bash
# Test SQLite (default)
python manage.py test books.tests.test_models

# Test MySQL/MariaDB connection
python -c "
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ebook_manager.settings')
django.setup()
from django.db import connection
with connection.cursor() as cursor:
    cursor.execute('SELECT VERSION()')
    print(f'✅ Database connected: {cursor.fetchone()[0]}')
"
```

### Test Organization

The test suite is organized into focused areas:

- **Model Testing**: Database operations, relationships, and data validation
- **AI Testing**: Machine learning pipeline, feature engineering, prediction accuracy, user feedback integration
- **View Testing**: Web interface, authentication, and user interactions
- **File Handling**: Book renaming, file operations, and error recovery
- **Scanner Engine**: Metadata extraction, progress tracking, and resume functionality
- **External APIs**: Integration testing for Google Books and Open Library
- **Edge Cases**: Unicode handling, malformed files, and error conditions

## 📁 Project Structure

```text
ebook_library_manager/
├── books/                          # Core application
│   ├── models.py                   # Database models with content type support
│   ├── views.py                    # Web views, AJAX endpoints, and theme management
│   ├── forms.py                    # Form classes with content type integration
│   ├── context_processors.py       # Theme context processor for template rendering
│   ├── admin.py                    # Django admin configuration
│   ├── urls.py                     # URL routing including theme preview endpoints
│   ├── scanner/                    # Scanning engine
│   │   ├── scanner_engine.py       # Main scanning logic
│   │   ├── external.py             # External API integration
│   │   ├── bootstrap.py            # Data source initialization
│   │   ├── ai/                     # AI-powered filename recognition
│   │   │   ├── __init__.py         # AI system initialization
│   │   │   ├── filename_recognizer.py # ML pipeline for metadata extraction
│   │   │   └── models/             # Trained ML models and training data
│   │   │       └── training_data.csv # Training dataset for ML models
│   │   ├── extractors/             # Format-specific extractors
│   │   │   ├── epub.py             # EPUB metadata extraction
│   │   │   ├── mobi.py             # MOBI/AZW3 metadata extraction
│   │   │   ├── pdf.py              # PDF metadata extraction
│   │   │   ├── comic.py            # CBR/CBZ comic archive extraction
│   │   │   ├── archive.py          # RAR/ZIP archive handling
│   │   │   └── opf.py              # OPF metadata files
│   │   └── ...
│   ├── templates/                  # HTML templates
│   │   ├── books/                  # Book-specific templates
│   │   │   ├── user_settings.html  # Enhanced settings page with theme management
│   │   │   ├── scanning/           # Scanning dashboard templates
│   │   │   │   └── dashboard.html  # Content type-aware scanning interface
│   │   │   ├── book_list.html      # Book listing page
│   │   │   ├── book_detail.html    # Book detail view
│   │   │   ├── book_renamer.html   # Enhanced file organization interface
│   │   │   ├── scanning/
│   │   │   │   ├── folder_list.html # Content type display in folder management
│   │   │   ├── add_scan_folder.html # Content type selection in folder creation
│   │   │   └── ...
│   │   └── ...
│   ├── static/                     # CSS/JS/Images
│   │   ├── book/                   # Book-specific assets
│   │   │   ├── css/                # Stylesheets
│   │   │   ├── js/                 # JavaScript files
│   │   │   └── images/             # Static images
│   │   └── ...
│   ├── tests/                      # Comprehensive test suite
│   │   ├── test_models.py          # Model testing
│   │   ├── test_views.py           # View and integration testing
│   │   ├── test_book_renamer.py    # File handling system tests
│   │   ├── test_forms.py           # Form validation testing
│   │   ├── test_scanner_engine.py  # Scanner functionality tests
│   │   ├── test_ai_filename_recognition.py # AI system comprehensive tests
│   │   ├── test_ai_working.py      # AI core functionality tests
│   │   ├── test_comic_renamer.py   # Comic book handling tests
│   │   └── ...
│   ├── utils/                      # Utility functions
│   │   ├── author.py               # Author name processing
│   │   ├── image_utils.py          # Image processing utilities
│   │   ├── isbn.py                 # ISBN validation and formatting
│   │   └── ...
│   ├── templatetags/               # Custom template tags
│   ├── migrations/                 # Database migrations
│   └── ...
├── ebook_manager/                  # Django project configuration
│   ├── settings.py                 # Django settings
│   ├── urls.py                     # Main URL configuration
│   ├── wsgi.py                     # WSGI application
│   └── ...
├── media/                          # User-uploaded and processed files
│   ├── cover_cache/                # Cached book covers
│   └── ...
├── staticfiles/                    # Collected static files for production
├── requirements.txt                # Python dependencies
├── manage.py                       # Django management script
├── .env                           # Environment variables (create manually)
└── README.md                      # This comprehensive guide
```

## 🔍 Key Features Deep Dive

### Metadata Extraction

- **Multi-source**: Combines internal metadata with external APIs
- **Confidence Scoring**: Each metadata piece has a confidence score
- **Conflict Resolution**: Intelligent handling of conflicting metadata
- **Manual Review**: User workflow for metadata validation

### Cover Management

- **Multiple Sources**: Internal extraction + external downloads
- **Resolution Priority**: Higher resolution covers preferred
- **Fallback System**: Multiple cover sources ensure availability
- **User Selection**: Manual cover selection interface

### Scanning Engine

- **Resumable**: Interrupted scans can be resumed
- **Progress Tracking**: Real-time progress updates
- **Error Handling**: Comprehensive error logging and recovery
- **Performance**: Optimized for large collections

### Rescan Functionality

- **Smart Search**: Uses final metadata as search terms
- **Source Selection**: Choose which external sources to query
- **Custom Search**: Override search terms manually
- **Progress Tracking**: Real-time rescan progress

### Enhanced File Organization System

The system now includes intelligent file handling capabilities:

#### Automatic File Detection

- **Related Files**: Automatically detects files with the same base name but different extensions
- **Cover Images**: JPG, PNG, GIF files are automatically identified as book covers
- **Metadata Files**: OPF and JSON files are recognized as metadata companions
- **Additional Content**: Text files, documents, and author materials are categorized appropriately

#### Interactive File Management

- **User Choice Interface**: Modal dialog presents all detected files with action options
- **Smart Categorization**:
  - **Automatic Files**: Covers (.jpg, .png), metadata (.opf, .json) - renamed automatically
  - **Optional Files**: Documents (.txt, .md, .pdf), extras - user chooses action
- **File Actions**: For each file, users can choose to:
  - **Rename**: Move with the book using the new naming scheme
  - **Delete**: Remove the file permanently
  - **Skip**: Leave the file in its original location

#### File Operation Features

- **Batch Processing**: Handle multiple books with their associated files simultaneously
- **Error Recovery**: Robust rollback mechanism if operations fail
- **Operation Tracking**: Complete audit trail of all file operations
- **Size and Type Display**: User-friendly file information with formatted sizes and descriptions
- **Conflict Detection**: Warns about potential naming conflicts before processing

### OPF Metadata File Generation

The system automatically generates OPF (Open Packaging Format) metadata files during the book renaming process, preserving all your curated metadata in a professional, industry-standard format.

#### How It Works

- **Automatic Generation**: OPF files are created automatically when you rename books through the web interface
- **File Location**: Saved in the same directory as the renamed ebook file (e.g., `book.epub` → `book.opf`)
- **Standards Compliance**: Full Dublin Core metadata format with proper XML namespaces
- **Calibre Compatible**: Includes Calibre-specific series metadata for seamless library integration

#### What's Included

- **Core Metadata**: Title, author, publisher, language, publication year
- **Identifiers**: ISBN and custom identifiers
- **Series Information**: Series name and number (Calibre-compatible format)
- **Descriptions**: Book summaries and descriptions
- **Quality Metrics**: Confidence scores and review status for data provenance

#### Benefits for Users

- **Data Security**: Your curated metadata is preserved outside the database in a standard format
- **Tool Compatibility**: Works seamlessly with Calibre, Adobe Digital Editions, and other ebook management software
- **Professional Distribution**: Include standardized metadata files when sharing or distributing ebooks
- **Future-Proofing**: Industry-standard format ensures long-term accessibility of your metadata
- **Library Migration**: Easily import your books and metadata into other ebook management systems

#### Usage

Simply use the Book Renamer feature in the web interface - OPF files are generated automatically for each renamed book. No additional configuration required.

## 🔧 Customization

### Adding New Ebook Formats

1. Create extractor in `books/scanner/extractors/`
2. Register in `scanner_engine.py`
3. Update file type detection

### Adding External APIs

1. Implement API client in `books/scanner/external.py`
2. Add to source selection options
3. Update confidence scoring

### UI Customization

- Templates in `books/templates/`
- Static files in `books/static/`
- Bootstrap 5 based styling

## 🐛 Troubleshooting

### Common Issues

#### CBR/CBZ Comic Processing Issues

**Windows Permission Errors:**

- If you see "PermissionError: The process cannot access the file" for CBR files
- This has been fixed with improved Windows-compatible temporary file handling
- Ensure the media/cover_cache directory has write permissions

**Comic Metadata Issues:**

- Comics now use specialized parsing for proper title/author/series extraction
- Comic Vine API integration provides enhanced metadata for comic books
- ISBN scanning is automatically skipped for comic files (more efficient)

#### Database Integrity Issues

**Duplicate File Path Errors:**

- MySQL errors like "Duplicate entry for key 'books_book.file_path_hash'" are now handled gracefully
- The system includes race condition protection for concurrent scanning
- Enhanced error reporting helps identify the specific conflict

**Migration Issues:**

- Run `python manage.py migrate` after any updates
- For MySQL issues, ensure UTF8MB4 encoding is configured correctly
- Use `python manage.py shell -c "from books.scanner.bootstrap import ensure_data_sources; ensure_data_sources()"` to verify data sources

#### API Rate Limiting Issues

**External API Failures:**

- The system now includes comprehensive rate limiting for all external APIs
- Circuit breaker protection prevents cascading failures
- Background scanning respects API quotas automatically
- Check API status with: `python manage.py scan_books status --apis`

#### Theme and UI Issues

**Theme Not Loading:**

- Clear browser cache if themes appear broken
- Verify the theme selection in user settings
- Default theme is Flatly - fallback to Bootstrap default if needed
- Check browser console for CSS loading errors

#### Scan Not Starting

- Check scan folder permissions
- Verify Python path in virtual environment
- Check Django database migrations

#### Missing Covers

- Verify internet connectivity for external APIs
- Check media directory permissions
- Review scan logs for errors

#### Performance Issues

- Consider database indexing for large collections
- Monitor memory usage during scans
- Adjust concurrent processing settings

#### MySQL Index Key Length Issues

If you encounter `(1071, 'Specified key was too long; max key length is 3072 bytes')` errors:

- This occurs when using MySQL with UTF8MB4 encoding and long unique fields
- The system uses 191-character limits for unique fields (file paths) to ensure compatibility
- For very long file paths (>191 chars), consider shortening directory structures
- Alternative: Use SQLite for testing or PostgreSQL for production with longer path support

### Logs

- Application logs: `ebook_scanner.log`
- Django logs: Console output during development
- Scan logs: Available in web interface

## 📚 User Guide Summary

This README contains comprehensive information about all system features:

### Current Functionality Covered

- **Complete Installation Guide**: From basic setup to advanced MySQL configuration
- **Comprehensive Format Support**: EPUB, MOBI, AZW3, PDF, CBR, CBZ with full metadata extraction
- **AI-Powered Processing**: Machine learning filename recognition with 20+ engineered features
- **Scanning & Metadata**: How the system discovers, processes, and enhances your ebook collection
- **Trust Level System**: How the system automatically chooses the best metadata from multiple sources
- **External API Integration**: Detailed coverage of Google Books, Open Library, and Goodreads integration
- **File Organization**: Intelligent file handling with user control over related files
- **OPF Generation**: Automatic creation of industry-standard metadata files
- **Quality Assurance**: How 554+ automated tests ensure your data stays safe

### Future Roadmap Outlined

- **Audiobook Support**: Planned MP3, M4A, M4B processing capabilities
- **Enhanced Archive Handling**: Improved RAR/ZIP processing for multiple ebooks
- **Advanced AI Features**: Ensemble models and multi-language support
- **Cloud Integration**: Sync capabilities with major cloud storage providers

### User Benefits Highlighted

- **Automated Processing**: Minimal manual work required for large collections
- **Data Safety**: Multiple backup mechanisms and error recovery systems
- **Professional Results**: Industry-standard outputs compatible with other tools
- **Future-Proofing**: Standards-based approach ensures long-term accessibility
- **User Control**: Extensive customization while maintaining simplicity

## 🤝 Contributing

This is a personal project, but you're welcome to:

1. Fork the repository
2. Create feature branches
3. Submit pull requests
4. Report issues

## 📄 License

This project is open source. Feel free to use, modify, and distribute according to your needs.

## 🙏 Acknowledgments

- **Django Team**: For the excellent web framework
- **EbookLib**: For EPUB processing capabilities
- **External APIs**: Google Books, Open Library for metadata
- **Bootstrap**: For responsive UI components

---

---

## 🎉 Recent Development Highlights

### What's New in 2025

The Universal Media Manager has undergone significant enhancements, evolving from a single-purpose ebook manager into a comprehensive media library system:

#### 🎨 Complete Theme System Implementation

- **25+ Professional Themes**: From classic Bootstrap to modern Darkly, Cyborg, and more
- **Instant Preview**: Real-time theme switching without page reloads
- **Enhanced User Experience**: Improved settings interface with better feedback and longer notification times

#### 📚 Content Type Organization

- **Multi-Media Support**: Dedicated handling for Ebooks, Comics, and Audiobooks content
- **Visual Organization**: Color-coded badges and interface elements for easy content identification
- **Smart Scanning**: Content type-aware processing with specialized extractors

#### 🖼️ Enhanced Comic Book Support

- **Full CBR/CBZ Processing**: Complete comic archive handling with metadata extraction
- **ComicInfo.xml Support**: Automatic detection and processing of comic metadata standards
- **Specialized UI Elements**: Comic-specific interface components and workflows

#### 🔧 Developer Experience Improvements

- **Comprehensive Testing**: 554+ automated tests ensuring reliability and data safety
- **Enhanced Documentation**: Complete feature coverage and implementation guides
- **Future-Ready Architecture**: Modular design supporting planned audiobook and advanced AI features

### Impact on User Experience

These implementations provide immediate benefits:

- **Personalized Interface**: Choose from 25+ themes to match your preferences
- **Organized Collections**: Clear visual distinction between different media types  
- **Streamlined Workflow**: Content type-aware scanning and processing
- **Professional Results**: Industry-standard metadata and file organization
- **Reliable Operation**: Comprehensive testing ensures your data stays safe

### Looking Forward

With the foundation for content type organization and theme management complete, the next development cycle will focus on:

1. **Audiobook Processing**: Complete MP3/M4A/M4B support with chapter detection
2. **Advanced AI Features**: Enhanced machine learning for better metadata extraction
3. **Segmented UI Areas**: Dedicated interfaces for each media type
4. **Cloud Integration**: Sync capabilities with major cloud storage providers

The project continues to evolve toward becoming the definitive universal media management solution while maintaining its core strengths in reliability, user control, and professional results.

### Happy Reading! 📚

For questions or support, please check the issue tracker or create a new issue in the repository.
