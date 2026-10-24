import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'plugin.video.silo/resources/lib'))
from silo.client import Error
from silo.playback import Attempt, media_url, subtitle_url


class Server:
    server = 'https://silo.example.test'

    def media_headers(self, profile):
        if profile != 'viewer':
            raise AssertionError('Incorrect media authority')
        return {}

    def __init__(self):
        self.calls = []
        self.fail = None
        self.delivery = 'original_http'
        self.subtitle = {'mode': 'off'}
        self.replans = 0

    def request(self, method, path, body=None, expected_profile=None):
        if expected_profile != 'viewer':
            raise AssertionError('Playback lost its originating profile')
        self.calls.append((method, path, copy.deepcopy(body)))
        if self.fail == path:
            self.fail = None
            raise Error('connection_failed')
        if path == '/playback/capabilities':
            return {'allowed': True, 'protocol_versions': [3], 'installation_id': 'server-install', 'features': ['fixed_media_file_v1']}
        if path.endswith('/replan'):
            self.replans += 1
            self.subtitle = dict(self.subtitle, mode='render' if 'subtitle' in body['selected_tracks'] else 'off')
        if path == '/playback/start' or path.endswith('/replan'):
            return {'outcome': 'playable', 'session_id': 'session-1', 'playback_plan': {
                'plan_id': 'plan-' + str(self.replans), 'plan_attempt_key': 'original-recipe',
                'selected_tracks': {'audio': {'id': 'audio-commentary', 'index': 2}},
                'delivery': self.delivery, 'stream': {'url': '/api/v2/stream/session-1?st=grant', 'header_refresh': 'none'},
                'subtitle': self.subtitle,
                'timeline': {'can_seek_anywhere': True, 'player_start_seconds': 24}}}
        return {'outcome': 'stopped' if method == 'DELETE' else 'applied'}


