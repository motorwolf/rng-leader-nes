/* scroll.c - the scrolling camera over the overworld map.
 *
 * The graphics chip holds two nametables (screen-sized grids of tile
 * numbers), set up side by side: a strip 64 tiles (512 pixels) wide. The
 * scroll registers choose which 256-pixel window of it is shown, and the
 * strip wraps around at the right edge back to the left, a circular buffer.
 *
 * The map is 112 tiles wide, too wide for the strip, so it is streamed in:
 * map tile column c lives in strip column c & 63 (c mod 64). As the camera
 * moves, each column about to come into view is written over a column that
 * went out of view long ago. The hardware does the sliding; the code only
 * writes one new column per 8 pixels moved.
 *
 * Writing to the graphics chip is only safe during vblank, which is short
 * (about 2,270 CPU cycles), so the work is split in two: scroll_to()
 * prepares the column during the frame, into a queue, and the vblank handler
 * (nmi in startup.s, in assembly for speed) copies it at the next vblank.
 *
 * For now the camera only moves horizontally: rows 0-29 of the screen show
 * map rows 0-7. */

#include "art.h"
#include "map.h"
#include "mmc1.h"
#include "ppu.h"
#include "scroll.h"

unsigned int camera_x;

/* The vblank queue, in startup.s. */
extern unsigned char ppu_updates_on, scroll_ctrl, scroll_x;
extern unsigned char vram_column[30], vram_column_ready;
extern unsigned int vram_column_addr;
extern unsigned char vram_attributes[8], vram_attributes_ready;
extern unsigned int vram_attribute_addr;

/* The terrain's tables, copied from its bank (see art.h). */
static unsigned char squares[64];           /* 16 tile numbers per square */
static unsigned char square_attributes[4];  /* 1 attribute byte per square */

void scroll_load_terrain(void) {
    unsigned char i;
    mmc1_set_bank(TERRAIN_BANK);
    for (i = 0; i < 64; ++i) {
        squares[i] = terrain.squares[i];
    }
    for (i = 0; i < 4; ++i) {
        square_attributes[i] = terrain.square_attributes[i];
    }
}

/* Which nametable a strip column (0-63) is in: 0-31 the first, 32-63 the
 * second. */
static unsigned int nametable_of(unsigned char strip_column) {
    return (strip_column & 32) ? PPU_NAMETABLE1 : PPU_NAMETABLE0;
}

/* Fill the queue with map tile column `col`: its 30 tiles, top to bottom. */
static void prepare_column(unsigned char col) {
    unsigned char y;
    unsigned char square_x = col >> 2;      /* which square, across */
    unsigned char inside_x = col & 3;       /* which tile column inside it */
    unsigned char strip = col & 63;         /* where it goes in the strip */

    for (y = 0; y < 30; ++y) {
        vram_column[y] = squares[(map[y >> 2][square_x] << 4) | ((y & 3) << 2) | inside_x];
    }
    vram_column_addr = nametable_of(strip) + (strip & 31);
}

/* Fill the queue with the palette bytes of map square column `square_x`.
 * The attribute table is 8x8 bytes at the end of each nametable, one byte
 * per 32x32 block, which is exactly one square. */
static void prepare_attributes(unsigned char square_x) {
    unsigned char y;
    unsigned char strip = (square_x << 2) & 63;

    for (y = 0; y < 8; ++y) {
        vram_attributes[y] = square_attributes[map[y][square_x]];
    }
    vram_attribute_addr = nametable_of(strip) + 0x3C0 + (square_x & 7);
}

void scroll_draw_all(void) {
    unsigned char col, y;
    unsigned char left = camera_x >> 3;

    /* The screen is off, so there's no rush: this writes straight from C,
     * through the same queue arrays, without involving the vblank handler. */
    /* 33 columns: when the camera isn't on a tile boundary, part of a 33rd
     * shows at the right edge. */
    for (col = left; col != (unsigned char)(left + 33); ++col) {
        prepare_column(col);
        PPU_CTRL = CTRL_SETTINGS | CTRL_DOWN;   /* each write moves down a row */
        ppu_set_addr(vram_column_addr);
        ppu_write(vram_column, 30);
        PPU_CTRL = CTRL_SETTINGS;

        if ((col & 3) == 0 || col == left) {
            prepare_attributes(col >> 2);
            for (y = 0; y < 8; ++y) {
                ppu_set_addr(vram_attribute_addr + (y << 3));
                PPU_DATA = vram_attributes[y];
            }
        }
    }
    scroll_to(camera_x);
}

void scroll_to(unsigned int x) {
    unsigned char col;

    if (x > camera_x) {
        /* Moving right: the column under the screen's right edge. If it's
         * new, queue it, plus the palettes when it starts a new square. */
        col = (x + 255) >> 3;
        if (col != (unsigned char)((camera_x + 255) >> 3)) {
            prepare_column(col);
            vram_column_ready = 1;
            if ((col & 3) == 0) {
                prepare_attributes(col >> 2);
                vram_attributes_ready = 1;
            }
        }
    } else if (x < camera_x) {
        /* Moving left: the column under the left edge. */
        col = x >> 3;
        if (col != (unsigned char)(camera_x >> 3)) {
            prepare_column(col);
            vram_column_ready = 1;
            if ((col & 3) == 3) {
                prepare_attributes(col >> 2);
                vram_attributes_ready = 1;
            }
        }
    }
    camera_x = x;

    /* The scroll position, for the vblank handler: the low 8 bits of X, and
     * the 9th bit (which nametable is on the left) as bit 0 of PPU_CTRL. */
    scroll_x = (unsigned char)x;
    scroll_ctrl = CTRL_SETTINGS | ((x >> 8) & 1);
}

void scroll_pause(void) {
    ppu_updates_on = 0;
}

void scroll_resume(void) {
    ppu_updates_on = 1;
}
