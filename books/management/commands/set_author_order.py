"""Set the reviewed sort order for an author keyed by natural-order name."""

from django.core.management.base import BaseCommand, CommandError

from books.models import Author
from books.utils.authors import find_author_by_name, normalize_author_name


class Command(BaseCommand):
    help = "Store the reviewed first/last order for an author keyed by natural-order name."

    def add_arguments(self, parser):
        parser.add_argument("name", help="Author name in natural order (as in final metadata).")
        parser.add_argument("--last", required=True, help="Last name to store.")
        parser.add_argument("--first", default="", help="First name to store (optional).")
        parser.add_argument(
            "--execute",
            action="store_true",
            help="Actually write; without it only print what would be stored.",
        )

    def handle(self, *args, **options):
        name = (options["name"] or "").strip()
        last = (options["last"] or "").strip()
        first = (options["first"] or "").strip()
        execute = options["execute"]

        if not name:
            raise CommandError("name is required")
        if not last:
            raise CommandError("--last is required")

        normalized = normalize_author_name(name)

        if not execute:
            self.stdout.write(
                f"Would store order for '{name}' (normalized '{normalized}'): "
                f"first_name='{first}', last_name='{last}', is_reviewed=True"
            )
            return

        author = find_author_by_name(name)
        if author is None:
            author = Author(name=name)
            author.save()

        # Author.save recomputes name_normalized from first_name+last_name, so
        # write the reviewed order with a queryset update to keep the stored
        # values (and the name_normalized keyed to the natural-order name).
        Author.objects.filter(pk=author.pk).update(
            first_name=first, last_name=last, is_reviewed=True
        )

        author = Author.objects.get(pk=author.pk)
        self.stdout.write(
            f"Stored order: name='{author.name}', first_name='{author.first_name}', "
            f"last_name='{author.last_name}', is_reviewed={author.is_reviewed}"
        )
