"""
Book management utilities for handling metadata, covers, and form processing.
"""

import os
import json
import logging
from django.conf import settings
from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from django.db import IntegrityError

from .models import (
    Author, Book, BookTitle, BookAuthor, BookCover, BookSeries, BookPublisher,
    BookGenre, BookMetadata, DataSource, Series, Publisher, Genre
)

logger = logging.getLogger('books.scanner')


class MetadataProcessor:
    """Handles processing and validation of metadata entries with bulk operations."""

    @staticmethod
    def handle_manual_entries(request, book, form_data):
        """Process manual entries and assign them to FinalMetadata."""
        manual_source, _ = DataSource.objects.get_or_create(
            name=DataSource.MANUAL,
            defaults={'trust_level': 1.0}
        )

        field_handlers = {
            'final_title': MetadataProcessor._handle_manual_title,
            'final_author': MetadataProcessor._handle_manual_author,
            'final_series': MetadataProcessor._handle_manual_series,
            'final_publisher': MetadataProcessor._handle_manual_publisher,
            'publication_year': MetadataProcessor._handle_manual_metadata_field,
            'language': MetadataProcessor._handle_manual_metadata_field,
            'isbn': MetadataProcessor._handle_manual_metadata_field,
            'description': MetadataProcessor._handle_manual_metadata_field,
        }

        # Map field names to their corresponding model queries for checking existing data
        existing_data_checks = {
            'final_title': lambda: book.titles.filter(is_active=True).exists(),
            'final_author': lambda: book.author_relationships.filter(is_active=True).exists(),
            'final_series': lambda: book.series_relationships.filter(is_active=True).exists(),
            'final_publisher': lambda: book.publisher_relationships.filter(is_active=True).exists(),
            'publication_year': lambda: book.metadata.filter(field_name='publication_year', is_active=True).exists(),
            'language': lambda: book.metadata.filter(field_name='language', is_active=True).exists(),
            'isbn': lambda: book.metadata.filter(field_name='isbn', is_active=True).exists(),
            'description': lambda: book.metadata.filter(field_name='description', is_active=True).exists(),
        }

        bulk_map = {
            BookTitle: [],
            BookAuthor: [],
            BookSeries: [],
            BookPublisher: [],
            BookMetadata: [],
            BookGenre: [],
        }

        final_metadata = book.finalmetadata

        # Process each field
        for field_name, handler in field_handlers.items():
            manual_flag = request.POST.get(f'manual_entry_{field_name}')
            field_value = form_data.get(field_name)

            # Check if field has a value
            has_value = field_value and str(field_value).strip()

            # Check if there's existing data for this field
            has_existing_data = existing_data_checks.get(field_name, lambda: False)()

            # Determine if this should be treated as manual entry:
            # 1. Explicitly marked as manual (manual_flag == 'true'), OR
            # 2. Field has a value but no existing data (no dropdown was shown), OR
            # 3. Field has a value and manual_flag is not explicitly 'false'
            should_be_manual = (
                manual_flag == 'true' or
                (has_value and not has_existing_data and manual_flag != 'false')
            )

            logger.debug(f"Processing {field_name}: manual_flag={manual_flag}, has_value={bool(has_value)}, "
                         f"has_existing_data={has_existing_data}, should_be_manual={should_be_manual}")

            if should_be_manual and has_value:
                handler_form_data = form_data.copy()
                if field_value == '__manual__':
                    manual_field_key = f"manual_{field_name.replace('final_', '')}"
                    manual_value = request.POST.get(manual_field_key, '').strip()
                    if manual_value:
                        handler_form_data[field_name] = manual_value

                entry = handler(book, field_name, handler_form_data, manual_source)
                if entry:
                    logger.debug(f"Created manual entry for {field_name}: {entry}")
                    # Only add to bulk_map if it's a real model instance (not a mock for testing)
                    entry_type = type(entry)
                    if entry_type in bulk_map:
                        bulk_map[entry_type].append(entry)

                    if field_name.startswith('final_'):
                        model_to_field = {
                            BookTitle: 'title',
                            BookAuthor: 'author__name',
                            BookSeries: 'name',
                            BookPublisher: 'name',
                        }
                        field_path = model_to_field.get(type(entry))
                        if field_path:
                            # Support nested fields like author.name
                            if '__' in field_path:
                                parts = field_path.split('__')
                                value = entry
                                for part in parts:
                                    value = getattr(value, part, None)
                            else:
                                value = getattr(entry, field_path, None)

                            logger.debug(f"Assigning {field_name} = '{value}' from manual entry")
                            setattr(final_metadata, field_name, value)

                    else:
                        # It's a dynamic field like 'isbn', 'language', etc.
                        sanitized_value = MetadataProcessor._sanitize_metadata_value(field_name, form_data.get(field_name))
                        if sanitized_value is not None:
                            setattr(final_metadata, field_name, sanitized_value)
                            logger.debug(f"Set final_metadata.{field_name} = '{sanitized_value}' from manual entry")
                        else:
                            logger.debug(f"Skipping assignment for {field_name} due to invalid value")

                else:
                    logger.warning(f"No entry created for manual {field_name}")

            elif not should_be_manual and has_value:
                # Use form_data directly for non-manual fields
                value = form_data.get(field_name)
                if field_name.startswith('final_'):
                    model_map = {
                        'final_title': (BookTitle, 'title', None),  # title is a plain string
                        'final_author': (BookAuthor, 'author', Author),
                        'final_series': (BookSeries, 'series', Series),
                        'final_publisher': (BookPublisher, 'publisher', Publisher),
                    }
                    model_info = model_map.get(field_name)
                    if model_info and value:
                        model_class, field_attr, related_model = model_info

                        # Resolve related object if applicable
                        if related_model:
                            filter_value = related_model.objects.filter(name=value).first()
                        else:
                            filter_value = value  # For plain string fields like title

                        if filter_value:
                            filter_kwargs = {'book': book, field_attr: filter_value}
                            instance = model_class.objects.filter(**filter_kwargs).first()
                            if instance:
                                value_to_assign = getattr(instance, field_attr)
                                logger.debug(f"Assigning {field_name} = '{value_to_assign}' from {instance}")
                                setattr(final_metadata, field_name, value_to_assign)
                            else:
                                logger.warning(f"No matching {model_class.__name__} found for value '{value}'")

                else:
                    sanitized_value = MetadataProcessor._sanitize_metadata_value(field_name, form_data.get(field_name))
                    if sanitized_value is not None:
                        setattr(final_metadata, field_name, sanitized_value)
                    else:
                        logger.debug(f"Skipping assignment for {field_name} due to invalid value")

        # Handle manual genres
        manual_genres = request.POST.get('manual_genres', '').strip()
        if manual_genres:
            logger.debug(f"Processing manual genres: {manual_genres}")
            genre_entries = MetadataProcessor._handle_manual_genres(request, book, manual_source)
            bulk_map[BookGenre].extend(genre_entries)

        # Bulk create entries
        for model_class, entries in bulk_map.items():
            if entries:
                logger.debug(f"Bulk creating {len(entries)} entries for {model_class.__name__}")
                try:
                    created_entries = model_class.objects.bulk_create(entries, ignore_conflicts=True)
                    logger.info(f"Successfully bulk created {len(created_entries)} {model_class.__name__} entries")
                except Exception as e:
                    logger.warning(f"Bulk create failed for {model_class.__name__}: {e}")
                    for entry in entries:
                        try:
                            entry.save()
                            logger.debug(f"Individual save successful for {entry}")
                        except Exception as save_error:
                            logger.error(f"Individual save failed for {entry}: {save_error}")

    @staticmethod
    def _sanitize_metadata_value(field_name, value):
        if value in [None, '', 'null']:
            return None

        if field_name == 'publication_year':
            try:
                return int(value)
            except (ValueError, TypeError):
                return None

        if isinstance(value, str):
            value = value.strip()
            if not value:
                return None

        return value

    @staticmethod
    def _handle_manual_title(book, field_name, form_data, manual_source):
        title_value = form_data.get('final_title', '').strip()
        if title_value:
            logger.debug(f"Creating manual title entry: {title_value}")
            return BookTitle(
                book=book,
                title=title_value,
                source=manual_source,
                confidence=1.0,
                is_active=True  # Ensure it's active
            )
        return None

    @staticmethod
    def _handle_manual_author(book, field_name, form_data, manual_source):
        author_value = form_data.get('final_author', '').strip()
        if author_value:
            logger.debug(f"Creating manual author entry: {author_value}")

            try:
                # Try to create the author - the model's save() method handles normalization correctly now
                author, created = Author.objects.get_or_create(
                    name=author_value,
                    defaults={'is_reviewed': True}
                )
                if created:
                    logger.debug(f"Created new author: {author}")
                else:
                    logger.debug(f"Found existing author: {author}")
            except IntegrityError as e:
                if "UNIQUE constraint failed: books_author.name_normalized" in str(e):
                    # Find existing author by normalized name
                    normalized = Author.normalize_name(author_value)
                    try:
                        author = Author.objects.get(name_normalized=normalized)
                        logger.debug(f"Found existing author via normalized name: {author}")
                        created = False
                    except Author.DoesNotExist:
                        logger.error(f"Constraint error but couldn't find existing author: {e}")
                        return
                else:
                    logger.error(f"Unexpected IntegrityError: {e}")
                    return

            # Check if BookAuthor relationship already exists
            existing_book_author = BookAuthor.objects.filter(
                book=book,
                author=author,
                source=manual_source
            ).first()

            if existing_book_author:
                # Update existing entry
                existing_book_author.confidence = 1.0
                existing_book_author.is_main_author = True
                existing_book_author.is_active = True
                existing_book_author.save()
                logger.debug(f"Updated existing book author: {existing_book_author}")
                return None  # Don't add to bulk create since we saved directly
            else:
                # Create new BookAuthor entry
                return BookAuthor(
                    book=book,
                    author=author,
                    source=manual_source,
                    confidence=1.0,
                    is_main_author=True,
                    is_active=True  # Ensure it's active
                )
        return None

    @staticmethod
    def _handle_manual_series(book, field_name, form_data, manual_source):
        series_value = form_data.get('final_series', '').strip()
        if series_value:
            logger.debug(f"Creating manual series entry: {series_value}")
            series, created = Series.objects.get_or_create(name=series_value)
            if created:
                logger.debug(f"Created new series: {series}")

            series_number = form_data.get('final_series_number', '').strip()

            # Check if this exact combination already exists
            existing_book_series = BookSeries.objects.filter(
                book=book,
                series=series,
                source=manual_source
            ).first()

            if existing_book_series:
                # Update existing entry
                existing_book_series.confidence = 1.0
                existing_book_series.series_number = series_number if series_number else None
                existing_book_series.is_active = True
                existing_book_series.save()
                logger.debug(f"Updated existing book series: {existing_book_series}")
                return None  # Don't add to bulk create since we saved directly
            else:
                # Create new entry for bulk create
                return BookSeries(
                    book=book,
                    series=series,
                    source=manual_source,
                    confidence=1.0,
                    series_number=series_number if series_number else None,
                    is_active=True
                )
        return None

    @staticmethod
    def _handle_manual_publisher(book, field_name, form_data, manual_source):
        publisher_value = form_data.get('final_publisher', '').strip()
        if publisher_value:
            logger.debug(f"Creating manual publisher entry: {publisher_value}")
            publisher, created = Publisher.objects.get_or_create(
                name=publisher_value,
                defaults={'is_reviewed': True}
            )
            if created:
                logger.debug(f"Created new publisher: {publisher}")

            return BookPublisher(
                book=book,
                publisher=publisher,
                source=manual_source,
                confidence=1.0,
                is_active=True  # Ensure it's active
            )
        return None

    @staticmethod
    def _handle_manual_metadata_field(book, field_name, form_data, manual_source):
        value = form_data.get(field_name, '').strip() if isinstance(form_data.get(field_name), str) else form_data.get(field_name)
        if value is not None and str(value).strip():
            logger.debug(f"Creating manual metadata entry for {field_name}: {value}")
            return BookMetadata(
                book=book,
                field_name=field_name,
                field_value=str(value),
                source=manual_source,
                confidence=1.0,
                is_active=True  # Ensure it's active
            )
        return None

    @staticmethod
    def _handle_manual_genres(request, book, manual_source):
        manual_genres = request.POST.get('manual_genres', '').strip()
        genre_entries = []

        if manual_genres:
            logger.debug(f"Processing manual genres: {manual_genres}")
            genre_names = [g.strip() for g in manual_genres.split(',') if g.strip()]
            for genre_name in genre_names:
                genre, created = Genre.objects.get_or_create(name=genre_name)
                if created:
                    logger.debug(f"Created new genre: {genre}")

                # Use the new create_or_update_best method to handle duplicates
                book_genre = BookGenre.create_or_update_best(
                    book=book,
                    genre=genre,
                    source=manual_source,
                    confidence=1.0,
                    is_active=True
                )

                if book_genre:
                    logger.debug(f"Processed genre entry for: {genre_name}")

        return genre_entries


