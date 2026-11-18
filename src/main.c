/* main.c - main(): where the C part of the game begins.
 *
 * For now it's a viewer for the map generator (Milestone 2):
 *   Start   make a new map
 *   D-pad   move the view half a screen (smooth scrolling comes later) */

#include "map.h"
#include "mmc1.h"
#include "pad.h"
#include "ppu.h"
#include "rng.h"
#include "screens.h"

/* Counts frames; startup.s adds one every vblank. "volatile" tells the
 * compiler it can change behind the code's back, so it must re-read it each
 * time instead of assuming it stays the same. */
extern volatile unsigned char frame_count;

/* PPU_CTRL settings: bit 7 = vblank interrupt on, bit 3 = sprite tiles come
 * from the second pattern table ($1000). Background tiles: the first ($0000). */
#define CTRL_SETTINGS 0x88

/* PPU_MASK settings: show the background and sprites (bits 3 and 4),
 * including in the leftmost 8 pixels (bits 1 and 2). */
#define MASK_SHOW 0x1E

/* How far the view can go, in squares: the screen is 8 squares wide and 7.5
 * tall, so the last row of squares is half off screen at the bottom. */
#define CAM_MAX_X (MAP_WIDTH - 8)
#define CAM_MAX_Y (MAP_HEIGHT - 8)
#define CAM_STEP  4

/* Sleep until the next vblank: the heartbeat every NES game is built on. */
static void wait_frame(void) {
    unsigned char start = frame_count;
    while (frame_count == start) {
        /* Nothing: just wait for the vblank handler to tick the counter. */
    }
}

/* Redraw the screen. Drawing must be off while the graphics chip's memory is
 * rewritten, so the screen goes blank for a moment. */
static void show(unsigned char cam_x, unsigned char cam_y) {
    wait_frame();                 /* switch off at the start of a frame, not mid-picture */
    PPU_MASK = 0;
    show_overworld(0, cam_x, cam_y);

    /* Using the mailbox also moves the PPU's scroll position (they share
     * internal wiring), so set the scroll back to the top-left corner. */
    PPU_CTRL = CTRL_SETTINGS;
    PPU_SCROLL = 0;
    PPU_SCROLL = 0;

    wait_frame();                 /* switch on at the start of a frame too */
    PPU_MASK = MASK_SHOW;
}

void main(void) {
    unsigned char cam_x = START_X - 3, cam_y = 0;
    unsigned char buttons, previous = 0, pressed;
    unsigned char seeded = 0;
    unsigned int frames = 0;      /* 16 bits, so 65,536 possible seeds, not 256 */

    mmc1_init();

    /* Switch on the vblank interrupt, which starts the frame_count clock. */
    PPU_CTRL = CTRL_SETTINGS;

    /* A first map from the default seed, until the player presses Start. */
    map_generate();
    show(cam_x, cam_y);

    /* The main loop: once per frame, read the controller and react. */
    for (;;) {
        wait_frame();
        ++frames;
        buttons = pad_read();
        /* Buttons down now that weren't last frame: one press = one step,
         * however long the button is held. (Edge detection.) */
        pressed = buttons & ~previous;
        previous = buttons;

        if (pressed & PAD_START) {
            /* The first press seeds the random numbers with how many frames
             * have passed: a human can't press on an exact 1/60th of a
             * second, so each run gets a different sequence. */
            if (!seeded) {
                rng_seed(frames);
                seeded = 1;
            }
            map_generate();
        } else if (pressed & PAD_RIGHT) {
            cam_x = (cam_x + CAM_STEP > CAM_MAX_X) ? CAM_MAX_X : cam_x + CAM_STEP;
        } else if (pressed & PAD_LEFT) {
            cam_x = (cam_x < CAM_STEP) ? 0 : cam_x - CAM_STEP;
        } else if (pressed & PAD_DOWN) {
            cam_y = (cam_y + CAM_STEP > CAM_MAX_Y) ? CAM_MAX_Y : cam_y + CAM_STEP;
        } else if (pressed & PAD_UP) {
            cam_y = (cam_y < CAM_STEP) ? 0 : cam_y - CAM_STEP;
        } else {
            continue;             /* nothing changed: skip the redraw */
        }
        show(cam_x, cam_y);
    }
}
