import http.client
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import socket
import sys
import threading
import time
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'plugin.video.silo/resources/lib'))
from silo.client import Error
from silo.relay import MediaRelay


class _Origin(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        self.server.requests.append((self.path, dict(self.headers)))
        if self.path == '/stall':
            self.server.worker = threading.current_thread()
            self.server.started.set()
            self.server.release.wait(10)
            return
        if self.headers.get('Authorization') != self.server.token:
            self.send_response(401)
            self.end_headers()
            return
        if self.path == '/redirect':
            self.send_response(302)
            self.send_header('Location', '/unexpected')
            self.end_headers()
            return
        if self.path == '/large':
            self.send_response(200)
            self.send_header('Content-Length', str(64 * 1024 * 1024))
            self.end_headers()
            self.server.started.set()
            try:
                for _ in range(1024):
                    self.wfile.write(b'x' * 65536)
            except (BrokenPipeError, ConnectionResetError):
                pass
            finally:
                self.server.finished.set()
            return
        replies = {
            None: (200, b'0123456789ABCDEFGHIJ', None),
            'bytes=2-5': (206, b'2345', 'bytes 2-5/20'),
            'bytes=-4': (206, b'GHIJ', 'bytes 16-19/20'),
            'bytes=15-': (206, b'FGHIJ', 'bytes 15-19/20'),
            'bytes=99-': (416, b'', 'bytes */20'),
        }
        status, body, content_range = replies[self.headers.get('Range')]
        self.send_response(status)
        self.send_header('Content-Length', '100' if self.path == '/truncated' else str(len(body)))
        self.send_header('Content-Type', 'application/octet-stream')
        self.send_header('Accept-Ranges', 'bytes')
        if content_range:
            self.send_header('Content-Range', content_range)
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(body)


class _Authority:
    def __init__(self, port):
        self.server = 'https://127.0.0.1:' + str(port)
        self.token = 'Bearer first'
        self.allowed = True

    def media_headers(self, profile):
        if profile != 'viewer' or not self.allowed:
            raise Error('profile_changed')
        return {'Authorization': self.token, 'X-Profile-Id': profile}


class Transport(unittest.TestCase):
    def setUp(self):
        self.origin = ThreadingHTTPServer(('127.0.0.1', 0), _Origin)
        self.origin.requests = []
        self.origin.token = 'Bearer first'
        self.origin.started = threading.Event()
        self.origin.release = threading.Event()
        self.origin.finished = threading.Event()
        self.thread = threading.Thread(target=self.origin.serve_forever)
        self.thread.start()
        self.authority = _Authority(self.origin.server_port)
        # Exercise real HTTP framing on both sockets; production always uses
        # verified HTTPS. Target acceptance separately exercises upstream TLS.
        self.connection = patch('silo.relay.http.client.HTTPSConnection', http.client.HTTPConnection)
        self.connection.start()
        self.relay = MediaRelay(self.authority, 'viewer', {
            'video': {'url': '/media?st=signed%2Bgrant', 'headers': {'X-Grant': 'plan'}},
            'redirect': {'url': '/redirect'}, 'stall': {'url': '/stall'},
            'truncated': {'url': '/truncated'}, 'large': {'url': '/large'}})

    def tearDown(self):
        self.origin.release.set()
        self.relay.close()
        self.connection.stop()
        self.origin.shutdown()
        self.origin.server_close()
        self.thread.join()

    def fetch(self, name='video', method='GET', headers=None):
        try:
            response = urlopen(Request(self.relay.url(name), method=method, headers=headers or {}), timeout=3)
        except HTTPError as exc:
            response = exc
        with response:
            return response.status, dict(response.headers), response.read()

    def test_ranges_and_head(self):
        for request, status, data, interval in (
                ('bytes=2-5', 206, b'2345', 'bytes 2-5/20'),
                ('bytes=-4', 206, b'GHIJ', 'bytes 16-19/20'),
                ('bytes=15-', 206, b'FGHIJ', 'bytes 15-19/20'),
                ('bytes=99-', 416, b'', 'bytes */20')):
            with self.subTest(request=request):
                actual, headers, body = self.fetch(headers={'Range': request, 'If-Range': 'validator'})
                self.assertEqual((actual, body, headers['Content-Range']), (status, data, interval))
                self.assertEqual(self.origin.requests[-1][1]['If-Range'], 'validator')
        status, headers, body = self.fetch(method='HEAD')
        self.assertEqual((status, headers['Content-Length'], body), (200, '20', b''))

    def test_new_request_uses_current_authority(self):
        url = self.relay.url('video')
        self.assertEqual(self.fetch()[0], 200)
        self.origin.token = self.authority.token = 'Bearer rotated'
        self.assertEqual(self.fetch(headers={'Authorization': 'Bearer attacker', 'Range': 'bytes=2-5'})[0], 206)
        self.assertEqual(self.relay.url('video'), url)
        path, headers = self.origin.requests[-1]
        self.assertEqual(path, '/media?st=signed%2Bgrant')
        self.assertEqual(headers['Authorization'], 'Bearer rotated')
        self.assertEqual(headers['X-Profile-Id'], 'viewer')
        self.assertEqual(headers['X-Grant'], 'plan')

    def test_revoked_profile_never_reaches_origin(self):
        self.authority.allowed = False
        self.assertEqual(self.fetch()[0], 403)
        self.assertEqual(self.origin.requests, [])

    def test_redirects_and_unknown_paths_are_not_forwarded(self):
        self.assertEqual(self.fetch('redirect')[0], 502)
        self.assertEqual([path for path, _ in self.origin.requests], ['/redirect'])
        with self.assertRaises(HTTPError) as raised:
            urlopen(self.relay.url('video') + '?url=https://other.example.test', timeout=3)
        self.assertEqual(raised.exception.code, 404)
        self.assertEqual(len(self.origin.requests), 1)

    def test_truncated_response_is_not_reported_as_complete(self):
        with self.assertRaises(http.client.IncompleteRead):
            self.fetch('truncated')

    def test_close_interrupts_stalled_read_and_releases_workers(self):
        baseline = set(threading.enumerate())
        def read():
            try:
                self.fetch('stall')
            except (OSError, http.client.HTTPException):
                pass
        reader = threading.Thread(target=read)
        reader.start()
        self.assertTrue(self.origin.started.wait(3))
        started = time.monotonic()
        self.relay.close()
        reader.join(2)
        self.assertFalse(reader.is_alive())
        self.assertLess(time.monotonic() - started, 2)
        self.assertFalse(set(threading.enumerate()) - baseline - {self.origin.worker})
        with self.assertRaises(OSError):
            socket.create_connection(('127.0.0.1', int(self.relay.url('video').split(':')[2].split('/')[0])), timeout=1)

    def test_cross_origin_resources_are_rejected(self):
        with self.assertRaises(Error):
            MediaRelay(self.authority, 'viewer', {'video': {'url': 'https://other.example.test/media'}})

    def test_parallel_ranges_are_independent(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            responses = list(pool.map(lambda _: self.fetch(headers={'Range': 'bytes=2-5'}), range(4)))
        self.assertEqual([(status, body) for status, _, body in responses], [(206, b'2345')] * 4)

    def test_close_interrupts_a_reader_that_stopped_consuming(self):
        response = urlopen(self.relay.url('large'), timeout=3)
        try:
            self.assertTrue(self.origin.started.wait(3))
            self.assertEqual(response.read(1), b'x')
            started = time.monotonic()
            self.relay.close()
            self.assertLess(time.monotonic() - started, 2)
        finally:
            response.close()

    def test_reader_disconnect_releases_upstream_transfer(self):
        response = urlopen(self.relay.url('large'), timeout=3)
        self.assertEqual(response.read(1), b'x')
        response.close()
        self.assertTrue(self.origin.finished.wait(3))
        self.assertEqual(self.fetch()[2], b'0123456789ABCDEFGHIJ')
