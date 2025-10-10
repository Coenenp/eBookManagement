"""External metadata service integration.

This module provides integration with external services like Google Books
and Open Library for retrieving book metadata, covers, and additional
information to enhance local book data.
"""
import logging
import re
import requests
import traceback
from PIL import Image
from io import BytesIO
from difflib import SequenceMatcher

from django.conf import settings
from django.core.cache import cache

from books.models import (
    BookTitle, BookAuthor, DataSource, Publisher, BookPublisher,
    Genre, BookGenre, BookMetadata, BookCover
)
from books.utils.isbn import normalize_isbn
from books.utils.language import normalize_language
from books.utils.author import attach_authors
from books.utils.cache_key import make_cache_key
from books.scanner.rate_limiting import get_api_client

logger = logging.getLogger("books.scanner")


def query_metadata_and_covers(book):
    """Combined function to fetch both metadata and covers in single API calls"""
    try:
        title = _get_best_title(book)
        author = _get_best_author(book)

        logger.info(f"Retrieving metadata and covers for {title or 'Unknown'} ({author or 'Unknown'})...")
        logger.info(f"[DEBUG] Title resolved: {title}, Author resolved: {author}")
        logger.info(f"[EXTERNAL PARSE] Book ID: {book.id}")

        if title or author:
            logger.info(f"[OPEN LIBRARY COMBINED] Title: {title}, Author: {author}")
            _query_open_library_combined(book, title, author, None)  # No ISBN available in this context

            logger.info(f"[GOOGLE BOOKS COMBINED] Title: {title}, Author: {author}")
            _query_google_books_combined(book, title, author, None)  # No ISBN available in this context

            logger.info(f"[GOODREADS COMBINED] Title: {title}, Author: {author}")
            _query_goodreads_combined(book, title, author)
        else:
            logger.warning(f"[QUERY SKIPPED] No usable title or author found for book ID {book.id}")
    except Exception as e:
        logger.error(f"[QUERY_METADATA_AND_COVERS EXCEPTION] {e}")
        traceback.print_exc()


def query_metadata_and_covers_with_terms(book, search_title=None, search_author=None, search_isbn=None):
    """Query external metadata using specific search terms instead of book's existing metadata"""
    metadata_list = []
    covers_list = []

    try:
        # Use provided search terms, fall back to existing metadata
        title = search_title or _get_best_title(book)
        author = search_author or _get_best_author(book)

        logger.info(f"Retrieving metadata and covers with custom terms for book {book.id}")
        logger.info(f"Search terms - Title: '{title}', Author: '{author}', ISBN: '{search_isbn}'")

        if title or author or search_isbn:
            # Count metadata and covers before queries
            initial_metadata_count = BookMetadata.objects.filter(book=book).count()
            initial_covers_count = BookCover.objects.filter(book=book).count()

            # Try ISBN search first if provided
            if search_isbn:
                logger.info(f"[ISBN SEARCH] Using ISBN for enhanced searches: {search_isbn}")

            logger.info(f"[OPEN LIBRARY COMBINED] Title: {title}, Author: {author}, ISBN: {search_isbn}")
            _query_open_library_combined(book, title, author, search_isbn)

            logger.info(f"[GOOGLE BOOKS COMBINED] Title: {title}, Author: {author}, ISBN: {search_isbn}")
            _query_google_books_combined(book, title, author, search_isbn)

            logger.info(f"[GOODREADS COMBINED] Title: {title}, Author: {author}")
            _query_goodreads_combined(book, title, author)

            # Collect new metadata and covers that were added
            final_metadata_count = BookMetadata.objects.filter(book=book).count()
            final_covers_count = BookCover.objects.filter(book=book).count()

            # Get the newly added metadata and covers
            if final_metadata_count > initial_metadata_count:
                new_metadata = BookMetadata.objects.filter(book=book)[initial_metadata_count:]
                metadata_list.extend(list(new_metadata))

            if final_covers_count > initial_covers_count:
                new_covers = BookCover.objects.filter(book=book)[initial_covers_count:]
                covers_list.extend(list(new_covers))
        else:
            logger.warning(f"[QUERY SKIPPED] No usable search terms provided for book ID {book.id}")

    except Exception as e:
        logger.error(f"[QUERY_METADATA_AND_COVERS_WITH_TERMS EXCEPTION] {e}")
        traceback.print_exc()

    return (metadata_list, covers_list)


