import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'plugin.video.silo.kodi/resources/lib'))


class Control:
    def __init__(self):
        self.items = []
        self.position = 0
        self.label = ''

    def reset(self):
        self.items = []
        self.position = 0

    def addItem(self, item):
        self.items.append(item)

    def addItems(self, items):
        self.items.extend(items)
        self.position = 0

    def selectItem(self, position):
        self.position = position

    def getSelectedPosition(self):
        return self.position

    def getWidth(self):
        return 160

    def size(self):
        return len(self.items)

    def setLabel(self, label):
        self.label = label

    def __getattr__(self, name):
        return lambda *args: None


class Window:
    def __init__(self, *args, **kwargs):
        self.controls = {}
        self.focus = 100

    def getControl(self, identifier):
        return self.controls.setdefault(identifier, Control())

    def setFocusId(self, identifier):
        self.focus = identifier

    def getFocusId(self):
        return self.focus

    def setProperty(self, *args):
        pass

    def close(self):
        pass


class HomeNavigation(unittest.TestCase):
    def setUp(self):
        modules = {name: Mock() for name in ('xbmc', 'xbmcaddon', 'xbmcvfs', 'silo.controls')}
        modules['silo.controls'].active_playback.return_value = None
        modules['silo.controls'].take_completed.return_value = None
        modules['xbmcaddon'].Addon.return_value.getAddonInfo.return_value = '/addon'
        modules['xbmcgui'] = SimpleNamespace(WindowXML=Window, ListItem=lambda label: Mock(label=label),
                                            getCurrentWindowId=lambda: 13000, getCurrentWindowDialogId=lambda: 9999)
        modules['silo.ui'] = SimpleNamespace(open_account=Mock(), _text=str)
        path = Path(__file__).resolve().parents[1] / 'plugin.video.silo.kodi/resources/lib/silo/browser.py'
        with patch.dict(sys.modules, modules):
            spec = importlib.util.spec_from_file_location('silo.browser_test', path)
            browser = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(browser)
        browser.autoplay_delay = Mock(return_value=None)
        session = Mock(server='https://silo.example.test')
        session.status.return_value = {'profile': {'id': 'viewer', 'name': 'Viewer'}}
        self.window = browser.BrowserWindow(session=session)
        self.window.window_id = 13000
        self.window._task = lambda operation: operation()
        self.catalog = Mock(profile_id='viewer')
        self.catalog.next_episode.return_value = None
        self.window.catalog = self.catalog
        self.rows = {
            'first': {'id': 'first', 'title': 'First', 'items': [self.card('a'), self.card('b')]},
            'empty': {'id': 'empty', 'title': 'Empty', 'items': []},
            'last': {'id': 'last', 'title': 'Last', 'items': [self.card('c')]},
        }
        self.catalog.home.return_value = [{'id': key} for key in self.rows]
        self.catalog.home_section.side_effect = lambda key: self.rows[key]
        self.catalog.home_content.side_effect = lambda sections: [self.catalog.home_section(row['id']) for row in sections]
        self.catalog.item.side_effect = lambda key, **kwargs: dict(self.card(key), title=key)

    @staticmethod
    def card(identifier):
        return {'content_id': identifier, 'type': 'movie', 'title': identifier}

    def test_season_episode_without_type_displays_progress(self):
        card = self.window._card({'content_id': 'episode', 'episode_number': 1,
                                  'user_data': {'position_seconds': 90, 'duration_seconds': 360}})
        card.setProperty.assert_any_call('watch_status', '25% watched')

    def test_empty_show_and_season_keep_remote_navigation(self):
        self.library()
        self.catalog.item.side_effect = None
        self.catalog.item.return_value = dict(self.card('show'), type='series')
        self.catalog.seasons.return_value = []
        self.catalog.episodes.return_value = []
        self.window._detail('show')
        self.assertEqual(self.window.getFocusId(), 302)
        self.window._season({'season_number': 1})
        self.assertEqual(self.window.getFocusId(), 303)
        self.window.onAction(SimpleNamespace(getId=lambda: 92))
        self.assertEqual(self.window.page['kind'], 'item')
        self.assertEqual(self.window.getFocusId(), 302)
        self.window.onAction(SimpleNamespace(getId=lambda: 92))
        self.assertEqual(self.window.page['kind'], 'library')
        self.assertEqual(self.window.getFocusId(), 200)

    def test_completion_requires_explicit_choice(self):
        globals_ = self.window._offer_next.__globals__
        globals_['xbmc'].Player.return_value.isPlaying.return_value = False
        self.catalog.next_episode.return_value = {'content_id': 'next', 'season_number': 1,
                                                 'episode_number': 2, 'title': 'Next'}
        self.window._detail = Mock()
        self.window._play = Mock()
        dialog = Mock()
        with patch.object(globals_['xbmcgui'], 'Dialog', return_value=dialog, create=True):
            dialog.yesno.return_value = False
            self.window._offer_next('episode')
            self.window._play.assert_not_called()
            dialog.yesno.return_value = True
            self.window._offer_next('episode')
        self.window._detail.assert_called_once_with('next')
        self.window._play.assert_called_once_with()

    def test_autoplay_preserves_resume_without_interactive_choices(self):
        globals_ = self.window._play.__globals__
        player = globals_['xbmc'].Player.return_value
        player.isPlaying.return_value = False
        self.window._remember = Mock()
        self.catalog.watch.return_value = {'versions': [{'file_id': 'preferred'}, {'file_id': 'alternate'}],
                                          'user_data': {'position_seconds': 120, 'played': False}}
        dialog = Mock()
        with patch.object(globals_['xbmcgui'], 'Dialog', return_value=dialog, create=True):
            self.window._play(self.card('next'), prompt=False)
        dialog.select.assert_not_called()
        dialog.contextmenu.assert_not_called()
        query = parse_qs(urlsplit(player.play.call_args.args[0]).query)
        self.assertEqual(query['file'], ['preferred'])
        self.assertEqual(query['content'], ['next'])
        self.assertNotIn('restart', query)

    def open_home(self):
        self.window.getControl(100).selectItem(0)
        self.window.onClick(100)
        self.window.onAction(SimpleNamespace(getId=lambda: 2))

    def test_return_refreshes_rows_and_preserves_card_identity(self):
        self.open_home()
        self.assertEqual(self.window.getControl(40).label, 'First')
        self.assertEqual(self.window.getControl(41).label, 'Last')
        self.window.getControl(230).selectItem(1)
        self.window.onClick(230)
        self.assertEqual(self.window.getControl(12).label, 'b')

        self.rows['first']['items'] = [self.card('b'), self.card('a')]
        self.window.onAction(SimpleNamespace(getId=lambda: 10))
        self.assertEqual(self.window.getControl(12).label, 'Home')
        self.assertEqual(self.window.getFocusId(), 230)
        self.assertEqual(self.window.getControl(230).getSelectedPosition(), 0)

    def test_empty_home_keeps_navigation_available(self):
        self.rows = {}
        self.catalog.home.return_value = []
        self.open_home()
        self.assertEqual(self.window.getFocusId(), 100)
        self.assertIn('No titles', self.window.getControl(21).label)

    def test_removed_selected_card_returns_to_first_available_card(self):
        self.open_home()
        self.window.getControl(230).selectItem(1)
        self.window.onClick(230)
        self.rows['first']['items'] = [self.card('a')]
        self.window.onAction(SimpleNamespace(getId=lambda: 10))
        self.assertEqual(self.window.getControl(230).getSelectedPosition(), 0)
        self.assertEqual(self.window.getFocusId(), 230)

    def test_watch_choices_start_selected_version_with_resume_or_restart(self):
        self.open_home()
        self.window.onClick(230)
        globals_ = self.window.onClick.__globals__
        player = globals_['xbmc'].Player.return_value
        player.isPlaying.return_value = False
        dialog = Mock()
        dialog.select.return_value = 1
        self.catalog.watch.return_value = {
            'versions': [{'file_id': 'first'}, {'file_id': 'chosen'}],
            'user_data': {'position_seconds': 125, 'played': False},
        }
        # A second source of version choices would disagree with this snapshot.
        self.catalog.versions.side_effect = AssertionError('Watch already contains playable versions')
        for choice, restart in ((0, None), (1, ['true'])):
            with self.subTest(choice=choice), patch.object(globals_['xbmcgui'], 'Dialog', return_value=dialog, create=True):
                dialog.contextmenu.return_value = choice
                self.window._detail('a')
                self.window.onClick(300)
                query = parse_qs(urlsplit(player.play.call_args.args[0]).query)
                self.assertEqual(query['file'], ['chosen'])
                self.assertEqual(query['content'], ['a'])
                self.assertEqual(query['profile'], ['viewer'])
                self.assertEqual(query.get('restart'), restart)
                self.assertEqual(dialog.contextmenu.call_args.args[0], ['Resume from 0:02:05', 'Play from beginning'])

    def test_cancel_watch_choice_does_not_start_playback(self):
        self.open_home()
        self.window.onClick(230)
        globals_ = self.window.onClick.__globals__
        player = globals_['xbmc'].Player.return_value
        player.isPlaying.return_value = False
        self.catalog.watch.return_value = {
            'versions': [{'file_id': 'first'}], 'user_data': {'position_seconds': 125}}
        dialog = Mock()
        dialog.contextmenu.return_value = -1
        with patch.object(globals_['xbmcgui'], 'Dialog', return_value=dialog, create=True):
            self.window.onClick(300)
        player.play.assert_not_called()

    def library(self, count=50):
        self.catalog.page.return_value = {'items': [self.card(str(i)) for i in range(count)],
                                          'next_cursor': 'page-2'}
        self.window._library({'id': 'movies', 'name': 'Movies'})
        return self.window.getControl(200)

    def test_paging_preloads_and_appends_without_moving_selection(self):
        control = self.library()
        control.selectItem(10)
        self.catalog.page.return_value = {'items': [self.card(str(i)) for i in range(49, 100)],
                                          'next_cursor': 'page-3'}
        self.window._prefetch()
        self.assertEqual([item.label for item in control.items], [str(i) for i in range(100)])
        self.assertEqual(control.position, 10)
        self.assertEqual(self.window.getControl(20).label, '')
        self.assertEqual(self.window.getFocusId(), 200)

        self.catalog.page.reset_mock()
        self.window._prefetch()
        self.catalog.page.assert_not_called()
        control.selectItem(40)
        self.catalog.page.return_value = {'items': [self.card('100')], 'next_cursor': None}
        self.window._prefetch()
        self.assertEqual(control.items[-1].label, '100')
        self.assertEqual(control.position, 40)
        self.window.onClick(200)
        self.window._back()
        self.assertEqual(control.position, 40)
        self.assertEqual(control.size(), 101)

    def test_paging_discards_result_after_navigation_or_close(self):
        for transition in (self.open_home, self.window.closed.set):
            with self.subTest(transition=transition):
                self.window.closed.clear()
                self.catalog.page.side_effect = None
                control = self.library()
                def fetch(*args):
                    transition()
                    return {'items': [self.card('stale')], 'next_cursor': None}
                self.catalog.page.side_effect = fetch
                self.window._prefetch()
                self.assertNotIn('stale', [item.label for item in control.items])

    def test_filtered_pages_continue_but_repeated_cursor_stops(self):
        control = self.library(count=0)
        self.catalog.page.side_effect = [
            {'items': [], 'next_cursor': 'page-3'},
            {'items': [self.card('a'), self.card('a')], 'next_cursor': 'page-2'},
        ]
        self.window._prefetch()
        self.window._prefetch()
        self.window._prefetch()
        self.assertEqual([item.label for item in control.items], ['a'])
        self.assertIsNone(self.window.page['next_cursor'])

    def test_paging_failure_preserves_cards_and_retries_only_after_reopen(self):
        control = self.library()
        control.selectItem(20)
        self.catalog.page.side_effect = OSError('offline')
        self.window._prefetch()
        self.assertEqual(control.size(), 50)
        self.assertEqual(control.position, 20)
        self.assertIn('Reopen', self.window.getControl(20).label)
        self.catalog.page.reset_mock()
        self.window._prefetch()
        self.catalog.page.assert_not_called()

        self.window._remember()
        self.window._show(self.window.page)
        self.catalog.page.side_effect = None
        self.catalog.page.return_value = {'items': [self.card('new')], 'next_cursor': None}
        self.window._prefetch()
        self.assertEqual(control.items[-1].label, 'new')
        self.assertEqual(control.position, 20)

    def test_section_paging_keeps_server_cursor_and_profile_authority(self):
        self.catalog.home_page.return_value = {'items': [self.card('first')], 'next_cursor': 'opaque/+cursor'}
        self.window._section({'id': 'recent', 'title': 'Recent'})
        self.catalog.home_page.return_value = {'items': [self.card('second')], 'next_cursor': None}
        self.window._prefetch()
        self.catalog.home_page.assert_called_with('recent', 'opaque/+cursor')
        self.catalog.page.assert_not_called()
        self.assertEqual([item.label for item in self.window.getControl(200).items], ['first', 'second'])

        self.window.page['next_cursor'] = 'next'
        def change_profile(*args):
            self.window.session.status.return_value = {'profile': {'id': 'other'}}
            return {'items': [self.card('wrong-profile')], 'next_cursor': None}
        self.catalog.home_page.side_effect = change_profile
        self.window._prefetch()
        self.assertEqual([item.label for item in self.window.getControl(200).items], ['first', 'second'])

    def test_playback_preserves_detail_and_back_pops_history(self):
        control = self.library()
        control.selectItem(12)
        self.window.onClick(200)
        self.catalog.watch.return_value = {'versions': [{'file_id': 'file'}], 'user_data': {}}
        globals_ = self.window.onClick.__globals__
        globals_['xbmc'].Player.return_value.isPlaying.return_value = False
        self.window.onClick(300)
        self.assertEqual(self.window.page['kind'], 'item')
        self.assertEqual(self.window.page['data']['content_id'], '12')

        globals_['active_playback'].return_value = {'content_id': '12'}
        self.window.onAction(SimpleNamespace(getId=lambda: 92))
        globals_['xbmc'].executebuiltin.assert_not_called()
        self.assertEqual(self.window.page['kind'], 'library')
        self.assertFalse(self.window.closed.is_set())
        self.assertEqual(control.position, 12)

    def test_sidebar_resume_preserves_browsing_history(self):
        self.library()
        origin = self.window.page
        self.window.onClick(200)
        detail = self.window.page
        globals_ = self.window.onClick.__globals__
        globals_['active_playback'].return_value = {'content_id': 'other'}
        globals_['xbmc'].getCondVisibility.return_value = True
        self.window._menu()
        self.assertEqual([item.label for item in self.window.getControl(100).items],
                         ['Home', 'Search', 'Resume playback', 'Account', 'Settings', 'Close'])
        self.window.getControl(100).selectItem(2)
        self.window.setFocusId(100)
        self.window.onClick(100)
        self.assertIs(self.window.page, detail)
        self.assertEqual(self.window.history, [origin])
        globals_['xbmc'].Player.return_value.pause.assert_called_once()
        globals_['xbmc'].executebuiltin.assert_called_once_with('ActivateWindow(fullscreenvideo)')
        self.window._back()
        self.assertIs(self.window.page, origin)
        self.window._back()
        self.assertTrue(self.window.closed.is_set())

    def test_expired_resume_does_not_reopen_player(self):
        self.library()
        globals_ = self.window.onClick.__globals__
        globals_['active_playback'].return_value = {'content_id': 'other'}
        self.window._menu()
        self.window.getControl(100).selectItem(2)
        globals_['active_playback'].return_value = None
        self.window.onClick(100)
        globals_['xbmc'].executebuiltin.assert_not_called()
        self.assertEqual([item.label for item in self.window.getControl(100).items],
                         ['Home', 'Search', 'Account', 'Settings', 'Close'])

    def test_context_play_keeps_launch_page(self):
        control = self.library()
        control.selectItem(7)
        origin = self.window.page
        self.catalog.watch.return_value = {'versions': [{'file_id': 'file'}], 'user_data': {}}
        globals_ = self.window.onClick.__globals__
        globals_['xbmc'].Player.return_value.isPlaying.return_value = False
        dialog = Mock()
        dialog.contextmenu.return_value = 0
        with patch.object(globals_['xbmcgui'], 'Dialog', return_value=dialog, create=True):
            self.window.onAction(SimpleNamespace(getId=lambda: 117))
        self.assertIs(self.window.page, origin)
        self.assertEqual(self.window.history, [])
        self.assertEqual(control.position, 7)
        globals_['xbmc'].Player.return_value.play.assert_called_once()

    def test_back_during_restore_does_not_close_browser(self):
        self.library()
        self.window.busy = True
        self.window.onAction(SimpleNamespace(getId=lambda: 92))
        self.assertFalse(self.window.closed.is_set())

    def test_bar_actions_require_owned_playback(self):
        self.library()
        globals_ = self.window.onClick.__globals__
        player = globals_['xbmc'].Player.return_value
        for identifier in range(500, 506):
            self.window.onClick(identifier)
        player.pause.assert_not_called()
        player.stop.assert_not_called()
        player.seekTime.assert_not_called()
        globals_['xbmc'].executebuiltin.assert_not_called()

    def test_bar_seek_respects_media_bounds(self):
        self.library()
        globals_ = self.window.onClick.__globals__
        globals_['active_playback'].return_value = {'content_id': 'current'}
        player = globals_['xbmc'].Player.return_value
        player.getTotalTime.return_value = 100
        player.getTime.return_value = 4
        self.window.onClick(501)
        player.seekTime.assert_called_with(0)
        player.getTime.return_value = 90
        self.window.onClick(502)
        player.seekTime.assert_called_with(99)

    def test_bar_back_restores_focus_without_popping_history(self):
        self.library()
        self.window.onClick(200)
        detail = self.window.page
        self.window.onFocus(300)
        self.window.setFocusId(500)
        self.window.onAction(SimpleNamespace(getId=lambda: 92))
        self.assertEqual(self.window.getFocusId(), 300)
        self.assertIs(self.window.page, detail)
        self.assertEqual(len(self.window.history), 1)

    def test_bar_return_focus_survives_page_restoration(self):
        for home in (False, True):
            with self.subTest(home=home):
                if home:
                    self.open_home()
                    origin_focus = 230
                else:
                    self.library()
                    self.window.onClick(200)
                    origin_focus = 300
                page = self.window.page
                self.window.onFocus(origin_focus)
                self.window.setFocusId(503)
                self.window.onClick.__globals__['active_playback'].return_value = {'content_id': 'playing'}
                self.window.onClick(503)
                self.window.onFocus(100)
                self.window._show(page, refresh=False)
                self.window.onAction(SimpleNamespace(getId=lambda: 92))
                self.assertEqual(self.window.getFocusId(), origin_focus)
                self.assertIs(self.window.page, page)

    def test_browser_return_pauses_only_running_silo_video(self):
        self.library()
        self.window.layout = Mock()
        self.window.artwork = Mock()
        self.window.pager = Mock()
        globals_ = self.window.onInit.__globals__
        player = globals_['xbmc'].Player.return_value
        for active, paused, expected in ((True, False, 1), (True, True, 0), (False, False, 0)):
            with self.subTest(active=active, paused=paused):
                player.pause.reset_mock()
                globals_['active_playback'].return_value = {'content_id': '0'} if active else None
                globals_['xbmc'].getCondVisibility.return_value = paused
                with patch.object(globals_['xbmcgui'], 'getScreenWidth', return_value=1920, create=True):
                    self.window.onInit()
                self.assertEqual(player.pause.call_count, expected)

    def test_episode_parent_navigation_from_direct_entry(self):
        episode = dict(self.card('episode'), type='episode', series_id='show', season_number=0)
        series = dict(self.card('show'), type='series')
        self.catalog.item.side_effect = lambda key, **kwargs: dict(episode if key == 'episode' else series)
        self.catalog.episodes.return_value = [dict(episode, content_id='other', episode_number=1),
                                              dict(episode, episode_number=2)]
        self.catalog.seasons.return_value = [{'season_number': 0}]
        self.window._detail('episode')
        self.window.setFocusId(303)
        self.window.onClick(303)
        self.assertEqual(self.window.page['kind'], 'season')
        self.assertEqual(self.window.page['title'], 'show · Specials')
        self.assertEqual(self.window.getControl(220).position, 1)
        self.catalog.episodes.assert_called_once_with('show', 0)

        self.window.setFocusId(303)
        self.window.onClick(303)
        self.assertEqual(self.window.page['data']['content_id'], 'show')
        self.window._back()
        self.assertEqual(self.window.page['kind'], 'season')
        self.assertEqual(self.window.getControl(220).position, 1)

    def test_browsing_during_playback_keeps_detail_back_navigation(self):
        self.library()
        origin = self.window.page
        self.window.onClick(200)
        globals_ = self.window.onClick.__globals__
        globals_['active_playback'].return_value = {'content_id': 'other'}
        self.window.onAction(SimpleNamespace(getId=lambda: 92))
        self.assertIs(self.window.page, origin)
        globals_['xbmc'].executebuiltin.assert_not_called()

    def test_menu_keeps_playback_choices_without_sidebar_entry(self):
        self.window._menu()
        self.assertEqual([item.label for item in self.window.getControl(100).items], ['Home', 'Search', 'Account', 'Settings', 'Close'])
        globals_ = self.window.onClick.__globals__
        globals_['active_playback'].return_value = {'content_id': 'movie'}
        self.window.onAction(SimpleNamespace(getId=lambda: 117))
        globals_['playback_options'].assert_called_once()


    def test_search_uses_trimmed_text_and_preserves_return_focus(self):
        self.library()
        self.window.getControl(200).selectItem(7)
        dialog = Mock()
        dialog.input.return_value = '  a & b  '
        self.catalog.search.return_value = {'items': [self.card('result')], 'next_cursor': 'opaque'}
        globals_ = self.window.onClick.__globals__
        with patch.object(globals_['xbmcgui'], 'Dialog', return_value=dialog, create=True):
            self.window._search()
        self.catalog.search.assert_called_once_with('a & b')
        self.assertEqual(self.window.page['kind'], 'search')
        self.catalog.search.return_value = {'items': [self.card('next')], 'next_cursor': None}
        self.window._prefetch()
        self.assertEqual([item.label for item in self.window.getControl(200).items], ['result', 'next'])
        self.catalog.search.assert_called_with('a & b', 'opaque')
        self.window._back()
        self.assertEqual(self.window.getControl(200).position, 7)

    def test_cancel_search_preserves_current_page(self):
        self.library()
        page = self.window.page
        dialog = Mock()
        dialog.input.return_value = ''
        globals_ = self.window.onClick.__globals__
        with patch.object(globals_['xbmcgui'], 'Dialog', return_value=dialog, create=True):
            self.window._search()
        self.assertIs(self.window.page, page)
        self.catalog.search.assert_not_called()

    def test_context_uses_fresh_personal_state_and_keeps_selection(self):
        control = self.library()
        control.selectItem(3)
        self.catalog.item.side_effect = None
        self.catalog.item.return_value = dict(self.card('3'), user_state={
            'played': False, 'is_favorite': True, 'in_watchlist': False})
        self.catalog.set_state.return_value = dict(self.card('3'), user_state={
            'played': False, 'is_favorite': False, 'in_watchlist': False})
        dialog = Mock()
        dialog.contextmenu.return_value = 2
        globals_ = self.window.onClick.__globals__
        with patch.object(globals_['xbmcgui'], 'Dialog', return_value=dialog, create=True):
            self.window.onAction(SimpleNamespace(getId=lambda: 117))
        self.assertIn('Remove from favourites', dialog.contextmenu.call_args.args[0])
        self.catalog.set_state.assert_called_once_with('3', 'is_favorite', False)
        self.assertEqual(control.position, 3)
        self.assertFalse(self.window.page['items'][3]['user_state']['is_favorite'])

    def test_detail_options_target_the_series(self):
        self.catalog.item.side_effect = None
        self.catalog.item.return_value = {'content_id': 'series', 'type': 'series', 'title': 'Series',
                                          'user_state': {'played': False, 'is_favorite': True}}
        self.catalog.seasons.return_value = [{'season_number': 1}]
        self.window._detail('series')
        self.window.setFocusId(302)
        dialog = Mock()
        dialog.contextmenu.return_value = -1
        globals_ = self.window.onClick.__globals__
        with patch.object(globals_['xbmcgui'], 'Dialog', return_value=dialog, create=True):
            self.window.onClick(302)
        self.catalog.item.assert_called_with('series')
        self.assertIn('Remove from favourites', dialog.contextmenu.call_args.args[0])
        self.catalog.set_state.assert_not_called()

    def test_context_cancel_and_missing_state_do_not_mutate(self):
        self.library()
        dialog = Mock()
        dialog.contextmenu.return_value = -1
        globals_ = self.window.onClick.__globals__
        with patch.object(globals_['xbmcgui'], 'Dialog', return_value=dialog, create=True):
            self.window.onAction(SimpleNamespace(getId=lambda: 117))
        self.assertEqual(dialog.contextmenu.call_args.args[0], ['Play / Resume', 'Details'])
        self.catalog.set_state.assert_not_called()


    def test_home_removal_uses_card_anchor_and_refreshes_membership(self):
        self.rows['first']['section_type'] = 'continue_watching'
        self.rows['first']['items'][0].update(progress_updated_at='2026-10-24T10:00:00Z', series_id='show')
        self.open_home()
        dialog = Mock()
        def choose(labels):
            return labels.index('Remove from Continue Watching')
        dialog.contextmenu.side_effect = choose
        def dismiss(*args):
            self.rows['first']['items'] = [self.card('b')]
        self.catalog.dismiss_home.side_effect = dismiss
        globals_ = self.window.onClick.__globals__
        with patch.object(globals_['xbmcgui'], 'Dialog', return_value=dialog, create=True):
            self.window.onAction(SimpleNamespace(getId=lambda: 117))
        self.catalog.dismiss_home.assert_called_once_with('a', 'continue_watching', '2026-10-24T10:00:00Z')
        self.assertEqual(self.window.getControl(230).items[0].label, 'b')
        self.assertEqual(self.window.getFocusId(), 230)
        self.catalog.set_state.assert_not_called()

    def test_next_up_removal_discards_inflight_page(self):
        row = dict(self.rows['first'], section_type='next_up')
        self.catalog.home_page.return_value = {
            'items': [dict(self.card('a'), type='episode', series_id='show')], 'next_cursor': 'old'}
        self.window._section(row)
        old_page = self.window.page
        dialog = Mock()
        dialog.contextmenu.side_effect = lambda labels: labels.index('Remove from Next Up')
        def fetch(section, cursor=None):
            if cursor:
                self.window.onAction(SimpleNamespace(getId=lambda: 117))
                return {'items': [self.card('stale')], 'next_cursor': 'old-next'}
            return {'items': [self.card('b')], 'next_cursor': 'new'}
        self.catalog.home_page.side_effect = fetch
        globals_ = self.window.onClick.__globals__
        with patch.object(globals_['xbmcgui'], 'Dialog', return_value=dialog, create=True):
            self.window._prefetch()
        self.catalog.dismiss_home.assert_called_once_with('a', 'next_up', 'show')
        self.assertIsNot(self.window.page, old_page)
        self.assertEqual([item.label for item in self.window.getControl(200).items], ['b'])
        self.assertEqual(self.window.page['next_cursor'], 'new')

    def test_home_removal_requires_progress_row_and_anchor(self):
        dialog = Mock()
        dialog.contextmenu.return_value = -1
        globals_ = self.window.onClick.__globals__
        for section_type, anchor in (('recently_added', {'series_id': 'show'}),
                                     ('next_up', {}), ('continue_watching', {'progress_updated_at': ' '})):
            with self.subTest(section_type=section_type, anchor=anchor):
                self.rows['first']['section_type'] = section_type
                self.rows['first']['items'] = [dict(self.card('a'), **anchor)]
                self.open_home()
                with patch.object(globals_['xbmcgui'], 'Dialog', return_value=dialog, create=True):
                    self.window.onAction(SimpleNamespace(getId=lambda: 117))
                self.assertFalse(any(label.startswith('Remove from') for label in dialog.contextmenu.call_args.args[0]))
        self.catalog.dismiss_home.assert_not_called()

    def test_sidebar_and_season_cards_do_not_target_detail_title(self):
        self.open_home()
        self.window.onClick(230)
        self.catalog.item.reset_mock()
        for focus in (100, 303, 210):
            self.window.setFocusId(focus)
            self.window.onAction(SimpleNamespace(getId=lambda: 117))
        self.catalog.item.assert_not_called()

    def test_home_keeps_shelves_visible_during_row_fetch(self):
        self.open_home()
        self.window.setFocusId(231)
        before = [item.label for item in self.window.getControl(231).items]

        def fetch(key):
            self.assertEqual([item.label for item in self.window.getControl(231).items], before)
            self.assertEqual(self.window.getFocusId(), 231)
            return self.rows[key]

        self.catalog.home_section.side_effect = fetch
        self.window.page['focus'] = 231
        self.window._show(self.window.page)
        self.assertEqual(self.window.getFocusId(), 231)

    def test_home_completion_respects_explicit_left_during_load(self):
        def fetch(key):
            self.window.setFocusId(100)
            self.window.busy = True
            self.window.onAction(SimpleNamespace(getId=lambda: 1))
            self.window.busy = False
            return self.rows[key]

        self.catalog.home_section.side_effect = fetch
        self.window.onClick(100)
        self.assertEqual(self.window.getFocusId(), 100)
        self.assertEqual(self.window.getControl(230).items[0].label, 'a')

    def test_failed_home_refresh_preserves_visible_shelves(self):
        self.open_home()
        self.window.setFocusId(231)
        before = [item.label for item in self.window.getControl(231).items]
        self.catalog.home_section.side_effect = RuntimeError('offline')
        with self.assertRaises(RuntimeError):
            self.window._show(self.window.page)
        self.assertEqual([item.label for item in self.window.getControl(231).items], before)
        self.assertEqual(self.window.getFocusId(), 231)

    def test_library_completion_respects_sidebar_navigation(self):
        def fetch(*args):
            self.window.setFocusId(100)
            self.window.busy = True
            self.window.onAction(SimpleNamespace(getId=lambda: 4))
            self.window.busy = False
            return {'items': [self.card('a')], 'next_cursor': None}

        self.catalog.page.side_effect = fetch
        self.window._library({'id': 'movies', 'name': 'Movies'})
        self.assertEqual(self.window.getFocusId(), 100)
        self.assertEqual(self.window.getControl(200).items[0].label, 'a')


    def test_home_starts_expanded_and_first_direction_enters_cards(self):
        for direction in (2, 3, 4):
            with self.subTest(direction=direction):
                self.window.getControl(100).selectItem(0)
                self.window.onClick(100)
                self.assertEqual(self.window.getFocusId(), 100)
                self.window.onAction(SimpleNamespace(getId=lambda: direction))
                self.assertEqual(self.window.getFocusId(), 230)

    def test_left_claims_sidebar_for_normal_navigation(self):
        self.window.onClick(100)
        self.window.onAction(SimpleNamespace(getId=lambda: 1))
        self.window.onAction(SimpleNamespace(getId=lambda: 4))
        self.assertEqual(self.window.getFocusId(), 100)

    def test_first_down_during_load_enters_cards_on_completion(self):
        def fetch(key):
            self.window.busy = True
            self.window.onAction(SimpleNamespace(getId=lambda: 4))
            self.window.busy = False
            return self.rows[key]

        self.catalog.home_section.side_effect = fetch
        self.window.onClick(100)
        self.assertEqual(self.window.getFocusId(), 230)

    def test_home_preview_becomes_next_shelf_without_skipping_empty_rows(self):
        self.rows['third'] = {'id': 'third', 'title': 'Third', 'items': [self.card('d')]}
        self.catalog.home.return_value = [{'id': key} for key in self.rows]
        self.open_home()
        self.assertEqual(self.window.getControl(42).label, 'Third')
        self.assertEqual(self.window.getControl(232).items[0].label, 'd')

        self.window.onAction(SimpleNamespace(getId=lambda: 4))
        self.window.onAction(SimpleNamespace(getId=lambda: 4))
        self.assertEqual(self.window.getControl(41).label, 'Third')
        self.assertEqual(self.window.getControl(231).items[0].label, 'd')
        self.assertEqual(self.window.getFocusId(), 231)
        self.assertEqual(self.window.getControl(42).label, '')
        self.assertEqual(self.window.getControl(232).items, [])

    def test_home_does_not_preview_empty_remaining_shelves(self):
        self.rows['trailing-empty'] = {'id': 'trailing-empty', 'title': 'Empty', 'items': []}
        self.catalog.home.return_value = [{'id': key} for key in self.rows]
        self.open_home()
        self.assertEqual(self.window.getControl(42).label, '')
        self.assertEqual(self.window.getControl(232).items, [])

    def test_home_horizontal_paging_appends_without_view_all_or_focus_change(self):
        self.rows['first'].update(section_type='continue_watching',
                                  items=[self.card(str(i)) for i in range(50)], next_cursor='next')
        self.open_home()
        control = self.window.getControl(230)
        self.assertEqual(control.size(), 50)
        control.selectItem(12)
        self.catalog.home_page.return_value = {
            'items': [self.card(str(i)) for i in range(49, 100)], 'next_cursor': None}
        self.window._prefetch()
        self.assertEqual([item.label for item in control.items], [str(i) for i in range(100)])
        self.assertEqual(control.position, 12)
        self.assertEqual(self.window.getFocusId(), 230)
        self.catalog.home_page.assert_called_once_with('first', 'next')

    def test_home_discards_paging_for_a_replaced_shelf(self):
        self.rows['first'].update(section_type='continue_watching', next_cursor='next')
        self.open_home()
        def fetch(*args):
            self.rows['first'] = dict(self.rows['first'], items=[self.card('replacement')], next_cursor=None)
            self.window._show(self.window.page)
            return {'items': [self.card('stale')], 'next_cursor': None}
        self.catalog.home_page.side_effect = fetch
        self.window._prefetch()
        self.assertEqual([item.label for item in self.window.getControl(230).items], ['replacement'])

    def test_home_vertical_scrolling_uses_preloaded_shelves(self):
        self.rows['third'] = {'id': 'third', 'title': 'Third', 'items': [self.card('d')]}
        self.catalog.home.return_value = [{'id': key} for key in self.rows]
        self.open_home()
        self.catalog.home_content.reset_mock()
        self.catalog.home_section.reset_mock()
        for direction in (4, 4, 3, 3):
            self.window.onAction(SimpleNamespace(getId=lambda: direction))
        self.catalog.home_content.assert_not_called()
        self.catalog.home_section.assert_not_called()

    def test_home_return_restores_a_card_beyond_first_page(self):
        self.rows['first'].update(section_type='continue_watching',
                                  items=[self.card(str(i)) for i in range(50)], next_cursor='next')
        self.open_home()
        self.catalog.home_page.return_value = {
            'items': [self.card(str(i)) for i in range(50, 100)], 'next_cursor': None}
        self.window._prefetch()
        self.window.getControl(230).selectItem(75)
        self.window.onClick(230)
        self.rows['first'] = dict(self.rows['first'], items=[self.card(str(i)) for i in range(50)], next_cursor='next')
        self.window.onAction(SimpleNamespace(getId=lambda: 10))
        control = self.window.getControl(230)
        self.assertEqual(control.items[control.position].label, '75')
        self.assertEqual(self.window.getFocusId(), 230)

    def test_home_discards_error_from_a_replaced_shelf(self):
        self.rows['first'].update(section_type='continue_watching', next_cursor='next')
        self.open_home()
        def fetch(*args):
            self.rows['first'] = dict(self.rows['first'], items=[self.card('replacement')], next_cursor=None)
            self.window._show(self.window.page)
            raise RuntimeError('old request failed')
        self.catalog.home_page.side_effect = fetch
        self.window._prefetch()
        self.assertEqual(self.window.getControl(20).label, '')
        self.assertEqual([item.label for item in self.window.getControl(230).items], ['replacement'])

    def test_home_paging_does_not_append_to_a_reassigned_shelf_control(self):
        self.rows['last'].update(section_type='continue_watching', next_cursor='next')
        self.rows['third'] = {'id': 'third', 'title': 'Third', 'items': [self.card('d')]}
        self.catalog.home.return_value = [{'id': key} for key in self.rows]
        self.open_home()
        def fetch(*args):
            self.window.setFocusId(231)
            self.window.onAction(SimpleNamespace(getId=lambda: 4))
            return {'items': [self.card('later')], 'next_cursor': None}
        self.catalog.home_page.side_effect = fetch
        self.window._prefetch()
        self.assertEqual([item.label for item in self.window.getControl(230).items], ['c'])
        self.assertEqual([item.label for item in self.window.getControl(231).items], ['d', 'View all'])
