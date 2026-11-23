"""File operation utilities for ebook scanning.

This module provides functions for detecting ebook file formats,
finding cover images, and handling OPF metadata files.
"""

import os
import unicodedata
from pathlib import Path


def _dirname(file_path: str) -> str:
    """Directory of a path, treating both ``/`` and ``\\`` as separators."""
    return os.path.dirname(file_path.replace("\\", "/"))


def _basename(file_path: str) -> str:
    """Base name of a path, treating both ``/`` and ``\\`` as separators."""
    return os.path.basename(file_path.replace("\\", "/"))


def _normalized_stem(file_path: str) -> str:
    """Return the NFC-normalized, casefolded stem of a file path."""
    return unicodedata.normalize("NFC", os.path.splitext(_basename(file_path))[0]).casefold()


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


def find_opf_file(ebook_path: str, opf_files: list, ebook_files: list = None) -> str:
    """Find the OPF file that belongs to the ebook.

    Returns, in order:
    1. the OPF in the same folder whose file stem equals the ebook's stem
       (compared NFC-normalized and case insensitive, independent of list order);
    2. otherwise ``metadata.opf`` in that folder, but only when the folder holds
       exactly one ebook file (this rule needs ``ebook_files`` and is skipped when
       it is not passed);
    3. otherwise an empty string.
    """
    ebook_dir = _dirname(ebook_path)
    ebook_stem = _normalized_stem(ebook_path)

    # Rule 1: stem match in the same folder, independent of list order.
    for opf_file in opf_files:
        if _dirname(opf_file) == ebook_dir and _normalized_stem(opf_file) == ebook_stem:
            return opf_file

    # Rule 2: metadata.opf, only when the folder holds exactly one ebook file.
    if ebook_files is not None:
        same_folder_ebooks = [f for f in ebook_files if _dirname(f) == ebook_dir]
        if len(same_folder_ebooks) == 1:
            for opf_file in opf_files:
                if _dirname(opf_file) == ebook_dir and _basename(opf_file).casefold() == "metadata.opf":
                    return opf_file

    return ""
