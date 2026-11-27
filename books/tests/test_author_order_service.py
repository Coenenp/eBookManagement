"""Golden output and merge tests for the set_author_order service layer."""

from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from books.models import Author, Book, BookAuthor, DataSource
from books.services.authors import store_author_order


class SetAuthorOrderGoldenTests(TestCase):
    def _run(self, *args):
        out = StringIO()
        call_command("set_author_order", *args, stdout=out)
        return out.getvalue()

    def test_golden_dry_run(self):
        out = self._run("Han Kang", "--last", "Han", "--first", "Kang")
        self.assertEqual(
            out,
            "Would store order for 'Han Kang' (normalized 'han kang'): "
            "first_name='Kang', last_name='Han', is_reviewed=True\n",
        )
        self.assertEqual(Author.objects.count(), 0)

    def test_golden_execute(self):
        out = self._run("Han Kang", "--last", "Han", "--first", "Kang", "--execute")
        self.assertEqual(
            out,
            "Stored order: name='Han Kang', first_name='Kang', "
            "last_name='Han', is_reviewed=True\n",
        )

    def test_golden_name_not_found(self):
        out = self._run("Jane Doe", "--last", "Doe", "--first", "Jane", "--execute")
        self.assertEqual(
            out,
            "Stored order: name='Jane Doe', first_name='Jane', "
            "last_name='Doe', is_reviewed=True\n",
        )
        self.assertTrue(Author.objects.filter(name="Jane Doe").exists())

    def test_golden_second_execute_changes_nothing(self):
        self._run("Han Kang", "--last", "Han", "--first", "Kang", "--execute")
        out = self._run("Han Kang", "--last", "Han", "--first", "Kang", "--execute")
        self.assertEqual(
            out,
            "Stored order: name='Han Kang', first_name='Kang', "
            "last_name='Han', is_reviewed=True\n",
        )
        self.assertEqual(Author.objects.filter(name_normalized="han kang").count(), 1)


