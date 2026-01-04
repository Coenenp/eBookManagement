"""File operation utilities for ebook scanning.

This module provides functions for detecting ebook file formats,
finding cover images, and handling OPF metadata files.
"""

import os
from pathlib import Path


def get_file_format(file_path: str) -> str:
    ext = Path(file_path).suffix.lower()
    return {
        ".epub": "epub",
        ".mobi": "mobi",
        ".pdf": "pdf",
        ".azw": "azw",
        ".azw3": "azw3",
        ".cbr": "cbr",
        ".cbz": "cbz",
    }.get(ext, "unknown")


def find_cover_file(ebook_path: str, cover_files: list) -> str:
    """Find cover file located in the same folder as the ebook"""
    ebook_dir = os.path.dirname(ebook_path)
    for cover_file in cover_files:
        if os.path.dirname(cover_file) == ebook_dir:
            return cover_file
    return ""


def find_opf_file(ebook_path: str, opf_files: list) -> str:
    """Find OPF file located in the same folder as the ebook"""
    ebook_dir = os.path.dirname(ebook_path)
    for opf_file in opf_files:
        if os.path.dirname(opf_file) == ebook_dir:
            return opf_file
    return ""
