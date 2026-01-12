"""Comic Vine API integration for comic book metadata extraction.

This module provides integration with the Comic Vine API for retrieving
comprehensive comic book metadata including:
- Series/Volume information
- Issue details
- Creator information
- Publisher data
- Cover images
"""

import logging
import time
from typing import Dict, List, Optional

import requests
from django.conf import settings

from books.models import (
    Author,
    Book,
    BookAuthor,
    BookCover,
    BookMetadata,
    BookPublisher,
    BookTitle,
    DataSource,
    Publisher,
)
from books.scanner.rate_limiting import get_api_client

logger = logging.getLogger("books.scanner")


class ComicVineAPI:
    """Comic Vine API client with centralized rate limiting."""

    BASE_URL = "https://comicvine.gamespot.com/api"

    def __init__(self):
        self.api_key = getattr(settings, "COMICVINE_API_KEY", None)
        self.client = get_api_client("comic_vine")

    def _make_request(self, endpoint: str, params: Dict) -> Optional[Dict]:
        """Make a request to the Comic Vine API using centralized rate limiting."""
        if not self.api_key:
            logger.warning("[COMICVINE] API key not configured")
            return None

        if not self.client:
            logger.error("[COMICVINE] Rate limiting client not available")
            return None

        params.update({"api_key": self.api_key, "format": "json"})

        url = f"{self.BASE_URL}/{endpoint}/"
        cache_key = f"comicvine_{endpoint}_{hash(str(sorted(params.items())))}"

        try:
            logger.debug(f"[COMICVINE REQUEST] {endpoint} with params: {params}")

            data = self.client.make_request(
                url,
                params=params,
                cache_key=cache_key,
                cache_timeout=3600,  # 1 hour cache for Comic Vine data
            )

            if not data:
                return None

            if data.get("status_code") != 1:
                logger.warning(f"[COMICVINE ERROR] {data.get('error', 'Unknown error')}")
                return None

            return data

        except Exception as e:
            logger.error(f"[COMICVINE ERROR] {e}")
            return None

    def search_volumes(self, series_name: str, limit: int = 5) -> List[Dict]:
        """Search for comic volumes by series name."""
        params = {
            "query": series_name,
            "resources": "volume",
            "limit": limit,
            "field_list": "id,name,publisher,start_year,count_of_issues,deck,image",
        }

        result = self._make_request("search", params)
        if result and result.get("results"):
            return result["results"]
        return []

    def search_issues(self, volume_id: int, issue_number: Optional[int] = None, limit: int = 10) -> List[Dict]:
        """Search for issues within a specific volume."""
        params = {
            "filter": f"volume:{volume_id}",
            "limit": limit,
            "field_list": "id,name,issue_number,cover_date,store_date,deck,description,image,person_credits",
        }

        if issue_number:
            params["filter"] += f",issue_number:{issue_number}"

        result = self._make_request("issues", params)
        if result and result.get("results"):
            return result["results"]
        return []

    def get_volume_details(self, volume_id: int) -> Optional[Dict]:
        """Get detailed information about a specific volume."""
        params = {"field_list": "id,name,publisher,start_year,count_of_issues,deck,description,person_credits,character_credits"}

        result = self._make_request(f"volume/4050-{volume_id}", params)
        if result and result.get("results"):
            return result["results"]
        return None

    def get_issue_details(self, issue_id: int) -> Optional[Dict]:
        """Get detailed information about a specific issue."""
        params = {"field_list": "id,name,issue_number,cover_date,store_date,deck,description,image,person_credits,volume"}

        result = self._make_request(f"issue/4000-{issue_id}", params)
        if result and result.get("results"):
            return result["results"]
        return None

    def search_issue(self, query: str, limit: int = 5) -> Optional[Dict]:
        """Search for issues by query string."""
        params = {
            "query": query,
            "resources": "issue",
            "limit": limit,
            "field_list": "id,name,issue_number,cover_date,store_date,deck,description,image,person_credits,volume",
        }

        result = self._make_request("search", params)
        if result and result.get("results"):
            # Return the first (best match) issue
            return result["results"][0] if result["results"] else None
        return None

    def save_comic_metadata(self, book: Book, issue_data: Dict):
        """Save Comic Vine issue metadata to the database."""
        try:
            source = DataSource.objects.get(name=DataSource.COMICVINE)
            _save_issue_metadata(book, issue_data, source)
        except Exception as e:
            logger.error(f"[COMICVINE] Error saving comic metadata: {e}")


def query_comicvine_metadata(book: Book, series_name: str, issue_number: Optional[int] = None) -> bool:
    """Query Comic Vine API for comic book metadata."""
    logger.info(f"[COMICVINE QUERY] Searching for series: {series_name}, issue: {issue_number}")

    try:
        api = ComicVineAPI()
        source = DataSource.objects.get(name=DataSource.COMICVINE)

        # Search for volumes/series
        volumes = api.search_volumes(series_name)
        if not volumes:
            logger.info(f"[COMICVINE] No volumes found for: {series_name}")
            return False

        # Use the first (best match) volume
        volume = volumes[0]
        volume_id = volume["id"]

        logger.info(f"[COMICVINE] Found volume: {volume['name']} (ID: {volume_id})")

        # Save series/volume information
        _save_volume_metadata(book, volume, source)

        # Search for specific issue if we have an issue number
        if issue_number:
            issues = api.search_issues(volume_id, issue_number, limit=1)
            if issues:
                issue = issues[0]
                logger.info(f"[COMICVINE] Found issue: {issue.get('name', 'Untitled')} #{issue.get('issue_number')}")
                _save_issue_metadata(book, issue, source)
                return True
            else:
                logger.info(f"[COMICVINE] No specific issue #{issue_number} found in volume {volume_id}")

        # If no specific issue found, use volume-level metadata
        return True

    except Exception as e:
        logger.error(f"[COMICVINE] Error querying Comic Vine API: {e}")
        return False


