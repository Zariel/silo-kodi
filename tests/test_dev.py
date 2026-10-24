import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('dev_checks', Path(__file__).resolve().parents[1] / 'scripts/dev.py')
dev = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dev)


class DisplayCleanup(unittest.TestCase):
    def exercise(self, replacement=False, ignored=False):
        state = SimpleNamespace(clock=0, active=False, activation=None, woke=False)

        def sleep(seconds):
            state.clock += seconds
            if state.activation is not None and state.clock >= state.activation + .5:
                state.active = True
            if not state.woke and state.clock >= 2:
                state.woke = True
                state.active = False
                state.activation = None

        def rpc(args, method, params=None):
            if method == 'Player.GetActivePlayers':
                return [{'playerid': 1}] if replacement else []
            return {'System.ScreenSaverActive': state.active}

        def activate(*args):
            if replacement:
                self.fail('Cleanup touched replacement playback')
            self.assertGreaterEqual(state.clock, 1, 'Protection ran before owner cleanup')
            if not ignored:
                state.activation = state.clock

        with patch.object(dev, 'rpc', side_effect=rpc), patch.object(dev, 'ssh', side_effect=activate), \
                patch.object(dev, 'remote_python', side_effect=lambda *args: 'released' if state.clock >= 1 else 'busy'), \
                patch.object(dev.time, 'monotonic', side_effect=lambda: state.clock), \
                patch.object(dev.time, 'sleep', side_effect=sleep):
            result = dev.protect_idle_display(None)
        return result, state

    def test_browser_return_does_not_leave_idle_display_awake(self):
        result, state = self.exercise()
        self.assertTrue(result)
        self.assertTrue(state.woke)
        self.assertTrue(state.active)
        self.assertGreaterEqual(state.clock, 4)

    def test_activation_ack_without_observed_protection_times_out(self):
        with self.assertRaisesRegex(RuntimeError, 'display protection'):
            self.exercise(ignored=True)

    def test_replacement_playback_is_left_alone(self):
        result, _ = self.exercise(replacement=True)
        self.assertFalse(result)
