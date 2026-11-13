/* main.c - main(): where the C part of the game begins.
 *
 * For now this proves the foundation works: the cartridge boots, the MMC1 is
 * set up, tiles are copied into graphics RAM, and a background made of those
 * tiles is drawn. The tiles are hand-made placeholders; the real art arrives
 * in Milestone 1. */

#include "mmc1.h"
#include "ppu.h"

/* Counts frames; startup.s adds one every vblank. "volatile" tells the
 * compiler it can change behind the code's back, so it must re-read it each
 * time instead of assuming it stays the same. */
extern volatile unsigned char frame_count;

/* --- Placeholder tiles --------------------------------------------------
 *
 * Each 8x8 tile is 16 bytes, stored as two layers ("planes") of 8 bytes, one
 * byte per row, leftmost pixel in the highest bit:
 *   plane 0: the low bit of every pixel's colour number
 *   plane 1: the high bit
 * A pixel's colour number (0-3) = plane 0 bit + 2 x plane 1 bit, and picks
 * one of the 4 colours in the palette below.
 */

#define TILE_BLANK 0
#define TILE_GRASS 1
#define TILE_TREE  2

static const unsigned char tiles[] = {
    /* Tile 0: blank. Graphics RAM wakes up full of random bits on real
     * hardware, so even "nothing" has to be written out. */
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,

    /* Tile 1: grass. Colour 0 (the field) with a few blades in colour 1.
     *   ........   0x00
     *   ..1.....   0x20
     *   .1.1....   0x50
     *   ........   0x00
     *   .....1..   0x04
     *   ....1.1.   0x0A
     *   ........   0x00
     *   ........   0x00
     * Only colours 0 and 1 are used, so plane 1 is all zeros. */
    0x00, 0x20, 0x50, 0x00, 0x04, 0x0A, 0x00, 0x00,   /* plane 0 */
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,   /* plane 1 */

    /* Tile 2: tree. Leaves in colour 2, trunk in colour 3.
     *   ...22...   plane 0: 0x00   plane 1: 0x18
     *   ..2222..            0x00            0x3C
     *   .222222.            0x00            0x7E
     *   .222222.            0x00            0x7E
     *   ..2222..            0x00            0x3C
     *   ...33...            0x18            0x18
     *   ...33...            0x18            0x18
     *   ........            0x00            0x00
     * Colour 2 = binary 10: plane 1 only. Colour 3 = binary 11: both planes. */
    0x00, 0x00, 0x00, 0x00, 0x00, 0x18, 0x18, 0x00,   /* plane 0 */
    0x18, 0x3C, 0x7E, 0x7E, 0x3C, 0x18, 0x18, 0x00,   /* plane 1 */
};

/* Background palette 0. Entries are numbers from the NES's fixed set of
 * colours; the console can't display arbitrary RGB values. */
static const unsigned char palette[4] = {
    0x1A,   /* colour 0: field green (also the backdrop behind everything) */
    0x2A,   /* colour 1: light green grass blades */
    0x0A,   /* colour 2: dark green leaves */
    0x07,   /* colour 3: brown trunk */
};

/* Sleep until the next vblank: the heartbeat every NES game is built on. */
static void wait_frame(void) {
    unsigned char start = frame_count;
    while (frame_count == start) {
        /* Nothing: just wait for the vblank handler to tick the counter. */
    }
}

/* Fill the first nametable (the 32x30 grid of tile numbers) with grass and a
 * scatter of trees. The scatter is a fixed pattern from a little arithmetic,
 * not random; real random maps come in Milestones 2 and 3. */
static void draw_field(void) {
    unsigned char x, y;
    unsigned int mix;

    ppu_set_addr(PPU_NAMETABLE0);
    for (y = 0; y < 30; ++y) {
        for (x = 0; x < 32; ++x) {
            /* Scramble x and y together so the trees don't line up in rows or
             * diagonals (simpler formulas did). Multiplying overflows past
             * 16 bits and wraps around, which is fine: we only keep 3 bits.
             * ">> 3 & 7" picks bits 3-5; one value in 8 becomes a tree. */
            mix = ((x * 37u) ^ (y * 91u)) * 29u;
            if (((mix >> 3) & 7) == 0) {
                PPU_DATA = TILE_TREE;
            } else {
                PPU_DATA = TILE_GRASS;
            }
        }
    }

    /* The attribute table follows the grid: 64 bytes that choose which of
     * the 4 background palettes each 16x16 pixel block uses. This is where
     * the "only 4 colours per 16x16 area" limit comes from. All 0: palette 0. */
    ppu_fill(0, 64);
}

void main(void) {
    mmc1_init();

    /* Drawing is still off from startup, so the PPU is free to receive data. */

    ppu_set_addr(PPU_TILES);
    ppu_write(tiles, sizeof(tiles));        /* 3 tiles x 16 bytes into graphics RAM */

    ppu_set_addr(PPU_PALETTES);
    ppu_write(palette, sizeof(palette));

    draw_field();

    /* Switch on the vblank interrupt, which starts the frame_count clock. */
    PPU_CTRL = 0x80;

    /* Using the mailbox also moves the PPU's scroll position (they share
     * internal wiring), so set the scroll back to the top-left corner. */
    PPU_SCROLL = 0;
    PPU_SCROLL = 0;

    /* Turn drawing on at the start of a frame, so the first frame is whole. */
    wait_frame();
    PPU_MASK = 0x0A;   /* bit 3: show the background; bit 1: including the leftmost 8 pixels */

    /* The game loop. For now it only waits; later, each pass will read the
     * controller, update the game, and queue drawing for the next vblank. */
    for (;;) {
        wait_frame();
    }
}
