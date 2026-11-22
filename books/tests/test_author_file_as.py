"""Part B: one shared author file_as function used by the engine and metadata sync.

The safe-move metadata sync and the renaming engine must derive an author's
``file_as`` (sort form) identically: from a reviewed ``Author`` row when one
exists, otherwise by splitting the name. Both call sites share
``books.utils.authors.author_file_as``.
"""

from django.test import TestCase

from books.models import Author, Book, FinalMetadata
from books.utils.renaming_engine import RenamingEngine
from books.utils.safe_move.metadata_sync import build_epub_metadata


class AuthorFileAsTests(TestCase):
    def _book(self, final_author):
        book = Book.objects.create()
        FinalMetadata.objects.create(book=book, final_author=final_author, final_title="T")
        return book

    def _file_as_from_metadata(self, book):
        return build_epub_metadata(book)["authors"][0]["file_as"]

    def _file_as_from_engine(self, book):
        engine = RenamingEngine()
        engine.current_book = book
        return engine._get_author_sortname()

    def test_unreviewed_author_ignored_for_file_as(self):
        # An unreviewed Author with a wrong split must not be used; sort_name
        # gives the correct "Peck, Robert Newton".
        Author.objects.create(first_name="Robert", last_name="Newton Peck")
        book = self._book("Robert Newton Peck")
        self.assertEqual(self._file_as_from_metadata(book), "Peck, Robert Newton")

    def test_reviewed_author_supplies_file_as(self):
        Author.objects.create(first_name="Robert", last_name="Newton Peck", is_reviewed=True)
        book = self._book("Robert Newton Peck")
        self.assertEqual(self._file_as_from_metadata(book), "Newton Peck, Robert")

    def test_engine_and_metadata_sync_agree(self):
        Author.objects.create(first_name="Robert", last_name="Newton Peck", is_reviewed=True)
        book = self._book("Robert Newton Peck")
        self.assertEqual(self._file_as_from_engine(book), self._file_as_from_metadata(book))
