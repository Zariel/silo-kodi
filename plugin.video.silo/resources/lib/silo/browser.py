"""Silo browsing windows using Kodi rendering and remote navigation."""
from pathlib import Path
import re
import threading
from urllib.parse import urlencode

import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs

from .catalog import Catalog, artwork
from .client import Error, Session
from .ui import open_account, _text


class BrowserWindow(xbmcgui.WindowXML):
    def __init__(self, *args, session, **kwargs):
        super().__init__(*args, **kwargs)
        self.session = session
        self.catalog = Catalog(session)
        self.libraries = []
        self.history = []
        self.page = None
        self.account_requested = False
        self.closed = threading.Event()
        self.busy = False
        self.worker = None

    def onInit(self):
        if self.page:
            def restore():
                self._menu()
                self._show(self.page)
            self._task(restore)
            return
        self.setProperty('accent', 'FFE8E8EC')
        self._task(self._load)

    def _task(self, operation):
        if self.busy or self.closed.is_set():
            return
        self.busy = True
        self.getControl(20).setLabel('Loading…')
        def work():
            try:
                operation()
                if not self.closed.is_set():
                    self.getControl(20).setLabel('')
            except Error as exc:
                if not self.closed.is_set():
                    self.getControl(20).setLabel(_text(exc))
            except Exception:
                xbmc.log('Silo: browsing operation failed', xbmc.LOGERROR)
                if not self.closed.is_set():
                    self.getControl(20).setLabel('Could not load this page. Go Back and try again.')
            finally:
                self.busy = False
        self.worker = threading.Thread(target=work, daemon=True)
        self.worker.start()

    def _load(self):
        try:
            accent = self.session.public('/theme/branding').get('accent_color', '')
            if re.fullmatch(r'#[0-9a-fA-F]{6}', accent) and not self.closed.is_set():
                self.setProperty('accent', 'FF' + accent[1:].upper())
        except Error:
            pass
        self.libraries = self.catalog.libraries()
        if self.closed.is_set():
            return
        self._menu()
        if self.libraries:
            self._library(self.libraries[0])
        else:
            self.getControl(12).setLabel('No video libraries available')
            self.setFocusId(100)

    def _menu(self):
        menu = self.getControl(100)
        menu.reset()
        for library in self.libraries:
            menu.addItem(xbmcgui.ListItem(_text(library['name'])))
        menu.addItem(xbmcgui.ListItem('Account'))
        menu.addItem(xbmcgui.ListItem('Close'))
        self.getControl(11).setLabel(_text(self.session.status()['profile']['name']))

    def _library(self, library):
        data = self.catalog.page(library['id'])
        if self.closed.is_set():
            return
        self.history = []
        self._show(dict(data, kind='library', title=library['name'], library=library))

    def _remember(self):
        if self.page:
            self.page['focus'] = self.getFocusId()
            control = {'library': 200, 'item': 210, 'season': 220}[self.page['kind']]
            self.page['selection'] = max(0, self.getControl(control).getSelectedPosition())

    def _push(self, page):
        if self.closed.is_set():
            return
        self._remember()
        if self.page:
            self.history.append(self.page)
        self._show(page)

    def _card(self, data, label=None, art_key='poster_url'):
        item = xbmcgui.ListItem(_text(label or data.get('title') or 'Untitled'))
        item.setArt({'poster': artwork(self.session.server, data.get(art_key))})
        item.setProperty('summary', _text(data.get('overview') or ''))
        item.setProperty('meta', _text(data.get('year') or data.get('air_date') or ''))
        return item

    def _show(self, page):
        if self.closed.is_set():
            return
        profile = self.session.status()['profile']
        if profile is None or profile['id'] != self.catalog.profile_id:
            raise Error('profile_changed')
        self.page = page
        kind = page['kind']
        self.setProperty('view', kind)
        self.getControl(12).setLabel(_text(page['title']))
        self.getControl(21).setLabel('')
        self.getControl(22).setText('')
        self.getControl(30).setImage('')
        self.getControl(31).setImage('')
        for identifier in (200, 210, 220):
            self.getControl(identifier).reset()
        self.getControl(300).setVisible(False)
        self.getControl(301).setVisible(kind != 'library')
        if kind == 'library':
            control_id = 200
            control = self.getControl(control_id)
            for data in page['items']:
                control.addItem(self._card(data))
            if page.get('next_cursor'):
                control.addItem(xbmcgui.ListItem('Load more'))
            if not page['items'] and not page.get('next_cursor'):
                self.getControl(21).setLabel('This library has no visible titles.')
        else:
            data = page['data']
            self.getControl(30).setImage(artwork(self.session.server, data.get('backdrop_url')))
            self.getControl(31).setImage(artwork(self.session.server, data.get('poster_url')))
            metadata = [str(data[key]) for key in ('year', 'content_rating') if data.get(key)]
            if data.get('runtime'):
                metadata.append('{} min'.format(data['runtime']))
            self.getControl(21).setLabel(_text('  •  '.join(metadata)))
            self.getControl(22).setText(_text(data.get('overview') or ''))
            if kind == 'season':
                control_id = 220
                for episode in page['items']:
                    label = '{}. {}'.format(episode['episode_number'], episode.get('title') or 'Episode')
                    self.getControl(220).addItem(self._card(episode, label, 'still_url'))
                if not page['items']:
                    self.getControl(21).setLabel('No episodes available.')
            else:
                control_id = 210
                if data['type'] == 'series':
                    for season in page['items']:
                        label = 'Specials' if season['season_number'] == 0 else 'Season {}'.format(season['season_number'])
                        card = self._card(season, label)
                        card.setProperty('meta', '{} episodes'.format(season.get('episode_count', 0)))
                        self.getControl(210).addItem(card)
                else:
                    self.getControl(300).setVisible(True)
                    self.getControl(300).setEnabled(True)
                    self.getControl(300).setLabel('Play')
        control = self.getControl(control_id)
        control.selectItem(page.get('selection', 0))
        playable = kind == 'item' and page['data']['type'] in ('movie', 'episode')
        focus = page.get('focus', 300 if playable else control_id if control.size() else 301 if kind != 'library' else 100)
        self.setFocusId(focus)
        destination = 300 if playable else control_id if control.size() else 301 if kind != 'library' else 100
        self.getControl(100).controlRight(self.getControl(destination))
        self.getControl(301).controlRight(self.getControl(control_id if control.size() else 100))
        self.getControl(301).controlUp(self.getControl(control_id if control.size() else 100))
        self.getControl(301).controlDown(self.getControl(control_id if control.size() else 100))
        if playable:
            self.getControl(301).controlUp(self.getControl(300))
            self.getControl(300).controlRight(self.getControl(301))

    def _detail(self, content_id):
        data = self.catalog.item(content_id)
        if data.get('type') not in ('movie', 'series', 'episode'):
            raise Error('invalid_response')
        seasons = self.catalog.seasons(content_id) if data['type'] == 'series' else []
        self._push({'kind': 'item', 'title': data.get('title') or 'Untitled', 'data': data, 'items': seasons})

    def _season(self, season):
        series = self.page['data']
        episodes = self.catalog.episodes(series['content_id'], season['season_number'])
        data = dict(series, poster_url=season.get('poster_url') or series.get('poster_url'))
        title = '{} · {}'.format(series['title'], 'Specials' if season['season_number'] == 0 else 'Season {}'.format(season['season_number']))
        self._push({'kind': 'season', 'title': title, 'data': data, 'items': episodes})

    def _more(self):
        self._remember()
        page = self.page
        data = self.catalog.page(page['library']['id'], page['next_cursor'])
        # A cursor page can overlap if the server catalog changed while browsing.
        known = {item['content_id'] for item in page['items']}
        items = page['items'] + [item for item in data['items'] if item['content_id'] not in known]
        self._show(dict(page, items=items, next_cursor=data['next_cursor']))

    def _play(self):
        if xbmc.Player().isPlaying():
            raise Error('playback_active')
        data = self.page['data']
        versions = [version for version in self.catalog.versions(data['content_id']) if not version.get('unreadable')]
        if not versions:
            raise Error('unsupported_playback')
        index = 0
        if len(versions) > 1:
            labels = [' · '.join(str(version.get(key) or '') for key in ('resolution', 'codec_video', 'codec_audio', 'container')) for version in versions]
            index = xbmcgui.Dialog().select('Choose version', labels)
        if index < 0 or self.closed.is_set():
            return
        watch = self.catalog.watch(data['content_id']).get('user_data') or {}
        position = watch.get('position_seconds') or 0
        restart = False
        if position > 0 and not watch.get('played'):
            if self.closed.is_set():
                return
            seconds = int(position)
            stamp = '{}:{:02d}:{:02d}'.format(seconds // 3600, seconds // 60 % 60, seconds % 60)
            choice = xbmcgui.Dialog().contextmenu(['Resume from ' + stamp, 'Play from beginning'])
            if choice < 0:
                return
            restart = choice == 1
        if self.closed.is_set():
            return
        query = {'action': 'play', 'profile': self.catalog.profile_id,
                 'file': versions[index]['file_id'], 'title': data.get('title') or 'Silo'}
        if restart:
            query['restart'] = 'true'
        self._remember()
        xbmc.Player().play('plugin://plugin.video.silo/?' + urlencode(query))

    def _back(self):
        if self.busy:
            return
        if self.history:
            page = self.history.pop()
            self._task(lambda: self._show(page))
        else:
            self.close()

    def onClick(self, control):
        if self.busy:
            return
        if control == 100:
            index = self.getControl(100).getSelectedPosition()
            if index < len(self.libraries):
                self._task(lambda: self._library(self.libraries[index]))
            elif index == len(self.libraries):
                self.account_requested = True
                self.close()
            else:
                self.close()
        elif control == 200:
            index = self.getControl(200).getSelectedPosition()
            if index == len(self.page['items']):
                self._task(self._more)
            elif index >= 0:
                content_id = self.page['items'][index]['content_id']
                self._task(lambda: self._detail(content_id))
        elif control == 210:
            index = self.getControl(210).getSelectedPosition()
            if index >= 0:
                season = self.page['items'][index]
                self._task(lambda: self._season(season))
        elif control == 220:
            index = self.getControl(220).getSelectedPosition()
            if index >= 0:
                content_id = self.page['items'][index]['content_id']
                self._task(lambda: self._detail(content_id))
        elif control == 301:
            self._back()
        elif control == 300:
            self._task(self._play)

    def onAction(self, action):
        if action.getId() in (9, 10, 92):
            if self.busy:
                self.close()
            else:
                self._back()

    def close(self):
        self.closed.set()
        super().close()

    def finish(self):
        self.closed.set()
        if self.worker:
            self.worker.join(timeout=35)


def open_browser():
    addon = xbmcaddon.Addon()
    directory = Path(xbmcvfs.translatePath(addon.getAddonInfo('profile')))
    session = Session.open(directory)
    if not session or not session.status()['signed_in'] or not session.status()['profile']:
        open_account()
    while True:
        session = Session.open(directory)
        if not session or not session.status()['signed_in'] or not session.status()['profile']:
            return
        window = BrowserWindow('Browser.xml', addon.getAddonInfo('path'), 'Default', '1080i', session=session)
        try:
            window.doModal()
        finally:
            window.finish()
        if not window.account_requested:
            return
        open_account()
