"""Comprehensive tests for books.forms module.

Tests for form validation, widget configuration, cleaning methods, and edge cases.
Focuses on achieving higher coverage for the forms module.
"""
import os
import django
from django.test import TestCase
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth.models import User
from unittest.mock import patch
import tempfile

from books.forms import (
    UserRegisterForm, ScanFolderForm, BookSearchForm, MetadataReviewForm,
    BookStatusForm, BookEditForm, BookCoverForm, BulkUpdateForm,
    AdvancedSearchForm, UserProfileForm
)
from books.models import (
    ScanFolder, Book, FinalMetadata, UserProfile
)

# Must set Django settings before importing Django models
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ebook_manager.settings')
django.setup()


class UserRegisterFormTests(TestCase):
    """Test UserRegisterForm functionality"""

    def test_user_register_form_valid(self):
        """Test UserRegisterForm with valid data"""
        form_data = {
            'username': 'testuser',
            'email': 'test@example.com',
            'password1': 'testpassword123',
            'password2': 'testpassword123'
        }
        form = UserRegisterForm(data=form_data)
        self.assertTrue(form.is_valid())

    def test_user_register_form_password_mismatch(self):
        """Test UserRegisterForm with password mismatch"""
        form_data = {
            'username': 'testuser',
            'email': 'test@example.com',
            'password1': 'testpassword123',
            'password2': 'differentpassword'
        }
        form = UserRegisterForm(data=form_data)
        self.assertFalse(form.is_valid())

    def test_user_register_form_invalid_email(self):
        """Test UserRegisterForm with invalid email"""
        form_data = {
            'username': 'testuser',
            'email': 'invalid-email',
            'password1': 'testpassword123',
            'password2': 'testpassword123'
        }
        form = UserRegisterForm(data=form_data)
        self.assertFalse(form.is_valid())

    def test_user_register_form_empty_data(self):
        """Test UserRegisterForm with empty data"""
        form = UserRegisterForm(data={})
        self.assertFalse(form.is_valid())
        self.assertIn('username', form.errors)
        self.assertIn('email', form.errors)
        self.assertIn('password1', form.errors)
        self.assertIn('password2', form.errors)


class ScanFolderFormTests(TestCase):
    """Test ScanFolderForm functionality"""

    def setUp(self):
        # Create a temporary directory for testing
        self.temp_dir = tempfile.mkdtemp()

    @patch('os.path.exists')
    @patch('os.path.isdir')
    def test_scan_folder_form_valid(self, mock_isdir, mock_exists):
        """Test ScanFolderForm with valid data"""
        mock_exists.return_value = True
        mock_isdir.return_value = True

        form_data = {
            'name': 'Test Folder',
            'path': '/test/path',
            'content_type': 'ebooks',
            'language': 'en',
            'is_active': True
        }
        form = ScanFolderForm(data=form_data)
        self.assertTrue(form.is_valid())

    def test_scan_folder_form_empty_path(self):
        """Test ScanFolderForm with empty path"""
        form_data = {
            'name': 'Test Folder',
            'path': '',
            'content_type': 'ebooks',
            'language': 'en',
            'is_active': True
        }
        form = ScanFolderForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('path', form.errors)

    def test_scan_folder_form_whitespace_path(self):
        """Test ScanFolderForm with whitespace-only path"""
        form_data = {
            'name': 'Test Folder',
            'path': '   ',
            'content_type': 'ebooks',
            'language': 'en',
            'is_active': True
        }
        form = ScanFolderForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('path', form.errors)

    def test_scan_folder_form_accepts_any_path_string(self):
        """Test ScanFolderForm accepts any path string (no path validation in current form)"""
        form_data = {
            'name': 'Test Folder',
            'path': '/any/path/string',
            'content_type': 'ebooks',
            'language': 'en',
            'is_active': True
        }
        form = ScanFolderForm(data=form_data)
        self.assertTrue(form.is_valid())

    def test_scan_folder_form_accepts_file_paths(self):
        """Test ScanFolderForm accepts file paths (no directory validation in current form)"""
        form_data = {
            'name': 'Test Folder',
            'path': '/test/file.txt',
            'content_type': 'ebooks',
            'language': 'en',
            'is_active': True
        }
        form = ScanFolderForm(data=form_data)
        self.assertTrue(form.is_valid())

    @patch('os.path.exists')
    @patch('os.path.isdir')
    def test_scan_folder_form_path_cleaning(self, mock_isdir, mock_exists):
        """Test ScanFolderForm path cleaning (whitespace removal)"""
        mock_exists.return_value = True
        mock_isdir.return_value = True

        form_data = {
            'name': 'Test Folder',
            'path': '  /test/path  ',
            'content_type': 'ebooks',
            'language': 'en',
            'is_active': True
        }
        form = ScanFolderForm(data=form_data)
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data['path'], '/test/path')


