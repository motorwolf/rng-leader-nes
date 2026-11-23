/* story.c - telling the story: filling in its templates.
 *
 * The templates come from the original's data/story_blocks, where a word
 * between dollar signs is a slot for a value:
 *
 *     $name$ has been tasked with retrieving $regent$'s $item$ ...
 *
 * The original filled them in on the server (Story_Block.format_story in
 * game.py), putting each value in capitals. tools/data.py has already
 * turned each $slot$ into a one-byte code (SLOT_NAME and so on), so here
 * it's one pass: copy the template, and wherever there's a code, copy the
 * value instead. */

#include "data.h"
#include "game.h"
#include "mmc1.h"
#include "story.h"

char story[STORY_SIZE];

/* Where the next character goes. */
static char *end;

static void put(const char *text) {
    while (*text) {
        *end++ = *text++;
    }
}

void story_format(unsigned char block) {
    const char *text;

    /* The templates, items, regents and enemy names are all in the data
     * bank, so it stays switched in for the whole copy. The result is in
     * RAM, so it can be read with any bank. */
    mmc1_set_bank(DATA_BANK);
    end = story;
    for (text = stories[block]; *text; ++text) {
        switch (*text) {
        case SLOT_NAME:
            put(player_name);
            break;
        case SLOT_REGENT:
            put(regents[game_regent]);
            break;
        case SLOT_ITEM:
            put(items[game_item]);
            break;
        case SLOT_KILLER:
            put(enemies[game_killer].stats.name);
            break;
        default:
            *end++ = *text;
        }
    }
    *end = 0;
}
