"""
Tests for view utilities and mixins
"""
from django.test import TestCase, RequestFactory
from django.http import JsonResponse
from django.contrib.auth.models import User
from books.models import Book, ScanFolder, FinalMetadata
from books.view_utils import (
    StandardAjaxResponseMixin, StandardPaginationMixin,
    BookFilterMixin, standard_ajax_handler
)
from books.mixins import BookAjaxViewMixin, ajax_book_operation
import json


class StandardAjaxResponseMixinTests(TestCase):
    """Test StandardAjaxResponseMixin functionality"""

    def setUp(self):
        self.mixin = StandardAjaxResponseMixin()

    def test_success_response(self):
        """Test success response generation"""
        response = self.mixin.success_response("Operation completed")

        self.assertIsInstance(response, JsonResponse)
        data = json.loads(response.content)
        self.assertTrue(data['success'])
        self.assertEqual(data['message'], "Operation completed")

    def test_success_response_with_extra_data(self):
        """Test success response with additional data"""
        response = self.mixin.success_response(
            "Operation completed",
            book_id=123,
            count=5
        )

        self.assertIsInstance(response, JsonResponse)
        data = json.loads(response.content)
        self.assertTrue(data['success'])
        self.assertEqual(data['message'], "Operation completed")
        self.assertEqual(data['book_id'], 123)
        self.assertEqual(data['count'], 5)

    def test_error_response(self):
        """Test error response generation"""
        response = self.mixin.error_response("Something went wrong")

        self.assertIsInstance(response, JsonResponse)
        data = json.loads(response.content)
        self.assertFalse(data['success'])
        self.assertEqual(data['error'], "Something went wrong")
        self.assertEqual(response.status_code, 400)

    def test_error_response_custom_status(self):
        """Test error response with custom status code"""
        response = self.mixin.error_response("Not found", status=404)

        self.assertIsInstance(response, JsonResponse)
        self.assertEqual(response.status_code, 404)

    def test_not_found_response(self):
        """Test not found response generation"""
        response = self.mixin.not_found_response("Book")

        self.assertIsInstance(response, JsonResponse)
        data = json.loads(response.content)
        self.assertFalse(data['success'])
        self.assertEqual(data['error'], "Book not found")
        self.assertEqual(response.status_code, 404)

    def test_validation_error_response(self):
        """Test validation error response generation"""
        errors = {'field1': ['This field is required'], 'field2': ['Invalid value']}
        response = self.mixin.validation_error_response(errors)

        self.assertIsInstance(response, JsonResponse)
        data = json.loads(response.content)
        self.assertFalse(data['success'])
        self.assertEqual(data['error'], "Validation failed")
        self.assertEqual(data['errors'], errors)
        self.assertEqual(response.status_code, 400)


