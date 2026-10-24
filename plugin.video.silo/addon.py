"""Installable scaffold for validating the Kodi development loop."""

import json
import sys
from urllib.error import URLError
from urllib.parse import parse_qs
from urllib.request import urlopen

import xbmc
import xbmcaddon
import xbmcgui
import xbmcplugin
import xbmcvfs


def main():
    handle = int(sys.argv[1])
    action = parse_qs(sys.argv[2].lstrip("?")).get("action", [""])[0]

    if action == "smoke":
        # The development harness creates this fixture; it is never packaged.
        path = "special://temp/silo-kodi-smoke.wav"
        item = xbmcgui.ListItem(path=path)
        item.setMimeType("audio/wav")
        item.setContentLookup(False)
        xbmcplugin.setResolvedUrl(handle, xbmcvfs.exists(path), item)
        return

    xbmcplugin.setPluginCategory(handle, "Silo")
    xbmcplugin.setContent(handle, "files")
    server = xbmcaddon.Addon().getSetting("server_url").rstrip("/")
    try:
        if not server:
            raise ValueError("Server URL is not configured")
        with urlopen(server + "/api/v2/system/info", timeout=10) as response:
            info = json.load(response)
        label = "Silo connected — API v{}".format(info["api_major"])
    except (URLError, TimeoutError, ValueError, KeyError):
        label = "Silo unavailable — check the server connection" if server else "Set Server URL in Silo settings"
        xbmc.log("Silo: server probe failed", xbmc.LOGWARNING)

    for label in (label, "Setup build: sign-in and browsing are not implemented yet"):
        item = xbmcgui.ListItem(label=label)
        xbmcplugin.addDirectoryItem(handle, "", item, isFolder=False)
    xbmcplugin.endOfDirectory(handle, cacheToDisc=False)


if __name__ == "__main__":
    main()
