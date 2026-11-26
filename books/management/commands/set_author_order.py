"""Set the reviewed sort order for an author keyed by natural-order name.

The writing action lives in :func:`books.services.authors.store_author_order`
so the command and the author order screen (UI) share one implementation.
This command only parses options, calls the service, and prints.
"""

from django.core.management.base import BaseCommand, CommandError

from books.services.authors import store_author_order


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

        result = store_author_order(name, last, first, execute)
        for line in result["lines"]:
            self.stdout.write(line)
