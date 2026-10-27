"""Profile-bound, on-demand catalog reads. No local catalog or API credentials in art."""
from copy import deepcopy
import math
import time
import threading
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
    def __init__(self, session, cache_reads=False):
        self.session = session
        profile = session.status()['profile']
        if not profile:
            raise Error('profile_required')
        self.profile_id = profile['id']
        self._search_type = None
        self.cache_reads = cache_reads
        self.artwork_scale = 0
        self._cache = {}
        self._cache_lock = threading.Lock()
        self._generation = 0

    def invalidate(self):
        with self._cache_lock:
            self._cache.clear()
            self._generation += 1

    def _get(self, path, query=None, fresh=False):
        cacheable = path.startswith(('/catalog', '/home/')) and not fresh
        if self.artwork_scale and path.startswith(('/catalog', '/home/sections')) and path != '/catalog/search/capabilities':
            query = dict(query or {}, poster_width=math.ceil(280 * self.artwork_scale),
                         backdrop_width=math.ceil(1920 * self.artwork_scale), still_width=math.ceil(250 * self.artwork_scale))
        if query:
            path += '?' + urlencode(query)
        if self.cache_reads and cacheable:
            profile = self.session.status()['profile']
            if not profile or profile['id'] != self.profile_id:
                raise Error('profile_changed')
            with self._cache_lock:
                generation = self._generation
                cached = self._cache.get(path)
            if cached and cached[0] > time.monotonic():
                return deepcopy(cached[1])
        result = self.session.request('GET', path, expected_profile=self.profile_id)
        if self.cache_reads and cacheable:
            snapshot = deepcopy(result)
            with self._cache_lock:
                # A read started before a mutation must not repopulate its cache.
                if generation == self._generation:
                    if len(self._cache) >= 128:
                        self._cache.pop(next(iter(self._cache)))
                    self._cache[path] = (time.monotonic() + 300, snapshot)
        return result

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
        return self._home_cards(result)

    def _home_cards(self, result):
        if result.get('section_type') in ('continue_watching', 'in_progress', 'next_up'):
            # Section cards are capped by the Home recipe; catalog supplies the
            # complete ordered collection and an opaque continuation cursor.
            return dict(result, **self.home_page(result['id']))
        return dict(result, items=[item for item in result['items']
                                   if item.get('type') in ('movie', 'series', 'episode')])

    def home_content(self, sections):
        try:
            rows = {str(row['id']): row for row in self._get('/home/sections')['sections']}
        except Error as exc:
            if exc.status not in (404, 405, 501):
                raise
            rows = {}
        return [self._home_cards(rows[str(section['id'])]) if str(section['id']) in rows
                else self.home_section(section['id']) for section in sections]

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

    def search(self, text, cursor=None):
        if self._search_type is None:
            try:
                capabilities = self._get('/catalog/search/capabilities')
            except Error as exc:
                if exc.status not in (404, 405, 501):
                    raise
                capabilities = {}
            self._search_type = 'video_with_episodes' if capabilities.get('video_with_episodes_scope') else 'video'
        query = {'source': 'query', 'q': text, 'type': self._search_type,
                 'limit': 50, 'skip_total': 'true'}
        if cursor is not None:
            query['cursor'] = cursor
        result = self._get('/catalog', query)
        return {'items': [item for item in result['items'] if item.get('type') in ('movie', 'series', 'episode')],
                'next_cursor': result.get('page', {}).get('next_cursor')}

    def set_state(self, content_id, field, enabled):
        path, method = {
            'played': ('watched', 'POST'),
            'is_favorite': ('favorites', 'PUT'),
            'in_watchlist': ('watchlist', 'PUT'),
        }[field]
        self.session.request(method if enabled else 'DELETE',
                             '/' + path + '/' + quote(str(content_id), safe=''),
                             expected_profile=self.profile_id)
        self.invalidate()
        # Re-read authoritative state before presenting the mutation as complete.
        item = self.item(content_id)
        if item.get('user_state', {}).get(field) is not enabled:
            raise Error('invalid_response')
        return item

    def item(self, content_id, fresh=True):
        return self._get('/catalog/items/' + quote(str(content_id), safe=''), fresh=fresh)

    def dismiss_home(self, content_id, surface, anchor):
        field = {'continue_watching': 'progress_updated_at', 'next_up': 'series_id'}.get(surface)
        if not field or not isinstance(anchor, str) or not anchor.strip():
            raise Error('invalid_response')
        # Use the observed card's anchor: newer progress must not be hidden by
        # a menu opened against an older snapshot.
        self.session.request('PUT', '/home/dismissals/' + surface + '/' + quote(str(content_id), safe=''),
                             {field: anchor}, expected_profile=self.profile_id)
        self.invalidate()

    def seasons(self, series_id):
        return self._get('/catalog/series/' + quote(str(series_id), safe='') + '/seasons')['items']

    def episodes(self, series_id, season):
        return self._get('/catalog/series/' + quote(str(series_id), safe='') + '/seasons/'
                         + quote(str(season), safe='') + '/episodes')['items']

    def watch(self, content_id):
        return self._get('/watch/' + quote(str(content_id), safe=''))

    def next_episode(self, episode):
        series = episode.get('series_id')
        season, number = episode.get('season_number'), episode.get('episode_number')
        if episode.get('type') != 'episode' or not series or type(season) is not int or type(number) is not int:
            return None

        def available(items):
            return [item for item in items if type(item.get('episode_number')) is int
                    and ('files' not in item or any(not file.get('unreadable') for file in item['files']))]

        candidates = [item for item in available(self.episodes(series, season)) if item['episode_number'] > number]
        if not candidates:
            seasons = [item['season_number'] for item in self.seasons(series)
                       if type(item.get('season_number')) is int and item['season_number'] > season
                       and item['season_number'] > 0]
            if not seasons:
                return None
            candidates = available(self.episodes(series, min(seasons)))
        return min(candidates, key=lambda item: item['episode_number']) if candidates else None
