import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple


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
    # Remove format strings in parentheses
    cleaned = re.sub(r'\s*\([^)]*(?:azw3?|epub|mobi|cbz|cbr|azw|pdf|txt)[^)]*\)', '', raw, flags=re.IGNORECASE)
    # Remove standalone format words
    cleaned = re.sub(r'\b(azw3?|epub|mobi|cbz|cbr|azw|pdf|txt)\b', '', cleaned, flags=re.IGNORECASE)
    # Clean up extra whitespace and empty parentheses
    cleaned = re.sub(r'\s*\(\s*\)', '', cleaned)
    return cleaned.strip()


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
    # Extended list including multi-word prefixes the user mentioned
    surname_particles = {
        'de', 'del', 'dela', 'la', 'le', 'von', 'van', 'vanden', 'van den', 'van der', 'van de',
        'da', 'di', 'o', 'mac', 'mc', 'von der', 'du', 'd', 'lo', 'gel', 'ter',
        'den', 'der', 'dos', 'das', 'ibn', 'bin', 'ben', 'abd', 'abu', 'al'
    }

    normalized = []
    i = 0
    while i < len(authors):
        current_token = authors[i].strip()

        # Check if current token is a surname prefix
        if current_token.lower() in surname_particles:
            # Combine with next token(s) to form complete name
            combined_parts = [current_token]
            i += 1

            # Keep adding tokens while they are either prefixes or the final surname
            while i < len(authors):
                next_token = authors[i].strip()
                combined_parts.append(next_token)
                i += 1

                # If this token is not a prefix, we've found the surname - stop here
                if next_token.lower() not in surname_particles:
                    break

            # Join all parts to form the complete name
            normalized.append(' '.join(combined_parts))
        else:
            # Regular token - check if we should combine with following prefix
            if i + 1 < len(authors) and authors[i + 1].lower() in surname_particles:
                # This is the first name, and next token is a prefix
                # Combine all following tokens until we get the complete surname
                combined_parts = [current_token]
                i += 1

                while i < len(authors):
                    next_token = authors[i].strip()
                    combined_parts.append(next_token)
                    i += 1

                    # If this token is not a prefix, we've completed the surname
                    if next_token.lower() not in surname_particles:
                        break

                normalized.append(' '.join(combined_parts))
            else:
                # Standalone token
                normalized.append(current_token)
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

    # Allow titles like "Dr." or initials like "J.R.R."
    valid_parts = re.compile(r'^[A-Z][a-z]*\.?$|^[A-Z]\.?$|^[A-Z][a-z]+$|^[A-Z]\.([A-Z]\.)*[A-Z]?\.?$')
    return all(valid_parts.match(word) for word in words)


def is_probable_author(name: str) -> bool:
    name = name.strip()
    name_lower = name.lower()

    # Flag single or double word names
    words = name.split()

    # Strong title indicators that make it unlikely to be an author
    title_words = {
        "book", "title", "story", "novel", "guide", "manual", "pdf", "ebook",
        "history", "complete", "adventures", "mystery", "romance", "fantasy",
        "science", "collection", "anthology", "tales", "volume", "part",
        "chapter", "series", "edition", "revised", "updated"
    }

    # Check if any word is a strong title indicator
    if any(word.lower() in title_words for word in words):
        return False

    # If it's 1–3 words and doesn't contain typical title terms, assume it's a name
    return (
        1 <= len(words) <= 3
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

    # Original logic: find the segment with highest score
    # Only use position-based tiebreaking for 3+ segments where all have equal scores
    max_score = max(score for _, score in scores)
    candidates = [i for i, score in scores if score == max_score]

    if len(tokens) >= 3 and len(candidates) == len(tokens) and all(score == max_score for _, score in scores):
        # Special case: all segments have equal scores in 3+ segment scenario
        # Prefer the last segment as it's more likely to be an author name
        author_index = candidates[-1]
    else:
        # Use original logic: first occurrence of max score
        author_index = max(scores, key=lambda tup: tup[1])[0]

    author_segment = normalize_surnames(split_authors(tokens[author_index]))
    title_segment = ' - '.join(p for i, p in enumerate(tokens) if i != author_index)
    return title_segment.strip(), author_segment
