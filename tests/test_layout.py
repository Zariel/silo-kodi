from pathlib import Path
import sys
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'plugin.video.silo.kodi/resources/lib'))
from silo.layout import _BrowserLayout


class Control:
    def __init__(self, element):
        self.x = float(element.findtext('left', '0'))
        self.y = float(element.findtext('top', '0'))
        self.width = float(element.findtext('width', '0'))
        self.height = float(element.findtext('height', '0'))
        self.count = 0
        self.selection = 0

    def size(self):
        return self.count

    def getSelectedPosition(self):
        return self.selection

    def selectItem(self, position):
        self.selection = position

    def getWidth(self):
        return self.width

    def setWidth(self, width):
        self.width = width
        self.selection = 0

    def setHeight(self, height):
        self.height = height
        self.selection = 0

    def setPosition(self, x, y):
        self.x, self.y = x, y


class Window:
    def __init__(self, root):
        self.controls = {int(node.attrib['id']): Control(node)
                         for node in root.iter('control') if 'id' in node.attrib}
        self.properties = {}

    def getControl(self, identifier):
        return self.controls[identifier]

    def setProperty(self, key, value):
        self.properties[key] = value


class BrowserLayout(unittest.TestCase):
    def test_playback_overlay_leaves_room_and_preserves_selection(self):
        path = Path(__file__).resolve().parents[1] / 'plugin.video.silo.kodi/resources/skins/Default/1080i/Browser.xml'
        window = Window(ET.parse(path).getroot())
        layout = _BrowserLayout(window)
        for identifier in (200, 220):
            window.getControl(identifier).count = 40
            window.getControl(identifier).selection = 24
        layout.playback(True)
        for identifier in (200, 220):
            control = window.getControl(identifier)
            self.assertLessEqual(control.y + control.height, 960)
            self.assertEqual(control.selection, 24)
        layout.playback(False)
        self.assertEqual(window.getControl(200).height, 885)
        self.assertEqual(window.getControl(220).height, 405)
        self.assertEqual(window.getControl(220).selection, 24)

    def test_content_fits_beside_sidebar_in_both_states(self):
        path = Path(__file__).resolve().parents[1] / 'plugin.video.silo.kodi/resources/skins/Default/1080i/Browser.xml'
        root = ET.parse(path).getroot()
        window = Window(root)
        layout = _BrowserLayout(window)
        window.getControl(200).count = 100
        window.getControl(200).selection = 17
        content = root.find("./controls/control[@id='400']")
        original = {int(node.attrib['id']): float(node.findtext('width'))
                    for node in content.findall('control')}

        for expanded, boundary in ((True, 360), (False, 120), (True, 360), (False, 120)):
            layout.apply(expanded)
            with self.subTest(expanded=expanded):
                viewport = window.getControl(400)
                sidebar = window.getControl(100)
                self.assertLessEqual(sidebar.x + sidebar.width, boundary)
                for identifier in original:
                    control = window.getControl(identifier)
                    self.assertGreaterEqual(viewport.x + control.x, boundary, identifier)
                    self.assertLessEqual(viewport.x + control.x + control.width, 1920, identifier)
                    self.assertGreater(control.width, 0, identifier)
                for node in content.findall("control[@type='list']"):
                    if node.findtext('orientation', 'vertical') != 'vertical':
                        continue
                    for row in (node.find('itemlayout'), node.find('focusedlayout')):
                        self.assertLessEqual(float(row.attrib['width']), window.getControl(int(node.attrib['id'])).width)
                        for child in row.findall('control'):
                            self.assertLessEqual(float(child.findtext('left', '0')) + float(child.findtext('width', '0')),
                                                 float(row.attrib['width']))
                self.assertEqual(window.getControl(200).selection, 17)
                self.assertEqual(window.getControl(300).width, 160)
                self.assertEqual(window.getControl(200).width, 1424 if expanded else 1664)
                self.assertEqual(window.properties['sidebar_expanded'], str(expanded).lower())
                if not expanded:
                    self.assertEqual({identifier: window.getControl(identifier).width for identifier in original}, original)