class BookAjaxViewMixinTests(TestCase):
    """Test BookAjaxViewMixin functionality"""

    def setUp(self):
        self.mixin = BookAjaxViewMixin()
        self.scan_folder = ScanFolder.objects.create(
            name='Test Folder',
            path='/test/folder',
            language='en'
        )
        self.book = Book.objects.create(
            file_path='/test/folder/book.epub',
            file_format='epub',
            file_size=1024,
            scan_folder=self.scan_folder
        )

    def test_get_book_or_404_success(self):
        """Test successful book retrieval"""
        book = self.mixin.get_book_or_404(self.book.id)
        self.assertEqual(book, self.book)

    def test_get_book_or_404_not_found(self):
        """Test book not found scenario"""
        book = self.mixin.get_book_or_404(99999)
        self.assertIsNone(book)

    def test_handle_book_operation_success(self):
        """Test successful book operation handling"""
        def mock_operation(book):
            return {'message': f'Processed book {book.id}', 'status': 'completed'}

        result = self.mixin.handle_book_operation(self.book.id, mock_operation)

        # The result should be a JsonResponse or dict depending on implementation
        if isinstance(result, JsonResponse):
            data = json.loads(result.content)
            self.assertTrue(data['success'])
            self.assertEqual(data['message'], f'Processed book {self.book.id}')
        else:
            self.assertTrue(result['success'])
            self.assertEqual(result['message'], f'Processed book {self.book.id}')

    def test_handle_book_operation_book_not_found(self):
        """Test book operation with non-existent book"""
        def mock_operation(book):
            return {'message': 'This should not be called'}

        result = self.mixin.handle_book_operation(99999, mock_operation)

        self.assertIsInstance(result, JsonResponse)
        data = json.loads(result.content)
        self.assertFalse(data['success'])
        self.assertEqual(data['error'], "Book not found")

    def test_handle_book_operation_exception(self):
        """Test book operation with exception"""
        def mock_operation(book):
            raise ValueError("Operation failed")

        result = self.mixin.handle_book_operation(self.book.id, mock_operation)

        self.assertIsInstance(result, JsonResponse)
        data = json.loads(result.content)
        self.assertFalse(data['success'])
        self.assertEqual(data['error'], "Operation failed")

    def test_handle_book_operation_json_response_return(self):
        """Test book operation that returns JsonResponse directly"""
        def mock_operation(book):
            return JsonResponse({'custom': 'response'})

        result = self.mixin.handle_book_operation(self.book.id, mock_operation)

        self.assertIsInstance(result, JsonResponse)
        data = json.loads(result.content)
        self.assertEqual(data['custom'], 'response')


class StandardPaginationMixinTests(TestCase):
    """Test StandardPaginationMixin functionality"""

    def setUp(self):
        self.mixin = StandardPaginationMixin()
        # Create test scan folder and books for pagination
        self.scan_folder = ScanFolder.objects.create(
            name='Test Folder',
            path='/test/folder',
            language='en'
        )

        # Create more books than the default page size
        for i in range(50):
            Book.objects.create(
                file_path=f'/test/folder/book{i}.epub',
                file_format='epub',
                file_size=1024,
                scan_folder=self.scan_folder
            )

    def test_get_paginated_context_first_page(self):
        """Test pagination context for first page"""
        queryset = Book.objects.all()
        context = self.mixin.get_paginated_context(queryset, 1)

        self.assertIn('page_obj', context)
        self.assertIn('paginator', context)
        self.assertIn('is_paginated', context)

        self.assertEqual(context['page_obj'].number, 1)
        self.assertTrue(context['is_paginated'])
        self.assertEqual(len(context['page_obj']), 25)  # Default page size

    def test_get_paginated_context_last_page(self):
        """Test pagination context for last page"""
        queryset = Book.objects.all()
        context = self.mixin.get_paginated_context(queryset, 2)

        self.assertEqual(context['page_obj'].number, 2)
        self.assertEqual(len(context['page_obj']), 25)  # Remaining books

    def test_get_paginated_context_invalid_page(self):
        """Test pagination with invalid page number"""
        queryset = Book.objects.all()
        context = self.mixin.get_paginated_context(queryset, 'invalid')

        # Should default to page 1
        self.assertEqual(context['page_obj'].number, 1)

    def test_get_paginated_context_empty_page(self):
        """Test pagination with page number too high"""
        queryset = Book.objects.all()
        context = self.mixin.get_paginated_context(queryset, 999)

        # Should default to last page
        self.assertEqual(context['page_obj'].number, context['paginator'].num_pages)

    def test_get_paginated_context_small_queryset(self):
        """Test pagination with queryset smaller than page size"""
        # Delete most books to have less than one page
        all_books = list(Book.objects.all())
        books_to_delete = all_books[10:]
        for book in books_to_delete:
            book.delete()

        queryset = Book.objects.all()
        context = self.mixin.get_paginated_context(queryset, 1)

        self.assertFalse(context['is_paginated'])
        self.assertEqual(context['paginator'].num_pages, 1)


