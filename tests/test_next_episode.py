import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch


class Countdown(unittest.TestCase):
    def run_prompt(self, action=None, invalidate=False):
        state = SimpleNamespace(clock=0, dialog=None, valid=True, labels=[], closed=False)

        class Dialog:
            def __init__(self, *args, **kwargs):
                state.dialog = self

            def show(self):
                self.onInit()

            def close(self):
                state.closed = True

            def getControl(self, control):
                return SimpleNamespace(setLabel=lambda value: state.labels.append(value))

        class Monitor:
            def abortRequested(self):
                return False

            def waitForAbort(self, seconds):
                state.clock += 1
                if action == 'back':
                    state.dialog.onAction(SimpleNamespace(getId=lambda: 92))
                elif action == 'play':
                    state.dialog.onClick(10)
                elif action == 'cancel':
                    state.dialog.onClick(11)
                if invalidate:
                    state.valid = False

        path = Path(__file__).resolve().parents[1] / 'plugin.video.silo.kodi/resources/lib/silo/next_episode.py'
        spec = importlib.util.spec_from_file_location('next_episode_test', path)
        module = importlib.util.module_from_spec(spec)
        modules = {'xbmc': SimpleNamespace(Monitor=Monitor), 'xbmcgui': SimpleNamespace(WindowXMLDialog=Dialog),
                   'xbmcaddon': SimpleNamespace(Addon=lambda _: SimpleNamespace(getAddonInfo=lambda _: '/addon'))}
        with patch.dict(sys.modules, modules):
            spec.loader.exec_module(module)
        with patch.object(module.time, 'monotonic', lambda: state.clock):
            result = module.confirm_next('Episode 2', 3, lambda: state.valid)
        self.assertTrue(state.closed)
        return result, state

    def test_timeout_plays_only_after_configured_delay(self):
        result, state = self.run_prompt()
        self.assertTrue(result)
        self.assertIn('Playing in 3 seconds', state.labels)
        self.assertIn('Playing in 1 second', state.labels)
        self.assertGreaterEqual(state.clock, 3)

    def test_back_and_cancel_prevent_timeout_playback(self):
        for action in ('back', 'cancel'):
            with self.subTest(action=action):
                result, state = self.run_prompt(action)
                self.assertFalse(result)
                self.assertLess(state.clock, 3)

    def test_play_now_still_requires_current_authority(self):
        self.assertTrue(self.run_prompt('play')[0])
        self.assertFalse(self.run_prompt('play', invalidate=True)[0])
        self.assertFalse(self.run_prompt(invalidate=True)[0])
