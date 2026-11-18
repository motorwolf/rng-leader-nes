/* main.c - main(): where the C part of the game begins.
 *
 * For now it's a viewer for the converted art (Milestone 1):
 *   Start        switch between the overworld and the battle screen
 *   Left/Right   previous or next player (overworld) or enemy (battle) */

#include "art.h"
#include "mmc1.h"
#include "pad.h"
#include "ppu.h"
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

/* Sleep until the next vblank: the heartbeat every NES game is built on. */
static void wait_frame(void) {
    unsigned char start = frame_count;
    while (frame_count == start) {
        /* Nothing: just wait for the vblank handler to tick the counter. */
    }
}

/* Swap to a new screen. Drawing must be off while the graphics chip's memory
 * is rewritten, so the screen goes blank for a moment, as most NES games do
 * between scenes. */
static void show(unsigned char battle, unsigned char which) {
    wait_frame();                 /* switch off at the start of a frame, not mid-picture */
    PPU_MASK = 0;
    if (battle) {
        show_battle(which);
    } else {
        show_overworld(which);
    }

    /* Using the mailbox also moves the PPU's scroll position (they share
     * internal wiring), so set the scroll back to the top-left corner. */
    PPU_CTRL = CTRL_SETTINGS;
    PPU_SCROLL = 0;
    PPU_SCROLL = 0;

    wait_frame();                 /* switch on at the start of a frame too */
    PPU_MASK = MASK_SHOW;
}

void main(void) {
    unsigned char battle = 0, player = 0, enemy = 0;
    unsigned char buttons, previous = 0, pressed;

    mmc1_init();

    /* Switch on the vblank interrupt, which starts the frame_count clock. */
    PPU_CTRL = CTRL_SETTINGS;
    show(0, player);

    /* The game loop: once per frame, read the controller and react. */
    for (;;) {
        wait_frame();
        buttons = pad_read();
        /* Buttons down now that weren't last frame: one press = one step,
         * however long the button is held. (Edge detection.) */
        pressed = buttons & ~previous;
        previous = buttons;

        if (pressed & PAD_START) {
            battle = !battle;
        } else if (pressed & PAD_RIGHT) {
            if (battle) {
                enemy = (enemy == ENEMY_COUNT - 1) ? 0 : enemy + 1;
            } else {
                player = (player == PLAYER_COUNT - 1) ? 0 : player + 1;
            }
        } else if (pressed & PAD_LEFT) {
            if (battle) {
                enemy = (enemy == 0) ? ENEMY_COUNT - 1 : enemy - 1;
            } else {
                player = (player == 0) ? PLAYER_COUNT - 1 : player - 1;
            }
        } else {
            continue;             /* nothing changed: skip the redraw */
        }
        show(battle, battle ? enemy : player);
    }
}
