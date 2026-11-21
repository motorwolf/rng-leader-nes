/* main.c - main(): where the C part of the game begins.
 *
 * For now (Milestone 3, in progress):
 *   D-pad   walk, one square per step; hold to keep walking
 *   Start   make a new map
 *   A       end a fight (until fights are real, in Milestone 4)
 * The camera follows the player around the map, and random fights happen
 * along the way. */

#include "art.h"

#include "map.h"
#include "mmc1.h"
#include "pad.h"
#include "ppu.h"
#include "rng.h"
#include "screens.h"
#include "scroll.h"

/* Counts frames; startup.s adds one every vblank. "volatile" tells the
 * compiler it can change behind the code's back, so it must re-read it each
 * time instead of assuming it stays the same. */
extern volatile unsigned char frame_count;

/* PPU_MASK settings: show the background and sprites (bits 3 and 4),
 * including in the leftmost 8 pixels (bits 1 and 2). */
#define MASK_SHOW 0x1E

/* Walking: a step of one square (32 pixels) takes WALK_FRAMES frames,
 * moving WALK_SPEED pixels each frame. */
#define WALK_FRAMES 16
#define WALK_SPEED  2

/* The camera keeps the player this many pixels from the screen's top-left
 * corner (square column 3 of 8, row 3 of 7.5), and stops at the map's edges.
 * The screen is 256x240, so it can go as far as the map's size minus that. */
#define CAMERA_LEAD  96
#define CAMERA_MAX_X (MAP_WIDTH * 32 - 256)
#define CAMERA_MAX_Y (MAP_HEIGHT * 32 - 240)

/* Random fights: after each step, a 26 in 256 chance (about 10%, as in the
 * original). Never on the castle square, which will heal the player, or on
 * the item's square, which will have the boss (both Milestone 6). */
#define FIGHT_CHANCE 26

/* The battle art is in the order of the original's enemy list. Number 0 is
 * the boss; random fights pick from the rest. (The original only picked
 * level 1 enemies, which left out the Squash Bug, the one level 10 enemy.
 * Levels never got used, so here it's back in.) */
#define BOSS 0

/* Sleep until the next vblank: the heartbeat every NES game is built on. */
static void wait_frame(void) {
    unsigned char start = frame_count;
    while (frame_count == start) {
        /* Nothing: just wait for the vblank handler to tick the counter. */
    }
}

/* Where the camera goes, along one axis, for a player at p on the map. */
static unsigned int camera_for(unsigned int p, unsigned int max) {
    if (p < CAMERA_LEAD) {
        return 0;
    }
    p -= CAMERA_LEAD;
    return (p > max) ? max : p;
}

/* Draw the whole screen for a new map. Drawing must be off while the
 * graphics chip's memory is rewritten, so the screen goes blank for a
 * moment. */
static void show(unsigned int player_x, unsigned int player_y) {
    wait_frame();                 /* switch off at the start of a frame, not mid-picture */
    PPU_MASK = 0;
    scroll_pause();
    show_overworld(0);
    scroll_load_terrain();
    camera_x = camera_for(player_x, CAMERA_MAX_X);
    camera_y = camera_for(player_y, CAMERA_MAX_Y);
    scroll_draw_all();
    scroll_resume();              /* the vblank handler sets the scroll from now on */

    wait_frame();                 /* switch on at the start of a frame too */
    PPU_MASK = MASK_SHOW;
}

/* A fight with the given enemy. For now just the battle screen, until A is
 * pressed; the fight itself is Milestone 4. */
static void fight(unsigned char enemy) {
    unsigned char buttons, previous;

    wait_frame();
    PPU_MASK = 0;
    scroll_pause();
    show_battle(enemy);
    scroll_home();                /* the battle screen doesn't scroll */
    scroll_resume();
    wait_frame();
    PPU_MASK = MASK_SHOW;

    /* A has to be pressed during the fight, not just still held from
     * before. */
    previous = pad_read();
    for (;;) {
        wait_frame();
        buttons = pad_read();
        if (buttons & ~previous & PAD_A) {
            return;
        }
        previous = buttons;
    }
}

void main(void) {
    unsigned char buttons, previous = 0, pressed;
    unsigned char seeded = 0;
    unsigned int frames = 0;      /* 16 bits, so 65,536 possible seeds, not 256 */

    /* The player: which square they're on, and where they're drawn, in
     * pixels on the map. While walking, the drawn position slides toward the
     * next square; the square changes when the step finishes. */
    unsigned char square_x = START_X, square_y = START_Y;
    unsigned int map_x = START_X * 32u, map_y = START_Y * 32u;
    unsigned char steps_left = 0;
    signed char dir_x = 0, dir_y = 0;
    unsigned char next_x, next_y;

    mmc1_init();

    /* Switch on the vblank interrupt, which starts the frame_count clock. */
    PPU_CTRL = CTRL_SETTINGS;

    /* A first map from the default seed, until the player presses Start. */
    map_generate();
    show(map_x, map_y);
    place_player(map_x - camera_x, map_y - camera_y);

    /* The main loop, once per frame. The vblank handler has just written
     * last frame's queued graphics; now prepare the next frame's. */
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
            square_x = START_X;
            square_y = START_Y;
            map_x = START_X * 32u;
            map_y = START_Y * 32u;
            steps_left = 0;
            show(map_x, map_y);
            place_player(map_x - camera_x, map_y - camera_y);
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
                /* Stay on the map. These are unsigned, so stepping left or up
                 * from 0 wraps around to 255, which the same "<" test
                 * rejects. */
                if (next_x < MAP_WIDTH && next_y < MAP_HEIGHT) {
                    steps_left = WALK_FRAMES;
                }
            }
        }

        /* Mid-step: slide a few pixels toward the next square, and bring the
         * camera along. */
        if (steps_left) {
            map_x += dir_x * WALK_SPEED;
            map_y += dir_y * WALK_SPEED;
            scroll_to(camera_for(map_x, CAMERA_MAX_X), camera_for(map_y, CAMERA_MAX_Y));
            place_player(map_x - camera_x, map_y - camera_y);
            if (--steps_left == 0) {
                square_x = next_x;
                square_y = next_y;

                if (!(square_x == START_X && square_y == START_Y) &&
                    !(square_x == item_x && square_y == item_y) &&
                    rng_byte() < FIGHT_CHANCE) {
                    fight(BOSS + 1 + rng_below(ENEMY_COUNT - 1));
                    show(map_x, map_y);   /* back to the overworld, as it was */
                    place_player(map_x - camera_x, map_y - camera_y);
                }
            }
        }
    }
}
