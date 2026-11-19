"""Tests for reviewed author order (Part C)."""

from django.core.management import call_command
from django.test import TestCase

from books.models import Author, Book, FinalMetadata
from books.utils.renaming_engine import RenamingEngine


class ReviewedAuthorOrderTests(TestCase):
    def _book(self, author_name):
        book = Book.objects.create()
        FinalMetadata.objects.create(book=book, final_author=author_name, final_title="T")
        return book

    def _reviewed_author(self, name, last, first):
        author = Author.objects.create(name=name, is_reviewed=True)
        Author.objects.filter(pk=author.pk).update(first_name=first, last_name=last)
        return author

    def test_reviewed_author_sortname(self):
        self._reviewed_author("Han Kang", "Han", "Kang")
        book = self._book("Han Kang")
        engine = RenamingEngine()
        self.assertEqual(engine.process_template("${author.sortname}", book), "Han, Kang")

    def test_reviewed_author_cached_second_book(self):
        self._reviewed_author("Han Kang", "Han", "Kang")
        book1 = self._book("Han Kang")
        book2 = self._book("Han Kang")
        engine = RenamingEngine()
        self.assertEqual(engine.process_template("${author.sortname}", book1), "Han, Kang")
        self.assertEqual(engine.process_template("${author.sortname}", book2), "Han, Kang")

    def test_unreviewed_author_ignored(self):
        Author.objects.create(name="Han Kang")  # is_reviewed=False
        book = self._book("Han Kang")
        engine = RenamingEngine()
        self.assertEqual(engine.process_template("${author.sortname}", book), "Kang, Han")

    def test_no_reviewed_row_behaves_as_before(self):
        book = self._book("Han Kang")
        engine = RenamingEngine()
        self.assertEqual(engine.process_template("${author.sortname}", book), "Kang, Han")

    def test_reviewed_order_survives_author_save(self):
        call_command("set_author_order", "Han Kang", "--last", "Han", "--first", "Kang", "--execute")
        author = Author.objects.get(name_normalized="han kang")
        author.save()  # Author.save recomputes name_normalized to "kang han"
        book = self._book("Han Kang")
        engine = RenamingEngine()
        self.assertEqual(engine.process_template("${author.sortname}", book), "Han, Kang")

    def test_reviewed_order_case_insensitive_final_author(self):
        self._reviewed_author("Han Kang", "Han", "Kang")
        book = self._book("han kang")
        engine = RenamingEngine()
        self.assertEqual(engine.process_template("${author.sortname}", book), "Han, Kang")

    def test_reviewed_wins_over_unreviewed_same_name(self):
        # An unreviewed Author created first and a reviewed Author created
        # second both match the same final author; the reviewed row must win
        # for the sort name.
        Author.objects.create(name="Han Kang")  # unreviewed, created first
        Author.objects.create(
            name="Han Kang", first_name="Kang", last_name="Han", is_reviewed=True
        )
        book = self._book("Han Kang")
        engine = RenamingEngine()
        self.assertEqual(engine.process_template("${author.sortname}", book), "Han, Kang")


class SetAuthorOrderCommandTests(TestCase):
    def test_without_execute_stores_nothing(self):
        before = Author.objects.count()
        call_command("set_author_order", "Han Kang", "--last", "Han", "--first", "Kang")
        self.assertEqual(Author.objects.count(), before)

    def test_execute_stores_fields_and_survives_reload(self):
        call_command("set_author_order", "Han Kang", "--last", "Han", "--first", "Kang", "--execute")
        author = Author.objects.get(name_normalized="han kang")
        self.assertEqual(author.first_name, "Kang")
        self.assertEqual(author.last_name, "Han")
        self.assertTrue(author.is_reviewed)

        reloaded = Author.objects.get(pk=author.pk)
        self.assertEqual(reloaded.first_name, "Kang")
        self.assertEqual(reloaded.last_name, "Han")
        self.assertTrue(reloaded.is_reviewed)
        self.assertEqual(reloaded.name_normalized, "han kang")

    def test_execute_is_idempotent(self):
        call_command("set_author_order", "Han Kang", "--last", "Han", "--first", "Kang", "--execute")
        call_command("set_author_order", "Han Kang", "--last", "Han", "--first", "Kang", "--execute")
        self.assertEqual(Author.objects.filter(name_normalized="han kang").count(), 1)
        author = Author.objects.get(name_normalized="han kang")
        self.assertEqual((author.first_name, author.last_name), ("Kang", "Han"))
        self.assertTrue(author.is_reviewed)

    def test_execute_updates_existing_author(self):
        Author.objects.create(name="Han Kang")  # name_normalized "han kang"
        call_command("set_author_order", "Han Kang", "--last", "Han", "--first", "Kang", "--execute")
        author = Author.objects.get(name_normalized="han kang")
        self.assertEqual(author.first_name, "Kang")
        self.assertEqual(author.last_name, "Han")
        self.assertTrue(author.is_reviewed)