class BookSearchFormTests(TestCase):
    """Test BookSearchForm functionality"""

    def test_book_search_form_all_fields(self):
        """Test BookSearchForm with all fields filled"""
        form_data = {
            'search_query': 'test book',
            'language': 'en',
            'file_format': 'epub',
            'has_placeholder': 'false',
            'is_reviewed': 'true',
            'confidence_level': 'high',
            'has_cover': 'true'
        }
        form = BookSearchForm(data=form_data)
        self.assertTrue(form.is_valid())

    def test_book_search_form_empty_optional_fields(self):
        """Test BookSearchForm with empty optional fields"""
        form_data = {
            'search_query': '',
            'language': '',
            'file_format': '',
            'has_placeholder': '',
            'is_reviewed': '',
            'confidence_level': '',
            'has_cover': ''
        }
        form = BookSearchForm(data=form_data)
        self.assertTrue(form.is_valid())

    def test_book_search_form_no_data(self):
        """Test BookSearchForm with no data"""
        form = BookSearchForm(data={})
        self.assertTrue(form.is_valid())  # All fields are optional

    def test_book_search_form_widget_attributes(self):
        """Test BookSearchForm widget attributes"""
        form = BookSearchForm()
        search_widget = form.fields['search_query'].widget
        self.assertEqual(search_widget.attrs['placeholder'], 'Search books, authors, series...')


