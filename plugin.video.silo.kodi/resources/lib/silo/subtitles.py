"""Resolve original embedded subtitles without mixing index namespaces."""
from .client import Error
from .tracks import NativeTracks


class SourceSubtitles:
    def __init__(self, tracks, language):
        self.tracks = [track for track in tracks if not track.get('external')]
        self.language = language
        self._native = NativeTracks(self.tracks, self._matches, 'subtitle_selection_unavailable')

    def _matches(self, source, native):
        source_language = source.get('language') or ''
        native_language = native.get('language') or ''
        if source_language or native_language:
            normalized = self.language(source_language)
            if not normalized or normalized != self.language(native_language):
                return False
        if (source.get('embedded_title') or '') != (native.get('name') or ''):
            return False
        return all(bool(source.get(left)) == bool(native.get(right)) for left, right in (
            ('default', 'isdefault'), ('forced', 'isforced'), ('hearing_impaired', 'isimpaired')))

    def native_index(self, stream_index, streams):
        candidates = [i for i, track in enumerate(self.tracks) if track.get('index') == stream_index]
        if type(stream_index) is not int or stream_index < 0 or len(candidates) != 1:
            raise Error('subtitle_selection_unavailable')
        return self._native.native_index(candidates[0], streams)

    def check_selection(self, track, streams):
        # The menu's combined ordinal is not a source stream index. Use its
        # metadata only for preflight; the committed plan supplies the index.
        candidates = [source for source in self.tracks
                      if all(source.get(key) == track.get(key) for key in
                             ('codec', 'language', 'forced', 'default', 'hearing_impaired'))
                      and track.get('label') in (source.get('embedded_title'), source.get('title'), source.get('language'))]
        if track.get('source') != 'embedded' or len(candidates) != 1:
            raise Error('subtitle_selection_unavailable')
        self.native_index(candidates[0]['index'], streams)
