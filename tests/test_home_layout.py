from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET
import sys

ADDON = Path(__file__).resolve().parents[1] / 'plugin.video.silo.kodi'
sys.path.insert(0, str(ADDON / 'resources/lib'))
from silo.home_layout import _write_home_layout


class HomeLayout(unittest.TestCase):
    def test_native_shelves_follow_server_count_without_duplicate_controls(self):
        for count in (0, 1, 45):
            with self.subTest(count=count), tempfile.TemporaryDirectory() as directory:
                _write_home_layout(ADDON, directory, count)
                skin = Path(directory) / 'resources/skins/Default'
                root = ET.parse(skin / '1080i/Browser.xml').getroot()
                identifiers = [node.attrib['id'] for node in root.iter('control') if 'id' in node.attrib]
                self.assertEqual(len(identifiers), len(set(identifiers)))
                shelves = root.find(".//control[@id='600']")
                groups = shelves.findall('control')
                self.assertEqual(len(groups), count)
                lists = [group.find("control[@type='list']") for group in groups]
                for index, row in enumerate(lists):
                    self.assertEqual(row.findtext('orientation'), 'horizontal')
                    self.assertEqual(row.findtext('onleft'), '100')
                    self.assertEqual(row.findtext('onup'), lists[index - 1].attrib['id'] if index else '100')
                    self.assertEqual(row.findtext('ondown'), lists[index + 1].attrib['id'] if index + 1 < count else '500')
                self.assertTrue((skin / 'media/rounded.png').is_file())
