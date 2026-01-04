"""Quick test for ScanFolder path validation fix"""

import shutil
import tempfile

import pytest
from django.test import TestCase

from books.models import ScanFolder


@pytest.mark.django_db
class TestScanFolderPathValidation(TestCase):
    """Test ScanFolder path validation improvements"""

    def test_can_create_with_nonexistent_path(self):
        """Test that we can create ScanFolder with non-existent path"""
        sf = ScanFolder.objects.create(
            path="/fake/nonexistent/path", name="Test Non-Existent"
        )
        self.assertIsNotNone(sf.pk)
        self.assertEqual(sf.path, "/fake/nonexistent/path")

    def test_can_create_with_real_path(self):
        """Test that we can create ScanFolder with real temp directory"""
        temp_dir = tempfile.mkdtemp()
        try:
            sf = ScanFolder.objects.create(path=temp_dir, name="Test Real Path")
            self.assertIsNotNone(sf.pk)
            self.assertEqual(sf.path, temp_dir)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_can_skip_validation(self):
        """Test that skip_validation parameter works"""
        sf = ScanFolder(path="/another/fake/path", name="Test Skip")
        sf.save(skip_validation=True)
        self.assertIsNotNone(sf.pk)
