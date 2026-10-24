import copy
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'plugin.video.silo/resources/lib'))
from silo.client import Error, Http, Session, server_url


class Server:
    def __init__(self):
        self.calls = []
        self.polls = [{'status': 'approved', 'tokens': {
            'access_token': 'access-1', 'refresh_token': 'refresh-1', 'expires_in': 3600,
            'user': {'id': 'account-1'}}, 'poll_after': 3}]
        self.refresh_error = None
        self.pin_result = {'valid': False}

    def request(self, method, path, body=None, headers=None):
        self.calls.append((method, path, copy.deepcopy(body), copy.deepcopy(headers)))
        if path == '/auth/device/capability':
            return {'state': 'available', 'protocol_versions': [2]}
        if path == '/auth/device/start':
            return {'device_code': 'secret-device-code', 'user_code': '1234-5678',
                    'verification_uri': 'https://silo.example.test/activate',
                    'verification_uri_complete': 'https://silo.example.test/activate?code=12345678',
                    'expires_in': 900, 'interval': 3}
        if path == '/auth/device/poll':
            return copy.deepcopy(self.polls.pop(0))
        if path == '/auth/device/cancel':
            return {'status': 'canceled'}
        if path == '/auth/refresh':
            if self.refresh_error:
                raise self.refresh_error
            time.sleep(0.02)
            return {'access_token': 'access-2', 'refresh_token': 'refresh-2', 'expires_in': 3600}
        if path == '/profiles':
            return {'items': [{'id': 'open', 'name': 'Open', 'has_pin': False},
                              {'id': 'locked', 'name': 'Locked', 'has_pin': True}]}
        if path.endswith('/verify-pin'):
            if isinstance(self.pin_result, Exception):
                raise self.pin_result
            return self.pin_result
        if path == '/auth/logout':
            return None
        if path == '/user/libraries':
            return {'items': [{'id': 'movies', 'name': 'Movies'}]}
        raise AssertionError((method, path))


