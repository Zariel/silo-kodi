"""Generate white alpha masks for Kodi's rounded card and focus textures."""
from pathlib import Path
import struct
import zlib


OUTPUT = Path(__file__).resolve().parents[1] / 'plugin.video.silo/resources/skins/Default/media'


def rounded(width, height, radius):
    pixels = bytearray()
    for y in range(height):
        pixels.append(0)  # PNG scanline filter: none.
        for x in range(width):
            covered = 0
            for sy in range(4):
                for sx in range(4):
                    px, py = x + (sx + .5) / 4, y + (sy + .5) / 4
                    dx = max(radius - px, 0, px - (width - radius))
                    dy = max(radius - py, 0, py - (height - radius))
                    covered += dx * dx + dy * dy <= radius * radius
            pixels.extend((255, 255, 255, round(255 * covered / 16)))

    def chunk(kind, data):
        return struct.pack('!I', len(data)) + kind + data + struct.pack('!I', zlib.crc32(kind + data))

    return (b'\x89PNG\r\n\x1a\n'
            + chunk(b'IHDR', struct.pack('!2I5B', width, height, 8, 6, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(pixels, 9)) + chunk(b'IEND', b''))


if __name__ == '__main__':
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / 'rounded.png').write_bytes(rounded(64, 64, 16))
    for width, height in ((185, 250), (215, 310), (250, 140), (280, 420)):
        (OUTPUT / f'card-{width}x{height}.png').write_bytes(rounded(width, height, 12))
