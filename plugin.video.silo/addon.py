"""Kodi entry point; the account UI and headless harness share one session."""
from pathlib import Path
import sys
from urllib.parse import parse_qs

sys.path.insert(0, str(Path(__file__).resolve().parent / 'resources/lib'))

import xbmcaddon
import xbmc
import xbmcgui
import xbmcplugin
import xbmcvfs

from silo.client import Error, Session


def main():
    handle = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else -1
    query = parse_qs(sys.argv[2].lstrip('?')) if len(sys.argv) > 2 else {}
    action = query.get('action', [''])[0]
    if action == 'play':
        from silo.player import play
        directory = xbmcvfs.translatePath(xbmcaddon.Addon().getAddonInfo('profile'))
        session = Session.open(directory)
        if session and all(key in query for key in ('profile', 'file')):
            play(handle, session, query['profile'][0], query['file'][0], query.get('title', ['Silo'])[0],
                 0 if query.get('restart') == ['true'] else None, sys.argv[0] + sys.argv[2],
                 subtitle_track_id=query.get('subtitle', [None])[0], content_id=query.get('content', [None])[0])
        else:
            xbmcplugin.setResolvedUrl(handle, False, xbmcgui.ListItem())
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
        # RunAddon prefers the plugin extension even for a script/video add-on.
        # Leave its directory before launching the independent UI script.
        xbmc.executebuiltin('ActivateWindow(Home)', True)
        xbmc.executebuiltin('RunScript(plugin.video.silo)')
        return
    # A window-owning script must not remain inside a directory request:
    # returning to that directory can invoke another browsing session.
    from silo.browser import open_browser
    open_browser()


if __name__ == '__main__':
    main()
