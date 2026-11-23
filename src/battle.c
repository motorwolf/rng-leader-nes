/* battle.c - a fight: the battle screen, its log and its menu.
 *
 * The screen (see show_battle in screens.c):
 *   - a log of the last LOG_LINES messages across the top, the newest at
 *     the bottom, like the original's message box;
 *   - a strip at the bottom with the menu (Attack, Run) and the player's HP.
 *     Left and Right move the cursor, A picks.
 *
 * The fighting is ported from the original (Player.attack and
 * startAttackSequence in static/js/game.js), in whole numbers, with four of
 * its bugs fixed:
 *   - a hit could do 0 damage; now it's at least 1;
 *   - a fighter at exactly 0 HP kept fighting; now 0 is dead;
 *   - dying when the enemy struck first showed two death messages;
 *   - misses showed the name in normal case, hits in capitals.
 *
 * The stats come from the original's data files, through tools/data.py.
 *
 * For now: the player is always the Elephant, named HERO. Winning or dying
 * just returns to the map; HP carries over between fights, and dying
 * refills it. Experience, the castle's healing and real death come in
 * Milestones 6 and 7. */

#include <string.h>

#include "art.h"
#include "battle.h"
#include "data.h"
#include "mmc1.h"
#include "pad.h"
#include "rng.h"
#include "ppu.h"
#include "screens.h"
#include "scroll.h"
#include "text.h"
#include "vram.h"

/* The log's text, one line per row, each padded with spaces to the full
 * width so redrawing it also clears what was there. Plus a 0 at the end of
 * each, which text_print() needs. */
static char lines[LOG_LINES][LOG_WIDTH + 1];

/* --- The fighters -------------------------------------------------------- */

/* The enemy table (data.h) is in the battle art's order, so an enemy's
 * number picks both. If the two counts differ, a data file and the art
 * have drifted apart. */
#if ENEMIES != ENEMY_COUNT
#error "data/enemies and the battle art have different numbers of enemies"
#endif

/* The two fighters in this fight, copied out of the data bank, so hp can
 * change and the names can be read with any bank switched in. Fighter 0 is
 * the player, fighter 1 the enemy, so the other one is always `f ^ 1`. */
#define PLAYER 0
#define ENEMY  1
static Stats fighters[2];

/* The player's HP, kept between fights (0 = start afresh), and the most
 * it can be. */
static unsigned char player_hp;
static unsigned char max_hp;

/* --- The menu ------------------------------------------------------------ */

/* Which choice the cursor is on. */
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

/* --- Messages -------------------------------------------------------------- */

/* A message being put together: put_text() and put_number() add to the end,
 * then say() shows it. */
static char message[LOG_WIDTH * 2 + 1];
static char *end;

static void put_text(const char *text) {
    while (*text) {
        *end++ = *text++;
    }
}

/* A number as decimal digits, without leading zeros. */
static void put_number(unsigned char n) {
    if (n >= 100) {
        *end++ = '0' + n / 100;
        n %= 100;
        *end++ = '0' + n / 10;
    } else if (n >= 10) {
        *end++ = '0' + n / 10;
    }
    *end++ = '0' + n % 10;
}

/* Wait this many frames. */
static void wait_frames(unsigned char frames) {
    while (frames--) {
        wait_frame();
    }
}

/* Show the message put together, then pause a moment so it can be read
 * before the next one. */
#define MESSAGE_PAUSE 20
static void say(void) {
    *end = 0;
    log_add(message);
    end = message;
    wait_frames(MESSAGE_PAUSE);
}

/* The strip: a cursor (">") before the current choice, and the HP. Uses
 * the message helpers, so only call it between messages. */
