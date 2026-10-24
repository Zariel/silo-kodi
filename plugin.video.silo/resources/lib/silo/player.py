"""Kodi owns playback; this invocation owns exactly one Silo session."""
import time

import xbmc
import xbmcgui
import xbmcplugin

from .client import Error
from .playback import Attempt


class _Player(xbmc.Player):
    def __init__(self):
        super().__init__()
        self.ready = False
        self.finished = False
        self.completed = False

    def onAVStarted(self):
        self.ready = True

    def onPlayBackStopped(self):
        self.finished = True

    def onPlayBackEnded(self):
        self.completed = True
        self.finished = True

    def onPlayBackError(self):
        self.finished = True


def _owns(player, url, source):
    return player.getPlayingFile().split('|', 1)[0] in (url.split('|', 1)[0], source)


def play(handle, session, profile_id, file_id, title, start_position=None, source=None):
    attempt = None
    resolved = False
    last_position = None
    paused = False
    duration = None
    player = _Player()
    monitor = xbmc.Monitor()
    try:
        with session.store.playback_lock():
            try:
                attempt = Attempt(session, profile_id, file_id, start_position)
                url = attempt.start()
                item = xbmcgui.ListItem(label=title, path=url)
                item.setContentLookup(False)
                mime = attempt.plan['stream'].get('mime_type')
                if mime:
                    item.setMimeType(mime)
                start = attempt.plan['timeline'].get('player_start_seconds', 0)
                if start > 0:
                    item.setProperty('StartOffset', str(start))
                xbmcplugin.setResolvedUrl(handle, True, item)
                resolved = True
                deadline = time.monotonic() + 60
                next_report = 0
                resume_pending = start > 0
                seek_deadline = None
                tracks_applied = False
                while not monitor.abortRequested() and not player.finished:
                    if not player.ready:
                        if time.monotonic() > deadline:
                            break
                        monitor.waitForAbort(.25)
                        continue
                    try:
                        # A different client may replace this playback. Never send
                        # its position to Silo or stop a player we no longer own.
                        if not _owns(player, url, source):
                            xbmc.log('Silo: player changed; ending the previous session', xbmc.LOGINFO)
                            break
                        position = player.getTime()
                        duration = player.getTotalTime()
                        paused = xbmc.getCondVisibility('Player.Paused')
                    except RuntimeError:
                        break
                    if not tracks_applied:
                        if attempt.plan.get('subtitle', {}).get('mode') == 'off':
                            player.showSubtitles(False)
                        tracks_applied = True
                    if resume_pending:
                        if abs(position - start) <= 10:
                            resume_pending = False
                        elif seek_deadline is None:
                            player.seekTime(start)
                            seek_deadline = time.monotonic() + 45
                        elif time.monotonic() > seek_deadline:
                            if player.isPlaying() and _owns(player, url, source):
                                player.stop()
                            raise Error('unsupported_playback')
                        if resume_pending:
                            monitor.waitForAbort(.25)
                            continue
                    last_position = position
                    if time.monotonic() >= next_report:
                        try:
                            attempt.sample(last_position, paused)
                        except Error as exc:
                            if attempt.ended or exc.status in (401, 403) or exc.code == 'sign_in_required':
                                if player.isPlaying() and _owns(player, url, source):
                                    player.stop()
                                break
                            xbmc.log('Silo: progress temporarily unavailable', xbmc.LOGWARNING)
                        next_report = time.monotonic() + 10
                    monitor.waitForAbort(.25)
                if player.completed and duration:
                    last_position = duration
            finally:
                if attempt:
                    try:
                        attempt.stop(last_position, paused)
                    except Error:
                        xbmc.log('Silo: could not confirm playback cleanup; server expiry will reclaim the session', xbmc.LOGWARNING)
    except Error as exc:
        xbmcgui.Dialog().notification('Silo', str(exc), xbmcgui.NOTIFICATION_ERROR)
    except Exception:
        xbmc.log('Silo: playback failed', xbmc.LOGERROR)
        xbmcgui.Dialog().notification('Silo', 'Could not start playback.', xbmcgui.NOTIFICATION_ERROR)
    finally:
        if not resolved:
            xbmcplugin.setResolvedUrl(handle, False, xbmcgui.ListItem())
