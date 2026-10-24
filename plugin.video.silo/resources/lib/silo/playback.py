"""One Silo playback attempt, with ordered samples and stable mutation identities."""
import time
import uuid
from urllib.parse import quote, urlencode, urljoin, urlsplit

from .client import Error


def capabilities():
    # Kodi owns original-file presentation. Declared decode eligibility does not
    # attest native HDR output, passthrough, or Dolby Vision enhancement layers.
    containers = ['mkv', 'mp4', 'mov', 'avi', 'mpegts']
    video = ['h264', 'hevc', 'mpeg2video']
    audio = ['aac', 'ac3', 'eac3', 'dts', 'truehd', 'flac', 'mp3', 'pcm_s16le', 'pcm_s24le']
    decoder = {'video_evidence': 'declared', 'audio_evidence': 'declared',
               'codecs_video': video, 'codecs_video_hardware': [], 'codecs_audio': audio, 'containers': containers,
               'max_resolution': '2160p', 'hdr': False}
    context = {'protocol_version': 3, 'form_factor': 'tv', 'app_version': '0.3.0',
               'device': {'platform': 'linux', 'model': 'Kodi'},
               'output': {'output_context_id': 'kodi-native'},
               'deliveries': {'original_http': {
                   'enabled': True, 'supported_on_device': True, 'containers': containers,
                   'video_codecs': video, 'audio_decode_codecs': audio,
                   'audio_passthrough_codecs': [], 'auth_header_refresh': False,
                   'features': [], 'validated_claims': ['client_managed_dynamic_range_v1'], 'transformations': [],
                   'subtitles': {'embedded_text': True, 'sidecar_text': True,
                                 'ass_styling': False, 'embedded_bitmap': False,
                                 'sidecar_bitmap': False, 'font_attachments': False}}}}
    context['deliveries']['hls'] = dict(context['deliveries']['original_http'],
                                      containers=['hls'], video_codecs=['h264'],
                                      audio_decode_codecs=['aac'], max_channels=2,
                                      validated_claims=[])
    return decoder, context


def media_url(server, stream, authority=None):
    try:
        url = urljoin(server.rstrip('/') + '/', stream['url'])
        parts = urlsplit(url)
        if (parts.scheme != 'https' or not parts.hostname or parts.username or parts.password
                or any(c in url for c in ('|', '\r', '\n'))):
            raise ValueError()
        # No cross-origin credential forwarding. Additional media origins can be
        # negotiated later; the initial client accepts only same-origin grants.
        if parts.netloc != urlsplit(server).netloc:
            raise ValueError()
        headers = dict(stream.get('headers') or {})
        headers.update(authority or {})
        if any(not isinstance(k, str) or not isinstance(v, str) or '\n' in k + v or '\r' in k + v
               for k, v in headers.items()):
            raise ValueError()
        return url + ('|' + urlencode(headers) if headers else '')
    except (KeyError, TypeError, ValueError, AttributeError):
        raise Error('unsupported_playback') from None


def subtitle_url(server, decision, authority):
    if decision.get('mode') == 'off':
        return None
    artifact = decision.get('artifact') or {}
    # Original media and its sidecar both use the source clock. Other timelines
    # need an explicit mapping rather than silently displaying shifted cues.
    if (decision.get('mode') not in ('render', 'convert')
            or artifact.get('format') not in ('srt', 'vtt', 'webvtt')
            or artifact.get('timing_origin_seconds') != 0
            or decision.get('embedded') or decision.get('hls_rendition')):
        raise Error('unsupported_playback')
    return media_url(server, artifact, authority)


