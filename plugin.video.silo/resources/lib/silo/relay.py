"""Attempt-scoped HTTP transport with fresh authority on every upstream read."""
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import secrets
import socket
import threading
from urllib.parse import urlsplit

from .client import Error
from .playback import media_url


class _Server(ThreadingHTTPServer):
    daemon_threads = False
    block_on_close = True

    def __init__(self, owner):
        self.owner = owner
        self.slots = threading.BoundedSemaphore(8)
        super().__init__(('127.0.0.1', 0), _Handler)

    def process_request(self, request, address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, address)
        except Exception:
            self.slots.release()
            raise

    def process_request_thread(self, request, address):
        try:
            super().process_request_thread(request, address)
        finally:
            self.slots.release()

    def handle_error(self, request, address):
        # HTTP diagnostics must not print local grants or upstream credentials.
        pass


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def setup(self):
        super().setup()
        self.connection.settimeout(10)
        self.server.owner._register(self.connection)

    def finish(self):
        try:
            super().finish()
        finally:
            self.server.owner._discard(self.connection)

    def do_HEAD(self):
        self._forward()

    def do_GET(self):
        self._forward()

    def _empty(self, status, content_range=None):
        self.send_response(status)
        self.send_header('Content-Length', '0')
        if content_range:
            self.send_header('Content-Range', content_range)
        self.end_headers()

    def _forward(self):
        relay = self.server.owner
        resource = relay._resources.get(self.path)
        if resource is None:
            self._empty(404)
            return
        # Kodi may stop reading while paused. Explicit socket shutdown, rather
        # than a write timeout, cancels that backpressure when playback ends.
        self.connection.settimeout(None)
        parts, plan_headers = resource
        conn = None
        upstream_socket = None
        sent = False
        try:
            if relay._closed:
                return
            authority = relay._session.media_headers(relay._profile)
            if relay._closed:
                return
            reserved = {k.lower() for k in authority} | {
                'host', 'connection', 'content-length', 'transfer-encoding',
                'accept-encoding', 'range', 'if-range'}
            headers = {k: v for k, v in plan_headers.items() if k.lower() not in reserved}
            headers.update(authority)
            headers['Accept-Encoding'] = 'identity'
            for name in ('Range', 'If-Range'):
                if name in self.headers:
                    headers[name] = self.headers[name]
            conn = http.client.HTTPSConnection(parts.hostname, parts.port, timeout=10)
            conn.connect()
            # Keep the connected socket even if HTTPResponse takes ownership
            # of it for a Connection: close response. Shutdown interrupts reads.
            upstream_socket = conn.sock
            relay._register(upstream_socket)
            conn.request(self.command, parts.path + ('?' + parts.query if parts.query else ''), headers=headers)
            with conn.getresponse() as response:
                if response.status not in (200, 206):
                    status = response.status if response.status in (401, 403, 404, 410, 416, 429, 503) else 502
                    self._empty(status, response.getheader('Content-Range') if status == 416 else None)
                    return
                if response.getheader('Content-Encoding', 'identity') != 'identity':
                    self._empty(502)
                    return
                self.send_response(response.status)
                for name in ('Content-Type', 'Content-Length', 'Content-Range', 'Accept-Ranges', 'ETag', 'Last-Modified'):
                    value = response.getheader(name)
                    if value is not None:
                        self.send_header(name, value)
                self.end_headers()
                sent = True
                if self.command == 'GET':
                    while not relay._closed:
                        block = response.read(256 * 1024)
                        if not block:
                            break
                        self.wfile.write(block)
        except Error as exc:
            if not sent:
                self._empty(403 if exc.code in ('profile_changed', 'sign_in_required', 'profile_required') else 502)
        except (OSError, http.client.HTTPException):
            # Once headers or bytes are sent, close the truncated response;
            # retrying here would duplicate bytes in Kodi's current read.
            if not sent and not relay._closed:
                self._empty(502)
        finally:
            if conn:
                conn.close()
            if upstream_socket:
                upstream_socket.close()
                relay._discard(upstream_socket)


class MediaRelay:
    def __init__(self, session, profile_id, resources):
        self._session = session
        self._profile = profile_id
        self._lock = threading.Lock()
        self._sockets = set()
        self._closed = False
        self._prefix = '/' + secrets.token_urlsafe(24) + '/'
        self.update(resources)
        self._server = _Server(self)
        self._thread = threading.Thread(target=self._server.serve_forever, kwargs={'poll_interval': .1})
        try:
            self._thread.start()
        except BaseException:
            self._server.server_close()
            raise

    def update(self, resources):
        updated = {}
        for name, stream in resources.items():
            parts = urlsplit(media_url(self._session.server, stream).split('|', 1)[0])
            if not name or parts.fragment or any(c in name for c in '/?#'):
                raise Error('unsupported_playback')
            updated[self._prefix + name] = (parts, dict(stream.get('headers') or {}))
        # Publish a fully validated plan in one assignment. Transfers already
        # reading keep their resource; later requests use the replacement grant.
        with self._lock:
            if self._closed:
                raise Error('unsupported_playback')
            self._resources = updated

    def url(self, name):
        path = self._prefix + name
        if path not in self._resources:
            raise KeyError(name)
        return 'http://127.0.0.1:{}{}'.format(self._server.server_port, path)

    def _register(self, connection):
        with self._lock:
            if self._closed:
                connection.close()
                raise ConnectionAbortedError()
            self._sockets.add(connection)

    def _discard(self, connection):
        with self._lock:
            self._sockets.discard(connection)

    def close(self):
        with self._lock:
            if self._closed:
                return
            self._closed = True
            for connection in self._sockets:
                try:
                    connection.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
        self._server.shutdown()
        self._server.server_close()
        self._thread.join()
