"""Comic book archive metadata extraction (CBR/CBZ).

This module provides metadata extraction for comic book archives:
- CBR: Comic Book RAR archives
- CBZ: Comic Book ZIP archives

Features:
- Extract title from filename with intelligent cleaning
- Extract first image as cover
- Parse ComicInfo.xml for detailed metadata
- Extract metadata from filename patterns
"""
import logging
import zipfile
import rarfile
import os
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from PIL import Image
from django.conf import settings
from books.models import Book, DataSource, BookTitle, BookCover, BookPublisher, Publisher, BookMetadata

logger = logging.getLogger("books.scanner")


def extract_cbr(book):
    """Extract metadata from CBR (Comic Book RAR) files"""
    try:
        source = DataSource.objects.get(name=DataSource.CONTENT_SCAN)

        # Basic validation
        if not rarfile.is_rarfile(book.file_path):
            logger.warning(f"CBR file is not a valid RAR archive: {book.file_path}")
            return None

        # Extract metadata from filename using comic-specific parsing
        from books.scanner.parsing import parse_comic_metadata
        filename_metadata = parse_comic_metadata(book.file_path)

        file_stem = Path(book.file_path).stem
        title = filename_metadata.get("title") or _clean_comic_title(file_stem)

        extracted_data = {
            "title": title,
            "source": source,
            "format": "cbr",
            "series": filename_metadata.get("series"),
            "series_number": filename_metadata.get("series_number"),
            "authors": filename_metadata.get("authors", [])
        }

        with rarfile.RarFile(book.file_path, 'r') as rar_file:
            # Extract ComicInfo.xml if present
            comic_info = _extract_comic_info_xml(rar_file)
            if comic_info:
                extracted_data.update(comic_info)

            # Extract first image as cover
            cover_path = _extract_first_image_as_cover(rar_file, book, 'cbr')
            if cover_path:
                extracted_data["cover_path"] = cover_path

        # Save metadata to database
        _save_comic_metadata(book, extracted_data, filename_metadata, source)

        # Try to enrich metadata with Comic Vine if available
        _enrich_with_comicvine(book, extracted_data)

        logger.info(f"CBR metadata extracted: {title or 'Unknown'}")
        return extracted_data

    except Exception as e:
        logger.warning(f"CBR metadata extraction failed for {book.file_path}: {e}")
        return None


def extract_cbz(book):
    """Extract metadata from CBZ (Comic Book ZIP) files"""
    try:
        source = DataSource.objects.get(name=DataSource.CONTENT_SCAN)

        # Basic validation
        if not zipfile.is_zipfile(book.file_path):
            logger.warning(f"CBZ file is not a valid ZIP archive: {book.file_path}")
            return None

        # Extract metadata from filename using comic-specific parsing
        from books.scanner.parsing import parse_comic_metadata
        filename_metadata = parse_comic_metadata(book.file_path)

        file_stem = Path(book.file_path).stem
        title = filename_metadata.get("title") or _clean_comic_title(file_stem)

        extracted_data = {
            "title": title,
            "source": source,
            "format": "cbz",
            "series": filename_metadata.get("series"),
            "series_number": filename_metadata.get("series_number"),
            "authors": filename_metadata.get("authors", [])
        }

        with zipfile.ZipFile(book.file_path, 'r') as zip_file:
            # Extract ComicInfo.xml if present
            comic_info = _extract_comic_info_xml(zip_file)
            if comic_info:
                extracted_data.update(comic_info)

            # Extract first image as cover
            cover_path = _extract_first_image_as_cover(zip_file, book, 'cbz')
            if cover_path:
                extracted_data["cover_path"] = cover_path

        # Save metadata to database
        _save_comic_metadata(book, extracted_data, filename_metadata, source)

        # Try to enrich metadata with Comic Vine if available
        _enrich_with_comicvine(book, extracted_data)

        logger.info(f"CBZ metadata extracted: {title or 'Unknown'}")
        return extracted_data

    except Exception as e:
        logger.warning(f"CBZ metadata extraction failed for {book.file_path}: {e}")
        return None


