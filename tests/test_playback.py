import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'plugin.video.silo/resources/lib'))
from silo.client import Error
from silo.playback import Attempt, media_url


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

    def request(self, method, path, body=None, expected_profile=None):
        if expected_profile != 'viewer':
            raise AssertionError('Playback lost its originating profile')
        self.calls.append((method, path, copy.deepcopy(body)))
        if self.fail == path:
            self.fail = None
            raise Error('connection_failed')
        if path == '/playback/capabilities':
            return {'allowed': True, 'protocol_versions': [3], 'installation_id': 'server-install', 'features': ['fixed_media_file_v1']}
        if path == '/playback/start':
            return {'outcome': 'playable', 'session_id': 'session-1', 'playback_plan': {
                'delivery': self.delivery, 'stream': {'url': '/api/v2/stream/session-1?st=grant', 'header_refresh': 'none'},
                'timeline': {'can_seek_anywhere': True, 'player_start_seconds': 24}}}
        return {'outcome': 'stopped' if method == 'DELETE' else 'applied'}


class Playback(unittest.TestCase):
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
