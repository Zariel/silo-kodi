from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'plugin.video.silo.kodi/resources/lib'))
from silo.audio import SourceAudio
from silo.client import Error


def language(value):
    return {'en': 'eng', 'eng': 'eng', 'fr': 'fre', 'fre': 'fre'}.get(value, '')


class Audio(unittest.TestCase):
    def setUp(self):
        self.source = SourceAudio('42', [
            {'codec': 'dts', 'channels': 6, 'language': 'en', 'embedded_title': 'Main'},
            {'codec': 'ac3', 'channels': 2, 'language': 'en', 'embedded_title': 'Commentary'},
        ], language)
        self.streams = [
            {'index': 0, 'codec': 'ac3', 'channels': 2, 'language': 'eng', 'name': 'Commentary - AC3 stereo'},
            {'index': 1, 'codec': 'dtshd_ma', 'channels': 6, 'language': 'eng', 'name': 'Main - DTS-HD MA 5.1'},
        ]

    def test_reordered_native_streams_keep_source_identity(self):
        identity = self.source.identity(self.streams, 0)
        self.assertEqual(identity, {'id': 'file:42:audio:1', 'index': 1})
        self.assertEqual(self.source.native_index(identity, self.streams), 0)
        self.assertEqual(self.source.identity(self.streams, 1), {'id': 'file:42:audio:0', 'index': 0})

    def test_profile_codec_names_match_the_source_family(self):
        for source_codec, native_codec in (('truehd', 'truehd_atmos'), ('eac3', 'eac3_ddp_atmos'),
                                           ('dts', 'dtshd_ma_x'), ('aac', 'he_aac_v2')):
            with self.subTest(codec=native_codec):
                source = SourceAudio('42', [{'codec': source_codec, 'channels': 8}], language)
                streams = [{'index': 2, 'codec': native_codec, 'channels': 8}]
                identity = {'id': 'file:42:audio:0', 'index': 0}
                self.assertEqual(source.identity(streams, 2), identity)
                self.assertEqual(source.native_index(identity, streams), 2)

    def test_unknown_profiles_and_different_families_are_not_guessed(self):
        source = SourceAudio('42', [{'codec': 'truehd', 'channels': 8}], language)
        for codec in ('truehd_unknown', 'eac3_ddp_atmos'):
            with self.subTest(codec=codec), self.assertRaises(Error):
                source.identity([{'index': 0, 'codec': codec, 'channels': 8}], 0)

    def test_ambiguous_source_and_native_metadata_are_rejected(self):
        self.source.tracks.append(dict(self.source.tracks[1]))
        with self.assertRaises(Error):
            self.source.identity(self.streams, 0)
        with self.assertRaises(Error):
            self.source.native_index({'id': 'file:42:audio:1', 'index': 1}, self.streams)
        self.source.tracks.pop()
        self.streams.append(dict(self.streams[0], index=2))
        with self.assertRaises(Error):
            self.source.identity(self.streams, 0)
        with self.assertRaises(Error):
            self.source.native_index({'id': 'file:42:audio:1', 'index': 1}, self.streams)

    def test_unknown_languages_do_not_match_through_empty_conversion(self):
        self.source.tracks[1]['language'] = 'unknown-source'
        self.streams[0]['language'] = 'unknown-native'
        with self.assertRaises(Error):
            self.source.identity(self.streams, 0)

    def test_identity_cannot_select_another_file_or_invalid_index(self):
        for identity in ({'id': 'file:99:audio:1', 'index': 1},
                         {'id': 'file:42:audio:-1', 'index': -1},
                         {'id': 'file:42:audio:1', 'index': True}):
            with self.subTest(identity=identity), self.assertRaises(Error):
                self.source.native_index(identity, self.streams)

    def test_selected_title_must_match_with_a_separator(self):
        self.streams[0]['name'] = 'Commentary extra - AC3 stereo'
        with self.assertRaises(Error):
            self.source.identity(self.streams, 0)
