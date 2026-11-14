"""Tests for the cover quality helper."""

import hashlib
import shutil
import tempfile
from pathlib import Path
from unittest import mock

from django.test import SimpleTestCase

from books.utils import cover_quality as cq


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
