/* scroll.c - the scrolling camera over the overworld map.
 *
 * The graphics chip holds two nametables (screen-sized grids of tile
 * numbers, 32 tiles across and 30 down), set up side by side. Together
 * they're a buffer 64 tiles wide and 30 tall that wraps around in both
 * directions, a circular buffer. The scroll registers choose which
 * 256x240 window of it is shown.
 *
 * The map is 112 tiles wide and 64 tall, bigger than the buffer, so it is
 * streamed in. Map tile (column c, row t) lives in buffer column c mod 64 and
 * row t mod 30. As the camera moves, each column or row about to come into
 * view is written over one that went out of view.
 *
 * Writing to the graphics chip is only safe during vblank, which is short
 * (about 2,270 CPU cycles), so the work is split in two: scroll_to()
 * prepares the new tiles during the frame, into a queue, and the vblank
 * handler (nmi in startup.s, in assembly for speed) copies them at the next
 * vblank.
 *
 * Two wrinkles, both from the buffer being 30 rows tall:
 *
 * - Palettes. The attribute table gives one palette per 16x16 area, packed 4
 *   to a byte (32x32). 30 rows isn't a multiple of 4, so once the buffer
 *   wraps, a byte's top and bottom halves can hold rows from different map
 *   squares. So each byte is built from whatever map rows are in its two
 *   halves right now. (30 is a multiple of 2, so each 16x16 half is always
 *   within one square.)
 *
 * - The edge row. While the camera is between tile rows, 31 rows show
 *   (part of the top one, part of the bottom one), but the buffer has 30, so
 *   those two share a buffer row and one of them shows the wrong tiles. It's
 *   only ever the outermost 8 pixels, which old TVs hid under the frame of
 *   the screen ("overscan"); many NES games have the same glitch there. */

#include "art.h"
#include "map.h"
#include "mmc1.h"
#include "ppu.h"
#include "scroll.h"

#define MAP_TILES_X (MAP_WIDTH * 4)     /* 112 */
#define BUFFER_ROWS 30

unsigned int camera_x, camera_y;

/* The vblank queue, in startup.s. */
extern unsigned char ppu_updates_on, scroll_ctrl, scroll_x, scroll_y;
extern unsigned char vram_buffer[96], vram_ready;

/* How much of vram_buffer is filled. */
static unsigned char queued;

/* The terrain's tables, copied from its bank (see art.h). */
static unsigned char squares[64];       /* 16 tile numbers per square */
static unsigned char palette_of[4];     /* the palette (0-3) of each square type */

void scroll_load_terrain(void) {
    unsigned char i;
    mmc1_set_bank(TERRAIN_BANK);
    for (i = 0; i < 64; ++i) {
        squares[i] = terrain.squares[i];
    }
    /* Every terrain square uses one palette throughout, so the low 2 bits of
     * its attribute byte say which. */
    for (i = 0; i < 4; ++i) {
        palette_of[i] = terrain.square_attributes[i] & 3;
    }
}

/* --- The queue ------------------------------------------------------------ */

/* Start a run of `count` bytes at graphics address `addr`; `down` = write
 * down a column instead of across a row. The bytes follow with add(). */
static void run(unsigned int addr, unsigned char count, unsigned char down) {
    vram_buffer[queued++] = down ? (count | 0x80) : count;
    vram_buffer[queued++] = addr >> 8;
    vram_buffer[queued++] = (unsigned char)addr;
}

static void add(unsigned char value) {
    vram_buffer[queued++] = value;
}

/* With the vblank handler on, mark the queue ready for it. With it paused
 * (screen off), write it right away, from C. Either way, start afresh. */
static void send(void) {
    unsigned char i, count, header;

    vram_buffer[queued] = 0;
    if (ppu_updates_on) {
        vram_ready = 1;
    } else {
        i = 0;
        while ((header = vram_buffer[i]) != 0) {
            PPU_CTRL = (header & 0x80) ? (CTRL_SETTINGS | CTRL_DOWN) : CTRL_SETTINGS;
            ppu_set_addr((vram_buffer[i + 1] << 8) | vram_buffer[i + 2]);
            count = header & 0x7F;
            i += 3;
            while (count--) {
                PPU_DATA = vram_buffer[i++];
            }
        }
        PPU_CTRL = CTRL_SETTINGS;
    }
    queued = 0;
}

