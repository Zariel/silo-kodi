import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch


class Controls(unittest.TestCase):
    def setUp(self):
        self.properties = {}
        window = SimpleNamespace(getProperty=lambda k: self.properties.get(k, ''),
                                 setProperty=self.properties.__setitem__,
                                 clearProperty=lambda k: self.properties.pop(k, None))
        self.dialog = Mock()
        modules = {'xbmcgui': SimpleNamespace(Window=lambda _: window, Dialog=lambda: self.dialog),
                   'xbmc': SimpleNamespace(Player=lambda: SimpleNamespace(isPlaying=lambda: True, isPlayingVideo=lambda: True), executebuiltin=Mock())}
        spec = importlib.util.spec_from_file_location('controls_test', Path(__file__).resolve().parents[1] /
                                                     'plugin.video.silo/resources/lib/silo/controls.py')
        self.module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, modules):
            spec.loader.exec_module(self.module)
        self.owner = self.module.PlaybackControls()
        self.plan = {'subtitle': {'mode': 'off', 'inventory': [
            {'track_id': 'opaque-id', 'label': 'English', 'delivery': 'sidecar', 'url': 'private'},
            {'track_id': 'bitmap', 'label': 'French', 'delivery': 'embedded'}]}}
        self.owner.publish(self.plan)
        self.dialog.contextmenu.return_value = 0

    def test_menu_transmits_exact_identity_and_off(self):
        for choice, expected in ((1, 'opaque-id'), (0, None)):
            with self.subTest(choice=choice):
                self.dialog.select.return_value = choice
                self.module.playback_options()
                request = self.owner.take()
                self.assertEqual(request['subtitle'], expected)
                self.assertIsNone(self.owner.take())
                self.owner.publish(self.plan)
        self.assertNotIn('private', json.dumps(self.properties))

    def test_pgs_sidecar_is_not_offered_without_native_support(self):
        plan = {'subtitle': {'mode': 'off', 'inventory': [{'track_id': 'pgs', 'label': 'English',
                'source': 'embedded', 'codec': 'hdmv_pgs_subtitle', 'delivery': 'sidecar'}]}}
        self.dialog.select.return_value = 1
        self.owner.publish(plan)
        self.module.playback_options()
        self.assertIsNone(self.owner.take())
        self.owner.publish(plan, native_subtitles=True)
        self.module.playback_options()
        self.assertEqual(self.owner.take()['subtitle'], 'pgs')

    def test_quality_menu_keeps_auto_distinct_from_delivered_rung(self):
        self.plan['available_qualities'] = [{'label': '360p'}, {'label': '720p-high'}]
        self.plan['active_quality'] = '360p'
        self.owner.publish(self.plan, 'auto')
        self.dialog.contextmenu.return_value = 1
        self.dialog.select.return_value = 2
        self.module.playback_options()
        self.dialog.select.assert_called_with('Quality', ['Auto', '360p', '720p-high'], preselect=0)
        self.assertEqual(self.owner.take()['quality'], '720p-high')

        self.owner.publish(self.plan, '720p-high')
        self.dialog.select.return_value = 0
        self.module.playback_options()
        self.assertEqual(self.owner.take()['quality'], 'auto')

    def test_menu_opened_before_replacement_cannot_control_new_playback(self):
        def select(*args, **kwargs):
            self.owner.publish(self.plan)
            return 1
        self.dialog.select.side_effect = select
        self.module.playback_options()
        self.assertIsNone(self.owner.take())
        self.dialog.notification.assert_called_once()

    def test_queued_choice_cannot_cross_plan_revision(self):
        self.dialog.select.return_value = 1
        self.module.playback_options()
        self.owner.publish(self.plan)
        self.assertIsNone(self.owner.take())

    def test_unsupported_choice_does_not_replan(self):
        self.dialog.select.return_value = 2
        self.module.playback_options()
        self.assertIsNone(self.owner.take())
        self.dialog.notification.assert_called_once()

    def test_cleanup_removes_pending_choices_and_metadata(self):
        self.dialog.select.return_value = 1
        self.module.playback_options()
        self.owner.close()
        self.assertEqual(self.properties, {})

    def test_completion_is_profile_bound_and_consumed_once(self):
        owner = self.module.PlaybackControls('viewer', 'episode')
        owner.complete()
        self.assertIsNone(self.module.take_completed('other'))
        self.assertEqual(self.module.take_completed('viewer'), 'episode')
        self.assertIsNone(self.module.take_completed('viewer'))

    def test_completion_expires_and_new_playback_clears_it(self):
        owner = self.module.PlaybackControls('viewer', 'episode')
        with patch.object(self.module.time, 'time', return_value=100):
            owner.complete()
        with patch.object(self.module.time, 'time', return_value=161):
            self.assertIsNone(self.module.take_completed('viewer'))
        owner.complete()
        self.module.PlaybackControls('viewer', 'another')
        self.assertIsNone(self.module.take_completed('viewer'))

    def test_playback_navigation_is_bound_to_profile_and_lifetime(self):
        self.owner = self.module.PlaybackControls('viewer', 'movie')
        self.owner.publish(self.plan)
        self.assertEqual(self.module.active_playback('viewer')['content_id'], 'movie')
        self.assertIsNone(self.module.active_playback('other'))
        self.owner.close()
        self.assertIsNone(self.module.active_playback('viewer'))