def _clean_comic_title(filename):
    """Clean up comic book title from filename

    Removes common patterns like:
    - Issue numbers: #001, #1, (2023), etc.
    - Volume indicators: Vol.1, V1, etc.
    - Underscores and excessive spaces
    """
    import re

    if not filename:
        return None

    # Replace underscores with spaces
    title = filename.replace('_', ' ')

    # Remove common comic patterns
    patterns_to_remove = [
        r'\s*#\d+.*$',           # #001, #1 (2023), etc.
        r'\s*\(\d{4}\).*$',      # (2023), (2020-2021), etc.
        r'\s*Vol\.?\s*\d+.*$',   # Vol.1, Vol 2, V1, etc.
        r'\s*v\d+.*$',           # v1, v2, etc.
        r'\s*\d{4}.*$',          # Year at end
    ]

    for pattern in patterns_to_remove:
        title = re.sub(pattern, '', title, flags=re.IGNORECASE)

    # Clean up spacing
    title = ' '.join(title.split())

    return title.strip() if title.strip() else None


def _parse_filename_metadata(filename):
    """Parse metadata from comic filename using common patterns"""
    import re

    metadata = {}

    # Detect issue type first (this affects how we parse other elements)
    issue_type = _detect_issue_type(filename)
    metadata['issue_type'] = issue_type

    # Extract issue number (adjusted based on issue type)
    if issue_type == 'annual':
        # Annual issues have their own numbering
        annual_patterns = [
            r'Annual\s*#?(\d+)',     # Annual #1, Annual 1
            r'#(\d+)\s*Annual',      # #1 Annual
        ]
        for pattern in annual_patterns:
            match = re.search(pattern, filename, re.IGNORECASE)
            if match:
                metadata['annual_number'] = int(match.group(1))
                break
    elif issue_type == 'main_series':
        # Regular issue number for main series
        issue_patterns = [
            r'#(\d+(?:\.\d+)?)',      # #001, #1, #1.5 (for decimal issues)
            r'Issue\s*(\d+(?:\.\d+)?)',  # Issue 001, Issue 1.5
            r'(\d+(?:\.\d+)?)$',      # Issue at end
        ]

        for pattern in issue_patterns:
            match = re.search(pattern, filename, re.IGNORECASE)
            if match:
                try:
                    issue_num = float(match.group(1))
                    metadata['issue'] = issue_num
                except ValueError:
                    metadata['issue'] = match.group(1)
                break

    # Extract year
    year_match = re.search(r'\((\d{4})\)', filename)
    if year_match:
        metadata['year'] = int(year_match.group(1))

    # Extract volume
    vol_patterns = [
        r'Vol\.?\s*(\d+)',      # Vol.1, Vol 2
        r'v(\d+)',              # v1, v2
        r'Volume\s*(\d+)',      # Volume 1
    ]

    for pattern in vol_patterns:
        match = re.search(pattern, filename, re.IGNORECASE)
        if match:
            metadata['volume'] = int(match.group(1))
            break

    # Extract special identifiers
    metadata.update(_extract_special_identifiers(filename))

    return metadata


def _detect_issue_type(filename):
    """Detect the type of comic issue from filename patterns"""
    import re

    filename_lower = filename.lower()

    # Patterns for different issue types
    if re.search(r'\btpb\b|\btrade\b.*\bpaperback\b|\bgraphic\b.*\bnovel\b|\bhc\b|\bhardcover\b', filename_lower):
        return 'collection'
    elif re.search(r'\bannual\b', filename_lower):
        return 'annual'
    elif re.search(r'\bspecial\b', filename_lower):
        return 'special'
    elif re.search(r'\bone[\-\s]?shot\b', filename_lower):
        return 'one_shot'
    elif re.search(r'\bholiday\b|\bchristmas\b|\bhalloween\b', filename_lower):
        return 'holiday_special'
    elif re.search(r'\bgiant\b|\bmega\b|\bsuper\b.*\bsize\b', filename_lower):
        return 'giant_size'
    elif re.search(r'\bpreview\b|\bpromo\b', filename_lower):
        return 'preview'
    elif re.search(r'\bwhatif\b|\bwhat\s+if\b|\belseworlds\b|\bimaginary\b', filename_lower):
        return 'alternate_reality'
    elif re.search(r'\bcrossover\b|\bevent\b', filename_lower):
        return 'crossover'
    elif re.search(r'\bmini[\-\s]?series\b|\blimited\b.*\bseries\b', filename_lower):
        return 'mini_series'
    elif re.search(r'#\d+(?:\.\d+)?(?:\s|$)', filename):  # Has regular issue number with #
        return 'main_series'
    elif re.search(r'\bissue\s+\d+(?:\.\d+)?(?:\s|$)', filename_lower):  # Has "Issue 15" format
        return 'main_series'
    elif re.search(r'\b\d+(?:\.\d+)?(?:\s*\.|$)', filename):  # Has number at end or before extension
        return 'main_series'
    else:
        return 'unknown'


