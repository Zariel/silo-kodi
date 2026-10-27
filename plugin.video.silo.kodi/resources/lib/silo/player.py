"""Kodi owns playback; this invocation owns exactly one Silo session."""
import json
import time

import xbmc
import xbmcgui
import xbmcplugin

from .client import Error
from .audio import SourceAudio
from .subtitles import SourceSubtitles
from .controls import PlaybackControls
from .playback import Attempt
from .relay import MediaRelay


class _Player(xbmc.Player):
    def __init__(self):
        super().__init__()
        self.ready = False
        self.finished = False
        self.completed = False

    def onAVStarted(self):
        self.ready = True
        xbmc.log('Silo: audio/video ready', xbmc.LOGINFO)

    def onPlayBackStopped(self):
        self.finished = True

    def onPlayBackEnded(self):
        self.completed = True
        self.finished = True

    def onPlayBackError(self):
        self.finished = True


def _owns(player, url, source):
    return player.getPlayingFile().split('|', 1)[0] in (url.split('|', 1)[0], source)


def _item(title, url, source, plan):
    # Fresh items must not retain a previous plugin resolution's dynamic path.
    item = xbmcgui.ListItem(label=title, path=url)
    item.setContentLookup(False)
    if source:
        item.setProperty('original_listitem_url', source)
    mime = plan['stream'].get('mime_type')
    if mime:
        item.setMimeType(mime)
    start = plan['timeline'].get('player_start_seconds', 0)
    if start > 0:
        item.setProperty('StartOffset', str(start))
    return item


