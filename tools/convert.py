"""convert.py - turn the original PNG art into NES tile data.

Runs on the development machine at build time, never on the NES (make runs
it whenever the art or this file changes). It writes build/art.c and
build/art.h, which the build compiles into the ROM, plus before/after
previews in build/.

The steps for one image:
  1. Shrink it back to its true size (one pixel per block; see measure_scale.py).
  2. Replace each color with the closest color the NES can show.
  3. Reduce the colors to fit the NES palette rules, which differ for
     sprites (per 8x8 tile, with transparency) and backgrounds (per 16x16
     area, with one color shared by the whole screen).
  4. Cut the image into 8x8 tiles and encode each as 16 bytes, in the same
     two-plane format as the hand-made tiles in src/main.c.
  5. Store each distinct tile once, plus a map of which tile goes where,
     and write it all out as C arrays.
"""

import random
from collections import Counter
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# --- The NES colors ---------------------------------------------------------
#
# The NES doesn't take RGB values. Its graphics chip generates a TV signal
# directly from 64 numbered colors ($00-$3F), so a game picks colors by
# number. There's no single true RGB value for each: the result depended on
# the TV, and every emulator uses a slightly different table. This is a
# common one.
#
# Rows go from dark ($0x) to light ($3x); columns go round the color wheel
# (gray, blues, purples, reds, oranges, greens, cyans), then blacks.

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

# Colors the converter may use. The $xD-$xF columns are all black; $0F is
# the standard black, and $0D in particular is "blacker than black", a signal
# level that can confuse some TVs, so it's avoided.
USABLE = [n for n in range(64) if (n & 0x0F) < 0x0D] + [0x0F]


def rgb(number):
    """Split 0xRRGGBB into an (r, g, b) tuple."""
    return (number >> 16, (number >> 8) & 0xFF, number & 0xFF)


def oklab(color):
    """Convert an (r, g, b) color to OKLab, a "perceptual" color space
    (Bjorn Ottosson, 2020). RGB describes how much each light a screen
    emits; it's a poor measure of how different two colors look, because
    eyes don't respond to the three lights equally or in proportion. In
    OKLab, the same distance means roughly the same visible difference
    anywhere: L is lightness, a runs green to red, b runs blue to yellow."""
    # sRGB values are gamma-encoded; undo that to get actual light amounts.
    r, g, b = (((c / 255 + 0.055) / 1.055) ** 2.4 if c > 10 else c / 255 / 12.92
               for c in color)
    # Roughly the responses of the eye's three kinds of cone cell...
    l = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
    m = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
    s = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b
    # ...compressed (we notice changes in dim colors more than bright ones)
    l, m, s = l ** (1 / 3), m ** (1 / 3), s ** (1 / 3)
    # ...and recombined into lightness and two color axes.
    return (0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
            1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
            0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s)


_oklab_cache = {}

# Which way of measuring color difference to use: "oklab" or "rgb". Set per
# image with use_method(). Neither is right for everything: the NES palette
# has almost no muted colors, so a muted color is matched either by
# lightness (OKLab: often too saturated) or by plain RGB (often the right hue
# but too light). The choice per image was made by eye, comparing previews.
method = "oklab"


def use_method(name):
    """Switch the color-difference measure for everything that follows."""
    global method
    method = name


def distance(a, b):
    """How different two (r, g, b) colors look, by the current method."""
    if method == "rgb":
        # Plain RGB distance, weighted: eyes are most sensitive to green and
        # least to blue, so a difference in green counts for more.
        dr, dg, db = a[0] - b[0], a[1] - b[1], a[2] - b[2]
        return 2 * dr * dr + 4 * dg * dg + 3 * db * db
    # OKLab: the squared distance between the two colors in OKLab.
    for c in (a, b):
        if c not in _oklab_cache:
            _oklab_cache[c] = oklab(c)
    pa, pb = _oklab_cache[a], _oklab_cache[b]
    return sum((x - y) ** 2 for x, y in zip(pa, pb))


def closest_nes(color):
    """The NES color number that looks most like an (r, g, b) color.

    One exception: near-blacks become black ($0F). The NES's darkest
    colors are much brighter than the near-black that pixel artists use
    for outlines (#181425 here), so by distance alone an outline would turn
    dark teal. Anything darker than this lightness is meant as black.
    (Only needed with OKLab; weighted RGB already picks black for these.)"""
    if method == "oklab" and oklab(color)[0] < 0.25:
        return 0x0F
    return min(USABLE, key=lambda n: distance(color, rgb(NES_RGB[n])))


# --- Encoding ------------------------------------------------------------------

