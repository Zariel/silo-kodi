from pathlib import Path
import sys
import unittest
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'plugin.video.silo.kodi/resources/lib'))
from silo.catalog import Catalog, artwork
from silo.client import Error


class Session:
    def __init__(self):
        self.profile = 'viewer'
        self.responses = {'/settings/values/effective?keys=ui.disabled_library_ids': {'items': []}}
        self.requests = []

    def status(self):
        return {'profile': {'id': self.profile} if self.profile else None}

    def request(self, method, path, expected_profile=None):
        if expected_profile != self.profile:
            raise Error('profile_changed')
        self.requests.append(path)
        actual = urlsplit(path)
        for expected, response in self.responses.items():
            target = urlsplit(expected)
            if actual.path == target.path and parse_qs(actual.query) == parse_qs(target.query):
                if isinstance(response, Error):
                    raise response
                return response
        raise AssertionError(path)


class Browsing(unittest.TestCase):
    def test_next_episode_uses_numeric_order_and_crosses_seasons(self):
        session = Session()
        session.responses.update({
            '/catalog/series/show/seasons/1/episodes': {'items': [
                {'content_id': 'later', 'episode_number': 10}, {'content_id': 'next', 'episode_number': 3}]},
            '/catalog/series/show/seasons': {'items': [{'season_number': 0}, {'season_number': 3}, {'season_number': 2}]},
            '/catalog/series/show/seasons/2/episodes': {'items': [
                {'content_id': 'second', 'episode_number': 2}, {'content_id': 'first', 'episode_number': 1}]},
        })
        catalog = Catalog(session)
        episode = {'type': 'episode', 'series_id': 'show', 'season_number': 1, 'episode_number': 2}
        self.assertEqual(catalog.next_episode(episode)['content_id'], 'next')
        episode['episode_number'] = 10
        self.assertEqual(catalog.next_episode(episode)['content_id'], 'first')
        session.responses['/catalog/series/show/seasons']['items'] = [{'season_number': 0}, {'season_number': 1}]
        self.assertIsNone(catalog.next_episode(episode))
        self.assertIsNone(catalog.next_episode({'type': 'movie'}))

    def test_next_episode_skips_missing_or_unreadable_files(self):
        session = Session()
        session.responses['/catalog/series/show/seasons/1/episodes'] = {'items': [
            {'content_id': 'missing', 'episode_number': 2, 'files': []},
            {'content_id': 'broken', 'episode_number': 3, 'files': [{'unreadable': True}]},
            {'content_id': 'available', 'episode_number': 4, 'files': [{'unreadable': False}]}]}
        result = Catalog(session).next_episode({'type': 'episode', 'series_id': 'show',
                                                'season_number': 1, 'episode_number': 1})
        self.assertEqual(result['content_id'], 'available')

    def test_only_exact_supported_counts_reserve_native_grid_slots(self):
        for total, exact, media, expected in (
                (500, True, 'movie', 500), (500, False, 'movie', None),
                (500, True, 'future', None), (0, True, 'movie', None),
                ('500', True, 'movie', None), (True, True, 'movie', None)):
            with self.subTest(total=total, exact=exact, media=media):
                session = Session()
                session.responses['/catalog?source=query&library_id=movies&type=video&sort=title&limit=200&skip_total=false'] = {
                    'items': [{'content_id': 'first', 'type': media}], 'total': total,
                    'total_exact': exact, 'page': {'next_cursor': 'next'}}
                result = Catalog(session).page('movies')
                self.assertEqual(result.get('total'), expected)
                self.assertEqual(result['next_cursor'], 'next')

    def test_libraries_honor_effective_hidden_settings(self):
        session = Session()
        session.responses['/settings/values/effective?keys=ui.disabled_library_ids'] = {
            'items': [{'key': 'ui.disabled_library_ids', 'value': ['hidden'],
                       'requested_value': ['visible'], 'source': 'profile'}]}
        session.responses['/user/libraries'] = {'items': [
            {'id': 'hidden', 'type': 'movies'}, {'id': 'visible', 'type': 'series'}]}
        self.assertEqual(Catalog(session).libraries(), [{'id': 'visible', 'type': 'series'}])

        session.responses['/settings/values/effective?keys=ui.disabled_library_ids']['items'][0]['value'] = None
        self.assertEqual(Catalog(session).libraries(), [
            {'id': 'hidden', 'type': 'movies'}, {'id': 'visible', 'type': 'series'}])

    def test_home_preserves_profile_order_custom_sections_and_empty_layout(self):
        session = Session()
        rows = [{'id': 'custom', 'title': 'My picks', 'is_custom': True},
                {'id': 'continue_watching', 'title': 'Continue Watching'}]
        session.responses['/home/layout'] = {'sections': rows}
        catalog = Catalog(session)
        self.assertEqual(catalog.home(), rows)

        session.responses['/home/layout'] = {'sections': []}
        self.assertEqual(catalog.home(), [])
        self.assertEqual(session.requests, ['/home/layout', '/home/layout'])

    def test_home_fallback_requires_an_unsupported_endpoint(self):
        for status in (404, 405, 501, 401, 403, 429, 500, 503, 0):
            with self.subTest(status=status):
                session = Session()
                session.responses['/home/layout'] = Error('unavailable', status)
                rows = [{'id': 'recent', 'items': []}]
                session.responses['/home/sections'] = {'sections': rows}
                if status in (404, 405, 501):
                    self.assertEqual(Catalog(session).home(), rows)
                else:
                    with self.assertRaises(Error):
                        Catalog(session).home()
                    self.assertEqual(session.requests, ['/home/layout'])

    def test_home_cards_keep_episodes_and_opaque_section_pagination(self):
        session = Session()
        episode = {'content_id': 'episode-1', 'type': 'episode'}
        session.responses['/home/sections/custom%2F1/items'] = {
            'id': 'custom/1', 'total_count': 9, 'items': [episode, {'type': 'ebook'}]}
        session.responses['/catalog?source=section&scope=home&section_id=custom%2F1&limit=50&skip_total=true&cursor=opaque%2F%2B'] = {
            'items': [episode, {'type': 'future'}], 'page': {'next_cursor': 'next-token'}}
        catalog = Catalog(session)
        self.assertEqual(catalog.home_section('custom/1'), {
            'id': 'custom/1', 'total_count': 9, 'items': [episode]})
        self.assertEqual(catalog.home_page('custom/1', 'opaque/+'), {
            'items': [episode], 'next_cursor': 'next-token'})

    def test_home_aggregate_fallback_refreshes_cards_without_guessing_section_ids(self):
        session = Session()
        session.responses['/home/layout'] = Error('http_error', 404)
        session.responses['/home/sections/opaque-row/items'] = Error('http_error', 404)
        session.responses['/home/sections'] = {'sections': [
            {'id': 'opaque-row', 'title': 'Keep watching', 'items': []}]}
        catalog = Catalog(session)
        section = catalog.home()[0]
        self.assertEqual(catalog.home_section(section['id'])['items'], [])

        episode = {'content_id': 'episode-2', 'type': 'episode'}
        session.responses['/home/sections'] = {'sections': [
            {'id': 'opaque-row', 'title': 'Keep watching', 'items': [episode]}]}
        self.assertEqual(catalog.home_section(section['id']), {
            'id': 'opaque-row', 'title': 'Keep watching', 'items': [episode]})

        session.responses['/home/sections'] = {'sections': []}
        with self.assertRaises(Error) as raised:
            catalog.home_section(section['id'])
        self.assertEqual(raised.exception.code, 'home_section_unavailable')

    def test_home_row_errors_do_not_fall_back_to_aggregate_data(self):
        for status in (401, 403, 429, 500, 503, 0):
            with self.subTest(status=status):
                session = Session()
                session.responses['/home/sections/row/items'] = Error('unavailable', status)
                with self.assertRaises(Error):
                    Catalog(session).home_section('row')
                self.assertEqual(session.requests, ['/home/sections/row/items'])

    def test_missing_home_endpoints_leave_library_reads_available(self):
        session = Session()
        session.responses['/home/layout'] = Error('http_error', 404)
        session.responses['/home/sections'] = Error('http_error', 404)
        session.responses['/profile/sections/settings?scope=home'] = Error('http_error', 404)
        session.responses['/user/libraries'] = {'items': [{'id': 'films', 'type': 'movies'}]}
        catalog = Catalog(session)
        with self.assertRaises(Error) as raised:
            catalog.home()
        self.assertEqual(raised.exception.code, 'home_unavailable')
        self.assertEqual(catalog.libraries(), [{'id': 'films', 'type': 'movies'}])

    def test_home_settings_preserve_positions_and_hide_profile_hidden_rows(self):
        session = Session()
        session.responses['/home/layout'] = Error('http_error', 404)
        session.responses['/home/sections'] = Error('http_error', 405)
        session.responses['/profile/sections/settings?scope=home'] = {'items': [
            {'id': 'later', 'position': 8, 'hidden': False},
            {'id': 'hidden', 'position': 0, 'hidden': True},
            {'id': 'first', 'position': 2, 'hidden': False}]}
        self.assertEqual([row['id'] for row in Catalog(session).home()], ['first', 'later'])

    def test_home_defaults_order_discovered_recipes_without_guessing_ids(self):
        session = Session()
        session.responses['/home/layout'] = Error('http_error', 404)
        session.responses['/home/sections'] = Error('http_error', 404)
        session.responses['/profile/sections/settings?scope=home'] = {'items': [
            {'id': 'custom-a', 'section_type': 'custom_filter'},
            {'id': 'tv', 'section_type': 'recently_added', 'config': {'media_scope': 'series'}},
            {'id': 'top', 'section_type': 'critically_acclaimed'},
            {'id': 'movies', 'section_type': 'recently_added', 'config': {'media_scope': 'movie'}},
            {'id': 'continue', 'section_type': 'continue_watching'},
            {'id': 'custom-b', 'section_type': 'future_recipe'},
            {'id': 'trending', 'section_type': 'trending_discover'}]}
        self.assertEqual([row['id'] for row in Catalog(session).home()],
                         ['continue', 'trending', 'movies', 'tv', 'top', 'custom-a', 'custom-b'])

    def test_library_types(self):
        session = Session()
        session.responses['/user/libraries'] = {'items': [
            {'id': 'm', 'type': 'movies'}, {'id': 's', 'type': 'series'},
            {'id': 'a', 'type': 'music'}, {'id': 'b', 'type': 'books'}]}
        self.assertEqual(Catalog(session).libraries(), [
            {'id': 'm', 'type': 'movies'}, {'id': 's', 'type': 'series'}])

    def test_cursor_survives_filtered_page(self):
        session = Session()
        session.responses['/catalog?source=query&library_id=lib%2F1&type=video&sort=title&limit=200&skip_total=false'] = {
            'items': [{'content_id': 'unknown', 'type': 'future'}],
            'page': {'next_cursor': 'opaque/+?='}}
        session.responses['/catalog?source=query&library_id=lib%2F1&type=video&sort=title&limit=200&skip_total=true&cursor=opaque%2F%2B%3F%3D'] = {
            'items': [{'content_id': 'title-1', 'type': 'movie', 'title': 'Example'}],
            'page': {'next_cursor': None}}
        catalog = Catalog(session)
        first = catalog.page('lib/1')
        self.assertEqual(first['items'], [])
        second = catalog.page('lib/1', first['next_cursor'])
        self.assertEqual(second, {'items': [{'content_id': 'title-1', 'type': 'movie', 'title': 'Example'}], 'next_cursor': None})
        query = parse_qs(urlsplit(session.requests[-1]).query)
        self.assertEqual(query['cursor'], ['opaque/+?='])

    def test_content_and_file_identity_remain_distinct(self):
        session = Session()
        session.responses['/catalog/items/title%2F1'] = {'content_id': 'title/1', 'type': 'movie'}
        session.responses['/watch/title%2F1'] = {'versions': [{'file_id': 'file-9', 'container': 'mkv'}]}
        catalog = Catalog(session)
        detail = catalog.item('title/1')
        self.assertEqual(catalog.watch(detail['content_id'])['versions'], [{'file_id': 'file-9', 'container': 'mkv'}])

    def test_specials_use_season_zero(self):
        session = Session()
        session.responses['/catalog/series/show/seasons'] = {'items': [{'season_number': 0}]}
        session.responses['/catalog/series/show/seasons/0/episodes'] = {'items': [{'content_id': 'special', 'files': []}]}
        catalog = Catalog(session)
        season = catalog.seasons('show')[0]
        self.assertEqual(catalog.episodes('show', season['season_number']), [{'content_id': 'special', 'files': []}])

    def test_navigation_retains_originating_profile(self):
        session = Session()
        catalog = Catalog(session)
        session.profile = 'other'
        for operation in (catalog.libraries, catalog.home, lambda: catalog.home_section('recent'),
                          lambda: catalog.home_page('recent'), lambda: catalog.page('library'),
                          lambda: catalog.item('title'), lambda: catalog.seasons('show'),
                          lambda: catalog.episodes('show', 1),
                          lambda: catalog.watch('title')):
            with self.subTest(operation=operation), self.assertRaises(Error) as raised:
                operation()
            self.assertEqual(raised.exception.code, 'profile_changed')
        self.assertEqual(session.requests, [])

    def test_artwork_preserves_grant_without_account_credentials(self):
        self.assertEqual(artwork('https://silo.example.test', '/api/v2/artwork/image?exp=123&sig=a%2Bb'),
                         'https://silo.example.test/api/v2/artwork/image?exp=123&sig=a%2Bb')
        self.assertEqual(artwork('https://silo.example.test', 'https://images.example.test/poster?sig=grant'),
                         'https://images.example.test/poster?sig=grant')
        for value in (None, '', 'file:///etc/passwd', 'http://example.test/art',
                      'https://user:password@example.test/art', '/art|Authorization=secret',
                      'https://[invalid/art'):
            with self.subTest(value=value):
                self.assertEqual(artwork('https://silo.example.test', value), '')


