/* main.c - main(): where the C part of the game begins.
 *
 * For now (Milestone 2, in progress):
 *   D-pad   walk, one square per step; hold to keep walking
 *   Start   make a new map
 * The camera doesn't follow yet: the player stops at the screen's edges. */

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

/* The screen shows 8 squares across and 7.5 down; the half square at the
 * bottom doesn't count as walkable for now. */
#define VIEW_W 8
#define VIEW_H 7

/* Walking: a step of one square (32 pixels) takes WALK_FRAMES frames,
 * moving WALK_SPEED pixels each frame. */
#define WALK_FRAMES 16
#define WALK_SPEED  2

/* The camera: the map square at the screen's top-left corner. Fixed for now,
 * placed so the castle is in view. */
#define CAM_X (START_X - 3)
#define CAM_Y 0

/* Sleep until the next vblank: the heartbeat every NES game is built on. */
static void wait_frame(void) {
    unsigned char start = frame_count;
    while (frame_count == start) {
        /* Nothing: just wait for the vblank handler to tick the counter. */
    }
}

/* Redraw the screen. Drawing must be off while the graphics chip's memory is
 * rewritten, so the screen goes blank for a moment. */
static void show(void) {
    wait_frame();                 /* switch off at the start of a frame, not mid-picture */
    PPU_MASK = 0;
    show_overworld(0, CAM_X, CAM_Y);

    /* Using the mailbox also moves the PPU's scroll position (they share
     * internal wiring), so set the scroll back to the top-left corner. */
    PPU_CTRL = CTRL_SETTINGS;
    PPU_SCROLL = 0;
    PPU_SCROLL = 0;

    wait_frame();                 /* switch on at the start of a frame too */
    PPU_MASK = MASK_SHOW;
}

void main(void) {
    unsigned char buttons, previous = 0, pressed;
    unsigned char seeded = 0;
    unsigned int frames = 0;      /* 16 bits, so 65,536 possible seeds, not 256 */

    /* The player: which square they're on, and where they're drawn on screen
     * in pixels. While walking, the drawn position slides toward the next
     * square; the square changes when the step finishes. */
    unsigned char square_x = START_X, square_y = START_Y;
    unsigned char screen_x = (START_X - CAM_X) << 5;    /* x 32: squares to pixels */
    unsigned char screen_y = (START_Y - CAM_Y) << 5;
    unsigned char steps_left = 0;
    signed char dir_x = 0, dir_y = 0;
    unsigned char next_x, next_y;

    mmc1_init();

    /* Switch on the vblank interrupt, which starts the frame_count clock. */
    PPU_CTRL = CTRL_SETTINGS;

    /* A first map from the default seed, until the player presses Start. */
    map_generate();
    show();
    place_player(screen_x, screen_y);

    /* The main loop: once per frame, read the controller and update. */
    for (;;) {
        wait_frame();
        ++frames;
        buttons = pad_read();
        /* Buttons down now that weren't last frame. (Edge detection.) */
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
            show();
            square_x = START_X;
            square_y = START_Y;
            screen_x = (START_X - CAM_X) << 5;
            screen_y = (START_Y - CAM_Y) << 5;
            steps_left = 0;
            place_player(screen_x, screen_y);
            continue;
        }

        /* Between steps, a held direction starts the next one. This checks
         * buttons (held), not pressed, so holding keeps walking. */
        if (steps_left == 0) {
            dir_x = 0;
            dir_y = 0;
            if (buttons & PAD_UP) {
                dir_y = -1;
            } else if (buttons & PAD_DOWN) {
                dir_y = 1;
            } else if (buttons & PAD_LEFT) {
                dir_x = -1;
            } else if (buttons & PAD_RIGHT) {
                dir_x = 1;
            }
            if (dir_x | dir_y) {
                next_x = square_x + dir_x;
                next_y = square_y + dir_y;
                /* Stay on screen. The casts keep the subtraction 8-bit and
                 * unsigned, so a square left of or above the view comes out
                 * as a big number (-1 wraps around to 255), and one "<"
                 * test rejects both sides at once. */
                if ((unsigned char)(next_x - CAM_X) < VIEW_W &&
                    (unsigned char)(next_y - CAM_Y) < VIEW_H) {
                    steps_left = WALK_FRAMES;
                }
            }
        }

        /* Mid-step: slide a few pixels toward the next square. */
        if (steps_left) {
            screen_x += dir_x * WALK_SPEED;
            screen_y += dir_y * WALK_SPEED;
            place_player(screen_x, screen_y);
            if (--steps_left == 0) {
                square_x = next_x;
                square_y = next_y;
            }
        }
    }
}
