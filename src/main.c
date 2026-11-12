/* main.c - main(): where the C part of the game begins.
 *
 * For now this only proves the foundation works: the cartridge boots, the
 * MMC1 is set up, and the frame loop ticks. It fills the screen with a single
 * colour. */

#include "mmc1.h"

/* The graphics chip's registers (see startup.s for the full list). */
#define PPU_CTRL (*(volatile unsigned char *)0x2000)
#define PPU_ADDR (*(volatile unsigned char *)0x2006)
#define PPU_DATA (*(volatile unsigned char *)0x2007)

/* Counts frames; startup.s adds one every vblank. "volatile" tells the
 * compiler it can change behind the code's back, so it must re-read it each
 * time instead of assuming it stays the same. */
extern volatile unsigned char frame_count;

/* Sleep until the next vblank: the heartbeat every NES game is built on. */
static void wait_frame(void) {
    unsigned char start = frame_count;
    while (frame_count == start) {
        /* Nothing: just wait for the vblank handler to tick the counter. */
    }
}

void main(void) {
    mmc1_init();

    /* Set the background colour. Palette memory lives inside the graphics
     * chip at $3F00, so: give it the address (high byte, then low byte),
     * then send the value. $1A is a grass green from the NES's fixed set of
     * colours. */
    PPU_ADDR = 0x3F;
    PPU_ADDR = 0x00;
    PPU_DATA = 0x1A;

    /* With drawing switched off, the graphics chip fills the screen with that
     * background colour, unless its address is still pointing into palette
     * memory, in which case it shows that palette entry instead. Point it
     * elsewhere so the screen shows our green. */
    PPU_ADDR = 0x00;
    PPU_ADDR = 0x00;

    /* Switch on the vblank interrupt, which starts the frame_count clock. */
    PPU_CTRL = 0x80;

    /* The game loop. For now it only waits; later, each pass will read the
     * controller, update the game, and queue drawing for the next vblank. */
    for (;;) {
        wait_frame();
    }
}
