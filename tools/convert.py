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


def decode_tile(tile):
    """The reverse of encode_tile: 16 bytes back to 8 rows of 8 slots. Used
    for previews, so they show what the NES will actually see."""
    return [[((tile[y] >> (7 - x)) & 1) | (((tile[8 + y] >> (7 - x)) & 1) << 1)
             for x in range(8)]
            for y in range(8)]


# --- Sprites: up to 3 palettes per object ------------------------------------
#
# Enemies are drawn as sprites (see PLAN.md). Each 8x8 sprite picks one of
# the 4 sprite palettes, and each palette is 3 colours plus transparent
# (slot 0). An enemy may use 3 of the palettes; the 4th is kept for the
# player. So an enemy can have up to 9 colours, but any one 8x8 piece only 3.
#
# Two stages:
#   1. Within each 8x8 piece, merge colours until it has at most 3.
#   2. Pack the pieces' colour sets into at most 3 palettes. A piece that
#      fits no palette is drawn with the closest colours of the best one.

def colour_gap(a, b):
    """distance() between two NES colour numbers."""
    return distance(rgb(NES_RGB[a]), rgb(NES_RGB[b]))


def merge_colours(counts, limit):
    """Greedy merging. counts maps colour -> number of pixels. While there
    are more than `limit` colours, find the pair whose merge changes the
    picture least (how different they are x how many pixels would change)
    and replace the less-used colour with the other. No new colours are
    invented; the survivors are all original colours.
    Returns a dict: each original colour -> the colour that replaces it."""
    counts = dict(counts)
    replaced_by = {c: c for c in counts}
    while len(counts) > limit:
        pairs = [(a, b) for a in counts for b in counts if a < b]
        a, b = min(pairs, key=lambda p: colour_gap(*p) * min(counts[p[0]], counts[p[1]]))
        keep, drop = (a, b) if counts[a] >= counts[b] else (b, a)
        counts[keep] += counts.pop(drop)
        for original, now in replaced_by.items():
            if now == drop:
                replaced_by[original] = keep
    return replaced_by


def closest_in(colour, palette):
    """The colour in palette that looks most like colour."""
    return min(palette, key=lambda p: colour_gap(colour, p))


def fit_cost(counts, palette):
    """How much a piece changes if drawn with this palette: every colour is
    swapped for the palette's closest, weighted by its number of pixels."""
    return sum(n * colour_gap(c, closest_in(c, palette)) for c, n in counts.items())


def pack_palettes(pieces, max_palettes=3, size=3):
    """pieces: one Counter of colours per 8x8 piece. Returns (palettes,
    choice): the palettes as lists of colour numbers, and which palette
    each piece uses. Pieces with the most colours are placed first, since
    they're the hardest to fit."""
    palettes = []
    choice = [0] * len(pieces)
    for i in sorted(range(len(pieces)), key=lambda i: -len(pieces[i])):
        colours = set(pieces[i])
        if not colours:
            continue                     # fully transparent: any palette works
        # Palettes this piece fits into, counting how many colours each would gain.
        room = [(len(colours - set(p)), k) for k, p in enumerate(palettes)
                if len(set(p) | colours) <= size]
        if room:
            _, k = min(room)             # the one that has to grow least
            palettes[k] += sorted(colours - set(palettes[k]))
        elif len(palettes) < max_palettes:
            k = len(palettes)
            palettes.append(sorted(colours))
        else:
            k = min(range(len(palettes)), key=lambda k: fit_cost(pieces[i], palettes[k]))
        choice[i] = k
    if not palettes:
        return [[]], choice

    # Refine (the k-means idea): the greedy pass above is a first guess. Now
    # repeat two moves until nothing changes:
    #   a. rebuild each palette from the pieces that chose it;
    #   b. let every piece choose again, whichever palette now suits it best.
    # Each round can only lower the total error, so it settles.
    for _ in range(20):
        for k in range(len(palettes)):
            members = Counter()
            for i, piece in enumerate(pieces):
                if choice[i] == k:
                    members += piece
            if members:
                palettes[k] = sorted(set(merge_colours(members, size).values()))
        new_choice = [min(range(len(palettes)), key=lambda k: fit_cost(piece, palettes[k]))
                      if piece else 0
                      for piece in pieces]
        if new_choice == choice:
            break
        choice = new_choice
    return palettes, choice


