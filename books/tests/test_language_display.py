"""Tests that FinalMetadata.language consumers name langid codes correctly.

``FinalMetadata.save`` stores a language reduced to its base langid code
(``sv``, ``nb``, ``af``, ...) or the ``und``/empty markers. Consumers that
display that code must resolve it to its English name, not fall back to the
raw code or a title-cased version.
"""

from django.test import TestCase

from books.models import Book, FinalMetadata
from books.utils.language_manager import LanguageManager


class GetLanguageNameTests(TestCase):
    def test_get_language_name_accepts_langid_codes(self):
        self.assertEqual(LanguageManager.get_language_name("sv"), "Swedish")
        self.assertEqual(LanguageManager.get_language_name("nb"), "Norwegian")
        self.assertEqual(LanguageManager.get_language_name("af"), "Afrikaans")

    def test_get_language_name_und_and_empty(self):
        self.assertEqual(LanguageManager.get_language_name("und"), "Unknown Language")
        self.assertEqual(LanguageManager.get_language_name(""), "Not defined")


class CoreBookListLanguageFilterTests(TestCase):
    """BookListView (core.py) names stored langid codes correctly."""

    def test_core_book_list_uses_language_names(self):
        from django.contrib.auth.models import AnonymousUser
        from django.test import RequestFactory

        from books.views.core import BookListView

        book = Book.objects.create(content_type="ebook")
        FinalMetadata.objects.create(book=book, final_title="T", final_author="A", language="sv")
        view = BookListView()
        view.request = RequestFactory().get("/")
        view.request.user = AnonymousUser()
        view.kwargs = {}
        view.object_list = Book.objects.all()
        context = view.get_context_data(object_list=view.object_list)
        languages = dict(context["languages"])
        self.assertEqual(languages.get("sv"), "Swedish")