def _get_best_title(book):
    best = BookTitle.objects.filter(book=book).order_by('-confidence').first()
    return best.title if best else None


def _get_best_author(book):
    best = BookAuthor.objects.filter(book=book).order_by('-confidence').first()
    return best.author.name if best else None


def _calculate_match_confidence(query_title, query_author, result_title, result_authors):
    """Calculate match confidence based on title and author similarity"""
    title_score = 0.0
    author_score = 0.0

    if query_title and result_title:
        title_score = SequenceMatcher(None, query_title.lower(), result_title.lower()).ratio()

    if query_author and result_authors:
        author_score = max(SequenceMatcher(None, query_author.lower(), a.lower()).ratio() for a in result_authors)

    # Weighted average: title 60%, author 40%
    if query_title and query_author:
        return (title_score * 0.6) + (author_score * 0.4)
    elif query_title:
        return title_score
    elif query_author:
        return author_score
    else:
        return 0.0


def _calculate_final_confidence(source, match_confidence):
    """Calculate final confidence by combining source trust level with match confidence"""
    return source.trust_level * match_confidence


def _safe_google_request(url, cache_key=None, retries=3):
    """Make a rate-limited request to Google Books API."""
    google_client = get_api_client('google_books')
    if not google_client:
        logger.error("Google Books API client not available")
        return None

    # Extract URL and params for the rate-limited client
    if '?' in url:
        base_url, query_string = url.split('?', 1)
        params = {}
        for param in query_string.split('&'):
            if '=' in param:
                key, value = param.split('=', 1)
                params[key] = value
    else:
        base_url = url
        params = {}

    return google_client.make_request(
        base_url,
        params=params,
        cache_key=cache_key,
        cache_timeout=10800  # 3 hours
    )


def _safe_apify_request(actor_name, input_payload, cache_key, token, timeout=3600):
    cached = cache.get(cache_key)
    if cached:
        return cached

    url = f"https://api.apify.com/v2/acts/{actor_name}/run-sync-get-dataset-items?token={token}"
    response = requests.post(url, json=input_payload, timeout=30)
    response.raise_for_status()
    data = response.json()
    cache.set(cache_key, data, timeout=timeout)
    return data


def get_image_metadata(url):
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        image = Image.open(BytesIO(response.content))
        width, height = image.size
        file_size = len(response.content)
        format = image.format.lower()
        return width, height, file_size, format
    except Exception as e:
        logger.warning(f"Metadata fetch failed for {url}: {str(e)}")
        return None, None, None, None