class Attempt:
    def __init__(self, session, profile_id, file_id, start_position=None, subtitle_track_id=None):
        self.session = session
        self.profile_id = profile_id
        self.session_id = None
        self.sequence = 0
        self.last_sample = None
        self.stop_body = None
        self.plan = None
        self.plan_attempt_id = None
        self.subtitle_url = None
        self.ended = False
        capability = self._request('GET', '/playback/capabilities')
        if not capability.get('allowed') or 3 not in capability.get('protocol_versions', []):
            raise Error('unsupported_playback')
        self.installation = capability['installation_id']
        decoder, context = capabilities()
        self.body = {'installation_id': self.installation, 'protocol_version': 3,
                     'client_features': ['playback_plan_v3'], 'file_id': str(file_id),
                     'profile_id': profile_id, 'playback_attempt_id': str(uuid.uuid4()),
                     'quality_preference': 'auto', 'subtitle_fidelity_preference': 'compatible',
                     'client_capabilities': decoder, 'client_playback_context': context}
        if 'fixed_media_file_v1' in capability.get('features', []):
            self.body['allow_alternate_versions'] = False
        if 'header_authenticated_media_v1' in capability.get('features', []):
            self.body['client_features'].append('header_authenticated_media_v1')
        if start_position is not None:
            self.body['start_position'] = start_position
        if subtitle_track_id is not None:
            self.body['subtitle_track_id'] = subtitle_track_id

    def _request(self, method, path, body=None):
        return self.session.request(method, path, body, expected_profile=self.profile_id)

    def _mutation(self, method, path, body):
        # An uncertain response must reuse both identity and payload, never mint
        # another attempt or sample merely because transport delivery failed.
        for retry in range(3):
            try:
                return self._request(method, path, body)
            except Error as exc:
                if retry == 2 or not (exc.code == 'connection_failed' or exc.status >= 500):
                    raise
                time.sleep(1 + retry)

    def start(self):
        result = self._mutation('POST', '/playback/start', self.body)
        self.session_id = result.get('session_id')
        return self._accept(result)

    def select_subtitle(self, track_id, position):
        if self.ended or not self.plan or not self.session_id:
            raise Error('unsupported_playback')
        inventory = self.plan.get('subtitle', {}).get('inventory', [])
        if track_id is not None and not any(track.get('track_id') == track_id for track in inventory):
            raise Error('unsupported_playback')
        tracks = dict(self.plan.get('selected_tracks') or {})
        tracks.pop('subtitle', None)
        if track_id is not None:
            tracks['subtitle'] = {'id': track_id}
        return self._replan('track_change', tracks, self.body['quality_preference'], position)

    def select_quality(self, quality, position):
        if self.ended or not self.plan or not self.session_id:
            raise Error('unsupported_playback')
        if quality != 'auto' and not any(
                entry.get('label') == quality for entry in self.plan.get('available_qualities', [])):
            raise Error('unsupported_playback')
        return self._replan('quality_change', dict(self.plan.get('selected_tracks') or {}), quality, position)

    def _replan(self, operation, tracks, quality, position):
        body = {key: self.body[key] for key in (
            'installation_id', 'protocol_version', 'playback_attempt_id', 'quality_preference',
            'client_features', 'client_capabilities', 'client_playback_context')}
        # Intent changes keep the previous recipe eligible. Omitting subtitle
        # means Off only for track_change; quality_change preserves the tracks.
        body.update(operation=operation, quality_preference=quality, replan_request_id=str(uuid.uuid4()),
                    failed_plan_id=self.plan['plan_id'], plan_attempt_id=self.plan_attempt_id,
                    plan_attempt_key=self.plan['plan_attempt_key'], attempted_plan_keys=[],
                    attempt_count=1, position_seconds=max(0, position), selected_tracks=tracks)
        result = self._mutation('POST', '/playback/' + quote(self.session_id, safe='') + '/replan', body)
        # The server may have committed before local delivery validation fails.
        self.body['quality_preference'] = quality
        return self._accept(result)

    def _accept(self, result):
        self.plan = result.get('playback_plan')
        self.plan_attempt_id = str(uuid.uuid4())
        self.subtitle_url = None
        if (result.get('outcome') != 'playable' or not self.session_id or not self.plan
                or result.get('session_id') != self.session_id):
            raise Error('unsupported_playback')
        delivery = self.plan.get('delivery')
        timeline = self.plan.get('timeline', {})
        if (delivery not in ('original_http', 'server_transcode_hls')
                or self.plan.get('stream', {}).get('header_refresh') not in ('none', None)
                or not timeline.get('can_seek_anywhere')):
            raise Error('unsupported_playback')
        if delivery == 'server_transcode_hls' and (
                self.plan.get('stream', {}).get('protocol') != 'hls'
                or timeline.get('timeline_offset_seconds') != 0):
            raise Error('unsupported_playback')
        authority = self.session.media_headers(self.profile_id)
        self.subtitle_url = subtitle_url(self.session.server, self.plan.get('subtitle', {'mode': 'off'}), authority)
        return media_url(self.session.server, self.plan['stream'], authority)

    def sample(self, position, paused):
        if self.ended:
            return
        self.sequence += 1
        self.last_sample = {'sequence': self.sequence, 'position': max(0, position), 'is_paused': bool(paused)}
        try:
            self._mutation('POST', '/playback/' + quote(self.session_id, safe='') + '/progress',
                           dict(self.last_sample, installation_id=self.installation))
        except Error as exc:
            if exc.status in (404, 410):
                self.ended = True
            raise

    def stop(self, position=None, paused=False):
        if not self.session_id or self.ended:
            return
        if self.stop_body is None:
            self.stop_body = {'installation_id': self.installation, 'stop_id': str(uuid.uuid4())}
            if position is not None:
                self.sequence += 1
                self.stop_body.update(sequence=self.sequence, position=max(0, position), is_paused=bool(paused))
            elif self.last_sample:
                self.stop_body.update(self.last_sample)
        try:
            result = self._mutation('DELETE', '/playback/' + quote(self.session_id, safe=''), self.stop_body)
            self.ended = True
            return result
        except Error as exc:
            if exc.status in (404, 410):
                self.ended = True
                return
            raise