def encode_tile(indices):
    """Step 4: encode an 8x8 tile (8 rows of 8 color slots, 0-3) as 16
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


def decode_tile(tile):
    """The reverse of encode_tile: 16 bytes back to 8 rows of 8 slots. Used
    for previews, so they show what the NES will actually see."""
    return [[((tile[y] >> (7 - x)) & 1) | (((tile[8 + y] >> (7 - x)) & 1) << 1)
             for x in range(8)]
            for y in range(8)]


# --- Sprites: up to 3 palettes per object ------------------------------------
#
# Players are drawn as sprites. Each 8x8 sprite picks one of the 4 sprite
# palettes, and each palette is 3 colors plus transparent (slot 0). Only one
# sprite object is on the overworld, so a player may use all 4 palettes: up
# to 12 colors, but any one 8x8 piece only 3.
#
# Two stages:
#   1. Within each 8x8 piece, merge colors until it has at most 3.
#   2. Pack the pieces' color sets into the palettes. A piece that
#      fits no palette is drawn with the closest colors of the best one.

def color_gap(a, b):
    """distance() between two NES color numbers."""
    return distance(rgb(NES_RGB[a]), rgb(NES_RGB[b]))


def merge_colors(counts, limit):
    """Greedy merging. counts maps color -> number of pixels. While there
    are more than `limit` colors, find the pair whose merge changes the
    picture least (how different they are x how many pixels would change)
    and replace the less-used color with the other. No new colors are
    invented; the survivors are all original colors.
    Returns a dict: each original color -> the color that replaces it."""
    counts = dict(counts)
    replaced_by = {c: c for c in counts}
    while len(counts) > limit:
        pairs = [(a, b) for a in counts for b in counts if a < b]
        a, b = min(pairs, key=lambda p: color_gap(*p) * min(counts[p[0]], counts[p[1]]))
        keep, drop = (a, b) if counts[a] >= counts[b] else (b, a)
        counts[keep] += counts.pop(drop)
        for original, now in replaced_by.items():
            if now == drop:
                replaced_by[original] = keep
    return replaced_by


def closest_in(color, palette):
    """The color in palette that looks most like color."""
    return min(palette, key=lambda p: color_gap(color, p))


def fit_cost(counts, palette):
    """How much a piece changes if drawn with this palette: every color is
    swapped for the palette's closest, weighted by its number of pixels."""
    return sum(n * color_gap(c, closest_in(c, palette)) for c, n in counts.items())


def pack_once(pieces, order, max_palettes, size, fixed=()):
    """One attempt at packing: a greedy first guess, placing pieces in the
    given order, then refined. Palettes in `fixed` come first and never
    change. Returns (palettes, choice)."""
    palettes = [list(p) for p in fixed]
    choice = [0] * len(pieces)
    for i in order:
        colors = set(pieces[i])
        if not colors:
            continue                     # fully transparent: any palette works
        # Palettes this piece fits into, counting how many colors each would
        # gain. A fixed palette only takes pieces it already covers.
        room = [(len(colors - set(p)), k) for k, p in enumerate(palettes)
                if len(set(p) | colors) <= size and (k >= len(fixed) or colors <= set(p))]
        if room:
            _, k = min(room)             # the one that has to grow least
            palettes[k] += sorted(colors - set(palettes[k]))
        elif len(palettes) < max_palettes:
            k = len(palettes)
            palettes.append(sorted(colors))
        else:
            k = min(range(len(palettes)), key=lambda k: fit_cost(pieces[i], palettes[k]))
        choice[i] = k
    if not palettes:
        return [[]], choice

    # Refine (the k-means idea): the greedy pass above is a first guess. Now
    # repeat two moves until nothing changes:
    #   a. rebuild each palette from the pieces that chose it;
    #   b. let every piece choose again, whichever palette now suits it best.
    for _ in range(20):
        for k in range(len(fixed), len(palettes)):
            members = Counter()
            for i, piece in enumerate(pieces):
                if choice[i] == k:
                    members += piece
            if members:
                palettes[k] = sorted(set(merge_colors(members, size).values()))
        new_choice = [min(range(len(palettes)), key=lambda k: fit_cost(piece, palettes[k]))
                      if piece else 0
                      for piece in pieces]
        if new_choice == choice:
            break
        choice = new_choice
    return palettes, choice


def total_error(pieces, palettes, choice):
    """How much the whole picture changes with this packing."""
    return sum(fit_cost(piece, palettes[k]) for piece, k in zip(pieces, choice) if piece)


def pack_palettes(pieces, max_palettes=3, size=3, restarts=30, fixed=()):
    """pieces: one Counter of colors per piece. Returns (palettes, choice):
    the palettes as lists of color numbers, and which palette each piece
    uses. `fixed`: palettes that must stay as they are (counted in
    max_palettes).

    k-means only finds the best answer near where it starts; a different
    first guess can settle somewhere better. So it runs several times: once
    with the hardest pieces (most colors) placed first, then with shuffled
    orders, and keeps the packing with the least total error ("random
    restarts"). The shuffles use a fixed seed, so every build gives the
    same result."""
    hardest_first = sorted(range(len(pieces)), key=lambda i: -len(pieces[i]))
    shuffler = random.Random(0)
    orders = [hardest_first]
    for _ in range(restarts):
        order = hardest_first[:]
        shuffler.shuffle(order)
        orders.append(order)

    attempts = [pack_once(pieces, order, max_palettes, size, fixed) for order in orders]
    return min(attempts, key=lambda a: total_error(pieces, *a))


