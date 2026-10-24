"""Map source audio identities to observed native streams without index guessing."""
from .client import Error


_CODEC_FAMILIES = {
    name: family
    for family, names in (
        ('dts', ('dca', 'dts_96_24', 'dts_es', 'dts_express', 'dtshd_hra',
                 'dtshd_ma', 'dtshd_ma_x', 'dtshd_ma_x_imax')),
        ('aac', ('aac_lc', 'he_aac', 'he_aac_v2', 'aac_ssr', 'aac_ltp')),
        ('truehd', ('truehd_atmos',)),
        ('eac3', ('eac3_ddp_atmos',)),
    )
    for name in names
}


class SourceAudio:
    def __init__(self, file_id, tracks, language):
        self.file_id = str(file_id)
        self.tracks = tracks
        self.language = language

    def _matches(self, source, native):
        codec = native.get('codec')
        # Kodi can expose a codec profile where ffprobe supplies its family.
        codec = _CODEC_FAMILIES.get(codec, codec)
        if not source.get('codec') or source['codec'] != codec:
            return False
        if not source.get('channels') or source['channels'] != native.get('channels'):
            return False
        if 'default' in source and 'isdefault' in native and source['default'] != native['isdefault']:
            return False
        source_language = source.get('language') or ''
        native_language = native.get('language') or ''
        if source_language or native_language:
            normalized = self.language(source_language)
            if not normalized or normalized != self.language(native_language):
                return False
        title = source.get('embedded_title')
        if title:
            name = native.get('name') or ''
            if name != title and not name.startswith(title + ' - '):
                return False
        return True

    def identity(self, streams, current_index):
        current = [stream for stream in streams if stream.get('index') == current_index]
        if len(current) != 1:
            raise Error('audio_selection_unavailable')
        candidates = [index for index, track in enumerate(self.tracks) if self._matches(track, current[0])]
        if len(candidates) != 1:
            raise Error('audio_selection_unavailable')
        index = candidates[0]
        identity = {'id': 'file:{}:audio:{}'.format(self.file_id, index), 'index': index}
        # Both directions must be unique; a title prefix can match two streams.
        if self.native_index(identity, streams) != current_index:
            raise Error('audio_selection_unavailable')
        return identity

    def native_index(self, identity, streams):
        index = identity.get('index')
        if (type(index) is not int or not 0 <= index < len(self.tracks)
                or identity.get('id') != 'file:{}:audio:{}'.format(self.file_id, index)):
            raise Error('audio_selection_unavailable')
        candidates = [stream for stream in streams if self._matches(self.tracks[index], stream)]
        if len(candidates) != 1:
            raise Error('audio_selection_unavailable')
        if [i for i, track in enumerate(self.tracks) if self._matches(track, candidates[0])] != [index]:
            raise Error('audio_selection_unavailable')
        return candidates[0]['index']