def _query_open_library_combined(book, title, author, isbn=None):
    """Combined Open Library query for both metadata and covers"""
    try:
        metadata_source, _ = DataSource.objects.get_or_create(
            name=DataSource.OPEN_LIBRARY,
            defaults={'trust_level': 0.8}
        )
        cover_source, _ = DataSource.objects.get_or_create(
            name=DataSource.OPEN_LIBRARY_COVERS,
            defaults={'trust_level': 0.7}
        )

        # Build query - prefer ISBN if available
        if isbn:
            qstring = f'isbn:{isbn}'
            cache_key = f"openlib_combined_isbn:{make_cache_key(isbn)}"
            logger.info(f"[OPEN LIBRARY ISBN SEARCH] Using ISBN: {isbn}")
        else:
            query = []
            if title:
                query.append(f'title:"{title}"')
            if author:
                query.append(f'author:"{author}"')
            if not query:
                return
            qstring = " AND ".join(query)
            cache_key = f"openlib_combined:{make_cache_key(title, author)}"
            logger.info(f"[OPEN LIBRARY TITLE/AUTHOR SEARCH] Title: {title}, Author: {author}")

        url = "https://openlibrary.org/search.json"
        params = {'q': qstring, 'limit': 5}

        # Use rate-limited client
        open_library_client = get_api_client('open_library')
        if not open_library_client:
            logger.error("Open Library API client not available")
            return

        data = open_library_client.make_request(
            url,
            params=params,
            cache_key=cache_key,
            cache_timeout=3600  # 1 hour
        )

        if not data:
            logger.info(f"[OPEN LIBRARY] No response for query: {qstring}")
            return

        docs = data.get("docs", [])
        if not docs:
            logger.info(f"[OPEN LIBRARY] No results found for query: {qstring}")
            return

        # Process metadata from best match
        best_match = docs[0]

        # For ISBN searches, we have high confidence since it's an exact match
        if isbn:
            match_confidence = 0.95  # High confidence for ISBN matches
        else:
            match_confidence = _calculate_match_confidence(
                title, author,
                best_match.get("title", ""),
                best_match.get("author_name", [])
            )

        if match_confidence > 0.5:
            metadata_confidence = _calculate_final_confidence(metadata_source, match_confidence)
            _process_open_library_metadata(book, metadata_source, best_match, metadata_confidence)

        # Process covers from all results
        for doc in docs:
            if doc.get("cover_i"):
                if isbn:
                    # High confidence for ISBN-based cover matches
                    doc_match_confidence = 0.9
                else:
                    doc_match_confidence = _calculate_match_confidence(
                        title, author,
                        doc.get("title", ""),
                        doc.get("author_name", [])
                    )

                if doc_match_confidence > 0.3:  # Lower threshold for covers
                    cover_confidence = _calculate_final_confidence(cover_source, doc_match_confidence)
                    _process_open_library_cover(book, cover_source, doc, cover_confidence)

    except Exception as e:
        logger.warning(f"Open Library combined query failed for {book.file_path}: {str(e)}")


def _query_google_books_combined(book, title, author, isbn=None):
    """Combined Google Books query for both metadata and covers"""
    try:
        if not settings.GOOGLE_BOOKS_API_KEY or not (title or author or isbn):
            return

        metadata_source, _ = DataSource.objects.get_or_create(
            name=DataSource.GOOGLE_BOOKS,
            defaults={'trust_level': 0.85}
        )
        cover_source, _ = DataSource.objects.get_or_create(
            name=DataSource.GOOGLE_BOOKS_COVERS,
            defaults={'trust_level': 0.8}
        )

        # Build query - prefer ISBN if available, otherwise use title/author
        if isbn:
            query = f'isbn:{isbn}'
            cache_key = f"gbooks_combined_isbn:{make_cache_key(isbn)}"
            logger.info(f"[GOOGLE BOOKS ISBN SEARCH] Using ISBN: {isbn}")
        else:
            query = '+'.join(
                f'{param}:"{value}"' for param, value in [('intitle', title), ('inauthor', author)] if value
            )
            cache_key = f"gbooks_combined:{make_cache_key(title, author)}"
            logger.info(f"[GOOGLE BOOKS TITLE/AUTHOR SEARCH] Title: {title}, Author: {author}")

        url = "https://www.googleapis.com/books/v1/volumes"
        params = {
            'q': query,
            'maxResults': 5,
            'key': settings.GOOGLE_BOOKS_API_KEY
        }

        # Use rate-limited client
        google_client = get_api_client('google_books')
        if not google_client:
            logger.error("Google Books API client not available")
            return

        data = google_client.make_request(
            url,
            params=params,
            cache_key=cache_key,
            cache_timeout=10800  # 3 hours
        )

        if not data:
            logger.info(f"[GOOGLE BOOKS] No response for query: {query}")
            return

        items = data.get("items", [])

        if not items:
            logger.info(f"[GOOGLE BOOKS] No results found for query: {query}")
            return

        # Process metadata from best match
        best = items[0].get("volumeInfo", {})

        # For ISBN searches, we have high confidence since it's an exact match
        if isbn:
            match_confidence = 0.95  # High confidence for ISBN matches
        else:
            match_confidence = _calculate_match_confidence(
                title, author,
                best.get("title", ""),
                best.get("authors", [])
            )

        if match_confidence > 0.5:
            metadata_confidence = _calculate_final_confidence(metadata_source, match_confidence)
            _process_google_books_metadata(book, metadata_source, best, metadata_confidence)

        # Process covers from all results
        for item in items:
            info = item.get("volumeInfo", {})
            image_links = info.get("imageLinks", {})

            if image_links.get("thumbnail"):
                if isbn:
                    # High confidence for ISBN-based cover matches
                    item_match_confidence = 0.9
                else:
                    item_match_confidence = _calculate_match_confidence(
                        title, author,
                        info.get("title", ""),
                        info.get("authors", [])
                    )

                if item_match_confidence > 0.3:  # Lower threshold for covers
                    cover_confidence = _calculate_final_confidence(cover_source, item_match_confidence)
                    _process_google_books_cover(book, cover_source, info, cover_confidence)

    except Exception as e:
        logger.warning(f"Google Books combined query failed for {book.file_path}: {str(e)}")


