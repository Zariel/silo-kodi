from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'plugin.video.silo/resources/lib'))
from silo.markers import intro_range, intro_at


class Markers(unittest.TestCase):
    def test_intro_bounds_and_source_duration(self):
        segment = intro_range({'start': 10, 'end': 80})
        self.assertEqual(segment, (10, 80))
        self.assertIsNone(intro_at(segment, 9, 600))
        self.assertEqual(intro_at(segment, 10, 600), (10, 80))
        self.assertIsNone(intro_at(segment, 80, 600))
        self.assertIsNone(intro_at(segment, 20, 60))
        self.assertIsNone(intro_at(segment, 20, 80))

    def test_missing_or_invalid_markers_never_offer_skip(self):
        for marker in (None, {}, {'start': 2}, {'start': -1, 'end': 30},
                       {'start': 30, 'end': 30}, {'start': True, 'end': 30},
                       {'start': '0', 'end': 30}, {'start': 0, 'end': float('inf')}):
            self.assertIsNone(intro_range(marker))
