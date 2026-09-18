#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""

import logging
import os
import sys

logging.basicConfig(stream=sys.stdout, level=logging.INFO, encoding="utf-8")  # Avoid UnicodeEncodeError on Windows


def main():
    """Run administrative tasks."""
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        os.environ["DJANGO_SETTINGS_MODULE"] = "ebook_manager.settings_test"
    else:
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ebook_manager.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and " "available on your PYTHONPATH environment variable? Did you " "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
