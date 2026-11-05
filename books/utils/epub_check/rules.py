"""Rule registry for the epub_check package.

Each rule is a small, independently registered check with a stable code, a
severity, and a ``detect(reader) -> list[Finding]`` function. New rules are added
with the :func:`register_rule` decorator as the library reveals new problems.
"""

import posixpath
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from typing import Callable, List

from books.utils.epub_check.report import Finding, Severity

XHTML_MEDIA_TYPES = ("application/xhtml+xml", "text/html")

MEDIA_TYPE_BY_EXT = {
    ".xhtml": "application/xhtml+xml",
    ".html": "application/xhtml+xml",
    ".htm": "application/xhtml+xml",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".svg": "image/svg+xml",
    ".css": "text/css",
    ".ncx": "application/x-dtbncx+xml",
    ".opf": "application/oebps-package+xml",
}


@dataclass
class Rule:
    code: str
    severity: Severity
    detect: Callable


_REGISTRY: List[Rule] = []

# Alias: the same mutable list object, so it reflects rules registered below.
ALL_RULES = _REGISTRY


def register_rule(code: str, severity: Severity = Severity.ERROR):
    """Decorator that registers ``fn`` as a rule under ``code``/``severity``."""

    def decorator(fn: Callable) -> Callable:
        _REGISTRY.append(Rule(code=code, severity=severity, detect=fn))
        return fn

    return decorator


def run_all_rules(reader) -> List[Finding]:
    """Run every registered rule against ``reader``, collecting all findings."""
    findings: List[Finding] = []
    for rule in _REGISTRY:
        try:
            findings.extend(rule.detect(reader) or [])
        except Exception as exc:  # a broken rule must never crash the run
            findings.append(Finding(rule.code, rule.severity, f"rule raised: {exc}"))
    return findings


# --------------------------------------------------------------------------- #
# Rule set
# --------------------------------------------------------------------------- #


@register_rule("MIMETYPE-001")
def _rule_mimetype(reader) -> List[Finding]:
    findings: List[Finding] = []
    if reader.mimetype is None:
        return [Finding("MIMETYPE-001", Severity.ERROR, "mimetype entry is missing")]
    if not reader.mimetype["first"]:
        findings.append(Finding("MIMETYPE-001", Severity.ERROR, "mimetype is not the first zip entry"))
    if reader.mimetype["compress_type"] != zipfile.ZIP_STORED:
        findings.append(Finding("MIMETYPE-001", Severity.ERROR, "mimetype is not stored uncompressed"))
    return findings


@register_rule("CONTAINER-001")
def _rule_container(reader) -> List[Finding]:
    if "META-INF/container.xml" not in reader.namelist:
        return [Finding("CONTAINER-001", Severity.ERROR, "META-INF/container.xml is missing")]
    if reader.container_root is None:
        return [Finding("CONTAINER-001", Severity.ERROR, "META-INF/container.xml is not well-formed XML")]
    return []


@register_rule("OPF-001")
def _rule_opf(reader) -> List[Finding]:
    if reader.opf_path is None:
        return [Finding("OPF-001", Severity.ERROR, "no OPF file declared in container.xml")]
    if reader.opf_root is None:
        return [Finding("OPF-001", Severity.ERROR, f"OPF {reader.opf_path} is missing or not well-formed XML")]
    return []


@register_rule("OPF-002")
def _rule_manifest_files(reader) -> List[Finding]:
    findings: List[Finding] = []
    for m in reader.manifest:
        if m["resolved"] not in reader.namelist:
            findings.append(
                Finding(
                    "OPF-002",
                    Severity.ERROR,
                    f"manifest item '{m['id']}' references missing file '{m['href']}'",
                    location=m["href"],
                )
            )
    return findings


@register_rule("OPF-003")
def _rule_spine(reader) -> List[Finding]:
    findings: List[Finding] = []
    manifest_ids = {m["id"] for m in reader.manifest}
    for idref in reader.spine:
        if idref not in manifest_ids:
            findings.append(
                Finding("OPF-003", Severity.ERROR, f"spine idref '{idref}' not found in manifest", location=idref)
            )
    return findings


@register_rule("OPF-004")
def _rule_nav(reader) -> List[Finding]:
    if reader.version == "3.0" and reader.nav_item is None:
        return [Finding("OPF-004", Severity.ERROR, "EPUB 3 requires a nav document (item with properties='nav')")]
    return []


@register_rule("OPF-005", Severity.WARNING)
def _rule_cover(reader) -> List[Finding]:
    findings: List[Finding] = []
    covers = [m for m in reader.manifest if "cover-image" in (m["properties"] or "").split()]
    if not covers:
        return [Finding("OPF-005", Severity.WARNING, "no cover image declared")]
    for c in covers:
        if c["resolved"] not in reader.namelist:
            findings.append(
                Finding(
                    "OPF-005",
                    Severity.WARNING,
                    f"cover image '{c['href']}' declared but missing",
                    location=c["href"],
                )
            )
    return findings


@register_rule("OPF-006")
def _rule_media_types(reader) -> List[Finding]:
    findings: List[Finding] = []
    for m in reader.manifest:
        ext = posixpath.splitext(m["href"] or "")[1].lower()
        expected = MEDIA_TYPE_BY_EXT.get(ext)
        if expected and m["media_type"] and m["media_type"] != expected:
            findings.append(
                Finding(
                    "OPF-006",
                    Severity.ERROR,
                    f"media-type '{m['media_type']}' does not match extension '{ext}' (expected '{expected}')",
                    location=m["href"],
                )
            )
    return findings


@register_rule("HTM-001")
def _rule_xhtml_wellformed(reader) -> List[Finding]:
    findings: List[Finding] = []
    for m in reader.manifest:
        if m["media_type"] in XHTML_MEDIA_TYPES and m["resolved"] in reader.namelist:
            try:
                ET.fromstring(reader.read(m["resolved"]))
            except Exception:
                findings.append(
                    Finding("HTM-001", Severity.ERROR, f"XHTML '{m['href']}' is not well-formed XML", location=m["href"])
                )
    return findings


@register_rule("HTM-002", Severity.WARNING)
def _rule_encoding(reader) -> List[Finding]:
    findings: List[Finding] = []
    for m in reader.manifest:
        if m["media_type"] in XHTML_MEDIA_TYPES and m["resolved"] in reader.namelist:
            head = reader.read(m["resolved"]).decode("utf-8", "replace")[:200]
            if "encoding=" not in head and "charset" not in head.lower():
                findings.append(
                    Finding("HTM-002", Severity.WARNING, f"XHTML '{m['href']}' does not declare a text encoding", location=m["href"])
                )
    return findings
