"""EPUB structural checker package.

A pure-Python, rule-based EPUB validator with no Java/EPUBCheck dependency.
Public entry point is :func:`check_epub`.
"""

from books.utils.epub_check.reader import EpubReader
from books.utils.epub_check.report import Finding, Report, Severity
from books.utils.epub_check.rules import run_all_rules

__all__ = ["EpubReader", "Finding", "Report", "Severity", "check_epub", "run_all_rules"]


def check_epub(path) -> Report:
    """Run every registered rule against the EPUB at ``path``.

    Returns a :class:`Report` whose ``findings`` list is empty when the file is
    structurally clean.
    """
    reader = EpubReader(path)
    try:
        findings = run_all_rules(reader)
    finally:
        reader.close()
    return Report(file=str(path), findings=findings)
