"""Ebook content ISBN extraction utilities.

This module provides functions for scanning the actual content of ebooks
to find ISBN numbers embedded in the text, typically found on title pages,
copyright pages, or back cover sections.
"""

import logging
import re
from pathlib import Path

from books.models import BookMetadata, DataSource
from books.utils.isbn import is_valid_isbn10, is_valid_isbn13, normalize_isbn

logger = logging.getLogger("books.scanner")


def extract_isbn_from_content(book, page_limit=10):
    """
    Extract ISBN numbers from ebook content by scanning the first and last pages.

    Args:
        book: Book model instance
        page_limit: Number of pages to scan from beginning and end (default: 10)

    Returns:
        list: List of valid ISBN numbers found
    """
    try:
        primary_file = book.primary_file
        if primary_file is None or not primary_file.file_path:
            return []

        file_path = Path(primary_file.file_path)
        file_extension = file_path.suffix.lower()

        # Route to appropriate extractor based on file type
        if file_extension == ".epub":
            return _extract_from_epub(str(file_path), page_limit)
        elif file_extension == ".pdf":
            return _extract_from_pdf(str(file_path), page_limit)
        elif file_extension in [".mobi", ".azw", ".azw3"]:
            return _extract_from_mobi(str(file_path), page_limit)
        else:
            logger.warning(f"Unsupported file type for content ISBN extraction: {file_extension}")
            return []

    except Exception as e:
        logger.error(f"Content ISBN extraction failed for {book.file_path}: {e}")
        return []


def _extract_from_epub(file_path, page_limit):
    """Extract ISBNs from EPUB content."""
    try:
        from ebooklib import epub

        epub_book = epub.read_epub(file_path)
        isbn_candidates = []

        # Get all text items (chapters, pages)
        items = [item for item in epub_book.get_items() if item.get_type() == 9]  # ITEM_DOCUMENT

        # Scan first few items (usually contain title/copyright pages)
        for i, item in enumerate(items[:page_limit]):
            try:
                content = item.get_content().decode("utf-8", errors="ignore")
                text = _extract_text_from_html(content)
                isbn_candidates.extend(_find_isbn_patterns(text))
            except Exception as e:
                logger.debug(f"Failed to process EPUB item {i}: {e}")
                continue

        # Scan last few items (might contain back cover info)
        if len(items) > page_limit:
            for i, item in enumerate(items[-page_limit:]):
                try:
                    content = item.get_content().decode("utf-8", errors="ignore")
                    text = _extract_text_from_html(content)
                    isbn_candidates.extend(_find_isbn_patterns(text))
                except Exception as e:
                    logger.debug(f"Failed to process EPUB item {len(items)-page_limit+i}: {e}")
                    continue

        return _validate_and_dedupe_isbns(isbn_candidates)

    except ImportError:
        logger.warning("ebooklib not available for EPUB content scanning")
        return []
    except Exception as e:
        logger.error(f"EPUB content ISBN extraction failed: {e}")
        return []


def _extract_from_pdf(file_path, page_limit):
    """Extract ISBNs from PDF content, OCR-ing image-based pages when needed."""
    try:
        from PyPDF2 import PdfReader

        from books.scanner.extractors.pdf_ocr import ocr_pages

        reader = PdfReader(file_path)
        isbn_candidates = []
        total_pages = len(reader.pages)

        # Limit to at most 3 pages from start and end to avoid hanging on large/corrupt PDFs
        effective_limit = min(page_limit, 3)

        # Build the ordered, de-duplicated list of pages to sample.
        page_indexes = list(range(min(effective_limit, total_pages)))
        if total_pages > effective_limit:
            start_page = max(total_pages - effective_limit, effective_limit)
            page_indexes.extend(range(start_page, total_pages))
        page_indexes = list(dict.fromkeys(page_indexes))

        # First pass: extract embedded text from each sampled page.
        page_texts = {}
        ocr_needed = []
        for i in page_indexes:
            try:
                text = reader.pages[i].extract_text()
            except Exception as e:
                logger.debug(f"Failed to extract text from PDF page {i}: {e}")
                text = None

            if text and text.strip():
                page_texts[i] = text
            else:
                ocr_needed.append(i)

        # Second pass: OCR any pages that produced no embedded text (typical
        # of scanned/image-based PDFs where the text only exists as an image).
        if ocr_needed:
            for i, text in ocr_pages(file_path, ocr_needed).items():
                if text and text.strip():
                    page_texts[i] = text

        for text in page_texts.values():
            isbn_candidates.extend(_find_isbn_patterns(text))

        return _validate_and_dedupe_isbns(isbn_candidates)

    except ImportError:
        logger.warning("PyPDF2 not available for PDF content scanning")
        return []
    except Exception as e:
        logger.error(f"PDF content ISBN extraction failed: {e}")
        return []


