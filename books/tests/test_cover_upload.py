"""
Tests for Phase 2 Cover Upload/Replace functionality
"""

from io import BytesIO

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse
from PIL import Image

from books.forms import CoverUploadForm
from books.models import Book, BookFile
from books.utils.cover_cache import CoverCache


class CoverUploadFormTestCase(TestCase):
    """Test CoverUploadForm validation"""

    def create_test_image(self, width=800, height=1200, format="JPEG"):
        """Helper to create test image data"""
        img = Image.new("RGB", (width, height), color="red")
        buffer = BytesIO()
        img.save(buffer, format=format)
        buffer.seek(0)
        return buffer.getvalue()

    def test_valid_jpg_upload(self):
        """Test that valid JPG upload passes validation"""
        image_data = self.create_test_image(800, 1200, "JPEG")
        uploaded_file = SimpleUploadedFile("cover.jpg", image_data, content_type="image/jpeg")

        form = CoverUploadForm({}, {"cover_image": uploaded_file})
        self.assertTrue(form.is_valid())
        width, height = form.get_dimensions()
        self.assertEqual(width, 800)
        self.assertEqual(height, 1200)

    def test_valid_png_upload(self):
        """Test that valid PNG upload passes validation"""
        image_data = self.create_test_image(600, 900, "PNG")
        uploaded_file = SimpleUploadedFile("cover.png", image_data, content_type="image/png")

        form = CoverUploadForm({}, {"cover_image": uploaded_file})
        self.assertTrue(form.is_valid())

    def test_oversized_image_rejected(self):
        """Test that oversized images are rejected"""
        # Create image larger than MAX_WIDTH x MAX_HEIGHT
        image_data = self.create_test_image(2500, 3500)
        uploaded_file = SimpleUploadedFile("huge_cover.jpg", image_data, content_type="image/jpeg")

        form = CoverUploadForm({}, {"cover_image": uploaded_file})
        self.assertFalse(form.is_valid())
        self.assertIn("cover_image", form.errors)

    def test_undersized_image_rejected(self):
        """Test that tiny images are rejected"""
        image_data = self.create_test_image(50, 50)
        uploaded_file = SimpleUploadedFile("tiny_cover.jpg", image_data, content_type="image/jpeg")

        form = CoverUploadForm({}, {"cover_image": uploaded_file})
        self.assertFalse(form.is_valid())
        self.assertIn("cover_image", form.errors)

    def test_file_size_limit_enforced(self):
        """Test that files over 5MB are rejected"""
        # Create a large image
        img = Image.new("RGB", (2000, 2000), color="red")
        buffer = BytesIO()
        # Save with low quality to hit size limit
        img.save(buffer, format="JPEG", quality=100)

        # Pad to exceed 5MB
        buffer.write(b"x" * (6 * 1024 * 1024))
        buffer.seek(0)

        uploaded_file = SimpleUploadedFile("large_cover.jpg", buffer.read(), content_type="image/jpeg")

        form = CoverUploadForm({}, {"cover_image": uploaded_file})
        self.assertFalse(form.is_valid())
        self.assertIn("cover_image", form.errors)

    def test_invalid_format_rejected(self):
        """Test that non-image files are rejected"""
        # Create a fake "image" that's actually text
        fake_image = SimpleUploadedFile("fake.jpg", b"This is not an image", content_type="image/jpeg")

        form = CoverUploadForm({}, {"cover_image": fake_image})
        self.assertFalse(form.is_valid())


