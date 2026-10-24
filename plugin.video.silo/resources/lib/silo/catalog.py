"""Profile-bound, on-demand catalog reads. No local catalog or API credentials in art."""
from urllib.parse import quote, urlencode, urljoin, urlsplit

from .client import Error


def _home_order(row):
    # Silo DefaultHomeSections recipe order; IDs remain server-owned.
    recipes = ('continue_watching', 'trending_discover', 'recently_added',
               'recommended_for_you', 'because_you_watched', 'returning_shows',
               'critically_acclaimed', 'hidden_gems', 'seasonal_themed')
    recipe = row.get('section_type')
    rank = recipes.index(recipe) if recipe in recipes else len(recipes)
    scope = (row.get('config') or {}).get('media_scope') if recipe == 'recently_added' else None
    return rank, {'movie': 0, 'series': 1}.get(scope, 2)


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
        settings = self._get('/settings/values/effective', {'keys': 'ui.disabled_library_ids'})['items']
        hidden = {str(identifier) for setting in settings if setting['key'] == 'ui.disabled_library_ids'
                  for identifier in (setting['value'] or [])}
        # Unrestricted viewer responses also contain self-hidden libraries.
        return [item for item in self._get('/user/libraries')['items']
                if item.get('type') in ('movies', 'series') and str(item['id']) not in hidden]

    def home(self):
        for path in ('/home/layout', '/home/sections'):
            try:
                # Empty layouts are authoritative, including profile-hidden rows.
                return self._get(path)['sections']
            except Error as exc:
                if exc.status not in (404, 405, 501):
                    raise
        try:
            settings = self._get('/profile/sections/settings', {'scope': 'home'})['items']
        except Error as exc:
            if exc.status in (404, 405, 501):
                raise Error('home_unavailable') from None
            raise
        rows = [row for row in settings if not row.get('hidden')]
        if all(type(row.get('position')) is int and row['position'] >= 0 for row in rows):
            return sorted(rows, key=lambda row: row['position'])
        return sorted(rows, key=_home_order)

    def home_section(self, section_id):
        try:
            result = self._get('/home/sections/' + quote(str(section_id), safe='') + '/items')
        except Error as exc:
            if exc.status not in (404, 405, 501):
                raise
            # The aggregate endpoint already carries cards. Read it afresh so
            # returning from playback does not reuse stale profile progress.
            result = next((row for row in self._get('/home/sections')['sections']
                           if str(row['id']) == str(section_id)), None)
            if result is None:
                raise Error('home_section_unavailable') from None
        return dict(result, items=[item for item in result['items']
                                   if item.get('type') in ('movie', 'series', 'episode')])

    def home_page(self, section_id, cursor=None):
        query = {'source': 'section', 'scope': 'home', 'section_id': section_id, 'limit': 50,
                 'skip_total': 'true'}
        if cursor is not None:
            query['cursor'] = cursor
        # Omit sort and type: preserve recipe ordering and episode cards.
        result = self._get('/catalog', query)
        return {'items': [item for item in result['items']
                          if item.get('type') in ('movie', 'series', 'episode')],
                'next_cursor': result.get('page', {}).get('next_cursor')}

    def page(self, library_id, cursor=None):
        query = {'source': 'query', 'library_id': library_id, 'type': 'video',
                 'sort': 'title', 'limit': 50, 'skip_total': 'true'}
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

    def watch(self, content_id):
        return self._get('/watch/' + quote(str(content_id), safe=''))
