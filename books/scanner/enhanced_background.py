"""
Enhanced Background Scanner with Intelligent API Management

This module integrates the intelligent API scanner with the existing background
scanning system to provide graceful degradation and automatic resumption.
"""
import logging
import time
from typing import Dict, List, Optional

from books.scanner.background import BackgroundScanner as BaseBackgroundScanner
from books.scanner.intelligent import IntelligentAPIScanner
from books.models import ScanFolder
from books.models import ScanSession

logger = logging.getLogger("books.scanner")


class EnhancedBackgroundScanner(BaseBackgroundScanner):
    """Enhanced background scanner with intelligent API management that:
    1. Continues scanning even when APIs fail
    2. Tracks API success per book
    3. Creates resumption queues for failed API calls
    4. Provides detailed progress reporting
    """

    def __init__(self, job_id: str):
        super().__init__(job_id)
        self.intelligent_scanner = None
        self.scan_session = None
        self.api_mode = 'adaptive'  # 'full', 'partial', 'internal_only', 'adaptive'

    def scan_folder(self, folder_path: str, language: str = None,
                   enable_external_apis: bool = True, content_type: str = None) -> Dict:
        """Enhanced folder scanning with intelligent API management"""

        try:
            logger.info(f"[ENHANCED SCAN] Starting intelligent scan of {folder_path}")

            # Initialize intelligent scanner
            self.intelligent_scanner = IntelligentAPIScanner()
            self.scan_session = self.intelligent_scanner.session

            # Get API availability recommendations
            recommendations = self.intelligent_scanner.get_scanning_recommendations()
            logger.info(f"[ENHANCED SCAN] API recommendations: {recommendations}")

            # Adjust scanning mode based on API availability
            if not enable_external_apis:
                self.api_mode = 'internal_only'
            elif not recommendations['available_apis']:
                logger.warning("[ENHANCED SCAN] No APIs available, switching to internal-only mode")
                self.api_mode = 'internal_only'
                enable_external_apis = False
            elif len(recommendations['available_apis']) < len(recommendations['api_status']):
                logger.info(f"[ENHANCED SCAN] Partial API availability, using: {recommendations['available_apis']}")
                self.api_mode = 'partial'
            else:
                self.api_mode = 'full'

            # Update progress with API mode information
            self.progress.update(0, 100, "Initializing",
                               f"Scanning mode: {self.api_mode}, Available APIs: {len(recommendations['available_apis'])}")

            # Call parent scan method with modifications
            result = self._enhanced_folder_scan(folder_path, language, enable_external_apis, content_type)

            # Complete the session
            self.intelligent_scanner.complete_session()

            # Add API-specific information to result
            result.update({
                'api_mode': self.api_mode,
                'available_apis': recommendations['available_apis'],
                'session_id': self.intelligent_scanner.session_id,
                'books_needing_retry': len(self.scan_session.resume_queue) if self.scan_session else 0
            })

            logger.info(f"[ENHANCED SCAN] Completed with mode: {self.api_mode}")
            return result

        except Exception as e:
            logger.error(f"[ENHANCED SCAN] Error in enhanced scan: {e}")
            if self.intelligent_scanner:
                self.intelligent_scanner.complete_session()
            raise

    def _enhanced_folder_scan(self, folder_path: str, language: str = None,
                            enable_external_apis: bool = True, content_type: str = None) -> Dict:
        """Enhanced folder scanning implementation"""

        from books.scanner.scanning import FolderScanner
        from books.models import ScanFolder

        # Initialize folder scanner
        folder_scanner = FolderScanner()

        # Get or create scan folder record
        try:
            scan_folder = ScanFolder.objects.get(path=folder_path)
        except ScanFolder.DoesNotExist:
            logger.warning(f"[ENHANCED SCAN] Scan folder not found: {folder_path}")
            return {'success': False, 'error': 'Scan folder not found'}

        # Update session with folder info
        if self.scan_session:
            self.scan_session.scan_folder = scan_folder
            self.scan_session.save(update_fields=['scan_folder'])

        # Get books to scan
        book_files = list(folder_scanner.get_book_files_in_folder(folder_path))
        total_books = len(book_files)

        if self.scan_session:
            self.scan_session.total_books = total_books
            self.scan_session.save(update_fields=['total_books'])

        if total_books == 0:
            logger.info("[ENHANCED SCAN] No books found in folder")
            return {'success': True, 'message': 'No books found', 'books_processed': 0}

        logger.info(f"[ENHANCED SCAN] Found {total_books} books to process")

        # Process each book
        processed_count = 0
        error_count = 0
        api_success_count = 0

        for i, book_path in enumerate(book_files):
            try:
                self.progress.update(
                    i, total_books,
                    "Processing",
                    f"Processing book {i+1}/{total_books}: {book_path}"
                )

                # Process the book with enhanced intelligence
                book_result = self._process_single_book_enhanced(
                    book_path, scan_folder, enable_external_apis
                )

                if book_result['success']:
                    processed_count += 1
                    if book_result.get('external_apis_used', False):
                        api_success_count += 1
                else:
                    error_count += 1

            except Exception as e:
                logger.error(f"[ENHANCED SCAN] Error processing {book_path}: {e}")
                error_count += 1

            # Add delay to prevent overwhelming the system
            time.sleep(0.1)

        # Final progress update
        self.progress.update(
            total_books, total_books,
            "Completed",
            f"Processed {processed_count} books, {api_success_count} with external APIs, {error_count} errors"
        )

        return {
            'success': True,
            'books_processed': processed_count,
            'books_with_apis': api_success_count,
            'errors': error_count,
            'total_books': total_books
        }

    def _process_single_book_enhanced(self, book_path: str, scan_folder: ScanFolder,
                                    enable_external_apis: bool) -> Dict:
        """Process a single book with enhanced API intelligence"""

        result = {
            'success': False,
            'book_path': book_path,
            'external_apis_used': False,
            'apis_succeeded': [],
            'apis_failed': [],
            'error': None
        }

        try:
            from books.scanner.scanning import FolderScanner
            folder_scanner = FolderScanner()

            # Create book record (same as parent)
            book = folder_scanner.create_book_from_file(book_path, scan_folder)
            if not book:
                result['error'] = 'Failed to create book record'
                return result

            # Extract internal metadata (same as parent)
            folder_scanner.extract_internal_metadata(book)

            # Enhanced external API handling
            if enable_external_apis and self.api_mode != 'internal_only':
                try:
                    # Use intelligent scanner for this book
                    api_result = self.intelligent_scanner.scan_book_with_intelligence(
                        book, force_all_apis=(self.api_mode == 'full')
                    )

                    result['external_apis_used'] = len(api_result['apis_attempted']) > 0
                    result['apis_succeeded'] = api_result['apis_succeeded']
                    result['apis_failed'] = api_result['apis_failed']

                    # Log API usage details
                    if api_result['apis_succeeded']:
                        logger.info(f"[ENHANCED API] Book {book.id}: Success with {api_result['apis_succeeded']}")
                    if api_result['apis_failed']:
                        logger.warning(f"[ENHANCED API] Book {book.id}: Failed with {api_result['apis_failed']}")

                except Exception as api_error:
                    logger.warning(f"[ENHANCED API] API error for book {book.id}: {api_error}")
                    result['error'] = f"API error: {str(api_error)}"

                    # Continue without APIs - don't fail the entire book
                    logger.info(f"[ENHANCED SCAN] Continuing without APIs for book {book.id}")

            # Sync final metadata (same as parent)
            if hasattr(book, 'finalmetadata'):
                book.finalmetadata.sync_from_sources()

            result['success'] = True
            logger.debug(f"[ENHANCED SCAN] Successfully processed: {book_path}")

        except Exception as e:
            logger.error(f"[ENHANCED SCAN] Error processing book {book_path}: {e}")
            result['error'] = str(e)

        return result


