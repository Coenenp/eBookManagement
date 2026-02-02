"""
File collision handling utilities.

Provides Windows-style collision resolution for file renaming operations.
"""

from pathlib import Path
from typing import Optional


def resolve_collision(target_path: str, max_attempts: int = 999) -> str:
    """
    Resolve filename collision by adding Windows-style suffix: (2), (3), etc.

    Args:
        target_path: The desired target file path
        max_attempts: Maximum number of collision resolution attempts

    Returns:
        A non-colliding file path with suffix if needed

    Examples:
        If "book.epub" exists:
            - First collision: "book (2).epub"
            - Second collision: "book (3).epub"
            - etc.
    """
    path = Path(target_path)

    # If target doesn't exist, no collision
    if not path.exists():
        return target_path

    # Extract components
    parent = path.parent
    stem = path.stem  # Filename without extension
    suffix = path.suffix  # Extension including dot

    # Try to find a non-colliding name
    for i in range(2, max_attempts + 2):
        new_stem = f"{stem} ({i})"
        new_path = parent / f"{new_stem}{suffix}"

        if not new_path.exists():
            return str(new_path)

    # If we've exhausted all attempts, raise an error
    raise RuntimeError(f"Could not resolve collision for {target_path} after {max_attempts} attempts")


def get_collision_suffix(original_path: str, resolved_path: str) -> Optional[str]:
    """
    Extract the collision suffix from a resolved path.

    Args:
        original_path: The original target path
        resolved_path: The resolved path with potential suffix

    Returns:
        The suffix (e.g., " (2)", " (3)") or None if no collision

    Examples:
        >>> get_collision_suffix("book.epub", "book (2).epub")
        " (2)"
        >>> get_collision_suffix("book.epub", "book.epub")
        None
    """
    if original_path == resolved_path:
        return None

    orig_path = Path(original_path)
    res_path = Path(resolved_path)

    # Compare stems (filename without extension)
    orig_stem = orig_path.stem
    res_stem = res_path.stem

    # Extract suffix
    if res_stem.startswith(orig_stem):
        suffix = res_stem[len(orig_stem) :]
        # Verify it matches pattern " (N)"
        if suffix.startswith(" (") and suffix.endswith(")"):
            return suffix

    return None


def apply_suffix_to_path(path: str, suffix: Optional[str]) -> str:
    """
    Apply a collision suffix to a path.

    Args:
        path: The original file path
        suffix: The suffix to apply (e.g., " (2)"), or None for no change

    Returns:
        The path with suffix applied

    Examples:
        >>> apply_suffix_to_path("cover.jpg", " (2)")
        "cover (2).jpg"
        >>> apply_suffix_to_path("cover.jpg", None)
        "cover.jpg"
    """
    if suffix is None:
        return path

    path_obj = Path(path)
    stem = path_obj.stem
    ext = path_obj.suffix
    parent = path_obj.parent

    new_stem = f"{stem}{suffix}"
    return str(parent / f"{new_stem}{ext}")
