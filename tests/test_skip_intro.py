import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'plugin.video.silo.kodi/resources/lib'))


class Dialog:
    def __init__(self, *args, **kwargs):
        self.shown = False

    def show(self):
        self.shown = True

    def close(self):
        self.shown = False


class SkipPrompt(unittest.TestCase):
    def setUp(self):
        self.gui = SimpleNamespace(WindowXMLDialog=Dialog, getCurrentWindowId=lambda: 12005,
                                   getCurrentWindowDialogId=lambda: 9999)
        self.xbmc = SimpleNamespace(executebuiltin=Mock(), getCondVisibility=lambda _: False)
        path = Path(__file__).resolve().parents[1] / 'plugin.video.silo.kodi/resources/lib/silo/skip_intro.py'
        spec = importlib.util.spec_from_file_location('silo.skip_intro_test', path)
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {'xbmcgui': self.gui, 'xbmc': self.xbmc}):
            spec.loader.exec_module(module)
        self.prompt = module.SkipIntro(segment=(10, 40))

    def test_automatic_skip_is_once_per_attempt_and_never_paused(self):
        self.prompt.automatic = True
        self.xbmc.getCondVisibility = lambda _: True
        self.assertIsNone(self.prompt.update(15, 600))
        self.assertFalse(self.prompt.shown)
        self.xbmc.getCondVisibility = lambda _: False
        self.assertEqual(self.prompt.update(16, 600), 40)
        self.assertFalse(self.prompt.shown)
        self.assertIsNone(self.prompt.update(17, 600))
        self.assertIsNone(self.prompt.update(50, 600))
        self.assertIsNone(self.prompt.update(15, 600))

    def test_automatic_skip_requires_fullscreen_source_timeline(self):
        self.prompt.automatic = True
        self.gui.getCurrentWindowId = lambda: 13000
        self.assertIsNone(self.prompt.update(15, 600))
        self.gui.getCurrentWindowId = lambda: 12005
        self.assertIsNone(self.prompt.update(15, 600, enabled=False))
        self.assertIsNone(self.prompt.update(50, 600))

    def test_seek_requires_current_valid_marker(self):
        self.prompt.update(15, 600)
        self.assertTrue(self.prompt.shown)
        self.prompt.onClick(10)
        self.assertFalse(self.prompt.shown)
        self.assertEqual(self.prompt.update(16, 600), 40)
        self.assertIsNone(self.prompt.update(17, 600))
        self.assertFalse(self.prompt.shown)

    def test_late_click_cannot_seek_back_into_finished_intro(self):
        self.prompt.update(15, 600)
        self.prompt.onClick(10)
        self.assertIsNone(self.prompt.update(45, 600))
        self.assertFalse(self.prompt.shown)

    def test_dismiss_and_other_windows_do_not_steal_focus(self):
        self.gui.getCurrentWindowDialogId = lambda: 10106
        self.prompt.update(15, 600)
        self.assertFalse(self.prompt.shown)
        self.gui.getCurrentWindowDialogId = lambda: 9999
        self.prompt.update(15, 600)
        self.prompt.onAction(SimpleNamespace(getId=lambda: 92))
        self.prompt.update(16, 600)
        self.assertFalse(self.prompt.shown)
        self.xbmc.executebuiltin.assert_not_called()

    def test_browsing_or_changed_timeline_hides_prompt(self):
        self.prompt.update(15, 600)
        self.gui.getCurrentWindowId = lambda: 13000
        self.prompt.update(16, 600)
        self.assertFalse(self.prompt.shown)
        self.gui.getCurrentWindowId = lambda: 12005
        self.prompt.update(16, 600, enabled=False)
        self.assertFalse(self.prompt.shown)
