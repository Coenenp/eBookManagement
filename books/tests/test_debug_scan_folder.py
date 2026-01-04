"""Debug test for scan folder form validation"""

import pytest
from django.test import Client, TestCase
from django.urls import reverse

from books.forms import ScanFolderForm


@pytest.mark.django_db
class TestScanFolderFormDebug(TestCase):
    """Debug scan folder form issues"""

    def setUp(self):
        self.client = Client()

    def test_form_directly(self):
        """Test the form directly to see validation errors"""
        form_data = {"name": "New Library", "path": "/new/library", "is_active": True}
        form = ScanFolderForm(data=form_data)
        print(f"\nForm is_valid: {form.is_valid()}")
        print(f"Form errors: {form.errors}")
        print(f"Form cleaned_data: {form.cleaned_data if form.is_valid() else 'N/A'}")
        self.assertTrue(form.is_valid())

    def test_view_response(self):
        """Test the view to see response details"""
        response = self.client.post(
            reverse("books:add_scan_folder"),
            {"name": "New Library", "path": "/new/library", "is_active": True},
        )
        print(f"\nResponse status: {response.status_code}")
        if hasattr(response, "context") and response.context:
            if "form" in response.context:
                print(f"Form errors: {response.context['form'].errors}")
        self.assertEqual(
            response.status_code,
            302,
            f"Expected redirect but got {response.status_code}",
        )
