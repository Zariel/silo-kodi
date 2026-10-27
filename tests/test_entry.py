from pathlib import Path
import runpy
import sys
import unittest
from unittest.mock import Mock, patch


class Entry(unittest.TestCase):
    def run_entry(self, argv):
        modules = {name: Mock() for name in ('xbmc', 'xbmcaddon', 'xbmcgui', 'xbmcplugin', 'xbmcvfs', 'silo.browser')}
        with patch.dict(sys.modules, modules), patch.object(sys, 'argv', argv):
            runpy.run_path(str(Path(__file__).resolve().parents[1] / 'plugin.video.silo.kodi/addon.py'), run_name='__main__')
        return modules

    def test_script_owns_the_browser_without_resolving_a_directory(self):
        modules = self.run_entry(['addon.py'])
        modules['silo.browser'].open_browser.assert_called_once_with()
        modules['xbmcplugin'].endOfDirectory.assert_not_called()
        modules['xbmc'].executebuiltin.assert_not_called()

    def test_directory_launch_delegates_to_an_independent_script(self):
        modules = self.run_entry(['plugin://plugin.video.silo.kodi/', '7', ''])
        modules['silo.browser'].open_browser.assert_not_called()
        modules['xbmcplugin'].endOfDirectory.assert_called_once_with(7, cacheToDisc=False)
        self.assertEqual([call.args for call in modules['xbmc'].executebuiltin.call_args_list], [
            ('ActivateWindow(Home)', True), ('RunScript(plugin.video.silo.kodi)',)])
