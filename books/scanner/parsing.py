"""Filename and metadata parsing utilities.

This module provides functions for parsing ebook filenames to extract
metadata like titles, authors, series information, and publication data.
Enhanced with AI-powered pattern recognition.
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

    # Check if either part contains multiple authors (comma-separated)
    def contains_multiple_authors(text: str) -> bool:
        return ',' in text and len([p.strip() for p in text.split(',') if p.strip()]) > 1

    # Check if text looks like author names (including multiple authors)
    def looks_like_authors(text: str) -> bool:
        if contains_multiple_authors(text):
            # Check if each comma-separated part looks like a name
            parts = [p.strip() for p in text.split(',') if p.strip()]
            return all(is_probable_author(part) for part in parts)
        else:
            return is_probable_author(text)

    # Special case: If one part has multiple authors (comma-separated), prioritize it
    if contains_multiple_authors(part1_clean) and looks_like_authors(part1_clean):
        return part2_clean, normalize_surnames(split_authors(part1_clean))
    elif contains_multiple_authors(part2_clean) and looks_like_authors(part2_clean):
        return part1_clean, normalize_surnames(split_authors(part2_clean))

    # For non-comma cases, use original logic
    elif is_probable_author(part1_clean) and not is_probable_author(part2_clean):
        return part2_clean, normalize_surnames(split_authors(part1_clean))
    elif is_probable_author(part2_clean) and not is_probable_author(part1_clean):
        return part1_clean, normalize_surnames(split_authors(part2_clean))
    else:
        # Fall back on punctuation density: titles tend to have more punctuation
        punc_score_1 = sum(part1_clean.count(p) for p in ":,-()")
        punc_score_2 = sum(part2_clean.count(p) for p in ":,-()")
        if punc_score_1 > punc_score_2:
            return part2_clean, normalize_surnames(split_authors(part1_clean))
        elif punc_score_2 > punc_score_1:
            return part1_clean, normalize_surnames(split_authors(part2_clean))
        else:
            # Equal punctuation: default to second part as title
            return part2_clean, normalize_surnames(split_authors(part1_clean))


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
        r'^(?P<author_last>[^,]+),\s*(?P<author_first>[^\-]+)\s*-\s*(?P<title>.+)$',  # Move this before general patterns
        r'^(?P<author>.+?)\s*-\s*(?P<title>.+)$',
        r'^(?P<title>.+?)\s*-\s*(?P<author>.+)$',
        r'^(?P<title>.+?)\s*\((?P<author>.+?)\)$',
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
            # Handle "Last, First - Title" format correctly
            # Pattern captures: author_last="Doe", author_first="John" from "Doe, John - Title"
            # So we need to put first name first: "John Doe"
            full_name = f"{groups['author_first'].strip()} {groups['author_last'].strip()}"
            metadata["authors"] = [full_name]
            if "title" in groups:
                metadata["title"] = groups["title"].strip()

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


def parse_comic_metadata(file_path: str) -> Dict[str, Optional[str]]:
    """Specialized parsing for comic book files (CBR/CBZ).

    Handles common comic filename patterns like:
    - Series - Issue# - Title (extra info)
    - Series Issue# Title

    And extracts folder-based author information from known comic creators.
    """
    path = Path(file_path)
    base_name = path.stem.replace('_', ' ').strip()

    metadata = {
        "title": None,
        "authors": [],
        "series": None,
        "series_number": None
    }

    # Comic-specific patterns
    comic_patterns = [
        # "De Rode Ridder - 271 - De kruisvaarder (Digitale rip)"
        r'^(?P<series>.+?)\s+-\s+(?P<num>\d{1,3}(?:\.\d+)?)\s+-\s+(?P<title>.+?)(?:\s+\([^)]*\))?$',
        # "Batman 15 - The Dark Knight Returns"
        r'^(?P<series>.+?)\s+(?P<num>\d{1,3}(?:\.\d+)?)\s+-\s+(?P<title>.+)$',
        # "Superman #42 Return of Doomsday"
        r'^(?P<series>.+?)\s+#(?P<num>\d{1,3}(?:\.\d+)?)\s+(?P<title>.+)$',
        # "X-Men Issue 100"
        r'^(?P<series>.+?)\s+Issue\s+(?P<num>\d{1,3}(?:\.\d+)?)\s+(?P<title>.+)$',
    ]

    # Try comic-specific patterns first
    for pattern in comic_patterns:
        match = re.match(pattern, base_name, re.IGNORECASE)
        if match:
            groups = match.groupdict()
            metadata["series"] = groups.get("series", "").strip()
            metadata["title"] = groups.get("title", "").strip()
            if "num" in groups:
                try:
                    metadata["series_number"] = float(groups["num"])
                except ValueError:
                    pass
            break

    # If no comic pattern matched, fall back to basic extraction
    if not metadata["series"] and not metadata["title"]:
        # Extract series and issue number from any format
        series_match = re.match(r'^(.+?)\s+(\d{1,3}(?:\.\d+)?)', base_name)
        if series_match:
            metadata["series"] = series_match.group(1).strip()
            try:
                metadata["series_number"] = float(series_match.group(2))
            except ValueError:
                pass
        else:
            metadata["title"] = base_name

    # Extract author from folder structure for known comic creators
    folder_clues = extract_folder_clues(path)
    comic_authors = _extract_comic_author_from_folders(path)

    # Prefer comic-specific author detection
    metadata["authors"] = comic_authors or folder_clues.get("all_authors", [])

    return metadata


def _extract_comic_author_from_folders(path: Path) -> List[str]:
    """Extract comic book author from folder structure using known creators."""
    # Known comic creators and their series
    known_creators = {
        'willy vandersteen': ['de rode ridder', 'suske en wiske', 'bessy'],
        'marc sleen': ['nero'],
        'stan lee': ['spider-man', 'x-men', 'fantastic four', 'iron man', 'hulk'],
        'frank miller': ['sin city', 'daredevil', 'batman dark knight'],
        'alan moore': ['watchmen', 'v for vendetta', 'league of extraordinary gentlemen'],
        'neil gaiman': ['sandman', 'american gods'],
        'grant morrison': ['batman', 'new x-men'],
        'hergé': ['tintin', 'kuifje'],
        'peyo': ['smurf', 'smurfen'],
        'morris': ['lucky luke'],
        'goscinny': ['asterix', 'lucky luke'],
        'uderzo': ['asterix'],
    }

    folders = [p.name.replace('_', ' ').strip().lower() for p in path.parents[:4]]

    # Check folder names for creator names or series
    for folder_name in folders:
        # Direct creator name match
        for creator, series_list in known_creators.items():
            if creator in folder_name:
                return [creator.title()]

            # Check if any of the creator's series appear in folder structure
            for series in series_list:
                if series in folder_name:
                    return [creator.title()]

    return []


def parse_path_metadata_with_ai(file_path: str, ai_recognizer=None) -> Dict[str, Optional[str]]:
    """Enhanced parsing that combines traditional pattern matching with AI predictions."""
    # Get traditional parsing results
    traditional_metadata = parse_path_metadata(file_path)

    # If AI recognizer is not available, return traditional results
    if not ai_recognizer:
        return traditional_metadata

    try:
        # Get AI predictions
        filename = Path(file_path).stem
        ai_predictions = ai_recognizer.predict_metadata(filename)

        # Combine traditional and AI results with confidence-based selection
        enhanced_metadata = traditional_metadata.copy()
        ai_confidence_used = {}

        for field, (ai_value, confidence) in ai_predictions.items():
            # Map AI field names to our metadata keys
            field_mapping = {
                'title': 'title',
                'author': 'authors',
                'series': 'series',
                'volume': 'series_number'
            }

            if field in field_mapping:
                metadata_key = field_mapping[field]

                # Use AI prediction if confident and traditional method didn't find anything
                # or if AI is highly confident (> 0.8)
                should_use_ai = (
                    confidence >= ai_recognizer.confidence_threshold and
                    (not enhanced_metadata.get(metadata_key) or confidence > 0.8)
                )

                if should_use_ai and ai_value.strip():
                    if metadata_key == 'authors':
                        # Handle authors specially - split and normalize
                        enhanced_metadata[metadata_key] = normalize_surnames(split_authors(ai_value))
                    else:
                        enhanced_metadata[metadata_key] = ai_value.strip()

                    ai_confidence_used[field] = confidence

        # Add metadata source information
        enhanced_metadata['_ai_used'] = ai_confidence_used

        return enhanced_metadata

    except Exception as e:
        # If AI processing fails, fall back to traditional parsing
        import logging
        logger = logging.getLogger("books.scanner")
        logger.warning(f"AI parsing failed for '{file_path}': {e}")
        return traditional_metadata