class SetAuthorOrderMergeTests(TestCase):
    def _source(self):
        return DataSource.objects.get_or_create(
            name=DataSource.EPUB_INTERNAL, defaults={"priority": 1, "trust_level": 5}
        )[0]

    def _book(self):
        return Book.objects.create()

    def _link(self, book, author, source):
        return BookAuthor.objects.create(book=book, author=author, source=source)

    def test_merge_natsume_soseki(self):
        # Row keyed by the natural-order name, holding the BookAuthor link.
        natural = Author.objects.create(name="Natsume Soseki")
        # Another row already holds the wanted pair.
        holder = Author.objects.create(
            name="Soseki Natsume", first_name="Soseki", last_name="Natsume"
        )
        source = self._source()
        book = self._book()
        self._link(book, natural, source)

        call_command(
            "set_author_order",
            "Natsume Soseki",
            "--last", "Natsume", "--first", "Soseki", "--execute",
        )

        self.assertEqual(Author.objects.count(), 1)
        kept = Author.objects.get()
        self.assertEqual(kept.name, "Natsume Soseki")
        self.assertEqual(kept.first_name, "Soseki")
        self.assertEqual(kept.last_name, "Natsume")
        self.assertTrue(kept.is_reviewed)
        self.assertEqual(kept.name_normalized, "natsume soseki")
        self.assertEqual(kept.pk, holder.pk)
        self.assertEqual(BookAuthor.objects.get().author_id, kept.pk)

    def test_merge_accented_pair(self):
        natural = Author.objects.create(name="Garcia Marquez")
        holder = Author.objects.create(
            name="García Márquez", first_name="García", last_name="Márquez"
        )
        source = self._source()
        book = self._book()
        self._link(book, natural, source)

        call_command(
            "set_author_order",
            "Garcia Marquez",
            "--last", "Márquez", "--first", "García", "--execute",
        )

        self.assertEqual(Author.objects.count(), 1)
        kept = Author.objects.get()
        self.assertEqual(kept.name, "Garcia Marquez")
        self.assertEqual(kept.first_name, "García")
        self.assertEqual(kept.last_name, "Márquez")
        self.assertTrue(kept.is_reviewed)
        self.assertEqual(kept.pk, holder.pk)
        self.assertEqual(BookAuthor.objects.get().author_id, kept.pk)

    def test_merge_keeps_kept_row_reviewed(self):
        natural = Author.objects.create(name="Natsume Soseki")
        holder = Author.objects.create(
            name="Soseki Natsume", first_name="Soseki", last_name="Natsume",
            is_reviewed=True,
        )
        source = self._source()
        book = self._book()
        self._link(book, natural, source)

        call_command(
            "set_author_order",
            "Natsume Soseki",
            "--last", "Natsume", "--first", "Soseki", "--execute",
        )

        kept = Author.objects.get()
        self.assertTrue(kept.is_reviewed)
        self.assertEqual(kept.pk, holder.pk)

    def test_merge_second_run_changes_nothing(self):
        natural = Author.objects.create(name="Natsume Soseki")
        holder = Author.objects.create(
            name="Soseki Natsume", first_name="Soseki", last_name="Natsume"
        )
        source = self._source()
        book = self._book()
        self._link(book, natural, source)

        call_command(
            "set_author_order",
            "Natsume Soseki",
            "--last", "Natsume", "--first", "Soseki", "--execute",
        )
        kept_id = Author.objects.get().pk
        call_command(
            "set_author_order",
            "Natsume Soseki",
            "--last", "Natsume", "--first", "Soseki", "--execute",
        )

        self.assertEqual(Author.objects.count(), 1)
        kept = Author.objects.get()
        self.assertEqual(kept.pk, kept_id)
        self.assertEqual(kept.name, "Natsume Soseki")
        self.assertTrue(kept.is_reviewed)
        self.assertEqual(BookAuthor.objects.get().author_id, kept_id)

    def test_merge_dedupes_book_author_rows(self):
        natural = Author.objects.create(name="Natsume Soseki")
        holder = Author.objects.create(
            name="Soseki Natsume", first_name="Soseki", last_name="Natsume"
        )
        source = self._source()
        book = self._book()
        # Both rows link the same book via the same source; after the merge
        # only one BookAuthor row may remain.
        self._link(book, natural, source)
        self._link(book, holder, source)

        call_command(
            "set_author_order",
            "Natsume Soseki",
            "--last", "Natsume", "--first", "Soseki", "--execute",
        )

        self.assertEqual(
            BookAuthor.objects.filter(book=book, source=source).count(), 1
        )
        self.assertEqual(BookAuthor.objects.get().author_id, holder.pk)

    def test_dry_run_reports_collision(self):
        natural = Author.objects.create(name="Natsume Soseki")
        Author.objects.create(
            name="Soseki Natsume", first_name="Soseki", last_name="Natsume"
        )

        out = StringIO()
        call_command(
            "set_author_order",
            "Natsume Soseki",
            "--last", "Natsume", "--first", "Soseki", stdout=out,
        )

        text = out.getvalue()
        self.assertIn("Would store order for 'Natsume Soseki'", text)
        self.assertIn("Collision:", text)
        # The dry run writes nothing.
        self.assertEqual(Author.objects.count(), 2)
        self.assertEqual(Author.objects.filter(is_reviewed=True).count(), 0)


    def test_merge_no_natural_row_holder_wins(self):
        # No row exists under the natural-order name; another row already
        # holds the wanted pair.
        holder = Author.objects.create(
            name="Soseki Natsume", first_name="Soseki", last_name="Natsume"
        )
        source = self._source()
        book = self._book()
        self._link(book, holder, source)
        link_id = BookAuthor.objects.get().pk

        call_command(
            "set_author_order",
            "Natsume Soseki",
            "--last", "Natsume", "--first", "Soseki", "--execute",
        )

        # Nothing is deleted: the holder survives, renamed and reviewed.
        self.assertEqual(Author.objects.count(), 1)
        kept = Author.objects.get()
        self.assertEqual(kept.pk, holder.pk)
        self.assertEqual(kept.name, "Natsume Soseki")
        self.assertTrue(kept.is_reviewed)
        # No BookAuthor row changed.
        link = BookAuthor.objects.get()
        self.assertEqual(link.pk, link_id)
        self.assertEqual(link.author_id, holder.pk)

    def test_dry_run_collision_line_exact(self):
        natural = Author.objects.create(name="Natsume Soseki")
        Author.objects.create(
            name="Soseki Natsume", first_name="Soseki", last_name="Natsume"
        )

        out = StringIO()
        call_command(
            "set_author_order",
            "Natsume Soseki",
            "--last", "Natsume", "--first", "Soseki", stdout=out,
        )

        lines = out.getvalue().splitlines()
        self.assertEqual(len(lines), 2)
        self.assertEqual(
            lines[1],
            "Collision: 'Soseki Natsume' already holds first_name='Soseki', "
            "last_name='Natsume'; would move BookAuthor links from "
            "'Natsume Soseki' to it, delete 'Natsume Soseki', rename the kept "
            "row to 'Natsume Soseki' and set it reviewed",
        )


