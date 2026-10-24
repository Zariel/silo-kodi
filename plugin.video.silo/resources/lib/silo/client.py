"""Silo v2 authentication shared by Kodi and the development harness."""

from contextlib import contextmanager
from datetime import datetime
from email.utils import parsedate_to_datetime
import fcntl
import json
import math
import os
from pathlib import Path
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
import uuid


class Error(Exception):
    def __init__(self, code, status=0, retry_after=0):
        self.code = code
        self.status = status
        self.retry_after = retry_after
        messages = {
            'connection_failed': 'Cannot reach Silo. Check the connection and try again.',
            'sign_in_required': 'Sign in to Silo to continue.',
            'profile_required': 'Choose a profile to continue.',
            'server_changed': 'The configured server changed. Open Silo again.',
            'already_signed_in': 'Sign out before connecting another account.',
            'profile_changed': 'The active profile changed. Open the library again.',
            'invalid_pin': 'Incorrect profile PIN.',
            'rate_limited': 'Too many attempts. Try again in {} seconds.'.format(retry_after),
            'invalid_server': 'Enter an HTTPS server URL without credentials, a query, or a fragment.',
            'invalid_response': 'Silo returned an unsupported response.',
            'pairing_unavailable': 'This server does not offer device sign-in.',
            'state_unreadable': 'The saved Silo session could not be read.',
            'redirect_refused': 'Silo redirected the API request. Check the configured server URL.',
        }
        # Never display arbitrary response bodies or URLs containing credentials.
        super().__init__(messages.get(code, 'Silo refused the request (HTTP {}).'.format(status)))


def server_url(value):
    try:
        url = urlsplit(value.strip())
        if (url.scheme != 'https' or not url.hostname or url.username or url.password
                or url.query or url.fragment or any(c.isspace() for c in value)):
            raise ValueError()
        port = url.port
        host = url.hostname.lower()
        if ':' in host:
            host = '[' + host + ']'
        netloc = host + (':' + str(port) if port and port != 443 else '')
        return urlunsplit(('https', netloc, url.path.rstrip('/'), '', ''))
    except ValueError:
        raise Error('invalid_server') from None


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise Error('redirect_refused', code)


def _retry_after(value):
    try:
        return max(1, int(value))
    except (ValueError, TypeError):
        try:
            return max(1, math.ceil(parsedate_to_datetime(value).timestamp() - time.time()))
        except (ValueError, TypeError, AttributeError):
            return 30


class Http:
    def __init__(self, server):
        self.server = server
        self.opener = build_opener(_NoRedirect())

    def request(self, method, path, body=None, headers=None):
        if not path.startswith('/') or path.startswith('//'):
            raise ValueError('API paths must be relative to /api/v2')
        request_headers = {'Accept': 'application/json', 'User-Agent': 'Silo-Kodi/0.1'}
        request_headers.update(headers or {})
        data = None
        if body is not None:
            data = json.dumps(body).encode('utf-8')
            request_headers['Content-Type'] = 'application/json'
        req = Request(self.server + '/api/v2' + path, data, request_headers, method=method)
        try:
            with self.opener.open(req, timeout=15) as response:
                raw = response.read(8 * 1024 * 1024 + 1)
                if len(raw) > 8 * 1024 * 1024:
                    raise Error('invalid_response')
                return json.loads(raw) if raw else None
        except HTTPError as exc:
            try:
                problem = json.loads(exc.read(65536))
                code = str(problem.get('type', '')).rsplit('/', 1)[-1]
            except (ValueError, AttributeError):
                code = ''
            raise Error(code or 'http_error', exc.code, _retry_after(exc.headers.get('Retry-After'))) from None
        except (URLError, TimeoutError, OSError):
            raise Error('connection_failed') from None
        except (ValueError, UnicodeError):
            raise Error('invalid_response') from None


