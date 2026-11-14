"""Tests for the cover quality helper."""

import hashlib
import shutil
import tempfile
from pathlib import Path
from unittest import mock

from django.test import SimpleTestCase
from PIL import Image

from books.utils import cover_quality as cq


def _blocky(width, height, value_fn):
    """Grey image split into an 8x8 grid of blocks, each filled by ``value_fn``.

    The coarse block structure survives the 64x64 thumbnail used by the shape
    check, so the spread / white-fraction statistics stay controllable.
    """
    img = Image.new("L", (width, height))
    px = img.load()
    blocks = 8
    bw = max(1, width // blocks)
    bh = max(1, height // blocks)
    for y in range(height):
        for x in range(width):
            px[x, y] = value_fn(min(x // bw, blocks - 1), min(y // bh, blocks - 1))
    return img


class CoverQualityFlagTests(SimpleTestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: shutil.rmtree(self.temp_dir, ignore_errors=True))

    def test_placeholder_hashes_hold_the_two_measured_values(self):
        # The two placeholder files measured in the 2026-11-13 calibration.
        expected = {
            "5e7f0425abc77878f2a1efe98f12070d7e97b3047d2ce1cd050598230e34e205",
            "3efa8c43e5b4348f303a528c81adf435f0111ea752fe9f0f6241478b60987fa6",
        }
        self.assertEqual(set(cq.PLACEHOLDER_HASHES), expected)

    def test_both_placeholder_hashes_are_flagged(self):
        files = []
        hashes = []
        for i, data in enumerate((b"alpha-file", b"beta-file")):
            p = self.temp_dir / f"ph{i}.jpg"
            p.write_bytes(data)
            files.append(str(p))
            hashes.append(hashlib.sha256(data).hexdigest())
        with mock.patch.object(cq, "PLACEHOLDER_HASHES", set(hashes)):
            self.assertEqual(cq.cover_quality_flag(files[0]), "placeholder")
            self.assertEqual(cq.cover_quality_flag(files[1]), "placeholder")

    def _save(self, img, name):
        p = self.temp_dir / name
        img.save(p)
        return str(p)

    def test_wide_image_flagged_shape(self):
        p = self._save(_blocky(300, 200, lambda bx, by: (bx * 37 + by * 17) % 256), "wide.png")
        self.assertEqual(cq.cover_quality_flag(p), "shape")

    def test_tall_image_flagged_shape(self):
        p = self._save(_blocky(200, 600, lambda bx, by: (bx * 37 + by * 17) % 256), "tall.png")
        self.assertEqual(cq.cover_quality_flag(p), "shape")

    def test_nearly_white_flagged_shape(self):
        p = self._save(_blocky(300, 450, lambda bx, by: 255 if (bx + by) % 5 != 0 else 180), "white.png")
        self.assertEqual(cq.cover_quality_flag(p), "shape")

    def test_flat_grey_flagged_shape(self):
        p = self._save(_blocky(200, 300, lambda bx, by: 128), "flat.png")
        self.assertEqual(cq.cover_quality_flag(p), "shape")

    def test_noisy_portrait_ratio_15_passes(self):
        p = self._save(_blocky(300, 450, lambda bx, by: (bx * 37 + by * 17) % 256), "noisy.png")
        self.assertIsNone(cq.cover_quality_flag(p))

    def test_ratio_exactly_on_limits_passes(self):
        # The ratio check is exclusive (< RATIO_MIN, > RATIO_MAX); patch the
        # limits to clean rationals so integer dimensions land exactly on them.
        with mock.patch.object(cq, "RATIO_MIN", 1.5), mock.patch.object(cq, "RATIO_MAX", 2.0):
            p1 = self._save(_blocky(300, 450, lambda bx, by: (bx * 37 + by * 17) % 256), "rmin.png")
            p2 = self._save(_blocky(300, 600, lambda bx, by: (bx * 37 + by * 17) % 256), "rmax.png")
            self.assertIsNone(cq.cover_quality_flag(p1))
            self.assertIsNone(cq.cover_quality_flag(p2))
