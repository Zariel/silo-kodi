import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'plugin.video.silo/resources/lib'))


class Control:
    def __init__(self):
        self.items = []
        self.position = 0
        self.label = ''

    def reset(self):
        self.items = []
        self.position = 0

    def addItem(self, item):
        self.items.append(item)

    def selectItem(self, position):
        self.position = position

    def getSelectedPosition(self):
        return self.position

    def size(self):
        return len(self.items)

    def setLabel(self, label):
        self.label = label

    def __getattr__(self, name):
        return lambda *args: None


class Window:
    def __init__(self, *args, **kwargs):
        self.controls = {}
        self.focus = 100

    def getControl(self, identifier):
        return self.controls.setdefault(identifier, Control())

    def setFocusId(self, identifier):
        self.focus = identifier

    def getFocusId(self):
        return self.focus

    def setProperty(self, *args):
        pass


class HomeNavigation(unittest.TestCase):
    def setUp(self):
        modules = {name: Mock() for name in ('xbmc', 'xbmcaddon', 'xbmcvfs', 'silo.controls')}
        modules['xbmcgui'] = SimpleNamespace(WindowXML=Window, ListItem=lambda label: Mock(label=label))
        modules['silo.ui'] = SimpleNamespace(open_account=Mock(), _text=str)
        path = Path(__file__).resolve().parents[1] / 'plugin.video.silo/resources/lib/silo/browser.py'
        with patch.dict(sys.modules, modules):
            spec = importlib.util.spec_from_file_location('silo.browser_test', path)
            browser = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(browser)
        session = Mock(server='https://silo.example.test')
        session.status.return_value = {'profile': {'id': 'viewer', 'name': 'Viewer'}}
        self.window = browser.BrowserWindow(session=session)
        self.window._task = lambda operation: operation()
        self.catalog = Mock(profile_id='viewer')
        self.window.catalog = self.catalog
        self.rows = {
            'first': {'id': 'first', 'title': 'First', 'items': [self.card('a'), self.card('b')]},
            'empty': {'id': 'empty', 'title': 'Empty', 'items': []},
            'last': {'id': 'last', 'title': 'Last', 'items': [self.card('c')]},
        }
        self.catalog.home.return_value = [{'id': key} for key in self.rows]
        self.catalog.home_section.side_effect = lambda key: self.rows[key]
        self.catalog.item.side_effect = lambda key: dict(self.card(key), title=key)

    @staticmethod
    def card(identifier):
        return {'content_id': identifier, 'type': 'movie', 'title': identifier}

    def open_home(self):
        self.window.getControl(100).selectItem(0)
        self.window.onClick(100)

    def test_return_refreshes_rows_and_preserves_card_identity(self):
        self.open_home()
        self.assertEqual(self.window.getControl(40).label, 'First')
        self.assertEqual(self.window.getControl(41).label, 'Last')
        self.window.getControl(230).selectItem(1)
        self.window.onClick(230)
        self.assertEqual(self.window.getControl(12).label, 'b')

        self.rows['first']['items'] = [self.card('b'), self.card('a')]
        self.window.onAction(SimpleNamespace(getId=lambda: 10))
        self.assertEqual(self.window.getControl(12).label, 'Home')
        self.assertEqual(self.window.getFocusId(), 230)
        self.assertEqual(self.window.getControl(230).getSelectedPosition(), 0)

    def test_empty_home_keeps_navigation_available(self):
        self.rows = {}
        self.catalog.home.return_value = []
        self.open_home()
        self.assertEqual(self.window.getFocusId(), 100)
        self.assertIn('No titles', self.window.getControl(21).label)

    def test_removed_selected_card_returns_to_first_available_card(self):
        self.open_home()
        self.window.getControl(230).selectItem(1)
        self.window.onClick(230)
        self.rows['first']['items'] = [self.card('a')]
        self.window.onAction(SimpleNamespace(getId=lambda: 10))
        self.assertEqual(self.window.getControl(230).getSelectedPosition(), 0)
        self.assertEqual(self.window.getFocusId(), 230)
