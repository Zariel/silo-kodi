import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'plugin.video.silo.kodi/resources/lib'))


class ProfileEntry(unittest.TestCase):
    def test_pin_uses_masked_text_and_preserves_leading_zeroes(self):
        dialog = Mock()
        gui = SimpleNamespace(WindowXML=object, Dialog=lambda: dialog,
                              INPUT_ALPHANUM=0, ALPHANUM_HIDE_INPUT=1)
        modules = {name: Mock() for name in ('xbmc', 'xbmcaddon', 'xbmcvfs', 'silo.pairing')}
        modules['xbmcgui'] = gui
        path = Path(__file__).resolve().parents[1] / 'plugin.video.silo.kodi/resources/lib/silo/ui.py'
        with patch.dict(sys.modules, modules):
            spec = importlib.util.spec_from_file_location('silo.account_test', path)
            ui = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(ui)
        window = ui.AccountWindow.__new__(ui.AccountWindow)
        window._busy = False
        window.profiles = [{'id': 'protected', 'has_pin': True}]
        window.session = Mock()
        window.getControl = lambda identifier: SimpleNamespace(getSelectedPosition=lambda: 0)
        window._task = lambda operation: operation()
        window._load = Mock()

        dialog.input.return_value = '0012-test'
        window.onClick(200)
        # Kodi's numeric dialog ignores ALPHANUM_HIDE_INPUT. The text dialog
        # is required both for masking and Silo's nonnumeric PIN contract.
        dialog.input.assert_called_once_with('Profile PIN', type=gui.INPUT_ALPHANUM,
                                             option=gui.ALPHANUM_HIDE_INPUT)
        window.session.select_profile.assert_called_once_with('protected', '0012-test')

        window.session.reset_mock()
        dialog.input.return_value = ''
        window.onClick(200)
        window.session.select_profile.assert_not_called()
