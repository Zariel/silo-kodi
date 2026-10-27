"""Warm Kodi's own persistent texture cache ahead of navigation."""
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote
import threading

import xbmcvfs


class _ArtworkPreloader:
    def __init__(self):
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix='silo-art')
        self.seen = set()
        self.lock = threading.Lock()
        self.closed = False

    def add(self, urls):
        with self.lock:
            if self.closed:
                return
            for url in urls:
                if url and url not in self.seen:
                    self.seen.add(url)
                    self.pool.submit(self._load, url)

    def _load(self, url):
        try:
            # image:// uses Kodi's existing texture database and deduplicates
            # concurrent GUI loads. Keep the signed URL intact as its cache key.
            handle = xbmcvfs.File('image://' + quote(url, safe='') + '/')
            handle.close()
        except Exception:
            # The GUI can retry normally; preloading must never block browsing.
            pass

    def close(self):
        with self.lock:
            self.closed = True
            self.pool.shutdown(wait=False, cancel_futures=True)