class MetadataReviewFormTests(TestCase):
    """Test MetadataReviewForm functionality"""

    def setUp(self):
        self.scan_folder = ScanFolder.objects.create(path='/test/path')
        self.book = Book.objects.create(
            file_path='/test/path/test_book.epub',
            file_size=1000,
            file_format='epub',
            scan_folder=self.scan_folder
        )
        self.final_metadata = FinalMetadata.objects.create(
            book=self.book,
            final_title='Test Title',
            final_author='Test Author'
        )

    def test_metadata_review_form_valid(self):
        """Test MetadataReviewForm with valid data"""
        form_data = {
            'final_title': 'Updated Title',
            'final_author': 'Updated Author',
            'final_series': 'Test Series',
            'final_series_number': '1',
            'final_publisher': 'Test Publisher',
            'language': 'en',
            'isbn': '9780123456789',
            'publication_year': 2023,
            'description': 'Test description',
            'is_reviewed': True,
            'manual_genres': 'Fantasy, Science Fiction'
        }
        form = MetadataReviewForm(data=form_data, instance=self.final_metadata, book=self.book)
        self.assertTrue(form.is_valid())

    def test_metadata_review_form_required_fields(self):
        """Test MetadataReviewForm required fields validation"""
        form_data = {
            'final_title': '',
            'final_author': '',
        }
        form = MetadataReviewForm(data=form_data, instance=self.final_metadata, book=self.book)
        self.assertFalse(form.is_valid())
        self.assertIn('final_title', form.errors)
        self.assertIn('final_author', form.errors)

    def test_metadata_review_form_year_validation(self):
        """Test MetadataReviewForm publication year validation"""
        form_data = {
            'final_title': 'Valid Title',
            'final_author': 'Valid Author',
            'publication_year': 999,  # Too old
        }
        form = MetadataReviewForm(data=form_data, instance=self.final_metadata, book=self.book)
        self.assertFalse(form.is_valid())
        self.assertIn('publication_year', form.errors)

    def test_metadata_review_form_isbn_validation(self):
        """Test MetadataReviewForm ISBN validation"""
        form_data = {
            'final_title': 'Valid Title',
            'final_author': 'Valid Author',
            'isbn': '123',  # Invalid ISBN
        }
        form = MetadataReviewForm(data=form_data, instance=self.final_metadata, book=self.book)
        self.assertFalse(form.is_valid())
        self.assertIn('isbn', form.errors)

    def test_metadata_review_form_series_number_validation(self):
        """Test MetadataReviewForm series number validation"""
        form_data = {
            'final_title': 'Valid Title',
            'final_author': 'Valid Author',
            'final_series_number': 'a' * 25,  # Too long
        }
        form = MetadataReviewForm(data=form_data, instance=self.final_metadata, book=self.book)
        self.assertFalse(form.is_valid())
        self.assertIn('final_series_number', form.errors)

    def test_metadata_review_form_manual_genres_cleaning(self):
        """Test MetadataReviewForm manual genres cleaning"""
        form_data = {
            'final_title': 'Valid Title',
            'final_author': 'Valid Author',
            'manual_genres': '  Genre1  ,  Genre2  ,  ,  Genre3  ',
        }
        form = MetadataReviewForm(data=form_data, instance=self.final_metadata, book=self.book)
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data['manual_genres'], 'Genre1, Genre2, Genre3')

    def test_metadata_review_form_cover_upload(self):
        """Test MetadataReviewForm cover upload field"""
        # Create a simple 1x1 pixel image file (minimal valid JPEG)
        from PIL import Image
        import io

        # Create a 1x1 pixel image
        img = Image.new('RGB', (1, 1), color='red')
        img_io = io.BytesIO()
        img.save(img_io, format='JPEG')
        img_io.seek(0)

        uploaded_file = SimpleUploadedFile(
            'test_cover.jpg',
            img_io.read(),
            content_type='image/jpeg'
        )

        form_data = {
            'final_title': 'Valid Title',
            'final_author': 'Valid Author',
        }
        file_data = {
            'new_cover_upload': uploaded_file
        }
        form = MetadataReviewForm(
            data=form_data,
            files=file_data,
            instance=self.final_metadata,
            book=self.book
        )
        self.assertTrue(form.is_valid())

    def test_metadata_review_form_initialization(self):
        """Test MetadataReviewForm initialization with book"""
        form = MetadataReviewForm(instance=self.final_metadata, book=self.book)

        # Check that language field has proper choices
        language_choices = form.fields['language'].widget.choices
        self.assertIn(('', 'Select language'), language_choices)
        self.assertIn(('en', 'English'), language_choices)


class BookStatusFormTests(TestCase):
    """Test BookStatusForm functionality"""

    def setUp(self):
        self.scan_folder = ScanFolder.objects.create(path='/test/path')
        self.book = Book.objects.create(
            file_path='/test/path/test_book.epub',
            file_size=1000,
            file_format='epub',
            scan_folder=self.scan_folder
        )

    def test_book_status_form_valid(self):
        """Test BookStatusForm with valid data"""
        form_data = {'is_duplicate': True}
        form = BookStatusForm(data=form_data, instance=self.book)
        self.assertTrue(form.is_valid())

    def test_book_status_form_false_value(self):
        """Test BookStatusForm with false value"""
        form_data = {'is_duplicate': False}
        form = BookStatusForm(data=form_data, instance=self.book)
        self.assertTrue(form.is_valid())