def _query_goodreads_combined(book, title, author):
    """Combined Goodreads query for both metadata and covers"""
    try:
        token = settings.APIFY_API_TOKEN
        if not token or not (title or author):
            return

        metadata_source, _ = DataSource.objects.get_or_create(
            name=DataSource.GOODREADS,
            defaults={'trust_level': 0.75}
        )
        cover_source, _ = DataSource.objects.get_or_create(
            name=DataSource.GOODREADS_COVERS,
            defaults={'trust_level': 0.7}
        )

        search_query = f"{title} {author}".strip()
        cache_key = f"goodreads_combined:{make_cache_key(title, author)}"

        input_payload = {
            "search": search_query,
            "maxItems": 5,
            "endPage": 1,
            "includeReviews": False,
            "proxy": {"useApifyProxy": True}
        }

        data = _safe_apify_request("epctex/goodreads-scraper", input_payload, cache_key, token)

        if not data:
            return

        # Process metadata from best match
        best = data[0]
        match_confidence = _calculate_match_confidence(
            title, author,
            best.get("title", ""),
            [best.get("authorName", "")]
        )

        if match_confidence > 0.5:
            metadata_confidence = _calculate_final_confidence(metadata_source, match_confidence)
            _process_goodreads_metadata(book, metadata_source, best, metadata_confidence)

        # Process covers from all results
        for item in data:
            if item.get("image"):
                item_match_confidence = _calculate_match_confidence(
                    title, author,
                    item.get("title", ""),
                    [item.get("authorName", "")] if item.get("authorName") else []
                )

                if item_match_confidence > 0.3:  # Lower threshold for covers
                    cover_confidence = _calculate_final_confidence(cover_source, item_match_confidence)
                    _process_goodreads_cover(book, cover_source, item, cover_confidence)

    except Exception as e:
        logger.warning(f"Goodreads combined query failed for {book.file_path}: {str(e)}")


# Metadata processing functions
def _process_open_library_metadata(book, source, result, confidence):
    if result.get("title"):
        BookTitle.objects.get_or_create(
            book=book,
            title=result["title"],
            source=source,
            defaults={"confidence": confidence}
        )

    raw_names = result.get("author_name", [])[:3]
    attach_authors(book, raw_names, source, confidence=confidence)

    for subject in result.get("subjects", [])[:5]:
        genre_obj, _ = Genre.objects.get_or_create(name=subject.strip().title())
        BookGenre.create_or_update_best(
            book=book,
            genre=genre_obj,
            source=source,
            confidence=confidence,
            is_active=True
        )

    if result.get("language"):
        lang = normalize_language(result["language"][0] if isinstance(result["language"], list) else result["language"])
        if lang:  # Only save if we got a valid language code
            BookMetadata.objects.get_or_create(
                book=book,
                field_name="language",
                source=source,
                defaults={"field_value": lang, "confidence": confidence}
            )

    if result.get("first_publish_year"):
        year = result["first_publish_year"]
        try:
            year_int = int(str(year)[:4])  # Ensure 4-digit year
            BookMetadata.objects.get_or_create(
                book=book,
                field_name="publication_year",
                source=source,
                defaults={"field_value": str(year_int), "confidence": confidence}
            )
        except ValueError:
            logger.debug(f"No 4-digit year extracted from: {result['first_publish_year']}")
            pass  # Silently skip invalid year

    if result.get("publisher"):
        pub_name = result["publisher"][0].strip()
        if pub_name:
            existing_pub = Publisher.objects.filter(name__iexact=pub_name).first()
            pub_obj = existing_pub or Publisher.objects.create(name=pub_name)
            BookPublisher.objects.get_or_create(
                book=book,
                publisher=pub_obj,
                source=source,
                defaults={"confidence": confidence}
            )


