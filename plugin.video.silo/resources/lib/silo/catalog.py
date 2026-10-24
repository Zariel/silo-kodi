"""Profile-bound, on-demand catalog reads. No local catalog or API credentials in art."""
from urllib.parse import quote, urlencode, urljoin, urlsplit

from .client import Error


def artwork(server, value):
    if not isinstance(value, str) or not value or any(c in value for c in ('|', '\r', '\n')):
        return ''
    try:
        url = urljoin(server.rstrip('/') + '/', value)
        parts = urlsplit(url)
    except ValueError:
        return ''
    if parts.scheme != 'https' or not parts.hostname or parts.username or parts.password:
        return ''
    # Signed artwork grants carry their own authority; never append account headers.
    return url


class Catalog:
    def __init__(self, session):
        self.session = session
        profile = session.status()['profile']
        if not profile:
            raise Error('profile_required')
        self.profile_id = profile['id']

    def _get(self, path, query=None):
        if query:
            path += '?' + urlencode(query)
        return self.session.request('GET', path, expected_profile=self.profile_id)

    def libraries(self):
        return [item for item in self._get('/user/libraries')['items']
                if item.get('type') in ('movies', 'series')]

    def home(self):
        try:
            result = self._get('/home/layout')
        except Error as exc:
            if exc.status not in (404, 405, 501):
                raise
            result = self._get('/home/sections')
        # Both endpoints return the profile's visible sections in display order.
        # An empty layout is authoritative; do not replace it with default rows.
        return result['sections']

    def home_section(self, section_id):
        result = self._get('/home/sections/' + quote(str(section_id), safe='') + '/items')
        return dict(result, items=[item for item in result['items']
                                   if item.get('type') in ('movie', 'series', 'episode')])

    def home_page(self, section_id, cursor=None):
        query = {'source': 'section', 'scope': 'home', 'section_id': section_id, 'limit': 50}
        if cursor is not None:
            query['cursor'] = cursor
        # Omit sort and type: preserve recipe ordering and episode cards.
        result = self._get('/catalog', query)
        return {'items': [item for item in result['items']
                          if item.get('type') in ('movie', 'series', 'episode')],
                'next_cursor': result.get('page', {}).get('next_cursor')}

    def page(self, library_id, cursor=None):
        query = {'source': 'query', 'library_id': library_id, 'type': 'video',
                 'sort': 'title', 'limit': 50}
        if cursor is not None:
            query['cursor'] = cursor
        result = self._get('/catalog', query)
        # Keep the server cursor even if an unfamiliar card was omitted.
        return {'items': [item for item in result['items'] if item.get('type') in ('movie', 'series')],
                'next_cursor': result.get('page', {}).get('next_cursor')}

    def item(self, content_id):
        return self._get('/catalog/items/' + quote(str(content_id), safe=''))

    def seasons(self, series_id):
        return self._get('/catalog/series/' + quote(str(series_id), safe='') + '/seasons')['items']

    def episodes(self, series_id, season):
        return self._get('/catalog/series/' + quote(str(series_id), safe='') + '/seasons/'
                         + quote(str(season), safe='') + '/episodes')['items']

    def versions(self, content_id):
        return self._get('/catalog/items/' + quote(str(content_id), safe='') + '/versions')['items']

    def watch(self, content_id):
        return self._get('/watch/' + quote(str(content_id), safe=''))