class BookEditFormTests(TestCase):
    """Test BookEditForm functionality"""

    def setUp(self):
        self.scan_folder = ScanFolder.objects.create(path='/test/path')
        self.book = Book.objects.create(
            file_path='/test/path/test_book.epub',
            file_size=1000,
            file_format='epub',
            scan_folder=self.scan_folder
        )

    def test_book_edit_form_valid(self):
        """Test BookEditForm with valid data"""
        form_data = {
            'file_format': 'pdf',
            'cover_path': '/new/cover/path.jpg',
            'opf_path': '/new/opf/path.opf',
            'is_placeholder': True,
            'is_duplicate': False
        }
        form = BookEditForm(data=form_data, instance=self.book)
        self.assertTrue(form.is_valid())

    def test_book_edit_form_widget_placeholders(self):
        """Test BookEditForm widget placeholders"""
        form = BookEditForm(instance=self.book)

        cover_widget = form.fields['cover_path'].widget
        opf_widget = form.fields['opf_path'].widget

        self.assertEqual(cover_widget.attrs['placeholder'], 'Path to cover image')
        self.assertEqual(opf_widget.attrs['placeholder'], 'Path to .opf metadata file')


class BookCoverFormTests(TestCase):
    """Test BookCoverForm functionality"""

    def test_book_cover_form_valid(self):
        """Test BookCoverForm with valid data"""
        form_data = {
            'cover_path': '/path/to/cover.jpg',
            'confidence': 0.8,
            'width': 800,
            'height': 1200,
            'format': 'jpg'
        }
        form = BookCoverForm(data=form_data)
        self.assertTrue(form.is_valid())

    def test_book_cover_form_confidence_validation(self):
        """Test BookCoverForm confidence validation"""
        form_data = {
            'cover_path': '/path/to/cover.jpg',
            'confidence': 1.5,  # Invalid confidence
            'width': 800,
            'height': 1200,
            'format': 'jpg'
        }
        form = BookCoverForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('confidence', form.errors)

    def test_book_cover_form_negative_confidence(self):
        """Test BookCoverForm with negative confidence"""
        form_data = {
            'cover_path': '/path/to/cover.jpg',
            'confidence': -0.1,  # Invalid confidence
            'width': 800,
            'height': 1200,
            'format': 'jpg'
        }
        form = BookCoverForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('confidence', form.errors)

    def test_book_cover_form_invalid_confidence_string(self):
        """Test BookCoverForm with invalid confidence string"""
        form_data = {
            'cover_path': '/path/to/cover.jpg',
            'confidence': 'invalid',
            'width': 800,
            'height': 1200,
            'format': 'jpg'
        }
        form = BookCoverForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('confidence', form.errors)

    def test_book_cover_form_widget_configuration(self):
        """Test BookCoverForm widget configuration"""
        form = BookCoverForm()

        # Check widget attributes
        cover_path_widget = form.fields['cover_path'].widget
        confidence_widget = form.fields['confidence'].widget
        width_widget = form.fields['width'].widget

        self.assertEqual(cover_path_widget.attrs['placeholder'], 'Path to cover image or URL')
        self.assertEqual(confidence_widget.attrs['placeholder'], 'Confidence score')
        self.assertEqual(width_widget.attrs['placeholder'], 'Width in pixels')


class BulkUpdateFormTests(TestCase):
    """Test BulkUpdateForm functionality"""

    def test_bulk_update_form_valid(self):
        """Test BulkUpdateForm with valid data"""
        form_data = {
            'action': 'mark_reviewed',
            'selected_books': '1,2,3'
        }
        form = BulkUpdateForm(data=form_data)
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data['selected_books'], [1, 2, 3])

    def test_bulk_update_form_no_action(self):
        """Test BulkUpdateForm without action"""
        form_data = {
            'action': '',
            'selected_books': '1,2,3'
        }
        form = BulkUpdateForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('action', form.errors)

    def test_bulk_update_form_no_books_selected(self):
        """Test BulkUpdateForm without selected books"""
        form_data = {
            'action': 'mark_reviewed',
            'selected_books': ''
        }
        form = BulkUpdateForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('selected_books', form.errors)

    def test_bulk_update_form_invalid_book_ids(self):
        """Test BulkUpdateForm with invalid book IDs"""
        form_data = {
            'action': 'mark_reviewed',
            'selected_books': '1,invalid,3'
        }
        form = BulkUpdateForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('selected_books', form.errors)

    def test_bulk_update_form_book_ids_with_spaces(self):
        """Test BulkUpdateForm with book IDs containing spaces"""
        form_data = {
            'action': 'mark_reviewed',
            'selected_books': ' 1 , 2 , 3 '
        }
        form = BulkUpdateForm(data=form_data)
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data['selected_books'], [1, 2, 3])