def _extract_from_mobi(file_path, page_limit):
    """Extract ISBNs from MOBI content."""
    try:
        # Try to use mobidedrm or similar library if available
        # For now, return empty list as MOBI parsing is complex
        logger.info(f"MOBI content ISBN extraction not yet implemented for {file_path}")
        return []

    except Exception as e:
        logger.error(f"MOBI content ISBN extraction failed: {e}")
        return []


def _extract_text_from_html(html_content):
    """Extract plain text from HTML content."""
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html_content, "html.parser")

        # Remove script and style elements
        for script in soup(["script", "style"]):
            script.decompose()

        # Get text and clean it up
        text = soup.get_text()
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        return " ".join(chunk for chunk in chunks if chunk)

    except ImportError:
        # Fallback: simple HTML tag removal
        import re

        text = re.sub("<[^<]+?>", "", html_content)
        return text
    except Exception as e:
        logger.debug(f"HTML text extraction failed: {e}")
        return html_content


def _find_isbn_patterns(text):
    """
    Find potential ISBN patterns in text.

    Looks for:
    - "ISBN" followed by 10 or 13 digits
    - 13-digit numbers starting with 978 or 979
    - 10-digit numbers in common ISBN formats
    """
    isbn_candidates = []

    if not text:
        return isbn_candidates

    # Pattern 1: ISBN prefix followed by number (with or without hyphens)
    # Matches ISBN: 9780134685991 or ISBN-13: 978-0-13-468599-1
    isbn_pattern = r"(?i)ISBN(?:-?1[03])?[-:\s]*([0-9-\s]+[0-9Xx])"
    matches = re.finditer(isbn_pattern, text)
    for match in matches:
        # Remove hyphens and spaces for consistent format
        clean_isbn = re.sub(r"[-\s]", "", match.group(1))
        # Only keep if it's 10 or 13 digits (plus optional X)
        if re.match(r"^[0-9]{9}[0-9Xx]$|^[0-9]{13}$", clean_isbn):
            isbn_candidates.append(clean_isbn)

    # Pattern 2: 13-digit numbers starting with 978 or 979 (standard ISBN-13 prefixes)
    isbn13_pattern = r"\b(97[89][0-9]{10})\b"
    matches = re.finditer(isbn13_pattern, text)
    for match in matches:
        isbn_candidates.append(match.group(1))

    # Pattern 3: 10-digit ISBN patterns (more restrictive to avoid false positives)
    # Look for 10-digit numbers with specific formatting or context
    isbn10_context_pattern = r"(?i)(?:ISBN|International\s+Standard\s+Book\s+Number)[-:\s]*([0-9-\s]+[0-9Xx])"
    matches = re.finditer(isbn10_context_pattern, text)
    for match in matches:
        clean_isbn = re.sub(r"[-\s]", "", match.group(1))
        if re.match(r"^[0-9]{9}[0-9Xx]$|^[0-9]{13}$", clean_isbn):
            isbn_candidates.append(clean_isbn)

    # Pattern 4: Look for numbers near copyright or publication info
    copyright_context = r"(?i)(?:copyright|published|edition|print).*?([0-9]{10,13})"
    matches = re.finditer(copyright_context, text)
    for match in matches:
        candidate = match.group(1)
        # Only consider if it looks like an ISBN (10 or 13 digits)
        if len(candidate) in [10, 13]:
            isbn_candidates.append(candidate)

    return isbn_candidates


