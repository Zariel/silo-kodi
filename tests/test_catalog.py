from pathlib import Path
import sys
import unittest
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'plugin.video.silo/resources/lib'))
from silo.catalog import Catalog, artwork
from silo.client import Error


class Session:
    def __init__(self):
        self.profile = 'viewer'
        self.responses = {}
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
        session.responses['/catalog?source=section&scope=home&section_id=custom%2F1&limit=50&cursor=opaque%2F%2B'] = {
            'items': [episode, {'type': 'future'}], 'page': {'next_cursor': 'next-token'}}
        catalog = Catalog(session)
        self.assertEqual(catalog.home_section('custom/1'), {
            'id': 'custom/1', 'total_count': 9, 'items': [episode]})
        self.assertEqual(catalog.home_page('custom/1', 'opaque/+'), {
            'items': [episode], 'next_cursor': 'next-token'})

    def test_library_types(self):
        session = Session()
        session.responses['/user/libraries'] = {'items': [
            {'id': 'm', 'type': 'movies'}, {'id': 's', 'type': 'series'},
            {'id': 'a', 'type': 'music'}, {'id': 'b', 'type': 'books'}]}
        self.assertEqual(Catalog(session).libraries(), [
            {'id': 'm', 'type': 'movies'}, {'id': 's', 'type': 'series'}])

    def test_cursor_survives_filtered_page(self):
        session = Session()
        session.responses['/catalog?source=query&library_id=lib%2F1&type=video&sort=title&limit=50'] = {
            'items': [{'content_id': 'unknown', 'type': 'future'}],
            'page': {'next_cursor': 'opaque/+?='}}
        session.responses['/catalog?source=query&library_id=lib%2F1&type=video&sort=title&limit=50&cursor=opaque%2F%2B%3F%3D'] = {
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
        session.responses['/catalog/items/title%2F1/versions'] = {'items': [{'file_id': 'file-9', 'container': 'mkv'}]}
        catalog = Catalog(session)
        detail = catalog.item('title/1')
        self.assertEqual(catalog.versions(detail['content_id']), [{'file_id': 'file-9', 'container': 'mkv'}])

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
                          lambda: catalog.episodes('show', 1), lambda: catalog.versions('title'),
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