class SearchAndActions(unittest.TestCase):
    def test_search_preserves_rank_cursor_and_supported_episode_scope(self):
        session = Session()
        session.responses['/catalog/search/capabilities'] = {'video_with_episodes_scope': True}
        session.responses['/catalog?source=query&q=a+%26+b&type=video_with_episodes&limit=50&skip_total=true&cursor=opaque%2F%2B'] = {
            'items': [{'content_id': 'episode', 'type': 'episode'}, {'content_id': 'movie', 'type': 'movie'}],
            'page': {'next_cursor': 'next'}}
        result = Catalog(session).search('a & b', 'opaque/+')
        self.assertEqual([item['content_id'] for item in result['items']], ['episode', 'movie'])
        self.assertEqual(result['next_cursor'], 'next')

    def test_unsupported_search_capability_falls_back_without_hiding_auth_errors(self):
        for status in (404, 401):
            session = Session()
            session.responses['/catalog/search/capabilities'] = Error('http_error', status)
            session.responses['/catalog?source=query&q=title&type=video&limit=50&skip_total=false'] = {
                'items': [], 'page': {}}
            if status == 404:
                self.assertEqual(Catalog(session).search('title'), {'items': [], 'next_cursor': None})
            else:
                with self.assertRaises(Error):
                    Catalog(session).search('title')
                self.assertEqual(len(session.requests), 1)

    def test_personal_actions_are_profile_bound_and_confirmed_by_read(self):
        from unittest.mock import Mock
        for field, path, method in (('played', 'watched', 'POST'), ('is_favorite', 'favorites', 'PUT'),
                                    ('in_watchlist', 'watchlist', 'PUT')):
            for enabled in (True, False):
                with self.subTest(field=field, enabled=enabled):
                    session = Mock()
                    session.status.return_value = {'profile': {'id': 'viewer'}}
                    item = {'content_id': 'movie/id', 'user_state': {field: enabled}}
                    session.request.side_effect = [None, item]
                    self.assertEqual(Catalog(session).set_state('movie/id', field, enabled), item)
                    session.request.assert_any_call(method if enabled else 'DELETE', '/' + path + '/movie%2Fid',
                                                    expected_profile='viewer')
                    session.request.assert_any_call('GET', '/catalog/items/movie%2Fid', expected_profile='viewer')

        session.request.side_effect = [None, {'user_state': {'is_favorite': False}}]
        with self.assertRaises(Error):
            Catalog(session).set_state('movie/id', 'is_favorite', True)


    def test_home_dismissal_preserves_anchor_and_profile(self):
        from unittest.mock import Mock
        session = Mock()
        session.status.return_value = {'profile': {'id': 'viewer'}}
        catalog = Catalog(session)
        catalog.dismiss_home('episode/a', 'continue_watching', '2026-10-24T10:00:00.123Z')
        session.request.assert_called_once_with(
            'PUT', '/home/dismissals/continue_watching/episode%2Fa',
            {'progress_updated_at': '2026-10-24T10:00:00.123Z'}, expected_profile='viewer')
        session.request.reset_mock()
        catalog.dismiss_home('episode/a', 'next_up', 'show/b')
        session.request.assert_called_once_with(
            'PUT', '/home/dismissals/next_up/episode%2Fa', {'series_id': 'show/b'}, expected_profile='viewer')
        session.request.reset_mock()
        for surface, anchor in (('other', 'show'), ('next_up', ''), ('continue_watching', None)):
            with self.subTest(surface=surface, anchor=anchor), self.assertRaises(Error):
                catalog.dismiss_home('episode/a', surface, anchor)
        session.request.assert_not_called()

    def test_home_preload_preserves_layout_order_and_pages_progress(self):
        session = Session()
        session.responses['/home/sections'] = {'sections': [
            {'id': 'recent', 'items': [{'content_id': 'r', 'type': 'movie'}]},
            {'id': 'watching', 'section_type': 'continue_watching', 'items': []}]}
        session.responses['/catalog?source=section&scope=home&section_id=watching&limit=50&skip_total=false'] = {
            'items': [{'content_id': 'episode', 'type': 'episode'}], 'page': {'next_cursor': 'opaque'}}
        rows = Catalog(session).home_content([{'id': 'watching'}, {'id': 'recent'}])
        self.assertEqual([row['id'] for row in rows], ['watching', 'recent'])
        self.assertEqual(rows[0]['items'], [{'content_id': 'episode', 'type': 'episode'}])
        self.assertEqual(rows[0]['next_cursor'], 'opaque')
        self.assertEqual(len(session.requests), 2)

    def test_home_preload_falls_back_only_for_unsupported_aggregate(self):
        for status in (404, 503):
            session = Session()
            session.responses['/home/sections'] = Error('unavailable', status)
            session.responses['/home/sections/one/items'] = {'id': 'one', 'items': []}
            if status == 404:
                self.assertEqual(Catalog(session).home_content([{'id': 'one'}]), [{'id': 'one', 'items': []}])
            else:
                with self.assertRaises(Error):
                    Catalog(session).home_content([{'id': 'one'}])
                self.assertEqual(session.requests, ['/home/sections'])

    def test_cached_reads_are_isolated_profile_bound_and_invalidatable(self):
        session = Session()
        session.responses['/home/layout'] = {'sections': [{'id': 'a'}]}
        catalog = Catalog(session, cache_reads=True)
        catalog.home()[0]['id'] = 'local edit'
        self.assertEqual(catalog.home(), [{'id': 'a'}])
        self.assertEqual(len(session.requests), 1)
        catalog.invalidate()
        catalog.home()
        self.assertEqual(len(session.requests), 2)
        session.profile = 'other'
        with self.assertRaises(Error):
            catalog.home()
        self.assertEqual(len(session.requests), 2)

    def test_invalidation_during_fetch_does_not_repopulate_cache(self):
        from unittest.mock import Mock
        session = Mock()
        session.status.return_value = {'profile': {'id': 'viewer'}}
        catalog = Catalog(session, cache_reads=True)
        def fetch(*args, **kwargs):
            catalog.invalidate()
            return {'sections': []}
        session.request.side_effect = fetch
        catalog.home()
        catalog.home()
        self.assertEqual(session.request.call_count, 2)

    def test_detail_actions_bypass_cached_metadata_and_artwork_matches_scale(self):
        from unittest.mock import Mock
        session = Mock()
        session.status.return_value = {'profile': {'id': 'viewer'}}
        session.request.return_value = {'content_id': 'a'}
        catalog = Catalog(session, cache_reads=True)
        catalog.artwork_scale = 2
        catalog.item('a', fresh=False)
        catalog.item('a', fresh=False)
        self.assertEqual(session.request.call_count, 1)
        catalog.item('a')
        self.assertEqual(session.request.call_count, 2)
        query = parse_qs(urlsplit(session.request.call_args.args[1]).query)
        self.assertEqual(query, {'poster_width': ['560'], 'backdrop_width': ['3840'], 'still_width': ['500']})

    def test_cached_reads_expire_and_watch_reads_stay_fresh(self):
        from unittest.mock import patch
        session = Session()
        session.responses['/home/layout'] = {'sections': []}
        session.responses['/watch/a'] = {'versions': []}
        catalog = Catalog(session, cache_reads=True)
        with patch('silo.catalog.time.monotonic', return_value=100) as clock:
            catalog.home()
            clock.return_value = 200
            catalog.home()
            self.assertEqual(session.requests, ['/home/layout'])
            clock.return_value = 401
            catalog.home()
            self.assertEqual(session.requests, ['/home/layout', '/home/layout'])
        catalog.watch('a')
        catalog.watch('a')
        self.assertEqual(session.requests[-2:], ['/watch/a', '/watch/a'])