def _save_volume_metadata(book: Book, volume: Dict, source: DataSource):
    """Save volume/series metadata to the database."""
    try:
        # Save series information
        volume_name = volume.get("name", "")
        if volume_name:
            from books.models import BookSeries, Series

            series_obj, _ = Series.objects.get_or_create(name=volume_name)
            BookSeries.objects.get_or_create(
                book=book,
                series=series_obj,
                source=source,
                defaults={"confidence": source.trust_level},
            )

        # Save publisher
        publisher_info = volume.get("publisher")
        if publisher_info and publisher_info.get("name"):
            publisher_obj, _ = Publisher.objects.get_or_create(name=publisher_info["name"])
            BookPublisher.objects.get_or_create(
                book=book,
                publisher=publisher_obj,
                source=source,
                defaults={"confidence": source.trust_level},
            )

        # Save description
        description = volume.get("deck") or volume.get("description")
        if description:
            BookMetadata.objects.get_or_create(
                book=book,
                field_name="description",
                source=source,
                defaults={"field_value": description, "confidence": source.trust_level},
            )

        # Save start year
        start_year = volume.get("start_year")
        if start_year:
            BookMetadata.objects.get_or_create(
                book=book,
                field_name="publication_year",
                source=source,
                defaults={
                    "field_value": str(start_year),
                    "confidence": source.trust_level,
                },
            )

        # Save cover image if available
        image_info = volume.get("image")
        if image_info and image_info.get("medium_url"):
            _save_cover_from_url(book, image_info["medium_url"], source)

    except Exception as e:
        logger.error(f"[COMICVINE] Error saving volume metadata: {e}")


def _save_issue_metadata(book: Book, issue: Dict, source: DataSource):
    """Save specific issue metadata to the database."""
    try:
        # Save issue title
        issue_name = issue.get("name")
        if issue_name:
            BookTitle.objects.get_or_create(
                book=book,
                source=source,
                defaults={"title": issue_name, "confidence": source.trust_level},
            )

        # Save issue description
        description = issue.get("deck") or issue.get("description")
        if description:
            BookMetadata.objects.get_or_create(
                book=book,
                field_name="description",
                source=source,
                defaults={"field_value": description, "confidence": source.trust_level},
            )

        # Save cover date
        cover_date = issue.get("cover_date")
        if cover_date:
            # Extract year from date (format: YYYY-MM-DD)
            try:
                year = cover_date.split("-")[0]
                # Validate that the year is actually a 4-digit number
                if len(year) == 4 and year.isdigit():
                    BookMetadata.objects.get_or_create(
                        book=book,
                        field_name="publication_year",
                        source=source,
                        defaults={
                            "field_value": year,
                            "confidence": source.trust_level,
                        },
                    )
            except (IndexError, ValueError):
                pass

        # Save creators from person_credits
        person_credits = issue.get("person_credits", [])
        _save_creators(book, person_credits, source)

        # Save cover image if available
        image_info = issue.get("image")
        if image_info and image_info.get("medium_url"):
            _save_cover_from_url(book, image_info["medium_url"], source)

    except Exception as e:
        logger.error(f"[COMICVINE] Error saving issue metadata: {e}")


def _save_creators(book: Book, person_credits: List[Dict], source: DataSource):
    """Save creator information from Comic Vine person credits."""
    try:
        for person in person_credits[:5]:  # Limit to 5 creators
            name = person.get("name")
            role = person.get("role", "").lower()

            if name:
                # Prioritize writers and artists
                is_main_author = role in ["writer", "story", "script"]

                author_obj, _ = Author.objects.get_or_create(name=name)
                BookAuthor.objects.get_or_create(
                    book=book,
                    author=author_obj,
                    source=source,
                    defaults={
                        "confidence": source.trust_level,
                        "is_main_author": is_main_author,
                    },
                )

    except Exception as e:
        logger.error(f"[COMICVINE] Error saving creators: {e}")


def _save_cover_from_url(book: Book, image_url: str, source: DataSource):
    """Download and save cover image from Comic Vine."""
    try:
        import hashlib
        import os
        import tempfile

        from PIL import Image

        # Create cover cache directory
        cover_cache_dir = os.path.join(settings.MEDIA_ROOT, "cover_cache")
        os.makedirs(cover_cache_dir, exist_ok=True)

        # Download image
        response = requests.get(image_url, timeout=30, stream=True)
        response.raise_for_status()

        # Generate unique filename
        hash_source = f"{book.file_path}_{image_url}_{time.time()}"
        file_hash = hashlib.md5(hash_source.encode()).hexdigest()[:8]
        cover_filename = f"book_{book.id}_comicvine_{file_hash}.jpg"
        cover_path = os.path.join(cover_cache_dir, cover_filename)

        # Save image
        with tempfile.NamedTemporaryFile() as temp_file:
            for chunk in response.iter_content(chunk_size=8192):
                temp_file.write(chunk)
            temp_file.flush()

            with Image.open(temp_file.name) as img:
                if img.mode in ("RGBA", "LA", "P"):
                    img = img.convert("RGB")
                img.save(cover_path, "JPEG", quality=85)
                width, height = img.size

        # Save to database
        BookCover.objects.get_or_create(
            book=book,
            cover_path=cover_path,
            source=source,
            defaults={
                "confidence": source.trust_level,
                "width": width,
                "height": height,
                "format": "jpg",
                "file_size": os.path.getsize(cover_path),
            },
        )

        logger.info(f"[COMICVINE] Downloaded cover from: {image_url}")

    except Exception as e:
        logger.error(f"[COMICVINE] Error downloading cover: {e}")
