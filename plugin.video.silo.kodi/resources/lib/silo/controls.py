"""Small Kodi window-property channel between browsing and the playback owner."""
import json
import uuid
import time

import xbmc
import xbmcgui

_STATE = 'plugin.video.silo.kodi.playback.state'
_REQUEST = 'plugin.video.silo.kodi.playback.request'
_COMPLETED = 'plugin.video.silo.kodi.playback.completed'


def _read(window, key):
    try:
        value = json.loads(window.getProperty(key))
        return value if isinstance(value, dict) else {}
    except (ValueError, TypeError):
        return {}


class PlaybackControls:
    def __init__(self, profile_id=None, content_id=None, title=None):
        self.window = xbmcgui.Window(10000)
        self.profile_id = profile_id
        self.content_id = content_id
        self.title = title
        self.state = {}
        self.window.clearProperty(_STATE)
        self.window.clearProperty(_REQUEST)
        self.window.clearProperty(_COMPLETED)

    def publish(self, plan, quality='auto', native_subtitles=False):
        subtitle = plan.get('subtitle') or {}
        tracks = []
        for track in subtitle.get('inventory', []):
            label = str(track.get('label') or track.get('language') or 'Subtitle')
            if track.get('forced'):
                label += ' · Forced'
            if track.get('hearing_impaired'):
                label += ' · SDH'
            pgs = track.get('codec') == 'hdmv_pgs_subtitle'
            tracks.append({'id': track['track_id'], 'label': label,
                           'supported': ((pgs and native_subtitles and track.get('source') == 'embedded')
                                         or (not pgs and track.get('delivery') == 'sidecar'))})
        # Publish only UI metadata, never stream URLs, headers, or credentials.
        self.state = {'revision': str(uuid.uuid4()), 'tracks': tracks,
                      'profile_id': self.profile_id, 'content_id': self.content_id,
                      'title': self.title,
                      'qualities': [entry['label'] for entry in plan.get('available_qualities', [])],
                      'quality': quality,
                      'selected': subtitle.get('track_id') if subtitle.get('mode') != 'off' else None}
        self.window.setProperty(_STATE, json.dumps(self.state))

    def take(self):
        request = _read(self.window, _REQUEST)
        if not request:
            return None
        self.window.clearProperty(_REQUEST)
        if request.get('revision') != self.state.get('revision'):
            return None
        if 'quality' in request and 'subtitle' not in request:
            if request['quality'] not in ['auto'] + self.state.get('qualities', []):
                return None
        elif 'subtitle' in request and 'quality' not in request:
            track = request['subtitle']
            if track is not None and not any(t['id'] == track and t['supported'] for t in self.state.get('tracks', [])):
                return None
        else:
            return None
        self.window.setProperty(_STATE, json.dumps(dict(self.state, busy=True)))
        return request

    def close(self):
        self.window.clearProperty(_STATE)
        self.window.clearProperty(_REQUEST)

    def complete(self):
        self.window.setProperty(_COMPLETED, json.dumps({'profile_id': self.profile_id,
                                'content_id': self.content_id, 'time': time.time()}))


def take_completed(profile_id):
    window = xbmcgui.Window(10000)
    event = _read(window, _COMPLETED)
    if event.get('profile_id') != profile_id:
        return None
    window.clearProperty(_COMPLETED)
    if event.get('content_id') and 0 <= time.time() - event.get('time', 0) < 60:
        return event['content_id']
    return None


def active_playback(profile_id):
    state = _read(xbmcgui.Window(10000), _STATE)
    if state.get('profile_id') == profile_id and xbmc.Player().isPlayingVideo():
        return state
    return None


def playback_options():
    window = xbmcgui.Window(10000)
    state = _read(window, _STATE)
    dialog = xbmcgui.Dialog()
    if not state or not xbmc.Player().isPlaying():
        dialog.notification('Silo', 'No Silo video is playing.')
        return
    if state.get('busy'):
        dialog.notification('Silo', 'Applying playback choice…')
        return
    action = dialog.contextmenu(['Subtitles', 'Quality'])
    if action not in (0, 1):
        return
    if action == 1:
        qualities = ['auto'] + [q for q in state.get('qualities', []) if q != 'auto']
        labels = ['Auto'] + [str(q).replace('[', '(').replace(']', ')') for q in qualities[1:]]
        selected = qualities.index(state['quality']) if state.get('quality') in qualities else 0
        choice = dialog.select('Quality', labels, preselect=selected)
        if choice < 0:
            return
        request = {'quality': qualities[choice]}
    else:
        tracks = state.get('tracks', [])
        labels = ['Off'] + [str(t['label']).replace('[', '(').replace(']', ')') +
                            ('' if t['supported'] else ' · Unavailable') for t in tracks]
        selected = next((i + 1 for i, t in enumerate(tracks) if t['id'] == state.get('selected')), 0)
        choice = dialog.select('Subtitles', labels, preselect=selected)
        if choice < 0:
            return
        if choice > 0 and not tracks[choice - 1]['supported']:
            dialog.notification('Silo', 'This subtitle format is not supported yet.')
            return
        request = {'subtitle': tracks[choice - 1]['id'] if choice else None}
    current = _read(window, _STATE)
    if current.get('revision') != state.get('revision') or current.get('busy'):
        dialog.notification('Silo', 'Playback changed. Open the menu again.')
        return
    window.setProperty(_REQUEST, json.dumps(dict(request, revision=state['revision'])))
