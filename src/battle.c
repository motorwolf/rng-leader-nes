/* battle.c - a fight: the battle screen, its log and its menu.
 *
 * The screen (see show_battle in screens.c):
 *   - a log of the last LOG_LINES messages across the top, the newest at
 *     the bottom, like the original's message box;
 *   - a strip at the bottom with the menu (Attack, Run) and the player's HP.
 *     Left and Right move the cursor, A picks.
 *
 * For now (Milestone 4, in progress) Attack only adds a message, and Run
 * ends the fight; the fighting itself comes next. */

#include "battle.h"
#include "pad.h"
#include "ppu.h"
#include "screens.h"
#include "scroll.h"
#include "text.h"
#include "vram.h"

/* The log's text, one line per row, each padded with spaces to the full
 * width so redrawing it also clears what was there. Plus a 0 at the end of
 * each, which text_print() needs. */
static char lines[LOG_LINES][LOG_WIDTH + 1];

/* The menu: which choice the cursor is on. */
#define ATTACK 0
#define RUN    1
static unsigned char choice;

static void log_clear(void) {
    unsigned char i, j;
    for (i = 0; i < LOG_LINES; ++i) {
        for (j = 0; j < LOG_WIDTH; ++j) {
            lines[i][j] = ' ';
        }
        lines[i][LOG_WIDTH] = 0;
    }
}

/* Scroll the log up one line and put the first `length` characters of
 * `text` on the bottom line. Then redraw it: each line is its own batch for
 * the vblank queue, which waits for the last one to go, so this takes 3
 * frames. */
static void log_push(const char *text, unsigned char length) {
    unsigned char i, j;
    for (i = 0; i < LOG_LINES - 1; ++i) {
        for (j = 0; j < LOG_WIDTH; ++j) {
            lines[i][j] = lines[i + 1][j];
        }
    }
    for (j = 0; j < LOG_WIDTH; ++j) {
        lines[LOG_LINES - 1][j] = (j < length) ? text[j] : ' ';
    }
    for (i = 0; i < LOG_LINES; ++i) {
        text_print(1, LOG_Y + i, lines[i]);
    }
}

void log_add(const char *text) {
    unsigned char length, cut;

    while (*text) {
        length = 0;
        while (text[length] && length <= LOG_WIDTH) {
            ++length;
        }
        if (length <= LOG_WIDTH) {          /* the rest fits on one line */
            log_push(text, length);
            return;
        }
        /* Too long: break at the last space that keeps the line within the
         * width, or mid-word if a word is longer than a whole line. */
        cut = LOG_WIDTH;
        while (cut && text[cut] != ' ') {
            --cut;
        }
        if (cut == 0) {
            cut = LOG_WIDTH;
        }
        log_push(text, cut);
        text += cut;
        while (*text == ' ') {
            ++text;
        }
    }
}

/* The strip: a cursor (">") before the current choice, and the HP. */
static void draw_menu(void) {
    static char strip[] = " ATTACK!   RUN AWAY   HP 20/20";
    strip[0]  = (choice == ATTACK) ? '>' : ' ';
    strip[10] = (choice == RUN) ? '>' : ' ';
    text_print(1, MENU_Y, strip);
}

void battle(unsigned char enemy) {
    unsigned char buttons, previous, pressed, i;

    /* Switch to the battle screen, with drawing off. */
    wait_frame();
    PPU_MASK = 0;
    vram_pause();
    show_battle(enemy);
    scroll_home();                  /* the battle screen doesn't scroll */
    log_clear();
    choice = ATTACK;
    draw_menu();                    /* paused, so this is written right away */
    vram_resume();
    wait_frame();
    PPU_MASK = MASK_SHOW;

    log_add("An enemy appears!");

    /* Buttons already held when the fight started don't count as presses. */
    previous = pad_read();
    for (;;) {
        wait_frame();
        buttons = pad_read();
        pressed = buttons & ~previous;
        previous = buttons;

        if (pressed & (PAD_LEFT | PAD_RIGHT)) {
            choice ^= 1;            /* two choices: either direction flips */
            draw_menu();
        } else if (pressed & PAD_A) {
            if (choice == ATTACK) {
                log_add("You attack! The fighting itself comes next.");
            } else {
                log_add("You run away.");
                for (i = 0; i < 60; ++i) {      /* a second to read it */
                    wait_frame();
                }
                return;
            }
        }
    }
}
