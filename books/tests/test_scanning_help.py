"""Test that the scanning help page renders (regression for the 500)."""

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse


class ScanningHelpTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="helpuser", email="help@example.com", password="testpass123"
        )
        self.client = Client()

    def test_scanning_help_renders(self):
        """GET /scanning/help/ returns 200 for an authenticated user."""
        self.client.force_login(self.user)
        response = self.client.get(reverse("books:scanning_help"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Scanning Help")