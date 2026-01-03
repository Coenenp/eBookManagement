"""
Quick book-by-book processing view.

This module provides a workflow for processing books one at a time from the top,
allowing users to review, confirm metadata, rename/move files, manage duplicates,
and handle remaining files in the folder.
"""
import os
import shutil
import logging
import requests
from pathlib import Path
from typing import Dict, List

from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.views import View
from django.http import JsonResponse
from django.db import transaction
from django.utils import timezone

from books.models import (
    Book, BookFile, FinalMetadata, DataSource,
    BookTitle, BookAuthor, Author, BookSeries, Series,
    BookPublisher, Publisher, BookMetadata
)
from books.scanner.external import query_metadata_and_covers_with_terms
from books.utils.opf_generator import save_opf_file, get_opf_filename
from books.utils.batch_renamer import CompanionFileFinder
from books.utils.isbn import normalize_isbn, normalize_publication_year

logger = logging.getLogger('books.scanner')


class QuickProcessView(LoginRequiredMixin, View):
    """View for quick book-by-book processing workflow."""

    template_name = 'books/quick_process.html'

    def get(self, request):
        """Display the next unprocessed book for review."""
        # Get the next unprocessed book (first book without is_reviewed=True)
        book = Book.objects.filter(
            finalmetadata__isnull=False
        ).exclude(
            finalmetadata__is_reviewed=True
        ).select_related(
            'finalmetadata'
        ).prefetch_related(
            'files',
            'titles',
            'author_relationships__author',
            'series_relationships__series',
            'publisher_relationships__publisher',
            'metadata',
            'covers',
            'genre_relationships__genre'
        ).order_by('id').first()

        if not book:
            messages.info(request, "No more books to process. All books have been reviewed!")
            return redirect('books:dashboard')

        # Get the book file
        book_file = book.files.first()
        if not book_file:
            messages.warning(request, f"Book {book.id} has no files. Skipping...")
            return self._skip_and_next(request, book.id)

        # Build context with all metadata sources
        context = self._build_book_context(book)

        return render(request, self.template_name, context)

    def post(self, request):
        """Handle form submission for book processing."""
        action = request.POST.get('action')
        book_id = request.POST.get('book_id')

        if not book_id:
            messages.error(request, "No book ID provided.")
            return redirect('books:quick_process')

        book = get_object_or_404(Book, pk=book_id)

        if action == 'lookup':
            return self._handle_metadata_lookup(request, book)
        elif action == 'confirm':
            return self._handle_confirm_and_process(request, book)
        elif action == 'skip':
            return self._skip_and_next(request, book_id)
        elif action == 'delete':
            return self._handle_delete(request, book)
        else:
            messages.error(request, f"Unknown action: {action}")
            return redirect('books:quick_process')

    def _build_book_context(self, book) -> Dict:
        """Build comprehensive context for book display."""
        book_file = book.files.first()
        file_path = book_file.file_path if book_file else None
        file_dir = Path(file_path).parent if file_path else None

        # Get all metadata grouped by field
        metadata_by_field = {}
        for meta in book.metadata.filter(is_active=True).select_related('source'):
            field = meta.field_name
            if field not in metadata_by_field:
                metadata_by_field[field] = []
            metadata_by_field[field].append({
                'value': meta.field_value,
                'source': meta.source.name,
                'confidence': meta.confidence,
            })

        # Get all titles
        titles = [{
            'value': title.title,
            'source': title.source.name,
            'confidence': title.confidence,
        } for title in book.titles.all().select_related('source')]

        # Get all authors
        authors = [{
            'value': ba.author.name,
            'source': ba.source.name if ba.source else 'Unknown',
            'confidence': ba.confidence,
        } for ba in book.author_relationships.all().select_related('author', 'source')]

        # Get all series
        series_list = [{
            'value': bs.series.name,
            'number': bs.series_number,
            'source': bs.source.name if bs.source else 'Unknown',
            'confidence': bs.confidence,
        } for bs in book.series_relationships.all().select_related('series', 'source')]

        # Get all publishers
        publishers = [{
            'value': bp.publisher.name,
            'source': bp.source.name,
            'confidence': bp.confidence,
        } for bp in book.publisher_relationships.all().select_related('publisher', 'source')]

        # Get all genres
        genres = [{
            'value': bg.genre.name,
            'source': bg.source.name if bg.source else 'Unknown',
            'confidence': bg.confidence,
        } for bg in book.genre_relationships.all().select_related('genre', 'source')]

        # Get covers
        covers = [{
            'id': cover.id,
            'url': cover.cover_path,
            'source': cover.source.name,
            'width': cover.width,
            'height': cover.height,
            'confidence': cover.confidence,
            'is_active': cover.is_active,
        } for cover in book.covers.all().select_related('source')]

        # Find companion files
        companion_files = []
        if file_path and os.path.exists(file_path):
            finder = CompanionFileFinder()
            companion_paths = finder.find_companion_files(file_path)
            for comp_path in companion_paths:
                companion_files.append({
                    'path': comp_path,
                    'name': os.path.basename(comp_path),
                    'size': os.path.getsize(comp_path) if os.path.exists(comp_path) else 0,
                })

        # Check for duplicate files (files with same final metadata)
        duplicates = self._find_duplicates(book)

        # List other files in the same directory
        other_files = []
        if file_dir and file_dir.exists():
            ebook_extensions = {'.epub', '.mobi', '.azw', '.azw3', '.pdf', '.cbz', '.cbr'}
            for item in file_dir.iterdir():
                if item.is_file():
                    # Skip the current book file and companion files
                    if str(item) == file_path:
                        continue
                    if str(item) in [c['path'] for c in companion_files]:
                        continue

                    # Add to other files list
                    other_files.append({
                        'path': str(item),
                        'name': item.name,
                        'size': item.stat().st_size if item.exists() else 0,
                        'is_ebook': item.suffix.lower() in ebook_extensions,
                    })

        # Get final metadata
        final_metadata = book.finalmetadata if hasattr(book, 'finalmetadata') else None

        return {
            'book': book,
            'book_file': book_file,
            'file_path': file_path,
            'file_dir': str(file_dir) if file_dir else None,
            'final_metadata': final_metadata,
            'titles': titles,
            'authors': authors,
            'series_list': series_list,
            'publishers': publishers,
            'genres': genres,
            'metadata_by_field': metadata_by_field,
            'covers': covers,
            'companion_files': companion_files,
            'duplicates': duplicates,
            'other_files': other_files,
        }

    def _find_duplicates(self, book) -> List[Dict]:
        """Find potential duplicate books based on file hash or metadata."""
        duplicates = []
        book_file = book.files.first()

        if not book_file:
            return duplicates

        # Find by file hash (exact duplicates)
        if book_file.file_path_hash:
            duplicate_files = BookFile.objects.filter(
                file_path_hash=book_file.file_path_hash
            ).exclude(
                book=book
            ).select_related('book', 'book__finalmetadata')

            for dup_file in duplicate_files:
                duplicates.append({
                    'type': 'exact',
                    'book': dup_file.book,
                    'file_path': dup_file.file_path,
                    'reason': 'Identical file hash',
                })

        # Find by similar metadata (title + author)
        if hasattr(book, 'finalmetadata') and book.finalmetadata:
            fm = book.finalmetadata
            if fm.final_title and fm.final_author:
                similar_books = Book.objects.filter(
                    finalmetadata__final_title__iexact=fm.final_title,
                    finalmetadata__final_author__iexact=fm.final_author
                ).exclude(
                    id=book.id
                ).select_related('finalmetadata').prefetch_related('files')

                for similar_book in similar_books:
                    dup_file = similar_book.files.first()
                    duplicates.append({
                        'type': 'similar',
                        'book': similar_book,
                        'file_path': dup_file.file_path if dup_file else 'Unknown',
                        'reason': 'Same title and author',
                    })

        return duplicates

    def _handle_metadata_lookup(self, request, book):
        """Perform metadata lookup for the book."""
        search_title = request.POST.get('search_title', '').strip()
        search_author = request.POST.get('search_author', '').strip()
        search_isbn = request.POST.get('search_isbn', '').strip()

        if not search_title and not search_author and not search_isbn:
            messages.warning(request, "Please provide at least a title, author, or ISBN for lookup.")
            return redirect('books:quick_process')

        try:
            # Perform the external metadata lookup
            query_metadata_and_covers_with_terms(
                book,
                search_title=search_title or None,
                search_author=search_author or None,
                search_isbn=search_isbn or None
            )

            # Refresh the book from database to get new metadata
            book.refresh_from_db()

            messages.success(request, "Metadata lookup completed. Please review the results below.")
        except Exception as e:
            logger.error(f"Error during metadata lookup for book {book.id}: {e}", exc_info=True)
            messages.error(request, f"Error during metadata lookup: {str(e)}")

        return redirect('books:quick_process')

    @transaction.atomic
    def _handle_confirm_and_process(self, request, book):
        """Confirm metadata and process the book (rename, move, create OPF, download covers)."""
        try:
            # 1. Update/create final metadata from form
            final_metadata = self._save_final_metadata(request, book)

            # 2. Check for duplicates and handle user choice
            duplicate_action = request.POST.get('duplicate_action')
            if duplicate_action == 'keep_existing':
                # Delete this book and keep the existing one
                self._delete_book_files(book)
                book.soft_delete()  # Use soft delete for consistency
                messages.success(request, "Book deleted. Kept the existing copy.")
                return redirect('books:quick_process')
            elif duplicate_action == 'keep_this':
                # Delete the duplicates
                duplicate_ids = request.POST.getlist('duplicate_ids')
                for dup_id in duplicate_ids:
                    try:
                        dup_book = Book.objects.get(id=dup_id)
                        self._delete_book_files(dup_book)
                        dup_book.soft_delete()  # Use soft delete for consistency
                    except Book.DoesNotExist:
                        pass
                messages.info(request, f"Deleted {len(duplicate_ids)} duplicate(s).")

            # 3. Generate new file path based on pattern
            folder_pattern = request.POST.get('folder_pattern', '${author.sortname}')
            filename_pattern = request.POST.get('filename_pattern', '${title}.${ext}')

            new_path = self._generate_new_path(book, folder_pattern, filename_pattern)

            # 4. Move/rename the ebook file
            book_file = book.files.first()
            if book_file and book_file.file_path:
                old_path = book_file.file_path
                self._move_file(old_path, new_path)
                book_file.file_path = new_path
                book_file.save()

                # 5. Move companion files
                include_companions = request.POST.get('include_companions') == 'on'
                if include_companions:
                    self._move_companion_files(old_path, new_path)

                # 6. Create/update OPF file
                opf_path = str(Path(new_path).parent / get_opf_filename(Path(new_path).name))
                save_opf_file(final_metadata, opf_path, Path(new_path).name)
                book_file.opf_path = opf_path
                book_file.save()

                # 7. Download covers
                cover_urls = request.POST.getlist('selected_covers')
                if cover_urls:
                    self._download_covers(book, new_path, cover_urls)

                # 8. Delete original files if in different location
                if Path(old_path).parent != Path(new_path).parent:
                    old_dir = Path(old_path).parent
                    if old_dir.exists():
                        # Handle remaining files
                        self._handle_remaining_files(request, old_dir)

                messages.success(request, f"Book processed successfully: {new_path}")

            # Mark as reviewed and renamed with proper flags and path
            final_metadata.is_reviewed = True
            final_metadata.mark_as_renamed(new_path, user=request.user if request.user.is_authenticated else None)

            # Update final_path separately since mark_as_renamed saves with specific update_fields
            final_metadata.final_path = new_path
            final_metadata.save()

        except Exception as e:
            logger.error(f"Error processing book {book.id}: {e}", exc_info=True)
            messages.error(request, f"Error processing book: {str(e)}")

        return redirect('books:quick_process')

    def _save_final_metadata(self, request, book) -> FinalMetadata:
        """Save final metadata from form data and create source records."""
        final_metadata, created = FinalMetadata.objects.get_or_create(book=book)

        # Get or create user-confirmed data source
        user_source, _ = DataSource.objects.get_or_create(
            name=DataSource.USER_CONFIRMED,
            defaults={'trust_level': 1.0}
        )

        # Update FinalMetadata fields from form
        final_title = request.POST.get('final_title', '').strip()
        final_author = request.POST.get('final_author', '').strip()
        final_series = request.POST.get('final_series', '').strip()
        final_series_number = request.POST.get('final_series_number', '').strip()
        final_publisher = request.POST.get('final_publisher', '').strip()
        description = request.POST.get('description', '').strip()

        final_metadata.final_title = final_title
        final_metadata.final_author = final_author
        final_metadata.final_series = final_series
        final_metadata.final_series_number = final_series_number
        final_metadata.final_publisher = final_publisher
        final_metadata.description = description

        # Normalize ISBN to 13-digit format (handles variations like 978-1-62625-172-4, 978 1 62625 172 4, etc.)
        raw_isbn = request.POST.get('isbn', '').strip()
        final_metadata.isbn = normalize_isbn(raw_isbn) or raw_isbn  # Use normalized or fall back to raw if invalid
        final_metadata.language = request.POST.get('language', '').strip()

        # Validate and normalize publication year (1450-current year + 5)
        raw_year = request.POST.get('publication_year', '').strip()
        normalized_year = normalize_publication_year(raw_year)
        if raw_year and not normalized_year:
            messages.warning(request, f"Invalid publication year '{raw_year}'. Must be between 1450-{timezone.now().year + 5}.")
        final_metadata.publication_year = normalized_year

        # Set confidence scores
        final_metadata.final_title_confidence = 1.0  # User confirmed = 100%
        final_metadata.final_author_confidence = 1.0

        final_metadata.save()

        # Create/update source records with is_active=True
        # 1. Title
        if final_title:
            # Deactivate all existing titles
            book.titles.update(is_active=False)
            # Create new user-confirmed title
            BookTitle.objects.get_or_create(
                book=book,
                title=final_title,
                source=user_source,
                defaults={'confidence': 1.0, 'is_active': True}
            )

        # 2. Author
        if final_author:
            from books.utils.authors import parse_author_name
            # Deactivate all existing authors
            book.author_relationships.update(is_active=False)
            # Parse and create author
            first_name, last_name = parse_author_name(final_author)
            author_obj, _ = Author.objects.get_or_create(
                first_name=first_name,
                last_name=last_name
            )
            BookAuthor.objects.get_or_create(
                book=book,
                author=author_obj,
                source=user_source,
                defaults={'confidence': 1.0, 'is_active': True, 'is_main_author': True}
            )

        # 3. Series
        if final_series:
            # Deactivate all existing series
            book.series_relationships.update(is_active=False)
            # Create series
            series_obj, _ = Series.objects.get_or_create(name=final_series)
            BookSeries.objects.get_or_create(
                book=book,
                series=series_obj,
                source=user_source,
                defaults={
                    'confidence': 1.0,
                    'is_active': True,
                    'series_number': final_series_number or None
                }
            )

        # 4. Publisher
        if final_publisher:
            # Deactivate all existing publishers
            book.publisher_relationships.update(is_active=False)
            # Create publisher
            publisher_obj, _ = Publisher.objects.get_or_create(name=final_publisher)
            BookPublisher.objects.get_or_create(
                book=book,
                publisher=publisher_obj,
                source=user_source,
                defaults={'confidence': 1.0, 'is_active': True}
            )

        # 5. ISBN as metadata
        if final_metadata.isbn:
            BookMetadata.objects.update_or_create(
                book=book,
                field_name='isbn',
                source=user_source,
                defaults={'field_value': final_metadata.isbn, 'confidence': 1.0, 'is_active': True}
            )

        # 6. Publication year as metadata
        if normalized_year:
            BookMetadata.objects.update_or_create(
                book=book,
                field_name='publication_year',
                source=user_source,
                defaults={'field_value': str(normalized_year), 'confidence': 1.0, 'is_active': True}
            )

        # 7. Description as metadata
        if description:
            BookMetadata.objects.update_or_create(
                book=book,
                field_name='description',
                source=user_source,
                defaults={'field_value': description, 'confidence': 1.0, 'is_active': True}
            )

        # 8. Language as metadata
        if final_metadata.language:
            BookMetadata.objects.update_or_create(
                book=book,
                field_name='language',
                source=user_source,
                defaults={'field_value': final_metadata.language, 'confidence': 1.0, 'is_active': True}
            )

        return final_metadata

    def _generate_new_path(self, book, folder_pattern: str, filename_pattern: str) -> str:
        """Generate new file path using renaming engine."""
        from books.utils.renaming_engine import RenamingEngine

        engine = RenamingEngine()
        target_folder = engine.process_template(folder_pattern, book)
        target_filename = engine.process_template(filename_pattern, book)

        # Use a base library path (configurable)
        base_path = Path(book.scan_folder.path if book.scan_folder else '/media/ebooks')
        new_path = base_path / target_folder / target_filename

        return str(new_path)

    def _move_file(self, source: str, target: str):
        """Move a file to a new location, creating directories as needed."""
        source_path = Path(source)
        target_path = Path(target)

        if not source_path.exists():
            raise FileNotFoundError(f"Source file not found: {source}")

        # Create target directory
        target_path.parent.mkdir(parents=True, exist_ok=True)

        # Handle existing file
        if target_path.exists():
            # Generate unique name
            counter = 1
            while target_path.exists():
                stem = target_path.stem
                suffix = target_path.suffix
                target_path = target_path.parent / f"{stem}_{counter}{suffix}"
                counter += 1

        # Move the file
        shutil.move(str(source_path), str(target_path))
        logger.info(f"Moved file: {source} -> {target_path}")

        return str(target_path)

    def _move_companion_files(self, old_book_path: str, new_book_path: str):
        """Move companion files alongside the renamed book."""
        finder = CompanionFileFinder()
        companion_files = finder.find_companion_files(old_book_path)

        old_base = Path(old_book_path).stem
        new_base = Path(new_book_path).stem
        new_dir = Path(new_book_path).parent

        for companion_path in companion_files:
            comp_file = Path(companion_path)
            comp_name = comp_file.name

            # Determine new name
            if comp_name.startswith(old_base):
                # Replace old base with new base
                new_comp_name = comp_name.replace(old_base, new_base, 1)
            else:
                # Generic file (cover.jpg, metadata.opf, etc.) - keep as is
                new_comp_name = comp_name

            new_comp_path = new_dir / new_comp_name

            try:
                if comp_file.exists():
                    shutil.move(str(comp_file), str(new_comp_path))
                    logger.info(f"Moved companion file: {comp_file} -> {new_comp_path}")
            except Exception as e:
                logger.error(f"Error moving companion file {comp_file}: {e}")

    def _download_covers(self, book, book_path: str, cover_urls: List[str]):
        """Download selected covers to the book's directory."""
        book_dir = Path(book_path).parent
        book_base = Path(book_path).stem

        google_source, _ = DataSource.objects.get_or_create(name=DataSource.GOOGLE_BOOKS_COVERS)

        for idx, cover_url in enumerate(cover_urls):
            if not cover_url:
                continue

            try:
                # Download cover
                cover_filename = f"{book_base}_cover_{idx}.jpg" if idx > 0 else f"{book_base}_cover.jpg"
                cover_path = book_dir / cover_filename

                # Simple download using requests
                response = requests.get(cover_url, timeout=10)
                response.raise_for_status()

                with open(cover_path, 'wb') as f:
                    f.write(response.content)

                logger.info(f"Downloaded cover to: {cover_path}")

                # Update BookFile cover_path if this is the first cover
                if idx == 0:
                    book_file = book.files.first()
                    if book_file:
                        book_file.cover_path = str(cover_path)
                        book_file.save()

            except Exception as e:
                logger.error(f"Error downloading cover from {cover_url}: {e}")

    def _handle_remaining_files(self, request, old_dir: Path):
        """Handle remaining files in the old directory."""
        remaining_action = request.POST.get('remaining_files_action', 'leave')

        if remaining_action == 'delete':
            # Delete all remaining files
            try:
                for item in old_dir.iterdir():
                    if item.is_file():
                        item.unlink()
                        logger.info(f"Deleted remaining file: {item}")

                # Try to remove the directory if empty
                if not any(old_dir.iterdir()):
                    old_dir.rmdir()
                    logger.info(f"Removed empty directory: {old_dir}")
            except Exception as e:
                logger.error(f"Error deleting remaining files in {old_dir}: {e}")

        elif remaining_action == 'move':
            # Move remaining files to a specified location
            move_target = request.POST.get('remaining_files_target', '')
            if move_target:
                target_dir = Path(move_target)
                target_dir.mkdir(parents=True, exist_ok=True)

                try:
                    for item in old_dir.iterdir():
                        if item.is_file():
                            shutil.move(str(item), str(target_dir / item.name))
                            logger.info(f"Moved remaining file: {item} -> {target_dir / item.name}")

                    # Try to remove the directory if empty
                    if not any(old_dir.iterdir()):
                        old_dir.rmdir()
                        logger.info(f"Removed empty directory: {old_dir}")
                except Exception as e:
                    logger.error(f"Error moving remaining files from {old_dir}: {e}")

        # 'leave' - do nothing
    def _delete_book_files(self, book):
        """Delete all files associated with a book."""
        for book_file in book.files.all():
            if book_file.file_path and os.path.exists(book_file.file_path):
                try:
                    os.remove(book_file.file_path)
                    logger.info(f"Deleted file: {book_file.file_path}")
                except Exception as e:
                    logger.error(f"Error deleting file {book_file.file_path}: {e}")

            # Delete companion files
            if book_file.file_path:
                finder = CompanionFileFinder()
                companions = finder.find_companion_files(book_file.file_path)
                for comp_path in companions:
                    try:
                        if os.path.exists(comp_path):
                            os.remove(comp_path)
                            logger.info(f"Deleted companion file: {comp_path}")
                    except Exception as e:
                        logger.error(f"Error deleting companion file {comp_path}: {e}")

    def _skip_and_next(self, request, book_id):
        """Skip the current book and move to the next one."""
        messages.info(request, f"Skipped book {book_id}.")
        return redirect('books:quick_process')

    def _handle_delete(self, request, book):
        """Delete the book and all its files."""
        try:
            self._delete_book_files(book)
            book_id = book.id

            # Use soft delete instead of hard delete for consistency
            # This allows the book to be recovered if files are restored
            book.soft_delete()

            messages.success(request, f"Book {book_id} and all associated files deleted.")
        except Exception as e:
            logger.error(f"Error deleting book {book.id}: {e}", exc_info=True)
            messages.error(request, f"Error deleting book: {str(e)}")

        return redirect('books:quick_process')


@login_required
def quick_process_ajax_preview(request):
    """AJAX endpoint to preview the renamed path."""
    book_id = request.GET.get('book_id')
    folder_pattern = request.GET.get('folder_pattern', '')
    filename_pattern = request.GET.get('filename_pattern', '')

    if not book_id:
        return JsonResponse({'error': 'No book ID provided'}, status=400)

    try:
        book = get_object_or_404(Book, pk=book_id)

        from books.utils.renaming_engine import RenamingEngine
        engine = RenamingEngine()

        target_folder = engine.process_template(folder_pattern, book)
        target_filename = engine.process_template(filename_pattern, book)

        preview_path = f"{target_folder}/{target_filename}" if target_folder and target_filename else "Error"

        return JsonResponse({
            'preview': preview_path,
            'folder': target_folder,
            'filename': target_filename,
        })

    except Exception as e:
        logger.error(f"Error generating preview for book {book_id}: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)
