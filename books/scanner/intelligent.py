"""
Intelligent API Scanner with Graceful Degradation

This module provides enhanced scanning capabilities that can gracefully handle
API failures, track API access success per book, and automatically resume
scanning when APIs become available again.
"""

import logging
import uuid
from typing import Dict, List, Optional

from django.utils import timezone

from books.models import APIAccessLog, Book, BookAPICompleteness, DataSource, ScanSession
from books.scanner.rate_limiting import check_api_health, get_api_status

logger = logging.getLogger("books.scanner")


class IntelligentAPIScanner:
    """
    Enhanced scanner with intelligent API management that:
    1. Tracks API success per book
    2. Continues scanning when APIs fail
    3. Automatically resumes when APIs recover
    4. Optimizes scanning based on API availability
    """

    def __init__(self, session_id: str = None):
        self.session_id = session_id or str(uuid.uuid4())
        self.session = None
        self.available_apis = set()
        self.failed_apis = set()
        self.api_sources = {
            "Google Books": "Google Books",
            "Open Library": "Open Library",
            "Goodreads": "Goodreads",
        }

        # Initialize session tracking
        self._initialize_session()

    def _initialize_session(self):
        """Initialize or resume scanning session"""
        try:
            self.session, created = ScanSession.objects.get_or_create(
                session_id=self.session_id,
                defaults={
                    "external_apis_enabled": True,
                    "enabled_sources": list(self.api_sources.keys()),
                    "is_active": True,
                    "api_calls_made": {},
                    "api_failures": {},
                    "rate_limits_hit": {},
                },
            )

            if created:
                logger.info(f"[INTELLIGENT SCAN] Created new session: {self.session_id}")
            else:
                logger.info(f"[INTELLIGENT SCAN] Resumed session: {self.session_id}")

        except Exception as e:
            logger.error(f"[INTELLIGENT SCAN] Failed to initialize session: {e}")

    def check_api_availability(self) -> Dict[str, bool]:
        """Check which APIs are currently available"""
        api_health = check_api_health()
        api_status = get_api_status()

        availability = {}

        for api_name in self.api_sources.keys():
            api_key = api_name.lower().replace(" ", "_")

            # Check circuit breaker status
            is_healthy = api_health.get(api_key, False)

            # Check rate limits
            status = api_status.get(api_key, {})
            rate_limits = status.get("rate_limits", {})

            # Consider API available if healthy and not rate limited
            is_available = is_healthy

            if rate_limits:
                current_counts = rate_limits.get("current_counts", {})
                limits = rate_limits.get("limits", {})

                # Check if any limit is exceeded
                for period in ["daily", "hourly", "minute"]:
                    if period in current_counts and period in limits:
                        if current_counts[period] >= limits[period]:
                            is_available = False
                            break

            availability[api_name] = is_available

        # Update internal tracking
        self.available_apis = {name for name, available in availability.items() if available}
        self.failed_apis = {name for name, available in availability.items() if not available}

        logger.info(f"[API AVAILABILITY] Available: {self.available_apis}, Unavailable: {self.failed_apis}")

        return availability

    def scan_book_with_intelligence(self, book: Book, force_all_apis: bool = False) -> Dict[str, any]:
        """
        Scan a book with intelligent API management

        Args:
            book: Book instance to scan
            force_all_apis: Whether to attempt all APIs regardless of previous failures

        Returns:
            Dictionary with scan results and API status
        """
        results = {
            "book_id": book.id,
            "apis_attempted": [],
            "apis_succeeded": [],
            "apis_failed": [],
            "metadata_items_added": 0,
            "covers_added": 0,
            "needs_retry": [],
            "session_id": self.session_id,
        }

        try:
            # Get or create API completeness record
            completeness, _ = BookAPICompleteness.objects.get_or_create(
                book=book,
                defaults={
                    "missing_sources": list(self.api_sources.keys()),
                    "needs_external_scan": True,
                },
            )

            # Check current API availability
            api_availability = self.check_api_availability()

            # Determine which APIs to attempt
            apis_to_attempt = self._determine_apis_to_attempt(book, completeness, api_availability, force_all_apis)

            if not apis_to_attempt:
                logger.info(f"[INTELLIGENT SCAN] No APIs to attempt for book {book.id}")
                return results

            logger.info(f"[INTELLIGENT SCAN] Book {book.id}: Attempting APIs: {apis_to_attempt}")

            # Attempt each API
            for api_name in apis_to_attempt:
                result = self._attempt_api_for_book(book, api_name)
                results["apis_attempted"].append(api_name)

                if result["success"]:
                    results["apis_succeeded"].append(api_name)
                    results["metadata_items_added"] += result.get("metadata_items", 0)
                    results["covers_added"] += result.get("covers", 0)

                    # Mark source as complete
                    completeness.mark_source_complete(api_name)

                else:
                    results["apis_failed"].append(api_name)

                    # Check if we should retry later
                    if result.get("should_retry", False):
                        results["needs_retry"].append(api_name)
                        completeness.add_missing_source(api_name)

                        # Add to session resume queue
                        self.session.add_book_to_resume_queue(book.id, [api_name])

            # Update session statistics
            self.session.processed_books += 1
            if results["apis_succeeded"]:
                self.session.books_with_external_data += 1
            self.session.save(update_fields=["processed_books", "books_with_external_data"])

            logger.info(f"[INTELLIGENT SCAN] Book {book.id} completed: " f"APIs succeeded: {results['apis_succeeded']}, " f"APIs failed: {results['apis_failed']}")

        except Exception as e:
            logger.error(f"[INTELLIGENT SCAN] Error scanning book {book.id}: {e}")
            results["error"] = str(e)

        return results

    def _determine_apis_to_attempt(
        self,
        book: Book,
        completeness: BookAPICompleteness,
        api_availability: Dict[str, bool],
        force_all: bool,
    ) -> List[str]:
        """Determine which APIs should be attempted for this book"""
        apis_to_attempt = []

        for api_name in self.api_sources.keys():
            # Skip if API is not available and not forcing
            if not force_all and not api_availability.get(api_name, False):
                logger.debug(f"[API SELECTION] Skipping {api_name} - not available")
                continue

            # Check if we've already got data from this source recently
            source_complete_field = f"{api_name.lower().replace(' ', '_')}_complete"
            if hasattr(completeness, source_complete_field):
                if getattr(completeness, source_complete_field) and not force_all:
                    logger.debug(f"[API SELECTION] Skipping {api_name} - already complete")
                    continue

            # Check API access log for this book/source
            try:
                data_source = DataSource.objects.get(name=api_name)
                access_log, _ = APIAccessLog.objects.get_or_create(
                    book=book,
                    data_source=data_source,
                    defaults={"status": APIAccessLog.NOT_ATTEMPTED},
                )

                # Skip if API is unhealthy for this book and not forcing
                if not force_all and not access_log.is_healthy:
                    logger.debug(f"[API SELECTION] Skipping {api_name} - unhealthy for book")
                    continue

                # Skip if we can't retry yet (rate limited)
                if not access_log.can_retry_now:
                    logger.debug(f"[API SELECTION] Skipping {api_name} - can't retry yet")
                    continue

            except DataSource.DoesNotExist:
                logger.warning(f"[API SELECTION] Data source not found: {api_name}")
                continue

            apis_to_attempt.append(api_name)

        return apis_to_attempt

    def _attempt_api_for_book(self, book: Book, api_name: str) -> Dict[str, any]:
        """Attempt to get data from a specific API for a book"""
        result = {
            "api_name": api_name,
            "success": False,
            "metadata_items": 0,
            "covers": 0,
            "error": None,
            "should_retry": True,
        }

        try:
            # Get data source and access log
            data_source = DataSource.objects.get(name=api_name)
            access_log, _ = APIAccessLog.objects.get_or_create(
                book=book,
                data_source=data_source,
                defaults={"status": APIAccessLog.NOT_ATTEMPTED},
            )

            # Count existing metadata before API call
            existing_metadata_count = self._count_book_metadata(book, data_source)
            existing_covers_count = book.covers.filter(source=data_source).count()

            logger.info(f"[API ATTEMPT] {api_name} for book {book.id}")

            # Record session API call
            self.session.record_api_call(api_name)

            # Make the actual API call
            # Note: This calls your existing external metadata function
            # We'll need to modify it to be source-specific
            api_success = self._call_specific_api(book, api_name)

            # Count new metadata after API call
            new_metadata_count = self._count_book_metadata(book, data_source)
            new_covers_count = book.covers.filter(source=data_source).count()

            metadata_added = new_metadata_count - existing_metadata_count
            covers_added = new_covers_count - existing_covers_count

            if api_success:
                # Calculate average confidence of new metadata
                avg_confidence = self._calculate_average_confidence(book, data_source)

                # Record successful attempt
                access_log.record_attempt(
                    success=True,
                    items_found=metadata_added + covers_added,
                    confidence=avg_confidence,
                    metadata_retrieved=metadata_added > 0,
                    cover_retrieved=covers_added > 0,
                )

                result.update(
                    {
                        "success": True,
                        "metadata_items": metadata_added,
                        "covers": covers_added,
                        "should_retry": False,
                    }
                )

                logger.info(f"[API SUCCESS] {api_name} for book {book.id}: " f"{metadata_added} metadata, {covers_added} covers")

            else:
                # API call didn't return data (but didn't error)
                access_log.record_attempt(
                    success=False,
                    error_message="No data returned from API",
                    items_found=0,
                )

                result["error"] = "No data returned"
                result["should_retry"] = access_log.consecutive_failures < 3

        except Exception as e:
            error_msg = str(e)
            logger.error(f"[API FAILURE] {api_name} for book {book.id}: {error_msg}")

            # Record failed attempt
            try:
                access_log.record_attempt(success=False, error_message=error_msg)

                # Update session failure count
                self.session.record_api_call(
                    api_name,
                    success=False,
                    rate_limited="rate limit" in error_msg.lower(),
                )

            except Exception as log_error:
                logger.error(f"[LOG ERROR] Failed to record API attempt: {log_error}")

            result.update(
                {
                    "error": error_msg,
                    "should_retry": "rate limit" not in error_msg.lower(),  # Don't retry rate limits immediately
                }
            )

        return result

    def _call_specific_api(self, book: Book, api_name: str) -> bool:
        """Call a specific API for the book"""
        from books.scanner.external import (
            _get_best_author,
            _get_best_title,
            _query_goodreads_combined,
            _query_google_books_combined,
            _query_open_library_combined,
        )

        try:
            # Get the best title and author for the API call
            title = _get_best_title(book)
            author = _get_best_author(book)

            # Get ISBN if available
            isbn = None
            if hasattr(book, "finalmetadata") and book.finalmetadata:
                isbn = book.finalmetadata.isbn

            logger.info(f"[API CALL] {api_name} for book {book.id} - Title: {title}, Author: {author}, ISBN: {isbn}")

            # Call the appropriate API based on the name
            if api_name == DataSource.GOOGLE_BOOKS or api_name == "Google Books":
                _query_google_books_combined(book, title, author, isbn)
                return True
            elif api_name == DataSource.OPEN_LIBRARY or api_name == "Open Library":
                _query_open_library_combined(book, title, author, isbn)
                return True
            elif api_name == "Goodreads":
                _query_goodreads_combined(book, title, author)
                return True
            else:
                logger.warning(f"[API CALL] Unknown API name: {api_name}")
                return False

        except Exception as e:
            logger.error(f"[API CALL ERROR] {api_name} for book {book.id}: {e}")
            return False

    def _count_book_metadata(self, book: Book, source: DataSource) -> int:
        """Count metadata items from a specific source for a book"""
        return (
            book.title_relationships.filter(source=source, is_active=True).count()
            + book.author_relationships.filter(source=source, is_active=True).count()
            + book.genre_relationships.filter(source=source, is_active=True).count()
            + book.series_relationships.filter(source=source, is_active=True).count()
            + book.publisher_relationships.filter(source=source, is_active=True).count()
            + book.metadata.filter(source=source, is_active=True).count()
        )

    def _calculate_average_confidence(self, book: Book, source: DataSource) -> float:
        """Calculate average confidence of metadata from a source"""
        from django.db.models import Avg

        confidences = []

        # Get confidence from all metadata types
        for relation_name in [
            "title_relationships",
            "author_relationships",
            "genre_relationships",
            "series_relationships",
            "publisher_relationships",
            "metadata",
        ]:
            if hasattr(book, relation_name):
                queryset = getattr(book, relation_name).filter(source=source, is_active=True)
                avg_conf = queryset.aggregate(avg_confidence=Avg("confidence"))["avg_confidence"]
                if avg_conf:
                    confidences.append(avg_conf)

        return sum(confidences) / len(confidences) if confidences else 0.0

    def resume_interrupted_scans(self) -> Dict[str, any]:
        """Resume scanning for books that were interrupted due to API failures"""
        resume_results = {
            "sessions_processed": 0,
            "books_resumed": 0,
            "apis_recovered": [],
            "books_completed": 0,
        }

        try:
            # Check current API availability
            api_availability = self.check_api_availability()
            recovered_apis = [name for name, available in api_availability.items() if available]
            resume_results["apis_recovered"] = recovered_apis

            if not recovered_apis:
                logger.info("[RESUME] No APIs have recovered, skipping resume")
                return resume_results

            logger.info(f"[RESUME] APIs recovered: {recovered_apis}")

            # Find sessions that can be resumed
            resumable_sessions = ScanSession.objects.filter(can_resume=True, is_active=True).order_by("-created_at")[:5]  # Limit to recent sessions

            for session in resumable_sessions:
                logger.info(f"[RESUME] Processing session {session.session_id}")

                books_in_queue = session.resume_queue.copy()
                books_completed_this_session = 0

                for book_data in books_in_queue:
                    book_id = book_data["book_id"]
                    missing_sources = book_data.get("missing_sources", [])

                    try:
                        book = Book.objects.get(id=book_id)

                        # Check which missing sources are now available
                        available_missing = [source for source in missing_sources if source in recovered_apis]

                        if available_missing:
                            logger.info(f"[RESUME] Resuming book {book_id} for APIs: {available_missing}")

                            # Scan with only the recovered APIs
                            scanner = IntelligentAPIScanner(session.session_id)
                            scanner.available_apis = set(available_missing)

                            result = scanner.scan_book_with_intelligence(book, force_all_apis=False)

                            if result["apis_succeeded"]:
                                books_completed_this_session += 1
                                session.remove_book_from_resume_queue(book_id)

                        else:
                            logger.debug(f"[RESUME] No recovered APIs for book {book_id}")

                    except Book.DoesNotExist:
                        logger.warning(f"[RESUME] Book {book_id} not found, removing from queue")
                        session.remove_book_from_resume_queue(book_id)

                    except Exception as e:
                        logger.error(f"[RESUME] Error resuming book {book_id}: {e}")

                resume_results["books_resumed"] += len(books_in_queue)
                resume_results["books_completed"] += books_completed_this_session
                resume_results["sessions_processed"] += 1

                # Update session status
                if not session.resume_queue:
                    session.can_resume = False
                    session.save(update_fields=["can_resume"])

            logger.info(f"[RESUME] Completed: {resume_results}")

        except Exception as e:
            logger.error(f"[RESUME] Error during resume process: {e}")
            resume_results["error"] = str(e)

        return resume_results

    def get_scanning_recommendations(self, scan_folder_id: Optional[int] = None) -> Dict[str, any]:
        """Get recommendations for optimal scanning based on current API status"""
        recommendations = {
            "api_status": {},
            "recommended_mode": "full",
            "available_apis": [],
            "unavailable_apis": [],
            "books_needing_retry": 0,
            "estimated_completion": "100%",
        }

        try:
            # Check API availability
            api_availability = self.check_api_availability()
            recommendations["api_status"] = api_availability
            recommendations["available_apis"] = [name for name, avail in api_availability.items() if avail]
            recommendations["unavailable_apis"] = [name for name, avail in api_availability.items() if not avail]

            # Determine recommended scanning mode
            available_count = len(recommendations["available_apis"])
            total_apis = len(self.api_sources)

            if available_count == 0:
                recommendations["recommended_mode"] = "internal_only"
            elif available_count < total_apis:
                recommendations["recommended_mode"] = "partial_external"
            else:
                recommendations["recommended_mode"] = "full_external"

            # Count books that need retrying
            books_needing_retry = APIAccessLog.objects.filter(should_retry=True, can_retry_now=True).values("book").distinct().count()

            recommendations["books_needing_retry"] = books_needing_retry

            # Estimate completion percentage
            if scan_folder_id:
                # Calculate for specific folder
                from books.models import ScanFolder

                try:
                    folder = ScanFolder.objects.get(id=scan_folder_id)
                    total_books = folder.books.count()

                    if total_books > 0:
                        # Count books with good completeness
                        complete_books = BookAPICompleteness.objects.filter(
                            book__scan_folder=folder,
                            scan_priority__in=["complete", "low"],
                        ).count()

                        completion_pct = (complete_books / total_books) * 100
                        recommendations["estimated_completion"] = f"{completion_pct:.1f}%"

                except ScanFolder.DoesNotExist:
                    pass

        except Exception as e:
            logger.error(f"[RECOMMENDATIONS] Error generating recommendations: {e}")
            recommendations["error"] = str(e)

        return recommendations

    def complete_session(self):
        """Mark the current session as complete"""
        if self.session:
            self.session.is_active = False
            self.session.completed_at = timezone.now()
            self.session.can_resume = len(self.session.resume_queue) > 0
            self.session.save(update_fields=["is_active", "completed_at", "can_resume"])

            logger.info(f"[SESSION] Completed session {self.session_id}")


# Convenience functions for backward compatibility and easy usage


def scan_book_intelligently(book: Book, session_id: str = None) -> Dict[str, any]:
    """Scan a single book with intelligent API management"""
    scanner = IntelligentAPIScanner(session_id)
    return scanner.scan_book_with_intelligence(book)


def resume_all_interrupted_scans() -> Dict[str, any]:
    """Resume all interrupted scans that can be resumed"""
    scanner = IntelligentAPIScanner()
    return scanner.resume_interrupted_scans()


def get_api_recommendations(scan_folder_id: int = None) -> Dict[str, any]:
    """Get scanning recommendations based on current API status"""
    scanner = IntelligentAPIScanner()
    return scanner.get_scanning_recommendations(scan_folder_id)