def _extract_special_identifiers(filename):
    """Extract special identifiers and metadata from filename"""
    import re

    metadata = {}
    filename_lower = filename.lower()

    # Detect if it's a variant cover
    if re.search(r'\bvariant\b|\balt\b.*\bcover\b|\bcover\b.*\b[abc]\b|\bincentive\b.*\bcover\b|\bsketch\b.*\bcover\b', filename_lower):
        metadata['is_variant'] = True

        # Try to extract variant type
        variant_match = re.search(r'(incentive|virgin|sketch|foil|holofoil|chromium)', filename_lower)
        if variant_match:
            metadata['variant_type'] = variant_match.group(1)

    # Detect reprint information
    if re.search(r'\breprint\b|\bsecond\b.*\bprinting\b|\b2nd\b.*\bprint\b', filename_lower):
        metadata['is_reprint'] = True

    # Detect digital vs print
    if re.search(r'\bdigital\b|\bweb\b|\bonline\b', filename_lower):
        metadata['format_type'] = 'digital'

    # Extract story arc or event name
    arc_patterns = [
        r':\s*([^#\(\)]+?)(?:\s*#|\s*\(|$)',  # After colon, before # or (
        r'-\s*([^#\(\)]+?)(?:\s*#|\s*\(|$)',  # After dash, before # or (
    ]

    for pattern in arc_patterns:
        match = re.search(pattern, filename)
        if match:
            potential_arc = match.group(1).strip()
            # Filter out common non-arc words
            if len(potential_arc) > 3 and not re.search(r'^(vol|volume|issue|part|pt)\b', potential_arc.lower()):
                metadata['story_arc'] = potential_arc
                break

    return metadata


def _extract_comic_info_xml(archive_file):
    """Extract metadata from ComicInfo.xml file if present in archive"""
    try:
        # Look for ComicInfo.xml in the archive
        comic_info_file = None

        if hasattr(archive_file, 'namelist'):  # ZIP file
            files = archive_file.namelist()
        else:  # RAR file
            files = archive_file.namelist()

        for file in files:
            if file.lower() == 'comicinfo.xml':
                comic_info_file = file
                break

        if not comic_info_file:
            return None

        # Read and parse ComicInfo.xml
        if hasattr(archive_file, 'read'):  # ZIP file
            xml_data = archive_file.read(comic_info_file)
        else:  # RAR file
            xml_data = archive_file.read(comic_info_file)

        root = ET.fromstring(xml_data)

        metadata = {}

        # Extract common fields
        field_mapping = {
            'Title': 'title',
            'Series': 'series',
            'Number': 'issue',
            'Volume': 'volume',
            'Year': 'year',
            'Month': 'month',
            'Publisher': 'publisher',
            'Writer': 'writer',
            'Penciller': 'penciller',
            'Inker': 'inker',
            'Colorist': 'colorist',
            'Letterer': 'letterer',
            'Summary': 'summary',
            'Genre': 'genre',
            'LanguageISO': 'language',
            'PageCount': 'page_count',
        }

        for xml_tag, meta_key in field_mapping.items():
            element = root.find(xml_tag)
            if element is not None and element.text:
                value = element.text.strip()
                if value:
                    # Convert numeric fields
                    if meta_key in ['issue', 'volume', 'year', 'month', 'page_count']:
                        try:
                            metadata[meta_key] = int(value)
                        except ValueError:
                            metadata[meta_key] = value
                    else:
                        metadata[meta_key] = value

        return metadata if metadata else None

    except Exception as e:
        logger.warning(f"Failed to parse ComicInfo.xml: {e}")
        return None


