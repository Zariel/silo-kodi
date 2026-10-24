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
from urllib.parse import urljoin
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
        if self.path == '/hls/master.m3u8':
            body = self.server.playlist
            if self.server.delay_playlist:
                self.server.started.set()
                self.server.release.wait(10)
            self.send_response(200)
            self.send_header('Content-Length', str(len(body) + self.server.missing_playlist_bytes))
            self.send_header('ETag', 'upstream-representation')
            self.end_headers()
            if self.command != 'HEAD':
                self.wfile.write(body)
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
        self.origin.playlist = b'#EXTM3U\n#EXT-X-PLAYLIST-TYPE:VOD\n#EXTINF:6,\nsegment/0.ts?grant=a%2Bb\n#EXTINF:6,\nsegment/1.ts\n#EXT-X-ENDLIST\n'
        self.origin.delay_playlist = False
        self.origin.missing_playlist_bytes = 0
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

    def test_hls_references_use_fresh_authority_and_preserve_queries(self):
        self.relay.update({'video': {'url': '/hls/master.m3u8', 'protocol': 'hls'}})
        status, headers, body = self.fetch()
        self.assertEqual(status, 200)
        self.assertEqual(int(headers['Content-Length']), len(body))
        self.assertNotIn('ETag', headers)
        references = [line for line in body.decode().splitlines() if line and not line.startswith('#')]
        self.assertEqual(len(references), 2)
        self.assertNotIn(b'grant=', body)
        self.origin.token = self.authority.token = 'Bearer rotated'
        with urlopen(urljoin(self.relay.url('video'), references[0]), timeout=3) as response:
            self.assertEqual(response.read(), b'0123456789ABCDEFGHIJ')
        path, forwarded = self.origin.requests[-1]
        self.assertEqual(path, '/hls/segment/0.ts?grant=a%2Bb')
        self.assertEqual(forwarded['Authorization'], 'Bearer rotated')
        status, head, empty = self.fetch(method='HEAD')
        self.assertEqual((status, head['Content-Length'], empty), (200, str(len(body)), b''))
        retired = urljoin(self.relay.url('video'), references[0])
        self.relay.update({'video': {'url': '/media'}})
        with self.assertRaises(HTTPError) as raised:
            urlopen(retired, timeout=3)
        with raised.exception as response:
            self.assertEqual(response.code, 404)

    def test_hls_rejects_unsupported_or_incomplete_playlists(self):
        self.relay.update({'video': {'url': '/hls/master.m3u8', 'protocol': 'hls'}})
        playlists = [
            b'#EXTM3U\n#EXTINF:6,\nhttps://other.example.test/a.ts\n#EXT-X-ENDLIST\n',
            b'#EXTM3U\n#EXT-X-KEY:METHOD=AES-128,URI="key"\n0.ts\n#EXT-X-ENDLIST\n',
            b'#EXTM3U\n#EXTINF:6,\nchild.m3u8\n#EXT-X-ENDLIST\n',
            b'#EXTM3U\n#EXTINF:6,\n0.ts\n',
            b'#EXTM3U\n#EXT-X-MAP:URI="init.mp4"\n0.ts\n#EXT-X-ENDLIST\n',
            b'#EXTM3U\n#EXTINF:6,\n\xff.ts\n#EXT-X-ENDLIST\n',
            b'#EXTM3U\n' + b'#comment\n' * 150000 + b'#EXT-X-ENDLIST\n',
            b'#EXTM3U\n' + b'#EXTINF:6,\n0.ts\n' * 10001 + b'#EXT-X-ENDLIST\n',
        ]
        for playlist in playlists:
            with self.subTest(prefix=playlist[:70]):
                self.origin.playlist = playlist
                self.assertEqual(self.fetch()[0], 502)

    def test_truncated_hls_is_rejected_even_when_endlist_arrived(self):
        self.relay.update({'video': {'url': '/hls/master.m3u8', 'protocol': 'hls'}})
        self.origin.missing_playlist_bytes = 10
        self.assertEqual(self.fetch()[0], 502)

    def test_retired_hls_response_cannot_publish_segment_grants(self):
        self.relay.update({'video': {'url': '/hls/master.m3u8', 'protocol': 'hls'}})
        self.origin.delay_playlist = True
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(self.fetch)
            self.assertTrue(self.origin.started.wait(3))
            self.relay.update({'video': {'url': '/media'}})
            self.origin.release.set()
            self.assertEqual(pending.result(timeout=3)[0], 502)
        self.assertEqual(self.fetch()[2], b'0123456789ABCDEFGHIJ')

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

    def test_replan_replaces_grants_without_changing_video_url(self):
        video = self.relay.url('video')
        retired = self.relay.url('redirect')
        self.relay.update({'video': {'url': '/media?st=replanned', 'headers': {'X-Grant': 'replacement'}},
                           'subtitle-2.vtt': {'url': '/subtitles/2'}})
        self.assertEqual(self.relay.url('video'), video)
        self.assertEqual(self.fetch(headers={'Range': 'bytes=2-5'})[2], b'2345')
        path, headers = self.origin.requests[-1]
        self.assertEqual(path, '/media?st=replanned')
        self.assertEqual(headers['X-Grant'], 'replacement')
        self.assertEqual(self.fetch('subtitle-2.vtt')[0], 200)
        with self.assertRaises(HTTPError) as raised:
            urlopen(retired, timeout=3)
        with raised.exception as response:
            self.assertEqual(response.code, 404)

    def test_invalid_replan_preserves_previous_resources(self):
        with self.assertRaises(Error):
            self.relay.update({'video': {'url': '/replacement'},
                               'subtitle.vtt': {'url': 'https://other.example.test/subtitle'}})
        self.assertEqual(self.fetch()[0], 200)
        self.assertEqual(self.origin.requests[-1][0], '/media?st=signed%2Bgrant')

    def test_revoked_profile_never_reaches_origin(self):
        self.authority.allowed = False
        self.assertEqual(self.fetch()[0], 403)
        self.assertEqual(self.origin.requests, [])

    def test_redirects_and_unknown_paths_are_not_forwarded(self):
        self.assertEqual(self.fetch('redirect')[0], 502)
        self.assertEqual([path for path, _ in self.origin.requests], ['/redirect'])
        with self.assertRaises(HTTPError) as raised:
            urlopen(self.relay.url('video') + '?url=https://other.example.test', timeout=3)
        with raised.exception as response:
            self.assertEqual(response.code, 404)
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