def merge_regions(pixels, corners, size, ignore):
    """Stage 1, for sprites and backgrounds alike: in each size x size
    region (given by its top-left corner), merge colors until at most 3
    remain. Pixels equal to `ignore` (transparent, or the shared background
    color) don't count. Changes pixels in place and returns one Counter of
    colors per region."""
    pieces = []
    for rx, ry in corners:
        counts = Counter(pixels[y][x] for y in range(ry, ry + size)
                         for x in range(rx, rx + size) if pixels[y][x] != ignore)
        merged = merge_colors(counts, 3)
        pieces.append(Counter({c: 0 for c in merged.values()}) +
                      Counter(merged[c] for c in counts.elements()))
        for y in range(ry, ry + size):
            for x in range(rx, rx + size):
                if pixels[y][x] != ignore:
                    pixels[y][x] = merged[pixels[y][x]]
    return pieces


def convert_sprite(pixels, max_palettes=3):
    """Convert one object (rows of NES color numbers, None = transparent)
    into 8x8 sprite tiles using up to max_palettes palettes.
    Returns (palettes, choice, tiles)."""
    height, width = len(pixels), len(pixels[0])
    corners = [(tx, ty) for ty in range(0, height, 8) for tx in range(0, width, 8)]

    # Stage 1: at most 3 colors in each piece.
    pieces = merge_regions(pixels, corners, 8, ignore=None)

    # Stage 2: share out the palettes.
    palettes, choice = pack_palettes(pieces, max_palettes)

    # Encode: transparent is slot 0, palette colors are slots 1-3.
    tiles = []
    for (tx, ty), k in zip(corners, choice):
        palette = palettes[k]
        indices = [[0 if pixels[y][x] is None
                    else 1 + palette.index(closest_in(pixels[y][x], palette))
                    for x in range(tx, tx + 8)]
                   for y in range(ty, ty + 8)]
        tiles.append(encode_tile(indices))
    return palettes, choice, tiles


# Hand-picked NES colors, per image: original color -> NES color number.
# Used where the closest color by the numbers looks wrong in context. Each
# was chosen by eye from previews.
OVERRIDES = {
    "art/terrain.png": {
        (0x19, 0x3C, 0x3E): 0x0A,   # forest's dark teal: the closest match ($0C)
                                    # is a blue that reads as water
        (0x63, 0xC7, 0x4D): 0x1A,   # grass's light green: $2A, a bright lime, is
                                    # closest; this deeper green is calmer
    },
}


def load_sprite_sheet(path, true_size):
    """Shrink a sheet to its true size, (width, height) in art pixels, and
    map it to NES colors (with any OVERRIDES for this image), keeping
    transparency (None). Returns rows of color numbers.

    NEAREST takes the pixel at the center of each block. For a clean
    whole-number scale any pixel in the block would do; for players.png,
    which was resized with smoothing (about 11.97x), the center matters:
    the blur sits at the block edges, and the centers still hold the
    original colors exactly."""
    image = Image.open(path).convert("RGBA")
    image = image.resize(true_size, Image.NEAREST)
    cache = dict(OVERRIDES.get(path, {}))
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


BLACK = 0x0F


# --- Backgrounds: palettes per 16x16 area -----------------------------------
#
# Background tiles differ from sprites in two ways:
#   - They can't be see-through. Slot 0 of every background palette is one
#     color shared by the whole screen, so each palette has 3 of its own.
#   - Palettes are chosen per 16x16 area (the attribute table), not per tile.
# So the same two stages run on 16x16 areas, with the shared color left out.

def convert_background(pixels, shared, max_palettes=4):
    """pixels: rows of NES color numbers; None (transparent) becomes the
    shared color. Returns (palettes, choice, tiles): palettes of up to 3
    colors (slots 1-3), the palette for each 16x16 area, and the 8x8 tiles,
    each list running left to right, top to bottom."""
    height, width = len(pixels), len(pixels[0])
    pixels = [[shared if c is None else c for c in row] for row in pixels]
    areas = [(ax, ay) for ay in range(0, height, 16) for ax in range(0, width, 16)]

    pieces = merge_regions(pixels, areas, 16, ignore=shared)
    palettes, choice = pack_palettes(pieces, max_palettes)

    tiles = []
    for ty in range(0, height, 8):
        for tx in range(0, width, 8):
            palette = palettes[choice[areas.index((tx - tx % 16, ty - ty % 16))]]
            indices = [[0 if pixels[y][x] == shared
                        else 1 + palette.index(closest_in(pixels[y][x], palette))
                        for x in range(tx, tx + 8)]
                       for y in range(ty, ty + 8)]
            tiles.append(encode_tile(indices))
    return palettes, choice, tiles


