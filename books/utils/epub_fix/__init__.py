"""Lossless EPUB fixer package.

Public entry points: :func:`plan_fixes` (dry-run plan), :func:`fix_epub`
(apply fixes to a new file) and :func:`write_epub` (safe writer with optional
cover embedding). Imports the read-only parser from books.utils.epub_check and
never modifies it.
"""

from books.utils.epub_fix.fixer import Fix, plan_fixes
from books.utils.epub_fix.writer import fix_epub, write_epub

__all__ = ["Fix", "plan_fixes", "fix_epub", "write_epub"]
