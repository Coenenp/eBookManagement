"""
Utilities for author name processing and normalization.
"""

import re


def clean_author_name(raw_name):
    """
    Clean author name by removing invalid patterns like years, birth/death dates, etc.

    Args:
        raw_name (str): Raw author name from any source

    Returns:
        str: Cleaned author name, or empty string if invalid
    """
    if not raw_name or not raw_name.strip():
        return ""

    name = raw_name.strip()

    # Reject standalone 4-digit years (1900-2099)
    if re.match(r"^(19|20)\d{2}$", name):
        return ""

    # Remove birth/death dates in various formats
    # "Michael 1973-" or "Author 1950-2020"
    name = re.sub(r"\s*\d{4}\s*[-–—]\s*\d{0,4}\s*$", "", name)
    name = re.sub(r"\s*\d{4}\s*[-–—]\s*\d{0,4}\s*", " ", name)

    # Remove dates in parentheses: "Author (1950-2020)" or "Author (1950-)"
    name = re.sub(r"\s*\(\s*\d{4}\s*[-–—]\s*\d{0,4}\s*\)", "", name)

    # Remove "ca." or "c." (circa) dates: "Author ca. 1950"
    name = re.sub(r"\s*\b(ca?\.|circa)\s*\d{4}", "", name, flags=re.IGNORECASE)

    # Remove trailing punctuation and clean up whitespace
    name = re.sub(r"[,;:\-–—]+$", "", name)
    name = " ".join(name.split())

    # Reject if result is empty, too short, or still contains just a year
    if len(name) < 2:
        return ""
    if re.match(r"^(19|20)\d{2}$", name):
        return ""

    # Normalize common format issues
    # Fix excessive spaces around periods: "J . R . R" -> "J.R.R"
    name = re.sub(r"(\w)\s+\.\s+", r"\1.", name)
    name = re.sub(r"(\w)\s+\.(\w)", r"\1.\2", name)

    return name.strip()


def normalize_author_name(name):
    """Normalize author name for consistent comparison."""
    name = re.sub(r"[^\w\s]", "", name.lower().strip())
    return " ".join(name.split())


def parse_author_name(full_name):
    """
    Parse a full author name into first_name and last_name components.

    Args:
        full_name (str): The full author name to parse

    Returns:
        tuple: (first_name, last_name)
    """
    from books.utils.surname_particles import split_author

    return split_author(full_name)
