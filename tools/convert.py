"""convert.py - turn the original PNG art into NES tile data.

Runs on the development machine at build time, never on the NES. For now it
converts one image (the grass square from terrain.png) and prints the
result; later chunks extend it to all the art and write a file the build
links into the ROM.

The steps for one image:
  1. Shrink it back to its true size (one pixel per block; see measure_scale.py).
  2. Replace each colour with the closest colour the NES can show.
  3. Number the colours 0-3: their slots in a 4-colour NES palette.
  4. Cut the image into 8x8 tiles and encode each as 16 bytes, in the same
     two-plane format as the hand-made tiles in src/main.c.
"""

from collections import Counter
from pathlib import Path

from PIL import Image

# --- The NES colours ---------------------------------------------------------
#
# The NES doesn't take RGB values. Its graphics chip generates a TV signal
# directly from 64 numbered colours ($00-$3F), so a game picks colours by
# number. There's no single true RGB value for each: the result depended on
# the TV, and every emulator uses a slightly different table. This is a
# common one.
#
# Rows go from dark ($0x) to light ($3x); columns go round the colour wheel
# (grey, blues, purples, reds, oranges, greens, cyans), then blacks.

NES_RGB = [
    0x7C7C7C, 0x0000FC, 0x0000BC, 0x4428BC, 0x940084, 0xA80020, 0xA81000, 0x881400,
    0x503000, 0x007800, 0x006800, 0x005800, 0x004058, 0x000000, 0x000000, 0x000000,
    0xBCBCBC, 0x0078F8, 0x0058F8, 0x6844FC, 0xD800CC, 0xE40058, 0xF83800, 0xE45C10,
    0xAC7C00, 0x00B800, 0x00A800, 0x00A844, 0x008888, 0x000000, 0x000000, 0x000000,
    0xF8F8F8, 0x3CBCFC, 0x6888FC, 0x9878F8, 0xF878F8, 0xF85898, 0xF87858, 0xFCA044,
    0xF8B800, 0xB8F818, 0x58D854, 0x58F898, 0x00E8D8, 0x787878, 0x000000, 0x000000,
    0xFCFCFC, 0xA4E4FC, 0xB8B8F8, 0xD8B8F8, 0xF8B8F8, 0xF8A4C0, 0xF0D0B0, 0xFCE0A8,
    0xF8D878, 0xD8F878, 0xB8F8B8, 0xB8F8D8, 0x00FCFC, 0xF8D8F8, 0x000000, 0x000000,
]

# Colours the converter may use. The $xD-$xF columns are all black; $0F is
# the standard black, and $0D in particular is "blacker than black", a signal
# level that can confuse some TVs, so it's avoided.
USABLE = [n for n in range(64) if (n & 0x0F) < 0x0D] + [0x0F]


def rgb(number):
    """Split 0xRRGGBB into an (r, g, b) tuple."""
    return (number >> 16, (number >> 8) & 0xFF, number & 0xFF)


def distance(a, b):
    """How different two colours look. Plain RGB distance, but weighted:
    eyes are most sensitive to green and least to blue, so a difference
    in green counts for more. (A rough stand-in for proper colour science.)"""
    dr, dg, db = a[0] - b[0], a[1] - b[1], a[2] - b[2]
    return 2 * dr * dr + 4 * dg * dg + 3 * db * db


def closest_nes(colour):
    """The NES colour number that looks most like an (r, g, b) colour."""
    return min(USABLE, key=lambda n: distance(colour, rgb(NES_RGB[n])))


# --- Steps 1-4 ---------------------------------------------------------------

def load_true_size(path, scale, box):
    """Step 1: crop one region (in on-disk pixels) and shrink it by the
    block size. NEAREST takes one pixel per block instead of blending, so
    no new colours are invented."""
    region = Image.open(path).convert("RGB").crop(box)
    return region.resize((region.width // scale, region.height // scale), Image.NEAREST)


def encode_tile(indices):
    """Step 4: encode an 8x8 tile (8 rows of 8 colour slots, 0-3) as 16
    bytes. Plane 0 holds the low bit of every pixel, plane 1 the high bit,
    one byte per row, leftmost pixel in the highest bit."""
    plane0, plane1 = [], []
    for row in indices:
        low = high = 0
        for slot in row:
            low = (low << 1) | (slot & 1)          # shift left, add the new bit on the right
            high = (high << 1) | (slot >> 1)
        plane0.append(low)
        plane1.append(high)
    return plane0 + plane1


def convert(image):
    """Steps 2-4 for a whole image. Returns (palette, tiles): up to 4 NES
    colour numbers, and the tiles left to right, top to bottom."""
    pixels = [[image.getpixel((x, y)) for x in range(image.width)]
              for y in range(image.height)]

    # Step 2: map every original colour to its closest NES colour.
    to_nes = {c: closest_nes(c) for row in pixels for c in row}

    # Step 3: give each NES colour a palette slot. The most common one goes
    # in slot 0, which on the NES is the shared background colour.
    counts = Counter(to_nes[c] for row in pixels for c in row)
    palette = [n for n, _ in counts.most_common()]
    if len(palette) > 4:
        raise ValueError(f"{len(palette)} colours; reducing to 4 comes in the next step")
    slot = {n: i for i, n in enumerate(palette)}

    for original, n in to_nes.items():
        print(f"  #{original[0]:02x}{original[1]:02x}{original[2]:02x}  ->  "
              f"NES ${n:02X} (#{NES_RGB[n]:06x})  slot {slot[n]}")

    # Step 4: cut into 8x8 tiles and encode each.
    tiles = []
    for ty in range(0, image.height, 8):
        for tx in range(0, image.width, 8):
            indices = [[slot[to_nes[pixels[y][x]]] for x in range(tx, tx + 8)]
                       for y in range(ty, ty + 8)]
            tiles.append(encode_tile(indices))
    return palette, tiles


def preview(original, palette, tiles, columns, path, zoom=8):
    """Save the original and the NES version side by side, enlarged."""
    nes = Image.new("RGB", original.size)
    for i, tile in enumerate(tiles):
        ox, oy = (i % columns) * 8, (i // columns) * 8
        for y in range(8):
            for x in range(8):
                bit = 7 - x
                slot = ((tile[y] >> bit) & 1) | (((tile[8 + y] >> bit) & 1) << 1)
                nes.putpixel((ox + x, oy + y), rgb(NES_RGB[palette[slot]]))

    gap = 2
    both = Image.new("RGB", (original.width * 2 + gap, original.height), (255, 255, 255))
    both.paste(original, (0, 0))
    both.paste(nes, (original.width + gap, 0))
    both = both.resize((both.width * zoom, both.height * zoom), Image.NEAREST)
    path.parent.mkdir(exist_ok=True)
    both.save(path)


if __name__ == "__main__":
    # terrain.png: four 64x64 squares at block size 2. Grass is the first.
    grass = load_true_size("art/terrain.png", scale=2, box=(0, 0, 64, 64))
    print(f"grass: {grass.width} x {grass.height} pixels")

    palette, tiles = convert(grass)
    print(f"palette: {', '.join(f'${n:02X}' for n in palette)}")
    print(f"{len(tiles)} tiles:")
    for i, tile in enumerate(tiles):
        print(f"  {i:2}: " + ", ".join(f"0x{b:02X}" for b in tile))

    preview(grass, palette, tiles, grass.width // 8, Path("build/preview_grass.png"))
    print("preview: build/preview_grass.png (original left, NES right)")