def _process_google_books_metadata(book, source, result, confidence):
    if result.get("title"):
        BookTitle.objects.get_or_create(
            book=book,
            title=result["title"],
            source=source,
            defaults={"confidence": confidence}
        )

    raw_names = result.get("authors", [])[:3]
    attach_authors(book, raw_names, source, confidence=confidence)

    if result.get("language"):
        lang = normalize_language(result["language"])
        BookMetadata.objects.get_or_create(
            book=book,
            field_name="language",
            source=source,
            defaults={"field_value": lang, "confidence": confidence}
        )

    if result.get("publisher"):
        pub_name = result["publisher"].strip()
        if pub_name:
            existing_pub = Publisher.objects.filter(name__iexact=pub_name).first()
            pub_obj = existing_pub or Publisher.objects.create(name=pub_name)
            BookPublisher.objects.get_or_create(
                book=book,
                publisher=pub_obj,
                source=source,
                defaults={"confidence": confidence}
            )

    if result.get("publishedDate"):
        match = re.search(r'\d{4}', result["publishedDate"])
        if match:
            BookMetadata.objects.get_or_create(
                book=book,
                field_name="publication_year",
                source=source,
                defaults={"field_value": match.group(), "confidence": confidence}
            )
        else:
            logger.debug(f"No 4-digit year extracted from: {result['publishedDate']}")

    if result.get("description"):
        BookMetadata.objects.get_or_create(
            book=book,
            field_name="description",
            source=source,
            defaults={"field_value": result["description"][:1000], "confidence": confidence}
        )

    for category in result.get("categories", [])[:5]:
        genre_obj, _ = Genre.objects.get_or_create(name=category.strip().title())
        BookGenre.create_or_update_best(
            book=book,
            genre=genre_obj,
            source=source,
            confidence=confidence,
            is_active=True
        )

    for identifier in result.get("industryIdentifiers", []):
        if identifier.get("type") in ["ISBN_13", "ISBN_10"]:
            isbn = normalize_isbn(identifier["identifier"])
            if isbn:
                BookMetadata.objects.get_or_create(
                    book=book,
                    field_name="isbn",
                    source=source,
                    defaults={"field_value": isbn, "confidence": confidence}
                )
                break


