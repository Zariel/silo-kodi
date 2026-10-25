import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'plugin.video.silo/resources/lib'))


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


class HomeNavigation(unittest.TestCase):
    def setUp(self):
        modules = {name: Mock() for name in ('xbmc', 'xbmcaddon', 'xbmcvfs', 'silo.controls')}
        modules['silo.controls'].active_playback.return_value = None
        modules['xbmcaddon'].Addon.return_value.getAddonInfo.return_value = '/addon'
        modules['xbmcgui'] = SimpleNamespace(WindowXML=Window, ListItem=lambda label: Mock(label=label))
        modules['silo.ui'] = SimpleNamespace(open_account=Mock(), _text=str)
        path = Path(__file__).resolve().parents[1] / 'plugin.video.silo/resources/lib/silo/browser.py'
        with patch.dict(sys.modules, modules):
            spec = importlib.util.spec_from_file_location('silo.browser_test', path)
            browser = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(browser)
        session = Mock(server='https://silo.example.test')
        session.status.return_value = {'profile': {'id': 'viewer', 'name': 'Viewer'}}
        self.window = browser.BrowserWindow(session=session)
        self.window._task = lambda operation: operation()
        self.catalog = Mock(profile_id='viewer')
        self.window.catalog = self.catalog
        self.rows = {
            'first': {'id': 'first', 'title': 'First', 'items': [self.card('a'), self.card('b')]},
            'empty': {'id': 'empty', 'title': 'Empty', 'items': []},
            'last': {'id': 'last', 'title': 'Last', 'items': [self.card('c')]},
        }
        self.catalog.home.return_value = [{'id': key} for key in self.rows]
        self.catalog.home_section.side_effect = lambda key: self.rows[key]
        self.catalog.item.side_effect = lambda key: dict(self.card(key), title=key)

    @staticmethod
    def card(identifier):
        return {'content_id': identifier, 'type': 'movie', 'title': identifier}

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

    def test_playback_returns_to_origin_and_back_reopens_video(self):
        control = self.library()
        control.selectItem(12)
        self.window.onClick(200)
        self.catalog.watch.return_value = {'versions': [{'file_id': 'file'}], 'user_data': {}}
        globals_ = self.window.onClick.__globals__
        globals_['xbmc'].Player.return_value.isPlaying.return_value = False
        self.window.onClick(300)
        self.assertEqual(self.window.page['kind'], 'library')
        self.assertEqual(control.position, 12)

        globals_['active_playback'].return_value = {'content_id': '12'}
        self.window.onAction(SimpleNamespace(getId=lambda: 92))
        globals_['xbmc'].executebuiltin.assert_called_once_with('ActivateWindow(fullscreenvideo)')
        self.assertFalse(self.window.closed.is_set())
        self.assertEqual(control.position, 12)

    def test_browsing_during_playback_keeps_detail_back_navigation(self):
        self.library()
        origin = self.window.page
        self.window.playback_page = origin
        self.window.onClick(200)
        globals_ = self.window.onClick.__globals__
        globals_['active_playback'].return_value = {'content_id': 'other'}
        self.window.onAction(SimpleNamespace(getId=lambda: 92))
        self.assertIs(self.window.page, origin)
        globals_['xbmc'].executebuiltin.assert_not_called()

    def test_menu_keeps_playback_choices_without_sidebar_entry(self):
        self.window._menu()
        self.assertEqual([item.label for item in self.window.getControl(100).items], ['Home', 'Search', 'Account', 'Close'])
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
        for focus in (100, 301, 210):
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
