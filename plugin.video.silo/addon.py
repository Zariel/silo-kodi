"""Kodi entry point; the account UI and headless harness share one session."""
from pathlib import Path
import sys
from urllib.parse import parse_qs

sys.path.insert(0, str(Path(__file__).resolve().parent / 'resources/lib'))

import xbmcaddon
import xbmcgui
import xbmcplugin
import xbmcvfs

from silo.client import Error, Session


def main():
    handle = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else -1
    query = parse_qs(sys.argv[2].lstrip('?')) if len(sys.argv) > 2 else {}
    action = query.get('action', [''])[0]
    if action == 'smoke':
        path = 'special://temp/silo-kodi-smoke.wav'
        item = xbmcgui.ListItem(path=path)
        item.setMimeType('audio/wav')
        item.setContentLookup(False)
        xbmcplugin.setResolvedUrl(handle, xbmcvfs.exists(path), item)
        return
    if action == 'status':
        directory = xbmcvfs.translatePath(xbmcaddon.Addon().getAddonInfo('profile'))
        session = Session.open(directory)
        label = 'Silo: server not configured'
        if session:
            try:
                session.public('/system/info')
                label = 'Silo connected — API v2'
            except Error:
                label = 'Silo: server unavailable'
        xbmcplugin.addDirectoryItem(handle, '', xbmcgui.ListItem(label=label), isFolder=False)
        xbmcplugin.endOfDirectory(handle, cacheToDisc=False)
        return
    if handle >= 0:
        xbmcplugin.endOfDirectory(handle, cacheToDisc=False)
    from silo.ui import open_account
    open_account()


if __name__ == '__main__':
    main()
