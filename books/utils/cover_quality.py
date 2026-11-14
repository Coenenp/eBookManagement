"""Cover quality checks: placeholder detection and shape thresholds.

``cover_quality_flag`` classifies a cover image file so that placeholder
graphics (a source's "no image available" / silhouette) and malformed covers
can be excluded from approval and skipped during download.

Thresholds are measured, not invented: they come from the 2026-11-13
calibration in ``/workspace/state/cover_calibration_20261113.txt`` and are
chosen so that every proper / doubtful / small cover stays on the pass side.
"""

import hashlib
from pathlib import Path

# Full sha256 values of the two known placeholder files, measured 2026-11-13
# (see /workspace/state/cover_calibration_20261113.txt).
PLACEHOLDER_HASHES = {
    # grey silhouette placeholder (shared by books 57 and 94)
    "5e7f0425abc77878f2a1efe98f12070d7e97b3047d2ce1cd050598230e34e205",
    # "image not available" graphic (shared by books 69 and 78)
    "3efa8c43e5b4348f303a528c81adf435f0111ea752fe9f0f6241478b60987fa6",
}

# Shape thresholds measured 2026-11-13 (cover_calibration_20261113.txt).
# The pass side (proper + doubtful + small) spans these ranges; an image whose
# ratio, grey-scale standard deviation or white fraction falls outside them is
# rejected as "shape".
RATIO_MIN = 1.26574
RATIO_MAX = 1.77305
STD_MIN = 15.0653
STD_MAX = 89.9076
WHITE_MAX = 0.732178

THUMB_SIZE = 64
WHITE_LUMINANCE = 240


def _shape_rejected(im):
    """Return True when a grey-scale image trips a measured shape threshold."""
    width, height = im.size
    if width <= 0 or height <= 0:
        return False
    ratio = height / width
    if ratio < RATIO_MIN or ratio > RATIO_MAX:
        return True
    thumb = im.resize((THUMB_SIZE, THUMB_SIZE))
    pixels = list(thumb.getdata())
    n = len(pixels)
    mean = sum(pixels) / n
    var = sum((p - mean) ** 2 for p in pixels) / n
    std = var ** 0.5
    if std < STD_MIN or std > STD_MAX:
        return True
    white = sum(1 for p in pixels if p >= WHITE_LUMINANCE) / n
    if white > WHITE_MAX:
        return True
    return False


def cover_quality_flag(path):
    """Return ``"placeholder"``, ``"shape"`` or ``None`` for a cover file.

    ``None`` means the cover is not flagged (it is either absent/unreadable,
    or it passes every check). A placeholder (hash match) is reported before
    any shape test.
    """
    if not path:
        return None
    try:
        data = Path(path).read_bytes()
    except OSError:
        return None
    if hashlib.sha256(data).hexdigest() in PLACEHOLDER_HASHES:
        return "placeholder"
    try:
        from PIL import Image

        im = Image.open(path).convert("L")
    except Exception:
        return None
    if _shape_rejected(im):
        return "shape"
    return None
