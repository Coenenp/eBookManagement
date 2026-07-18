#!/usr/bin/env python
"""Script to clear cache"""

import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ebook_manager.settings")
django.setup()

from django.core.cache import cache

print("Clearing all cache...")
cache.clear()
print("Cache cleared successfully!")
