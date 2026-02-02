"""
EPUB metadata embedding and manipulation utilities.

This module provides functionality to embed metadata, covers, and OPF data
directly into EPUB files rather than maintaining external companion files.

It also includes validation and repair functionality to fix common EPUB
structural issues, as well as preview and diff utilities for showing
changes before they are applied.
"""

from .diff import (
    FileDiff,
    generate_file_diff,
    generate_opf_diff_summary,
    generate_unified_diff,
)
from .inspector import (
    EPUBFile,
    EPUBStructure,
    get_file_tree,
    inspect_epub,
)
from .metadata_embedder import embed_metadata_in_epub
from .preview import (
    EPUBMetadataPreview,
    generate_preview_summary,
    preview_metadata_changes,
)
from .structure_fixer import (
    EPUBValidationIssues,
    repair_epub_structure,
    validate_epub_structure,
)

__all__ = [
    "embed_metadata_in_epub",
    "validate_epub_structure",
    "repair_epub_structure",
    "EPUBValidationIssues",
    "inspect_epub",
    "EPUBStructure",
    "EPUBFile",
    "get_file_tree",
    "preview_metadata_changes",
    "EPUBMetadataPreview",
    "generate_preview_summary",
    "generate_file_diff",
    "generate_unified_diff",
    "generate_opf_diff_summary",
    "FileDiff",
]