class BookFilterMixinTests(TestCase):
    """Test BookFilterMixin functionality"""

    def setUp(self):
        self.mixin = BookFilterMixin()
        self.scan_folder = ScanFolder.objects.create(
            name='Test Folder',
            path='/test/folder',
            language='en'
        )

        # Create test books with different attributes
        self.book1 = Book.objects.create(
            file_path='/test/folder/book1.epub',
            file_format='epub',
            file_size=1024,
            scan_folder=self.scan_folder
        )

        self.book2 = Book.objects.create(
            file_path='/test/folder/book2.pdf',
            file_format='pdf',
            file_size=2048,
            scan_folder=self.scan_folder
        )

        # Create FinalMetadata for books
        self.metadata1 = FinalMetadata.objects.create(
            book=self.book1,
            final_title="Test Book One",
            final_author="Author One",
            language='en',
            is_reviewed=True
        )
        # Set confidence after creation to avoid auto-calculation
        FinalMetadata.objects.filter(book=self.book1).update(overall_confidence=0.9)

        self.metadata2 = FinalMetadata.objects.create(
            book=self.book2,
            final_title="Test Book Two",
            final_author="Author Two",
            language='fr',
            is_reviewed=False
        )
        # Set fields after creation to avoid auto-update override
        FinalMetadata.objects.filter(book=self.book2).update(
            overall_confidence=0.3,
            final_title="Test Book Two",
            final_author="Author Two",
            language='fr'
        )

        # Refresh the objects
        self.metadata1.refresh_from_db()
        self.metadata2.refresh_from_db()

    def test_apply_search_filters_no_filters(self):
        """Test applying filters with no filter parameters"""
        queryset = Book.objects.all()
        filtered = self.mixin.apply_search_filters(queryset, {})

        self.assertEqual(filtered.count(), 2)

    def test_apply_search_filters_by_title(self):
        """Test filtering by title search"""
        queryset = Book.objects.all()
        search_params = {'search_query': 'Book One'}
        filtered = self.mixin.apply_search_filters(queryset, search_params)

        self.assertEqual(filtered.count(), 1)
        self.assertEqual(filtered.first(), self.book1)

    def test_apply_search_filters_by_author(self):
        """Test filtering by author search"""
        queryset = Book.objects.all()
        search_params = {'search_query': 'Author Two'}
        filtered = self.mixin.apply_search_filters(queryset, search_params)

        self.assertEqual(filtered.count(), 1)
        self.assertEqual(filtered.first(), self.book2)

    def test_apply_search_filters_by_language(self):
        """Test filtering by language"""
        queryset = Book.objects.all()
        search_params = {'language': 'en'}
        filtered = self.mixin.apply_search_filters(queryset, search_params)

        self.assertEqual(filtered.count(), 1)
        self.assertEqual(filtered.first(), self.book1)

    def test_apply_search_filters_by_file_format(self):
        """Test filtering by file format"""
        queryset = Book.objects.all()
        search_params = {'file_format': 'pdf'}
        filtered = self.mixin.apply_search_filters(queryset, search_params)

        self.assertEqual(filtered.count(), 1)
        self.assertEqual(filtered.first(), self.book2)

    def test_apply_search_filters_by_confidence_high(self):
        """Test filtering by high confidence level"""
        queryset = Book.objects.all()
        search_params = {'confidence_level': 'high'}
        filtered = self.mixin.apply_search_filters(queryset, search_params)

        self.assertEqual(filtered.count(), 1)
        self.assertEqual(filtered.first(), self.book1)

    def test_apply_search_filters_by_confidence_low(self):
        """Test filtering by low confidence level"""
        queryset = Book.objects.all()
        search_params = {'confidence_level': 'low'}
        filtered = self.mixin.apply_search_filters(queryset, search_params)

        self.assertEqual(filtered.count(), 1)
        self.assertEqual(filtered.first(), self.book2)

    def test_apply_search_filters_by_review_status_true(self):
        """Test filtering by reviewed books"""
        queryset = Book.objects.all()
        search_params = {'is_reviewed': 'true'}
        filtered = self.mixin.apply_search_filters(queryset, search_params)

        self.assertEqual(filtered.count(), 1)
        self.assertEqual(filtered.first(), self.book1)

    def test_apply_search_filters_by_review_status_false(self):
        """Test filtering by unreviewed books"""
        queryset = Book.objects.all()
        search_params = {'is_reviewed': 'false'}
        filtered = self.mixin.apply_search_filters(queryset, search_params)

        self.assertEqual(filtered.count(), 1)
        self.assertEqual(filtered.first(), self.book2)

    def test_apply_search_filters_combined(self):
        """Test filtering with multiple parameters"""
        queryset = Book.objects.all()
        search_params = {
            'file_format': 'epub',
            'language': 'en',
            'confidence_level': 'high'
        }
        filtered = self.mixin.apply_search_filters(queryset, search_params)

        self.assertEqual(filtered.count(), 1)
        self.assertEqual(filtered.first(), self.book1)


