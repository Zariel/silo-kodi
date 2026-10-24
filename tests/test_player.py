from contextlib import nullcontext
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'plugin.video.silo/resources/lib'))


class Lifetime(unittest.TestCase):
    def run_playback(self, scenario):
        state = SimpleNamespace(file=None, closed=False, relay_closed=False, clock=0, player=None,
                                subtitles=[], relay_updated=False)
        url = 'https://silo.example.test/api/v2/stream/owned'

        class Player:
            def __init__(self):
                state.player = self

            def isPlaying(self):
                return state.file is not None

            def getPlayingFile(self):
                return state.file

            def getTime(self):
                return 20

            def getTotalTime(self):
                return 600

            def stop(self):
                state.file = None

            def setSubtitles(self, path):
                state.subtitles.append(path)
                raise RuntimeError('Player rejected subtitle')

            def showSubtitles(self, enabled):
                pass

        class Monitor:
            def abortRequested(self):
                return False

            def waitForAbort(self, seconds):
                state.clock += 31
                if scenario == 'replacement':
                    state.file = 'https://other.example.test/replacement'

        class Attempt:
            def __init__(self, *args, **kwargs):
                self.plan = {'stream': {}, 'timeline': {'player_start_seconds': 0}, 'effective_media_file_id': 'file'}
                self.plan['subtitle'] = {'artifact': {'format': 'vtt'}}
                self.subtitle_url = '/subtitle.vtt' if scenario == 'subtitle_error' else None

            def start(self):
                return url

            def sample(self, *args):
                pass

            def select_subtitle(self, track, position):
                state.file = 'https://other.example.test/replacement'
                self.subtitle_url = '/subtitle.vtt'
                self.plan_attempt_id = 'new-plan'

            def stop(self, *args):
                state.closed = True

        class Relay:
            def __init__(self, *args):
                pass

            def url(self, name):
                return url if name == 'video' else '/subtitle.vtt'

            def close(self):
                state.relay_closed = True

            def update(self, resources):
                state.relay_updated = True

        def resolve(handle, success, item):
            if success:
                state.file = url
                if scenario != 'readiness_timeout':
                    state.player.onAVStarted()

        modules = {
            'xbmc': SimpleNamespace(Player=Player, Monitor=Monitor, log=Mock(), LOGINFO=1, LOGWARNING=2,
                                    LOGERROR=3, getCondVisibility=lambda name: False),
            'xbmcgui': SimpleNamespace(ListItem=Mock(), Dialog=Mock(), NOTIFICATION_ERROR=1),
            'xbmcplugin': SimpleNamespace(setResolvedUrl=resolve),
        }
        path = Path(__file__).resolve().parents[1] / 'plugin.video.silo/resources/lib/silo/player.py'
        spec = importlib.util.spec_from_file_location('silo.player_test', path)
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, modules):
            spec.loader.exec_module(module)
            controls = Mock()
            controls.take.return_value = {'subtitle': 'track'} if scenario == 'replan_replacement' else None
            with patch.object(module, 'Attempt', Attempt), patch.object(module, 'MediaRelay', Relay), patch.object(module, 'PlaybackControls', return_value=controls), patch.object(module.time, 'monotonic', lambda: state.clock):
                session = SimpleNamespace(store=SimpleNamespace(playback_lock=nullcontext))
                module.play(1, session, 'profile', 'file', 'Title')
        return state

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