def _validate_and_dedupe_isbns(candidates):
    """
    Validate ISBN candidates and remove duplicates.

    Args:
        candidates: List of potential ISBN strings

    Returns:
        list: List of valid, normalized ISBN-13 numbers
    """
    valid_isbns = set()

    for candidate in candidates:
        if not candidate:
            continue

        # Clean the candidate
        cleaned = re.sub(r"[^0-9Xx]", "", candidate)

        if len(cleaned) == 10:
            if is_valid_isbn10(cleaned):
                # Convert to ISBN-13
                normalized = normalize_isbn(cleaned)
                if normalized:
                    valid_isbns.add(normalized)
        elif len(cleaned) == 13:
            if is_valid_isbn13(cleaned):
                valid_isbns.add(cleaned)

    return list(valid_isbns)


def save_content_isbns(book, page_limit=10):
    """
    Extract ISBNs from book content and save them as metadata.

    Args:
        book: Book model instance
        page_limit: Number of pages to scan from the beginning and end
    """
    try:
        # Get the data source for content-extracted ISBNs
        source, created = DataSource.objects.get_or_create(
            name=DataSource.CONTENT_SCAN,
            defaults={
                "trust_level": 0.85,  # Will be overridden by bootstrap if already exists
            },
        )

        # Extract ISBNs from content
        isbns = extract_isbn_from_content(book, page_limit=page_limit)

        if not isbns:
            logger.info(f"No ISBNs found in content for {book.file_path}")
            return

        # Save each unique ISBN as metadata
        saved_count = 0
        for isbn in isbns:
            try:
                metadata, created = BookMetadata.objects.get_or_create(
                    book=book,
                    field_name="isbn",
                    field_value=isbn,
                    source=source,
                    defaults={"confidence": source.trust_level},  # Use source's trust level
                )
                if created:
                    saved_count += 1
                    logger.info(f"Found ISBN in content: {isbn} for {book.file_path}")
            except Exception as e:
                logger.warning(f"Failed to save content ISBN {isbn}: {e}")

        if saved_count > 0:
            logger.info(f"Saved {saved_count} ISBNs from content scan for {book.file_path}")
        else:
            logger.info(f"All content ISBNs already existed for {book.file_path}")

    except Exception as e:
        logger.error(f"Failed to save content ISBNs for {book.file_path}: {e}")


def has_isbn_metadata(book):
    """Return True if the book already has any active ISBN metadata."""
    return BookMetadata.objects.filter(book=book, field_name="isbn", is_active=True).exists()


def ensure_content_isbn(book, page_limit=10):
    """Run content ISBN extraction only if the book has no ISBN metadata yet.

    Returns:
        bool: True if a content scan was performed, False if skipped.
    """
    if has_isbn_metadata(book):
        return False
    save_content_isbns(book, page_limit=page_limit)
    return True


def bulk_scan_content_isbns(books_queryset=None, page_limit=10):
    """
    Bulk scan multiple books for content ISBNs.

    Args:
        books_queryset: QuerySet of books to scan (default: all books)
        page_limit: Number of pages to scan per book

    Returns:
        dict: Statistics about the scanning process
    """
    from books.models import Book

    if books_queryset is None:
        books_queryset = Book.objects.all()

    stats = {
        "total_books": 0,
        "books_with_isbns": 0,
        "total_isbns_found": 0,
        "errors": 0,
    }

    for book in books_queryset:
        try:
            stats["total_books"] += 1

            # Check if we already have content-scanned ISBNs for this book
            existing_content_isbns = BookMetadata.objects.filter(book=book, field_name="isbn", source__name=DataSource.CONTENT_SCAN).count()

            if existing_content_isbns > 0:
                logger.debug(f"Skipping {book.file_path}, already has content-scanned ISBNs")
                continue

            # Extract and save ISBNs
            initial_count = BookMetadata.objects.filter(book=book, field_name="isbn", source__name=DataSource.CONTENT_SCAN).count()

            save_content_isbns(book)

            final_count = BookMetadata.objects.filter(book=book, field_name="isbn", source__name=DataSource.CONTENT_SCAN).count()

            new_isbns = final_count - initial_count
            if new_isbns > 0:
                stats["books_with_isbns"] += 1
                stats["total_isbns_found"] += new_isbns

        except Exception as e:
            stats["errors"] += 1
            logger.error(f"Error scanning {book.file_path}: {e}")

    return stats