class Playback(unittest.TestCase):
    @patch('silo.playback.time.sleep')
    def test_subtitle_replans_preserve_audio_position_and_retry_identity(self, sleep):
        server = Server()
        server.subtitle = {'mode': 'off', 'inventory': [{'track_id': 'opaque-sidecar'}],
                           'artifact': {'url': '/sub.vtt', 'format': 'vtt', 'timing_origin_seconds': 0}}
        attempt = Attempt(server, 'viewer', 'file-7')
        attempt.start()
        server.fail = '/playback/session-1/replan'
        attempt.select_subtitle('opaque-sidecar', 42)
        self.assertEqual(attempt.subtitle_url, 'https://silo.example.test/sub.vtt')
        attempt.select_subtitle(None, 57)
        self.assertIsNone(attempt.subtitle_url)
        attempt.select_subtitle('opaque-sidecar', 61)
        self.assertEqual(attempt.subtitle_url, 'https://silo.example.test/sub.vtt')

        requests = [body for _, path, body in server.calls if path.endswith('/replan')]
        self.assertEqual(requests[0], requests[1])
        self.assertEqual([r['position_seconds'] for r in requests], [42, 42, 57, 61])
        self.assertEqual([r['failed_plan_id'] for r in requests], ['plan-0', 'plan-0', 'plan-1', 'plan-2'])
        self.assertEqual(len({r['replan_request_id'] for r in requests}), 3)
        for request in requests:
            self.assertEqual(request['selected_tracks']['audio'], {'id': 'audio-commentary', 'index': 2})
            self.assertEqual(request['operation'], 'track_change')
            self.assertEqual(request['attempted_plan_keys'], [])
        self.assertEqual(requests[0]['selected_tracks']['subtitle'], {'id': 'opaque-sidecar'})
        self.assertNotIn('subtitle', requests[2]['selected_tracks'])

    def test_unknown_subtitle_does_not_mutate_session(self):
        server = Server()
        attempt = Attempt(server, 'viewer', 'file-7')
        attempt.start()
        with self.assertRaises(Error):
            attempt.select_subtitle('guessed-index', 12)
        self.assertFalse(any(path.endswith('/replan') for _, path, _ in server.calls))

    def test_unsupported_replan_retains_cleanup_owner(self):
        server = Server()
        attempt = Attempt(server, 'viewer', 'file-7')
        attempt.start()
        server.delivery = 'server_remux_progressive'
        with self.assertRaises(Error):
            attempt.select_subtitle(None, 12)
        attempt.stop(12)
        self.assertEqual(server.calls[-1][0:2], ('DELETE', '/playback/session-1'))

    def test_subtitle_selection_uses_server_track_identity(self):
        server = Server()
        server.subtitle = {'mode': 'convert', 'artifact': {
            'url': '/sub.vtt', 'format': 'vtt', 'timing_origin_seconds': 0}}
        attempt = Attempt(server, 'viewer', 'file-7', subtitle_track_id='file:7:subtitle:4')
        attempt.start()
        body = next(body for _, path, body in server.calls if path == '/playback/start')
        self.assertEqual(body['subtitle_track_id'], 'file:7:subtitle:4')
        self.assertNotIn('subtitle_track_index', body)
        self.assertEqual(attempt.subtitle_url, 'https://silo.example.test/sub.vtt')

    def test_selected_sidecar_uses_profile_authority(self):
        decision = {'mode': 'render', 'artifact': {'url': '/api/v2/stream/s/subtitles/4.vtt?file_id=8',
                    'format': 'vtt', 'timing_origin_seconds': 0}}
        self.assertEqual(subtitle_url('https://silo.example.test', decision, {'Authorization': 'Bearer current'}),
                         'https://silo.example.test/api/v2/stream/s/subtitles/4.vtt?file_id=8|Authorization=Bearer+current')
        self.assertIsNone(subtitle_url('https://silo.example.test', {'mode': 'off', 'inventory': [decision['artifact']]}, {}))

    def test_unhandled_subtitle_plan_is_rejected(self):
        artifact = {'url': '/sub.vtt', 'format': 'vtt', 'timing_origin_seconds': 0}
        decisions = [
            {'mode': 'render', 'artifact': dict(artifact, timing_origin_seconds=60)},
            {'mode': 'render', 'artifact': dict(artifact, url='https://other.example.test/sub.vtt')},
            {'mode': 'render', 'artifact': dict(artifact, format='ass')},
            {'mode': 'render', 'embedded': {'stream_index': 7}},
            {'mode': 'burn_in'},
        ]
        for decision in decisions:
            with self.subTest(decision=decision), self.assertRaises(Error):
                subtitle_url('https://silo.example.test', decision, {'Authorization': 'Bearer current'})

    @patch('silo.playback.time.sleep')
    def test_uncertain_start_reuses_identity_and_payload(self, sleep):
        server = Server()
        attempt = Attempt(server, 'viewer', 'file-7')
        server.fail = '/playback/start'
        self.assertEqual(attempt.start(), 'https://silo.example.test/api/v2/stream/session-1?st=grant')
        starts = [body for _, path, body in server.calls if path == '/playback/start']
        self.assertEqual(len(starts), 2)
        self.assertEqual(starts[0], starts[1])
        self.assertEqual(starts[0]['file_id'], 'file-7')
        self.assertFalse(starts[0]['allow_alternate_versions'])
        self.assertNotIn('start_position', starts[0])

    @patch('silo.playback.time.sleep')
    def test_backward_seek_and_final_stop_use_newer_sequences(self, sleep):
        server = Server()
        attempt = Attempt(server, 'viewer', 'file-7', 0)
        attempt.start()
        attempt.sample(60, False)
        attempt.sample(10, True)
        server.fail = '/playback/session-1'
        attempt.stop(12, False)
        attempt.stop(999, False)
        samples = [body for _, path, body in server.calls if path.endswith('/progress')]
        self.assertEqual(samples, [
            {'installation_id': 'server-install', 'sequence': 1, 'position': 60, 'is_paused': False},
            {'installation_id': 'server-install', 'sequence': 2, 'position': 10, 'is_paused': True}])
        stops = [body for method, _, body in server.calls if method == 'DELETE']
        self.assertEqual(len(stops), 2)
        self.assertEqual(stops[0], stops[1])
        self.assertEqual(stops[0]['position'], 12)
        self.assertEqual(stops[0]['sequence'], 3)
        self.assertEqual(attempt.body['start_position'], 0)

    def test_rejected_delivery_retains_session_for_cleanup(self):
        server = Server()
        server.delivery = 'server_remux_progressive'
        attempt = Attempt(server, 'viewer', 'file-7')
        with self.assertRaises(Error):
            attempt.start()
        attempt.stop()
        self.assertEqual(server.calls[-1][0:2], ('DELETE', '/playback/session-1'))
        self.assertNotIn('position', server.calls[-1][2])

    def test_media_grant_and_headers_are_preserved(self):
        self.assertEqual(media_url('https://silo.example.test', {
            'url': '/api/v2/stream/a?st=a%2Bb&seek=0', 'headers': {'X-Media-Token': 'a+b/c'}}),
            'https://silo.example.test/api/v2/stream/a?st=a%2Bb&seek=0|X-Media-Token=a%2Bb%2Fc')
        self.assertEqual(media_url('https://silo.example.test', {'url': '/api/v2/stream/a'},
                                   {'Authorization': 'Bearer current', 'X-Profile-Id': 'viewer'}),
                         'https://silo.example.test/api/v2/stream/a|Authorization=Bearer+current&X-Profile-Id=viewer')
        for url in ('https://other.example.test/media', 'http://silo.example.test/media',
                    '/media|Authorization=secret', 'https://user:pass@silo.example.test/media'):
            with self.subTest(url=url), self.assertRaises(Error):
                media_url('https://silo.example.test', {'url': url, 'headers': {'Authorization': 'secret'}})