class _Store:
    def __init__(self, directory, server):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.server = server
        self.path = self.directory / 'session.json'

    @contextmanager
    def locked(self, rebind=False):
        fd = os.open(self.directory / 'session.lock', os.O_CREAT | os.O_RDWR, 0o600)
        with os.fdopen(fd, 'a') as lock:
            # Kodi and the headless harness may overlap. Hold one process lock
            # across read, refresh, and replacement so rotated tokens cannot race.
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                state = json.loads(self.path.read_text()) if self.path.exists() else {}
                if not isinstance(state, dict):
                    raise ValueError()
            except (ValueError, OSError):
                raise Error('state_unreadable') from None
            if self.server and state.get('server') != self.server:
                if state.get('server') and not rebind:
                    raise Error('server_changed')
                state = {'server': self.server, 'device_id': str(uuid.uuid4())}
                self.save(state)
            yield state

    def save(self, state):
        fd, name = tempfile.mkstemp(prefix='.session-', dir=self.directory)
        try:
            with os.fdopen(fd, 'w') as stream:
                json.dump(state, stream)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, self.path)
            # Persist the rename before reporting a one-time credential delivery
            # as complete. The file and lock are local to this Kodi installation.
            directory = os.open(self.directory, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            if os.path.exists(name):
                os.unlink(name)


def _expiry(tokens):
    try:
        if not tokens['access_token'] or not tokens['refresh_token']:
            raise ValueError()
        return time.time() + float(tokens['expires_in'])
    except (KeyError, ValueError, TypeError):
        raise Error('invalid_response') from None


class Session:
    def __init__(self, server, directory, transport=None):
        self.server = server_url(server)
        self.store = _Store(directory, self.server)
        self.http = transport or Http(self.server)

    @classmethod
    def open(cls, directory):
        with _Store(directory, None).locked() as state:
            server = state.get('server')
        return cls(server, directory) if server else None

    @classmethod
    def configure(cls, server, directory, transport=None):
        session = cls(server, directory, transport)
        with session.store.locked(rebind=True):
            pass
        return session

    def status(self):
        with self.store.locked() as state:
            profile = state.get('profile')
            return {'signed_in': bool(state.get('tokens')), 'server': self.server,
                    'profile': {k: profile[k] for k in ('id', 'name')} if profile else None}

    def public(self, path):
        return self.http.request('GET', path)

    def _headers(self, state, profile):
        headers = {'Authorization': 'Bearer ' + state['tokens']['access_token'],
                   'X-Silo-Device-Id': state['device_id'], 'X-Silo-Client': 'Silo Kodi'}
        if profile:
            active = state.get('profile')
            if not active:
                raise Error('profile_required')
            headers['X-Profile-Id'] = active['id']
            if active.get('token'):
                headers['X-Profile-Token'] = active['token']
        return headers

    def _refresh(self, state):
        try:
            tokens = self.http.request('POST', '/auth/refresh', {'refresh_token': state['tokens']['refresh_token']})
        except Error as exc:
            if exc.status == 401:
                state.pop('tokens', None)
                state.pop('profile', None)
                self.store.save(state)
                raise Error('sign_in_required') from None
            raise
        expiry = _expiry(tokens)
        state['tokens'].update(tokens)
        state['expires_at'] = expiry
        self.store.save(state)

    def _request(self, state, method, path, body=None, profile=False, retry=True):
        if not state.get('tokens'):
            raise Error('sign_in_required')
        if state.get('expires_at', 0) <= time.time() + 30:
            self._refresh(state)
        try:
            return self.http.request(method, path, body, self._headers(state, profile))
        except Error as exc:
            if exc.status != 401 or not retry:
                raise
        self._refresh(state)
        return self.http.request(method, path, body, self._headers(state, profile))

    def request(self, method, path, body=None, profile=True, expected_profile=None):
        with self.store.locked() as state:
            if expected_profile is not None and state.get('profile', {}).get('id') != expected_profile:
                raise Error('profile_changed')
            return self._request(state, method, path, body, profile)

    def profiles(self):
        return self.request('GET', '/profiles', profile=False)['items']

    def select_profile(self, profile_id, pin=None):
        with self.store.locked() as state:
            profiles = self._request(state, 'GET', '/profiles')['items']
            profile = next((p for p in profiles if str(p['id']) == str(profile_id)), None)
            if profile is None:
                raise Error('profile_required')
            token = None
            if profile['has_pin']:
                if pin is None:
                    raise Error('invalid_pin')
                # PIN checks spend a guess. Never automatically replay one.
                result = self._request(state, 'POST', '/profiles/' + quote(str(profile_id), safe='') + '/verify-pin',
                                       {'pin': pin}, retry=False)
                if not result.get('valid') or not result.get('profile_token'):
                    raise Error('invalid_pin')
                token = result['profile_token']
            state['profile'] = {'id': str(profile['id']), 'name': profile['name'], 'token': token}
            self.store.save(state)
            return {'id': str(profile['id']), 'name': profile['name']}

    def logout(self):
        with self.store.locked() as state:
            revoked = True
            try:
                if state.get('tokens'):
                    self._request(state, 'POST', '/auth/logout', profile=False)
            except Error as exc:
                revoked = exc.status == 401 or exc.code == 'sign_in_required'
            finally:
                for key in ('tokens', 'profile', 'expires_at'):
                    state.pop(key, None)
                self.store.save(state)
            return revoked

    def start_pairing(self):
        with self.store.locked() as state:
            if state.get('tokens'):
                raise Error('already_signed_in')
            pairing = state.get('pairing')
            if pairing and pairing['deadline'] > time.time():
                return self._pairing_view(pairing)
            capability = self.public('/auth/device/capability')
            if capability.get('state') != 'available' or 2 not in capability.get('protocol_versions', []):
                raise Error('pairing_unavailable')
            result = self.http.request('POST', '/auth/device/start', {
                'device_name': 'Silo Kodi', 'device_platform': 'Kodi', 'client_purpose': 'device_login'})
            try:
                verification = urlsplit(result['verification_uri_complete'])
                if verification.scheme != 'https' or not verification.hostname or verification.username:
                    raise ValueError()
                pairing = dict(result, deadline=time.time() + int(result['expires_in']),
                               next_poll=time.time() + max(1, int(result['interval'])))
                if not result['device_code']:
                    raise ValueError()
            except (KeyError, TypeError, ValueError):
                raise Error('invalid_response') from None
            state['pairing'] = pairing
            self.store.save(state)
            return self._pairing_view(pairing)

    @staticmethod
    def _pairing_view(pairing):
        return {k: pairing[k] for k in ('verification_uri', 'verification_uri_complete', 'user_code', 'deadline')}

    def poll_pairing(self):
        with self.store.locked() as state:
            pairing = state.get('pairing')
            if not pairing:
                return {'status': 'approved' if state.get('tokens') else 'expired'}
            now = time.time()
            if pairing['next_poll'] > now:
                return {'status': 'pending', 'poll_after': math.ceil(pairing['next_poll'] - now)}
            try:
                result = self.http.request('POST', '/auth/device/poll', {'device_code': pairing['device_code']})
            except Error as exc:
                delay = exc.retry_after if exc.status == 429 else 5
                pairing['next_poll'] = now + delay
                self.store.save(state)
                raise
            status = result.get('status')
            if status == 'approved':
                # V2 wraps tokens, unlike v1. Save the one-time response before
                # telling the UI or harness that approval completed.
                tokens = result.get('tokens', {})
                expiry = _expiry(tokens)
                state.update(tokens=tokens, expires_at=expiry)
                state.pop('profile', None)
                state.pop('pairing', None)
            elif status == 'pending':
                pairing['next_poll'] = time.time() + max(1, result.get('poll_after', 3))
                if result.get('expires_at'):
                    pairing['deadline'] = datetime.fromisoformat(result['expires_at'].replace('Z', '+00:00')).timestamp()
            elif status in ('denied', 'canceled', 'expired', 'consumed'):
                state.pop('pairing', None)
            else:
                raise Error('invalid_response')
            self.store.save(state)
            return {k: result[k] for k in ('status', 'poll_after', 'opened') if k in result}

    def cancel_pairing(self):
        with self.store.locked() as state:
            pairing = state.get('pairing')
            if pairing:
                self.http.request('POST', '/auth/device/cancel', {'device_code': pairing['device_code']})
                state.pop('pairing', None)
                self.store.save(state)
