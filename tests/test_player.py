from contextlib import nullcontext
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'plugin.video.silo/resources/lib'))


class Lifetime(unittest.TestCase):
    def run_playback(self, scenario, source=None):
        state = SimpleNamespace(file=None, closed=False, relay_closed=False, clock=0, player=None,
                                subtitles=[], relay_updated=False, item_properties={}, position=20,
                                paused=scenario.startswith('quality') or scenario == 'hls_subtitle',
                                done=False, samples=[], opens=[], audio_index=1, audio_selections=[],
                                subtitle_index=None, subtitle_enabled=False, subtitle_selections=[], completions=[])
        url = 'https://silo.example.test/api/v2/stream/owned'

        class Player:
            def __init__(self):
                state.player = self

            def isPlaying(self):
                return state.file is not None

            def getPlayingFile(self):
                return state.file

            def getTime(self):
                return state.position

            def seekTime(self, position):
                state.position = position

            def pause(self):
                state.paused = not state.paused

            def play(self, path, item):
                state.audio_index = 1
                state.opens.append(path)
                state.file = path
                state.position = 0
                state.paused = False
                self.onPlayBackStopped()
                if scenario == 'quality_timeout':
                    self.onPlayBackEnded()
                else:
                    self.onAVStarted()

            def getTotalTime(self):
                return 600

            def stop(self):
                state.file = None

            def setSubtitles(self, path):
                state.subtitles.append(path)
                raise RuntimeError('Player rejected subtitle')

            def showSubtitles(self, enabled):
                state.subtitle_enabled = enabled

            def setSubtitleStream(self, index):
                state.subtitle_selections.append(index)
                if scenario != 'embedded_timeout':
                    state.subtitle_index = index

            def setAudioStream(self, index):
                state.audio_selections.append(index)
                state.audio_index = index

        class Monitor:
            def abortRequested(self):
                return state.done

            def waitForAbort(self, seconds):
                state.clock += 31
                if scenario == 'replacement':
                    state.file = 'https://other.example.test/replacement'

        class Attempt:
            def __init__(self, *args, **kwargs):
                self.audio_tracks = None
                self.subtitle_tracks = []
                self.native_subtitles = False
                self.embedded_subtitle_index = None
                self.body = {'quality_preference': 'auto'}
                self.plan = {'stream': {}, 'timeline': {'player_start_seconds': 0}, 'effective_media_file_id': 'file'}
                self.plan['delivery'] = 'server_transcode_hls' if scenario == 'hls_subtitle' else 'original_http'
                self.plan['subtitle'] = {'artifact': {'format': 'vtt'}}
                if scenario.startswith('embedded'):
                    self.native_subtitles = True
                    self.subtitle_tracks = [{'index': 7, 'embedded_title': 'English'}]
                    self.embedded_subtitle_index = 7
                if scenario.startswith('quality_audio'):
                    self.audio_tracks = [{'codec': 'dts', 'channels': 6}, {'codec': 'ac3', 'channels': 2}]
                    self.plan['selected_tracks'] = {'audio': {'id': 'file:file:audio:0', 'index': 0}}
                    if scenario == 'quality_audio_ambiguous':
                        self.audio_tracks.append(dict(self.audio_tracks[1]))
                self.subtitle_url = '/subtitle.vtt' if scenario == 'subtitle_error' else None

            def start(self):
                return url

            def sample(self, *args):
                state.samples.append(args)
                if scenario in ('natural_end', 'remote_stop'):
                    if scenario == 'natural_end':
                        state.player.onPlayBackEnded()
                    else:
                        state.player.onPlayBackStopped()
                if state.opens or scenario == 'hls_subtitle':
                    state.done = True
                    state.reported_audio = state.audio_index
                elif scenario.startswith('embedded'):
                    state.reported_subtitle = (state.subtitle_index, state.subtitle_enabled)
                    state.done = True
                elif scenario.startswith('quality_audio'):
                    state.audio_index = 0

            def select_subtitle(self, track, position, audio_track=None):
                if scenario == 'hls_subtitle':
                    self.plan_attempt_id = 'new-plan'
                    self.plan['timeline']['player_start_seconds'] = position
                    return
                state.file = 'https://other.example.test/replacement'
                self.subtitle_url = '/subtitle.vtt'
                self.plan_attempt_id = 'new-plan'

            def select_quality(self, quality, position, audio_track=None):
                if scenario.startswith('quality_audio'):
                    state.requested_audio = audio_track
                    self.plan['selected_tracks']['audio'] = audio_track
                self.plan_attempt_id = 'new-plan'
                self.body['quality_preference'] = quality
                self.plan['timeline']['player_start_seconds'] = position
                if scenario == 'quality_replacement':
                    state.file = 'https://other.example.test/replacement'

            def stop(self, *args):
                state.closed = True
                state.final_sample = args

        class Relay:
            def __init__(self, *args):
                pass

            def url(self, name):
                return url if name == 'video' else url + '/' + name

            def close(self):
                state.relay_closed = True

            def update(self, resources):
                state.relay_updated = True

        def resolve(handle, success, item):
            if success:
                state.file = url
                if scenario != 'readiness_timeout':
                    state.player.onAVStarted()

        item = Mock()
        item.setProperty.side_effect = state.item_properties.__setitem__
        modules = {
            'xbmc': SimpleNamespace(Player=Player, Monitor=Monitor, log=Mock(), LOGINFO=1, LOGWARNING=2,
                                    LOGERROR=3, getCondVisibility=lambda name: state.paused),
            'xbmcgui': SimpleNamespace(ListItem=Mock(return_value=item), Dialog=Mock(), NOTIFICATION_ERROR=1),
            'xbmcplugin': SimpleNamespace(setResolvedUrl=resolve),
        }
        path = Path(__file__).resolve().parents[1] / 'plugin.video.silo/resources/lib/silo/player.py'
        spec = importlib.util.spec_from_file_location('silo.player_test', path)
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, modules):
            spec.loader.exec_module(module)
            controls = Mock()
            controls.complete.side_effect = lambda: state.completions.append((state.closed, state.final_sample))
            controls.take.return_value = {'subtitle': 'track'} if scenario == 'replan_replacement' else None
            if scenario.startswith('quality'):
                controls.take.side_effect = [{'quality': '360p'}, None]
            if scenario.startswith('quality_audio'):
                controls.take.side_effect = [None, {'quality': 'auto'}, None]
            if scenario == 'quality_audio_ambiguous':
                def published(*args, **kwargs):
                    if controls.publish.call_count == 2:
                        state.refused_while_playing = state.file == url
                        state.done = True
                controls.publish.side_effect = published
            if scenario == 'hls_subtitle':
                controls.take.side_effect = [{'subtitle': None}, None]
            def audio_state(properties):
                if scenario == 'quality_audio_replacement' and state.opens:
                    state.file = 'https://other.example.test/replacement'
                if 'subtitles' in properties:
                    if scenario == 'embedded_replacement':
                        state.file = 'https://other.example.test/replacement'
                    return {'subtitles': [{'index': 2, 'name': 'English'}],
                            'currentsubtitle': {'index': state.subtitle_index}, 'subtitleenabled': state.subtitle_enabled}
                return {'audiostreams': [{'index': 0, 'codec': 'ac3', 'channels': 2},
                                         {'index': 1, 'codec': 'dtshd_ma', 'channels': 6}],
                        'currentaudiostream': {'index': state.audio_index}}

            with patch.object(module, '_track_state', audio_state), patch.object(module, 'Attempt', Attempt), patch.object(module, 'MediaRelay', Relay), patch.object(module, 'PlaybackControls', return_value=controls), patch.object(module.time, 'monotonic', lambda: state.clock):
                session = SimpleNamespace(store=SimpleNamespace(playback_lock=nullcontext))
                module.play(1, session, 'profile', 'file', 'Title', source=source)
        return state

    def test_only_natural_end_offers_next_after_final_progress(self):
        completed = self.run_playback('natural_end')
        self.assertEqual(completed.completions, [(True, (600, False))])
        stopped = self.run_playback('remote_stop')
        self.assertEqual(stopped.completions, [])
        self.assertEqual(stopped.final_sample, (20, False))

    def test_quality_reopen_restores_observed_audio_before_reporting(self):
        state = self.run_playback('quality_audio')
        self.assertEqual(state.requested_audio, {'id': 'file:file:audio:1', 'index': 1})
        self.assertEqual(state.audio_selections, [0])
        self.assertEqual(state.reported_audio, 0)
        self.assertEqual(state.samples[-1], (20, True))

    def test_embedded_subtitle_is_selected_and_observed_before_reporting(self):
        state = self.run_playback('embedded')
        self.assertEqual(state.subtitle_selections, [2])
        self.assertEqual(state.reported_subtitle, (2, True))
        self.assertEqual(state.samples, [(20, False)])

    def test_embedded_selection_timeout_closes_owned_playback(self):
        state = self.run_playback('embedded_timeout')
        self.assertEqual(state.samples, [])
        self.assertTrue(state.closed)
        self.assertIsNone(state.file)

    def test_embedded_selection_preserves_replacement_playback(self):
        state = self.run_playback('embedded_replacement')
        self.assertEqual(state.subtitle_selections, [])
        self.assertEqual(state.file, 'https://other.example.test/replacement')

    def test_ambiguous_audio_keeps_current_playback_without_replanning(self):
        state = self.run_playback('quality_audio_ambiguous')
        self.assertTrue(state.refused_while_playing)
        self.assertFalse(hasattr(state, 'requested_audio'))
        self.assertEqual(state.opens, [])

    def test_audio_restoration_does_not_change_replacement_player(self):
        state = self.run_playback('quality_audio_replacement')
        self.assertEqual(state.audio_selections, [])
        self.assertEqual(state.file, 'https://other.example.test/replacement')

    def test_list_item_retains_plugin_identity_for_kodi_bookkeeping(self):
        source = 'plugin://plugin.video.silo/?action=play&file=example'
        state = self.run_playback('subtitle_error', source=source)
        self.assertEqual(state.item_properties['original_listitem_url'], source)

    def test_quality_reopen_restores_paused_position_before_reporting(self):
        state = self.run_playback('quality')
        self.assertEqual(state.samples, [(20, True)])
        self.assertEqual(len(state.opens), 1)
        self.assertTrue(state.closed)
        self.assertIsNone(state.file)

    def test_hls_subtitle_replan_reopens_and_restores_paused_position(self):
        state = self.run_playback('hls_subtitle')
        self.assertEqual(state.samples, [(20, True)])
        self.assertEqual(len(state.opens), 1)
        self.assertTrue(state.closed)
        self.assertIsNone(state.file)

    def test_quality_readiness_timeout_cleans_up_without_reporting_startup_zero(self):
        state = self.run_playback('quality_timeout')
        self.assertEqual(state.samples, [])
        self.assertEqual(state.final_sample[0], 20)
        self.assertIsNone(state.file)
        self.assertTrue(state.closed)

    def test_quality_replan_does_not_reopen_external_replacement(self):
        state = self.run_playback('quality_replacement')
        self.assertEqual(state.opens, [])
        self.assertEqual(state.file, 'https://other.example.test/replacement')
        self.assertTrue(state.closed)

    def test_failure_stops_owned_media_and_closes_session(self):
        for scenario in ('subtitle_error', 'readiness_timeout'):
            with self.subTest(scenario=scenario):
                state = self.run_playback(scenario)
                self.assertIsNone(state.file)
                self.assertTrue(state.closed)
                self.assertTrue(state.relay_closed)

    def test_cleanup_preserves_replacement(self):
        state = self.run_playback('replacement')
        self.assertEqual(state.file, 'https://other.example.test/replacement')
        self.assertTrue(state.closed)
        self.assertTrue(state.relay_closed)

    def test_replacement_during_replan_does_not_receive_old_subtitles(self):
        state = self.run_playback('replan_replacement')
        self.assertEqual(state.file, 'https://other.example.test/replacement')
        self.assertEqual(state.subtitles, [])
        self.assertFalse(state.relay_updated)
        self.assertTrue(state.closed)
        self.assertTrue(state.relay_closed)