def convert_sprite(pixels):
    """Convert one object (rows of NES colour numbers, None = transparent)
    into 8x8 sprite tiles. Returns (palettes, choice, tiles)."""
    height, width = len(pixels), len(pixels[0])
    corners = [(tx, ty) for ty in range(0, height, 8) for tx in range(0, width, 8)]

    # Stage 1: at most 3 colours in each piece.
    pieces = []
    for tx, ty in corners:
        counts = Counter(pixels[y][x] for y in range(ty, ty + 8)
                         for x in range(tx, tx + 8) if pixels[y][x] is not None)
        merged = merge_colours(counts, 3)
        pieces.append(Counter({c: 0 for c in merged.values()}) +
                      Counter(merged[c] for c in counts.elements()))
        for y in range(ty, ty + 8):
            for x in range(tx, tx + 8):
                if pixels[y][x] is not None:
                    pixels[y][x] = merged[pixels[y][x]]

    # Stage 2: share out the palettes.
    palettes, choice = pack_palettes(pieces)

    # Encode: transparent is slot 0, palette colours are slots 1-3.
    tiles = []
    for (tx, ty), k in zip(corners, choice):
        palette = palettes[k]
        indices = [[0 if pixels[y][x] is None
                    else 1 + palette.index(closest_in(pixels[y][x], palette))
                    for x in range(tx, tx + 8)]
                   for y in range(ty, ty + 8)]
        tiles.append(encode_tile(indices))
    return palettes, choice, tiles


def load_sprite_sheet(path, scale):
    """Shrink a sheet to true size and map it to NES colours, keeping
    transparency (None). Returns rows of colour numbers."""
    image = Image.open(path).convert("RGBA")
    image = image.resize((image.width // scale, image.height // scale), Image.NEAREST)
    cache = {}
    rows = []
    for y in range(image.height):
        row = []
        for x in range(image.width):
            r, g, b, a = image.getpixel((x, y))
            if a < 128:
                row.append(None)
            else:
                row.append(cache.setdefault((r, g, b), closest_nes((r, g, b))))
        rows.append(row)
    return image, rows


# --- Enemies: black on the background, colour on sprites --------------------
#
# Almost every 8x8 piece of an enemy contains black (the outlines, eyes and
# mouth lines), so if black lived in the sprite palettes it would take one of
# the 3 slots in every palette. Instead, black is drawn on the background
# layer, as a silhouette behind the enemy, and the sprite is see-through
# wherever the original is black. Each sprite palette then holds 3 real
# colours. The cost is paid in the battle screen (Milestone 4): the
# background tiles behind the enemy are generated from its silhouette.

BLACK = 0x0F


def convert_enemy(pixels):
    """Split an enemy into a black mask for the background layer and sprite
    tiles for everything else. Returns (mask, palettes, choice, tiles):
    mask is rows of True (black) / False, the rest is as convert_sprite."""
    pixels = [row[:] for row in pixels]
    mask = [[c == BLACK for c in row] for row in pixels]
    for y, row in enumerate(pixels):
        for x, c in enumerate(row):
            if c == BLACK:
                row[x] = None            # the sprite is see-through here
    palettes, choice, tiles = convert_sprite(pixels)
    return mask, palettes, choice, tiles


def render_enemy(mask, palettes, choice, tiles, backdrop):
    """Draw what the NES would show: backdrop, black silhouette, sprites on top."""
    width = len(mask[0])
    image = Image.new("RGB", (width, len(mask)), backdrop)
    for y, row in enumerate(mask):
        for x, black in enumerate(row):
            if black:
                image.putpixel((x, y), rgb(NES_RGB[BLACK]))
    for i, tile in enumerate(tiles):
        ox, oy = (i % (width // 8)) * 8, (i // (width // 8)) * 8
        for y, row in enumerate(decode_tile(tile)):
            for x, slot in enumerate(row):
                if slot:
                    image.putpixel((ox + x, oy + y), rgb(NES_RGB[palettes[choice[i]][slot - 1]]))
    return image


def preview(original, palette, tiles, columns, path, zoom=8):
    """Save the original and the NES version side by side, enlarged."""
    nes = Image.new("RGB", original.size)
    for i, tile in enumerate(tiles):
        ox, oy = (i % columns) * 8, (i // columns) * 8
        for y, row in enumerate(decode_tile(tile)):
            for x, slot in enumerate(row):
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

    # enemies.png: fifteen 32x32 enemies in a row, at block size 20.
    sheet, rows = load_sprite_sheet("art/enemies.png", scale=20)
    backdrop = (220, 220, 220)               # stands in for the battle backdrop
    out = Image.new("RGB", (sheet.width, 32 * 2 + 4), (255, 255, 255))
    out.paste(Image.alpha_composite(Image.new("RGBA", sheet.size, backdrop + (255,)), sheet), (0, 0))
    print("\nenemies:  colours before -> after, sprite palettes")
    for e in range(15):
        pixels = [row[e * 32:e * 32 + 32] for row in rows]
        before = len({c for row in pixels for c in row if c is not None})
        mask, palettes, choice, tiles = convert_enemy(pixels)
        image = render_enemy(mask, palettes, choice, tiles, backdrop)
        out.paste(image, (e * 32, 36))
        after = len(set(image.get_flattened_data()) - {backdrop})
        print(f"  {e:2}: {before:2} -> {after}   "
              + "  ".join("/".join(f"${c:02X}" for c in p) for p in palettes))
    out.resize((out.width * 4, out.height * 4), Image.NEAREST).save("build/preview_enemies.png")
    print("preview: build/preview_enemies.png (originals on top, NES below)")
