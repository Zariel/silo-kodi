from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'plugin.video.silo.kodi/resources/lib'))
from silo.client import Error
from silo.tracks import NativeTracks


class TrackCorrespondence(unittest.TestCase):
    def test_correspondence_is_unique_in_both_directions(self):
        sources = ['main', 'commentary']
        mapping = NativeTracks(sources, lambda source, native: source == native['name'], 'unmapped')
        streams = [{'index': 5, 'name': 'commentary'}, {'index': 9, 'name': 'main'}]
        self.assertEqual(mapping.native_index(0, streams), 9)
        self.assertEqual(mapping.source_index(streams, 5), 1)
        with self.assertRaises(Error):
            mapping.native_index(-1, streams)
        with self.assertRaises(Error):
            mapping.source_index(streams, 0)
        with self.assertRaises(Error):
            mapping.native_index(0, [{'index': 9, 'name': 'main'}, {'index': 9, 'name': 'commentary'}])
        sources.append('main')
        with self.assertRaises(Error):
            mapping.native_index(0, streams)
        with self.assertRaises(Error):
            mapping.source_index(streams, 9)