/* --- Where map tiles go in the buffer -------------------------------------- */

static unsigned int nametable_of(unsigned char buffer_column) {
    return (buffer_column & 32) ? PPU_NAMETABLE1 : PPU_NAMETABLE0;
}

/* The tile number for map tile (col, row). */
static unsigned char tile_at(unsigned char col, unsigned char row) {
    if (col >= MAP_TILES_X) {
        col = MAP_TILES_X - 1;      /* off the map: never shown, any tile will do */
    }
    return squares[(map[row >> 2][col >> 2] << 4) | ((row & 3) << 2) | (col & 3)];
}

/* x mod 30, for the small numbers here (under 90), without dividing. */
static unsigned char mod30(unsigned char x) {
    while (x >= BUFFER_ROWS) {
        x -= BUFFER_ROWS;
    }
    return x;
}

/* Which map tile row is in buffer row r, when the buffer holds map rows
 * top..top+29. */
static unsigned char row_in(unsigned char r, unsigned char top) {
    unsigned char top_mod = mod30(top);
    return top + (r >= top_mod ? r - top_mod : r + BUFFER_ROWS - top_mod);
}

/* One attribute byte: the palettes for buffer attribute row `ar` (buffer
 * tile rows 4ar to 4ar+3) at map square column `square_x`, when the buffer
 * holds map rows top..top+29. Two bits per 16x16 quarter, top-left first:
 * the two top quarters share a palette, and so do the two bottom ones. */
static unsigned char attribute_at(unsigned char square_x, unsigned char ar, unsigned char top) {
    unsigned char upper, lower = 0;
    if (square_x >= MAP_WIDTH) {
        square_x = MAP_WIDTH - 1;   /* off the map: never shown */
    }
    upper = palette_of[map[row_in(ar << 2, top) >> 2][square_x]];
    if (ar < 7) {               /* row 7's bottom half would be rows 30-31: not there */
        lower = palette_of[map[row_in((ar << 2) + 2, top) >> 2][square_x]];
    }
    return upper * 0x05 | lower * 0x50;
}

/* --- Columns and rows ------------------------------------------------------- */

/* Queue map tile column `col`: all 30 buffer rows, holding map rows from
 * `top`. Plus its 8 palette bytes, when it starts a square or `palettes`. */
static void queue_column(unsigned char col, unsigned char top, unsigned char palettes) {
    unsigned char r;
    unsigned char slot = col & 63;
    unsigned char square_x = col >> 2;
    unsigned int base = nametable_of(slot);

    run(base + (slot & 31), BUFFER_ROWS, 1);
    for (r = 0; r < BUFFER_ROWS; ++r) {
        add(tile_at(col, row_in(r, top)));
    }

    if ((col & 3) == 0 || palettes) {
        /* The attribute table is 8x8 bytes at the end of each nametable; a
         * column of it is 8 bytes, 8 apart, so each gets its own run. */
        for (r = 0; r < 8; ++r) {
            run(base + 0x3C0 + (r << 3) + (square_x & 7), 1, 0);
            add(attribute_at(square_x, r, top));
        }
    }
    send();
}

/* Queue map tile row `row` across the 33 columns from `left`, with the
 * buffer holding map rows top..top+29 once it's written. Plus, if
 * `palettes`, the 9 palette bytes of that row's attribute row. */