class CoverManager:
    """Handles cover upload, selection, and management."""

    @staticmethod
    def handle_cover_upload(request, book, uploaded_file):
        """Handle uploaded cover file and create BookCover entry."""
        try:
            import time
            import uuid

            # Create unique filename to avoid conflicts
            file_ext = uploaded_file.name.split('.')[-1].lower()
            timestamp = int(time.time())
            unique_id = str(uuid.uuid4())[:8]
            filename = f"book_{book.id}_cover_{timestamp}_{unique_id}.{file_ext}"

            upload_dir = os.path.join(settings.MEDIA_ROOT, 'cover_cache')
            os.makedirs(upload_dir, exist_ok=True)

            # Create relative path for storage
            relative_path = os.path.join('cover_cache', filename).replace('\\', '/')
            full_path = os.path.join(settings.MEDIA_ROOT, 'cover_cache', filename)

            # Save file
            with open(full_path, 'wb+') as destination:
                for chunk in uploaded_file.chunks():
                    destination.write(chunk)

            # Create media URL path (ensure forward slashes for URLs)
            cover_url = f"{settings.MEDIA_URL}{relative_path}"

            # Get or create manual source
            manual_source, _ = DataSource.objects.get_or_create(
                name=DataSource.MANUAL,
                defaults={'trust_level': 0.9}
            )

            # Check if this exact cover already exists
            existing_cover = BookCover.objects.filter(
                book=book,
                cover_path=cover_url,
                source=manual_source
            ).first()

            if existing_cover:
                # Update existing cover
                existing_cover.confidence = 1.0
                existing_cover.format = file_ext
                existing_cover.is_active = True
                existing_cover.save()
                logger.debug(f"Updated existing cover: {existing_cover}")
                cover_entry = existing_cover
            else:
                # Create new cover entry
                cover_entry = BookCover.objects.create(
                    book=book,
                    cover_path=cover_url,
                    source=manual_source,
                    confidence=1.0,
                    format=file_ext,
                    is_active=True
                )
                logger.debug(f"Created new cover: {cover_entry}")

            return {
                'success': True,
                'cover_path': cover_url,
                'cover_id': cover_entry.id,
                'filename': filename,
                'full_path': full_path
            }

        except Exception as e:
            logger.error(f"Error uploading cover for book {book.id}: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    @staticmethod
    def manage_cover_action(request, book_id):
        """Handle cover selection and removal via AJAX."""
        try:
            book = Book.objects.get(pk=book_id)
            data = json.loads(request.body)
            action = data.get("action")
            cover_path = data.get("cover_path")
            source_name = data.get("source")

            if not cover_path or not source_name:
                return JsonResponse({
                    "success": False,
                    "message": "Missing cover_path or source"
                }, status=400)

            normalized_source = source_name.strip().lower()

            # Handle original covers
            if normalized_source in ["original", "initial scan"]:
                return CoverManager._handle_original_cover(book, action)

            # Handle metadata-based covers
            return CoverManager._handle_metadata_cover(book, action, cover_path, source_name)

        except Book.DoesNotExist:
            return JsonResponse({"success": False, "message": "Book not found"}, status=404)
        except json.JSONDecodeError:
            return JsonResponse({"success": False, "message": "Invalid JSON"}, status=400)
        except Exception as e:
            logger.error(f"Error managing cover for book {book_id}: {e}")
            return JsonResponse({"success": False, "message": str(e)}, status=500)

    @staticmethod
    def _handle_original_cover(book, action):
        """Handle actions on original cover."""
        if action == "select":
            cover_path = book.primary_file.cover_path if book.primary_file else ''
            book.finalmetadata.final_cover_path = cover_path
            book.finalmetadata.final_cover_confidence = 0.96
            book.finalmetadata.save()
            return JsonResponse({
                "success": True,
                "message": "Original cover selected",
                "cover_path": cover_path
            })
        elif action == "remove":
            # Check if original cover is currently selected as final cover
            cover_path = book.primary_file.cover_path if book.primary_file else ''
            was_final_cover = book.finalmetadata.final_cover_path == cover_path

            if was_final_cover:
                # Find next best cover to use as fallback
                book.finalmetadata.update_final_cover()
                book.finalmetadata.save()

                return JsonResponse({
                    "success": True,
                    "message": "Original cover removed from selection, switched to next best cover",
                    "new_cover_path": book.finalmetadata.final_cover_path
                })
            else:
                return JsonResponse({
                    "success": False,
                    "message": "Original cover is not currently selected"
                }, status=400)

        return JsonResponse({"success": False, "message": "Invalid action for original cover"}, status=400)

    @staticmethod
    def _handle_metadata_cover(book, action, cover_path, source_name):
        """Handle actions on metadata-based covers."""
        try:
            source = DataSource.objects.get(name=source_name)
            cover = BookCover.objects.get(book=book, cover_path=cover_path, source=source)
        except DataSource.DoesNotExist:
            return JsonResponse({"success": False, "message": "Invalid source"}, status=400)
        except BookCover.DoesNotExist:
            return JsonResponse({"success": False, "message": "Cover not found"}, status=404)

        if action == "remove":
            if not cover.is_active:
                return JsonResponse({"success": False, "message": "Cover already inactive"}, status=400)

            # Check if this is the currently selected final cover
            was_final_cover = book.finalmetadata.final_cover_path == cover.cover_path

            cover.is_active = False
            cover.save()

            # Only update final cover if we removed the currently selected one
            if was_final_cover:
                book.finalmetadata.update_final_cover()
                book.finalmetadata.save()
                logger.debug(f"Removed final cover, updated to next best: {book.finalmetadata.final_cover_path}")

                return JsonResponse({
                    "success": True,
                    "message": "Cover deactivated, switched to next best cover",
                    "new_cover_path": book.finalmetadata.final_cover_path
                })

            return JsonResponse({"success": True, "message": "Cover deactivated"})

        elif action == "select":
            book.finalmetadata.final_cover_path = cover.cover_path
            book.finalmetadata.final_cover_confidence = cover.confidence
            book.finalmetadata.save()
            cover.is_active = True
            cover.save()
            return JsonResponse({
                "success": True,
                "message": "Cover selected",
                "cover_path": cover.cover_path
            })

        return JsonResponse({"success": False, "message": "Invalid action"}, status=400)


class GenreManager:
    """Handles genre selection and management."""

    @staticmethod
    def handle_genre_updates(request, book, form):
        """Handle genre selection and manual genre additions - IMPROVED VERSION."""
        try:
            selected_genres = request.POST.getlist('final_genres')
            manual_genres = request.POST.get('manual_genres', '').strip()

            # Process manual genres - add them to selected list
            if manual_genres:
                manual_genre_list = [g.strip() for g in manual_genres.split(',') if g.strip()]
                selected_genres.extend(manual_genre_list)
                logger.debug(f"Manual genres added: {manual_genre_list}")

            # Get manual source
            manual_source, _ = DataSource.objects.get_or_create(
                name=DataSource.MANUAL,
                defaults={'trust_level': 1.0}
            )

            # Get all currently active genres for this book to compare
            current_active_genres = set(
                BookGenre.objects.filter(book=book, is_active=True)
                                 .values_list('genre__name', flat=True)
            )

            selected_genre_names = set(selected_genres)

            # Deactivate genres that are no longer selected
            genres_to_deactivate = current_active_genres - selected_genre_names
            if genres_to_deactivate:
                deactivated_count = BookGenre.objects.filter(
                    book=book,
                    genre__name__in=genres_to_deactivate,
                    is_active=True
                ).update(is_active=False)
                logger.debug(f"Deactivated {deactivated_count} genres: {list(genres_to_deactivate)}")

            # Process each selected genre using the new create_or_update_best method
            for genre_name in selected_genres:
                # Create or get genre
                genre, created = Genre.objects.get_or_create(name=genre_name)
                if created:
                    logger.debug(f"Created new genre: {genre_name}")

                # Use the new method to handle potential duplicates intelligently
                book_genre = BookGenre.create_or_update_best(
                    book=book,
                    genre=genre,
                    source=manual_source,
                    confidence=1.0,
                    is_active=True
                )

                if book_genre:
                    logger.debug(f"Processed BookGenre relationship: {genre_name}")

            logger.debug(f"Successfully processed {len(selected_genres)} genres for book {book.id}")

        except Exception as e:
            logger.error(f"Error handling genre updates for book {book.id}: {e}")
            raise e  # Re-raise to be handled by calling code


class MetadataResetter:
    """Handles resetting metadata to best available values."""

    @staticmethod
    def reset_to_best_values(book, final_metadata):
        """Reset final metadata to most confident available values."""
        # Reset title
        best_title = book.titles.filter(is_active=True).order_by('-confidence').first()
        if best_title:
            final_metadata.final_title = best_title.title

        # Reset author
        best_author = book.author_relationships.filter(is_active=True).order_by('-confidence', '-is_main_author').first()
        if best_author:
            final_metadata.final_author = best_author.author.name

        # Reset series
        best_series = book.series_relationships.filter(is_active=True).order_by('-confidence').first()
        if best_series:
            final_metadata.final_series = best_series.series.name
            final_metadata.final_series_number = str(best_series.series_number) if best_series.series_number else ''

        # Reset publisher
        best_publisher = book.publisher_relationships.filter(is_active=True).order_by('-confidence').first()
        if best_publisher:
            final_metadata.final_publisher = best_publisher.publisher.name

        # Reset additional metadata fields
        for field_name in ['isbn', 'language', 'publication_year', 'description']:
            best_meta = book.metadata.filter(field_name=field_name, is_active=True).order_by('-confidence').first()
            if best_meta:
                setattr(final_metadata, field_name, best_meta.field_value)

        # Reset cover
        best_cover = book.covers.filter(is_active=True).order_by('-confidence', '-is_high_resolution').first()
        if best_cover:
            final_metadata.final_cover_path = best_cover.cover_path
        elif book.primary_file and book.primary_file.cover_path:
            final_metadata.final_cover_path = book.primary_file.cover_path

        final_metadata.save()


class BookStatusManager:
    """Handles book status updates."""

    @staticmethod
    def update_book_status(request, book_id):
        """AJAX view to update book status flags."""
        try:
            book = get_object_or_404(Book, id=book_id)
            final_metadata = getattr(book, "finalmetadata", None)

            if 'is_reviewed' in request.POST and final_metadata:
                final_metadata.is_reviewed = request.POST.get('is_reviewed') == 'true'
                final_metadata.save()

            if 'is_duplicate' in request.POST:
                book.is_duplicate = request.POST.get('is_duplicate') == 'true'
                book.save()

            return JsonResponse({
                'success': True,
                'message': 'Book status updated successfully'
            })

        except Exception as e:
            logger.error(f"Error updating book status for {book_id}: {e}")
            return JsonResponse({'success': False, 'error': str(e)})


class MetadataConflictAnalyzer:
    """Analyzes and reports metadata conflicts."""

    @staticmethod
    def get_metadata_conflicts(request, book_id):
        """AJAX view to get metadata conflicts for a book."""
        try:
            book = get_object_or_404(Book, id=book_id)

            conflicts = {
                'titles': MetadataConflictAnalyzer._get_title_conflicts(book),
                'authors': MetadataConflictAnalyzer._get_author_conflicts(book),
                'series': MetadataConflictAnalyzer._get_series_conflicts(book),
                'genres': MetadataConflictAnalyzer._get_genre_conflicts(book)
            }

            return JsonResponse({'success': True, 'conflicts': conflicts})

        except Exception as e:
            logger.error(f"Error getting conflicts for book {book_id}: {e}")
            return JsonResponse({'success': False, 'error': str(e)})

    @staticmethod
    def _get_title_conflicts(book):
        """Get title conflicts."""
        conflicts = []
        titles = book.titles.filter(is_active=True).order_by('-confidence')
        if titles.count() > 1:
            for title in titles:
                conflicts.append({
                    'value': title.title,
                    'source': getattr(title.source, 'name', str(title.source)),
                    'confidence': title.confidence
                })
        return conflicts

    @staticmethod
    def _get_author_conflicts(book):
        """Get author conflicts."""
        conflicts = []
        authors = book.author_relationships.filter(is_active=True).order_by('-confidence')
        if authors.count() > 1:
            for author in authors:
                conflicts.append({
                    'value': author.author.name,
                    'source': getattr(author.source, 'name', str(author.source)),
                    'confidence': author.confidence,
                    'is_main': author.is_main_author
                })
        return conflicts

    @staticmethod
    def _get_series_conflicts(book):
        """Get series conflicts."""
        conflicts = []
        series = book.series_relationships.filter(is_active=True).order_by('-confidence')
        if series.count() > 1:
            for s in series:
                value = f"{s.series.name} #{s.series_number}" if s.series_number else s.series.name
                conflicts.append({
                    'value': value,
                    'source': getattr(s.source, 'name', str(s.source)),
                    'confidence': s.confidence
                })
        return conflicts

    @staticmethod
    def _get_genre_conflicts(book):
        """Get genre conflicts."""
        conflicts = []
        genres = book.genre_relationships.filter(is_active=True).order_by('-confidence')
        unique_genres = {}

        for genre in genres:
            if genre.genre.name not in unique_genres:
                unique_genres[genre.genre.name] = []
            unique_genres[genre.genre.name].append({
                'source': getattr(genre.source, 'name', str(genre.source)),
                'confidence': genre.confidence
            })

        for genre_name, sources in unique_genres.items():
            if len(sources) > 1:
                conflicts.append({
                    'value': genre_name,
                    'sources': sources
                })
        return conflicts


class MetadataRemover:
    """Handles removal of metadata entries."""

    MODEL_MAP = {
        'title': BookTitle,
        'author': BookAuthor,
        'cover': BookCover,
        'series': BookSeries,
        'publisher': BookPublisher,
        'metadata': BookMetadata,
        'genre': BookGenre,
    }

    @staticmethod
    def remove_metadata(request, book_id):
        """Remove metadata entry via AJAX."""
        try:
            payload = json.loads(request.body)
            metadata_type = payload.get('type')
            metadata_id = payload.get('id')

            if not metadata_type or not metadata_id:
                return JsonResponse({'error': 'Missing type or ID'}, status=400)

            model = MetadataRemover.MODEL_MAP.get(metadata_type)
            if not model:
                return JsonResponse({'error': 'Invalid metadata type'}, status=400)

            book = Book.objects.get(pk=book_id)
            instance = model.objects.get(pk=metadata_id, book=book)

            if not instance.is_active:
                return JsonResponse({'error': 'Metadata already inactive'}, status=400)

            instance.is_active = False
            instance.save()

            return JsonResponse({'status': 'success', 'message': 'Metadata removed'})

        except Book.DoesNotExist:
            return JsonResponse({'error': 'Book not found'}, status=404)
        except model.DoesNotExist:
            return JsonResponse({'error': f'{metadata_type} metadata not found'}, status=404)
        except Exception as e:
            logger.error(f"Error removing metadata for book {book_id}: {e}")
            return JsonResponse({'error': str(e)}, status=500)