def _process_goodreads_metadata(book, source, result, confidence):
    if result.get("title"):
        BookTitle.objects.get_or_create(
            book=book,
            title=result["title"].strip(),
            source=source,
            defaults={"confidence": confidence}
        )

    raw_names = [result.get("authorName")] if result.get("authorName") else []
    attach_authors(book, raw_names[:3], source, confidence=confidence)

    if result.get("genres"):
        for genre in result["genres"][:5]:
            genre_obj, _ = Genre.objects.get_or_create(name=genre.strip().title())
            BookGenre.create_or_update_best(
                book=book,
                genre=genre_obj,
                source=source,
                confidence=confidence,
                is_active=True
            )

    if result.get("language"):
        lang = normalize_language(result["language"])
        BookMetadata.objects.get_or_create(
            book=book,
            field_name="language",
            source=source,
            defaults={"field_value": lang, "confidence": confidence}
        )

    if result.get("publishedDate"):
        raw_year = result["publishedDate"]
        match = re.search(r'\d{4}', str(raw_year))
        if match:
            year_val = match.group()
            BookMetadata.objects.get_or_create(
                book=book,
                field_name="publication_year",
                source=source,
                defaults={"field_value": year_val, "confidence": confidence}
            )
        else:
            logger.debug(f"[YEAR] No valid 4-digit year in '{raw_year}'")

    if result.get("ISBN"):
        BookMetadata.objects.get_or_create(
            book=book,
            field_name="isbn",
            source=source,
            defaults={"field_value": result["ISBN"].strip(), "confidence": confidence}
        )

    if result.get("description"):
        BookMetadata.objects.get_or_create(
            book=book,
            field_name="description",
            source=source,
            defaults={"field_value": result["description"].strip(), "confidence": confidence}
        )

    if result.get("rating"):
        BookMetadata.objects.get_or_create(
            book=book,
            field_name="rating",
            source=source,
            defaults={"field_value": str(result["rating"]), "confidence": confidence}
        )

    # Publisher handling
    pub_name = None
    if result.get("publisher"):
        pub_name = result["publisher"].strip()
    elif result.get("publisherName"):
        pub_name = result["publisherName"].strip()

    if pub_name:
        existing_pub = Publisher.objects.filter(name__iexact=pub_name).first()
        pub_obj = existing_pub or Publisher.objects.create(name=pub_name)
        BookPublisher.objects.get_or_create(
            book=book,
            publisher=pub_obj,
            source=source,
            defaults={"confidence": confidence}
        )


# Cover processing functions
def _process_open_library_cover(book, source, doc, confidence):
    if doc.get("cover_i"):
        image_url = f"https://covers.openlibrary.org/b/id/{doc['cover_i']}-L.jpg"
        width, height, file_size, format = get_image_metadata(image_url)

        if format:  # Only proceed if we got valid image metadata
            try:
                BookCover.objects.get_or_create(
                    book=book,
                    cover_path=image_url,
                    source=source,
                    defaults={
                        "confidence": confidence,
                        "width": width,
                        "height": height,
                        "file_size": file_size,
                        "format": format,
                    }
                )
            except Exception as e:
                logger.warning(f"Failed to store Open Library cover: {image_url}, error: {str(e)}")


def _process_google_books_cover(book, source, info, confidence):
    image_links = info.get("imageLinks", {})
    if image_links.get("thumbnail"):
        image_url = image_links["thumbnail"].replace("http://", "https://")
        width, height, file_size, format = get_image_metadata(image_url)

        if format:  # Only proceed if we got valid image metadata
            try:
                BookCover.objects.get_or_create(
                    book=book,
                    cover_path=image_url,
                    source=source,
                    defaults={
                        "confidence": confidence,
                        "width": width,
                        "height": height,
                        "file_size": file_size,
                        "format": format,
                    }
                )
            except Exception as e:
                logger.warning(f"Failed to store Google Books cover: {image_url}, error: {str(e)}")


def _process_goodreads_cover(book, source, item, confidence):
    image_url = item.get("image")
    if image_url:
        width, height, file_size, format = get_image_metadata(image_url)

        if format:  # Only proceed if we got valid image metadata
            try:
                BookCover.objects.get_or_create(
                    book=book,
                    cover_path=image_url,
                    source=source,
                    defaults={
                        "confidence": confidence,
                        "width": width,
                        "height": height,
                        "file_size": file_size,
                        "format": format,
                    }
                )
            except Exception as e:
                logger.warning(f"Failed to store Goodreads cover: {image_url}, error: {str(e)}")


# Mock API client for testing
class GoodreadsAPI:
    """Mock Goodreads API client for testing."""

    def get_book_metadata(self, *args, **kwargs):
        """Mock metadata retrieval that can be mocked to raise exceptions."""
        # This will be mocked in tests to raise rate limit or other exceptions
        raise Exception("Rate limit exceeded")


# Create instance for tests to patch
goodreads_api = GoodreadsAPI()
