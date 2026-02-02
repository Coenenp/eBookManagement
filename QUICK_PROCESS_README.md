# Quick Book-by-Book Processing Feature

## Overview

The Quick Process feature provides a streamlined workflow for processing books one at a time, starting from the first unprocessed book in your library. This feature is perfect for users who want to review, organize, and manage their books in a systematic, sequential manner.

## Key Features

### 1. **Sequential Processing**

- Automatically loads the first unreviewed book
- Processes books one at a time
- Skips to the next book automatically after processing

### 2. **Metadata Lookup**

- Search external sources (Google Books, Open Library) for metadata
- Supports lookup by title, author, or ISBN
- Displays all available metadata options with confidence scores

### 3. **Metadata Confirmation**

- Review all available metadata from different sources
- Click to select preferred metadata (title, author, series, publisher)
- Edit fields directly if needed
- Visual selection with confidence badges

### 4. **Cover Management**

- View all available covers from different sources
- Select multiple covers to download
- Covers are saved with the book in the new location
- Primary cover is automatically set

### 5. **Duplicate Detection**

- Automatically detects duplicate books by: - Exact file hash (identical files) - Similar metadata (same title + author)
- Choose which copies to keep
- Options: - Keep this book and delete duplicates - Keep existing books and delete this one - Keep all copies

### 6. **File Renaming & Moving**

- Configure folder and filename patterns using tokens
- Live preview of new file path
- Supports template patterns like: - `${author.sortname}` - Author (Last, First) - `${title}` - Book title - `${bookseries.title}` - Series name - `${bookseries.number}` - Series number - `${ext}` - File extension
- Automatically moves companion files (covers, OPF, metadata)

### 7. **OPF File Creation**

- Automatically creates or updates OPF metadata files
- Includes all finalized metadata
- Compatible with Calibre and other ebook managers
- Saved in the same directory as the ebook

### 8. **Companion File Management**

- Automatically detects companion files: - Cover images (.jpg, .jpeg, .png, .gif) - Metadata files (.opf, .xml) - Description files (.txt, .nfo)
- Option to include or exclude companions during move
- Maintains file relationships

### 9. **Remaining Files Handling**

- Lists all other files in the source directory
- Choose what to do with remaining files: - Leave them in the original location - Delete all remaining files - Move to a specific location

## Usage

### Accessing Quick Process

1. Navigate to **Management** → **Quick Process** in the main navigation
2. Or go directly to `/quick-process/`

### Workflow

1. **Review Current Book**
    - View current file path and basic metadata
    - See existing cover if available

2. **Lookup Metadata (Optional)**
    - Click "Lookup Metadata" button
    - Enter title, author, or ISBN
    - Wait for results to populate

3. **Select Final Metadata**
    - Click on preferred metadata options (highlighted in blue when selected)
    - Or type custom values in the input fields
    - Review all fields: title, author, series, publisher, ISBN, language, year

4. **Select Covers**
    - Click on covers you want to download
    - Selected covers show a blue border
    - Multiple covers can be selected

5. **Handle Duplicates (if found)**
    - Review list of duplicate books
    - Choose which copies to keep
    - Select action (keep this, keep existing, or keep all)

6. **Configure Rename Pattern**
    - Adjust folder pattern (default: `${author.sortname}`)
    - Adjust filename pattern (default: `${title}.${ext}`)
    - Preview shows the resulting path
    - Check "Include companion files" to move related files

7. **Handle Remaining Files**
    - Review list of other files in the directory
    - Choose action (leave, delete, or move to specific location)

8. **Confirm & Process**
    - Click "Confirm & Process" button
    - The book will be:
        - Moved to the new location
        - Renamed according to pattern
        - OPF file created/updated
        - Covers downloaded
        - Companion files moved
        - Original files cleaned up
        - Marked as reviewed

9. **Next Book**
    - Automatically loads the next unreviewed book
    - Or shows completion message if all books are processed

### Quick Actions

