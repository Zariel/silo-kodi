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

    return png(width, height, pixels)


def png(width, height, pixels):
    def chunk(kind, data):
        return struct.pack('!I', len(data)) + kind + data + struct.pack('!I', zlib.crc32(kind + data))

    return (b'\x89PNG\r\n\x1a\n'
            + chunk(b'IHDR', struct.pack('!2I5B', width, height, 8, 6, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(pixels, 9)) + chunk(b'IEND', b''))


def detail_fade():
    pixels = bytearray()
    for y in range(108):
        pixels.append(0)
        for x in range(180):
            opacity = max(.8 * (1 - x / 180), min(1, y / 65))
            pixels.extend((16, 16, 20, round(255 * opacity)))
    return png(180, 108, pixels)


def icon(segments, circles=()):
    pixels = bytearray()
    for y in range(128):
        pixels.append(0)
        for x in range(128):
            covered = 0
            for sy in range(4):
                for sx in range(4):
                    px, py = (x + (sx + .5) / 4) * 48 / 128, (y + (sy + .5) / 4) * 48 / 128
                    hit = any(abs(((px-cx)**2 + (py-cy)**2)**.5 - radius) <= 1.5
                              for cx, cy, radius in circles)
                    for ax, ay, bx, by in segments:
                        dx, dy = bx-ax, by-ay
                        t = max(0, min(1, ((px-ax)*dx + (py-ay)*dy) / (dx*dx+dy*dy)))
                        hit |= (px-ax-t*dx)**2 + (py-ay-t*dy)**2 <= 2.25
                    covered += hit
            pixels.extend((255, 255, 255, round(255 * covered / 16)))
    return png(128, 128, pixels)


def navigation_icons():
    shapes = {
        'search': ([(30,30,41,41)], [(21,21,13)]),
        'home': ([(7,22,24,7),(24,7,41,22),(12,19,12,40),(12,40,36,40),
                  (36,40,36,19),(20,40,20,28),(20,28,28,28),(28,28,28,40)], []),
        'movies': ([(8,10,40,10),(40,10,40,38),(40,38,8,38),(8,38,8,10),
                    (8,18,40,18),(16,10,12,18),(27,10,23,18),(38,10,34,18)], []),
        'tv': ([(7,14,41,14),(41,14,41,38),(41,38,7,38),(7,38,7,14),
                (17,6,24,14),(24,14,31,6),(18,43,30,43)], []),
        'account': ([(9,40,9,35),(9,35,16,28),(16,28,32,28),(32,28,39,35),(39,35,39,40)],
                    [(24,15,8)]),
        'close': ([(12,12,36,36),(12,36,36,12)], []),
    }
    for name, (segments, circles) in shapes.items():
        (OUTPUT / ('nav-' + name + '.png')).write_bytes(icon(segments, circles))


if __name__ == '__main__':
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / 'details-fade.png').write_bytes(detail_fade())
    navigation_icons()
    (OUTPUT / 'rounded.png').write_bytes(rounded(64, 64, 16))
    for width, height in ((150, 225), (185, 250), (215, 310), (250, 140), (280, 420)):
        (OUTPUT / f'card-{width}x{height}.png').write_bytes(rounded(width, height, 12))
