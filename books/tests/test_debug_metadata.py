"""Debug test for metadata form validation"""

import pytest
from django.test import Client, TestCase

from books.forms import MetadataReviewForm
from books.models import Book, BookFile, FinalMetadata, ScanFolder


@pytest.mark.django_db
class TestMetadataFormDebug(TestCase):
    """Debug metadata form issues"""

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.create_user())

        # Create test data
        self.scan_folder = ScanFolder.objects.create(
            name="Test Library", path="/test/library", is_active=True
        )

        self.book = Book.objects.create(scan_folder=self.scan_folder)

        BookFile.objects.create(
            book=self.book,
            file_path="/test/library/test.epub",
            file_format="epub",
            file_size=1024000,
        )

        self.final_metadata = FinalMetadata.objects.create(
            book=self.book,
            final_title="Original Title",
            final_author="Original Author",
            is_reviewed=False,
        )

    def create_user(self):
        from django.contrib.auth.models import User

        return User.objects.create_user(username="testuser", password="testpass")

    def test_form_directly_minimal(self):
        """Test the form directly with minimal data"""
        form_data = {
            "isbn": "9781234567890",
            "publication_year": "2023",
            "language": "English",
            "description": "Updated description",
        }
        form = MetadataReviewForm(
            data=form_data, instance=self.final_metadata, book=self.book
        )
        print(f"\nForm is_valid: {form.is_valid()}")
        print(f"Form errors: {form.errors}")
        if form.is_valid():
            print(f"Form cleaned_data: {form.cleaned_data}")
        else:
            for field, errors in form.errors.items():
                print(f"  {field}: {errors}")
        self.assertTrue(form.is_valid())

    def test_form_directly_complete(self):
        """Test the form with all required fields"""
        form_data = {
            "final_title": "Updated Title",
            "final_author": "Updated Author",
            "isbn": "9781234567890",
            "publication_year": "2023",
            "language": "en",
            "description": "Updated description",
        }
        form = MetadataReviewForm(
            data=form_data, instance=self.final_metadata, book=self.book
        )
        print(f"\nComplete form is_valid: {form.is_valid()}")
        print(f"Complete form errors: {form.errors}")
        self.assertTrue(form.is_valid())
