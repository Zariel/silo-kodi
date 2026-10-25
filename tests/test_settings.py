import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch


class Settings(unittest.TestCase):
    def test_autoplay_is_opt_in_and_delay_is_bounded(self):
        values = {'enabled': False, 'delay': 10}
        addon = SimpleNamespace(getSettingBool=lambda _: values['enabled'], getSettingInt=lambda _: values['delay'])
        path = Path(__file__).resolve().parents[1] / 'plugin.video.silo/resources/lib/silo/settings.py'
        spec = importlib.util.spec_from_file_location('settings_test', path)
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {'xbmcaddon': SimpleNamespace(Addon=lambda _: addon)}):
            spec.loader.exec_module(module)
        self.assertIsNone(module.autoplay_delay())
        values['enabled'] = True
        self.assertEqual(module.autoplay_delay(), 10)
        for delay, expected in ((1, 1), (25, 25), (-1, 1), (100, 60)):
            values['delay'] = delay
            self.assertEqual(module.autoplay_delay(), expected)
