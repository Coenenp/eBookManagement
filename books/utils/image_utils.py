"""Image and cover handling utilities.

This module provides functions for downloading, processing, and encoding
book cover images for display and storage operations.
"""
import base64
import os

import requests
from django.conf import settings
from django.utils.text import slugify


def download_and_store_cover(candidate):
    response = requests.get(candidate.image_url, timeout=10)
    response.raise_for_status()

    # Get filename from the primary file
    primary_file = candidate.book.primary_file
    book_filename = primary_file.filename if primary_file else f"book_{candidate.book.id}"
    filename = f"{slugify(book_filename)}_cover.jpg"
    relative_path = os.path.join('covers', filename)
    absolute_path = os.path.join(settings.MEDIA_ROOT, relative_path)

    with open(absolute_path, 'wb') as f:
        f.write(response.content)

    return os.path.join(settings.MEDIA_URL, relative_path)


def encode_cover_to_base64(path):
    if not path or not os.path.isfile(path):
        return ""
    try:
        with open(path, "rb") as image_file:
            encoded_bytes = base64.b64encode(image_file.read())
            return f"data:image/jpeg;base64,{encoded_bytes.decode('utf-8')}"
    except Exception as e:
        print(f"Error encoding image: {e}")
        return ""
