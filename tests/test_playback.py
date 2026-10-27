import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'plugin.video.silo.kodi/resources/lib'))
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
        self.versions = []
        self.file_id = None
        self.features = ['fixed_media_file_v1']
        self.subtitle_mode = 'render'
        self.tracks = {'audio': {'id': 'audio-commentary', 'index': 2}}
        self.timeline = {'can_seek_anywhere': True, 'player_start_seconds': 24, 'timeline_offset_seconds': 0}

    def request(self, method, path, body=None, expected_profile=None):
        if expected_profile != 'viewer':
            raise AssertionError('Playback lost its originating profile')
        self.calls.append((method, path, copy.deepcopy(body)))
        if path.endswith('/versions'):
            return {'items': self.versions}
        if self.fail == path:
            self.fail = None
            raise Error('connection_failed')
        if path == '/playback/capabilities':
            return {'allowed': True, 'protocol_versions': [3], 'installation_id': 'server-install', 'features': self.features}
        if path == '/playback/start':
            self.file_id = body['file_id']
        if path.endswith('/replan'):
            self.replans += 1
            self.tracks = body['selected_tracks']
            self.subtitle = dict(self.subtitle, mode=self.subtitle_mode if 'subtitle' in body['selected_tracks'] else 'off')
            if 'subtitle' in body['selected_tracks']:
                self.subtitle['track_id'] = body['selected_tracks']['subtitle']['id']
            else:
                self.subtitle.pop('track_id', None)
        if path == '/playback/start' or path.endswith('/replan'):
            return {'outcome': 'playable', 'session_id': 'session-1', 'playback_plan': {
                'plan_id': 'plan-' + str(self.replans), 'plan_attempt_key': 'original-recipe',
                'effective_media_file_id': self.file_id,
                'selected_tracks': self.tracks,
                'available_qualities': [{'label': 'original'}, {'label': '360p'}],
                'delivery': self.delivery, 'stream': {'url': '/api/v2/stream/session-1?st=grant', 'header_refresh': 'none',
                                                    'protocol': 'hls' if self.delivery == 'server_transcode_hls' else 'http'},
                'subtitle': self.subtitle,
                'timeline': self.timeline}}
        return {'outcome': 'stopped' if method == 'DELETE' else 'applied'}