class CoverUploadEndpointTestCase(TestCase):
    """Test AJAX cover upload endpoint"""

    def setUp(self):
        """Set up test data"""
        self.client = Client()
        self.user = User.objects.create_user("testuser", "test@example.com", "password")
        self.client.login(username="testuser", password="password")

        # Create a test book and file
        self.book = Book.objects.create()
        self.bookfile = BookFile.objects.create(book=self.book, file_path="/test/book.epub", file_format="epub", cover_path="original/cover.jpg", cover_source_type="epub_internal")

    def tearDown(self):
        """Clean up after tests"""
        # Clear cover cache
        try:
            CoverCache.clear_all()
        except:
            pass

    def create_test_image(self, width=800, height=1200):
        """Helper to create test image"""
        img = Image.new("RGB", (width, height), color="blue")
        buffer = BytesIO()
        img.save(buffer, format="JPEG")
        buffer.seek(0)
        return buffer.getvalue()

    def test_upload_cover_success(self):
        """Test successful cover upload"""
        image_data = self.create_test_image(800, 1200)
        uploaded_file = SimpleUploadedFile("new_cover.jpg", image_data, content_type="image/jpeg")

        response = self.client.post(reverse("books:ajax_upload_bookfile_cover", args=[self.bookfile.id]), {"cover_image": uploaded_file})

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertIn("cover_url", data)
        self.assertEqual(data["width"], 800)
        self.assertEqual(data["height"], 1200)
        self.assertIsNotNone(data["quality_score"])

        # Verify database updated
        self.bookfile.refresh_from_db()
        self.assertEqual(self.bookfile.cover_source_type, "manual")
        self.assertEqual(self.bookfile.original_cover_path, "original/cover.jpg")
        self.assertEqual(self.bookfile.cover_width, 800)
        self.assertEqual(self.bookfile.cover_height, 1200)

    def test_upload_cover_requires_login(self):
        """Test that endpoint requires authentication"""
        self.client.logout()

        image_data = self.create_test_image()
        uploaded_file = SimpleUploadedFile("cover.jpg", image_data, content_type="image/jpeg")

        response = self.client.post(reverse("books:ajax_upload_bookfile_cover", args=[self.bookfile.id]), {"cover_image": uploaded_file})

        # Should redirect to login
        self.assertEqual(response.status_code, 302)

    def test_upload_cover_invalid_image(self):
        """Test that invalid images are rejected"""
        invalid_file = SimpleUploadedFile("fake.jpg", b"Not an image", content_type="image/jpeg")

        response = self.client.post(reverse("books:ajax_upload_bookfile_cover", args=[self.bookfile.id]), {"cover_image": invalid_file})

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data["success"])
        self.assertIn("errors", data)

    def test_upload_cover_bookfile_not_found(self):
        """Test 404 when BookFile doesn't exist"""
        image_data = self.create_test_image()
        uploaded_file = SimpleUploadedFile("cover.jpg", image_data, content_type="image/jpeg")

        response = self.client.post(reverse("books:ajax_upload_bookfile_cover", args=[9999]), {"cover_image": uploaded_file})

        self.assertEqual(response.status_code, 404)

    def test_replace_existing_manual_cover(self):
        """Test replacing an already-uploaded manual cover"""
        # First upload
        image1 = self.create_test_image(600, 900)
        self.client.post(reverse("books:ajax_upload_bookfile_cover", args=[self.bookfile.id]), {"cover_image": SimpleUploadedFile("cover1.jpg", image1, content_type="image/jpeg")})

        # Second upload (replacement)
        image2 = self.create_test_image(800, 1200)
        response = self.client.post(
            reverse("books:ajax_upload_bookfile_cover", args=[self.bookfile.id]), {"cover_image": SimpleUploadedFile("cover2.jpg", image2, content_type="image/jpeg")}
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])

        # Original should still be preserved
        self.bookfile.refresh_from_db()
        self.assertEqual(self.bookfile.original_cover_path, "original/cover.jpg")
        self.assertEqual(self.bookfile.cover_width, 800)
        self.assertEqual(self.bookfile.cover_height, 1200)


class CoverRestoreEndpointTestCase(TestCase):
    """Test cover restoration endpoint"""

    def setUp(self):
        """Set up test data"""
        self.client = Client()
        self.user = User.objects.create_user("testuser", "test@example.com", "password")
        self.client.login(username="testuser", password="password")

        self.book = Book.objects.create()
        self.bookfile = BookFile.objects.create(
            book=self.book, file_path="/test/book.epub", file_format="epub", cover_path="manual/upload.jpg", cover_source_type="manual", original_cover_path="original/cover.jpg"
        )

    def test_restore_original_cover(self):
        """Test restoring original cover after manual upload"""
        response = self.client.post(reverse("books:ajax_restore_bookfile_cover", args=[self.bookfile.id]))

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertIn("cover_path", data)

        # Verify restoration
        self.bookfile.refresh_from_db()
        self.assertEqual(self.bookfile.cover_path, "original/cover.jpg")
        self.assertEqual(self.bookfile.original_cover_path, "")
        self.assertNotEqual(self.bookfile.cover_source_type, "manual")

    def test_restore_without_original_fails(self):
        """Test that restore fails when there's no original"""
        # Remove original cover path
        self.bookfile.original_cover_path = ""
        self.bookfile.save()

        response = self.client.post(reverse("books:ajax_restore_bookfile_cover", args=[self.bookfile.id]))

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data["success"])

    def test_restore_requires_login(self):
        """Test that restore requires authentication"""
        self.client.logout()

        response = self.client.post(reverse("books:ajax_restore_bookfile_cover", args=[self.bookfile.id]))

        self.assertEqual(response.status_code, 302)