def _extract_first_image_as_cover(archive_file, book, format_type):
    """Extract the first image from archive as cover"""
    try:
        # Get list of files in archive
        if hasattr(archive_file, 'namelist'):  # ZIP file
            files = archive_file.namelist()
        else:  # RAR file
            files = archive_file.namelist()

        # Find first image file
        image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}
        image_files = []

        for file in files:
            if any(file.lower().endswith(ext) for ext in image_extensions):
                image_files.append(file)

        if not image_files:
            return None

        # Sort to get the first image (typically the cover)
        image_files.sort()
        first_image = image_files[0]

        # Create cover cache directory if it doesn't exist
        cover_cache_dir = os.path.join(settings.MEDIA_ROOT, 'cover_cache')
        os.makedirs(cover_cache_dir, exist_ok=True)

        # Generate unique filename for cover
        import hashlib
        import time
        hash_source = f"{book.file_path}_{first_image}_{time.time()}"
        file_hash = hashlib.md5(hash_source.encode()).hexdigest()[:8]
        cover_filename = f"book_{book.id}_cover_{file_hash}.jpg"
        cover_path = os.path.join(cover_cache_dir, cover_filename)

        # Extract image data
        if hasattr(archive_file, 'read'):  # ZIP file
            image_data = archive_file.read(first_image)
        else:  # RAR file
            image_data = archive_file.read(first_image)

        # Save image using PIL to ensure it's in a standard format
        # Use Windows-compatible temporary file handling
        temp_path = None
        try:
            # Create temp file in cover cache directory to avoid permission issues
            temp_fd, temp_path = tempfile.mkstemp(
                suffix='.tmp',
                dir=cover_cache_dir,
                prefix='cover_temp_'
            )

            # Write image data to temp file
            with os.fdopen(temp_fd, 'wb') as f:
                f.write(image_data)

            # Process with PIL
            with Image.open(temp_path) as img:
                # Convert to RGB if necessary (for JPEG)
                if img.mode in ('RGBA', 'LA', 'P'):
                    img = img.convert('RGB')

                # Save as JPEG
                img.save(cover_path, 'JPEG', quality=85)

                # Get image dimensions
                width, height = img.size

        finally:
            # Clean up temporary file
            if temp_path and os.path.exists(temp_path):
                try:
                    os.unlink(temp_path)
                except PermissionError:
                    # On Windows, sometimes files are locked briefly
                    import time
                    time.sleep(0.1)
                    try:
                        os.unlink(temp_path)
                    except Exception:
                        logger.warning(f"Could not remove temporary file: {temp_path}")

        # Save cover to database
        source = DataSource.objects.get(name=DataSource.CONTENT_SCAN)
        BookCover.objects.get_or_create(
            book=book,
            cover_path=cover_path,
            source=source,
            defaults={
                'confidence': source.trust_level,
                'width': width,
                'height': height,
                'format': 'jpg',
                'file_size': os.path.getsize(cover_path)
            }
        )

        logger.info(f"Extracted cover from {format_type.upper()}: {first_image}")
        return cover_path

    except Exception as e:
        logger.warning(f"Failed to extract cover from {format_type.upper()}: {e}")
        return None


def _save_comic_metadata(book, extracted_data, filename_metadata, source):
    """Save extracted comic metadata to database"""
    try:
        # Save title
        title = extracted_data.get('title')
        if title:
            BookTitle.objects.get_or_create(
                book=book,
                source=source,
                defaults={'title': title, 'confidence': source.trust_level}
            )

        # Save series information if available
        series_name = extracted_data.get('series')
        series_number = extracted_data.get('series_number')
        if series_name:
            from books.models import Series, BookSeries
            series_obj, _ = Series.objects.get_or_create(name=series_name)
            BookSeries.objects.get_or_create(
                book=book,
                series=series_obj,
                source=source,
                defaults={
                    'series_number': str(series_number) if series_number else '',
                    'confidence': source.trust_level
                }
            )

        # Save authors from filename parsing
        authors_list = extracted_data.get('authors', [])
        if authors_list:
            from books.utils.author import attach_authors
            attach_authors(book, authors_list, source, confidence=source.trust_level)

        # Save publisher if available
        publisher_name = extracted_data.get('publisher')
        if publisher_name:
            publisher_obj, _ = Publisher.objects.get_or_create(name=publisher_name)
            BookPublisher.objects.get_or_create(
                book=book,
                publisher=publisher_obj,
                source=source,
                defaults={'confidence': source.trust_level}
            )

        # Save authors if available (writers, pencillers, etc. from ComicInfo.xml)
        author_fields = ['writer', 'penciller', 'inker', 'colorist', 'letterer']
        comic_info_authors = []

        for field in author_fields:
            if field in extracted_data:
                # Split multiple authors by comma or semicolon
                import re
                authors = re.split(r'[,;]', extracted_data[field])
                comic_info_authors.extend([author.strip() for author in authors if author.strip()])

        # Add comic info authors to the main authors list if we don't have any from filename
        if comic_info_authors and not authors_list:
            from books.utils.author import attach_authors
            attach_authors(book, comic_info_authors, source, confidence=source.trust_level)

        # Add language from scan folder for comics
        if hasattr(book, 'scan_folder') and book.scan_folder and book.scan_folder.language:
            BookMetadata.objects.get_or_create(
                book=book,
                field_name='language',
                source=source,
                defaults={
                    'field_value': book.scan_folder.language,
                    'confidence': 0.9  # High confidence since it's user-configured
                }
            )

        # Save additional metadata
        metadata_fields = {
            'series': 'series',
            'issue': 'issue_number',
            'volume': 'volume_number',
            'year': 'publication_year',
            'summary': 'description',
            'genre': 'genre',
            'language': 'language',
            'page_count': 'page_count'
        }

        for data_key, meta_key in metadata_fields.items():
            value = extracted_data.get(data_key) or filename_metadata.get(data_key)
            if value:
                BookMetadata.objects.get_or_create(
                    book=book,
                    field_name=meta_key,
                    source=source,
                    defaults={'field_value': str(value), 'confidence': source.trust_level}
                )

    except Exception as e:
        logger.warning(f"Failed to save comic metadata: {e}")


