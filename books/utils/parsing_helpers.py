import re
from pathlib import Path
from typing import List, Tuple, Dict, Optional


def clean_title_and_extract_series_number(raw_title: str) -> Tuple[str, Optional[float]]:
    """
    Extract leading series number from title string.
    Example: "02 - Book Title" → ("Book Title", 2.0)
    """
    match = re.match(r'^(?P<num>\d{1,2}(?:\.\d)?)[.\- ]+(?P<title>.+)$', raw_title.strip())
    if match:
        title = match.group("title").strip()
        try:
            number = float(match.group("num"))
        except ValueError:
            number = None
        return title, number
    return raw_title.strip(), None


def clean_author_string(raw: str) -> str:
    """
    Remove common format strings from author names.
    Example: "Jane Doe (epub)" → "Jane Doe"
    """
    return re.sub(r'\b(azw3?|epub|mobi|cbz|cbr|azw|pdf|txt)\b', '', raw, flags=re.IGNORECASE).strip()


def split_authors(author_str: str) -> List[str]:
    """
    Split a string of author names into a list.
    Handles commas, ampersands, and conjunctions.
    """
    cleaned = clean_author_string(author_str)
    parts = re.split(r'\s*(?:,|&|and|;)\s*', cleaned)
    return [p.strip() for p in parts if p]


def normalize_surnames(authors: List[str]) -> List[str]:
    """
    Handle prefix-based surname normalization for names like "van Gogh" or "de la Cruz".
    Joins prefix + surname if matched.
    """
    surname_particles = {
        'de', 'del', 'la', 'le', 'von', 'van', 'vanden', 'van den', 'da', 'di',
        'o’', 'mac', 'mc', 'van der', 'von der', 'du', 'd’', 'lo', 'gel', 'ter'
    }
    normalized = []
    i = 0
    while i < len(authors):
        name = authors[i]
        if any(name.lower().startswith(p + ' ') for p in surname_particles):
            normalized.append(name)
        else:
            if i + 1 < len(authors):
                combined = f"{name} {authors[i+1]}"
                if any(authors[i+1].lower().startswith(p) for p in surname_particles):
                    normalized.append(combined)
                    i += 1
                else:
                    normalized.append(name)
            else:
                normalized.append(name)
        i += 1
    return normalized


def extract_folder_clues(path: Path, max_depth: int = 4) -> Dict[str, Optional[str]]:
    """
    Traverse parent folders to extract possible title/author/series hints.
    Returns clues dictionary based on heuristics.
    """
    clues = {
        "likely_title": None,
        "likely_author": None,
        "series": None,
        "all_authors": [],
    }

    folders = [p.name.replace('_', ' ').strip() for p in path.parents[:max_depth]]

    for i, folder_name in enumerate(reversed(folders)):  # From deepest upward
        folder_lower = folder_name.lower()

        if not clues["series"] and "series" in folder_lower:
            clues["series"] = re.sub(r'\bseries\b', '', folder_name, flags=re.IGNORECASE).strip()

        if i == len(folders) - 1 and not clues["likely_author"]:
            if looks_like_author(folder_name):
                clues["likely_author"] = folder_name.strip()
                clues["all_authors"] = [folder_name.strip()]

    return clues


def looks_like_author(text: str) -> bool:
    words = text.strip().split()
    if not (1 <= len(words) <= 4):
        return False

    # Allow titles like "Dr." or initials
    valid_parts = re.compile(r'^[A-Z][a-z]*\.?$|^[A-Z]\.?$|^[A-Z][a-z]+$')
    return all(valid_parts.match(word) for word in words)


def is_probable_author(name: str) -> bool:
    name = name.strip()
    name_lower = name.lower()

    # Flag single or double word names
    words = name.split()
    common_words = {"the", "guide", "history", "manual", "pdf", "ebook"}

    # If it's 1–3 words and doesn't contain typical title terms, assume it's a name
    return (
        1 <= len(words) <= 3
        and not any(word.lower() in common_words for word in words)
        or "unknown" in name_lower
    )


def extract_number_from_filename(filename: str) -> Optional[float]:
    match = re.match(r'^(?P<num>\d{1,2}(?:\.\d)?)[.\- ]+', filename)
    if match:
        try:
            return float(match.group("num"))
        except ValueError:
            pass
    return None


def fallback_segment_resolution(base_name: str) -> Tuple[Optional[str], List[str]]:
    tokens = re.split(r'\s*[-–—]\s*', base_name)
    if len(tokens) < 2:
        return base_name.strip(), []

    scores = [(i, is_probable_author(part)) for i, part in enumerate(tokens)]
    author_index = max(scores, key=lambda tup: tup[1])[0]

    author_segment = normalize_surnames(split_authors(tokens[author_index]))
    title_segment = ' - '.join(p for i, p in enumerate(tokens) if i != author_index)
    return title_segment.strip(), author_segment
