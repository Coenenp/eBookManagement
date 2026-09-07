"""
Advanced author matching and deduplication utilities.

This module provides fuzzy matching algorithms to detect potential
duplicate authors that differ in formatting, spacing, or punctuation.
"""

import re
from typing import List, Tuple, Dict
from difflib import SequenceMatcher


def normalize_for_comparison(name: str) -> str:
    """
    Normalize author name for fuzzy comparison.

    Removes punctuation, extra spaces, and converts to lowercase
    for comparison purposes.

    Args:
        name: Author name to normalize

    Returns:
        Normalized name string
    """
    # Convert to lowercase
    normalized = name.lower()

    # Remove all punctuation except spaces
    normalized = re.sub(r"[^\w\s]", "", normalized)

    # Normalize whitespace
    normalized = " ".join(normalized.split())

    return normalized


def calculate_similarity(name1: str, name2: str) -> float:
    """
    Calculate similarity score between two author names.

    Uses multiple strategies:
    1. Exact match on normalized names (score: 1.0)
    2. Sequence matching on normalized names
    3. Initials matching (e.g., "J.K. Rowling" vs "J. K. Rowling")
    4. Reversed name matching (e.g., "Smith, John" vs "John Smith")

    Args:
        name1: First author name
        name2: Second author name

    Returns:
        Similarity score between 0.0 and 1.0
    """
    # Normalize both names
    norm1 = normalize_for_comparison(name1)
    norm2 = normalize_for_comparison(name2)

    # Exact match
    if norm1 == norm2:
        return 1.0

    # Use SequenceMatcher for basic similarity
    base_similarity = SequenceMatcher(None, norm1, norm2).ratio()

    # Check for initials variations
    # "JK Rowling" vs "J K Rowling" should score high
    initials_score = check_initials_match(name1, name2)
    if initials_score > 0.8:
        return max(base_similarity, initials_score)

    # Check for name order reversal
    # "Smith, John" vs "John Smith"
    reversal_score = check_name_reversal(norm1, norm2)
    if reversal_score > 0.8:
        return max(base_similarity, reversal_score)

    return base_similarity


def check_initials_match(name1: str, name2: str) -> float:
    """
    Check if two names differ only in initials spacing/punctuation.

    Examples:
    - "J.K. Rowling" vs "J. K. Rowling" -> 1.0
    - "JK Rowling" vs "J.K. Rowling" -> 1.0
    - "J K Rowling" vs "J.K. Rowling" -> 1.0

    Args:
        name1: First author name
        name2: Second author name

    Returns:
        Similarity score (1.0 if initials match, 0.0 otherwise)
    """

    # Extract initials and remaining parts
    def extract_initials_and_rest(name: str) -> Tuple[str, str]:
        # Normalize the name
        normalized = normalize_for_comparison(name)
        parts = normalized.split()

        initials = []
        rest = []

        for part in parts:
            # Consider it an initial if 1-2 chars
            if len(part) <= 2 and part.isalpha():
                initials.append(part[0])
            else:
                rest.append(part)

        return "".join(initials), " ".join(rest)

    init1, rest1 = extract_initials_and_rest(name1)
    init2, rest2 = extract_initials_and_rest(name2)

    # If initials and rest both match, it's the same name
    if init1 == init2 and rest1 == rest2:
        return 1.0

    return 0.0


def check_name_reversal(norm1: str, norm2: str) -> float:
    """
    Check if two normalized names are reversals of each other.

    Examples:
    - "smith john" vs "john smith" -> 1.0
    - "doe jane mary" vs "mary jane doe" -> 0.9 (partial match)

    Args:
        norm1: First normalized name
        norm2: Second normalized name

    Returns:
        Similarity score based on reversal match
    """
    parts1 = norm1.split()
    parts2 = norm2.split()

    # Check if reversing parts1 gives parts2
    if parts1[::-1] == parts2:
        return 1.0

    # Partial reversal check (first and last swapped)
    if len(parts1) >= 2 and len(parts2) >= 2:
        if parts1[0] == parts2[-1] and parts1[-1] == parts2[0]:
            # At least first and last are swapped
            return 0.9

    return 0.0


def find_potential_duplicates(authors: List[Tuple[int, str]], threshold: float = 0.85) -> List[Dict]:
    """
    Find potential duplicate authors using fuzzy matching.

    Args:
        authors: List of (id, name) tuples
        threshold: Minimum similarity score to consider as duplicate (0.0-1.0)

    Returns:
        List of duplicate groups, each containing:
        {
            'similarity': float,
            'authors': [(id1, name1), (id2, name2), ...]
        }
    """
    duplicates = []
    checked_pairs = set()

    # Compare each author with every other author
    for i, (id1, name1) in enumerate(authors):
        for id2, name2 in authors[i + 1 :]:
            # Skip if already checked
            pair_key = tuple(sorted([id1, id2]))
            if pair_key in checked_pairs:
                continue

            checked_pairs.add(pair_key)

            # Calculate similarity
            similarity = calculate_similarity(name1, name2)

            if similarity >= threshold:
                # Check if either author is already in a duplicate group
                found_group = None
                for dup_group in duplicates:
                    group_ids = [a[0] for a in dup_group["authors"]]
                    if id1 in group_ids or id2 in group_ids:
                        found_group = dup_group
                        break

                if found_group:
                    # Add to existing group
                    existing_ids = [a[0] for a in found_group["authors"]]
                    if id1 not in existing_ids:
                        found_group["authors"].append((id1, name1))
                    if id2 not in existing_ids:
                        found_group["authors"].append((id2, name2))
                    # Update similarity to average
                    found_group["similarity"] = (found_group["similarity"] + similarity) / 2
                else:
                    # Create new group
                    duplicates.append({"similarity": similarity, "authors": [(id1, name1), (id2, name2)]})

    # Sort by similarity (highest first)
    duplicates.sort(key=lambda x: x["similarity"], reverse=True)

    return duplicates


def suggest_canonical_name(names: List[str]) -> str:
    """
    Suggest the best canonical name from a list of variations.

    Prefers:
    1. Names with proper capitalization
    2. Names with full initials (with periods)
    3. Longer, more complete names

    Args:
        names: List of name variations

    Returns:
        Suggested canonical name
    """
    if not names:
        return ""

    # Score each name
    scores = []
    for name in names:
        score = 0

        # Prefer proper capitalization (not all lowercase)
        if not name.islower():
            score += 10

        # Prefer names with periods in initials (J.K. vs JK)
        if "." in name:
            score += 5

        # Prefer longer names (more complete)
        score += len(name)

        # Prefer names with capital letters at word starts
        words = name.split()
        for word in words:
            if word and word[0].isupper():
                score += 2

        scores.append((score, name))

    # Return name with highest score
    scores.sort(reverse=True)
    return scores[0][1]


def estimate_duplicate_count(total_authors: int, sample_duplicates: int, sample_size: int) -> int:
    """
    Estimate total number of duplicates in full author database
    based on a sample.

    Args:
        total_authors: Total number of authors in database
        sample_duplicates: Number of duplicates found in sample
        sample_size: Size of sample checked

    Returns:
        Estimated total duplicate count
    """
    if sample_size == 0:
        return 0

    duplicate_rate = sample_duplicates / sample_size
    estimated_total = int(total_authors * duplicate_rate)

    return estimated_total
