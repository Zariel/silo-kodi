"""Require unique source/native correspondence in both directions."""
from .client import Error


class NativeTracks:
    def __init__(self, sources, matches, error_code):
        self.sources = sources
        self.matches = matches
        self.error_code = error_code

    def native_index(self, source_index, streams):
        if type(source_index) is not int or not 0 <= source_index < len(self.sources):
            raise Error(self.error_code)
        candidates = [stream for stream in streams if self.matches(self.sources[source_index], stream)]
        if len(candidates) != 1:
            raise Error(self.error_code)
        native_index = candidates[0].get('index')
        if (type(native_index) is not int or native_index < 0
                or sum(stream.get('index') == native_index for stream in streams) != 1):
            raise Error(self.error_code)
        if [i for i, track in enumerate(self.sources) if self.matches(track, candidates[0])] != [source_index]:
            raise Error(self.error_code)
        return native_index

    def source_index(self, streams, current_index):
        current = [stream for stream in streams if stream.get('index') == current_index]
        if len(current) != 1:
            raise Error(self.error_code)
        candidates = [i for i, track in enumerate(self.sources) if self.matches(track, current[0])]
        if len(candidates) != 1 or self.native_index(candidates[0], streams) != current_index:
            raise Error(self.error_code)
        return candidates[0]