class CoverInfoEndpointTestCase(TestCase):
    """Test cover info retrieval endpoint"""

    def setUp(self):
        """Set up test data"""
        self.client = Client()
        self.user = User.objects.create_user("testuser", "test@example.com", "password")
        self.client.login(username="testuser", password="password")

        self.book = Book.objects.create()
        self.bookfile = BookFile.objects.create(
            book=self.book,
            file_path="/test/book.epub",
            file_format="epub",
            cover_path="cover_cache/abc123.jpg",
            cover_source_type="epub_internal",
            cover_width=800,
            cover_height=1200,
            cover_quality_score=85,
        )

    def test_get_cover_info_success(self):
        """Test retrieving cover information"""
        response = self.client.get(reverse("books:ajax_get_bookfile_cover_info", args=[self.bookfile.id]))

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertTrue(data["has_cover"])
        self.assertEqual(data["cover_source"], "epub_internal")
        self.assertEqual(data["width"], 800)
        self.assertEqual(data["height"], 1200)
        self.assertEqual(data["quality_score"], 85)
        self.assertFalse(data["can_restore"])

    def test_get_cover_info_manual_with_restore(self):
        """Test cover info shows restore capability for manual uploads"""
        self.bookfile.cover_source_type = "manual"
        self.bookfile.original_cover_path = "original/cover.jpg"
        self.bookfile.save()

        response = self.client.get(reverse("books:ajax_get_bookfile_cover_info", args=[self.bookfile.id]))

        data = response.json()
        self.assertTrue(data["can_restore"])
        self.assertTrue(data["has_original"])

    def test_get_cover_info_no_cover(self):
        """Test cover info for BookFile without cover"""
        self.bookfile.cover_path = ""
        self.bookfile.save()

        response = self.client.get(reverse("books:ajax_get_bookfile_cover_info", args=[self.bookfile.id]))

        data = response.json()
        self.assertTrue(data["success"])
        self.assertFalse(data["has_cover"])
        self.assertIsNone(data["cover_url"])


class CoverQualityScoreTestCase(TestCase):
    """Test cover quality scoring algorithm"""

    def test_high_resolution_gets_high_score(self):
        """Test that high resolution images get high quality scores"""
        from books.views.ajax_cover import _calculate_quality_score

        # 1000x1500px, 200KB - should score high
        score = _calculate_quality_score(1000, 1500, 200000)
        self.assertGreaterEqual(score, 80)

    def test_low_resolution_gets_low_score(self):
        """Test that low resolution images get low quality scores"""
        from books.views.ajax_cover import _calculate_quality_score

        # 300x450px, 50KB - should score lower
        score = _calculate_quality_score(300, 450, 50000)
        self.assertLess(score, 70)

    def test_perfect_aspect_ratio_bonus(self):
        """Test that ideal aspect ratio (1.5:1) gets bonus points"""
        from books.views.ajax_cover import _calculate_quality_score

        # Perfect 1.5:1 aspect ratio
        score_perfect = _calculate_quality_score(1000, 1500, 150000)

        # Non-ideal aspect ratio
        score_nonideal = _calculate_quality_score(1000, 1000, 150000)

        self.assertGreater(score_perfect, score_nonideal)

    def test_score_bounds(self):
        """Test that scores are always 0-100"""
        from books.views.ajax_cover import _calculate_quality_score

        # Very small image
        score_min = _calculate_quality_score(100, 100, 10000)
        self.assertGreaterEqual(score_min, 0)
        self.assertLessEqual(score_min, 100)

        # Very large image
        score_max = _calculate_quality_score(2000, 3000, 500000)
        self.assertGreaterEqual(score_max, 0)
        self.assertLessEqual(score_max, 100)
