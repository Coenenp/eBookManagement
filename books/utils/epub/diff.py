"""
EPUB diff generation utilities.

Generates unified and side-by-side diffs for EPUB content comparisons.
"""

import difflib
import logging
from dataclasses import dataclass
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class DiffLine:
    """Represents a single line in a diff."""

    line_type: str  # 'add', 'remove', 'context', 'header'
    content: str
    line_number_old: Optional[int] = None
    line_number_new: Optional[int] = None


@dataclass
class FileDiff:
    """Represents a diff between two file versions."""

    filename: str
    diff_type: str  # 'modified', 'added', 'removed', 'unchanged'
    unified_diff: str
    side_by_side: List[Tuple[Optional[str], Optional[str]]]  # (old_line, new_line)
    lines_added: int
    lines_removed: int
    lines_changed: int

    @property
    def has_changes(self) -> bool:
        """Check if file has any changes."""
        return self.diff_type != "unchanged"


def generate_unified_diff(original: str, modified: str, filename: str = "file") -> str:
    """
    Generate unified diff between two text strings.

    Args:
        original: Original content
        modified: Modified content
        filename: Filename for diff header

    Returns:
        Unified diff as string
    """
    original_lines = original.splitlines(keepends=True)
    modified_lines = modified.splitlines(keepends=True)

    diff = difflib.unified_diff(original_lines, modified_lines, fromfile=f"{filename} (before)", tofile=f"{filename} (after)", lineterm="")

    return "".join(diff)


def generate_side_by_side_diff(original: str, modified: str) -> List[Tuple[Optional[str], Optional[str]]]:
    """
    Generate side-by-side diff for display.

    Args:
        original: Original content
        modified: Modified content

    Returns:
        List of tuples (old_line, new_line) for side-by-side display
    """
    original_lines = original.splitlines()
    modified_lines = modified.splitlines()

    # Use SequenceMatcher for side-by-side alignment
    matcher = difflib.SequenceMatcher(None, original_lines, modified_lines)

    result = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            # Lines are the same
            for i, j in zip(range(i1, i2), range(j1, j2)):
                result.append((original_lines[i], modified_lines[j]))

        elif tag == "replace":
            # Lines replaced
            max_len = max(i2 - i1, j2 - j1)
            for k in range(max_len):
                old_line = original_lines[i1 + k] if (i1 + k) < i2 else None
                new_line = modified_lines[j1 + k] if (j1 + k) < j2 else None
                result.append((old_line, new_line))

        elif tag == "delete":
            # Lines removed from original
            for i in range(i1, i2):
                result.append((original_lines[i], None))

        elif tag == "insert":
            # Lines added to modified
            for j in range(j1, j2):
                result.append((None, modified_lines[j]))

    return result


def generate_file_diff(original: str, modified: str, filename: str) -> FileDiff:
    """
    Generate complete diff for a file.

    Args:
        original: Original file content
        modified: Modified file content
        filename: Filename for display

    Returns:
        FileDiff object with unified and side-by-side diffs
    """
    # Determine diff type
    if original == modified:
        diff_type = "unchanged"
    elif not original:
        diff_type = "added"
    elif not modified:
        diff_type = "removed"
    else:
        diff_type = "modified"

    # Generate unified diff
    unified = generate_unified_diff(original, modified, filename)

    # Generate side-by-side diff
    side_by_side = generate_side_by_side_diff(original, modified)

    # Count changes
    lines_added = sum(1 for old, new in side_by_side if old is None and new is not None)
    lines_removed = sum(1 for old, new in side_by_side if old is not None and new is None)
    lines_changed = sum(1 for old, new in side_by_side if old is not None and new is not None and old != new)

    return FileDiff(
        filename=filename, diff_type=diff_type, unified_diff=unified, side_by_side=side_by_side, lines_added=lines_added, lines_removed=lines_removed, lines_changed=lines_changed
    )


def format_side_by_side_html(diff: FileDiff, context_lines: int = 3) -> str:
    """
    Format side-by-side diff as HTML.

    Args:
        diff: FileDiff object
        context_lines: Number of context lines to show around changes

    Returns:
        HTML string
    """
    if not diff.has_changes:
        return '<div class="diff-no-changes">No changes</div>'

    html_lines = []
    html_lines.append('<table class="diff-table">')
    html_lines.append("<thead><tr>")
    html_lines.append('<th class="line-num">Old</th>')
    html_lines.append('<th class="diff-content">Before</th>')
    html_lines.append('<th class="line-num">New</th>')
    html_lines.append('<th class="diff-content">After</th>')
    html_lines.append("</tr></thead>")
    html_lines.append("<tbody>")

    old_line_num = 1
    new_line_num = 1

    for old_line, new_line in diff.side_by_side:
        if old_line == new_line and old_line is not None:
            # Unchanged line
            row_class = "diff-equal"
            html_lines.append(f'<tr class="{row_class}">')
            html_lines.append(f'<td class="line-num">{old_line_num}</td>')
            html_lines.append(f'<td class="diff-content"><pre>{_escape_html(old_line)}</pre></td>')
            html_lines.append(f'<td class="line-num">{new_line_num}</td>')
            html_lines.append(f'<td class="diff-content"><pre>{_escape_html(new_line)}</pre></td>')
            html_lines.append("</tr>")
            old_line_num += 1
            new_line_num += 1

        elif old_line is None:
            # Added line
            html_lines.append('<tr class="diff-add">')
            html_lines.append('<td class="line-num"></td>')
            html_lines.append('<td class="diff-content"></td>')
            html_lines.append(f'<td class="line-num">{new_line_num}</td>')
            html_lines.append(f'<td class="diff-content"><pre>+ {_escape_html(new_line)}</pre></td>')
            html_lines.append("</tr>")
            new_line_num += 1

        elif new_line is None:
            # Removed line
            html_lines.append('<tr class="diff-remove">')
            html_lines.append(f'<td class="line-num">{old_line_num}</td>')
            html_lines.append(f'<td class="diff-content"><pre>- {_escape_html(old_line)}</pre></td>')
            html_lines.append('<td class="line-num"></td>')
            html_lines.append('<td class="diff-content"></td>')
            html_lines.append("</tr>")
            old_line_num += 1

        else:
            # Changed line
            html_lines.append('<tr class="diff-change">')
            html_lines.append(f'<td class="line-num">{old_line_num}</td>')
            html_lines.append(f'<td class="diff-content"><pre>- {_escape_html(old_line)}</pre></td>')
            html_lines.append(f'<td class="line-num">{new_line_num}</td>')
            html_lines.append(f'<td class="diff-content"><pre>+ {_escape_html(new_line)}</pre></td>')
            html_lines.append("</tr>")
            old_line_num += 1
            new_line_num += 1

    html_lines.append("</tbody>")
    html_lines.append("</table>")

    return "\n".join(html_lines)


def _escape_html(text: str) -> str:
    """Escape HTML special characters."""
    if text is None:
        return ""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;").replace("'", "&#x27;")


def generate_opf_diff_summary(original_opf: str, modified_opf: str) -> dict:
    """
    Generate summary of OPF changes for quick review.

    Args:
        original_opf: Original OPF content
        modified_opf: Modified OPF content

    Returns:
        Dictionary with diff summary
    """
    diff = generate_file_diff(original_opf, modified_opf, "content.opf")

    return {
        "has_changes": diff.has_changes,
        "lines_added": diff.lines_added,
        "lines_removed": diff.lines_removed,
        "lines_changed": diff.lines_changed,
        "unified_diff": diff.unified_diff,
        "side_by_side_html": format_side_by_side_html(diff),
    }