class Playback(unittest.TestCase):
    def test_intro_marker_belongs_to_selected_file(self):
        server = Server()
        server.versions = [
            {'file_id': 'other', 'intro': {'start': 0, 'end': 120}},
            {'file_id': '42', 'intro': {'start': 10, 'end': 40}}]
        attempt = Attempt(server, 'viewer', '42', content_id='episode')
        self.assertEqual(attempt.intro, (10, 40))
        server.versions[1].pop('intro')
        self.assertIsNone(Attempt(server, 'viewer', '42', content_id='episode').intro)

    def test_rejects_wrong_source_before_returning_media_grant(self):
        for stage in ('start', 'replan'):
            for identity in (None, 'different-file'):
                for features in ([], ['fixed_media_file_v1']):
                    with self.subTest(stage=stage, identity=identity, features=features):
                        server = Server()
                        server.features = features
                        attempt = Attempt(server, 'viewer', 'chosen-file')
                        if stage == 'replan':
                            attempt.start()
                        request = server.request

                        def changed_source(method, path, body=None, expected_profile=None):
                            response = request(method, path, body, expected_profile)
                            if 'playback_plan' in response:
                                if identity is None:
                                    response['playback_plan'].pop('effective_media_file_id')
                                else:
                                    response['playback_plan']['effective_media_file_id'] = identity
                            return response

                        with patch.object(server, 'request', side_effect=changed_source):
                            with self.assertRaises(Error) as raised:
                                if stage == 'start':
                                    attempt.start()
                                else:
                                    attempt.select_quality('360p', 24)
                            self.assertEqual(raised.exception.code, 'unsupported_playback')
                            attempt.stop()
                        self.assertEqual(server.calls[-1][:2], ('DELETE', '/playback/session-1'))

    def test_pgs_replans_use_native_original_then_burned_in_hls(self):
        server = Server()
        server.features.append('embedded_subtitles_v1')
        server.versions = [{'file_id': '42', 'container': 'mkv',
                            'subtitle_tracks': [{'index': 7, 'codec': 'hdmv_pgs_subtitle'}]}]
        server.subtitle = {'mode': 'off', 'inventory': [{'track_id': 'pgs'}]}
        attempt = Attempt(server, 'viewer', '42', content_id='movie')
        attempt.start()
        deliveries = attempt.body['client_playback_context']['deliveries']
        self.assertIn('embedded_subtitles_v1', attempt.body['client_features'])
        self.assertEqual(deliveries['original_http']['subtitles']['native_embedded'][0]['track_identity'], 'ffmpeg_stream_index')
        self.assertNotIn('native_embedded', deliveries['hls']['subtitles'])

        server.subtitle['embedded'] = {'stream_index': 7}
        attempt.select_subtitle('pgs', 20)
        self.assertEqual(attempt.embedded_subtitle_index, 7)
        self.assertIsNone(attempt.subtitle_url)

        server.subtitle.pop('embedded')
        server.subtitle_mode = 'burn_in'
        server.delivery = 'server_transcode_hls'
        attempt.select_quality('360p', 22)
        self.assertIsNone(attempt.embedded_subtitle_index)
        self.assertIsNone(attempt.subtitle_url)
        self.assertEqual(attempt.plan['subtitle']['track_id'], 'pgs')
        attempt.select_subtitle(None, 24)
        self.assertEqual(attempt.plan['subtitle']['mode'], 'off')

    def test_invalid_native_and_burn_in_decisions_are_rejected(self):
        for delivery, decision in (
                ('original_http', {'mode': 'render', 'track_id': 'pgs', 'embedded': {'stream_index': 7}}),
                ('original_http', {'mode': 'burn_in', 'track_id': 'pgs'}),
                ('server_transcode_hls', {'mode': 'burn_in', 'track_id': 'pgs', 'artifact': {'url': '/sub.sup'}})):
            with self.subTest(delivery=delivery, decision=decision):
                server = Server()
                server.delivery = delivery
                server.subtitle = decision
                attempt = Attempt(server, 'viewer', '42')
                with self.assertRaises(Error):
                    attempt.start()
                attempt.stop()
                self.assertEqual(server.calls[-1][:2], ('DELETE', '/playback/session-1'))

    def test_inventory_is_fetched_under_playback_profile_and_scopes_audio_claim(self):
        server = Server()
        server.versions = [{'file_id': '42', 'audio_tracks': [{'codec': 'ac3', 'channels': 2}]}]
        attempt = Attempt(server, 'viewer', '42', content_id='movie/42')
        attempt.start()
        self.assertEqual(server.calls[0][:2], ('GET', '/catalog/items/movie%2F42/versions'))
        self.assertEqual(attempt.audio_tracks, [{'codec': 'ac3', 'channels': 2}])
        deliveries = attempt.body['client_playback_context']['deliveries']
        self.assertIn('client_selected_audio_track_v1', deliveries['original_http']['validated_claims'])
        self.assertNotIn('client_selected_audio_track_v1', deliveries['hls']['validated_claims'])
        with self.assertRaises(Error):
            Attempt(server, 'viewer', '99', content_id='movie/42')

    def test_original_presentation_is_delegated_without_claiming_sink_formats(self):
        server = Server()
        attempt = Attempt(server, 'viewer', 'file-7')
        attempt.start()
        body = next(body for _, path, body in server.calls if path == '/playback/start')
        decoder = body['client_capabilities']
        deliveries = body['client_playback_context']['deliveries']
        self.assertEqual(decoder['max_resolution'], '2160p')
        self.assertEqual(decoder['audio_evidence'], 'declared')
        self.assertFalse(decoder['hdr'])
        self.assertIn('client_managed_dynamic_range_v1', deliveries['original_http']['validated_claims'])
        self.assertNotIn('client_managed_dynamic_range_v1', deliveries['hls']['validated_claims'])
        self.assertEqual(deliveries['original_http']['audio_passthrough_codecs'], [])

    @patch('silo.playback.time.sleep')
    def test_quality_replans_preserve_tracks_and_intent(self, sleep):
        server = Server()
        server.tracks['subtitle'] = {'id': 'sidecar'}
        server.subtitle = {'mode': 'render', 'artifact': {
            'url': '/sub.vtt', 'format': 'vtt', 'timing_origin_seconds': 0}}
        attempt = Attempt(server, 'viewer', 'file-7')
        attempt.start()
        server.delivery = 'server_transcode_hls'
        server.fail = '/playback/session-1/replan'
        attempt.select_quality('360p', 120)
        attempt.select_subtitle(None, 121)
        server.delivery = 'original_http'
        attempt.select_quality('auto', 125)

        requests = [body for _, path, body in server.calls if path.endswith('/replan')]
        self.assertEqual(requests[0], requests[1])
        self.assertEqual([r['quality_preference'] for r in requests], ['360p', '360p', '360p', 'auto'])
        self.assertEqual([r['position_seconds'] for r in requests], [120, 120, 121, 125])
        self.assertEqual([r['failed_plan_id'] for r in requests], ['plan-0', 'plan-0', 'plan-1', 'plan-2'])
        self.assertEqual(requests[0]['selected_tracks'], {
            'audio': {'id': 'audio-commentary', 'index': 2}, 'subtitle': {'id': 'sidecar'}})
        self.assertEqual(requests[-1]['selected_tracks'], {'audio': {'id': 'audio-commentary', 'index': 2}})
        self.assertEqual(requests[-1]['operation'], 'quality_change')
        self.assertEqual(attempt.body['quality_preference'], 'auto')

    def test_unknown_quality_does_not_mutate_session(self):
        server = Server()
        attempt = Attempt(server, 'viewer', 'file-7')
        attempt.start()
        with self.assertRaises(Error):
            attempt.select_quality('invented-rung', 12)
        self.assertFalse(any(path.endswith('/replan') for _, path, _ in server.calls))

    def test_observed_audio_replaces_plan_selection_for_both_controls(self):
        server = Server()
        attempt = Attempt(server, 'viewer', '42')
        attempt.start()
        commentary = {'id': 'file:42:audio:1', 'index': 1}
        main = {'id': 'file:42:audio:0', 'index': 0}
        attempt.select_quality('360p', 40, audio_track=commentary)
        attempt.select_subtitle(None, 42, audio_track=main)
        requests = [body for _, path, body in server.calls if path.endswith('/replan')]
        self.assertEqual(requests[0]['selected_tracks']['audio'], commentary)
        self.assertEqual(requests[1]['selected_tracks']['audio'], main)
        self.assertEqual(requests[1]['quality_preference'], '360p')

    def test_different_returned_audio_is_rejected_with_new_plan_retained_for_cleanup(self):
        server = Server()
        request = server.request

        def replace_audio(method, path, body=None, expected_profile=None):
            response = copy.deepcopy(request(method, path, body, expected_profile))
            if path.endswith('/replan'):
                response['playback_plan']['selected_tracks']['audio'] = {'id': 'different-audio', 'index': 0}
            return response

        server.request = replace_audio
        attempt = Attempt(server, 'viewer', '42')
        attempt.start()
        with self.assertRaises(Error):
            attempt.select_quality('360p', 40, audio_track={'id': 'file:42:audio:1', 'index': 1})
        self.assertEqual(attempt.plan['plan_id'], 'plan-1')
        attempt.stop(40)
        self.assertEqual(server.calls[-1][:2], ('DELETE', '/playback/session-1'))

    def test_anchored_hls_is_rejected_without_losing_committed_plan(self):
        server = Server()
        attempt = Attempt(server, 'viewer', 'file-7')
        attempt.start()
        server.delivery = 'server_transcode_hls'
        server.timeline = dict(server.timeline, timeline_offset_seconds=90)
        with self.assertRaises(Error):
            attempt.select_quality('360p', 120)
        self.assertEqual(attempt.plan['plan_id'], 'plan-1')
        self.assertEqual(attempt.body['quality_preference'], '360p')
        attempt.stop(120)
        self.assertEqual(server.calls[-1][0:2], ('DELETE', '/playback/session-1'))

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