static void queue_row(unsigned char row, unsigned char left, unsigned char top,
                      unsigned char palettes) {
    unsigned char i, first, slot, block, ar;
    unsigned char r = mod30(row);
    unsigned char col = left;

    /* 33 tiles, which may cross from one nametable into the other: the first
     * run goes to the end of the starting nametable, the second continues at
     * the start of the other one. */
    slot = left & 63;
    first = 32 - (slot & 31);
    run(nametable_of(slot) + (r << 5) + (slot & 31), first, 0);
    for (i = 0; i < first; ++i) {
        add(tile_at(col++, row));
    }
    run(nametable_of(slot ^ 32) + (r << 5), 33 - first, 0);
    for (i = first; i < 33; ++i) {
        add(tile_at(col++, row));
    }

    if (!palettes) {
        send();
        return;
    }

    /* The 9 attribute bytes those 33 columns touch, split the same way. */
    block = left >> 2;
    slot = (block << 2) & 63;
    ar = r >> 2;
    first = 8 - (block & 7);
    run(nametable_of(slot) + 0x3C0 + (ar << 3) + (block & 7), first, 0);
    for (i = 0; i < first; ++i) {
        add(attribute_at(block + i, ar, top));
    }
    run(nametable_of(slot ^ 32) + 0x3C0 + (ar << 3), 9 - first, 0);
    for (i = first; i < 9; ++i) {
        add(attribute_at(block + i, ar, top));
    }
    send();
}

/* --- The camera ----------------------------------------------------------- */

/* Tell the vblank handler where to scroll. X: the low 8 bits, plus the 9th
 * bit (which nametable is on the left) as bit 0 of PPU_CTRL. Y: 0-239,
 * wrapping every 240 pixels, the buffer's height. */
static void set_scroll(void) {
    unsigned int y = camera_y;
    while (y >= 240) {
        y -= 240;
    }
    scroll_x = (unsigned char)camera_x;
    scroll_y = (unsigned char)y;
    scroll_ctrl = CTRL_SETTINGS | ((camera_x >> 8) & 1);
}

void scroll_draw_all(void) {
    unsigned char col;
    unsigned char left = camera_x >> 3;

    /* 33 columns: when the camera isn't on a tile boundary, part of a 33rd
     * shows at the right edge. With the vblank handler paused, send() writes
     * each one straight away. */
    for (col = left; col != (unsigned char)(left + 33); ++col) {
        queue_column(col, camera_y >> 3, col == left);
    }
    set_scroll();
}

void scroll_to(unsigned int x, unsigned int y) {
    unsigned char col, row;

    /* The camera moves along one axis at a time, at most 8 pixels, so at
     * most one new column or row is needed. */
    if (x > camera_x) {
        /* Right: the column under the screen's right edge, if it's new. */
        col = (x + 255) >> 3;
        if (col != (unsigned char)((camera_x + 255) >> 3)) {
            queue_column(col, y >> 3, 0);
        }
    } else if (x < camera_x) {
        /* Left: the column under the left edge. Its palettes are due when
         * it's the last column of a square, entering from the right. */
        col = x >> 3;
        if (col != (unsigned char)(camera_x >> 3)) {
            queue_column(col, y >> 3, (col & 3) == 3);
        }
    } else if (y > camera_y) {
        /* Down: the row under the bottom edge. It takes the buffer row of
         * the top one, so the buffer now holds rows row-29..row.
         *
         * Palettes come in 16x16 areas, two buffer rows tall. When the new
         * row is the first of its pair, the pair is half new, half old (the
         * old one still on screen), so the palettes wait; when it's the
         * second, the pair is all new, and they're written. */
        row = (y + 239) >> 3;
        if (row != (unsigned char)((camera_y + 239) >> 3)) {
            queue_row(row, x >> 3, row - (BUFFER_ROWS - 1), mod30(row) & 1);
        }
    } else if (y < camera_y) {
        /* Up: the row under the top edge, taking the bottom one's place.
         * Coming from below, it's the first of its pair that completes it. */
        row = y >> 3;
        if (row != (unsigned char)(camera_y >> 3)) {
            queue_row(row, x >> 3, row, !(mod30(row) & 1));
        }
    }
    camera_x = x;
    camera_y = y;
    set_scroll();
}

void scroll_pause(void) {
    ppu_updates_on = 0;
}

void scroll_resume(void) {
    ppu_updates_on = 1;
}