- **Lookup Metadata**: Search external sources for book information
- **Confirm & Process**: Execute all operations and move to next book
- **Skip This Book**: Skip without processing and move to next book
- **Delete Book**: Delete the book and all associated files

## Pattern Tokens

### Basic Tokens

- `${title}` - Book title
- `${author.sortname}` - Author (Last, First)
- `${author.fullname}` - Author full name
- `${language}` - Book language
- `${category}` - Book category
- `${ext}` - File extension

### Series Tokens

- `${bookseries.title}` - Series name
- `${bookseries.number}` - Series number (padded)
- `${bookseries.titleSortable}` - Series (sortable format)

### Advanced Tokens

- `${title[0]}` - First character of title
- `${title;first}` - First letter (A-Z) or #
- `${publicationyear}` - Publication year
- `${decadeShort}` - Decade (e.g., 2020s)
- `${format}` - File format
- `${genre}` - Genre

## Examples

### Example 1: Simple Author/Title Organization

```text
Folder Pattern: ${author.sortname}
Filename Pattern: ${title}.${ext}

Result: Asimov, Isaac/Foundation.epub
```

### Example 2: Series-Aware Organization

```text
Folder Pattern: ${author.sortname}/${bookseries.title}
Filename Pattern: ${bookseries.title} #${bookseries.number} - ${title}.${ext}

Result: Asimov, Isaac/Foundation Series/Foundation Series #01 - Foundation.epub
```

### Example 3: Category-Based Organization

```text
Folder Pattern: ${category}/${author.sortname}
Filename Pattern: ${author.sortname} - ${title}.${ext}

Result: Science Fiction/Asimov, Isaac/Asimov, Isaac - Foundation.epub
```

## Technical Details

### Files Created

- **Renamed ebook file**: Moved to new location with new name
- **OPF file**: `{book_name}.opf` - metadata file
- **Cover files**: `{book_name}_cover.jpg` (and additional if selected)
- **Companion files**: Moved with book, renamed to match

### Database Updates

- `Book.file_path` - Updated to new location
- `FinalMetadata.is_reviewed` - Set to `True`
- `FinalMetadata.is_read` - Reading status flag
- `FinalMetadata.read_date` - When book was marked as read
- `FinalMetadata.reading_progress` - Reading progress (0-100%)
- `BookFile.opf_path` - Path to OPF file
- `BookFile.cover_path` - Path to primary cover

### Atomic Operations

All file operations are wrapped in database transactions to ensure consistency. If an error occurs, changes are rolled back.

## Troubleshooting

### Book Not Appearing

- Ensure the book has files attached
- Check that `FinalMetadata` exists for the book
- Verify `is_reviewed` is `False`

### Metadata Lookup Not Working

- Check internet connection
- Verify API keys are configured (if required)
- Check scan folder permissions

### File Move Errors

- Verify write permissions on target directory
- Check disk space
- Ensure target path doesn't exceed OS limits

### Covers Not Downloading

- Check internet connection
- Verify cover URLs are valid
- Check write permissions on target directory

## API Endpoints

### Main View

- **GET** `/quick-process/` - Display current book for processing
- **POST** `/quick-process/` - Process actions (lookup, confirm, skip, delete)

### Preview Endpoint

- **GET** `/quick-process/preview/` - Generate preview of renamed path - Parameters: `book_id`, `folder_pattern`, `filename_pattern` - Returns: JSON with preview path

## Future Enhancements

- [ ] Batch processing mode (process N books at once)
- [ ] Custom sorting (by author, date added, etc.)
- [ ] Progress tracking with statistics
- [ ] Undo/revert functionality
- [ ] Export processing log
- [ ] Keyboard shortcuts for common actions
- [ ] Auto-advance option (process without confirmation)
- [ ] Custom metadata templates
- [ ] Integration with external metadata sources

## Related Features

- **Book Renamer**: Batch rename multiple books at once
- **Book Metadata View**: Detailed metadata editing
- **Scanning**: Automatic discovery and initial metadata extraction
- **Data Sources**: Configure metadata source priorities
