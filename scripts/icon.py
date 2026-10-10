"""Render the fan icon used by the repository and the plugin package."""

import math
import pathlib
import struct
import zlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
SIZE = 256
CENTER = (SIZE - 1) / 2
RADIUS = 116
HUB = 30
BLADES = 5
SUPERSAMPLE = 3

# Palette matches the fan panel: dark slate background, light blue blades.
BACKGROUND = (0x18, 0x23, 0x2D)
BLADE = (0x8F, 0xD0, 0xFF)
BLADE_EDGE = (0x4A, 0x86, 0xB8)
HUB_COLOR = (0xE8, 0xF2, 0xFA)


def blade_angle(x, y):
    """Return the blade coverage at a point, 0..1, before supersampling."""
    dx, dy = x - CENTER, y - CENTER
    distance = math.hypot(dx, dy)
    if distance > RADIUS or distance < HUB * 0.55:
        return 0.0
    angle = (math.atan2(dy, dx) / (2 * math.pi)) % 1
    # Each blade spans 40 degrees and sweeps outward like a real impeller.
    span = 0.11
    position = (angle * BLADES + (distance - HUB) / RADIUS * 0.55) % 1
    if position > span and position < 1 - span:
        return 0.0
    # Fade the very tip so the silhouette stays round.
    if distance > RADIUS - 1:
        return 0.0
    inner = HUB * 0.55
    if distance < inner + 3:
        return (distance - inner) / 3
    return 1.0


def sample(x, y):
    dx, dy = x - CENTER, y - CENTER
    distance = math.hypot(dx, dy)
    if distance <= HUB * 0.55:
        return HUB_COLOR
    coverage = blade_angle(x, y)
    if coverage <= 0:
        return BACKGROUND
    color = tuple(a + (b - a) * 0.65 for a, b in zip(BACKGROUND, BLADE))
    if distance > RADIUS * 0.86:
        color = tuple(a + (b - a) * 0.45 for a, b in zip(color, BLADE_EDGE))
    return color


rows = []
step = 1.0 / SUPERSAMPLE
for y in range(SIZE):
    row = bytearray()
    for x in range(SIZE):
        total = [0.0, 0.0, 0.0]
        for sy in range(SUPERSAMPLE):
            for sx in range(SUPERSAMPLE):
                pixel = sample(x + (sx + 0.5) * step, y + (sy + 0.5) * step)
                for index in range(3):
                    total[index] += pixel[index]
        count = SUPERSAMPLE * SUPERSAMPLE
        row.extend(round(value / count) for value in total)
        # Fully opaque: the launcher shows this icon on its own plate.
        row.append(255)
    rows.append(b'\0' + row)


def chunk(kind, data):
    return (struct.pack('>I', len(data)) + kind + data
            + struct.pack('>I', zlib.crc32(kind + data) & 0xFFFFFFFF))


image = (b'\x89PNG\r\n\x1a\n'
         + chunk(b'IHDR', struct.pack('>IIBBBBB', SIZE, SIZE, 8, 6, 0, 0, 0))
         + chunk(b'IDAT', zlib.compress(b''.join(rows), 9))
         + chunk(b'IEND', b''))
(ROOT / 'icon.png').write_bytes(image)
print(ROOT / 'icon.png')
