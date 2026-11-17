"""convert.py - turn the original PNG art into NES tile data.

Runs on the development machine at build time, never on the NES. For now it
converts the art and saves before/after previews in build/; a later chunk
writes a file the build links into the ROM.

The steps for one image:
  1. Shrink it back to its true size (one pixel per block; see measure_scale.py).
  2. Replace each colour with the closest colour the NES can show.
  3. Reduce the colours to fit the NES palette rules, which differ for
     sprites (per 8x8 tile, with transparency) and backgrounds (per 16x16
     area, with one colour shared by the whole screen).
  4. Cut the image into 8x8 tiles and encode each as 16 bytes, in the same
     two-plane format as the hand-made tiles in src/main.c.
"""

import random
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


def oklab(colour):
    """Convert an (r, g, b) colour to OKLab, a "perceptual" colour space
    (Bjorn Ottosson, 2020). RGB describes how much each light a screen
    emits; it's a poor measure of how different two colours look, because
    eyes don't respond to the three lights equally or in proportion. In
    OKLab, the same distance means roughly the same visible difference
    anywhere: L is lightness, a runs green to red, b runs blue to yellow."""
    # sRGB values are gamma-encoded; undo that to get actual light amounts.
    r, g, b = (((c / 255 + 0.055) / 1.055) ** 2.4 if c > 10 else c / 255 / 12.92
               for c in colour)
    # Roughly the responses of the eye's three kinds of cone cell...
    l = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
    m = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
    s = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b
    # ...compressed (we notice changes in dim colours more than bright ones)
    l, m, s = l ** (1 / 3), m ** (1 / 3), s ** (1 / 3)
    # ...and recombined into lightness and two colour axes.
    return (0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
            1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
            0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s)


_oklab_cache = {}

# Which way of measuring colour difference to use: "oklab" or "rgb". Set per
# image with use_method(). Neither is right for everything: the NES palette
# has almost no muted colours, so a muted colour is matched either by
# lightness (OKLab: often too saturated) or by plain RGB (often the right hue
# but too light). The choice per image was made by eye, comparing previews.
method = "oklab"


def use_method(name):
    """Switch the colour-difference measure for everything that follows."""
    global method
    method = name


def distance(a, b):
    """How different two (r, g, b) colours look, by the current method."""
    if method == "rgb":
        # Plain RGB distance, weighted: eyes are most sensitive to green and
        # least to blue, so a difference in green counts for more.
        dr, dg, db = a[0] - b[0], a[1] - b[1], a[2] - b[2]
        return 2 * dr * dr + 4 * dg * dg + 3 * db * db
    # OKLab: the squared distance between the two colours in OKLab.
    for c in (a, b):
        if c not in _oklab_cache:
            _oklab_cache[c] = oklab(c)
    pa, pb = _oklab_cache[a], _oklab_cache[b]
    return sum((x - y) ** 2 for x, y in zip(pa, pb))


def closest_nes(colour):
    """The NES colour number that looks most like an (r, g, b) colour.

    One exception: near-blacks become black ($0F). The NES's darkest
    colours are much brighter than the near-black that pixel artists use
    for outlines (#181425 here), so by distance alone an outline would turn
    dark teal. Anything darker than this lightness is meant as black.
    (Only needed with OKLab; weighted RGB already picks black for these.)"""
    if method == "oklab" and oklab(colour)[0] < 0.25:
        return 0x0F
    return min(USABLE, key=lambda n: distance(colour, rgb(NES_RGB[n])))


# --- Encoding ------------------------------------------------------------------

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
# (slot 0). The player never appears in battle, so an enemy may use all 4
# palettes: up to 12 colours, but any one 8x8 piece only 3.
#
# Two stages:
#   1. Within each 8x8 piece, merge colours until it has at most 3.
#   2. Pack the pieces' colour sets into the palettes. A piece that
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


def pack_once(pieces, order, max_palettes, size):
    """One attempt at packing: a greedy first guess, placing pieces in the
    given order, then refined. Returns (palettes, choice)."""
    palettes = []
    choice = [0] * len(pieces)
    for i in order:
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


def total_error(pieces, palettes, choice):
    """How much the whole picture changes with this packing."""
    return sum(fit_cost(piece, palettes[k]) for piece, k in zip(pieces, choice) if piece)


