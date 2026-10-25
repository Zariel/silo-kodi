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
from .controls import active_playback, playback_options
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
        self.playback_page = None
        self.playback_history = []
        self.closed = threading.Event()
        self.busy = False
        self.keep_sidebar_focus = False
        self.home_entry_focus = 100
        self.worker = None
        self.pager = None
        self.publish_lock = threading.Lock()

    def onInit(self):
        if self.pager is None:
            self.pager = threading.Thread(target=self._page_loop, daemon=True)
            self.pager.start()
        if self.page:
            def restore():
                self._menu()
                self._show(self.page)
            self._task(restore)
            return
        self.setProperty('accent', 'FFE8E8EC')
        self._task(self._load)

    def _task(self, operation):
        with self.publish_lock:
            if self.busy or self.closed.is_set():
                return
            self.busy = True
            self.keep_sidebar_focus = False
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
        self.setFocusId(100)
        self._home()

    def _menu(self):
        menu = self.getControl(100)
        menu.reset()
        media = Path(xbmcaddon.Addon('plugin.video.silo').getAddonInfo('path')) / 'resources/skins/Default/media'

        def add(label, icon):
            item = xbmcgui.ListItem(label)
            item.setProperty('nav_icon', str(media / ('nav-' + icon + '.png')))
            menu.addItem(item)

        add('Home', 'home')
        add('Search', 'search')
        for library in self.libraries:
            add(_text(library['name']), 'tv' if library.get('type') == 'series' else 'movies')
        add('Account', 'account')
        add('Close', 'close')
        self.getControl(11).setLabel(_text(self.session.status()['profile']['name']))

    def _home(self):
        sections = self.catalog.home()
        if self.closed.is_set():
            return
        self.history = []
        self._show({'kind': 'home', 'title': 'Home', 'sections': sections,
                    'offset': 0, 'positions': {}})

    def _home_row(self, page, index):
        section = page['sections'][index]
        return self.catalog.home_section(section['id'])

    def _home_rows(self, page):
        visible = []
        index = page['offset']
        while index < len(page['sections']) and len(visible) < 2:
            row = self._home_row(page, index)
            if row['items']:
                visible.append((index, row))
            index += 1
        return visible, index

    def _show_home(self, page, visible, index):
        page['visible'] = visible
        page['next_row'] = index
        for slot in range(2):
            control = self.getControl(230 + slot)
            self.getControl(40 + slot).setLabel('')
            if slot >= len(visible):
                control.reset()
                continue
            _, row = visible[slot]
            self.getControl(40 + slot).setLabel(_text(row['title']))
            cards = [self._card(data) for data in row['items']]
            cards.append(xbmcgui.ListItem('View all'))
            control.reset()
            control.addItems(cards)
            selected = page['positions'].get(row['id'])
            position = next((i for i, item in enumerate(row['items'])
                             if item['content_id'] == selected), 0)
            if selected == '__all__':
                position = len(row['items'])
            control.selectItem(position)
        focus = page.get('focus', 230) if visible else 100
        if visible and self.home_entry_focus is not None:
            focus = self.home_entry_focus
            if focus == 230:
                self.home_entry_focus = None
        if focus == 231 and len(visible) < 2:
            focus = 230 if visible else 100
        if self.keep_sidebar_focus:
            focus = 100
        self.setFocusId(focus)
        self.getControl(100).controlRight(self.getControl(230 if visible else 100))
        if not visible:
            self.getControl(21).setLabel('No titles on Home. Browse a library from the menu.')

    def _move_home(self, direction):
        page = self.page
        slot = self.getFocusId() - 230
        visible = page['visible']
        self._remember()
        if direction > 0:
            if slot == 0 and len(visible) > 1:
                self.setFocusId(231)
            elif page['next_row'] < len(page['sections']):
                page['offset'] = visible[-1][0]
                page['focus'] = 231
                self._show(page)
        elif slot == 1:
            self.setFocusId(230)
        elif visible and visible[0][0] > 0:
            index = visible[0][0] - 1
            while index > 0 and not self._home_row(page, index)['items']:
                index -= 1
            page['offset'] = index
            page['focus'] = 230
            self._show(page)
        else:
            self.setFocusId(100)

    def _section(self, row):
        data = self.catalog.home_page(row['id'])
        self._push(dict(data, kind='section', title=row['title'], section=row['id'],
                        section_type=row.get('section_type')))

    def _library(self, library):
        self.home_entry_focus = None
        data = self.catalog.page(library['id'])
        if self.closed.is_set():
            return
        self.history = []
        self._show(dict(data, kind='library', title=library['name'], library=library))

    def _search(self):
        previous = self.page.get('query', '') if self.page else ''
        self.getControl(20).setLabel('')
        query = xbmcgui.Dialog().input('Search Silo', defaultt=previous).strip()
        if not query or self.closed.is_set():
            return
        data = self.catalog.search(query)
        self._push(dict(data, kind='search', title='Search: ' + query, query=query))

    def _selected(self):
        if not self.page:
            return None
        focus = self.getFocusId()
        if focus in (230, 231) and self.page['kind'] == 'home':
            rows = self.page.get('visible', [])
            slot = focus - 230
            items = rows[slot][1]['items'] if slot < len(rows) else []
        elif focus in (200, 220):
            items = self.page.get('items', [])
        elif focus == 300 and self.page['kind'] == 'item':
            return self.page['data']
        else:
            return None
        index = self.getControl(focus).getSelectedPosition()
        return items[index] if 0 <= index < len(items) else None

    def _home_dismissal(self, selected):
        section_type = self.page.get('section_type')
        if self.page['kind'] == 'home':
            slot = self.getFocusId() - 230
            section_type = self.page['visible'][slot][1].get('section_type')
        if section_type not in ('continue_watching', 'in_progress', 'next_up'):
            return None
        for surface, field, label in (
                ('continue_watching', 'progress_updated_at', 'Remove from Continue Watching'),
                ('next_up', 'series_id', 'Remove from Next Up')):
            anchor = selected.get(field)
            if isinstance(anchor, str) and anchor.strip():
                return surface, anchor, label
        return None

    def _context(self):
        selected = self._selected()
        playing = active_playback(self.catalog.profile_id)
        if not selected or not selected.get('content_id'):
            if playing:
                playback_options()
            return
        data = self.catalog.item(selected['content_id'])
        choices = []
        if data['type'] in ('movie', 'episode'):
            choices.append(('Play / Resume', 'play'))
        state = data.get('user_state') or {}
        for field, on, off in (('played', 'Mark watched', 'Mark unwatched'),
                               ('is_favorite', 'Add to favourites', 'Remove from favourites'),
                               ('in_watchlist', 'Add to watchlist', 'Remove from watchlist')):
            if type(state.get(field)) is bool:
                label = off if state[field] else on
                if field == 'played' and data['type'] == 'series':
                    label += ' (all episodes)'
                choices.append((label, field))
        dismissal = self._home_dismissal(selected)
        if dismissal:
            choices.append((dismissal[2], 'dismiss'))
        choices.append(('Details', 'detail'))
        if playing:
            choices.append(('Playback options', 'playback'))
        self.getControl(20).setLabel('')
        choice = xbmcgui.Dialog().contextmenu([label for label, _ in choices])
        if choice < 0 or self.closed.is_set():
            return
        action = choices[choice][1]
        if action == 'playback':
            playback_options()
        elif action == 'dismiss':
            self.catalog.dismiss_home(data['content_id'], dismissal[0], dismissal[1])
            self._refresh_action()
            xbmcgui.Dialog().notification('Silo', 'Removed from Home', time=1500, sound=False)
        elif action in ('detail', 'play'):
            if self.page['kind'] != 'item' or self.page['data']['content_id'] != data['content_id']:
                self._detail(data['content_id'])
            if action == 'play':
                self._play()
        else:
            fresh = self.catalog.set_state(data['content_id'], action, not state[action])
            selected.update(fresh)
            self._refresh_action()
            xbmcgui.Dialog().notification('Silo', 'Updated', time=1500, sound=False)

    def _refresh_action(self):
        self._remember()
        page = self.page
        if page['kind'] == 'section':
            selected = self._selected()
            fresh = self.catalog.home_page(page['section'])
            # A new page identity also invalidates an in-flight prefetch from
            # before the mutation. The server owns membership and ordering.
            page = dict(fresh, kind='section', title=page['title'], section=page['section'],
                        section_type=page.get('section_type'))
            page['selection'] = next((i for i, item in enumerate(page['items'])
                                      if selected and item['content_id'] == selected['content_id']), 0)
        self._show(page)

    def _remember(self):
        if self.page:
            self.page['focus'] = self.getFocusId()
            if self.page['kind'] == 'home':
                for slot, (_, row) in enumerate(self.page.get('visible', [])):
                    position = self.getControl(230 + slot).getSelectedPosition()
                    self.page['positions'][row['id']] = (row['items'][position]['content_id']
                                                         if 0 <= position < len(row['items']) else '__all__')
                return
            control = {'library': 200, 'section': 200, 'search': 200, 'item': 210, 'season': 220}[self.page['kind']]
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
        meta = []
        if data.get('type') == 'series':
            meta.append('TV')
        elif data.get('type') == 'episode':
            season, episode = data.get('season_number'), data.get('episode_number')
            meta.append('S{} E{}'.format(season, episode) if season is not None and episode is not None else 'Episode')
        date = data.get('year') or data.get('air_date')
        if date:
            meta.append(str(date))
        item.setProperty('meta', _text(' · '.join(meta)))
        return item

    def _show(self, page):
        if self.closed.is_set():
            return
        # Keep the current controls and focus valid while fetching Home rows.
        # Emptying a focused shelf makes Kodi fall back to the default sidebar.
        rows = self._home_rows(page) if page['kind'] == 'home' else None
        if self.closed.is_set():
            return
        profile = self.session.status()['profile']
        if profile is None or profile['id'] != self.catalog.profile_id:
            raise Error('profile_changed')
        self.page = page
        page.pop('paging_failed', None)
        kind = page['kind']
        if kind != 'home':
            self.home_entry_focus = None
        self.setProperty('view', kind)
        self.getControl(12).setLabel(_text(page['title']))
        self.getControl(21).setLabel('')
        self.getControl(22).setText('')
        self.getControl(30).setImage('')
        self.getControl(31).setImage('')
        for identifier in ((200, 210, 220) if kind == 'home' else (200, 210, 220, 230, 231)):
            self.getControl(identifier).reset()
        self.getControl(300).setVisible(False)
        self.getControl(301).setVisible(kind in ('item', 'season'))
        if kind == 'home':
            self._show_home(page, *rows)
            return
        if kind in ('library', 'section', 'search'):
            control_id = 200
            control = self.getControl(control_id)
            for data in page['items']:
                control.addItem(self._card(data))
            if not page['items'] and not page.get('next_cursor'):
                self.getControl(21).setLabel('No matching titles.' if page['kind'] == 'search' else 'This library has no visible titles.')
        else:
            data = page['data']
            self.getControl(30).setImage(artwork(self.session.server, data.get('backdrop_url')))
            self.getControl(31).setImage(artwork(self.session.server, data.get('poster_url')))
            metadata = [str(data[key]) for key in ('year', 'content_rating') if data.get(key)]
            if data.get('runtime'):
                metadata.append('{} min'.format(data['runtime']))
            metadata.extend(data.get('genres', [])[:3])
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
                    playing = active_playback(self.catalog.profile_id)
                    self.getControl(300).setLabel('Return to video' if playing and
                                                 playing.get('content_id') == data['content_id'] else 'Play')
        control = self.getControl(control_id)
        control.selectItem(page.get('selection', 0))
        playable = kind == 'item' and page['data']['type'] in ('movie', 'episode')
        focus = page.get('focus', 300 if playable else control_id if control.size() else 301 if kind in ('item', 'season') else 100)
        if self.keep_sidebar_focus:
            focus = 100
        self.setFocusId(focus)
        destination = 300 if playable else control_id if control.size() else 301 if kind in ('item', 'season') else 100
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

    def _page_loop(self):
        while not self.closed.wait(.15):
            page = self.page
            try:
                self._prefetch()
            except Exception:
                if page is not None:
                    page['paging_failed'] = True
                xbmc.log('Silo: background paging failed', xbmc.LOGERROR)

    def _prefetch(self):
        page = self.page
        if (self.busy or self.closed.is_set() or not page
                or page['kind'] not in ('library', 'section', 'search')
                or not page.get('next_cursor') or page.get('paging_failed')):
            return
        control = self.getControl(200)
        # Keep a full server page plus a screen ahead of the selection.
        if len(page['items']) - max(0, control.getSelectedPosition()) > 74:
            return
        cursor = page['next_cursor']
        try:
            if page['kind'] == 'section':
                data = self.catalog.home_page(page['section'], cursor)
            elif page['kind'] == 'search':
                data = self.catalog.search(page['query'], cursor)
            else:
                data = self.catalog.page(page['library']['id'], cursor)
        except Exception:
            page['paging_failed'] = True
            with self.publish_lock:
                if self.page is page and not self.busy and not self.closed.is_set():
                    self.getControl(20).setLabel('Could not load more titles. Reopen this page to retry.')
            return

        while self.busy and not self.closed.wait(.1):
            pass
        with self.publish_lock:
            # Navigation owns the controls while a foreground operation is running.
            if self.closed.is_set() or self.busy or self.page is not page:
                return
            profile = self.session.status()['profile']
            if profile is None or profile['id'] != self.catalog.profile_id:
                page['paging_failed'] = True
                return
            seen = page.setdefault('cursors', set())
            seen.add(cursor)
            known = {item['content_id'] for item in page['items']}
            added = []
            for item in data['items']:
                if item['content_id'] not in known:
                    known.add(item['content_id'])
                    added.append(item)
            page['items'].extend(added)
            if added:
                selection = max(0, control.getSelectedPosition())
                # Kodi rebinds the entire list on addItems; restore focus in the same message batch.
                control.addItems([self._card(item) for item in added])
                control.selectItem(selection)
            next_cursor = data['next_cursor']
            page['next_cursor'] = next_cursor if next_cursor not in seen else None
            if not page['items'] and not page['next_cursor']:
                self.getControl(21).setLabel('No matching titles.' if page['kind'] == 'search' else 'This library has no visible titles.')
            if page['items']:
                self.getControl(100).controlRight(control)

    def _play(self):
        playing = active_playback(self.catalog.profile_id)
        if playing and playing.get('content_id') == self.page['data']['content_id']:
            self._video()
            return
        if xbmc.Player().isPlaying():
            raise Error('playback_active')
        data = self.page['data']
        watch = self.catalog.watch(data['content_id'])
        versions = watch['versions']
        if not versions:
            raise Error('unsupported_playback')
        index = 0
        if len(versions) > 1:
            labels = [' · '.join(str(version.get(key) or '') for key in ('resolution', 'codec_video', 'codec_audio', 'container')) for version in versions]
            index = xbmcgui.Dialog().select('Choose version', labels)
        if index < 0 or self.closed.is_set():
            return
        progress = watch.get('user_data') or {}
        position = progress.get('position_seconds') or 0
        restart = False
        if position > 0 and not progress.get('played'):
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
                 'content': data['content_id'],
                 'file': versions[index]['file_id'], 'title': data.get('title') or 'Silo'}
        if restart:
            query['restart'] = 'true'
        self._remember()
        if self.history:
            self._show(self.history.pop())
        self.playback_page = self.page
        self.playback_history = list(self.history)
        xbmc.Player().play('plugin://plugin.video.silo/?' + urlencode(query))

    def _video(self):
        if self.playback_page is not None and self.page is not self.playback_page:
            self.history = list(self.playback_history)
            self._show(self.playback_page)
        xbmc.executebuiltin('ActivateWindow(fullscreenvideo)')

    def _back(self):
        if self.busy:
            return
        playing = active_playback(self.catalog.profile_id)
        if playing and (self.page is self.playback_page or not self.history):
            self._task(self._video)
        elif self.history:
            page = self.history.pop()
            self._task(lambda: self._show(page))
        else:
            self.close()

    def onClick(self, control):
        if self.busy:
            return
        if control == 100:
            index = self.getControl(100).getSelectedPosition()
            if index == 0:
                self.home_entry_focus = 100
                self._task(self._home)
            elif index == 1:
                self._task(self._search)
            elif index <= len(self.libraries) + 1:
                self._task(lambda: self._library(self.libraries[index - 2]))
            elif index == len(self.libraries) + 2:
                self.account_requested = True
                self.close()
            else:
                self.close()
        elif control in (230, 231):
            slot = control - 230
            if slot >= len(self.page['visible']):
                return
            row = self.page['visible'][slot][1]
            index = self.getControl(control).getSelectedPosition()
            if index == len(row['items']):
                self._task(lambda: self._section(row))
            elif index >= 0:
                self._task(lambda: self._detail(row['items'][index]['content_id']))
        elif control == 200:
            index = self.getControl(200).getSelectedPosition()
            if 0 <= index < len(self.page['items']):
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
        if self.home_entry_focus is not None and self.getFocusId() == 100 and action.getId() in (1, 2, 3, 4):
            if action.getId() == 1:
                self.home_entry_focus = None
                self.keep_sidebar_focus = True
            else:
                self.home_entry_focus = 230
                self.keep_sidebar_focus = False
                if not self.busy and self.page and self.page['kind'] == 'home' and self.page.get('visible'):
                    self.getControl(100).selectItem(0)
                    self.setFocusId(230)
                    self.home_entry_focus = None
            return
        if self.busy and action.getId() in (1, 2, 3, 4) and self.getFocusId() == 100:
            self.keep_sidebar_focus = True
        if action.getId() == 117:
            self._task(self._context)
            return
        if (not self.busy and self.page and self.page['kind'] == 'home'
                and self.getFocusId() in (230, 231) and action.getId() in (3, 4)):
            direction = 1 if action.getId() == 4 else -1
            self._task(lambda: self._move_home(direction))
            return
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
        if self.pager:
            self.pager.join(timeout=35)


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