class Authentication(unittest.TestCase):
    def test_media_authority_refreshes_and_rejects_stale_profiles(self):
        self.approve()
        self.session.select_profile('open')
        with patch('silo.client.time.time', return_value=time.time() + 7200):
            headers = self.session.media_headers('open')
        self.assertEqual(headers['Authorization'], 'Bearer access-2')
        self.assertEqual(headers['X-Profile-Id'], 'open')
        with self.assertRaises(Error) as raised:
            self.session.media_headers('another')
        self.assertEqual(raised.exception.code, 'profile_changed')

    def test_playback_prevents_authority_changes_until_cleanup(self):
        self.approve()
        self.session.select_profile('open')
        with self.session.store.playback_lock():
            self.assertEqual(self.session.request('GET', '/user/libraries')['items'][0]['id'], 'movies')
            for change in (lambda: self.session.select_profile('locked', '1234'), self.session.logout,
                           lambda: Session.configure('https://other.example.test', self.temp.name)):
                with self.assertRaises(Error) as raised:
                    change()
                self.assertEqual(raised.exception.code, 'playback_active')
            self.assertEqual(self.session.status()['profile']['id'], 'open')
        self.session.logout()
        self.assertFalse(self.session.status()['signed_in'])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.server = Server()
        self.session = Session('https://silo.example.test', self.temp.name, self.server)

    def approve(self):
        self.session.start_pairing()
        with patch('silo.client.time.time', return_value=time.time() + 5):
            self.assertEqual(self.session.poll_pairing()['status'], 'approved')

    def calls(self, path):
        return [c for c in self.server.calls if c[1] == path]

    def test_approval_survives_restart_without_exposing_tokens(self):
        pair = self.session.start_pairing()
        self.assertNotIn('device_code', pair)
        with patch('silo.client.time.time', return_value=time.time() + 5):
            self.assertEqual(self.session.poll_pairing(), {'status': 'approved', 'poll_after': 3})
        restarted = Session('https://silo.example.test/', self.temp.name, self.server)
        self.assertTrue(restarted.status()['signed_in'])
        restarted.profiles()
        self.assertEqual(self.calls('/profiles')[-1][3]['Authorization'], 'Bearer access-1')
        self.assertNotIn('access-1', json.dumps(restarted.status()))
        self.assertEqual((Path(self.temp.name) / 'session.json').stat().st_mode & 0o777, 0o600)

    def test_polling_waits_and_honors_rate_limit(self):
        self.session.start_pairing()
        self.assertEqual(self.session.poll_pairing()['status'], 'pending')
        self.assertEqual(len(self.calls('/auth/device/poll')), 0)
        original = self.server.request
        def rate_limited(method, path, body=None, headers=None):
            if path == '/auth/device/poll':
                raise Error('rate_limited', 429, 60)
            return original(method, path, body, headers)
        self.server.request = rate_limited
        now = time.time()
        with patch('silo.client.time.time', return_value=now + 5):
            with self.assertRaises(Error):
                self.session.poll_pairing()
        with patch('silo.client.time.time', return_value=now + 10):
            self.assertEqual(self.session.poll_pairing()['poll_after'], 55)

    def test_pending_expiry_can_be_extended_by_server(self):
        now = time.time()
        expiry = '2099-01-01T00:00:00Z'
        self.server.polls = [{'status': 'pending', 'poll_after': 7, 'expires_at': expiry},
                             {'status': 'expired', 'poll_after': 3}]
        self.session.start_pairing()
        with patch('silo.client.time.time', return_value=now + 5):
            self.session.poll_pairing()
            self.assertGreater(self.session.start_pairing()['deadline'], now + 900)
        with patch('silo.client.time.time', return_value=now + 15):
            self.assertEqual(self.session.poll_pairing()['status'], 'expired')
        self.assertFalse(self.session.status()['signed_in'])
        self.session.start_pairing()
        self.assertEqual(len(self.calls('/auth/device/start')), 2)

    def test_cancellation_is_repeatable(self):
        self.session.start_pairing()
        self.session.cancel_pairing()
        self.session.cancel_pairing()
        self.assertEqual(self.session.poll_pairing()['status'], 'expired')
        self.assertEqual(len(self.calls('/auth/device/cancel')), 1)

    def test_wrong_pin_preserves_active_profile(self):
        self.approve()
        self.session.select_profile('open')
        with self.assertRaisesRegex(Error, 'Incorrect'):
            self.session.select_profile('locked', '0000')
        self.assertEqual(self.session.status()['profile']['id'], 'open')
        self.assertEqual(len(self.calls('/profiles/locked/verify-pin')), 1)

    def test_pin_request_is_never_replayed(self):
        self.approve()
        self.server.pin_result = Error('unauthorized', 401)
        with self.assertRaises(Error):
            self.session.select_profile('locked', '1234')
        self.assertEqual(len(self.calls('/profiles/locked/verify-pin')), 1)
        self.assertEqual(len(self.calls('/auth/refresh')), 0)

    def test_profile_authority_and_stale_navigation(self):
        self.approve()
        self.session.select_profile('open')
        self.server.pin_result = {'valid': True, 'profile_token': 'proof'}
        self.session.select_profile('locked', '1234')
        with self.assertRaises(Error) as caught:
            self.session.request('GET', '/user/libraries', expected_profile='open')
        self.assertEqual(caught.exception.code, 'profile_changed')
        self.session.request('GET', '/user/libraries', expected_profile='locked')
        headers = self.calls('/user/libraries')[-1][3]
        self.assertEqual(headers['X-Profile-Id'], 'locked')
        self.assertEqual(headers['X-Profile-Token'], 'proof')
        self.session.profiles()
        self.assertNotIn('X-Profile-Id', self.calls('/profiles')[-1][3])

    def test_overlapping_callers_refresh_once(self):
        self.approve()
        later = time.time() + 7200
        second = Session('https://silo.example.test', self.temp.name, self.server)
        with patch('silo.client.time.time', return_value=later):
            with ThreadPoolExecutor(2) as pool:
                list(pool.map(lambda client: client.profiles(), [self.session, second]))
        self.assertEqual(len(self.calls('/auth/refresh')), 1)
        for call in self.calls('/profiles'):
            self.assertEqual(call[3]['Authorization'], 'Bearer access-2')

    def test_rejected_token_renews_persistently(self):
        self.approve()
        request = self.server.request
        observed = []

        def reject_old_access(method, path, body=None, headers=None):
            if path == '/profiles':
                observed.append(headers['Authorization'])
                if headers['Authorization'] == 'Bearer access-1':
                    raise Error('unauthorized', 401)
            return request(method, path, body, headers)

        self.server.request = reject_old_access
        self.assertEqual(self.session.profiles()[0]['id'], 'open')
        reopened = Session('https://silo.example.test', self.temp.name, self.server)
        self.assertEqual(reopened.profiles()[0]['id'], 'open')
        self.assertEqual(observed, ['Bearer access-1', 'Bearer access-2', 'Bearer access-2'])
        self.assertEqual(len(self.calls('/auth/refresh')), 1)

    def test_rejected_retry_does_not_refresh_again(self):
        self.approve()
        request = self.server.request

        def reject_access(method, path, body=None, headers=None):
            if path == '/profiles':
                raise Error('unauthorized', 401)
            return request(method, path, body, headers)

        self.server.request = reject_access
        with self.assertRaises(Error) as raised:
            self.session.profiles()
        self.assertEqual(raised.exception.status, 401)
        self.assertEqual(len(self.calls('/auth/refresh')), 1)

    def test_refresh_outage_preserves_login_but_refusal_clears_it(self):
        self.approve()
        later = time.time() + 7200
        self.server.refresh_error = Error('dependency_unavailable', 503)
        with patch('silo.client.time.time', return_value=later), self.assertRaises(Error):
            self.session.profiles()
        self.assertTrue(self.session.status()['signed_in'])
        self.server.refresh_error = Error('session_expired', 401)
        with patch('silo.client.time.time', return_value=later), self.assertRaises(Error):
            self.session.profiles()
        self.assertFalse(self.session.status()['signed_in'])

    def test_logout_clears_login_on_network_failure(self):
        self.approve()
        self.session.select_profile('open')
        original = self.server.request
        def offline(method, path, body=None, headers=None):
            if path == '/auth/logout':
                raise Error('connection_failed')
            return original(method, path, body, headers)
        self.server.request = offline
        self.assertFalse(self.session.logout())
        self.assertEqual(self.session.status()['profile'], None)
        self.assertFalse(self.session.status()['signed_in'])

    def test_server_change_does_not_reuse_authority(self):
        self.approve()
        other = Session.configure('https://other.example.test', self.temp.name, self.server)
        self.assertFalse(other.status()['signed_in'])
        with self.assertRaises(Error):
            other.profiles()
        self.assertEqual(len(self.calls('/profiles')), 0)
        with self.assertRaises(Error) as caught:
            self.session.profiles()
        self.assertEqual(caught.exception.code, 'server_changed')
        self.assertEqual(other.status()['server'], 'https://other.example.test')


class Transport(unittest.TestCase):
    def test_server_validation(self):
        self.assertEqual(server_url('https://SILO.example.test:443/root/'), 'https://silo.example.test/root')
        for value in ('http://silo.example.test', 'https://user:pass@silo.example.test',
                      'https://silo.example.test?token=secret', 'https://silo.example.test/#fragment'):
            with self.subTest(value=value), self.assertRaises(Error):
                server_url(value)

    def test_redirect_does_not_forward_credentials(self):
        requests = []
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                requests.append(self.path)
                self.send_response(302)
                self.send_header('Location', '/stolen')
                self.end_headers()
            def log_message(self, *args):
                pass
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            http = Http('http://127.0.0.1:' + str(server.server_port))
            with self.assertRaises(Error) as caught:
                http.request('GET', '/profiles', headers={'Authorization': 'Bearer secret'})
            self.assertEqual(caught.exception.code, 'redirect_refused')
            self.assertEqual(requests, ['/api/v2/profiles'])
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == '__main__':
    unittest.main()
