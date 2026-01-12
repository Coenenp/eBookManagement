"""
Utilities for author name processing and normalization.
"""

import re


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
    if not full_name:
        return "", ""

    # Surname prefixes that should be kept with the last name
    surname_prefixes = {
        "o'",
        "mac",
        "mc",
        "van",
        "von",
        "vander",
        "vonder",
        "van der",
        "von der",
        "van den",
        "von den",
        "vanden",
        "vonden",
        "del",
        "della",
        "d'",
        "du",
        "de",
        "di",
        "ter",
        "lo",
        "gel",
        "van t",
    }

    name_clean = full_name.strip()
    parts = name_clean.replace(",", "").split()

    # If comma-separated, assume inverted format: Last, First
    if "," in full_name and len(parts) >= 2:
        last_name = parts[0]
        first_name = " ".join(parts[1:])
        return first_name, last_name

    # Prefix-aware splitting
    parts = [p.strip() for p in full_name.split()]
    first = []
    last = []

    # Look for surname prefixes starting from each position
    found_prefix = False
    for i in range(len(parts)):
        # Check if any prefix starts at position i
        for prefix in surname_prefixes:
            prefix_parts = prefix.split()
            # Check if we have enough remaining parts to match the prefix
            if i + len(prefix_parts) <= len(parts):
                # Check if the parts match the prefix (case insensitive)
                if all(parts[i + j].lower() == prefix_parts[j] for j in range(len(prefix_parts))):
                    # Found a prefix, everything from here is last name
                    first = parts[:i]
                    last = parts[i:]
                    found_prefix = True
                    break
        if found_prefix:
            break

    # If no prefix found, use traditional splitting (last word as surname)
    if not found_prefix:
        if len(parts) > 1:
            first = parts[:-1]
            last = [parts[-1]]
        else:
            first = []
            last = parts

    first_name = " ".join(first).strip()
    last_name = " ".join(last).strip()

    return first_name, last_name