def render_background(width, height, shared, palettes, choice, tiles):
    """Draw what the NES would show for a converted background."""
    image = Image.new("RGB", (width, height))
    per_row = width // 16
    for i, tile in enumerate(tiles):
        tx, ty = (i % (width // 8)) * 8, (i // (width // 8)) * 8
        palette = [shared] + palettes[choice[(ty // 16) * per_row + tx // 16]]
        for y, row in enumerate(decode_tile(tile)):
            for x, slot in enumerate(row):
                image.putpixel((tx + x, ty + y), rgb(NES_RGB[palette[slot]]))
    return image


# --- Terrain: repeating patterns --------------------------------------------
#
# Grass, sand and forest are textures, not pictures, so each 32x32 square is
# replaced by one 16x16 piece of itself, repeated 2x2. The repeats line up
# with the 8x8 tile grid, so deduplication then stores 4 tiles per square
# instead of 16. (An 8x8 piece was tried too: it shows an obvious grid.)
# The castle is a picture and stays whole.

REPEATING_SQUARES = (0, 1, 3)       # grass, sand, forest; 2 is the castle


def best_piece(rows, sx, size):
    """The size x size piece of the 32x32 square at column sx that repeats
    with the least visible seam: where the piece wraps around, how often
    does its first column (or row) differ from the pixels that came next in
    the original? Returns the piece's top-left corner within the square."""
    def seam(x0, y0):
        return sum((rows[y0 + i][sx + (x0 + size) % 32] != rows[y0 + i][sx + x0]) +
                   (rows[(y0 + size) % 32][sx + x0 + i] != rows[y0][sx + x0 + i])
                   for i in range(size))
    corners = [(x, y) for y in range(32 - size + 1) for x in range(32 - size + 1)]
    return min(corners, key=lambda corner: seam(*corner))


def repeat_piece(rows, sx, size=16):
    """Fill the 32x32 square at column sx with its best piece, repeated."""
    x0, y0 = best_piece(rows, sx, size)
    piece = [rows[y0 + y][sx + x0:sx + x0 + size] for y in range(size)]
    for y in range(32):
        rows[y][sx:sx + 32] = piece[y % size] * (32 // size)


def most_common(rows):
    """The most used color in an image, ignoring transparency."""
    return Counter(c for row in rows for c in row if c is not None).most_common(1)[0][0]


def save_comparison(sheet, converted, behind, path):
    """Original on top, NES version below, enlarged 4x."""
    out = Image.new("RGB", (sheet.width, sheet.height * 2 + 4), (255, 255, 255))
    out.paste(Image.alpha_composite(Image.new("RGBA", sheet.size, behind + (255,)), sheet), (0, 0))
    out.paste(converted, (0, sheet.height + 4))
    out.resize((out.width * 4, out.height * 4), Image.NEAREST).save(path)


# --- Battle screens ----------------------------------------------------------
#
# The battle screen is one background picture: the backdrop enlarged 4x
# (64 x 4 = 256, the screen's width) with the enemy enlarged 4x standing on
# it, the same proportions as the original game, which stretched both.
# Sprites can't do it: a 128x128 enemy would need 256 of them, and the NES
# has 64.
#
# Enlarging is cheaper than it sounds. At 4x an 8x8 tile covers only 2x2 art
# pixels, so tiles repeat a lot, and a 16x16 palette area covers 4x4 art
# pixels, which rarely hold more than 3 colors.
#
# The backdrop is stored once, with one fixed palette (palette 0). Each enemy
# stores only its 128x128 area: the tiles the backdrop doesn't already have,
# the tile numbers for the area, the other 3 palettes and the attribute table.

SCALE = 4
CROP_TOP = 4            # 64 art rows x 4 = 256 pixels, 16 more than the screen:
                        # drop the top 4 art rows (the original cropped the top too)
ENEMY_X, ENEMY_Y = 64, 80   # the enemy's top-left on screen. Matches the original:
                            # centered, feet on the ground, clear of the sun.
                            # Multiples of 16, so its area lines up with palette areas.


def enlarge(rows, scale):
    """Nearest-neighbor enlargement: every pixel becomes a scale x scale block."""
    return [[v for v in row for _ in range(scale)] for row in rows for _ in range(scale)]


def convert_backdrop(art_rows):
    """The backdrop alone, as a full screen. It has 3 colors besides the sky,
    so one palette covers all of it. Returns (screen pixels, shared color,
    palette, the 960 tiles of the screen)."""
    screen = enlarge(art_rows, SCALE)[CROP_TOP * SCALE:CROP_TOP * SCALE + 240]
    shared = most_common(art_rows)
    palettes, _, tiles = convert_background(screen, shared, max_palettes=1)
    return screen, shared, palettes[0], tiles


def convert_battle(screen, shared, backdrop_palette, backdrop_tiles, enemy_rows):
    """Stand an enemy on the backdrop and convert its area. Returns
    (palettes, palette per 16x16 area for the whole screen, the 960 tiles)."""
    pixels = [row[:] for row in screen]
    for y, row in enumerate(enlarge(enemy_rows, SCALE)):
        for x, color in enumerate(row):
            if color is not None:
                pixels[ENEMY_Y + y][ENEMY_X + x] = color
    areas = [(x, y) for y in range(ENEMY_Y, ENEMY_Y + 128, 16)
             for x in range(ENEMY_X, ENEMY_X + 128, 16)]
    pieces = merge_regions(pixels, areas, 16, ignore=shared)
    palettes, area_choice = pack_palettes(pieces, 4, fixed=[backdrop_palette])

    choice = [0] * (16 * 15)            # outside the enemy: the backdrop's palette
    for (x, y), k in zip(areas, area_choice):
        choice[(y // 16) * 16 + x // 16] = k
    tiles = list(backdrop_tiles)
    for ty in range(ENEMY_Y, ENEMY_Y + 128, 8):
        for tx in range(ENEMY_X, ENEMY_X + 128, 8):
            palette = palettes[choice[(ty // 16) * 16 + tx // 16]]
            tiles[(ty // 8) * 32 + tx // 8] = encode_tile(
                [[0 if pixels[y][x] == shared
                  else 1 + palette.index(closest_in(pixels[y][x], palette))
                  for x in range(tx, tx + 8)]
                 for y in range(ty, ty + 8)])
    return palettes, choice, tiles


def attribute_table(choice):
    """Pack a palette number per 16x16 area (16 across, 15 down) into the
    64-byte attribute table: one byte per 32x32 block, 2 bits per quarter,
    top-left in the lowest bits. The screen is 7.5 blocks tall, so the last
    row of bytes only uses its top half."""
    def at(ax, ay):
        return choice[ay * 16 + ax] if ay < 15 else 0
    return [at(2 * bx, 2 * by) | at(2 * bx + 1, 2 * by) << 2 |
            at(2 * bx, 2 * by + 1) << 4 | at(2 * bx + 1, 2 * by + 1) << 6
            for by in range(8) for bx in range(8)]


# --- Output: C arrays for the ROM -------------------------------------------
#
# The NES has no image files, so art reaches the ROM as constant byte arrays,
# ready to copy into graphics memory. Each distinct tile is stored once, with
# maps saying which tile goes where.
#
# The art is too big for the fixed bank (16 KB, shared with all the code), so
# it goes in the switchable banks: the C code switches to an item's bank
# before reading it. Small index tables in the fixed bank say where each
# item is.

BANK_ROOM = 0x4000 - 16          # each bank ends with a 16-byte reset stub
ART_BANKS = 14                   # banks 0-13; bank 14 holds the data tables (tools/data.py)


def unique_tiles(tiles, known=None):
    """Deduplication: keep the first copy of each distinct tile. Returns
    (the new distinct tiles, the tile number for every cell). `known` maps
    tiles already stored elsewhere to their numbers; they're reused, and
    new tiles are numbered after them."""
    number_of = dict(known or {})
    unique, numbers = [], []
    for tile in tiles:
        key = tuple(tile)
        if key not in number_of:
            number_of[key] = len(number_of)
            unique.append(tile)
        numbers.append(number_of[key])
    return unique, numbers


def full_palettes(palettes, slot0):
    """Pad to the 4 palettes x 4 colors the graphics chip has, in the order
    it stores them: slot 0, then the 3 colors. Unused slots are black."""
    out = []
    for k in range(4):
        p = palettes[k] if k < len(palettes) else []
        out += [slot0] + p + [BLACK] * (3 - len(p))
    return out


HEADER = """\
/* art.h - generated by tools/convert.py from the PNGs in art/. Don't edit;
 * make rebuilds it when the art or the converter changes.
 *
 * The art lives in the switchable banks: switch to an item's bank with
 * mmc1_set_bank() before reading it. The bank numbers and the tables of
 * pointers below are in the fixed bank, so they can always be read. */

#ifndef ART_H
#define ART_H

/* The overworld terrain: four 32x32 squares (grass, sand, castle, forest). */
typedef struct {
    unsigned char tile_count;
    const unsigned char *tiles;              /* tile_count x 16 bytes */
    const unsigned char *squares;            /* 16 tile numbers per square, 4x4, row by row */
    const unsigned char *square_attributes;  /* 1 attribute byte per square: a square
                                                is exactly one 32x32 attribute block */
    const unsigned char *palettes;           /* 16 bytes: 4 background palettes */
} Terrain;

/* The battle backdrop, enlarged to fill the screen. */
typedef struct {
    unsigned char tile_count;
    const unsigned char *tiles;
    const unsigned char *nametable;          /* 960 tile numbers: the whole screen */
} Backdrop;

/* One battle screen: an enemy standing on the backdrop. Only the enemy's
 * 16x16-tile area differs from the backdrop. */
typedef struct {
    unsigned char tile_count;                /* new tiles, numbered after the backdrop's */
    const unsigned char *tiles;
    const unsigned char *tile_map;           /* 256 tile numbers for the enemy's area */
    const unsigned char *attributes;         /* 64 bytes: the whole attribute table */
    const unsigned char *palettes;           /* 16 bytes: 4 background palettes */
} Battle;

/* A 32x32 sprite object (a player): 16 sprites in a 4x4 grid. */
typedef struct {
    unsigned char tile_count;
    const unsigned char *tiles;
    const unsigned char *tile_map;           /* 16 tile numbers, row by row */
    const unsigned char *sprite_palettes;    /* 16: which palette each sprite uses */
    const unsigned char *palettes;           /* 16 bytes: 4 sprite palettes */
} Sprite;

/* The font: one 8x8 character for each printable ASCII code, 1 bit per pixel
 * (8 bytes, one per row, leftmost pixel in bit 7). text.c turns them into
 * tiles when loading, in whichever two colors are wanted. */
typedef struct {
    unsigned char first;                     /* the first character's code */
    unsigned char count;
    const unsigned char *glyphs;             /* count x 8 bytes */
} Font;

/* A set of ready-made tiles. */
typedef struct {
    unsigned char count;
    const unsigned char *tiles;              /* count x 16 bytes */
} Tiles;

"""


class Output:
    """Collects C text, filling the switchable banks in order."""

    def __init__(self):
        self.banks = [[]]
        self.room = BANK_ROOM
        self.header = [HEADER]
        self.fixed = []

    def array(self, name, values):
        return (f"static const unsigned char {name}[{len(values)}] = {{\n"
                + "\n".join("    " + ", ".join(f"0x{v:02X}" for v in values[i:i + 16]) + ","
                            for i in range(0, len(values), 16))
                + "\n};\n", len(values))

    def item(self, type_name, name, fields):
        """Place one struct and its arrays in a bank. fields: a list of
        numbers (ints) and (array name, values). Returns the bank number."""
        text, size, inits = [], 16, []
        for field in fields:
            if isinstance(field, int):
                inits.append(str(field))
            else:
                array_text, array_size = self.array(f"{name}_{field[0]}", field[1])
                text.append(array_text)
                size += array_size
                inits.append(f"{name}_{field[0]}")
        text.append(f"const {type_name} {name} = {{ {', '.join(inits)} }};\n\n")
        if size > self.room:
            self.banks.append([])
            self.room = BANK_ROOM
        self.banks[-1].append("".join(text))
        self.room -= size
        return len(self.banks) - 1

    def table(self, type_name, name, items):
        """A table in the fixed bank of (bank, struct name) for a set of items."""
        count = len(items)
        self.header.append(f"extern const unsigned char {name}_bank[{count}];\n"
                           f"extern const {type_name} * const {name}[{count}];\n")
        self.fixed.append(
            f"const unsigned char {name}_bank[{count}] = {{ "
            + ", ".join(str(bank) for bank, _ in items) + " };\n"
            f"const {type_name} * const {name}[{count}] = {{\n"
            + "".join(f"    &{struct},\n" for _, struct in items) + "};\n\n")

    def write(self, c_path, h_path):
        if len(self.banks) > ART_BANKS:
            raise SystemExit(f"art doesn't fit in the {ART_BANKS} banks it has")
        source = ["/* art.c - generated by tools/convert.py. Don't edit. */\n\n"
                  '#include "art.h"\n\n']
        for number, bank in enumerate(self.banks):
            source.append(f'#pragma rodata-name (push, "BANK{number:02d}")\n\n')
            source += bank
            source.append("#pragma rodata-name (pop)\n\n")
        source.append("/* In the fixed bank: where everything is. */\n\n")
        source += self.fixed
        Path(c_path).write_text("".join(source))
        Path(h_path).write_text("".join(self.header) + "\n#endif\n")
        print(f"wrote {c_path} and {h_path}: {len(self.banks)} bank(s), "
              f"{BANK_ROOM - self.room} bytes in the last")


# --- The font ----------------------------------------------------------------
#
# The original uses Press Start 2P, a font drawn on an 8x8 pixel grid, so at
# 8 px each character lands exactly on one NES tile, with nothing to redraw.
# (It's under the SIL Open Font License, art/OFL.txt, which reserves its name
# for the unmodified font, so the converted version here doesn't use it.)
#
# The characters go at the end of the background tiles, after anything the
# screens use, so text can be shown on any screen.

FONT_FIRST, FONT_LAST = 32, 126           # printable ASCII: space to ~
FONT_COUNT = FONT_LAST - FONT_FIRST + 1   # 95
FONT_TILE = 256 - FONT_COUNT              # 161: the space's tile number


def convert_font(path):
    """Draw each character and return its 8 rows as bytes, leftmost pixel in
    bit 7. Stops if a character doesn't fit its 8x8 tile exactly."""
    font = ImageFont.truetype(path, 8)
    glyphs = []
    for code in range(FONT_FIRST, FONT_LAST + 1):
        char = chr(code)
        if font.getlength(char) != 8:
            raise SystemExit(f"font: {char!r} isn't 8 pixels wide")
        left, top, right, bottom = font.getbbox(char)
        if left < 0 or top < 0 or right > 8 or bottom > 8:
            raise SystemExit(f"font: {char!r} spills outside its 8x8 tile")
        image = Image.new("L", (8, 8), 0)
        ImageDraw.Draw(image).text((0, 0), char, font=font, fill=255)
        for y in range(8):
            row = 0
            for x in range(8):
                value = image.getpixel((x, y))
                if value not in (0, 255):
                    raise SystemExit(f"font: {char!r} has a blurred pixel")
                row = (row << 1) | (value == 255)
            glyphs.append(row)
    return glyphs


# --- The battle screen's text boxes -----------------------------------------
#
# Boxes with a line around them, inset 3 pixels from the tile's edge, in the
# backdrop's own colors (no palette is free for them). The 8 tiles, in this
# order: top-left, top, top-right, left, right, bottom-left, bottom,
# bottom-right. They go just before the font.

BOX_TILES = 8
BOX_TILE = FONT_TILE - BOX_TILES          # 153
BOX_LINE = (3, 4)                         # which pixels of a tile the line is on


def box_tiles(fill, line):
    """The 8 box tiles, as 16 bytes each: color slot `line` for the line,
    `fill` everywhere else."""
    def tile(top, bottom, left, right):
        rows = []
        for y in range(8):
            row = []
            for x in range(8):
                # Inside the box's outline: past the line on each side that has one.
                inside = ((not top or y >= BOX_LINE[0]) and (not bottom or y <= BOX_LINE[1]) and
                          (not left or x >= BOX_LINE[0]) and (not right or x <= BOX_LINE[1]))
                on_line = inside and ((top and y in BOX_LINE) or (bottom and y in BOX_LINE) or
                                      (left and x in BOX_LINE) or (right and x in BOX_LINE))
                row.append(line if on_line else fill)
            rows.append(row)
        return encode_tile(rows)
    sides = [(1, 0, 1, 0), (1, 0, 0, 0), (1, 0, 0, 1), (0, 0, 1, 0),
             (0, 0, 0, 1), (0, 1, 1, 0), (0, 1, 0, 0), (0, 1, 0, 1)]
    return [b for t in sides for b in tile(*t)]


# The rows the boxes cover, in 8x8 tiles. They must stay clear of the enemy's
# area (rows 10-25), so they're in the backdrop's palette. Checked below.
BOX_ROWS = list(range(1, 6)) + list(range(26, 30))


def font_preview(glyphs, path):
    """All the characters in rows of 16, enlarged 4x."""
    image = Image.new("RGB", (16 * 8, 6 * 8), (0, 0, 0))
    for i in range(FONT_COUNT):
        for y in range(8):
            for x in range(8):
                if glyphs[i * 8 + y] & (0x80 >> x):
                    image.putpixel(((i % 16) * 8 + x, (i // 16) * 8 + y), (0, 255, 255))
    image.resize((512, 192), Image.NEAREST).save(path)


def render_sprite(palettes, choice, tiles, backdrop):
    """Draw what the NES would show for a 32x32 sprite object."""
    image = Image.new("RGB", (32, 32), backdrop)
    for i, tile in enumerate(tiles):
        ox, oy = (i % 4) * 8, (i // 4) * 8
        for y, row in enumerate(decode_tile(tile)):
            for x, slot in enumerate(row):
                if slot:
                    image.putpixel((ox + x, oy + y), rgb(NES_RGB[palettes[choice[i]][slot - 1]]))
    return image


def screen_image(pixels):
    """Pixels (NES color numbers) as an RGB image."""
    image = Image.new("RGB", (len(pixels[0]), len(pixels)))
    image.putdata([rgb(NES_RGB[c]) for row in pixels for c in row])
    return image


if __name__ == "__main__":
    Path("build").mkdir(exist_ok=True)
    out = Output()

    # --- Terrain (oklab matched best by eye) ---
    use_method("oklab")
    sheet, rows = load_sprite_sheet("art/terrain.png", (128, 32))
    for square in REPEATING_SQUARES:
        repeat_piece(rows, square * 32)
    terrain_shared = most_common(rows)
    palettes, choice, tiles = convert_background(rows, terrain_shared)
    image = render_background(128, 32, terrain_shared, palettes, choice, tiles)
    save_comparison(sheet, image, rgb(NES_RGB[terrain_shared]), "build/preview_terrain.png")
    unique, numbers = unique_tiles(tiles)
    squares = [numbers[r * 16 + s * 4 + c] for s in range(4) for r in range(4) for c in range(4)]
    square_attributes = [choice[2 * s] | choice[2 * s + 1] << 2 |
                         choice[8 + 2 * s] << 4 | choice[9 + 2 * s] << 6 for s in range(4)]
    bank = out.item("Terrain", "terrain", [
        len(unique), ("tiles", [b for t in unique for b in t]), ("squares", squares),
        ("square_attributes", square_attributes),
        ("palettes", full_palettes(palettes, terrain_shared))])
    out.header.append(f"#define TERRAIN_BANK {bank}\nextern const Terrain terrain;\n")
    print(f"terrain: {len(unique)} tiles, shared ${terrain_shared:02X}, palettes "
          + "  ".join("/".join(f"${c:02X}" for c in p) for p in palettes))

    # --- Players: sprites (oklab). They appear only on the overworld, so slot 0
    # of their palettes is the terrain's shared color: $3F10, the first sprite
    # palette's slot 0, is the same memory as $3F00, the shared color. ---
    sheet, rows = load_sprite_sheet("art/players.png", (160, 32))
    preview = Image.new("RGB", (160, 32 * 2 + 4), (255, 255, 255))
    preview.paste(Image.alpha_composite(
        Image.new("RGBA", sheet.size, rgb(NES_RGB[terrain_shared]) + (255,)), sheet), (0, 0))
    players = []
    for e in range(5):
        palettes, choice, tiles = convert_sprite([row[e * 32:e * 32 + 32] for row in rows],
                                                 max_palettes=4)
        preview.paste(render_sprite(palettes, choice, tiles, rgb(NES_RGB[terrain_shared])),
                      (e * 32, 36))
        unique, numbers = unique_tiles(tiles)
        name = f"player{e}"
        players.append((out.item("Sprite", name, [
            len(unique), ("tiles", [b for t in unique for b in t]), ("tile_map", numbers),
            ("sprite_palettes", choice),
            ("palettes", full_palettes(palettes, terrain_shared))]), name))
    preview.resize((640, 272), Image.NEAREST).save("build/preview_players.png")
    out.header.append(f"\n#define PLAYER_COUNT {len(players)}\n")
    out.table("Sprite", "players", players)

    # --- Battles: backdrop and enemies (weighted RGB matched best by eye) ---
    use_method("rgb")
    _, back_rows = load_sprite_sheet("art/background.png", (64, 64))
    screen, shared, backdrop_palette, backdrop_tiles = convert_backdrop(back_rows)
    backdrop_unique, backdrop_map = unique_tiles(backdrop_tiles)
    bank = out.item("Backdrop", "backdrop", [
        len(backdrop_unique), ("tiles", [b for t in backdrop_unique for b in t]),
        ("nametable", backdrop_map)])
    out.header.append(f"\n#define BACKDROP_BANK {bank}\n"
                      f"#define BACKDROP_TILES {len(backdrop_unique)}\n"
                      "extern const Backdrop backdrop;\n\n"
                      f"/* Where the enemy's area starts, in tiles. */\n"
                      f"#define BATTLE_ENEMY_X {ENEMY_X // 8}\n"
                      f"#define BATTLE_ENEMY_Y {ENEMY_Y // 8}\n")
    print(f"backdrop: {len(backdrop_unique)} tiles, shared ${shared:02X}, palette "
          + "/".join(f"${c:02X}" for c in backdrop_palette))

    known = {tuple(t): n for n, t in enumerate(backdrop_unique)}
    _, enemy_rows = load_sprite_sheet("art/enemies.png", (480, 32))
    preview = Image.new("RGB", (5 * 262, 6 * 246), (255, 255, 255))
    battles = []
    for e in range(15):
        enemy = [row[e * 32:e * 32 + 32] for row in enemy_rows]
        palettes, choice, tiles = convert_battle(screen, shared, backdrop_palette,
                                                 backdrop_tiles, enemy)
        area = [tiles[ty * 32 + tx] for ty in range(ENEMY_Y // 8, ENEMY_Y // 8 + 16)
                for tx in range(ENEMY_X // 8, ENEMY_X // 8 + 16)]
        new, numbers = unique_tiles(area, known)
        if len(backdrop_unique) + len(new) > BOX_TILE:
            raise SystemExit(f"enemy {e}: too many tiles to leave room for the font")
        if any(choice[(row // 2) * 16 + x] != 0 for row in BOX_ROWS for x in range(16)):
            raise SystemExit(f"enemy {e}: a text box's rows aren't all in the backdrop's palette")
        name = f"battle{e}"
        battles.append((out.item("Battle", name, [
            len(new), ("tiles", [b for t in new for b in t]), ("tile_map", numbers),
            ("attributes", attribute_table(choice)),
            ("palettes", full_palettes(palettes, shared))]), name))
        print(f"  enemy {e:2}: {len(new):3} new tiles, palettes "
              + "  ".join("/".join(f"${c:02X}" for c in p) for p in palettes))

        original = [row[:] for row in screen]
        for y, row in enumerate(enlarge(enemy, SCALE)):
            for x, color in enumerate(row):
                if color is not None:
                    original[ENEMY_Y + y][ENEMY_X + x] = color
        col, row = e % 5, (e // 5) * 2
        preview.paste(screen_image(original), (col * 262, row * 246))
        preview.paste(render_background(256, 240, shared, palettes, choice, tiles),
                      (col * 262, (row + 1) * 246))
    preview.save("build/preview_battles.png")
    out.header.append(f"\n#define ENEMY_COUNT {len(battles)}\n")
    out.table("Battle", "battles", battles)

    # --- The font ---
    glyphs = convert_font("art/PressStart2P-Regular.ttf")
    font_preview(glyphs, "build/preview_font.png")
    bank = out.item("Font", "font", [FONT_FIRST, FONT_COUNT, ("glyphs", glyphs)])
    out.header.append(f"\n#define FONT_BANK {bank}\n"
                      f"/* The tile number of the font's first character (the space). */\n"
                      f"#define FONT_TILE {FONT_TILE}\n"
                      "extern const Font font;\n")
    print(f"font: {FONT_COUNT} characters, tiles {FONT_TILE}-255")

    # --- Text boxes: the backdrop's dark purple, a line of its orange, and the
    # font in its pink. These are color slots (1-3) in its palette, palette 0. ---
    fill, ink, line = (backdrop_palette.index(c) + 1 for c in (0x04, 0x25, 0x27))
    bank = out.item("Tiles", "box", [BOX_TILES, ("tiles", box_tiles(fill, line))])
    out.header.append(f"\n/* The battle screen's text boxes (see convert.py). */\n"
                      f"#define BOX_BANK {bank}\n"
                      f"#define BOX_TILE {BOX_TILE}\n"
                      f"#define BOX_FILL {fill}\n"
                      f"#define BOX_INK  {ink}\n"
                      "extern const Tiles box;\n")

    out.write("build/art.c", "build/art.h")
    print("previews: build/preview_{terrain,players,battles}.png (original above NES), "
          "build/preview_font.png")