class SetAuthorOrderParityTests(TestCase):
    def test_command_and_service_agree(self):
        # Command path.
        cmd_out = StringIO()
        call_command(
            "set_author_order",
            "Han Kang", "--last", "Han", "--first", "Kang", "--execute",
            stdout=cmd_out,
        )
        cmd_author = Author.objects.get()
        cmd_state = (
            cmd_author.name, cmd_author.first_name,
            cmd_author.last_name, cmd_author.is_reviewed,
        )

        # Reset and run the service path directly.
        Author.objects.all().delete()
        result = store_author_order("Han Kang", "Han", "Kang", True)
        svc_author = Author.objects.get()
        svc_state = (
            svc_author.name, svc_author.first_name,
            svc_author.last_name, svc_author.is_reviewed,
        )

        self.assertEqual(result["lines"], [cmd_out.getvalue().rstrip("\n")])
        self.assertEqual(svc_state, cmd_state)


class StoreAuthorOrderRefusalTests(TestCase):
    def _source(self):
        return DataSource.objects.get_or_create(
            name=DataSource.EPUB_INTERNAL, defaults={"priority": 1, "trust_level": 5}
        )[0]

    def _refused_setup(self):
        natural = Author.objects.create(name="Natsume Soseki", is_reviewed=True)
        holder = Author.objects.create(
            name="Soseki Natsume", first_name="Soseki", last_name="Natsume"
        )
        source = self._source()
        book = Book.objects.create()
        BookAuthor.objects.create(book=book, author=natural, source=source)
        return natural, holder, book

    def test_execute_refuses_when_natural_row_reviewed(self):
        natural, holder, book = self._refused_setup()

        out = StringIO()
        call_command(
            "set_author_order",
            "Natsume Soseki",
            "--last", "Natsume", "--first", "Soseki", "--execute",
            stdout=out,
        )

        text = out.getvalue()
        self.assertTrue(text.startswith("Refused: "), text)
        self.assertIn("Natsume Soseki", text)
        self.assertIn("Soseki Natsume", text)
        # Nothing changed: both rows remain and the reviewed row is untouched.
        self.assertEqual(Author.objects.count(), 2)
        natural.refresh_from_db()
        self.assertTrue(natural.is_reviewed)
        holder.refresh_from_db()
        self.assertEqual(holder.name, "Soseki Natsume")
        self.assertEqual(BookAuthor.objects.get().author_id, natural.pk)

    def test_dry_run_reports_refusal_not_collision(self):
        natural, holder, book = self._refused_setup()

        out = StringIO()
        call_command(
            "set_author_order",
            "Natsume Soseki",
            "--last", "Natsume", "--first", "Soseki", stdout=out,
        )

        text = out.getvalue()
        self.assertIn("Would store order for 'Natsume Soseki'", text)
        self.assertIn("Refused: ", text)
        self.assertNotIn("Collision:", text)
        self.assertEqual(Author.objects.count(), 2)
        self.assertEqual(Author.objects.filter(is_reviewed=True).count(), 1)

    def test_service_returns_merged_false_on_refusal(self):
        natural, holder, book = self._refused_setup()

        result = store_author_order("Natsume Soseki", "Natsume", "Soseki", True)

        self.assertFalse(result["merged"])
        self.assertIsNone(result["author_id"])
        self.assertTrue(result["lines"][0].startswith("Refused: "))
        self.assertEqual(Author.objects.count(), 2)