def scan_folder_in_background_enhanced(folder_id: int, folder_path: str, folder_name: str,
                                     content_type: str, language: str, enable_external_apis: bool = True):
    """Enhanced background folder scanning with intelligent API management"""
    import uuid
    import threading

    # Generate unique job ID
    job_id = str(uuid.uuid4())

    logger.info(f"[ENHANCED BACKGROUND] Starting enhanced scan for folder {folder_name}")
    logger.info(f"[ENHANCED BACKGROUND] Job ID: {job_id}, External APIs: {enable_external_apis}")

    # Start background scan thread with enhanced scanner
    thread = threading.Thread(
        target=_background_scan_folder_enhanced,
        args=(job_id, folder_path, language, enable_external_apis, content_type),
        daemon=True,
        name=f"enhanced_scan_{job_id[:8]}"
    )

    try:
        thread.start()
        logger.info(f"[ENHANCED BACKGROUND] Started enhanced background thread for job {job_id}")
        return job_id
    except Exception as e:
        logger.error(f"[ENHANCED BACKGROUND] Failed to start thread: {e}")
        raise


def _background_scan_folder_enhanced(job_id: str, folder_path: str, language: str,
                                   enable_external_apis: bool, content_type: str):
    """Enhanced background scanning function"""

    scanner = None
    try:
        # Create enhanced scanner
        scanner = EnhancedBackgroundScanner(job_id)

        logger.info(f"[ENHANCED BACKGROUND] Starting enhanced scan: job_id={job_id}")

        # Perform the scan
        result = scanner.scan_folder(folder_path, language, enable_external_apis, content_type)

        logger.info(f"[ENHANCED BACKGROUND] Enhanced scan completed: {result}")

    except Exception as e:
        logger.error(f"[ENHANCED BACKGROUND] Enhanced background scan failed: {e}")

        if scanner:
            scanner.progress.complete(
                success=False,
                message=f"Enhanced scan failed: {str(e)}"
            )

    finally:
        # Clean up
        if scanner and scanner.intelligent_scanner:
            scanner.intelligent_scanner.complete_session()


# Management command helpers

def resume_all_background_scans() -> Dict:
    """Resume all background scans that were interrupted due to API failures"""
    from books.scanner.intelligent import resume_all_interrupted_scans
    return resume_all_interrupted_scans()


def get_scan_recommendations(folder_id: Optional[int] = None) -> Dict:
    """Get scanning recommendations for a folder"""
    from books.scanner.intelligent import get_api_recommendations
    return get_api_recommendations(folder_id)


def get_active_scan_sessions() -> List[Dict]:
    """Get information about active scan sessions"""
    sessions = []

    try:
        active_sessions = ScanSession.objects.filter(is_active=True).order_by('-created_at')

        for session in active_sessions:
            sessions.append({
                'session_id': session.session_id,
                'folder_name': session.scan_folder.name if session.scan_folder else 'Unknown',
                'progress': f"{session.processed_books}/{session.total_books}",
                'completion_pct': session.completion_percentage,
                'external_data_pct': session.external_data_percentage,
                'can_resume': session.can_resume,
                'resume_queue_size': len(session.resume_queue),
                'started': session.created_at
            })

    except Exception as e:
        logger.error(f"[SCAN SESSIONS] Error getting active sessions: {e}")

    return sessions