def pack_palettes(pieces, max_palettes=3, size=3, restarts=30):
    """pieces: one Counter of colours per piece. Returns (palettes, choice):
    the palettes as lists of colour numbers, and which palette each piece
    uses.

    k-means only finds the best answer near where it starts; a different
    first guess can settle somewhere better. So it runs several times: once
    with the hardest pieces (most colours) placed first, then with shuffled
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

    attempts = [pack_once(pieces, order, max_palettes, size) for order in orders]
    return min(attempts, key=lambda a: total_error(pieces, *a))


def merge_regions(pixels, corners, size, ignore):
    """Stage 1, for sprites and backgrounds alike: in each size x size
    region (given by its top-left corner), merge colours until at most 3
    remain. Pixels equal to `ignore` (transparent, or the shared background
    colour) don't count. Changes pixels in place and returns one Counter of
    colours per region."""
    pieces = []
    for rx, ry in corners:
        counts = Counter(pixels[y][x] for y in range(ry, ry + size)
                         for x in range(rx, rx + size) if pixels[y][x] != ignore)
        merged = merge_colours(counts, 3)
        pieces.append(Counter({c: 0 for c in merged.values()}) +
                      Counter(merged[c] for c in counts.elements()))
        for y in range(ry, ry + size):
            for x in range(rx, rx + size):
                if pixels[y][x] != ignore:
                    pixels[y][x] = merged[pixels[y][x]]
    return pieces


def convert_sprite(pixels, max_palettes=3):
    """Convert one object (rows of NES colour numbers, None = transparent)
    into 8x8 sprite tiles using up to max_palettes palettes.
    Returns (palettes, choice, tiles)."""
    height, width = len(pixels), len(pixels[0])
    corners = [(tx, ty) for ty in range(0, height, 8) for tx in range(0, width, 8)]

    # Stage 1: at most 3 colours in each piece.
    pieces = merge_regions(pixels, corners, 8, ignore=None)

    # Stage 2: share out the palettes.
    palettes, choice = pack_palettes(pieces, max_palettes)

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


def load_sprite_sheet(path, true_size):
    """Shrink a sheet to its true size, (width, height) in art pixels, and
    map it to NES colours, keeping transparency (None). Returns rows of
    colour numbers.

    NEAREST takes the pixel at the centre of each block. For a clean
    whole-number scale any pixel in the block would do; for players.png,
    which was resized with smoothing (about 11.97x), the centre matters:
    the blur sits at the block edges, and the centres still hold the
    original colours exactly."""
    image = Image.open(path).convert("RGBA")
    image = image.resize(true_size, Image.NEAREST)
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
    palettes, choice, tiles = convert_sprite(pixels, max_palettes=4)
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


# --- Backgrounds: palettes per 16x16 area -----------------------------------
#
# Background tiles differ from sprites in two ways:
#   - They can't be see-through. Slot 0 of every background palette is one
#     colour shared by the whole screen, so each palette has 3 of its own.
#   - Palettes are chosen per 16x16 area (the attribute table), not per tile.
# So the same two stages run on 16x16 areas, with the shared colour left out.

def convert_background(pixels, shared, max_palettes=4):
    """pixels: rows of NES colour numbers; None (transparent) becomes the
    shared colour. Returns (palettes, choice, tiles): palettes of up to 3
    colours (slots 1-3), the palette for each 16x16 area, and the 8x8 tiles,
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


def most_common(rows):
    """The most used colour in an image, ignoring transparency."""
    return Counter(c for row in rows for c in row if c is not None).most_common(1)[0][0]


def save_comparison(sheet, converted, behind, path):
    """Original on top, NES version below, enlarged 4x."""
    out = Image.new("RGB", (sheet.width, sheet.height * 2 + 4), (255, 255, 255))
    out.paste(Image.alpha_composite(Image.new("RGBA", sheet.size, behind + (255,)), sheet), (0, 0))
    out.paste(converted, (0, sheet.height + 4))
    out.resize((out.width * 4, out.height * 4), Image.NEAREST).save(path)


if __name__ == "__main__":
    Path("build").mkdir(exist_ok=True)

    # Backgrounds: the overworld terrain and the battle backdrop. Each is its
    # own screen, so each gets its own 4 background palettes and shared colour.
    for name, true_size, colours in (("terrain", (128, 32), "oklab"),
                                     ("background", (64, 64), "rgb")):
        use_method(colours)
        sheet, rows = load_sprite_sheet(f"art/{name}.png", true_size)
        shared = most_common(rows)
        palettes, choice, tiles = convert_background(rows, shared)
        image = render_background(sheet.width, sheet.height, shared, palettes, choice, tiles)
        print(f"{name}: {len(tiles)} tiles, shared colour ${shared:02X}, palettes: "
              + "  ".join("/".join(f"${c:02X}" for c in p) for p in palettes))
        print(f"  palette per 16x16 area: {choice}")
        save_comparison(sheet, image, rgb(NES_RGB[shared]), f"build/preview_{name}.png")
        print(f"preview: build/preview_{name}.png (original on top, NES below)\n")

    # enemies.png: fifteen 32x32 enemies in a row, at block size 20.
    use_method("rgb")
    sheet, rows = load_sprite_sheet("art/enemies.png", (480, 32))
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

    # players.png: five 32x32 characters, resized with smoothing; the true
    # grid (160 x 32) was found by checking which grid puts every sample
    # point clear of the blurred edges. Players move, so the outline trick
    # can't follow them: black stays in the sprite palettes. On the
    # overworld no enemy is on screen, so a player may use all 4 palettes.
    use_method("oklab")
    sheet, rows = load_sprite_sheet("art/players.png", (160, 32))
    out = Image.new("RGB", (sheet.width, 32 * 2 + 4), (255, 255, 255))
    out.paste(Image.alpha_composite(Image.new("RGBA", sheet.size, backdrop + (255,)), sheet), (0, 0))
    print("\nplayers:  colours before -> after, sprite palettes")
    for e in range(5):
        pixels = [row[e * 32:e * 32 + 32] for row in rows]
        before = len({c for row in pixels for c in row if c is not None})
        palettes, choice, tiles = convert_sprite(pixels, max_palettes=4)
        no_mask = [[False] * 32 for _ in range(32)]
        image = render_enemy(no_mask, palettes, choice, tiles, backdrop)
        out.paste(image, (e * 32, 36))
        after = len(set(image.get_flattened_data()) - {backdrop})
        print(f"  {e:2}: {before:2} -> {after}   "
              + "  ".join("/".join(f"${c:02X}" for c in p) for p in palettes))
    out.resize((out.width * 4, out.height * 4), Image.NEAREST).save("build/preview_players.png")
    print("preview: build/preview_players.png (originals on top, NES below)")