def analyze_comic_series(series_name, publisher=None):
    """Analyze completeness of a comic series"""
    from django.db.models import Q

    try:
        # Find all books in the series
        series_filter = Q(metadata__field_name='series', metadata__field_value__iexact=series_name)
        if publisher:
            series_filter &= Q(finalmetadata__final_publisher__iexact=publisher)

        series_books = Book.objects.filter(series_filter).distinct()

        if not series_books.exists():
            return None

        analysis = {
            'series_name': series_name,
            'publisher': publisher,
            'total_books': series_books.count(),
            'main_series_issues': [],
            'annuals': [],
            'specials': [],
            'collections': [],
            'one_shots': [],
            'other': [],
            'completeness_analysis': {}
        }

        # Categorize issues by type
        for book in series_books:
            issue_info = _get_comic_issue_info(book)

            if issue_info['issue_type'] == 'main_series':
                analysis['main_series_issues'].append(issue_info)
            elif issue_info['issue_type'] == 'annual':
                analysis['annuals'].append(issue_info)
            elif issue_info['issue_type'] in ['special', 'holiday_special', 'giant_size']:
                analysis['specials'].append(issue_info)
            elif issue_info['issue_type'] == 'collection':
                analysis['collections'].append(issue_info)
            elif issue_info['issue_type'] == 'one_shot':
                analysis['one_shots'].append(issue_info)
            else:
                analysis['other'].append(issue_info)

        # Analyze main series completeness
        if analysis['main_series_issues']:
            analysis['completeness_analysis'] = _analyze_main_series_completeness(
                analysis['main_series_issues']
            )

        return analysis

    except Exception as e:
        logger.error(f"Error analyzing comic series {series_name}: {e}")
        return None


def _get_comic_issue_info(book):
    """Extract issue information from a comic book"""
    info = {
        'book_id': book.id,
        'file_path': book.file_path,
        'issue_type': 'unknown',
        'issue_number': None,
        'annual_number': None,
        'volume': None,
        'year': None,
        'is_variant': False,
        'story_arc': None,
        'title': book.finalmetadata.final_title if hasattr(book, 'finalmetadata') else '',
    }

    # Get metadata from database
    metadata_fields = {
        'issue_type': book.metadata.filter(field_name='issue_type').first(),
        'issue_number': book.metadata.filter(field_name='issue_number').first(),
        'annual_number': book.metadata.filter(field_name='annual_number').first(),
        'volume_number': book.metadata.filter(field_name='volume_number').first(),
        'publication_year': book.metadata.filter(field_name='publication_year').first(),
        'is_variant': book.metadata.filter(field_name='is_variant').first(),
        'story_arc': book.metadata.filter(field_name='story_arc').first(),
    }

    # Extract values
    for field, metadata in metadata_fields.items():
        if metadata:
            value = metadata.field_value
            if field in ['issue_number', 'annual_number', 'volume_number', 'publication_year']:
                try:
                    info[field] = float(value) if '.' in value else int(value)
                except (ValueError, TypeError):
                    info[field] = value
            elif field == 'is_variant':
                info[field] = value.lower() in ['true', '1', 'yes']
            else:
                info[field] = value

    return info