class AjaxDecoratorTests(TestCase):
    """Test AJAX decorators"""

    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.scan_folder = ScanFolder.objects.create(
            name='Test Folder',
            path='/test/folder',
            language='en'
        )
        self.book = Book.objects.create(
            file_path='/test/folder/book.epub',
            file_format='epub',
            file_size=1024,
            scan_folder=self.scan_folder
        )

    def test_ajax_book_operation_decorator_success(self):
        """Test ajax_book_operation decorator with successful operation"""
        @ajax_book_operation
        def test_operation(book, request):
            return {'message': f'Processed {book.file_path}'}

        request = self.factory.post('/test/')
        response = test_operation(request, self.book.id)

        self.assertIsInstance(response, JsonResponse)
        data = json.loads(response.content)
        self.assertTrue(data['success'])

    def test_ajax_book_operation_decorator_book_not_found(self):
        """Test ajax_book_operation decorator with non-existent book"""
        @ajax_book_operation
        def test_operation(book, request):
            return {'message': 'Should not reach here'}

        request = self.factory.post('/test/')
        response = test_operation(request, 99999)

        self.assertIsInstance(response, JsonResponse)
        data = json.loads(response.content)
        self.assertFalse(data['success'])
        self.assertEqual(data['error'], 'Book not found')

    def test_standard_ajax_handler_success(self):
        """Test standard_ajax_handler decorator with successful function"""
        @standard_ajax_handler
        def test_view(request):
            return {'message': 'Success', 'data': 'test'}

        request = self.factory.post('/test/')
        response = test_view(request)

        self.assertIsInstance(response, JsonResponse)
        data = json.loads(response.content)
        self.assertEqual(data['message'], 'Success')
        self.assertEqual(data['data'], 'test')

    def test_standard_ajax_handler_json_parsing(self):
        """Test standard_ajax_handler decorator with JSON request body"""
        @standard_ajax_handler
        def test_view(request):
            return {'received': request.json}

        request_data = {'test': 'data'}
        request = self.factory.post(
            '/test/',
            data=json.dumps(request_data),
            content_type='application/json'
        )
        response = test_view(request)

        self.assertIsInstance(response, JsonResponse)
        data = json.loads(response.content)
        self.assertEqual(data['received'], request_data)

    def test_standard_ajax_handler_invalid_json(self):
        """Test standard_ajax_handler decorator with invalid JSON"""
        @standard_ajax_handler
        def test_view(request):
            return {'message': 'Should not reach here'}

        request = self.factory.post(
            '/test/',
            data='invalid json',
            content_type='application/json'
        )
        response = test_view(request)

        self.assertIsInstance(response, JsonResponse)
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.content)
        self.assertFalse(data['success'])
        self.assertEqual(data['error'], 'Invalid JSON data')

    def test_standard_ajax_handler_exception(self):
        """Test standard_ajax_handler decorator with exception"""
        @standard_ajax_handler
        def test_view(request):
            raise ValueError("Test exception")

        request = self.factory.post('/test/')
        response = test_view(request)

        self.assertIsInstance(response, JsonResponse)
        self.assertEqual(response.status_code, 500)
        data = json.loads(response.content)
        self.assertFalse(data['success'])
        self.assertEqual(data['error'], 'An error occurred while processing your request')