class AdvancedSearchFormTests(TestCase):
    """Test AdvancedSearchForm functionality"""

    def test_advanced_search_form_all_fields(self):
        """Test AdvancedSearchForm with all fields"""
        form_data = {
            'title': 'Test Title',
            'author': 'Test Author',
            'series': 'Test Series',
            'isbn': '9780123456789',
            'publisher': 'Test Publisher',
            'publication_year_from': 2000,
            'publication_year_to': 2023,
            'language': 'en',
            'file_format': 'epub',
            'confidence_min': 0.3,
            'confidence_max': 0.9
        }
        form = AdvancedSearchForm(data=form_data)
        self.assertTrue(form.is_valid())

    def test_advanced_search_form_empty_fields(self):
        """Test AdvancedSearchForm with empty fields"""
        form_data = {}
        form = AdvancedSearchForm(data=form_data)
        self.assertTrue(form.is_valid())  # All fields are optional

    def test_advanced_search_form_invalid_year_range(self):
        """Test AdvancedSearchForm with invalid year range"""
        form_data = {
            'publication_year_from': 2023,
            'publication_year_to': 2000  # From year > To year
        }
        form = AdvancedSearchForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('__all__', form.errors)

    def test_advanced_search_form_invalid_confidence_range(self):
        """Test AdvancedSearchForm with invalid confidence range"""
        form_data = {
            'confidence_min': 0.8,
            'confidence_max': 0.3  # Min > Max
        }
        form = AdvancedSearchForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('__all__', form.errors)

    def test_advanced_search_form_invalid_from_year(self):
        """Test AdvancedSearchForm with invalid from year"""
        form_data = {
            'publication_year_from': 999  # Too old
        }
        form = AdvancedSearchForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('publication_year_from', form.errors)

    def test_advanced_search_form_invalid_to_year(self):
        """Test AdvancedSearchForm with invalid to year"""
        form_data = {
            'publication_year_to': 3000  # Too future
        }
        form = AdvancedSearchForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('publication_year_to', form.errors)

    def test_advanced_search_form_widget_placeholders(self):
        """Test AdvancedSearchForm widget placeholders"""
        form = AdvancedSearchForm()

        self.assertEqual(form.fields['title'].widget.attrs['placeholder'], 'Title contains...')
        self.assertEqual(form.fields['author'].widget.attrs['placeholder'], 'Author contains...')
        self.assertEqual(form.fields['isbn'].widget.attrs['placeholder'], 'ISBN')
        self.assertEqual(form.fields['publication_year_from'].widget.attrs['placeholder'], 'From year')
        self.assertEqual(form.fields['confidence_min'].widget.attrs['placeholder'], 'Min confidence')


class UserProfileFormTests(TestCase):
    """Test UserProfileForm functionality"""

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass'
        )

    def test_user_profile_form_valid(self):
        """Test UserProfileForm with valid data"""
        form_data = {
            'theme': 'darkly',
            'items_per_page': 25,
            'show_covers_in_list': False,
            'default_view_mode': 'grid',
            'share_reading_progress': True
        }
        form = UserProfileForm(data=form_data)
        self.assertTrue(form.is_valid())

    def test_user_profile_form_defaults(self):
        """Test UserProfileForm with default instance"""
        profile = UserProfile.objects.create(user=self.user)
        form = UserProfileForm(instance=profile)

        # Check that form fields have correct initial values
        self.assertEqual(form.initial.get('theme', profile.theme), 'flatly')
        self.assertEqual(form.initial.get('items_per_page', profile.items_per_page), 50)

    def test_user_profile_form_widget_attributes(self):
        """Test UserProfileForm widget attributes"""
        form = UserProfileForm()

        # Check theme widget attributes
        theme_widget = form.fields['theme'].widget
        self.assertEqual(theme_widget.attrs['class'], 'form-select')
        self.assertEqual(theme_widget.attrs['data-bs-toggle'], 'tooltip')

        # Check items_per_page widget attributes
        items_widget = form.fields['items_per_page'].widget
        self.assertEqual(items_widget.attrs['min'], '10')
        self.assertEqual(items_widget.attrs['max'], '200')
        self.assertEqual(items_widget.attrs['step'], '10')

    def test_user_profile_form_help_text(self):
        """Test UserProfileForm help text"""
        form = UserProfileForm()

        self.assertEqual(
            form.fields['theme'].help_text,
            'Choose your preferred visual theme'
        )
        self.assertEqual(
            form.fields['items_per_page'].help_text,
            'Number of books to display per page (10-200)'
        )


