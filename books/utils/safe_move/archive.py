"""Archive path helpers for the safe-move routine.

Computes where a moved book's original copy is archived, mirroring the scan
folder structure and never overwriting an existing file.
"""

import posixpath
from datetime import datetime
from pathlib import Path

from django.conf import settings

ARCHIVE_FOLDER_NAME = "Archive [To Delete]"


def default_archive_root(scan_root):
    """Return the archive root for a scan root.

    Uses ``settings.ARCHIVE_ROOT`` when set; otherwise a sibling folder named
    ``Archive [To Delete]`` in the same parent as ``scan_root``.
    """
    configured = getattr(settings, "ARCHIVE_ROOT", None)
    if configured:
        return str(configured)
    root = Path(scan_root).resolve()
    return str(root.parent / ARCHIVE_FOLDER_NAME)


def archive_destination(source, scan_root, scan_label, archive_root):
    """Return the archive path for ``source`` (never overwrites an existing file).

    The path is ``<archive_root>/<scan_label>/<path of source relative to
    scan_root>``. Refuses a ``source`` that is not inside ``scan_root`` (after
    resolving symlinks) and an ``archive_root`` that lies inside ``scan_root``.
    On a name collision the returned name gets an ``(archived YYYYmmddTHHMMSS)``
    suffix before the extension, then a counter if that name also exists.
    """
    source_path = Path(source).resolve()
    root_path = Path(scan_root).resolve()
    archive_path = Path(archive_root).resolve()

    try:
        rel = source_path.relative_to(root_path)
    except ValueError:
        raise ValueError(f"source is not inside scan_root: {source}") from None

    if archive_path == root_path or root_path in archive_path.parents:
        raise ValueError(f"archive_root must not lie inside scan_root: {archive_root}")

    dest = archive_path / scan_label / rel

    if dest.exists():
        dest = _collide(dest)

    return str(dest)


def _collide(dest):
    """Return ``dest`` with a timestamp suffix (then a counter) so it is free."""
    stamp = "(archived " + datetime.now().strftime("%Y%m%dT%H%M%S") + ")"
    candidate = dest.with_name(dest.stem + stamp + dest.suffix)
    n = 2
    while candidate.exists():
        candidate = dest.with_name(dest.stem + stamp + f"-{n}" + dest.suffix)
        n += 1
    return candidate
