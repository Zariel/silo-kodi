"""Render only the public verification URL, never the polling credential."""
import os
from pathlib import Path
import tempfile

import segno


def write_qr(pairing, path):
    path = Path(path)
    fd, temporary = tempfile.mkstemp(prefix='.qr-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as output:
            segno.make_qr(pairing['verification_uri_complete'], error='m').save(output, kind='png', scale=8, border=4)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