class FormIntegrationTests(TestCase):
    """Test form integration and edge cases"""

    def setUp(self):
        self.scan_folder = ScanFolder.objects.create(path='/test/path')
        self.book = Book.objects.create(
            file_path='/test/path/test_book.epub',
            file_size=1000,
            file_format='epub',
            scan_folder=self.scan_folder
        )

    def test_form_styling_inheritance(self):
        """Test that forms inherit proper styling from mixins"""
        form = MetadataReviewForm(book=self.book)

        # Check that styling was applied to form fields
        title_field = form.fields['final_title']
        self.assertEqual(title_field.widget.attrs['class'], 'form-control')
        self.assertTrue(title_field.widget.attrs.get('required'))

    def test_form_validation_chain(self):
        """Test form validation chain with mixin validators"""
        form_data = {
            'final_title': '   ',  # Whitespace only - should fail
            'final_author': 'Valid Author',
            'isbn': '123',  # Invalid ISBN
            'publication_year': 999  # Invalid year
        }

        final_metadata = FinalMetadata.objects.create(book=self.book)
        form = MetadataReviewForm(data=form_data, instance=final_metadata, book=self.book)

        self.assertFalse(form.is_valid())
        self.assertIn('final_title', form.errors)
        self.assertIn('isbn', form.errors)
        self.assertIn('publication_year', form.errors)

    def test_bulk_form_edge_cases(self):
        """Test bulk form edge cases"""
        # Test with single book ID
        form_data = {
            'action': 'mark_reviewed',
            'selected_books': '5'
        }
        form = BulkUpdateForm(data=form_data)
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data['selected_books'], [5])

        # Test with trailing comma
        form_data = {
            'action': 'mark_reviewed',
            'selected_books': '1,2,3,'
        }
        form = BulkUpdateForm(data=form_data)
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data['selected_books'], [1, 2, 3])

    def test_metadata_form_widget_generation(self):
        """Test metadata form widget generation from mixin"""
        form = MetadataReviewForm(book=self.book)
        widgets = form.get_standard_metadata_widgets()

        # Test specific widget types
        self.assertIn('final_title', widgets)
        self.assertIn('publication_year', widgets)
        self.assertIn('description', widgets)

        # Check that publication_year has proper range constraints
        year_widget = widgets['publication_year']
        self.assertEqual(year_widget.attrs['min'], '1000')
        self.assertEqual(year_widget.attrs['max'], '2030')

    def test_form_error_messages(self):
        """Test form error messages for required fields"""
        # Test ScanFolderForm required field validation
        form_data = {
            'name': '',  # Required field left empty
            'path': '/test/path',
            'content_type': 'ebooks',
            'language': 'en',
            'is_active': True
        }

        form = ScanFolderForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('name', form.errors)

    def test_form_field_requirements(self):
        """Test form field requirements"""
        # Test that required fields are properly marked
        metadata_form = MetadataReviewForm(book=self.book)
        self.assertTrue(metadata_form.fields['final_title'].required)
        self.assertTrue(metadata_form.fields['final_author'].required)
        self.assertFalse(metadata_form.fields['final_series'].required)

        # Test optional search form fields
        search_form = BookSearchForm()
        self.assertFalse(search_form.fields['search_query'].required)
        self.assertFalse(search_form.fields['language'].required)


if __name__ == '__main__':
    import unittest
    unittest.main()
