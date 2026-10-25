import importlib.util
from pathlib import Path
import sys
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch


class ArtworkPreload(unittest.TestCase):
    def test_deduplicates_signed_urls_and_closes_files(self):
        done = threading.Event()
        handle = Mock()
        handle.close.side_effect = done.set
        backend = Mock(return_value=handle)
        path = Path(__file__).resolve().parents[1] / 'plugin.video.silo/resources/lib/silo/artwork.py'
        with patch.dict(sys.modules, {'xbmcvfs': SimpleNamespace(File=backend)}):
            spec = importlib.util.spec_from_file_location('silo_artwork_test', path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        loader = module._ArtworkPreloader()
        try:
            loader.add(['https://art.example/poster?sig=a+b', 'https://art.example/poster?sig=a+b', ''])
            self.assertTrue(done.wait(5))
            backend.assert_called_once_with('image://https%3A%2F%2Fart.example%2Fposter%3Fsig%3Da%2Bb/')
            handle.close.assert_called_once()
        finally:
            loader.close()
        loader.add(['https://art.example/another'])
        self.assertEqual(backend.call_count, 1)