def _analyze_main_series_completeness(main_series_issues):
    """Analyze completeness of main series issues"""
    if not main_series_issues:
        return {'is_complete': False, 'missing_issues': [], 'gap_analysis': []}

    # Sort by issue number
    sorted_issues = sorted(
        [issue for issue in main_series_issues if issue['issue_number'] is not None],
        key=lambda x: float(x['issue_number'])
    )

    if not sorted_issues:
        return {'is_complete': False, 'missing_issues': [], 'gap_analysis': []}

    # Analyze gaps
    issue_numbers = [float(issue['issue_number']) for issue in sorted_issues]
    min_issue = min(issue_numbers)
    max_issue = max(issue_numbers)

    missing_issues = []
    gap_analysis = []

    # Check for gaps in sequence (assuming integer issue numbers mostly)
    if min_issue == int(min_issue) and max_issue == int(max_issue):
        expected_range = range(int(min_issue), int(max_issue) + 1)
        present_issues = set(int(num) for num in issue_numbers if num == int(num))
        missing_issues = [num for num in expected_range if num not in present_issues]

        # Group consecutive missing issues into ranges
        if missing_issues:
            gap_start = missing_issues[0]
            gap_end = missing_issues[0]

            for i in range(1, len(missing_issues)):
                if missing_issues[i] == missing_issues[i-1] + 1:
                    gap_end = missing_issues[i]
                else:
                    # End of current gap
                    if gap_start == gap_end:
                        gap_analysis.append(f"#{gap_start}")
                    else:
                        gap_analysis.append(f"#{gap_start}-#{gap_end}")
                    gap_start = gap_end = missing_issues[i]

            # Add final gap
            if gap_start == gap_end:
                gap_analysis.append(f"#{gap_start}")
            else:
                gap_analysis.append(f"#{gap_start}-#{gap_end}")

    completeness_percentage = len(sorted_issues) / (max_issue - min_issue + 1) * 100 if max_issue > min_issue else 100

    return {
        'is_complete': len(missing_issues) == 0,
        'total_issues': len(sorted_issues),
        'issue_range': f"#{int(min_issue)}-#{int(max_issue)}",
        'missing_issues': missing_issues,
        'gap_analysis': gap_analysis,
        'completeness_percentage': round(completeness_percentage, 1)
    }


def get_comic_series_list():
    """Get a list of all comic series with their basic info"""
    from django.db.models import Count
    from books.models import BookMetadata

    # Get all series from comics
    comic_series = BookMetadata.objects.filter(
        field_name='series',
        book__file_path__iregex=r'\.(cbr|cbz)$'
    ).values(
        'field_value'
    ).annotate(
        book_count=Count('book', distinct=True)
    ).order_by('field_value')

    series_list = []
    for series_data in comic_series:
        series_name = series_data['field_value']

        # Get publisher if available
        publisher = BookMetadata.objects.filter(
            field_name='publisher',
            book__metadata__field_name='series',
            book__metadata__field_value=series_name
        ).first()

        publisher_name = publisher.field_value if publisher else None

        series_list.append({
            'name': series_name,
            'publisher': publisher_name,
            'book_count': series_data['book_count']
        })

    return series_list


def _enrich_with_comicvine(book, extracted_data):
    """Enrich comic metadata using Comic Vine API"""
    try:
        from django.conf import settings

        # Check if Comic Vine API key is configured
        if not hasattr(settings, 'COMICVINE_API_KEY') or not settings.COMICVINE_API_KEY:
            logger.debug("Comic Vine API key not configured, skipping Comic Vine enrichment")
            return

        # Import Comic Vine API wrapper
        from books.scanner.extractors.comicvine import ComicVineAPI

        api = ComicVineAPI()

        # Build search query from extracted data
        series_name = extracted_data.get('series')
        issue_number = extracted_data.get('series_number') or extracted_data.get('issue')
        title = extracted_data.get('title')

        # Prefer series + issue number for search
        if series_name and issue_number:
            search_query = f"{series_name} #{issue_number}"
        elif series_name:
            search_query = series_name
        elif title:
            search_query = title
        else:
            logger.debug(f"No suitable search terms for Comic Vine API for book {book.id}")
            return

        logger.info(f"Searching Comic Vine for: {search_query}")

        # Search for the issue
        issue_result = api.search_issue(search_query)

        if issue_result:
            logger.info(f"Found Comic Vine match for {search_query}: {issue_result.get('name', 'Unknown')}")
            # Save Comic Vine metadata to database
            api.save_comic_metadata(book, issue_result)
        else:
            logger.debug(f"No Comic Vine results found for {search_query}")

    except ImportError:
        logger.warning("Comic Vine API wrapper not available, skipping Comic Vine enrichment")
    except Exception as e:
        logger.warning(f"Error enriching comic metadata with Comic Vine: {e}")
