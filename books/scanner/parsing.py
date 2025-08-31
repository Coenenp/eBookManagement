"""Filename and metadata parsing utilities.

This module provides functions for parsing ebook filenames to extract
metadata like titles, authors, series information, and publication data.
"""
import re
from pathlib import Path
from typing import Dict, Optional, Tuple, List
from books.utils.parsing_helpers import (
    split_authors,
    normalize_surnames,
    extract_folder_clues,
    clean_title_and_extract_series_number,
    is_probable_author,
    extract_number_from_filename,
    fallback_segment_resolution
)


def resolve_title_author_ambiguity(part1: str, part2: str) -> Tuple[str, List[str]]:
    """Resolve whether part1 or part2 is more likely the author."""
    # Strip and normalize
    part1_clean = part1.strip()
    part2_clean = part2.strip()

    if is_probable_author(part1_clean) and not is_probable_author(part2_clean):
        return part2_clean, normalize_surnames(split_authors(part1_clean))
    elif is_probable_author(part2_clean) and not is_probable_author(part1_clean):
        return part1_clean, normalize_surnames(split_authors(part2_clean))
    else:
        # Fall back on punctuation density: titles tend to have more punctuation
        punc_score_1 = sum(part1_clean.count(p) for p in ":,-()")
        punc_score_2 = sum(part2_clean.count(p) for p in ":,-()")
        if punc_score_1 > punc_score_2:
            return part2_clean, normalize_surnames(split_authors(part1_clean))
        else:
            return part1_clean, normalize_surnames(split_authors(part2_clean))


def parse_path_metadata(file_path: str) -> Dict[str, Optional[str]]:
    path = Path(file_path)
    base_name = path.stem.replace('_', ' ').strip()

    metadata = {
        "title": None,
        "authors": [],
        "series": None,
        "series_number": None
    }

    series_number = extract_number_from_filename(base_name)
    if series_number and not metadata["series_number"]:
        metadata["series_number"] = series_number

    patterns = [
        r'^(?P<num>\d{1,2}(?:\.\d)?)\.\s+(?P<title>.+)$',
        r'^\[(?P<series>.+?)\]\s*(?P<title>.+?)\s*-\s*(?P<author>.+)$',
        r'^(?P<series>.+?)\s+-\s+(?P<num>\d{1,2}(?:\.\d)?)\s+-\s+(?P<title>.+?)\s+-\s+(?P<author>.+)$',
        r'^(?P<num>\d{1,2}(?:\.\d)?)\s+[-.]\s+(?P<title>.+?)\s+[-.]\s+(?P<author>.+)$',
        r'^(?P<title>.+?)\s+by\s+(?P<author>.+)$',
        r'^(?P<author>.+?)\s*-\s*(?P<title>.+)$',
        r'^(?P<title>.+?)\s*-\s*(?P<author>.+)$',
        r'^(?P<title>.+?)\s*\((?P<author>.+?)\)$',
        r'^(?P<author_last>[^,]+),\s*(?P<author_first>[^\-]+)\s*-\s*(?P<title>.+)$',
        r'^(?P<title>.+)$'
    ]

    # Pattern matching
    for pattern in patterns:
        match = re.match(pattern, base_name, re.IGNORECASE)
        if not match:
            continue

        groups = match.groupdict()

        # Intelligent resolution
        if "title" in groups and "author" in groups:
            title, authors = resolve_title_author_ambiguity(groups["title"], groups["author"])
            metadata["title"] = title
            metadata["authors"] = authors
        elif "author" in groups:
            metadata["authors"] = normalize_surnames(split_authors(groups["author"]))
        elif "author_first" in groups and "author_last" in groups:
            metadata["authors"] = [f"{groups['author_first'].strip()} {groups['author_last'].strip()}"]

        if "series" in groups:
            metadata["series"] = groups["series"].strip()

        if "num" in groups:
            try:
                metadata["series_number"] = float(groups["num"])
            except ValueError:
                pass

        if not metadata["title"] or not metadata["authors"]:
            title_fallback, author_fallback = fallback_segment_resolution(base_name)
            metadata["title"] = metadata["title"] or title_fallback
            metadata["authors"] = metadata["authors"] or author_fallback

        break  # Use only the first matching pattern

    # Folder-based fallback hints
    folder_clues = extract_folder_clues(path)
    metadata["title"] = metadata["title"] or folder_clues["likely_title"]
    metadata["authors"] = metadata["authors"] or folder_clues["all_authors"]
    metadata["series"] = metadata["series"] or folder_clues["series"]

    # Series number extraction from title
    if metadata["title"]:
        metadata["title"], series_number = clean_title_and_extract_series_number(metadata["title"])
        if series_number is not None:
            metadata["series_number"] = series_number

    return metadata