static void draw_menu(void) {
    static char strip[LOG_WIDTH + 1];
    end = strip;
    put_text(choice == ATTACK ? ">ATTACK!  " : " ATTACK!  ");
    put_text(choice == RUN ? ">RUN AWAY  " : " RUN AWAY  ");
    put_text("HP ");
    put_number(fighters[PLAYER].hp);
    *end++ = '/';
    put_number(max_hp);
    while (end < strip + LOG_WIDTH) {
        *end++ = ' ';               /* clear what a longer HP left behind */
    }
    *end = 0;
    end = message;
    text_print(1, MENU_Y, strip);
}

/* --- Fighting ------------------------------------------------------------ */

/* Fighter f attacks the other one. Returns 1 if that kills it. */
static unsigned char attack(unsigned char f) {
    Stats *a = &fighters[f];
    Stats *t = &fighters[f ^ 1];
    unsigned char base, damage;

    /* To hit: a roll of 0 to dex + 19 must beat 2, so the chance of
     * missing is 3 in (dex + 20). */
    if (rng_below(a->dex + 20) <= 2) {
        put_text(a->name);
        put_text(" MISSES!");
        say();
        return 0;
    }

    /* Damage: base = weapon + half the strength, then a roll from base up
     * to 3 x base - 1, minus the target's armor, and at least 1. */
    base = a->weap + (a->str >> 1);
    damage = rng_below(base << 1) + base;
    damage = (damage > t->arm) ? damage - t->arm : 1;

    put_text(a->name);
    put_text(" hits for ");
    put_number(damage);
    put_text(" damage!");
    say();

    if (damage >= t->hp) {
        t->hp = 0;
    } else {
        t->hp -= damage;
    }
    if (f == ENEMY) {
        draw_menu();                /* the player's HP changed */
    }
    if (t->hp == 0) {
        put_text("The death blow has been delivered.");
        say();
        return 1;
    }
    return 0;
}

/* One turn, after the player picks Attack or Run. Returns 1 if the fight
 * is over. */
static unsigned char turn(void) {
    unsigned char first, roll;

    /* Whoever has more dex goes first; a tie goes to the player. */
    first = (fighters[ENEMY].dex > fighters[PLAYER].dex) ? ENEMY : PLAYER;

    if (choice == RUN) {
        /* Getting away: 1 in 10 from a faster enemy, otherwise 3 in 10. If
         * it fails, the enemy gets a free hit. */
        roll = rng_below(10);
        if (first == ENEMY ? roll == 1 : roll < 3) {
            put_text("You've run away!");
            say();
            return 1;
        }
        put_text("You couldn't run away!");
        say();
        return attack(ENEMY);
    }

    /* Attack: 1 time in 10 the slower one gets to go first. Each strikes
     * once, unless the first blow kills. */
    if (rng_below(10) == 1) {
        first ^= 1;
    }
    return attack(first) || attack(first ^ 1);
}

void battle(unsigned char enemy) {
    unsigned char buttons, previous, pressed;

    /* The fighters: for now the player is always an Elephant, named HERO. */
    mmc1_set_bank(DATA_BANK);
    fighters[PLAYER] = classes[CLASS_ELEPHANT];
    fighters[ENEMY] = enemies[enemy].stats;
    strcpy(fighters[PLAYER].name, "HERO");
    max_hp = fighters[PLAYER].hp;
    if (player_hp) {
        fighters[PLAYER].hp = player_hp;
    }
    end = message;

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

    put_text("A ");
    put_text(fighters[ENEMY].name);
    put_text(" draws near.");
    say();

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
            if (turn()) {
                break;
            }
            previous = pad_read();  /* presses made during the turn don't count */
        }
    }

    /* The fight is over. */
    if (fighters[PLAYER].hp == 0) {
        put_text("You are dead.");
        say();
        player_hp = 0;              /* for now, the next fight starts afresh */
    } else {
        if (fighters[ENEMY].hp == 0) {
            put_text("YOU HAVE DEFEATED THE ");
            put_text(fighters[ENEMY].name);
            put_text("!");
            say();
        }
        player_hp = fighters[PLAYER].hp;
    }
    wait_frames(90);                /* a moment to read it */
}