def _track_state(properties):
    def request(method, params=None):
        response = json.loads(xbmc.executeJSONRPC(json.dumps(
            {'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params or {}})))
        if 'result' not in response:
            raise Error('playback_state_unavailable')
        return response['result']

    players = [item for item in request('Player.GetActivePlayers') if item.get('type') == 'video']
    if len(players) != 1:
        raise Error('playback_state_unavailable')
    return request('Player.GetProperties', {'playerid': players[0]['playerid'],
                                           'properties': properties})


def play(handle, session, profile_id, file_id, title, start_position=None, source=None, subtitle_track_id=None, content_id=None):
    attempt = None
    relay = None
    controls = None
    skip_intro = None
    resolved = False
    last_position = None
    paused = False
    duration = None
    pending_url = None
    restore_pause = None
    pause_requested = False
    player = _Player()
    monitor = xbmc.Monitor()
    try:
        with session.store.playback_lock():
            try:
                controls = PlaybackControls(profile_id, content_id, title)
                attempt = Attempt(session, profile_id, file_id, start_position,
                                  subtitle_track_id=subtitle_track_id, content_id=content_id)
                if attempt.intro:
                    import xbmcaddon
                    from .skip_intro import SkipIntro
                    skip_intro = SkipIntro('SkipIntro.xml', xbmcaddon.Addon('plugin.video.silo.kodi').getAddonInfo('path'),
                                           'Default', '1080i', segment=attempt.intro,
                                           automatic=xbmcaddon.Addon('plugin.video.silo.kodi').getSettingBool('auto_skip_intro'))
                audio = SourceAudio(file_id, attempt.audio_tracks,
                                    lambda value: xbmc.convertLanguage(value, xbmc.ISO_639_2)) if attempt.audio_tracks else None
                subtitles = SourceSubtitles(attempt.subtitle_tracks,
                                            lambda value: xbmc.convertLanguage(value, xbmc.ISO_639_2)) if attempt.native_subtitles else None
                attempt.start()
                video_name = 'video'
                resources = {video_name: attempt.plan['stream']}
                subtitle_name = None
                if attempt.subtitle_url:
                    artifact = attempt.plan['subtitle']['artifact']
                    subtitle_name = 'subtitle.' + ('srt' if artifact['format'] == 'srt' else 'vtt')
                    resources[subtitle_name] = artifact
                relay = MediaRelay(session, profile_id, resources)
                url = relay.url(video_name)
                xbmc.log('Silo: playback plan accepted', xbmc.LOGINFO)
                start = attempt.plan['timeline'].get('player_start_seconds', 0)
                xbmcplugin.setResolvedUrl(handle, True, _item(title, url, source, attempt.plan))
                resolved = True
                deadline = time.monotonic() + 60
                next_report = 0
                resume_pending = start > 0
                seek_deadline = None
                tracks_applied = False
                audio_deadline = None
                subtitle_deadline = None
                while not monitor.abortRequested():
                    if pending_url is not None:
                        if skip_intro:
                            skip_intro.close()
                        # Core changes can emit an old stop callback. Commit only
                        # after the new dynamic URL is observed with A/V ready.
                        try:
                            current = player.getPlayingFile().split('|', 1)[0] if player.isPlaying() else None
                        except RuntimeError:
                            current = None
                        if current and current not in (url, pending_url, source):
                            break
                        if current == url and player.ready:
                            pending_url = None
                            player.finished = False
                            player.completed = False
                        elif time.monotonic() > deadline:
                            raise Error('unsupported_playback')
                        else:
                            monitor.waitForAbort(.25)
                            continue
                    if player.finished:
                        break
                    if not player.ready:
                        if time.monotonic() > deadline:
                            xbmc.log('Silo: player readiness timed out', xbmc.LOGWARNING)
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
                    if resume_pending:
                        if abs(position - start) <= 10:
                            resume_pending = False
                        elif seek_deadline is None:
                            player.seekTime(start)
                            seek_deadline = time.monotonic() + 45
                        elif time.monotonic() > seek_deadline:
                            raise Error('unsupported_playback')
                        if resume_pending:
                            monitor.waitForAbort(.25)
                            continue
                    if restore_pause is not None:
                        if paused == restore_pause:
                            restore_pause = None
                        elif not pause_requested:
                            player.pause()
                            pause_requested = True
                            deadline = time.monotonic() + 10
                        elif time.monotonic() > deadline:
                            raise Error('unsupported_playback')
                        if restore_pause is not None:
                            monitor.waitForAbort(.25)
                            continue
                    if not tracks_applied and audio and attempt.plan.get('delivery') == 'original_http':
                        identity = attempt.plan.get('selected_tracks', {}).get('audio')
                        if identity:
                            observed = _track_state(['audiostreams', 'currentaudiostream'])
                            native_index = audio.native_index(identity, observed['audiostreams'])
                            if not _owns(player, url, source):
                                break
                            if observed['currentaudiostream'].get('index') != native_index:
                                if audio_deadline is None:
                                    player.setAudioStream(native_index)
                                    audio_deadline = time.monotonic() + 15
                                elif time.monotonic() > audio_deadline:
                                    raise Error('audio_selection_unavailable')
                                monitor.waitForAbort(.25)
                                continue
                    last_position = position
                    if skip_intro:
                        target = skip_intro.update(position, duration,
                                                   attempt.plan.get('timeline', {}).get('timeline_offset_seconds', 0) == 0)
                        if target is not None and _owns(player, url, source):
                            player.seekTime(target)
                    request = controls.take()
                    if request is not None:
                        previous_delivery = attempt.plan.get('delivery')
                        audio_track = None
                        try:
                            if previous_delivery == 'original_http':
                                if attempt.plan.get('selected_tracks', {}).get('audio'):
                                    if audio is None:
                                        raise Error('audio_selection_unavailable')
                                    observed = _track_state(['audiostreams', 'currentaudiostream'])
                                    audio_track = audio.identity(observed['audiostreams'], observed['currentaudiostream'].get('index'))
                                selected = next((track for track in attempt.plan.get('subtitle', {}).get('inventory', [])
                                                 if track['track_id'] == request.get('subtitle')), None)
                                if selected and selected.get('codec') == 'hdmv_pgs_subtitle':
                                    if subtitles is None:
                                        raise Error('subtitle_selection_unavailable')
                                    observed = _track_state(['subtitles'])
                                    subtitles.check_selection(selected, observed['subtitles'])
                        except Error as exc:
                            # Identity uncertainty must not retire a working plan.
                            controls.publish(attempt.plan, attempt.body['quality_preference'], native_subtitles=attempt.native_subtitles)
                            xbmcgui.Dialog().notification('Silo', str(exc), xbmcgui.NOTIFICATION_ERROR)
                            continue
                        if not _owns(player, url, source):
                            break
                        quality_change = 'quality' in request
                        if quality_change:
                            attempt.select_quality(request['quality'], position, audio_track=audio_track)
                        else:
                            attempt.select_subtitle(request['subtitle'], position, audio_track=audio_track)
                        if not _owns(player, url, source):
                            break
                        # HLS demuxers retain segment grants from their playlist.
                        # Reopen each new HLS plan to acquire its replacement grants.
                        reopen = (quality_change or previous_delivery == 'server_transcode_hls'
                                  or attempt.plan.get('delivery') == 'server_transcode_hls')
                        if reopen:
                            video_name = 'video-' + attempt.plan_attempt_id
                        resources = {video_name: attempt.plan['stream']}
                        if attempt.subtitle_url:
                            artifact = attempt.plan['subtitle']['artifact']
                            subtitle_name = 'subtitle-' + attempt.plan_attempt_id + ('.srt' if artifact['format'] == 'srt' else '.vtt')
                            resources[subtitle_name] = artifact
                        relay.update(resources)
                        tracks_applied = False
                        audio_deadline = None
                        subtitle_deadline = None
                        if reopen:
                            pending_url = url
                            url = relay.url(video_name)
                            restore_pause = paused
                            pause_requested = False
                            player.ready = False
                            player.finished = False
                            player.completed = False
                            start = attempt.plan['timeline'].get('player_start_seconds', 0)
                            resume_pending = start > 0
                            seek_deadline = None
                            deadline = time.monotonic() + 60
                            player.play(url, _item(title, url, source, attempt.plan))
                            continue
                    if not tracks_applied:
                        if attempt.embedded_subtitle_index is not None:
                            observed = _track_state(['subtitles', 'currentsubtitle', 'subtitleenabled'])
                            native_index = subtitles.native_index(attempt.embedded_subtitle_index, observed['subtitles'])
                            if not _owns(player, url, source):
                                break
                            if observed['currentsubtitle'].get('index') != native_index or not observed['subtitleenabled']:
                                if subtitle_deadline is None:
                                    player.setSubtitleStream(native_index)
                                    player.showSubtitles(True)
                                    subtitle_deadline = time.monotonic() + 15
                                elif time.monotonic() > subtitle_deadline:
                                    raise Error('subtitle_selection_unavailable')
                                monitor.waitForAbort(.25)
                                continue
                        elif attempt.subtitle_url:
                            player.setSubtitles(relay.url(subtitle_name))
                            player.showSubtitles(True)
                        else:
                            player.showSubtitles(False)
                        tracks_applied = True
                        controls.publish(attempt.plan, attempt.body['quality_preference'], native_subtitles=attempt.native_subtitles)
                    if time.monotonic() >= next_report:
                        try:
                            attempt.sample(last_position, paused)
                        except Error as exc:
                            if attempt.ended or exc.status in (401, 403) or exc.code == 'sign_in_required':
                                break
                            xbmc.log('Silo: progress temporarily unavailable', xbmc.LOGWARNING)
                        next_report = time.monotonic() + 10
                    monitor.waitForAbort(.25)
                if player.completed and duration and pending_url is None:
                    last_position = duration
            finally:
                if skip_intro:
                    skip_intro.close()
                if controls:
                    controls.close()
                # Close the player before revoking its stream, including failures
                # after resolution. A replacement belongs to its new caller.
                if resolved:
                    try:
                        if player.isPlaying() and (_owns(player, url, source)
                                or (pending_url is not None and _owns(player, pending_url, source))):
                            player.stop()
                    except RuntimeError:
                        pass
                try:
                    if relay:
                        relay.close()
                finally:
                    if attempt:
                        try:
                            xbmc.log('Silo: closing playback session', xbmc.LOGINFO)
                            attempt.stop(last_position, paused)
                            xbmc.log('Silo: playback session closed', xbmc.LOGINFO)
                            if controls and player.completed and duration and pending_url is None:
                                # Publish before releasing ownership; a subsequent start clears this event.
                                controls.complete()
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
