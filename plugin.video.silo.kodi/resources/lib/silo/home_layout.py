"""Instantiate a native scrolling shelf for each server Home section."""
from copy import deepcopy
from pathlib import Path
import xml.etree.ElementTree as ET


def _write_home_layout(addon, directory, count):
    source = Path(addon) / 'resources/skins/Default'
    destination = Path(directory) / 'resources/skins/Default'
    (destination / '1080i').mkdir(parents=True)
    # Textures remain owned by the installed add-on, not duplicated in userdata.
    (destination / 'media').symlink_to(source / 'media', target_is_directory=True)
    tree = ET.parse(source / '1080i/Browser.xml')
    shelves = tree.find(".//control[@id='600']")
    template = shelves.find('control')
    shelves.remove(template)
    for index in range(count):
        identifier = 1000 + index * 3
        group = deepcopy(template)
        group.set('id', str(identifier + 2))
        title, row = group.findall('control')
        title.set('id', str(identifier + 1))
        row.set('id', str(identifier))
        row.find('onright').text = str(identifier)
        row.find('onup').text = str(identifier - 3 if index else 100)
        row.find('ondown').text = str(identifier + 3 if index + 1 < count else 500)
        for node in row.iter('visible'):
            node.text = node.text.replace('Control.HasFocus(1000)', 'Control.HasFocus({})'.format(identifier))
        shelves.append(group)
    tree.write(destination / '1080i/Browser.xml', encoding='utf-8', xml_declaration=True)
