"""Device playback preferences persisted by Kodi."""
import xbmcaddon


def autoplay_delay():
    addon = xbmcaddon.Addon('plugin.video.silo')
    if not addon.getSettingBool('autoplay_next'):
        return None
    return max(1, min(60, addon.getSettingInt('autoplay_delay')))
