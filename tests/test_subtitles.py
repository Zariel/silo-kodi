from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'plugin.video.silo.kodi/resources/lib'))
from silo.client import Error
from silo.subtitles import SourceSubtitles


class Subtitles(unittest.TestCase):
    def setUp(self):
        self.tracks = [
            {'index': 8, 'codec': 'hdmv_pgs_subtitle', 'language': 'en', 'title': 'English',
             'embedded_title': 'English', 'default': False, 'forced': False, 'hearing_impaired': False},
            {'index': 17, 'codec': 'hdmv_pgs_subtitle', 'language': 'en', 'title': 'English SDH',
             'embedded_title': 'English SDH', 'default': False, 'forced': False, 'hearing_impaired': True},
        ]
        self.source = SourceSubtitles(self.tracks, lambda v: {'en': 'eng', 'eng': 'eng'}.get(v, ''))
        self.streams = [{'index': 3, 'name': 'English', 'language': 'eng', 'isdefault': False,
                         'isforced': False, 'isimpaired': False},
                        {'index': 0, 'name': 'English SDH', 'language': 'eng', 'isdefault': False,
                         'isforced': False, 'isimpaired': True}]

    def test_source_stream_index_is_not_a_native_or_combined_ordinal(self):
        self.assertEqual(self.source.native_index(17, self.streams), 0)
        self.assertEqual(self.source.native_index(8, self.streams), 3)
        selection = dict(self.tracks[0], source='embedded', label='English', combined_index=99)
        self.source.check_selection(selection, self.streams)
        with self.assertRaises(Error):
            self.source.native_index(0, self.streams)

    def test_native_titles_are_exact_and_flags_must_agree(self):
        for change in ({'name': 'English - PGS'}, {'isforced': True}, {'isimpaired': True}):
            with self.subTest(change=change), self.assertRaises(Error):
                self.source.native_index(8, [dict(self.streams[0], **change), self.streams[1]])

    def test_duplicate_native_tracks_cannot_be_disambiguated_by_position(self):
        with self.assertRaises(Error):
            self.source.native_index(8, self.streams + [dict(self.streams[0], index=9)])

    def test_ambiguous_source_indexes_and_metadata_fail_before_selection(self):
        for duplicate in (dict(self.tracks[0]), dict(self.tracks[0], index=20)):
            with self.subTest(duplicate=duplicate), self.assertRaises(Error):
                SourceSubtitles(self.tracks + [duplicate], self.source.language).native_index(8, self.streams)

