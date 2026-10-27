"""Validate source-time intro markers supplied for the selected file."""
import math


def intro_range(marker):
    if not isinstance(marker, dict):
        return None
    start, end = marker.get('start'), marker.get('end')
    if (type(start) in (int, float) and type(end) in (int, float)
            and math.isfinite(start) and math.isfinite(end) and 0 <= start < end):
        return start, end
    return None


def intro_at(segment, position, duration):
    return segment if segment and 0 <= segment[0] <= position < segment[1] < duration else None
